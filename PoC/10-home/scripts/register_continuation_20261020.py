"""Register visually checked official plans and the evidenced Dangsu C5 link.

Run in the HOME container. Default is a read-only preview. Originals and their
checksums live in data/continuation-20261020; existing officer records are pinned.
"""
import argparse
import hashlib
import json
from collections import Counter
from datetime import date

from sqlalchemy import select, text

from backend.collectors import urban_project
from backend.db import Audit, Mapping, ProgramMapping, Revision, engine_for, entity_id, upsert_revision
from backend.lh_policy_followup import POLICY
from backend.lh_spring_followup import review_key
from backend.service import HomeService
from scripts.review_policy_readmission_20261019 import protected, digest

ACTOR='담당자 대행 · 계속 검증 사용자 지시 2026-10-20'
POLICY_URL='https://www.korea.kr/common/download.do?fileId=198344116#page=6'
NEW_KEY='reviewed:12047:수원당수:C5'
NEW_ID=entity_id('project','lh_policy_followup',NEW_KEY)
BASIS=('9·7 이행실적 공식 자료 PDF 6쪽의 수원당수 490호(단독→공동), '
       '국토부 고시 제2025-806호 PDF 7쪽 C-5의 170+320=490호 및 '
       '단독·생태마을 75호 감소/공동주택 490호 증가, LH 2026.05.29 PDF 2쪽 '
       '수원당수 C-5 490호를 대조했다. 지역·지구·전환 방식·호수·블록을 연결하여 '
       '9·7 LH 직접시행 전환·토지이용 효율화에 배정한다. 지구 순증은 415호이며 '
       '블록 공급량 490호와 구분한다. 지구계획 승인일을 주택 착공일로 사용하지 않는다.')


def main(apply=False):
    s=HomeService(engine_for());folder=s.data_dir/'continuation-20261020'
    image=json.loads((folder/'official-0813-image-plans.json').read_text())
    manifest=json.loads((folder/'followup-documents-manifest.json').read_text())
    if len(image['rows'])!=45 or sum(r['units'] for r in image['rows'])!=26695:
        raise ValueError('시각 대조한 45개 행·합계 변경')
    if image['original_sha256']!='a4e8f12daf2d421a44ed8c8c0c825a13495f9cf84d9ebedeaacbc1ebad86d8f4':
        raise ValueError('시각 검토한 PDF 판본 변경')
    if hashlib.sha256((folder/'official-0813-0.pdf').read_bytes()).hexdigest()!=image['original_sha256']:
        raise ValueError('공식 PDF 해시 불일치')
    for m in manifest:
        if m['status']!='SAVED' or hashlib.sha256((folder/m['file']).read_bytes()).hexdigest()!=m['sha256']:
            raise ValueError('추가 확보 문서 해시 확인 실패')
    notice=(folder/'notice-636472.txt').read_text()
    if not all(token in notice for token in ('C-5','170','320','8,181','7,766')):
        raise ValueError('수원당수 지구계획 근거 누락')
    before=protected(s);actions=[];links=[]
    from backend.delivery_operations import schedule_goals
    managed_supply={g['scope_id'] for g in schedule_goals(s,date(2026,10,20)) if g['stage']=='SUPPLY'}
    with s.sessions.begin() as db:
        if s.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(1019193)'))
        rows=db.scalars(select(Revision).where(Revision.superseded_at.is_(None),Revision.kind.in_(['agency_plan','project']))).all()
        projects=[r for r in rows if r.kind=='project']
        src=next((r for r in rows if r.kind=='agency_plan' and r.source_id=='lh_policy_followup'
                  and r.payload.get('source_object_id')=='12047:수원당수:C5'),None)
        if not src or src.payload.get('units')!=490 or src.payload.get('original_sha256')!='f438dd0901da281ceb81bf2ffe0ce1130707438f57d8835fb882980cd4d2109e':
            raise ValueError('LH C5 개별 계획 판본 변경')
        pg=db.scalar(select(ProgramMapping).where(ProgramMapping.name=='LH 직접시행 전환·토지이용 효율화',
                                                ProgramMapping.policy_id==POLICY,ProgramMapping.status=='CONFIRMED'))
        if not pg:raise ValueError('기존 승인 프로그램 없음')
        same=[r for r in projects if review_key(r.payload)==('경기도','수원당수','C5')]
        if any(r.entity_id!=NEW_ID for r in same):raise ValueError('동일 C5 블록 중복')
        # A later contract uses B4; do not create two projects for a possible alias.
        other=[r for r in projects if review_key(r.payload)==('경기도','수원당수','B4') or
               ('수원당수' in r.payload.get('name','') and r.payload.get('planned_units')==490 and r.entity_id!=NEW_ID)]
        if other:raise ValueError('수원당수 490호/B4 별칭 중복 사전 검토 필요')
        if same:
            m=db.scalar(select(Mapping).where(Mapping.project_id==NEW_ID))
            if not m or m.status!='CONFIRMED' or m.policy_id!=POLICY or m.program_id!=pg.id or same[0].payload.get('planned_units')!=490:
                raise ValueError('등록 후 담당자 변경 보존 필요')
        def save(kind,source,key,payload):
            if not apply:return entity_id(kind,source,key),1
            row,outcome=upsert_revision(db,kind,source,key,payload,'continuation-20261020')
            actions.append(dict(kind=kind,id=row.entity_id,outcome=outcome))
            if outcome!='unchanged':
                db.add(Audit(entity_id=row.entity_id,action='CONTINUATION_EVIDENCE_REVIEW',before={},
                             after=dict(actor=ACTOR,kind=kind,source_id=source,basis=payload.get('review_basis') or payload.get('basis'))))
            return row.entity_id,row.revision_no
        if not same:
            payload=urban_project('수원당수 C5','수원시','경기도',490,POLICY,'2026-05-29',pg.name)
            payload.update(district='수원당수',block='C5',developer='LH',tenure='공공주택 · 민간참여 공공분양 계획',
                source_object_id=NEW_KEY,evidence_url=src.payload['evidence_url'],policy_evidence_url=POLICY_URL,
                source_reference_id=src.entity_id,source_reference_revision=src.revision_no,
                source_document_sha256=src.payload['original_sha256'],mapping_basis=BASIS,
                source_scope='SINGLE_BLOCK',facts=[],registration_set='CONTINUATION_20261020',
                unit_basis='블록 전체 490호. 지구 순증 415호와 구분',schedule_basis='2027년 하반기 분양 계획 · 실제 착공 미확인')
            save('project','lh_policy_followup',NEW_KEY,payload)
            if apply:
                db.add(Mapping(project_id=NEW_ID,policy_id=POLICY,program_id=pg.id,status='CONFIRMED',
                               revision_no=1,basis=ACTOR+' · '+BASIS,evidence_url=POLICY_URL))
                db.add(Audit(entity_id=NEW_ID,action='MAPPING_REVIEW',before={},
                             after=dict(actor=ACTOR,policy_id=POLICY,program_id=pg.id,status='CONFIRMED',basis=BASIS)))
        def project_ids(district,blocks):
            return [r.entity_id for r in projects if review_key(r.payload) in [('인천광역시' if district.startswith('인천') else '경기도',district,b) for b in blocks]]
        document_links={
            'krx-dangsu-contract':project_ids('수원당수2',['B1','A1','A3']),
            'notice-636471':project_ids('수원당수2',['B1','A1','A3']),
            'notice-641646':project_ids('인천계양',['A16','A18']),
            'notice-635569':project_ids('인천계양',['A16','A18']),
            'notice-628726':project_ids('남양주왕숙2',['A6','A7']),
            'notice-636472':[NEW_ID],
            'notice-643252':project_ids('부천대장',['A9']),
        }
        for m in manifest:
            key='continuation-20261020:'+m['key'];pids=document_links.get(m['key'],[])
            basis=('지구·블록에 따른 원문 연결. 계약·지구계획 단계와 주택 착공을 구분. '
                   '담당자 관리 호수·일정은 유지하고 원문 판본 차이를 대조 근거로 보존.')
            confirmed_facts=[]
            if m['key']=='notice-643252':
                body=(folder/'notice-643252.txt').read_text()
                if len(pids)!=1 or not all(t in body for t in ('제2026-364호','568세대','574세대','증 6세대','2026년 07월 14일')):
                    raise ValueError('부천대장 A9 변경승인·호수 근거 변경')
                basis=('국토부 제2026-364호 2026.07.14: 부천대장 A9, 분양전환 공공임대, '
                       '대지 27,892㎡, 12개동의 사업규모를 568→574세대로 변경승인. '
                       'API PER_659498cd3ee4d1ca7910c9da의 568호는 변경 전 값과 일치. '
                       '574호는 이 날짜까지 승인된 총량이며 최초 승인일·2026년 신규 승인량이 아니다. 실제 착공 확인 없음.')
                confirmed_facts=[dict(stage='APPROVAL',kind='ACTUAL',date='2026-07-14',units=574,
                    precision='DAY',date_basis='OBSERVED_BY',source_event_date=None,observed_on='2026-07-14',
                    method='AMENDED_APPROVED_STOCK',basis=basis)]
            payload=dict(name=m['name'],sample_kind='document_evidence',source_object_id=key,
                source_date=m['source_date'],base_date=m['source_date'],date_precision='DAY',
                evidence_url=m.get('landing_url') or m['url'],attachment_url=m['url'],
                original_file='continuation-20261020/'+m['file'],original_sha256=m['sha256'],
                content_text=(folder/(m['key']+'.txt')).read_text(),matched_project_ids=pids,
                facts=confirmed_facts,units=None,planned_units=None,exclude_from_project_totals=True,
                verification_status='SOURCE_CONTENT_CHECKED',review_actor=ACTOR,review_basis=basis)
            sid,revision=save('document_evidence','official_document',key,payload)
            for pid in pids:
                bridge=dict(project_id=pid,name=m['name'],source_entity_id=sid,source_revision_no=revision,
                    evidence_source_id='official_document',source_id='official_document',source_name=m['name'],
                    evidence_url=payload['evidence_url'],units=None,facts=confirmed_facts,status='CONFIRMED',reviewed=True,
                    review_actor=ACTOR,relation_type='REVIEWED_AMENDMENT_APPROVAL' if confirmed_facts else 'REVIEWED_DOCUMENT_IDENTITY',basis=basis,base_date='2026-10-20')
                save('evidence_bridge','cross_source',pid+':'+sid,bridge)
                links.append(dict(project_id=pid,source_id=sid,kind='AMENDMENT_APPROVAL' if confirmed_facts else 'DOCUMENT_IDENTITY'))
        for r in image['rows']:
            raw_block=r['block'];key='0813-2027:'+r['district']+':'+raw_block
            target=[p for p in projects if review_key(r) and review_key(p.payload)==review_key(r)
                    and p.payload.get('planned_units')==r['units']]
            special=r['district']=='수원당수' and raw_block=='신설(전환)' and r['units']==490
            pids=[NEW_ID] if special else [target[0].entity_id] if len(target)==1 else []
            stamp='2027년 '+('상반기' if r['plan_half']=='H1' else '하반기')
            basis='공식 2026.08.13 PDF 15쪽 이미지 표 직접 확인: 지구·블록·분양 계획 호수 대조. '+stamp
            if special:basis+=' · 수원당수 전환 490호는 제2025-806호 C5 170+320호 및 LH 개별 공모와 연결'
            facts=[dict(stage='SUPPLY',kind='PLAN',date=stamp,precision='HALF_YEAR',units=r['units'],basis=basis)]
            payload=dict(r,name=r['district']+' '+raw_block,sample_kind='agency_plan',source_object_id=key,
                source_date='2026-08-13',base_date='2026-08-13',date_precision='DAY',planned_units=r['units'],
                evidence_url=image['source_url']+'#page=15',original_sha256=image['original_sha256'],
                original_file='continuation-20261020/official-0813-0.pdf',
                facts=facts,matched_project_ids=pids,policy_candidate_only=True,proposed_policy='UNASSIGNED',
                verification_status='SOURCE_CONTENT_CHECKED',review_actor=ACTOR,review_basis=basis,
                unit_basis='2027년 분양 계획 · 실제 공급·착공 실적 아님')
            sid,revision=save('agency_plan','official_document',key,payload)
            for pid in pids:
                mapping=db.scalar(select(Mapping).where(Mapping.project_id==pid)) if pid!=NEW_ID else None
                if pid!=NEW_ID and (not mapping or mapping.status!='CONFIRMED' or mapping.policy_id!=POLICY):continue
                reference_only=pid in managed_supply
                bridge=dict(project_id=pid,name=payload['name'],region=r['region'],source_entity_id=sid,
                    source_revision_no=revision,evidence_source_id='official_document',source_id='official_document',
                    source_name=payload['name'],evidence_url=payload['evidence_url'],units=r['units'],
                    facts=[] if reference_only else facts,reference_facts=facts if reference_only else [],
                    approved_schedule_preserved=reference_only,
                    status='CONFIRMED',reviewed=True,review_actor=ACTOR,relation_type='REVIEWED_SUPPLY_PLAN',
                    basis=basis,base_date='2026-10-20')
                save('evidence_bridge','cross_source',pid+':'+sid,bridge)
                links.append(dict(project_id=pid,source_id=sid,kind='SUPPLY_PLAN',units=r['units'],
                                  reference_only=reference_only))
    after=protected(s);changed=[k for k,v in before.items() if after.get(k)!=v]
    if changed:raise RuntimeError('기존 담당자 기록 변경 확인 필요')
    result=dict(applied=apply,new_project_id=NEW_ID,new_project_added=apply and not same,
        new_project_units=490,new_actual_construction_units=0,confirmed_approval_stock_units=574,
        approval_date_basis='OBSERVED_BY · 최초 승인일 또는 연간 신규 승인량 아님',plan_rows=45,plan_units=26695,
        links=links,actions=actions,action_counts=dict(Counter(a['outcome'] for a in actions)),
        protected_existing_records=len(before),protected_before=digest(before),
        protected_after=digest({k:after.get(k) for k in before}),changed_existing_keys=changed,basis=BASIS)
    filename='registration-preview.json'
    if apply:
        filename='registration-applied.json' if result['new_project_added'] else 'registration-refinement.json'
        if actions and all(a['outcome']=='unchanged' for a in actions):filename='registration-idempotence.json'
    (folder/filename).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in ('links','actions','basis')},ensure_ascii=False))
    print('link_counts',dict(Counter(r['kind'] for r in links)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true')
    main(parser.parse_args().apply)
