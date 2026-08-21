from __future__ import annotations

import unittest
from pathlib import Path

from app.db.live_repository import LiveBroadcastObservation


MIGRATION = (
    Path(__file__).parents[1]
    / "migrations"
    / "0005_live_broadcasts_and_transcripts.sql"
)


class LiveSchemaTests(unittest.TestCase):
    def test_live_lifecycle_and_revision_tables_are_declared(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        for table in (
            "live_broadcasts",
            "live_broadcast_source_versions",
            "transcript_segments",
            "transcript_segment_revisions",
        ):
            self.assertIn(f"CREATE TABLE {table}", sql)
        self.assertIn("UNIQUE (source_system, external_id)", sql)
        self.assertIn("UNIQUE (broadcast_id, source_segment_id)", sql)
        self.assertIn("UNIQUE (segment_id, content_hash)", sql)

    def test_transcript_revisions_have_monotonic_event_cursor(self):
        sql = (MIGRATION.parent / "0007_transcript_event_cursor.sql").read_text(encoding="utf-8")
        self.assertIn("event_cursor bigint GENERATED ALWAYS AS IDENTITY", sql)
        self.assertIn("transcript_revisions_event_cursor_idx", sql)

    def test_ended_broadcast_reviews_keep_revision_evidence(self):
        sql = (MIGRATION.parent / "0008_broadcast_reviews.sql").read_text(encoding="utf-8")
        for table in ("broadcast_reviews", "broadcast_review_topics", "broadcast_review_evidence"):
            self.assertIn(f"CREATE TABLE {table}", sql)
        self.assertIn("representative_revision_id", sql)
        self.assertIn("review_lease_expires_at", sql)

    def test_official_observation_defaults_to_official_source_system(self):
        field = LiveBroadcastObservation.__dataclass_fields__["source_system"]
        self.assertEqual(field.default, "assembly.webcast.go.kr")

    def test_demo_replay_uses_an_isolated_source_system(self):
        script = (
            Path(__file__).parents[1]
            / "app"
            / "ingestion"
            / "demo_live_replay.py"
        ).read_text(encoding="utf-8")
        self.assertIn('source_system="poc07.demo"', script)
        self.assertIn('"simulation": True', script)
        self.assertIn('"task_status": "OPEN"', script)
        repository = (
            Path(__file__).parents[1] / "app" / "db" / "live_repository.py"
        ).read_text(encoding="utf-8")
        self.assertIn("observation.source_system", repository)
        self.assertIn("WHERE source_system = %s AND lifecycle_status = 'LIVE'", repository)


    def test_ended_broadcast_history_has_list_and_detail_contracts(self):
        app_source = (Path(__file__).parents[1] / "app" / "main.py").read_text(
            encoding="utf-8"
        )
        repository = (
            Path(__file__).parents[1] / "app" / "db" / "live_repository.py"
        ).read_text(encoding="utf-8")
        self.assertIn('@app.get("/api/live/broadcasts"', app_source)
        self.assertIn('@app.get("/api/live/broadcasts/{broadcast_id}/transcript"', app_source)
        self.assertIn("def list_ended_broadcasts", repository)
        self.assertIn("def ended_transcript_snapshot", repository)
        self.assertIn("broadcast.thumbnail_url", repository)
        self.assertIn("def broadcast_official_context", repository)
        self.assertIn("matched_segment_count", repository)
        self.assertIn('"official_context": official_context', app_source)

        self.assertIn('@app.get("/api/live/tasks"', app_source)
        self.assertIn("def list_open_follow_up_tasks", repository)
        self.assertIn("def broadcast_reconciliation_details", repository)
        self.assertIn("official_reconciliation", app_source)
        self.assertIn('"revision_id", "broadcast_id"', repository)
if __name__ == "__main__":
    unittest.main()
