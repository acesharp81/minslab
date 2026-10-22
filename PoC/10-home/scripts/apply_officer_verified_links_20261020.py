"""Delegated source-link review and plan-only admission; preserve existing approvals."""
import argparse
import hashlib
import json
from datetime import date
from sqlalchemy import select, text
from backend.db import Revision, Mapping, ProgramMapping, Audit, entity_id, upsert_revision, engine_for
from backend.service import HomeService
from backend.collectors import urban_project
from scripts.review_policy_readmission_20261019 import protected, digest

BATCH='officer-additional-links-20261020'
ACTOR='담당자 대행 · 사용자 추가 매핑 지시 2026-10-20'
POLICY='POL_2025_0907'
BRIEF_URL='https://www.fsc.go.kr/comm/getFile?srvcId=BBSTY1&upperNo=87948&fileTy=ATTACH&fileNo=3'
BRIEF_SHA='e95a9929b94f9994fe963907a46b90e7761cd26a9811d1b36d7e7988f1ecdc1f'
YEON_DOC='DOC_3725d8e3826e7b58dbf23eee'
YEON_KEY='reviewed:official-20261016:Q4:32'
YEON_ID=entity_id('project','official_document',YEON_KEY)
LINKS={
 'EVI_f35803b2e1648bdf8a38eaa1':('인천계양 A17','PRO_12d91632b8ca640e1505869f','CONTAINED_SCOPE'),
 'EVI_95d57c4dda3aa78b13c9d72c':('흑석11','PRO_af0e615a920526eee9302fe0','SAME_SCOPE'),
 'EVI_7fce03be7a065e5877f16274':('신림2','PRO_8afa3f6b5386e8b6e5f1eda2','SAME_SCOPE')}
CASES=[('고양창릉',2300,'S3 1,282+S4 1,024=2,306호 직접 원천으로 개략 규모 대응. 공식 전체 구성 블록의 동일성은 미확정.'),
 ('인천계양',2300,'당해 직접 착공 확인분 A17 463호. 공식 지구 전체 2,300호를 해당 블록에 복사하지 않음.'),
 ('하남교산',1100,'사업 규모1,115호, LH 공사현황 착공일2024-10-30. 공식 당해 실적 인정 범위 미확정.'),
 ('남양주왕숙2',1100,'A1·A3 1,498호는2025년 착공 원천. 공식1,100호 구성 블록 미확정.'),
 ('부천대장',600,'직접 원천의 당해 A2·A12 1,343호와 공식600호의 포함 블록 미확정.'),
 ('중계본동',3100,'사업 규모3,178호 대응. 관리 착공일2026-08-15는 추정이며 실제 사건일 확정 아님.'),
 ('흑석11',1500,'서면1,500호·구두2,500호 상충. 사업 규모1,515호는 서면 개략값에 대응. 기존 관측일 보존.'),
 ('신림2',1400,'사업 규모1,430호·공식 기착공 관측을 대조. 실제 착공일을 발표일로 치환하지 않음.')]

def current(db,eid):
    return db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))

def protected_in_db(db):
    result={f'revision:{r.entity_id}':r.payload_hash for r in db.scalars(select(Revision).where(
        Revision.superseded_at.is_(None),Revision.kind.in_(['project','project_profile','execution_schedule'])))}
    for m in db.scalars(select(Mapping)):
        result['mapping:'+m.project_id]=[m.policy_id,m.program_id,m.status,m.revision_no,m.basis,m.evidence_url]
    for p in db.scalars(select(ProgramMapping)):
        result['program:'+p.id]=[p.name,p.policy_id,p.status]
    return result

def apply_reviews(service,apply=False,verify_files=True):
    if verify_files:
        body=(service.data_dir/BATCH/'official.pdf').read_bytes()
        if hashlib.sha256(body).hexdigest()!=BRIEF_SHA:raise ValueError('공식 원문 해시 변경')
    before=protected(service);results=[]
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(10203032)'))
        before=protected_in_db(db)
        pg=db.scalar(select(ProgramMapping).where(ProgramMapping.name=='건설형 공공임대',ProgramMapping.policy_id==POLICY,ProgramMapping.status=='CONFIRMED'))
        if not pg:raise ValueError('확인된 공공임대 프로그램 없음')
        doc=current(db,YEON_DOC)
        if not doc or doc.payload.get('official_units')!=8 or doc.payload.get('official_source_sha256')!=BRIEF_SHA or doc.payload.get('official_stage')!='SUPPLY' or doc.payload.get('official_kind')!='PLAN':
            raise ValueError('연남 공식8호 공급계획 근거 불일치')
        projects=list(db.scalars(select(Revision).where(Revision.kind=='project',Revision.superseded_at.is_(None))))
        collisions=[p for p in projects if p.entity_id!=YEON_ID and p.payload.get('name','').replace(' ','')=='연남동공공임대주택']
        if collisions:raise ValueError('기존 연남 사업 중복 대조 필요')
        existing=current(db,YEON_ID)
        if existing:
            m=db.scalar(select(Mapping).where(Mapping.project_id==YEON_ID))
            if existing.payload.get('planned_units')!=8 or not m or m.policy_id!=POLICY or m.status!='CONFIRMED' or m.program_id!=pg.id:
                raise ValueError('기존 연남 승인값 충돌')
        pending=[]
        for eid,(name,pid,relation) in LINKS.items():
            link=current(db,eid)
            if not link:raise ValueError('검토 연결 누락 '+eid)
            p=link.payload;target=current(db,pid)
            if entity_id('evidence_bridge','cross_source',pid+':'+p['source_entity_id'])!=link.entity_id:raise ValueError('연결 식별키 충돌')
            if p['project_id']!=pid or p.get('relation_type')!=relation or not target or name.replace(' ','') not in target.payload['name'].replace(' ',''):
                raise ValueError('연결 대상 변경 '+eid)
            m=db.scalar(select(Mapping).where(Mapping.project_id==pid))
            if not m or m.status!='CONFIRMED' or m.policy_id!=POLICY:raise ValueError('확인된 정책 연결 필요')
            source=db.scalar(select(Revision).where(Revision.entity_id==p['source_entity_id'],Revision.revision_no==p['source_revision_no']))
            if not source:raise ValueError('원천 고정 판본 누락')
            if p.get('status')=='RELEASED':raise ValueError('해제된 연결 보존')
            if name=='인천계양 A17':
                fs=p['facts']
                if not fs or any(f.get('scope_units')!=309 or f.get('source_total_units')!=463 for f in fs):raise ValueError('A17 유형 범위 미확정')
                if any(f.get('kind')=='ACTUAL' and f.get('milestone')=='CONSTRUCTION' for f in fs):raise ValueError('A17 공정일을 착공일로 전용 금지')
            pending.append((link,name))
        # Validate every referenced project before any write.
        named=[]
        mappings={m.project_id:m for m in db.scalars(select(Mapping).where(Mapping.policy_id==POLICY,Mapping.status=='CONFIRMED'))}
        for name,units,basis in CASES:
            members=sorted(p.entity_id for p in projects if p.entity_id in mappings and name.replace(' ','') in p.payload['name'].replace(' ',''))
            if not members:raise ValueError('공식 언급 사업 연결 누락 '+name)
            named.append((name,units,basis,members))
        def put(kind,source,key,payload,action):
            old=current(db,entity_id(kind,source,key));prior=dict(old.payload) if old else {}
            # A later SH row-level review supersedes this batch's 96-unit hypothesis.
            # Replaying an earlier admission must not restore its obsolete explanation.
            if old and prior.get('identity_resolution_status')=='INDEPENDENT_PROJECT_VERIFIED' and kind in ('document_evidence','evidence_bridge'):
                return old.entity_id,'newer_identity_preserved'
            if not apply:return entity_id(kind,source,key),'preview'
            row,outcome=upsert_revision(db,kind,source,key,payload,BATCH)
            if outcome!='unchanged':db.add(Audit(entity_id=row.entity_id,action=action,before=prior,after=dict(payload,actor=ACTOR)))
            return row.entity_id,outcome
        for link,name in pending:
            p=link.payload
            if p.get('status')=='CONFIRMED' and p.get('reviewed'):
                results.append(dict(kind='SOURCE_LINK',id=link.entity_id,name=name,result='existing_confirmed'));continue
            basis=(ACTOR+' · 원천 사업명·지역·보유 사업 식별 및 고정 판본 대조. '+
                   ('공공분양309호/전체463호 유형 구분 근거를 유지하며 공정률과 계획만 확인. 공정 확인일을 실제착공일로 전용하지 않음.' if name=='인천계양 A17' else
                    '서울 정비사업 정보몽땅의 동일 구역명·사업장 원천을 연결. 원천 추진경과 사실을 보존하고 실제 착공일·물량을 새로 입력하지 않음.'))
            payload=dict(p,status='CONFIRMED',reviewed=True,review_basis=basis,review_actor=ACTOR,reviewed_on='2026-10-20')
            rid,outcome=put('evidence_bridge','cross_source',p['project_id']+':'+p['source_entity_id'],payload,'OFFICER_LINK_CONFIRMED')
            results.append(dict(kind='SOURCE_LINK',id=rid,name=name,result=outcome,project_id=p['project_id']))
        basis=(ACTOR+' · 공식4분기 수도권 공공임대 명세의 연남동8호를 건설형 공공임대 프로그램의 정책 누적 관리대상으로 채택. '
               '공식 명시 공급계획 등록이며 9·7만의 신규 발생 물량이라는 인과 주장 아님. 합본96호와의 동일 현장·착공 배분은 미확정.')
        if not existing:
            project=urban_project('연남동 공공임대주택','마포구','서울특별시',8,POLICY,'2026-10-16','건설형 공공임대')
            project.update(source_object_id=YEON_KEY,tenure='공공임대',stage='PLANNING',stage_label='공식4분기 공급계획 · 착공 개별 미확인',
                evidence_url=BRIEF_URL+'#page=6',policy_evidence_url=BRIEF_URL+'#page=6',mapping_basis=basis,
                unit_basis='공식 2026년4분기 공공임대 공급계획8호 · 사업 전체 건설물량 확정 아님',
                quantity_scope='OFFICIAL_SUPPLY_PLAN',policy_admission_basis='OFFICER_CUMULATIVE_MONITORING',
                registration_set=BATCH,construction_scope_status='UNRESOLVED',facts=[],start_actual_date=None,
                source_reference_id=doc.entity_id,source_reference_revision=doc.revision_no,schedule_basis='공식4분기 예정 범위',
                warnings=['CONSTRUCTION_SCOPE_UNRESOLVED','EXACT_ADDRESS_UNCONFIRMED'])
            rid,outcome=put('project','official_document',YEON_KEY,project,'OFFICER_PLAN_ADMITTED')
            if apply:
                db.add(Mapping(project_id=rid,policy_id=POLICY,program_id=pg.id,status='CONFIRMED',revision_no=1,basis=basis,evidence_url=BRIEF_URL+'#page=6'))
                db.add(Audit(entity_id=rid,action='OFFICER_POLICY_CONFIRMED',before={},after=dict(actor=ACTOR,policy_id=POLICY,program_id=pg.id,units=8,basis=basis)))
        else:rid,outcome=YEON_ID,'existing_preserved'
        results.append(dict(kind='POLICY_PLAN',id=rid,name='연남동 공공임대주택',units=8,result=outcome))
        plan=dict(name='연남동 공공임대주택 · 공식4분기 공급계획',sample_kind='agency_plan',source_object_id=BATCH+':Q4:32',
            region='서울특별시',municipality='마포구',units=8,planned_units=8,tenure='공공임대',base_date='2026-10-16',source_date='2026-10-16',
            evidence_url=BRIEF_URL+'#page=6',original_sha256=BRIEF_SHA,review_actor=ACTOR,verification_status='SOURCE_CONTENT_CHECKED',
            quantity_scope='OFFICIAL_SUPPLY_PLAN',facts=[dict(stage='SUPPLY',kind='PLAN',date='2026년4분기',date_label='2026년4분기',units=8,precision='QUARTER',basis='공식4분기 임대 공급계획 · 실제 모집·착공·입주 실적 아님')])
        plan_id,act=put('agency_plan','official_document',plan['source_object_id'],plan,'OFFICER_PLAN_EVIDENCE')
        bridge=dict(project_id=YEON_ID,name=plan['name'],region='서울특별시',source_entity_id=plan_id,
            source_revision_no=(current(db,plan_id).revision_no if apply else 1),source_id='official_document',evidence_source_id='official_document',
            source_name=plan['name'],evidence_url=plan['evidence_url'],units=8,facts=plan['facts'],status='CONFIRMED',reviewed=True,
            review_actor=ACTOR,review_basis=basis,relation_type='OFFICIAL_PLAN_ITEM',basis=basis,base_date='2026-10-20')
        put('evidence_bridge','cross_source',YEON_ID+':'+plan_id,bridge,'OFFICER_PLAN_LINK')
        prior=dict(doc.payload);updated=dict(prior,policy_mapping_status='CONFIRMED',proposed_policy=POLICY,program_id=pg.id,
            matched_project_ids=[YEON_ID],review_decision='SUPPLY_PLAN_ADMITTED_START_HELD',policy_basis=basis,review_actor=ACTOR,
            construction_scope_status='UNRESOLVED',construction_allocation_confirmed=False)
        put('document_evidence',doc.source_id,prior['source_object_id'],updated,'OFFICER_SCOPE_SEPARATED')
        for name,units,note,members in named:
            payload=dict(name=name+' · 10月 착공 검증 담당자 재확인'.replace('10月','10월'),sample_kind='document_evidence',
                source_object_id=BATCH+':named:'+name,source_date='2026-10-16',base_date='2026-10-20',date_precision='COLLECTION',
                evidence_url=BRIEF_URL+'#page=4',original_sha256=BRIEF_SHA,review_actor=ACTOR,review_decision='NAMED_PROJECT_LINK_RECONFIRMED',
                proposed_policy=POLICY,policy_mapping_status='CONFIRMED',matched_project_ids=members,facts=[],units=None,planned_units=None,
                official_approx_units=units,quantity_scope='DISTRICT_OR_PROJECT_REFERENCE',official_block_membership_verified=False,
                basis=note,exclude_from_project_totals=True,comparison_eligible=False,
                source_conflicts=({'oral_units':2500,'written_approx_units':1500} if name=='흑석11' else {}))
            rid,outcome=put('document_evidence','officer',payload['source_object_id'],payload,'OFFICER_NAMED_RECHECK')
            results.append(dict(kind='NAMED_REFERENCE',id=rid,name=name,result=outcome,project_ids=members,basis=note))
        # Flush and verify before the transaction can commit.
        if apply:db.flush()
        after=protected_in_db(db);changed=[k for k,v in before.items() if after.get(k)!=v]
        if changed:raise ValueError('기존 사업·매핑·일정 변경 감지 '+str(changed))
    return dict(applied=apply,actor=ACTOR,results=results,old_business_records_unchanged=True,protected_before_hash=digest(before),
        protected_after_hash=digest({k:after.get(k) for k in before}),added_project_units=8 if apply and not existing else 0,
        construction_added_units=0,unresolved='연남 개별 착공·계양/왕숙2/대장 공식 구성 블록·교산 실적시점은 미확정')

def main():
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');a=p.parse_args();s=HomeService(engine_for())
    from backend.policy_delivery import build_delivery
    from scripts.build_continuation_review_20261020 import metrics
    w=s.data_dir/BATCH;w.mkdir(exist_ok=True)
    before=metrics(build_delivery(s,date(2026,10,20),include_portfolio_comparisons=False))
    result=apply_reviews(s,a.apply)
    after=metrics(build_delivery(s,date(2026,10,20),include_portfolio_comparisons=False))
    result.update(metrics_before=before,metrics_after=after)
    assert before['CONSTRUCTION']==after['CONSTRUCTION']
    assert all(before[k]['actual']==after[k]['actual'] for k in before)
    assert after['SUPPLY']['year_end']-before['SUPPLY']['year_end']==result['added_project_units']
    name='applied.json' if a.apply else 'preview.json'
    if a.apply and result['added_project_units']==0:name='idempotence.json'
    (w/name).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
