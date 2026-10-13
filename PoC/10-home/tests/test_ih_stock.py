import unittest
from unittest.mock import patch
from backend.ih_stock import parse_page, collect_ih_stock, RESIDENTIAL
from backend.api_samples import key_for


class IhStockTests(unittest.TestCase):
    source=dict(id='ih_supply',url='https://www.data.go.kr/data/15168460/openapi.do',
                key_env='POC10_IH_SERVICE_KEY',fallback_key_env='POC10_LH_NOTICE_SERVICE_KEY')

    def test_stock_is_not_new_supply_and_non_residential_units_are_excluded(self):
        house=dict(regionName='계양구',housName='주택',totalHouseholds=dict({k:0 for k in RESIDENTIAL},publicRental=100,commercialRental=10,substituteProcessing=3),
                   contractHouseholds=dict(publicRental=70),vacantHouseholds=dict(publicRental=30))
        data=dict(header=dict(resultCode='00'),body=dict(totalCount=1,houses=[house]))
        records,total=parse_page(data,self.source,'2026-09-30')
        self.assertEqual(total,1)
        kind,key,payload=records[0]
        self.assertEqual(kind,'agency_stock')
        self.assertEqual(payload['units'],100)
        self.assertEqual(payload['policy_mapping_status'],'REFERENCE_ONLY')
        self.assertIsNone(payload['source_date'])
        self.assertEqual(payload['raw_households']['totalHouseholds']['commercialRental'],10)
        house['totalHouseholds'].pop('safeHouse')
        partial,_=parse_page(data,self.source,'2026-09-30')
        self.assertIsNone(partial[0][2]['units'])
        self.assertEqual(partial[0][2]['stock_known_units'],100)
        self.assertEqual(partial[0][2]['stock_quantity_status'],'PARTIAL')

    def test_error_response_is_never_a_successful_empty_source(self):
        with self.assertRaisesRegex(ValueError,'0호 아님'):
            parse_page(dict(header=dict(resultCode='05'),body=dict(totalCount=0,houses=[])),self.source,'2026-09-30')
        with self.assertRaisesRegex(ValueError,'schema'):
            parse_page(dict(header=dict(resultCode='00'),body=dict(totalCount=0)),self.source,'2026-09-30')

    def test_successful_explicit_empty_list_can_be_zero_records(self):
        records,total=parse_page(dict(header=dict(resultCode='00'),body=dict(totalCount=0,houses=[])),self.source,'2026-09-30')
        self.assertEqual((records,total),([],0))

    def test_existing_home_portal_key_can_be_reused_without_disclosing_it(self):
        with patch.dict('os.environ',{'POC10_IH_SERVICE_KEY':'','POC10_LH_NOTICE_SERVICE_KEY':'test%2Bkey'}):
            self.assertEqual(key_for(self.source),'test+key')

    def test_failed_connection_requests_a_retry_not_a_zero_quantity(self):
        class FailedFetcher:
            def get(self,*args,**kwargs):raise RuntimeError('official timeout')
        with patch('backend.ih_stock.key_for',return_value='test'),self.assertRaisesRegex(ValueError,'데이터 존재 여부 미판정'):
            collect_ih_stock(self.source,FailedFetcher())


if __name__=='__main__':unittest.main()
