import json
import tempfile
import unittest
from unittest.mock import patch

import httpx
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend.area_stats import (area_context, collect_kosis_employment,
                                collect_kosis_household_forecast, kosis_geography, kosis_housing_place, sgis_geography)
from backend.collectors import Fetcher
from backend.db import Base, upsert_revision
from backend.service import HomeService


class AreaStatsTests(unittest.TestCase):
    def test_city_crosswalk_and_suppressed_metric(self):
        self.assertEqual(sgis_geography('경기도', '수원시 장안구'), '수원시')
        self.assertEqual(sgis_geography('경기도', '양평군'), '양평군')
        self.assertIsNone(sgis_geography('경기도', '다른시 동구'))
        self.assertEqual(kosis_geography({'C1':'1101','C1_NM':'서울 종로구'}), ('서울특별시','종로구'))
        self.assertEqual(kosis_geography({'C1':'3101','C1_NM':'수원시'}), ('경기도','수원시'))

    def test_adjusted_housing_uses_city_totals_not_ward_duplicates(self):
        self.assertEqual(kosis_housing_place({'C1':'31010','C1_NM':'수원시'}), ('경기도','수원시'))
        self.assertIsNone(kosis_housing_place({'C1':'31011','C1_NM':'수원시 장안구'}))
        self.assertEqual(kosis_housing_place({'C1':'31','C1_NM':'경기도'}), ('경기도',None))

    def test_housing_gap_requires_same_year_stock_and_households(self):
        engine=create_engine('sqlite+pysqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(engine)
        service=HomeService(engine)
        with service.sessions.begin() as session:
            for year,stock,households in [(2023,None,1000),(2024,920,1010)]:
                upsert_revision(session,'area_stat','kosis_housing',f'경기도|수원시|{year}',{
                    'name':'수원시','region':'경기도','municipality':'수원시','metric_group':'kosis_housing',
                    'year':year,'base_date':f'{year}-12-31','housing_units':stock,'households':households,
                    'official_ratio':None,'housing_source_table':'DT_1MH2090'},'batch')
        rows=area_context(service,'경기도','수원시',2026)['housing_balance']
        self.assertIsNone(rows[0]['gap_units'])
        self.assertEqual(rows[1]['gap_units'],-90)
        self.assertEqual(rows[1]['stock_to_household_pct'],91.1)

    def test_fetcher_removes_kosis_key_and_sgis_access_token(self):
        with tempfile.TemporaryDirectory() as raw:
            fetcher=Fetcher('area',raw)
            fetcher.client.close()
            fetcher.client=httpx.Client(transport=httpx.MockTransport(
                lambda request:httpx.Response(200,json={'echo':str(request.url)})))
            fetcher.get('https://kosis.kr/openapi/Param/statisticsParameterData.do','json',
                        params={'apiKey':'secret-key','format':'json'})
            fetcher.get('https://sgisapi.mods.go.kr/OpenAPI3/stats/population.json','json',
                        params={'accessToken':'secret-token','year':2024})
            fetcher.close()
            self.assertNotIn('secret-key',json.dumps(fetcher.manifest))
            self.assertNotIn('secret-token',json.dumps(fetcher.manifest))
            from pathlib import Path
            for path in Path(raw).rglob('*.json'):
                self.assertNotIn('secret-',path.read_text())

    def test_kosis_periods_and_forecast_are_separate(self):
        class FakeFetcher:
            def get(self,url,suffix,params):
                if params['tblId']=='DT_1BZ0505':
                    return json.dumps([{'C1':'11','C2':'000','PRD_DE':'2026','DT':'4000000','LST_CHN_DE':'2024-12-02'}]).encode()
                item=params['itmId'];value={'T3':'123.4','T7':'67.8','T2':'180.1'}[item]
                return json.dumps([{'C1':'3101','C1_NM':'수원시','PRD_DE':'202601','DT':value}]).encode()
        with patch('backend.area_stats.kosis_key',return_value='key'):
            employed,stats=collect_kosis_employment({'id':'kosis_employment'},FakeFetcher())
            forecast,_=collect_kosis_household_forecast({'id':'kosis_household_forecast'},FakeFetcher())
        self.assertEqual(employed[0][2]['resident_employed'],123400)
        self.assertEqual(employed[0][2]['employment_rate'],67.8)
        self.assertEqual(forecast[0][2]['forecast_households'],4000000)
        self.assertEqual(stats['region_city_count'],1)

    def test_region_uses_complete_coverage_and_city_sums_gu(self):
        engine=create_engine('sqlite+pysqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(engine)
        service=HomeService(engine)
        with service.sessions.begin() as session:
            for code,pop in [('31011',200),('31012',300)]:
                upsert_revision(session,'area_stat','sgis_area','2024|'+code,{
                    'name':'수원시','region':'경기도','municipality':'수원시','metric_group':'sgis_census',
                    'year':2024,'base_date':'2024-12-31','population':pop,'households':pop//2,
                    'workplace_workers':pop//4,'businesses':1,'industry_workers':{'C':pop//4},
                    'industry_labels':{'C':'제조업'}},'batch')
        city=area_context(service,'경기도','수원시',2026)
        region=area_context(service,'경기도',None,2026)
        self.assertEqual(city['census'][0]['population'],500)
        self.assertEqual(city['census'][0]['industry_workers']['C']['workers'],125)
        self.assertIsNone(region['census'][0]['population'])
        self.assertEqual(region['census'][0]['covered_units'],2)
