"""Pinned LH follow-up notices: source plans only; officer admission is separate.

Revisits reviewed URLs, not a claim to discover every future LH tender. Changed
quantities become source revisions and never overwrite approved project values.
"""
import hashlib
import io
import re

from bs4 import BeautifulSoup
from pypdf import PdfReader

TENDER_URL = 'https://www.lh.or.kr/boardDownload.es?bid=0034&list_no=727339&seq=2'
PRESS_URL = 'https://www.lh.or.kr/gallery.es?act=view&bid=0003&list_no=11872&mid=a10502000000'
FINANCE_URL = 'https://www.lh.or.kr/gallery.es?act=view&bid=0003&list_no=11896&mid=a10502000000'
POLICY = 'POL_2025_0907'
SITES = [
    ('남양주왕숙2','A6','경기도','남양주시','공공분양'),
    ('남양주왕숙2','A7','경기도','남양주시','이익공유형 공공분양'),
    ('부천대장','A9','경기도','부천시','분양전환 공공임대'),
    ('인천계양','A16','인천광역시','계양구','분양전환 공공임대'),
    ('인천계양','A18','인천광역시','계양구','통합공공임대'),
    ('수원당수2','B1','경기도','수원시','공공분양'),
    ('수원당수2','A1','경기도','수원시','통합공공임대'),
    ('수원당수2','A3','경기도','수원시','통합공공임대'),
]

REVIEWED_UNITS = [510,553,574,434,782,705,693,911]


def physical_key(row):
    """Native block column takes precedence over a multi-block contract title."""
    from .plan_review_matching import scope_key
    if row.get('district') and row.get('block'):
        return scope_key(dict(row,name=row['district']+' '+row['block']))
    return scope_key(row)


def admit_reviewed(service, apply=False):
    """User-authorized admission of the eight named blocks, not fuzzy candidates."""
    from sqlalchemy import select, text
    from .db import Revision, Mapping, ProgramMapping, Audit, upsert_revision, entity_id
    from .collectors import urban_project
    actor='담당자 대행 · 미연결 사업 재심사 사용자 지시 2026-10-19'
    result=dict(applied=apply,actor=actor,projects=[])
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(1019193)'))
        rows=db.scalars(select(Revision).where(Revision.superseded_at.is_(None),Revision.kind.in_(['agency_plan','project']))).all()
        sources={r.payload.get('source_object_id'):r for r in rows if r.kind=='agency_plan' and r.source_id=='lh_policy_followup'}
        projects=[r for r in rows if r.kind=='project']
        todo=[]
        for site,units in zip(SITES,REVIEWED_UNITS):
            district,block,region,city,tenure=site
            key='727339:'+district+':'+block
            src=sources.get(key)
            if src is None or src.payload.get('units')!=units or src.payload.get('start_plan_month')!='2026-06':
                raise ValueError('검토한 사업 호수·일정 판본 변경: '+key)
            if src.payload.get('policy_relationship')!='EXPLICIT_FOLLOWUP_TENDER':raise ValueError('정책 후속 근거 누락')
            pid=entity_id('project','lh_policy_followup','reviewed:'+key)
            same=[r for r in projects if physical_key(r.payload)==(region,district,block)]
            if any(r.entity_id!=pid for r in same):raise ValueError('기존 동일 블록과 중복 재검토 필요: '+key)
            program_name='LH 직접시행 전환·토지이용 효율화'
            pg=db.scalar(select(ProgramMapping).where(ProgramMapping.name==program_name,ProgramMapping.policy_id==POLICY,ProgramMapping.status=='CONFIRMED'))
            if not pg:raise ValueError('승인 프로그램 미확보: '+program_name)
            basis=(actor+' · LH 2025.09.25 공식 발표의 9·7 후속 8개 블록 명단과 2025.10.30 제6차 공모를 대조. '
                   +district+' '+block+f' / {tenure} / {units}호 / 2026년 6월 착공 목표. '
                   '시도·지구·블록 및 개별 공모의 전체 건설호수 확인; 기존 전체 사업 원장에 동일 블록 없음. '
                   '공모의 LH 직접시행 전환 명시와 정책 프로그램의 직접시행 전환 범위 일치. '
                   '보도자료 개략량보다 개별 공모 세부 명세를 관리 기준으로 채택. 실제 착공 여부는 별도 확인. '+PRESS_URL)
            item=dict(id=pid,name=district+' '+block,units=units,program_id=pg.id,program=pg.name,
                      source_id=src.entity_id,source_revision=src.revision_no,evidence_url=src.payload['evidence_url'],basis=basis)
            if same:
                mapping=db.scalar(select(Mapping).where(Mapping.project_id==pid))
                if not mapping or mapping.status!='CONFIRMED' or mapping.policy_id!=POLICY or mapping.program_id!=pg.id or same[0].payload.get('planned_units')!=units:
                    raise ValueError('등록 사업의 후속 판정 보존 필요: '+pid)
                result['projects'].append(dict(item,result='existing_preserved'));continue
            todo.append((src,key,site,units,pg,item))
        # Preflight every item before the first write; one transaction for all eight.
        for src,key,site,units,pg,item in todo:
            if not apply:result['projects'].append(dict(item,result='proposed'));continue
            district,block,region,city,tenure=site
            payload=urban_project(item['name'],city,region,units,POLICY,'2025-10-30',pg.name)
            payload.update(district=district,block=block,tenure=tenure,developer='LH',source_scope='SINGLE_BLOCK',
                evidence_url=src.payload['evidence_url'],policy_evidence_url=PRESS_URL,
                source_object_id='reviewed:'+key,source_reference_id=src.entity_id,
                source_reference_revision=src.revision_no,source_document_sha256=src.payload['original_sha256'],
                mapping_basis=item['basis'],start_plan_month='2026-06',
                schedule_basis='LH 개별 공모 착공 목표: 2026년 6월',
                unit_basis='LH 2025.10.30 개별 공모의 블록 전체 건설호수 · 담당자 대행 채택',
                facts=[],registration_set='POLICY_READMISSION_20261019')
            row,_=upsert_revision(db,'project','lh_policy_followup','reviewed:'+key,payload,'readmission-20261019')
            db.add(Mapping(project_id=row.entity_id,policy_id=POLICY,program_id=pg.id,status='CONFIRMED',
                           revision_no=1,basis=item['basis'],evidence_url=PRESS_URL))
            db.add(Audit(entity_id=row.entity_id,action='MAPPING_REVIEW',before={},after=dict(
                actor=actor,policy_id=POLICY,program_id=pg.id,status='CONFIRMED',basis=item['basis'],revision_no=1)))
            bridge=dict(project_id=row.entity_id,name=item['name'],region=region,source_entity_id=src.entity_id,
                source_revision_no=src.revision_no,evidence_source_id=src.source_id,source_id=src.source_id,
                source_name=src.payload['name'],evidence_url=src.payload['evidence_url'],units=units,
                facts=src.payload['facts'],status='CONFIRMED',reviewed=True,review_actor=actor,
                relation_type='EXPLICIT_POLICY_FOLLOWUP_BLOCK',basis=item['basis'],base_date='2026-10-19')
            b,_=upsert_revision(db,'evidence_bridge','cross_source',row.entity_id+':'+src.entity_id,bridge,'readmission-20261019')
            db.add(Audit(entity_id=b.entity_id,action='DELEGATED_PLAN_LINK_CONFIRMED',before={},after=bridge))
            result['projects'].append(dict(item,result='added'))
    return result


def parse_tender(pages):
    text='\n'.join(pages)
    compact=re.sub(r'\s+','',text)
    if not all(t in compact for t in ['2025.10.30.', '주택공급확대방안', '25.9.7', 'LH직접시행']):
        raise ValueError('검토한 LH 후속 공모의 정책·발표일 근거 변경')
    headings=list(re.finditer(r'^\s*\d\.\s*(남양주왕숙2|부천대장|인천계양|수원당수2)\s+([AB])-?(\d+)BL\s*$',text,re.M))
    keys=[(m[1],m[2]+str(int(m[3]))) for m in headings]
    if keys!=[(r[0],r[1]) for r in SITES]:
        raise ValueError('LH 공모 블록 누락·중복·구조 변경')
    rows=[]
    for i,(m,site) in enumerate(zip(headings,SITES)):
        district,block,region,city,tenure=site
        section=text[m.end():headings[i+1].start() if i+1<len(headings) else len(text)]
        table=section.split('*')[0]
        quantities=[int(n.replace(',','')) for n in re.findall(r'(?<![\d.])([\d,]+)\s*호',table)]
        if len(quantities)==3 and sum(quantities[:2])==quantities[-1]:units=quantities[-1]
        elif len(quantities)==1:units=quantities[0]
        else:raise ValueError('LH 블록별 면적·총 호수 대사 실패: '+district+' '+block)
        if not 0<units<10000:raise ValueError('LH 블록 호수 범위 변경')
        if not re.search(r'착공\s*\([`‘’\']26년\s*06월\s*예정\)',section):
            raise ValueError('LH 블록별 착공 목표월 변경: '+district+' '+block)
        key='727339:'+district+':'+block
        page=next(n+1 for n,p in enumerate(pages) if re.search(re.escape(m[0].strip()),p))
        rows.append(dict(sample_kind='agency_plan',name=district+' '+block,region=region,
            municipality=city,district=district,block=block,tenure=tenure,developer='LH',
            source_object_id=key,units=units,planned_units=units,source_date='2025-10-30',
            base_date='2025-10-30',date_precision='DAY',dataset_version='2025-10-30',
            source_date_label='민간사업자 공모 공고일',evidence_url=TENDER_URL+'#page='+str(page),
            policy_evidence_url=PRESS_URL,source_page=page,source_excerpt=section.strip(),
            policy_mapping_status='UNMAPPED',proposed_policy=POLICY,
            policy_relationship='EXPLICIT_FOLLOWUP_TENDER',start_plan_month='2026-06',
            facts=[dict(stage='CONSTRUCTION',kind='PLAN',date='2026-06',precision='MONTH',
                        units=units,basis='LH 2025.10.30 공모의 블록별 2026년 6월 착공 목표')],
            warnings=[],unit_basis='개별 공모의 블록 전체 건설호수; 실제 착공 실적과 구분'))
    return rows


def collect(source,fetcher):
    records=[]
    for url,key,stamp in [(PRESS_URL,'11872','2025-09-25'),(FINANCE_URL,'11896','2025-10-27')]:
        body=fetcher.get(url)
        soup=BeautifulSoup(body,'html.parser')
        content=soup.select_one('.board_view') or soup
        text=content.get_text(' ',strip=True)
        if '9.7' not in text or '민간참여' not in text:raise ValueError('LH 정책 후속 근거 미확보')
        records.append(('document_evidence',key,dict(name='LH 9·7 후속 민간참여 공공주택 '+stamp,
            sample_kind='document_evidence',base_date=stamp,source_date=stamp,date_precision='DAY',
            evidence_url=url,content_text=text,original_sha256=hashlib.sha256(body).hexdigest(),
            original_file='raw/'+fetcher.manifest[-1]['file'],facts=[],matched_project_ids=[],
            planned_units=None,policy_candidate_only=True,proposed_policy=POLICY)))
    body=fetcher.get(TENDER_URL,'pdf')
    pages=[p.extract_text(extraction_mode='layout') or '' for p in PdfReader(io.BytesIO(body)).pages]
    for row in parse_tender(pages):
        row.update(original_sha256=hashlib.sha256(body).hexdigest(),original_file='raw/'+fetcher.manifest[-1]['file'])
        records.append(('agency_plan',row['source_object_id'],row))
    from .lh_spring_followup import FEB_URL, MAY_URL, parse_plans
    spring_pages = {}
    for url, number, stamp in [(FEB_URL,11981,'2026-02-12'),(MAY_URL,12047,'2026-05-29')]:
        content = fetcher.get(url, 'pdf')
        pages = [p.extract_text(extraction_mode='layout') or '' for p in PdfReader(io.BytesIO(content)).pages]
        spring_pages[number] = pages
        meta = dict(original_sha256=hashlib.sha256(content).hexdigest(), original_file='raw/'+fetcher.manifest[-1]['file'])
        records.append(('document_evidence',str(number),dict(name='LH 민간참여 공모 '+stamp,
            sample_kind='document_evidence',base_date=stamp,source_date=stamp,date_precision='DAY',
            evidence_url=url,content_text='\n'.join(pages),facts=[],matched_project_ids=[],planned_units=None,**meta)))
    for row in parse_plans(spring_pages[12047], spring_pages[11981]):
        row.update(meta)
        records.append(('agency_plan',row['source_object_id'],row))
    return records,dict(fetched=len(records),provided=len(records),incremental=True,
        complete_query=True,complete_population=False,reviewed_urls=5,plan_blocks=29,
        plan_units=sum(r[2]['units'] for r in records if r[0]=='agency_plan'),
        scope_note='검토한 LH 후속 보도자료 4건·공모 1건 재확인. 전체 공모 탐색 아님. 변경 원문은 판본 보존하며 승인 사업값은 자동 대체하지 않음')
