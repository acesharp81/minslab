"""Repair the AIWorks audit hash chain after an explicitly approved incident.

Dry-run is the default. --apply creates an online SQLite backup, preserves
every existing event payload/order/id, recalculates only chain hashes, and
appends a repair event to the rebuilt chain.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "aiworks.sqlite3"
GENESIS_HASH = "0" * 64


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def load_json(value: str | None) -> dict:
    try:
        parsed = json.loads(value) if value else {}
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def event_canonical(row: sqlite3.Row) -> str:
    return canonical_json({
        "id": row["id"],
        "executionId": row["execution_id"],
        "planId": row["plan_id"],
        "actor": row["actor"],
        "eventType": row["event_type"],
        "detail": load_json(row["detail_json"]),
        "createdAt": row["created_at"],
    })


def inspect(rows: list[sqlite3.Row]) -> dict:
    previous_hash = GENESIS_HASH
    failures: list[dict] = []
    for row in rows:
        expected = hashlib.sha256((previous_hash + "\0" + event_canonical(row)).encode("utf-8")).hexdigest()
        if (
            not hmac.compare_digest(str(row["previous_hash"] or ""), previous_hash)
            or not hmac.compare_digest(str(row["event_hash"] or ""), expected)
        ):
            failures.append({"id": row["id"], "eventType": row["event_type"]})
        previous_hash = str(row["event_hash"] or expected)
    return {
        "events": len(rows),
        "valid": not failures,
        "headHash": previous_hash,
        "failures": failures,
    }


def backup_database(source: sqlite3.Connection, db_path: Path) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"{db_path.stem}-before-audit-repair-{stamp}.sqlite3"
    destination = sqlite3.connect(backup_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
    return backup_path


def repair(connection: sqlite3.Connection, before: dict) -> dict:
    rows = connection.execute("SELECT * FROM audit_events ORDER BY id").fetchall()
    previous_hash = GENESIS_HASH
    for row in rows:
        event_hash = hashlib.sha256((previous_hash + "\0" + event_canonical(row)).encode("utf-8")).hexdigest()
        connection.execute(
            "UPDATE audit_events SET previous_hash=?,event_hash=? WHERE id=?",
            (previous_hash, event_hash, row["id"]),
        )
        previous_hash = event_hash

    created_at = utc_now()
    detail = {
        "contractVersion": "audit-chain-repair/1.0",
        "approved": True,
        "preservedEventCount": len(rows),
        "previousHeadHash": before["headHash"],
        "previousFailureIds": [item["id"] for item in before["failures"]],
        "repairScope": ["previous_hash", "event_hash"],
    }
    cursor = connection.execute(
        "INSERT INTO audit_events(execution_id,plan_id,actor,event_type,detail_json,created_at,previous_hash,event_hash) "
        "VALUES(NULL,NULL,?,?,?,?,?,NULL)",
        (
            "operator-approved-maintenance",
            "audit.chain_repaired",
            canonical_json(detail),
            created_at,
            previous_hash,
        ),
    )
    event_id = int(cursor.lastrowid)
    inserted = connection.execute("SELECT * FROM audit_events WHERE id=?", (event_id,)).fetchone()
    event_hash = hashlib.sha256((previous_hash + "\0" + event_canonical(inserted)).encode("utf-8")).hexdigest()
    connection.execute("UPDATE audit_events SET event_hash=? WHERE id=?", (event_hash, event_id))
    return {"repairEventId": event_id, "newHeadHash": event_hash}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    db_path = args.db.expanduser().resolve()
    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute("SELECT * FROM audit_events ORDER BY id").fetchall()
        before = inspect(rows)
        report = {"mode": "apply" if args.apply else "dry-run", "database": str(db_path), "before": before}
        if args.apply:
            report["backup"] = str(backup_database(connection, db_path))
            connection.execute("BEGIN IMMEDIATE")
            try:
                report["result"] = repair(connection, before)
                after_rows = connection.execute("SELECT * FROM audit_events ORDER BY id").fetchall()
                report["after"] = inspect(after_rows)
                if not report["after"]["valid"]:
                    raise RuntimeError("audit chain remains invalid after repair")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
