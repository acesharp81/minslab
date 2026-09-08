from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_repair_module():
    path = ROOT / "scripts" / "repair_audit_chain.py"
    spec = importlib.util.spec_from_file_location("aiworks_repair_audit_chain", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def load_restore_module():
    path = ROOT / "scripts" / "sqlite_live_restore_drill.py"
    spec = importlib.util.spec_from_file_location("aiworks_sqlite_live_restore_drill", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


class AIWorksMaintenanceTests(unittest.TestCase):
    def test_audit_repair_preserves_events_and_appends_repair_record(self):
        repair_module = load_repair_module()
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute(
            "CREATE TABLE audit_events("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "execution_id TEXT,plan_id TEXT,actor TEXT NOT NULL,event_type TEXT NOT NULL,"
            "detail_json TEXT NOT NULL,created_at TEXT NOT NULL,previous_hash TEXT,event_hash TEXT)"
        )
        connection.execute(
            "INSERT INTO audit_events(execution_id,plan_id,actor,event_type,detail_json,created_at,previous_hash,event_hash) "
            "VALUES(NULL,NULL,'tester','fixture.created','{\"value\":1}','2026-09-01T00:00:00.000Z','broken','broken')"
        )
        before_rows = connection.execute("SELECT * FROM audit_events ORDER BY id").fetchall()
        before = repair_module.inspect(before_rows)
        self.assertFalse(before["valid"])

        result = repair_module.repair(connection, before)
        after_rows = connection.execute("SELECT * FROM audit_events ORDER BY id").fetchall()
        after = repair_module.inspect(after_rows)
        self.assertTrue(after["valid"])
        self.assertEqual(2, after["events"])
        self.assertEqual("fixture.created", after_rows[0]["event_type"])
        self.assertEqual('{"value":1}', after_rows[0]["detail_json"])
        self.assertEqual("audit.chain_repaired", after_rows[1]["event_type"])
        self.assertEqual(result["repairEventId"], after_rows[1]["id"])

    def test_fixture_cleanup_never_deletes_audit_events(self):
        source = (ROOT / "scripts" / "cleanup_test_data.py").read_text(encoding="utf-8")
        self.assertNotIn("DELETE FROM audit_events", source)

    def test_live_restore_drill_preserves_logical_data_and_original_copy(self):
        restore = load_restore_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            db_path = root / "service.sqlite3"
            with sqlite3.connect(db_path) as connection:
                connection.execute("CREATE TABLE records(id INTEGER PRIMARY KEY,value TEXT,content BLOB)")
                connection.execute("INSERT INTO records(value,content) VALUES(?,?)", ("보존 값", b"binary"))
            before = restore.database_snapshot(db_path)
            result = restore.run_restore_drill(
                db_path,
                root / "backups",
                apply_live_swap=True,
                confirm_path=str(db_path.resolve()),
                health_port=0,
            )
            after = restore.database_snapshot(db_path)
            self.assertEqual("passed", result["status"])
            self.assertTrue(result["applied"])
            self.assertEqual(before["logicalSha256"], after["logicalSha256"])
            self.assertTrue(Path(result["backup"]).is_file())
            self.assertTrue(Path(result["displacedOriginal"]).is_file())
            self.assertTrue(Path(result["manifest"]).is_file())


if __name__ == "__main__":
    unittest.main()
