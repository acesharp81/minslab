import unittest
from datetime import date
from backend.unsold import parse,context

class Service:
    def __init__(self,rows):self.records=rows
    def rows(self,kind):return self.records

class UnsoldTests(unittest.TestCase):
    def payload(self,metric='TOTAL'):
        records=[]
        for region in ('서울','경기','인천'):
            for area,amount in [('계',10),('가상시',10)]:
                r={'date':'202608','구분':region,'시군구':area,'미분양현황':amount,'호':amount,'부문':'계','규모':'계'};records.append(r)
        return dict(result_status={'status_code':'INFO-000'},result_data={'unitName':'호','formList':records})
    def test_totals_duplicates_and_zero(self):
        d=self.payload();rows=parse(d,dict(id='unsold_statistics'),'2082','128','TOTAL','미분양현황','202608');self.assertEqual(len(rows),6)
        d['result_data']['formList'][1]['미분양현황']=11
        with self.assertRaisesRegex(ValueError,'합계'):parse(d,dict(id='unsold_statistics'),'2082','128','TOTAL','미분양현황','202608')
        d=self.payload();d['result_data']['formList']+=d['result_data']['formList'][:1]
        with self.assertRaisesRegex(ValueError,'중복'):parse(d,dict(id='x'),'2082','128','TOTAL','미분양현황','202608')
    def rows(self):
        return [dict(region='경기도',municipality=None,period=p,metric=k,units=n,evidence_url='https://stat.molit.go.kr/',recorded_at='2026-10-13T00:00:00Z') for p,a,b in [('2026-05',10,1),('2026-06',10,2),('2026-07',10,3),('2026-08',10,4)] for k,n in [('TOTAL',a),('COMPLETED',b)]]
    def test_context_range_fallback_nested_inventory_and_trend(self):
        d=context(Service(self.rows()),'경기도','없는시',date(2026,10,13));self.assertTrue(d['fallback']);c=d['current']
        self.assertEqual(c['completed_share_pct'],40);self.assertEqual(c['pre_completion'],6);self.assertEqual(c['mom_completed_change'],1);self.assertEqual(c['three_month_completed_change'],3);self.assertIn('3개월 연속',c['signal']);self.assertIsNone(c['yoy_completed_change'])
        self.assertEqual(context(Service(self.rows()),'경기도',as_of=date(2026,6,30))['current']['period'],'2026-06')
    def test_zero_not_missing_and_missing_month_not_previous(self):
        rows=self.rows();rows=[r for r in rows if r['period'] not in ('2026-07',)]
        for r in rows:
            if r['period']=='2026-08':r['units']=0
        c=context(Service(rows),'경기도')['current'];self.assertEqual(c['total'],0);self.assertIsNone(c['completed_share_pct']);self.assertIsNone(c['mom_completed_change'])

    def test_latest_only_metadata_still_collects_thirteen_months(self):
        from backend.unsold import collect
        from unittest.mock import patch
        outer=self
        class Fetcher:
            def get(self,url,suffix,params):
                import json
                if url.endswith('period.do'):return json.dumps({'periodList':[{'MNG_DIV_VL':'202608'}]})
                d=outer.payload()
                for r in d['result_data']['formList']:
                    r['date']=params['start_dt']
                    r['호']=4
                return json.dumps(d)
        with patch('backend.unsold.today',return_value=date(2026,10,13)),patch('backend.unsold.key_for',return_value='test'):
            rows,stats=collect(dict(id='unsold_statistics',key_env='TEST_KEY'),Fetcher(),Service([]))
        self.assertEqual(len(stats['periods']),13)
        self.assertEqual(stats['periods'][0],'202508')
        self.assertEqual(len(set(r[2]['period'] for r in rows)),13)
