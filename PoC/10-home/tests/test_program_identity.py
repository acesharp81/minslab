import unittest
from datetime import datetime,timezone,date
from unittest.mock import patch
from sqlalchemy import create_engine,select
from sqlalchemy.pool import StaticPool
from backend.db import Base,ProgramMapping,Mapping,Audit,upsert_revision
from backend.service import HomeService
from backend.program_hierarchy import program_id
from backend.program_identity import apply,resolve_in_session

class ProgramIdentityTests(unittest.TestCase):
    def setUp(self):
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine);self.s=HomeService(engine)
        self.a=program_id('같은 프로그램','UNASSIGNED');self.c=program_id('같은 프로그램','POL_2025_0907')
        self.pairs=patch('backend.program_identity.PAIRS',[(self.a,self.c)]);self.pairs.start();self.addCleanup(self.pairs.stop)
        with self.s.sessions.begin() as db:
            for pid,seed in ((self.a,'UNASSIGNED'),(self.c,'POL_2025_0907')):
                db.add(ProgramMapping(id=pid,name='같은 프로그램',seed_policy_id=seed,policy_id='POL_2025_0907',status='REVIEW',basis='수집 유형',evidence_url='https://example.org',revision_no=1,created_at=datetime(2026,10,12,tzinfo=timezone.utc)))
            db.add(Mapping(project_id='P',program_id=self.a,policy_id='UNASSIGNED',status='CONFIRMED',basis='기존 근거',evidence_url='https://example.org',revision_no=2))
    def test_merge_preserves_project_review_and_history_and_is_idempotent(self):
        preview=apply(self.s);self.assertEqual(preview['moved_projects'],1)
        with self.s.sessions() as db:self.assertEqual(db.scalar(select(Mapping)).program_id,self.a)
        result=apply(self.s,False);self.assertEqual(result['moved_projects'],1)
        with self.s.sessions() as db:
            m=db.scalar(select(Mapping));self.assertEqual(m.program_id,self.c);self.assertEqual(m.status,'CONFIRMED');self.assertIn('기존 근거',m.basis)
            self.assertEqual(db.get(ProgramMapping,self.a).status,'RELEASED');self.assertEqual(resolve_in_session(db,self.a),self.c)
        self.assertEqual([p['id'] for p in self.s.program_links(projects=[])],[self.c])
        self.assertEqual(len(self.s.program_links(date(2026,10,13),projects=[])),2)
        self.assertEqual(apply(self.s,False)['moved_projects'],0)
        with self.s.sessions() as db:self.assertEqual(len(db.scalars(select(Audit).where(Audit.action=='PROGRAM_PROJECT_MERGE')).all()),1)
    def test_future_source_attach_uses_saved_alias(self):
        apply(self.s,False)
        with self.s.sessions.begin() as db:
            m=Mapping(project_id='NEW',policy_id='UNASSIGNED',status='REVIEW',revision_no=1,basis='추가 원천',evidence_url='https://example.org');db.add(m)
            self.s._attach_program(db,m,dict(program='같은 프로그램'),{})
            self.assertEqual(m.program_id,self.c)
    def test_user_program_fields_block_automatic_merge(self):
        with self.s.sessions.begin() as db:upsert_revision(db,'program_profile','manual_program',self.a,dict(program_id=self.a,base_date='2026-10-14',overrides={'target_units':dict(value=100)}),'test')
        result=apply(self.s,False);self.assertEqual(result['merged'],[]);self.assertEqual(result['skipped'],[self.a])
