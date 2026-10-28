from copy import deepcopy
import csv
import io
from datetime import date
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from backend.db import Base,upsert_revision,Batch,now
from backend.service import HomeService
from backend.app import create_app
from backend.policy_delivery import build_delivery
from backend.policy_delivery_view import screen_view
from backend.projection_cache import delivery_screen_projection_version
from test_policy_delivery import FakeService


class Source(FakeService):
    def __init__(self):
        super().__init__()
        for p,pid,city in zip(self.project_rows,('P1','P2'),('C1','C2')):
            p['mapping']['program_id']=pid;p['municipality']=city
    def supply_dashboard(self,**kwargs):
        return dict(blocks=[],municipalities=[dict(id=city,name=city,region='경기도',project_ids=[p['id']])
            for p,city in zip(self.project_rows,('C1','C2'))],knowledge_date='2026-10-12')


def test_screen_does_not_fetch_discarded_source_diagnostics():
    service=Source()
    with patch.object(service,'sources',side_effect=AssertionError('unused source scan')):
        assert build_delivery(service,date(2026,10,12),comparison_scopes=())['status']=='READY'


def test_unlinked_discovery_keeps_screen_cache_but_approved_links_and_source_edits_invalidate():
    engine=create_engine('sqlite://',poolclass=StaticPool);Base.metadata.create_all(engine)
    service=HomeService(engine)
    try:
        initial=delivery_screen_projection_version(service)
        with service.sessions.begin() as db:
            doc,_=upsert_revision(db,'document_evidence','sh_notice_watch','new',{'name':'신규 공고'},'collect')
        assert delivery_screen_projection_version(service)==initial
        with service.sessions.begin() as db:
            upsert_revision(db,'evidence_bridge','officer','link',{'source_entity_id':doc.entity_id,'facts':[],'status':'CONFIRMED'},'approve')
        linked=delivery_screen_projection_version(service)
        assert linked!=initial
        with service.sessions.begin() as db:
            upsert_revision(db,'document_evidence','sh_notice_watch','new',{'name':'정정 공고'},'collect')
        assert delivery_screen_projection_version(service)!=linked
    finally:engine.dispose()


@pytest.fixture
def pair():
    day=date(2026,10,12)
    return build_delivery(Source(),day),build_delivery(Source(),day,comparison_scopes=())


def test_visible_policy_comparisons_and_every_cohort_equal_full_report(pair):
    full,base=pair;before=deepcopy(base);screen=screen_view(base)
    assert base==before
    assert not base['portfolio_comparisons']
    assert len(base['yearly_comparisons'])==1
    for k in ('cohorts','portfolio_cohorts','current','snapshots','geometry','issues','map_reconciliation'):
        assert screen[k]==full[k]
    for field in ('yearly_comparisons','portfolio_comparisons'):
        for key,value in screen[field].items():assert value==full[field][key]
        assert 'program:P2' not in screen[field] and 'project:new' not in screen[field]
    assert '_comparison_inputs' not in screen and 'goal_comparisons' not in screen


def test_program_map_and_lazily_selected_project_equal_full_report(pair):
    full,base=pair
    for group,scope in [('program:P1',None),('policy','project:old')]:
        screen=screen_view(base,group,scope)
        for field in ('yearly_comparisons','portfolio_comparisons'):
            for key,value in screen[field].items():assert value==full[field][key]
        assert screen['portfolio_cohorts']==full['portfolio_cohorts']
    program=screen_view(base,'program:P1','program:P1|project:new')
    assert program['portfolio_comparisons']['program:P1|project:new']==full['portfolio_comparisons']['project:new']
    with pytest.raises(ValueError):screen_view(base,'program:P1','project:old')
    with pytest.raises(ValueError):screen_view(base,'program:missing')


def test_empty_map_selection_has_no_fabricated_actual_or_project(pair):
    _,base=pair;base['geometry']['shapes'].append(dict(id='empty',name='사업 미식별 구',region='서울특별시'))
    before=deepcopy(base['portfolio_cohorts'])
    for group,scope in [('policy','city:empty'),('program:P1','program:P1|city:empty'),('program:P1','program:P1|region:서울특별시')]:
        screen=screen_view(base,group,scope)
        metric=screen['portfolio_comparisons'][scope]['metrics']['CONSTRUCTION']
        assert metric['actual_points']==[] and metric['tracking']['project_count']==0
        assert screen['portfolio_cohorts']==before


def test_policy_csv_includes_pre_period_projects(pair):
    _,base=pair
    assert len(base['portfolio_cohorts'])>len(base['cohorts'])
    e=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(e);app=create_app(e,auto_collect=False)
    try:
        with TestClient(app) as client,patch('backend.app.build_delivery',return_value=base):
            response=client.get('/poc/home/api/policy-delivery/export.csv')
            assert response.status_code==200
            rows=list(csv.DictReader(io.StringIO(response.text.lstrip('\ufeff'))))
            assert {r['id'] for r in rows}=={c['id'] for c in base['portfolio_cohorts']}
            assert any(r['eligibility_status']=='PRE_POLICY_START' for r in rows)
    finally:e.dispose()


def test_screen_versions_ignore_collection_status_but_see_statistic_and_approved_inputs():
    e=create_engine('sqlite://');Base.metadata.create_all(e);s=HomeService(e)
    try:
        before=delivery_screen_projection_version(s)
        with s.sessions.begin() as db:
            db.add(Batch(source_id='lh_notice',status='SUCCESS',finished_at=now()))
            upsert_revision(db,'area_stat','kosis_living','area',{'year':2026},'ingest')
        assert delivery_screen_projection_version(s)==before
        for kind in ['statistic','project_profile','evidence_bridge','program_profile','block_location']:
            before=delivery_screen_projection_version(s)
            with s.sessions.begin() as db:upsert_revision(db,kind,'officer',kind,{'value':8},'edit')
            assert delivery_screen_projection_version(s)!=before
    finally:e.dispose()


def test_api_reuses_base_between_scopes_and_invalidates_next_officer_read(pair):
    _,base=pair;e=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(e);app=create_app(e,auto_collect=False)
    try:
        with TestClient(app) as client,patch('backend.app.build_delivery',return_value=base) as build:
            url='/poc/home/api/policy-delivery/view?as_of_date=2026-10-12'
            a=client.get(url);assert a.status_code==200 and a.headers['x-home-cache']=='MISS'
            assert client.get(url).headers['x-home-cache']=='HIT'
            assert client.get(url+'&group=program:P1').status_code==200
            assert build.call_count==1
            assert client.get(url+'&group=program:missing').status_code==422
            with app.state.service.sessions.begin() as db:
                upsert_revision(db,'project_profile','officer','p',{'value':16},'edit')
            assert client.get(url).headers['x-home-cache']=='MISS'
            assert build.call_count==2
    finally:e.dispose()


def test_only_selected_comparisons_are_built_and_values_equal_full_report(pair):
    full,base=pair
    initial=screen_view(base,'policy','policy')
    assert set(initial['portfolio_comparisons'])=={'policy'}
    for scope in ('city:C1','region:경기도','project:old'):
        selected=screen_view(base,'policy',scope)
        for field in ('yearly_comparisons','portfolio_comparisons'):
            expected={k:v for k,v in full[field].items() if k in {'policy',scope}}
            assert selected[field]==expected
        assert scope in selected['portfolio_comparisons']
    selected=screen_view(base,'program:P1','program:P1|project:new')
    assert set(selected['portfolio_comparisons'])=={'policy','program:P1','project:new','program:P1|project:new'}


def test_unchanged_chart_survives_half_hour_but_officer_edit_invalidates_immediately(pair):
    _,base=pair
    e=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(e);app=create_app(e,auto_collect=False)
    try:
        with TestClient(app) as client,patch('backend.app.build_delivery',return_value=base) as build,patch('backend.projection_cache.monotonic',return_value=100) as clock:
            url='/poc/home/api/policy-delivery/view?as_of_date=2026-10-12'
            first=client.get(url);assert first.status_code==200 and first.headers['x-home-cache']=='MISS'
            clock.return_value=3700
            repeated=client.get(url)
            assert repeated.headers['x-home-cache']=='HIT' and repeated.json()==first.json() and build.call_count==1
            with app.state.service.sessions.begin() as db:
                upsert_revision(db,'goal','officer','new',dict(base_date='2026-10-12',units=12),'edit')
            changed=client.get(url)
            assert changed.headers['x-home-cache']=='MISS' and build.call_count==2
    finally:e.dispose()
