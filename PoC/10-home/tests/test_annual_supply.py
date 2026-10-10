import csv
import io
import unittest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend.additional_apis import STAT_SERIES, parse_statistics
from backend.annual_supply import annual_supply, annual_supply_csv
from backend.db import Base, upsert_revision
from backend.service import HomeService
from backend.sources import SOURCES


class AnnualSupplyTests(unittest.TestCase):
    def test_sale_approval_uses_monthly_net_total_and_rejects_bad_components(self):
        source = next(s for s in SOURCES if s['id'] == 'molit_statistics')
        series = next(s for s in STAT_SERIES if s[3] == '분양승인')
        row = {'date':'201801','구분1':'수도권','구분2':'서울',
               '순계>합계':13,'순계>분양':8,'순계>임대':3,'순계>조합':2,'누계>합계':99}
        response = {'result_status':{'status_code':'INFO-000'},
                    'result_data':{'unitName':'호','cert_id':'secret','formList':[row,dict(row,구분2='소계')]}}
        records = parse_statistics(response,source,series,'201801','201801')
        self.assertEqual(len(records),1)
        self.assertEqual(records[0][2]['units'],13)
        self.assertEqual(records[0][2]['supply_approval_breakdown'],{'분양':8,'임대':3,'조합':2})
        self.assertNotIn('secret',str(records))
        bad=dict(row);bad['순계>조합']=3
        response['result_data']['formList']=[bad]
        with self.assertRaises(ValueError):parse_statistics(response,source,series,'201801','201801')

    def test_annual_totals_require_all_months_for_full_year_comparison(self):
        engine=create_engine('sqlite+pysqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(engine)
        service=HomeService(engine)
        with service.sessions.begin() as session:
            for year,months in [(2018,12),(2019,11)]:
                for month in range(1,months+1):
                    period=f'{year}{month:02d}'
                    for metric in ('분양승인','착공','준공'):
                        payload={'name':metric,'region':'서울특별시','statistic_metric':metric,
                                 'statistic_frequency':'MONTH','statistic_period':period,'units':10,
                                 'source_date':f'{year}-{month:02d}-28'}
                        if metric=='분양승인':payload['supply_approval_breakdown']={'분양':7,'임대':2,'조합':1}
                        upsert_revision(session,'statistic','molit_statistics',f'{metric}|{period}',payload,'batch')
                upsert_revision(session,'statistic','molit_statistics',f'인허가|{year}',
                                {'name':'인허가','region':'서울특별시','statistic_metric':'인허가',
                                 'statistic_frequency':'YEAR','statistic_period':str(year),'units':100,
                                 'source_date':f'{year}-12-31'},'batch')
        rows=annual_supply(service,'서울특별시',2019)['rows']
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['metrics']['준공']['units'],120)
        self.assertTrue(rows[0]['metrics']['준공']['complete'])
        self.assertEqual(rows[1]['metrics']['분양승인']['units'],110)
        self.assertEqual(rows[1]['metrics']['분양승인']['breakdown']['분양'],77)
        self.assertFalse(rows[1]['metrics']['분양승인']['complete'])
        self.assertIsNone(rows[1]['metrics']['준공']['change_yoy_units'])
        self.assertEqual(rows[1]['metrics']['인허가']['change_yoy_units'],0)
        exported=list(csv.DictReader(io.StringIO(annual_supply_csv({'rows':rows,'metrics':['준공'],'sources':{'준공':'https://stat.molit.go.kr'}}).lstrip('\ufeff'))))
        self.assertEqual(len(exported),2)
        self.assertEqual(exported[1]['complete'],'False')
        self.assertEqual(exported[1]['units'],'110')


if __name__ == '__main__':unittest.main()
