import unittest

from backend.area_stats import parse_household_size_rows
from backend.area_outlook import build_outlook


class AreaOutlookTests(unittest.TestCase):
    def test_household_size_total_and_five_plus_are_verified(self):
        values={'T10':20,'T21':7,'T22':5,'T23':4,'T24':2,'T25':1,'T26':1,'T27':0}
        rows=[{'C1':'31010','C1_NM':'수원시','C2':'00','ITM_ID':key,'DT':str(value),'PRD_DE':'2025'}
              for key,value in values.items()]
        parsed=parse_household_size_rows(rows,2025)
        self.assertEqual(parsed[('경기도','수원시')]['sizes'],{'1':7,'2':5,'3':4,'4':2,'5+':2})
        rows[-1]['DT']='1'
        with self.assertRaises(ValueError):parse_household_size_rows(rows,2025)

    def test_future_gap_uses_observed_partial_completions_and_deduplicated_plans(self):
        area={'housing_balance':[{'year':2025,'housing_units':1000,'households':1100,'gap_units':-100}],
              'household_forecast':[{'year':2026,'households':1150,'published_at':'2024-12-02'},
                                    {'year':2027,'households':1200,'published_at':'2024-12-02'},
                                    {'year':2028,'households':1250,'published_at':'2024-12-02'}]}
        annual={'rows':[{'region':'경기도','year':2026,'metrics':{'준공':{'units':50,'complete':False,'periods':8,'expected_periods':12}}}]}
        projection={'future':[{'end_year':2027,'increment_units':100,'eligible_events':2,'excluded_events':1},
                              {'end_year':2028,'increment_units':None,'eligible_events':0,'excluded_events':2}]}
        result=build_outlook('경기도',area,annual,projection,2026)
        self.assertEqual(result['years'][0]['scenario_gap_units'],-100)
        self.assertEqual(result['years'][0]['coverage'],'PARTIAL_YEAR')
        self.assertEqual(result['years'][1]['scenario_housing_units'],1150)
        self.assertEqual(result['years'][1]['scenario_gap_units'],-50)
        self.assertIsNone(result['years'][2]['scenario_gap_units'])
        self.assertEqual(result['years'][2]['coverage'],'SCHEDULE_UNAVAILABLE')


if __name__=='__main__':unittest.main()
