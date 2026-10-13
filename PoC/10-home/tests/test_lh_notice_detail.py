import unittest
from datetime import date
from backend.lh_notice_detail import parse_detail,candidates
from backend.evidence_bridge import reconcile
from backend.project_collection import collection_matrix
from tests.test_evidence_bridge import EvidenceBridgeTests

HTML='''<h3>성남금토 A-2블록 국민임대주택 입주자 모집공고</h3><li><strong>공고일</strong>2026.07.08</li>
<ul><li>소재지 : 경기도 성남시 금토동</li><li>총 세대수 : 438</li><li>입주예정월 : 2027.01</li></ul>
<table><thead><tr><th>주택형</th><th>세대수</th><th>금회공급 세대수</th></tr></thead>
<tbody><tr><th>26</th><td>47</td><td>23</td></tr><tr><th>29~44</th><td>391</td><td>196</td></tr></tbody></table>'''
NOTICE=dict(id='notice1',name='성남금토 A-2블록 국민임대주택 입주자 모집공고',region='경기도',notice_no='n1',revision_no=1,
 notice_type='국민임대',source_date='2026-07-08',evidence_url='https://apply.lh.or.kr/example')
KEY=('경기도','성남금토','A2')

class DetailParserTests(unittest.TestCase):
 def test_total_and_current_offer_and_occupancy_are_separate(self):
  p=parse_detail(HTML.encode(),NOTICE,KEY)
  self.assertEqual((p['planned_units'],p['offered_units'],p['move_in_month']),(438,219,'2027-01'))
  self.assertEqual(p['facts'][0]['units'],219)
  self.assertEqual(p['facts'][1]['kind'],'PLAN')
 def test_mixed_complex_does_not_assign_sale_schedule_to_rental_households(self):
  html=HTML.replace('438','1030')+'<p>1,030세대 중 686세대는 신혼희망타운(공공분양)으로 공급하며 나머지 344세대는 행복주택으로 향후 공급할 예정입니다.</p>'
  p=parse_detail(html.encode(),NOTICE,KEY)
  self.assertEqual(p['scope_breakdown'],{'공공분양':686,'행복주택':344})
  self.assertTrue(all(f['scope_partial'] and f['scope_units']==686 for f in p['facts']))
 def test_sale_label_date_with_month_precision(self):
  p=parse_detail(HTML.replace('입주예정월 : 2027.01','입주예정일 : 2027년 01월').encode(),NOTICE,KEY)
  self.assertEqual(p['move_in_month'],'2027-01')
 def test_unknown_date_is_acquired_verbatim_not_zero_or_january(self):
  p=parse_detail(HTML.replace('2027.01','미정').encode(),NOTICE,KEY)
  self.assertIsNone(p['move_in_month']);self.assertEqual(p['facts'][1]['schedule_status'],'UNDETERMINED')
 def test_multi_complex_and_cancellation_not_silently_applied(self):
  with self.assertRaises(ValueError):parse_detail((HTML+'<ul><li>총 세대수 : 195</li><li>입주예정월 : 2027.03</li></ul>').encode(),NOTICE,KEY)
  self.assertFalse(parse_detail(HTML.encode(),dict(NOTICE,name='[취소]'+NOTICE['name']),KEY)['facts'])
 def test_candidates_require_region_district_and_known_blocks(self):
  project=dict(name='성남금토 A2',region='경기도',district='성남금토',block='A2')
  self.assertEqual(len(candidates([project],[NOTICE])),1)
  self.assertFalse(candidates([project],[dict(NOTICE,region='서울특별시')]))
  self.assertEqual(len(candidates([project],[dict(NOTICE,name=NOTICE['name']+' A4블록')])),1)

 def test_numeric_district_suffix_prevents_wangsuk_collision(self):
  ps=[dict(region='경기도',district=d,block='A3',name=d+' A3') for d in ('남양주왕숙','남양주왕숙2')]
  n=dict(NOTICE,name='남양주왕숙2 A-3BL 공공분양')
  selected=candidates(ps,[n]);self.assertEqual(len(selected),1)
  self.assertEqual(selected[0][1],('경기도','남양주왕숙2','A3'))
 def test_multi_complex_tabs_keep_dates_and_partial_quantities_separate(self):
  def tab(i,b,u,m,q):
   return f'<div id="wrtancSbdTab{i}"><h4>의왕월암 {b}</h4><ul><li>총 세대수 : {u}</li><li>입주예정월 : {m}</li></ul><table><thead><tr><th>주택형</th><th>금회공급 세대수</th></tr></thead><tbody><tr><td>55</td><td>{q}</td></tr></tbody></table></div>'
  body='<li><strong>공고일</strong>2024.11.15</li><p>입주자모집공고일은 2024.11.08입니다.</p>'+tab(0,'A1',674,'2027.11',446)+tab(1,'A3',642,'2028.04',424)
  body+='<p>674세대 중 446세대는 신혼희망타운(공공분양)으로 공급하며 나머지 228세대는 행복주택</p><p>642세대 중 424세대는 신혼희망타운(공공분양)으로 공급하며 나머지 218세대는 행복주택</p>'
  n=dict(NOTICE,name='[정정] 의왕월암 A1 및 A3 신혼희망타운',notice_type='공공분양')
  for b,u,q,m in [('A1',674,446,'2027-11'),('A3',642,424,'2028-04')]:
   p=parse_detail(body.encode(),n,('경기도','의왕월암',b))
   self.assertEqual((p['planned_units'],p['offered_units'],p['move_in_month']),(u,q,m))
   self.assertEqual(p['announcement_date'],'2024-11-08')
   self.assertEqual(p['scope_breakdown']['공공분양'],q)
   self.assertTrue(all(f['scope_partial'] for f in p['facts']))
   self.assertEqual(p['notice_title'],n['name'])
 def test_additional_notice_preserves_subset_without_total_replacement(self):
  p=parse_detail(HTML.encode(),dict(NOTICE,name='[추가] '+NOTICE['name']),KEY)
  self.assertEqual(p['notice_round'],'ADDITIONAL')
  self.assertEqual(p['facts'][0]['units'],219)
  self.assertIn('중복 합산 금지',p['facts'][0]['basis'])
  self.assertTrue(all(f['scope_partial'] and f['scope_units']==219 for f in p['facts']))

class PartialScopeTests(EvidenceBridgeTests):
 def test_partial_document_shows_date_without_whole_project_actual(self):
  base=dict(self.base,name='성남금토 A2',district='성남금토',block='A2',planned_units=633)
  target=self.put('lh_construction','geumto',base)
  doc=parse_detail(HTML.encode(),NOTICE,KEY)
  self.put('lh_notice_detail','n1',doc,'document_evidence')
  result=reconcile(self.s,apply=True);self.assertEqual(result['added_links'],1)
  r=self.s.rows('evidence_bridge')[0];self.assertEqual(r['relation_type'],'PARTIAL_SCOPE')
  cells=next(p for p in collection_matrix(self.s)['items'] if p['id']==target)['cells']
  self.assertFalse(cells['SUPPLY']['actual_available']);self.assertFalse(cells['MOVE_IN']['actual_available'])
  t=cells['MOVE_IN']['targets'][0];self.assertEqual(t['date'],'2027-01');self.assertTrue(t['reference_only'])
  self.assertIn('438호 / 전체 633호',t['label']);self.assertEqual(t['name'],'LH 공고 상세')
  self.assertEqual(reconcile(self.s,apply=True)['added_links'],0)
 def test_same_date_can_retain_official_corroboration_but_other_tenure_is_held(self):
  p=dict(self.base,name='성남금토 A2',district='성남금토',block='A2',planned_units=438,tenure='국민임대',
         rows=[dict(move_in_month='2027-01',units=438)])
  self.put('lh_rent','rent',p)
  self.put('lh_notice_detail','n1',parse_detail(HTML.encode(),NOTICE,KEY),'document_evidence')
  reconcile(self.s,apply=True);self.assertTrue(any(f['stage']=='MOVE_IN' for f in self.s.rows('evidence_bridge')[0]['facts']))
  self.put('lh_rent','wrong',dict(p,tenure='영구임대'))
  r=reconcile(self.s,apply=False);self.assertFalse(r['proposals']);self.assertTrue(r['held'])

 def test_mixed_contract_requires_separate_official_housing_breakdown(self):
  p=dict(self.base,name='성남금토 A2 건설 및 복합시설',district='성남금토',block='A2',planned_units=633,warnings=['MULTI_SITE_CONTRACT'])
  self.put('lh_construction','mixed',p)
  self.put('lh_notice_detail','n1',parse_detail(HTML.encode(),NOTICE,KEY),'document_evidence')
  self.assertEqual(reconcile(self.s,apply=True)['added_links'],0)
  doc=dict(p,name='성남금토 A2 변경승인',warnings=[],scope_breakdown={'국민임대':438,'영구임대':195},
           verification_status='SOURCE_CONTENT_CHECKED',facts=[dict(stage='APPROVAL',kind='ACTUAL',date='2023-10-23',basis='변경승인')])
  self.put('official_document','approval',doc,'document_evidence')
  self.assertEqual(reconcile(self.s,apply=True)['added_links'],2)
