from __future__ import annotations

from pathlib import Path

from ..config import get_settings
from .connection import connect


MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def apply_migrations(database_url: str) -> list[str]:
    applied: list[str] = []
    with connect(database_url) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.stem
            exists = connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version = %s", (version,)
            ).fetchone()
            if exists:
                continue
            connection.execute(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)", (version,)
            )
            applied.append(version)
    return applied


if __name__ == "__main__":
    versions = apply_migrations(get_settings().database_url)
    print({"applied": versions, "count": len(versions)})
