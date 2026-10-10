import gzip
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine

from backend.db import Audit, Base, Batch, Mapping, ProgramMapping, upsert_revision
from scripts.export_json import export
from scripts.export_schema import build as build_schema
from scripts.export_collection_methods import build as build_methods
from scripts.write_data_sharing_guide import write_guide


class JsonExportTests(unittest.TestCase):
    def test_snapshot_exports_links_history_and_scrubs_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            url = 'sqlite:///' + str(path / 'home.sqlite')
            engine = create_engine(url)
            Base.metadata.create_all(engine)
            with engine.begin() as conn:
                from sqlalchemy.orm import Session
                with Session(bind=conn) as session:
                    record, _ = upsert_revision(session, 'project', 'lh_sale', 'A1', {
                        'name': '사업 A1', 'base_date': '2026-01-01', 'region': '경기도',
                        'evidence_url': 'https://example.org/items?serviceKey=SECRET-EXPORT-KEY&id=1',
                    }, 'batch-1')
                    session.add(ProgramMapping(id='PRG_TEST', name='공공주택 건설', seed_policy_id='UNASSIGNED',
                        policy_id='POL_2025_0907', status='REVIEW', revision_no=1,
                        basis='자동 임시 제안', evidence_url='https://example.org/policy'))
                    session.add(Mapping(project_id=record.entity_id, policy_id='UNASSIGNED', program_id='PRG_TEST',
                        status='REVIEW', basis='원천 프로그램명 일치', evidence_url='https://example.org/project'))
                    session.add(Batch(source_id='lh_sale', status='SUCCESS', stats={'record_count': 1},
                        manifest=[{'url': 'https://example.org/api?serviceKey=SECRET-EXPORT-KEY&id=1',
                                   'sha256': 'abc', 'bytes': 10}]))
                    session.add(Audit(entity_id='PRG_TEST', action='PROGRAM_POLICY_AUTO', before={'policy_id': 'UNASSIGNED'},
                        after={'policy_id': 'POL_2025_0907'}))
                    session.flush()
            destination = path / 'export'
            with patch.dict(os.environ, {'POC10_DATABASE_URL': url,
                                          'POC10_KOSIS_API_KEY': 'SECRET-EXPORT-KEY'}):
                result = export(destination)
            self.assertEqual(result['kind_counts']['project'], {'revisions': 1, 'current': 1})
            self.assertEqual(result['files']['current_projects']['records'], 1)
            projects = json.loads((destination / 'current_projects.json').read_text())
            self.assertEqual(projects[0]['link']['policy_id'], 'POL_2025_0907')
            with gzip.open(destination / 'revisions/project.json.gz', 'rt') as handle:
                revisions = json.load(handle)
            self.assertEqual(len(revisions), 1)
            self.assertNotIn('SECRET-EXPORT-KEY', json.dumps(revisions))
            with gzip.open(destination / 'collection_batches.json.gz', 'rt') as handle:
                batches = json.load(handle)
            self.assertEqual(batches[0]['manifest'][0]['url'], 'https://example.org/api?id=1')
            self.assertEqual(result['files']['review_audit']['records'], 1)
            build_schema(destination)
            build_methods(destination)
            write_guide(destination)
            payload_schema = json.loads((destination/'schema/payloads/project.schema.json').read_text())
            self.assertEqual(payload_schema['properties']['name']['type'], 'string')
            self.assertIn('program_id', (destination/'schema/relationships.json').read_text())
            self.assertIn('정책', (destination/'DATA_SHARING_GUIDE.md').read_text())
            self.assertFalse((destination.with_name('export.partial')).exists())
            engine.dispose()
