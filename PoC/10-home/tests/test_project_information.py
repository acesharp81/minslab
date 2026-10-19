import unittest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from backend.db import Base,Mapping,ProgramMapping,upsert_revision
from backend.service import HomeService
from backend.project_profile import save,view,profile,fingerprint
from backend.project_collection import collection_matrix
from backend.delivery_operations import schedule_goals
from backend.api_samples import today

class ProjectInformationTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine);self.s=HomeService(self.engine)
        with self.s.sessions.begin() as db:
            row,_=upsert_revision(db,'project','lh_construction','editor-test',dict(name='검증 A1',program='공공주택',region='경기도',municipality='고양시',base_date='2026-01-01',planned_units=100,progress_pct=20,progress_date='2026-01-01',stage='CONSTRUCTION',stage_label='공사 진행',evidence_url='https://example.org',start_actual_date='2025-01-01',completion_plan_date='2028-01-01'),'test')
            self.pid=row.entity_id
            db.add(ProgramMapping(id='PRG_TEST',name='프로그램',seed_policy_id='POL_2025_0907',policy_id='POL_2025_0907',status='REVIEW',revision_no=1,basis='문서',evidence_url='https://example.org'))
            db.add(Mapping(project_id=self.pid,program_id='PRG_TEST',policy_id='POL_2025_0907',status='REVIEW',revision_no=1,basis='원천',evidence_url='https://example.org'))
    def test_single_project_projection_preserves_full_profile_and_evidence(self):
        with self.s.sessions.begin() as db:
            other,_=upsert_revision(db,'project','lh_construction','other',dict(name='다른 사업',region='경기도',base_date='2026-01-01',planned_units=77,stage='CONSTRUCTION',stage_label='공사 진행'), 'test')
            db.add(Mapping(project_id=other.entity_id,program_id='PRG_TEST',policy_id='POL_2025_0907',status='REVIEW',revision_no=1,basis='원천',evidence_url='https://example.org'))
        full=collection_matrix(self.s)
        scoped=collection_matrix(self.s,project_ids=(self.pid,))
        self.assertGreater(full['total'],scoped['total'])
        self.assertEqual(scoped['total'],1)
        self.assertEqual(scoped['items'][0],next(r for r in full['items'] if r['id']==self.pid))
        self.assertEqual(view(self.s,self.pid,full),view(self.s,self.pid,scoped))
        self.assertEqual(collection_matrix(self.s,project_ids=())['items'],[])

    def test_cached_profile_invalidates_after_officer_and_source_edits(self):
        from fastapi.testclient import TestClient
        from backend.app import create_app
        with TestClient(create_app(self.engine,auto_collect=False)) as client:
            path='/poc/home/api/project-information/'+self.pid
            first=client.get(path)
            self.assertEqual(first.status_code,200)
            self.assertEqual(client.get(path).headers['x-home-cache'],'HIT')
            self.edit({'planned_units':120})
            edited=client.get(path)
            self.assertEqual(edited.headers['x-home-cache'],'MISS')
            self.assertEqual(edited.json()['fields']['planned_units']['value'],120)
            self.assertEqual(client.get(path).headers['x-home-cache'],'HIT')
            row=self.s.rows('project')[0]
            with self.s.sessions.begin() as db:
                upsert_revision(db,'project','lh_construction','editor-test',dict(row,contractor='변경 시공사'),'source update')
            self.assertEqual(client.get(path).headers['x-home-cache'],'MISS')
            self.assertEqual(client.get('/poc/home/api/project-information/missing').status_code,404)

    def edit(self,changes=None,version=0,**kw):return save(self.s,self.pid,version,1,changes or {},'담당자','근거 대조',**kw)
    def test_priority_restore_and_source_immutable(self):
        self.edit({'name':'수정 사업','planned_units':120,'progress_pct':25,'progress_date':'2026-05-01'})
        p=self.s.projects()[0];self.assertEqual(p['name'],'수정 사업');self.assertEqual(p['planned_units'],120)
        self.assertEqual(self.s.rows('project')[0]['planned_units'],100)
        self.assertEqual(p['source_values']['progress_pct'],20)
        self.assertTrue(self.edit({'name':'충돌'},0)['conflict'])
        self.edit({'name':None,'planned_units':None},1)
        self.assertEqual(self.s.projects()[0]['name'],'검증 A1')
    def test_manual_progress_retains_the_original_source_in_evidence(self):
        self.edit({'progress_pct':35,'progress_date':'2026-05-01'})
        cell=collection_matrix(self.s)['items'][0]['cells']['CONSTRUCTION']
        source=[r for r in cell['sources'] if r.get('pct') is not None and r['source_id']!='officer']
        manual=[r for r in cell['sources'] if r.get('pct') is not None and r['source_id']=='officer']
        self.assertEqual(source[0]['pct'],20);self.assertEqual(manual[0]['pct'],35)
        self.assertEqual(manual[0]['input_status'],'CONFIRMED')
        self.assertEqual(cell['management']['progress_pct']['pct'],35)

    def test_schedule_integrates_and_failed_edit_rolls_back_mapping(self):
        mapping=dict(program_id='PRG_TEST',program_revision_no=1,status='CONFIRMED')
        with self.assertRaises(ValueError):self.edit({'name':'반영 금지'},mapping=mapping,schedules={'COMPLETION':dict(revision_no=0,due_date='2029-01-01',units=101)})
        self.assertEqual(profile(self.s,self.pid),{})
        self.assertEqual(self.s.projects()[0]['mapping']['status'],'REVIEW')
        self.edit(schedules={'COMPLETION':dict(revision_no=0,due_date='2029-01-01',units=100)})
        self.assertEqual(schedule_goals(self.s,today())[0]['units'],100)
        self.assertEqual(self.s.projects()[0]['construction_plan']['completion_date'],'2029-01-01')
        with self.assertRaises(ValueError):self.edit({'planned_units':50},1)
        cell=collection_matrix(self.s)['items'][0]['cells']['CONSTRUCTION']
        self.assertTrue(any(t['date']=='2029-01-01' for t in cell['targets']))
        self.edit(version=1,schedules={'COMPLETION':dict(revision_no=1,reset=True)})
        self.assertEqual(schedule_goals(self.s,today()),[])
    def test_review_is_pinned_and_unknown_cannot_be_approved(self):
        cell=collection_matrix(self.s)['items'][0]['cells']['CONSTRUCTION']
        self.edit(approvals={'CONSTRUCTION':fingerprint(cell)})
        self.assertTrue(view(self.s,self.pid,collection_matrix(self.s))['cells']['CONSTRUCTION']['review_current'])
        self.edit({'progress_pct':35},1)
        self.assertFalse(view(self.s,self.pid,collection_matrix(self.s))['cells']['CONSTRUCTION']['review_current'])
        with self.assertRaises(ValueError):self.edit(version=2,approvals={'MOVE_IN':fingerprint({'sources':[]})})
        self.assertEqual(self.s.projects()[0]['mapping']['status'],'REVIEW')
    def test_validation_and_parent_revision(self):
        for changes in ({'planned_units':True},{'progress_pct':101},{'progress_pct':float('nan')},{'name':''},{'id':'fake'},{'progress_date':'2099-01-01'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.edit(changes)
        self.assertTrue(self.edit({'name':'미저장'},mapping=dict(program_id='PRG_TEST',program_revision_no=2,status='CONFIRMED'))['conflict'])
        self.assertEqual(profile(self.s,self.pid),{})
    def test_api_guest_read_admin_write_conflict(self):
        import os,time,hmac,hashlib
        from fastapi.testclient import TestClient
        from backend.app import create_app
        path='/poc/home/api/admin/project-information/'+self.pid
        payload=dict(revision_no=0,mapping_revision_no=1,changes={'name':'관리자 사업'},actor='담당자',reason='문서 대조')
        with patch.dict(os.environ,{'POC10_INTERNAL_SECRET':'test'}),TestClient(create_app(self.engine,auto_collect=False)) as c:
            self.assertEqual(c.get('/poc/home/api/project-workspace').status_code,200)
            self.assertEqual(c.post(path,json=payload).status_code,401)
            stamp=str(int(time.time()));sig=hmac.new(b'test',f'{stamp}:POST:{path}'.encode(),hashlib.sha256).hexdigest()
            headers={'x-home-admin':stamp+':'+sig}
            self.assertEqual(c.post(path,json=payload,headers=headers).status_code,200)
            self.assertEqual(c.post(path,json=payload,headers=headers).status_code,409)
            info=c.get('/poc/home/api/project-information/'+self.pid)
            self.assertEqual(info.status_code,200);self.assertEqual(info.json()['project']['name'],'관리자 사업')

    def test_default_dates_preserve_month_year_and_never_turn_actual_into_goal(self):
        from backend.project_profile import target_default
        cell=dict(targets=[dict(date='2028-02',units=381,milestone='SUPPLY')],sources=[dict(kind='ACTUAL',date='2026-02-27',units=381)])
        d=target_default(cell,'SUPPLY');self.assertEqual(d['due_date'],'2028-02-29');self.assertEqual(d['source_date'],'2028-02');self.assertEqual(d['precision'],'MONTH')
        self.assertEqual(cell['targets'][0]['date'],'2028-02')
        self.assertEqual(target_default(dict(targets=[dict(date='2030')]),'MOVE_IN')['due_date'],'2030-12-31')
        self.assertEqual(target_default(dict(targets=[],sources=cell['sources']),'SUPPLY')['due_date'],'')
        cell['targets'].append(dict(date='2029-02',milestone='SUPPLY',units=381))
        self.assertEqual(target_default(cell,'SUPPLY')['due_date'],'')
        self.assertEqual(target_default(dict(targets=[dict(date='2028-02',reference_only=True)]),'MOVE_IN')['due_date'],'')
        saved=dict(status='CONFIRMED',due_date='2029-06-01',units=100)
        self.assertEqual(target_default(cell,'SUPPLY',saved)['due_date'],'2029-06-01')

    def test_managed_progress_keeps_sources_and_validates_actuals(self):
        from backend.project_profile import progress_events
        self.edit(progress={'SUPPLY':dict(event_date='2026-02-01',units=75),'APPROVAL':dict(event_date='',units=100)})
        data=view(self.s,self.pid,collection_matrix(self.s))
        self.assertEqual(data['progress_defaults']['SUPPLY']['units'],75)
        self.assertTrue(data['progress_defaults']['SUPPLY']['manual'])
        self.assertEqual(len(progress_events(self.s)),1)  # Undated observation cannot invent a chart date.
        facts=data['cells']['SUPPLY']['sources']
        self.assertTrue(any(r.get('manual_priority') and r['units']==75 for r in facts))
        self.assertEqual(self.s.rows('project')[0]['progress_pct'],20)
        for value in ({'event_date':'2099-01-01','units':10},{'event_date':'2026-01-01','units':101},{'event_date':'2026-01-01','units':True}):
            with self.subTest(value=value),self.assertRaises(ValueError):self.edit(version=1,progress={'SUPPLY':value})
        self.assertTrue(self.edit(version=0,progress={'SUPPLY':None})['conflict'])
        self.edit(version=1,progress={'SUPPLY':None})
        self.assertEqual(progress_events(self.s),[])

    def test_progress_default_does_not_infer_from_document_or_partial_scope(self):
        from backend.project_profile import progress_default
        facts=[dict(kind='DOCUMENT',date='2026-01-01',units=100),dict(kind='ACTUAL',date='2026-02-01',units=30,scope_partial=True)]
        d=progress_default({'sources':facts},'SUPPLY')
        self.assertEqual(d['event_date'],'');self.assertIsNone(d['units'])
        facts.extend([dict(kind='ACTUAL',date='2026-03-01',units=100),dict(kind='ACTUAL',date='2026-04-01',units=90)])
        self.assertEqual(progress_default({'sources':facts},'SUPPLY')['display_note'],'원천 상충 · 근거 확인')

    def test_start_date_is_not_progress_observation_date(self):
        from backend.project_profile import progress_default,linked_progress
        facts=[dict(kind='ACTUAL',milestone='CONSTRUCTION',date='2026-02-01',review_status='REVIEW'),
               dict(kind='ACTUAL',date='2026-07-01',pct=0,source_id='lh_construction',review_status='REVIEW')]
        result=progress_default(dict(sources=facts),'CONSTRUCTION')
        self.assertEqual(result['event_date'],'2026-02-01')
        self.assertIsNone(result['units'])  # No project capacity inferred as an actual quantity.
        self.assertEqual(result['display_note'],'수집 실적 · 연결 검토 중')
        self.assertEqual(linked_progress(dict(sources=facts))['pct'],0)
        facts.append(dict(kind='ACTUAL',date='2026-07-01',pct=5))
        self.assertIsNone(linked_progress(dict(sources=facts)))
        facts[-1]['scope_partial']=True
        self.assertEqual(linked_progress(dict(sources=facts))['pct'],0)

    def test_linked_zero_progress_defaults_preserve_source_and_manual_priority(self):
        raw=self.s.rows('project')[0]
        with self.s.sessions.begin() as db:
            upsert_revision(db,'project','lh_construction','editor-test',dict(raw,progress_pct=None,progress_date=None),'test')
        matrix=collection_matrix(self.s)
        cell=matrix['items'][0]['cells']['CONSTRUCTION']
        cell['sources'].append(dict(kind='ACTUAL',date='2026-07-01',pct=0,source_id='lh_construction',review_status='REVIEW',evidence_url='https://example.org/linked'))
        data=view(self.s,self.pid,matrix)
        self.assertEqual(data['fields']['progress_pct']['value'],0)
        self.assertEqual(data['fields']['progress_date']['value'],'2026-07-01')
        self.assertTrue(data['fields']['progress_pct']['review_required'])
        self.assertEqual(data['fields']['progress_pct']['evidence'][0]['origin'],'LINKED_SOURCE')
        self.assertIsNone(data['project']['source_values']['progress_pct'])
        self.edit({'progress_pct':10,'progress_date':'2026-08-01'})
        data=view(self.s,self.pid,matrix)
        self.assertEqual(data['fields']['progress_pct']['value'],10)
        self.assertEqual(data['fields']['progress_date']['value'],'2026-08-01')
        self.assertEqual(data['fields']['progress_pct']['evidence'][1]['origin'],'LINKED_SOURCE')
        self.assertIsNone(self.s.rows('project')[0]['progress_pct'])

    def test_sale_plan_quantity_reaches_editor_without_summing_repeated_totals(self):
        from backend.project_profile import target_default
        from backend.evidence_bridge import facts
        raw=dict(name='검증 A1',program='공공주택',region='경기도',municipality='고양시',base_date='2026-01-01',planned_units=548,
                 supply_month='2026-09',stage='SUPPLY',rows=[dict(area=area,units=units,total_units=548,supply_month='2026-09') for area,units in [('59',382),('74',50),('84',116)]])
        with self.s.sessions.begin() as db:
            row,_=upsert_revision(db,'project','lh_sale','sale-test',raw,'test')
            db.add(Mapping(project_id=row.entity_id,program_id='PRG_TEST',policy_id='POL_2025_0907',status='REVIEW',revision_no=1,basis='원천',evidence_url='https://example.org'))
            pid=row.entity_id
        matrix=collection_matrix(self.s)
        cell=next(r for r in matrix['items'] if r['id']==pid)['cells']['SUPPLY']
        target=target_default(cell,'SUPPLY')
        self.assertEqual(target['due_date'],'2026-09-30')
        self.assertEqual(target['units'],548)
        row=next(r for r in self.s.rows('project') if r['id']==pid)
        self.assertEqual(next(r for r in facts(row,today()) if r.get('milestone')=='SUPPLY')['units'],548)

    def test_missing_actuals_distinguish_collected_plans_and_states(self):
        from backend.project_profile import progress_default
        for kind,note in [('STATE','상태 근거 확보'),('DOCUMENT','문서 확보'),('PLAN','예정 정보 확보')]:
            result=progress_default(dict(sources=[dict(kind=kind,date='2026-01-01',units=548)]),'BUSINESS')
            self.assertEqual(result['event_date'],'');self.assertIsNone(result['units'])
            self.assertIn(note,result['display_note'])
        result=progress_default(dict(sources=[dict(kind='PLAN_STATUS',schedule_status='NOT_PROVIDED')]),'MOVE_IN')
        self.assertIn('원천 항목 미제공',result['display_note'])

    def test_plan_quantity_repair_uses_pinned_revision_and_preserves_review(self):
        import runpy
        from pathlib import Path
        restore=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/restore-bridge-plan-units.py'))['restore']
        source=self.s.rows('project')[0]
        payload=dict(base_date=today().isoformat(),project_id='target',source_entity_id=self.pid,source_revision_no=1,relation_type='SAME_SCOPE',status='REVIEW',units=100,
                     facts=[dict(stage='CONSTRUCTION',kind='PLAN',date='2028-01-01',milestone='COMPLETION',basis='준공 예정'),
                            dict(stage='CONSTRUCTION',kind='ACTUAL',date='2025-01-01',milestone='CONSTRUCTION')])
        with self.s.sessions.begin() as db:
            upsert_revision(db,'evidence_bridge','cross_source','target:'+self.pid,payload,'test')
            upsert_revision(db,'project','lh_construction','editor-test',dict(source,planned_units=120),'test')
            upsert_revision(db,'evidence_bridge','cross_source','partial:'+self.pid,dict(payload,project_id='partial',relation_type='PARTIAL_SCOPE'),'test')
        self.assertEqual(restore(self.s)['facts'],1)
        self.assertNotIn('units',self.s.rows('evidence_bridge')[0]['facts'][0])
        self.assertEqual(restore(self.s,True)['facts'],1)
        result=next(r for r in self.s.rows('evidence_bridge') if r['project_id']=='target')
        self.assertEqual(result['facts'][0]['units'],100)
        self.assertNotIn('units',result['facts'][1])
        self.assertEqual(result['status'],'REVIEW')
        self.assertEqual(result['source_revision_no'],1)
        self.assertEqual(restore(self.s,True)['facts'],0)

    def test_legacy_bridge_plan_restore_requires_equal_source_and_target_scope(self):
        import runpy
        from pathlib import Path
        restore=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/restore-bridge-plan-units.py'))['restore']
        payload=dict(base_date=today().isoformat(),project_id=self.pid,source_entity_id=self.pid,source_revision_no=1,
                     matching_version='district-block-units-v1',status='REVIEW',units=100,
                     facts=[dict(stage='CONSTRUCTION',kind='PLAN',date='2028-01-01',milestone='COMPLETION',basis='준공 예정')])
        with self.s.sessions.begin() as db:upsert_revision(db,'evidence_bridge','cross_source',self.pid+':'+self.pid,payload,'test')
        self.assertEqual(restore(self.s)['facts'],1)
        raw=self.s.rows('project')[0]
        with self.s.sessions.begin() as db:upsert_revision(db,'project','lh_construction','editor-test',dict(raw,planned_units=80),'test')
        self.assertEqual(restore(self.s,True)['facts'],0)

    def test_partial_stage_quantities_are_explicit_and_source_goals_stay_separate(self):
        self.edit(progress={'CONSTRUCTION':dict(event_date='2026-02-01',units=60),'MOVE_IN':dict(event_date='2026-09-01',units=20)})
        result=view(self.s,self.pid,collection_matrix(self.s))
        self.assertEqual(result['progress_defaults']['CONSTRUCTION']['units'],60)
        self.assertEqual(result['progress_defaults']['MOVE_IN']['units'],20)
        self.assertEqual(self.s.rows('project')[0]['planned_units'],100)
        with self.assertRaises(ValueError):self.edit(version=1,progress={'CONSTRUCTION':dict(event_date='2026-02-01',units=101)})

    def test_collected_representative_address_is_visible_without_overwriting_source(self):
        with self.s.sessions.begin() as db:
            upsert_revision(db,'project_location','vworld',self.pid,dict(project_id=self.pid,base_date=today().isoformat(),status='REVIEW',
                latitude=37.5,longitude=127.1,coordinate_basis='APPROXIMATE_ADDRESS',address_original='서울특별시 강남구 일원동 711',
                location_label='대표 지번 근사 위치 · 사업 경계 아님',evidence_url='https://example.org/location'),'test')
        data=view(self.s,self.pid,collection_matrix(self.s))
        self.assertIn('711',data['fields']['address']['value'])
        self.assertTrue(data['location']['approximate'])
        self.assertEqual(data['fields']['address']['evidence'][0]['origin'],'LINKED_SOURCE')
        self.assertIsNone(data['project']['source_values']['address'])
        self.edit({'address':'담당자 확인 주소'})
        data=view(self.s,self.pid,collection_matrix(self.s))
        self.assertEqual(data['fields']['address']['value'],'담당자 확인 주소')
        self.assertEqual(data['location']['latitude'],37.5)
