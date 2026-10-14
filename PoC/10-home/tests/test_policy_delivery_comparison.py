import unittest
from datetime import date
from backend.policy_delivery_comparison import comparison_index


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.plan=dict(policy_id='POL_2025_0907',period_start='2026-01-01',evidence_url='https://official/plan',
                       annual=[dict(year=2026,units=269000,seoul_units=68000),dict(year=2027,units=246000,seoul_units=63000)])
        self.cohort=dict(id='A1',source_ids=['A1','ALIAS'],name='A1',units=1000,region='경기도',
                         municipality_id='CITY',municipality='고양시',events=[],schedules=[])
        self.config=dict(targets=[])
        self.statistics=[]
        self.reference=date(2026,10,12)

    def model(self):
        return comparison_index(self.plan,[self.cohort],self.config,self.statistics,self.reference)

    def add_month(self,month,values=(100,200,300)):
        for region,value in zip(('서울특별시','경기도','인천광역시'),values):
            self.statistics.append(dict(region=region,statistic_metric='착공',statistic_period='2026'+month,
                                        units=value,evidence_url='https://official/stat'))

    def test_official_targets_pair_with_partial_common_month_actuals(self):
        self.add_month('01');self.add_month('02',(200,300,400))
        model=self.model()['policy']['metrics']['CONSTRUCTION']
        annual=next(a for a in model['annual'] if a['year']==2026)
        self.assertEqual(annual['target_units'],269000)
        self.assertEqual(annual['actual_units'],1500)
        self.assertEqual(annual['actual_cumulative_units'],1500)
        self.assertEqual(annual['actual_through'],'2026-02-28')
        self.assertEqual(annual['actual_status'],'PARTIAL')
        future=next(a for a in model['annual'] if a['year']==2027)
        self.assertEqual(future['target_cumulative_units'],515000)
        self.assertIsNone(future['actual_units'])
        self.assertIsNone(future['actual_cumulative_units'])

    def test_missing_month_never_becomes_zero_or_a_false_cumulative_total(self):
        self.add_month('01');self.add_month('03')
        model=self.model()['policy']['metrics']['CONSTRUCTION']
        self.assertEqual(len(model['actual_points']),1)
        self.assertEqual(model['actual_points'][0]['units'],600)

    def test_missing_one_region_limits_whole_scope_to_common_period(self):
        self.add_month('01');self.add_month('02');self.statistics.pop()
        model=self.model()
        self.assertEqual(len(model['policy']['metrics']['CONSTRUCTION']['actual_points']),1)
        self.assertEqual(len(model['region:경기도']['metrics']['CONSTRUCTION']['actual_points']),2)
        self.assertEqual(len(model['region:서울특별시']['metrics']['CONSTRUCTION']['target_points']),2)
        self.assertEqual(model['region:인천광역시']['metrics']['CONSTRUCTION']['target_points'],[])

    def test_source_zero_and_not_acquired_remain_distinct(self):
        self.add_month('01',(0,0,0))
        model=self.model()['policy']['metrics']
        self.assertEqual(model['CONSTRUCTION']['actual_points'][0]['units'],0)
        self.assertEqual(model['BUSINESS']['actual_points'],[])
        self.assertTrue(all(a['actual_units'] is None for a in model['BUSINESS']['annual']))

    def test_partial_supply_and_repeated_sources_count_once(self):
        self.cohort['events']=[dict(stage='SUPPLY',event_date='2026-06-01',units=200),
                               dict(stage='SUPPLY',event_date='2026-07-01',units=200),
                               dict(stage='SUPPLY',event_date='2026-08-01',units=500),
                               dict(stage='SUPPLY',event_date='2026-09-01',units=1000,status='DELAYED')]
        schedule=lambda when,units:dict(stage='SUPPLY',due_date=when,units=units,origin='SOURCE',source_object_id='A1')
        self.cohort['schedules']=[schedule('2026-06-01',200),schedule('2026-06-01',200),schedule('2027-01-01',800)]
        model=self.model()
        for key in ('policy','city:CITY','project:A1'):
            measure=model[key]['metrics']['SUPPLY']
            a=next(a for a in measure['annual'] if a['year']==2026)
            self.assertEqual(a['target_units'],200)
            self.assertEqual(a['actual_units'],500)
            self.assertEqual(measure['target_points'][-1]['units'],1000)

    def test_operator_cumulative_goals_are_not_added_as_annual_supply(self):
        self.config['targets']=[dict(scope_kind='policy',scope_id='POL_2025_0907',stage='BUSINESS',
                                    due_date=d,units=u,origin='MANUAL',basis='담당자 목표')
                                for d,u in [('2026-12-31',1000),('2027-12-31',2000)]]
        model=self.model()['policy']['metrics']['BUSINESS']
        a=next(a for a in model['annual'] if a['year']==2027)
        self.assertIsNone(a['target_units'])
        self.assertEqual(a['management_cumulative_units'],2000)
        self.assertEqual(model['target_points'],[])

    def test_stage_and_scope_do_not_borrow_an_unrelated_actual(self):
        self.cohort['events']=[dict(stage='CONSTRUCTION',event_date='2026-03-01',units=1000)]
        model=self.model()
        self.assertEqual(model['project:A1']['metrics']['CONSTRUCTION']['actual_points'][0]['units'],1000)
        self.assertEqual(model['project:A1']['metrics']['APPROVAL']['actual_points'],[])
        self.assertEqual(model['region:서울특별시']['metrics']['CONSTRUCTION']['actual_points'],[])


    def test_program_and_region_intersection_keep_policy_goals_out(self):
        self.cohort.update(program_id='PRG_A', program='프로그램 A')
        self.cohort['events']=[dict(stage='SUPPLY',event_date='2026-07-01',units=120)]
        self.config['targets']=[dict(scope_kind='program',scope_id='PRG_A',stage='SUPPLY',due_date='2026-12-31',units=200)]
        other=dict(self.cohort,id='B',source_ids=['B'],program_id='PRG_B',program='프로그램 B',events=[dict(stage='SUPPLY',event_date='2026-07-01',units=900)])
        data=comparison_index(self.plan,[self.cohort,other],self.config,[],self.reference)
        model=data['program:PRG_A']['metrics']
        self.assertEqual(model['SUPPLY']['actual_points'][-1]['units'],120)
        self.assertEqual(model['SUPPLY']['management_points'][0]['units'],200)
        self.assertEqual(model['CONSTRUCTION']['target_points'],[])
        subset=data['program:PRG_A|region:경기도']['metrics']['SUPPLY']
        self.assertEqual(subset['actual_points'][-1]['units'],120)
        self.assertEqual(subset['management_points'],[])


    def test_manual_movein_and_past_project_targets_are_not_hidden(self):
        self.cohort['events']=[dict(stage='MOVE_IN',event_date='2025-10-01',units=400,origin='MANUAL',inferred=True)]
        self.cohort['schedules']=[dict(stage='MOVE_IN',due_date='2025-09-01',units=500,origin='MANUAL',managed_schedule=True)]
        c=self.model()['policy']['metrics']['MOVE_IN']
        self.assertEqual(c['actual_points'][-1]['units'],400)
        self.assertEqual(c['tracking']['target_points'][-1]['units'],500)
        self.assertEqual(c['tracking']['actual_points'][-1]['manual_units'],400)
        self.assertEqual(c['tracking']['actual_points'][-1]['inferred_units'],400)

    def test_tracking_includes_registered_old_projects_but_keeps_macro_separate(self):
        self.add_month('01')
        old=dict(self.cohort,id='OLD',source_ids=['OLD'],events=[dict(stage='CONSTRUCTION',event_date='2025-01-01',units=700,origin='MANUAL')],schedules=[dict(stage='CONSTRUCTION',due_date='2025-01-01',units=800,origin='MANUAL',managed_schedule=True)])
        c=comparison_index(self.plan,[self.cohort],self.config,self.statistics,self.reference,program_cohorts=[self.cohort,old])['policy']['metrics']['CONSTRUCTION']
        self.assertEqual(c['actual_points'][-1]['units'],600)
        self.assertEqual(c['tracking']['actual_points'][-1]['units'],700)
        self.assertEqual(c['tracking']['target_points'][-1]['units'],800)
        self.assertEqual(c['tracking']['project_count'],2)

    def test_future_movein_plan_never_creates_measured_points(self):
        self.cohort['schedules']=[dict(stage='MOVE_IN',due_date='2028-01-01',units=1000,origin='MANUAL',managed_schedule=True)]
        c=self.model()['policy']['metrics']['MOVE_IN']['tracking']
        self.assertEqual(c['target_points'][0]['units'],1000)
        self.assertEqual(c['actual_points'],[])


    def test_tracking_cumulative_reach_includes_later_stages_without_double_counting(self):
        self.cohort['events']=[dict(stage='APPROVAL',event_date='2026-01-01',units=50),dict(stage='SUPPLY',event_date='2026-02-01',units=100,origin='MANUAL')]
        m=self.model()['policy']['metrics']
        for stage in ('BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY'):
            self.assertEqual(m[stage]['tracking']['actual_points'][-1]['units'],100)
        self.assertEqual(m['MOVE_IN']['tracking']['actual_points'],[])
        self.assertEqual(m['BUSINESS']['actual_points'],[])  # preserve the original same-stage reference

    def test_explicit_zero_measurement_is_retained(self):
        self.cohort['events']=[dict(stage='SUPPLY',event_date='2026-01-01',units=0,origin='MANUAL')]
        self.assertEqual(self.model()['policy']['metrics']['SUPPLY']['tracking']['actual_points'][-1]['units'],0)


if __name__=='__main__':unittest.main()
