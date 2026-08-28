from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.services.mistral_summary import MistralSummaryClient
from app.services.openrouter_summary import OpenRouterSummaryClient
from app.services.summary_client import (
    build_summary_client,
    summary_daily_limit,
    summary_identity,
    summary_mistral_prices,
    summary_monthly_credit_usd,
)


class SummaryClientFactoryTests(unittest.TestCase):
    def settings(self, provider: str):
        return SimpleNamespace(
            llm_provider=provider,
            llm_model="",
            mistral_api_key="mistral-secret",
            mistral_base_url="https://api.mistral.ai/v1",
            mistral_monthly_credit_usd=10.0,
            mistral_input_usd_per_million=0.15,
            mistral_output_usd_per_million=0.60,
            openrouter_api_key="openrouter-secret",
            openrouter_base_url="https://openrouter.ai/api/v1",
            openrouter_daily_limit=500,
        )

    def test_builds_mistral_without_changing_business_cache_contract(self):
        settings = self.settings("mistral")
        client = build_summary_client(settings)
        self.assertIsInstance(client, MistralSummaryClient)
        self.assertEqual(
            summary_identity(settings),
            ("mistral", "mistral-small-2603", client.prompt_version),
        )
        self.assertEqual(summary_daily_limit(settings), 0)
        self.assertEqual(summary_monthly_credit_usd(settings), 10.0)
        self.assertEqual(summary_mistral_prices(settings), (0.15, 0.60))

    def test_openrouter_remains_available_as_fallback(self):
        settings = self.settings("openrouter")
        self.assertIsInstance(build_summary_client(settings), OpenRouterSummaryClient)
        self.assertEqual(summary_daily_limit(settings), 500)
        self.assertEqual(summary_monthly_credit_usd(settings), 0.0)


if __name__ == "__main__":
    unittest.main()
