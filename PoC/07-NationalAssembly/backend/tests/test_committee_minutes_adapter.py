from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.adapters.national_assembly.base import SourcePayload
from app.adapters.national_assembly.committee_minutes import CommitteeMinutesAdapter

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_committee_minutes_response.json"


class CommitteeMinutesAdapterTests(unittest.TestCase):
    def test_preserves_multiple_sections_for_one_conference(self):
        payload = SourcePayload("committee_minutes", FIXTURE.read_bytes(), "application/json", datetime.now(timezone.utc), "https://example.invalid", 200)
        rows = CommitteeMinutesAdapter().parse(payload)
        self.assertEqual(len(rows), 2)
        self.assertEqual({row.conference_id for row in rows}, {"N999001"})
        self.assertEqual(len({row.source_record_key for row in rows}), 2)
        self.assertEqual(rows[0].committee_name, "행정안전위원회")


if __name__ == "__main__":
    unittest.main()
