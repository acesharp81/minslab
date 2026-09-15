from dataclasses import replace
from pathlib import Path
import sqlite3
import tarfile

from app.config import get_settings
from scripts.backup_data import create_backup


def test_portable_backup_contains_db_data_and_no_secrets(tmp_path: Path):
    data = tmp_path / "data"
    settings = replace(
        get_settings(), project_root=tmp_path, data_dir=data,
        raw_dir=data / "raw", parsed_dir=data / "parsed",
        reports_dir=data / "reports", logs_dir=data / "logs",
        database_url=f"sqlite:///{data / 'cache.db'}",
    )
    settings.ensure_directories()
    with sqlite3.connect(data / "cache.db") as db:
        db.execute("create table sample (value text)")
        db.execute("insert into sample values ('safe')")
    (settings.raw_dir / "public.pdf").write_bytes(b"public")
    (settings.parsed_dir / "public.txt").write_text("parsed", encoding="utf-8")
    (settings.reports_dir / "daily.md").write_text("report", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=never-copy", encoding="utf-8")

    result = create_backup(settings, tmp_path / "backups")

    assert Path(result["archive"]).is_file()
    assert Path(result["checksum_file"]).read_text(encoding="utf-8").startswith(result["sha256"])
    with tarfile.open(result["archive"], "r:gz") as archive:
        names = archive.getnames()
        assert any(name.endswith("/database/cache.db") for name in names)
        assert any(name.endswith("/data/raw/public.pdf") for name in names)
        assert not any(name.endswith("/.env") for name in names)
