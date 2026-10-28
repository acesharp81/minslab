import unittest
from datetime import date
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from backend.db import Base
from backend.service import HomeService
from backend.project_collection import collection_matrix, refresh_links, save_assessment

class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine);self.s=HomeService(self.engine)
        self.project=dict(id='p1',name='고양창릉 A1',district='고양창릉',block='A1',region='경기도',municipality='고양시',
            source_id='lh_sale',revision_no=1,planned_units=100,base_date='2026-01-01',evidence_url='https://www.lh.or.kr/plan',
            stage='PLANNED_SUPPLY',mapping=dict(policy_id='POL_2025_0907',status='REVIEW',program_id='pr'),program='공공주택')
        self.patch=patch.object(self.s,'projects',return_value=[self.project]);self.patch.start();self.addCleanup(self.patch.stop)
    def cells(self):return collection_matrix(self.s)['items'][0]['cells']
    def test_coverage_projection_skips_audit_history_without_changing_metrics(self):
        from backend.requirements_status import build_status
        from backend.collection_repairs import enrich
        full=collection_matrix(self.s)
        expected=build_status(self.s,full)
        with patch('backend.collection_repairs.enrich',side_effect=AssertionError('coverage must not load audit history')):
            coverage=collection_matrix(self.s,include_link_history=False)
        self.assertEqual(coverage['items'][0]['cells'],full['items'][0]['cells'])
        self.assertEqual(build_status(self.s,coverage),expected)
        with patch('backend.collection_repairs.enrich',wraps=enrich) as history:
            collection_matrix(self.s)
            history.assert_called_once()

    def test_single_project_keeps_evidence_without_loading_other_candidate_archives(self):
        from backend.db import upsert_revision, entity_id
        selected=dict(source_id='official_document',source_entity_id='doc',event_date='2026-01-01',
                      method='OFFICIAL_DOCUMENT',basis='공식 승인',evidence_url='https://example.org/permit',units=100)
        with self.s.sessions.begin() as db:
            for pid in ('p1','other'):
                upsert_revision(db,'stage_evidence','stage_match',pid+':APPROVAL',
                    dict(project_id=pid,stage='APPROVAL',status='CONFIRMED',base_date='2026-01-01',
                         selected=selected,actor='담당자',basis='확인',candidates=[{'text':'원문'*10000}]),'test')
        full=collection_matrix(self.s,include_link_history=False)
        original=self.s.rows
        def scoped(kind,*args,**kwargs):
            if kind=='stage_evidence':
                self.assertEqual(set(kwargs['entity_ids']),
                    {entity_id(kind,'stage_match','p1:'+stage) for stage in ('BUSINESS','APPROVAL')})
            return original(kind,*args,**kwargs)
        with patch.object(self.s,'rows',side_effect=scoped):
            detail=collection_matrix(self.s,project_ids=('p1',),include_link_history=False)
        self.assertEqual(detail,full)
        self.assertTrue(detail['items'][0]['cells']['APPROVAL']['actual_available'])

    def test_equal_months_keep_distinct_official_documents_and_partial_scopes(self):
        bridges=[]
        for i,units in enumerate((715,590)):
            bridges.append(dict(id='b'+str(i),project_id='p1',source_id='official_document',
                source_entity_id='doc'+str(i),source_revision_no=1,evidence_url='https://example.org/'+str(i),
                status='REVIEW',basis='공식 원문 대조',facts=[dict(stage='SUPPLY',kind='PLAN',date='2026-08',
                    basis='동일한 본청약 예정월',scope_partial=True,scope_units=units,scope_label=str(units)+'호')]))
        with patch('backend.evidence_bridge.by_project',return_value={'p1':bridges}):
            cell=self.cells()['SUPPLY']
        self.assertEqual(len(cell['targets']),2)
        self.assertEqual({t['scope_units'] for t in cell['targets']},{715,590})
        self.assertTrue(all(t['reference_only'] for t in cell['targets']))

    def test_completion_bridge_stays_in_construction_not_move_in(self):
        bridge=dict(id='completion',project_id='p1',source_id='official_document',
            source_entity_id='doc1',source_revision_no=1,evidence_url='https://example.org/1',
            status='CONFIRMED',basis='공식 준공 근거',facts=[dict(stage='COMPLETION',
                kind='ACTUAL',date='2026-01-01',basis='실제 준공',units=100)])
        with patch('backend.evidence_bridge.by_project',return_value={'p1':[bridge]}):
            cells=self.cells()
        self.assertTrue(cells['CONSTRUCTION']['actual_available'])
        self.assertFalse(cells['MOVE_IN']['actual_available'])
        fact=next(x for x in cells['CONSTRUCTION']['sources'] if x.get('bridge_id')=='completion')
        self.assertEqual(fact['milestone'],'COMPLETION')
        self.assertEqual(fact['units'],100)

    def test_historical_plan_remains_reference_in_targets_and_editor(self):
        from backend.project_profile import target_default
        bridge=dict(id='historical',project_id='p1',source_id='official_document',source_entity_id='sh',
            source_revision_no=1,evidence_url='https://example.org/sh',status='CONFIRMED',basis='SH 과거계획',
            facts=[dict(stage='CONSTRUCTION',kind='PLAN',date='2025-11',precision='MONTH',
                        milestone='CONSTRUCTION',units=8,reference_only=True,basis='당시 계획')])
        with patch('backend.evidence_bridge.by_project',return_value={'p1':[bridge]}):
            cell=self.cells()['CONSTRUCTION']
        target=next(t for t in cell['targets'] if t.get('bridge_id')=='historical')
        self.assertTrue(target['reference_only'])
        self.assertEqual(target['date'],'2025-11')
        self.assertEqual(target_default(cell,'CONSTRUCTION')['due_date'],'')
        self.assertFalse(cell['actual_available'])

    def test_partial_plan_without_display_label_still_loads_and_stays_reference(self):
        bridge=dict(id='partial',project_id='p1',source_id='official_document',source_entity_id='partial-doc',
            source_revision_no=1,evidence_url='https://example.org/partial',status='CONFIRMED',basis='부분 계획',
            facts=[dict(stage='SUPPLY',kind='PLAN',date='2026-12',units=8,scope_partial=True,basis='일부 모집')])
        with patch('backend.evidence_bridge.by_project',return_value={'p1':[bridge]}):
            cell=self.cells()['SUPPLY']
        t=next(t for t in cell['targets'] if t.get('bridge_id')=='partial')
        self.assertTrue(t['reference_only'])
        self.assertEqual(t['units'],8)
        self.assertIn('부분 범위',t['label'])

    def test_missing_never_infers_unplanned_or_zero(self):
        c=self.cells();self.assertEqual(c['SUPPLY']['status'],'COLLECTION_REQUIRED')
        self.assertEqual(c['MOVE_IN']['status'],'METHOD_UNKNOWN')
        self.assertTrue(all(v['status']!='NOT_PLANNED' for v in c.values()))
        self.assertNotIn('units',c['MOVE_IN'])
    def test_progress_zero_is_acquired_not_missing(self):
        self.project.update(progress_pct=0,progress_date='2026-01-01')
        c=self.cells()['CONSTRUCTION'];self.assertEqual(c['status'],'ACQUIRED');self.assertEqual(c['sources'][0]['pct'],0)
        self.assertTrue(c['actual_available'])
    def test_plan_does_not_prove_actual(self):
        self.project['rows']=[dict(units=100,supply_month='2027-01',move_in_month='2028-01')]
        c=self.cells();self.assertTrue(c['MOVE_IN']['plan_available']);self.assertFalse(c['MOVE_IN']['actual_available'])
    def test_added_actual_changes_coverage_without_inflating_acquired_cells(self):
        self.project.update(source_id='lh_construction',start_plan_date='2026-01-01',completion_plan_date='2028-01-01')
        before=self.cells()['CONSTRUCTION']
        self.project.update(start_actual_date='2026-02-01')
        after=self.cells()['CONSTRUCTION']
        self.assertEqual(before['status'],after['status'])
        self.assertEqual(after['status'],'ACQUIRED')
        self.assertTrue(before['dated_plan_available'])
        self.assertFalse(before['actual_available']);self.assertTrue(after['actual_available'])
        self.assertGreater(after['evidence_count'],before['evidence_count'])

    def test_assessment_persist_conflict_release_and_evidence_wins(self):
        a=save_assessment(self.s,'p1','CONSTRUCTION',0,'NOT_PLANNED','담당기관 확인 · 아직 공사계획 미수립')
        self.assertEqual(self.cells()['CONSTRUCTION']['status'],'NOT_PLANNED')
        self.assertTrue(save_assessment(self.s,'p1','CONSTRUCTION',0,'METHOD_UNKNOWN','제공처 조사')['conflict'])
        self.project['start_actual_date']='2026-02-01';c=self.cells()['CONSTRUCTION']
        self.assertEqual(c['status'],'ACQUIRED');self.assertTrue(c['assessment_conflict'])
        del self.project['start_actual_date'];save_assessment(self.s,'p1','CONSTRUCTION',a['revision_no'],'RELEASED','기존 판정 재검토')
        self.assertEqual(self.cells()['CONSTRUCTION']['status'],'COLLECTION_REQUIRED')
    def test_no_bare_unplanned_assessment(self):
        with self.assertRaises(ValueError):save_assessment(self.s,'p1','SUPPLY',0,'NOT_PLANNED',' ')
        with self.assertRaises(ValueError):save_assessment(self.s,'other','SUPPLY',0,'NOT_PLANNED','확인')
    def test_later_empty_search_does_not_erase_known_unlinked_source(self):
        original=self.s.rows
        findings=[dict(project_ids=['p1'],checked_at='2026-10-13',iteration=2,status='LINK_PENDING',link_stages=['SUPPLY']),
                  dict(project_ids=['p1'],checked_at='2026-10-13',iteration=3,status='NO_PUBLIC_MATCH')]
        with patch.object(self.s,'rows',side_effect=lambda kind,*args,**kw:findings if kind=='collection_research' else original(kind,*args,**kw)):
            cell=self.cells()['SUPPLY']
        self.assertEqual(cell['status'],'LINK_REQUIRED');self.assertEqual(cell['progress']['code'],'LINK_REQUIRED')

    def test_read_never_matches_or_writes(self):
        with patch('backend.project_collection.linked_notices',side_effect=AssertionError('recomputed')):
            collection_matrix(self.s);collection_matrix(self.s)
        self.assertEqual(self.s.rows('collection_link'),[])
    def test_stored_link_survives_new_source_and_repeat_refresh(self):
        notice=dict(id='n1',source_id='cheongyak',revision_no=1,region='경기도',name='고양창릉 A1BL 공공분양',
            developer='한국토지주택공사',source_date='2026-02-01',units=100,move_in_plan_month='202801',evidence_url='https://www.applyhome.co.kr/n1')
        original=self.s.rows
        def rows(kind,*args,**kw):return [notice] if kind=='notice' else original(kind,*args,**kw)
        with patch.object(self.s,'rows',side_effect=rows):
            refresh_links(self.s);saved=original('collection_link');self.assertEqual(sum(bool(r['links']) for r in saved),2)
            notice['id']='n2';notice['source_date']='2026-03-01'
            with patch('backend.project_collection.linked_notices',side_effect=AssertionError('recomputed')):
                self.assertEqual(refresh_links(self.s),{'preserved':2})
            c=self.cells()['SUPPLY'];self.assertEqual(c['sources'][0]['source_entity_id'],'n1');self.assertTrue(c['review_required'])
    def test_unknown_provider_and_released_stage_link(self):
        self.project['source_id']='sh_inventory'
        self.assertEqual(self.cells()['CONSTRUCTION']['status'],'METHOD_UNKNOWN')
        original=self.s.rows
        link=dict(project_id='p1',stage='APPROVAL',status='RELEASED',selected=dict(source_id='building_hub',basis='허가',event_date='2026-01-01'))
        with patch.object(self.s,'rows',side_effect=lambda kind,*args,**kw:[link] if kind=='stage_evidence' else original(kind,*args,**kw)):
            self.assertFalse(self.cells()['APPROVAL']['sources'])

    def test_prerequisite_is_visible_as_inference_not_actual_permit(self):
        original=self.s.rows
        link=dict(project_id='p1',stage='APPROVAL',status='REVIEW',selected=dict(source_id='lh_construction',basis='착공 선행 추정',observed_on='2026-01-01',method='PREREQUISITE'))
        with patch.object(self.s,'rows',side_effect=lambda kind,*args,**kw:[link] if kind=='stage_evidence' else original(kind,*args,**kw)):
            c=self.cells()['APPROVAL'];self.assertTrue(c['inferred_available']);self.assertFalse(c['actual_available']);self.assertTrue(c['review_required'])

    def test_completion_is_only_a_construction_target(self):
        self.project.update(source_id='lh_construction',start_actual_date='2023-11-28',
                            start_plan_date='2023-11-28',completion_plan_date='2026-08-22')
        c=self.cells()
        self.assertFalse(c['SUPPLY']['targets'])
        completion=[t for t in c['CONSTRUCTION']['targets'] if t['label']=='예상 준공']
        self.assertEqual(completion[0]['date'],'2026-08-22')
        self.assertFalse(c['SUPPLY']['sources'])
        self.assertFalse(c['SUPPLY']['plan_available'])
        self.assertFalse(c['SUPPLY']['actual_available'])
        self.assertEqual(c['SUPPLY']['status'],'COLLECTION_REQUIRED')
        self.assertEqual({t['label'] for t in c['CONSTRUCTION']['targets']},{'착공 예정','예상 준공'})

    def test_incheon_and_progress_schedule_fields_are_visible(self):
        for sid in ('lh_incheon_construction','lh_progress'):
            with self.subTest(sid=sid):
                self.project.update(source_id=sid,start_plan_date='2027-02-02',completion_plan_date='2029-04-30')
                c=self.cells()
                self.assertEqual([t['date'] for t in c['CONSTRUCTION']['targets']],['2027-02-02','2029-04-30'])
                self.assertFalse(c['CONSTRUCTION']['actual_available'])
                self.assertFalse(c['MOVE_IN']['targets'])  # Completion is never move-in.

    def test_gh_half_year_uses_authorized_period_end(self):
        self.project.update(source_id='gh_supply_plan',source_move_in_label='2026년 하반기 예정',source_supply_label='2026년 5월')
        c=self.cells();t=c['MOVE_IN']['targets'][0]
        self.assertEqual(t['date'],'2026-12');self.assertEqual(t['date_label'],'2026년 하반기 예정')
        self.assertFalse(c['MOVE_IN']['actual_available'])
        self.assertEqual(c['MOVE_IN']['status'],'ACQUIRED')

    def test_plan_and_actual_are_separate_and_unknown_occupancy_is_grouped(self):
        self.project['rows']=[dict(units=100,supply_month='2027-01',move_in_month='2028-01')]
        result=collection_matrix(self.s);g=next(g for g in result['gap_groups'] if g['stage']=='MOVE_IN')
        self.assertEqual(g['owner'],'LH');self.assertEqual(g['code'],'UPCOMING')
        self.assertEqual(g['planned_projects'],1);self.assertEqual(g['project_ids'],['p1'])
        self.project['move_in_actual_date']='2026-01-01'
        result=collection_matrix(self.s)
        self.assertFalse(any(g['stage']=='MOVE_IN' for g in result['gap_groups']))

    def test_groups_count_projects_and_preserve_distinct_assessment_reasons(self):
        other=dict(self.project,id='p2',name='다른 사업')
        with patch.object(self.s,'projects',return_value=[self.project,other]):
            result=collection_matrix(self.s);g=next(g for g in result['gap_groups'] if g['stage']=='MOVE_IN')
            self.assertEqual(g['project_count'],2)
            save_assessment(self.s,'p2','MOVE_IN',0,'METHOD_UNKNOWN','해당 사업 관리기관에 확인 중')
            result=collection_matrix(self.s);groups=[g for g in result['gap_groups'] if g['stage']=='MOVE_IN']
            self.assertEqual(len(groups),2)
            self.assertEqual(sum(g['project_count'] for g in groups),2)

    def test_unplanned_assessment_is_not_unknown_collection_method(self):
        save_assessment(self.s,'p1','MOVE_IN',0,'NOT_PLANNED','담당기관 확인: 아직 입주계획 미수립')
        result=collection_matrix(self.s)
        self.assertFalse(any(g['stage']=='MOVE_IN' for g in result['gap_groups']))

    def test_csv_cell_preserves_dates_and_reference_semantics(self):
        from backend.project_collection import collection_cell_text
        self.project.update(source_id='lh_construction',completion_plan_date='2026-08-22')
        value=collection_cell_text(self.cells()['CONSTRUCTION'])
        self.assertIn('예상 준공: 2026-08-22',value)
        self.assertNotIn('공급일 대체 아님',value);self.assertIn('실적 미확인',value)


    def test_missing_move_in_column_does_not_count_as_acquired(self):
        self.project['rows']=[dict(units=100,supply_month='2026-06',move_in_month=None)]
        c=self.cells()['MOVE_IN']
        self.assertEqual(c['status'],'METHOD_UNKNOWN')
        self.assertEqual(c['evidence_count'],0)
        self.assertFalse(c['targets']);self.assertFalse(c['actual_available'])
        self.assertEqual(c['sources'][0]['kind'],'PLAN_STATUS')
        self.assertEqual(c['sources'][0]['schedule_status'],'NOT_PROVIDED')
        self.assertIn('항목 없음',c['sources'][0]['basis'])

    def test_explicit_undecided_is_preserved_not_missing_or_dated(self):
        self.project.update(source_id='lh_rent',rows=[dict(units=100,move_in_month=None,
                            move_in_raw='미정',move_in_field_present=True)])
        c=self.cells()['MOVE_IN']
        self.assertEqual(c['status'],'ACQUIRED');self.assertTrue(c['plan_available'])
        self.assertEqual(c['targets'][0]['date_label'],'미정')
        self.assertEqual(c['targets'][0]['schedule_status'],'UNDETERMINED')
        self.assertIsNone(c['targets'][0]['date']);self.assertFalse(c['actual_available'])
        self.assertFalse(c['dated_plan_available']);self.assertGreater(c['evidence_count'],0)
        from backend.roadmap import source_events
        self.assertFalse(source_events(self.project,date(2026,10,12)))

    def test_blank_and_legacy_lost_raw_values_do_not_prove_undecided(self):
        for raw,status in [('', 'EMPTY'),(None,'UNVERIFIED')]:
            self.project.update(source_id='lh_rent',rows=[dict(units=100,move_in_month=None,move_in_raw=raw)])
            c=self.cells()['MOVE_IN']
            self.assertFalse(c['targets'])
            self.assertEqual(c['sources'][0]['schedule_status'],status)
            self.assertNotEqual(c['status'],'ACQUIRED')
            self.assertFalse(c['actual_available'])


class CollectionApiTests(unittest.TestCase):
    def test_read_export_and_auth(self):
        from fastapi.testclient import TestClient
        from backend.app import create_app
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine)
        with TestClient(create_app(engine,auto_collect=False)) as c:
            r=c.get('/poc/home/api/project-collection');self.assertEqual(r.status_code,200);self.assertEqual(r.json()['total'],0)
            r=c.get('/poc/home/api/project-collection/export.csv');self.assertEqual(r.status_code,200);self.assertIn('정책',r.text)
            r=c.post('/poc/home/api/admin/project-collection/assessment',json=dict(project_id='p1',stage='SUPPLY',revision_no=0,status='NOT_PLANNED',basis='기관 확인'))
            self.assertEqual(r.status_code,401)
