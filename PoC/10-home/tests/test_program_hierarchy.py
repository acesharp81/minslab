import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from backend.db import Audit, Base, Mapping, ProgramMapping, upsert_revision
from backend.service import HomeService


class ProgramHierarchyTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.tmp=tempfile.TemporaryDirectory()
        self.service=HomeService(self.engine,self.tmp.name)
        with self.service.sessions.begin() as session:
            for pid in ('POL_A','POL_B'):
                upsert_revision(session,'policy','policy_source',pid,dict(id=pid,name=pid,
                    announced_at='2025-01-01',base_date='2025-01-01',target_units=None,
                    evidence_url='https://www.korea.kr/'), 'batch')
            for key,name,programme,policy in (
                ('ONE','첫 사업','공공주택 건설','POL_A'),
                ('ONE_COPY','첫 사업 복제','공공주택 건설','POL_A'),
                ('TWO','둘째 사업','공공재개발','UNASSIGNED'),
                ('THREE','셋째 사업','3기 신도시','MON_THIRD_NEW_TOWN')):
                row,_=upsert_revision(session,'project','test',key,dict(name=name,region='경기도',
                    program=programme,planned_units=100,base_date='2026-01-01',date_precision='YEAR',
                    stage='PLANNING',stage_label='계획',warnings=[],proposed_policy=policy,
                    mapping_basis='원천 제안',evidence_url='https://www.korea.kr/'), 'batch')
                session.add(Mapping(project_id=row.entity_id,policy_id=policy,status='REVIEW',
                    basis='원천 제안',evidence_url='https://www.korea.kr/'))
        self.ids={row['name']:row['id'] for row in self.service.projects()}

    def tearDown(self):
        self.engine.dispose();self.tmp.cleanup()

    def test_legacy_backfill_preserves_review_and_exposes_unlinked(self):
        self.assertEqual(self.service.reconcile_program_links(),4)
        self.assertEqual(self.service.reconcile_program_links(),0)
        data=self.service.mappings()
        self.assertEqual(len(data['programs']),3)
        self.assertEqual(data['audit']['unlinked_policy_projects'],2)
        self.assertEqual(data['audit']['unlinked_projects'],0)
        self.assertEqual(data['audit']['unlinked_programs'],2)
        self.assertEqual(next(p for p in data['programs'] if p['name']=='3기 신도시')['policy_id'],'UNASSIGNED')
        self.assertEqual(next(p for p in data['programs'] if p['name']=='공공주택 건설')['status'],'REVIEW')
        self.assertEqual(len(next(p for p in self.service.policy_monitor()['items'] if p['id']=='UNASSIGNED')['project_ids']),2)
        self.assertEqual(len(self.service.projects(policy_id='MON_THIRD_NEW_TOWN')),1)

    def test_tentative_policy_backfill_is_idempotent_and_respects_staff_edits(self):
        self.service.reconcile_program_links()
        with self.service.sessions.begin() as session:
            for pid in ('POL_2025_0907', 'POL_2026_0813'):
                upsert_revision(session, 'policy', 'policy_source', pid, dict(id=pid, name=pid,
                    announced_at='2025-01-01', base_date='2025-01-01', target_units=None,
                    evidence_url='https://www.korea.kr/'), 'batch')
        self.assertEqual(self.service.propose_program_policies(), 2)
        self.assertEqual(self.service.propose_program_policies(), 0)
        data = self.service.mappings()
        self.assertEqual(data['audit']['unlinked_programs'], 0)
        self.assertEqual(data['audit']['unlinked_policy_projects'], 0)
        self.assertEqual(data['audit']['review_programs'], 3)
        self.assertEqual(data['audit']['review_projects'], 4)
        redevelopment = next(p for p in data['programs'] if p['name'] == '공공재개발')
        self.assertEqual(redevelopment['policy_id'], 'POL_2026_0813')
        self.assertEqual(redevelopment['status'], 'REVIEW')
        self.assertIn('자동 임시 제안', redevelopment['basis'])
        self.assertEqual(self.service.program_policy_history(redevelopment['id'])[0]['action'], 'PROGRAM_POLICY_AUTO')
        self.service.confirm_program_policy(redevelopment['id'], 'UNASSIGNED', 2, 'REVIEW',
            '담당자 보류', 'https://www.korea.kr/')
        self.assertEqual(self.service.propose_program_policies(), 0)
        self.assertEqual(next(p for p in self.service.program_links() if p['id'] == redevelopment['id'])['policy_id'], 'UNASSIGNED')

    def test_auto_policy_audit_can_be_reversed_for_historical_view(self):
        self.service.reconcile_program_links()
        with self.service.sessions.begin() as session:
            for pid in ('POL_2025_0907', 'POL_2026_0813'):
                upsert_revision(session, 'policy', 'policy_source', pid, dict(id=pid, name=pid,
                    announced_at='2025-01-01', base_date='2025-01-01', target_units=None,
                    evidence_url='https://www.korea.kr/'), 'batch')
        self.service.propose_program_policies()
        with self.service.sessions.begin() as session:
            for change in session.query(Audit).filter(Audit.action == 'PROGRAM_POLICY_AUTO'):
                change.recorded_at = datetime.now(timezone.utc) + timedelta(days=2)
        historical = self.service.mappings(as_of=date.today())
        self.assertEqual(historical['audit']['unlinked_programs'], 2)
        self.assertEqual(historical['audit']['unlinked_policy_projects'], 2)

    def test_two_reviews_move_project_without_direct_policy_edit(self):
        self.service.reconcile_program_links()
        data=self.service.mappings()
        redevelopment=next(p for p in data['programs'] if p['name']=='공공재개발')
        self.service.confirm_program_policy(redevelopment['id'],'POL_B',1,'REVIEW','공식 근거','https://www.korea.kr/')
        self.assertEqual(next(r for r in self.service.projects() if r['name']=='둘째 사업')['mapping']['policy_id'],'POL_B')
        self.service.confirm_program_policy(redevelopment['id'],'POL_B',2,'CONFIRMED','담당자 확인','https://www.korea.kr/')
        self.assertEqual(next(r for r in self.service.projects() if r['name']=='둘째 사업')['mapping']['policy_status'],'CONFIRMED')
        one=self.ids['첫 사업']
        self.service.confirm_project_program(one,redevelopment['id'],1,'REVIEW','사업 확인','https://www.korea.kr/')
        moved=next(r for r in self.service.projects() if r['id']==one)
        self.assertEqual((moved['program'],moved['mapping']['policy_id']),('공공재개발','POL_B'))
        self.assertEqual(len(next(p for p in self.service.policy_monitor()['items'] if p['id']=='POL_B')['project_ids']),2)
        with self.assertRaises(ValueError):
            self.service.confirm_mapping(one,'POL_A',2,'CONFIRMED','직접 변경','https://www.korea.kr/')
        self.assertEqual(self.service.confirm_project_program(one,redevelopment['id'],2,'CONFIRMED','담당자 확인','https://www.korea.kr/')['revision_no'],3)
        self.assertTrue(self.service.confirm_project_program(one,redevelopment['id'],2,'REVIEW','동시 수정','https://www.korea.kr/')['conflict'])

    def test_unassign_and_release_policy_link_keep_audit_visible(self):
        self.service.reconcile_program_links()
        one=self.ids['첫 사업']
        program=self.service.mappings()['items'][0]['mapping']['program_id']
        self.service.confirm_project_program(one,'UNASSIGNED',1,'REVIEW','프로그램 보류','https://www.korea.kr/')
        self.assertEqual(next(r for r in self.service.projects() if r['id']==one)['mapping']['policy_id'],'UNASSIGNED')
        self.assertEqual(self.service.mappings()['audit']['unlinked_projects'],1)
        self.assertEqual(len(self.service.mapping_history(one)),1)
        self.service.confirm_program_policy(program,'POL_A',1,'RELEASED','정책 연결 해제','https://www.korea.kr/')
        self.assertEqual(self.service.program_policy_history(program)[0]['after']['status'],'RELEASED')
