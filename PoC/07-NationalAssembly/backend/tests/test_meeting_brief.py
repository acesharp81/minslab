from __future__ import annotations

import unittest
from unittest import mock

from app.services.meeting_brief import (
    PROMPT_VERSION,
    MistralMeetingBriefClient,
    _assert_summary_quality,
    _clean_text,
    iter_meeting_chunks,
    meeting_transcript_hash,
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

    def test_transcript_hash_is_stable_and_chunks_preserve_order(self):
        first = meeting_transcript_hash(self.utterances)
        second = meeting_transcript_hash(list(self.utterances))
        self.assertEqual(first, second)
        chunks = list(iter_meeting_chunks(self.utterances, max_items=2))
        self.assertEqual([["u-1", "u-2"], ["u-3", "u-4"]], [
            [item["utterance_id"] for item in chunk] for chunk in chunks
        ])

    def test_quality_gate_repairs_known_residue_and_rejects_unknown_latin(self):
        self.assertEqual("청와대 협의 의혹", _clean_text("청와대 협의 sospicion", 100))
        self.assertEqual("법사 위원회", _clean_text("법사 committee", 100))
        with self.assertRaisesRegex(ValueError, "unknownword"):
            _assert_summary_quality(
                {"headline": "회의 결과", "summary": "청와대 협의 unknownword를 점검했다.", "topics": []},
                {},
            )

    def test_quality_gate_rejects_verbatim_speaker_excerpt(self):
        source = "예산 편성 기준을 구체적으로 공개하고 집행 계획을 다시 보고해 주시기 바랍니다."
        with self.assertRaisesRegex(ValueError, "extractive"):
            _assert_summary_quality({
                "headline": "회의 결과", "summary": "예산 집행을 점검했다.",
                "topics": [{
                    "summary": "예산 편성과 집행 계획을 논의했다.", "evidence_ids": ["u-1"],
                    "speaker_points": [{"summary": source, "evidence_ids": ["u-1"]}],
                }],
            }, {"u-1": source})

    def test_validation_rejects_invented_evidence_ids(self):
        data = {
            "headline": "결산과 후속 조치 점검",
            "summary": "기관 결산과 수사 지연 문제를 논의했다.",
            "topics": [{
                "title": "수사 지연",
                "summary": "수사 기간과 제도 개선을 질의했다.",
                "speaker_points": [{
                    "speaker_label": "화자 1",
                    "summary": "처리 기한을 질의했다.",
                    "evidence_ids": ["u-1", "invented"],
                }],
                "evidence_ids": ["u-1", "invented"],
            }],
            "tasks": [{
                "title": "처리 일정 보고",
                "topic_title": "수사 지연",
                "status": "OPEN",
                "ministries": ["법무부"],
                "owner_basis": "EXPLICIT",
                "evidence_ids": ["u-1", "invented"],
            }],
        }
        result = validate_meeting_brief(data, {"u-1", "u-2"})
        self.assertEqual(["u-1"], result["topics"][0]["evidence_ids"])
        self.assertEqual(["u-1"], result["tasks"][0]["evidence_ids"])
        self.assertEqual("topic-1", result["topics"][0]["id"])
        self.assertEqual("task-1", result["tasks"][0]["id"])
        self.assertEqual("topic-1", result["tasks"][0]["topic_id"])
        self.assertEqual("수사 지연", result["tasks"][0]["topic_title"])

    def test_speaker_label_is_restored_from_evidence_instead_of_model_output(self):
        data = {
            "headline": "결산 심사 결과",
            "summary": "기관별 결산 현황과 집행 개선 필요성을 점검했다.",
            "topics": [{
                "title": "결산 집행 점검",
                "summary": "예산 집행 현황과 개선 방향을 논의했다.",
                "speaker_points": [{
                    "speaker_label": "화자 0 · 이름 미ignacun",
                    "summary": "세입 징수체계 개선 필요성을 설명했다.",
                    "evidence_ids": ["u-1"],
                }],
                "evidence_ids": ["u-1"],
            }],
            "tasks": [],
        }
        result = validate_meeting_brief(
            data, {"u-1"}, {"u-1": "세입 징수체계를 개선해야 한다."},
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
            "tasks": [{
                "title": "미래대응기금 재원과 로드맵 구체화",
                "topic_title": "미래대응기금 설계와 재정 안정화 방안",
                "status": "OPEN",
                "ministries": ["기획재정부"],
                "owner_basis": "EXPLICIT",
                "evidence_ids": ["u-2", "u-3"],
            }],
        }
        result = validate_meeting_brief(data, {"u-1", "u-2", "u-3"})
        task = result["tasks"][0]
        self.assertEqual("topic-2", task["topic_id"])
        self.assertEqual(
            "3대 메가프로젝트 추진과 인프라 안정화",
            task["topic_title"],
        )

    def test_client_generates_one_cached_brief_contract(self):
        chunk = {
            "topics": [{
                "title": "결산 심사", "summary": "집행 실적을 점검했다.",
                "speaker_points": [{
                    "speaker_label": "화자 1", "summary": "집행 근거를 질의했다.",
                    "evidence_ids": ["u-1"],
                }],
                "tasks": [],
                "evidence_ids": ["u-1"],
            }],
        }
        final = {
            "headline": "결산 집행과 개선 조치를 점검",
            "summary": "예산 집행 근거와 후속 보고 필요성을 논의했다.",
            "topics": [{
                "title": "결산 심사", "summary": "집행 실적과 근거를 점검했다.",
                "speaker_points": [{
                    "speaker_label": "화자 1", "summary": "집행 근거를 질의했다.",
                    "evidence_ids": ["u-1"],
                }],
                "evidence_ids": ["u-1"],
            }],
            "tasks": [],
        }
        client = MistralMeetingBriefClient(
            "secret", model="mistral-small-2603", base_url="https://api.mistral.ai/v1",
        )
        with mock.patch.object(
            client, "_post",
            side_effect=[(chunk, {"usage": {}}), (final, {"usage": {}})],
        ) as post:
            after_request = mock.Mock()
            on_progress = mock.Mock()
            result = client.generate(
                {"title": "회의", "committee_name": "법제사법위원회"},
                self.utterances,
                after_request=after_request,
                on_progress=on_progress,
            )
        self.assertEqual(2, post.call_count)
        self.assertEqual(2, after_request.call_count)
        self.assertEqual(4, on_progress.call_count)
        self.assertEqual("COMPLETED", on_progress.call_args.args[0]["status"])
        self.assertEqual(2, result.api_requests)
        self.assertEqual(PROMPT_VERSION, client.prompt_version)
        self.assertEqual("결산 집행과 개선 조치를 점검", result.brief["headline"])


if __name__ == "__main__":
    unittest.main()
