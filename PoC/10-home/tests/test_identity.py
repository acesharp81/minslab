"""Stable project identities keep unapproved LH links and reviewer state separate."""
import unittest

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from backend.db import Audit, Base, IdentityAlias, ProjectEvidence, ProjectIdentity, Revision
from backend.identity import identity_summary, reconcile_identity_links, review_identity_alias
from backend.service import HomeService


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite+pysqlite:///:memory:')
        @event.listens_for(self.engine, 'connect')
        def enforce_foreign_keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(self.engine)
        self.service = HomeService(self.engine)

    def add(self, kind, eid, payload, source='fixture'):
        with self.service.sessions.begin() as session:
            session.add(Revision(id=('r' + eid)[-36:], entity_id=eid, kind=kind, source_id=source,
                revision_no=1, payload=payload, payload_hash='fixture', batch_id='batch',
                sample_name=payload['name'], sample_region=payload['region']))
        return eid

    def test_unique_block_proposal_is_review_only_and_idempotent(self):
        self.add('project', 'PROJ_A', dict(name='창릉 S4', region='경기도',
            district='고양창릉', block='S-4', planned_units=900, evidence_url='https://lh.or.kr/project'))
        self.add('lh_completion_plan', 'PLAN_A', dict(name='창릉 S4 준공예정', region='경기도',
            district='고양창릉', block='S4BL', planned_units=800, evidence_url='https://lh.or.kr/plan'),
            source='lh_completion_plan')
        first = reconcile_identity_links(self.service)
        self.assertEqual(first['source_anchors_added'], 1)
        self.assertEqual(first['forecast_proposals_added'], 1)
        self.assertEqual(reconcile_identity_links(self.service)['forecast_proposals_added'], 0)
        with self.service.sessions.begin() as session:
            alias = session.scalar(select(IdentityAlias).where(IdentityAlias.source_entity_id == 'PLAN_A'))
            self.assertEqual(alias.relation_status, 'REVIEW')
            self.assertEqual(alias.unit_comparison, 'DIFFERENT')
            alias.relation_status = 'CONFIRMED'
        self.assertEqual(reconcile_identity_links(self.service)['forecast_proposals_added'], 0)
        with self.service.sessions() as session:
            self.assertEqual(session.scalar(select(IdentityAlias).where(
                IdentityAlias.source_entity_id == 'PLAN_A')).relation_status, 'CONFIRMED')
            self.assertEqual(len(session.scalars(select(ProjectIdentity)).all()), 1)
            self.assertEqual(len(session.scalars(select(ProjectEvidence)).all()), 2)
        summary = identity_summary(self.service)
        self.assertEqual(summary['total'], 1)
        self.assertEqual(len(summary['items'][0]['aliases']), 2)

    def test_reviewer_can_reassign_without_losing_evidence_or_audit(self):
        self.add('project', 'PROJ_A', dict(name='A', region='경기도',
            district='창릉', block='S4', planned_units=900, evidence_url='https://lh.or.kr/a'))
        self.add('project', 'PROJ_B', dict(name='B', region='경기도',
            district='창릉', block='S5', planned_units=800, evidence_url='https://lh.or.kr/b'))
        self.add('lh_completion_plan', 'PLAN_A', dict(name='A forecast', region='경기도',
            district='창릉', block='S4', planned_units=900, evidence_url='https://lh.or.kr/plan'),
            source='lh_completion_plan')
        reconcile_identity_links(self.service)
        with self.service.sessions() as session:
            alias = session.scalar(select(IdentityAlias).where(IdentityAlias.source_entity_id == 'PLAN_A'))
            alias_id, old_id = alias.id, alias.project_id
            new_id = session.scalar(select(ProjectIdentity.id).where(ProjectIdentity.name == 'B'))
        result = review_identity_alias(self.service, alias_id, project_id=new_id,
            expected_project_id=old_id, expected_status='REVIEW', status='CONFIRMED',
            basis='공식 사업번호 대조 후 담당자 확인', evidence_url='https://lh.or.kr/plan')
        self.assertFalse(result['conflict'])
        reconcile_identity_links(self.service)
        with self.service.sessions() as session:
            alias = session.get(IdentityAlias, alias_id)
            self.assertEqual((alias.project_id, alias.relation_status), (new_id, 'CONFIRMED'))
            self.assertEqual(len(session.scalars(select(ProjectEvidence).where(
                ProjectEvidence.project_id == new_id)).all()), 2)
            self.assertEqual(len(session.scalars(select(Audit).where(
                Audit.action == 'IDENTITY_REVIEW')).all()), 1)
        self.assertTrue(review_identity_alias(self.service, alias_id, project_id=old_id,
            expected_project_id=old_id, expected_status='REVIEW', status='CONFIRMED',
            basis='오래된 화면에서 저장 시도', evidence_url='https://lh.or.kr/plan')['conflict'])

    def test_ambiguous_block_is_never_autolinked(self):
        for eid in ('PROJ_A', 'PROJ_B'):
            self.add('project', eid, dict(name=eid, region='경기도', district='고양창릉',
                block='S4', planned_units=900, evidence_url='https://lh.or.kr/project'))
        self.add('lh_completion_plan', 'PLAN_A', dict(name='창릉 S4', region='경기도',
            district='고양창릉', block='S4', planned_units=900, evidence_url='https://lh.or.kr/plan'),
            source='lh_completion_plan')
        result = reconcile_identity_links(self.service)
        self.assertEqual(result['ambiguous_forecasts'], 1)
        self.assertEqual(result['forecast_proposals_added'], 0)
        with self.service.sessions() as session:
            self.assertIsNone(session.scalar(select(IdentityAlias).where(
                IdentityAlias.source_entity_id == 'PLAN_A')))


if __name__ == '__main__':
    unittest.main()

