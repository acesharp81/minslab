from __future__ import annotations

import time
import unittest
from unittest import mock

import service


class HarnessServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        service._LIVE_AUTH_TOKENS.clear()
        service._LIVE_AUTH_FAILURES.clear()
        service._LIVE_HISTORY.clear()

    def test_config_includes_workflow_and_registry(self) -> None:
        config = service.dispatch("/config", "GET")
        self.assertIn("workflow", config)
        self.assertIn("model_registry", config)
        self.assertGreaterEqual(len(config["workflow"]["waves"]), 4)
        self.assertIn("live_execution", config)
        self.assertEqual(config["live_execution"]["limits"]["max_model_calls"], 8)

    def test_live_execution_requires_server_password(self) -> None:
        with mock.patch.object(service, "_live_secret", return_value=""):
            config = service.dispatch("/config", "GET")
            self.assertFalse(config["live_execution"]["enabled"])
            self.assertFalse(config["live_execution"]["available"])
            with self.assertRaises(service.HarnessServiceError) as caught:
                service.dispatch("/live", "POST", {"prompt": "실제 실행"})
            self.assertEqual(caught.exception.status, 503)

    def test_live_password_issues_one_time_token(self) -> None:
        options = {
            "models": [{"value": "ollama:test", "available": True}],
            "providers": {},
        }
        with (
            mock.patch.object(service, "_live_secret", return_value="test-password"),
            mock.patch.object(service, "model_options", return_value=options),
        ):
            with self.assertRaises(service.HarnessServiceError) as caught:
                service.dispatch("/live/authorize", "POST", {"password": "wrong"})
            self.assertEqual(caught.exception.status, 401)
            authorized = service.dispatch("/live/authorize", "POST", {"password": "test-password"})
            token = authorized["authorization_token"]
            self.assertTrue(authorized["live_execution"]["enabled"])
            service._validate_live_token(token, consume=True)
            with self.assertRaises(service.HarnessServiceError) as reused:
                service._validate_live_token(token, consume=False)
            self.assertEqual(reused.exception.status, 401)

    def test_live_endpoint_publishes_background_progress(self) -> None:
        class StubExecutor:
            def __init__(self, gateway) -> None:  # noqa: ANN001
                self.gateway = gateway

            def execute(self, run, *, emit_event, publish_artifact) -> None:  # noqa: ANN001
                publish_artifact(
                    {
                        "id": "10_final_package.md",
                        "artifact_id": "10_final_package.md",
                        "title": "실제 결과",
                        "agent_id": "final-synthesizer",
                        "content": "# 실제 결과",
                    }
                )
                emit_event({"seq": 1, "at_ms": 0, "type": "run.started", "data": {"mode": "live-llm"}})
                emit_event(
                    {
                        "seq": 2,
                        "at_ms": 1,
                        "type": "run.completed",
                        "data": {"artifact_id": "10_final_package.md", "message": "완료"},
                    }
                )

        live_config = {
            "enabled": True,
            "available": True,
            "owner_available": True,
            "endpoint": "/live",
            "reason": "",
            "limits": {"max_concurrent_runs": 1, "max_model_calls": 8, "max_runs_per_hour": 1},
        }
        token = "background-test-token"
        service._LIVE_AUTH_TOKENS[token] = time.time() + 60
        with (
            mock.patch.object(service, "_live_execution_config", return_value=live_config),
            mock.patch.object(service, "LiveHarnessExecutor", StubExecutor),
            mock.patch.object(service, "_gateway", return_value=object()),
        ):
            started = service.dispatch("/live", "POST", {"prompt": "실제 실행", "authorization_token": token})
            snapshot = started
            deadline = time.time() + 2
            while snapshot["status"] not in {"complete", "failed"} and time.time() < deadline:
                time.sleep(0.01)
                snapshot = service.dispatch(f"/runs/{started['run_id']}", "GET")
            self.assertEqual(snapshot["status"], "complete")
            self.assertEqual(snapshot["events"][-1]["type"], "run.completed")
            self.assertEqual(snapshot["artifacts"][0]["id"], "10_final_package.md")
            self.assertNotIn(token, service._LIVE_AUTH_TOKENS)

    def test_personal_key_is_ephemeral_and_needs_no_owner_password(self) -> None:
        secret = "personal-key-must-not-enter-run"
        captured: dict[str, object] = {}

        class StubGateway:
            def __init__(self, key_overrides=None, *, allow_environment_keys=True) -> None:  # noqa: ANN001
                captured["keys"] = dict(key_overrides or {})
                captured["allow_environment_keys"] = allow_environment_keys

        class StubExecutor:
            def __init__(self, gateway) -> None:  # noqa: ANN001
                captured["gateway"] = gateway

            def execute(self, run, *, emit_event, publish_artifact) -> None:  # noqa: ANN001
                captured["run_contains_secret"] = secret in repr(run)
                emit_event(
                    {
                        "seq": 1,
                        "at_ms": 0,
                        "type": "run.completed",
                        "data": {"artifact_id": "10_final_package.md", "message": "완료"},
                    }
                )

        live_config = {
            "enabled": False,
            "available": False,
            "owner_available": False,
            "personal_key_available": True,
            "reason": "오너 키 비활성",
            "limits": {"max_concurrent_runs": 1, "max_model_calls": 8, "max_runs_per_hour": 1},
        }
        with (
            mock.patch.object(service, "_live_execution_config", return_value=live_config),
            mock.patch.object(service, "ModelGateway", StubGateway),
            mock.patch.object(service, "LiveHarnessExecutor", StubExecutor),
        ):
            started = service.dispatch(
                "/live",
                "POST",
                {
                    "prompt": "개인 키 실행",
                    "credential_mode": "personal",
                    "personal_keys": {"openrouter": secret},
                },
            )
            deadline = time.time() + 2
            snapshot = started
            while snapshot["status"] not in {"complete", "failed"} and time.time() < deadline:
                time.sleep(0.01)
                snapshot = service.dispatch(f"/runs/{started['run_id']}", "GET")
            self.assertEqual(snapshot["status"], "complete")
            self.assertEqual(snapshot["credential_mode"], "personal")
            self.assertNotIn(secret, repr(snapshot))
            self.assertEqual(captured["keys"], {"openrouter": secret})
            self.assertFalse(captured["allow_environment_keys"])
            self.assertFalse(captured["run_contains_secret"])

    def test_demo_applies_allowed_assignment(self) -> None:
        config = service.dispatch("/config", "GET")
        available = [item for item in config["model_registry"]["models"] if item["available"]]
        if not available:
            self.skipTest("사용 가능한 모델이 없음")
        selected = available[0]["value"]
        run = service.dispatch(
            "/demo",
            "POST",
            {"prompt": "가상 장애", "assignments": {"mission-manager": selected}},
        )
        manager = next(item for item in run["agents"] if item["id"] == "mission-manager")
        self.assertEqual(manager["model"], selected)


if __name__ == "__main__":
    unittest.main()
