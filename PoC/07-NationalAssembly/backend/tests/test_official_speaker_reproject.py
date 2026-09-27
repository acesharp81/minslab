from __future__ import annotations

import unittest

from app.ingestion.official_speaker_reproject import _unknown_points


class OfficialSpeakerReprojectTests(unittest.TestCase):
    def test_only_evidenced_official_names_count_as_confirmed(self) -> None:
        brief = {"topics": [{"speaker_points": [
            {"speaker_label": "김영진", "speaker_official": True,
             "official_evidence_ids": ["official-1"]},
            {"speaker_label": "소위 소장"},
            {"speaker_label": "화자 0"},
        ]}]}
        self.assertEqual(_unknown_points(brief), 2)


if __name__ == "__main__":
    unittest.main()
