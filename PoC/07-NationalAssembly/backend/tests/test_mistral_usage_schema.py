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
        self.assertIn("repository.monthly_model_usage()", api)
        self.assertIn("def _model_usage_payload(", api)
        self.assertIn('"official_limit": openrouter_official_limit', api)
        self.assertIn('"operational_limit": openrouter_limit', api)
        self.assertIn('"provider": "mistral", "period": "MONTHLY"', api)
        self.assertIn('"resets_at": _usage_reset_at', api)
        self.assertIn('"MONTHLY", settings.national_assembly_timezone', api)
        self.assertIn('"usage_percent": round(', api)
        self.assertIn('"topic_report": "주제별 보고서 생성"', api)
        self.assertIn(
            '"meeting_brief_lineage": "LIVE 주제 ↔ 최종 보고서 연관관계 분석"',
            api,
        )
        self.assertIn(
            '"official_revision": "공식 보고서 ↔ LIVE 초안 변화 분석"',
            api,
        )

if __name__ == "__main__":
    unittest.main()
