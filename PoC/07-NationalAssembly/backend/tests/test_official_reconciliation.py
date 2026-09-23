from __future__ import annotations

import unittest
import uuid

from app.services.official_reconciliation import (
    align_live_segments,
    apply_official_edits,
    inline_diff,
    minimal_patch_text,
    speaker_reconciliation_stats,
    style_only_equivalent,
)


class OfficialReconciliationTests(unittest.TestCase):
    def test_alignment_uses_official_speaker_without_llm(self):
        revision_id = uuid.uuid4()
        matches = align_live_segments(
            [{
                "revision_id": revision_id,
                "segment_id": "live-1",
                "speaker_label": "0",
                "text": "정부는 재난 피해 복구를 위한 예산을 신속히 편성하겠습니다",
            }],
            [{
                "utterance_id": uuid.uuid4(),
                "sequence_number": 3,
                "speaker_name": "행정안전부장관",
                "speaker_role": "국무위원",
                "text": "정부는 재난 피해 복구를 위한 예산을 신속히 편성하겠습니다.",
            }],
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["official_speaker_name"], "행정안전부장관")
        self.assertGreaterEqual(matches[0]["confidence"], 0.9)

    def test_alignment_rejects_ambiguous_generic_fragment(self):
        matches = align_live_segments(
            [{
                "revision_id": uuid.uuid4(),
                "segment_id": "live-ambiguous",
                "speaker_label": "0",
                "text": "정부는 관련 대책을 신속히 검토하고 있습니다",
            }],
            [{
                "utterance_id": uuid.uuid4(),
                "sequence_number": 1,
                "speaker_name": "장관 A",
                "text": "정부는 관련 대책을 신속히 검토하고 있습니다. 추가 방안을 보고하겠습니다.",
            }, {
                "utterance_id": uuid.uuid4(),
                "sequence_number": 2,
                "speaker_name": "장관 B",
                "text": "정부는 관련 대책을 신속히 검토하고 있습니다. 세부 계획은 추후 제출하겠습니다.",
            }],
        )
        self.assertEqual(matches, [])

    def test_speaker_stats_detect_split_and_merge_without_history_ui(self):
        stats = speaker_reconciliation_stats([
            {"source_speaker_label": "0", "official_speaker_name": "김 의원"},
            {"source_speaker_label": "0", "official_speaker_name": "박 장관"},
            {"source_speaker_label": "1", "official_speaker_name": "박 장관"},
        ])
        self.assertEqual(stats["split_source_labels"], 1)
        self.assertEqual(stats["merged_source_labels"], 1)

    def test_inline_diff_marks_changed_and_deleted_text(self):
        spans = inline_diff("행안부가 검토한다", "행안부와 경찰청이 추진한다")
        kinds = {item["kind"] for item in spans}
        self.assertIn("changed", kinds)
        self.assertIn("deleted", kinds)

    def test_inline_diff_ignores_spacing_shift_without_replacing_sentence(self):
        before = "부대가져있어요 반환하면서 녹지로 조성한 겁니다."
        after = "부대가 져있어요 반환하면서 녹지로 조성한 겁니다."
        spans = inline_diff(before, after)
        changed = "".join(
            item["text"] for item in spans if item["kind"] != "equal"
        )
        self.assertEqual("", changed.strip())

    def test_reordered_bullet_and_prose_are_style_only(self):
        before = "대법원과 법원행정처의 비상계엄 관련 회의 및 입장을 점검했다."
        after = "비상계엄 관련 회의 및 입장: 대법원·법원행정처 점검."
        self.assertTrue(style_only_equivalent(before, after))
        self.assertEqual(
            inline_diff(before, after),
            [{"kind": "equal", "text": after}],
        )
        self.assertEqual(minimal_patch_text(before, after), before)

    def test_style_filter_does_not_hide_fact_action_or_ministry_change(self):
        self.assertFalse(style_only_equivalent(
            "법무부는 관련 대책을 검토한다고 밝혔다.",
            "법무부는 관련 대책을 즉시 추진한다고 밝혔다.",
        ))
        self.assertFalse(style_only_equivalent(
            "법무부는 관련 대책을 추진한다.",
            "법무부와 경찰청은 관련 대책을 추진한다.",
        ))
        self.assertFalse(style_only_equivalent(
            "관련 사업에 20억 원을 편성한다.",
            "관련 사업에 30억 원을 편성한다.",
        ))
        self.assertFalse(style_only_equivalent(
            "법무부는 예산을 추진하고 행정안전부는 재난 대책을 검토했다.",
            "법무부는 재난 대책을 검토하고 행정안전부는 예산을 추진했다.",
        ))
        self.assertFalse(style_only_equivalent(
            "20억 원 사업과 별도 20억 원 사업을 편성한다.",
            "20억 원 사업을 편성한다.",
        ))

    def test_independent_sentence_reordering_is_style_only(self):
        self.assertTrue(style_only_equivalent(
            "법무부는 예산을 점검했다. 행정안전부는 재난 대책을 검토했다.",
            "행정안전부는 재난 대책을 검토했다. 법무부는 예산을 점검했다.",
        ))

    def test_moved_clause_is_not_reported_twice_and_real_append_is_minimal(self):
        before = (
            "법무부는 예산을 점검했다. "
            "행정안전부는 재난 대책을 검토했다."
        )
        after = (
            "행정안전부는 재난 대책을 검토했다. "
            "법무부는 예산을 점검했고 개선안을 제출했다."
        )
        spans = inline_diff(before, after)
        changed = "".join(
            item["text"] for item in spans if item["kind"] != "equal"
        )
        self.assertEqual(changed, "고 개선안을 제출했")
        self.assertFalse(any(item["kind"] == "deleted" for item in spans))
        self.assertEqual(
            minimal_patch_text(before, after),
            "법무부는 예산을 점검했고 개선안을 제출했다. "
            "행정안전부는 재난 대책을 검토했다.",
        )

    def test_minimal_patch_preserves_provisional_spacing_and_unchanged_wording(self):
        before = "이것 부대가져있어요 반환하면서 녹지로 조성한 겁니다."
        after = "이것 부대 반환 기지였어요. 반환받으면서 녹지로 조성한 겁니다."
        patched = minimal_patch_text(before, after)
        self.assertIn("이것", patched)
        self.assertIn("부대 반환", patched)
        self.assertIn("기지였어요. 반환받으면서", patched)
        self.assertIn("녹지로 조성한 겁니다.", patched)
        self.assertEqual(after, patched)

    def test_minimal_patch_does_not_duplicate_sentence_stop_at_insert_boundary(self):
        before = "대법원은 예산 집행에 반영하겠다고 밝혔다."
        after = "대법원은 예산 집행에 반영하겠다고 밝혔다. 또한 불용액 사유를 설명했다."
        patched = minimal_patch_text(before, after)
        self.assertEqual(after, patched)
        self.assertNotIn(".. 또한", patched)

    def test_official_edits_are_composed_without_overwriting_base(self):
        base = {
            "headline": "잠정 제목", "summary": "잠정 요약",
            "topics": [{"id": "topic-1", "title": "재난 대응", "summary": "검토"}],
            "tasks": [{"id": "task-1", "title": "대책 검토", "ministries": ["행안부"]}],
        }
        integrated, changes = apply_official_edits(base, [{
            "entity_type": "task", "entity_id": "task-1",
            "operation": "UPDATE", "field": "title",
            "new_text": "재난 대책 즉시 추진", "new_values": [],
            "official_utterance_ids": ["official-1"],
        }])
        self.assertEqual(base["tasks"][0]["title"], "대책 검토")
        self.assertEqual(integrated["tasks"][0]["title"], "재난 대책 즉시 추진")
        self.assertEqual(len(changes), 1)
        self.assertIn("_official_diffs", integrated["tasks"][0])
        self.assertEqual(
            integrated["tasks"][0]["official_evidence_ids"], ["official-1"]
        )

    def test_duplicate_official_topic_reuses_existing_topic_and_skips_child_task(self):
        base = {
            "headline": "법사위 결과", "summary": "사법 현안을 점검했다.",
            "topics": [{
                "id": "topic-1",
                "title": "대법관 제청 지연과 사법부 독립성 훼손 논란",
                "summary": "대법관 제청 지연과 청와대·대법원 협의 절차를 논의했다.",
            }],
            "tasks": [],
        }
        edits = [
            {
                "entity_type": "topic", "entity_id": "new-topic-1",
                "operation": "ADD", "topic_id": "new-topic-1",
                "title": "대법관 제청권과 임명권의 헌법적 절차 재정립",
                "summary": "대법관 제청권 행사와 청와대 협의 절차를 재검토했다.",
                "official_utterance_ids": ["official-1"],
            },
            {
                "entity_type": "task", "entity_id": "new-task-1",
                "operation": "ADD", "topic_id": "new-topic-1",
                "title": "대법관 제청권과 임명권 절차 재정립 TF 구성",
                "summary": "특별 TF 구성을 추진한다.",
                "official_utterance_ids": ["official-1"],
            },
        ]
        integrated, _changes = apply_official_edits(base, edits)
        self.assertEqual(len(integrated["topics"]), 1)
        self.assertEqual(
            integrated["topics"][0]["title"],
            "대법관 제청 지연과 사법부 독립성 훼손 논란",
        )
        self.assertEqual(
            integrated["topics"][0]["official_evidence_ids"], ["official-1"],
        )
        self.assertEqual(integrated["tasks"], [])


if __name__ == "__main__":
    unittest.main()
