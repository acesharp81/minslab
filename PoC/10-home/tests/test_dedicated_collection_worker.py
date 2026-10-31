from unittest.mock import patch
from sqlalchemy import create_engine,select
from backend.db import Base,CollectionJob
from backend.service import HomeService
from backend.collection_jobs import enqueue,run_next
from backend.collection_worker import worker_loop


def test_separate_worker_keeps_collect_link_snapshot_sequence_and_lease_recovery():
    e=create_engine('sqlite://');Base.metadata.create_all(e);s=HomeService(e)
    try:
        jid=enqueue(s,'lh_notice',force=True)
        with patch.object(s,'collect_one',return_value={'status':'SUCCESS'}):
            assert run_next(s,'LATEST')['next_stage']=='LINK'
        with patch('backend.stage_evidence.refresh',return_value={}),patch('backend.project_collection.refresh_links',return_value={}),patch('backend.evidence_bridge.reconcile',return_value={}):
            assert run_next(s,'LATEST')['next_stage']=='SNAPSHOT'
        with patch('backend.independent_metrics.freeze',return_value={'id':'snapshot','result':{'counts':{}}}):
            assert run_next(s,'LATEST')['status']=='SUCCESS'
        with s.sessions() as db:
            job=db.get(CollectionJob,jid)
            assert job.status=='SUCCESS' and job.finished_at is not None
            assert set(job.result)=={'COLLECT','LINK','SNAPSHOT','manual'}
            assert job.lease_until is None
    finally:e.dispose()


def test_worker_retries_errors_and_keeps_lane_processing():
    class Stop:
        waits=[]
        def is_set(self):return len(self.waits)>=2
        def wait(self,seconds):self.waits.append(seconds)
    stop=Stop()
    with patch('backend.collection_worker.run_next',side_effect=[RuntimeError('retry'),{'status':'ADVANCED'}]) as run:
        worker_loop(object(),'BACKFILL',stop)
    assert run.call_count==2 and stop.waits==[30,1]
