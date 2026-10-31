import pytest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from backend.db import Base
from backend.service import HomeService
from backend.sources import SOURCES
from backend.general_building_permits import parse,collect
from backend.collection_jobs import enqueue_due

SOURCE=next(s for s in SOURCES if s['id']=='building_general_permit')

def scheduled_jobs():
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    try:
        with patch('backend.collection_jobs.night_open',return_value=True):
            return enqueue_due(HomeService(engine))
    finally:engine.dispose()


def row(**extra):
    return dict(mgmPmsrgstPk='1000000000000000123456',sigunguCd='11680',bjdongCd='10300',
        platPlc='서울특별시 강남구 개포동 1번지',bldNm='원천 건물',archGbCdNm='신축',mainPurpsCdNm='공동주택',
        hhldCnt=0,hoCnt=60,fmlyCnt=30,archPmsDay='20260102',realStcnsDay='',stcnsSchedDay='20260401',**extra)


def response(rows,total=None):
    return dict(response=dict(header=dict(resultCode='00'),body=dict(totalCount=len(rows) if total is None else total,items=dict(item=rows))))


def test_separate_households_rooms_families_and_actual_scheduled_dates():
    records,_=parse(response([row()]),SOURCE,'서울특별시','11680','10300')
    kind,key,p=records[0]
    assert kind=='general_permit' and key=='1000000000000000123456'
    assert p['units']==0 and p['unit_count']==60 and p['family_count']==30
    assert p['dates']['실제착공일 (realStcnsDay)'] is None
    assert p['dates']['착공예정일 (stcnsSchedDay)']=='2026-04-01'
    assert p['facts']==[] and 'ZERO_HOUSEHOLDS_UNRESOLVED' in p['warnings']


@pytest.mark.parametrize('mode',['auth','region','duplicate','missing_pk'])
def test_source_rejection_never_becomes_empty_success(mode):
    data=response([row()])
    if mode=='auth':data=dict(OpenAPI_ServiceResponse=dict(cmmMsgHeader=dict(returnReasonCode='30')))
    elif mode=='region':data['response']['body']['items']['item'][0]['sigunguCd']='99999'
    elif mode=='duplicate':data=response([row(),row()])
    else:data['response']['body']['items']['item'][0]['mgmPmsrgstPk']=''
    with pytest.raises(ValueError):parse(data,SOURCE,'서울특별시','11680','10300')


def test_collection_routes_to_separate_kind_without_policy_creation(monkeypatch):
    monkeypatch.setenv('POC10_GENERAL_BUILDING_SERVICE_KEY','test-key')
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine);s=HomeService(engine)
    with patch('backend.general_building_permits.next_districts',return_value=([('서울특별시','11680','10300','개포동')],{},1)),patch('backend.collectors.Fetcher.get',return_value=__import__('json').dumps(response([row()]))):
        result=s.collect_one(SOURCE)
    assert result['status']=='SUCCESS'
    assert len(s.rows('general_permit'))==1
    assert s.rows('permit')==[] and s.rows('project')==[]
    engine.dispose()


def test_missing_key_is_not_queued_and_partial_pages_are_rejected(monkeypatch):
    monkeypatch.delenv('POC10_GENERAL_BUILDING_SERVICE_KEY',raising=False)
    monkeypatch.delenv('POC10_BUILDING_HUB_SERVICE_KEY',raising=False)
    with patch('backend.collection_jobs.SOURCES',[SOURCE]),patch('backend.collection_jobs.enqueue') as queued:
        assert enqueue_due(object())==[];queued.assert_not_called()
    monkeypatch.setenv('POC10_GENERAL_BUILDING_SERVICE_KEY','test-key')
    with patch('backend.collection_jobs.SOURCES',[SOURCE]),patch('backend.collection_jobs.enqueue',return_value='job'):
        assert scheduled_jobs()==['job']
    class Fetch:
        def get(self,*args,**kwargs):return __import__('json').dumps(response([row()],101))
    with patch('backend.general_building_permits.next_districts',return_value=([('서울특별시','11680','10300','개포동')],{},1)):
        with pytest.raises(ValueError,match='페이지 누락'):collect(SOURCE,Fetch(),object())


def test_existing_portal_key_is_reused_for_collection_and_scheduling(monkeypatch):
    from backend.api_samples import key_for
    monkeypatch.delenv('POC10_GENERAL_BUILDING_SERVICE_KEY',raising=False)
    monkeypatch.setenv('POC10_BUILDING_HUB_SERVICE_KEY','shared%2Bkey%3D')
    assert key_for(SOURCE)=='shared+key='
    with patch('backend.collection_jobs.SOURCES',[SOURCE]),patch('backend.collection_jobs.enqueue',return_value='job'):
        assert scheduled_jobs()==['job']
    monkeypatch.setenv('POC10_GENERAL_BUILDING_SERVICE_KEY','override')
    assert key_for(SOURCE)=='override'


def test_dense_dong_over_ten_thousand_rows_is_fully_paged(monkeypatch):
    import json
    monkeypatch.setenv('POC10_GENERAL_BUILDING_SERVICE_KEY','test-key')
    calls=[]
    class Fetch:
        def get(self,*args,**kwargs):
            page=kwargs['params']['pageNo'];calls.append(page)
            values=[dict(row(),mgmPmsrgstPk=str(i)) for i in range((page-1)*100,min(page*100,10001))]
            return json.dumps(response(values,10001))
    with patch('backend.general_building_permits.next_districts',return_value=([('서울특별시','11680','10300','개포동')],{},1)):
        records,stats=collect(SOURCE,Fetch(),object())
    assert len(records)==10001 and calls==list(range(1,102))
    assert stats['scope_completed_dongs']==1 and stats['complete_scope']


def test_parallel_dongs_keep_independent_pages_and_fail_whole_batch(monkeypatch):
    import json
    monkeypatch.setenv('POC10_GENERAL_BUILDING_SERVICE_KEY','test-key')
    monkeypatch.setenv('POC10_GENERAL_PERMIT_QUERY_WORKERS','2')
    districts=[('서울특별시','11680',code,code) for code in ('10300','10400')]
    class Fetch:
        fail=False
        def get(self,*args,params,**kwargs):
            code=params['bjdongCd'];page=params['pageNo']
            values=[dict(row(),bjdongCd=code,mgmPmsrgstPk=code+str(i))
                    for i in range((page-1)*100,min(page*100,101))]
            if self.fail and code=='10400' and page==2:values=[]
            return json.dumps(response(values,101))
    fetch=Fetch();counts={}
    with patch('backend.general_building_permits.next_districts',return_value=(districts,counts,2)):
        records,stats=collect(SOURCE,fetch,object())
        assert len(records)==202 and len({x[1] for x in records})==202
        assert stats['scope_completed_dongs']==2
        counts.clear();fetch.fail=True
        with pytest.raises(ValueError,match='페이지 누락'):collect(SOURCE,fetch,object())
        assert counts=={}  # A partial success is never published as completed scope.
