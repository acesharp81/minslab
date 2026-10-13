import unittest
from datetime import date
from backend.map_stage_state import cohort_parts, aggregate
from backend.supply_dashboard import build_dashboard, block_key, inventory


def project(pid='P', **extra):
    return dict(dict(id=pid, source_id='lh_sale', name='양주회천 A26', district='양주회천',
                     block='A26', region='경기도', municipality='양주시', planned_units=100,
                     base_date='2026-01-01', stage='PLANNED_SUPPLY', program='공공주택', warnings=[],
                     mapping={'policy_id':'POL_2025_0907','status':'REVIEW'}), **extra)


class MapStageTests(unittest.TestCase):
    reference = date(2026, 10, 13)

    def distribution(self, events, row=None):
        row = row or project()
        parts = cohort_parts([row], [row], {}, {row['id']: events}, self.reference, block_key)
        return aggregate([row], parts)

    def test_partition_conservation_and_later_stages_count_toward_construction(self):
        d = self.distribution([dict(stage='APPROVAL', event_date='2025-01-01'),
                               dict(stage='CONSTRUCTION', event_date='2025-06-01'),
                               dict(stage='SUPPLY', units=70, event_date='2026-01-01'),
                               dict(stage='MOVE_IN', units=20, event_date='2026-03-01')])
        self.assertEqual(sum(d['parts'].values()), 100)
        self.assertEqual([d['parts'][s] for s in ('CONSTRUCTION','SUPPLY','MOVE_IN')], [30,50,20])
        self.assertEqual([d['cumulative'][s] for s in ('BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN')], [100,100,100,70,20])
        self.assertEqual(d['advanced_units'], 100)

    def test_supplied_project_is_fully_construction_attained_without_fabricating_dates(self):
        d=self.distribution([dict(stage='SUPPLY',event_date='2026-01-01')])
        self.assertEqual(d['cumulative']['CONSTRUCTION'],100)
        self.assertEqual(d['parts']['CONSTRUCTION'],0)

    def test_future_plans_and_inferences_do_not_advance_observed_slice(self):
        d=self.distribution([dict(stage='MOVE_IN',event_date='2027-01-01'),
                             dict(stage='CONSTRUCTION',event_date='2025-01-01',status='STATE')])
        self.assertEqual(d['parts']['UNKNOWN'],100)
        self.assertEqual(d['advanced_units'],0)

    def test_duplicate_notices_use_max_not_sum(self):
        d=self.distribution([dict(stage='SUPPLY',event_date='2026-01-01',units=70),
                             dict(stage='SUPPLY',event_date='2026-02-01',units=60)])
        self.assertEqual(d['parts']['SUPPLY'],70)
        self.assertEqual(d['parts']['UNKNOWN'],30)

    def test_missing_plan_recovers_unique_same_block_quantity_and_notice(self):
        sale=project(planned_units=None)
        construction=project('C',source_id='lh_construction',planned_units=792,start_actual_date='2025-01-01')
        notice=dict(id='N',name='양주회천 A26블록 공공분양주택',region='경기도',units=792,
                    developer='한국토지주택공사',source_date='2026-08-27')
        boundary=dict(id='YC',name='양주시',region='경기도',latitude=37.8,longitude=127.0)
        d=build_dashboard([sale,construction],[],[],[],[],[notice],[],self.reference,2018,municipalities=[boundary])
        for amount in (d['summary'],d['municipalities'][0],d['blocks'][0]):
            self.assertEqual(amount['target_units'],792)
            self.assertEqual(amount['stage_distribution']['cumulative']['SUPPLY'],792)
            self.assertEqual(amount['stage_distribution']['cumulative']['CONSTRUCTION'],792)
        self.assertIsNone(sale['planned_units'])

    def test_conflicting_peer_quantities_stay_missing(self):
        rows=[project(planned_units=None), project('A',source_id='lh_construction',planned_units=100),
              project('B',source_id='lh_progress',planned_units=200)]
        self.assertIsNone(inventory(rows)[0][0]['planned_units'])

    def test_policy_pool_does_not_count_as_implementation(self):
        d=self.distribution([], project(source_id='policy_907'))
        self.assertEqual(d['parts']['POLICY'],100)
        self.assertEqual(d['advanced_units'],0)

    def test_unknown_capacity_does_not_turn_into_zero(self):
        d=self.distribution([], project(planned_units=None))
        self.assertIsNone(d['total_units'])
        self.assertEqual(d['missing_quantity_projects'],1)
