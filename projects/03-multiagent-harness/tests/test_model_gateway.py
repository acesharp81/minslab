from __future__ import annotations

import threading
import time
import unittest
from unittest import mock

from model_gateway import ModelGateway, ProviderLane, _bounded_float, _bounded_int, model_options


class ModelGatewayTests(unittest.TestCase):
    def test_settings_are_bounded(self) -> None:
        self.assertEqual(_bounded_int("99", 2, 1, 8), 8)
        self.assertEqual(_bounded_int("bad", 2, 1, 8), 2)
        self.assertEqual(_bounded_float(-1, 0.2, 0.0, 1.5), 0.0)

    def test_provider_lane_enforces_single_slot(self) -> None:
        lane = ProviderLane("ollama", 1)
        active = 0
        peak = 0
        lock = threading.Lock()

        def work() -> str:
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.03)
            with lock:
                active -= 1
            return "ok"

        threads = [threading.Thread(target=lambda: lane.execute(work)) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(peak, 1)
        self.assertEqual(lane.snapshot()["completed"], 3)

    def test_personal_keys_do_not_fallback_to_owner_remote_keys(self) -> None:
        with (
            mock.patch.dict(
                "os.environ",
                {"OPENROUTER_API_KEY": "owner-openrouter", "HF_API_KEY": "owner-hf"},
            ),
            mock.patch("model_gateway._ollama_models", return_value=[]),
        ):
            options = model_options(
                {"openrouter": "personal-openrouter"},
                allow_environment_keys=False,
            )
            by_provider = {item["provider"]: item for item in options["models"]}
            self.assertTrue(by_provider["openrouter"]["available"])
            self.assertFalse(by_provider["huggingface"]["available"])
            gateway = ModelGateway(
                {"openrouter": "personal-openrouter"},
                allow_environment_keys=False,
            )
            self.assertTrue(gateway.allowed["openrouter:openai/gpt-4o-mini"]["available"])
            self.assertFalse(gateway.allowed["huggingface:Qwen/Qwen2.5-72B-Instruct"]["available"])


if __name__ == "__main__":
    unittest.main()
