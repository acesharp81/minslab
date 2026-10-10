import csv
import io
import unittest
from datetime import date

from backend.collectors import GYEONGGI_CITIES
from backend.municipality_geo import municipal_name,parse_boundaries
from backend.supply_dashboard import block_key,build_dashboard,quantities
from backend.supply_geography import block_milestones,municipal_membership
from backend.supply_export import supply_csv
from test_supply_dashboard import project

DAY=date(2026,10,3)


class ProjectionTests(unittest.TestCase):
    def test_future_stacks_on_current_once_and_year_two_does_not_repeat_year_one(self):
        a=project('A')
        b={**project('B',rows=[{'units':60,'supply_month':'2027-03'},{'units':40,'supply_month':'2028-03'}]),'name':'고양창릉 A2'}
        projection=quantities([a,b],{},DAY,3,'SUPPLY',notice_links={'A':{'units':40,'source_date':'2026-05-01'}})['projection']
        self.assertEqual([x['increment_units'] for x in projection['future']],[60,100,100])
        self.assertEqual([x['cumulative_units'] for x in projection['future']],[100,140,140])
        self.assertEqual([x['cumulative_pct'] for x in projection['future']],[50,70,70])

    def test_already_noticed_block_is_not_added_again_as_a_future_cohort(self):
        row=project(rows=[{'units':100,'supply_month':'2027-03'}])
        projection=quantities([row],{},DAY,3,'SUPPLY',notice_links={'P':{'units':80,'source_date':'2026-05-01'}})['projection']
        self.assertEqual(projection['baseline_units'],80)
        self.assertIsNone(projection['future'][0]['cumulative_units'])
        self.assertEqual(projection['future'][0]['excluded_reasons'],['NOTICE_COHORT_OVERLAP'])

    def test_missing_baseline_is_never_zero_and_notice_is_not_move_in(self):
        row=project(rows=[{'units':100,'supply_month':'2027-03','move_in_month':'2027-06'}])
        p=quantities([row],{},DAY,3,'SUPPLY')['projection']
        self.assertIsNone(p['baseline_units'])
        self.assertEqual(p['future'][0]['increment_units'],100)
        self.assertIsNone(p['future'][0]['cumulative_pct'])
        moved=quantities([row],{},DAY,3,'MOVE_IN',notice_links={'P':{'units':80,'source_date':'2026-05-01'}})['projection']
        self.assertIsNone(moved['baseline_units'])
        self.assertIsNone(moved['future'][0]['cumulative_pct'])

    def test_incompatible_capacity_excluded_and_manual_stays_separate(self):
        a=project('A')
        b={**project('B',rows=[{'units':110,'supply_month':'2027-03'}]),'name':'고양창릉 A2'}
        plan={'B':{'targets':[{'year':2027,'stage':'SUPPLY','units':80}]}}
        p=quantities([a,b],plan,DAY,3,'SUPPLY',notice_links={'A':{'units':50,'source_date':'2026-05-01'}})
        self.assertEqual(p['future'][0]['manual_units'],80)
        self.assertEqual(p['projection']['future'][0]['excluded_reasons'],['CAPACITY_CONFLICT'])
        self.assertIsNone(p['projection']['future'][0]['cumulative_units'])

    def test_csv_exports_stacked_projection_alongside_original_schedule(self):
        a=project('A')
        b={**project('B',rows=[{'units':100,'supply_month':'2027-03'}]),'name':'고양창릉 A2'}
        notice={'id':'N','name':'고양창릉 A1블록 공공임대 본 모집','region':'경기도','developer':'한국토지주택공사','units':80,'source_date':'2026-05-01'}
        data=build_dashboard([a,b],[],[],[],[],[notice],[],DAY,2018,horizon=3,measure='SUPPLY')
        rows=list(csv.DictReader(io.StringIO(supply_csv(data,'region','경기도').lstrip('\ufeff'))))
        self.assertEqual(rows[0]['source_units'],'100')
        self.assertEqual(rows[0]['projected_cumulative_units'],'180')
        self.assertEqual(rows[0]['projected_cumulative_pct'],'90.0')


class GeographyTests(unittest.TestCase):
    def test_city_subdistricts_normalize_and_seoul_boroughs_stay_distinct(self):
        self.assertEqual(municipal_name('경기도','수원시 권선구'),'수원시')
        self.assertEqual(municipal_name('경기도','군포시'),'군포시')
        self.assertEqual(municipal_name('경기도','양평군'),'양평군')
        self.assertEqual(municipal_name('서울특별시','강서구'),'강서구')
        self.assertIsNone(municipal_name('서울특별시','서울'))

    def test_full_boundary_scope_and_code_validation(self):
        boroughs='종로 중 용산 성동 광진 동대문 중랑 성북 강북 도봉 노원 은평 서대문 마포 양천 강서 구로 금천 영등포 동작 관악 서초 강남 송파 강동'.split()
        names=[('11',name+'구') for name in boroughs]+[('41',name+('군' if name in {'연천','가평','양평'} else '시')) for name in GYEONGGI_CITIES]
        features=[{'properties':{'sig_cd':prefix+f'{i:03}','sig_kor_nm':name},'geometry':{'type':'Polygon','coordinates':[]}} for i,(prefix,name) in enumerate(names)]
        data={'response':{'status':'OK','record':{'total':len(features)},'result':{'featureCollection':{'features':features}}}}
        self.assertEqual(len(parse_boundaries(data)),56)
        features.pop();data['response']['record']['total']=len(features)
        with self.assertRaises(ValueError):parse_boundaries(data)

    def test_membership_uses_explicit_source_then_same_block_not_name_prefix_guess(self):
        a={**project('A',municipality='고양'),'source_id':'lh_construction','block':'A1','district':'고양창릉'}
        b=project('B')
        c={**project('C'),'name':'고양창릉 A2','municipality':'지역 상세 확인 필요'}
        boundaries=[{'id':'G','name':'고양시','region':'경기도','district_names':[]}]
        assigned=municipal_membership([a,b,c],boundaries,[],block_key)
        self.assertEqual(assigned,{'A':'G','B':'G'})
        self.assertNotIn('C',assigned)

    def test_geography_and_group_totals_preserve_inventory_and_scope(self):
        a=project(municipality='고양')
        boundary={'id':'G','name':'고양시','region':'경기도','longitude':127,'latitude':37.5,'geometry':{},'district_names':[]}
        data=build_dashboard([a],[],[],[],[],[],[],DAY,2018,horizon=3,municipalities=[boundary])
        self.assertEqual(data['municipalities'][0]['target_units'],data['summary']['target_units'])
        self.assertEqual(data['municipality_unlinked_ids'],[])
        self.assertEqual(data['municipalities'][0]['group_quantities']['region']['경기도']['target_units'],100)

    def test_milestones_never_infer_approval_or_move_in_from_construction_and_notice(self):
        a={**project(),'source_id':'lh_construction','start_actual_date':'2026-03-01','progress_pct':40,'completion_plan_date':'2027-05-01'}
        phases=block_milestones([a],{'P':{'source_date':'2026-05-01','units':80}},DAY)
        self.assertEqual([p['status'] for p in phases],['UNKNOWN','OBSERVED','PLANNED','OBSERVED','UNKNOWN'])
        self.assertEqual(phases[1]['progress_pct'],40)
        self.assertIsNone(phases[2]['actual_date'])
