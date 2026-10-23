from datetime import date
from copy import deepcopy
from backend.policy_delivery import build_delivery
from backend.policy_delivery_view import screen_view
from test_policy_delivery import FakeService


def test_report_adds_provenance_without_changing_ledger_or_writing():
    service=FakeService()
    row=service.project_rows[0]
    row.update(tenure='공공분양',recorded_at='2026-10-10T00:00:00+00:00',source_revision_id='REV-1',source_payload_hash='abc')
    before=deepcopy(service.project_rows)
    base=build_delivery(service,date(2026,10,12),comparison_scopes=())
    ordinary=screen_view(base)
    report=screen_view(base,report=True)
    assert ordinary['portfolio_cohorts']==report['portfolio_cohorts']
    assert ordinary['portfolio_comparisons']==report['portfolio_comparisons']
    meta=report['portfolio_cohorts'][0]['report_metadata']
    assert meta['supply_type']['code']=='PUBLIC'
    assert meta['source_revisions'][0]['source_revision_id']=='REV-1'
    assert report['report_snapshot']['as_of_date']=='2026-10-12'
    assert 'report_snapshot' not in ordinary
    assert service.project_rows==before


def test_lean_brief_keeps_screen_tracking_without_scanning_market_statistics():
    from backend.policy_delivery_view import policy_report_view
    service=FakeService()
    day=date(2026,10,12)
    expected=screen_view(build_delivery(service,day,comparison_scopes=()))
    calls=[]
    original=service.rows
    def rows(kind,*args,**kwargs):
        calls.append(kind)
        assert kind != 'statistic'
        return original(kind,*args,**kwargs)
    service.rows=rows
    actual=policy_report_view(service,day,'policy')
    # The lean report omits only map/animation presentation fields.
    strip=lambda rows:[{k:v for k,v in row.items() if k not in ('parts','representative_stage')} for row in rows]
    assert strip(actual['portfolio_cohorts'])==strip(expected['portfolio_cohorts'])
    for stage,metric in actual['portfolio_comparisons']['policy']['metrics'].items():
        assert metric['tracking']==expected['portfolio_comparisons']['policy']['metrics'][stage]['tracking']
    assert 'statistic' not in calls


def test_report_api_uses_registered_cache_and_does_not_replace_screen_entry():
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from backend.db import Base
    from backend.app import create_app
    e=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(e)
    app=create_app(e,auto_collect=False)
    try:
        with TestClient(app) as client,patch('backend.policy_delivery_view.policy_report_view',return_value={'status':'READY','report_snapshot':{'as_of_date':'2026-10-12'}}) as build:
            url='/poc/home/api/policy-delivery/view?as_of_date=2026-10-12&report=true'
            first=client.get(url)
            assert first.status_code==200
            assert first.headers['x-home-cache']=='MISS'
            assert client.get(url).headers['x-home-cache']=='HIT'
            assert build.call_count==1
            assert client.get(url+'&group=program:P1').status_code==422
    finally:
        e.dispose()
