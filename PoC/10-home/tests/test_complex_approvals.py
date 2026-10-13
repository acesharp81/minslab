import unittest
from backend.complex_approvals import parse_complex_approvals
from backend.sources import SOURCES

SOURCE = next(s for s in SOURCES if s['id'] == 'complex_approval_reference')
HEADER = '단지고유번호,필지고유번호,주소,단지명_공시가격,단지명_건축물대장,단지명_도로명주소,단지종류,동수,세대수,사용승인일,도로명주소\n'
ROW = '100,200,경기도 남양주시 다산동 6084,다산역자연앤푸르지오,,,1,8,1272,2024-02-22,다산역로 1\n'


class ComplexApprovalTests(unittest.TestCase):
    def test_current_use_approval_is_reference_not_policy_delivery(self):
        content=(HEADER+ROW+'101,201,서울특별시 중구 1,서울단지,,,1,2,9,2017-12-31,도로 1\n').encode('cp949')
        records,stats=parse_complex_approvals(content,SOURCE,'2026-08-31')
        self.assertEqual(len(records),1)
        self.assertEqual(stats['before_2018_target_rows'],1)
        row=records[0][2]
        self.assertEqual(row['approval_date'],'2024-02-22')
        self.assertEqual(row['units'],1272)
        self.assertIsNone(row['actual_occupied_units'])
        self.assertEqual(row['project_link_status'],'REVIEW')
        self.assertEqual(row['record_role'],'COMPLEX_APPROVAL_REFERENCE')

    def test_duplicate_natural_key_rejected(self):
        with self.assertRaisesRegex(ValueError,'중복'):
            parse_complex_approvals((HEADER+ROW+ROW).encode('cp949'),SOURCE,'2026-08-31')
