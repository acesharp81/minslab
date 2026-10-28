"""Menu read optimizations retain evidence and invalidate on officer writes."""
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from backend.app import create_app
from backend.db import Base, Batch, upsert_revision, now
from backend.service import HomeService
from backend.sources import SOURCES

class MenuPerformanceTests(unittest.TestCase):
    def test_document_index_preserves_live_and_historical_visibility_without_text(self):
        from datetime import timedelta
        from backend.service import today
        instant=now();day=today()
        with self.service.sessions.begin() as db:
            old,_=upsert_revision(db,'document_evidence','official_document','doc',
                {'base_date':day.isoformat(),'reported_phase':'승인','phase_observed_at':day.isoformat(),'text':'원문'*10000},'a')
            old.recorded_at=instant-timedelta(minutes=2)
            new,_=upsert_revision(db,'document_evidence','official_document','doc',
                {'base_date':day.isoformat(),'reported_phase':'착공','text':'수정 원문\x00'*10000},'b')
            old.superseded_at=new.recorded_at=instant-timedelta(minutes=1)
            upsert_revision(db,'document_evidence','official_document','future',
                {'base_date':(day+timedelta(days=1)).isoformat()},'a')
            upsert_revision(db,'document_evidence','official_document','undated',{},'a')
        historical=HomeService(self.engine,known_at=instant-timedelta(seconds=90))
        keys=('id','source_id','base_date','reported_phase','phase_observed_at')
        for service,phase in ((self.service,'착공'),(historical,'승인')):
            expected=[{k:r.get(k) for k in keys} for r in service.rows('document_evidence')]
            self.assertEqual(service.document_evidence_index(),expected)
            self.assertEqual(expected[0]['reported_phase'],phase)
            self.assertEqual(len(expected),1)
        self.assertNotIn('text',self.service.document_evidence_index()[0])

    def test_screen_mapping_payload_preserves_membership_units_and_full_detail(self):
        from copy import deepcopy
        full=dict(items=[dict(id='p',planned_units=8,mapping={'status':'CONFIRMED'},evidence_url='https://example.org/',
            managed_schedules={'SUPPLY':{'units':8,'calculation':{'x':100}}},manual_fields={'x':8},source_values={'planned_units':8})],programs=[{'id':'P'}],total=1)
        saved=deepcopy(full)
        with patch.object(HomeService,'mappings',return_value=full):
            compact=self.client.get('/poc/home/api/mappings?compact=true').json()
            ordinary=self.client.get('/poc/home/api/mappings').json()
        self.assertEqual(full,saved);self.assertEqual(ordinary,full)
        self.assertEqual(compact['items'][0],{k:v for k,v in full['items'][0].items() if k not in ('managed_schedules','manual_fields','source_values')})
        self.assertEqual(compact['programs'],full['programs'])
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.service=HomeService(self.engine)
        self.client=TestClient(create_app(self.engine,auto_collect=False))
        self.addCleanup(self.client.close);self.addCleanup(self.engine.dispose)

    def test_view_polling_ignores_unlinked_raw_import_but_sees_officer_changes(self):
        from backend.db import Audit
        urls=['/poc/home/api/view-version?view='+v for v in ('projects','policy-progress','program-progress')]
        before=[self.client.get(u).json()['version'] for u in urls]
        with self.service.sessions.begin() as db:
            upsert_revision(db,'general_permit','building_general_permit','raw-candidate',{'units':8},'batch')
            db.add(Audit(entity_id='raw',action='START_CANDIDATE_FOUND',before={},after={}))
            db.add(Batch(source_id='building_general_permit',status='SUCCESS',finished_at=now()))
        self.assertEqual(before,[self.client.get(u).json()['version'] for u in urls])
        with self.service.sessions.begin() as db:
            upsert_revision(db,'project_profile','manual_project','p',{'overrides':{'planned_units':{'value':8}}},'edit')
        after=[self.client.get(u).json()['version'] for u in urls]
        self.assertTrue(all(a!=b for a,b in zip(before,after)))
        self.assertEqual(self.client.get('/poc/home/api/view-version?view=arbitrary').status_code,422)

    def test_live_rows_use_current_index_and_knowledge_snapshot_keeps_history(self):
        from datetime import timedelta
        from sqlalchemy import event
        from backend.db import Revision
        instant=now();queries=[]
        with self.service.sessions.begin() as db:
            old,_=upsert_revision(db,'stage_evidence','test','one',{'base_date':'2026-01-01','value':1},'a')
            old.recorded_at=instant-timedelta(minutes=2)
            new,_=upsert_revision(db,'stage_evidence','test','one',{'base_date':'2026-01-01','value':2},'b')
            old.superseded_at=new.recorded_at=instant-timedelta(minutes=1)
        def capture(conn,cursor,statement,parameters,context,executemany):queries.append(statement)
        event.listen(self.engine,'before_cursor_execute',capture)
        try:
            self.assertEqual(self.service.rows('stage_evidence')[0]['value'],2)
            self.assertFalse(any('superseded_at IS NULL OR' in q for q in queries))
            historical=HomeService(self.engine,known_at=instant-timedelta(seconds=90))
            self.assertEqual(historical.rows('stage_evidence')[0]['value'],1)
            self.assertTrue(any('superseded_at IS NULL OR' in q for q in queries))
        finally:event.remove(self.engine,'before_cursor_execute',capture)

    def test_chart_stage_projection_keeps_selection_without_candidate_payload(self):
        from backend.stage_evidence import linked_events
        from backend.service import today
        selected=dict(event_date='2026-01-02',observed_on=None,units=12,method='SOURCE',basis='official',evidence_url='https://example.org/',source_id='test')
        with self.service.sessions.begin() as db:
            upsert_revision(db,'stage_evidence','test','selected',dict(base_date='2026-01-01',project_id='P',stage='APPROVAL',status='CONFIRMED',selected=selected,candidates=[{'large':'x'*10000}]),'batch')
            upsert_revision(db,'stage_evidence','test','released',dict(base_date='2026-01-01',project_id='Q',stage='APPROVAL',status='RELEASED',selected=selected),'batch')
        from types import SimpleNamespace
        expected=linked_events(SimpleNamespace(rows=self.service.rows),today())
        self.assertEqual(linked_events(self.service,today()),expected)
        compact=self.service.selected_stage_links(today())
        self.assertEqual(len(compact),1)
        self.assertNotIn('candidates',compact[0])

    def test_compact_sources_keep_status_and_full_evidence_remains_available(self):
        with self.service.sessions.begin() as db:
            db.add(Batch(source_id=SOURCES[0]['id'],status='SUCCESS',finished_at=now(),
                         stats={'record_count':17,'source_base_date':'2026-10-13','large_detail':['detail']},
                         manifest=[{'url':'https://example.org/source','sha256':'abc'}]))
        full=self.client.get('/poc/home/api/sources').json()['items'][0]
        compact=self.client.get('/poc/home/api/sources?compact=true').json()['items'][0]
        for key in ['id','name','status','record_count','last_success']:
            self.assertEqual(full[key],compact[key])
        self.assertEqual(compact['snapshot_count'],1);self.assertEqual(compact['snapshots'],[])
        self.assertEqual(full['snapshots'][0]['sha256'],'abc')
        self.assertNotIn('large_detail',compact['stats'])

    def test_menu_caches_see_saved_revision_immediately(self):
        for endpoint,method,value in [('tree','tree',[]),('mappings','mappings',{'items':[]}),
                                     ('policy-monitor','policy_monitor',{'items':[]})]:
            with self.subTest(endpoint=endpoint),patch.object(HomeService,method,return_value=value) as build:
                url='/poc/home/api/'+endpoint
                self.assertEqual(self.client.get(url).headers['x-home-cache'],'MISS')
                self.assertEqual(self.client.get(url).headers['x-home-cache'],'HIT')
                with self.service.sessions.begin() as db:
                    upsert_revision(db,'collection_assessment','officer',endpoint,{'status':'REVIEW'},'test')
                self.assertEqual(self.client.get(url).headers['x-home-cache'],'MISS')
                self.assertEqual(build.call_count,2)

    def test_restart_scheduler_skips_recent_success_but_manual_remains_available(self):
        source=dict(id='demo_source',implemented=True,collection_mode='PUBLIC_FILE')
        with self.service.sessions.begin() as db:
            db.add(Batch(source_id=source['id'],status='SUCCESS',finished_at=now()))
        with patch('backend.service.SOURCES',[source]),patch.object(self.service,'collect_one',return_value={'status':'FAILED'}) as collect:
            result=self.service.collect_all(scheduled=True)
            self.assertEqual(result['results'],[]);collect.assert_not_called()
            self.service.collect_all(source_id=source['id'])
            collect.assert_called_once()

    def test_scheduler_collects_expired_sources_and_backs_off_failures(self):
        from datetime import timedelta
        source=dict(id='demo_source',implemented=True,collection_mode='PUBLIC_FILE')
        with self.service.sessions.begin() as db:
            db.add(Batch(source_id=source['id'],status='SUCCESS',finished_at=now()-timedelta(days=2),started_at=now()-timedelta(days=2)))
        with patch('backend.service.SOURCES',[source]),patch.object(self.service,'collect_one',return_value={'status':'FAILED'}) as collect,patch('backend.stage_evidence.refresh'),patch('backend.project_collection.refresh_links'):
            self.service.collect_all(scheduled=True)
            collect.assert_called_once()
        with self.service.sessions.begin() as db:
            db.add(Batch(source_id=source['id'],status='FAILED',finished_at=now()))
        with patch('backend.service.SOURCES',[source]),patch.object(self.service,'collect_one') as collect:
            self.service.collect_all(scheduled=True)
            collect.assert_not_called()


def test_document_index_only_reads_requested_evidence_and_handles_empty_selection():
    from backend.service import today
    e=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(e);s=HomeService(e)
    try:
        with s.sessions.begin() as db:
            first,_=upsert_revision(db,'document_evidence','official_document','wanted',dict(base_date=today().isoformat(),text='원문\x00'),'test')
            upsert_revision(db,'document_evidence','official_document','unrelated',dict(base_date=today().isoformat(),text='큰 원문'*10000),'test')
        rows=s.document_evidence_index(entity_ids=(first.entity_id,))
        assert [r['id'] for r in rows]==[first.entity_id]
        assert s.document_evidence_index(entity_ids=())==[]
        assert len(s.document_evidence_index())==2
    finally:e.dispose()


def test_project_enrichment_reused_across_filtered_views_without_mutation_leak():
    from backend.read_scope import projection_reads
    from backend.service import today
    e=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(e);s=HomeService(e)
    try:
        with patch.object(HomeService,'rows',return_value=[]) as rows:
            with projection_reads():
                assert s.projects(today(),policy_id='POL_2025_0907')==[]
                count=rows.call_count
                assert s.projects(today())==[]
                assert rows.call_count==count
            s.projects(today())
            assert rows.call_count>count
    finally:e.dispose()


def test_policy_statistics_projection_preserves_history_dates_and_reclassification():
    from datetime import timedelta
    from backend.service import today
    from backend.db import now
    engine=create_engine('sqlite://',poolclass=StaticPool);Base.metadata.create_all(engine)
    service=HomeService(engine);instant=now();day=today()
    try:
        with service.sessions.begin() as db:
            old,_=upsert_revision(db,'statistic','test','monthly',dict(base_date=day.isoformat(),statistic_metric='착공',units=8),'a')
            old.recorded_at=instant-timedelta(minutes=2)
            new,_=upsert_revision(db,'statistic','test','monthly',dict(base_date=day.isoformat(),statistic_metric='착공',units=12),'b')
            old.superseded_at=new.recorded_at=instant-timedelta(minutes=1)
            upsert_revision(db,'statistic','test','other',dict(base_date=day.isoformat(),statistic_metric='준공',units=99),'b')
            upsert_revision(db,'statistic','test','future',dict(base_date=(day+timedelta(days=1)).isoformat(),statistic_metric='착공',units=100),'b')
        historical=HomeService(engine,known_at=instant-timedelta(seconds=90))
        for reader,expected in [(service,12),(historical,8)]:
            selected=reader.policy_start_statistics(day)
            assert len(selected)==1 and selected[0]['units']==expected
            assert [r['units'] for r in reader.rows('statistic',day) if r.get('statistic_metric')=='착공']==[expected]
        with service.sessions.begin() as db:
            upsert_revision(db,'statistic','test','monthly',dict(base_date=day.isoformat(),statistic_metric='준공',units=12),'c')
        assert service.policy_start_statistics(day)==[]
    finally:engine.dispose()
