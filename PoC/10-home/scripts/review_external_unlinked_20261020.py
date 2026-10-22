"""Review three Q4 comparison items; preserve policy attribution and approved metrics.

--apply stores source correspondence decisions only. It never creates projects,
policy mappings or stage events. Scenario calculations are offline and explicit.
"""
import argparse
import hashlib
import json

from sqlalchemy import select
from backend.db import Audit, Revision, engine_for, upsert_revision
from backend.service import HomeService
from scripts.review_policy_readmission_20261019 import protected, digest

ACTOR = 'Codex 담당자 대행 검토 · 사용자 외부 분석자료 재검증 요청 2026-10-20'
FOLDER = 'external-match-review-20261020'
CONTRACT = 'AGE_a2609f5d6ded5d0cf715d275'
COMBINED = 'AGE_453d66171a940e9edc4d0809'


def review(service, apply=False):
    folder = service.data_dir / FOLDER
    manifest = {r['key']: r for r in json.loads((folder / 'manifest.json').read_text())}
    for key in ('official-brief', 'seoul-investment-correct', 'doksan-building', 'yeonhui-yeonnam'):
        m = manifest[key]
        assert m['status'] == 200
        assert hashlib.sha256((folder / m['file']).read_bytes()).hexdigest() == m['sha256']
    assert manifest['official-brief']['sha256'] == 'e95a9929b94f9994fe963907a46b90e7761cd26a9811d1b36d7e7988f1ecdc1f'
    assert manifest['seoul-investment-correct']['sha256'] == '61a22b01cef2eb3192b655b8bcf2da81c774f6b4afccfe61873b796c811ae32c'
    cis = (folder / 'doksan-building.txt').read_text()
    assert all(t in cis for t in ('독산동 산업문화어울림센터 건설공사', '2024-12-30', '세대 수 : 20', '성안건설주식회사'))
    combined = (folder / 'yeonhui-yeonnam.txt').read_text()
    assert all(t in combined for t in ('연희 및 연남동', '세대 수 : 96', '2025-06-26', '현대아산'))
    before = protected(service)
    cases = [
        dict(number=30, name='방화차고지', official_units=75, key='seoul-investment-correct',
             decision='OFFICIAL_ITEM_SOURCE_MATCH_CONFIRMED', confirmed_source_identity_ids=[],
             basis='공식 32항목의 방화차고지75호 ↔ 시의회 2025.09.02 심사보고의 사업명·SH·임대75호·마곡동1410-10(구 방화동168-50) 대조. 2025년6월 착공 기재. 기존 방화동 행복주택 계약과 연결하지 않음.',
             observations=[dict(stage='CONSTRUCTION',date='2025-06',precision='MONTH',units=75,
                                scope='시의회 문서의 사업 전체',status='SOURCE_REPORTED')],
             conflicts=[], candidate_source_ids=[]),
        dict(number=31, name='독산동 산업문화어울림센터', official_units=20, key='doksan-building',
             decision='OFFICIAL_ITEM_SOURCE_MATCH_CONFIRMED', confirmed_source_identity_ids=[CONTRACT],
             basis='공식 항목20호 ↔ 건설알림이 SH·동일 건설공사명·20세대. 보유 SH 건설계약과 공사명·성안건설주식회사·2024-12-30 시작일 일치. 건설알림이 착공 표기를 별도 확인; 전기공사 계약일로 대체하지 않음.',
             observations=[dict(stage='CONSTRUCTION',date='2024-12-30',precision='DAY',units=20,
                                scope='건설알림이 건설공사 전체',status='SOURCE_REPORTED')],
             conflicts=['시의회 2025년 보고서는 착공2025.02, 준공예정2026.10; 현행 건설알림이는 착공2024-12-30, 준공2027-04-04. 날짜 차이 원인 미확정. 두 판본 모두 2026년 이전 착공.'],
             candidate_source_ids=[]),
        dict(number=32, name='연남동 공공임대주택', official_units=8, key='yeonhui-yeonnam',
             decision='PARTIAL_SCOPE_HELD', confirmed_source_identity_ids=[],
             basis='공식 공급계획8호는 확인. 보유 계약과 건설알림이의 연희·연남 합본명·현대아산·2025-06-26 일치하나, 개요96호를 연남8호로 분리할 주소·동별 명세 미확보. 설계사 소개는 사업 존재만 보조한다.',
             observations=[], conflicts=['합본96호를 연남8호에 전용하지 않음. 연남동244-16 가로주택 사업과 연결하지 않음.'],
             candidate_source_ids=[COMBINED]),
    ]
    results = []
    with service.sessions.begin() as db:
        for eid, name, contractor in [
            (CONTRACT, '독산동 산업문화어울림센터 건설공사', '성안건설주식회사'),
            (COMBINED, '연희 및 연남동 공공주택 건설공사', '현대아산주식회사'),
        ]:
            row = db.scalar(select(Revision).where(Revision.entity_id == eid, Revision.superseded_at.is_(None)))
            assert row and row.kind == 'agency_contract'
            assert row.payload['name'] == name and row.payload['native_fields']['계약대상'] == contractor
        for case in cases:
            m = manifest[case['key']]
            payload = dict(
                name=f"10월 공식 항목 {case['number']} · {case['name']} 연결 재검토",
                source_object_id=f"{FOLDER}:Q4:{case['number']}", sample_kind='document_evidence',
                base_date='2026-10-20', date_precision='COLLECTION',
                source_date_label='검토일 · 사건일 아님', evidence_url=m['url'],
                original_file=FOLDER+'/'+m['file'], original_sha256=m['sha256'],
                content_text=(folder/(case['key']+'.txt')).read_text(),
                review_actor=ACTOR, review_basis=case['basis'], review_decision=case['decision'],
                official_row_id=f"2026-10-16:Q4:{case['number']}",
                official_source_url=manifest['official-brief']['url']+'#page=6',
                official_source_sha256=manifest['official-brief']['sha256'],
                official_units=case['official_units'], official_period='2026Q4',
                official_stage='SUPPLY', official_kind='PLAN',
                confirmed_source_identity_ids=case['confirmed_source_identity_ids'],
                candidate_source_ids=case['candidate_source_ids'], matched_project_ids=[],
                source_observations=case['observations'], conflicts=case['conflicts'],
                policy_mapping_status='HELD', proposed_policy='UNASSIGNED',
                policy_basis='통합발표 항목 대응은 확인하되, 9·7 단독 정책 귀속의 추가 근거 미확보',
                facts=[], units=None, planned_units=None, exclude_from_project_totals=True,
                verification_status='SOURCE_CONTENT_CHECKED',
            )
            if apply:
                current = db.scalar(select(Revision).where(
                    Revision.kind == 'document_evidence',
                    Revision.source_id == 'official_document',
                    Revision.superseded_at.is_(None),
                    Revision.payload['source_object_id'].as_string() == payload['source_object_id']))
                if current and current.payload.get('review_decision') in ('CUMULATIVE_POLICY_ADMITTED', 'SUPPLY_PLAN_ADMITTED_START_HELD'):
                    results.append(dict(row_id=current.entity_id, action='later_approval_preserved', **case))
                    continue
                row, action = upsert_revision(db, 'document_evidence', 'official_document',
                                              payload['source_object_id'], payload, FOLDER)
                if action != 'unchanged':
                    db.add(Audit(entity_id=row.entity_id, action='EXTERNAL_SOURCE_MATCH_REVIEW',
                                 before={}, after={k: v for k, v in payload.items() if k != 'content_text'}))
                results.append(dict(row_id=row.entity_id, action=action, **case))
            else:
                results.append(dict(action='proposed', **case))
    after = protected(service)
    assert before == after, '기존 project / mapping / schedule 변경'
    return dict(applied=apply, cases=results, source_matched_items=2, source_matched_units=95,
                policy_mappings_added=0, projects_added=0, stage_events_added=0,
                protected_unchanged=True, before_hash=digest(before), after_hash=digest(after))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    service = HomeService(engine_for())
    result = review(service, args.apply)
    filename = 'applied.json' if args.apply else 'preview.json'
    path = service.data_dir / FOLDER / filename
    if path.exists() and args.apply and all(c['action'] == 'unchanged' for c in result['cases']):
        path = path.with_name('idempotence.json')
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}, ensure_ascii=False))
