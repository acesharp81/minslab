from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.adapters.national_assembly.base import SourcePayload
from app.adapters.national_assembly.meeting_agendas import MeetingAgendasAdapter

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_meeting_agendas_response.json"


class MeetingAgendasAdapterTests(unittest.TestCase):
    def test_parses_verified_conference_and_bill_ids(self):
        payload = SourcePayload("meeting_agendas", FIXTURE.read_bytes(), "application/json", datetime.now(timezone.utc), "https://example.invalid", 200)
        row = MeetingAgendasAdapter().parse(payload)[0]
        self.assertEqual(row.conference_id, "N999001")
        self.assertEqual(row.bill_id, "PRC_SYNTHETIC_001")
        self.assertEqual(len(row.source_record_key), 64)


if __name__ == "__main__":
    unittest.main()
