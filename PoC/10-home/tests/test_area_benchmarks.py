import unittest
from backend.area_benchmarks import national_age,national_household,national_workers,context

class BenchmarkTests(unittest.TestCase):
    def ages(self):
        return [dict(C1='00',C1_NM='전국',C2=age,ITM_ID=item,PRD_DE='202609',UNIT_NM='명',DT=str(scale*(21 if age=='0' else 1))) for item,scale in [('T2',3),('T3',1),('T4',2)] for age in ['0',*[str(i) for i in range(5,106,5)]]]
    def test_age_population_and_sex_totals(self):
        rows=self.ages();value=national_age(rows,'202609')
        self.assertEqual(value['total'],63);self.assertEqual(value['sex_age_classes']['male']['5'],1)
        for invalid in [rows[:-1],rows+rows[:1],[dict(r,PRD_DE='202608') for r in rows],[dict(r,C1='11') for r in rows]]:
            with self.assertRaises(ValueError):national_age(invalid,'202609')
        rows[0]['DT']='64'
        with self.assertRaisesRegex(ValueError,'합계'):national_age(rows,'202609')
    def test_households_complete_group_and_sum(self):
        from backend.area_stats import HOUSEHOLD_SIZE_ITEMS
        rows=[dict(C1='00',C1_NM='전국',C2='00',PRD_DE='2025',ITM_ID=k,DT='7' if v=='total' else '1') for k,v in HOUSEHOLD_SIZE_ITEMS.items()]
        value=national_household(rows,2025);self.assertEqual(value['sizes']['5+'],3);self.assertEqual(value['total'],7)
        with self.assertRaises(ValueError):national_household(rows[:-1],2025)
        with self.assertRaises(ValueError):national_household(rows,2024)
    def test_nationwide_workers_verify_province_coverage_and_total(self):
        rows=[dict(adm_cd=str(11+i),tot_worker=10,all_worker_cnt=170) for i in range(17)]
        self.assertEqual(national_workers(rows),170);self.assertIsNone(national_workers([]))
        with self.assertRaises(ValueError):national_workers(rows[:-1])
        with self.assertRaises(ValueError):national_workers(rows+[rows[0]])
        rows[0]['tot_worker']=11
        with self.assertRaisesRegex(ValueError,'총계'):national_workers(rows)
    def test_context_never_substitutes_another_year(self):
        class S:
            def rows(self,kind):return [dict(metric_group='age',period='2026-09'),dict(metric_group='household',year=2025),dict(metric_group='industry',year=2024)]
        result=context(S(),{'current':{'period':'2026-08'}},[{'year':2024}],[{'year':2024}])
        self.assertIsNone(result['age']);self.assertIsNone(result['household']);self.assertEqual(result['industry']['year'],2024)
