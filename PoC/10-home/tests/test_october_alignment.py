from copy import deepcopy
from datetime import date
from backend.october_alignment import build


def cohort(id,name,units,events):
    return dict(id=id,name=name,units=units,region='경기도',municipality_id='city',source_ids=[id],events=events,schedules=[])


def test_official_named_old_start_remains_included_and_is_flagged_without_rewriting():
    row=cohort('old','하남교산 A-2BL',1115,[dict(stage='CONSTRUCTION',event_date='2024-10-30',units=1115)])
    before=deepcopy(row);result=build([row],[dict(id='old',name=row['name'])],date(2026,10,19))
    c=next(c for c in result['cases'] if c['id']=='S03')
    assert c['included_project_ids']==['old'] and c['members'][0]['current_units']==1115
    assert c['members'][0]['issues']==['START_YEAR_CONFLICT'] and not result['exclude_by_start_year']
    assert c['official_units']==1100 and not c['comparison_eligible'] and row==before


def test_source_stage_conflict_is_retained_instead_of_faking_a_start_date_or_capacity():
    row=cohort('heuk','흑석11재정비촉진',1515,[])
    row['schedules']=[dict(stage='CONSTRUCTION',due_date='2028-05-04',units=1515)]
    result=build([row],[],date(2026,10,19));c=next(c for c in result['cases'] if c['id']=='S06')
    assert c['official_units']==1500 and c['members'][0]['units']==1515
    assert c['members'][0]['current_units'] is None
    assert c['members'][0]['issues']==['ANNOUNCED_START_NOT_REFLECTED']
    assert c['members'][0]['future_plan_dates']==['2028-05-04']
    assert row['events']==[]


def test_announcement_scope_is_not_duplicated_per_block_and_wangsuk2_is_not_wangsuk():
    rows=[cohort('a','남양주왕숙2 A01',812,[]),cohort('b','남양주왕숙2 A03',686,[])]
    result=build(rows,[],date(2026,10,19))
    second=next(c for c in result['cases'] if c['id']=='S04')
    first=next(c for c in result['cases'] if c['id']=='S10')
    assert second['official_units']==1100 and second['managed_capacity']==1498
    assert second['scope_status']=='BLOCK_SCOPE_REVIEW' and len(second['members'])==2
    assert not first['members'] and all('official_units' not in m for m in second['members'])
    assert build(rows,[],date(2026,10,15)) is None


def test_written_appendix_components_and_conflicting_transcript_remain_distinct():
    result=build([],[],date(2026,10,19))
    assert sum(r['target_units'] for r in result['start_components'])==268000
    assert sum(r['actual_units'] for r in result['start_components'])==98800
    assert result['official_start_units_lower_bound']==99000
    assert result['component_reconciliation']['unreconciled_minimum']==200
    c=next(c for c in result['cases'] if c['id']=='S06')
    assert c['official_units']==1500 and c['prior_source_value']==2500
    assert c['source_correction_note'] and '#page=4' in c['evidence_url']
    assert '8월' in result['official_start_period'] and '9월' in result['official_start_period']
    assert {c['name'] for c in result['cases'] if c['id'] in ('S17','S18','S19')}=={'부천대장','수원당수2','부천역곡'}
