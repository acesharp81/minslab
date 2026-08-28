from __future__ import annotations

import unittest

from app.services.executive_briefing_query import (
    build_executive_content_groups,
    build_government_source_flow,
    filter_executive_briefings,
)


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

    def test_builds_only_verified_government_source_relationships(self):
        meeting = {
            "news_id": "state-37",
            "title": "제37회 국무회의",
            "source_url": "https://example.test/state",
            "presidential_briefing": {
                "briefing_id": "president-37",
                "title": "제37회 국무회의 관련 브리핑",
                "source_url": "https://example.test/president",
            },
            "agendas": [
                {"topic": "재난 지원", "ministries": ["행정안전부"]},
                {"topic": "재정 운용", "ministries": ["기획재정부"]},
            ],
        }
        flow = build_government_source_flow(meeting)
        self.assertEqual(
            [node["source_type"] for node in flow["nodes"]],
            ["STATE_COUNCIL", "PRESIDENTIAL_OFFICE", "MINISTRY", "MINISTRY"],
        )
        self.assertEqual(
            {link["relation_type"] for link in flow["links"]},
            {"SAME_MEETING_NUMBER_AND_DATE", "OFFICIAL_AGENDA_OWNER"},
        )
        self.assertTrue(all(link["authority_status"] for link in flow["links"]))

    def test_exposes_reporting_ministry_and_linked_official_briefing(self):
        meeting = {
            "news_id": "state-37",
            "title": "제37회 국무회의",
            "agendas": [{
                "agenda_type": "REPORT",
                "topic": "세계 최고의 AI민주정부 실현 전략",
                "ministries": ["행정안전부"],
                "related_ministry_briefings": [{
                    "briefing_id": "156775445",
                    "ministry": "행정안전부",
                    "title": "AI민주정부 실현전략",
                    "source_url": "https://example.test/ministry",
                    "relation": {
                        "relation_type": "SAME_DAY_MINISTRY_REPORT_BRIEFING",
                        "label": "같은 날·동일 부처·동일 주제의 공식 브리핑",
                        "authority_status": "VERIFIED",
                    },
                }],
            }],
        }
        flow = build_government_source_flow(meeting)
        self.assertIn(
            "MINISTRY_BRIEFING",
            [node["source_type"] for node in flow["nodes"]],
        )
        self.assertEqual(
            {link["relation_type"] for link in flow["links"]},
            {
                "OFFICIAL_REPORTING_MINISTRY",
                "SAME_DAY_MINISTRY_REPORT_BRIEFING",
            },
        )

    def test_groups_reports_spokesperson_briefing_and_deliberated_agendas(self):
        meeting = {
            "presidential_briefing": {
                "briefing_id": "president-37",
                "title": "제37회 국무회의 결과 관련 수석대변인 서면 브리핑",
                "messages": [{"speaker": "대통령", "text": "정책 설명"}],
            },
            "agendas": [
                {
                    "source_span_id": "report-1", "agenda_type": "REPORT",
                    "topic": "AI민주정부 실현 전략",
                },
                {
                    "source_span_id": "agenda-1", "agenda_type": "DELIBERATION",
                    "topic": "소방기본법 시행령 일부개정령안",
                },
            ],
        }
        groups = build_executive_content_groups(meeting)
        self.assertEqual(
            [group["label"] for group in groups],
            ["부처보고", "심의안건", "대변인 브리핑"],
        )
        self.assertEqual([group["count"] for group in groups], [1, 1, 1])
        self.assertEqual(
            groups[2]["items"][0]["content_type"],
            "SPOKESPERSON_BRIEFING",
        )


if __name__ == "__main__":
    unittest.main()
