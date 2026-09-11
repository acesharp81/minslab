from __future__ import annotations

import unittest
from pathlib import Path


class OpenRouterUsageSchemaTests(unittest.TestCase):
    def test_daily_usage_table_and_atomic_limit_contract_exist(self):
        backend = Path(__file__).parents[1]
        migration = (backend / "migrations" / "0020_llm_provider_daily_usage.sql").read_text()
        repository = (backend / "app" / "db" / "summary_repository.py").read_text()
        cache = (backend / "app" / "services" / "summary_cache.py").read_text()
        self.assertIn("CREATE TABLE llm_provider_daily_usage", migration)
        self.assertIn("ON CONFLICT (provider, usage_date) DO UPDATE", repository)
        self.assertIn("request_count < %s", repository)
        self.assertIn("HARD_DAILY_REQUEST_LIMIT = 950", cache)


if __name__ == "__main__":
    unittest.main()
