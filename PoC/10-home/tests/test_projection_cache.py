import json
import unittest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from backend.db import Base, Mapping, ProgramMapping, upsert_revision
from backend.service import HomeService
from backend.projection_cache import ProjectionCache, projection_version
from backend.projection_cache import collection_projection_version


class ProjectionCacheTests(unittest.TestCase):
    def test_score_and_snapshot_audits_keep_project_cache_but_officer_edits_invalidate(self):
        from backend.db import Audit
        engine=create_engine('sqlite://',poolclass=StaticPool)
        self.addCleanup(engine.dispose);Base.metadata.create_all(engine);service=HomeService(engine)
        cache=ProjectionCache(lambda:collection_projection_version(service))
        cache.get('project',lambda:{'units':8})
        for action in ('INDEPENDENT_SNAPSHOT','DATA_INTEGRITY_ROUND','DATA_INTEGRITY_ROUND_AMENDED','DATA_INTEGRITY_ROUND_REPLACED'):
            with service.sessions.begin() as db:
                db.add(Audit(entity_id='snapshot',action=action,before={},after={}))
            self.assertEqual(cache.get('project',lambda:self.fail(action+' rebuilt project'))[1],'HIT')
        with service.sessions.begin() as db:
            upsert_revision(db,'stage_evidence','officer','actual',{'units':16},'review')
        self.assertEqual(cache.get('project',lambda:{'units':16})[1],'MISS')
        with service.sessions.begin() as db:
            db.add(Audit(entity_id='project',action='OFFICER_START_CONFIRMED',before={},after={}))
        self.assertEqual(cache.get('project',lambda:{'units':16})[1],'MISS')

    def test_requirements_cache_ignores_raw_imports_and_sees_execution_changes(self):
        from backend.projection_cache import requirements_projection_version
        from backend.db import Audit, Batch, now
        engine=create_engine('sqlite://',poolclass=StaticPool)
        self.addCleanup(engine.dispose);Base.metadata.create_all(engine);service=HomeService(engine)
        initial=requirements_projection_version(service)
        with service.sessions.begin() as db:
            upsert_revision(db,'general_permit','building_general_permit','raw',{'units':20},'raw')
            db.add(Batch(source_id='building_general_permit',status='SUCCESS',finished_at=now()))
            db.add(Audit(entity_id='raw',action='START_CANDIDATE_FOUND',before={},after={}))
        self.assertEqual(initial,requirements_projection_version(service))
        for kind in ('execution_case','execution_scenario','execution_agency','project_profile','collection_assessment'):
            previous=requirements_projection_version(service)
            with service.sessions.begin() as db:upsert_revision(db,kind,'officer',kind,{'units':12},'review')
            self.assertNotEqual(previous,requirements_projection_version(service),kind)

    def test_large_cached_body_is_compact_but_returned_bytes_are_identical(self):
        data={'한국어 근거':['공식 근거와 계획·실제 구분 '*40]*500}
        cache=ProjectionCache(lambda:1)
        first,status=cache.get('large',lambda:data)
        second,status=cache.get('large',lambda:self.fail('rebuilt large cache'))
        self.assertEqual(status,'HIT');self.assertEqual(second,first)
        self.assertEqual(json.loads(second),data)
        self.assertLess(len(cache.entries['large'][2]),len(first)//10)

    def test_shared_cold_build_limit_keeps_hits_available_and_releases_after_failure(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import BoundedSemaphore,Event
        from unittest.mock import Mock
        gate=BoundedSemaphore(1);started=Event();release=Event();second_started=Event()
        one=ProjectionCache(lambda:1,build_guard=gate);two=ProjectionCache(lambda:1,build_guard=gate)
        two.get('ready',lambda:{'ok':True})
        def slow():
            started.set()
            if not release.wait(3):raise RuntimeError('timed out')
            raise ValueError('retryable')
        def later():second_started.set();return {'ok':'later'}
        with ThreadPoolExecutor(max_workers=3) as pool:
            first=pool.submit(one.get,'first',slow)
            self.assertTrue(started.wait(1))
            queued=pool.submit(two.get,'second',later)
            try:
                self.assertFalse(second_started.wait(.05))
                self.assertEqual(two.get('ready',lambda:self.fail('hit rebuilt'))[1],'HIT')
            finally:release.set()
            with self.assertRaises(ValueError):first.result(1)
            self.assertEqual(json.loads(queued.result(1)[0]),{'ok':'later'})

    def test_ai_analysis_does_not_rebuild_policy_but_officer_confirmation_does(self):
        from backend.db import Audit
        from backend.projection_cache import delivery_projection_version
        engine=create_engine('sqlite://',poolclass=StaticPool)
        self.addCleanup(engine.dispose);Base.metadata.create_all(engine);service=HomeService(engine)
        for version in (collection_projection_version, delivery_projection_version):
            before=version(service)
            with service.sessions.begin() as db:
                for action in ('AI_PUBLICATION_DISCOVERY','AI_PUBLICATION_ANALYSIS'):
                    db.add(Audit(entity_id='candidate',action=action,before={},after={'note':'review only'}))
                upsert_revision(db,'ai_publication_analysis','ai','candidate',{'result':'candidate'},'analysis')
            self.assertEqual(before,version(service))
            with service.sessions.begin() as db:
                db.add(Audit(entity_id='project',action='OFFICER_START_CONFIRMED',before={},after={}))
                upsert_revision(db,'evidence_bridge','officer','bridge',{'source_entity_id':'candidate'},'approval')
            self.assertNotEqual(before,version(service))

    def test_collection_version_ignores_raw_candidate_audit_but_sees_review(self):
        from backend.db import Audit
        engine=create_engine('sqlite://',poolclass=StaticPool)
        self.addCleanup(engine.dispose);Base.metadata.create_all(engine);service=HomeService(engine)
        before=collection_projection_version(service)
        with service.sessions.begin() as db:
            upsert_revision(db,'general_permit','building_general_permit','raw',{'units':8},'batch')
            db.add(Audit(entity_id='raw',action='START_CANDIDATE_FOUND',before={},after={}))
        self.assertEqual(before,collection_projection_version(service))
        with service.sessions.begin() as db:
            db.add(Audit(entity_id='p',action='OFFICER_START_CONFIRMED',before={},after={}))
        self.assertNotEqual(before,collection_projection_version(service))

    def test_workspace_retains_cache_during_candidate_ingestion_and_sees_officer_edits(self):
        from backend.projection_cache import workspace_projection_version
        from backend.db import Audit, Batch, now
        engine=create_engine('sqlite://',poolclass=StaticPool)
        self.addCleanup(engine.dispose);Base.metadata.create_all(engine);service=HomeService(engine)
        cache=ProjectionCache(lambda:workspace_projection_version(service))
        self.assertEqual(cache.get('picker',lambda:{'name':'원본'})[1],'MISS')
        with service.sessions.begin() as db:
            upsert_revision(db,'stage_evidence','stage_match','candidate',{'status':'REVIEW'},'batch')
            upsert_revision(db,'permit','building_hub','raw',{'units':8},'batch')
            db.add(Audit(entity_id='candidate',action='STAGE_CANDIDATES_UPDATED',before={},after={}))
            db.add(Batch(source_id='sh_inventory',status='SUCCESS',finished_at=now()))
        self.assertEqual(cache.get('picker',lambda:self.fail('background ingestion rebuilt picker'))[1],'HIT')
        with service.sessions.begin() as db:
            upsert_revision(db,'project_profile','manual_project','p',{'overrides':{'name':{'value':'수정'}}},'edit')
        body,status=cache.get('picker',lambda:{'name':'수정'})
        self.assertEqual(status,'MISS');self.assertEqual(json.loads(body)['name'],'수정')
        for kind in ('project','program_profile','program_alias','policy_profile'):
            before=workspace_projection_version(service)
            with service.sessions.begin() as db:upsert_revision(db,kind,'officer',kind,{'units':16},'edit')
            self.assertNotEqual(before,workspace_projection_version(service),kind)
        before=workspace_projection_version(service)
        with service.sessions.begin() as db:
            db.add(Mapping(project_id='p',policy_id='POL_A',status='CONFIRMED',revision_no=1,basis='검토',evidence_url='https://example.org'))
        self.assertNotEqual(before,workspace_projection_version(service))
        before=workspace_projection_version(service)
        with service.sessions.begin() as db:
            db.add(ProgramMapping(id='prg',name='프로그램',seed_policy_id='POL_A',policy_id='POL_A',status='CONFIRMED',revision_no=1,basis='검토',evidence_url='https://example.org'))
        self.assertNotEqual(before,workspace_projection_version(service))

    def test_policy_cache_preserves_raw_imports_but_invalidates_confirmed_links(self):
        from backend.projection_cache import delivery_projection_version
        from backend.db import Batch,Audit,now
        engine=create_engine('sqlite://',poolclass=StaticPool)
        Base.metadata.create_all(engine);service=HomeService(engine)
        initial=delivery_projection_version(service)
        with service.sessions.begin() as db:
            upsert_revision(db,'general_permit','building_general_permit','raw',{'units':20},'raw')
            db.add(Batch(source_id='building_general_permit',status='SUCCESS',finished_at=now()))
            db.add(Audit(entity_id='raw',action='START_CANDIDATE_FOUND',before={},after={}))
        self.assertEqual(initial,delivery_projection_version(service))
        with service.sessions.begin() as db:
            upsert_revision(db,'evidence_bridge','cross_source','link',{'status':'CONFIRMED','facts':[{'stage':'CONSTRUCTION','units':20}]},'review')
        linked=delivery_projection_version(service);self.assertNotEqual(initial,linked)
        with service.sessions.begin() as db:
            upsert_revision(db,'delivery_setting','officer','goal',{'targets':[{'units':30}]},'edit')
        edited=delivery_projection_version(service);self.assertNotEqual(linked,edited)
        with service.sessions.begin() as db:
            db.add(Batch(source_id='ih_supply',status='FAILED',finished_at=now()))
        self.assertNotEqual(edited,delivery_projection_version(service))
        engine.dispose()

    def test_matrix_ignores_unlinked_raw_ingestion_but_sees_links_and_reviews(self):
        from backend.db import Audit, Batch, now
        engine=create_engine('sqlite://',poolclass=StaticPool)
        Base.metadata.create_all(engine);service=HomeService(engine)
        initial=collection_projection_version(service)
        with service.sessions.begin() as db:
            upsert_revision(db,'general_permit','building_general_permit','raw',{'base_date':'2026-10-18'},'batch')
            db.add(Batch(source_id='building_general_permit',status='SUCCESS',finished_at=now()))
        self.assertEqual(initial,collection_projection_version(service))
        with service.sessions.begin() as db:
            upsert_revision(db,'collection_link','auto','link',{'base_date':'2026-10-18'},'batch')
        linked=collection_projection_version(service);self.assertNotEqual(initial,linked)
        with service.sessions.begin() as db:
            db.add(Audit(entity_id='pr',action='PROGRAM_POLICY_REVIEW',before={},after={'actor':'김민'}))
        reviewed=collection_projection_version(service);self.assertNotEqual(linked,reviewed)
        with service.sessions.begin() as db:
            db.add(Batch(source_id='ih_notice',status='FAILED',finished_at=now()))
        self.assertNotEqual(reviewed,collection_projection_version(service))
        engine.dispose()

    def test_revision_change_and_variant_separation(self):
        version=[1];calls=[]
        cache=ProjectionCache(lambda:version[0])
        def build():calls.append(1);return {'units':version[0]}
        self.assertEqual(cache.get(('2026-10-12',False),build)[1],'MISS')
        self.assertEqual(cache.get(('2026-10-12',False),build)[1],'HIT')
        self.assertEqual(cache.get(('2026-10-12',True),build)[1],'MISS')
        version[0]=2
        body,status=cache.get(('2026-10-12',False),build)
        self.assertEqual(status,'MISS');self.assertEqual(json.loads(body)['units'],2)
        self.assertEqual(len(calls),3)

    def test_changed_during_build_is_not_cached(self):
        version=[1];cache=ProjectionCache(lambda:version[0])
        def changing():version[0]+=1;return {'units':1}
        cache.get('key',changing)
        self.assertEqual(cache.get('key',lambda:{'units':2})[1],'MISS')
        self.assertEqual(cache.get('key',lambda:None)[1],'HIT')

    def test_bounded_and_expired_entries(self):
        cache=ProjectionCache(lambda:1,max_entries=1)
        cache.get('a',lambda:1);cache.get('b',lambda:2)
        self.assertEqual(cache.get('a',lambda:3)[1],'MISS')
        cache.ttl=0
        self.assertEqual(cache.get('a',lambda:4)[1],'MISS')

    def test_source_goal_and_mapping_changes_invalidate_db_version(self):
        engine=create_engine('sqlite://',poolclass=StaticPool)
        Base.metadata.create_all(engine);service=HomeService(engine)
        first=projection_version(service)
        with service.sessions.begin() as session:
            upsert_revision(session,'delivery_setting','officer','goal',{'base_date':'2026-10-12','targets':[]},'batch')
        second=projection_version(service);self.assertNotEqual(first,second)
        with service.sessions.begin() as session:
            session.add(Mapping(project_id='project',policy_id='POL_A',status='REVIEW',revision_no=1,basis='test',evidence_url='https://example.org'))
        third=projection_version(service);self.assertNotEqual(second,third)
        with service.sessions.begin() as session:
            row=session.query(Mapping).one();row.policy_id='POL_B';row.revision_no+=1
        fourth=projection_version(service);self.assertNotEqual(third,fourth)
        engine.dispose()

class ConcurrentCacheTests(unittest.TestCase):
    def test_cached_read_does_not_wait_for_unrelated_fill(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        started, release = Event(), Event()
        cache = ProjectionCache(lambda: 1)
        cache.get('ready', lambda: {'units': 10})
        def slow():
            started.set()
            if not release.wait(3): raise RuntimeError('fill timed out')
            return {'units': 20}
        with ThreadPoolExecutor(max_workers=3) as pool:
            work = pool.submit(cache.get, 'slow', slow)
            try:
                self.assertTrue(started.wait(1))
                hit = pool.submit(cache.get, 'ready', lambda: self.fail('rebuild'))
                self.assertEqual(hit.result(timeout=1)[1], 'HIT')
            finally:
                release.set()
            self.assertEqual(json.loads(work.result()[0])['units'], 20)

    def test_memory_bound_and_failed_fill_retry(self):
        cache=ProjectionCache(lambda:1,max_bytes=6)
        cache.get('large',lambda:'long body')
        self.assertEqual(len(cache.entries),0)
        with self.assertRaises(ValueError):
            cache.get('bad',lambda:(_ for _ in ()).throw(ValueError('failed')))
        self.assertEqual(cache.get('bad',lambda:1)[1],'MISS')
