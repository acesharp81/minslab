import csv
import io
import unittest
from datetime import date

from backend.supply_dashboard import build_dashboard, quantities
from backend.supply_export import supply_csv
from test_supply_dashboard import project


class ProgressTests(unittest.TestCase):
    def test_missing_actual_is_unknown_and_reference_month_is_not_overdue(self):
        row=project(rows=[{'units':40,'supply_month':'2026-09'}, {'units':60,'supply_month':'2026-10'}])
        p=quantities([row],{},date(2026,10,3),3,'SUPPLY')['progress']
        self.assertIsNone(p['observed_pct'])
        self.assertIsNone(p['actual_delivery_pct'])
        self.assertEqual(p['year_to_date_goal_units'],40)
        self.assertEqual(p['verification_count'],1)
        self.assertEqual(p['late_count'],0)

    def test_notice_proves_supply_delay_only_and_not_move_in(self):
        row={**project(rows=[{'units':100,'supply_month':'2026-04','move_in_month':'2026-05'}]),'date_precision':'DAY'}
        links={'P':{'units':90,'source_date':'2026-07-01'}}
        p=quantities([row],{},date(2026,10,3),3,'SUPPLY',notice_links=links)['progress']
        self.assertEqual(p['observed_units'],90)
        self.assertEqual(p['observed_pct'],90)
        self.assertEqual(p['late_projects'],['P'])
        self.assertEqual(p['max_lag_months'],3)
        self.assertEqual(p['verification_count'],0)
        move=quantities([row],{},date(2026,10,3),3,'MOVE_IN',notice_links=links)['progress']
        self.assertIsNone(move['observed_units'])
        self.assertEqual(move['late_count'],0)
        self.assertEqual(move['verification_count'],1)

    def test_early_notice_compares_future_plan_without_requiring_overdue(self):
        row={**project(rows=[{'units':100,'supply_month':'2026-12'}]),'date_precision':'DAY'}
        p=quantities([row],{},date(2026,10,3),3,'SUPPLY',notice_links={'P':{'units':90,'source_date':'2026-09-01'}})['progress']
        self.assertEqual(p['early_count'],1)
        self.assertEqual(p['max_lead_months'],3)
        self.assertEqual(p['on_time_count'],0)
        self.assertEqual(p['late_count'],0)

    def test_same_month_notice_is_on_time_but_year_precision_is_unverified(self):
        row={**project(rows=[{'units':100,'supply_month':'2026-04'}]),'date_precision':'DAY'}
        links={'P':{'units':90,'source_date':'2026-04-20'}}
        p=quantities([row],{},date(2026,10,3),3,'SUPPLY',notice_links=links)['progress']
        self.assertEqual(p['on_time_count'],1)
        row['date_precision']='YEAR'
        p=quantities([row],{},date(2026,10,3),3,'SUPPLY',notice_links=links)['progress']
        self.assertEqual(p['on_time_count'],0)
        self.assertEqual(p['verification_count'],1)

    def test_revised_or_multitranche_plan_cannot_claim_early_or_on_time(self):
        for extra in ({'base_date':'2026-06-01'}, {'rows':[{'units':50,'supply_month':'2026-04'},{'units':50,'supply_month':'2026-05'}]}):
            row={**project(rows=[{'units':100,'supply_month':'2026-04'}]),'date_precision':'DAY',**extra}
            p=quantities([row],{},date(2026,10,3),3,'SUPPLY',notice_links={'P':{'units':90,'source_date':'2026-04-01'}})['progress']
            self.assertEqual(p['early_count'],0)
            self.assertEqual(p['on_time_count'],0)
            self.assertEqual(p['verification_count'],1)

    def test_later_revised_plan_cannot_prove_notice_delay(self):
        row={**project(rows=[{'units':100,'supply_month':'2025-04'}]),'base_date':'2026-01-01'}
        p=quantities([row],{},date(2026,10,3),3,'SUPPLY',notice_links={'P':{'units':90,'source_date':'2025-07-01'}})['progress']
        self.assertEqual(p['late_count'],0)

    def test_year_precision_plan_creates_delay_candidate_not_confirmed_delay(self):
        row=project(rows=[{'units':100,'supply_month':'2026-04'}])
        p=quantities([row],{},date(2026,10,3),3,'SUPPLY',notice_links={'P':{'units':90,'source_date':'2026-07-01'}})['progress']
        self.assertEqual(p['late_count'],0)
        self.assertEqual(p['schedule_gap_project_ids'],['P'])
        self.assertEqual(p['max_gap_months'],3)

    def test_duplicate_excluded_inventory_never_inflates_ratio(self):
        row=project()
        duplicate={**project('C'),'source_id':'lh_construction','district':'고양창릉','block':'A1','planned_units':110}
        p=quantities([row,duplicate],{},date(2026,10,3),3,'SUPPLY',notice_links={'P':{'units':90,'source_date':'2026-07-01'}})['progress']
        self.assertEqual(p['capacity_projects'],1)
        self.assertEqual(p['observed_pct'],90)

    def test_notice_cannot_prove_delay_for_multiple_supply_tranches(self):
        row=project(rows=[{'units':40,'supply_month':'2026-04'},{'units':60,'supply_month':'2026-05'}])
        p=quantities([row],{},date(2026,10,3),3,'SUPPLY',notice_links={'P':{'units':90,'source_date':'2026-07-01'}})['progress']
        self.assertEqual(p['late_count'],0)
        self.assertEqual(p['verification_count'],1)

    def test_year_only_manual_goal_is_not_prorated_into_year_to_date(self):
        p=quantities([project()],{'P':{'targets':[{'year':2026,'stage':'SUPPLY','units':70}]}},date(2026,10,3),3,'SUPPLY')['progress']
        self.assertIsNone(p['year_to_date_goal_units'])
        self.assertEqual(p['annual_manual_goal_units'],70)

    def test_block_aggregation_is_conserved_and_uses_representative_geometry(self):
        row=project(rows=[{'units':100,'supply_month':'2027-01'}])
        contract={**project('C'),'source_id':'lh_construction','district':'고양창릉','block':'A1','planned_units':110}
        other={**project('D'),'name':'고양창릉 A2'}
        district={'name':'고양창릉 공공주택지구','project_ids':['P','C','D'],'latitude':37.5,'longitude':127.1}
        data=build_dashboard([row,contract,other],[],[district],[],[],[],[],date(2026,10,3),2018,horizon=3,measure='SUPPLY')
        self.assertEqual(len(data['blocks']),2)
        self.assertEqual(sum(b['target_units'] for b in data['blocks']),data['summary']['target_units'])
        self.assertEqual(data['blocks'][0]['coordinate_basis'],'DISTRICT_REPRESENTATIVE')
        self.assertEqual(data['blocks'][0]['latitude'],district['latitude'])
        self.assertEqual(data['blocks'][0]['future'][0]['source_units'],100)
        self.assertEqual(data['blocks'][0]['target_excluded_projects'],1)

    def test_short_dashboard_horizon_still_supplies_five_year_chart_evidence(self):
        row=project(rows=[{'units':100,'supply_month':'2030-01'}])
        data=build_dashboard([row],[],[],[],[],[],[],date(2026,10,3),2018,horizon=1,measure='SUPPLY')
        self.assertEqual(data['horizon'],1)
        self.assertEqual(len(data['summary']['future']),1)
        year=next(item for item in data['items'][0]['annual'] if item['year']==2030)
        self.assertEqual(year['events'][0]['units'],100)

    def test_csv_has_utf8_bom_preserves_unknowns_and_does_not_add_manual(self):
        row=project(rows=[{'units':100,'supply_month':'2027-01'}])
        goals=[{'project_id':'P','base_date':'2026-01-01','targets':[{'year':2027,'stage':'SUPPLY','units':60,'basis':'관리자'}]}]
        data=build_dashboard([row],[],[],[],goals,[],[],date(2026,10,3),2018,horizon=3,measure='SUPPLY')
        encoded=supply_csv(data,'region','경기도')
        self.assertTrue(encoded.startswith('\ufeff'))
        rows=list(csv.DictReader(io.StringIO(encoded.lstrip('\ufeff'))))
        self.assertEqual(len(rows),6) # region + its block, three horizons each
        self.assertEqual(rows[0]['source_units'],'100')
        self.assertEqual(rows[0]['manual_units'],'60')
        self.assertEqual(rows[0]['actual_delivery_pct'],'')
        self.assertEqual(rows[0]['observed_pct'],'')
        self.assertEqual(rows[-1]['coordinate_basis'],'UNLOCATED')

    def test_csv_escapes_spreadsheet_formulas(self):
        row={**project(),'program':'=danger()'}
        data=build_dashboard([row],[],[],[],[],[],[],date(2026,10,3),2018,horizon=1)
        rows=list(csv.DictReader(io.StringIO(supply_csv(data,'program').lstrip('\ufeff'))))
        self.assertEqual(rows[0]['name'],"'=danger()")

    def test_selected_program_export_excludes_other_source_evidence(self):
        row=project(evidence_url='https://apply.lh.or.kr/plan')
        contract={**project('C'),'source_id':'lh_construction','program':'공사','district':'고양창릉','block':'A1',
                  'evidence_url':'https://www.lh.or.kr/contract'}
        data=build_dashboard([row,contract],[],[],[],[],[],[],date(2026,10,3),2018,horizon=1)
        rows=list(csv.DictReader(io.StringIO(supply_csv(data,'program','3기 신도시').lstrip('\ufeff'))))
        block=next(row for row in rows if row['group_type']=='block')
        self.assertEqual(block['project_ids'],'P')
        self.assertEqual(block['project_count'],'1')
        self.assertEqual(block['evidence_urls'],'https://apply.lh.or.kr/plan')

    def test_annual_manual_goal_uses_its_own_deduplicated_cohort(self):
        contract={**project('C'),'source_id':'lh_construction','district':'고양창릉','block':'A1'}
        plans={'C':{'targets':[{'year':2026,'stage':'SUPPLY','units':80}]}}
        p=quantities([project(),contract],plans,date(2026,10,3),3,'SUPPLY')['progress']
        self.assertEqual(p['annual_manual_goal_units'],80)
