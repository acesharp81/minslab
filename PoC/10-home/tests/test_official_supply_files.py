"""Official file rows remain candidates or forecasts, never delivery facts."""
import unittest

from backend.official_supply_files import parse_lh_completion_plan, parse_renewal_inventory
from backend.sources import SOURCES

SOURCES_BY_ID = {source['id']: source for source in SOURCES}


class OfficialSupplyFileTests(unittest.TestCase):
    def test_renewal_inventory_preserves_unknown_and_non_applicable_units(self):
        content = (
            '시도,시군구,구역명칭,현 사업추진단계,사업유형,사업시행자,공급 예정 세대수\n'
            '서울특별시,성북구,장위 검증,7)착공,1)재개발(주택정비),조합,120\n'
            '경기도,수원시,다른 검증,2)정비구역지정,1)재개발(주택정비),,0\n'
            '서울특별시,중구,비주택 검증,5)사업시행인가,도시환경정비,,해당없음\n'
            '부산광역시,중구,범위외,7)착공,1)재개발(주택정비),조합,500\n'
        ).encode('utf-8-sig')
        records, stats = parse_renewal_inventory(content, SOURCES_BY_ID['molit_renewal_inventory'], '2026-05-18')
        self.assertEqual(len(records), 3)
        self.assertEqual(stats['file_rows'], 4)
        self.assertEqual(stats['unverified_zero_rows'], 1)
        self.assertEqual(stats['not_applicable_rows'], 1)
        self.assertFalse(stats['complete_population'])
        self.assertEqual(records[0][2]['planned_units'], 120)
        self.assertEqual(records[0][2]['legal_effect'], 'REFERENCE_ONLY')
        self.assertEqual(records[1][2]['value_status'], 'UNVERIFIED')
        self.assertIsNone(records[1][2]['planned_units'])
        self.assertEqual(records[2][2]['value_status'], 'NOT_APPLICABLE')
        self.assertTrue(all(kind == 'renewal_inventory' for kind, _, _ in records))

    def test_lh_completion_file_is_planned_not_actual_and_zero_is_unknown(self):
        content = (
            '사업지구명,블록명,위치,공급유형,세대수,준공예정일\n'
            '고양검증,A4,경기도 고양시 덕양구,공공분양,400,2028-08-31\n'
            '서울검증,S1,서울특별시 강동구,공공임대,0,\n'
            '인천검증,B2,인천광역시 중구,공공분양,200,2027-01-01\n'
        ).encode('cp949')
        records, stats = parse_lh_completion_plan(content, SOURCES_BY_ID['lh_completion_plan'], '2026-01-27')
        self.assertEqual(len(records), 2)
        self.assertEqual(stats['file_rows'], 3)
        self.assertEqual(stats['unknown_units_rows'], 1)
        self.assertFalse(stats['complete_population'])
        self.assertEqual(records[0][2]['completion_plan_date'], '2028-08-31')
        self.assertEqual(records[0][2]['stage_label'], '준공 예정')
        self.assertEqual(records[1][2]['value_status'], 'UNVERIFIED')
        self.assertEqual(records[1][2]['schedule_status'], 'DATE_UNKNOWN')
        self.assertIsNone(records[1][2]['units'])
        self.assertTrue(all(kind == 'lh_completion_plan' for kind, _, _ in records))

    def test_duplicate_natural_key_blocks_ambiguous_file(self):
        content = (
            '사업지구명,블록명,위치,공급유형,세대수,준공예정일\n'
            '고양검증,A4,경기도 고양시,공공분양,400,2028-08-31\n'
            '고양검증,A4,경기도 고양시,공공분양,500,2029-08-31\n'
        ).encode('utf-8')
        with self.assertRaisesRegex(ValueError, '중복'):
            parse_lh_completion_plan(content, SOURCES_BY_ID['lh_completion_plan'], '2026-01-27')


if __name__ == '__main__':
    unittest.main()
