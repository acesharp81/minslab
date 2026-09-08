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

    def test_groups_reports_directives_and_deliberated_agendas_without_full_briefing(self):
        meeting = {
            "presidential_briefing": {
                "briefing_id": "president-37",
                "title": "제37회 국무회의 결과 관련 수석대변인 서면 브리핑",
                "paragraphs": [{
                    "source_span_id": "president-paragraph-9",
                    "text": "관계부처에 민생 대책을 신속히 마련해 달라고 지시했습니다.",
                }],
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
            ["부처 보고 내용", "그 밖의 대통령 지시", "심의안건"],
        )
        self.assertEqual([group["count"] for group in groups], [1, 1, 1])
        self.assertEqual(
            groups[1]["items"][0]["content_type"],
            "PRESIDENTIAL_DIRECTIVE",
        )
        self.assertIn("민생 대책을 신속히 마련해 달라", groups[1]["items"][0]["display_text"])
        self.assertNotIn("지시했습니다", groups[1]["items"][0]["display_text"])

    def test_excludes_presidential_commentary_without_an_action_request(self):
        groups = build_executive_content_groups({
            "presidential_briefing": {
                "paragraphs": [{
                    "source_span_id": "commentary-1",
                    "text": "국방 역량이 충분하다는 점을 다시 강조했습니다.",
                }],
            },
            "agendas": [],
        })
        presidential = next(
            group for group in groups if group["key"] == "presidential_directives"
        )
        self.assertEqual(presidential["count"], 0)

    def test_groups_continuing_directives_and_preserves_official_paragraphs(self):
        groups = build_executive_content_groups({
            "presidential_briefing": {"paragraphs": [
                {
                    "source_span_id": "president-paragraph-17",
                    "text": "네팔 홍수와 관련해 구조 인력과 헬기를 추가 투입해 달라 지시했습니다.",
                },
                {
                    "source_span_id": "president-paragraph-18",
                    "text": "이어 수색 인력의 안전에도 각별히 주의해 달라 당부했습니다.",
                },
            ]},
            "agendas": [],
        })
        presidential = next(
            group for group in groups if group["key"] == "presidential_directives"
        )
        self.assertEqual(presidential["count"], 1)
        directive = presidential["items"][0]
        self.assertEqual(directive["topic"], "네팔 홍수")
        self.assertEqual(
            directive["source_span_ids"],
            ["president-paragraph-17", "president-paragraph-18"],
        )
        self.assertEqual(len(directive["source_paragraphs"]), 2)
        self.assertIn("헬기", directive["display_text"])
        self.assertIn("수색 인력", directive["display_text"])

    def test_keeps_different_directive_topics_separate(self):
        groups = build_executive_content_groups({
            "presidential_briefing": {"paragraphs": [
                {
                    "source_span_id": "president-paragraph-13",
                    "text": "예산안 편성을 잘 마무리해 달라 당부했습니다.",
                },
                {
                    "source_span_id": "president-paragraph-15",
                    "text": "이 대통령은 경찰 기강해이와 치안 문제를 언급했습니다.",
                },
                {
                    "source_span_id": "president-paragraph-16",
                    "text": "이어 국민 의견을 수렴해 경찰 개혁안을 마련해 달라 지시했습니다.",
                },
            ]},
            "agendas": [],
        })
        presidential = next(
            group for group in groups if group["key"] == "presidential_directives"
        )
        self.assertEqual(presidential["count"], 2)
        self.assertEqual(
            presidential["items"][1]["topic"], "경찰 수사 책임·조직 개혁",
        )
        self.assertEqual(len(presidential["items"][1]["source_paragraphs"]), 2)
        self.assertIn("개혁안을 마련해 달라", presidential["items"][1]["display_text"])

    def test_reassigns_report_directive_and_excludes_meeting_overview(self):
        meeting = {
            "presidential_briefing": {"paragraphs": [
                {
                    "source_span_id": "president-paragraph-5",
                    "text": "비공개 회의에서는 부처 보고 3건과 협조 요청 1건 외에 법률안 18건을 심의·의결했습니다.",
                },
                {
                    "source_span_id": "president-paragraph-11",
                    "text": "대통령 세종 집무실과 국회 세종의사당 건립에 속도를 내고 차질없이 진행해 주기 바란다고 주문했습니다.",
                },
            ]},
            "agendas": [{
                "agenda_type": "REPORT",
                "topic": "대통령 세종 집무실 건립 및 국가상징구역 조성 현황·계획",
                "ministries": ["행정중심복합도시건설청"],
            }],
        }
        groups = build_executive_content_groups(meeting)
        report = groups[0]["items"][0]
        presidential = groups[1]
        self.assertEqual(presidential["count"], 0)
        self.assertEqual(len(report["presidential_guidance"]), 1)
        self.assertEqual(
            report["presidential_guidance"][0]["target_ministries"],
            ["행정중심복합도시건설청"],
        )
        self.assertNotIn("협조 요청 1건", report["presidential_guidance"][0]["text"])

    def test_keeps_all_content_group_headings_when_sources_are_empty(self):
        groups = build_executive_content_groups({
            "presidential_briefing": None,
            "agendas": [{"agenda_type": "DELIBERATION", "topic": "시행령안"}],
        })
        self.assertEqual(
            [group["label"] for group in groups],
            ["부처 보고 내용", "그 밖의 대통령 지시", "심의안건"],
        )
        self.assertEqual([group["count"] for group in groups], [0, 0, 1])

    def test_labels_presidential_briefing_recovered_report_source(self):
        result = filter_executive_briefings([{
            "news_id": "state-36",
            "title": "제36회 국무회의 브리핑",
            "agendas": [{
                "agenda_type": "REPORT",
                "topic": "주택 신속공급 방안 후속조치 계획",
                "summary": "국토교통부의 보고 사실이 청와대 브리핑에서 확인됐습니다.",
                "ministries": ["국토교통부"],
                "source_origin": "PRESIDENTIAL_BRIEFING",
            }],
        }])
        report = result["items"][0]["agendas"][0]
        self.assertEqual(
            report["report_content"]["source_label"],
            "공식자료만 반영 · 상세내용 미공개",
        )
        self.assertIn("세부 보고 내용이 공개되지 않아", report["report_content"]["text"])
        self.assertNotIn("확인됐습니다", report["report_content"]["text"])

    def test_live_report_content_is_separate_from_presidential_guidance(self):
        meeting = {
            "news_id": "state-38",
            "agendas": [{
                "agenda_type": "REPORT",
                "topic": "2027년도 예산안 및 국가재정운용계획",
                "summary": "기존에는 대통령 지시 문단으로 덮어쓴 값",
                "ministries": ["기획예산처"],
                "presidential_guidance": [{
                    "label": "대통령 지시사항",
                    "text": "국회의 보완 의견을 적극 존중해 달라고 당부했습니다.",
                    "target_ministries": ["기획예산처"],
                    "source_span_ids": ["president-paragraph-15"],
                }],
                "related_ministry_briefings": [{
                    "title": "2027년도 예산안 브리핑",
                    "summary": "기획예산처가 별도로 발표한 예산안 설명입니다.",
                }],
            }],
            "presidential_briefing": {"paragraphs": []},
        }
        live = {"state-38": {
            "broadcast_id": "broadcast-38",
            "brief": {"topics": [{
                "title": "내년 예산안 편성: 미래성장동력과 청년 지원",
                "summary": "정부가 미래 성장동력과 청년 지원에 중점을 두어 예산안을 편성했다고 보고했다.",
            }]},
        }}
        result = filter_executive_briefings(
            [meeting], live_briefs_by_official_id=live,
        )
        report = result["items"][0]["agendas"][0]
        self.assertEqual(
            report["report_content"]["source_label"], "LIVE 저장본 요약",
        )
        self.assertIn("미래 성장동력", report["report_content"]["text"])
        self.assertIn("국회의 보완", report["presidential_guidance"][0]["text"])
        self.assertEqual(
            report["presidential_guidance"][0]["label"], "대통령 지시",
        )
        self.assertIn(
            "별도로 발표", report["related_ministry_briefings"][0]["summary"],
        )
        self.assertNotEqual(
            report["report_content"]["text"],
            report["presidential_guidance"][0]["text"],
        )
        self.assertIn("부처 보고 1건", result["items"][0]["presentation_summary"])

    def test_duplicate_live_summary_is_not_reused_as_ministry_report_content(self):
        directive = "물가 문제만큼은 확실하게 지원해 달라고 강조했습니다."
        meeting = {
            "news_id": "state-38", "presidential_briefing": {"paragraphs": []},
            "agendas": [{
                "agenda_type": "REPORT", "topic": "2026년 추석 민생안정대책",
                "ministries": ["재정경제부"],
                "presidential_guidance": [{"text": directive}],
            }],
        }
        live = {"state-38": {"brief": {"topics": [{
            "title": "추석 민생안정대책과 물가 지원",
            "summary": directive,
        }]}}}
        result = filter_executive_briefings(
            [meeting], live_briefs_by_official_id=live,
        )
        report = result["items"][0]["agendas"][0]
        self.assertEqual(
            report["report_content"]["source_label"],
            "공식자료만 반영 · 상세내용 미공개",
        )
        self.assertEqual(
            report["report_content"]["separation_reason"],
            "PRESIDENTIAL_GUIDANCE_DUPLICATE_SUPPRESSED",
        )
        self.assertNotEqual(report["report_content"]["text"], directive)

    def test_uses_official_presidential_discussion_facts_without_directive(self):
        result = filter_executive_briefings([{
            "news_id": "state-37",
            "agendas": [{
                "agenda_type": "REPORT",
                "topic": "국민의 일상을 바꾸는 고속철도 통합",
                "ministries": ["국토교통부"],
                "summary": "공식 결과문에서 보고 제목과 담당 부처가 확인됐습니다.",
                "discussion_summary": (
                    "SRT와 통합 후 KTX 운임이 평균 10% 인하됐습니다. "
                    "철도 운영 적자를 함께 점검했습니다. "
                    "교통 양극화 대책도 검토해 달라 지시했습니다."
                ),
            }],
        }])
        content = result["items"][0]["agendas"][0]["report_content"]
        self.assertEqual(content["source_label"], "공식 대통령실 브리핑 기반")
        self.assertIn("KTX 운임", content["text"])
        self.assertIn("철도 운영 적자", content["text"])
        self.assertNotIn("검토해 달라", content["text"])

    def test_confirmation_only_summary_is_final_official_limited_not_pending(self):
        result = filter_executive_briefings([{
            "news_id": "state-33",
            "agendas": [{
                "agenda_type": "REPORT", "topic": "정부 대응현황",
                "ministries": ["관계부처"],
                "summary": "공식 결과문에서 보고 주제가 확인됐으며 담당 부처는 관계부처로 표기합니다.",
            }],
        }])
        content = result["items"][0]["agendas"][0]["report_content"]
        self.assertEqual(content["authority_status"], "OFFICIAL_LIMITED")
        self.assertNotIn("연결하는 중", content["text"])

    def test_uses_substantive_official_summary_before_title_fallback(self):
        result = filter_executive_briefings([{
            "news_id": "state-summary",
            "agendas": [{
                "agenda_type": "REPORT",
                "topic": "민생안정대책",
                "ministries": ["재정경제부"],
                "summary": "성수품 공급을 확대하고 소상공인 금융 지원을 보강하는 대책입니다.",
            }],
        }])
        content = result["items"][0]["agendas"][0]["report_content"]
        self.assertEqual(content["source_label"], "공식 결과문 요약")
        self.assertIn("성수품 공급", content["text"])

    def test_verified_ministry_briefing_supplies_report_content_without_llm(self):
        meeting = {
            "news_id": "state-37", "presidential_briefing": {"paragraphs": []},
            "agendas": [{
                "agenda_type": "REPORT", "topic": "AI민주정부 실현 전략",
                "ministries": ["행정안전부"],
                "presidential_guidance": [{
                    "text": "민간 참여 방안을 검토해 달라고 지시했습니다.",
                }],
                "related_ministry_briefings": [{
                    "title": "AI민주정부 실현전략",
                    "summary": (
                        "안녕하십니까. 행정안전부 인공지능정부실장 황규철입니다. "
                        "오늘 국무회의에서 보고한 전략을 말씀드리겠습니다. "
                        "정부는 국민이 국정운영의 실질적 주체가 되도록 정부 운영 전반을 혁신합니다. "
                        "공공서비스를 AI 기반으로 재설계해 국민의 삶에 변화를 만들겠습니다."
                    ),
                    "source_url": "https://example.test/ai-government",
                    "authority_status": "OFFICIAL",
                    "relation": {"authority_status": "VERIFIED"},
                }],
            }],
        }
        result = filter_executive_briefings([meeting])
        report = result["items"][0]["agendas"][0]
        content = report["report_content"]
        self.assertEqual(content["source_label"], "공식 부처 브리핑 기반")
        self.assertIn("정부 운영 전반을 혁신", content["text"])
        self.assertNotIn("안녕하십니까", content["text"])
        self.assertNotIn("황규철", content["text"])
        self.assertNotEqual(content["text"], report["presidential_guidance"][0]["text"])
        additional = report["related_ministry_briefings"][0]
        self.assertIn("정부 운영 전반을 혁신", additional["display_summary"])
        self.assertLessEqual(len(additional["display_summary"]), 440)

    def test_official_briefing_excerpt_prefers_policy_steps_over_late_numbers(self):
        meeting = {
            "news_id": "state-housing",
            "agendas": [{
                "agenda_type": "REPORT",
                "topic": "주택 신속공급 방안 후속조치 계획",
                "ministries": ["국토교통부"],
                "related_ministry_briefings": [{
                    "title": "주택 신속공급 방안",
                    "summary": (
                        "최근 주택가격이 상승하고 있습니다. "
                        "첫째, 공급 발표와 착공 사이의 시차를 줄이겠습니다. "
                        "둘째, 민간 공급을 위해 금융·세제·규제를 개선하겠습니다. "
                        "셋째, 조기 착공 인센티브로 공급을 확대하겠습니다. "
                        "또한, 후반 사업지에서 3,700호를 공급할 계획입니다."
                    ),
                    "authority_status": "OFFICIAL",
                    "relation": {"authority_status": "VERIFIED"},
                }],
            }],
        }
        content = filter_executive_briefings([meeting])["items"][0]["agendas"][0]["report_content"]
        self.assertIn("공급 발표와 착공", content["text"])
        self.assertIn("금융·세제·규제", content["text"])
        self.assertNotIn("최근 주택가격", content["text"])

    def test_official_press_release_supplies_actual_report_content(self):
        meeting = {
            "news_id": "state-housing",
            "agendas": [{
                "agenda_type": "REPORT",
                "topic": "주택 신속공급 방안 후속조치 계획",
                "ministries": ["국토교통부"],
                "related_ministry_briefings": [{
                    "title": "주택 신속공급 방안 속도감 있는 이행에 총력",
                    "summary": (
                        "첫째, 공공택지 조성 기간을 단축해 공급 시점을 앞당깁니다. "
                        "둘째, 민간 공급을 가로막는 금융·세제·규제를 개선합니다."
                    ),
                    "source_kind": "PRESS_RELEASE",
                    "authority_status": "OFFICIAL",
                    "relation": {"authority_status": "VERIFIED"},
                }],
            }],
        }
        content = filter_executive_briefings([meeting])["items"][0]["agendas"][0]["report_content"]
        self.assertEqual(content["source_label"], "공식 부처 보도자료 기반")
        self.assertIn("공공택지 조성 기간", content["text"])
        self.assertIn("금융·세제·규제", content["text"])


if __name__ == "__main__":
    unittest.main()
