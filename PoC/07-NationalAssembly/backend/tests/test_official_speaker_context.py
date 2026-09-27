from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.services.official_speaker_context import resolve_brief_speaker_context
from app.services.transcript_presentation import utterance_content_hash
from app.services.meeting_brief import _evidence_speaker_label


class OfficialSpeakerContextTests(unittest.TestCase):
    def test_model_cannot_invent_name_without_source_label(self) -> None:
        self.assertEqual(
            _evidence_speaker_label(["segment-1"], {}, "소위 소장"),
            "화자 미확인",
        )
        self.assertEqual(
            _evidence_speaker_label(["segment-1"], {"segment-1": "김의겸"}, "화자 0"),
            "김의겸",
        )

    def test_reviewed_law_committee_interruption_repairs_name_and_claim(self) -> None:
        evidence_id = "df3fb4f0-b53d-4876-92d2-5adb050c1863:0"
        old_summary = (
            "자신이 증인 문제를 해결하라고 말했지만, 상대방이 이를 무시하며 "
            "시기를 연기하는 것에 대해 불만을 표현한다."
        )
        brief = {"topics": [{"speaker_points": [{
            "id": "reviewed-point", "speaker_label": "화자 0",
            "summary": old_summary, "evidence_ids": [evidence_id],
        }]}]}
        segments = [{
            "segment_id": evidence_id,
            "broadcast_id": "205bacd6-10ed-46bc-b4d6-8be4293fcab1",
            "cursor": 1, "received_at": datetime.now(timezone.utc),
            "source_speaker_label": "0", "speaker_label": "화자 0",
            "text": "내가 언제 얘기를 했어요 그것도 안 된다고 해 놓고 뭔 소리예요 지금",
        }]
        official = [{
            "utterance_id": "official-134", "speaker_name": "박형수",
            "text": "그것은 내가 먼저 얘기를 했어요. 그런데 안 된다고 그래 놓고 뭔 소리야, 지금.",
        }]
        corrected, _ = resolve_brief_speaker_context(
            brief, segments, official, reviewed_decisions=[{
                "point_id": "reviewed-point",
                "source_text_hash": utterance_content_hash(segments[0]["text"]),
                "official_utterance_id": "official-134",
                "replacement_summary": (
                    "박형수는 증인 협의안을 자신이 먼저 제안했으나 당시 "
                    "받아들여지지 않았다고 반박했다."
                ),
            }],
        )
        point = corrected["topics"][0]["speaker_points"][0]
        self.assertEqual(point["speaker_label"], "박형수")
        self.assertEqual(point["official_evidence_ids"], ["official-134"])
        self.assertEqual(
            point["summary"],
            "박형수는 증인 협의안을 자신이 먼저 제안했으나 당시 받아들여지지 않았다고 반박했다.",
        )
        self.assertTrue(point["speaker_summary_reviewed"])
        self.assertEqual(point["provisional_summary"], old_summary)
        self.assertEqual(brief["topics"][0]["speaker_points"][0]["summary"], old_summary)

    def test_review_does_not_apply_when_source_hash_changed(self) -> None:
        brief = {"topics": [{"speaker_points": [{
            "id": "reviewed-point", "speaker_label": "화자 0",
            "summary": "초안", "evidence_ids": ["segment-1"],
        }]}]}
        segments = [{
            "segment_id": "segment-1", "broadcast_id": "broadcast-1", "cursor": 1,
            "received_at": datetime.now(timezone.utc), "source_speaker_label": "0",
            "speaker_label": "화자 0", "text": "새로 바뀐 자막 문장입니다.",
        }]
        official = [{"utterance_id": "official-1", "speaker_name": "박형수",
                     "text": "증인 협의안을 먼저 제안했습니다."}]
        projected, _ = resolve_brief_speaker_context(
            brief, segments, official, reviewed_decisions=[{
                "point_id": "reviewed-point", "source_text_hash": "old-hash",
                "official_utterance_id": "official-1",
                "replacement_summary": "검토한 문장",
            }],
        )
        point = projected["topics"][0]["speaker_points"][0]
        self.assertNotEqual(point["summary"], "검토한 문장")
        self.assertNotEqual(point.get("speaker_match_method"),
                            "REVIEWED_OFFICIAL_SOURCE_V2")

    def test_substantive_speaker_replaces_wrong_greeting_match(self) -> None:
        brief = {"topics": [{"speaker_points": [{
            "id": "point-1", "speaker_label": "김영진",
            "speaker_official": True, "official_evidence_ids": ["chair-1"],
            "summary": "장관 부재와 경찰청장 공백에 대해 장관의 직접 답변이 필요하다고 지적했다.",
            "evidence_ids": ["segment-1"],
        }]}]}
        segments = [{
            "segment_id": "segment-1", "broadcast_id": "broadcast-1", "cursor": 1,
            "received_at": datetime.now(timezone.utc), "source_speaker_label": "0",
            "speaker_label": "화자 0",
            "text": (
                "다음 박상웅 위원님 의사진행발언해 주십시오. "
                "오늘 국무회의 때문에 장관이 나오지 않아 부적절합니다. "
                "경찰청장 공백에 대해서 차관이 아니라 장관이 직접 답해야 합니다."
            ),
        }]
        official = [
            {"utterance_id": "chair-1", "speaker_name": "김영진",
             "text": "다음 박상웅 위원님 의사진행발언해 주십시오."},
            {"utterance_id": "member-1", "speaker_name": "박상웅",
             "text": ("오늘 국무회의 때문에 장관이 나오지 않아 부적절합니다. "
                      "경찰청장 공백에 대해서 차관이 아니라 장관이 직접 답해야 합니다.")},
        ]

        projected, stats = resolve_brief_speaker_context(brief, segments, official)
        point = projected["topics"][0]["speaker_points"][0]
        self.assertEqual(point["speaker_label"], "박상웅")
        self.assertEqual(point["official_evidence_ids"], ["member-1"])
        self.assertEqual(stats["labels_changed"], 1)
        self.assertEqual(brief["topics"][0]["speaker_points"][0]["speaker_label"], "김영진")

    def test_unverified_generated_label_is_removed(self) -> None:
        brief = {"topics": [{"speaker_points": [{
            "speaker_label": "소위 소장", "summary": "조치를 요청했다.",
            "evidence_ids": ["segment-1"],
        }]}]}
        segments = [{
            "segment_id": "segment-1", "broadcast_id": "broadcast-1", "cursor": 1,
            "received_at": datetime.now(timezone.utc), "source_speaker_label": "1",
            "speaker_label": "화자 1", "text": "확인하겠습니다.",
        }]
        projected, stats = resolve_brief_speaker_context(brief, segments, [])
        point = projected["topics"][0]["speaker_points"][0]
        self.assertEqual(point["speaker_label"], "화자 미확인")
        self.assertFalse(point["speaker_official"])
        self.assertEqual(stats["unsupported_labels_removed"], 1)

    def test_unsupported_multi_speaker_group_is_not_confirmed(self) -> None:
        brief = {"topics": [{"speaker_points": [{
            "speaker_label": "서영교 · 손인혁", "speaker_official": True,
            "official_evidence_ids": ["official-1", "official-2"],
            "summary": "감사원은 군사법원 운영의 철저한 관리를 요구했다.",
            "evidence_ids": ["segment-1"],
        }]}]}
        segments = [{
            "segment_id": "segment-1", "broadcast_id": "broadcast-1", "cursor": 1,
            "received_at": datetime.now(timezone.utc), "source_speaker_label": "0",
            "speaker_label": "화자 0",
            "text": "철저히 잘 관리하도록 하겠습니다. 다음은 헌법재판소 업무보고입니다.",
        }]
        official = [
            {"utterance_id": "official-1", "speaker_name": "김호철",
             "text": "철저히 잘 관리하도록 하겠습니다."},
            {"utterance_id": "official-2", "speaker_name": "서영교",
             "text": "다음은 헌법재판소 업무보고입니다."},
        ]
        projected, stats = resolve_brief_speaker_context(brief, segments, official)
        point = projected["topics"][0]["speaker_points"][0]
        self.assertEqual(point["speaker_label"], "화자 미확인")
        self.assertFalse(point["speaker_official"])
        self.assertEqual(stats["ambiguous_group_labels_removed"], 1)

    def test_short_generic_reply_does_not_inherit_unrelated_summary(self) -> None:
        brief = {"topics": [{"speaker_points": [{
            "speaker_label": "화자 1", "summary": "추가 검증으로 지명이 철회될 수 있다고 지적했다.",
            "evidence_ids": ["segment-1"],
        }]}]}
        segments = [{
            "segment_id": "segment-1", "broadcast_id": "broadcast-1", "cursor": 1,
            "received_at": datetime.now(timezone.utc), "source_speaker_label": "1",
            "speaker_label": "화자 1", "text": "그렇게 알고",
        }]
        official = [{"utterance_id": "official-1", "speaker_name": "윤호중",
                     "text": "그렇게 알고 있습니다."}]
        projected, stats = resolve_brief_speaker_context(brief, segments, official)
        point = projected["topics"][0]["speaker_points"][0]
        self.assertEqual(point["speaker_label"], "화자 1")
        self.assertFalse(point["speaker_official"])
        self.assertEqual(stats["unresolved"], 1)


    def test_contextual_match_corrects_long_group_with_short_chair_reply(self) -> None:
        brief = {"topics": [{"speaker_points": [{
            "speaker_label": "박상웅 · 김영진",
            "speaker_official": True,
            "official_evidence_ids": ["chair-1"],
            "summary": (
                "제주 실종사건 1048건 중 298건을 한 경장이 처리한 실태와 "
                "경찰청장 공백 600일을 지적하며 중수청의 재수사 범위를 비판했다."
            ),
            "evidence_ids": ["segment-1"],
        }]}]}
        segments = [{
            "segment_id": "segment-1", "broadcast_id": "broadcast-1", "cursor": 1,
            "received_at": datetime.now(timezone.utc), "source_speaker_label": "0",
            "speaker_label": "화자 0",
            "text": (
                "제주 실종사건 1048건 중 한 경장이 298건을 처리했습니다. "
                "경찰청장 공백이 600일입니다. 중수청의 재수사 범위를 7대 범죄로 "
                "한정하는 것은 맞지 않습니다. 다음 위원님 말씀하십시오."
            ),
        }]
        official = [
            {"utterance_id": "member-1", "speaker_name": "박상웅",
             "text": (
                 "제주 실종사건 1048건 중 한 경장이 298건을 처리했습니다. "
                 "경찰청장 공백이 600일입니다. 중수청의 재수사 범위를 7대 범죄로 "
                 "한정하는 것은 맞지 않습니다."
             )},
            {"utterance_id": "chair-1", "speaker_name": "김영진",
             "text": "다음 위원님 말씀하십시오."},
        ]
        projected, _ = resolve_brief_speaker_context(brief, segments, official)
        point = projected["topics"][0]["speaker_points"][0]
        self.assertEqual(point["speaker_label"], "박상웅")
        self.assertEqual(point["official_evidence_ids"], ["member-1"])

    def test_short_reply_does_not_override_substantive_current_speaker(self) -> None:
        brief = {"topics": [{"speaker_points": [{
            "speaker_label": "주진우", "speaker_official": True,
            "official_evidence_ids": ["member-1"],
            "summary": "예산은 공용이므로 개인 용도로 사용할 수 없다는 원칙을 설명했다.",
            "evidence_ids": ["segment-1"],
        }]}]}
        segments = [{
            "segment_id": "segment-1", "broadcast_id": "broadcast-1", "cursor": 1,
            "received_at": datetime.now(timezone.utc), "source_speaker_label": "0",
            "speaker_label": "화자 0",
            "text": "그 예산에 대해서는 제가 잘 수사활동비는 개인 용도로 쓸 수 없는 것이 당연합니다.",
        }]
        official = [
            {"utterance_id": "reply-1", "speaker_name": "최길수",
             "text": "예산에 대해서는 제가 잘……"},
            {"utterance_id": "member-1", "speaker_name": "주진우",
             "text": "수사활동비에 대해서는 너무 상식적이잖아요. 개인 용도로 쓸 수 없는 것입니다."},
        ]
        projected, _ = resolve_brief_speaker_context(brief, segments, official)
        self.assertEqual(projected["topics"][0]["speaker_points"][0]["speaker_label"], "주진우")

    def test_short_exact_fragment_with_one_official_speaker_is_named(self) -> None:
        brief = {"topics": [{"speaker_points": [{
            "speaker_label": "화자 1", "summary": "상정을 표결하고자 함.",
            "evidence_ids": ["segment-1"],
        }]}]}
        segments = [{
            "segment_id": "segment-1", "broadcast_id": "broadcast-1", "cursor": 1,
            "received_at": datetime.now(timezone.utc), "source_speaker_label": "1",
            "speaker_label": "화자 1", "text": "상정을 표결하고자",
        }]
        official = [{"utterance_id": "official-1", "speaker_name": "김영진",
                     "text": "이 안건의 상정을 표결하고자 합니다."}]
        projected, _ = resolve_brief_speaker_context(brief, segments, official)
        point = projected["topics"][0]["speaker_points"][0]
        self.assertEqual(point["speaker_label"], "김영진")
        self.assertEqual(point["speaker_match_method"], "UNIQUE_EXACT_FRAGMENT_V1")

    def test_repeated_short_fragment_with_different_names_stays_unknown(self) -> None:
        brief = {"topics": [{"speaker_points": [{
            "speaker_label": "화자 1", "summary": "상정을 표결하고자 함.",
            "evidence_ids": ["segment-1"],
        }]}]}
        segments = [{
            "segment_id": "segment-1", "broadcast_id": "broadcast-1", "cursor": 1,
            "received_at": datetime.now(timezone.utc), "source_speaker_label": "1",
            "speaker_label": "화자 1", "text": "상정을 표결하고자",
        }]
        official = [
            {"utterance_id": "official-1", "speaker_name": "김영진",
             "text": "이 안건의 상정을 표결하고자 합니다."},
            {"utterance_id": "official-2", "speaker_name": "서영교",
             "text": "다음 안건의 상정을 표결하고자 합니다."},
        ]
        projected, _ = resolve_brief_speaker_context(brief, segments, official)
        self.assertEqual(projected["topics"][0]["speaker_points"][0]["speaker_label"], "화자 1")

    def test_unrelated_short_summary_does_not_claim_official_name(self) -> None:
        brief = {"topics": [{"speaker_points": [{
            "speaker_label": "화자 0", "summary": "감사원은 군사법원 운영을 감독한다.",
            "evidence_ids": ["segment-1"],
        }]}]}
        segments = [{
            "segment_id": "segment-1", "broadcast_id": "broadcast-1", "cursor": 1,
            "received_at": datetime.now(timezone.utc), "source_speaker_label": "0",
            "speaker_label": "화자 0", "text": "철저히 잘 관리하도록 하겠습니다.",
        }]
        official = [{"utterance_id": "official-1", "speaker_name": "김호철",
                     "text": "철저히 잘 관리하도록 하겠습니다."}]
        projected, _ = resolve_brief_speaker_context(brief, segments, official)
        self.assertEqual(projected["topics"][0]["speaker_points"][0]["speaker_label"], "화자 0")


if __name__ == "__main__":
    unittest.main()
