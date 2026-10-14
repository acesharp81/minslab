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
