from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


def psycopg_dsn(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + database_url.removeprefix("postgresql+psycopg://")
    return database_url


@contextmanager
def connect(database_url: str) -> Iterator[Any]:
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    import psycopg

    with psycopg.connect(psycopg_dsn(database_url)) as connection:
        yield connection
