"""Pin additional official scope proofs without inventing policy membership.

prepare runs on the host; apply runs in the HOME image. Project quantities,
policy/program assignments, profiles and execution schedules are protected.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

FOLDER = 'additional_mapping_review_20261021'
BATCH = 'additional-scope-20261021'
ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    folder = ROOT / 'docs/analysis' / FOLDER
    manifest = {r['key']: r for r in json.loads((folder / 'manifest.json').read_text())}
    pdf = json.loads((folder / 'pdf_manifest.json').read_text())
    text = re.sub(r'\s+', '', (folder / 'gyeyang_a17_notice.txt').read_text())
    assert '나머지154세대는행복주택으로향후공급할예정' in text
    magok = re.sub(r'\s+', '', (folder / 'magok_gangseo.txt').read_text())
    for term in ['제2026-838호', '2026-05-04', '총201호', '마곡동777', '2026년10월이후']:
        assert term in magok, term
    prior = ROOT / 'docs/analysis/policy907-full-verification-20261021'
    projects = {r['id']: r for r in json.loads((prior / 'projects.json').read_text())}
    ids = ['PRO_6a66b31b8f84244d491514e6', 'PRO_b0f7e7ded4e31142e5b39d02',
           'PRO_2dfb63f2826a3d14481c2fb4']
    plan = dict(batch_id=BATCH, base_date='2026-10-21', a17=pdf,
                magok=manifest['magok_gangseo'], corroboration=manifest['magok_youth'],
                source_plan_rows=[{k: projects[pid].get(k) for k in
                    ['id', 'name', 'source_id', 'revision_no', 'source_payload_hash', 'rows',
                     'planned_units', 'tenure', 'schedule_month', 'evidence_url', 'in_latest_source']}
                    for pid in ids])
    for item in [plan['a17'], plan['magok'], plan['corroboration']]:
        assert sha(folder / item['file']) == item['sha256']
    (folder / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    print(json.dumps(dict(official_documents=2, scope_links=2, research_records=3), ensure_ascii=False))


def apply():
    from sqlalchemy import select, text
    from backend.db import Revision, Mapping, ProgramMapping, Audit, entity_id, upsert_revision, engine_for
    from backend.service import HomeService
    folder = Path('/app/data') / FOLDER
    plan = json.loads((folder / 'plan.json').read_text())
    for item in [plan['a17'], plan['magok'], plan['corroboration']]:
        assert sha(folder / item['file']) == item['sha256']
    service = HomeService(engine_for())
    changes = []
    with service.sessions.begin() as db:
        db.execute(text('SELECT pg_advisory_xact_lock(9072026)'))

        def protected():
            revisions = [(r.entity_id, r.payload_hash) for r in db.scalars(select(Revision).where(
                Revision.superseded_at.is_(None), Revision.kind.in_(
                    ['project', 'project_profile', 'execution_schedule'])).order_by(Revision.entity_id))]
            mappings = [(m.project_id, m.policy_id, m.program_id, m.status, m.revision_no)
                        for m in db.scalars(select(Mapping).order_by(Mapping.project_id))]
            programs = [(m.id, m.policy_id, m.status, m.revision_no)
                        for m in db.scalars(select(ProgramMapping).order_by(ProgramMapping.id))]
            return revisions, mappings, programs

        before = protected()

        def put(kind, source, key, payload):
            old = db.scalar(select(Revision).where(Revision.entity_id == entity_id(kind, source, key),
                Revision.superseded_at.is_(None)).with_for_update())
            previous = deepcopy(old.payload) if old else {}
            row, outcome = upsert_revision(db, kind, source, key, payload, BATCH)
            if outcome != 'unchanged':
                db.add(Audit(entity_id=row.entity_id, action='OFFICIAL_SCOPE_REVIEW', before=previous, after=payload))
            changes.append(dict(kind=kind, id=row.entity_id, outcome=outcome))
            return row

        common = dict(base_date='2026-10-21', units=None, planned_units=None,
            status='CONFIRMED', checked_source_type='OFFICIAL',
            verification_status='SOURCE_CONTENT_CHECKED', exclude_from_project_totals=True)
        ids = ['PRO_12d91632b8ca640e1505869f', 'PRO_c1f32197fe5a45ab84ea895f']
        label = '공식 공고 자동 매핑 - LH 계양 A17 분양309·행복154 구성 확인'
        s = plan['a17']
        doc = put('document_evidence', 'official_document', BATCH + ':A17', dict(common,
            sample_kind='document_evidence', name='인천계양 A17 전체·금회 분양·향후 행복주택 범위 증빙',
            district='인천계양', block='A17', region='인천광역시', municipality='계양구',
            source_date='2026-09-30', source_publication_date='2026-09-30',
            block_total_units=463, offered_units=309, future_rental_units=154,
            scope_breakdown={'공공분양': 309, '행복주택': 154},
            rental_offer_status='FUTURE_SEPARATE_NOTICE', facts=[], matched_project_ids=ids,
            evidence_url=s['url'], original_file=FOLDER + '/' + s['file'], original_sha256=s['sha256'],
            source_pages='PDF p1 및 공급대상표', review_label=label,
            scope_note='전체463=분양309+행복154. 임대154는 향후 별도 공고; 현재 모집·착공 실적을 신규 생성하지 않음',
            policy_link_status='EXISTING_CONFIRMED_SCOPE_PROOF_ONLY'))
        for pid in ids:
            put('evidence_bridge', 'cross_source', pid + ':' + doc.entity_id, dict(common,
                project_id=pid, source_entity_id=doc.entity_id, source_revision_no=doc.revision_no,
                source_id='official_document', source_name='LH 계양 A17 분양·임대 구성표',
                source_type='OFFICIAL', reviewed=True, facts=[], review_label=label,
                evidence_url=s['url'], relation_type='EXACT_DISTRICT_BLOCK_SCOPE_PROOF',
                basis='공식 원문의 전체463·분양309·행복154를 대조. 사건일 및 신규 실적을 추정하지 않음'))
        s = plan['magok']
        source_id = 'AGE_4caa36314cede89a40bcee76'
        existing = db.scalar(select(Revision).where(Revision.entity_id == source_id,
            Revision.superseded_at.is_(None)))
        assert existing and existing.payload['units'] == 201
        assert '마곡동 777' in existing.payload['address']
        label = '공식 공고 자동 연결 - 강서구 2026-838호 마곡 도전숙 201호'
        fact = dict(stage='SUPPLY', kind='ACTUAL', date='2026-05-04', units=201,
            milestone='NOTICE', notice_round='MAIN', source_type='OFFICIAL',
            basis=label + '; 모집공고 실적, 계약·입주 완료 아님')
        magok_doc = put('document_evidence', 'official_document', BATCH + ':MAGOK', dict(common,
            sample_kind='document_evidence', name='마곡 도전숙 최초 입주자 모집공고', region='서울특별시',
            municipality='강서구', address='서울특별시 강서구 마곡동 777', block='DS13', tenure='공공임대',
            source_date='2026-05-04', source_publication_date='2026-05-04',
            notice_no='서울특별시 강서구 공고 제2026-838호', offered_units=201,
            application_start='2026-05-04', application_end='2026-05-22',
            move_in_plan_label='2026년 10월 이후', move_in_plan_date=None,
            matched_source_ids=[source_id], matched_project_ids=[], facts=[fact],
            policy_mapping_status='UNMAPPED', review_label=label, evidence_url=s['url'],
            corroboration_url=plan['corroboration']['url'],
            original_file=FOLDER + '/' + s['file'], original_sha256=s['sha256'],
            source_relation='EXACT_ADDRESS_NAME_UNITS',
            scope_note='기존 한국부동산원 입주예정201호와 동일 사업. 마곡17단지 임대196호와 별개. 9·7 정책 귀속은 미확정'))
        put('collection_research', 'official_document', BATCH + ':MAGOK_IDENTITY', dict(common,
            sample_kind='collection_research', name='마곡 도전숙 201호 모집·입주계획 동일성 및 정책 유보',
            project_ids=[], source_entity_ids=[source_id, magok_doc.entity_id], facts=[],
            verification_scope='명칭·주소 마곡동777·DS13·201호의 원천 간 동일성',
            policy_mapping_status='UNMAPPED', policy_review_status='HOLD',
            possible_official_indicator='R066', candidate_units=201,
            competing_candidate=dict(name='마곡17단지', rental_units=196),
            evidence_url=s['url'], review_label=label,
            unresolved_requirement='정부 서울마곡0.2천호의 사업·공고 식별자 및 9·7 프로그램 귀속 근거',
            date_difference_reason='부동산원2026-06-30판본은12월 예정, 강서구5월공고는10월이후. 기준일·정밀도가 달라 충돌로 단정하지 않음'))
        groups = [plan['source_plan_rows'][:1], plan['source_plan_rows'][1:]]
        for name, rows in zip(['과천지식정보타운', '구리갈매역세권'], groups):
            total = sum(sum(r['units'] for r in p['rows']) for p in rows)
            assert total == (1424 if name == '과천지식정보타운' else 896)
            for p in rows:
                r = db.scalar(select(Revision).where(Revision.entity_id == p['id'], Revision.superseded_at.is_(None)))
                assert r and r.payload_hash == p['source_payload_hash'], 'source plan changed after review'
            put('collection_research', 'official_document', BATCH + ':' + name, dict(common,
                sample_kind='collection_research', name=name + ' 4분기 임대 모집계획 범위 대조',
                project_ids=[p['id'] for p in rows], source_plan_rows=rows, facts=[],
                planned_offer_units=total, official_rounded_units=1400 if total == 1424 else 900,
                official_comparison_id='R067' if total == 1424 else 'R068',
                match_status='PLAN_ALIGNED' if total == 1424 else 'HISTORICAL_PLAN_APPROX_COMPATIBLE',
                evidence_url=rows[0]['evidence_url'], review_label='공식 LH 공급계획 원천 재대조',
                scope_note='LH 임대 유형·공급월 원천 행만 사용. 공사 전체나 담당자 추정 공급을 합산하지 않음',
                unresolved_requirement='' if total == 1424 else 'A3가 최신 목록에 없어 계획 존속·변경 공고 재확인 필요'))
        assert protected() == before, 'protected project/mapping/schedule modified'
    result = dict(batch_id=BATCH, changes=changes,
        changed=sum(r['outcome'] != 'unchanged' for r in changes),
        protected_quantities_events_schedules_mappings_unchanged=True,
        new_policy_assignments=0, new_policy_actual_units=0)
    name = 'applied.json' if result['changed'] else 'idempotence.json'
    (folder / name).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'apply'])
    args = parser.parse_args()
    (prepare if args.action == 'prepare' else apply)()
