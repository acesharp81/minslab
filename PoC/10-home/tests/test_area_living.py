from unittest import TestCase
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from backend.db import Base,upsert_revision
from backend.service import HomeService
from backend.area_living import parse_migration,parse_housing,parse_pir,context,payload,fetch_table

class LivingTests(TestCase):
    def test_migration_excludes_intra_city_moves(self):
        rows=[dict(C1='11110',C1_NM='종로구',PRD_DE='202608',ITM_ID=k,DT=str(v)) for k,v in [('T10',140),('T20',120),('T25',20),('T30',50)]]
        r=parse_migration(rows)[0]
        self.assertEqual((r['incoming'],r['outgoing'],r['net']),(90,70,20))
        rows[2]['DT']='21'
        with self.assertRaises(ValueError):parse_migration(rows)
    def test_monthly_period_strips_separator_and_crosses_year(self):
        import json
        class Fetch:
            def get(self,url,suffix,params):
                if params['method']=='getMeta':return json.dumps([dict(PRD_SE='월',END_PRD_DE='2026.08')])
                assert params['startPrdDe']=='202509' and params['endPrdDe']=='202608'
                return '[{"ok":1}]'
        with patch('backend.area_living.kosis_key',return_value='test-key'):
            self.assertEqual(fetch_table(Fetch(),'test',period='M',count=12),[{'ok':1}])
    def test_tenure_combines_monthly_rent_and_preserves_suppression(self):
        values={'T10':100,'T11':50,'T12':20,'T13':10,'T14':15,'T15':2,'T16':3}
        rows=[dict(C1='11010',C1_NM='종로구',C2='00',PRD_DE='2020',ITM_ID=k,DT=str(v)) for k,v in values.items()]
        r=parse_housing(rows,'tenure')[0];self.assertEqual(r['bins'][2]['value'],25)
        rows[4]['DT']='X';r=parse_housing(rows,'tenure')[0];self.assertIsNone(r['bins'][2]['value']);self.assertIsNone(r['bins'][2]['pct']);self.assertEqual(r['total'],100)
    def test_housing_other_uses_total_residual_without_zero_filling_components(self):
        values={'00':'100','101':'10','102':'40','103':'10','104':'20','201':'15','105':'X','202':'2','203':'X','204':'X','205':'1'}
        rows=[dict(C1='11010',C1_NM='종로구',C2=k,PRD_DE='2025',ITM_ID='T210',DT=v) for k,v in values.items()]
        r=parse_housing(rows,'housing_type')[0]
        self.assertEqual([b['value'] for b in r['bins']],[40,10,15,30,5])
        self.assertEqual(r['bins'][-1]['pct'],5)
        rows[2]['DT']='X';r=parse_housing(rows,'housing_type')[0]
        self.assertIsNone(r['bins'][0]['value']);self.assertIsNone(r['bins'][-1]['value'])
    def test_pir_uses_year_columns_and_separate_regional_series(self):
        html='<table id="t_Table_F018801"><thead><tr><th item-id="2023Y">2023</th><th item-id="2024Y">2024</th></tr></thead><tbody><tr><th>전체</th><td>6.3</td><td>6.3</td></tr><tr><th>수도권</th><td>8.5</td><td>8.7</td></tr></tbody></table>'
        rows=parse_pir(html);self.assertEqual(rows[-1]['capital'],8.7);self.assertEqual(rows[-1]['national'],6.3);self.assertEqual(rows[-1]['year'],2024)
        with self.assertRaises(ValueError):parse_pir(html.replace('<td>8.7</td>',''))
    def test_context_prefers_city_then_province_then_national_without_future(self):
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine);s=HomeService(engine)
        with s.sessions.begin() as db:
            for i,(group,region,city,year) in enumerate([('income','전국',None,'2025'),('duration','서울특별시',None,'2024'),('tenure','서울특별시',None,'2025'),('tenure','서울특별시','종로구','2020'),('income','전국',None,'2027')]):
                upsert_revision(db,'living_stat','kosis_living',str(i),payload(group,region,city,year,'test'),'test')
        result=context(s,'서울특별시','종로구',2026)
        self.assertEqual(result['income']['year'],2025);self.assertTrue(result['income']['fallback']);self.assertEqual(result['duration']['scope_label'],'서울특별시');self.assertEqual(result['tenure']['year'],2020);self.assertFalse(result['tenure']['fallback'])
