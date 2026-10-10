import json
import unittest
from unittest.mock import patch

from backend.sh_apis import collect_sh, parse_rows, scheduled_month, versions
from backend.sources import SOURCES

PLAN = next(s for s in SOURCES if s['id'] == 'sh_supply_plan')
PROJECT = next(s for s in SOURCES if s['id'] == 'sh_redevelopment')


def plan(**extra):
    return dict({'단지명': '마곡17', '사업유형': '토지임대부', '주택형': 59, '합계': 355,
                 '사전청약 공급세대수': 175, '본청약 공급세대수': 180,
                 '공급시기 예정 년도': 2026, '공급시기 예정월': 2}, **extra)


class SHTests(unittest.TestCase):
    def test_planned_units_are_not_added_to_subscription_subtotals(self):
        kind, _, row = parse_rows([plan()], PLAN, '2026-06-22', '2026-06-22')[0]
        self.assertEqual(kind, 'sh_plan')
        self.assertEqual(row['units'], 355)
        self.assertEqual(row['schedule_month'], '2026-02')
        self.assertEqual(row['source_date'], '2026-06-22')
        self.assertIn('SH_PLAN_NOT_ACTUAL', row['warnings'])
        self.assertIn('SH_SCHEDULE_NOT_ACTUAL', row['warnings'])
        self.assertEqual(row['policy_mapping_status'], 'UNMAPPED')

    def test_housing_types_and_historical_snapshots_have_distinct_identity(self):
        records = parse_rows([plan(), plan(**{'주택형': 84})], PLAN, '2026-06-22', '2026-06-22')
        self.assertNotEqual(records[0][1], records[1][1])
        historical = parse_rows([plan()], PLAN, '2023-07-08', '2026-06-22')[0]
        self.assertNotEqual(records[0][1], historical[1])
        self.assertIn('SH_HISTORY_SNAPSHOT', historical[2]['warnings'])

    def test_quantity_change_retains_identity(self):
        a = parse_rows([plan()], PLAN, '2026-06-22', '2026-06-22')[0]
        b = parse_rows([plan(**{'합계': 356, '본청약 공급세대수': 181})], PLAN, '2026-06-22', '2026-06-22')[0]
        self.assertEqual(a[1], b[1])

    def test_duplicate_and_sum_mismatch_fail(self):
        for rows in ([plan(), plan()], [plan(**{'합계': 99})]):
            with self.assertRaises(ValueError): parse_rows(rows, PLAN, '2026-06-22', '2026-06-22')

    def test_legacy_schema_preserves_snapshot_and_past_schedule(self):
        r = parse_rows([{'단지명': '1단지', '지구': '상계동', '계': 228, '분양예정시기': '2015-05'}], PLAN, '2019-08-26', '2026-06-22')[0][2]
        self.assertEqual(r['name'], '상계동 1단지')
        self.assertEqual(r['schedule_month'], '2015-05')
        self.assertEqual(r['source_date'], '2019-08-26')

    def test_redevelopment_rental_is_subset_and_missing_units_stay_unknown(self):
        row = {'구역명': '강북5', '구분': '공공재개발', '자치구': '강북구', '위치': '강북구 미아동 61',
               '전체 세대수': 688, '임대 세대수': 298, '추진현황': '정비계획 수립중'}
        r = parse_rows([row], PROJECT, '2023-11-02', '2023-11-02')[0][2]
        self.assertEqual(r['units'], 688)
        self.assertEqual(r['rental_units'], 298)
        self.assertIn('SH_OLD_STATUS', r['warnings'])
        self.assertEqual(r['source_stage'], '정비계획 수립중')
        row.update({'전체 세대수': None, '임대 세대수': None})
        self.assertIsNone(parse_rows([row], PROJECT, '2023-11-02', '2023-11-02')[0][2]['units'])

    def test_metadata_rejects_untrusted_host_and_other_dataset(self):
        for data in [{'host': 'evil.test', 'basePath': '/api', 'paths': {}},
                     {'host': 'api.odcloud.kr', 'basePath': '/api', 'paths': {'/other/v1/uddi:abc': {'get': {'summary': 'SH_20260622'}}}}]:
            with self.assertRaises(ValueError): versions(data, '15008820')

    def test_invalid_month_is_not_silently_used(self):
        with self.assertRaises(ValueError): scheduled_month(plan(**{'공급시기 예정월': 13}))

    def test_collection_checks_all_pages_and_keeps_key_out_of_metadata(self):
        calls = []
        class Fetch:
            def get(self, url, suffix, params):
                calls.append((url, params))
                if 'namespace' in params:
                    data = {'host': 'api.odcloud.kr', 'basePath': '/api', 'paths': {
                        '/15008820/v1/uddi:abc': {'get': {'summary': 'SH_20260622'}}}}
                else:
                    page = params['page']
                    rows = [plan(**{'단지명': str(i)}) for i in range((page - 1)*100, min(page*100,101))]
                    data = dict(page=page, perPage=100, totalCount=101, currentCount=len(rows), data=rows)
                return json.dumps(data).encode()
        with patch.dict('os.environ', {'POC10_SH_SERVICE_KEY': 'test-only-key'}):
            records, stats = collect_sh(PLAN, Fetch())
        self.assertEqual(len(records), 101)
        self.assertEqual(stats['dataset_versions'][0]['pages'], 2)
        self.assertNotIn('serviceKey', calls[0][1])
        self.assertNotIn('test-only-key', json.dumps(stats))
