import json
import unittest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from backend.db import Base, Mapping, ProgramMapping, upsert_revision
from backend.service import HomeService
from backend.projection_cache import ProjectionCache, projection_version


class ProjectionCacheTests(unittest.TestCase):
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
