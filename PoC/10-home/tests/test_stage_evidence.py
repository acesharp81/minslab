import unittest
from datetime import date
from backend.api_samples import today
from unittest.mock import patch
from sqlalchemy import create_engine,select
from sqlalchemy.pool import StaticPool
from backend.db import Base,Audit,Revision
from backend.service import HomeService
from backend.stage_evidence import propose,similarity,refresh,list_links,save_link,linked_events
from backend.policy_delivery import build_delivery
from backend.policy_delivery_comparison import _events
from backend.occupancy_monitor import build_occupancy_monitor
from tests.test_policy_delivery import FakeService

class StageEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.project=dict(id='p1',name='고양창릉 A1 아파트 건설공사',district='고양창릉',block='A1',region='경기도',
            source_id='lh_construction',planned_units=1000,start_actual_date='2026-03-01',base_date='2026-10-01',
            evidence_url='https://www.lh.or.kr/source',mapping={'policy_id':'POL_2025_0907'})
    def test_block_not_reused_across_districts(self):
        source=dict(self.project,id='r',name='고양창릉 A2',block='A2',sample_kind='permit')
        self.assertEqual(similarity(self.project,source)[0],0)
    def test_start_is_provisional_prerequisite_without_fake_permit_date(self):
        choices=propose(self.project,[],[])
        for stage in ('BUSINESS','APPROVAL'):
            self.assertIsNone(choices[stage][0]['event_date'])
            self.assertEqual(choices[stage][0]['observed_on'],'2026-03-01')
            self.assertEqual(choices[stage][0]['method'],'PREREQUISITE')
    def test_source_permit_date_preferred_no_use_approval_substitution(self):
        source=dict(self.project,id='r',sample_kind='permit',dates={'원천 허가일 (apprvDay)':'2024-08-01','사용검사 필드 useInsptDay':'2026-01-01'})
        pick=propose(self.project,[],[source])['APPROVAL'][0]
        self.assertEqual(pick['event_date'],'2024-08-01')
    def test_release_persists_auto_refresh_and_audit_conflict(self):
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(engine);s=HomeService(engine)
        with patch.object(s,'projects',return_value=[self.project]):
            refresh(s);row=list_links(s)['items'][0]
            self.assertEqual(row['status'],'REVIEW');self.assertEqual(len(linked_events(s,today())['p1']),2)
            result=save_link(s,'p1',row['stage'],row['revision_no'],'RELEASED',None,'잘못 연결되어 해제')
            self.assertEqual(result['status'],'RELEASED')
            self.assertTrue(save_link(s,'p1',row['stage'],row['revision_no'],'RELEASED',None,'중복 제출')['conflict'])
            refresh(s);self.assertEqual(list_links(s)['items'][0]['status'],'RELEASED')
            with s.sessions() as db:self.assertGreaterEqual(len(db.scalars(select(Audit)).all()),3)
    def test_earlier_permit_prerequisite_is_included_and_review_separated(self):
        cohorts=[dict(id='p',units=100,events=[dict(stage='APPROVAL',event_date='2024-01-01',units=100,review_status='REVIEW')])]
        points=_events(cohorts,'APPROVAL',date(2026,10,12),'2026-01-01')
        self.assertEqual(points[-1]['units'],100);self.assertEqual(points[-1]['review_units'],100);self.assertEqual(points[-1]['confirmed_units'],0)
    def test_portfolio_includes_prior_start_without_inflating_135m_ledger(self):
        model=build_delivery(FakeService(),date(2026,10,12))
        self.assertEqual(len(model['portfolio_cohorts']),2)
        self.assertEqual(model['map_reconciliation']['linked_units'],1500)
        self.assertEqual(model['map_reconciliation']['prior_start_units'],500)
        self.assertEqual(model['allocated_units'],1000)
        self.assertEqual(model['current']['total_units'],1350000)

class OccupancyMonitorTests(unittest.TestCase):
    def monitor(self,observations):
        plan={'occupancy_outlook':{'annual':[dict(year=2025,units=100,seoul_units=30),dict(year=2026,units=110,seoul_units=40)]}}
        return build_occupancy_monitor(plan,{'occupancy_observations':observations},date(2026,10,12))['scopes'][0]['annual']
    def test_missing_is_not_zero_or_delay(self):
        row=self.monitor([])[0];self.assertIsNone(row['actual_units']);self.assertIsNone(row['gap_units']);self.assertEqual(row['status'],'VERIFY')
    def test_verified_full_year_gap_becomes_delay(self):
        row=self.monitor([dict(year=2025,region='수도권',as_of_date='2026-01-01',units=80)])[0]
        self.assertEqual(row['gap_units'],20);self.assertEqual(row['status'],'DELAYED');self.assertEqual(row['actual_cumulative_units'],80)
    def test_partial_observation_never_becomes_annual_delay(self):
        row=self.monitor([dict(year=2025,region='수도권',as_of_date='2025-06-01',units=20)])[0]
        self.assertEqual(row['gap_units'],80);self.assertEqual(row['status'],'VERIFY');self.assertIsNone(row['actual_cumulative_units'])
if __name__=='__main__':unittest.main()

class OccupancyTargetTests(unittest.TestCase):
    def test_current_plan_dimensions_become_targets_without_changing_movein_events(self):
        from backend.occupancy_targets import occupancy_schedules
        from backend.roadmap import source_events
        p=dict(id='p',name='고양창릉 A1',district='고양창릉',block='A1',region='경기도',source_id='lh_rent',planned_units=100,
            base_date='2026-01-01',evidence_url='https://www.lh.or.kr/plan',rows=[dict(move_in_month='2028-01',units=40),dict(move_in_month='2028-01',units=60)])
        class S:
            def rows(self,*args):return []
        plans=occupancy_schedules(S(),[p],date(2026,10,12))['p']
        self.assertEqual(plans[0]['units'],100)
        self.assertEqual(plans[0]['due_date'],'2028-01-01')
        self.assertIsNone(next(e for e in source_events(p,date(2026,10,12)) if e['stage']=='MOVE_IN')['units'])
    def test_unknown_plan_with_known_supply_stays_visible_but_does_not_inflate_target(self):
        s=FakeService();s.project_rows[0]['planned_units']=None
        m=build_delivery(s,date(2026,10,12))
        row=next(c for c in m['portfolio_cohorts'] if c['id']=='new')
        self.assertEqual(row['units'],200);self.assertIsNone(row['planned_units'])
        self.assertEqual(m['map_reconciliation']['linked_units'],500)
        self.assertEqual(m['allocated_units'],0)
        self.assertEqual(m['current']['total_units'],1350000)

class PersistentLinkTests(unittest.TestCase):
    def test_repeat_refresh_reuses_db_and_does_not_rescore_existing_links(self):
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine);s=HomeService(engine)
        project=dict(id='p1',name='고양창릉 A1',district='고양창릉',block='A1',region='경기도',source_id='lh_construction',planned_units=1000,start_actual_date='2026-03-01',base_date='2026-10-01',evidence_url='https://www.lh.or.kr/source',mapping={'policy_id':'POL_2025_0907'})
        with patch.object(s,'projects',return_value=[project]):
            refresh(s);before=list_links(s)['items']
            with patch('backend.stage_evidence.propose',side_effect=AssertionError('existing links must not be rematched')):
                self.assertEqual(refresh(s)['preserved'],2)
                list_links(s);linked_events(s,date(2026,10,12))
            after=list_links(s)['items'];self.assertEqual([r['revision_no'] for r in before],[r['revision_no'] for r in after])
            alternative={k:[dict(before[0]['selected'],source_name='새 후보',score=1)] for k in ('BUSINESS','APPROVAL')}
            with patch('backend.stage_evidence.propose',return_value=alternative):refresh(s,refresh_candidates=True)
            new=list_links(s)['items']
            self.assertEqual([r['selected'] for r in before],[r['selected'] for r in new])
            self.assertEqual(new[0]['candidates'][0]['source_name'],'새 후보')
    def test_unmatched_unchanged_inputs_not_recomputed(self):
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine);s=HomeService(engine)
        p=dict(id='p',name='미확인 사업',region='서울특별시',source_id='other',base_date='2026-10-01',mapping={})
        with patch.object(s,'projects',return_value=[p]):
            refresh(s)
            with patch('backend.stage_evidence.propose',side_effect=AssertionError('unchanged evidence')):self.assertEqual(refresh(s)['preserved'],2)

class ApprovalScopeRepairTests(unittest.TestCase):
    def setUp(self):
        self.project=dict(id='juam-rent',name='과천주암(뉴스테이) C2',district='과천주암(뉴스테이)',block='C2',region='경기도',
            source_id='lh_rent',planned_units=344,base_date='2026-01-01',evidence_url='https://www.lh.or.kr/source',mapping={'policy_id':'POL_2025_0907'})
        self.permit=dict(id='permit1',name='과천주암 C-2BL',sample_kind='permit',region='경기도',source_id='building_hub',revision_no=1,
            units=1030,base_date='2026-10-10',dates={'원천 허가일 (apprvDay)':'2020-12-29'},evidence_url='https://www.data.go.kr/data/15136560/openapi.do')
    def test_qualifier_normalization_and_approval_parent_scope(self):
        choice=propose(self.project,[],[self.permit])['APPROVAL'][0]
        self.assertEqual(choice['event_date'],'2020-12-29');self.assertEqual(choice['units'],344)
        self.assertEqual(choice['source_units'],1030);self.assertEqual(choice['relation_type'],'PART_OF_APPROVAL')
        self.assertFalse(choice['scope_partial']);self.assertEqual(choice['score'],1)
        self.assertEqual(similarity(self.project,dict(self.permit,name='과천주암지구 C-1BL'))[0],0)
    def test_dangling_parenthesis_and_partial_approval_do_not_cover_whole(self):
        p=dict(self.project,district='과천주암(뉴스테이) (',planned_units=1030)
        choice=propose(p,[],[dict(self.permit,units=344)])['APPROVAL'][0]
        self.assertEqual(choice['units'],344);self.assertTrue(choice['scope_partial'])
        self.assertEqual(choice['relation_type'],'PARTIAL_APPROVAL')
    def test_official_approval_document_not_district_plan_or_undated_draft(self):
        doc=dict(self.permit,sample_kind='document_evidence',facts=[dict(stage='APPROVAL',kind='ACTUAL',date='2023-10-23',milestone='CHANGE_APPROVAL',basis='변경승인')])
        self.assertEqual(propose(self.project,[doc],[])['APPROVAL'][0]['method'],'OFFICIAL_DOCUMENT')
        doc['facts']=[dict(stage='APPROVAL',kind='DOCUMENT',date=None,basis='초안')]
        self.assertFalse(propose(self.project,[doc],[])['APPROVAL'])
    def test_inferred_unreviewed_link_upgraded_but_reviewed_choice_preserved(self):
        from backend.db import upsert_revision
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        self.addCleanup(engine.dispose);Base.metadata.create_all(engine);s=HomeService(engine)
        p=dict(self.project,source_id='lh_construction',planned_units=1030,start_actual_date='2024-12-31')
        with patch.object(s,'projects',return_value=[p]):
            refresh(s);r=next(r for r in list_links(s)['items'] if r['stage']=='APPROVAL')
            self.assertEqual(r['selected']['method'],'PREREQUISITE')
            with s.sessions.begin() as db:upsert_revision(db,'permit','building_hub','permit',self.permit,'test')
            result=refresh(s,refresh_candidates=True);self.assertEqual(result['inference_upgraded'],1)
            r=next(r for r in list_links(s)['items'] if r['stage']=='APPROVAL')
            self.assertEqual(r['status'],'REVIEW');self.assertEqual(r['selected']['event_date'],'2020-12-29')
            save_link(s,p['id'],'APPROVAL',r['revision_no'],'RELEASED',None,'담당자 범위 확인 후 해제')
            refresh(s,refresh_candidates=True)
            self.assertEqual(next(r for r in list_links(s)['items'] if r['stage']=='APPROVAL')['status'],'RELEASED')

    def test_equal_date_candidates_keep_stable_order(self):
        first=dict(self.permit,id='permit-a');second=dict(self.permit,id='permit-b')
        a=propose(self.project,[],[first,second])['APPROVAL']
        b=propose(self.project,[],[second,first])['APPROVAL']
        self.assertEqual([r['source_entity_id'] for r in a],[r['source_entity_id'] for r in b])

class InferenceActualTests(unittest.TestCase):
    def test_observed_prerequisite_remains_state_not_actual(self):
        class Service:
            def rows(self,*args):return [dict(project_id='p',status='REVIEW',stage='APPROVAL',selected=dict(observed_on='2026-06-01',event_date=None,method='PREREQUISITE',evidence_url='https://www.lh.or.kr/',units=463))]
        event=linked_events(Service(),date(2026,10,13))['p'][0]
        self.assertEqual(event['status'],'STATE');self.assertIsNone(event['source_event_date'])
