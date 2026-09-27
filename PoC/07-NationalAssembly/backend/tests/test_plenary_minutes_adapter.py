from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.adapters.national_assembly.base import AdapterError, SourcePayload
from app.adapters.national_assembly.committee_minutes import PlenaryMinutesAdapter
from app.domain.committee_bundle import group_target_committee_minutes


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_plenary_minutes_response.json"


def payload(content: bytes) -> SourcePayload:
    return SourcePayload(
        "plenary_minutes", content, "application/json",
        datetime.now(timezone.utc), "https://example.invalid/plenary", 200,
    )


class PlenaryMinutesAdapterTests(unittest.TestCase):
    def test_two_official_agenda_rows_become_one_plenary_meeting(self):
        rows = PlenaryMinutesAdapter().parse(payload(FIXTURE.read_bytes()))
        self.assertEqual(len(rows), 2)
        self.assertEqual({row.committee_name for row in rows}, {"본회의"})
        self.assertEqual(len({row.source_record_key for row in rows}), 2)
        meetings = group_target_committee_minutes(rows, source_key="plenary_minutes")
        self.assertEqual(len(meetings), 1)
        self.assertEqual(meetings[0].conference_id, "N999001")
        self.assertEqual(meetings[0].session_text, "제439회")
        self.assertEqual(meetings[0].meeting_order_text, "제5차")
        self.assertEqual(len(meetings[0].sections), 2)
        self.assertEqual(group_target_committee_minutes(rows), [])

    def test_multiple_plenary_conferences_keep_independent_source_keys(self):
        data = json.loads(FIXTURE.read_text())
        first = data["nzbyfwhwaoanttzje"][1]["row"]
        second = dict(first[0])
        second["CONF_ID"] = "N999002"
        second["TITLE"] = "제22대 제439회 제6차 국회본회의 (2026년 09월 09일)"
        first.append(second)
        rows = PlenaryMinutesAdapter().parse(payload(json.dumps(data).encode()))
        meetings = group_target_committee_minutes(rows, source_key="plenary_minutes")
        self.assertEqual(len(meetings), 2)
        for meeting in meetings:
            expected = hashlib.sha256(
                f"plenary_minutes|{meeting.conference_id}".encode()
            ).hexdigest()
            self.assertEqual(meeting.meeting_source_key, expected)

    def test_rejects_unverified_meeting_class(self):
        data = json.loads(FIXTURE.read_text())
        data["nzbyfwhwaoanttzje"][1]["row"][0]["CLASS_NAME"] = "위원회"
        with self.assertRaises(AdapterError):
            PlenaryMinutesAdapter().parse(payload(json.dumps(data).encode()))


if __name__ == "__main__":
    unittest.main()
