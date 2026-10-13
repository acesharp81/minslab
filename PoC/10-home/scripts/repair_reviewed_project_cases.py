"""Reproducible reviewed source captures and durable links for reported omissions.

Run after lh_notice_detail collection. Does not replace officer decisions, original
source quantities, policy attribution or turn forecasts into delivery actuals.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
from sqlalchemy import select, text
from backend.db import Audit, Revision, engine_for, entity_id, upsert_revision
from backend.service import HomeService
from backend.evidence_bridge import reconcile, facts
from backend.collection_repairs import save
from backend.api_samples import today


def put_document(service, snapshots, key, terms, payload):
    manifest=json.loads((snapshots/'manifest.json').read_text())[key]
    body=(snapshots/key).read_bytes();digest=hashlib.sha256(body).hexdigest()
    if manifest['sha256']!=digest:raise ValueError('원문 해시 불일치: '+key)
    content=re.sub(r'\s+',' ',BeautifulSoup(body,'html.parser').get_text(' ',strip=True))
    if not all(t in content for t in terms):raise ValueError('원문 검증 실패: '+key)
    path=service.data_dir/'raw'/'official_document'/(digest+'.html');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
    payload=dict(payload,sample_kind='document_evidence',evidence_url=manifest['url'],original_sha256=digest,
                 original_file=str(path.relative_to(service.data_dir)),verification_status='SOURCE_CONTENT_CHECKED',
                 base_date=today().isoformat(),date_precision='COLLECTION')
    with service.sessions.begin() as db:
        row,result=upsert_revision(db,'document_evidence','official_document',key+'-review-20261013',payload,'reviewed_project_cases')
        if result!='unchanged':db.add(Audit(entity_id=row.entity_id,action='OFFICIAL_DOCUMENT_CAPTURE',before={},after=payload))
    return dict(payload,id=row.entity_id,revision_no=row.revision_no,source_id='official_document')


def explicit_link(service,project,source,evidence,basis):
    """Exact IDs inspected against primary documents; never name-only runtime matching."""
    key=project['id']+':'+source['id'];eid=entity_id('evidence_bridge','cross_source',key)
    payload=dict(project_id=project['id'],name=project['name'],region=project['region'],
        source_entity_id=source['id'],source_revision_no=source['revision_no'],source_id=source['source_id'],
        evidence_source_id=source['source_id'],source_name=source['name'],relation_type='SAME_SCOPE',
        evidence_url=source['evidence_url'],units=source.get('planned_units'),facts=evidence,
        status='REVIEW',reviewed=False,basis=basis,matching_version='primary-document-reviewed-20261013',base_date=today().isoformat())
    with service.sessions.begin() as db:
        db.execute(text('SELECT pg_advisory_xact_lock(1019081)')) if service.engine.dialect.name=='postgresql' else None
        if db.scalar(select(Revision.id).where(Revision.entity_id==eid,Revision.superseded_at.is_(None))):return 'preserved'
        row,_=upsert_revision(db,'evidence_bridge','cross_source',key,payload,'reviewed_project_cases')
        db.add(Audit(entity_id=row.entity_id,action='EVIDENCE_BRIDGE_AUTO',before={},after=payload))
    return 'added'


def repair(service,key,title,cause,action,remaining,projects,stages,kind='COLLECTION_GAP'):
    return save(service,key,dict(title=title,cause=cause,action=action,remaining=remaining,
        project_ids=[p['id'] for p in projects],source_ids=sorted({p['source_id'] for p in projects}),
        stages=stages,repair_type=kind,status='APPLIED_REVIEW_PENDING',base_date=today().isoformat(),
        related_keys=['project_id','source_entity_id','source_revision_no','stage','facts'],
        quality_checks=[dict(id=key,title=title,kind='CONSISTENCY',layer='LINKAGE',result='PARTIAL',
            rule='공식 원천의 사업 범위·단계·기준일·물량을 대조하고 예정과 실적을 구분한다.',
            evidence=cause,repair=action,completion_criteria=remaining,checked_at=today().isoformat(),checked_scope=' / '.join(p['name'] for p in projects))]))


def apply(service,snapshots):
    projects=service.rows('project');byid={p['id']:p for p in projects};out={}
    jemulpo=byid['PRO_a0d337124ee67a9f014a4b0f']
    doc=put_document(service,snapshots,'jemulpo',['3,497','2024-12-23','2022년 2월 9일','2031년','2,943','554'],dict(
        name='제물포역 북측 도심 공공주택 복합사업 · 인천시 승인 발표',region='인천광역시',municipality='미추홀구',
        planned_units=3497,scope_breakdown={'공공분양':2943,'공공임대':554},source_date='2024-12-23',
        unit_basis='승인 물량 3,497호 · 1·29 정책문서 약 3,500호와 같은 사업, 중복 합산 금지',
        address='인천광역시 미추홀구 도화동 94-1',facts=[
            dict(stage='BUSINESS',kind='ACTUAL',date='2022-02-09',basis='인천시 공식 발표의 복합지구 지정일'),
            dict(stage='APPROVAL',kind='ACTUAL',date='2024-12-23',units=3497,basis='인천시 복합사업계획 승인·고시 발표'),
            dict(stage='CONSTRUCTION',kind='PLAN',date=None,date_label='2026년',date_precision='YEAR',milestone='CONSTRUCTION',basis='2024-12-23 인천시 발표의 착공 계획 · 월 미확인, 실제 착공 아님'),
            dict(stage='CONSTRUCTION',kind='PLAN',date=None,date_label='2031년',date_precision='YEAR',milestone='COMPLETION',basis='인천시 발표의 준공 목표 · 월 미확인'),
            dict(stage='MOVE_IN',kind='PLAN',date=None,date_label='2031년',date_precision='YEAR',milestone='MOVE_IN',basis='인천시 발표의 입주 목표 · 실제 입주 아님')]))
    out['jemulpo']=explicit_link(service,jemulpo,doc,doc['facts'],'제물포 도심공공복합 ↔ 제물포역 북측: 인천시 미추홀구 동일 사업 원문 확인 · 원 정책자료 약 3,500호와 승인 3,497호를 구분, 최종 산입량 담당자 확인')
    repair(service,'official-urban-project-evidence','도심 사업의 별칭·반올림 물량과 승인 근거 누락',
        '제물포 정책 등록자료에는 약 3,500호와 착공 연도만 있었고 인천시 승인 보도자료가 연결되지 않았다.',
        '인천시 2024-12-23 원문을 보존하고 지구 지정·승인 3,497호·2026년 착공 계획·2031년 준공 및 입주 목표를 단계별 DB 연결 후보로 저장했다. 연도만 있는 일정은 월을 만들지 않았다.',
        '정책 원천의 반올림 3,500호는 보존. 정책 산입량·최신 착공 여부는 담당자 확인 필요. 제보된 이주율 90.8%는 건설 공정률로 반영하지 않았고 최신 공식 이주 원문은 추가 확보 대상이다.',[jemulpo],['BUSINESS','APPROVAL','CONSTRUCTION','MOVE_IN'],'IDENTITY_LINK')
    bp=[p for p in projects if '인천부평' in p['name']]
    construction=next(p for p in bp if p['source_id']=='lh_incheon_construction');rental=next(p for p in bp if p['source_id']=='lh_incheon_rent')
    assert construction['planned_units']==rental['planned_units']==350
    doc=put_document(service,snapshots,'bupyeong',['혁신센터','2027. 10월','착공신고'],dict(
        name='인천부평 도시재생뉴딜 혁신센터 · 부평구 주요사업',region='인천광역시',municipality='부평구',
        planned_units=None,unit_basis='부평구 혁신센터 일정 근거 · 주택 350호는 별도 LH 원천에서 대조',
        facts=[dict(stage='CONSTRUCTION',kind='PLAN',date='2027-10',milestone='COMPLETION',basis='부평구 주요사업의 혁신센터 준공 계획 · LH 계약 준공 2027-10-19와 월 일치')]))
    basis='LH 동일 인천부평(도시재생뉴딜) A·350호 대조 및 부평구 혁신센터 사업 확인. 복합시설 포함 계약의 주택 부분 연결 후보 · 지구 필드/문자 A 블록/복합계약 제한으로 자동 연결 누락, 담당자 최종 검토 필요'
    out['bupyeong']=[explicit_link(service,rental,construction,facts(construction,today()),basis),
                     explicit_link(service,construction,rental,facts(rental,today()),basis)]
    for p in bp:explicit_link(service,p,doc,doc['facts'],'부평구 공식 혁신센터 사업 일정의 보조 근거 · 주택·복합시설 범위 담당자 검토')
    repair(service,'non-numeric-block-mixed-facility-link','문자 블록·복합시설 사업의 건설/공급 원천 연결 누락',
        '인천부평 공급계획은 지구/블록 필드가 없고 건설자료의 A 블록은 숫자 블록 파서 대상에서 제외된다. 사업명에 및이 포함돼 복수현장 경고도 붙었다. 건설 원천에는 잘못된 서울 지역 안내 문자열이 있으며 원천 사업 위치와 불일치한다.',
        '동일 사업명·LH·350호·부평구 사업 설명을 대조해 건설↔임대 공급계획 연결을 DB에 저장하고 부평구 준공 목표 2027-10 근거를 추가했다. 기존 원천 공정률 47.06%(2026-07-01), 착공 기록 2023-03-31, 준공 계획 2027-10-19 및 임대 입주 계획 2028-02를 연결 상세에 보존했다.',
        '제보의 2022-04-01 착공과 LH 계약 착공 2023-03-31은 착공식/계약/실착공 기준을 추가 검증해야 한다. 제보 입주 2028-01은 현재 확보 LH 계획 2028-02와 상충해 덮어쓰지 않았다. 기사 골조 현황을 현재 공정률로 쓰지 않는다. 승인 완료일·고시 원문과 최신 모집공고는 추가 확보 대상이며 물량 350호를 두 번 합산하지 않는다.',bp,['APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],'IDENTITY_LINK')
    a25=byid['PRO_f345f2ad0c4ce9f333d7e80d']
    doc=put_document(service,snapshots,'wangsuk-a25',['A-25BL','2025-931','2025-12-30'],dict(
        name='남양주왕숙 A25 · 국토교통부 제2025-931호 고시',region='경기도',district='남양주왕숙',block='A25',
        planned_units=None,unit_basis='고시 상세 페이지 승인 식별 · 첨부 세대수 추가 검증 필요',source_date='2025-12-30',
        facts=[dict(stage='APPROVAL',kind='ACTUAL',date='2025-12-30',basis='토지이음 국토교통부 제2025-931호 사업계획 승인 고시 · 기존 최초 허가일을 대체하지 않는 별도 승인 사건')]))
    out['a25']=explicit_link(service,a25,doc,doc['facts'],'토지이음 고시의 남양주왕숙 A-25BL 정확한 사업명 대조 · 기존 건축HUB 허가 이력과 별도 고시 기록')
    repair(service,'approval-event-contract-date-conflicts','승인 사건과 공사·분양 일정의 기준 충돌',
        '왕숙 A25는 건축HUB 허가와 LH 건설자료가 있으나 2025-931 고시가 누락됐다. 제보 공사기간과 LH 계약 일정이 서로 다르다.',
        '2025-12-30 고시를 추가 연결하고 기존 2024-12-31 허가 근거와 LH 계획 착공 2025-12-30/준공 2028-10-29는 보존했다.',
        '제보 2024-12-27 착공·2028-12-31 준공·2027년 하반기 분양은 동일 계약/최신 공식 원문 확인 필요. 사업협약일을 실착공으로 바꾸지 않고 고시의 최초·변경 승인 구분은 첨부 원문 추가 검증 대상이다.',[a25],['APPROVAL','CONSTRUCTION','SUPPLY'],'STAGE_DATE')
    cheongra=byid['PRO_3b288213c58c0a4e7ca7f754']
    law=put_document(service,snapshots,'cheongra-law',['노후청사','2026.08.20','국회 본회의 통과'],dict(name='노후청사 복합개발 특별법 국회 통과 · 정책 제도 근거',region='전국',planned_units=None,facts=[],unit_basis='법률 통과는 개별 청라 사업의 인허가가 아님'))
    repair(service,'policy-law-versus-site-permit','특별법 통과와 개별 사업 인허가 혼동 방지',
        '청라동 92-29의 110호·2030-12 착공 목표는 1·29 원문에 이미 등록돼 있다. 특별법 통과와 2033~2034 입주 전망은 개별 사업의 확정 승인/입주일 근거가 아니다.',
        '기존 계획을 유지하고 법률 통과 정부 원문을 별도 문서로 보존했다. 2033~2034 입주는 사용자 제시 전망으로 이력에 기록하며 확정 목표·실적에 넣지 않았다.',
        '개별 사업계획 승인, 모집공고 및 공식 입주 계획 추가 확보 필요. 미확보를 실적 0으로 간주하지 않는다. 제도 원문: '+law['evidence_url'],[cheongra],['POLICY','APPROVAL','CONSTRUCTION','MOVE_IN'],'STAGE_DATE')
    result=reconcile(service,apply=True);out['automatic_links']={k:v for k,v in result.items() if k not in ('proposals','held')}
    affected=[p for p in projects if any(t in p['name'] for t in ('왕숙2','월암'))]
    repair(service,'lh-notice-multi-block-numeric-district','숫자 지구명·복수단지 모집공고 상세 수집 누락',
        '왕숙2 A3 제목에 왕숙 A3도 부분 일치해 상세 수집 후보에서 제외됐다. 월암 A1/A3 통합공고는 단일 블록만 허용한 수집기로 제외됐다.',
        '숫자 지구 경계를 구분하고 공식 LH 단지 탭별로 물량·공급일·입주 예정월을 분리해 재수집했다. 정정공고의 원 모집일을 보존하고 추가공고는 중복 합산 금지로 표시한다. 왕숙2 A3 686호 입주 예정 2030-05, 월암 A1 공공분양 446호 2027-11/A3 공공분양 424호 2028-04를 연결 후보로 저장했다.',
        '왕숙 A3 7공구 428호는 왕숙2 A3 1공구 686호와 별개. 월암 행복주택 A1 228호/A3 218호에 공공분양 입주일을 일괄 적용하지 않는다. 새 원천 판본은 기존 담당자 결정과 분리해 검토한다.',affected,['SUPPLY','MOVE_IN'],'COLLECTION_GAP')
    return out

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot-dir',type=Path,required=True);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    if not args.apply:raise SystemExit('--apply is required for reviewed DB backfill')
    print(json.dumps(apply(HomeService(engine_for(),'/app/data'),args.snapshot_dir),ensure_ascii=False,indent=2))
