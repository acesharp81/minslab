import unittest
from unittest.mock import patch
from datetime import date, datetime, timezone
from sqlalchemy import create_engine, select, func
from sqlalchemy.pool import StaticPool
from backend.db import Base, Revision, Audit, upsert_revision
from backend.service import HomeService
from backend.collection_repairs import save, enrich, record_collection, classify_existing

class RepairHistoryTests(unittest.TestCase):
    def setUp(self):
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return datetime(2026,10,12,12,tzinfo=timezone.utc)
        clock=patch('backend.db.datetime',Clock);clock.start();self.addCleanup(clock.stop)
        day=patch('backend.collection_repairs.today',return_value=date(2026,10,12));day.start();self.addCleanup(day.stop)
        self.engine=create_engine('sqlite://',poolclass=StaticPool)
        Base.metadata.create_all(self.engine);self.addCleanup(self.engine.dispose)
        self.s=HomeService(self.engine)
    def payload(self,**kw):
        return dict(title='오류',cause='원인',action='조치',remaining='검토 필요',stages=['APPROVAL'],status='APPLIED_REVIEW_PENDING',base_date='2026-10-12',source_ids=['building_hub'],**kw)
    def item(self,pid='p1'):
        return dict(id=pid,cells={'APPROVAL':dict(sources=[dict(source_id='building_hub')])})
    def test_project_only_repair_accepts_missing_source_list_and_preserves_scope(self):
        payload=self.payload(project_ids=['p1']);payload.pop('source_ids')
        save(self.s,'project-only',payload)
        self.assertEqual(self.s.rows('collection_repair')[0]['source_ids'],[])
        save(self.s,'scoped',self.payload(project_ids=['p1']))
        update=self.payload();update.pop('source_ids');update['action']='추가 조치'
        save(self.s,'scoped',update)
        record=next(r for r in self.s.rows('collection_repair') if r['action']=='추가 조치')
        self.assertEqual(record['source_ids'],['building_hub'])
        self.assertEqual(record['project_ids'],['p1'])

    def test_idempotence_history_and_scope(self):
        self.assertEqual(save(self.s,'one',self.payload(project_ids=['p1']))['revision_no'],1)
        self.assertEqual(save(self.s,'one',self.payload(project_ids=['p1']))['outcome'],'unchanged')
        revised=self.payload(project_ids=['p1']);revised['action']='후속 조치'
        self.assertEqual(save(self.s,'one',revised)['revision_no'],2)
        items=[self.item(),self.item('p2')];result=enrich(self.s,items,date(2026,10,12))
        self.assertEqual(len(result),1);self.assertEqual(len(result[0]['history']),2)
        self.assertEqual(result[0]['history'][1]['action'],'조치')
        self.assertEqual(len(items[0]['repair_ids']),1);self.assertFalse(items[1]['repair_ids'])
    def test_history_reads_do_not_write_and_include_officer_changes(self):
        with self.s.sessions.begin() as db:
            r,_=upsert_revision(db,'stage_evidence','auto','p1',dict(project_id='p1',base_date='2026-10-12'),'test')
            db.add(Audit(entity_id=r.entity_id,action='STAGE_EVIDENCE_REVIEW',before=dict(status='REVIEW'),after=dict(project_id='p1',stage='APPROVAL',status='RELEASED',basis='담당자 해제')))
        item=self.item();enrich(self.s,[item],date(2026,10,12));enrich(self.s,[item],date(2026,10,12))
        self.assertEqual(item['link_changes'][0]['status'],'RELEASED')
        with self.s.sessions() as db:self.assertEqual(db.scalar(select(func.count()).select_from(Revision)),1)
    def test_future_records_are_hidden(self):
        save(self.s,'future',self.payload())
        with self.s.sessions.begin() as db:
            for r in db.scalars(select(Revision)):r.recorded_at=datetime(2026,11,1,tzinfo=timezone.utc)
        self.assertFalse(enrich(self.s,[self.item()],date(2026,10,12)))
    def test_collection_failure_recovery_preserves_both_versions(self):
        source=dict(id='building_hub',name='건축HUB')
        record_collection(self.s,source,True)
        self.assertFalse(self.s.rows('collection_repair'))
        record_collection(self.s,source,False);record_collection(self.s,source,False)
        record_collection(self.s,source,True);record_collection(self.s,source,True)
        result=enrich(self.s,[self.item()],date(2026,10,12))
        self.assertEqual(result[0]['status'],'RECOVERED');self.assertEqual(result[0]['revision_no'],2)
        self.assertEqual(result[0]['history'][1]['status'],'OPEN')

    def test_type_backfill_preserves_officer_fields_and_previous_version(self):
        old_payload=self.payload(project_ids=['p1']);old_payload.update(status='CONFIRMED',action='담당자가 수정한 조치',review_basis='확인 완료')
        with self.s.sessions.begin() as db:
            upsert_revision(db,'collection_repair','repair_log','juam-c2-approval',old_payload,'test')
        changed=classify_existing(self.s)
        self.assertEqual(len(changed),1);self.assertEqual(changed[0]['repair_type'],'SCOPE_QUANTITY')
        result=enrich(self.s,[self.item()],date(2026,10,12))[0]
        self.assertEqual(result['status'],'CONFIRMED');self.assertEqual(result['action'],'담당자가 수정한 조치')
        self.assertEqual(result['review_basis'],'확인 완료');self.assertEqual(result['revision_no'],2)
        self.assertNotIn('repair_type',result['history'][1]);self.assertFalse(classify_existing(self.s))
    def test_untyped_future_edit_retains_saved_type(self):
        save(self.s,'juam-c2-approval',self.payload())
        value=self.payload();value['action']='후속 조치'
        save(self.s,'juam-c2-approval',value)
        self.assertEqual(self.s.rows('collection_repair')[0]['repair_type'],'SCOPE_QUANTITY')

    def test_quality_patch_preserves_officer_decision_and_history(self):
        from backend.collection_repairs import patch_details, quality_guide
        from scripts.record_quality_details import DETAILS
        original=self.payload();original['status']='CONFIRMED';original['action']='담당자 확인 조치'
        save(self.s,'geumto-a2-split-tenure',original)
        patch_details(self.s,'geumto-a2-split-tenure',DETAILS['geumto-a2-split-tenure'])
        self.assertEqual(patch_details(self.s,'geumto-a2-split-tenure',DETAILS['geumto-a2-split-tenure'])['outcome'],'unchanged')
        result=enrich(self.s,[self.item()],date(2026,10,12))
        row=result[0];self.assertEqual(row['status'],'CONFIRMED');self.assertEqual(row['action'],'담당자 확인 조치')
        self.assertEqual(row['quality_checks'][0]['kind'],'CONSISTENCY');self.assertEqual(row['revision_no'],2)
        self.assertNotIn('quality_checks',row['history'][1])
        original['action']='후속 조치';save(self.s,'geumto-a2-split-tenure',original)
        self.assertEqual(self.s.rows('collection_repair')[0]['quality_checks'],row['quality_checks'])
        exported=quality_guide(dict(as_of_date='2026-10-12',total=1,repairs=result))
        self.assertEqual(exported['repairs'][0]['quality_checks'],row['quality_checks'])
    def test_quality_rejects_impossible_counts_without_revision(self):
        from backend.collection_repairs import patch_details
        from scripts.record_quality_details import check,m
        save(self.s,'one',self.payload())
        bad=check('bad','점검','COVERAGE','COLLECTION','FAIL','규칙','근거','정비','완료','범위',[m('확보',179,178)])
        with self.assertRaisesRegex(ValueError,'분모'):
            patch_details(self.s,'one',dict(quality_checks=[bad]))
        self.assertEqual(self.s.rows('collection_repair')[0]['revision_no'],1)
