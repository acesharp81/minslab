"""Verify the SH row, enrich the existing 8-unit project, never invent actuals."""
import argparse
from copy import deepcopy
from datetime import date
import hashlib
import json
import re
from sqlalchemy import select, text
from backend.db import Revision, Mapping, Audit, entity_id, upsert_revision, engine_for
from backend.service import HomeService
from scripts.apply_officer_verified_links_20261020 import current, protected_in_db, YEON_ID, YEON_KEY, YEON_DOC
from scripts.review_policy_readmission_20261019 import digest

BATCH='yeonnam-sh-identity-20261020'
ACTOR='담당자 대행 · 사용자 SH 원문 재식별·보완 지시'
URL='https://mas.smc.seoul.kr/attach/record/SEOUL/appendix/a11/A0069855.pdf#page=79'
SHA='578f4d92c7db264f4f062e800ec79e4d48696446948042941b97fd839e7d345b'
KEY=BATCH+':A0069855:p79'
DOC_ID=entity_id('document_evidence','official_document',KEY)
YEONHUI_ID='AGE_ee477cf8737114e5bf0559b0'
OTHER_YEONNAM='PRO_0abce10856b8c6218fa0d63e'
PLAN_ID='AGE_28b43b51b00d7e8d22b11164'
PLAN_BRIDGE='EVI_36f732e1e9da16e537b837d4'
DESIGNER='DOC_af41c4d72153e5430d45df79'
CIS='DOC_88506a6cdf3041b29ee0deb8'
RESOLVED='INDEPENDENT_PROJECT_VERIFIED'
BASIS=('SH 2025년11월 주요업무보고 PDF79쪽 원문에서 연남동 공공임대주택 8호(대지277㎡·1동·5층)와 '
       '연희 공공주택96호를 별도 행으로 확인. 정부2026년4분기 공급계획의 동일 명칭·유형·8호에 대응하는 기존 사업을 재사용. '
       '96호 일부·배분 가설 철회. 2025-11 착공·2026-10 준공은 당시 월 단위 계획이며 실제 사건·모집 실적 미확인.')


def verify_pdf(path):
    from pypdf import PdfReader
    body=path.read_bytes()
    if hashlib.sha256(body).hexdigest()!=SHA:raise ValueError('SH 원문 해시 불일치')
    reader=PdfReader(path)
    if len(reader.pages)!=100:raise ValueError('SH 페이지 수 불일치')
    cover=re.sub(r'\s','',reader.pages[0].extract_text())
    page=reader.pages[78].extract_text(extraction_mode='layout')
    compact=re.sub(r'\s','',page)
    if '2025.11.' not in cover:raise ValueError('업무보고 발행월 불일치')
    # Read the two rows independently; values from neighbouring rows cannot fill a missing cell.
    y=compact.split('연남동',1)[1].split('송파',1)[0]
    h=compact.split('연희',1)[1].split('위례',1)[0]
    if not re.search(r'공공임대2771개동8-812[’‘]25\.11[’‘]26\.10',y):raise ValueError('연남8호 행 불일치')
    if '(5F)' not in y or '1%' not in y or '착공준비' not in y:raise ValueError('연남 규모·실적 열 확인 필요')
    if not re.search(r'공공주택4,2731개동96-9685[’‘]25\.6[’‘]27\.8',h):raise ValueError('연희96호 별도 행 불일치')
    return dict(sha256=SHA,pages=100,page=79,page_index=78,published_month='2025-11',
        yeonnam=dict(name='연남동 공공임대주택',total_units=8,sale_units=0,rental_units=8,land_area_sqm=277,
                     building_count=1,floors_above=5,planned_construction='2025-11',planned_completion='2026-10'),
        yeonhui=dict(name='연희 공공주택',total_units=96,land_area_sqm=4273,planned_construction='2025-06',planned_completion='2027-08'),
        text_excerpt=page,verification='PDF_SHA_AND_SEPARATE_ROWS_CHECKED')


def historical_facts():
    return [dict(stage='CONSTRUCTION',kind='PLAN',date=stamp,date_label=stamp,precision='MONTH',milestone=milestone,
                 units=8,reference_only=True,source_as_of='2025-11',basis='SH2025년11월 업무보고의 당시 계획; 최신 목표·실제 사건 아님')
            for stamp,milestone in [('2025-11','CONSTRUCTION'),('2026-10','COMPLETION')]]


def apply_identity(service,proof,apply=False):
    if proof.get('sha256')!=SHA or proof.get('yeonnam',{}).get('total_units')!=8:raise ValueError('원문 검증 결과 불일치')
    changes=[]
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(10203032)'))
        before=protected_in_db(db)
        plans_before={r.entity_id:r.payload_hash for r in db.scalars(select(Revision).where(Revision.kind=='agency_plan',Revision.superseded_at.is_(None)))}
        project=current(db,YEON_ID);m=db.scalar(select(Mapping).where(Mapping.project_id==YEON_ID))
        if not project or project.payload.get('planned_units')!=8 or not m or m.status!='CONFIRMED' or m.policy_id!='POL_2025_0907':raise ValueError('기존 연남8호 정책 승인값 확인 필요')
        yeonhui=current(db,YEONHUI_ID);other=current(db,OTHER_YEONNAM)
        if not yeonhui or yeonhui.payload.get('units',yeonhui.payload.get('planned_units'))!=96:raise ValueError('연희96호 보호 대상 확인 필요')
        if not other or '244-16' not in other.payload.get('name',''):raise ValueError('연남 가로주택 보호 대상 확인 필요')
        link=current(db,PLAN_BRIDGE);gov_doc=current(db,YEON_DOC)
        if not link or link.payload.get('project_id')!=YEON_ID or not gov_doc:raise ValueError('기존 정부8호 계획 연결 누락')
        if any(f.get('kind')!='PLAN' or f.get('units')!=8 for f in link.payload['facts']):raise ValueError('정부 계획 범위 변경')
        approval_before=[m.policy_id,m.program_id,m.status]
        old_basis=m.basis
        def put(kind,source,key,payload):
            eid=entity_id(kind,source,key);old=current(db,eid)
            if not apply:return eid,'preview'
            prior=deepcopy(old.payload) if old else {}
            row,outcome=upsert_revision(db,kind,source,key,payload,BATCH)
            if outcome!='unchanged':db.add(Audit(entity_id=eid,action='YEONNAM_SH_IDENTITY',before=prior,after=dict(payload,review_actor=ACTOR)))
            changes.append(dict(id=eid,kind=kind,result=outcome,revision_no=row.revision_no))
            return eid,outcome
        exclusions=[dict(relation='NOT_SAME_PROJECT',entity_id=YEONHUI_ID,name='연희 공공주택96호',reason='SH 동일 표 별도 행·별도 대지·8호와96호 구분'),
                    dict(relation='NOT_SAME_PROJECT',entity_id=OTHER_YEONNAM,name='연남동244-16 가로주택',reason='독립8호와 사업명·유형·사업장 불일치; 연남 지명만 같음. 관리 추정167호를 원천 확정 규모로 사용하지 않음')]
        source=dict(name='SH2025년11월 주요업무보고 · 연남동 공공임대주택8호',source_object_id=KEY,
                    sample_kind='document_evidence',publisher='서울주택도시개발공사(SH)',document_title='2025년11월 주요업무보고',
                    published_month='2025-11',source_date=None,source_page=79,source_page_index=78,base_date='2026-10-20',
                    evidence_url=URL,original_sha256=SHA,original_file='yeonnam-sh-20261020/A0069855.pdf',
                    checked_source_type='OFFICIAL',review_label='담당자 확인 완료 - 공식 자료: SH2025년11월 주요업무보고79쪽',
                    status='CONFIRMED',reviewed=True,verification_status='SOURCE_CONTENT_CHECKED',review_actor=ACTOR,
                    identity_resolution_status=RESOLVED,matched_project_ids=[YEON_ID],basis=BASIS,
                    region='서울특별시',municipality='마포구',units=8,planned_units=8,tenure='공공임대',
                    quantity_scope='INDEPENDENT_PROJECT_TOTAL_PLAN',identity=proof['yeonnam'],not_same_project=exclusions,
                    facts=historical_facts(),reference_facts=[dict(kind='REPORTED_PROGRESS',pct=1,as_of='2025-11',precision='MONTH',
                        activity='착공준비·토공사',basis='2025년 실적 열. 현재 공정률·실제 착공 사건으로 전용하지 않음')],
                    actual_admission_status='NOT_CONFIRMED',official_actual_verified=False,exclude_from_project_totals=True,
                    superseded_hypothesis='연남8호가 연희·연남 합본96호 일부일 수 있다는 가설 철회',
                    unverified_fields=['정확한 지번·주소','개별 인허가·공사 관리번호','실제 착공일','실제 준공일','실제 모집공고·회차'])
        docid,_=put('document_evidence','official_document',KEY,source)
        old=current(db,docid)
        evidence=dict(project_id=YEON_ID,name=source['name'],source_entity_id=docid,source_revision_no=old.revision_no if old else 1,
                      source_id='official_document',evidence_source_id='official_document',source_name=source['name'],evidence_url=URL,
                      units=8,facts=historical_facts(),status='CONFIRMED',reviewed=True,review_actor=ACTOR,review_label=source['review_label'],
                      checked_source_type='OFFICIAL',review_basis=BASIS,basis=BASIS,relation_type='SAME_PROJECT',base_date='2026-10-20')
        put('evidence_bridge','cross_source',YEON_ID+':'+docid,evidence)
        p=deepcopy(project.payload)
        p.update(developer='서울주택도시개발공사(SH)',land_area_sqm=277,building_count=1,floors_above=5,
                 unit_basis='SH2025년11월 업무보고79쪽의 독립 공공임대 사업 전체8호 · 정부4분기 계획8호와 별도 근거',
                 quantity_scope='INDEPENDENT_PROJECT_TOTAL_PLAN',official_supply_plan_units=8,
                 identity_resolution_status=RESOLVED,construction_scope_status=RESOLVED,
                 identity_source_id=docid,identity_evidence_url=URL,identity_exclusions=exclusions,
                 historical_schedule=dict(source_as_of='2025-11',planned_construction='2025-11',planned_completion='2026-10',precision='MONTH',reference_only=True),
                 mapping_basis=BASIS,stage_label='공식4분기 공급계획 · 독립8호 확인 · 실제 착공일 미확인')
        p['warnings']=[v for v in p.get('warnings',[]) if v!='CONSTRUCTION_SCOPE_UNRESOLVED']
        for warning in ['EXACT_ADDRESS_UNCONFIRMED','ACTUAL_START_UNCONFIRMED','ACTUAL_COMPLETION_UNCONFIRMED']:
            if warning not in p['warnings']:p['warnings'].append(warning)
        put('project',project.source_id,YEON_KEY,p)
        if apply and m.basis!=BASIS:
            m.basis=BASIS;m.revision_no+=1
            db.add(Audit(entity_id=YEON_ID,action='YEONNAM_MAPPING_BASIS',before=dict(basis=old_basis),after=dict(basis=BASIS,actor=ACTOR,approval_status_unchanged=True)))
        # Preserve the existing government quarter-plan and its facts; only correct the obsolete explanation.
        bp=deepcopy(link.payload);bp.update(basis=BASIS,review_basis=BASIS,identity_resolution_status=RESOLVED,identity_source_id=docid)
        put('evidence_bridge',link.source_id,YEON_ID+':'+PLAN_ID,bp)
        for target in [YEON_DOC,DESIGNER,CIS]:
            r=current(db,target)
            if not r:raise ValueError('기존 검토 증빙 누락 '+target)
            q=deepcopy(r.payload)
            q.update(identity_resolution_status=RESOLVED,identity_source_id=docid,identity_evidence_url=URL,
                     superseded_hypothesis='96호 일부·8호 배분 미분리 가설 철회. SH 표에서8호와96호 별도 사업 확인',
                     identity_correction=BASIS)
            if target==YEON_DOC:
                q.update(review_decision='SUPPLY_PLAN_ADMITTED_IDENTITY_VERIFIED_ACTUAL_HELD',construction_scope_status=RESOLVED,
                         construction_allocation_required=False,policy_basis=BASIS,basis=BASIS)
            elif target==DESIGNER:
                q.update(unverified_fields=['정확한 지번·주소','실제 착공일','실제 준공일','실제 모집공고·회차'],
                         official_corroboration='독립8호 사업 존재·규모·당시 계획은 SH 원문으로 추가 확인. 기존 비공식 출처의 검토 범위·등급은 유지')
            else:
                q['scope_caution']='연희·연남 합본 공사 제목만으로96호를8호의 전체·부분 물량으로 전용하지 않음. 계약 제목은 원문 그대로 보존.'
            put('document_evidence',r.source_id,q['source_object_id'],q)
        if apply:db.flush()
        after=protected_in_db(db)
        allowed={'revision:'+YEON_ID,'mapping:'+YEON_ID}
        unexpected=[k for k,v in before.items() if after.get(k)!=v and k not in allowed]
        plans_after={r.entity_id:r.payload_hash for r in db.scalars(select(Revision).where(Revision.kind=='agency_plan',Revision.superseded_at.is_(None)))}
        if unexpected or plans_before!=plans_after:raise ValueError('보호된 기존 자료 변경 '+str(unexpected))
        if approval_before!=[m.policy_id,m.program_id,m.status]:raise ValueError('정책·프로그램 승인 변경')
        protected_before={k:v for k,v in before.items() if k not in allowed}
        protected_after={k:after.get(k) for k in protected_before}
        result=dict(applied=apply,project_id=YEON_ID,source_document_id=docid,source_sha256=SHA,
                    source_page=79,changes=changes,added_projects=0,added_actual_facts=0,added_units=0,
                    approval_before=approval_before,approval_after=[m.policy_id,m.program_id,m.status],
                    protected_records=len(protected_before),protected_before_hash=digest(protected_before),
                    protected_after_hash=digest(protected_after),unexpected_changes=unexpected,
                    all_existing_agency_plans_unchanged=plans_before==plans_after,
                    notes=['기존8호 사업 ID 재사용','정부4분기 공급8호 기등록: 재가산0','과거 월 단위 계획은 reference_only로 보관; 최신 목표·실적 자동 반영 안 함','매핑 승인 유지; 설명 근거만 새 판본으로 정정'])
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');a=ap.parse_args()
    s=HomeService(engine_for());work=s.data_dir/'yeonnam-sh-20261020';proof=verify_pdf(work/'A0069855.pdf')
    (work/'verified_rows.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2))
    from backend.policy_delivery import build_delivery
    from scripts.build_continuation_review_20261020 import metrics
    before=metrics(build_delivery(s,date(2026,10,20),include_portfolio_comparisons=False))
    result=apply_identity(s,proof,a.apply)
    after=metrics(build_delivery(s,date(2026,10,20),include_portfolio_comparisons=False))
    result.update(metrics_before=before,metrics_after=after,all_metrics_unchanged=before==after)
    if before!=after:raise RuntimeError('집계 변화 확인 필요; 원문은 과거계획이며 실제 사건이 아님')
    name='applied.json' if a.apply else 'preview.json'
    if a.apply and not any(c['result']!='unchanged' for c in result['changes']):name='idempotence.json'
    (work/name).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
