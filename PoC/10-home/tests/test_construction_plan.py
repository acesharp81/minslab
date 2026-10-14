import unittest
from datetime import date
from backend.construction_plan import construction_plan
from backend.roadmap import source_events

class ConstructionPlanTests(unittest.TestCase):
    def test_monthly_endpoints_and_observation_date_gap(self):
        row=dict(start_plan_date='2026-01-01',completion_plan_date='2026-12-31',
                 progress_pct=20,progress_date='2026-03-31')
        p=construction_plan(row,date(2026,10,12))
        self.assertEqual(p['method'],'LINEAR_ESTIMATE')
        self.assertEqual(len(p['monthly']),12)
        self.assertEqual([x['pct'] for x in p['milestones']],[0,25,50,75,100])
        self.assertEqual(p['milestones'][0]['date'],'2026-01-01')
        self.assertEqual(p['monthly'][-1]['planned_pct'],100)
        self.assertLess(p['comparison']['planned_pct'],p['current_planned_pct'])
        self.assertEqual(p['comparison']['actual_pct'],20)
        self.assertEqual(p['comparison']['date'],'2026-03-31')
    def test_no_inferred_completion_or_plan_with_missing_reversed_dates(self):
        for row in ({},dict(start_plan_date='2026-01-01'),dict(start_plan_date='2026-02-01',completion_plan_date='2026-01-01')):
            self.assertIsNone(construction_plan(row,date(2026,10,12)))
    def test_before_start_after_end_and_future_observation(self):
        row=dict(start_plan_date='2027-01-01',completion_plan_date='2028-12-31',progress_pct=0,progress_date='2027-03-01')
        p=construction_plan(row,date(2026,10,12));self.assertEqual(p['current_planned_pct'],0);self.assertIsNone(p['comparison'])
        p=construction_plan(row,date(2029,1,1));self.assertEqual(p['current_planned_pct'],100);self.assertEqual(p['comparison']['actual_pct'],0)
    def test_lh_progress_and_incheon_keep_exact_schedule_day(self):
        for sid in ('lh_construction','lh_progress','lh_incheon_construction'):
            events=source_events(dict(source_id=sid,start_plan_date='2027-01-31',completion_plan_date='2029-08-22'),date(2026,10,12))
            self.assertEqual(events[0]['due_date'],'2027-01-31')
            self.assertEqual(events[-1]['due_date'],'2029-08-22')
            self.assertEqual(events[-1]['precision'],'DAY')

    def test_estimated_manual_progress_is_not_labelled_source_observation(self):
        row=dict(start_plan_date='2026-01-01',completion_plan_date='2027-01-01',progress_pct=70,progress_date='2026-10-01',manual_fields={'progress_pct':dict(origin='MANUAL',inferred=True)})
        p=construction_plan(row,date(2026,10,14))
        self.assertEqual(p['comparison']['input_label'],'추정 입력(미수집)')
