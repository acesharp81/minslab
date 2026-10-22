"""Delegated admission of two identified official Q4 projects to the policy portfolio.

The user adopted cumulative monitoring regardless of the original start year.
This is an officer management decision, not a claim of exclusive policy causation.
Source values, existing approvals, annual statistics and the 1.35m target are untouched.
"""
import argparse
import hashlib
import json
import re

from sqlalchemy import select, text
from backend.db import Audit, Mapping, ProgramMapping, Revision, engine_for, entity_id, upsert_revision
from backend.collectors import urban_project
from backend.service import HomeService
from scripts.review_policy_readmission_20261019 import protected, digest

POLICY = 'POL_2025_0907'
SOURCE = 'official_document'
BATCH = 'cumulative-q4-20261020'
PROGRAM = '건설형 공공임대'
ACTOR = 'Codex 담당자 대행 · 사용자 정책 누계 기준 확인 및 최종 반영 지시 2026-10-20'
BRIEF_URL = 'https://www.fsc.go.kr/comm/getFile?srvcId=BBSTY1&upperNo=87948&fileTy=ATTACH&fileNo=3'
BRIEF_SHA = 'e95a9929b94f9994fe963907a46b90e7761cd26a9811d1b36d7e7988f1ecdc1f'
SPECS = [
    dict(number=30, name='방화차고지 공공주택 건설사업', token='방화차고지', units=75,
         municipality='강서구', address='서울특별시 강서구 마곡동 1410-10',
         evidence_id='DOC_7674018c6c530643b5943e3c',
         source_key='seoul-investment-correct', source_month='2025-06',
         # The report observes an already-started project. Do not invent a June day.
         observed_date='2025-09-02', actual_date=None, completion='2027-02',
         evidence_sha='61a22b01cef2eb3192b655b8bcf2da81c774f6b4afccfe61873b796c811ae32c'),
    dict(number=31, name='독산동 산업문화어울림센터', token='독산동산업문화어울림센터', units=20,
         municipality='금천구', address='서울특별시 금천구 독산동 331-38',
         evidence_id='DOC_c7799ea535758d2b7a92bb90', source_key='doksan-building',
         source_month='2024-12', observed_date='2024-12-30', actual_date='2024-12-30',
         completion='2027-04-04',
         evidence_sha='ff77e7685d3c4a73b207a7bfc8b175c05823c9a5a8f0dbc45f7cf321fa96360b'),
]


def norm(value):
    return re.sub(r'[^가-힣A-Z0-9]', '', str(value or '').upper())


def admit(service, apply=False, verify_files=True):
    folder = service.data_dir/'external-match-review-20261020'
    manifest = {m['key']: m for m in json.loads((folder/'manifest.json').read_text())} if verify_files else {}
    if verify_files:
        for key, expected in [('official-brief', BRIEF_SHA)] + [(s['source_key'], s['evidence_sha']) for s in SPECS]:
            m = manifest[key]
            if m.get('sha256') != expected or hashlib.sha256((folder/m['file']).read_bytes()).hexdigest() != expected:
                raise ValueError('검토 원문 판본 변경: '+key)
    before = protected(service)
    results = []
    with service.sessions.begin() as db:
        if service.engine.dialect.name == 'postgresql':
            db.execute(text('SELECT pg_advisory_xact_lock(10203031)'))
        pg = db.scalar(select(ProgramMapping).where(ProgramMapping.name == PROGRAM,
                       ProgramMapping.policy_id == POLICY, ProgramMapping.status == 'CONFIRMED'))
        if not pg:
            raise ValueError('확인된 건설형 공공임대 프로그램 없음')
        projects = list(db.scalars(select(Revision).where(Revision.kind == 'project',
                                                        Revision.superseded_at.is_(None))))
        prepared = []
        for spec in SPECS:
            key = f"reviewed:official-20261016:Q4:{spec['number']}"
            pid = entity_id('project', SOURCE, key)
            source = db.scalar(select(Revision).where(Revision.entity_id == spec['evidence_id'],
                                                       Revision.superseded_at.is_(None)))
            if not source or source.kind != 'document_evidence' or source.payload.get('official_units') != spec['units']:
                raise ValueError('검토 원천 누락/수량 변경')
            if source.payload.get('original_sha256') != spec['evidence_sha']:
                raise ValueError('사업 근거 해시 변경')
            if source.payload.get('official_source_sha256') != BRIEF_SHA:
                raise ValueError('공식 발표 판본 변경')
            if source.payload.get('review_decision') not in ('OFFICIAL_ITEM_SOURCE_MATCH_CONFIRMED', 'CUMULATIVE_POLICY_ADMITTED'):
                raise ValueError('사업 동일성 검토 미완료')
            other = [r for r in projects if r.entity_id != pid and (
                spec['token'] in norm(r.payload.get('name')) or
                norm(r.payload.get('address')) == norm(spec['address']))]
            if other:
                raise ValueError('기존 사업 중복 검토 필요: '+','.join(r.entity_id for r in other))
            old = next((r for r in projects if r.entity_id == pid), None)
            if old:
                mapping = db.scalar(select(Mapping).where(Mapping.project_id == pid))
                if not mapping or mapping.status != 'CONFIRMED' or mapping.policy_id != POLICY or mapping.program_id != pg.id or old.payload.get('planned_units') != spec['units']:
                    raise ValueError('기존 승인 판정 변경 금지: '+pid)
                bridges = list(db.scalars(select(Revision).where(Revision.kind == 'evidence_bridge',
                               Revision.superseded_at.is_(None), Revision.payload['project_id'].as_string() == pid)))
                schedules = list(db.scalars(select(Revision).where(Revision.kind == 'execution_schedule',
                                 Revision.superseded_at.is_(None), Revision.payload['project_id'].as_string() == pid)))
                if len(bridges) != 2 or {r.payload['stage'] for r in schedules} != {'BUSINESS','APPROVAL','CONSTRUCTION'}:
                    raise ValueError('기존 등록 일부 누락: '+pid)
                results.append(dict(id=pid,name=spec['name'],units=spec['units'],result='existing_preserved'))
                continue
            basis = (
                ACTOR+' · 공식 10월 공급계획 항목과 기관 사업명·SH·주택유형·호수 대조 완료. '
                '공공임대 신축의 건설형 공공임대 프로그램에 연결. '
                '정책 관리대상 누계는 과거 착공 포함이라는 사용자 기준에 따른 관리 귀속 승인. '
                '9·7만으로 새로 발생한 물량 또는 2026년 신규 착공이라는 주장은 하지 않음. '
                + source.payload['review_basis'])
            prepared.append((spec, key, pid, source, basis))
        # All source/collision checks precede any writes; one transaction for both sites.
        for spec, key, pid, source, basis in prepared:
            if not apply:
                results.append(dict(id=pid,name=spec['name'],units=spec['units'],result='proposed',basis=basis))
                continue
            payload = urban_project(spec['name'], spec['municipality'], '서울특별시',
                                    spec['units'], POLICY, '2026-10-16', PROGRAM)
            payload.update(source_object_id=key, developer='SH', address=spec['address'],
                tenure='건설형 공공임대', stage='CONSTRUCTION', stage_label='착공 확인',
                evidence_url=source.payload['evidence_url'], policy_evidence_url=BRIEF_URL+'#page=6',
                mapping_basis=basis, unit_basis='공식 4분기 임대 공급계획과 동일 사업의 공공임대 전체 호수',
                source_reference_id=source.entity_id, source_reference_revision=source.revision_no,
                registration_set=BATCH, policy_admission_basis='OFFICER_CUMULATIVE_MONITORING',
                start_actual_date=spec['actual_date'], construction_source_month=spec['source_month'],
                construction_observed_by=spec['observed_date'],
                source_conflicts=source.payload.get('conflicts', []),
                facts=[], schedule_basis='공식 공급계획 2026년4분기 · 실제 공급 아님')
            row, _ = upsert_revision(db, 'project', SOURCE, key, payload, BATCH)
            db.add(Mapping(project_id=pid, policy_id=POLICY, program_id=pg.id, status='CONFIRMED',
                           revision_no=1, basis=basis, evidence_url=BRIEF_URL+'#page=6'))
            db.add(Audit(entity_id=pid,action='CUMULATIVE_POLICY_ADMISSION',before={},after=dict(
                actor=ACTOR,basis=basis,policy_id=POLICY,program_id=pg.id,units=spec['units'])))
            # Keep exact source date vs report observation separate.
            start = dict(stage='CONSTRUCTION',kind='ACTUAL',date=spec['observed_date'],units=spec['units'],
                         date_basis='EVENT' if spec['actual_date'] else 'OBSERVED_BY',
                         source_event_date=spec['actual_date'], observed_on=spec['observed_date'],
                         source_event_month=spec['source_month'], basis=(
                             '건설알림이 본공사 착공일 채택 · 시의회 날짜 차이 별도 보존' if spec['actual_date']
                             else '시의회 2025-09-02 보고에서 2025년6월 착공 확인 · 9월2일은 확인 상한, 실제 착공일 아님'))
            stage_facts = [start, dict(stage='COMPLETION',kind='PLAN',date=spec['completion'],
                                     units=spec['units'],basis='기관 원문 준공 예정 · 실준공 아님')]
            bridge = dict(project_id=pid,name=spec['name'],region='서울특별시',
                source_entity_id=source.entity_id,source_revision_no=source.revision_no,
                evidence_source_id=SOURCE,source_id=SOURCE,source_name=source.payload['name'],
                evidence_url=source.payload['evidence_url'],units=spec['units'],facts=stage_facts,
                status='CONFIRMED',reviewed=True,review_actor=ACTOR,
                relation_type='OFFICIAL_ITEM_SAME_PROJECT',basis=basis,base_date='2026-10-20')
            b,_ = upsert_revision(db,'evidence_bridge','cross_source',pid+':'+source.entity_id,bridge,BATCH)
            db.add(Audit(entity_id=b.entity_id,action='CUMULATIVE_STAGE_LINK',before={},after=bridge))
            plan_payload = dict(name=spec['name']+' · 공식 2026년4분기 공급계획',sample_kind='document_evidence',
                source_object_id=key+':supply-plan',base_date='2026-10-16',source_date='2026-10-16',
                evidence_url=BRIEF_URL+'#page=6',original_sha256=BRIEF_SHA,
                original_file='external-match-review-20261020/official-brief.pdf',source_page=6,
                official_row_id=f"2026-10-16:Q4:{spec['number']}",matched_project_ids=[pid],
                facts=[dict(stage='SUPPLY',kind='PLAN',date='2026년4분기',units=spec['units'],
                            basis='공식 발표 4분기 공급계획 · 실제 모집·계약 아님')],
                units=spec['units'],exclude_from_project_totals=True,verification_status='SOURCE_CONTENT_CHECKED')
            plan,_ = upsert_revision(db,'document_evidence',SOURCE,plan_payload['source_object_id'],plan_payload,BATCH)
            bridge2 = dict(bridge,source_entity_id=plan.entity_id,source_revision_no=plan.revision_no,
                           source_name=plan_payload['name'],evidence_url=plan_payload['evidence_url'],
                           facts=plan_payload['facts'])
            b2,_ = upsert_revision(db,'evidence_bridge','cross_source',pid+':'+plan.entity_id,bridge2,BATCH)
            db.add(Audit(entity_id=b2.entity_id,action='CUMULATIVE_SUPPLY_PLAN_LINK',before={},after=bridge2))
            # Known completed milestones form the officer's opening plan balance.
            # This is explicitly adopted management data, never a fabricated original plan.
            for stage in ('BUSINESS','APPROVAL','CONSTRUCTION'):
                skey=pid+':'+stage
                schedule=dict(project_id=pid,name=spec['name'],region='서울특별시',policy_id=POLICY,
                    key=skey,stage=stage,due_date=spec['observed_date'],units=spec['units'],
                    status='CONFIRMED',origin='MANUAL',responsible_org='SH',actor=ACTOR,
                    input_rule='CONFIRMED_REACHED_OPENING_BALANCE',
                    basis='담당자 누적 관리 기초량: 확인된 착공 물량과 선행 단계 도달량을 연말 계획 누계에도 포함. 원래 사업화·허가일 또는 최초 계획일을 뜻하지 않음.',
                    evidence_url=source.payload['evidence_url'],base_date='2026-10-20',
                    baseline=dict(due_date=spec['observed_date'],units=spec['units'],origin='MANUAL',
                                  accepted_on='2026-10-20',label='확인된 단계 도달량의 관리 기초선'),
                    shift_days=0)
                sr,_=upsert_revision(db,'execution_schedule','officer',skey,schedule,BATCH)
                db.add(Audit(entity_id=sr.entity_id,action='CUMULATIVE_OPENING_BALANCE',before={},after=schedule))
            old_source=dict(source.payload)
            updated=dict(old_source,review_decision='CUMULATIVE_POLICY_ADMITTED',
                         policy_mapping_status='CONFIRMED',proposed_policy=POLICY,
                         matched_project_ids=[pid],policy_basis=basis,review_actor=ACTOR)
            updated_source,_=upsert_revision(db,'document_evidence',source.source_id,
                                             old_source['source_object_id'],updated,BATCH)
            db.add(Audit(entity_id=updated_source.entity_id,action='CUMULATIVE_REVIEW_ADMITTED',
                         before={'review_decision':old_source['review_decision']},
                         after={'review_decision':updated['review_decision'],'project_id':pid,'basis':basis}))
            results.append(dict(id=pid,name=spec['name'],units=spec['units'],result='added',basis=basis))
    after=protected(service)
    changed=[k for k,v in before.items() if after.get(k)!=v]
    if changed:
        raise ValueError('기존 승인값 변경: '+str(changed))
    return dict(applied=apply,projects=results,existing_approvals_unchanged=True,
                before_hash=digest(before),protected_after_hash=digest({k:after[k] for k in before}),
                added_units=sum(p['units'] for p in results if p['result']=='added'),
                held=dict(name='연남동 공공임대주택',units=8,reason='합본 공사에서 개별 현장 범위·착공 분리 미확보'))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    service=HomeService(engine_for())
    result=admit(service,args.apply)
    folder=service.data_dir/BATCH
    folder.mkdir(exist_ok=True)
    path=folder/('applied.json' if args.apply else 'preview.json')
    if path.exists() and args.apply and all(p['result']=='existing_preserved' for p in result['projects']):
        path=folder/'idempotence.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))
