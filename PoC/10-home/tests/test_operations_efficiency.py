from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import hashlib,json
import httpx
import pytest
from sqlalchemy import create_engine,select,func,event
from backend.db import Base,MetricSnapshot,MetricSnapshotContent,Batch,CollectionJob,now
from backend.service import HomeService
from backend.operations_window import night_open,next_night,bulk_work,check_window,NightWindowClosed
from backend.collection_jobs import enqueue,claim,enqueue_due,run_next
from backend.ai_collection_store import Store
from backend.raw_archive import read_raw
from backend.collectors import Fetcher

@pytest.fixture
def service(tmp_path):
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    yield HomeService(engine,tmp_path)
    engine.dispose()

@pytest.mark.parametrize('hour,minute,opened',[(0,59,False),(1,0,True),(4,59,True),(5,0,False),(13,0,False)])
def test_night_boundaries(hour,minute,opened):
    from zoneinfo import ZoneInfo
    point=datetime(2026,10,31,hour,minute,tzinfo=ZoneInfo('Asia/Seoul'))
    assert night_open(point)==opened
    following=next_night(point)
    assert night_open(following) and following>=point

def test_bulk_stops_new_request_after_window_and_manual_is_allowed():
    with patch('backend.operations_window.night_open',return_value=True):
        with bulk_work():
            check_window()
            with patch('backend.operations_window.night_open',return_value=False),pytest.raises(NightWindowClosed):check_window()
    with patch('backend.operations_window.night_open',return_value=False),bulk_work(False):check_window()

def test_auto_bulk_and_links_wait_but_notices_and_manual_run(service):
    bulk=enqueue(service,'lh_completion_plan');notice=enqueue(service,'lh_notice')
    with patch('backend.collection_jobs.night_open',return_value=False):
        assert claim(service,'BACKFILL') is None
        assert claim(service,'LATEST')['id']==notice
    with service.sessions.begin() as db:
        job=db.get(CollectionJob,notice);job.status='QUEUED';job.stage='LINK'
    with patch('backend.collection_jobs.night_open',return_value=False):assert claim(service,'LATEST') is None
    with patch('backend.collection_jobs.night_open',return_value=True):assert claim(service,'BACKFILL')['id']==bulk
    manual=enqueue(service,'gh_files',force=True)
    with patch('backend.collection_jobs.night_open',return_value=False):assert claim(service,'BACKFILL')['id']==manual

def test_paused_window_keeps_attempt_budget_and_moves_to_next_night(service):
    identity=enqueue(service,'lh_completion_plan',force=True)
    with patch.object(service,'collect_one',return_value={'status':'PAUSED','error':'night ended'}):assert run_next(service,'BACKFILL')['status']=='PAUSED'
    with service.sessions() as db:
        row=db.get(CollectionJob,identity)
        assert row.status=='QUEUED' and row.attempts==0 and row.lease_until is None
        assert night_open(row.run_after.replace(tzinfo=timezone.utc))

def test_scheduler_batches_state_reads(service):
    from backend.sources import SOURCES
    with service.sessions.begin() as db:
        for s in SOURCES:db.add(Batch(source_id=s['id'],status='SUCCESS',finished_at=now()))
    queries=[]
    def before(*args):queries.append(args[2])
    event.listen(service.engine,'before_cursor_execute',before)
    with patch('backend.collection_jobs.enqueue',return_value=None),patch('backend.collection_jobs.night_open',return_value=True):enqueue_due(service)
    event.remove(service.engine,'before_cursor_execute',before)
    assert len(queries)==3

def test_snapshot_content_shared_and_all_observation_identities_preserved(service):
    from backend.independent_metrics import freeze,get_snapshot
    def build(_service,known_at,**kw):return dict(known_at=known_at.isoformat(),counts={'selected':2},events=[{'units':10}])
    with patch('backend.independent_metrics.build',side_effect=build):
        a=freeze(service,'담당자','first',known_at=now()-timedelta(minutes=2))
        b=freeze(service,'담당자','second',known_at=now()-timedelta(minutes=1))
    assert a['id']!=b['id'] and a['digest']!=b['digest']
    with service.sessions() as db:
        assert db.scalar(select(func.count()).select_from(MetricSnapshotContent))==1
        assert db.scalar(select(func.count()).select_from(MetricSnapshot))==2
    assert get_snapshot(service,a['id'])['result']==a['result']
    assert get_snapshot(service,b['id'])['result']==b['result']

def test_existing_snapshot_compaction_is_lossless_and_night_only(service):
    from backend.independent_metrics import digest,get_snapshot
    from backend.operations_maintenance import compact_snapshots,step
    context={'known_at':now().isoformat(),'algorithm_version':'test'};result={'known_at':context['known_at'],'units':4}
    checksum=digest(dict(context=context,result=result))
    with service.sessions.begin() as db:db.add(MetricSnapshot(id='old',known_at=now(),actor='a',reason='r',context=context,result=result,digest=checksum))
    state={}
    with patch('backend.operations_maintenance.night_open',return_value=False):
        assert step(service)=={'status':'NIGHT_WAIT'}
    with patch('backend.operations_maintenance.night_open',return_value=True):assert compact_snapshots(service,state)==1
    restored=get_snapshot(service,'old');assert restored['result']==result and restored['digest']==checksum
    with service.sessions.begin() as db:
        content=db.scalar(select(MetricSnapshotContent));content.payload={'corrupt':True}
    with pytest.raises(ValueError):get_snapshot(service,'old')

def test_conditional_fetch_preserves_hash_and_compressed_archive(tmp_path):
    body=b'<html>'+b'reproducible official data '*1000+b'</html>';seen=[]
    def send(request):
        seen.append(dict(request.headers))
        return httpx.Response(304,request=request) if request.headers.get('if-none-match')=='"v1"' else httpx.Response(200,content=body,headers={'ETag':'"v1"'},request=request)
    f=Fetcher('test',tmp_path);f.client.close();f.client=httpx.Client(transport=httpx.MockTransport(send))
    try:
        assert f.get('https://www.lh.or.kr/source')==body
        assert f.get('https://www.lh.or.kr/source')==body
        assert len(seen)==2
        row=f.manifest[-1];assert row['file'].endswith('.gz') and read_raw(tmp_path/row['file'])==body
        assert row['sha256']==hashlib.sha256(body).hexdigest() and seen[1]['if-none-match']=='"v1"'
        (tmp_path/row['file']).unlink()
        assert f.get('https://www.lh.or.kr/source')==body and 'if-none-match' not in seen[2]
    finally:f.close()

def test_permanent_http_failure_is_not_retried(tmp_path):
    calls=[]
    def send(request):calls.append(1);return httpx.Response(404,request=request)
    f=Fetcher('test',tmp_path);f.client.close();f.client=httpx.Client(transport=httpx.MockTransport(send))
    try:
        with pytest.raises(RuntimeError):f.get('https://www.lh.or.kr/missing')
        assert len(calls)==1
    finally:f.close()

def test_ai_compact_status_skips_events_but_keeps_cost_and_progress(tmp_path):
    s=Store(tmp_path);r=s.enqueue();s.event(r['id'],'TEST',value='details')
    before=s.status();after=s.status(include_events=False)
    assert before['runs'][0]['events'] and after['runs'][0]['events']==[]
    assert before['runs'][0]['cost_usd']==after['runs'][0]['cost_usd']
    assert before['runs'][0]['progress']==after['runs'][0]['progress']

def test_ai_scheduled_claim_waits_until_night_manual_stays_available(tmp_path):
    s=Store(tmp_path);r=s.enqueue(schedule_day='2026-10-31')
    assert s.claim(allow_scheduled=False) is None
    assert s.claim(allow_scheduled=True)['id']==r['id']
    with patch('backend.operations_window.night_open',return_value=False):
        assert s.alive(r['id'],allow_finish=True)
        assert not s.alive(r['id'])
    s.finish(r['id'],'CANCELLED');manual=s.enqueue()
    assert s.claim(allow_scheduled=False)['id']==manual['id']

def test_health_reads_only_worker_heartbeat(tmp_path):
    from backend.ai_worker_health import online
    assert not online(tmp_path)
    s=Store(tmp_path);s.heartbeat()
    with patch.object(Store,'status',side_effect=AssertionError('no history')):assert online(tmp_path)

def test_area_automatic_rebuild_waits_during_day(service):
    from backend.area_snapshot import refresh
    with patch('backend.operations_window.night_open',return_value=False),patch('backend.area_snapshot.stamp',side_effect=AssertionError('no build')):
        state={};assert refresh(service,state,scheduled=True)==[] and state['status']=='NIGHT_WAIT'


def test_parallel_fetcher_preserves_scheduled_window(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    with patch('backend.operations_window.night_open',return_value=True),bulk_work():
        fetcher=Fetcher('test',tmp_path)
    try:
        with patch('backend.operations_window.night_open',return_value=False),patch.object(fetcher.client,'get') as request:
            with ThreadPoolExecutor(max_workers=1) as pool:
                with pytest.raises(NightWindowClosed):
                    pool.submit(fetcher.get,'https://www.lh.or.kr/test').result()
            request.assert_not_called()
    finally:fetcher.close()


def test_scheduled_collector_cannot_commit_success_after_window(service):
    opened=[True]
    def collected(*args):
        opened[0]=False
        return [],{}
    with patch('backend.operations_window.night_open',side_effect=lambda:opened[0]),bulk_work():
        with patch('backend.service.collect',side_effect=collected):
            result=service._collect_one(dict(id='night-test',name='test'))
    assert result['status']=='PAUSED'
    with service.sessions() as db:
        assert db.scalar(select(Batch)).status=='PAUSED'
