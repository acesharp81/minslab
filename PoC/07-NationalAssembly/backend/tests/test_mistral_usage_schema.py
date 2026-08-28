from __future__ import annotations

import unittest
from pathlib import Path


class MistralUsageSchemaTests(unittest.TestCase):
    def test_monthly_token_usage_schema_and_atomic_accumulation_exist(self):
        backend = Path(__file__).parents[1]
        migration = (
            backend / "migrations"
            / "0023_llm_provider_monthly_token_usage.sql"
        ).read_text()
        event_migration = (
            backend / "migrations"
            / "0024_llm_token_usage_events_backfill.sql"
        ).read_text()
        repository = (
            backend / "app" / "db" / "summary_repository.py"
        ).read_text()
        self.assertIn(
            "CREATE TABLE llm_provider_monthly_token_usage", migration,
        )
        self.assertIn(
            "PRIMARY KEY (provider, model, usage_month)", migration,
        )
        self.assertIn(
            "ON CONFLICT (provider, model, usage_month) DO UPDATE", repository,
        )
        self.assertIn("EXCLUDED.total_tokens", repository)
        self.assertIn(
            "CREATE TABLE llm_provider_token_usage_events", event_migration,
        )
        self.assertIn(
            "PRIMARY KEY (provider, request_id)", event_migration,
        )
        self.assertIn(
            "ON CONFLICT (provider, request_id) DO NOTHING", repository,
        )
        api = (backend / "app" / "main.py").read_text()
        self.assertIn('@app.get("/api/ai/usage"', api)
        self.assertIn("repository.monthly_token_usage(provider, model)", api)
        self.assertIn('"mistral": "Mistral Studio"', api)
        self.assertIn('"resets_at": _usage_reset_at', api)


if __name__ == "__main__":
    unittest.main()
