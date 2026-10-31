from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine
from backend.db import Base,Batch,CollectionJob,now
from backend.service import HomeService
from backend.collection_jobs import enqueue,run_next
from backend.collection_policy import unchanged_collection,backfill_window_open,REPAIR_MARKER

@pytest.fixture
def service(tmp_path):
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    yield HomeService(engine,tmp_path)
    engine.dispose()

def test_unchanged_collection_finishes_without_link_or_snapshot(service):
    identity=enqueue(service,'lh_notice',force=True)
    with service.sessions.begin() as db:
        for minutes in [10,1]:db.add(Batch(source_id='lh_notice',status='SUCCESS',finished_at=now()-timedelta(minutes=minutes),stats={'complete_query':True}))
    with patch.object(service,'collect_one',return_value={'status':'SUCCESS','records':4030,'unchanged':4030}),patch('backend.stage_evidence.refresh',side_effect=AssertionError('No full rebuild')):
        result=run_next(service,'LATEST')
    assert result['status']=='SUCCESS' and result['next_stage'] is None
    with service.sessions() as db:
        job=db.get(CollectionJob,identity)
        assert job.status=='SUCCESS' and job.finished_at and set(job.result)=={'COLLECT','manual'}

def test_real_change_still_enters_link_and_snapshot(service):
    enqueue(service,'lh_notice',force=True)
    with patch.object(service,'collect_one',return_value={'status':'SUCCESS','records':2,'new':1,'unchanged':1}):
        assert run_next(service,'LATEST')['next_stage']=='LINK'

@pytest.mark.parametrize('result',[{'status':'SUCCESS'}, {'records':3,'unchanged':2},{'records':True},{'records':2,'new':1,'unchanged':2}])
def test_missing_or_inconsistent_accounting_never_skips_work(result):
    assert not unchanged_collection(result)

def test_structural_failure_is_held_but_manual_retry_remains_available(service):
    identity=enqueue(service,'lh_completion_plan',force=True)
    with patch.object(service,'collect_one',return_value={'status':'FAILED','error':'공식 파일 링크·기준일 확인 실패: 원천 페이지 변경'}):
        assert run_next(service,'BACKFILL')['reason']=='SOURCE_REPAIR_REQUIRED'
    with service.sessions() as db:assert db.get(CollectionJob,identity).error.startswith(REPAIR_MARKER)
    assert enqueue(service,'lh_completion_plan') is None
    assert enqueue(service,'lh_completion_plan',force=True)

def test_transient_source_failure_keeps_existing_retry_path(service):
    enqueue(service,'lh_completion_plan',force=True)
    with patch.object(service,'collect_one',return_value={'status':'FAILED','error':'공식 원천 연결 실패 (HTTP 503)'}):
        assert run_next(service,'BACKFILL')['status']=='RETRY'

def test_daytime_historic_acceleration_waits_while_manual_request_works(service):
    with service.sessions.begin() as db:
        db.add(Batch(source_id='building_general_permit',status='SUCCESS',finished_at=now()-timedelta(hours=2),stats={'scope_remaining_dongs':10}))
    with patch('backend.collection_jobs.backfill_window_open',return_value=False):
        assert enqueue(service,'building_general_permit') is None
    assert enqueue(service,'building_general_permit',force=True)

def test_night_backfill_is_capped_at_three_successes_per_kst_day(service):
    instant=datetime(2026,10,30,19,tzinfo=timezone.utc) # 04:00 KST
    with service.sessions.begin() as db:
        for hours in [3,2,1]:db.add(Batch(source_id='building_general_permit',status='SUCCESS',finished_at=instant-timedelta(hours=hours),stats={'scope_remaining_dongs':10}))
    with patch('backend.collection_jobs.now',return_value=instant):
        assert enqueue(service,'building_general_permit') is None

def test_kst_window_does_not_depend_on_host_timezone():
    assert backfill_window_open(datetime(2026,10,30,17,tzinfo=timezone.utc))
    assert not backfill_window_open(datetime(2026,10,31,2,tzinfo=timezone.utc))

def test_changed_coverage_still_rebuilds_even_when_all_facts_are_unchanged(service):
    enqueue(service,'lh_notice',force=True)
    with service.sessions.begin() as db:
        for minutes,complete in [(10,False),(1,True)]:db.add(Batch(source_id='lh_notice',status='SUCCESS',finished_at=now()-timedelta(minutes=minutes),stats={'complete_query':complete}))
    with patch.object(service,'collect_one',return_value={'status':'SUCCESS','records':1,'unchanged':1}):
        assert run_next(service,'LATEST')['next_stage']=='LINK'
