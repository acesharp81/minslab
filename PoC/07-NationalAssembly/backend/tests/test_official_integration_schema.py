from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.ingestion.official_integration_worker import (
    cached_ready_status,
    normalized_cached_edits,
    temporary_document_stable,
)

PROJECT_DIR = Path(__file__).resolve().parents[2]


class OfficialIntegrationSchemaTests(unittest.TestCase):
    def test_llm_workers_do_not_receive_root_env_wholesale(self):
        compose = (PROJECT_DIR / "docker-compose.yml").read_text(encoding="utf-8")
        deploy_script = (
            PROJECT_DIR / "scripts" / "deploy_secure_workers.sh"
        ).read_text(encoding="utf-8")
        self.assertNotIn("../../.env", compose)
        self.assertEqual(compose.count("MISTRAL_API_KEY: ${MISTRAL_API_KEY:-}"), 2)
        self.assertIn("MEETING_BRIEF_PROVIDER: ${MEETING_BRIEF_PROVIDER:-openrouter}", compose)
        self.assertIn("external: true", compose)
        self.assertIn("mktemp -d /tmp/poc07-worker-env.", deploy_script)
        self.assertIn("--env-file", deploy_script)
        self.assertNotIn("-e MISTRAL_API_KEY=", deploy_script)

    def test_integration_cache_preserves_both_source_versions(self):
        sql = (
            PROJECT_DIR / "backend" / "migrations"
            / "0027_meeting_official_integrations.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE meeting_official_integrations", sql)
        self.assertIn("meeting_brief_id uuid", sql)
        self.assertIn("official_document_id uuid", sql)
        self.assertIn("integrated_brief jsonb", sql)
        self.assertIn("changes jsonb", sql)
        self.assertIn(
            "UNIQUE (meeting_brief_id, official_document_id, integration_version)", sql,
        )
        repository = (
            PROJECT_DIR / "backend" / "app" / "db"
            / "official_integration_repository.py"
        ).read_text(encoding="utf-8")
        worker = (
            PROJECT_DIR / "backend" / "app" / "ingestion"
            / "official_integration_worker.py"
        ).read_text(encoding="utf-8")
        self.assertIn("official_utterance_id_map", repository)
        self.assertIn("official_semantic_hash", worker)
        self.assertIn("TEMPORARY_UPDATE_DEFERRED", worker)
        self.assertIn('result.get("status") in {', worker)
        self.assertIn('"DEFERRED", "SKIPPED_LLM_REQUIRED"', worker)
        self.assertIn("TEMPORARY_STABILITY_WINDOW", worker)
        self.assertIn('"api_requests": 0', worker)

    def test_temporary_minutes_wait_for_stable_window(self):
        now = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
        assert not temporary_document_stable({
            "publication_stage": "TEMPORARY",
            "retrieved_at": now - timedelta(minutes=29),
        }, now=now)
        assert temporary_document_stable({
            "publication_stage": "TEMPORARY",
            "retrieved_at": now - timedelta(minutes=30),
        }, now=now)
        assert temporary_document_stable({
            "publication_stage": "FINAL",
            "retrieved_at": now,
        }, now=now)

    def test_deferred_cache_retries_until_temporary_minutes_are_stable(self):
        deferred = {
            "status": "READY",
            "usage_metadata": {"reuse_reason": "TEMPORARY_UPDATE_DEFERRED"},
        }
        self.assertEqual(
            "DEFERRED",
            cached_ready_status(
                deferred, temporary_stable=False, force=False,
            ),
        )
        self.assertIsNone(cached_ready_status(
            deferred, temporary_stable=True, force=False,
        ))
        self.assertEqual(
            "CACHED",
            cached_ready_status(
                {"status": "READY", "usage_metadata": {}},
                temporary_stable=False, force=False,
            ),
        )

    def test_cached_changes_can_be_reapplied_without_new_llm_call(self):
        restored = normalized_cached_edits([
            {
                "entity_type": "topic", "entity_id": "topic-1",
                "operation": "UPDATE", "field": "summary",
                "new_text": "", "before": "잠정 문구", "after": "공식 문구",
            },
            {
                "entity_type": "task", "entity_id": "task-1",
                "operation": "UPDATE", "field": "ministries",
                "new_values": [], "after": ["법무부", "경찰청"],
            },
        ])
        self.assertEqual(restored[0]["new_text"], "공식 문구")
        self.assertEqual(restored[1]["new_values"], ["법무부", "경찰청"])
        worker = (
            PROJECT_DIR / "backend/app/ingestion/official_integration_worker.py"
        ).read_text(encoding="utf-8")
        self.assertIn("DETERMINISTIC_COMPARISON_UPGRADE", worker)
        self.assertIn("--deterministic-only", worker)
        self.assertIn("SKIPPED_LLM_REQUIRED", worker)

    def test_pending_first_queue_prevents_completed_meeting_starvation(self):
        migration = (
            PROJECT_DIR / "backend/migrations/0041_official_integration_jobs.sql"
        ).read_text(encoding="utf-8")
        repository = (
            PROJECT_DIR / "backend/app/db/official_integration_job_repository.py"
        ).read_text(encoding="utf-8")
        worker = (
            PROJECT_DIR / "backend/app/ingestion/official_integration_worker.py"
        ).read_text(encoding="utf-8")
        compose = (PROJECT_DIR / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE meeting_official_integration_jobs", migration)
        self.assertIn("FOR UPDATE SKIP LOCKED", repository)
        self.assertIn("integration.status = 'READY'", repository)
        self.assertIn("TEMPORARY_UPDATE_DEFERRED", repository)
        self.assertIn(
            "WHERE meeting_official_integration_jobs.status = 'READY'",
            repository,
        )
        self.assertIn("candidate.status = 'RETRY_WAIT'", repository)
        self.assertIn("OfficialIntegrationJobRepository(connection).claim", worker)
        self.assertIn("--interval", worker)
        self.assertIn("official-integration-worker:", compose)

    def test_body_collected_before_publication_is_attached_idempotently(self):
        repository = (
            PROJECT_DIR / "backend/app/db/official_publication_repository.py"
        ).read_text(encoding="utf-8")
        worker = (
            PROJECT_DIR / "backend/app/ingestion/official_minutes_worker.py"
        ).read_text(encoding="utf-8")
        migration = (
            PROJECT_DIR / "backend/migrations/0041_official_integration_jobs.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("def attach_preserved_documents", repository)
        self.assertIn(
            "publication_id = COALESCE(\n"
            "                              official_transcript_documents.publication_id",
            repository,
        )
        self.assertIn("WHERE document.publication_id IS NULL", migration)
        self.assertIn("publication.conference_id = document.conference_id", migration)
        self.assertIn("official.preserved-bodies.attached", worker)

    def test_body_collection_prioritizes_unlinked_publications(self):
        repository = (
            PROJECT_DIR / "backend/app/db/official_publication_repository.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "ORDER BY (publication.body_contract_status = 'LINK_ONLY') DESC",
            repository,
        )
        self.assertIn(
            "publication.conference_id = external.external_id",
            repository,
        )

    def test_official_collection_errors_are_isolated_per_item(self):
        worker = (
            PROJECT_DIR / "backend/app/ingestion/official_minutes_worker.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"official.date.error"', worker)
        self.assertIn('"official.body.error"', worker)
        self.assertIn('"official.meeting-body.error"', worker)

    def test_official_worker_fills_missing_bill_details_in_bounded_batches(self):
        worker = (
            PROJECT_DIR / "backend/app/ingestion/official_minutes_worker.py"
        ).read_text(encoding="utf-8")
        sync = (
            PROJECT_DIR / "backend/app/ingestion/bill_sync.py"
        ).read_text(encoding="utf-8")
        repository = (
            PROJECT_DIR / "backend/app/db/bill_repository.py"
        ).read_text(encoding="utf-8")
        self.assertIn("sync_pending_target_bill_details(", worker)
        self.assertIn('"bills.details.completed"', worker)
        self.assertIn("limit=20", worker)
        self.assertIn("def pending_target_bill_external_ids(", repository)
        self.assertIn("WHERE NOT EXISTS (", repository)
        self.assertIn("ORDER BY max(meeting.scheduled_date) DESC", repository)
        self.assertIn("MISSING_DETAIL_RETRY_SECONDS", sync)
        self.assertIn("FAILED_DETAIL_RETRY_SECONDS", sync)
        self.assertIn('"missing_details": []', sync)
        self.assertIn('"errors": []', sync)

    def test_ui_exposes_real_comparison_stages(self):
        repository = (
            PROJECT_DIR / "backend/app/db/live_repository.py"
        ).read_text(encoding="utf-8")
        script = (PROJECT_DIR / "web/official-integration.js").read_text(
            encoding="utf-8"
        )
        for status in (
            "OFFICIAL_BODY_PENDING", "COMPARISON_QUEUED",
            "COMPARISON_PROCESSING", "COMPARISON_RETRY_WAIT",
        ):
            self.assertIn(status, repository)
            self.assertIn(status, script)
        api = (PROJECT_DIR / "backend/app/main.py").read_text(encoding="utf-8")
        self.assertIn('official_context or {}).get("official_document_id")', api)

    def test_change_report_transient_failures_have_bounded_retry(self):
        migration = (
            PROJECT_DIR / "backend/migrations/0042_official_change_report_retries.sql"
        ).read_text(encoding="utf-8")
        repository = (
            PROJECT_DIR / "backend/app/db/official_change_report_repository.py"
        ).read_text(encoding="utf-8")
        self.assertIn("attempt_count integer", migration)
        self.assertIn("next_attempt_at timestamptz", migration)
        self.assertIn("candidate.attempt_count < 3", repository)
        self.assertIn("LEAST(300", repository)


if __name__ == "__main__":
    unittest.main()
