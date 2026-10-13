"""Portfolio-wide cohort linkage audit plus verified A17/renewal source capture.

Run with a locally captured source directory. Officer decisions are preserved;
all newly discovered identity relationships stay REVIEW. Never synthesize events.
"""
import argparse,hashlib,io,json
from collections import Counter,defaultdict
from pathlib import Path
from bs4 import BeautifulSoup
from pypdf import PdfReader
from sqlalchemy import select
from backend.api_samples import today
from backend.db import engine_for,upsert_revision,Audit,Revision
from backend.service import HomeService
from backend.evidence_bridge import reconcile
from backend.project_collection import collection_matrix
from backend.policy_project_registry import registry_records
from scripts.repair_reviewed_project_cases import explicit_link,repair


def capture(service,root,file,url,key,terms,payload):
    body=(root/file).read_bytes();pdf=body.startswith(b'%PDF')
    text='\n'.join(p.extract_text(extraction_mode='layout') or '' for p in PdfReader(io.BytesIO(body)).pages) if pdf else BeautifulSoup(body,'html.parser').get_text(' ',strip=True)
    compact=''.join(text.split());assert all(t in compact for t in terms),(file,'source content mismatch')
    digest=hashlib.sha256(body).hexdigest();dest=service.data_dir/'raw'/'official_document'/(digest+('.pdf' if pdf else '.html'));dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(body)
    payload=dict(payload,sample_kind='document_evidence',evidence_url=url,original_sha256=digest,original_file=str(dest.relative_to(service.data_dir)),verification_status='SOURCE_CONTENT_CHECKED',base_date=today().isoformat(),date_precision='COLLECTION')
    with service.sessions.begin() as db:
        r,result=upsert_revision(db,'document_evidence','official_document',key,payload,'cohort_sequence_repair')
        if result!='unchanged':db.add(Audit(entity_id=r.entity_id,action='OFFICIAL_DOCUMENT_CAPTURE',before={},after=payload))
    return dict(payload,id=r.entity_id,revision_no=r.revision_no,source_id='official_document')


def sources(service,root):
    fetched=json.loads((root/'fetched.json').read_text());downloads=json.loads((root/'downloads.json').read_text())
    base=dict(region='인천광역시',municipality='계양구',district='인천계양',block='A17',planned_units=463,address='인천광역시 계양구 박촌동 일원')
    capture(service,root,'approval-original',downloads['approval-original']['url'],'gyeyang-a17-initial', ['2021-1555','A17BL','2022년1월6일'],dict(base,name='인천계양 A17 · 최초 사업계획 승인 고시',facts=[
        dict(stage='APPROVAL',kind='ACTUAL',date='2022-01-06',units=463,milestone='INITIAL_APPROVAL',basis='국토부 제2021-1555호 고시 본문의 승인 고시일 · 현재 전체 463호 범위 연결'),
        dict(stage='BUSINESS',kind='STATE',date='2022-01-06',basis='최초 승인 고시에 LH 사업시행 사업 명시 · 사업화 최초 사건일 별도 확인')]))
    capture(service,root,'approval',fetched['approval']['url'],'gyeyang-a17-amendment', ['2026-328','2026년06월30일','463호','A17BL'],dict(base,name='인천계양 A17 · 사업계획 변경승인 제2026-328호',facts=[
        dict(stage='APPROVAL',kind='ACTUAL',date='2026-06-30',units=463,milestone='AMENDED_APPROVAL',basis='국토부 제2026-328호 변경승인 · 최초 승인 사건과 별도 보존'),
        dict(stage='CONSTRUCTION',kind='DOCUMENT',date=None,date_label='사업기간 2029.08까지',basis='변경승인 사업기간의 종료월은 계약 준공일·입주일과 다르므로 준공 목표로 대체하지 않음')]))
    # All registered complexes mentioned in the same official follow-up, not just Suseo.
    projects=service.rows('project');items={p['name']:p for p in projects if p['source_id']=='policy_907'}
    timetable={'하계5단지':('2025-02',2026,2029),'상계마들':('2024-12',2026,2029),'중계1단지':(2026,2028,2031),'가양 노후 임대 재건축':(2027,2029,2032),'수서 노후 임대 재건축':(2028,2030,2033)}
    updated=[]
    for kind,key,payload in registry_records('policy_907'):
        if key not in timetable or key not in items:continue
        project=items[key];approval,start,move=timetable[key]
        # Original source entity and mapping IDs stay stable; old revisions remain accessible.
        with service.sessions.begin() as db:
            old=db.scalar(select(Revision).where(Revision.entity_id==project['id'],Revision.superseded_at.is_(None)))
            new=dict(old.payload,**{k:v for k,v in payload.items() if k in ('existing_stock_units','planned_units','developer','net_additional_units','start_plan_year','unit_basis','quantity_status','quantity_evidence_url','scope_note','schedule_basis','address','source_scope')})
            row,result=upsert_revision(db,kind,'policy_907',key,new,'cohort_sequence_repair')
            assert row.entity_id==project['id']
            if result!='unchanged':db.add(Audit(entity_id=row.entity_id,action='SOURCE_PLAN_CORRECTION',before=old.payload,after=new))
        fact=[dict(stage='CONSTRUCTION',kind='PLAN',date=str(start)+'-12',date_label=str(start)+'년',date_precision='YEAR',date_conversion='PERIOD_END',units=payload['planned_units'],milestone='CONSTRUCTION',basis='국토부 후속 계획 착공연도 · 연말 기준 표시, 실제 착공 아님'),
              dict(stage='MOVE_IN',kind='PLAN',date=str(move)+'-12',date_label=str(move)+'년',date_precision='YEAR',date_conversion='PERIOD_END',units=payload['planned_units'],milestone='MOVE_IN',basis='국토부 후속 계획 입주연도 · 연말 기준 표시, 실제 입주 아님')]
        if isinstance(approval,int):fact.append(dict(stage='APPROVAL',kind='PLAN',date=str(approval)+'-12',date_label=str(approval)+'년',date_precision='YEAR',date_conversion='PERIOD_END',units=payload['planned_units'],basis='국토부 후속 계획 사업승인 목표연도 · 연말 기준 표시'))
        else:fact.append(dict(stage='APPROVAL',kind='STATE',date=approval,date_label=approval,basis='국토부 후속표에 기승인 월 표시 · 승인 일자 원문 추가 확인'))
        doc=capture(service,root,'renewal.pdf',downloads['renewal']['url'],'renewal-20251001:'+project['id'],['2,565','3,899','1,998','3,235','500%'],dict(name=key+' · 국토부 노후 공공임대 후속 계획',region='서울특별시',municipality=project['municipality'],planned_units=payload['planned_units'],existing_stock_units=payload['existing_stock_units'],source_date='2025-10-01',quantity_status=payload['quantity_status'],facts=fact))
        explicit_link(service,project,doc,fact,'2025-10-01 국토부 단지별 후속계획 대조 · 기존 재고/재건축 후 계획/순증 구분 · 용적률 가정 전망은 확정 물량과 구분')
        updated.append(project)
    suseo=items['수서 노후 임대 재건축']
    doc=capture(service,root,'suseo-address',fetched['suseo-address']['url'],'suseo-lh-address',['수서주공','2,565','수서동707'],dict(name='수서주공 LH · K-apt 단지 위치',region='서울특별시',municipality='강남구',address='서울특별시 강남구 수서동 707',planned_units=None,existing_stock_units=2565,facts=[]))
    explicit_link(service,suseo,doc,[],'K-apt 수서주공 2,565호와 국토부 후속표 수서(LH) 2,565호 대조 · SH 일원동 711과 다른 단지')
    repair(service,'renewal-followup-plan-stock-confusion','노후 공공임대 후속계획 누락 및 기존 재고·계획호수 혼동',
        '수서·가양 정책 등록은 계획호수를 기존 재고로 오기했고 단지별 후속계획이 누락됐다. 수서1 명칭만으로 SH 일원동 711과 LH 수서동 707을 혼동할 위험이 있다.',
        '같은 국토부 2025-10-01 첨부표의 등록사업 5개를 일괄 보완. 기존 재고/계획/순증을 분리하고 승인·착공·입주 목표를 저장했다. 수서는 LH 수서동 707 대표 지번을 연결하고 3,899호 계획을 집계한다.',
        'LH 승인 전 계획은 용적률 500% 가정으로 변동 가능. 실제 승인·착공·입주와 분양 일정은 추가 확인. SH 수서1-1 2,214호·민간 999호는 해당 정책 LH 물량에 합산하지 않는다.',updated,['POLICY','APPROVAL','CONSTRUCTION','MOVE_IN'],'SCOPE_QUANTITY')


def audit_and_apply(service):
    before=collection_matrix(service);result=reconcile(service,apply=True)
    from backend.stage_evidence import refresh
    refresh(service,refresh_candidates=True)
    projects={p['id']:p for p in service.rows('project')}
    affected={p['project_id'] for p in result['proposals']}
    if affected:
        repair(service,'portfolio-mixed-tenure-containment','혼합단지 전체/분양/임대 물량 차이로 끊긴 선후 단계 연결',
            '전체 건설 물량과 특정 분양·임대 유형의 물량이 달라 동일 물량 조건에서 연결이 보류됐다. 입주 일정이 전체 건설 원장에만 연결되고 해당 공급 원장에는 전달되지 않는 사례가 있었다.',
            f'전체 {len(projects)}개 사업을 검사하고 공식 유형별 구성표·시도·지구·블록을 대조해 {len(affected)}개 사업, {result["added_links"]}개 연결을 DB에 추가했다. 포함 관계는 해당 유형 호수에만 적용하며 입주 예정으로 실제 입주를 만들지 않는다.',
            '담당자 확정/해제 및 기존 연결 판정 보존. 전체 463호와 분양 309호 같은 상하위 물량은 더하지 않는다. 구성표 미확보·불일치·다중 블록 계약은 자동 확정하지 않고 검토 대상으로 유지.',[projects[k] for k in sorted(affected)],['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],'IDENTITY_LINK')
    after=collection_matrix(service);groups=defaultdict(set)
    for p in after['items']:
        for check in p['sequence_checks']:groups[(check['code'],check['downstream'],check['stage'])].add(p['id'])
    # Persist the portfolio audit once at repair time. GET requests only read links.
    counts={}
    for (code,downstream,stage),ids in sorted(groups.items()):
        key=f'sequence-review:{code}:{downstream}:{stage}';counts[key]=len(ids)
        payload=dict(name=key,project_ids=sorted(ids),code=code,downstream=downstream,stage=stage,count=len(ids),base_date=today().isoformat(),status='REVIEW',basis='전체 사업 단계 근거 점검 · 미래 계획만으로 과거 단계 완료 처리하지 않음')
        with service.sessions.begin() as db:upsert_revision(db,'sequence_review','cross_source',key,payload,'cohort_sequence_repair')
    a17=[p for p in projects.values() if '계양' in p['name'] and 'A17' in p['name']]
    repair(service,'a17-predecessor-source-verification','공급·입주 일정과 인허가·건설 선행 근거 누락',
        '계양 A17 공급계획 309호와 건설 463호의 물량 범위 차이, 공식 고시 수집 누락, 공고 판본별 부분 유형 제한으로 앞 단계 연결이 끊겼다.',
        '국토부 최초 고시 2022-01-06 및 변경 고시 2026-06-30을 보존하고 LH 공사 착공 2026-06-01·준공예정 2029-07-26, 본모집 2026-09-30 309호, 입주예정 2029-11을 범위별로 연결했다. 전체 사업에도 공식 구성표 기반 규칙을 적용했다.',
        '공정률 0%는 2026-07-01 원천 시점 값. 고시 사업기간 종료 2029-08과 계약 준공예정 2029-07-26은 의미가 달라 병기한다. 행복주택 154호 공급·입주 일정과 최신 실적은 별도 확인.',a17,['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],'COLLECTION_GAP')
    remaining={p['id'] for p in after['items'] if p['sequence_checks']}
    repair(service,'portfolio-predecessor-review-queue','전체 사업 선후 관계 미연결 근거 재검토',
        f'전체 {len(projects)}개 사업을 단계별로 재검토했다. 입주 계획·실적, 분양·임대 모집, 착공 근거에 비해 앞 단계의 사건 원문 또는 날짜가 빠진 사례를 유형별로 구분했다.',
        f'공식 구성표로 입증된 연결은 반영했고 남은 {len(remaining)}개 사업을 {len(groups)}개 선후 관계 유형의 DB 검토 목록으로 저장했다. 사업 상세의 선후 관계 수집 점검에서 누락 단계와 원인을 확인할 수 있다.',
        '남은 건은 오류 확정이나 단계 미이행을 뜻하지 않는다. 실제 사건 원문 수집 및 담당자 판정 필요. 미래 입주 예정·사전청약만으로 인허가/착공 실적을 일괄 생성하지 않는다.',[projects[k] for k in sorted(remaining)],['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],'COLLECTION_GAP')
    return dict(projects=len(projects),links_added=result['added_links'],affected=len(affected),held=len(result['held']),remaining_projects=len(remaining),review_groups=counts,
                before_checks=sum(len(p['sequence_checks']) for p in before['items']),after_checks=sum(len(p['sequence_checks']) for p in after['items']))


def record_projection_repairs(service):
    projects={p['id']:p for p in service.rows('project')}
    ids={b['project_id'] for b in service.rows('evidence_bridge') if b.get('status') in ('REVIEW','CONFIRMED')
         and any(f.get('milestone') in ('NOTICE','INITIAL_APPROVAL','AMENDED_APPROVAL') for f in b.get('facts',[]))}
    repair(service,'event-subtype-stage-projection','세부 사건명과 정책 단계명 불일치로 그래프 실적 누락',
        '연결된 사실의 NOTICE·INITIAL_APPROVAL·AMENDED_APPROVAL을 정책 단계명으로 사용해 그래프 허용 단계에서 제외했다. 선행 추정의 관측일도 사건일 없는 실적처럼 전달됐다.',
        '전체 자료의 모집공고는 공급, 최초/변경승인은 인허가로 반영하고 준공만 건설의 세부 완료사건으로 구분했다. 사건일 없는 선행 추정은 STATE로 전달해 실제 인허가 실적에 넣지 않는다. 계양 A17 지도와 그래프의 공급 309호를 동일하게 검증한다.',
        '새로운 사건 유형도 원래 stage를 따른다. 담당자 확정 근거·계획·실적은 별도로 유지한다.',[projects[i] for i in sorted(ids) if i in projects],['APPROVAL','CONSTRUCTION','SUPPLY'],'STAGE_DATE')
    ids={r['project_id'] for r in service.rows('project_location') if r.get('status')!='RELEASED' and str(r.get('coordinate_basis','')).startswith('APPROXIMATE')}
    repair(service,'approximate-location-3d-display','근사 좌표 확보 후에도 지도에서 위치 미연계로 표시',
        'DB의 근사 주소·시군구 대표점은 확보되어 있으나 3D 모델·선택·카메라 코드는 LH 블록 라벨점만 허용했다.',
        f'전체 {len(ids)}개 근사 위치 사업에 동일한 표시 규칙을 적용했다. 대표점 인근에 가상 동을 배치하고 근사 위치 근거를 표시한다. 물량은 DB 사업 계획으로 집계하며 물량 미확보 모델은 호수를 생성하지 않는다.',
        '시군구 대표점은 해당 사업 부지 경계가 아니다. 주소 확보 시 위치 수집으로 정밀도를 높이고 담당자 확정·해제 좌표는 보존한다. 가상 동수·높이·배치를 PNU·실제 공정·공급 실적으로 사용하지 않는다.',[projects[i] for i in sorted(ids) if i in projects],['POLICY','CONSTRUCTION','SUPPLY'],'IDENTITY_LINK')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot-dir',required=True);args=parser.parse_args()
    s=HomeService(engine_for(),'/app/data');sources(s,Path(args.snapshot_dir));print(json.dumps(audit_and_apply(s),ensure_ascii=False));record_projection_repairs(s)
