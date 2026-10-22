from concurrent.futures import ThreadPoolExecutor
from threading import Event
import time
from unittest import TestCase, mock

from app.services.ontology_snapshot import OntologySnapshotCache


class OntologySnapshotTests(TestCase):
    def test_cold_concurrent_requests_return_taxonomy_and_build_only_once(self):
        cache = OntologySnapshotCache()
        started, release = Event(), Event()
        calls = []
        def build():
            calls.append(1)
            started.set()
            release.wait(3)
            return {'metrics': {'report_count': 44}}
        taxonomy = lambda: {'metrics': {'report_count': 0}, 'domains': ['policy']}
        try:
            first = cache.get(build, taxonomy)
            self.assertEqual(first['snapshot']['status'], 'LOADING')
            self.assertIsNone(first['snapshot']['generated_at'])
            self.assertTrue(started.wait(1))
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: cache.get(build, taxonomy), range(16)))
            self.assertTrue(all(r['snapshot']['status'] == 'LOADING' for r in results))
            self.assertEqual(len(calls), 1)
        finally:
            release.set()
        for _ in range(100):
            result = cache.get(build, taxonomy)
            if result['snapshot']['status'] == 'READY':
                break
            time.sleep(.01)
        self.assertEqual(result['metrics']['report_count'], 44)
        result['metrics']['report_count'] = -1
        self.assertEqual(cache.get(build, taxonomy)['metrics']['report_count'], 44)
        self.assertEqual(len(calls), 1)

    def test_failed_refresh_keeps_last_good_snapshot_and_backs_off(self):
        cache = OntologySnapshotCache()
        cache._refresh(lambda: {'metrics': {'report_count': 44}})
        generated = cache._generated_at
        failure = mock.Mock(side_effect=RuntimeError('offline'))
        cache._attempted_at = time.monotonic()
        cache._refresh(failure)
        for _ in range(3):
            response = cache.get(failure, lambda: {}, refresh=True)
            self.assertEqual(response['snapshot']['status'], 'STALE')
            self.assertEqual(response['snapshot']['generated_at'], generated)
            self.assertEqual(response['metrics']['report_count'], 44)
        failure.assert_called_once()

    def test_expired_snapshot_served_while_new_one_is_computed(self):
        cache = OntologySnapshotCache(ttl_seconds=1)
        cache._refresh(lambda: {'metrics': {'report_count': 44}})
        cache._completed_at -= 2
        release = Event()
        def build():
            release.wait(3)
            return {'metrics': {'report_count': 45}}
        try:
            result = cache.get(build, lambda: {})
            self.assertEqual(result['snapshot']['status'], 'REFRESHING')
            self.assertEqual(result['metrics']['report_count'], 44)
            self.assertIsNotNone(result['snapshot']['generated_at'])
        finally:
            release.set()

    def test_cold_failure_is_not_a_valid_zero_report_snapshot(self):
        cache = OntologySnapshotCache()
        cache._attempted_at = time.monotonic()
        cache._refresh(mock.Mock(side_effect=RuntimeError()))
        result = cache.get(lambda: {}, lambda: {'metrics': {'report_count': 0}})
        self.assertEqual(result['snapshot']['status'], 'FAILED')
        self.assertIsNone(result['snapshot']['generated_at'])
