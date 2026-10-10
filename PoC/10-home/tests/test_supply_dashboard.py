import tempfile
import unittest
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend.app import create_app
from backend.db import Base, Mapping, upsert_revision
from backend.service import HomeService, today
from backend.supply_dashboard import block_key, build_dashboard, inventory, linked_notices, market_notices, quantities


def project(id="P", **extra):
    return dict(id=id,source_id="lh_rent",name="고양창릉 A-01",region="경기도",program="3기 신도시",
        planned_units=100,base_date="2026-01-01",stage="PLANNED_SUPPLY",stage_label="공급계획",date_precision="YEAR",
        warnings=[],mapping={"policy_id":"POL","status":"REVIEW"},**extra)


class SupplyTests(unittest.TestCase):
    def test_notice_links_require_provider_exact_district_block_and_tenure(self):
        row={**project(),'source_id':'lh_sale'}
        notice={'id':'N','name':'고양창릉지구 A-01블록 공공분양주택(본청약)','region':'경기도',
                'units':95,'developer':'한국토지주택공사 경기북부지역본부','source_date':'2026-07-01'}
        self.assertEqual(linked_notices([row],[notice],date(2026,10,3))['P']['units'],95)
        for change in ({'developer':'민간 주식회사'},{'name':'고양창릉2 A1블록 공공분양주택'},
                       {'name':'고양창릉 A10블록 공공분양주택'},{'region':'서울특별시'},{'units':101},
                       {'source_date':'2026-12-01'}):
            self.assertEqual(linked_notices([row],[dict(notice,**change)],date(2026,10,3)),{})
        self.assertEqual(linked_notices([project()],[notice],date(2026,10,3)),{})

    def test_preliminary_residual_and_multi_block_notices_do_not_count(self):
        row={**project(),'source_id':'lh_sale'}
        notice={'id':'N','name':'고양창릉 A1블록 공공분양주택','region':'경기도','units':95,
                'developer':'한국토지주택공사','source_date':'2026-07-01'}
        for suffix in (' 사전청약',' 잔여세대',' 추가입주자',' 무순위',' 및 A2블록'):
            self.assertEqual(linked_notices([row],[dict(notice,name=notice['name']+suffix)],date(2026,10,3)),{})
        self.assertEqual(linked_notices([row,dict(row,id='P2')],[notice],date(2026,10,3)),{})

    def test_latest_main_notice_is_review_quantity_and_earlier_year_is_bounded(self):
        row={**project(),'source_id':'lh_sale'}
        notice={'id':'N1','name':'고양창릉 A1블록 공공분양주택','region':'경기도','units':90,
                'developer':'한국토지주택공사','source_date':'2025-07-01','house_manage_no':'H1'}
        later=dict(notice,id='N2',source_date='2026-07-01',units=95)
        self.assertEqual(linked_notices([row],[notice,later],date(2025,12,31))['P']['units'],90)
        data=build_dashboard([row],[],[],[],[],[notice,later],[],date(2026,10,3),2018)
        self.assertEqual(data['summary']['current_notice_units'],95)
        self.assertEqual(data['summary']['current_notice_status'],'REVIEW')
        self.assertIsNone(data['summary']['current_units'])
        self.assertEqual(data['items'][0]['notice_evidence']['id'],'N2')
        for kind in ('policy','program','region'):
            # No policy definition in this fixture; it is intentionally not an
            # official policy aggregate despite a proposed mapping ID.
            if kind=='policy':continue
            self.assertEqual(sum(group['current_notice_units'] or 0 for group in data['groups'][kind]),95)

    def test_notice_move_in_plan_replaces_same_project_plan_without_double_count(self):
        row=project(rows=[{'units':100,'move_in_month':'2027-03'}])
        notice={'id':'N','name':'고양창릉 A1블록 공공임대주택 본청약','region':'경기도','units':95,
                'developer':'한국토지주택공사','source_date':'2026-07-01','move_in_plan_month':'202805'}
        data=build_dashboard([row],[],[],[],[],[notice],[],date(2026,10,3),2018,horizon=3)
        self.assertIsNone(data['summary']['future'][0]['source_units'])
        self.assertEqual(data['summary']['future'][1]['source_units'],95)
        event=data['items'][0]['annual'][2]['events'][0]
        self.assertIn('모집공고',event['basis'])
        self.assertFalse(event['actual_verified'])

    def test_older_notice_does_not_replace_newer_annual_move_in_plan(self):
        row=project(rows=[{'units':100,'move_in_month':'2027-03'}])
        notice={'id':'N','name':'고양창릉 A1블록 공공임대주택 본청약','region':'경기도','units':95,
                'developer':'한국토지주택공사','source_date':'2025-07-01','move_in_plan_month':'202805'}
        data=build_dashboard([row],[],[],[],[],[notice],[],date(2026,10,3),2018,horizon=3)
        self.assertEqual(data['summary']['future'][0]['source_units'],100)
        self.assertEqual(data['summary']['current_notice_units'],95)

    def test_supply_completion_and_move_in_are_not_combined(self):
        rent=project(rows=[{"units":60,"supply_month":"2026-11","move_in_month":"2027-05"},
                            {"units":40,"supply_month":"2027-02","move_in_month":"2028-05"}])
        contract={**project("C"),"source_id":"lh_construction","block":"A1","district":"고양창릉","planned_units":110,
                  "completion_plan_date":"2027-09-01"}
        self.assertEqual(block_key(rent),block_key(contract))
        q=quantities([rent,contract],{},date(2026,10,2),3,"MOVE_IN")
        self.assertEqual(q['target_units'],100)
        self.assertEqual(q['target_excluded_projects'],1)
        self.assertEqual([r['source_units'] for r in q['future']],[60,100,100])
        self.assertIsNone(q['current_units'])
        self.assertEqual(quantities([rent,contract],{},date(2026,10,2),3,"COMPLETION")['future'][0]['source_units'],110)
        self.assertEqual(quantities([rent,contract],{},date(2026,10,2),3,"SUPPLY")['future'][0]['source_units'],100)

    def test_unknown_and_manual_targets_are_separate_not_zero_or_added(self):
        row=project(rows=[{"units":None,"move_in_month":"2027-03"}])
        plans={'P':{'targets':[{'year':2027,'stage':'MOVE_IN','units':80}]}}
        q=quantities([row],plans,date(2026,10,2),2,"MOVE_IN")
        self.assertIsNone(q['future'][0]['source_units'])
        self.assertEqual(q['future'][0]['manual_units'],80)
        self.assertEqual(q['future'][0]['units_missing_events'],1)
        self.assertIsNone(quantities([project()],{},date(2026,10,2),2,"MOVE_IN")['future'][0]['source_units'])

    def test_ambiguous_plan_blocks_and_multisite_contracts_are_excluded(self):
        a=project('A');b={**project('B'), 'source_id':'lh_sale','planned_units':120}
        self.assertEqual(inventory([a,b]),([],['A','B']))
        c={**project('C'),'source_id':'lh_construction','warnings':['MULTI_SITE_CONTRACT']}
        self.assertEqual(inventory([c]),([],['C']))

    def test_old_report_uses_latest_source_date_without_later_policy_or_goals(self):
        row=project('P')
        reports=[]
        for stamp,pct in [('2025-01-01',10),('2025-11-01',40),('2026-03-01',70)]:
            reports.append({**row,'id':stamp,'report_date':stamp,'base_date':stamp,'source_object_id':'object',
                            'current_project_id':'P','district':'고양창릉','block':'A1','progress_pct':pct,
                            'stage':'CONSTRUCTION','source_id':'lh_history','completion_plan_date':'2027-05-01'})
        district={'name':'고양창릉 공공주택지구','project_ids':['P'],'latitude':37,'longitude':127}
        policies=[{'policy_id':'POL','name':'정책','announced_at':'2026-01-29','target_units':60000}]
        goals=[{'project_id':'P','base_date':'2026-10-02','targets':[{'year':2027,'stage':'MOVE_IN','units':300,'basis':'관리자'}]}]
        data=build_dashboard([row],reports,[district],policies,goals,[],[],date(2026,10,2),2018,2025,3,'COMPLETION')
        self.assertEqual(len(data['items']),1)
        self.assertEqual(data['items'][0]['progress_pct'],40)
        self.assertIsNone(data['items'][0]['mapping']['policy_id'])
        self.assertEqual(data['items'][0]['manual_count'],0)
        self.assertEqual(data['groups']['policy'][0]['id'],'UNMAPPED')
        self.assertEqual(data['districts'][0]['project_ids'],['P'])
        self.assertEqual(data['summary']['future'][1]['source_units'],100)

    def test_program_group_totals_equal_deduplicated_summary(self):
        a=project('A',rows=[{'units':100,'move_in_month':'2027-03'}])
        b={**project('B'),'source_id':'lh_construction','program':'공공주택 건설','district':'고양창릉','block':'A1','planned_units':110,
           'completion_plan_date':'2027-01-01'}
        data=build_dashboard([a,b],[],[],[],[],[],[],date(2026,10,2),2018,2026,3)
        self.assertEqual(sum(row['target_units'] or 0 for row in data['groups']['program']),data['summary']['target_units'])
        self.assertEqual(sum(row['future'][0]['source_units'] or 0 for row in data['groups']['program']),100)

    def test_notice_amendments_deduplicate_and_do_not_become_actual_supply(self):
        notices=[dict(id='1',house_manage_no='X',region='경기도',source_date='2025-01-01',units=100,move_in_plan_month='202703'),
                 dict(id='2',house_manage_no='X',region='경기도',source_date='2026-01-01',units=80,move_in_plan_month='202805'),
                 dict(id='3',house_manage_no='Y',region='서울특별시',source_date='2026-12-01',units=70,move_in_plan_month='202703')]
        q=market_notices(notices,date(2026,10,2),3,'경기도')
        self.assertEqual(q['notice_count'],1);self.assertEqual(q['announced_units'],80)
        self.assertIsNone(q['future_move_in'][0]['units'])
        self.assertEqual(q['future_move_in'][1]['units'],80)
        old=market_notices(notices,date(2025,12,31),3,'경기도')
        self.assertEqual(old['announced_units'],100)

    def test_early_year_displays_policy_evidence_without_backdated_projects(self):
        event={'event_date':'2018-12-19','name':'최초 발표'}
        data=build_dashboard([project()],[],[],[],[],[],[event],date(2026,10,2),2018,2018,3)
        self.assertEqual(data['items'],[])
        self.assertEqual(data['history']['events'],[event])
        self.assertIsNone(data['summary']['target_units'])
        self.assertIsNone(data['summary']['current_units'])


class SupplyAPITests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.directory=tempfile.TemporaryDirectory()
        self.service=HomeService(self.engine,self.directory.name)
        with self.service.sessions.begin() as session:
            row,_=upsert_revision(session,'project','lh_rent','P',{**project(),'base_date':'2018-01-01'},'test')
            session.add(Mapping(project_id=row.entity_id,policy_id='POL',status='REVIEW',basis='검토',evidence_url='https://apply.lh.or.kr/'))
        self.client=TestClient(create_app(self.engine,auto_collect=False))

    def tearDown(self):
        self.client.close();self.engine.dispose();self.directory.cleanup()

    def test_analysis_year_is_distinct_from_knowledge_cutoff(self):
        self.assertEqual(self.client.get('/poc/home/api/map/dashboard?analysis_year=2018').status_code,200)
        self.assertEqual(self.client.get('/poc/home/api/map/dashboard?as_of_date=2018-12-31').json()['items'],[])
        self.assertEqual(self.client.get('/poc/home/api/map/dashboard?analysis_year='+str(today().year+1)).status_code,422)
        self.assertEqual(self.client.get('/poc/home/api/map/dashboard?measure=INVALID').status_code,422)

    def test_supply_export_accepts_history_and_rejects_invalid_groups(self):
        response=self.client.get('/poc/home/api/map/supply.csv?analysis_year=2018&horizon=3&group_by=region&group_id=경기도')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.text.startswith('\ufeff'))
        self.assertIn('home-supply-2018.csv',response.headers['content-disposition'])
        self.assertIn('actual_delivery_pct',response.text)
        self.assertIn('2018,2018-12-31',response.text)
        self.assertEqual(self.client.get('/poc/home/api/map/supply.csv?group_by=region&group_id=UNKNOWN').status_code,422)
        self.assertEqual(self.client.get('/poc/home/api/map/supply.csv?measure=INVALID').status_code,422)
        self.assertEqual(self.client.get('/poc/home/api/map/supply.csv?analysis_year='+str(today().year+1)).status_code,422)
