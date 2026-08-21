from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.adapters.national_assembly.committee_minutes import CommitteeMinuteSourceRecord
from app.domain.committee_bundle import group_target_committee_minutes


def record(committee_name: str, subject: str) -> CommitteeMinuteSourceRecord:
    return CommitteeMinuteSourceRecord(
        source_record_key=subject.encode().hex().ljust(64, "0")[:64],
        conference_id="N999001",
        conference_number="90001",
        title=f"제22대 제999회 제1차 {committee_name}",
        class_name="상임위원회",
        assembly_number="22",
        committee_name=committee_name,
        conference_date="2099-01-02",
        subject_name=subject,
        vod_url=None,
        minutes_url="https://example.invalid/minutes",
        pdf_url=None,
        pdf_file_id=None,
        department_code="9700000",
    )


class CommitteeBundleDomainTests(unittest.TestCase):
    def test_groups_sections_and_extracts_meeting_identity(self):
        meetings = group_target_committee_minutes([
            record("법제사법위원회", "첫째"),
            record("법제사법위원회", "둘째"),
        ])
        self.assertEqual(len(meetings), 1)
        self.assertEqual(len(meetings[0].sections), 2)
        self.assertEqual(meetings[0].session_text, "제999회")
        self.assertEqual(meetings[0].meeting_order_text, "제1차")

    def test_excludes_non_target_committee_from_canonical_layer(self):
        self.assertEqual(group_target_committee_minutes([record("교육위원회", "첫째")]), [])


if __name__ == "__main__":
    unittest.main()
