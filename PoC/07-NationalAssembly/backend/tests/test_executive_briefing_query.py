from __future__ import annotations

import unittest

from app.services.executive_briefing_query import filter_executive_briefings


class ExecutiveBriefingQueryTests(unittest.TestCase):
    def setUp(self):
        self.items = [
            {
                "news_id": "a", "agenda_count": 2,
                "agendas": [
                    {"topic": "재정 운용", "summary": "예산안 편성", "ministries": ["기획예산처"]},
                    {"topic": "재난 대응", "summary": "호우 복구", "ministries": ["행정안전부"]},
                ],
            },
            {
                "news_id": "b", "agenda_count": 1,
                "agendas": [
                    {"topic": "지방 행정", "summary": "공무원 제도", "ministries": ["행정안전부"]},
                ],
            },
        ]

    def test_filters_exact_official_ministry_and_preserves_facets(self):
        result = filter_executive_briefings(self.items, ministry="행정안전부")
        self.assertEqual(result["meeting_count"], 2)
        self.assertEqual(result["agenda_count"], 2)
        self.assertEqual(result["items"][0]["agenda_count"], 1)
        self.assertEqual(result["facets"]["ministries"][0], {"label": "행정안전부", "count": 2})

    def test_query_searches_only_official_topic_and_summary_text(self):
        result = filter_executive_briefings(self.items, query="예산안")
        self.assertEqual([item["news_id"] for item in result["items"]], ["a"])
        self.assertEqual(result["items"][0]["agendas"][0]["topic"], "재정 운용")

    def test_unknown_filter_returns_empty_without_inventing_rows(self):
        result = filter_executive_briefings(self.items, ministry="존재하지 않는 부처")
        self.assertEqual(result["items"], [])
        self.assertEqual(result["agenda_count"], 0)


if __name__ == "__main__":
    unittest.main()
