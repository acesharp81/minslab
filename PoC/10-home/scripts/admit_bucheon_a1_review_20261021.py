"""Officer admission of a named public-housing case with explicit uncertainty."""
import json
from pathlib import Path
from copy import deepcopy

BATCH = 'bucheon-a1-review-20261021'
FOLDER = 'external_diagnostic_review_20261021'
PROJECT_KEY = 'bucheon-yeokgok:A1:R26BK01440851'
PROGRAM = 'PRG_1bb8c2898f442905b7224bac'


def main():
    from sqlalchemy import select, text
    from backend.db import Revision, Mapping, ProgramMapping, Audit, entity_id, upsert_revision, engine_for, now
    from backend.service import HomeService
    service = HomeService(engine_for())
    pid = entity_id('project', 'official_document', PROJECT_KEY)
    results = []
    with service.sessions.begin() as db:
        db.execute(text('SELECT pg_advisory_xact_lock(9072026)'))

        def current(eid):
            return db.scalar(select(Revision).where(Revision.entity_id == eid, Revision.superseded_at.is_(None)))

        def protect():
            return ([(r.entity_id, r.payload_hash) for r in db.scalars(select(Revision).where(
                Revision.superseded_at.is_(None), Revision.entity_id != pid,
                Revision.kind.in_(['project', 'project_profile', 'execution_schedule']))
                .order_by(Revision.entity_id)) if r.payload.get('project_id') != pid],
                [(m.project_id, m.policy_id, m.program_id, m.status, m.revision_no)
                 for m in db.scalars(select(Mapping).where(Mapping.project_id != pid).order_by(Mapping.project_id))])

        before = protect()
        pg = db.get(ProgramMapping, PROGRAM)
        assert pg and pg.status == 'CONFIRMED' and pg.policy_id == 'POL_2025_0907'
        tender = current('DOC_8a670d0ed212959af7fd608d')
        contractor = current('DOC_b07e4706bed828b41f846c6c')
        assert tender.payload['contract_housing_units'] == 1160
        assert tender.payload['block'] == contractor.payload['block'] == 'A1'
        basis = ('담당자 확인 - 공식 자료: 정부2026-10-16 부천역곡 약1,200호 사례와 조달청 A1통합공공임대1,160호; '
            '담당자 확인 - 비공식 자료: 동원건설산업 신규수주알림·진행중 사업목록. '
            '지구·A1블록·춘의동317·LH발주·연면적112,120.28㎡ 대조. 사용자 담당자 대행 지시에 따라 '
            '건설형 공공임대 프로그램의 정책 누적 관리대상으로 채택. '
            '정부가 A1블록을 직접 명시하거나 10월둘째주 산입을 확정했다는 뜻은 아님. '
            '공사기간2026-06-30 개시는 실제착공일로 채택하지 않음.')

        def put(kind, sid, key, payload):
            old = current(entity_id(kind, sid, key))
            prior = deepcopy(old.payload) if old else {}
            r, outcome = upsert_revision(db, kind, sid, key, payload, BATCH)
            if outcome != 'unchanged':
                db.add(Audit(entity_id=r.entity_id, action='OFFICER_CASE_ADMISSION', before=prior, after=payload))
            results.append(dict(kind=kind, id=r.entity_id, outcome=outcome))
            return r

        label = '담당자 확인 - 비공식 자료: 동원건설산업 진행중 사업목록; 규모는 조달청 공식1,160호'
        p = dict(name='부천역곡 A1', region='경기도', municipality='부천시', district='부천역곡', block='A1',
            address='경기도 부천시 원미구 춘의동317', developer='LH', contractor='동원건설산업',
            program='건설형 공공임대', tenure='통합공공임대', planned_units=1160, units=1160,
            stage='CONSTRUCTION', stage_label='담당자 확인 공사 진행 · 정확한 착공일 미확정',
            start_actual_date=None, construction_start_evidence=None,
            base_date='2026-10-21', source_date='2026-04-03', source_publication_date='2026-04-03',
            evidence_url=tender.payload['evidence_url'], proposed_policy='POL_2025_0907',
            policy_evidence_url='https://www.fsc.go.kr/comm/getFile?srvcId=BBSTY1&upperNo=87948&fileTy=ATTACH&fileNo=3#page=4',
            mapping_basis=basis, policy_admission_basis='OFFICER_CUMULATIVE_MONITORING',
            official_case_block_verified=False, official_case_period_verified=False,
            quantity_scope='SINGLE_BLOCK', unit_basis='조달청 입찰설명서 A1 통합공공임대 전체1,160호',
            checked_source_type='OFFICIAL', verification_status='SOURCE_CONTENT_CHECKED', facts=[],
            source_reference_id=tender.entity_id, source_reference_revision=tender.revision_no,
            source_object_id=PROJECT_KEY, availability='PUBLIC',
            warnings=['EXACT_START_DATE_UNCONFIRMED', 'OFFICIAL_CASE_INCLUSION_UNCONFIRMED'])
        put('project', 'official_document', PROJECT_KEY, p)
        m = db.scalar(select(Mapping).where(Mapping.project_id == pid))
        mapping_created = m is None
        if m:
            assert m.status == 'CONFIRMED' and m.program_id == PROGRAM
        else:
            db.add(Mapping(project_id=pid, policy_id='POL_2025_0907', program_id=PROGRAM,
                status='CONFIRMED', revision_no=1, basis=basis, evidence_url=p['policy_evidence_url'], reviewed_at=now()))
            db.add(Audit(entity_id=pid, action='OFFICER_POLICY_CONFIRMED', before={}, after=dict(
                policy_id='POL_2025_0907', program_id=PROGRAM, actor='사용자 지시 담당자 대행', basis=basis)))
        put('evidence_bridge', 'cross_source', pid + ':' + tender.entity_id, dict(
            project_id=pid, source_entity_id=tender.entity_id, source_revision_no=tender.revision_no,
            source_id='official_document', source_name='조달청 부천역곡 A1 통합공공임대 입찰설명서',
            source_type='OFFICIAL', checked_source_type='OFFICIAL', units=1160, facts=[],
            status='CONFIRMED', reviewed=True, review_label='공식 자료 자동 매핑 - 조달청 A1 1,160호',
            relation_type='EXACT_PROCUREMENT_BLOCK_ADDRESS', basis='공고번호·A1블록·주소·연면적·공식호수 동일',
            evidence_url=tender.payload['evidence_url'], base_date='2026-10-21'))
        event = dict(stage='CONSTRUCTION', kind='ACTUAL', date='2026-10-21', units=1160,
            milestone='CONSTRUCTION', date_basis='OBSERVED_BY', observed_on='2026-10-21',
            source_event_date=None, source_type='NON_OFFICIAL', basis=label,
            evidence_url='https://dwce.co.kr/business/performance')
        put('evidence_bridge', 'cross_source', pid + ':' + contractor.entity_id, dict(
            project_id=pid, source_entity_id=contractor.entity_id, source_revision_no=contractor.revision_no,
            source_id='external_officer', source_name='동원건설산업 부천역곡 A1 진행 현황',
            source_type='NON_OFFICIAL', checked_source_type='NON_OFFICIAL', units=1160,
            facts=[event], status='CONFIRMED', reviewed=True, review_label=label,
            relation_type='OFFICER_EXACT_BLOCK_ADDRESS_CONTRACT', basis=basis,
            evidence_url='https://dwce.co.kr/business/performance', base_date='2026-10-21'))
        old_profile=current(entity_id('project_profile','manual_project',pid))
        changed_at=(old_profile.payload.get('progress',{}).get('CONSTRUCTION',{}).get('changed_at')
                    if old_profile else None) or now().isoformat()
        put('project_profile', 'manual_project', pid, dict(project_id=pid, name=p['name'],
            base_date='2026-10-21', overrides={}, targets={}, progress=dict(CONSTRUCTION=dict(
                origin='MANUAL', actor='사용자 지시 담당자 대행', reason=basis,
                input_rule='OFFICER_VERIFIED_SOURCE', input_basis=label, inferred=False,
                event_date='2026-10-21', units=1160, date_basis='OBSERVED_BY', source_event_date=None,
                observed_on='2026-10-21', source_type='NON_OFFICIAL', review_label=label,
                evidence_url='https://dwce.co.kr/business/performance',
                source_entity_id=contractor.entity_id, batch_id=BATCH,changed_at=changed_at))))
        put('collection_research', 'external_officer', BATCH + ':ADMISSION', dict(
            sample_kind='collection_research', name='부천역곡 A1 담당자 정책관리 채택 및 발표 시점 유보',
            project_ids=[pid], source_entity_ids=[tender.entity_id, contractor.entity_id],
            policy_mapping_status='CONFIRMED', status='CONFIRMED', checked_source_type='MIXED',
            review_label=label, basis=basis, facts=[], exclude_from_project_totals=True,
            evidence_url=p['policy_evidence_url'], base_date='2026-10-21',
            comparison_status='EVENT_DATE_PENDING', prior_candidate_status='HOLD_SUPERSEDED',
            review_decision='정책 누적 관리 포함. 정부 약1,200호 산입 확정과 정확한 착공일은 유보'))
        assert protect() == before
    result = dict(project_id=pid, units=1160, new_policy_assignment=int(mapping_created), source_quantity_type='OFFICIAL',
        construction_status_source='OFFICER_CONFIRMED_NON_OFFICIAL', construction_date_basis='OBSERVED_BY',
        exact_start_date=None, official_case_inclusion_verified=False, changes=results,
        changed=sum(r['outcome'] != 'unchanged' for r in results), existing_approved_values_preserved=True)
    out = Path('/app/data') / FOLDER
    (out / ('admission_applied.json' if result['changed'] else 'admission_idempotence.json')).write_text(
        json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
