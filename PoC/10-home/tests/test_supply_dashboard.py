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
from backend.supply_geography import municipal_membership


def project(id="P", **extra):
    return dict(id=id,source_id="lh_rent",name="고양창릉 A-01",region="경기도",program="3기 신도시",
        planned_units=100,base_date="2026-01-01",stage="PLANNED_SUPPLY",stage_label="공급계획",date_precision="YEAR",
        warnings=[],mapping={"policy_id":"POL","status":"REVIEW"},**extra)


class SupplyTests(unittest.TestCase):
    def test_repeated_group_members_compute_once_without_sharing_mutable_output(self):
        from unittest.mock import patch
        from collections import Counter
        rows=[dict(project('P1'),program='하나'),dict(project('P2'),name='고양창릉 A2',program='둘')]
        calls=[]
        def counted(members,*args,**kwargs):
            calls.append(tuple(r['id'] for r in members));return quantities(members,*args,**kwargs)
        with patch('backend.supply_dashboard.quantities',side_effect=counted):
            data=build_dashboard(rows,[],[],[],[],[],[],date(2026,10,20),2018)
        self.assertEqual(Counter(calls)[('P1','P2')],1)
        regional=next(r for r in data['groups']['region'] if r['id']=='경기도')
        self.assertEqual(data['summary']['target_units'],regional['target_units'])
        data['summary']['chart_target_ids'].append('mutated')
        self.assertNotIn('mutated',regional['chart_target_ids'])
    def test_bupyeong_letter_block_counts_supply_and_progress_once(self):
        rent = dict(project('RENT'), source_id='lh_incheon_rent',
                    name='인천부평(도시재생뉴딜) A', region='인천광역시',
                    municipality='부평구', planned_units=350, tenure='행복주택')
        progress = dict(rent, id='PROGRESS', source_id='lh_progress',
                        name='인천부평 A', district='인천부평', block='A',
                        mapping={'policy_id':'UNASSIGNED', 'status':'REVIEW'})
        construction = dict(rent, id='BUILD', source_id='lh_incheon_construction',
                            name='인천부평 행복주택 및 도시재생뉴딜 혁신센터 건설공사',
                            district='인천부평(도시재생뉴딜)', block='A',
                            warnings=['MULTI_SITE_CONTRACT'])
        data = build_dashboard([rent, progress, construction], [], [], [], [], [], [],
                               date(2026, 10, 20), 2018)
        self.assertEqual(data['summary']['target_units'], 350)
        self.assertEqual(data['summary']['chart_target_ids'], ['RENT'])
        self.assertEqual({r['id'] for r in data['items']}, {'RENT', 'PROGRESS', 'BUILD'})
        self.assertEqual(len(data['blocks']), 1)
        self.assertEqual(data['blocks'][0]['target_units'], 350)
        self.assertEqual(set(data['blocks'][0]['project_ids']), {'RENT', 'PROGRESS', 'BUILD'})

    def test_letter_blocks_keep_different_regions_districts_and_tenures_separate(self):
        rent = dict(project('RENT'), name='인천부평(도시재생뉴딜) A',
                    region='인천광역시', tenure='국민임대', planned_units=200)
        permanent = dict(rent, id='PERMANENT', tenure='영구임대', planned_units=150)
        progress = dict(rent, id='PROGRESS', source_id='lh_progress',
                        district='인천부평', block='A', planned_units=350)
        selected, excluded = inventory([rent, permanent, progress])
        self.assertEqual({r['id'] for r in selected}, {'RENT', 'PERMANENT'})
        self.assertEqual(sum(r['planned_units'] for r in selected), 350)
        self.assertEqual(excluded, ['PROGRESS'])
        for other in (dict(rent, region='경기도'), dict(rent, name='인천부평2 A'),
                      dict(rent, name='인천부평 B'), dict(rent, name='인천부평 A1')):
            self.assertNotEqual(block_key(rent), block_key(other))
        self.assertIsNone(block_key(dict(rent, block='B')))
        self.assertIsNone(block_key(dict(rent, name='인천부평 사업')))

    def test_letter_block_does_not_create_unreviewed_notice_link(self):
        row = dict(project(), name='인천부평(도시재생뉴딜) A', region='인천광역시')
        notice = dict(id='N', name='인천부평 A블록 공공임대주택', region='인천광역시',
                      units=100, developer='한국토지주택공사', source_date='2026-07-01')
        self.assertEqual(linked_notices([row], [notice], date(2026, 10, 20)), {})

    def test_colocated_bars_keep_each_source_quantity_without_changing_totals(self):
        rent = dict(project('RENT'), planned_units=438, name='성남금토 A2')
        construction = dict(rent, id='BUILD', source_id='lh_construction', planned_units=633)
        data = build_dashboard([rent, construction], [], [], [], [], [], [], date(2026, 10, 14), 2018)
        self.assertEqual({r['id']:r['map_quantities']['target_units'] for r in data['items']}, {'RENT':438, 'BUILD':633})
        self.assertEqual(data['summary']['target_units'], 438)
        self.assertEqual(data['blocks'][0]['target_units'], 438)

    def test_incheon_source_names_resolve_without_guessing_legacy_boundaries(self):
        boundaries=[dict(id='GY',name='계양구',region='인천광역시'),
                    dict(id='SH',name='서해구',region='인천광역시')]
        rows=[dict(project('A'),name='인천계양 A17',region='인천광역시',municipality='서울 (구 확인 필요)'),
              dict(project('B'),name='인천서구(석남어울림) 1',region='인천광역시')]
        self.assertEqual(municipal_membership(rows,boundaries,[],block_key),{'A':'GY'})

    def test_incheon_is_in_main_groups_and_uses_same_lh_inventory_rules(self):
        sale={**project('IC_SALE'), 'source_id':'lh_incheon_sale', 'name':'인천계양 A17',
              'district':'인천계양', 'block':'A17', 'region':'인천광역시', 'municipality':'계양구'}
        construction={**sale,'id':'IC_BUILD','source_id':'lh_incheon_construction'}
        boundary={'id':'IC_GY','name':'계양구','region':'인천광역시',
                  'longitude':126.73,'latitude':37.54,'district_names':['인천계양']}
        notice={'id':'IC_NOTICE','name':'인천계양 A17블록 공공분양주택',
                'region':'인천광역시','units':95,'developer':'한국토지주택공사','source_date':'2026-07-01'}
        data=build_dashboard([sale,construction],[],[],[],[],[notice],[],date(2026,10,12),2018,municipalities=[boundary])
        group=next(r for r in data['groups']['region'] if r['id']=='인천광역시')
        self.assertEqual(group['target_units'],100)
        self.assertEqual(group['current_notice_units'],95)
        self.assertEqual(data['municipalities'][0]['project_ids'],['IC_SALE','IC_BUILD'])
        filtered=build_dashboard([sale,construction],[],[],[],[],[],[],date(2026,10,12),2018,source_id='lh_incheon_sale')
        self.assertEqual([r['id'] for r in filtered['items']],['IC_SALE'])

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
        data=build_dashboard([row],[],[],[],[],[notice],[],date(2026,10,3),2018,horizon=3,measure='MOVE_IN')
        self.assertIsNone(data['summary']['future'][0]['source_units'])
        self.assertIsNone(data['summary']['future'][1]['source_units'])
        self.assertEqual(data['summary']['future'][1]['start_date'],'2028-05')
        self.assertEqual(data['items'][0]['move_in_start']['date'],'2028-05')
        event=data['items'][0]['annual'][2]['events'][0]
        self.assertIn('모집공고',event['basis'])
        self.assertFalse(event['actual_verified'])

    def test_older_notice_does_not_replace_newer_annual_move_in_plan(self):
        row=project(rows=[{'units':100,'move_in_month':'2027-03'}])
        notice={'id':'N','name':'고양창릉 A1블록 공공임대주택 본청약','region':'경기도','units':95,
                'developer':'한국토지주택공사','source_date':'2025-07-01','move_in_plan_month':'202805'}
        data=build_dashboard([row],[],[],[],[],[notice],[],date(2026,10,3),2018,horizon=3,measure='MOVE_IN')
        self.assertIsNone(data['summary']['future'][0]['source_units'])
        self.assertEqual(data['summary']['future'][0]['start_date'],'2027-03')
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
        self.assertEqual([r['source_units'] for r in q['future']],[None,None,None])
        self.assertEqual([r['start_date'] for r in q['future']],['2027-05','2027-05','2027-05'])
        self.assertEqual(q['projection']['future'][0]['status'],'DATE_ONLY')
        self.assertIsNone(q['current_units'])
        self.assertEqual(quantities([rent,contract],{},date(2026,10,2),3,"COMPLETION")['future'][0]['source_units'],110)
        self.assertEqual(quantities([rent,contract],{},date(2026,10,2),3,"SUPPLY")['future'][0]['source_units'],100)

    def test_unknown_and_manual_targets_are_separate_not_zero_or_added(self):
        row=project(rows=[{"units":None,"move_in_month":"2027-03"}])
        plans={'P':{'targets':[{'year':2027,'stage':'MOVE_IN','units':80}]}}
        q=quantities([row],plans,date(2026,10,2),2,"MOVE_IN")
        self.assertIsNone(q['future'][0]['source_units'])
        self.assertIsNone(q['future'][0]['manual_units'])
        self.assertEqual(q['future'][0]['start_date'],'2027-03')
        self.assertEqual(q['future'][0]['units_missing_events'],0)
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
        data=build_dashboard([a,b],[],[],[],[],[],[],date(2026,10,2),2018,2026,3,'MOVE_IN')
        self.assertEqual(sum(row['target_units'] or 0 for row in data['groups']['program']),data['summary']['target_units'])
        self.assertTrue(all(row['future'][0]['source_units'] is None for row in data['groups']['program']))
        self.assertEqual(data['summary']['future'][0]['start_date'],'2027-03')

    def test_notice_amendments_deduplicate_and_do_not_become_actual_supply(self):
        notices=[dict(id='1',house_manage_no='X',region='경기도',source_date='2025-01-01',units=100,move_in_plan_month='202703'),
                 dict(id='2',house_manage_no='X',region='경기도',source_date='2026-01-01',units=80,move_in_plan_month='202805'),
                 dict(id='3',house_manage_no='Y',region='서울특별시',source_date='2026-12-01',units=70,move_in_plan_month='202703')]
        q=market_notices(notices,date(2026,10,2),3,'경기도')
        self.assertEqual(q['notice_count'],1);self.assertEqual(q['announced_units'],80)
        self.assertIsNone(q['future_move_in'][0]['start_date'])
        self.assertEqual(q['future_move_in'][1]['start_date'],'2028-05')
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


def test_distinct_aa19_rental_cohorts_and_contract_share_one_located_block():
    first=dict(project('N'),name='인천검단 AA19',district='인천검단',block='AA19',region='인천광역시',tenure='국민임대',planned_units=991,latitude=37.6,longitude=126.7,coordinate_basis='APPROXIMATE_ADDRESS')
    second=dict(first,id='Y',tenure='영구임대',planned_units=332)
    contract=dict(first,id='C',name='인천검단 AA19BL 민간참여 공공주택건설사업',block='A13-1',source_id='lh_construction',tenure='유형 확인 필요',planned_units=1323)
    d=build_dashboard([first,second,contract],[],[],[],[],[],[],date(2026,10,14),2018)
    assert len(d['blocks'])==1
    assert d['blocks'][0]['target_units']==1323
    assert d['summary']['target_units']==1323
    assert set(d['blocks'][0]['project_ids'])=={'N','Y','C'}


def test_excluded_multisite_contract_keeps_own_visual_target_without_inflating_totals():
    row=dict(project('M'),source_id='lh_construction',warnings=['MULTI_SITE_CONTRACT'],latitude=37.5,longitude=127,coordinate_basis='APPROXIMATE_ADDRESS',planned_units=747)
    d=build_dashboard([row],[],[],[],[],[],[],date(2026,10,14),2018)
    assert d['summary']['target_units'] is None
    assert d['blocks'][0]['target_units']==747
    assert d['blocks'][0]['quantity_basis']=='PROJECT_REFERENCE'
    assert d['blocks'][0]['group_quantities']['region']['경기도']['target_units']==747
