from copy import deepcopy
from datetime import date, datetime, timezone
from unittest import TestCase
from unittest.mock import Mock, patch

from app.db.topic_report_repository import TopicReportRepository, _topic_relevant_content


class CurrentStructureSearchTests(TestCase):
    def search(self, structured, official=None):
        self.connection = Mock()
        self.base = {'topics': [{'id': 'old', 'title': '국감 종합 질의', 'summary': '위원회 현안을 점검했다.'}]}
        self.connection.execute.return_value.fetchall.return_value = [(
            'broadcast', '행정안전위원회 국정감사', 'LEGISLATURE', '행정안전위원회',
            datetime(2026, 10, 26, 1, tzinfo=timezone.utc), self.base,
            official or {}, 'READY' if official else None, 'current-brief',
        )]
        with patch('app.db.topic_report_repository.TopicStructureRepository') as repository:
            repository.return_value.ready_current.return_value = structured
            result = TopicReportRepository(self.connection).search(
                ministry='', topic='신분증', institution='LEGISLATURE',
                period_start=date(2026, 10, 26), period_end=date(2026, 10, 26),
            )
            repository.return_value.ready_current.assert_called_once_with({
                'brief_id': 'current-brief', 'broadcast_id': 'broadcast', 'brief': self.base,
            })
        return result

    def structure(self):
        return {
            'topics': [{'id': 'structured-mobile-id', 'title': '모바일 신분증 보안 개선',
                        'summary': '질의 2건', 'evidence_ids': ['u-1', 'u-2']}],
            'report_summary': {'topics': [{'source_structured_topic_id': 'structured-mobile-id',
                'summary': '모바일 신분증 검증 체계와 위조 방지 대책을 점검했다.'}]},
            'tasks': [{'title': '검증 대책 제출', 'related_topic_ids': ['structured-mobile-id'],
                       'ministries': ['행정안전부'], 'evidence_ids': ['u-2']}],
        }

    def test_new_visible_issue_is_found_when_original_brief_has_no_keyword(self):
        structured = self.structure()
        original = deepcopy(structured)
        result = self.search(structured)
        self.assertEqual(result['count'], 1)
        evidence = result['items'][0]
        self.assertEqual(evidence['id'], 'broadcast:structured-mobile-id')
        self.assertEqual(evidence['authority_status'], 'PROVISIONAL')
        self.assertIn('위조 방지', evidence['summary'])
        self.assertEqual(evidence['tasks'][0]['title'], '검증 대책 제출')
        self.assertEqual(evidence['mention_count'], 2)
        self.assertEqual(result['llm_calls'], 0)
        self.assertEqual(structured, original)

    def test_finished_summary_can_establish_relevance_without_title_keyword(self):
        structured = self.structure()
        structured['topics'][0]['title'] = '디지털 행정서비스 보안'
        self.assertEqual(self.search(structured)['count'], 1)

    def test_official_and_detailed_live_sources_keep_separate_authority(self):
        official = {'topics': [{'id': 'official-id', 'title': '신분증 제도',
                               'summary': '공식 자료의 신분증 운영 방침이다.'}]}
        result = self.search(self.structure(), official)
        self.assertEqual(result['count'], 2)
        self.assertEqual({x['authority_status'] for x in result['items']},
                         {'OFFICIAL_INTEGRATED', 'PROVISIONAL'})
        self.assertEqual(result['meeting_count'], 1)
        self.assertEqual(len({x['id'] for x in result['items']}), 2)

    def test_missing_structure_still_uses_saved_official_result(self):
        official = {'topics': [{'id': 'official-id', 'title': '신분증 발급',
                               'summary': '발급 절차를 안내했다.'}]}
        result = self.search(None, official)
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['items'][0]['authority_status'], 'OFFICIAL_INTEGRATED')

    def test_korean_particle_in_later_sentence_does_not_hide_requested_word(self):
        self.assertTrue(_topic_relevant_content('신분증', '본인 확인 체계',
            '접근 절차를 점검했다. 신분증으로 본인 확인이 가능한지 질의했다.'))
        self.assertFalse(_topic_relevant_content('AI, 인공지능', '주택 공급',
            '주택 공급을 확대한다. 토지 이용은 AI 혁명에 맞춰 조정한다.'))
