import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GoldenWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ.update(
            {
                "AIWORKS_DB_PATH": str(Path(self.tempdir.name) / "golden.sqlite3"),
                "AIWORKS_ENABLE_DEMO_SEED": "0",
                "AIWORKS_APPROVAL_SECRET": "golden-test-secret",
                "AIWORKS_SOLAR_LIVE": "0",
                "AIWORKS_OPENROUTER_LIVE": "0",
                "AIWORKS_LOCAL_RAG_LLM": "0",
            }
        )
        self.backend = load_module("ai_work_hub_golden_test_backend", ROOT / "backend.py")
        self.runner = load_module("ai_work_hub_golden_runner", ROOT / "golden_workflows" / "runner.py")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_budget_business_review_completes_full_round_trip(self):
        report = self.runner.run(self.backend)
        failed = [item for item in report["checks"] if not item["passed"]]
        self.assertEqual(report["status"], "passed", failed)
        self.assertEqual(report["artifacts"]["finalRevision"], 2)
        self.assertNotEqual(
            report["artifacts"]["initialMarkdownVersionId"],
            report["artifacts"]["finalMarkdownVersionId"],
        )


if __name__ == "__main__":
    unittest.main()
