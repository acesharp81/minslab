from copy import deepcopy
import json
from pathlib import Path
from backend.report_reproducibility import evaluate

BENCHMARK=json.loads((Path(__file__).parents[1]/'backend/data/official_benchmark_20261016.json').read_text())


def inputs():
    projects=[dict(id='third',name='인천계양 A17',district='인천계양',block='A17',region='인천광역시',program='공공주택 건설'),
              dict(id='other',name='평택고덕 A65',district='평택고덕',block='A65',region='경기도',program='공공주택 건설')]
    events=[dict(event_id='e1',project_id='third',name='인천계양 A17',region='인천광역시',event_date='2026-10-17',
        event_type='CONSTRUCTION_STARTED',quantity=463,source_id='lh_construction',source_revision_id='rev1'),
        dict(event_id='e2',project_id='other',name='평택고덕 A65',region='경기도',event_date='2026-03-01',
        event_type='CONSTRUCTION_STARTED',quantity=837,source_id='lh_construction',source_revision_id='rev2')]
    snapshot=dict(id='snapshot',context=dict(known_at='2026-10-16T23:00:00+00:00'),result=dict(selected_events=events))
    return snapshot,projects,dict(plan={'target_units':1350000},portfolio_cohorts=[]),dict(rows=[]),[]


def test_third_town_is_scoped_by_district_not_program_label_or_all_construction():
    result=evaluate(BENCHMARK,*inputs());rows={r['id']:r for r in result['rows']}
    assert rows['M08']['own_value']==463  # Incheon is included despite its UI programme label.
    assert rows['M08']['event_ids']==['e1']
    assert rows['M04']['own_value']==1300
    assert rows['M08']['numeric_gap'] is None and not rows['M08']['comparable']
    assert rows['M15']['own_value'] is None  # Unknown private classification cannot borrow all events.


def test_briefing_answers_do_not_change_own_results_or_readiness():
    changed=deepcopy(BENCHMARK)
    for r in changed['rows']:r['official_value']=99999999
    before=evaluate(BENCHMARK,*inputs());after=evaluate(changed,*inputs())
    assert [(r['own_value'],r['status']) for r in before['rows']]==[(r['own_value'],r['status']) for r in after['rows']]
    assert len(before['rows'])==53 and before['reportability_score'] is None
    assert before['full_report_ready'] is False


def test_prior_year_and_unknown_quantity_are_not_current_year_zero():
    args=list(inputs());args[0]['result']['selected_events'][0]['event_date']='2025-12-31'
    result=evaluate(BENCHMARK,*args);rows={r['id']:r for r in result['rows']}
    assert rows['M08']['own_value'] is None
    assert rows['M08']['status']=='SOURCE_EVIDENCE_GAP'
    assert rows['M27']['status']=='POLICY_FACT_REQUIRED'
    assert rows['M13']['status']=='INPUT_LEDGER_GAP'
    assert rows['M05']['status']=='FORECAST_GAP'
