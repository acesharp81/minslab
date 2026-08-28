from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

import requests

from app.services.summary_cache import cache_missing_summaries


class OpenRouterRetryQuotaTests(unittest.TestCase):
    @mock.patch("app.services.summary_cache.time.sleep")
    def test_each_retry_reserves_a_daily_request(self, sleep):
        utterance = {
            "content_hash": "c" * 64, "text": "긴 발언 " * 50,
            "source_speaker_label": "1", "segment_count": 3,
        }
        repository = mock.Mock()
        repository.existing_hashes.return_value = set()
        repository.deferred_hashes.return_value = set()
        repository.reserve_daily_request.side_effect = [1, 2]
        repository.save_many.return_value = 0
        repository.daily_usage.side_effect = [0, 2]
        response = mock.Mock(status_code=429)
        error = requests.HTTPError(response=response)
        client = mock.Mock(
            provider="openrouter", model="openrouter/free",
            prompt_version="assembly-conversation-summary/2.0",
        )
        client.summarize.side_effect = [
            error, SimpleNamespace(items=[], usage_metadata={}),
        ]
        connection = mock.Mock()
        with mock.patch(
            "app.services.summary_cache.SummaryRepository", return_value=repository,
        ):
            stats = cache_missing_summaries(
                connection, "broadcast-id", [utterance], client,
            )
        self.assertEqual(repository.reserve_daily_request.call_count, 2)
        self.assertEqual(connection.commit.call_count, 3)
        self.assertEqual(stats["api_requests"], 2)
        sleep.assert_called_once_with(10)


if __name__ == "__main__":
    unittest.main()
