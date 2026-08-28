from __future__ import annotations

import unittest
from unittest import mock

from app.db.summary_repository import SummaryRepository
from app.services.summary_cache import (
    DailyRequestLimitReached,
    HARD_DAILY_REQUEST_LIMIT,
    cache_missing_summaries,
)


class OpenRouterDailyLimitTests(unittest.TestCase):
    def test_repository_rejects_daily_quota_for_mistral(self):
        connection = mock.Mock()
        with self.assertRaisesRegex(ValueError, "OpenRouter only"):
            SummaryRepository(connection).reserve_daily_request(
                "mistral", 500,
            )
        connection.execute.assert_not_called()

    def test_hard_limit_blocks_request_before_external_call(self):
        utterance = {
            "content_hash": "b" * 64, "text": "긴 발언 " * 50,
            "source_speaker_label": "1", "segment_count": 3,
        }
        repository = mock.Mock()
        repository.existing_hashes.return_value = set()
        repository.deferred_hashes.return_value = set()
        repository.daily_usage.return_value = 0
        repository.reserve_daily_request.return_value = None
        client = mock.Mock(
            provider="openrouter", model="google/gemma-4-26b-a4b-it:free",
            prompt_version="assembly-conversation-summary/2.0",
        )
        with mock.patch(
            "app.services.summary_cache.SummaryRepository", return_value=repository,
        ):
            with self.assertRaises(DailyRequestLimitReached):
                cache_missing_summaries(
                    mock.Mock(), "broadcast-id", [utterance], client,
                    daily_limit=9999,
                )
        repository.reserve_daily_request.assert_called_once_with(
            "openrouter", HARD_DAILY_REQUEST_LIMIT
        )
        client.summarize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
