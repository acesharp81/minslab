from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    import _bootstrap  # noqa: F401
except ModuleNotFoundError:  # imported as scripts.backup_data by tests/tools
    from scripts import _bootstrap  # type: ignore # noqa: F401
from sqlalchemy.engine import make_url

from app.config import Settings, get_settings
from app.services.batch_lock import exclusive_collection_lock


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_path(settings: Settings) -> Path | None:
    url = make_url(settings.database_url)
    if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
        return None
    path = Path(url.database)
    return path if path.is_absolute() else (settings.project_root / path).resolve()


def _copy_tree(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)


def create_backup(settings: Settings, output_dir: Path, *, include_logs: bool = False) -> dict:
    """Create a consistent, portable archive without copying secrets."""
    settings.ensure_directories()
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = output_dir / f"poc08-backup-{stamp}.tar.gz"

    with tempfile.TemporaryDirectory(prefix="poc08-backup-") as temporary:
        snapshot = Path(temporary) / f"poc08-backup-{stamp}"
        snapshot.mkdir()
        with exclusive_collection_lock(settings.data_dir):
            database_source = _sqlite_path(settings)
            database_included = bool(database_source and database_source.is_file())
            if database_included:
                database_dir = snapshot / "database"
                database_dir.mkdir()
                source = sqlite3.connect(f"file:{database_source}?mode=ro", uri=True)
                destination = sqlite3.connect(database_dir / "cache.db")
                try:
                    source.backup(destination)
                finally:
                    destination.close()
                    source.close()
            _copy_tree(settings.raw_dir, snapshot / "data/raw")
            _copy_tree(settings.parsed_dir, snapshot / "data/parsed")
            _copy_tree(settings.reports_dir, snapshot / "data/reports")
            if include_logs:
                _copy_tree(settings.logs_dir, snapshot / "data/logs")

        metadata = {
            "format": "poc08-portable-backup-v1",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "database_backend": settings.database_backend,
            "database_included": database_included,
            "includes": ["database/cache.db" if database_included else None,
                         "data/raw", "data/parsed", "data/reports",
                         "data/logs" if include_logs else None],
            "excludes": [".env", "API keys", "service-role key"],
            "note": "Supabase가 운영 원본인 경우 이 DB는 마지막 재조정 시점의 로컬 장애 캐시입니다.",
        }
        metadata["includes"] = [value for value in metadata["includes"] if value]
        (snapshot / "backup.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        files = []
        for path in sorted(item for item in snapshot.rglob("*") if item.is_file()):
            files.append({
                "path": path.relative_to(snapshot).as_posix(),
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            })
        (snapshot / "manifest.json").write_text(
            json.dumps({"files": files}, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(snapshot, arcname=snapshot.name)

    checksum = _sha256(archive_path)
    checksum_path = Path(f"{archive_path}.sha256")
    checksum_path.write_text(f"{checksum}  {archive_path.name}\n", encoding="utf-8")
    return {
        "archive": str(archive_path), "checksum_file": str(checksum_path),
        "sha256": checksum, "database_included": database_included,
    }


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="PoC08 DB·원문·추출문·리포트 휴대형 백업")
    parser.add_argument("--output-dir", type=Path, default=settings.project_root / "backups")
    parser.add_argument("--include-logs", action="store_true")
    args = parser.parse_args()
    print(json.dumps(create_backup(settings, args.output_dir, include_logs=args.include_logs),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
