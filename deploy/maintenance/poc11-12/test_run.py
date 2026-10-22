"""Exercise retirement and rollback using temporary files and mocked services."""
from datetime import timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("retirement", Path(__file__).with_name("run.py"))
retirement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retirement)


class RetirementTests(unittest.TestCase):
    def exercise(self, regression=False, changed_source=False, immediate=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "private-state"
            unit = root / "poc12.service"
            unit.write_text("original unit")
            for relative in retirement.TARGETS:
                (root / relative).mkdir(parents=True)
                (root / relative / "only-this-poc").write_text(relative)
            (root / "main.py").write_text("original main")
            (root / "other-service").write_text("preserve")
            calls = []

            def systemctl(*args, **kwargs):
                calls.append(args)
                return types.SimpleNamespace(stdout="", returncode=0)

            def command(*args, **kwargs):
                if args[:4] == ("sudo", "-n", "/usr/bin/rm", "--"):
                    unit.unlink()
                return types.SimpleNamespace(stdout="enabled\n", returncode=0)

            before = dict.fromkeys(retirement.PATHS, 200)
            before[retirement.PATHS[-1]] = 0
            after = dict(before)
            if regression:
                after["/poc/home/"] = 503
            clock = types.SimpleNamespace(now=lambda tz: retirement.START - timedelta(hours=1) if immediate else retirement.START)
            with mock.patch.multiple(retirement, ROOT=root, STATE=state, UNIT=unit, datetime=clock), \
                 mock.patch.object(retirement, "systemctl", side_effect=systemctl), \
                 mock.patch.object(retirement, "command", side_effect=command), \
                 mock.patch.object(retirement, "reviewed_changes", return_value=retirement.PreparedChanges(
                                       {"main.py": b"retired main"}, {"main.py": b"original main"}),
                                   side_effect=RuntimeError("changed reviewed source") if changed_source else None), \
                 mock.patch.object(retirement, "validate"), \
                 mock.patch.object(retirement, "snapshot", side_effect=[before, after]), \
                 mock.patch.object(retirement, "status", return_value=200), \
                 mock.patch.object(retirement, "verify_retired_routes"), \
                 mock.patch.object(retirement.socket, "socket") as connection, mock.patch("builtins.print"):
                connection.return_value.__enter__.return_value.connect_ex.return_value = 111
                if regression or changed_source:
                    with self.assertRaises(RuntimeError):
                        retirement.execute()
                else:
                    retirement.execute(immediate=immediate)
            result = json.loads((state / "result.json").read_text())
            self.assertEqual((root / "other-service").read_text(), "preserve")
            if changed_source:
                self.assertEqual(result["status"], "aborted")
                self.assertEqual(calls, [])
            elif regression:
                self.assertEqual(result["status"], "rolled_back")
                self.assertEqual((root / "main.py").read_text(), "original main")
                self.assertTrue(all((root / path / "only-this-poc").exists() for path in retirement.TARGETS))
                self.assertTrue(unit.exists())
            else:
                self.assertEqual(result["status"], "completed")
                self.assertEqual((root / "main.py").read_text(), "retired main")
                self.assertTrue(all(not (root / path).exists() for path in retirement.TARGETS))
                self.assertFalse((state / "pending-delete").exists())
                self.assertFalse(unit.exists())

    def test_success_deletes_only_targets(self):
        self.exercise()

    def test_user_approved_immediate_execution_retains_all_checks(self):
        self.exercise(immediate=True)

    def test_protected_service_operations_are_rejected(self):
        with mock.patch.object(retirement, "command") as command:
            with self.assertRaisesRegex(RuntimeError, "outside the approved deletion scope"):
                retirement.systemctl("stop", "poc10-home-api.service")
            command.assert_not_called()

    def test_protected_directory_edits_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            job = Path(temporary)
            (job / "review.json").write_text(json.dumps({"edits": [{"path": "PoC/10-home/README.md"}]}))
            with mock.patch.object(retirement, "JOB", job):
                with self.assertRaisesRegex(RuntimeError, "beyond the approved shared files"):
                    retirement.reviewed_changes()

    def test_regression_restores_both_services_and_files(self):
        self.exercise(regression=True)

    def test_changed_source_aborts_before_service_changes(self):
        self.exercise(changed_source=True)

    def test_outside_window_never_changes_services(self):
        clock = types.SimpleNamespace(now=lambda tz: retirement.START - timedelta(days=1))
        with mock.patch.object(retirement, "datetime", clock), \
             mock.patch.object(retirement, "systemctl") as systemctl:
            with self.assertRaisesRegex(RuntimeError, "Outside the approved"):
                retirement.execute()
            systemctl.assert_not_called()

    def check_edit(self, relative, before, current):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(current)
        entry = {"path": relative, "sha256": hashlib.sha256(before).hexdigest(),
                 "replacements": [["retired PoC entry\n", ""]]}
        with mock.patch.object(retirement, "ROOT", root):
            return retirement.prepare_shared_edits([entry])

    def test_unrelated_home_documentation_changes_are_preserved(self):
        before = b"HOME\nretired PoC entry\n"
        current = before + b"new HOME documentation\n"
        result = self.check_edit("PoC/10-home/README.md", before, current)
        self.assertEqual(result["PoC/10-home/README.md"], b"HOME\nnew HOME documentation\n")
        self.assertEqual(result.originals["PoC/10-home/README.md"], current)

    def test_executable_changes_still_require_review(self):
        with self.assertRaisesRegex(RuntimeError, "Reviewed file changed"):
            self.check_edit("main.py", b"retired PoC entry\n", b"retired PoC entry\nnew code\n")

    def test_changed_documentation_target_requires_review(self):
        with self.assertRaisesRegex(RuntimeError, "Edit no longer matches"):
            self.check_edit("PoC/10-home/README.md", b"retired PoC entry\n", b"different entry\n")


if __name__ == "__main__":
    unittest.main()
