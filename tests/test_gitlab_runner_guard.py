import os
from pathlib import Path
import subprocess
import unittest


GUARD = Path(__file__).resolve().parents[1] / "deploy/gitlab-runner/job-guard.sh"


class GitLabRunnerGuardTests(unittest.TestCase):
    def run_guard(self, **changes):
        env = dict(os.environ, GITHUB_REPOSITORY="acesharp81/minslab",
                   GITHUB_REF="refs/heads/main", GITHUB_EVENT_NAME="push",
                   GITHUB_WORKFLOW_REF="acesharp81/minslab/.github/workflows/sync-gitlab-projects.yml@refs/heads/main")
        env.update(changes)
        return subprocess.run(["bash", str(GUARD)], env=env, text=True, capture_output=True)

    def test_accepts_only_main_sync_push_and_manual_jobs(self):
        for event in ("push", "workflow_dispatch"):
            with self.subTest(event=event):
                result = self.run_guard(GITHUB_EVENT_NAME=event)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_pull_requests_other_repositories_branches_and_workflows(self):
        cases = [
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
