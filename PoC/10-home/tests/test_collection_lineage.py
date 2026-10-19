import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch
from sqlalchemy import create_engine, select, func
from sqlalchemy.pool import StaticPool
from backend.db import Base, Revision, upsert_revision
from backend.service import HomeService
from backend.collection_lineage import fields, enrich, assignment_explanation

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
        self.assertFalse(pinned['lineage']['stage_links']['APPROVAL'][0]['source_record_available'])

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
        link=item['lineage']['stage_links']['APPROVAL'][0]
        self.assertEqual((link['project_id'],link['source_entity_id'],link['source_revision_no']),('p1',eid,1))
        self.assertEqual(link['keys']['permit'],'PK-old')
        self.assertNotIn('policy',link['keys'])  # Shared project keys are not raw permit fields.
        self.assertTrue(link['source_record_available'])
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

    def test_matching_explanation_keeps_raw_fields_separate_from_internal_ids(self):
        from backend.db import ProgramMapping, Audit
        engine=create_engine('sqlite://',poolclass=StaticPool)
        Base.metadata.create_all(engine);service=HomeService(engine);self.addCleanup(engine.dispose)
        with service.sessions.begin() as db:
            project,_=upsert_revision(db,'project','lh_sale','agency-project',dict(name='원천 사업 A-1',region='경기도',district='테스트지구',block='A-1',source_object_id='기관-001',program='공공주택 건설',planned_units=500,start_actual_date='2026-04-01',evidence_url='https://example.org/project',base_date='2026-04-02'),'test')
            project.recorded_at=datetime(2026,1,1,tzinfo=timezone.utc);pid=project.entity_id
            permit,_=upsert_revision(db,'permit','building_hub','permit',dict(name='원천 허가 A1',region='경기도',district='테스트지구',block='A1',source_object_id='허가-123',units=500),'test')
            permit.recorded_at=datetime(2026,1,1,tzinfo=timezone.utc);eid=permit.entity_id
            db.add(ProgramMapping(id='pr',name='공공주택 건설',seed_policy_id='pol',policy_id='future',status='CONFIRMED',revision_no=2,basis='미래 변경',evidence_url='',created_at=datetime(2026,1,1,tzinfo=timezone.utc)))
            db.add(Audit(entity_id='pr',action='PROGRAM_POLICY_REVIEW',before=dict(policy_id='pol',basis='당시 사업 유형 대조'),after={},recorded_at=datetime(2026,11,1,tzinfo=timezone.utc)))
            db.add(Audit(entity_id='pr',action='PROGRAM_POLICY_REVIEW',before=dict(policy_id='pol',basis='원천 정책 제안을 프로그램 단위로 이관'),after=dict(policy_id='pol',basis='당시 사업 유형 대조'),recorded_at=datetime(2026,10,1,tzinfo=timezone.utc)))
            db.add(Audit(entity_id=pid,action='MAPPING_AUTO',before={},after=dict(policy_id='pol',basis='수집기 정책 후보 적용',rule='SOURCE_POLICY'),recorded_at=datetime(2026,1,2,tzinfo=timezone.utc)))
        p=dict(id=pid,revision_no=1,source_id='lh_sale',name='화면에 정비한 이름',mapping=dict(policy_id='pol',program_id='pr',basis='담당자 사업 배정'))
        item=dict(id=pid,cells={
            'APPROVAL':dict(sources=[dict(source_id='building_hub',source_entity_id=eid,source_revision_no=1,kind='STATE',method='EXACT',basis='지구·단일 블록 일치',match_score=1,decision_basis='담당자가 채택')]),
            'CONSTRUCTION':dict(sources=[dict(source_id='lh_sale',kind='PLAN',date='2027-01')]),
            'MOVE_IN':dict(sources=[dict(source_id='officer',kind='PLAN',basis='대상 사업 지정',date='2028-01')])})
        enrich(service,[p],[item],date(2026,10,16),{},baselines=[])
        line=item['lineage'];match=line['stage_links']['APPROVAL'][0]
        self.assertEqual(line['identity']['source_fields']['name'],'원천 사업 A-1')
        self.assertEqual(match['source_fields']['block'],'A1')
        self.assertEqual(match['matching']['basis'],'지구·단일 블록 일치')
        self.assertEqual(match['matching']['score'],1)
        self.assertNotIn('project',match['source_fields']);self.assertNotIn('policy',match['source_fields'])
        self.assertEqual(line['identity']['program_mapping']['basis'],'당시 사업 유형 대조')
        assignment=line['identity']['assignment']
        self.assertEqual(assignment['project']['rows'][0]['result'],'일치')
        self.assertEqual(assignment['project']['history'][0]['rule'],'SOURCE_POLICY')
        self.assertEqual(assignment['policy']['history'][0]['basis'],'원천 정책 제안을 프로그램 단위로 이관')
        self.assertNotIn('미래 변경',str(assignment))
        self.assertEqual(line['stage_links']['CONSTRUCTION'][0]['matching']['method'],'SOURCE_RECORD')
        self.assertEqual(line['stage_links']['CONSTRUCTION'][0]['source_url'],'https://example.org/project')
        self.assertEqual(line['stage_links']['CONSTRUCTION'][0]['source_facts']['start'],'2026-04-01')
        self.assertEqual(line['stage_links']['CONSTRUCTION'][0]['source_date'],'2026-04-02')
        self.assertEqual(line['stage_links']['MOVE_IN'][0]['matching']['method'],'DIRECT_INPUT')
        self.assertEqual(line['stage_links']['MOVE_IN'][0]['source_fields'],{})
        with service.sessions() as db:self.assertEqual(db.scalar(select(func.count()).select_from(Revision)),2)

    def test_assignment_compares_saved_fields_without_inventing_document_matches(self):
        names={'pol':'9.7 공급대책','other':'다른 정책'}
        raw=dict(program='3기 신도시',proposed_policy='pol',district='고양창릉')
        mapping=dict(program_name='3기 신도시',policy_id='pol',status='CONFIRMED')
        program=dict(name='3기 신도시',seed_policy_id='pol')
        history=[dict(action='PROGRAM_POLICY_REVIEW',before=dict(basis='원천 정책 제안을 프로그램 단위로 이관'),
                      after=dict(basis='담당자 자동매칭 확인 완료'),recorded_at='2026-10-14')]
        result=assignment_explanation(raw,mapping,program,[],history,names)
        self.assertEqual(result['project']['rows'][0]['left'],'3기 신도시')
        self.assertEqual(result['policy']['rows'][0]['left'],'9.7 공급대책')
        self.assertEqual(result['policy']['rows'][1]['result'],'일치')
        self.assertEqual(len(result['policy']['history']),2)
        self.assertIn('수집·분류 과정',result['policy']['note'])
        self.assertNotIn('고양창릉',str(result))  # No fabricated policy-document match.
        override=assignment_explanation(raw,dict(mapping,policy_id='other'),dict(program,name='공공주택 건설'),[],[],names)
        self.assertEqual(override['project']['rows'][0]['result'],'다른 값으로 배정')
        self.assertEqual(override['policy']['rows'][0]['result'],'다른 값으로 배정')
        missing=assignment_explanation({}, {}, {}, [], [], {})
        self.assertEqual(missing['project']['rows'][0]['result'],'대조값 미기록')
        self.assertEqual(missing['policy']['rows'][0]['result'],'대조값 미기록')
        same_titles=assignment_explanation(raw,dict(mapping,policy_id='other'),program,[],[],{'pol':'동일 제목','other':'동일 제목'})
        self.assertEqual(same_titles['policy']['rows'][0]['result'],'다른 값으로 배정')

    def test_lh_classification_explains_input_keyword_without_changing_assignment(self):
        from backend.matching_rules import construction_program_classification
        self.assertEqual(construction_program_classification('고양창릉')['program'],'3기 신도시')
        self.assertEqual(construction_program_classification('성남금토')['program'],'공공주택 건설')
        raw=dict(district='고양창릉',program='3기 신도시')
        result=assignment_explanation(raw,{},dict(name='3기 신도시'),[],[],{},'lh_construction')
        self.assertEqual(result['project']['classification']['matched'],'창릉')
        self.assertTrue(result['project']['classification']['agrees'])
        other=assignment_explanation(raw,{},dict(name='3기 신도시'),[],[],{},'other_source')
        self.assertIsNone(other['project']['classification'])
        changed=assignment_explanation(dict(raw,program='다른 유형'),{},dict(name='3기 신도시'),[],[],{},'lh_construction')
        self.assertFalse(changed['project']['classification']['agrees'])
        self.assertEqual(changed['project']['rows'][0]['left'],'다른 유형')

    def test_plan_extraction_distinguishes_native_type_from_system_program(self):
        raw=dict(name='과천주암(뉴스테이) C2',tenure='행복주택',program='건설형 공공임대',
                 evidence_url='https://example.org/rent',rows=[
                     dict(name='과천주암(뉴스테이) C2',tenure='행복주택',area='46',units=30,supply_raw='2026년12월'),
                     dict(name='과천주암(뉴스테이) C2',tenure='행복주택',area='55',units=314,supply_raw='2026년12월')])
        for source in ('lh_rent','lh_incheon_rent'):
            with self.subTest(source=source):
                result=assignment_explanation(raw,{},dict(name='건설형 공공임대'),[],[],{},source)['project']
                c=result['classification']
                self.assertEqual(c['field'],'유형');self.assertEqual(c['value'],'행복주택')
                self.assertEqual(c['output'],'건설형 공공임대')
                self.assertEqual(sum(r['units'] for r in c['extracted_rows']),344)
                self.assertNotIn('건설형 공공임대',str(c['extracted_rows']))
                self.assertIn('매입·전세',c['criterion'])
                self.assertEqual(c['source_url'],'https://example.org/rent')
        override=assignment_explanation(raw,{},dict(name='담당자가 지정한 프로그램'),[],[],{},'lh_rent')['project']
        self.assertEqual(override['rows'][0]['result'],'다른 값으로 배정')
        self.assertEqual(override['classification']['value'],'행복주택')
        absent=assignment_explanation(dict(raw,rows=[]),{},dict(name='건설형 공공임대'),[],[],{},'lh_rent')['project']
        self.assertEqual(absent['classification']['extracted_rows'],[])
        excluded=assignment_explanation(dict(raw,tenure='매입임대'),{},dict(name='건설형 공공임대'),[],[],{},'lh_rent')['project']['classification']
        self.assertIsNone(excluded['output']);self.assertFalse(excluded['agrees'])
