from __future__ import annotations

import unittest

from app.services.official_speaker_presentation import (
    apply_official_speakers, overlay_confirmed_brief_speakers,
    present_brief_speaker_references,
)
from app.services.transcript_presentation import group_transcript_segments


class OfficialSpeakerPresentationTests(unittest.TestCase):
    def test_official_names_split_and_merge_presentation_turns(self):
        source = [
            {
                "segment_id": "1", "broadcast_id": "b", "speaker_label": "화자 0",
                "source_speaker_label": "0", "text": "질의입니다", "cursor": 1,
                "official_reconciliation": {
                    "status": "MATCHED", "official_speaker_name": "김 의원",
                },
            },
            {
                "segment_id": "2", "broadcast_id": "b", "speaker_label": "화자 0",
                "source_speaker_label": "0", "text": "답변입니다", "cursor": 2,
                "official_reconciliation": {
                    "status": "MATCHED", "official_speaker_name": "박 장관",
                },
            },
            {
                "segment_id": "3", "broadcast_id": "b", "speaker_label": "화자 1",
                "source_speaker_label": "1", "text": "추가 답변입니다", "cursor": 3,
                "official_reconciliation": {
                    "status": "MATCHED", "official_speaker_name": "박 장관",
                },
            },
        ]
        groups = group_transcript_segments(apply_official_speakers(source))
        self.assertEqual([item["speaker_label"] for item in groups], ["김 의원", "박 장관"])
        self.assertEqual(groups[1]["segment_count"], 2)


    def test_default_brief_uses_only_evidenced_names_without_mutating_source(self):
        provisional = {"topics": [{"id": "topic-1", "speaker_points": [
            {"id": "point-1", "speaker_label": "화자 0", "summary": "질의"},
            {"id": "point-2", "speaker_label": "화자 1", "summary": "답변"},
        ]}]}
        official = {"topics": [{"id": "topic-1", "speaker_points": [
            {"id": "point-1", "speaker_label": "김의원", "speaker_official": True,
             "official_evidence_ids": ["utterance-1"]},
            {"id": "point-2", "speaker_label": "박장관", "speaker_official": True,
             "official_evidence_ids": []},
        ]}]}

        presented = overlay_confirmed_brief_speakers(provisional, official)
        points = presented["topics"][0]["speaker_points"]
        self.assertEqual(points[0]["speaker_label"], "김의원")
        self.assertEqual(points[0]["provisional_speaker_label"], "화자 0")
        self.assertEqual(points[0]["official_evidence_ids"], ["utterance-1"])
        self.assertEqual(points[1]["speaker_label"], "화자 1")
        self.assertEqual(provisional["topics"][0]["speaker_points"][0]["speaker_label"], "화자 0")


    def test_unverified_model_name_is_hidden_in_default_brief(self):
        provisional = {"topics": [{"id": "topic-1", "speaker_points": [
            {"id": "point-1", "speaker_label": "소위 소장"},
        ]}]}
        presented = overlay_confirmed_brief_speakers(provisional, {"topics": []})
        point = presented["topics"][0]["speaker_points"][0]
        self.assertEqual(point["speaker_label"], "화자 미확인")
        self.assertEqual(point["provisional_speaker_label"], "소위 소장")


    def test_official_names_replace_topic_speaker_codes_only_when_unambiguous(self):
        provisional = {"topics": [{"id": "topic-1", "speaker_points": [
            {"id": "point-1", "speaker_label": "화자 0"},
            {"id": "point-2", "speaker_label": "화자 1"},
        ]}]}
        official = {"topics": [{"id": "topic-1",
            "summary": "화자 0은 반박했고 화자 1은 답했다.",
            "speaker_points": [
                {"id": "point-1", "speaker_label": "박형수",
                 "speaker_official": True, "official_evidence_ids": ["official-1"],
                 "summary": "화자 0은 먼저 제안했다고 말했다."},
                {"id": "point-2", "speaker_label": "화자 1",
                 "speaker_official": False, "summary": "화자 1은 답했다."},
            ],
        }]}
        presented = present_brief_speaker_references(official, provisional)
        topic = presented["topics"][0]
        self.assertEqual(topic["summary"], "박형수는 반박했고 다른 참석자는 답했다.")
        self.assertEqual(topic["speaker_points"][0]["summary"], "박형수는 먼저 제안했다고 말했다.")
        self.assertEqual(topic["speaker_points"][1]["summary"], "다른 참석자는 답했다.")
        self.assertEqual(topic["speaker_points"][1]["speaker_label"], "화자 미확인")
        self.assertEqual(topic["speaker_points"][1]["provisional_speaker_label"], "화자 1")
        self.assertEqual(official["topics"][0]["summary"], "화자 0은 반박했고 화자 1은 답했다.")

    def test_official_view_keeps_ai_synopsis_anonymous_even_with_named_point(self):
        provisional = {"topics": [{"id": "topic-1", "speaker_points": [
            {"id": "point-1", "speaker_label": "화자 0"},
        ]}]}
        official = {"topics": [{"id": "topic-1",
            "summary": "화자 0은 답했다.",
            "speaker_points": [{
                "id": "point-1", "speaker_label": "박형수",
                "speaker_official": True,
                "official_evidence_ids": ["official-1"],
            }],
        }]}
        presented = present_brief_speaker_references(
            official, provisional, neutralize_topic_summaries=True,
        )
        topic = presented["topics"][0]
        self.assertEqual(topic["summary"], "한 참석자는 답했다.")
        self.assertEqual(topic["provisional_summary"], "화자 0은 답했다.")
        self.assertEqual(topic["speaker_points"][0]["speaker_label"], "박형수")
        self.assertEqual(official["topics"][0]["summary"], "화자 0은 답했다.")

    def test_conflicting_code_never_becomes_one_person(self):
        provisional = {"topics": [{"id": "topic-1", "speaker_points": [
            {"id": "point-1", "speaker_label": "화자 0"},
            {"id": "point-2", "speaker_label": "화자 0"},
        ]}]}
        official = {"topics": [{"id": "topic-1", "summary": "화자 0은 발언했다.",
            "speaker_points": [
                {"id": "point-1", "speaker_label": "박형수", "speaker_official": True,
                 "official_evidence_ids": ["official-1"]},
                {"id": "point-2", "speaker_label": "서영교", "speaker_official": True,
                 "official_evidence_ids": ["official-2"]},
            ]}]}
        presented = present_brief_speaker_references(official, provisional)
        self.assertEqual(presented["topics"][0]["summary"], "한 참석자는 발언했다.")


if __name__ == "__main__":
    unittest.main()
