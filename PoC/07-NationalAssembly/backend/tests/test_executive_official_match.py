from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timezone

from app.services.executive_official_match import reconcile_executive_official_matches


class Result:
    def __init__(self, rows=None):
        self.rows = rows or []

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if "SELECT id, title, detected_at" in query:
            return Result(self.rows)
        return Result()


class ExecutiveOfficialMatchTests(unittest.TestCase):
    def test_matches_same_meeting_number_and_seoul_date(self):
        broadcast_id = uuid.uuid4()
        connection = Connection([(
            broadcast_id, "제37회 국무회의",
            datetime(2026, 8, 25, 1, 0, tzinfo=timezone.utc),
        )])
        matched = reconcile_executive_official_matches(connection, [{
            "news_id": "1489521", "title": "제37회 국무회의 브리핑",
            "meeting_number": 37, "published_date": "2026.08.25",
            "content_hash": "f" * 64,
        }])
        self.assertEqual(1, matched)
        upsert = next(params for query, params in connection.calls if "INSERT INTO executive_official_matches" in query)
        self.assertEqual("1489521", upsert[1])
        self.assertEqual("MEETING_NUMBER_AND_DATE", upsert[4])

    def test_ambiguous_number_without_matching_date_is_not_forced(self):
        connection = Connection([(
            uuid.uuid4(), "제37회 국무회의",
            datetime(2026, 8, 25, 1, 0, tzinfo=timezone.utc),
        )])
        matched = reconcile_executive_official_matches(connection, [
            {"news_id": "1", "meeting_number": 37, "published_date": "2026.08.24"},
            {"news_id": "2", "meeting_number": 37, "published_date": "2026.08.26"},
        ])
        self.assertEqual(0, matched)


if __name__ == "__main__":
    unittest.main()
