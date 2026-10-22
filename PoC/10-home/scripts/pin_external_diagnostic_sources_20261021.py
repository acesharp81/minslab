"""Store scoped tender/contract research; never infer a housing start from a bid."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

FOLDER = 'external_diagnostic_review_20261021'
BATCH = 'external-diagnostic-20261021'


def main():
    from sqlalchemy import select, text
    from backend.db import Revision, Mapping, Audit, entity_id, upsert_revision, engine_for
    from backend.service import HomeService
    folder = Path('/app/data') / FOLDER
    captures = json.loads((folder / 'capture_manifest.json').read_text()) + json.loads((folder / 'extra_manifest.json').read_text())
    sources = {r['key']: r for r in captures if not r.get('error')}
    for s in sources.values():
        assert hashlib.sha256((folder / s['file']).read_bytes()).hexdigest() == s['sha256']
    assert '1,160' in (folder / 'bucheon_a1_tender.txt').read_text()
    assert '2026.06.30.' in (folder / 'bucheon_a1_contractor.txt').read_text()
    assert '664' in (folder / 'suwon_a2_tender_repost.txt').read_text()
    service = HomeService(engine_for())
    changed = []
    with service.sessions.begin() as db:
        db.execute(text('SELECT pg_advisory_xact_lock(9072026)'))

        def protect():
            revisions = [(r.entity_id, r.payload_hash) for r in db.scalars(select(Revision).where(
                Revision.superseded_at.is_(None), Revision.kind.in_(['project', 'project_profile', 'execution_schedule']))
                .order_by(Revision.entity_id))]
            mappings = [(r.project_id, r.policy_id, r.program_id, r.status, r.revision_no)
                        for r in db.scalars(select(Mapping).order_by(Mapping.project_id))]
            return revisions, mappings

        before = protect()

        def put(kind, sid, key, payload):
            old = db.scalar(select(Revision).where(Revision.entity_id == entity_id(kind, sid, key),
                Revision.superseded_at.is_(None)))
            prior = deepcopy(old.payload) if old else {}
            row, outcome = upsert_revision(db, kind, sid, key, payload, BATCH)
            if outcome != 'unchanged':
                db.add(Audit(entity_id=row.entity_id, action='EXTERNAL_DIAGNOSTIC_REVIEW', before=prior, after=payload))
            changed.append(dict(kind=kind, id=row.entity_id, outcome=outcome))
            return row.entity_id

        common = dict(base_date='2026-10-21', facts=[], units=None, planned_units=None,
            exclude_from_project_totals=True, matched_project_ids=[], policy_mapping_status='UNMAPPED',
            status='CONFIRMED', verification_status='SOURCE_CONTENT_CHECKED')
        def doc(key, name, source_type, label, **extra):
            s = sources[key]
            sid = 'official_document' if source_type == 'OFFICIAL' else 'external_officer'
            return put('document_evidence', sid, BATCH + ':' + key, dict(common,
                sample_kind='document_evidence', name=name, evidence_url=s['url'],
                original_file=FOLDER + '/' + s['file'], original_sha256=s['sha256'],
                checked_source_type=source_type, review_label=label, **extra))

        tender = doc('bucheon_a1_tender', '부천역곡 A1 통합공공임대 1,160호 공식 입찰 규모', 'OFFICIAL',
            '공식 원문 확인 - 조달청 R26BK01440851-000', district='부천역곡', block='A1',
            region='경기도', municipality='부천시', tenure='통합공공임대', contract_housing_units=1160,
            source_publication_date='2026-04-03', source_pages='공사개요 PDF p5·시공실적 기준표 p30',
            address='경기도 부천시 원미구 춘의동317', actual_start_verified=False,
            evidence_scope='입찰 공사규모 확인. 실제 착공 신고·정부 착공 산입·정책 귀속은 미확정')
        contractor = doc('bucheon_a1_contractor', '부천역곡 A1 시공사 수주·공사기간 확인', 'NON_OFFICIAL',
            '담당자 확인 - 비공식 자료: 동원건설산업 2026-06-30 신규수주알림',
            district='부천역곡', block='A1', source_publication_date='2026-06-30',
            contract_period_start='2026-06-30', contract_period_end='2029-08-18',
            actual_start_verified=False, reference_facts=[dict(kind='CONTRACT_PERIOD',
                start='2026-06-30', end='2029-08-18')],
            evidence_scope='공사기간 개시일은 실제 착공일로 채택하지 않음')
        put('collection_research', 'external_officer', BATCH + ':V02', dict(common,
            sample_kind='collection_research', name='V02 부천역곡 정부1,200호의 A1 1,160호 유력 후보',
            project_ids=['PRO_8aa9dcf9ed7eaafe3bef3196', 'PRO_e4e3d8647720b2239bc5b5c1'],
            candidate_name='부천역곡 A1', candidate_units=1160, source_entity_ids=[tender, contractor],
            possible_official_indicator='R030', comparison_status='EVENT_DATE_PENDING',
            checked_source_type='MIXED', review_label='담당자 확인 - 비공식 자료: 동원건설산업; 수량은 조달청 공식 원문',
            evidence_url=sources['bucheon_a1_tender']['url'],
            not_same_as_existing_project=True,
            review_decision='A2 976호에 덧붙이거나 덮어쓰지 않음. A1 실제 착공·정부 산입·9·7 귀속 확인 전 후보 보존'))
        suwon = doc('suwon_transparency_attachment', 'LH 수원당수2 사업실명제 2026-32', 'OFFICIAL',
            '공식 원문 확인 - LH 사업실명제 2026-32', district='수원당수2', region='경기도',
            source_publication_date='2026-03-30', district_plan_units=6353, actual_start_verified=False,
            evidence_scope='지구계획·개발 이력. 블록별 실제 주택 착공 원장 아님')
        bid = doc('suwon_a2_tender_repost', '수원당수2 A2 통합공공임대 664호 입찰 재게시', 'NON_OFFICIAL',
            '담당자 확인 - 비공식 자료: 비드프로 R26BK01586143-000 입찰공고 재게시',
            district='수원당수2', block='A2', tenure='통합공공임대', contract_housing_units=664,
            actual_start_verified=False, evidence_scope='재게시 원문 공사규모664 확인. 실제 착공과 정부3,400 산입 미확정')
        put('collection_research', 'external_officer', BATCH + ':V01', dict(common,
            sample_kind='collection_research', name='V01 수원당수2 A2 664호 추가 공개 후보 조사',
            project_ids=['PRO_bd9d1c9a0e058d70200be0e8', 'PRO_fb6568f0135c296216c81ad3',
                'PRO_10c86e6129bce4d7273a055b', 'PRO_99ee1fc085ac97b36b95b01b', 'PRO_a203837c7ac2ffe2d83c02f8'],
            candidate_units=664, source_entity_ids=[suwon, bid], comparison_status='UNVERIFIED',
            checked_source_type='MIXED', review_label='담당자 확인 - 비공식 자료: 비드프로; 지구 정보는 LH 공식',
            evidence_url=sources['suwon_a2_tender_repost']['url'],
            review_decision='기존5블록3,553호와 별개 후보 보존. 입찰 공사기간·계약을 착공 실적으로 추가하지 않음'))
        assert protect() == before
    result = dict(batch_id=BATCH, changes=changed, changed=sum(r['outcome'] != 'unchanged' for r in changed),
        protected_project_quantities_profiles_schedules_policy_mappings=True,
        new_policy_assignments=0, new_actual_housing_units=0)
    file = 'applied.json' if result['changed'] else 'idempotence.json'
    (folder / file).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
