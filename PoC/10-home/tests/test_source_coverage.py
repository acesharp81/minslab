"""A successful source query must expose its exact scope without creating policy supply."""
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.pool import StaticPool

from backend.app import create_app
from backend.db import Base, Coverage, Mapping
from backend.official_supply_files import parse_renewal_inventory
from backend.service import HomeService
from backend.sources import SOURCES


class SourceCoverageTests(unittest.TestCase):
    def test_file_query_coverage_and_unmapped_candidate(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        source = next(row for row in SOURCES if row['id'] == 'molit_renewal_inventory')
        content = ('시도,시군구,구역명칭,현 사업추진단계,사업유형,사업시행자,공급 예정 세대수\n'
            '서울특별시,성북구,검증 구역,착공,재개발,조합,100\n'
            '경기도,수원시,검증 구역,인가,재건축,조합,0\n').encode()
        records, stats = parse_renewal_inventory(content, source, '2026-05-18')
        with tempfile.TemporaryDirectory() as directory:
            service = HomeService(engine, directory)
            with patch('backend.service.collect_renewal_inventory', return_value=(records, stats)):
                result = service.collect_all(source['id'])
            self.assertEqual(result['results'][0]['status'], 'SUCCESS')
            with service.sessions() as session:
                self.assertEqual(session.scalar(select(func.count()).select_from(Mapping)), 0)
                self.assertEqual(session.scalar(select(func.count()).select_from(Coverage)), 3)
            app = create_app(engine, auto_collect=False)
            with TestClient(app) as client:
                body = client.get('/poc/home/api/coverage').json()
                self.assertEqual(body['complete_population'], False)
                self.assertEqual(len(body['items']), 3)
                self.assertEqual([row['fetched_count'] for row in body['items']], [1, 1, 0])
                self.assertTrue(all(row['query_status'] == 'COMPLETE_QUERY' for row in body['items']))
                self.assertTrue(all(row['population_status'] == 'PARTIAL_SCOPE' for row in body['items']))
                rows = client.get('/poc/home/api/samples?kind=renewal_inventory').json()
                self.assertEqual(rows['total'], 2)
                self.assertTrue(all(row['policy_mapping_status'] == 'UNMAPPED' for row in rows['items']))
            # A later official edition omits one zone. Keep its prior evidence, but flag it.
            revised_stats = dict(stats, file_rows=1, included_rows=1, excluded_rows=0,
                region_counts={'서울특별시': 1}, dataset_version='2026-06-01')
            with patch('backend.service.collect_renewal_inventory', return_value=(records[:1], revised_stats)):
                self.assertEqual(service.collect_all(source['id'])['results'][0]['status'], 'SUCCESS')
            with TestClient(create_app(engine, auto_collect=False)) as client:
                rows = client.get('/poc/home/api/samples?kind=renewal_inventory').json()['items']
                self.assertEqual(len(rows), 2)
                self.assertEqual(sum(row['in_latest_source'] is False for row in rows), 1)
                old = next(row for row in rows if row['in_latest_source'] is False)
                detail = client.get('/poc/home/api/samples/' + old['id']).json()
                self.assertIn('MISSING_IN_LATEST_SOURCE', detail['warnings'])
                self.assertEqual(len(client.get('/poc/home/api/coverage').json()['items']), 1)
        engine.dispose()


if __name__ == '__main__':
    unittest.main()
