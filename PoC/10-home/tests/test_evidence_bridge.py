import unittest
from datetime import date
from sqlalchemy import create_engine,select,func
from sqlalchemy.pool import StaticPool
from backend.db import Base,Revision,upsert_revision
from backend.service import HomeService
from backend.evidence_bridge import reconcile,review,match_key
from backend.project_collection import collection_matrix

class EvidenceBridgeTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine);self.s=HomeService(self.engine);self.addCleanup(self.engine.dispose)
        self.base=dict(name='평택고덕 A31',district='평택고덕',block='A31',region='경기도',municipality='평택시',planned_units=690,
            program='공공분양',tenure='분양',base_date='2026-01-01',date_precision='YEAR',stage='PLANNED_SUPPLY',stage_label='공급 계획',
            warnings=[],developer='LH',evidence_url='https://example.org/plan')
    def put(self,source,key,payload,kind='project'):
        with self.s.sessions.begin() as db:
            r,_=upsert_revision(db,kind,source,key,payload,'test');return r.entity_id
    def pair(self):
        target=self.put('lh_sale','sale',self.base)
        other=dict(self.base,name='평택고덕 A-31BL 민간참여 공공주택건설사업',district='평택고덕국제화계획',block='Ab31',
                   start_actual_date='2025-06-30',completion_plan_date='2028-12-31',stage='CONSTRUCTION',progress_pct=0)
        source=self.put('lh_construction','construction',other)
        return target,source,other
    def test_high_confidence_persisted_once_and_read_does_not_rematch(self):
        target,source,_=self.pair();result=reconcile(self.s,apply=True)
        self.assertEqual(result['added_links'],1)
        self.assertEqual(reconcile(self.s,apply=True)['added_links'],0)
        row=self.s.rows('evidence_bridge')[0]
        self.assertEqual(row['status'],'REVIEW');self.assertEqual(row['source_revision_no'],1)
        matrix=collection_matrix(self.s)
        cell=next(p for p in matrix['items'] if p['id']==target)['cells']['CONSTRUCTION']
        self.assertTrue(cell['actual_available']);self.assertTrue(cell['plan_available']);self.assertTrue(cell['review_required'])
        self.assertTrue(any(f.get('pct')==0 for f in cell['sources']))
        self.assertFalse(next(p for p in matrix['items'] if p['id']==target)['cells']['SUPPLY']['targets'])
        self.assertEqual(next(p for p in self.s.rows('project') if p['id']==target)['block'],'A31')
    def test_quantity_conflict_and_cross_region_and_multi_site_held(self):
        self.pair()
        self.put('lh_construction','construction',dict(self.base,name='평택고덕 A-31BL',planned_units=100,start_actual_date='2025-01-01'))
        result=reconcile(self.s,apply=True);self.assertEqual(result['added_links'],0);self.assertTrue(result['held'])
        self.assertIsNone(match_key(dict(self.base,name='평택고덕 A31BL 및 A34BL 건설')))
        self.assertNotEqual(match_key(self.base),match_key(dict(self.base,region='인천광역시')))
        self.assertNotEqual(match_key(dict(self.base,name='이름에 블록 없음',block='Ab31')),match_key(self.base))
    def test_release_is_preserved_and_stale_review_rejected(self):
        target,source,other=self.pair();reconcile(self.s,apply=True);r=self.s.rows('evidence_bridge')[0]
        saved=review(self.s,r['id'],r['revision_no'],'RELEASED','다른 계약 범위로 확인')
        self.assertTrue(review(self.s,r['id'],r['revision_no'],'CONFIRMED','검토')['conflict'])
        self.put('lh_construction','construction',dict(other,progress_pct=10))
        self.assertEqual(reconcile(self.s,apply=True)['added_links'],0)
        current=self.s.rows('evidence_bridge')[0];self.assertEqual(current['status'],'RELEASED');self.assertEqual(current['source_revision_no'],1)
        cell=next(p for p in collection_matrix(self.s)['items'] if p['id']==target)['cells']['CONSTRUCTION']
        self.assertFalse(cell['actual_available'])
    def test_draft_document_never_becomes_actual_and_forecast_remains_plan(self):
        target=self.put('lh_sale','sale',self.base)
        doc=dict(self.base,sample_kind='document_evidence',facts=[
            dict(stage='APPROVAL',kind='DOCUMENT',date=None,date_label='번호·일자 미확정',basis='고시 첨부 원문 확보'),
            dict(stage='MOVE_IN',kind='PLAN',date='2029-07',milestone='MOVE_IN',basis='입주 예정')])
        self.put('official_document','doc',doc,'document_evidence');reconcile(self.s,apply=True)
        cells=next(p for p in collection_matrix(self.s)['items'] if p['id']==target)['cells']
        self.assertFalse(cells['APPROVAL']['actual_available']);self.assertIsNone(cells['APPROVAL']['sources'][0]['date'])
        self.assertFalse(cells['MOVE_IN']['actual_available']);self.assertEqual(cells['MOVE_IN']['targets'][0]['date'],'2029-07')
    def test_old_source_version_and_reviewer_basis_are_preserved(self):
        target,source,other=self.pair();reconcile(self.s,apply=True);r=self.s.rows('evidence_bridge')[0]
        review(self.s,r['id'],1,'CONFIRMED','담당자 동일 사업 확인')
        self.put('lh_construction','construction',dict(other,completion_plan_date='2029-12-31'))
        result=reconcile(self.s,apply=True);self.assertTrue(result['held'])
        r=self.s.rows('evidence_bridge')[0];self.assertEqual(r['status'],'CONFIRMED');self.assertEqual(r['source_revision_no'],1)
        self.assertEqual(r['review_basis'],'담당자 동일 사업 확인')
        self.assertTrue(any(f.get('date')=='2028-12-31' for f in r['facts']))

    def test_mixed_cohort_links_with_official_breakdown_not_quantity_ratio(self):
        target=self.put('lh_incheon_sale','sale',dict(self.base,name='인천계양 A17',district='인천계양',block='A17',region='인천광역시',tenure='공공분양',planned_units=309))
        whole=dict(self.base,name='인천계양 A17BL 공사',district='인천계양',block='A17',region='인천광역시',tenure='유형 확인 필요',planned_units=463,start_actual_date='2026-06-01')
        self.put('lh_incheon_construction','construction',whole)
        self.assertEqual(reconcile(self.s,apply=True)['added_links'],0)
        notice=dict(whole,name='인천계양 A17 모집',tenure='공공분양(신혼희망)',scope_breakdown={'공공분양':309,'행복주택':154},verification_status='SOURCE_CONTENT_CHECKED',facts=[
            dict(stage='SUPPLY',kind='ACTUAL',date='2026-09-30',units=309,scope_partial=True,scope_units=309,basis='공식 본청약'),
            dict(stage='MOVE_IN',kind='PLAN',date='2029-11',scope_partial=True,scope_units=309,basis='분양형 입주 예정')])
        self.put('lh_notice_detail','notice',notice,'document_evidence');reconcile(self.s,apply=True)
        links=[r for r in self.s.rows('evidence_bridge') if r['project_id']==target]
        self.assertEqual(len(links),2)
        self.assertTrue(all(r['relation_type']=='CONTAINED_SCOPE' for r in links))
        f=[f for r in links for f in r['facts']];self.assertTrue(any(e['stage']=='CONSTRUCTION' for e in f))
        self.assertEqual(next(e['units'] for e in f if e['stage']=='SUPPLY'),309)
        self.assertTrue(all(not e['scope_partial'] for e in f))
        self.assertFalse(any(e['kind']=='ACTUAL' and e['stage']=='MOVE_IN' for e in f))
        # Same quantity without correct tenure is not a proved cohort.
        from backend.evidence_bridge import contained_facts
        self.assertIsNone(contained_facts(dict(whole,planned_units=309,tenure='행복주택'),whole,[dict(notice,id='doc')],date(2026,10,13)))

    def test_bad_breakdown_does_not_enable_containment(self):
        from backend.evidence_bridge import contained_facts
        target=dict(self.base,tenure='공공분양',planned_units=309)
        source=dict(self.base,planned_units=463,start_actual_date='2026-06-01')
        proof=dict(source,id='doc',verification_status='SOURCE_CONTENT_CHECKED',scope_breakdown={'공공분양':309,'행복주택':155})
        self.assertIsNone(contained_facts(target,source,[proof],date(2026,10,13)))

    def test_additional_recruitment_is_not_promoted_to_full_cohort(self):
        from backend.evidence_bridge import contained_facts
        project=dict(self.base,planned_units=309,tenure='공공분양')
        source=dict(self.base,id='doc',planned_units=463,tenure='공공분양',notice_round='ADDITIONAL',offered_units=2,
                    scope_breakdown={'공공분양':309,'행복주택':154},verification_status='SOURCE_CONTENT_CHECKED',facts=[
                    dict(stage='MOVE_IN',kind='PLAN',date='2029-11',scope_partial=True,scope_units=309,basis='잔여 모집')])
        self.assertIsNone(contained_facts(project,source,[source],date(2026,10,13)))
