from __future__ import annotations

import sys
import unittest
from datetime import date, time
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.adapters.national_assembly.schedule import ScheduleSourceRecord
from app.domain.schedule import normalize_schedule
from app.domain.states import ReconciliationStatus


def record(**overrides: str | None) -> ScheduleSourceRecord:
    values: dict[str, str | None] = {
        "source_record_key": "a" * 64,
        "schedule_kind": "위원회",
        "content": "합성 회의",
        "date_text": "2099-01-02",
        "time_text": "10:00~11:30",
        "meeting_type": "전체회의",
        "committee_name": "테스트위원회",
        "session_text": "제999회국회",
        "meeting_order_text": "제1차",
        "host_name": None,
        "place": "테스트 회의실",
    }
    values.update(overrides)
    return ScheduleSourceRecord(**values)  # type: ignore[arg-type]


class ScheduleNormalizerTests(unittest.TestCase):
    def test_committee_meeting_gets_stable_uid_and_parsed_times(self):
        first = normalize_schedule(record())
        second = normalize_schedule(record(content="수정된 합성 회의"))
        self.assertEqual(first.meeting_uid, second.meeting_uid)
        self.assertEqual(first.scheduled_date, date(2099, 1, 2))
        self.assertEqual(first.start_time, time(10, 0))
        self.assertEqual(first.end_time, time(11, 30))
        self.assertEqual(first.reconciliation_status, ReconciliationStatus.MATCHED)

    def test_non_meeting_event_is_preserved_without_forced_match(self):
        normalized = normalize_schedule(record(
            schedule_kind="국회행사",
            meeting_type=None,
            committee_name=None,
            time_text="15:00",
        ))
        self.assertIsNone(normalized.meeting_uid)
        self.assertEqual(normalized.start_time, time(15, 0))
        self.assertIsNone(normalized.end_time)
        self.assertEqual(normalized.reconciliation_status, ReconciliationStatus.UNRESOLVED)

    def test_invalid_date_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid SCH_DT"):
            normalize_schedule(record(date_text="20990102"))

    def test_only_configured_committees_are_in_target_scope(self):
        target = normalize_schedule(record(committee_name="행정안전위원회"))
        outside = normalize_schedule(record(committee_name="교육위원회"))
        self.assertTrue(target.is_target_committee)
        self.assertFalse(outside.is_target_committee)


if __name__ == "__main__":
    unittest.main()
