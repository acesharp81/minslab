import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "gitlab_sync.py"
SPEC = importlib.util.spec_from_file_location("minslab_gitlab_sync", SCRIPT)
sync = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sync
SPEC.loader.exec_module(sync)


class GitLabSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="gitlab-sync-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "source"
        self.root.mkdir()
        self.git(self.root, "init", "-b", "main")
        self.identity(self.root)
        self.projects = {}
        for key, original in sync.PROJECTS.items():
            directory = self.root / original.prefix
            directory.mkdir(parents=True)
            (directory / "README.md").write_text(original.name, encoding="utf-8")
            (directory / "app.py").write_text(f"SERVICE = {key!r}\n")
            (directory / ".gitignore").write_text(".env\n")
            remote = self.base / f"{key}.git"
            self.git(self.base, "init", "--bare", "--initial-branch=main", str(remote))
            self.projects[key] = sync.Project(original.name, original.prefix, str(remote), original.token_env)
        (self.root / "parent-only.txt").write_text("must not be exported")
        self.commit("initial monorepo")
        self.env = {
            key: value for key, value in os.environ.items()
            if key not in {"GITLAB_TOKEN", "GITLAB_USERNAME", "GIT_ASKPASS", "GITLAB_KJON_TOKEN", "GITLAB_HOME_TOKEN"}
        }
        self.env["GIT_TERMINAL_PROMPT"] = "0"

    def git(self, root, *args):
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=False,
        )
        if result.returncode:
            self.fail(result.stderr or result.stdout)
        return result.stdout.strip()

    def identity(self, root):
        self.git(root, "config", "user.name", "Sync Test")
        self.git(root, "config", "user.email", "sync@example.invalid")

    def commit(self, message):
        self.git(self.root, "add", "--all")
        self.git(self.root, "commit", "-m", message)
        return self.git(self.root, "rev-parse", "HEAD")

    def prepare(self, key):
        return sync.prepare_export(
            self.root, self.projects[key], self.git(self.root, "rev-parse", "HEAD"),
        )

    def tip(self, key):
        return self.git(Path(self.projects[key].remote), "rev-parse", "main")

    def refs(self, key):
        return self.git(Path(self.projects[key].remote), "for-each-ref", "--format=%(refname)")

    def test_exports_exact_project_trees_and_only_main_without_changing_source(self):
        head = self.git(self.root, "rev-parse", "HEAD")
        index = self.git(self.root, "write-tree")
        self.git(self.root, "config", "push.followTags", "true")
        for key, project in self.projects.items():
            with self.subTest(project=key):
                export = self.prepare(key)
                self.git(self.root, "tag", "-a", f"export-{key}", "-m", "do not push", export.commit)
                sync.publish(self.root, export, self.env)
                remote = Path(project.remote)
                self.assertEqual(
                    self.git(remote, "rev-parse", "main^{tree}"),
                    self.git(self.root, "rev-parse", f"HEAD:{project.prefix}"),
                )
                self.assertEqual(self.refs(key), "refs/heads/main")
                self.assertEqual(export.files, 3)
                for commit in self.git(remote, "rev-list", "main").splitlines():
                    names = self.git(remote, "ls-tree", "-r", "--name-only", commit).splitlines()
                    self.assertEqual(set(names), {"README.md", "app.py", ".gitignore"})
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD"), head)
        self.assertEqual(self.git(self.root, "write-tree"), index)
        self.assertEqual(self.git(self.root, "branch", "--show-current"), "main")
        self.assertEqual(self.git(self.root, "status", "--porcelain"), "")

    def test_evidence_is_removed_from_all_history_but_runtime_data_and_fixtures_remain(self):
        prefix = self.root / self.projects['home'].prefix
        evidence = prefix / 'docs/evidence/audit.json'
        evidence.parent.mkdir(parents=True)
        evidence.write_text('large generated verification dump')
        for name in ['tests/fixtures/source.json', 'backend/data/seed.json', 'docs/setup.md']:
            path = prefix / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('required reconstruction input')
        self.commit('add reconstruction inputs and audit dump')
        refs = self.git(self.root, 'show-ref')
        fetch_head = self.root / '.git/FETCH_HEAD'
        fetch_head.write_text('keep existing fetch marker\n')
        export = self.prepare('home')
        sync.publish(self.root, export, self.env)
        for commit in self.git(Path(export.project.remote), 'rev-list', 'main').splitlines():
            paths = self.git(Path(export.project.remote), 'ls-tree', '-r', '--name-only', commit)
            self.assertNotIn('docs/evidence/', paths)
        paths = self.git(Path(export.project.remote), 'ls-tree', '-r', '--name-only', 'main')
        for name in ['tests/fixtures/source.json', 'backend/data/seed.json', 'docs/setup.md']:
            self.assertIn(name, paths)
        self.assertEqual(self.git(self.root, 'show-ref'), refs)
        self.assertEqual(fetch_head.read_text(), 'keep existing fetch marker\n')
        evidence.write_text('new verification dump only')
        self.commit('change audit dump only')
        self.assertEqual(self.prepare('home').commit, export.commit)
        self.assertTrue(evidence.exists())


    def test_publication_starts_at_reviewed_version_and_future_updates_fast_forward(self):
        key = 'home'
        directory = self.root / self.projects[key].prefix
        (directory / 'README.md').write_text('unpublished legacy implementation')
        old_source = self.commit('legacy change')
        (directory / 'README.md').write_text('reviewed reconstructable implementation')
        baseline = self.commit('reviewed publication baseline')
        original = self.projects[key]
        self.projects[key] = sync.Project(original.name, original.prefix, original.remote,
                                          original.token_env, baseline)
        first = self.prepare(key)
        sync.publish(self.root, first, self.env)
        remote = Path(original.remote)
        self.assertEqual(self.git(remote, 'rev-list', '--count', 'main'), '1')
        self.assertEqual(self.git(remote, 'show', 'main:README.md'), 'reviewed reconstructable implementation')
        (directory / 'app.py').write_text('reviewed incremental update')
        self.commit('incremental source update')
        second = self.prepare(key)
        sync.publish(self.root, second, self.env)
        self.assertEqual(self.git(remote, 'rev-list', '--count', 'main'), '2')
        self.assertEqual(self.git(remote, 'rev-parse', 'main^'), first.commit)
        self.assertEqual(self.prepare(key).commit, second.commit)
        with self.assertRaises(sync.SyncError):
            sync.prepare_export(self.root, self.projects[key], old_source)


    def test_repeated_sync_and_other_project_commits_do_not_change_export(self):
        first = self.prepare("kjon")
        sync.publish(self.root, first, self.env)
        sync.publish(self.root, self.prepare("kjon"), self.env)
        (self.root / self.projects["home"].prefix / "README.md").write_text("home only")
        self.commit("change HOME only")
        (self.root / "parent-only.txt").write_text("parent only change")
        self.commit("change parent only")
        second = self.prepare("kjon")
        self.assertEqual(first.commit, second.commit)
        sync.publish(self.root, second, self.env)
        self.assertEqual(self.tip("kjon"), first.commit)

    def test_selected_updates_and_deletions_preserve_other_remote(self):
        for key in self.projects:
            sync.publish(self.root, self.prepare(key), self.env)
        home_tip = self.tip("home")
        original = self.tip("kjon")
        directory = self.root / self.projects["kjon"].prefix
        (directory / "app.py").unlink()
        (directory / "README.md").write_text("updated 국정ON", encoding="utf-8")
        self.commit("update national assembly")
        export = self.prepare("kjon")
        sync.publish(self.root, export, self.env)
        self.assertNotEqual(self.tip("kjon"), original)
        self.assertEqual(self.tip("home"), home_tip)
        remote = Path(self.projects["kjon"].remote)
        self.assertNotIn("app.py", self.git(remote, "ls-tree", "--name-only", "main").splitlines())
        self.assertEqual(self.git(remote, "rev-list", "--count", "main"), "2")

    def test_dirty_project_cannot_be_published(self):
        directory = self.root / self.projects["kjon"].prefix
        (directory / "README.md").write_text("not committed")
        export = self.prepare("kjon")
        self.assertTrue(export.dirty)
        with self.assertRaisesRegex(sync.SyncError, "미커밋"):
            sync.publish(self.root, export, self.env)
        self.assertEqual(self.refs("kjon"), "")

    def test_untracked_project_file_cannot_be_silently_omitted_from_push(self):
        (self.root / self.projects["kjon"].prefix / "new.py").write_text("untracked")
        self.assertTrue(self.prepare("kjon").dirty)

    def test_other_dirty_project_and_ignored_environment_do_not_block_selected_push(self):
        (self.root / self.projects["home"].prefix / "README.md").write_text("home in progress")
        (self.root / self.projects["kjon"].prefix / ".env").write_text("EXAMPLE_ONLY=ignored")
        export = self.prepare("kjon")
        self.assertFalse(export.dirty)
        sync.publish(self.root, export, self.env)
        names = self.git(Path(export.project.remote), "ls-tree", "-r", "--name-only", "main")
        self.assertNotIn(".env", names.splitlines())

    def test_independent_remote_change_is_not_overwritten(self):
        sync.publish(self.root, self.prepare("kjon"), self.env)
        remote = Path(self.projects["kjon"].remote)
        independent = self.base / "gitlab-edit"
        self.git(self.base, "clone", str(remote), str(independent))
        self.identity(independent)
        (independent / "README.md").write_text("independent GitLab change")
        self.git(independent, "add", "README.md")
        self.git(independent, "commit", "-m", "GitLab change")
        self.git(independent, "push", "origin", "main")
        protected = self.tip("kjon")
        (self.root / self.projects["kjon"].prefix / "README.md").write_text("source change")
        self.commit("source change")
        with self.assertRaises(sync.SyncError):
            sync.publish(self.root, self.prepare("kjon"), self.env)
        self.assertEqual(self.tip("kjon"), protected)

    def test_shallow_source_requires_full_history(self):
        clone = self.base / "shallow"
        self.git(self.base, "clone", "--depth=1", self.root.as_uri(), str(clone))
        with self.assertRaisesRegex(sync.SyncError, "전체 Git 이력"):
            sync.prepare_export(clone, self.projects["kjon"], self.git(clone, "rev-parse", "HEAD"))

    def test_cli_defaults_to_preview_and_preflights_both_projects_before_push(self):
        with patch.object(sync, "__file__", str(self.root / "deploy" / "gitlab_sync.py")), \
             patch.object(sync, "PROJECTS", self.projects), \
             patch("sys.stdout", new_callable=io.StringIO), \
             patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(sync.main(["all"]), 0)
            self.assertEqual(self.refs("kjon"), "")
            self.assertEqual(self.refs("home"), "")
            (self.root / self.projects["home"].prefix / "README.md").write_text("dirty HOME")
            self.assertEqual(sync.main(["all", "--push"]), 1)
            self.assertEqual(self.refs("kjon"), "")
            self.assertEqual(self.refs("home"), "")

    def test_ci_askpass_reads_credentials_from_environment_and_is_removed(self):
        with patch.dict(os.environ, {"GITLAB_USERNAME": "test-user", "GITLAB_TOKEN": "test-only-token"}):
            with sync.push_environment() as env:
                helper = Path(env["GIT_ASKPASS"])
                self.assertNotIn("test-only-token", helper.read_text())
                self.assertNotIn("test-user", helper.read_text())
                self.assertEqual(helper.stat().st_mode & 0o777, 0o700)
                for prompt, expected in [("Username for 'https://example.invalid'", "test-user"),
                                         ("Password for 'https://example.invalid'", "test-only-token")]:
                    result = subprocess.run([str(helper), prompt], env=env, capture_output=True, text=True, check=True)
                    self.assertEqual(result.stdout.strip(), expected)
            self.assertFalse(helper.exists())

    def test_each_project_receives_only_its_own_token(self):
        credentials = dict(self.env, GITLAB_KJON_TOKEN="assembly-test-token",
                           GITLAB_HOME_TOKEN="housing-test-token", GITLAB_TOKEN="legacy-test-token")
        with patch.dict(os.environ, credentials, clear=True):
            for key, expected in [("kjon", "assembly-test-token"), ("home", "housing-test-token")]:
                with self.subTest(project=key), sync.push_environment(self.projects[key]) as env:
                    self.assertEqual(env["GITLAB_TOKEN"], expected)
                    self.assertEqual(env["GITLAB_USERNAME"], "gitlab-sync")
                    self.assertNotIn("GITLAB_KJON_TOKEN", env)
                    self.assertNotIn("GITLAB_HOME_TOKEN", env)
                    result = subprocess.run([env["GIT_ASKPASS"], "Password"], env=env,
                                            capture_output=True, text=True, check=True)
                    self.assertEqual(result.stdout.strip(), expected)

    def test_missing_project_token_does_not_use_another_token_or_publish_partially(self):
        credentials = dict(self.env, GITLAB_KJON_TOKEN="assembly-test-token", GITLAB_TOKEN="legacy-test-token")
        with patch.dict(os.environ, credentials, clear=True):
            with self.assertRaisesRegex(sync.SyncError, "GITLAB_HOME_TOKEN"):
                with sync.push_environment(self.projects["home"]):
                    self.fail("Missing housing token must not fall back to the shared token")
            with patch.object(sync, "__file__", str(self.root / "deploy" / "gitlab_sync.py")), \
                 patch.object(sync, "PROJECTS", self.projects), \
                 patch("sys.stdout", new_callable=io.StringIO), \
                 patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(sync.main(["all", "--push"]), 1)
            self.assertEqual(self.refs("kjon"), "")
            self.assertEqual(self.refs("home"), "")

    def test_explicitly_empty_project_token_cannot_use_legacy_credentials(self):
        with self.assertRaisesRegex(sync.SyncError, "GITLAB_KJON_TOKEN"):
            sync.token_for(self.projects["kjon"], {"GITLAB_KJON_TOKEN": "", "GITLAB_TOKEN": "legacy-test-token"})

    def test_askpass_uses_runner_scratch_instead_of_noexec_system_tmp(self):
        scratch = self.base / "runner-temp"
        scratch.mkdir()
        credentials = dict(self.env, RUNNER_TEMP=str(scratch), GITLAB_TOKEN="test-only-token")
        with patch.dict(os.environ, credentials, clear=True):
            with sync.push_environment() as env:
                helper = Path(env["GIT_ASKPASS"])
                self.assertTrue(helper.is_relative_to(scratch))
                result = subprocess.run([str(helper), "Password"], env=env,
                                        capture_output=True, text=True, check=True)
                self.assertEqual(result.stdout.strip(), "test-only-token")
            self.assertFalse(helper.exists())

    def test_transport_summary_does_not_disclose_headers_or_body(self):
        trace = self.base / "trace.log"
        trace.write_text("\n".join([
            "01:02:03.000001 http.c: => Send header: Authorization: Basic private-token",
            "01:02:03.000002 http.c: => Send header: Content-Length: 1234",
            "01:02:03.000003 http.c: == Info: upload completely sent off: 1234 bytes",
            "01:02:04.000004 http.c: <= Recv header: HTTP/1.1 502 Bad Gateway",
            "01:02:04.000005 http.c: <= Recv header: Set-Cookie: private-session",
            "01:02:04.000006 http.c: <= Recv data: private-response",
        ]))
        self.assertEqual(sync.trace_summary(trace), [
            "01:02:03.000002 request bytes=1234",
            "01:02:03.000003 upload complete bytes=1234",
            "01:02:04.000004 HTTP 502",
        ])

    def test_diagnostic_push_preserves_result_and_removes_private_trace(self):
        scratch = self.base / "scratch"
        scratch.mkdir()
        export = self.prepare("home")
        env = dict(self.env, RUNNER_TEMP=str(scratch))
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            sync.publish(self.root, export, env, diagnose=True)
        self.assertEqual(self.tip("home"), export.commit)
        self.assertIn("push elapsed:", output.getvalue())
        self.assertEqual(list(scratch.iterdir()), [])
        self.assertNotIn("GIT_TRACE_CURL", env)
        (self.root / export.project.prefix / "README.md").write_text("new")
        self.commit("new source revision")
        with patch.object(sync, "git", side_effect=sync.SyncError("HTTP 502")), \
             patch("sys.stdout", new_callable=io.StringIO):
            with self.assertRaisesRegex(sync.SyncError, "HTTP 502"):
                sync.publish(self.root, export, env, diagnose=True)
        self.assertEqual(list(scratch.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
