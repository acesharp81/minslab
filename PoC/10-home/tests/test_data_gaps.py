import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.data_gaps import data_gap_audit, project_data_status
from backend.db import Base, Revision
from backend.source_coverage import coverage_rows


class DataGapAuditTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)

    @staticmethod
    def source(sid, attempted=True, succeeded=True, status='SUCCESS'):
        return dict(id=sid, url='https://example.org/source', status=status,
                    last_attempt='2026-10-10T00:00:00Z' if attempted else None,
                    last_success='2026-10-10T00:00:00Z' if succeeded else None,
                    stats={})

    def test_empty_year_is_not_zero_or_non_start(self):
        sources = [self.source('molit_statistics'), self.source('lh_supply_history', False, False, 'NOT_COLLECTED'),
                   self.source('lh_progress', True, False, 'FAILED')]
        with Session(self.engine) as session:
            session.add(Revision(entity_id='STA_TEST', kind='statistic', source_id='molit_statistics',
                                 revision_no=1, sample_region='서울특별시', sample_source_date='2018-12-31',
                                 payload={'statistic_metric': '준공', 'year': 2018}, payload_hash='x', batch_id='test',
                                 recorded_at=datetime.now(timezone.utc)))
            session.commit()
            report = data_gap_audit(session, sources, [], 2020)
        completion = next(r for r in report['rows'] if r['label'] == '준공 · 지역 전체' and r['region'] == '서울특별시')
        self.assertEqual([c['status'] for c in completion['cells']], ['ACQUIRED', 'NOT_ACQUIRED', 'NOT_ACQUIRED'])
        no_attempt = next(r for r in report['rows'] if r['source_id'] == 'lh_supply_history' and r['region'] == '서울특별시')
        failed = next(r for r in report['rows'] if r['source_id'] == 'lh_progress' and r['region'] == '서울특별시')
        self.assertEqual(no_attempt['cells'][0]['status'], 'NOT_STARTED')
        self.assertEqual(failed['cells'][0]['status'], 'FAILED')
        self.assertIn('미입수는 0건·미착수를 뜻하지 않습니다', report['notice'])

    def test_planning_stage_does_not_prove_non_start(self):
        status = project_data_status({'stage': 'PLANNING', 'planned_units': 300, 'progress_pct': None})
        self.assertFalse(status['not_started_verified'])
        self.assertIn('미확인', status['phase'])
        self.assertIn('미입수', status['progress'])
        self.assertEqual(status['planned_units'], '확보')
        self.assertEqual(status['move_in_start'], '입주 시작일 미확보')
        with_date = project_data_status({'stage':'CONSTRUCTION','move_in_start':{'date':'2028-05','precision':'MONTH','status':'PLANNED'}})
        self.assertEqual(with_date['move_in_start'], '입주 시작 예정월 확보')

    def test_full_source_file_can_have_no_regional_row(self):
        source = self.source('lh_supply_history')
        source['stats'] = {'complete_query': True, 'period_start': '2020', 'period_end': '2025'}
        with Session(self.engine) as session:
            session.add(Revision(entity_id='LH_TEST', kind='lh_supply', source_id='lh_supply_history',
                                 revision_no=1, sample_region='경기도', sample_source_date='2020-05-01',
                                 payload={'year': 2020}, payload_hash='x', batch_id='test'))
            session.commit()
            report = data_gap_audit(session, [source], [], 2020)
        seoul = next(r for r in report['rows'] if r['source_id'] == 'lh_supply_history' and r['region'] == '서울특별시')
        self.assertEqual(seoul['cells'][-1]['status'], 'NO_SOURCE_RECORD')
        self.assertEqual(project_data_status({'stage': 'PLANNING', 'not_started_verified': True})['not_started_verified'], False)

    def test_legal_dong_scope_is_labeled_as_dongs(self):
        rows = coverage_rows('building_hub', {'scope_total_dongs': 2629, 'scope_completed_dongs': 838})
        self.assertEqual(rows[0]['expected_count'], 2629)
        self.assertEqual(rows[0]['fetched_count'], 838)
        self.assertIn('법정동 조회 수', rows[0]['scope_note'])
        self.assertEqual(rows[0]['query_status'], 'PARTIAL')
