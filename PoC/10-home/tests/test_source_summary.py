from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.pool import StaticPool

from backend.db import Base, Batch, IdentityAlias, Revision, upsert_revision
from backend.service import HomeService
from backend.source_summary import build, category

NOW = datetime(2026, 10, 16, 3, tzinfo=timezone.utc)


def test_latest_success_refreshes_running_batch_cached_by_attempt_query(service):
    from sqlalchemy import update
    from backend.service import latest_batches
    with service.sessions.begin() as db:
        batch=Batch(source_id='building_hub',status='RUNNING',stats={})
        db.add(batch);db.flush();bid=batch.id
    with service.sessions() as db:
        attempt=latest_batches(db)[0]
        assert attempt.finished_at is None
        # Simulate a committed worker update without refreshing the reader's ORM object.
        db.execute(update(Batch).where(Batch.id==bid).values(status='SUCCESS',finished_at=NOW,
                   stats={'record_count':17}).execution_options(synchronize_session=False))
        success=latest_batches(db,'SUCCESS')[0]
        assert success.finished_at is not None
        assert success.status=='SUCCESS' and success.stats['record_count']==17


@pytest.fixture
def service():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield HomeService(engine)
    engine.dispose()


def put(db, kind, source, key, payload):
    row, _ = upsert_revision(db, kind, source, key, payload, 'fixture')
    row.recorded_at = datetime(2026, 10, 14, tzinfo=timezone.utc)
    return row.entity_id


def test_rows_times_union_columns_current_only_and_kst_recollection(service):
    with service.sessions.begin() as db:
        first = put(db, 'notice', 'lh_notice', 'one', {'obsolete': 9})
        put(db, 'notice', 'lh_notice', 'one', {'name': 'A', 'units': 0, 'optional': None})
        second = put(db, 'notice', 'lh_notice', 'two', {'name': 'B', 'units': 3, 'extra': []})
        project = put(db, 'project', 'lh_notice', 'project', {'name': '사업', 'region': '경기도'})
        permit = put(db, 'permit', 'building_hub', 'permit', {'permit': 'P', 'units': 5})
        # Internal generated rows are not registered external collection sources.
        put(db, 'execution_schedule', 'officer', 'internal', {'units': 999, 'due_date': '2027-01-01'})
        put(db, 'stage_evidence', 'stage_match', 'selected', {
            'project_id': project, 'status': 'CONFIRMED', 'selected': {'source_entity_id': first},
            'candidates': [{'source_entity_id': second}]})
        put(db, 'collection_link', 'stage_collection', 'repeated', {
            'project_id': project, 'links': [{'source_entity_id': first}, {'source_entity_id': first}]})
        put(db, 'evidence_bridge', 'cross_source', 'released', {
            'project_id': project, 'status': 'RELEASED', 'source_entity_id': second})
        db.add(IdentityAlias(project_id='identity', source_entity_id=permit, source_id='building_hub',
                             relation_status='CONFIRMED', match_rule='fixture', basis='fixture',
                             evidence_revision_id='fixture', evidence_url='https://example.org'))
        for hour, minute, ids in [(14, 59, [permit]), (15, 0, [first, second]), (16, 0, [first])]:
            db.add(Batch(source_id='building_hub' if ids == [permit] else 'lh_notice', status='SUCCESS',
                         finished_at=datetime(2026, 10, 15, hour, minute, tzinfo=timezone.utc),
                         stats={'entity_ids': ids}))
        db.add(Batch(source_id='building_hub', status='FAILED', finished_at=NOW,
                     stats={'entity_ids': [permit]}))
        db.add(Batch(source_id='building_hub', status='SUCCESS',
                     finished_at=datetime(2026, 10, 17, tzinfo=timezone.utc),
                     stats={'entity_ids': [permit]}))
    with service.sessions() as db:
        before = db.scalar(select(func.count()).select_from(Revision))
    result = build(service, NOW)
    assert result['as_of_date'] == '2026-10-16'
    assert result['current'] == {'sources': 2, 'extracted_cells': 12, 'linked_records': 3}
    assert result['today'] == {'sources': 1, 'extracted_cells': 8, 'linked_records': 1}
    group = next(g for g in result['groups'] if g['source_id'] == 'lh_notice' and g['kind'] == 'notice')
    assert (group['rows'], group['columns'], group['extracted_cells']) == (2, 4, 8)
    assert group['today_rows'] == 2  # Unchanged records recollected today still count, once.
    assert sum(t['extracted_cells'] for t in result['types']) == 12
    assert sum(t['source_count'] for t in result['types']) == 2  # Multiple schemas, one source.
    news = next(t for t in result['types'] if t['id'] == 'NEWS')
    assert news['source_count'] == news['extracted_cells'] == 0
    with service.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Revision)) == before


def test_empty_data_and_content_priority_over_api(service):
    result = build(service, NOW)
    assert result['current'] == result['today'] == {'sources': 0, 'extracted_cells': 0, 'linked_records': 0}
    assert category({'id': 'notice', 'type': 'NOTICE', 'key_env': 'KEY'}) == 'NOTICE'
    assert category({'id': 'press', 'type': 'POLICY'}) == 'PRESS'
    assert category({'id': 'article', 'type': 'NEWS', 'key_env': 'KEY'}) == 'NEWS'
    assert category({'id': 'permit', 'type': 'ACTUAL', 'key_env': 'KEY'}) == 'API'


def test_endpoint_cache_invalidates_when_current_source_data_changes(service):
    from fastapi.testclient import TestClient
    from backend.app import create_app
    client = TestClient(create_app(service.engine, auto_collect=False))
    path = '/poc/home/api/source-summary'
    first = client.get(path)
    assert first.status_code == 200
    assert first.headers['X-Home-Cache'] == 'MISS'
    assert client.get(path).headers['X-Home-Cache'] == 'HIT'
    with service.sessions.begin() as db:
        upsert_revision(db, 'notice', 'lh_notice', 'one', {'name': 'A', 'units': None}, 'fixture')
    changed = client.get(path)
    assert changed.headers['X-Home-Cache'] == 'MISS'
    assert changed.json()['current']['extracted_cells'] == 2
    source = next(s for s in client.get('/poc/home/api/sources?compact=true').json()['items']
                  if s['id'] == 'lh_notice')
    assert (source['data_type'], source['data_type_label'], source['access_method']) == ('NOTICE', '분양·임대 입주자 모집공고', 'API')


def test_document_control_character_preserved_in_column_counts(service):
    with service.sessions.begin() as db:
        put(db,'plan_notice','eum_housing_notices','nul',{'name':'공식 고시','text':'고\u0000시 본문','units':3})
    result=build(service,NOW)
    row=next(g for g in result['groups'] if g['source_id']=='eum_housing_notices')
    assert (row['rows'],row['columns'],row['extracted_cells'])==(1,3,3)
    with service.sessions() as db:
        saved=db.scalar(select(Revision).where(Revision.source_id=='eum_housing_notices'))
        assert saved.payload['text']=='고\u0000시 본문'
