from __future__ import annotations

import threading
import unittest

from harness_engine import AGENTS
from live_executor import LiveHarnessExecutor, new_live_run


class FakeGateway:
    def __init__(self) -> None:
        refs = {agent.model for agent in AGENTS}
        self.allowed = {ref: {"available": True} for ref in refs}
        self.options = {"default": sorted(refs)[0]}
        self.calls: list[str] = []
        self.lock = threading.Lock()

    def complete(self, model_ref, messages, **settings):  # noqa: ANN001, ANN003
        with self.lock:
            self.calls.append(model_ref)
            index = len(self.calls)
        self.assert_messages(messages)
        return f"# 실제 모델 산출물 {index}\n\n테스트 게이트웨이 결과입니다."

    @staticmethod
    def assert_messages(messages) -> None:  # noqa: ANN001
        if not messages or messages[-1]["role"] != "user":
            raise AssertionError("user 메시지가 필요합니다.")


class LiveExecutorTests(unittest.TestCase):
    def test_live_executor_runs_eight_model_tasks(self) -> None:
        run = new_live_run("가상 예약 서비스 장애 대응")
        events = []
        artifacts = []
        lock = threading.Lock()

        def emit(event) -> None:  # noqa: ANN001
            with lock:
                events.append(event)

        def publish(artifact) -> None:  # noqa: ANN001
            with lock:
                artifacts.append(artifact)

        gateway = FakeGateway()
        LiveHarnessExecutor(gateway).execute(
            run,
            emit_event=emit,
            publish_artifact=publish,
        )
        self.assertEqual(len(gateway.calls), 8)
        self.assertEqual(len(artifacts), 9)
        self.assertEqual(len({item["id"] for item in artifacts}), 9)
        self.assertEqual(events[-1]["type"], "run.completed")
        self.assertTrue(any(event["type"] == "review.passed" for event in events))
        self.assertTrue(all(item["content"] for item in artifacts))

    def test_live_run_rejects_large_prompt(self) -> None:
        with self.assertRaises(Exception):
            new_live_run("가" * 2001)


if __name__ == "__main__":
    unittest.main()
