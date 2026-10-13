import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch
from sqlalchemy import create_engine, select, func
from sqlalchemy.pool import StaticPool
from backend.db import Base, Revision, upsert_revision
from backend.service import HomeService
from backend.collection_lineage import fields, enrich

class LineageTests(unittest.TestCase):
    def test_unpinned_uses_latest_known_revision_and_future_pin_is_hidden(self):
        engine=create_engine('sqlite://',poolclass=StaticPool)
        Base.metadata.create_all(engine);service=HomeService(engine)
        self.addCleanup(engine.dispose)
        with service.sessions.begin() as db:
            first,_=upsert_revision(db,'permit','building_hub','p',{'source_object_id':'old'},'test')
            first.recorded_at=datetime(2026,1,1,tzinfo=timezone.utc);eid=first.entity_id
        with service.sessions.begin() as db:
            second,_=upsert_revision(db,'permit','building_hub','p',{'source_object_id':'future'},'test')
            second.recorded_at=datetime(2026,11,1,tzinfo=timezone.utc)
        project=dict(id='p1',source_id='lh_sale',region='경기도')
        def item(revision):
            return dict(id='p1',cells={'APPROVAL':dict(sources=[dict(source_entity_id=eid,
                source_revision_no=revision,source_id='building_hub',kind='STATE')])})
        unpinned=item(None)
        enrich(service,[project],[unpinned],date(2026,10,12),{},baselines=[])
        self.assertEqual(unpinned['lineage']['keys']['permit'],'old')
        pinned=item(2)
        enrich(service,[project],[pinned],date(2026,10,12),{},baselines=[])
        self.assertNotIn('permit',pinned['lineage']['keys'])

    def test_explicit_keys_preserve_zero_and_do_not_invent_pnu(self):
        value=fields(dict(progress_pct=0,planned_units=0,sigungu_code='41171',bjdong_code='10100',bun='0001',ji='0000',source_object_id='permit-1',move_in_plan_month='202901'),'permit')
        self.assertEqual(value['progress'],'0');self.assertEqual(value['target'],'0')
        self.assertEqual(value['legal_dong'],'4117110100');self.assertEqual(value['permit'],'permit-1')
        self.assertNotIn('pnu',value);self.assertNotIn('move_actual',value)
        self.assertNotIn('permit',fields(dict(source_object_id='project-1'),'project'))
        self.assertNotIn('pnu',fields(dict(pnu='bad')))
        self.assertEqual(fields(dict(pnu='4117110100100010000'))['pnu'],'4117110100100010000')

    def test_pinned_revision_and_read_only_provenance(self):
        engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
        Base.metadata.create_all(engine);service=HomeService(engine)
        with service.sessions.begin() as db:
            first,_=upsert_revision(db,'permit','building_hub','permit-1',dict(source_object_id='PK-old',sigungu_code='41171',bjdong_code='10100'),'test')
            eid=first.entity_id
        with service.sessions.begin() as db:
            upsert_revision(db,'permit','building_hub','permit-1',dict(source_object_id='PK-new',sigungu_code='41171',bjdong_code='10200'),'test')
            for r in db.scalars(select(Revision)):r.recorded_at=datetime(2026,1,1,tzinfo=timezone.utc)
        project=dict(id='p1',source_id='lh_sale',name='사업',region='경기도',mapping=dict(policy_id='pol',program_id='pr',status='REVIEW'))
        item=dict(id='p1',cells={'APPROVAL':dict(sources=[dict(source_entity_id=eid,source_revision_no=1,source_id='building_hub',kind='STATE',review_status='REVIEW')])})
        with patch.object(service,'rows',return_value=[]):
            enrich(service,[project],[item],date(2026,10,12),{})
        self.assertEqual(item['lineage']['keys']['permit'],'PK-old')
        self.assertEqual(item['lineage']['keys']['legal_dong'],'4117110100')
        self.assertTrue(item['lineage']['sources']['building_hub']['review'])
        with service.sessions() as db:self.assertEqual(db.scalar(select(func.count()).select_from(Revision)),2)
        engine.dispose()

    def test_inferred_predecessor_is_not_permit_and_plan_not_move_actual(self):
        engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
        Base.metadata.create_all(engine);service=HomeService(engine)
        project=dict(id='p1',source_id='lh_sale',name='사업',region='경기도',mapping=dict(status='RELEASED',policy_id='pol',program_id='pr'))
        item=dict(id='p1',cells={
            'APPROVAL':dict(sources=[dict(source_id='lh_sale',kind='STATE',method='PREREQUISITE',review_status='REVIEW')]),
            'MOVE_IN':dict(sources=[dict(source_id='lh_sale',kind='PLAN',date='2029-01')])})
        with patch.object(service,'rows',return_value=[]):enrich(service,[project],[item],date(2026,10,12),{})
        keys=item['lineage']['keys'];self.assertEqual(keys['move_plan'],'2029-01')
        for k in ('move_actual','permit','policy','program'):self.assertNotIn(k,keys)
        self.assertTrue(item['lineage']['sources']['lh_sale']['inferred'])
        self.assertNotIn('due',item['lineage']['stage_keys']['APPROVAL'])
        self.assertEqual(item['lineage']['stage_keys']['MOVE_IN']['due'],'2029-01')
        engine.dispose()
