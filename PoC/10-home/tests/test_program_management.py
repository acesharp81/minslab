import unittest
from datetime import date
from unittest.mock import patch
from backend.program_management import assessment
from backend.policy_delivery_comparison import comparison_index
from tests import test_program_information as fixtures
from backend.program_profile import save,profiles

VALUES=dict(target_units=1000,unit='호',metric='SUPPLY',period_start='2025-10-01',period_end='2026-12-31',target_mode='INDEPENDENT')
def cohort(pid='P',units=1000,when='2026-06-30',amount=400):
    return dict(id='C',name='사업',region='경기도',planned_units=units,units=units,program_id=pid,mapping_status='REVIEW',source_ids=['C'],events=[dict(stage='CONSTRUCTION',event_date='2023-01-01',units=units),dict(stage='SUPPLY',event_date='2026-04-30',units=amount)],schedules=[dict(stage='SUPPLY',due_date=when,units=amount,origin='SOURCE',source_object_id='C',source_base_date='2025-09-07')])

def raw(units=1000):return dict(id='C',planned_units=units,mapping=dict(program_id='P',status='REVIEW'))

class ProgramManagementTests(unittest.TestCase):
    def test_same_stage_period_not_whole_capacity_and_other_programs(self):
        c=cohort();s=assessment('P',VALUES,{},dict(portfolio_cohorts=[c,cohort('OTHER')]),[raw()])
        self.assertEqual(s['capacity_units'],1000);self.assertEqual(s['period_plan_units'],400)
        self.assertEqual(s['plan_gap_units'],600);self.assertEqual(s['counted_project_count'],1)
        self.assertEqual(s['review_project_count'],1)
    def test_unknown_and_outside_period_not_zero(self):
        c=cohort(when='2030-01-01');s=assessment('P',VALUES,{},dict(portfolio_cohorts=[c]),[raw()])
        self.assertIsNone(s['period_plan_units']);self.assertIsNone(s['plan_gap_units']);self.assertEqual(s['outside_period_count'],1)
        s=assessment('P',VALUES,{},dict(portfolio_cohorts=[]),[])
        self.assertIsNone(s['capacity_units']);self.assertEqual(s['subtotal_status'],'NOT_ACQUIRED');self.assertFalse(s['aggregate_allowed'])
    def test_effects_and_nonhousing_not_adopted(self):
        for values,source in ((VALUES,{'target_kind':'EFFECT'}),(dict(VALUES,unit='개소'),{})):
            s=assessment('P',values,source,dict(portfolio_cohorts=[cohort()]),[raw()])
            self.assertIsNone(s['plan_gap_units']);self.assertFalse(s['aggregate_allowed'])
    def test_ambiguous_sources_block_aggregate_adoption(self):
        s=assessment('P',VALUES,{},dict(portfolio_cohorts=[cohort()]),[raw(),dict(raw(),id='UNKNOWN',planned_units=None)])
        self.assertEqual(s['missing_quantity_count'],1);self.assertEqual(s['unresolved_source_count'],1);self.assertFalse(s['aggregate_allowed'])
    def test_supply_program_uses_own_period_even_when_policy_cohort_excludes_prior_start(self):
        plan=dict(policy_id='POL',period_start='2026-01-01',period_end='2030-12-31',annual=[],program_profiles={'P':dict(values=VALUES,source={},overrides={})})
        index=comparison_index(plan,[],{},[],date(2026,10,14),program_cohorts=[cohort()])
        result=index['program:P']['metrics']['SUPPLY']
        self.assertEqual(result['actual_points'][-1]['units'],400)
        self.assertEqual(index['program:P|region:경기도']['metrics']['SUPPLY']['actual_points'][-1]['units'],400)
        self.assertEqual(index['policy']['metrics']['SUPPLY']['actual_points'],[])
    def test_extended_program_period_is_in_annual_comparison(self):
        values=dict(VALUES,period_end='2035-12-31')
        plan=dict(policy_id='POL',period_start='2026-01-01',period_end='2030-12-31',annual=[],program_profiles={'P':dict(values=values,source={},overrides={})})
        metrics=comparison_index(plan,[],{},[],date(2026,10,14))['program:P']['metrics']['SUPPLY']
        self.assertEqual(metrics['annual'][-1]['year'],2035)

    def test_source_case_guidance_and_data_needs_are_preserved(self):
        s=assessment('P',VALUES,dict(management=dict(case='분양기간',guidance='기간 대조',required_data=['블록 목록'],api_ids=['lh_notice'])),dict(portfolio_cohorts=[]))
        self.assertEqual(s['case'],'분양기간');self.assertEqual(s['required_data'],['블록 목록'])

class ProgramAggregateSaveTests(unittest.TestCase):
    setUp=fixtures.ProgramInformationTests.setUp
    edit=fixtures.ProgramInformationTests.edit
    def test_aggregate_snapshot_is_validated_and_source_target_preserved(self):
        c=cohort(self.p,units=80,amount=80);c['id']='PRO_TEST';c['source_ids']=['PRO_TEST'];c['schedules'][0]['stage']='CONSTRUCTION'
        row=dict(id='PRO_TEST',planned_units=80,mapping=dict(program_id=self.p,status='CONFIRMED'))
        with patch.object(self.s,'projects',return_value=[row]),patch('backend.policy_delivery.build_delivery',return_value=dict(portfolio_cohorts=[c])):
            with self.assertRaises(ValueError):self.edit({'target_mode':'PROJECT_SUM','target_units':79})
            self.assertEqual(profiles(self.s)[self.p]['revision_no'],0)
            self.edit({'target_mode':'PROJECT_SUM','target_units':80})
        p=profiles(self.s)[self.p]
        self.assertEqual(p['values']['target_units'],80);self.assertEqual(p['source']['fields']['target_units'],100)
        self.assertEqual(p['overrides']['target_units']['calculation']['project_ids'],['PRO_TEST'])
        self.edit({'name':'사업'},1)
        self.assertEqual(profiles(self.s)[self.p]['values']['target_units'],80)
