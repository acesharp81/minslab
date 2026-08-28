from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from app.db.summary_repository import token_usage_from_metadata
from app.services.summary_cache import (
    MonthlyTokenLimitReached,
    cache_missing_summaries,
)


class MistralMonthlyTokenLimitTests(unittest.TestCase):
    def utterance(self):
        return {
            "content_hash": "d" * 64,
            "text": "긴 발언 " * 50,
            "source_speaker_label": "1",
            "segment_count": 3,
        }

    def client(self):
        return mock.Mock(
            provider="mistral",
            model="mistral-small-2603",
            prompt_version="assembly-conversation-summary/2.0",
        )

    def test_mistral_records_tokens_without_reserving_daily_request(self):
        utterance = self.utterance()
        repository = mock.Mock()
        repository.existing_hashes.return_value = set()
        repository.deferred_hashes.return_value = set()
        repository.monthly_token_usage.side_effect = [
            {"request_count": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            {"request_count": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            {"request_count": 1, "input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
        ]
        repository.save_many.return_value = 1
        client = self.client()
        client.summarize.return_value = SimpleNamespace(
            items=[{
                "content_hash": utterance["content_hash"],
                "summary": "핵심 요약",
            }],
            usage_metadata={
                "request_id": "req-summary-1",
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 30,
                    "total_tokens": 150,
                },
            },
        )
        connection = mock.Mock()
        with mock.patch(
            "app.services.summary_cache.SummaryRepository",
            return_value=repository,
        ):
            stats = cache_missing_summaries(
                connection, "broadcast-id", [utterance], client,
                monthly_credit_usd=10.0,
            )
        repository.reserve_daily_request.assert_not_called()
        repository.record_monthly_token_usage.assert_called_once_with(
            "mistral", "mistral-small-2603",
            client.summarize.return_value.usage_metadata,
        )
        self.assertEqual(150, stats["monthly_tokens"])
        self.assertEqual(1, stats["api_requests"])
        self.assertAlmostEqual(0.000036, stats["monthly_cost_usd"])

    def test_monthly_credit_blocks_before_external_call(self):
        utterance = self.utterance()
        repository = mock.Mock()
        repository.existing_hashes.return_value = set()
        repository.deferred_hashes.return_value = set()
        repository.monthly_token_usage.return_value = {
            "request_count": 10, "input_tokens": 4_000_000,
            "output_tokens": 1_000_000, "total_tokens": 5_000_000,
        }
        client = self.client()
        with mock.patch(
            "app.services.summary_cache.SummaryRepository",
            return_value=repository,
        ):
            with self.assertRaises(MonthlyTokenLimitReached):
                cache_missing_summaries(
                    mock.Mock(), "broadcast-id", [utterance], client,
                    monthly_credit_usd=1.0,
                )
        client.summarize.assert_not_called()
        repository.reserve_daily_request.assert_not_called()

    def test_extracts_mistral_input_and_output_usage(self):
        self.assertEqual(
            {
                "input_tokens": 12,
                "output_tokens": 3,
                "total_tokens": 15,
            },
            token_usage_from_metadata({"usage": {
                "prompt_tokens": 12,
                "completion_tokens": 3,
                "total_tokens": 15,
            }}),
        )


if __name__ == "__main__":
    unittest.main()
