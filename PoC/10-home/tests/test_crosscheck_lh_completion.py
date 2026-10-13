"""Cross-source identity evidence remains a review proposal, including conflicts."""
import unittest

from scripts.crosscheck_lh_completion import crosscheck


class CrosscheckTests(unittest.TestCase):
    def test_grouped_contract_and_unit_conflict_do_not_approve_any_match(self):
        projects = [
            {'id': 'P1', 'source_id': 'lh_progress', 'data': {
                'name': 'A-1', 'region': '경기도', 'district': '부천 대장', 'block': 'A-1', 'planned_units': 300}},
            {'id': 'P2', 'source_id': 'lh_construction', 'data': {
                'name': 'A-1 및 A-2 공사', 'region': '경기도', 'district': '부천대장', 'block': 'A1', 'planned_units': 500}},
            {'id': 'P3', 'source_id': 'lh_progress', 'data': {
                'name': 'S1', 'region': '서울특별시', 'district': '서울 검증', 'block': 'S-1', 'planned_units': 120}},
        ]
        def forecast(entity, region, district, block, units):
            return {'entity_id': entity, 'payload': {'name': entity, 'region': region,
                'district': district, 'block': block, 'planned_units': units}}
        result = crosscheck(projects, [forecast('F1','경기도','부천대장','A1BL',300),
            forecast('F2','서울특별시','서울검증','S1',125),
            forecast('F3','경기도','미등록','A1',200)])
        self.assertEqual(result['ambiguous_candidate'], 1)
        self.assertEqual(result['unique_candidate'], 1)
        self.assertEqual(result['unmatched'], 1)
        self.assertEqual(result['unique_unit_different'], 1)
        self.assertEqual(result['approval_effect'], 'NONE')
        self.assertEqual(result['proposals'][0]['review_status'], 'REVIEW')
        self.assertEqual(result['proposals'][1]['unit_comparison'], 'DIFFERENT')


if __name__ == '__main__':
    unittest.main()
