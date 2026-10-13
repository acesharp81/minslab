import unittest
from datetime import date
from unittest.mock import patch
from backend.gh_portal import parse_detail,pdf_schedules
from backend.project_collection import progress_state
from scripts.research_missing_sources import identity_matches,documentary_facts,official_notice_facts

class ResearchCollectionTests(unittest.TestCase):
 def gh(self,title='(최초) 다산지금A3 통합공공임대 입주자 모집공고',units=518):
  row=dict(name=title,source_date='2026-05-28',source_object_id='793',evidence_url='https://apply.gh.or.kr/detail')
  p=dict(id='p',name='다산지금A3',planned_units=518,region='경기도',municipality='남양주시')
  body=f'<h1>{title}</h1><table><tbody><tr><th scope="col">주택형</th><th scope="col">금회공급 세대수</th><th scope="col">예비입주자 세대수</th></tr><tr><td>59A</td><td>{units}</td><td>{units}</td></tr></tbody></table>'
  return parse_detail(body.encode(),row,p)
 def test_gh_counts_current_offer_once_and_preserves_partial_round(self):
  first=self.gh();self.assertEqual(first['offered_units'],518);self.assertFalse(first['facts'][0]['scope_partial'])
  extra=self.gh('(추가) 다산지금A3 추가모집',105);self.assertEqual(extra['offered_units'],105);self.assertTrue(extra['facts'][0]['scope_partial'])
  with self.assertRaises(ValueError):self.gh(units=519)
 def test_split_pdf_table_date_is_plan_not_actual_or_contract_date(self):
  class Page:
   def extract_text(self):return '공급대상 총건설호수 518 입주\n예정일\n‘27.05\n예정'
  with patch('backend.gh_portal.PdfReader',return_value=type('Reader',(),{'pages':[Page()]})()):
   facts,_=pdf_schedules(b'%PDF mock supply table');self.assertEqual(facts[0]['date'],'2027-05');self.assertEqual(facts[0]['kind'],'PLAN')
 def cell(self):return dict(status='METHOD_UNKNOWN',actual_available=False,partial_actual_available=False,targets=[])
 def test_phase_future_undecided_and_missing_are_distinct(self):
  phase=dict(reported_phase='사업시행자지정',base_date='2026-10-13')
  self.assertEqual(progress_state(self.cell(),'APPROVAL',date(2026,10,13),phase)['code'],'NOT_REACHED_REPORTED')
  future=dict(self.cell(),targets=[dict(date='2027-05',milestone='MOVE_IN')])
  self.assertEqual(progress_state(future,'MOVE_IN',date(2026,10,13))['code'],'UPCOMING')
  pending=dict(self.cell(),targets=[dict(date=None,date_label='미정',schedule_status='UNDETERMINED')])
  self.assertEqual(progress_state(pending,'MOVE_IN',date(2026,10,13))['code'],'SCHEDULE_PENDING')
  self.assertEqual(progress_state(self.cell(),'MOVE_IN',date(2026,10,13))['code'],'METHOD_UNKNOWN')
 def test_collected_actual_wins_over_older_upstream_phase(self):
  c=dict(self.cell(),actual_available=True)
  self.assertEqual(progress_state(c,'CONSTRUCTION',date(2026,10,13),dict(reported_phase='조합설립인가'))['code'],'ACTUAL_REPORTED')
 def test_candidate_identity_has_numeric_boundary_and_does_not_create_dates(self):
  p=dict(district='남양주왕숙',block='A19')
  self.assertFalse(identity_matches(p,'남양주왕숙 A19','남양주왕숙 A190 주택건설사업'))
  self.assertTrue(identity_matches(p,'남양주왕숙 A19','남양주왕숙 A-19BL 주택건설사업'))
  self.assertTrue(identity_matches(p,'남양주왕숙 A019','남양주왕숙 공공주택지구 내 A-19BL 주택건설사업'))
  facts=documentary_facts('남양주왕숙 A19 주택건설사업계획 승인','공식 고시 본문')
  self.assertEqual(facts[0]['kind'],'DOCUMENT');self.assertIsNone(facts[0]['date'])

 def test_official_gosi_date_is_accepted_but_application_is_not(self):
  body=b'<p>test</p>'
  text='고시정보 공공주택건설 사업계획 승인(남양주왕숙 A-25BL) - 고시번호 국토교통부 고시 제2025-931호 담당기관 국토교통부 고시일 2025-12-30'
  facts=official_notice_facts(text.encode(),'https://www.eum.go.kr/web/gs/gv/gvGosiDet.jsp','왕숙 A25',text)
  self.assertEqual(facts[0]['date'],'2025-12-30');self.assertEqual(facts[0]['kind'],'ACTUAL')
  self.assertIsNone(official_notice_facts(text.replace('계획 승인','계획 승인 신청').encode(),'https://www.eum.go.kr/web/gs/gv/gvGosiDet.jsp','왕숙 A25',text))
