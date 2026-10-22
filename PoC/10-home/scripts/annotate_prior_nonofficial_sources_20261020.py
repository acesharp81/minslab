"""Record the previously checked designer source without promoting its scope."""
import argparse
from copy import deepcopy
import hashlib
import json

from bs4 import BeautifulSoup
from sqlalchemy import select

from backend.db import Audit, Revision, engine_for, upsert_revision
from backend.service import HomeService
from scripts.apply_officer_verified_links_20261020 import protected_in_db
from scripts.review_policy_readmission_20261019 import digest


def annotate(service, apply=False):
    folder = service.data_dir / 'external-match-review-20261020'
    source = next(r for r in json.loads((folder / 'manifest.json').read_text()) if r['key'] == 'yeonnam-designer')
    body = (folder / source['file']).read_bytes()
    if source['status'] != 200 or hashlib.sha256(body).hexdigest() != source['sha256']:
        raise ValueError('이전 검토 비공식 원문 판본 불일치')
    content = BeautifulSoup(body, 'html.parser').get_text(' ', strip=True)
    if not all(w in content for w in ('연남동 공공임대주택 복합화사업', '서울주택도시공사', '마포구 연남동')):
        raise ValueError('설계사 사업명·기관·위치 내용 불일치')
    label = '담당자 확인 - 비공식 자료: 공간유앤아이건축사사무소, 연남동 공공임대주택 복합화사업 소개'
    payload = dict(
        name='연남동 공공임대 · 이전 비공식 보조 근거 확인', sample_kind='document_evidence',
        source_object_id='prior-nonofficial-20261020:yeonnam-designer',
        evidence_url=source['url'], original_file='external-match-review-20261020/' + source['file'],
        original_sha256=source['sha256'], checked_at=source['checked_at'], base_date='2026-10-20',
        review_label=label, review_actor='담당자 대행 · 이전 비공식 확인 자료 동일 표기 사용자 지시 2026-10-20',
        officer_review_status='CONTENT_CHECKED', checked_source_type='NON_OFFICIAL',
        review_decision='SUPPORTING_PROJECT_EXISTENCE_ONLY',
        verified_fields=['사업명', 'SH 건축주', '마포구 연남동 위치'],
        unverified_fields=['8호 개별 현장·지번', '실제 착공일', '합본 96호에 포함되는지'],
        actual_admission_status='NOT_APPLIED', official_actual_verified=False,
        official_brief_membership_verified=False, quantity_scope='SUPPORTING_ONLY',
        matched_project_ids=['PRO_b8e9b07eb43ee60a807ec231'],
        facts=[], units=None, planned_units=None, exclude_from_project_totals=True,
        comparison_eligible=False,
        basis=label + ' · 사업 존재·건축주·대략 위치만 보조 확인. 공식 발표의 8호 또는 합본공사 96호의 개별 착공 근거로 사용하지 않음. 기존 공식 공급계획 등록과 개별 착공 유보 판단을 보존.',
    )
    with service.sessions.begin() as db:
        before = protected_in_db(db)
        prior = db.scalar(select(Revision).where(
            Revision.kind == 'document_evidence', Revision.source_id == 'officer',
            Revision.payload['source_object_id'].as_string() == payload['source_object_id'],
            Revision.superseded_at.is_(None)))
        old = deepcopy(prior.payload) if prior else {}
        if prior and prior.payload.get('officer_review_status') == 'CONFIRMED':
            return dict(applied=apply,id=prior.entity_id,outcome='unchanged',label=prior.payload['review_label'],url=source['url'],protected_before=digest(before),protected_after=digest(before),quantity_change=0)
        eid = prior.entity_id if prior else None
        outcome = 'preview'
        if apply:
            row, outcome = upsert_revision(db, 'document_evidence', 'officer', payload['source_object_id'], payload, 'prior-nonofficial-20261020')
            eid = row.entity_id
            if outcome != 'unchanged':
                db.add(Audit(entity_id=eid, action='NONOFFICIAL_SOURCE_LABEL', before=old, after=payload))
        after = protected_in_db(db)
        if before != after:
            raise ValueError('기존 사업·일정·담당자 판단 변경 감지')
    return dict(applied=apply, id=eid, outcome=outcome, label=label, url=source['url'],
                protected_before=digest(before), protected_after=digest(after), quantity_change=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    service = HomeService(engine_for())
    result = annotate(service, args.apply)
    target = service.data_dir / 'named-start-deep-20261020'
    filename = 'prior-label-idempotence.json' if result['outcome'] == 'unchanged' else 'prior-label-applied.json' if args.apply else 'prior-label-preview.json'
    (target / filename).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))
