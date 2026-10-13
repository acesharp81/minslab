import unittest
from backend.seoul_project_documents import parse_construction_overview,parse_godeok_pre_notice_text

NAME='고덕강일 공공주택지구 3단지 아파트 건설공사'
HTML=f'''<h2>{NAME}</h2><script>var pjt_cd = "7042023051599";</script>
<p>착공 2023-05-15 준공 2026-11-06</p><p>계획 2.75% 실적 2.49% 달성 90.55%</p>
<table><tr><th>공사기간</th><td>2023-05-15 ~ 2026-11-06</td></tr><tr><th>사업규모</th><td>17개동</td></tr></table>'''
TEXT='''고덕강일 3단지 사전예약 입주자모집공고일 2022.12.30
총 건설호수는 1,305호이며 그 중 59㎡ 715호이고 49㎡ 590호입니다.
전용 59㎡ 사전예약 공급호수 500세대
4. 본청약 및 입주 예정시기 고덕강일 공공주택지구 3단지 2026년 8월 2027년 3월'''

class SeoulDocumentTests(unittest.TestCase):
    def test_construction_start_and_forecast_completion_are_separate(self):
        p=parse_construction_overview(HTML.encode(),'7042023051599',NAME)
        self.assertEqual(p['facts'][0]['kind'],'ACTUAL')
        self.assertEqual(p['facts'][0]['date'],'2023-05-15')
        self.assertEqual(p['facts'][1]['milestone'],'COMPLETION')
        self.assertEqual(p['facts'][1]['kind'],'PLAN')
        self.assertFalse(any(f['stage'] in ('SUPPLY','MOVE_IN') for f in p['facts']))
    def test_undated_percent_is_document_not_current_actual(self):
        p=parse_construction_overview(HTML.encode(),'7042023051599',NAME)
        self.assertEqual(p['raw_progress']['actual_pct'],2.49)
        self.assertIsNone(p['progress_observation_date'])
        self.assertFalse(any(f.get('pct') is not None for f in p['facts']))
        self.assertEqual(p['facts'][2]['kind'],'DOCUMENT')
    def test_wrong_project_code_name_and_reversed_dates_are_rejected(self):
        for body,code in [(HTML,'7042023051598'),(HTML.replace(NAME,'고덕강일 4단지'),'7042023051599'),(HTML.replace('2026-11-06','2022-11-06'),'7042023051599')]:
            with self.subTest(code=code):
                with self.assertRaises(ValueError):parse_construction_overview(body.encode(),code,NAME)
    def test_percent_range_and_missing_start_label_are_rejected(self):
        for body in [HTML.replace('실적 2.49%','실적 102.49%'),HTML.replace('착공','계약')]:
            with self.assertRaises(ValueError):parse_construction_overview(body.encode(),'7042023051599',NAME)
    def test_first_reservation_is_partial_state_and_future_move_in_plan(self):
        p=parse_godeok_pre_notice_text(TEXT,'2022-12-30',1)
        self.assertEqual((p['planned_units'],p['offered_units']),(1305,500))
        self.assertEqual(p['facts'][0]['kind'],'STATE')
        self.assertEqual(p['facts'][0]['event_type'],'ADVANCE_RESERVATION')
        self.assertEqual(p['facts'][0]['scope_units'],500)
        self.assertEqual(p['facts'][2]['date'],'2027-03')
        self.assertEqual(p['facts'][2]['scope_units'],715)
        self.assertTrue(all(f['kind']!='ACTUAL' for f in p['facts']))
    def test_second_reservation_stays_in_49sqm_cohort(self):
        text=TEXT.replace('2022.12.30','2023.06.13').replace('전용 59㎡ 사전예약 공급호수 500세대','전용 49㎡ 사전예약 공급호수 590세대')
        p=parse_godeok_pre_notice_text(text,'2023-06-13',2)
        self.assertEqual((p['offered_units'],p['facts'][2]['scope_units']),(590,590))
    def test_household_conservation_date_and_missing_schedule_fail(self):
        for text in [TEXT.replace('1,305','1,306'),TEXT.replace('49㎡ 590','49㎡ 591'),TEXT.replace('2022.12.30','2022.12.29'),TEXT.replace('2027년 3월','미정')]:
            with self.assertRaises(ValueError):parse_godeok_pre_notice_text(text,'2022-12-30',1)
