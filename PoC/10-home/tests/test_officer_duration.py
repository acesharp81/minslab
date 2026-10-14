from copy import deepcopy
from datetime import date
import unittest
from backend.officer_duration import construction_days,refine_project
from backend.officer_completion import STAGES

def model():
    return {k:dict(mean_days=v,sample_count=10,origin='COLLECTED_INTERVAL_MEAN',**(dict(days_per_unit=1.5,typical_units=750) if k=='CONSTRUCTION_COMPLETION' else {})) for k,v in [('BUSINESS_APPROVAL',300),('APPROVAL_CONSTRUCTION',200),('CONSTRUCTION_COMPLETION',1125),('COMPLETION_MOVE_IN',60),('CONSTRUCTION_SUPPLY',180)]}
def goals():
    dates=['2025-01-01','2026-01-01','2027-01-01','2030-01-01','2028-01-01','2030-03-01']
    return {s:dict(due_date=d,units=500,input_rule='OFFICER_SCHEDULE_ESTIMATE',inferred=True) for s,d in zip(STAGES,dates)}

class DurationTests(unittest.TestCase):
    def test_large_district_parallel_model_not_serial_80_year_build(self):
        v=construction_days(dict(planned_units=20000,block=None),model())
        self.assertGreater(v['parallel_groups'],1)
        self.assertEqual(v['raw_days'],30000)
        self.assertLess(v['days'],1500)
        self.assertEqual(construction_days(dict(planned_units=500,block='A1'),model())['days'],750)
    def test_completion_anchor_implies_movein_gap_and_does_not_create_actuals(self):
        g=goals();g['COMPLETION'].update(due_date='2026-07-31',input_rule='SOURCE_ACCEPTED',inferred=False)
        profile=dict(progress={});before=deepcopy(profile)
        changes,calc=refine_project(dict(name='test',planned_units=500,block='A1'),g,profile,model())
        self.assertNotIn('COMPLETION',changes)
        self.assertEqual(changes['MOVE_IN']['due_date'],'2026-09-29')
        self.assertEqual(changes['CONSTRUCTION']['due_date'], '2024-07-11')
        self.assertEqual(profile,before)
    def test_known_move_in_date_kept_and_missing_completion_backcalculated(self):
        g=goals();g['MOVE_IN'].update(due_date='2029-09-30',input_rule='SOURCE_ACCEPTED',inferred=False)
        changes,_=refine_project(dict(name='test',planned_units=500,block='A1'),g,dict(progress={}),model())
        self.assertNotIn('MOVE_IN',changes)
        self.assertEqual(changes['COMPLETION']['due_date'],'2029-08-01')
