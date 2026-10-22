from backend.source_operations import operations
from backend.sources import SOURCES


def source(sid):
    return next(s for s in SOURCES if s['id'] == sid)


def test_schedule_matches_worker_fast_and_backfill(monkeypatch):
    monkeypatch.setenv('POC10_AUTO_COLLECT', 'true')
    monkeypatch.setenv('POC10_BUILDING_HUB_SERVICE_KEY', 'test')
    assert operations(source('lh_notice'))['interval_seconds'] == 900
    value = operations(source('building_general_permit'), {'scope_remaining_dongs': 5})
    assert value['backfill'] and value['interval_seconds'] == 900
    assert operations(source('building_general_permit'), {'scope_remaining_dongs': 0})['interval_seconds'] == 86400


def test_manual_and_disabled_are_not_claimed_automatic(monkeypatch):
    monkeypatch.setenv('POC10_AUTO_COLLECT', 'false')
    assert operations(source('lh_policy_followup'))['mode'] == '자동 수집 일시 중지'
    assert operations(source('national_statistics'))['mode'] == '수동 실행'
    monkeypatch.delenv('POC10_GENERAL_BUILDING_SERVICE_KEY', raising=False)
    monkeypatch.delenv('POC10_BUILDING_HUB_SERVICE_KEY', raising=False)
    assert 'API 키 필요' in operations(source('building_general_permit'))['mode']


def test_pinned_pdf_describes_collection_and_preprocessing_only():
    o = operations(source('lh_policy_followup'))
    assert '전체의 신규 공모를 자동 발견' in o['discovery']
    assert 'pypdf' in o['parser']
    assert '모델' not in str(o)
    assert all(t['kind'] != 'manual' for t in o['tags'])
    assert o['manual'] == ''
    assert '스캔 PDF' in o['pdf']
    assert '정책 연결' not in str(o)
    assert 'reviewed_links' not in o
    assert 'OCR_REQUIRED' in operations(source('eum_housing_notices'))['pdf']
    assert '새 데이터셋 ID는 자동 등록하지 않습니다' in operations(source('sh_happy_plan_file'))['discovery']


def test_policy_link_reviews_do_not_change_collection_metadata():
    from sqlalchemy import create_engine
    from backend.db import Base, upsert_revision
    from backend.service import HomeService
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    service = HomeService(engine)
    try:
        before = next(s for s in service.sources() if s['id'] == 'lh_policy_followup')['operations']
        with service.sessions.begin() as db:
            for key, status, reviewed in [('yes', 'CONFIRMED', True),
                                          ('rejected', 'REJECTED', True),
                                          ('automatic', 'CONFIRMED', False)]:
                upsert_revision(db, 'evidence_bridge', 'cross_source', key,
                                dict(source_id='lh_policy_followup', status=status,
                                     reviewed=reviewed), 'test')
            upsert_revision(db, 'evidence_bridge', 'cross_source', 'yes',
                            dict(source_id='lh_policy_followup', status='CONFIRMED',
                                 reviewed=True, basis='rechecked'), 'test2')
        full = next(s for s in service.sources() if s['id'] == 'lh_policy_followup')
        compact = next(s for s in service.sources(compact=True) if s['id'] == 'lh_policy_followup')
        assert full['operations'] == before
        assert 'reviewed_links' not in full['operations']
        assert full['operations'] == compact['operations']
    finally:
        engine.dispose()


def test_api_copy_only_describes_applicable_processing():
    value = operations(source('building_general_permit'))
    assert 'API 응답' in value['parser']
    assert value['pdf'] == ''
    assert value['manual'] == ''
    for item in SOURCES:
        text = str(operations(item))
        assert 'AI 모델' not in text
        assert '생성형' not in text
        assert '정책 연결' not in text
        assert '수집 대상 수동 등록' not in text
        assert '추출 규칙 수동 작성' not in text
