import unittest
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from backend.read_scope import projection_reads, reuse_rows, reuse_projection

class Source:
    known_at = None
    def __init__(self): self.calls = 0
    @reuse_rows
    def rows(self, kind, as_of=None, entity_ids=None, known_at=None):
        self.calls += 1
        return [{'nested': {'value': self.calls}}]

class ReadScopeTests(unittest.TestCase):
    def test_metadata_projection_is_request_local_and_mutation_isolated(self):
        class IndexSource:
            known_at=None
            calls=0
            @reuse_projection
            def index(self,day):
                self.calls+=1
                return [{'nested':{'value':self.calls},'day':day}]
        s=IndexSource();day=date(2026,10,22)
        with projection_reads():
            s.index(day)[0]['nested']['value']=999
            self.assertEqual(s.index(day)[0]['nested']['value'],1)
            s.index(date(2026,10,21))
            s.known_at='older';s.index(day)
        with projection_reads():s.index(day)
        self.assertEqual(s.calls,4)

    def test_fast_row_copy_preserves_types_and_mutable_aliases_within_each_copy(self):
        class TypedSource:
            known_at=None
            @reuse_rows
            def rows(self,*args):
                shared={'units':8}
                return [{1:(date(2026,10,20),shared), 'same':shared}]
        s=TypedSource()
        with projection_reads():
            first=s.rows('project');first[0]['same']['units']=96
            assert first[0][1][1]['units']==96
            second=s.rows('project')
            assert second[0][1][0]==date(2026,10,20)
            assert second[0]['same']['units']==8
            assert second[0][1][1] is second[0]['same']
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


def test_bridge_reads_reuse_explicit_provenance_without_scanning_documents():
    from backend.evidence_bridge import by_project
    class EvidenceSource:
        known_at=None
        calls=0
        def rows(self,kind,reference):
            assert kind=='evidence_bridge'
            self.calls+=1
            return [dict(project_id='p',source_entity_id='doc',source_id='cross_source',evidence_source_id='official',facts=[dict(units=10)])]
        def document_evidence_index(self,*args,**kwargs):raise AssertionError('Unneeded document scan')
    s=EvidenceSource()
    with projection_reads():
        first=by_project(s,date(2026,10,27));first['p'][0]['facts'][0]['units']=0
        second=by_project(s,date(2026,10,27))
        assert second['p'][0]['source_id']=='official' and second['p'][0]['facts'][0]['units']==10
        assert s.calls==1
    by_project(s,date(2026,10,27));assert s.calls==2
