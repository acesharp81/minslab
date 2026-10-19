from datetime import date
from backend.map_progress import build_progress
from backend.policy_delivery_comparison import _events, _schedule_targets


def test_map_selection_deduplicates_source_aliases_and_shares_progress_math():
    c=dict(id='C',source_ids=['A','B'],units=100,region='서울특별시',program_id='P',program='프로그램 명칭',
           events=[dict(stage='SUPPLY',event_date='2026-09-01',units=30,origin='MANUAL',inferred=True),
                   dict(stage='MOVE_IN',event_date='2027-01-01',units=30)],
           schedules=[dict(stage='SUPPLY',due_date='2026-09-01',units=100,managed_schedule=True)])
    other=dict(c,id='D',source_ids=['D'],region='경기도',program_id='Q')
    model=dict(as_of_date='2026-10-14',portfolio_cohorts=[c,other],stages={'SUPPLY':'공급'},issues=[],plan={})
    data=build_progress(model,['A','B','UNKNOWN'],region='서울특별시')
    assert build_progress(model,['A','B'],program_id='프로그램 명칭')['project_count']==1
    assert data['project_count']==1
    assert data['source_record_count']==2
    assert data['unmatched_count']==1
    assert data['policy_target']==100
    assert data['comparisons']['SUPPLY']['target_points']==_schedule_targets([c],'SUPPLY','1900-01-01')
    assert data['comparisons']['BUSINESS']['actual_points']==_events([c],'BUSINESS',date(2026,10,14),'1900-01-01',cumulative=True)
    assert data['comparisons']['MOVE_IN']['actual_points']==[]
    assert build_progress(model,['A','B'],program_id='Q')['project_count']==0
    assert build_progress(model,[])['project_count']==0


def test_region_target_uses_input_zero_instead_of_inventing_capacity():
    model=dict(as_of_date='2026-10-14',portfolio_cohorts=[],stages={},issues=[],plan={'region_allocations':{'서울특별시':0}})
    assert build_progress(model,[],region='서울특별시',level='region')['policy_target']==0


def test_policy_scope_uses_policy_goal_and_program_scope_uses_program_goal():
    c=dict(id='C',source_ids=['A'],units=100,region='서울특별시',program_id='P',program='프로그램',events=[],schedules=[])
    model=dict(as_of_date='2026-10-14',portfolio_cohorts=[c],stages={},issues=[],target_units=1350000,
               plan={'program_profiles':{'P':{'values':{'target_units':800}}}})
    assert build_progress(model,['A'],level='region')['policy_target']==1350000
    assert build_progress(model,['A'],program_id='프로그램',level='region')['policy_target']==800
    assert build_progress(model,['A'],level='block')['policy_target']==100


def test_compact_cards_use_this_stage_actuals_and_only_its_confirmed_dates():
    c=dict(id='C',source_ids=['A'],units=1332,region='서울특별시',events=[
        dict(stage='BUSINESS',event_date='2026-04-01',units=100),
        dict(stage='APPROVAL',event_date='2026-04-01',units=200),
        dict(stage='APPROVAL',event_date='2026-07-01',units=300),
        dict(stage='APPROVAL',event_date='2026-08-01',units=400,inferred=True),
        dict(stage='APPROVAL',event_date='2026-09-01',units=500,status='DELAYED'),
        dict(stage='APPROVAL',event_date='2027-01-01',units=1332),
        dict(stage='SUPPLY',event_date='2026-10-01',units=1332)],schedules=[])
    model=dict(as_of_date='2026-10-15',portfolio_cohorts=[c],stages={},issues=[])
    data=build_progress(model,['A'])['comparisons']
    assert data['BUSINESS']['actual_points'][-1]['units']==1332  # Existing cumulative graph math.
    assert data['BUSINESS']['display_actual_points'][-1]['units']==100
    assert data['BUSINESS']['actual_period']==dict(start='2026-04-01',end=None)
    assert data['APPROVAL']['actual_period']==dict(start='2026-04-01',end='2026-07-01')
    assert data['CONSTRUCTION']['display_actual_points']==[]
    assert data['CONSTRUCTION']['actual_period']==dict(start=None,end=None)


def test_announced_start_counts_but_does_not_invent_actual_start_date():
    c=dict(id='C',source_ids=['A'],units=100,region='서울특별시',events=[dict(stage='CONSTRUCTION',event_date='2026-10-16',units=100,status='ACTUAL',date_basis='OBSERVED_BY')],schedules=[])
    model=dict(as_of_date='2026-10-19',portfolio_cohorts=[c],stages={},issues=[])
    data=build_progress(model,['A'])['comparisons']['CONSTRUCTION']
    assert data['actual_points'][-1]['units']==100
    assert data['actual_period']==dict(start=None,end=None)
