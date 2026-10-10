from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock
from uuid import UUID

import requests

from app.ingestion import meeting_brief_worker as worker
from app.services.meeting_brief import NvidiaMeetingBriefClient


def settings() -> SimpleNamespace:
    return SimpleNamespace(
        meeting_brief_provider="auto",
        meeting_brief_nvidia_enabled=True,
        nvidia_api_key="test-key",
        openai_api_key="test-key",
        openrouter_gateway_status_url="https://gateway.invalid/internal/status",
        openrouter_daily_limit=950,
    )


class MeetingBriefProviderPoolTests(unittest.TestCase):
    def test_nim_is_first_then_openrouter_then_openai(self) -> None:
        config = settings()
        with mock.patch.object(worker.time, "monotonic", return_value=1000):
            with mock.patch.object(worker, "_nvidia_retry_after", 0):
                with mock.patch.object(
                    worker, "openrouter_brief_has_capacity", return_value=True,
                ):
                    self.assertEqual(worker.automatic_brief_provider(config), "nvidia")
                config.meeting_brief_nvidia_enabled = False
                with mock.patch.object(
                    worker, "openrouter_brief_has_capacity", return_value=True,
                ):
                    self.assertEqual(worker.automatic_brief_provider(config), "openrouter")
                with mock.patch.object(
                    worker, "openrouter_brief_has_capacity", return_value=False,
                ):
                    self.assertEqual(worker.automatic_brief_provider(config), "openai")

    def test_openai_requires_exhausted_openrouter_quota(self) -> None:
        config = settings()
        with mock.patch.object(
            worker, "openrouter_brief_has_capacity", return_value=True,
        ):
            self.assertEqual(
                worker.next_brief_provider(config, "nvidia", RuntimeError("nim")),
                "openrouter",
            )
            self.assertIsNone(
                worker.next_brief_provider(config, "openrouter", RuntimeError("transient")),
            )
        with mock.patch.object(
            worker, "openrouter_brief_has_capacity", return_value=False,
        ):
            self.assertEqual(
                worker.next_brief_provider(config, "nvidia", RuntimeError("nim")),
                "openai",
            )
            self.assertEqual(
                worker.next_brief_provider(config, "openrouter", RuntimeError("limit")),
                "openai",
            )

    def test_failed_nim_report_is_resumed_on_openrouter(self) -> None:
        broadcast_id = UUID("00000000-0000-0000-0000-000000000001")
        config = settings()
        with (
            mock.patch.object(worker, "eligible_broadcast_ids", return_value=[broadcast_id]),
            mock.patch.object(worker, "get_settings", return_value=config),
            mock.patch.object(worker, "meeting_brief_identity", return_value=("nvidia", "nim", "v1")),
            mock.patch.object(worker, "openrouter_brief_has_capacity", return_value=True),
            mock.patch.object(
                worker, "generate_one",
                side_effect=[RuntimeError("nim unavailable"), {"status": "GENERATED"}],
            ) as generate,
        ):
            result = worker.process_available()
        self.assertEqual(result[0]["status"], "GENERATED")
        self.assertEqual(result[0]["fallback_from"], ["nvidia"])
        self.assertEqual(
            [call.kwargs["provider_override"] for call in generate.call_args_list],
            ["nvidia", "openrouter"],
        )

    def test_exhausted_openrouter_skips_to_openai(self) -> None:
        broadcast_id = UUID("00000000-0000-0000-0000-000000000001")
        config = settings()
        with (
            mock.patch.object(worker, "eligible_broadcast_ids", return_value=[broadcast_id]),
            mock.patch.object(worker, "get_settings", return_value=config),
            mock.patch.object(worker, "meeting_brief_identity", return_value=("nvidia", "nim", "v1")),
            mock.patch.object(worker, "openrouter_brief_has_capacity", return_value=False),
            mock.patch.object(
                worker, "generate_one",
                side_effect=[RuntimeError("nim unavailable"), {"status": "GENERATED"}],
            ) as generate,
        ):
            result = worker.process_available()
        self.assertEqual(result[0]["fallback_from"], ["nvidia"])
        self.assertEqual(
            [call.kwargs["provider_override"] for call in generate.call_args_list],
            ["nvidia", "openai"],
        )

    def test_nim_posts_strict_json_schema_without_router_fields(self) -> None:
        client = NvidiaMeetingBriefClient(
            "test-key", model="nvidia/nemotron-3-ultra-550b-a55b",
            base_url="https://integrate.api.nvidia.com/v1",
            min_interval_seconds=0,
        )
        response = mock.Mock(status_code=200)
        response.json.return_value = {
            "id": "probe-1",
            "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2},
        }
        with mock.patch("app.services.meeting_brief.requests.post", return_value=response) as post:
            result, metadata = client._post(
                "test", {"type": "object", "properties": {"ok": {"type": "boolean"}},
                         "required": ["ok"], "additionalProperties": False},
                "probe",
            )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(metadata["request_id"], "probe-1")
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertNotIn("provider", body)


if __name__ == "__main__":
    unittest.main()
