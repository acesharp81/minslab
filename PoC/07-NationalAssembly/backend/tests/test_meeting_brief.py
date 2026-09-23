from __future__ import annotations

import unittest
from types import SimpleNamespace

import requests
from unittest import mock

from app.ingestion.meeting_brief_worker import (
    brief_retry_hours,
    meeting_brief_identity,
    safe_brief_error_code,
)
from app.services.meeting_brief import (
    ANALYSIS_CACHE_VERSION,
    OPENROUTER_FINAL_RETRY_MODEL,
    OPENROUTER_FINAL_MAX_TOKENS,
    OPENROUTER_GATEWAY_TIMEOUT_SECONDS,
    OPENROUTER_STRUCTURED_RETRY_MODEL,
    MAX_FINAL_TOPICS,
    PROMPT_VERSION,
    MistralMeetingBriefClient,
    MalformedMeetingBriefResponse,
    OpenRouterMeetingBriefClient,
    _assert_summary_quality,
    _clean_text,
    clean_task_title,
    _sanitize_final_display_language,
    brief_response_schema,
    iter_meeting_chunks,
    improve_promoted_topic_summaries,
    meeting_transcript_hash,
    minimum_final_topic_count,
    minimum_final_task_count,
    promote_unassigned_live_topics,
    validate_meeting_brief,
)


class MeetingBriefTests(unittest.TestCase):
    def setUp(self):
        self.utterances = [
            {
                "utterance_id": f"u-{index}",
                "content_hash": str(index) * 64,
                "speaker_label": f"화자 {index % 2}",
                "summary": f"요약 {index}",
                "text": f"근거 발언 {index}",
            }
            for index in range(1, 5)
        ]

    def test_meeting_brief_identity_uses_brief_prompt_version(self):
        settings = SimpleNamespace(
            llm_provider="openrouter",
            llm_model="summary-model",
            meeting_brief_model="brief-model",
        )

        self.assertEqual(
            ("openrouter", "brief-model", PROMPT_VERSION),
            meeting_brief_identity(settings),
        )

    def test_meeting_brief_identity_can_select_independent_mistral_reserve(self):
        settings = SimpleNamespace(
            llm_provider="openrouter",
            llm_model="summary-model",
            meeting_brief_provider="mistral",
            meeting_brief_model="brief-model",
            meeting_brief_mistral_model="mistral-small-2603",
        )

        self.assertEqual(
            ("mistral", "mistral-small-2603", PROMPT_VERSION),
            meeting_brief_identity(settings),
        )

    def test_transcript_hash_is_stable_and_chunks_preserve_order(self):
        first = meeting_transcript_hash(self.utterances)
        second = meeting_transcript_hash(list(self.utterances))
        self.assertEqual(first, second)
        chunks = list(iter_meeting_chunks(self.utterances, max_items=2))
        self.assertEqual(
            [["u-1", "u-2"], ["u-3", "u-4"]],
            [[item["utterance_id"] for item in chunk] for chunk in chunks],
        )

    def test_quality_gate_repairs_known_residue_and_rejects_unknown_latin(self):
        self.assertEqual("청와대 협의 의혹", _clean_text("청와대 협의 sospicion", 100))
        self.assertEqual("법사 위원회", _clean_text("법사 committee", 100))
        self.assertEqual(
            "서영교 위원장과 증인 협의 일정",
            _clean_text("서영교장과 증인 혼의 일정", 100),
        )
        self.assertEqual(
            "회의는 교육방송 교육 데이터와 데이터 연계 규격, 거버넌스를 논의했다.",
            _clean_text(
                "次会议는 EBS 교육 데이터와 API, governance를 논의했다.", 100,
            ),
        )
        self.assertEqual(
            "대외협력기금과 대외경제협력기금으로 케이마루를 지원하고 의견을 표현했다.",
            _clean_text(
                "ODCF와 EDCF로 K-MARU를 지원하고 의견을表达했다.", 100,
            ),
        )
        self.assertEqual(
            "국회는 정치 이슈와 발표 자료를 검토했고 대통령 본인이라고 지적했다.",
            _clean_text(
                "国会는 Politics 이슈와 PPT를 검토했고 대통령 herself라고 지적했다.",
                100,
            ),
        )
        self.assertEqual(
            "한반도 모병제와 완전운용능력, 공적개발원조 캠페인을 종합 논의했다.",
            _clean_text(
                "북半岛 모兵제와 FOC, ODA Campaign을 총망点 논의했다.", 100,
            ),
        )
        self.assertEqual(
            "대립 발생했다, 인사권 행사, 현재 상정",
            _clean_text("대립 occurred, 인사권 exercise, current 상정", 100),
        )
        self.assertEqual(
            "법무부장관 당시 대검찰청 기획조정장이 법원행정처 방문, 여야 간 합의 주장",
            _clean_text(
                "법무/ecology장관 unavoidably 대검찰청 기획조정ionage장이 "
                "법원행정处 visits, 여야_deepening 합의 主张",
                100,
            ),
        )
        self.assertEqual(
            "의원은 사업 현실화가 후퇴했다고 주장",
            _clean_text("议员은 BUSINESS 现实化가 后退했다고 主张", 100),
        )
        self.assertEqual(
            "검찰개혁 후퇴와 경찰 자체 개혁안, 의원의 지적",
            _clean_text("검찰개혁 후退와 경찰 SW 자체 개혁안, 의원builders의 지적", 100),
        )
        self.assertEqual(
            "정부는 의원 의견을 반영하겠다고 답변했다.",
            _clean_text("정부는 의사의的意见을 반영하겠습니다고 답변했다.", 100),
        )
        with self.assertRaisesRegex(ValueError, "unknownword"):
            _assert_summary_quality(
                {
                    "headline": "회의 결과",
                    "summary": "청와대 협의 unknownword를 점검했다.",
                    "topics": [],
                },
                {},
            )
        with self.assertRaisesRegex(ValueError, "CJK"):
            _assert_summary_quality(
                {"headline": "회의 결과", "summary": "알 수 없는 字가 남았다.", "topics": []},
                {},
            )
        with self.assertRaisesRegex(ValueError, "unknownword"):
            _assert_summary_quality(
                {
                    "headline": "회의 결과",
                    "summary": "회의 결과를 정리했다.",
                    "topics": [],
                    "tasks": [{"title": "후속 unknownword 검토", "topic_title": "후속 조치"}],
                },
                {},
            )

    def test_validation_drops_verbatim_speaker_excerpt_without_losing_topic(self):
        source = "예산 편성 기준을 구체적으로 공개하고 집행 계획을 다시 보고해 주시기 바랍니다."
        result = validate_meeting_brief(
            {
                "headline": "회의 결과",
                "summary": "예산 집행을 점검했다.",
                "topics": [
                    {
                        "title": "예산 집행",
                        "summary": "예산 편성과 집행 계획을 논의했다.",
                        "evidence_ids": ["u-1"],
                        "speaker_points": [
                        {
                            "speaker_label": "화자 1",
                            "summary": source,
                            "evidence_ids": ["u-1"],
                        }
                        ],
                    }
                ],
                "tasks": [],
            },
            {"u-1"},
            {"u-1": source},
        )
        self.assertEqual(1, len(result["topics"]))
        self.assertEqual([], result["topics"][0]["speaker_points"])

    def test_final_language_sanitizer_preserves_evidence_and_status_fields(self):
        result = _sanitize_final_display_language({
            "headline": "외교 成果 summary",
            "summary": "국회 논의에 張과 unknownword가 남았다.",
            "topics": [{
                "title": "모兵제 followup",
                "summary": "후속 政策을 promised 점검했다.",
                "evidence_ids": ["abc-def-123"],
                "speaker_points": [],
            }],
            "tasks": [{
                "title": "Campaign 후속 조치",
                "topic_title": "모兵제 followup",
                "status": "UNCONFIRMED",
                "owner_basis": "INFERRED",
                "ministries": ["외교部", "ministryword"],
                "evidence_ids": ["abc-def-123"],
            }],
        })
        self.assertEqual("외교", result["headline"])
        self.assertEqual("국회 논의에 과 가 남았다.", result["summary"])
        self.assertEqual(["abc-def-123"], result["topics"][0]["evidence_ids"])
        self.assertEqual("UNCONFIRMED", result["tasks"][0]["status"])
        self.assertEqual("INFERRED", result["tasks"][0]["owner_basis"])
        self.assertEqual(["외교"], result["tasks"][0]["ministries"])

    def test_task_title_strips_only_generated_internal_id_suffix(self):
        self.assertEqual("청문보고서 송부 요청", clean_task_title("청문보고서 송부 요청 ( id: 4)"))
        self.assertEqual("청문보고서 송부 요청", clean_task_title("청문보고서 송부 요청 (ID:4)"))
        self.assertEqual("ID 검증 서비스 구축", clean_task_title("ID 검증 서비스 구축"))

    def test_quality_gate_still_rejects_verbatim_topic_summary(self):
        source = "예산 편성 기준을 구체적으로 공개하고 집행 계획을 다시 보고해 주시기 바랍니다."
        with self.assertRaisesRegex(ValueError, "extractive"):
            _assert_summary_quality(
                {
                    "headline": "회의 결과",
                    "summary": "예산 집행을 점검했다.",
                    "topics": [{"summary": source, "evidence_ids": ["u-1"]}],
                },
                {"u-1": source},
            )

    def test_validation_rejects_invented_evidence_ids(self):
        data = {
            "headline": "결산과 후속 조치 점검",
            "summary": "기관 결산과 수사 지연 문제를 논의했다.",
            "topics": [
                {
                    "title": "수사 지연",
                    "summary": "수사 기간과 제도 개선을 질의했다.",
                    "speaker_points": [
                        {
                            "speaker_label": "화자 1",
                            "summary": "처리 기한을 질의했다.",
                            "evidence_ids": ["u-1", "invented"],
                        }
                    ],
                    "evidence_ids": ["u-1", "invented"],
                }
            ],
            "tasks": [
                {
                    "title": "처리 일정 보고",
                    "topic_title": "수사 지연",
                    "status": "OPEN",
                    "ministries": ["EXPLICIT", "법무부", "builders"],
                    "owner_basis": "EXPLICIT",
                    "evidence_ids": ["u-1", "invented"],
                }
            ],
        }
        result = validate_meeting_brief(data, {"u-1", "u-2"})
        self.assertEqual(["u-1"], result["topics"][0]["evidence_ids"])
        self.assertEqual(["u-1"], result["tasks"][0]["evidence_ids"])
        self.assertEqual(["법무부"], result["tasks"][0]["ministries"])
        self.assertEqual("topic-1", result["topics"][0]["id"])
        self.assertEqual("task-1", result["tasks"][0]["id"])
        self.assertEqual("topic-1", result["tasks"][0]["topic_id"])
        self.assertEqual("수사 지연", result["tasks"][0]["topic_title"])

    def test_speaker_label_is_restored_from_evidence_instead_of_model_output(self):
        data = {
            "headline": "결산 심사 결과",
            "summary": "기관별 결산 현황과 집행 개선 필요성을 점검했다.",
            "topics": [
                {
                    "title": "결산 집행 점검",
                    "summary": "예산 집행 현황과 개선 방향을 논의했다.",
                    "speaker_points": [
                        {
                            "speaker_label": "화자 0 · 이름 미ignacun",
                            "summary": "세입 징수체계 개선 필요성을 설명했다.",
                            "evidence_ids": ["u-1"],
                        }
                    ],
                    "evidence_ids": ["u-1"],
                }
            ],
            "tasks": [],
        }
        result = validate_meeting_brief(
            data,
            {"u-1"},
            {"u-1": "세입 징수체계를 개선해야 한다."},
            {"u-1": "화자 1 · 이름 미확인"},
        )
        self.assertEqual(
            "화자 1 · 이름 미확인",
            result["topics"][0]["speaker_points"][0]["speaker_label"],
        )

    def test_task_mapping_prefers_shared_evidence_over_different_generated_title(self):
        data = {
            "headline": "예결위 주요 결과",
            "summary": "재정과 미래 투자 과제를 논의했다.",
            "topics": [
                {
                    "title": "미래대응기금 설계와 재정 안정화 방안",
                    "summary": "재정 안정화 장치를 논의했다.",
                    "speaker_points": [],
                    "evidence_ids": ["u-1"],
                },
                {
                    "title": "3대 메가프로젝트 추진과 인프라 안정화",
                    "summary": "장기 투자 재원을 논의했다.",
                    "speaker_points": [],
                    "evidence_ids": ["u-2", "u-3"],
                },
            ],
            "tasks": [
                {
                    "title": "미래대응기금 재원과 로드맵 구체화",
                    "topic_title": "미래대응기금 설계와 재정 안정화 방안",
                    "status": "OPEN",
                    "ministries": ["기획재정부"],
                    "owner_basis": "EXPLICIT",
                    "evidence_ids": ["u-2", "u-3"],
                }
            ],
        }
        result = validate_meeting_brief(data, {"u-1", "u-2", "u-3"})
        task = result["tasks"][0]
        self.assertEqual("topic-2", task["topic_id"])
        self.assertEqual(
            "3대 메가프로젝트 추진과 인프라 안정화",
            task["topic_title"],
        )

    def test_all_live_topic_clusters_are_assigned_exactly_once(self):
        data = {
            "headline": "회의 결과",
            "summary": "예산과 재난 대응 현안을 종합적으로 점검하였다.",
            "topics": [
                {
                    "title": "예산 집행",
                    "summary": "예산 집행 현황을 점검하였다.",
                    "speaker_points": [],
                    "evidence_ids": ["u-1"],
                    "live_topic_cluster_ids": [
                        "live-topic-1",
                        "live-topic-1",
                        "live-topic-3",
                    ],
                },
                {
                    "title": "재난 대응",
                    "summary": "재난 대응 체계를 점검하였다.",
                    "speaker_points": [],
                    "evidence_ids": ["u-2"],
                    "live_topic_cluster_ids": [],
                },
            ],
            "tasks": [],
        }
        clusters = [
            {
                "id": "live-topic-1",
                "title": "예산 집행",
                "aliases": [],
                "owners": [],
                "tasks": [],
            },
            {
                "id": "live-topic-2",
                "title": "재난 대응",
                "aliases": [],
                "owners": [],
                "tasks": [],
            },
            {
                "id": "live-topic-3",
                "title": "재정 집행 점검",
                "aliases": [],
                "owners": [],
                "tasks": [],
            },
        ]
        result = validate_meeting_brief(
            data,
            {"u-1", "u-2"},
            live_topic_clusters=clusters,
        )
        assigned = [
            cluster_id
            for topic in result["topics"]
            for cluster_id in topic["live_topic_cluster_ids"]
        ]
        self.assertEqual(3, len(assigned))
        self.assertEqual(3, len(set(assigned)))
        self.assertEqual(0, result["live_topic_assignment"]["unassigned_count"])

    def test_unrelated_live_topic_is_not_forced_into_an_arbitrary_topic(self):
        data = {
            "headline": "회의 결과",
            "summary": "예산 집행 현황을 점검하였다.",
            "topics": [
                {
                    "title": "예산 집행",
                    "summary": "재정 집행 현황을 점검하였다.",
                    "speaker_points": [],
                    "evidence_ids": ["u-1"],
                    "live_topic_cluster_ids": [],
                }
            ],
            "tasks": [],
        }
        clusters = [
            {
                "id": "live-topic-1",
                "title": "문화재 복원",
                "aliases": ["전통 건축 보존"],
                "owners": ["국가유산청"],
                "tasks": [],
            }
        ]
        result = validate_meeting_brief(
            data,
            {"u-1"},
            live_topic_clusters=clusters,
        )
        self.assertEqual([], result["topics"][0]["live_topic_cluster_ids"])
        self.assertEqual(1, result["live_topic_assignment"]["unassigned_count"])
        with self.assertRaisesRegex(ValueError, "omitted live topic clusters"):
            validate_meeting_brief(
                data,
                {"u-1"},
                live_topic_clusters=clusters,
                require_complete_live_topics=True,
            )

    def test_unassigned_live_topic_is_promoted_locally_with_evidence(self):
        brief = validate_meeting_brief(
            {
                "headline": "회의 결과",
                "summary": "예산 집행 현황을 점검하였다.",
                "topics": [{
                    "title": "예산 집행",
                    "summary": "재정 집행 현황을 점검하였다.",
                    "speaker_points": [],
                    "evidence_ids": ["u-1"],
                    "live_topic_cluster_ids": [],
                }],
                "tasks": [],
            },
            {"u-1", "u-2"},
        )
        result = promote_unassigned_live_topics(
            brief,
            [{
                "id": "live-topic-1",
                "title": "문화재 복원",
                "utterance_ids": ["u-2"],
            }],
            {"u-1", "u-2"},
            {"u-2": "문화재 복원 범위와 보존 방식을 함께 검토해야 한다고 제안함."},
        )
        self.assertEqual(2, len(result["topics"]))
        self.assertEqual("문화재 복원", result["topics"][1]["title"])
        self.assertEqual(["u-2"], result["topics"][1]["evidence_ids"])
        self.assertEqual(
            ["live-topic-1"], result["topics"][1]["live_topic_cluster_ids"],
        )
        self.assertEqual(0, result["live_topic_assignment"]["unassigned_count"])
        self.assertEqual(1, result["live_topic_assignment"]["promoted_topic_count"])
        self.assertEqual(
            "문화재 복원 범위와 보존 방식을 함께 검토해야 한다고 제안함.",
            result["topics"][1]["summary"],
        )
        self.assertEqual(
            "CACHED_UTTERANCE_SUMMARY", result["topics"][1]["summary_source"]
        )

    def test_cached_title_fallback_is_upgraded_from_utterance_summary(self):
        brief = {
            "topics": [{
                "id": "topic-1",
                "title": "주택 세제 개편 방향 제시",
                "summary": (
                    "회의에서는 '주택 세제 개편 방향 제시' 관련 쟁점과 "
                    "대응 필요성을 논의했다."
                ),
                "evidence_ids": ["u-1"],
            }],
        }

        result = improve_promoted_topic_summaries(
            brief,
            {
                "u-1": (
                    "보유 중심이 아닌 거주 중심의 주택 정책을 제안하고, "
                    "1가구 1주택자의 세 부담 완화를 주장함."
                )
            },
        )

        self.assertIn("거주 중심", result["topics"][0]["summary"])
        self.assertNotIn("관련 쟁점과 대응 필요성", result["topics"][0]["summary"])
        self.assertEqual(
            "CACHED_UTTERANCE_SUMMARY", result["topics"][0]["summary_source"]
        )
        self.assertIn("관련 쟁점과 대응 필요성", brief["topics"][0]["summary"])

    def test_final_topics_have_operational_maximum_and_use_adaptive_floor(self):
        self.assertEqual("assembly-meeting-brief/1.9", PROMPT_VERSION)
        self.assertEqual("assembly-meeting-brief/1.2", ANALYSIS_CACHE_VERSION)
        self.assertEqual(
            MAX_FINAL_TOPICS,
            brief_response_schema()["properties"]["topics"]["maxItems"],
        )
        self.assertEqual(
            7,
            minimum_final_topic_count([
                {"topics": [{"title": str(index)} for index in range(12)]},
                {"topics": [{"title": "next"}]},
            ]),
        )
        self.assertEqual(
            2,
            minimum_final_topic_count([
                {"topics": [{"title": "one"}, {"title": "two"}]},
            ]),
        )
        self.assertEqual(
            4,
            minimum_final_task_count([
                {"topics": [{"tasks": [{"title": str(index)} for index in range(7)]}]},
            ]),
        )
        self.assertEqual(0, minimum_final_task_count([{"topics": [{"tasks": []}]}]))

    def test_local_topic_promotion_respects_final_topic_limit(self):
        topics = [
            {
                "id": f"topic-{index}",
                "title": f"정책 대상 {index}",
                "summary": f"정책 대상 {index}의 현황과 후속 조치를 점검하였다.",
                "speaker_points": [],
                "evidence_ids": [f"u-{index}"],
                "live_topic_cluster_ids": [],
            }
            for index in range(1, MAX_FINAL_TOPICS)
        ]
        clusters = [
            {
                "id": f"live-{index}",
                "title": f"별도 현안 {index}",
                "utterance_ids": [f"extra-{index}"],
                "utterance_count": index,
            }
            for index in range(1, 4)
        ]
        valid_ids = {
            *[f"u-{index}" for index in range(1, MAX_FINAL_TOPICS)],
            *[f"extra-{index}" for index in range(1, 4)],
        }
        result = promote_unassigned_live_topics(
            {"topics": topics, "live_topic_assignment": {}},
            clusters,
            valid_ids,
        )
        self.assertEqual(MAX_FINAL_TOPICS, len(result["topics"]))
        self.assertEqual(["live-3"], result["live_topic_assignment"]["promoted_cluster_ids"])
        self.assertEqual(2, result["live_topic_assignment"]["unassigned_count"])

    def test_liquid_structured_retry_uses_supported_parameters(self):
        response = mock.Mock(status_code=200)
        response.json.return_value = {
            "id": "retry",
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": '{"topics": []}'},
            }],
        }
        client = OpenRouterMeetingBriefClient(
            "secret",
            model="nvidia/nemotron-3-super-120b-a12b:free",
            base_url="http://openrouter-gateway:8071/api/v1",
        )
        with mock.patch(
            "app.services.meeting_brief.requests.post", return_value=response,
        ) as post:
            client._post(
                "retry",
                {"type": "object"},
                "meeting_chunk_analysis",
                model_override=OPENROUTER_STRUCTURED_RETRY_MODEL,
            )
        body = post.call_args.kwargs["json"]
        self.assertEqual(OPENROUTER_STRUCTURED_RETRY_MODEL, body["model"])
        self.assertEqual(8000, body["max_tokens"])
        self.assertNotIn("reasoning", body)
        self.assertEqual(OPENROUTER_GATEWAY_TIMEOUT_SECONDS, post.call_args.kwargs["timeout"])

    def test_primary_nemotron_uses_required_low_reasoning(self):
        response = mock.Mock(status_code=200)
        response.json.return_value = {
            "id": "primary",
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": '{"topics": []}'},
            }],
        }
        client = OpenRouterMeetingBriefClient(
            "secret",
            model="nvidia/nemotron-3-super-120b-a12b:free",
            base_url="http://openrouter-gateway:8071/api/v1",
        )
        with mock.patch(
            "app.services.meeting_brief.requests.post", return_value=response,
        ) as post:
            client._post("primary", {"type": "object"}, "meeting_chunk_analysis")
        self.assertEqual(
            {"effort": "low", "exclude": True},
            post.call_args.kwargs["json"]["reasoning"],
        )

    def test_live_topic_mapping_uses_dots_without_reasoning(self):
        response = mock.Mock(status_code=200)
        response.json.return_value = {
            "id": "mapping",
            "choices": [{
                "finish_reason": "stop",
                "message": {
                    "content": '{"assignments":[],"unresolved_cluster_ids":["c-1"]}'
                },
            }],
        }
        client = OpenRouterMeetingBriefClient(
            "secret",
            model="nvidia/nemotron-3-super-120b-a12b:free",
            base_url="http://openrouter-gateway:8071/api/v1",
        )
        with mock.patch(
            "app.services.meeting_brief.requests.post", return_value=response,
        ) as post:
            client.map_live_topics(
                {"topics": [{"id": "topic-1", "title": "예산 심사"}]},
                [{"id": "c-1", "title": "외교 현안"}],
            )
        body = post.call_args.kwargs["json"]
        self.assertEqual(OPENROUTER_FINAL_RETRY_MODEL, body["model"])
        self.assertEqual(12000, body["max_tokens"])
        self.assertEqual(
            {"enabled": False, "exclude": True}, body["reasoning"],
        )

    def test_final_retry_uses_long_context_note_model(self):
        response = mock.Mock(status_code=200)
        response.json.return_value = {
            "id": "retry",
            "choices": [{
                "finish_reason": "stop",
                "message": {
                    "content": '{"headline":"h","summary":"s","topics":[],"tasks":[]}'
                },
            }],
        }
        client = OpenRouterMeetingBriefClient(
            "secret",
            model="nvidia/nemotron-3-super-120b-a12b:free",
            base_url="http://openrouter-gateway:8071/api/v1",
        )
        with mock.patch(
            "app.services.meeting_brief.requests.post", return_value=response,
        ) as post:
            client._post(
                "retry",
                {"type": "object"},
                "meeting_brief",
                model_override=OPENROUTER_FINAL_RETRY_MODEL,
            )
        body = post.call_args.kwargs["json"]
        self.assertEqual(OPENROUTER_FINAL_RETRY_MODEL, body["model"])
        self.assertEqual(32_000, OPENROUTER_FINAL_MAX_TOKENS)
        self.assertEqual(OPENROUTER_FINAL_MAX_TOKENS, body["max_tokens"])
        self.assertEqual(
            {"enabled": False, "exclude": True}, body["reasoning"],
        )

    def test_client_generates_one_cached_brief_contract(self):
        chunk = {
            "topics": [
                {
                    "title": "결산 심사",
                    "summary": "집행 실적을 점검했다.",
                    "speaker_points": [
                        {
                            "speaker_label": "화자 1",
                            "summary": "집행 근거를 질의했다.",
                            "evidence_ids": ["u-1"],
                        }
                    ],
                    "tasks": [],
                    "evidence_ids": ["u-1"],
                }
            ],
        }
        final = {
            "headline": "결산 집행과 개선 조치를 점검",
            "summary": "예산 집행 근거와 후속 보고 필요성을 논의했다.",
            "topics": [
                {
                    "title": "결산 심사",
                    "summary": "집행 실적과 근거를 점검했다.",
                    "speaker_points": [
                        {
                            "speaker_label": "화자 1",
                            "summary": "집행 근거를 질의했다.",
                            "evidence_ids": ["u-1"],
                        }
                    ],
                    "evidence_ids": ["u-1"],
                }
            ],
            "tasks": [],
        }
        client = OpenRouterMeetingBriefClient(
            "secret",
            model="nvidia/nemotron-3-super-120b-a12b:free",
            base_url="http://openrouter-gateway:8071/api/v1",
        )
        with mock.patch.object(
            client,
            "_post",
            side_effect=[
                MalformedMeetingBriefResponse({"usage": {"prompt_tokens": 1, "completion_tokens": 1}}),
                (chunk, {"usage": {}}),
                (final, {"usage": {}}),
            ],
        ) as post, mock.patch("app.services.meeting_brief.time.sleep"):
            after_request = mock.Mock()
            on_progress = mock.Mock()
            result = client.generate(
                {"title": "회의", "committee_name": "법제사법위원회"},
                self.utterances,
                after_request=after_request,
                on_progress=on_progress,
            )
        self.assertEqual(3, post.call_count)
        self.assertNotEqual(
            post.call_args_list[0].args[0],
            post.call_args_list[1].args[0],
        )
        self.assertIn("완결된 JSON 객체만 출력", post.call_args_list[1].args[0])
        self.assertEqual(
            OPENROUTER_STRUCTURED_RETRY_MODEL,
            post.call_args_list[1].kwargs["model_override"],
        )
        self.assertEqual(
            OPENROUTER_FINAL_RETRY_MODEL,
            post.call_args_list[2].kwargs["model_override"],
        )
        self.assertEqual(3, after_request.call_count)
        self.assertEqual(4, on_progress.call_count)
        self.assertEqual("COMPLETED", on_progress.call_args.args[0]["status"])
        self.assertEqual(3, result.api_requests)
        self.assertEqual(PROMPT_VERSION, client.prompt_version)
        self.assertEqual("결산 집행과 개선 조치를 점검", result.brief["headline"])

    def test_worker_records_safe_http_status_and_short_retry(self):
        response = mock.Mock(status_code=429)
        error = requests.HTTPError(response=response)
        self.assertEqual("HTTPError:HTTP_429", safe_brief_error_code(error))
        self.assertEqual(1, brief_retry_hours(error))
        conflict = requests.HTTPError(response=mock.Mock(status_code=409))
        self.assertEqual(1, brief_retry_hours(conflict))
        self.assertAlmostEqual(5 / 60, brief_retry_hours(requests.ConnectionError()))
        self.assertAlmostEqual(5 / 60, brief_retry_hours(requests.Timeout()))
        self.assertEqual(6, brief_retry_hours(ValueError("invalid")))
        filtered = MalformedMeetingBriefResponse({"finish_reason": "content_filter"})
        self.assertEqual(
            "MalformedMeetingBriefResponse:CONTENT_FILTER",
            safe_brief_error_code(filtered),
        )

    def test_openrouter_provider_400_retries_chunk_with_structured_model(self):
        response = mock.Mock(status_code=400)
        provider_error = requests.HTTPError(response=response)
        chunk = {
            "topics": [{
                "title": "예산 심사",
                "summary": "예산 집행의 적정성을 점검했다.",
                "speaker_points": [],
                "tasks": [],
                "evidence_ids": ["u-1"],
            }],
        }
        final = {
            "headline": "예산 심사 결과",
            "summary": "예산 집행 현황과 후속 과제를 논의했다.",
            "topics": [{
                "title": "예산 심사",
                "summary": "예산 집행의 적정성을 점검했다.",
                "speaker_points": [],
                "evidence_ids": ["u-1"],
                "live_topic_cluster_ids": [],
            }],
            "tasks": [],
        }
        client = OpenRouterMeetingBriefClient(
            "secret",
            model="nvidia/nemotron-3-super-120b-a12b:free",
            base_url="http://openrouter-gateway:8071/api/v1",
        )
        with mock.patch.object(
            client,
            "_post",
            side_effect=[provider_error, (chunk, {"usage": {}}), (final, {"usage": {}})],
        ) as post, mock.patch("app.services.meeting_brief.time.sleep"):
            result = client.generate(
                {"title": "회의", "committee_name": "예산결산특별위원회"},
                self.utterances,
            )
        self.assertEqual(3, result.api_requests)
        self.assertEqual(
            OPENROUTER_STRUCTURED_RETRY_MODEL,
            post.call_args_list[1].kwargs["model_override"],
        )

    def test_length_limited_reduction_splits_only_failed_batch(self):
        chunk = {
            "topics": [{
                "title": "예산 심사",
                "summary": "예산 집행의 적정성을 점검했다.",
                "speaker_points": [],
                "tasks": [],
                "evidence_ids": ["u-1"],
            }],
        }
        final = {
            "headline": "예산 심사 결과",
            "summary": "예산 집행 현황과 후속 과제를 논의했다.",
            "topics": [{
                "title": "예산 심사",
                "summary": "예산 집행의 적정성을 점검했다.",
                "speaker_points": [],
                "evidence_ids": ["u-1"],
                "live_topic_cluster_ids": [],
            }, {
                "title": "집행 현황",
                "summary": "예산 집행 현황을 확인했다.",
                "speaker_points": [],
                "evidence_ids": ["u-1"],
                "live_topic_cluster_ids": [],
            }, {
                "title": "후속 과제",
                "summary": "예산 심사의 후속 과제를 논의했다.",
                "speaker_points": [],
                "evidence_ids": ["u-1"],
                "live_topic_cluster_ids": [],
            }],
            "tasks": [],
        }
        cached_batches: list[int] = []
        saved_batches: list[int] = []

        def load_chunk(index, _chunk_hash):
            if index <= 9:
                return chunk
            if index == 1002:
                cached_batches.append(index)
                return chunk
            return None

        def save_chunk(index, _chunk_hash, _analysis, _metadata):
            saved_batches.append(index)

        client = OpenRouterMeetingBriefClient(
            "secret",
            model="nvidia/nemotron-3-super-120b-a12b:free",
            base_url="http://openrouter-gateway:8071/api/v1",
        )
        length_error = MalformedMeetingBriefResponse({"finish_reason": "length"})
        with mock.patch(
            "app.services.meeting_brief.iter_meeting_chunks",
            return_value=[[self.utterances[0]]] * 9,
        ), mock.patch.object(
            client,
            "_post",
            side_effect=[
                length_error,
                length_error,
                length_error,
                (chunk, {"usage": {}}),
                (chunk, {"usage": {}}),
                (final, {"usage": {}}),
            ],
        ) as post, mock.patch("app.services.meeting_brief.time.sleep"):
            result = client.generate(
                {"title": "회의", "committee_name": "예산결산특별위원회"},
                self.utterances,
                load_chunk=load_chunk,
                save_chunk=save_chunk,
            )

        self.assertEqual("예산 심사 결과", result.brief["headline"])
        self.assertEqual([1002], cached_batches)
        self.assertEqual([10011, 10012], saved_batches)
        self.assertEqual(6, post.call_count)


if __name__ == "__main__":
    unittest.main()
