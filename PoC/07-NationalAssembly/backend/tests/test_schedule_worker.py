from __future__ import annotations

import unittest
from datetime import date, datetime, timezone

from app.adapters.national_assembly.members import MemberSourceRecord
from app.adapters.national_assembly.schedule import ScheduleSourceRecord
from app.domain.schedule import normalize_schedule
from app.ingestion.schedule_worker import (
    ASSEMBLY_REFERENCE_SCHEMA, UPCOMING_SCHEDULE_SCHEMA,
    build_assembly_reference_snapshot, build_upcoming_schedule_snapshot,
)


def schedule_entry(*, committee: str, scheduled_date: str, start_time: str, title: str):
    return normalize_schedule(ScheduleSourceRecord(
        source_record_key=f"{scheduled_date}:{committee}:{start_time}:{title}",
        schedule_kind="위원회", content=title, date_text=scheduled_date,
        time_text=start_time, meeting_type="전체회의", committee_name=committee,
        session_text="제438회국회(임시회)", meeting_order_text="제1차",
        host_name=None, place=None,
    ))


class ScheduleWorkerTests(unittest.TestCase):
    def test_snapshot_keeps_only_target_committees_in_requested_range(self):
        entries = [
            schedule_entry(committee="행정안전위원회", scheduled_date="2099-01-02", start_time="10:00", title="행안위 전체회의"),
            schedule_entry(committee="예산결산특별위원회", scheduled_date="2099-01-03", start_time="10:00", title="예결위 전체회의"),
            schedule_entry(committee="교육위원회", scheduled_date="2099-01-02", start_time="09:00", title="대상 밖 회의"),
            schedule_entry(committee="법제사법위원회", scheduled_date="2099-01-04", start_time="10:00", title="범위 밖 회의"),
        ]
        snapshot = build_upcoming_schedule_snapshot(
            entries, start_date=date(2099, 1, 2), days=2,
            generated_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(snapshot["schema_version"], UPCOMING_SCHEDULE_SCHEMA)
        self.assertEqual(snapshot["count"], 2)
        self.assertEqual(
            [item["committee_name"] for item in snapshot["items"]],
            ["행정안전위원회", "예산결산특별위원회"],
        )
        self.assertTrue(all(item["authority_status"] == "OFFICIAL" for item in snapshot["items"]))

    def test_reference_snapshot_counts_only_active_current_term_members(self):
        members = [
            MemberSourceRecord(
                member_code="a", name="현역 지역구",
                parties=("옛정당", "현재정당"),
                elected_terms=("제21대", "제22대"),
                election_types=("지역구", "지역구"), gender="남",
                duty_name="위원", committee_name="행정안전위원회",
            ),
            MemberSourceRecord(
                member_code="b", name="현역 비례", parties=("비례정당",),
                elected_terms=("제22대",), election_types=("비례대표",),
                gender="여", duty_name="위원", committee_name="법제사법위원회",
            ),
            MemberSourceRecord(
                member_code="c", name="임기 종료", parties=("이전정당",),
                elected_terms=("제22대",), election_types=("비례대표",),
                gender="여", duty_name=None, committee_name=None,
            ),
        ]
        snapshot = build_assembly_reference_snapshot(
            members, current_term="제22대",
            generated_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(ASSEMBLY_REFERENCE_SCHEMA, snapshot["schema_version"])
        self.assertEqual(2, snapshot["seat_count"])
        self.assertEqual(
            [{"label": "비례정당", "count": 1}, {"label": "현재정당", "count": 1}],
            snapshot["party_seats"],
        )
        self.assertEqual(2, snapshot["committee_count"])

    def test_runtime_and_web_use_upcoming_schedule_worker(self):
        from pathlib import Path
        project_dir = Path(__file__).resolve().parents[2]
        script = (project_dir / "web/app.js").read_text(encoding="utf-8")
        worker = (project_dir / "backend/app/ingestion/schedule_worker.py").read_text(encoding="utf-8")
        self.assertIn('filters={"SCH_DT": target_date.isoformat()}', worker)
        self.assertIn('api/schedule/today', script)
        self.assertIn("mergedOfficialSchedules", script)
        self.assertIn("scheduleDateLabel", script)
        extras = (project_dir / "web/assembly-extras.js").read_text(encoding="utf-8")
        api = (project_dir / "backend/app/main.py").read_text(encoding="utf-8")
        repository = (project_dir / "backend/app/db/schedule_repository.py").read_text(encoding="utf-8")
        self.assertIn("api/schedule/calendar", extras)
        self.assertIn("api/assembly/reference", extras)
        self.assertIn("calendar range is limited to 42 days", api)
        self.assertIn("_reference_snapshot_fresh", worker)
        self.assertIn("DISTINCT ON (se.source_record_key)", repository)


if __name__ == "__main__":
    unittest.main()
