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

    def test_report_reads_use_denormalized_broadcast_cursor(self):
        project = Path(__file__).parents[2]
        migration = (
            project / "backend/migrations/0045_report_read_cursor.sql"
        ).read_text(encoding="utf-8")
        live_repository = (
            project / "backend/app/db/live_repository.py"
        ).read_text(encoding="utf-8")
        brief_repository = (
            project / "backend/app/db/meeting_brief_repository.py"
        ).read_text(encoding="utf-8")
        self.assertIn("ADD COLUMN source_last_event_cursor", migration)
        self.assertIn("live_broadcasts_ended_detected_idx", migration)
        self.assertIn("source_last_event_cursor = GREATEST", live_repository)
        self.assertIn("WITH recent_broadcasts AS MATERIALIZED", live_repository)
        self.assertIn("broadcast.source_last_event_cursor", brief_repository)
        self.assertNotIn("SELECT COALESCE(MAX(revision.event_cursor)", brief_repository)

    def test_official_context_reads_denormalized_counts(self):
        project = Path(__file__).parents[2]
        migration = (
            project / "backend/migrations/0046_official_context_read_model.sql"
        ).read_text(encoding="utf-8")
        repository = (
            project / "backend/app/db/live_repository.py"
        ).read_text(encoding="utf-8")
        self.assertIn("ADD COLUMN final_segment_count", migration)
        self.assertIn("ADD COLUMN matched_segment_count", migration)
        self.assertIn("maintain_broadcast_final_segment_count", migration)
        context_query = repository.split("def broadcast_official_context", 1)[1].split(
            "def refresh_official_context_stats", 1
        )[0]
        self.assertIn("broadcast.final_segment_count", context_query)
        self.assertIn("broadcast.matched_segment_count", context_query)
        self.assertNotIn("SELECT COUNT(", context_query)
        self.assertIn("def refresh_official_context_stats", repository)

    def test_ended_broadcast_reviews_keep_revision_evidence(self):
        sql = (MIGRATION.parent / "0008_broadcast_reviews.sql").read_text(encoding="utf-8")
        for table in ("broadcast_reviews", "broadcast_review_topics", "broadcast_review_evidence"):
            self.assertIn(f"CREATE TABLE {table}", sql)
        self.assertIn("representative_revision_id", sql)
        self.assertIn("review_lease_expires_at", sql)

    def test_official_observation_defaults_to_official_source_system(self):
        field = LiveBroadcastObservation.__dataclass_fields__["source_system"]
        self.assertEqual(field.default, "assembly.webcast.go.kr")

    def test_three_target_committees_and_plenary_can_be_captured_concurrently(self):
        project = Path(__file__).parents[2]
        worker = (
            project / "backend/app/ingestion/caption_worker.py"
        ).read_text(encoding="utf-8")
        repository = (
            project / "backend/app/db/live_repository.py"
        ).read_text(encoding="utf-8")
        compose = (project / "docker-compose.yml").read_text(encoding="utf-8")
        deploy_script = (project / "scripts/deploy_live_capture_workers.sh").read_text(encoding="utf-8")
        self.assertIn("ThreadPoolExecutor(max_workers=args.workers", worker)
        self.assertIn("MAX_CAPTION_WORKERS = 4", worker)
        self.assertIn("if not 1 <= args.workers <= MAX_CAPTION_WORKERS", worker)
        self.assertIn("FOR UPDATE SKIP LOCKED LIMIT 1", repository)
        self.assertIn('"--workers", "4"', compose)
        self.assertIn('app.ingestion.caption_worker --workers 4', deploy_script)
        self.assertIn("poc07-national-assembly-executive-caption-worker", deploy_script)
        self.assertIn('app.ingestion.executive_caption_worker --interval 5', deploy_script)

    def test_live_broadcast_initializes_and_fails_over_transcript_source(self):
        project = Path(__file__).parents[2]
        repository = (project / "backend/app/db/live_repository.py").read_text(encoding="utf-8")
        worker = (project / "backend/app/ingestion/caption_worker.py").read_text(encoding="utf-8")
        self.assertIn("active_transcript_source,", repository)
        self.assertIn('"OFFICIAL_CAPTION"\n                    if observation.caption_websocket_url', repository)
        self.assertIn("WHEN live_broadcasts.active_transcript_source = 'NONE'", repository)
        self.assertIn("A connection-level failure never reaches recv()", worker)
        self.assertGreaterEqual(worker.count("mark_official_caption_timeout("), 2)
        self.assertIn('"detail": str(exc)[:240]', worker)
        self.assertIn('item["live_revision_id"] = str(revision_id)', repository)
        self.assertIn('"live_text"', repository)

    def test_completed_briefs_are_not_reprocessed_until_caption_cursor_changes(self):
        worker = (
            Path(__file__).parents[1] / "app" / "ingestion" / "meeting_brief_worker.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "current_brief.source_last_event_cursor =\n                        broadcast.source_last_event_cursor",
            worker,
        )
        self.assertNotIn("MAX(revision.event_cursor)", worker)
        self.assertIn("current_brief.prompt_version = %s", worker)
        self.assertIn("current_brief.brief ? 'live_topic_assignment'", worker)
        self.assertIn("ORDER BY ended_at DESC NULLS LAST", worker)


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
        self.assertIn("broadcast.committee_name = ANY(%s)", repository)
        self.assertIn("official_integration_updated_at", repository)
        self.assertIn("ORDER BY broadcast.detected_at DESC", repository)
        self.assertIn("LIMIT %s OFFSET %s", repository)
        self.assertIn("offset: int = 0", app_source)
        self.assertIn('"next_offset": offset + len(items)', app_source)
        self.assertIn('"has_more": has_more', app_source)
        self.assertIn("def ended_transcript_snapshot", repository)
        self.assertIn("broadcast.thumbnail_url", repository)
        self.assertIn("def broadcast_official_context", repository)
        self.assertIn("matched_segment_count", repository)
        self.assertIn('"official_context": official_context', app_source)
        self.assertIn("broadcast.institution,", repository)
        self.assertIn("broadcast.caption_source_status", repository)
        self.assertNotIn(
            "WHERE broadcast.institution = 'LEGISLATURE'\n              AND broadcast.lifecycle_status = 'ENDED'", repository,
        )
        self.assertIn("capture_status = 'POST_PROCESSING'", repository)
        self.assertIn("WHEN lifecycle_status = 'ENDED' AND %s THEN 'POST_PROCESSING'", repository)
        worker = (
            Path(__file__).parents[1] / "app" / "ingestion" / "executive_caption_worker.py"
        ).read_text(encoding="utf-8")
        self.assertIn('claim.get("lifecycle_status") == "ENDED"', worker)
        self.assertIn('"terminal_failure": terminal_failure', worker)

        self.assertIn('@app.get("/api/live/tasks"', app_source)
        self.assertIn("def list_open_follow_up_tasks", repository)
        self.assertIn("def broadcast_reconciliation_details", repository)
        self.assertIn("official_reconciliation", app_source)
        self.assertRegex(repository, r'"revision_id",\s+"broadcast_id"')
if __name__ == "__main__":
    unittest.main()
