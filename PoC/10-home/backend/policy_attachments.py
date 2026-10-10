"""Explicit official policy appendices; aggregate quantities are never split by guesswork."""
import io
import json
import hashlib
from pathlib import Path
import re
from pypdf import PdfReader

from .collectors import clean, integer, urban_project

POLICY129_PDF='https://www.korea.kr/common/download.do?fileId=198344116'
TABLE_ROW=re.compile(r'^\s*(\d+)\s+(서울|경기|인천)\s+(\S+)\s+(.+?)\s+([\d,]+)\s+(공유지|국유지|공공기관)\s*[‘’\'](\d{2})\.(\d{2})\s*(\S+)\s*$',re.M)


def parse_policy129_table(text):
    if '사업' not in text or '34개소' not in re.sub(r'\s+','',text):
        raise ValueError('1·29 별첨 사업표 제목 변경')
    rows=TABLE_ROW.findall(text)
    if [int(r[0]) for r in rows]!=list(range(1,35)) or sum(integer(r[4]) for r in rows)!=9894:
        raise ValueError('1·29 별첨 사업표 행 누락·중복·합계 불일치')
    records=[]
    for seq,region,city,name,units,ownership,year,month,manager in rows:
        if region=='인천':continue
        if not 1<=int(month)<=12:raise ValueError('1·29 별첨 착공월 형식 변경')
        name=clean(name);region='서울특별시' if region=='서울' else '경기도';city+= '구' if region=='서울특별시' else '시'
        payload=urban_project(name,city,region,integer(units),'POL_2026_0129','2026-01-29','노후청사·공공부지')
        payload.update(evidence_url=POLICY129_PDF,source_page=19,source_table_sequence=int(seq),
            ownership=ownership,source_manager=manager,start_plan_month=f'20{year}-{month}',
            schedule_basis='공식 별첨 착공 예정월 · 공급·준공·입주월 아님',
            developer={'SH':'서울주택도시공사','GH':'경기주택도시공사'}.get(manager,'시행기관 확인 필요'),
            warnings=['POLICY_PLAN_NOT_ACTUAL'],unit_basis='공식 정책 별첨 사업별 계획호수 · 실제 공급량 아님')
        records.append(('project',name,payload))
    return records


def collect_policy129_attachment(fetcher):
    pdf=PdfReader(io.BytesIO(fetcher.get(POLICY129_PDF,'pdf')))
    texts=[p.extract_text(extraction_mode='layout') or '' for p in pdf.pages]
    tables=[text for text in texts if '사업리스트(34개소' in re.sub(r'\s+','',text)]
    if len(tables)!=1:raise ValueError('1·29 별첨 사업표 미확보·중복')
    records=parse_policy129_table(tables[0])
    # These five named sites are separate from the old-office appendix. Existing
    # briefing project identities are retained, rather than inserted as aliases.
    specs=[('용산국제업무지구','용산구','서울특별시',10000,9,'1만호','28'),
           ('캠프킴','용산구','서울특별시',2500,10,'2,500호','29'),
           ('501 정보대(서빙고초 앞)','용산구','서울특별시',150,10,'150호','28'),
           ('과천 경마장·방첩사 부지','과천시','경기도',9800,10,'9,800호',None),
           ('태릉 CC','노원구','서울특별시',6800,11,'6,800호','30')]
    for name,city,region,units,page,assertion,year in specs:
        text=re.sub(r'\s+','',texts[page])
        anchor='501정보대' if name.startswith('501') else '과천' if name.startswith('과천') else name.replace(' ','')
        if anchor not in text or assertion not in text:raise ValueError('1·29 개별 입지·호수 근거 변경')
        payload=urban_project(name,city,region,units,'POL_2026_0129','2026-01-29','공공시설·유휴부지 개발')
        payload.update(evidence_url=POLICY129_PDF,source_page=page+1,warnings=['POLICY_PLAN_NOT_ACTUAL'],
            unit_basis='공식 첨부 개별 입지 계획호수 · 기계획 물량 포함 · 실제 공급량 아님')
        if year:payload['start_plan_year']=2000+int(year)
        records.append(('project',name,payload))
    text=re.sub(r'\s+','',texts[12])
    if not all(token in text for token in ('성남금토2','성남여수2','6,300호')):
        raise ValueError('1·29 성남 신규지구 근거 변경')
    for name in ('성남 금토2','성남 여수2'):
        payload=urban_project(name,'성남시','경기도',None,'POL_2026_0129','2026-01-29','신규 공공주택지구')
        payload.update(evidence_url=POLICY129_PDF,source_page=13,warnings=['JOINT_QUANTITY_UNALLOCATED'],
            unit_basis='두 지구 합계 6,300호만 확인 · 지구별 배분 미확인',start_plan_year=2030)
        records.append(('project',name,payload))
    return records,dict(attachment_url=POLICY129_PDF,attachment_table_rows=34,attachment_table_in_scope=32,
        attachment_table_excluded=2,attachment_table_units=9894,attachment_table_complete=True,
        additional_attachment_projects=len(records),complete_population=False,
        scope_note='1·29 공식 PDF 별첨 34행·합계 검증 후 서울·경기 32행과 개별 입지 추가. 인천 제외. 성남 두 지구 합계 6,300호를 임의 배분하지 않음')

URBAN930_PDF = 'https://www.korea.kr/common/download.do?fileId=198562238&tblKey=GMN'


def parse_urban930_attachment(texts):
    if len(texts) < 8 or '신규후보지개요' not in re.sub(r'\s+', '', texts[4]):
        raise ValueError('9·30 후보지 별첨 제목·페이지 변경')
    records=[]
    for page in range(4,8):
        blocks=re.split(r'[①②③④⑤⑥]',texts[page])[1:]
        for block in blocks:
            match=re.search(r'^\s*(.+?)\s*·\(위치\)\s*서울시\s+(\S+구)\s+(\S+)\s*·\(면적\)\s*([\d,.]+)㎡\s*·\(공급규모\)\s*([\d,]+)호',block,re.S)
            if not match:raise ValueError('9·30 후보지 이름·위치·물량 행 형식 변경')
            name,city,dong,area,units=match.groups();name=clean(name)
            payload=urban_project(name,city,'서울특별시',integer(units),'POL_2026_0813','2026-09-30','도심 공공주택 복합사업')
            payload.update(stage='CANDIDATE',stage_label='신규 후보지',address=f'서울특별시 {city} {dong}',
                evidence_url=URBAN930_PDF,source_page=page+1,site_area_sqm=float(area.replace(',','')),
                unit_basis='공식 별첨 후보지별 계획호수 · 실제 공급실적 아님',warnings=['POLICY_PLAN_NOT_ACTUAL'],
                start_plan_year=2030,schedule_basis='2030년 하반기 착공 추진 · 공급·준공 시점 미확인')
            records.append(('project',name,payload))
    if len(records)!=11 or len({r[1] for r in records})!=11 or sum(r[2]['planned_units'] for r in records)!=17881:
        raise ValueError('9·30 후보지 11행·합계 불일치')
    table=texts[2]
    matches=re.findall(r'^\s*([1-5])\s+(.+?)\s+(\S+구)\s+(?:저층주거지\s+)?([\d,.]+)㎡\s*([\d,]+)호',table,re.M)
    if len(matches)!=5 or [int(r[0]) for r in matches]!=list(range(1,6)) or sum(integer(r[4]) for r in matches)!=11818:
        raise ValueError('9·30 지정지구 5행·합계 불일치')
    for seq,name,city,area,units in matches:
        name=clean(name)
        payload=urban_project(name,city,'서울특별시',integer(units),'POL_2026_0813','2026-09-30','도심 공공주택 복합사업')
        payload.update(stage='DESIGNATED',stage_label='복합지구 지정 · 사업계획 승인 추진',evidence_url=URBAN930_PDF,
            source_page=3,unit_basis='공식 지정지구별 계획호수 · 실제 공급실적 아님',warnings=['POLICY_PLAN_NOT_ACTUAL'],
            designation_date='2026-09-04' if int(seq)<=2 else '2026-09-30')
        records.append(('project',name,payload))
    return records,dict(selected_projects=11,announced_candidates=11,additional_designated_projects=5,
        candidate_plan_units=17881,designated_plan_units=11818,missing_candidate_names=0,
        complete_query=True,complete_population=False,attachment_url=URBAN930_PDF,
        scope_note='공식 PDF 신규 후보지 11행·17,881호와 지정지구 5행·11,818호 전체 대조. 전국 47개 추진 사업 전체 목록은 별도 확인 필요')


def collect_urban930_attachment(fetcher):
    content=fetcher.get(URBAN930_PDF,'pdf')
    reader=PdfReader(io.BytesIO(content))
    records,stats=parse_urban930_attachment([p.extract_text(extraction_mode='layout') or '' for p in reader.pages])
    curated=json.loads((Path(__file__).parent/'data'/'urban930_progress.json').read_text())
    if hashlib.sha256(content).hexdigest()!=curated['pdf_sha256']:
        raise ValueError('9·30 추진현황 이미지 PDF 판본 변경: 수동 대조 후 적재 필요')
    if len(curated['records'])!=47:raise ValueError('9·30 추진현황 명단 행 누락')
    existing={key for _,key,_ in records}
    labels={'BUSINESS_APPROVED':'사업계획 승인','DESIGNATED':'복합지구 지정',
        'PROPOSED_DISTRICT':'예정지구 지정','UNKNOWN':'진행 단계 확인 필요'}
    included=0
    for row in curated['records']:
        if row['region'] not in ('서울특별시','경기도'):continue
        included+=1
        if row['name'] in existing:continue
        payload=urban_project(row['name'],row['municipality'],row['region'],None,'POL_2026_0813',
            '2026-09-30','도심 공공주택 복합사업')
        payload.update(stage='APPROVAL' if row['status']=='BUSINESS_APPROVED' else row['status'],
            stage_label=labels[row['status']],evidence_url=URBAN930_PDF,source_page=9,
            source_sequence=row['sequence'],program_type=row['program_type'],
            unit_basis='공식 추진현황 이미지에 개별 물량 미제공 · 전국 합계를 배분하지 않음',
            extraction_basis=curated['extraction'],warnings=['UNITS_UNKNOWN'] if row['status']!='UNKNOWN' else ['UNITS_UNKNOWN','STAGE_UNVERIFIED'])
        records.append(('project',row['name'],payload))
    stats.update(progress_list_rows=47,progress_list_in_scope=included,progress_list_excluded=47-included,
        scope_note='공식 PDF 후보지 11행·17,881호, 지정지구 5행·11,818호 대조. 참고2 추진 47곳 중 서울·경기 40곳 명단 추가, 중복 5곳 통합. 개별 물량 미제공은 미확인 유지')
    return records,stats
