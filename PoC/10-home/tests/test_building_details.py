"""The Housing HUB detail rows keep native identity and do not create supply facts."""
import json
import unittest
from unittest.mock import patch

from backend.building_details import collect_building_details, next_detail_dongs, parse_detail_rows
from backend.sources import SOURCES

SOURCE = next(source for source in SOURCES if source['id'] == 'building_hub_details')


def response(rows, total):
    return {'response': {'header': {'resultCode': '00'}, 'body': {
        'totalCount': total, 'items': {'item': rows}}}}


class BuildingDetailTests(unittest.TestCase):
    def test_dong_breakdown_is_evidence_without_completed_units(self):
        row = {'platPlc': '서울특별시 강남구 개포동 1', 'sigunguCd': '11680',
               'bjdongCd': '10300', 'mgmHsrgstPk': 120, 'mgmDongOulnPk': 340,
               'dongNm': '101동', 'hhldCntPubRentTot': 42, 'hhldCntCvlLotou': 8,
               'grndFlrCnt': 18, 'crtnDay': '20260901'}
        records, total = parse_detail_rows(response([row], 1), SOURCE, 'permit_dong',
            '서울특별시', '11680', '10300')
        self.assertEqual(total, 1)
        self.assertEqual(records[0][1], '120:340')
        payload = records[0][2]
        self.assertEqual(payload['parent_permit_native_id'], '120')
        self.assertEqual(payload['household_breakdown']['hhldCntPubRentTot'], 42)
        self.assertIsNone(payload['units'])
        self.assertEqual(payload['policy_mapping_status'], 'UNMAPPED')

    def test_missing_parcel_lot_is_preserved_for_review(self):
        row = {'platPlc': '경기도 수원시 영통구 이의동', 'sigunguCd': '41117',
               'bjdongCd': '10300', 'mgmHsrgstPk': '50', 'reprYn': '1',
               'bun': None, 'ji': None, 'crtnDay': '20220909'}
        records, _ = parse_detail_rows(response([row], 1), SOURCE, 'permit_parcel',
            '경기도', '41117', '10300')
        self.assertIn('PARCEL_LOT_MISSING', records[0][2]['warnings'])
        self.assertIsNone(records[0][2]['units'])
        self.assertEqual(records[0][2]['parent_permit_native_id'], '50')

    def test_expansion_resumes_after_complete_pilot_dong(self):
        class Service:
            def rows(self, kind):
                return [
                    {'source_object_id': '1168010300', 'address': '서울특별시 강남구 개포동'},
                    {'source_object_id': '4111710300', 'address': '경기도 수원시 영통구 이의동'},
                    {'source_object_id': '1174010200', 'address': '서울특별시 강동구 고덕동'}]
            def latest_collection_stats(self, source_id):
                return {'endpoint_coverage': [
                    {'legal_dong_code': '1168010300', 'endpoint': endpoint,
                     'expected': 1, 'fetched': 1, 'complete_query': True}
                    for endpoint in ('getHpDongOulnInfo', 'getHpPlatPlcInfo')]}
            def projects(self):
                return [{'address': '서울특별시 강동구 고덕동 1'}]
        selected, completed, total = next_detail_dongs(Service())
        self.assertEqual(total, 3)
        self.assertEqual(selected, ('1174010200', '4111710300'))
        self.assertTrue(completed['1168010300']['complete_query'])

    def test_identical_source_duplicates_keep_query_complete(self):
        class Fetcher:
            def get(self, url, suffix, params):
                common = dict(platPlc='서울특별시 강남구 개포동 1', sigunguCd='11680',
                              bjdongCd='10300', mgmHsrgstPk='120')
                if url.endswith('getHpDongOulnInfo'):
                    return json.dumps(response([dict(common, mgmDongOulnPk='340')], 1)).encode()
                row = dict(common, bun='0001', ji='0000', crtnDay='20260901')
                return json.dumps(response([dict(row, rnum=1), dict(row, rnum=2)], 2)).encode()
        with patch('backend.building_details.next_detail_dongs',
                   return_value=(('1168010300',), {}, 3)), \
             patch('backend.building_details.key_for', return_value='fixture'):
            records, stats = collect_building_details(SOURCE, Fetcher(), service=object())
        self.assertEqual(len(records), 2)
        self.assertEqual(stats['fetched'], 3)
        self.assertEqual(stats['duplicate_rows'], 1)
        self.assertEqual(stats['scope_completed_dongs'], 1)
        self.assertEqual(stats['endpoint_coverage'][1]['unique_records'], 1)

    def test_same_source_key_with_changed_content_fails(self):
        class Fetcher:
            def get(self, url, suffix, params):
                common = dict(platPlc='서울특별시 강남구 개포동 1', sigunguCd='11680',
                              bjdongCd='10300', mgmHsrgstPk='120')
                if url.endswith('getHpDongOulnInfo'):
                    return json.dumps(response([dict(common, mgmDongOulnPk='340')], 1)).encode()
                row = dict(common, bun='0001', ji='0000', crtnDay='20260901')
                return json.dumps(response([row, dict(row, platPlc='서울특별시 강남구 개포동 2')], 2)).encode()
        with patch('backend.building_details.next_detail_dongs',
                   return_value=(('1168010300',), {}, 3)), \
             patch('backend.building_details.key_for', return_value='fixture'):
            with self.assertRaisesRegex(ValueError, '원천키 충돌'):
                collect_building_details(SOURCE, Fetcher(), service=object())

    def test_incomplete_second_page_blocks_the_batch(self):
        class Fetcher:
            def get(self, url, suffix, params):
                page = params['pageNo']
                rows = [dict(platPlc='서울특별시 강남구 개포동 1', sigunguCd='11680',
                    bjdongCd='10300', mgmHsrgstPk=str(n), mgmDongOulnPk=str(n))
                    for n in range(100)] if page == 1 else []
                return json.dumps(response(rows, 101)).encode()
        with patch('backend.building_details.pilot_dongs', return_value=('1168010300',)), \
             patch('backend.building_details.key_for', return_value='fixture'):
            with self.assertRaisesRegex(ValueError, '페이지 누락'):
                collect_building_details(SOURCE, Fetcher())


if __name__ == '__main__':
    unittest.main()

class NegativeFloorsTest(unittest.TestCase):
    def test_invalid_source_floor_does_not_drop_valid_permit_evidence(self):
        from backend.building_details import parse_detail_rows
        row=dict(sigunguCd='11110',bjdongCd='10100',platPlc='서울특별시 종로구 청운동',mgmHsrgstPk='p',mgmDongOulnPk='d',grndFlrCnt=-1,hhldCnt=12)
        data={'response':{'header':{'resultCode':'00'},'body':{'totalCount':1,'items':{'item':[row]}}}}
        records,_=parse_detail_rows(data,{'url':'https://www.data.go.kr/'},'permit_dong','서울특별시','11110','10100')
        value=records[0][2];self.assertIsNone(value['floors']);self.assertEqual(value['raw_floors'],-1)
        self.assertIn('FLOORS_INVALID',value['warnings']);self.assertEqual(value['household_breakdown']['hhldCnt'],12)
