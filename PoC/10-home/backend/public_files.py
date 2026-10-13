"""Public agency inventory and statutory area codes; stock is never a policy delivery."""
import csv
import hashlib
import io
import re
import zipfile
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup
from .api_samples import base, today
from .collectors import clean, integer

SH_DOWNLOAD='https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do'
CODES_DOWNLOAD='https://www.code.go.kr/etc/codeFullDown.do'
NS={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def xlsx_rows(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        strings=[''.join(t.text or '' for t in n.findall('.//x:t',NS)) for n in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('x:si',NS)] if 'xl/sharedStrings.xml' in archive.namelist() else []
        rows=[]
        for row in ET.fromstring(archive.read('xl/worksheets/sheet1.xml')).findall('x:sheetData/x:row',NS):
            values={}
            for cell in row:
                text=cell.findtext('x:v','',NS)
                if cell.get('t')=='s':text=strings[int(text)]
                elif cell.get('t')=='inlineStr':text=''.join(cell.find('x:is',NS).itertext())
                values[re.sub(r'\d','',cell.get('r',''))]=clean(text)
            rows.append(values)
        return rows


def excel_day(value):
    if not value:return None
    if re.fullmatch(r'\d+(?:\.\d+)?',value):
        return (datetime(1899,12,30)+timedelta(days=float(value))).date().isoformat()
    match=re.fullmatch(r'(\d{4})[-./](\d{1,2})[-./](\d{1,2})',value)
    if not match:raise ValueError('SH 입주개시일 형식 변경')
    return datetime(*map(int,match.groups())).date().isoformat()


def parse_sh_stock(content,source,year,version_date,evidence):
    rows=xlsx_rows(content)
    if not rows or rows[0].get('B')!='단지명' or rows[0].get('D') not in ('세대수','임대세대수'):
        raise ValueError('SH 관리현황 표 제목 변경')
    records=[];seen=set();excluded=0
    for row in rows[1:]:
        city,name,tenure,address=(row.get(k,'') for k in ('A','B','C','F'))
        if not name and not city:continue
        if not city.endswith('구') or city in ('계','합계'):
            excluded+=1;continue
        if not name or not address:raise ValueError('SH 관리단지 이름·주소 누락')
        identifier=f'{year}:'+hashlib.sha256('|'.join([city,name,tenure,address]).encode()).hexdigest()[:24]
        if identifier in seen:raise ValueError('SH 관리현황 단지·유형·주소 중복')
        seen.add(identifier)
        payload=base(source,'agency_stock',name,'서울특별시',f'서울특별시 {city} {address}',version_date)
        payload.update(units=integer(row.get('D')),municipality=city,tenure=tenure,agency='SH',dataset_year=year,
            source_object_id=identifier,source_date_label='파일 공개·수정일',evidence_url=evidence,
            dataset_version=version_date,stock_basis=rows[0]['D'],
            unit_basis=f'{year}년 공개본 관리 {rows[0]["D"]} · 신규 정책 공급실적 아님',
            dates={'단지 입주개시일':excel_day(row.get('E',''))},warnings=['AGENCY_STOCK_NOT_SUPPLY'],
            stage_label='SH 관리 단지 · 정책 연결 검토 자료')
        records.append(('agency_stock',identifier,payload))
    if not records:raise ValueError('SH 주택관리 현황 행 미확보')
    return records,dict(records=len(records),excluded_rows=excluded,complete_query=True,
        total_stock_units=sum(r[2]['units'] or 0 for r in records),stock_basis=rows[0]['D'])


def collect_sh_files(source,fetcher):
    soup=BeautifulSoup(fetcher.get(source['url']),'html.parser');versions={}
    for anchor in soup.select('a[href]'):
        match=re.fullmatch(r"javascript:downloadFile\('(\d+)'\);?",anchor['href'])
        title=anchor.get('title','');year=re.search(r'(202[456]|24년)',title)
        if not match or not year or '.xlsx' not in title.lower():continue
        cells=anchor.find_parent('tr').find_all('td');stamp=next((clean(c.get_text()) for c in cells if re.fullmatch(r'\d{4}\.\d{2}\.\d{2}\.',clean(c.get_text()))),None)
        if not stamp:raise ValueError('SH 공개 파일 수정일 미확인')
        version_date=stamp.strip('.').replace('.','-');value=2024 if year[1]=='24년' else int(year[1])
        versions[value]=(match[1],version_date)
    if set(versions)!={2024,2025,2026}:raise ValueError('SH 관리 현황 2024~2026 공개본 누락')
    records=[];stats=[]
    for year,(seq,stamp) in sorted(versions.items()):
        params=dict(infId='OA-12027',infSeq='3',seq=seq)
        evidence=SH_DOWNLOAD+f'?infId=OA-12027&infSeq=3&seq={seq}'
        current,meta=parse_sh_stock(fetcher.get(SH_DOWNLOAD,'xlsx',params=params),source,year,stamp,evidence)
        records.extend(current);stats.append(dict(meta,version=stamp,year=year))
    latest=max(v['version'] for v in stats)
    for _,_,payload in records:
        payload.update(latest_dataset_version=latest,is_latest_dataset=payload['dataset_version']==latest)
    return records,dict(dataset_versions=stats,complete_query=True,complete_population=False,
        latest_dataset_version=max(v['version'] for v in stats),period_start='2024',period_end='2026',
        scope_note='공개 XLSX 3개 판본 전체 관리 단지. 판본간 호수 합산 금지. 2026 임대세대수와 이전 세대수는 지표 차이도 확인 필요')


def parse_gh_stock(content,source,evidence):
    try:text=content.decode('utf-8-sig')
    except UnicodeDecodeError:text=content.decode('cp949')
    rows=list(csv.DictReader(io.StringIO(text)));records=[];seen=set()
    if not rows or '매입임대주택명' not in rows[0] or '공급물량(세대)' not in rows[0]:
        raise ValueError('GH 매입임대 CSV 제목 변경')
    for row in rows:
        name,address=clean(row['매입임대주택명']),clean(row['소재지도로명주소'])
        identifier=hashlib.sha256((name+'|'+address).encode()).hexdigest()[:24]
        if not address.startswith('경기도 ') or not name or identifier in seen:raise ValueError('GH 매입임대 지역·중복 오류')
        seen.add(identifier)
        stamp=clean(row['데이터확인일']);datetime.strptime(stamp,'%Y-%m-%d')
        payload=base(source,'agency_stock',name,'경기도',address,stamp)
        lat,lng=float(row['위도']),float(row['경도'])
        if not (36.8<lat<38.4 and 126.3<lng<128):raise ValueError('GH 매입임대 좌표 범위 오류')
        payload.update(units=integer(row['공급물량(세대)']),municipality=address.split()[1],agency='GH',
            dataset_year=int(stamp[:4]),dataset_version=stamp,latest_dataset_version=stamp,is_latest_dataset=True,source_object_id=identifier,lat=lat,lng=lng,
            source_date_label='데이터 확인일',evidence_url=evidence,source_note=clean(row.get('비고')),
            unit_basis='재건축 매입임대 확보 물량 · 신규 정책 준공·입주 실적 아님',
            dates={},warnings=['AGENCY_STOCK_NOT_SUPPLY'],stage_label='GH 재건축 매입임대 현황')
        records.append(('agency_stock',identifier,payload))
    return records,dict(provided=len(rows),fetched=len(rows),complete_query=True,complete_population=False,
        source_base_date=max(r[2]['source_date'] for r in records),stock_units=sum(r[2]['units'] for r in records),
        scope_note='공식 CSV 전체 매입임대 단지. 확보 물량은 별도 재고 지표이며 정부 신축 공급 실적에 합산하지 않음')


def collect_gh_files(source,fetcher):
    text=fetcher.get(source['url']).decode('utf-8','replace')
    match=re.search(r'"contentUrl"\s*:\s*"(https://www\.data\.go\.kr/cmm/cmm/fileDownload\.do\?[^"\s]+)"',text)
    if not match:raise ValueError('GH 공개 CSV 다운로드 링크 미확보')
    return parse_gh_stock(fetcher.get(match[1],'csv'),source,match[1])


def parse_legal_dongs(content,source):
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        names=[n for n in z.namelist() if n.endswith('.txt')]
        if len(names)!=1:raise ValueError('법정동 코드 파일 구성 변경')
        text=z.read(names[0]).decode('cp949')
    records=[];seen=set()
    for row in csv.DictReader(io.StringIO(text),delimiter='\t'):
        code,name,status=row.get('법정동코드',''),row.get('법정동명',''),row.get('폐지여부','')
        if status!='존재' or code[:2] not in source.get('region_prefixes',('11','41')) or code[5:]=='00000':continue
        if not re.fullmatch(r'\d{10}',code) or code in seen:raise ValueError('법정동 코드 형식·중복 오류')
        seen.add(code)
        payload=base(source,'legal_dong',name,name.split()[0],name)
        payload.update(source_object_id=code,sigungu_code=code[:5],bjdong_code=code[5:],
            code_status=status,stage_label='현존 법정동 · API 수집 범위',units=None,unit_basis='행정코드 · 공급 물량 아님')
        records.append((source.get('code_kind','legal_dong'),code,payload))
    if len(records)<source.get('minimum_codes',2000):raise ValueError('요청 범위 법정동 전체 파일 누락')
    return records,dict(provided=len(records),fetched=len(records),complete_query=True,complete_population=False,
        region_counts={r:dict(matching_records=sum(x[2]['region']==r for x in records),fetched=sum(x[2]['region']==r for x in records),complete_query=True) for r in ('서울특별시','경기도')},
        scope_note='행정표준코드 전체 파일의 서울·경기 현존 동·읍·면·리. 전체 주택사업 확보와 구분')


def collect_legal_dongs(source,fetcher):
    return parse_legal_dongs(fetcher.get(CODES_DOWNLOAD,'zip',params={'codeseId':'법정동코드'}),source)
