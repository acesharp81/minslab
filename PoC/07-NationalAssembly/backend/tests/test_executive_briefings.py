from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

from app.adapters.national_assembly.base import SourcePayload
from app.ingestion.executive_briefings import (
    _pdf_press_release_text,
    attach_presidential_ministry_reports,
    attach_presidential_guidance,
    attach_related_ministry_briefings,
    parse_detail,
    parse_list,
    parse_policy_briefing_detail,
    parse_policy_briefing_list,
    parse_press_release_detail,
    parse_press_release_list,
    parse_president_detail,
    parse_president_list,
    report_matches_policy_briefing,
    reusable_detail,
)


class ExecutiveBriefingTests(unittest.TestCase):
    def test_detail_cache_expires_and_does_not_mutate_snapshot(self):
        now = datetime(2026, 9, 24, tzinfo=timezone.utc)
        previous = {
            "source_url": "https://example.org/detail",
            "retrieved_at": (now - timedelta(hours=2)).isoformat(),
            "agendas": [{"related_ministry_briefings": []}],
        }
        reused = reusable_detail(
            previous, previous["source_url"], now=now,
            max_age=timedelta(hours=6),
        )
        self.assertIsNotNone(reused)
        reused["agendas"][0]["related_ministry_briefings"].append({"id": 1})
        self.assertEqual([], previous["agendas"][0]["related_ministry_briefings"])
        self.assertIsNone(reusable_detail(
            previous, previous["source_url"], now=now,
            max_age=timedelta(hours=1),
        ))
        self.assertIsNone(reusable_detail(
            previous, "https://example.org/changed", now=now,
            max_age=timedelta(hours=6),
        ))
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

    def test_matches_prior_official_briefing_by_ministry_and_specific_topic(self):
        report = {
            "topic": "주택 신속공급 방안 후속조치 계획",
            "ministries": ["국토교통부"],
            "published_date": "2026.08.18",
        }
        briefing = {
            "title": "전월세 및 매매시장 안정을 위한 주택 신속공급 방안",
            "ministry": "국토교통부",
            "published_date": "2026.08.13",
        }
        self.assertTrue(report_matches_policy_briefing(report, briefing))
        briefing["ministry"] = "행정안전부"
        self.assertFalse(report_matches_policy_briefing(report, briefing))

    def test_matches_independent_ai_model_report_to_foundation_model_release(self):
        report = {
            "topic": "독자 AI모델 개발 도전 의의 및 성과",
            "ministries": ["과학기술정보통신부"],
            "published_date": "2026.08.25",
        }
        release = {
            "title": "독자 AI 파운데이션 모델 프로젝트 2차 단계평가 결과 발표",
            "ministry": "과학기술정보통신부",
            "published_date": "2026.08.18",
        }
        self.assertTrue(report_matches_policy_briefing(report, release))

    def test_parses_ministry_press_release_with_preview_and_source_kind(self):
        listing = """
        <div class="article_body"><div class="list_type"><ul><li>
          <a href="/briefing/pressReleaseView.do?newsId=156774738">
            <span class="text">
              <strong>[참고] 「주택 신속공급 방안」 속도감 있는 이행에 총력</strong>
              <span class="lead">공공과 산업계가 공급 가속화 방안을 논의했다.</span>
              <span class="source"><span>2026-08-18</span><span>국토교통부</span></span>
            </span>
          </a>
        </li></ul></div></div>
        """.encode()
        rows = parse_press_release_list(listing)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["briefing_id"], "156774738")
        self.assertEqual(rows[0]["ministry"], "국토교통부")
        self.assertEqual(rows[0]["published_date"], "2026.08.18")
        self.assertEqual(rows[0]["source_kind"], "PRESS_RELEASE")
        self.assertIn("공급 가속화", rows[0]["preview_summary"])

    def test_press_release_detail_finds_pdf_when_html_has_no_substance(self):
        listed = {
            "briefing_id": "156774738", "ministry": "국토교통부",
            "title": "주택 신속공급 방안 후속조치", "published_date": "2026.08.18",
            "source_url": "https://www.korea.kr/briefing/pressReleaseView.do?newsId=156774738",
        }
        html = """
        <div class="filedown"><a href="/common/download.do?fileId=1&amp;tblKey=GMN">
          <img alt="PDF파일">housing.pdf</a></div>
        <div class="article_body"><div class="view_cont">
          관련 보도자료 내용입니다. 자세한 내용은 첨부파일을 참고하시기 바랍니다.
        </div></div>
        """.encode()
        payload = SourcePayload(
            "executive_ministry_press_release_detail", html, "text/html",
            datetime.now(timezone.utc), listed["source_url"], 200,
        )
        detail = parse_press_release_detail(listed, payload, "p" * 64)
        self.assertEqual(detail["summary"], "")
        self.assertEqual(detail["source_kind"], "PRESS_RELEASE")
        self.assertIn("fileId=1", detail["pdf_url"])

    def test_press_release_pdf_keeps_action_blocks_and_removes_layout_noise(self):
        pages = ["""
        보도참고자료
        주택 신속공급 방안
        - 금융· 세제·규제 개선 및 조기 착공 인센티브 제공

        □ 공공 부문이 공급 대책*의 3분의 1을 담당 하고 목표를 완수한다.
        ㅇ 재원과 조직 대응방안을 마련 할 계획이다.
        담당 부서 국토교통부 책임자 홍길동
        """]
        text = _pdf_press_release_text(pages)
        self.assertNotIn("보도참고자료", text)
        self.assertNotIn("담당 부서", text)
        self.assertIn("금융·세제·규제", text)
        self.assertIn("담당하고", text)
        self.assertIn("마련할", text)
        self.assertNotIn("대책*", text)

    def test_attaches_same_day_ministry_press_release_as_verified_source(self):
        report = {
            "agenda_type": "REPORT", "topic": "주택 신속공급 방안 후속조치 계획",
            "ministries": ["국토교통부"], "published_date": "2026.08.18",
            "related_ministry_briefings": [],
        }
        row = {
            "briefing_id": "156774738", "ministry": "국토교통부",
            "title": "주택 신속공급 방안 속도감 있는 이행에 총력",
            "published_date": "2026.08.18", "source_kind": "PRESS_RELEASE",
            "source_url": "https://example.test/housing",
        }
        meeting = {"published_date": "2026.08.18", "agendas": [report]}
        linked = attach_related_ministry_briefings(
            meeting, [row], fetch_detail=lambda _: {
                **row, "summary": "공공택지는 조기 착공하고 금융·세제·규제를 개선한다.",
                "authority_status": "OFFICIAL",
            },
        )
        self.assertEqual(linked, 1)
        attached = report["related_ministry_briefings"][0]
        self.assertEqual(
            attached["relation"]["relation_type"],
            "SAME_DAY_MINISTRY_PRESS_RELEASE",
        )
        self.assertIn("공식 보도자료", attached["relation"]["label"])

    def test_does_not_match_policy_briefing_after_meeting_or_too_old(self):
        report = {
            "topic": "중대범죄수사청 출범 준비 상황",
            "ministries": ["행정안전부"],
            "published_date": "2026.08.18",
        }
        briefing = {
            "title": "중대범죄수사청 개청 진행상황 관련 브리핑",
            "ministry": "행정안전부",
            "published_date": "2026.08.19",
        }
        self.assertFalse(report_matches_policy_briefing(report, briefing))
        briefing["published_date"] = "2026.07.01"
        self.assertFalse(report_matches_policy_briefing(report, briefing))

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

    def test_composite_ulji_title_uses_state_council_meeting_number(self):
        listing = json.dumps({"data": {"list": [{
            "SUBJECT": "제1회 을지국무회의 및 제36회 국무회의 관련 브리핑",
            "WRITE_DATE": "2026.08.18", "BBS_CD": "brief-36",
        }]}}).encode()
        item = parse_president_list(listing)[0]
        self.assertEqual(item["meeting_number"], 36)

    def test_recovers_reports_only_listed_in_presidential_briefing(self):
        meeting = {
            "agenda_count": 1,
            "agendas": [{
                "agenda_type": "DELIBERATION", "topic": "전자정부법 시행령",
            }],
            "presidential_briefing": {"paragraphs": [
                {
                    "source_span_id": "president-paragraph-2",
                    "text": (
                        "법무부가 준비한 「혐오 표현 제재방안」 토의가 진행됐고, "
                        "이어 「중동전쟁 대응현황」, 「주택 공급 후속조치」, "
                        "「중수청 출범 준비」, 「광복절 후속조치」 등 4건의 "
                        "부처보고가 있었습니다."
                    ),
                },
                {
                    "source_span_id": "president-paragraph-20",
                    "text": (
                        "국토교통부로부터 「주택 공급 후속조치」를 보고받은 후 "
                        "필요한 조치를 챙겨달라 주문했습니다."
                    ),
                },
                {
                    "source_span_id": "president-paragraph-30",
                    "text": (
                        "행정안전부가 준비한 「중수청 출범 준비」를 보고받은 후 "
                        "누락이 없는지 챙겨달라 당부했습니다."
                    ),
                },
            ]},
        }
        self.assertEqual(attach_presidential_ministry_reports(meeting), 4)
        reports = [
            item for item in meeting["agendas"]
            if item["agenda_type"] == "REPORT"
        ]
        self.assertEqual(len(reports), 4)
        self.assertNotIn("혐오 표현 제재방안", [item["topic"] for item in reports])
        self.assertEqual(reports[1]["ministries"], ["국토교통부"])
        self.assertEqual(reports[2]["ministries"], ["행정안전부"])
        self.assertEqual(reports[0]["ministries"], ["관계부처"])
        self.assertEqual(meeting["agenda_count"], 5)

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
        self.assertNotIn("summary", meeting["agendas"][0])
        self.assertNotIn("summary", meeting["agendas"][1])

    def test_prefers_substantive_later_report_paragraph_over_agenda_listing(self):
        meeting = {
            "agendas": [{
                "agenda_type": "REPORT",
                "topic": "2026년 추석 민생안정대책",
                "ministries": ["재정경제부"],
            }],
            "presidential_briefing": {"paragraphs": [
                {
                    "source_span_id": "president-paragraph-2",
                    "text": "오늘 회의에서는 2026년 추석 민생안정대책 등 2건의 부처 보고가 있었습니다.",
                },
                {
                    "source_span_id": "president-paragraph-16",
                    "text": "재정경제부가 마련한 추석 민생 안정 대책에 대해서는 물가 문제를 확실하게 지원해 주면 좋겠다고 강조했습니다.",
                },
                {
                    "source_span_id": "president-paragraph-17",
                    "text": "전남광주통합특별시 국립의대 부지와 관련해 지원 조치를 해 달라 당부했습니다.",
                },
            ]},
        }
        self.assertEqual(attach_presidential_guidance(meeting), 1)
        report = meeting["agendas"][0]
        self.assertIn("물가 문제", report["discussion_summary"])
        self.assertNotIn("국립의대", report["discussion_summary"])
        self.assertIn("물가 문제", report["presidential_guidance"][0]["text"])

    def test_presidential_guidance_does_not_overwrite_ministry_report_summary(self):
        meeting = {
            "agendas": [{
                "agenda_type": "REPORT",
                "topic": "2026년 추석 민생안정대책",
                "summary": "재정경제부가 추석 성수품 공급과 소상공인 지원안을 보고했다.",
                "ministries": ["재정경제부"],
            }],
            "presidential_briefing": {"paragraphs": [{
                "source_span_id": "president-paragraph-29",
                "text": "추석 민생 안정 대책과 관련해 물가를 확실하게 지원해 달라고 강조했습니다.",
            }]},
        }
        self.assertEqual(attach_presidential_guidance(meeting), 1)
        report = meeting["agendas"][0]
        self.assertIn("성수품 공급", report["summary"])
        self.assertIn("물가를 확실하게", report["presidential_guidance"][0]["text"])
        self.assertNotEqual(
            report["summary"], report["presidential_guidance"][0]["text"],
        )

    def test_does_not_attach_multi_report_agenda_listing_as_discussion(self):
        meeting = {
            "agendas": [
                {"agenda_type": "REPORT", "topic": "중동전쟁 관련 비상국정운영 및 대응현황", "ministries": ["재정경제부"]},
                {"agenda_type": "REPORT", "topic": "독자 AI 모델 개발 도전 의의 및 성과", "ministries": ["과학기술정보통신부"]},
                {"agenda_type": "REPORT", "topic": "세계 최고의 AI 민주정부 실현 전략", "ministries": ["행정안전부"]},
                {"agenda_type": "REPORT", "topic": "국민의 일상을 바꾸는 고속철도 통합", "ministries": ["국토교통부"]},
                {"agenda_type": "REPORT", "topic": "업무보고 후속조치 이행상황", "ministries": ["국무조정실"]},
            ],
            "presidential_briefing": {"paragraphs": [{
                "source_span_id": "president-paragraph-2",
                "text": "오늘 회의에서는 중동전쟁 관련 비상국정운영 및 대응현황, 독자 AI 모델 개발 도전 의의 및 성과, 세계 최고의 AI 민주정부 실현 전략, 국민의 일상을 바꾸는 고속철도 통합, 업무보고 후속조치 이행상황 등 5건의 부처보고가 있었습니다.",
            }]},
        }
        self.assertEqual(attach_presidential_guidance(meeting), 0)
        self.assertNotIn("discussion_summary", meeting["agendas"][0])
        self.assertNotIn("discussion_summary", meeting["agendas"][-1])


if __name__ == "__main__":
    unittest.main()
