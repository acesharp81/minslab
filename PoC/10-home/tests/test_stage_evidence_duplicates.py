import unittest
from copy import deepcopy
from backend.stage_evidence_duplicates import annotate_duplicates

class DuplicateTests(unittest.TestCase):
    def rows(self):
        projects={pid:dict(id=pid,name='과천주암 '+block,region='경기도',district='과천주암',block=block) for pid,block in [('a','C2'),('b','C2'),('c','C1')]}
        evidence=dict(source_entity_id='permit-1',source_id='building_hub',evidence_url='https://example.com/catalog',units=1030)
        rows=[dict(project_id=pid,name=p['name'],stage='APPROVAL',selected=deepcopy(evidence),candidates=[deepcopy(evidence)],planned_units=344 if pid=='b' else 1030) for pid,p in projects.items()]
        return rows,projects
    def test_shared_same_block_marks_whole_partial_without_mutating_links(self):
        rows,projects=self.rows();original=deepcopy(rows);result=annotate_duplicates(rows,projects)
        self.assertEqual([r['duplicate_suspected'] for r in result],[True,True,False])
        self.assertEqual(result[0]['duplicate_peers'][0]['planned_units'],344)
        self.assertTrue(result[0]['candidates'][0]['duplicate_suspected'])
        self.assertEqual(rows,original)
    def test_common_url_and_selected_candidate_repeat_are_not_duplicates(self):
        rows,projects=self.rows();rows[1]['selected']['source_entity_id']='permit-2';rows[1]['candidates'][0]['source_entity_id']='permit-2'
        self.assertFalse(any(r['duplicate_suspected'] for r in annotate_duplicates(rows,projects)))
    def test_different_stages_or_unknown_sources_are_not_duplicates(self):
        rows,projects=self.rows();rows[1]['stage']='BUSINESS'
        self.assertFalse(any(r['duplicate_suspected'] for r in annotate_duplicates(rows,projects)))
        for r in rows:
            r['selected'].pop('source_entity_id');r['candidates'][0].pop('source_entity_id')
        self.assertFalse(any(r['duplicate_suspected'] for r in annotate_duplicates(rows,projects)))
