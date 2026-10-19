import unittest
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from backend.read_scope import projection_reads, reuse_rows

class Source:
    known_at = None
    def __init__(self): self.calls = 0
    @reuse_rows
    def rows(self, kind, as_of=None, entity_ids=None, known_at=None):
        self.calls += 1
        return [{'nested': {'value': self.calls}}]

class ReadScopeTests(unittest.TestCase):
    def test_mutations_do_not_leak_and_next_build_reads_fresh(self):
        s = Source()
        with projection_reads():
            s.rows('project')[0]['nested']['value'] = 900
            self.assertEqual(s.rows('project')[0]['nested']['value'], 1)
        with projection_reads(): self.assertEqual(s.rows('project')[0]['nested']['value'], 2)
        self.assertEqual(s.rows('project')[0]['nested']['value'], 3)

    def test_nested_projection_reuses_reads_and_exception_clears_context(self):
        s=Source()
        with self.assertRaises(ValueError):
            with projection_reads():
                s.rows('project')
                with projection_reads():
                    self.assertEqual(s.rows('project')[0]['nested']['value'],1)
                self.assertEqual(s.calls,1)
                raise ValueError('failed build')
        self.assertEqual(s.rows('project')[0]['nested']['value'],2)

    def test_dates_instances_and_knowledge_are_separate(self):
        s = Source(); other = Source()
        with projection_reads():
            s.rows('project', date(2026, 1, 1)); s.rows('project', date(2026, 2, 1))
            other.rows('project', date(2026, 1, 1))
            s.known_at = 'changed'; s.rows('project', date(2026, 1, 1))
        self.assertEqual(s.calls, 3); self.assertEqual(other.calls, 1)

    def test_raw_tables_not_retained_and_worker_context_isolated(self):
        s = Source()
        with projection_reads():
            s.rows('permit'); s.rows('permit'); s.rows('project')
            with ThreadPoolExecutor(max_workers=1) as pool:
                self.assertEqual(pool.submit(s.rows, 'project').result()[0]['nested']['value'], 4)
            self.assertEqual(s.rows('project')[0]['nested']['value'], 3)
        self.assertEqual(s.calls, 4)
