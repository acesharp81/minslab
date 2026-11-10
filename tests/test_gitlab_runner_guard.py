import json
import os
import tempfile
from pathlib import Path
import subprocess
import unittest


GUARD = Path(__file__).resolve().parents[1] / "deploy/gitlab-runner/job-guard.sh"


class GitLabRunnerGuardTests(unittest.TestCase):
    def run_guard(self, inputs=None, **changes):
        env = dict(os.environ, GITHUB_REPOSITORY="acesharp81/minslab",
                   GITHUB_REF="refs/heads/main", GITHUB_EVENT_NAME="workflow_dispatch",
                   GITHUB_WORKFLOW_REF="acesharp81/minslab/.github/workflows/sync-gitlab-projects.yml@refs/heads/main")
        env.update(changes)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as event_file:
            json.dump({"inputs": inputs if inputs is not None else {
                "approved": "true", "source_sha": "a" * 40, "project": "check",
            }}, event_file)
            event_file.flush()
            env["GITHUB_EVENT_PATH"] = event_file.name
            return subprocess.run(["bash", str(GUARD)], env=env, text=True, capture_output=True)

    def test_accepts_approved_manual_jobs_for_each_selection(self):
        for project in ("check", "baton", "kjon", "home", "all"):
            with self.subTest(project=project):
                result = self.run_guard(inputs={"approved": "true", "source_sha": "a" * 40, "project": project})
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_legacy_manual_runs_and_missing_or_invalid_approval(self):
        valid = {"approved": "true", "source_sha": "a" * 40, "project": "check"}
        for inputs in ({}, {"project": "home"}, dict(valid, approved="false"),
                       dict(valid, source_sha="main"), dict(valid, project="unknown")):
            with self.subTest(inputs=inputs):
                self.assertNotEqual(self.run_guard(inputs=inputs).returncode, 0)

    def test_rejects_pull_requests_other_repositories_branches_and_workflows(self):
        cases = [
            dict(GITHUB_EVENT_NAME="push"),
            dict(GITHUB_EVENT_NAME="pull_request"),
            dict(GITHUB_EVENT_NAME="pull_request_target"),
            dict(GITHUB_EVENT_NAME="workflow_run"),
            dict(GITHUB_REPOSITORY="some-fork/minslab"),
            dict(GITHUB_REF="refs/heads/feature"),
            dict(GITHUB_WORKFLOW_REF="acesharp81/minslab/.github/workflows/other.yml@refs/heads/main"),
            dict(GITHUB_WORKFLOW_REF="acesharp81/minslab/.github/workflows/sync-gitlab-projects.yml@refs/pull/1/merge"),
            dict(GITHUB_WORKFLOW_REF=""),
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                self.assertNotEqual(self.run_guard(**changes).returncode, 0)


if __name__ == "__main__":
    unittest.main()
