import unittest
from backend.age_distribution import parse,place,context

class AgeTests(unittest.TestCase):
    def rows(self):
        result=[]
        regions=[('11','서울특별시',25),('28','인천광역시',11),('41','경기도',31)]
        from backend.area_stats import GYEONGGI
        for prefix,name,n in regions:
            codes=[(prefix,name,n)]
            names=sorted(GYEONGGI) if prefix=='41' else [f'가상{i}구' for i in range(n)]
            codes.extend((prefix+f'{i+1:03}',names[i],1) for i in range(n))
            for code,label,scale in codes:
                for age in ['0',*[str(i) for i in range(5,106,5)]]:
                    result.append(dict(C1=code,C1_NM=label,C2=age,ITM_ID='T2',PRD_DE='202609',UNIT_NM='명',DT=str(21*scale if age=='0' else scale)))
        return result
    def test_age_bands_conserve_population_and_all_regions(self):
        result=parse(self.rows(),'202609');self.assertEqual(len(result),70)
        row=result[('서울특별시',None)];self.assertEqual(sum(row['bands'].values()),row['total'])
        self.assertEqual(row['bands']['65+'],25*8)
    def test_duplicate_missing_class_wrong_period_and_sum(self):
        rows=self.rows()
        with self.assertRaisesRegex(ValueError,'중복'):parse(rows+rows[:1],'202609')
        with self.assertRaisesRegex(ValueError,'누락'):parse(rows[1:],'202609')
        with self.assertRaisesRegex(ValueError,'기준월'):parse(rows,'202608')
        rows[0]['DT']='1'
        with self.assertRaisesRegex(ValueError,'합계'):parse(rows,'202609')
    def test_foreign_region_and_city_wards_are_not_combined(self):
        self.assertIsNone(place(dict(C1='41111',C1_NM='장안구')))
        self.assertIsNone(place(dict(C1='26',C1_NM='부산광역시')))
    def test_unmapped_old_region_uses_explicit_province_reference(self):
        class Service:
            def rows(self,kind):return [dict(metric_group='kosis_age',region='인천광역시',municipality=None,year=2026,period='2026-09',population_total=0,age_bands={k:0 for k in ('0-14','15-34','35-64','65+')},evidence_url='https://kosis.kr/',definition='주민등록')]
        d=context(Service(),'인천광역시','구행정구역',2026);self.assertTrue(d['fallback']);self.assertTrue(all(r['percent'] is None for r in d['current']['bands']))
        self.assertIsNone(context(Service(),'인천광역시',None,2025)['current'])

    def test_sex_age_population_conservation(self):
        from backend.age_distribution import parse_sexes
        rows=self.rows()
        sexes=[dict(r,ITM_ID=sex) for r in rows for sex in ('T3','T4')]
        totals=[dict(r,DT=str(int(r['DT'])*2)) for r in rows]
        result=parse_sexes(totals+sexes,'202609')
        v=result[('서울특별시',None)]
        self.assertEqual(v['sex_age_classes']['male']['0']+v['sex_age_classes']['female']['0'],v['total'])
        with self.assertRaises(ValueError):parse_sexes(totals+sexes[:-1],'202609')
        with self.assertRaisesRegex(ValueError,'남녀'):parse_sexes(rows+sexes,'202609')
