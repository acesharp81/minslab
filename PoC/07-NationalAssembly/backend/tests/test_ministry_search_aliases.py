from copy import deepcopy
from datetime import date, datetime, timezone
from unittest import TestCase
from unittest.mock import Mock

from app.domain.ministry import (
    MINISTRY_ALIASES, canonical_ministry_name, normalize_ministry_mentions,
)
from app.db.topic_report_repository import TopicReportRepository, _official_executive_evidence


class MinistrySearchAliasTests(TestCase):
    def test_all_aliases_and_whitespace_variants_resolve_consistently(self):
        for alias, full in MINISTRY_ALIASES.items():
            with self.subTest(alias=alias):
                self.assertEqual(canonical_ministry_name(alias), full)
                self.assertEqual(canonical_ministry_name(' '.join(alias)), full)
                self.assertEqual(canonical_ministry_name(full), full)
                self.assertEqual(normalize_ministry_mentions(f'{alias}에서 검토한다.'), f'{full}에서 검토한다.')
        self.assertEqual(canonical_ministry_name('행정안정부'), '행정안전부')
        self.assertEqual(canonical_ministry_name('행정 안전부'), '행정안전부')
        self.assertEqual(canonical_ministry_name('기관명 미상'), '기관명 미상')

    def test_different_and_historical_organizations_remain_distinct(self):
        self.assertNotEqual(canonical_ministry_name('금융위'), canonical_ministry_name('금감원'))
        self.assertNotEqual(canonical_ministry_name('기재부'), canonical_ministry_name('재경부'))
        self.assertNotEqual(canonical_ministry_name('방통위'), canonical_ministry_name('방미통위'))
        self.assertEqual(normalize_ministry_mentions('농식품부문 투자'), '농식품부문 투자')
        self.assertEqual(normalize_ministry_mentions('국가행안부'), '국가행안부')

    def test_repository_matches_both_directions_without_altering_source(self):
        brief = {'topics': [
            {'id': 'short', 'title': '안전 정책', 'summary': '행안부에서 재난 대응을 검토한다.'},
            {'id': 'full', 'title': '재난 대응', 'summary': '행정안전부가 안전 대책을 마련한다.'},
            {'id': 'tag', 'title': '업무 보고', 'summary': '추진 현황을 보고했다.', 'ministries': ['행안부']},
            {'id': 'task', 'title': '후속 조치', 'summary': '검토를 요청했다.'},
            {'id': 'other', 'title': '공공 연구', 'summary': '과기정통부가 통신 대책을 검토한다.'},
        ], 'tasks': [{'topic_id': 'task', 'title': '이행 점검', 'ministries': ['행정안정부']}]}
        original = deepcopy(brief)
        connection = Mock()
        connection.execute.return_value.fetchall.return_value = [(
            'meeting-1', '위원회 회의', 'LEGISLATURE', '위원회',
            datetime(2026, 10, 19, tzinfo=timezone.utc), brief, {}, 'PENDING',
        )]
        repository = TopicReportRepository(connection)
        results = []
        for query in ('행안부', '행정안전부', '행정안정부', '행정 안전부'):
            result = repository.search(ministry=query, topic='', period_start=date(2026,10,1), period_end=date(2026,10,20))
            self.assertEqual(result['count'], 4)
            results.append(result)
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(brief, original)
        self.assertIn('행안부에서', next(item['summary'] for item in results[0]['items'] if item['id'].endswith(':short')))
        # Ministry aliases must not bypass an unrelated requested topic.
        unrelated = repository.search(ministry='행안부', topic='양자컴퓨터', period_start=date(2026,10,1), period_end=date(2026,10,20))
        self.assertEqual(unrelated['count'], 0)

    def test_official_executive_sources_match_abbreviated_tags_and_text(self):
        sources = [{'news_id': '1', 'published_date': '2026.10.19', 'title': '국무회의', 'agendas': [
            {'topic': '농업 대책', 'summary': '농식품부는 피해 복구를 지원한다.', 'ministries': ['농식품부']},
            {'topic': '농업 지원', 'summary': '농림축산식품부가 지원을 확대한다.', 'ministries': ['농림축산식품부']},
            {'topic': '연구 대책', 'summary': '과기정통부의 연구 대책', 'ministries': ['과기정통부']},
        ]}]
        original = deepcopy(sources)
        short = _official_executive_evidence(sources, broadcast_ids={}, ministry='농식품부', topic='', period_start=date(2026,10,1), period_end=date(2026,10,20))
        full = _official_executive_evidence(sources, broadcast_ids={}, ministry='농림축산식품부', topic='', period_start=date(2026,10,1), period_end=date(2026,10,20))
        self.assertEqual(len(full), 2)
        self.assertEqual(short, full)
        self.assertEqual(sources, original)
