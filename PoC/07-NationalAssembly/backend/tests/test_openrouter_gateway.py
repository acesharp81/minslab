from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app import openrouter_gateway as gateway


class OpenRouterGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.old_path = gateway.DB_PATH
        self.old_key = gateway.API_KEY
        gateway.DB_PATH = Path(self.temporary.name) / "gateway.sqlite3"
        gateway._schema_ready_path = None
        gateway.API_KEY = "test-key"
        self.client = TestClient(gateway.app)

    def tearDown(self) -> None:
        gateway.DB_PATH = self.old_path
        gateway._schema_ready_path = None
        gateway.API_KEY = self.old_key
        self.temporary.cleanup()

    @staticmethod
    def response(status: int, payload: dict) -> Mock:
        result = Mock()
        result.status_code = status
        result.content = __import__("json").dumps(payload).encode()
        result.headers = {"Content-Type": "application/json"}
        result.json.return_value = payload
        return result

    def headers(self, key: str) -> dict[str, str]:
        return {
            "X-Minslab-Project": "poc7",
            "X-Minslab-Workload": "test",
            "X-Minslab-Priority": "40",
            "X-Minslab-Data-Class": "public_official",
            "X-Idempotency-Key": key,
        }

    @patch("app.openrouter_gateway.requests.post")
    def test_success_is_replayed_without_second_upstream_attempt(self, post: Mock) -> None:
        post.return_value = self.response(200, {"id": "one", "choices": []})
        body = {"model": "openai/gpt-oss-20b:free", "messages": []}
        first = self.client.post("/api/v1/chat/completions", json=body, headers=self.headers("same"))
        second = self.client.post("/api/v1/chat/completions", json=body, headers=self.headers("same"))
        self.assertEqual(200, first.status_code)
        self.assertEqual("1", second.headers["X-Minslab-Idempotent-Replay"])
        self.assertEqual(1, post.call_count)
        self.assertEqual(1, self.client.get("/internal/status").json()["reserved"])
        upstream_body = post.call_args.kwargs["json"]
        self.assertEqual(list(gateway.FREE_MODELS), upstream_body["models"])
        self.assertEqual({
            "data_collection": "allow",
            "allow_fallbacks": True,
            "require_parameters": True,
        }, upstream_body["provider"])

    @patch("app.openrouter_gateway.requests.post")
    def test_failed_attempt_counts_and_same_logical_request_can_retry(self, post: Mock) -> None:
        post.side_effect = [
            self.response(429, {"error": {"message": "upstream limited"}}),
            self.response(200, {"id": "two", "choices": []}),
        ]
        body = {"model": "openai/gpt-oss-20b:free", "messages": []}
        first = self.client.post("/api/v1/chat/completions", json=body, headers=self.headers("retry"))
        second = self.client.post("/api/v1/chat/completions", json=body, headers=self.headers("retry"))
        status = self.client.get("/internal/status").json()
        self.assertEqual(429, first.status_code)
        self.assertEqual(200, second.status_code)
        self.assertEqual(2, status["reserved"])
        self.assertEqual(1, status["failed"])
        self.assertEqual(1, status["completed"])

    @patch("app.openrouter_gateway.requests.post")
    def test_stale_inflight_idempotency_lock_is_reclaimed(self, post: Mock) -> None:
        with gateway._connect() as connection:
            connection.execute(
                "INSERT INTO gateway_requests(id,idempotency_key,usage_date,project,"
                "workload,priority,model,status,started_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    "stale", "stale-key", "2000-01-01", "poc7", "test", 40,
                    "old/free:free", "INFLIGHT", "2000-01-01T00:00:00+00:00",
                ),
            )
        post.return_value = self.response(200, {"id": "fresh", "choices": []})
        response = self.client.post(
            "/api/v1/chat/completions",
            json={"model": "openai/gpt-oss-20b:free", "messages": []},
            headers=self.headers("stale-key"),
        )
        self.assertEqual(200, response.status_code)
        with gateway._connect() as connection:
            old = connection.execute(
                "SELECT status,error FROM gateway_requests WHERE id='stale'",
            ).fetchone()
        self.assertEqual(("FAILED", "stale_inflight_reclaimed"), tuple(old))

    @patch("app.openrouter_gateway.requests.post")
    def test_malformed_structured_output_is_not_replayed(self, post: Mock) -> None:
        post.side_effect = [
            self.response(200, {
                "id": "truncated",
                "choices": [{"message": {"content": '{"topics": ['}}],
            }),
            self.response(200, {
                "id": "valid",
                "choices": [{"message": {"content": '{"topics": []}'}}],
            }),
        ]
        body = {
            "model": "nvidia/nemotron-3-super-120b-a12b:free",
            "messages": [],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "meeting_chunk_analysis", "schema": {}},
            },
        }
        first = self.client.post(
            "/api/v1/chat/completions", json=body,
            headers=self.headers("structured-retry"),
        )
        second = self.client.post(
            "/api/v1/chat/completions", json=body,
            headers=self.headers("structured-retry"),
        )
        status = self.client.get("/internal/status").json()
        self.assertEqual(200, first.status_code)
        self.assertEqual(200, second.status_code)
        self.assertNotIn("X-Minslab-Idempotent-Replay", second.headers)
        self.assertEqual(2, post.call_count)
        self.assertEqual(1, status["failed"])
        self.assertEqual(1, status["completed"])

    @patch("app.openrouter_gateway.requests.post")
    def test_valid_structured_output_is_replayed(self, post: Mock) -> None:
        post.return_value = self.response(200, {
            "id": "valid",
            "choices": [{
                "message": {"content": "```json\n{\"topics\": []}\n```"},
            }],
        })
        body = {
            "model": "nvidia/nemotron-3-super-120b-a12b:free",
            "messages": [],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "meeting_chunk_analysis", "schema": {}},
            },
        }
        first = self.client.post(
            "/api/v1/chat/completions", json=body,
            headers=self.headers("structured-success"),
        )
        second = self.client.post(
            "/api/v1/chat/completions", json=body,
            headers=self.headers("structured-success"),
        )
        self.assertEqual(200, first.status_code)
        self.assertEqual("1", second.headers["X-Minslab-Idempotent-Replay"])
        self.assertEqual(1, post.call_count)

    def test_priority_shedding_preserves_essential_requests(self) -> None:
        self.assertEqual("booster_and_backfill_paused", gateway._admission_error(700, 50))
        self.assertEqual("", gateway._admission_error(700, 40))
        self.assertEqual("essential_workloads_only", gateway._admission_error(850, 40))
        self.assertEqual("", gateway._admission_error(850, 30))
        self.assertEqual("global_daily_operational_limit", gateway._admission_error(950, 10))

    @patch("app.openrouter_gateway.requests.post")
    def test_http_200_error_envelope_is_counted_as_failure(self, post: Mock) -> None:
        post.return_value = self.response(200, {"error": {"message": "provider overloaded"}})
        response = self.client.post(
            "/api/v1/chat/completions",
            json={"model": "retired/free:free", "messages": []},
            headers=self.headers("error-envelope"),
        )
        self.assertEqual(502, response.status_code)
        status = self.client.get("/internal/status").json()
        self.assertEqual(1, status["failed"])
        self.assertEqual(0, status["completed"])


if __name__ == "__main__":
    unittest.main()
