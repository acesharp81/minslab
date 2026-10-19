from unittest.mock import patch
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.pool import StaticPool
from backend.db import Base, Audit, Mapping, ProgramMapping, Revision, upsert_revision
from backend.service import HomeService
from backend.connection_confirmation import apply_review


@pytest.fixture
def setup():
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    service = HomeService(engine)
    with service.sessions.begin() as db:
        db.add(ProgramMapping(id='pr', name='iH 공공분양', seed_policy_id='UNASSIGNED', policy_id='POL_TEST',
            status='REVIEW', revision_no=1, basis='후보', evidence_url='https://www.ih.co.kr/'))
        raw, _ = upsert_revision(db, 'project', 'ih_notice', 'land:130', dict(name='검암 S3', region='인천광역시',
            base_date='2026-01-01', planned_units=749, program='iH 공공분양',
            proposed_policy='UNASSIGNED', policy_candidate_only=True), 'test')
        pid = raw.entity_id
        db.add(Mapping(project_id=pid, program_id='pr', policy_id='UNASSIGNED', status='REVIEW',
                       revision_no=1, basis='후보', evidence_url='https://www.ih.co.kr/'))
    plan = dict(programs=[dict(id='pr', policy_id='POL_TEST', revision_no=1, explanation='공식 정책의 공공주택 관리범위 검토',
                              evidence_url='https://www.korea.kr/')],
                projects=[dict(id=pid, program_id='pr', policy_id='POL_TEST', revision_no=1,
                               explanation='iH 원문 블록·유형 대조', evidence_url='https://www.ih.co.kr/')])
    with patch.object(service, 'mapping_policies', return_value=[dict(policy_id='POL_TEST', monitor_kind='POLICY')]):
        yield service, plan, pid
    engine.dispose()


def test_review_confirms_both_edges_preserves_source_and_is_idempotent(setup):
    s, plan, pid = setup
    raw_before = s.rows('project')[0]['source_revision_id']
    result = apply_review(s, 'review1', plan, '김민', '공식 자료 확인 및 IH 추가 연결')
    p = s.rows('project')[0]
    assert p['mapping']['status'] == p['mapping']['policy_status'] == 'CONFIRMED'
    assert p['mapping']['policy_id'] == 'POL_TEST' and not p['mapping'].get('reference_policy_pending')
    assert p['source_revision_id'] == raw_before and not p.get('start_actual_date')
    assert result['actual_events_created'] == 0
    with s.sessions() as db:
        for a in db.scalars(select(Audit).where(Audit.action.in_(['PROGRAM_POLICY_REVIEW', 'PROGRAM_PROJECT_REVIEW']))):
            assert a.after['actor'] == '김민'
            assert a.after['reason'] == '공식 자료 확인 및 IH 추가 연결'
            assert a.before['status'] == 'REVIEW'
        count = db.scalar(select(func.count()).select_from(Audit))
    assert apply_review(s, 'review1', plan, '김민', '공식 자료 확인 및 IH 추가 연결')['unchanged']
    with s.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Audit)) == count


@pytest.mark.parametrize('failure', ['stale', 'released', 'wrong_parent'])
def test_bad_project_review_rolls_back_program_and_all_audits(setup, failure):
    s, plan, pid = setup
    if failure == 'stale':
        plan['projects'][0]['revision_no'] = 2
    elif failure == 'wrong_parent':
        plan['projects'][0]['program_id'] = 'other'
    else:
        with s.sessions.begin() as db:
            db.scalar(select(Mapping).where(Mapping.project_id == pid)).status = 'RELEASED'
    with pytest.raises(ValueError):
        apply_review(s, 'review1', plan, '김민', '공식 자료 확인 및 IH 추가 연결')
    with s.sessions() as db:
        assert db.get(ProgramMapping, 'pr').status == 'REVIEW'
        assert db.scalar(select(func.count()).select_from(Audit)) == 0
        assert db.scalar(select(func.count()).select_from(Revision).where(Revision.kind == 'connection_review')) == 0
