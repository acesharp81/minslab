from copy import deepcopy
from datetime import date
from unittest.mock import Mock, patch
from backend.project_brief import report_input


def test_report_uses_only_explicit_identity_members_and_historical_reads():
    day=date(2026,10,20)
    p=dict(id='P1',name='A1',source_ids=['P1','P2'],units=1030)
    ledger=dict(portfolio_cohorts=[p,dict(id='P3',name='A3',source_ids=['P3'],units=200)],policy_id='POL',plan={})
    original=deepcopy(ledger)
    service=Mock()
    service.projects.return_value=[dict(id='P1',planned_units=344),dict(id='P2',planned_units=1030),dict(id='P3',planned_units=200)]
    service.rows.side_effect=lambda kind,day: []
    service.history.return_value=[dict(revision_no=1,values={'reason':'기존 승인 보존'},recorded_at='2026-10-19T00:00:00Z')]
    service.mapping_history.return_value=[]
    matrix={'items':[{'id':'P1','cells':{'SUPPLY':{'sources':[{'source_entity_id':'DOC1','units':344,'basis':'부분 공급'}]}}}]}
    with patch('backend.project_collection.collection_matrix',return_value=matrix) as collect,patch('backend.project_brief.revision_histories',side_effect=lambda service,refs,day:[dict(r,revisions=[]) for r in refs]) as revisions:
        result=report_input(service,'P2',day,ledger)
    assert result['scope']['project_id']=='P1'
    assert result['data']['cohort']['units']==1030
    assert [r['planned_units'] for r in result['data']['projects']]==[344,1030]
    assert result['data']['evidence'][0]['units']==344
    assert collect.call_args.kwargs['as_of']==day
    assert collect.call_args.kwargs['project_ids']==('P1','P2')
    assert revisions.call_args.args[2]==day
    assert any(h['entity_id']=='DOC1' for h in result['data']['histories'])
    assert ledger==original


def test_ambiguous_or_absent_identity_is_not_guessed():
    import pytest
    ledger={'portfolio_cohorts':[{'id':'P1','source_ids':['X']},{'id':'P2','source_ids':['X']}]}
    for pid in ['X']:
        with pytest.raises(ValueError,match='단일 대표사업'):
            report_input(Mock(),pid,date(2026,10,20),ledger)


def test_project_report_api_cache_is_separate_and_future_date_rejected():
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from backend.db import Base
    from backend.app import create_app
    e=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(e)
    app=create_app(e,auto_collect=False)
    try:
        with TestClient(app) as client,patch('backend.policy_delivery_view.policy_report_view',return_value={'status':'READY','portfolio_cohorts':[]}),patch('backend.project_brief.report_input',return_value={'scope':{'project_id':'P1','as_of_date':'2026-10-20'}}) as build:
            url='/poc/home/api/project-brief/P1?as_of_date=2026-10-20'
            a=client.get(url);assert a.status_code==200
            assert a.headers['x-home-cache']=='MISS'
            assert client.get(url).headers['x-home-cache']=='HIT'
            assert build.call_count==1
            assert client.get('/poc/home/api/project-brief/P1?as_of_date=2099-01-01').status_code==422
    finally:e.dispose()


def test_revision_history_preserves_hashes_and_excludes_future_knowledge_without_manifests():
    from datetime import datetime, timezone
    from sqlalchemy import create_engine
    from backend.db import Base, Revision
    from backend.service import HomeService
    from backend.project_brief import revision_histories
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    service=HomeService(engine)
    try:
        with service.sessions.begin() as session:
            for number,hour in [(1,14),(2,16)]:
                session.add(Revision(id='REV'+str(number),entity_id='P',kind='project',source_id='official',
                    revision_no=number,payload={'base_date':'2026-10-20','planned_units':568+number},payload_hash='hash'+str(number),
                    batch_id='archive-ref',recorded_at=datetime(2026,10,20,hour,tzinfo=timezone.utc),
                    superseded_at=datetime(2026,10,20,16,tzinfo=timezone.utc) if number==1 else None))
        records=revision_histories(service,[{'entity_id':'P','kind':'project'}],date(2026,10,20))
        assert len(records[0]['revisions'])==1
        r=records[0]['revisions'][0]
        assert r['source_revision_id']=='REV1' and r['payload_hash']=='hash1'
        assert r['values']['planned_units']==569
        assert 'snapshots' not in r
    finally:engine.dispose()


def test_project_without_policy_representative_keeps_own_editor_values_without_adding_policy_units():
    from backend.project_brief import project_only_cohort
    p={'id':'SOURCE','name':'사업 관리 원천','planned_units':1198,'mapping':{'status':'CONFIRMED'}}
    matrix={'items':[{'id':'SOURCE','cells':{'CONSTRUCTION':{'management':{
        'measurement':[{'milestone':'CONSTRUCTION','date':'2024-07-10','units':1198,'manual':True,'inferred':True,'reason':'선후관계 검토'}],
        'target':[{'milestone':'COMPLETION','date':'2028-01-21','units':1198,'manual':True}]}}}}]}
    result=project_only_cohort(p,matrix)
    assert result['ledger_scope']=='PROJECT_ONLY'
    assert result['source_ids']==['SOURCE']
    assert result['events'][0]['inferred'] is True
    assert result['events'][0]['reason']=='선후관계 검토'
    assert result['schedules'][0]['stage']=='COMPLETION'


def test_slow_report_returns_pending_and_poll_reuses_one_build():
    from concurrent.futures import TimeoutError
    from fastapi.testclient import TestClient
    from starlette.responses import Response
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from backend.db import Base
    from backend.app import create_app
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with patch('backend.app.ThreadPoolExecutor') as executor:
            future=executor.return_value.submit.return_value
            future.result.side_effect=[TimeoutError(),Response('{"kind":"project"}',media_type='application/json')]
            with TestClient(create_app(engine,auto_collect=False)) as client:
                url='/poc/home/api/project-brief/P?as_of_date=2026-10-20'
                pending=client.get(url)
                assert pending.status_code==202 and pending.json()['status']=='PENDING'
                assert client.get(url).status_code==200
                assert executor.return_value.submit.call_count==1
    finally:engine.dispose()


def test_abandoned_completed_reports_release_capacity_without_discarding_pending_work():
    from concurrent.futures import TimeoutError
    from fastapi.testclient import TestClient
    from starlette.responses import Response
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from backend.db import Base
    from backend.app import create_app
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    jobs=[Mock() for _ in range(9)]
    for job in jobs[:8]:
        job.done.return_value=False
        job.result.side_effect=TimeoutError()
    jobs[8].result.return_value=Response('{"kind":"project"}',media_type='application/json')
    try:
        with patch('backend.app.ThreadPoolExecutor') as executor:
            executor.return_value.submit.side_effect=jobs
            with TestClient(create_app(engine,auto_collect=False)) as client:
                for i in range(8):
                    assert client.get(f'/poc/home/api/project-brief/P{i}?as_of_date=2026-10-20').status_code==202
                url='/poc/home/api/project-brief/NEXT?as_of_date=2026-10-20'
                assert client.get(url).status_code==429
                assert executor.return_value.submit.call_count==8
                # The tab for P0 closed, but its job has now finished.
                jobs[0].done.return_value=True
                assert client.get(url).status_code==200
                assert executor.return_value.submit.call_count==9
                # Other active jobs are still reused, not restarted.
                assert client.get('/poc/home/api/project-brief/P1?as_of_date=2026-10-20').status_code==202
                assert executor.return_value.submit.call_count==9
    finally:engine.dispose()
