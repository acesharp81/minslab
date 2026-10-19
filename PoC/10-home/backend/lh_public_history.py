"""Official LH historical files; announcement supply, planned move-in and stock stay separate."""
import csv
import hashlib
import io
import re
import zipfile
from collections import Counter
from datetime import datetime
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup
from .api_samples import base
from .collectors import clean, integer, GYEONGGI_CITIES
from .public_files import xlsx_rows

HP={'hp':'http://www.hancom.co.kr/hwpml/2011/paragraph'}
W={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
SEOUL_NAMES='서울 관악 강동 면목 강서 금천 번동 수서 잠실'.split()
CAPITAL_REGIONS=('서울특별시','경기도','인천광역시')


def identity(*values):
    return hashlib.sha256('|'.join(map(str,values)).encode()).hexdigest()[:24]


def address_area(address):
    match=re.match(r'^(서울특별시|서울|경기도|경기|인천광역시|인천)\s+(\S+)',address)
    if not match:return None,None
    region=next(r for r in CAPITAL_REGIONS if r.startswith(match[1][:2]))
    return region,match[2]


def name_area(name):
    # A regional headquarters is NOT the location. Ambiguous Wirye/Gwangju stays unlocated.
    compact=re.sub(r'\s','',name)
    # Explicit city in the district name, not the responsible LH headquarters.
    if compact.startswith('인천'):return '인천광역시',None
    if any(compact.startswith(n) for n in SEOUL_NAMES):return '서울특별시',None
    if compact.startswith('경기'):compact=compact[2:]
    city=next((c for c in GYEONGGI_CITIES if c!='광주' and compact.startswith(c)),None)
    return ('경기도',city+('군' if city in ('연천','가평','양평') else '시')) if city else (None,None)


def attachments(source,fetcher):
    soup=BeautifulSoup(fetcher.get(source['url']),'html.parser');files=[]
    for a in soup.select('a[href]'):
        if not a['href'].startswith('/boardDownload.es?'):continue
        label=clean(a.parent.parent.get_text(' ',strip=True))
        files.append((label,urljoin(source['url'],a['href'])))
    if not files:raise ValueError('LH 공개 첨부파일 미확보')
    return files


def parse_supply(content,source,evidence):
    rows=xlsx_rows(content)
    header=next((i for i,r in enumerate(rows) if r.get('A')=='공급년도'),None)
    if header is None or [rows[header].get(c) for c in 'BCDEFGHI']!=['사업지구','블록','시도','주소','공급유형','세대수','모집공고일','최초입주시기']:
        raise ValueError('LH 공공분양 공급현황 제목 변경')
    stamp=re.search(r'기준일:\s*(\d{2})\.(\d{2})\.(\d{2})',' '.join(v for r in rows[:header] for v in r.values()))
    if not stamp:raise ValueError('LH 공급현황 기준일 미확인')
    version=datetime(2000+int(stamp[1]),int(stamp[2]),int(stamp[3])).date().isoformat()
    records=[];seen=set();national=0
    for r in rows[header+1:]:
        if not re.fullmatch(r'20\d{2}',r.get('A','')):continue
        national+=1
        if r.get('D') not in CAPITAL_REGIONS:continue
        year=int(r['A']);region,city=address_area(r.get('E',''))
        if region!=r['D']:raise ValueError('LH 공급현황 소재지·시도 불일치')
        day=datetime.strptime(r['H'],'%Y%m%d').date().isoformat()
        if int(day[:4])!=year:raise ValueError('LH 공급년도·모집공고일 불일치')
        month=r.get('I','');movein=None
        undecided=bool(re.search(r'미정|미확정|추후',month))
        if month and not undecided:
            parsed=datetime.strptime(month,'%Y%m');movein=parsed.strftime('%Y-%m')
        identifier=identity(year,r['B'],r['C'],r['F'],day)
        if identifier in seen:raise ValueError('LH 공급현황 사업·블록·공고 중복')
        seen.add(identifier);units=integer(r.get('J'));total=integer(r.get('G'))
        if units is None or total is None or units>total:raise ValueError('LH 공급유형별 호수·세대수 오류')
        p=base(source,'lh_supply',f"{r['B']} {r['C']} · {r['F']}",region,r['E'],day)
        p.update(source_object_id=identifier,sample_mode='PUBLIC_FILE',agency='LH',municipality=city,
            district_name=r['B'],block=r['C'],housing_type=r['F'],units=units,total_units=total,dataset_year=year,
            dataset_version=version,is_latest_dataset=True,latest_dataset_version=version,
            source_date_label='모집공고일 · 공급년도 기준',move_in_plan_month=movein,move_in_raw=month,
            unit_basis='공급유형별 합계(공고 공급호수) · 총세대수·실입주량과 구분',
            stage_label='LH 공공분양 공고 공급현황 · 실입주 검증 전',
            dates={'모집공고일':day,'최초입주시기 (원천, 예정 포함)':movein},evidence_url=evidence,
            warnings=['ANNOUNCEMENT_NOT_OCCUPANCY']+(['MOVE_IN_UNDETERMINED'] if undecided else []),native_fields=r)
        records.append(('lh_supply',identifier,p))
    if not records:raise ValueError('LH 수도권 과거 공급현황 행 미확보')
    return records,dict(provided=len(records),fetched=len(records),complete_query=True,complete_population=False,
        national_records=national,source_base_date=version,period_start=min(p[2]['source_date'] for p in records),
        period_end=max(p[2]['source_date'] for p in records),year_counts=dict(Counter(p[2]['dataset_year'] for p in records)),
        region_counts=dict(Counter(p[2]['region'] for p in records)),
        scope_note='공개 XLSX의 서울·경기·인천 공급유형별 합계. 공고 공급량이며 실제 입주·준공량이 아님')


def collect_supply(source,fetcher):
    files=[f for f in attachments(source,fetcher) if '.xlsx' in f[0].lower() and '공공분양' in f[0]]
    if len(files)!=1:raise ValueError('LH 공공분양 공개 XLSX 구성 변경')
    return parse_supply(fetcher.get(files[0][1],'xlsx'),source,files[0][1])


def movein_rows(content):
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        if 'word/document.xml' in z.namelist():
            root=ET.fromstring(z.read('word/document.xml'))
            # Word's AlternateContent fallback repeats every PDF-converted text box.
            for parent in root.iter():
                for child in list(parent):
                    if child.tag=='{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback':parent.remove(child)
            tokens=[clean(n.text) for n in root.findall('.//w:t',W) if clean(n.text)]
            text=' '.join(tokens);rows=[]
            for i,t in enumerate(tokens):
                if re.fullmatch(r'20\d{2}-\d{2}',t) and i>=5:
                    r=tokens[i-5:i+1]
                    if re.fullmatch(r'\d[\d,]*',r[-2]) and re.search(r'以下|이하|초과',r[2]):rows.append(r)
            return rows,text
        sections=sorted(n for n in z.namelist() if re.fullmatch(r'Contents/section\d+\.xml',n))
        if not sections:raise ValueError('LH 입주계획 HWPX 본문 미확보')
        rows=[];texts=[]
        for name in sections:
            root=ET.fromstring(z.read(name));texts.extend(clean(t.text) for t in root.findall('.//hp:t',HP))
            for tr in root.findall('.//hp:tr',HP):
                vals=[clean(''.join(t.text or '' for t in c.findall('.//hp:t',HP))) for c in tr.findall('hp:tc',HP)]
                if len(vals)==6 and re.fullmatch(r'20\d{2}-\s*\d{2}',vals[-1]):
                    vals[-1]=re.sub(r'\s','',vals[-1]);rows.append(vals)
        return rows,' '.join(texts)


def parse_movein(content,source,year,evidence,supply_lookup=None):
    rows,text=movein_rows(content);match=re.search(r'(?:20\d{2}\s*년\s*주택\s*입주계획).*?(\d[\d,]{3,})',text)
    if not rows or not match:raise ValueError('LH 입주계획 본문·전국 총계 미확인')
    published_total=integer(match[1]);national_total=sum(integer(r[4]) for r in rows)
    records=[];unknown=0;seen=Counter();lookup=supply_lookup or {}
    for r in rows:
        name,block,area,tenure,units,month=r
        if int(month[:4])!=year:raise ValueError('LH 입주계획 파일 연도·입주월 불일치')
        region,city=name_area(name);address=''
        supplied=lookup.get((re.sub(r'\s','',name),re.sub(r'[-\s]','',block).upper()))
        if supplied:region,city,address=supplied['region'],supplied.get('municipality'),supplied['address']
        if not region:unknown+=1;continue
        units=integer(units)
        core=identity(year,name,block,area,tenure,units,month);seen[core]+=1;identifier=f'{core}:{seen[core]}'
        p=base(source,'lh_movein_plan',f'{name} {block} · {tenure} {area}㎡',region,address or name,month)
        p.update(source_object_id=identifier,sample_mode='PUBLIC_FILE',agency='LH',district_name=name,block=block,
            municipality=city,units=units,dataset_year=year,dataset_version=str(year),housing_type=tenure,
            unit_basis='연간 입주계획 호수 · 실제 입주실적 아님',move_in_plan_month=month,schedule_month=month,
            source_date_label='입주 예정월 · 해당 연도 공개계획',stage_label='LH 과거·현재 입주 예정계획',
            source_note='주소 없는 자료는 지구명으로 위치 범위를 검증. 본부 관할로 시도를 배정하지 않음',
            dates={'입주 예정월':month},warnings=['PLAN_NOT_ACTUAL'],evidence_url=evidence)
        if published_total!=national_total:p['warnings'].append('SOURCE_TOTAL_MISMATCH')
        records.append(('lh_movein_plan',identifier,p))
    if not records:raise ValueError('LH 수도권 입주계획 행 미확보')
    return records,dict(year=year,records=len(records),complete_query=True,complete_population=False,
        national_detail_rows=len(rows),national_published_units=published_total,national_detail_units=national_total,
        summary_matches_details=published_total==national_total,unlocated_or_outside_rows=unknown,
        region_counts=dict(Counter(r[2]['region'] for r in records)),
        scope_units=sum(r[2]['units'] for r in records))


def collect_movein(source,fetcher,service):
    lookup={}
    for p in service.rows('lh_supply'):
        lookup[(re.sub(r'\s','',p['district_name']),re.sub(r'[-\s]','',p['block']).upper())]=p
    files=[]
    for label,url in attachments(source,fetcher):
        m=re.search(r'(20\d{2})',label)
        if m and ('입주계획' in label) and re.search(r'\.(hwpx|docx)',label,re.I):files.append((int(m[1]),url,'hwpx' if '.hwpx' in label else 'docx'))
    if not files:raise ValueError('LH 연도별 입주계획 공개 첨부 미확보')
    records=[];versions=[]
    for year,url,suffix in sorted(files):
        current,stats=parse_movein(fetcher.get(url,suffix),source,year,url,lookup);records.extend(current);versions.append(stats)
    latest=max(v['year'] for v in versions)
    for _,_,payload in records:
        payload.update(latest_dataset_version=str(latest),is_latest_dataset=payload['dataset_year']==latest)
    return records,dict(dataset_versions=versions,complete_query=True,complete_population=False,
        period_start=min(v['year'] for v in versions),period_end=max(v['year'] for v in versions),
        missing_years=[y for y in range(2018,max(v['year'] for v in versions)+1) if y not in {v['year'] for v in versions}],
        region_counts=dict(Counter(p[2]['region'] for p in records)),
        scope_note='공식 첨부 전체 입주계획. 실제 소재지 확인되는 서울·경기·인천 지구 포함. 원천 총계·상세 불일치는 별도 표시')


def parse_stock(content,source,evidence,version):
    try:text=content.decode('utf-8-sig')
    except UnicodeDecodeError:text=content.decode('cp949')
    rows=list(csv.DictReader(io.StringIO(text)));records=[];seen=set();missing_location=0;excluded=0
    if not rows or not {'단지코드','단지명','세대수','주소','준공일','입주지정시작일','입주지정종료일'}<=set(rows[0]):raise ValueError('LH 단지정보 CSV 제목 변경')
    for r in rows:
        address=clean(r['주소']);name=clean(r['단지명']);code=clean(r['단지코드'])
        if re.search(r'공공리모델링|기존주택매입|아파트형공장',name+' '+clean(r.get('주택유형'))) or re.search(r'서울시청|경기도청|본관동',address):excluded+=1;continue
        region,city=address_area(address)
        if not region and not address:region,city=name_area(name)
        if not region:missing_location+=1;continue
        if not code or code in seen:raise ValueError('LH 단지코드 중복·누락')
        seen.add(code);dates={}
        for key in ('준공일','입주지정시작일','입주지정종료일'):
            v=clean(r[key]);dates[key]=datetime.strptime(v,'%Y-%m-%d').date().isoformat() if v else None
        event=dates['입주지정시작일'] or dates['준공일']
        p=base(source,'lh_stock',name,region,address or name,event or version)
        p.update(source_object_id=code,sample_mode='PUBLIC_FILE',agency='LH',municipality=city,units=integer(r['세대수']),
            dataset_year=int(version[:4]),dataset_version=version,latest_dataset_version=version,is_latest_dataset=True,
            housing_type=clean(r.get('주택유형')),tenure=clean(r.get('임대유형')),unit_basis='현재 단지정보의 세대수 · 과거 연간 신규 공급량 아님',
            stock_basis='단지 세대수 (상가 포함 유형은 원천 별도 검토)',source_date_label='입주지정 시작일 또는 준공일 (예정 포함)' if event else '공개본 기준일 · 단지 일정 미제공',
            stage_label='LH 단지정보 · 과거 준공·입주지정 일정 검토',dates=dates,evidence_url=evidence,warnings=['AGENCY_STOCK_NOT_SUPPLY'],native_fields=r)
        if not address:p['warnings'].append('ADDRESS_MISSING')
        if p['units']==0:p['warnings'].append('ZERO_STOCK_UNITS_UNVERIFIED')
        records.append(('lh_stock',code,p))
    if not records:raise ValueError('LH 수도권 단지정보 미확보')
    dated=[p[2]['source_date'] for p in records if p[2]['dates']['입주지정시작일'] or p[2]['dates']['준공일']]
    return records,dict(provided=len(records),fetched=len(records),complete_query=True,complete_population=False,
        national_records=len(rows),excluded_nonresidential_or_aggregate=excluded,unlocated_or_outside_rows=missing_location,
        source_base_date=version,period_start=min(dated),period_end=max(dated),
        region_counts=dict(Counter(p[2]['region'] for p in records)),
        historic_2018_2024_records=sum('2018'<=p[2]['source_date'][:4]<='2024' for p in records),
        scope_note='현재 단지정보에 남아 있는 과거 준공·입주지정 일정. 미래 예정일도 포함하며 당시 월별 공정률·실입주량을 증명하지 않음')


def collect_stock(source,fetcher):
    raw=fetcher.get(source['url']).decode('utf-8','replace')
    soup=BeautifulSoup(raw,'html.parser');title=soup.title.get_text() if soup.title else ''
    stamp=re.search(r'단지정보_(20\d{6})',title)
    link=re.search(r'"contentUrl"\s*:\s*"(https://www\.data\.go\.kr/cmm/cmm/fileDownload\.do\?[^"\s]+)"',raw)
    if not stamp or not link:raise ValueError('LH 단지정보 공개본 날짜·다운로드 링크 미확보')
    version=datetime.strptime(stamp[1],'%Y%m%d').date().isoformat()
    return parse_stock(fetcher.get(link[1],'csv'),source,link[1],version)
