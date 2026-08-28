from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from app.adapters.national_assembly.base import SourcePayload
from app.ingestion.executive_briefings import (
    attach_presidential_guidance,
    attach_related_ministry_briefings,
    parse_detail,
    parse_list,
    parse_policy_briefing_detail,
    parse_policy_briefing_list,
    parse_president_detail,
    parse_president_list,
    report_matches_policy_briefing,
)


class ExecutiveBriefingTests(unittest.TestCase):
    def test_parses_only_official_state_council_links(self):
        html = b"""
        <ul><li><a onclick="goView('/briefing/stateCouncilView.do?newsId=123','')">
        <strong>\xec\xa0\x9c35\xed\x9a\x8c \xea\xb5\xad\xeb\xac\xb4\xed\x9a\x8c\xec\x9d\x98 \xeb\xb8\x8c\xeb\xa6\xac\xed\x95\x91</strong></a>
        <span class="source"><span>2026.08.11</span></span></li></ul>
        """
        items = parse_list(html)
        self.assertEqual(items[0]["news_id"], "123")
        self.assertEqual(items[0]["published_date"], "2026.08.11")

    def test_extracts_explicit_agenda_and_ministry_evidence(self):
        body = """
        <div class="article_body"><div class="view_cont">
        <p>&lt;물가안정에 관한 법률 시행령 일부개정령안&gt;, 매점매석 단속 권한을 정비합니다.
        【소관 : 재정경제부 물가정책과 044-215-2831】</p>
        </div></div>
        """.encode()
        payload = SourcePayload(
            "executive_state_council_detail", body, "text/html",
            datetime.now(timezone.utc), "https://www.korea.kr/briefing/stateCouncilView.do?newsId=123", 200,
        )
        item = {"news_id": "123", "title": "제35회 국무회의 브리핑", "published_date": "2026.08.11", "source_url": payload.source_url}
        result = parse_detail(item, payload, "a" * 64)
        self.assertEqual(result["meeting_number"], 35)
        self.assertEqual(result["agendas"][0]["ministries"], ["재정경제부"])
        self.assertEqual(result["agendas"][0]["authority_status"], "OFFICIAL")

    def test_extracts_state_council_ministry_reports_before_deliberated_agendas(self):
        body = """
        <div class="article_body"><div class="view_cont"><p>
        대통령 주재로 제37회 국무회의를 개최하였습니다.
        △세계 최고의 AI민주정부 실현 전략(행안부)
        △국민의 일상을 바꾸는 고속철도 통합(국토부)
        관련 부처보고를 진행하였습니다.
        &lt;소방기본법 시행령 일부개정령안&gt;, 보험 가입 기준을 정합니다.
        【소관 : 소방청 보건안전담당관 044-205-7412】
        </p></div></div>
        """.encode()
        payload = SourcePayload(
            "executive_state_council_detail", body, "text/html",
            datetime.now(timezone.utc),
            "https://www.korea.kr/briefing/stateCouncilView.do?newsId=37", 200,
        )
        item = {
            "news_id": "37", "title": "제37회 국무회의 브리핑",
            "published_date": "2026.08.25", "source_url": payload.source_url,
        }
        result = parse_detail(item, payload, "c" * 64)
        self.assertEqual(result["agenda_count"], 3)
        self.assertEqual(result["agendas"][0]["agenda_type"], "REPORT")
        self.assertEqual(result["agendas"][0]["ministries"], ["행정안전부"])
        self.assertEqual(result["agendas"][1]["ministries"], ["국토교통부"])
        self.assertEqual(result["agendas"][2]["agenda_type"], "DELIBERATION")

    def test_extracts_reports_from_related_to_wording_and_skips_agenda_counts(self):
        body = """
        <div class="article_body"><div class="view_cont"><p>
        대통령 주재로 제35회 국무회의를 개최하였습니다.
        △대통령령안 19건, △일반안건 4건을 심의·의결 하였습니다.
        △중동전쟁 관련 비상국정운영 및 대응현황(재경부)
        △범정부 자살예방 대책(복지부) 관련하여 부처보고를 진행하였습니다.
        </p></div></div>
        """.encode()
        payload = SourcePayload(
            "executive_state_council_detail", body, "text/html",
            datetime.now(timezone.utc),
            "https://www.korea.kr/briefing/stateCouncilView.do?newsId=35", 200,
        )
        result = parse_detail({
            "news_id": "35", "title": "제35회 국무회의 브리핑",
            "published_date": "2026.08.11", "source_url": payload.source_url,
        }, payload, "e" * 64)
        reports = [
            agenda for agenda in result["agendas"]
            if agenda["agenda_type"] == "REPORT"
        ]
        self.assertEqual(len(reports), 2)
        self.assertEqual(reports[0]["ministries"], ["재정경제부"])
        self.assertEqual(reports[1]["ministries"], ["보건복지부"])

    def test_keeps_reports_with_angle_or_omitted_ministry_labels(self):
        body = """
        <div class="article_body"><div class="view_cont"><p>
        대통령 주재로 제31회 국무회의를 개최하였습니다.
        △GMO 완전표시제 시행 추진계획&lt;관계부처 합동&gt;
        △중소기업 지원사업 제3자 부당개입 근절 방안
        관련 부처보고를 진행하였습니다.
        </p></div></div>
        """.encode()
        payload = SourcePayload(
            "executive_state_council_detail", body, "text/html",
            datetime.now(timezone.utc),
            "https://www.korea.kr/briefing/stateCouncilView.do?newsId=31", 200,
        )
        result = parse_detail({
            "news_id": "31", "title": "제31회 국무회의 브리핑",
            "published_date": "2026.07.21", "source_url": payload.source_url,
        }, payload, "f" * 64)
        reports = [
            agenda for agenda in result["agendas"]
            if agenda["agenda_type"] == "REPORT"
        ]
        self.assertEqual(len(reports), 2)
        self.assertEqual(reports[0]["ministries"], ["관계부처"])
        self.assertEqual(reports[1]["ministries"], ["관계부처"])

    def test_matches_and_attaches_same_day_ministry_policy_briefing(self):
        listing = """
        <table><tbody><tr>
          <td>행정안전부</td>
          <td class="subject"><a href="/briefing/policyBriefingView.do?newsId=156775445"><strong>AI민주정부 실현전략</strong></a></td>
          <td>2026.08.25</td><td>황규철 인공지능정부실장</td>
        </tr></tbody></table>
        """.encode()
        rows = parse_policy_briefing_list(listing)
        report = {
            "agenda_type": "REPORT",
            "topic": "세계 최고의 AI민주정부 실현 전략",
            "ministries": ["행정안전부"],
            "published_date": "2026.08.25",
            "related_ministry_briefings": [],
            "summary": "보고 안건",
        }
        self.assertTrue(report_matches_policy_briefing(report, rows[0]))
        detail_html = """
        <div class="article_body"><div class="view_cont">
        &lt;황규철 행정안전부 인공지능정부실장&gt;<br>
        오늘 국무회의에서 보고한 세계 최고의 AI민주정부 실현 전략에 대해 말씀드리겠습니다.
        정부 운영 전반을 AI 시대에 맞게 혁신합니다.
        </div></div>
        """.encode()
        detail_payload = SourcePayload(
            "executive_ministry_briefing_detail", detail_html, "text/html",
            datetime.now(timezone.utc), rows[0]["source_url"], 200,
        )
        detail = parse_policy_briefing_detail(rows[0], detail_payload, "d" * 64)
        meeting = {
            "published_date": "2026.08.25",
            "agendas": [report],
        }
        linked = attach_related_ministry_briefings(
            meeting, rows, fetch_detail=lambda row: detail,
        )
        self.assertEqual(linked, 1)
        attached = meeting["agendas"][0]["related_ministry_briefings"][0]
        self.assertEqual(attached["briefing_id"], "156775445")
        self.assertEqual(
            attached["relation"]["relation_type"],
            "SAME_DAY_MINISTRY_REPORT_BRIEFING",
        )
        self.assertIn("국무회의에서 보고한", attached["relation"]["evidence"])

    def test_presidential_briefing_keeps_official_message_spans(self):
        listing = json.dumps({"data": {"list": [{
            "SUBJECT": "제35회 국무회의 관련 서면 브리핑",
            "WRITE_DATE": "2026.08.11", "BBS_CD": "sample",
        }]}}).encode()
        item = parse_president_list(listing)[0]
        html = """<div class="view_txt ck-content">
        <p>이 대통령은 국민 안전 대책을 빈틈없이 마련해 달라고 지시했습니다.</p>
        <p>일반적인 안건 설명입니다.</p></div>""".encode()
        payload = SourcePayload(
            "president_state_council_detail", html, "text/html",
            datetime.now(timezone.utc), item["source_url"], 200,
        )
        result = parse_president_detail(item, payload, "b" * 64)
        self.assertEqual(result["message_count"], 1)
        self.assertEqual(result["paragraph_count"], 2)
        self.assertEqual(result["messages"][0]["source_span_id"], "president-paragraph-1")
        self.assertEqual(result["messages"][0]["authority_status"], "OFFICIAL")

    def test_attaches_directive_to_its_report_with_target_ministry(self):
        meeting = {
            "agendas": [
                {
                    "agenda_type": "REPORT",
                    "topic": "독자 AI 모델 개발 도전 의의 및 성과",
                    "ministries": ["과학기술정보통신부"],
                },
                {
                    "agenda_type": "REPORT",
                    "topic": "세계 최고의 AI 민주정부 실현 전략",
                    "ministries": ["행정안전부"],
                },
            ],
            "presidential_briefing": {
                "paragraphs": [
                    {
                        "source_span_id": "president-paragraph-3",
                        "text": "오늘 회의에서는 독자 AI 모델 개발 도전 의의 및 성과, 세계 최고의 AI 민주정부 실현 전략 등 2건의 부처보고가 있었습니다.",
                    },
                    {
                        "source_span_id": "president-paragraph-23",
                        "text": "과학기술정보통신부가 준비한 독자 AI 모델 개발 도전 의의 및 성과에 대해 보고받았습니다.",
                    },
                    {
                        "source_span_id": "president-paragraph-25",
                        "text": "공공 AI 에이전트를 개발해달라 당부했습니다.",
                    },
                    {
                        "source_span_id": "president-paragraph-27",
                        "text": "행정안전부가 준비한 세계 최고의 AI 민주정부 실현 전략에 대해 민간 참여 방안을 고민해 달라 제안했습니다.",
                    },
                ],
            },
        }
        linked = attach_presidential_guidance(meeting)
        self.assertEqual(linked, 2)
        first = meeting["agendas"][0]["presidential_guidance"][0]
        second = meeting["agendas"][1]["presidential_guidance"][0]
        self.assertEqual(first["target_ministries"], ["과학기술정보통신부"])
        self.assertIn("개발해달라", first["text"])
        self.assertEqual(second["target_ministries"], ["행정안전부"])
        self.assertIn("제안했습니다", second["text"])


if __name__ == "__main__":
    unittest.main()
