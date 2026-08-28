from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.ingestion.official_integration_worker import temporary_document_stable


PROJECT_DIR = Path(__file__).resolve().parents[2]


class OfficialIntegrationSchemaTests(unittest.TestCase):
    def test_llm_workers_do_not_receive_root_env_wholesale(self):
        compose = (PROJECT_DIR / "docker-compose.yml").read_text(encoding="utf-8")
        deploy_script = (
            PROJECT_DIR / "scripts" / "deploy_secure_workers.sh"
        ).read_text(encoding="utf-8")
        self.assertNotIn("../../.env", compose)
        self.assertEqual(compose.count("MISTRAL_API_KEY: ${MISTRAL_API_KEY:-}"), 4)
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


if __name__ == "__main__":
    unittest.main()
