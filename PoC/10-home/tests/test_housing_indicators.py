from datetime import date
import pytest
from backend.housing_indicators import (price_series,housing_series,annual_series,monthly_starts,unsold_series,future_schedules,assessed_delay,build_indicators,CAPITAL)
from backend.apartment_prices import parse_prices,place_for_path

REF=date(2026,10,15)

def cohort(**changes):
    c=dict(id='C',source_ids=['A','B'],name='시험 아파트',units=1000,planned_units=1000,region='서울특별시',municipality='강남구',municipality_id='11|강남구',program_id='P',developer='한국토지주택공사',events=[],schedules=[],mapping_status='CONFIRMED')
    c.update(changes);return c

def event(stage='CONSTRUCTION',when='2026-01-10',units=500,**extra):return dict(stage=stage,event_date=when,units=units,**extra)
def plan(stage='MOVE_IN',when='2028-01-01',units=1000,**extra):return dict(stage=stage,due_date=when,units=units,origin='SOURCE',**extra)
def statistic(period,units,region='서울특별시',metric='착공'):return dict(region=region,statistic_metric=metric,statistic_period=period,units=units)

def model(cohorts):
    return dict(status='READY',policy_id='POL_2025_0907',name='정책',target_units=1350000,cohorts=cohorts,portfolio_cohorts=cohorts,
        geometry=dict(shapes=[dict(id='11|강남구',name='강남구',region='서울특별시',rings=[],longitude=127,latitude=37.5)]),
        plan=dict(annual=[dict(year=2026,units=269000,seoul_units=68000)],program_profiles={'P':dict(name='프로그램',values=dict(metric='CAPACITY',unit='개',target_units=3))}))

def test_price_change_requires_same_vintage_basis_and_consecutive_month():
    row=lambda period,index,vintage='v1':dict(region='서울특별시',municipality=None,period=period,index=index,index_basis='2026.06=100',source_vintage=vintage)
    r=price_series([row('2026-05',100),row('2026-06',101),row('2026-08',105),row('2026-09',106,'v2')],'서울특별시',None,REF)
    assert r[0]['change_pct'] is None
    assert r[1]['change_pct']==1
    assert r[2]['change_pct'] is None
    assert r[3]['change_pct'] is None


def test_public_price_parser_retains_geography_and_missing_cells():
    d={'RESULT':{'CODE':0},'DATA':[{'CATE1':'인천','CATE2':'검단구','COL_202607100001OD':'100.00','COL_202608100001OD':'-'}]}
    records=parse_prices(d,{'id':'reb_apartment_price'},'2026.06=100')
    assert len(records)==1
    assert records[0][2]['municipality']=='검단구'
    assert place_for_path(['서울','강남지역','동남권']) is None
    with pytest.raises(ValueError):parse_prices(dict(d,DATA=d['DATA']*2),{'id':'source'},'base')


def test_partial_year_is_not_a_full_year_and_regions_use_common_months():
    stats=[statistic('202501',100),statistic('202502',200),statistic('202501',300,'경기도')]
    data=annual_series(stats,['서울특별시','경기도'],REF)
    assert data[0]['metrics']['착공']==dict(units=400,complete=False,periods=1,through_period='01')
    stats=[statistic('2025'+f'{m:02}',100) for m in range(1,13)]
    assert annual_series(stats,['서울특별시'],REF)[0]['metrics']['착공']['complete']


def test_monthly_yoy_same_period_and_no_cumulative_bridge_over_missing_month():
    stats=[statistic('202601',100),statistic('202603',300),statistic('202501',50),statistic('202502',60),statistic('202503',70)]
    c=cohort(events=[event(units=10),event(when='2026-02-10',units=20,inferred=True)])
    data=monthly_starts(stats,['서울특별시'],2026,REF,[c])
    assert data[0]['cumulative']==100 and data[0]['yoy_pct']==100
    assert data[1]['cumulative'] is None and data[2]['cumulative'] is None
    assert data[1]['policy_cumulative']==20
    assert data[1]['confirmed_policy_cumulative']==10  # Estimated record is not policy-recognised.
    assert data[10]['regional'] is None and data[10]['policy_cumulative'] is None
    assert monthly_starts([],['서울특별시'],2026,REF,[])[0]['confirmed_policy_cumulative'] is None


def test_official_housing_ratio_does_not_become_a_new_calculated_publication():
    common=dict(metric_group='kosis_housing',region='인천광역시',municipality=None,households=100,housing_units=99)
    data=housing_series([dict(common,year=2024,official_ratio=98.5,source_date='2025-12-08'),dict(common,year=2025,official_ratio=None,source_date='2026-07-24')],'인천광역시',None,REF)
    assert data[-1]['official_ratio'] is None and data[-1]['calculated_ratio']==99
    assert housing_series([dict(common,year=2025,source_date='2026-07-24')],'인천광역시',None,date(2026,1,1))==[]


def test_future_schedule_deduplication_capacity_and_missing_measurements():
    c=cohort(schedules=[plan(units=400),plan(units=400),plan(when='2029-01-01',units=900)])
    data=future_schedules([c,cohort(id='missing',schedules=[])],REF)
    assert [p['units'] for p in data['points']]==[400,600]
    assert data['missing_move_in_schedule_count']==1
    assert data['overdue_move_in_units']==0
    c=cohort(schedules=[plan(when='2026-01-01')])
    assert future_schedules([c],REF)['overdue_move_in_units']==0  # Unmeasured is not delayed zero.


def test_delay_threshold_and_unique_project_gap():
    for actual,status in [(980,'DELAYED'),(981,'WARNING'),(1000,'NORMAL')]:
        c=cohort(schedules=[plan('CONSTRUCTION','2026-01-01')],events=[event(units=actual)])
        assert assessed_delay(c,REF)['status']==status
    assert assessed_delay(cohort(schedules=[plan('CONSTRUCTION','2026-01-01')]),REF)['gap_units']==0


def test_unsold_completed_is_subset_not_addition_and_zero_share_is_missing():
    row=lambda region,metric,units:dict(region=region,municipality=None,period='2026-08',metric=metric,units=units)
    records=[row('서울특별시','TOTAL',100),row('서울특별시','COMPLETED',40)]
    data=unsold_series(records,['서울특별시'],None,REF)
    assert data[0]['total']==100 and data[0]['pre_completion']==60 and data[0]['completed_share_pct']==40
    assert unsold_series(records,['서울특별시','경기도'],None,REF)==[]
    assert unsold_series([row('서울특별시','TOTAL',0),row('서울특별시','COMPLETED',0)],['서울특별시'],None,REF)[0]['completed_share_pct'] is None
    with pytest.raises(ValueError):unsold_series([row('서울특별시','TOTAL',1),row('서울특별시','COMPLETED',2)],['서울특별시'],None,REF)


def test_scope_and_goal_comparison_never_borrow_other_programs_or_regional_totals():
    c=cohort();other=cohort(id='other',source_ids=['X'],program_id='Q')
    d=build_indicators(model([c,other]),[],[],[],[],'program','P',REF)
    assert d['scope']['project_count']==1 and d['goal']['total_value']==3 and d['goal']['unit']=='개'
    assert d['goal_scale']['multiplier'] is None
    d=build_indicators(model([c,other]),[],[],[],[],'project','B',REF)
    assert d['scope']['project_count']==1 and d['scope']['name']==c['name']
    with pytest.raises(ValueError):build_indicators(model([c]),[],[],[],[],'project','unknown',REF)
    with pytest.raises(ValueError):build_indicators(model([c]),[],[],[],[],'policy','POL_2025_0907',REF,region='경기도',municipality_id='11|강남구')


def test_average_uses_complete_prior_years_only_and_preserves_missing():
    stats=[statistic(str(y)+f'{m:02}',100) for y in (2023,2024,2025) for m in range(1,13)]
    stats+=[statistic('202601',50000)]
    d=build_indicators(model([]),stats,[],[],[],'policy','POL_2025_0907',REF,region='서울특별시')
    assert d['averages']['착공']['value']==1200 and d['goal']['value']==68000
    assert d['goal_scale']['multiplier']==68000/1200
    d=build_indicators(model([]),stats[:-2],[],[],[],'policy','POL_2025_0907',REF,region='서울특별시')
    assert d['averages']['착공']['value'] is None and d['goal_scale']['multiplier'] is None


def test_public_endpoint_validates_scope_and_period_before_returning_cached_comparison():
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from backend.db import Base
    from backend.app import create_app
    from unittest.mock import patch
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine)
    app=create_app(engine,auto_collect=False)
    with patch('backend.app.build_delivery',return_value=model([])):
        client=TestClient(app);url='/poc/home/api/housing-indicators'
        response=client.get(url,params={'region':'인천광역시'})
        assert response.status_code==200 and response.json()['scope']['regions']==['인천광역시']
        assert client.get(url,params={'baseline_years':4}).status_code==422
        assert client.get(url,params={'kind':'program','scope_id':'unknown'}).status_code==422
        assert client.get(url,params={'year':REF.year+11}).status_code==422
        assert client.get(url,params={'kind':'project','scope_id':'unknown'}).status_code==422
    engine.dispose()


def test_type_classification_uses_only_saved_source_ids_and_keeps_conflicts_unknown():
    from backend.housing_indicators import classification
    c=cohort(name='공공택지 A1',developer=None)
    rows=[dict(id='A',name='공공택지 A1 아파트 건설공사',developer='한국토지주택공사'),dict(id='different',name='공공택지 A1 오피스텔',developer='㈜민간')]
    data=classification([c],rows)
    assert data['housing_types']==[dict(label='아파트',units=1000)]
    assert data['sectors']==[dict(label='공공 시행기관',units=1000)]
    assert classification([c],rows+[dict(id='B',name='오피스텔 공급')])['housing_types'][0]['label']=='주택유형 미분류'


def test_severe_stage_wins_even_if_warning_has_a_larger_absolute_gap():
    c=cohort(schedules=[plan('BUSINESS','2026-01-01',1000),plan('APPROVAL','2026-01-01',500)],events=[event('BUSINESS',units=981),event('APPROVAL',units=490)])
    result=assessed_delay(c,REF)
    assert result==dict(status='DELAYED',gap_units=10,stage='APPROVAL')
