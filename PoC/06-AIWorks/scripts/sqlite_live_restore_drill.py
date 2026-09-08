#!/usr/bin/env python3
"""Create, validate, and optionally live-swap an AI Work Hub SQLite backup."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_value(digest: "hashlib._Hash", value) -> None:
    if value is None:
        digest.update(b"N\0")
    elif isinstance(value, bytes):
        digest.update(b"B" + len(value).to_bytes(8, "big") + value)
    else:
        encoded = str(value).encode("utf-8")
        digest.update(b"T" + len(encoded).to_bytes(8, "big") + encoded)


def database_snapshot(path: Path) -> dict:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        rows = connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        digest = hashlib.sha256()
        counts: dict[str, int] = {}
        schema_digest = hashlib.sha256()
        for table, schema in rows:
            quoted = '"' + table.replace('"', '""') + '"'
            schema_digest.update(table.encode("utf-8") + b"\0" + str(schema or "").encode("utf-8") + b"\0")
            count = int(connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0])
            counts[table] = count
            digest.update(table.encode("utf-8") + b"\0" + count.to_bytes(8, "big"))
            try:
                data_rows = connection.execute(f"SELECT * FROM {quoted} ORDER BY rowid")
            except sqlite3.OperationalError:
                data_rows = connection.execute(f"SELECT * FROM {quoted}")
            for row in data_rows:
                for value in row:
                    _hash_value(digest, value)
                digest.update(b"\xff")
        return {
            "integrity": integrity,
            "tables": len(rows),
            "rows": sum(counts.values()),
            "tableCounts": counts,
            "schemaSha256": schema_digest.hexdigest(),
            "logicalSha256": digest.hexdigest(),
        }
    finally:
        connection.close()


def service_port_open(host: str, port: int) -> bool:
    if port <= 0:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(0.5)
        return client.connect_ex((host, port)) == 0


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def run_restore_drill(
    db_path: Path,
    backup_dir: Path,
    *,
    apply_live_swap: bool,
    confirm_path: str = "",
    health_host: str = "127.0.0.1",
    health_port: int = 8000,
) -> dict:
    started = time.perf_counter()
    db_path = db_path.expanduser().resolve()
    backup_dir = backup_dir.expanduser().resolve()
    if not db_path.is_file():
        raise RuntimeError(f"복원 대상 DB를 찾을 수 없습니다: {db_path}")
    if apply_live_swap and confirm_path != str(db_path):
        raise RuntimeError("--confirm-path에 복원 대상 DB의 절대경로를 정확히 입력해야 합니다.")
    if apply_live_swap and service_port_open(health_host, health_port):
        raise RuntimeError(f"{health_host}:{health_port} 서비스가 실행 중입니다. 안전한 교체를 위해 먼저 중지해야 합니다.")

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_dir / f"{db_path.stem}-online-backup-{stamp}.sqlite3"
    staged_path = db_path.parent / f".{db_path.name}.restore-{stamp}.tmp"
    displaced_path = backup_dir / f"{db_path.stem}-displaced-original-{stamp}.sqlite3"
    manifest_path = backup_dir / f"{db_path.stem}-restore-drill-{stamp}.json"

    source = sqlite3.connect(db_path)
    try:
        source.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        destination = sqlite3.connect(backup_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()

    before = database_snapshot(db_path)
    backup = database_snapshot(backup_path)
    if before["integrity"] != "ok" or backup["integrity"] != "ok":
        raise RuntimeError("원본 또는 온라인 백업의 SQLite 무결성 검사가 실패했습니다.")
    if before["logicalSha256"] != backup["logicalSha256"]:
        raise RuntimeError("온라인 백업의 논리 데이터 지문이 원본과 일치하지 않습니다.")

    result = {
        "contractVersion": "sqlite-live-restore-drill/1.0",
        "status": "backup-validated",
        "target": str(db_path),
        "backup": str(backup_path),
        "displacedOriginal": None,
        "manifest": str(manifest_path),
        "startedAt": utc_now(),
        "before": before,
        "backupSnapshot": backup,
        "backupFileSha256": file_sha256(backup_path),
        "applied": False,
        "rpoSeconds": 0,
    }

    if apply_live_swap:
        shutil.copy2(backup_path, staged_path)
        if file_sha256(staged_path) != result["backupFileSha256"]:
            raise RuntimeError("복원 staging 파일의 SHA-256이 백업과 일치하지 않습니다.")
        sidecars = []
        try:
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(db_path) + suffix)
                if sidecar.exists():
                    preserved = backup_dir / f"{db_path.name}{suffix}.{stamp}"
                    os.replace(sidecar, preserved)
                    sidecars.append({"source": str(sidecar), "preserved": str(preserved)})
            os.replace(db_path, displaced_path)
            os.replace(staged_path, db_path)
            _fsync_directory(db_path.parent)
            restored = database_snapshot(db_path)
            if restored["integrity"] != "ok" or restored["logicalSha256"] != before["logicalSha256"]:
                raise RuntimeError("교체된 DB의 무결성 또는 논리 데이터 지문이 원본과 일치하지 않습니다.")
            result.update(
                {
                    "status": "passed",
                    "applied": True,
                    "displacedOriginal": str(displaced_path),
                    "preservedSidecars": sidecars,
                    "restored": restored,
                    "restoredFileSha256": file_sha256(db_path),
                }
            )
        except Exception:
            failed_path = backup_dir / f"{db_path.stem}-failed-restore-{stamp}.sqlite3"
            if db_path.exists() and displaced_path.exists():
                os.replace(db_path, failed_path)
                os.replace(displaced_path, db_path)
                for item in sidecars:
                    preserved = Path(item["preserved"])
                    if preserved.exists():
                        os.replace(preserved, Path(item["source"]))
                _fsync_directory(db_path.parent)
            raise
        finally:
            if staged_path.exists():
                staged_path.unlink()

    result["completedAt"] = utc_now()
    result["elapsedMilliseconds"] = round((time.perf_counter() - started) * 1000, 2)
    manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--backup-dir", required=True, type=Path)
    parser.add_argument("--apply-live-swap", action="store_true")
    parser.add_argument("--confirm-path", default="")
    parser.add_argument("--health-host", default="127.0.0.1")
    parser.add_argument("--health-port", type=int, default=8000)
    args = parser.parse_args()
    try:
        result = run_restore_drill(
            args.db,
            args.backup_dir,
            apply_live_swap=args.apply_live_swap,
            confirm_path=args.confirm_path,
            health_host=args.health_host,
            health_port=args.health_port,
        )
    except Exception as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
