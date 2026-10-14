import unittest
from unittest.mock import patch
from datetime import date
from backend.officer_completion import project_values,normalized,ACTOR,REASON

def cells():
    return {s:dict(sources=[],targets=[],progress={},assessment=None) for s in ('POLICY','BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN')}
def fact(c,stage,day,units=None,**extra):
    c[stage]['sources'].append(dict(kind='ACTUAL',date=day,units=units,**extra))

class OfficerCompletionTests(unittest.TestCase):
    def test_future_plan_never_becomes_measured_and_not_uncollectable(self):
        c=cells();c['MOVE_IN']['targets']=[dict(date='2099-01',units=100,milestone='MOVE_IN')]
        r=project_values(dict(planned_units=100),c,'test')
        self.assertEqual(r['progress'],{})
        self.assertEqual(r['targets']['MOVE_IN']['due_date'],'2099-01-31')
        self.assertTrue(any(x['code']=='UPCOMING' for x in r['remaining']))
        self.assertNotIn('UNAVAILABLE_POLICY_ESTIMATE',[v['input_rule'] for v in r['targets'].values()])
    def test_partial_move_in_backfills_earlier_without_expanding_quantity(self):
        c=cells();fact(c,'MOVE_IN','2025-02-01',30)
        r=project_values(dict(planned_units=100),c,'test')
        self.assertEqual(set(r['progress']),{'BUSINESS','APPROVAL','CONSTRUCTION','COMPLETION','SUPPLY','MOVE_IN'})
        self.assertTrue(all(v['units']==30 for v in r['progress'].values()))
        self.assertTrue(r['progress']['APPROVAL']['inferred'])
        self.assertEqual(r['progress']['APPROVAL']['actor'],ACTOR)
        self.assertEqual(r['progress']['APPROVAL']['reason'],REASON)
        self.assertNotIn('CONSTRUCTION',r['targets']) # equal start/completion deadline rejected
    def test_presale_does_not_invent_construction_or_move_in(self):
        c=cells();fact(c,'SUPPLY','2025-02-01',100)
        r=project_values(dict(planned_units=100),c,'test')
        self.assertEqual(set(r['progress']),{'BUSINESS','APPROVAL','SUPPLY'})
        self.assertEqual(r['targets']['SUPPLY']['due_date'],'2025-02-01')
    def test_zero_and_source_quantity_conflict_are_preserved(self):
        c=cells();fact(c,'SUPPLY','2025-02-01',0)
        r=project_values(dict(planned_units=100),c,'test');self.assertEqual(r['progress']['SUPPLY']['units'],0)
        c=cells();fact(c,'SUPPLY','2025-02-01',120)
        r=project_values(dict(planned_units=100),c,'test');self.assertIsNone(r['progress']['SUPPLY']['units'])
        self.assertTrue(any(x['code']=='SCOPE_CONFLICT' for x in r['remaining']))
    def test_only_explicit_unavailable_decision_allows_policy_estimate(self):
        c=cells();r=project_values(dict(planned_units=100),c,'test',dict(period_end='2030-12-31'));self.assertFalse(r['targets'])
        c['MOVE_IN']['assessment']=dict(status='COLLECTION_UNAVAILABLE')
        r=project_values(dict(planned_units=100),c,'test',dict(period_end='2030-12-31'))
        self.assertTrue(r['targets']['MOVE_IN']['inferred']);self.assertEqual(r['progress'],{})

    def test_completed_targets_do_not_create_future_measurements(self):
        from backend.officer_completion import complete_values
        c=cells();c['MOVE_IN']['targets']=[dict(date='2099-01',units=100,milestone='MOVE_IN')]
        p=dict(planned_units=100);r=complete_values(p,c,project_values(p,c,'test'),'test',1095)
        self.assertEqual(len(r['targets']),6)
        self.assertFalse(r['progress'])
        self.assertTrue(all(t['units']==100 and t['due_date'] for t in r['targets'].values()))
    def test_goal_grid_conserves_totals_and_preserves_known_values(self):
        from backend.officer_completion import complete_goal_grid
        values=dict(target_units=100,period_start='2026-01-01',period_end='2027-12-31',**{'region:서울특별시':30,'annual:전체:2026':40,'annual:서울특별시:2026':10})
        overrides={};complete_goal_grid(values,overrides,'test',{'서울특별시':1,'경기도':3,'인천광역시':1})
        self.assertEqual(values['region:서울특별시'],30)
        self.assertEqual(values['annual:전체:2026'],40)
        for y in (2026,2027):self.assertEqual(sum(values[f'annual:{r}:{y}'] for r in ('서울특별시','경기도','인천광역시')),values[f'annual:전체:{y}'])
