from __future__ import annotations

import unittest

from app.services.official_speaker_presentation import apply_official_speakers
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


if __name__ == "__main__":
    unittest.main()
