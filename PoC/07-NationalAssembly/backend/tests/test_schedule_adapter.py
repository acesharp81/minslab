from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.adapters.national_assembly.base import SourcePayload
from app.adapters.national_assembly.schedule import ScheduleAdapter


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_schedule_response.json"


class ScheduleAdapterTests(unittest.TestCase):
    def payload(self) -> SourcePayload:
        return SourcePayload(
            source_key="assembly_schedule",
            content=FIXTURE.read_bytes(),
            content_type="application/json",
            retrieved_at=datetime(2099, 1, 2, tzinfo=timezone.utc),
            source_url="https://open.assembly.go.kr/portal/openapi/ALLSCHEDULE?Type=json",
            http_status=200,
        )

    def test_normalizes_only_verified_fields(self):
        record = ScheduleAdapter().parse(self.payload())[0]
        self.assertEqual(record.committee_name, "테스트위원회")
        self.assertEqual(record.date_text, "2099-01-02")
        self.assertEqual(record.place, "테스트 회의실")
        self.assertIsNone(record.host_name)
        self.assertEqual(len(record.source_record_key), 64)

    def test_source_record_key_is_deterministic(self):
        adapter = ScheduleAdapter()
        self.assertEqual(
            adapter.parse(self.payload())[0].source_record_key,
            adapter.parse(self.payload())[0].source_record_key,
        )


if __name__ == "__main__":
    unittest.main()
