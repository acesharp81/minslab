from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
if settings.database_url.startswith("sqlite"):
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False, "timeout": 30},
        pool_pre_ping=True,
    )
else:
    # 선택적으로 DATABASE_URL에 PostgreSQL을 지정할 때만 쓰는 직접 연결 경로다.
    engine = create_engine(
        settings.database_url,
        connect_args={"connect_timeout": 10, "application_name": "poc08_ai_common_platform_radar"},
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=5,
    )


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


class RadarSession(Session):
    pass


@event.listens_for(RadarSession, "before_flush")
def _capture_supabase_changes(session: RadarSession, _flush_context, _instances) -> None:
    if session.info.get("suppress_supabase_sync"):
        return
    session.info.setdefault("supabase_upserts", set()).update(session.new)
    session.info.setdefault("supabase_upserts", set()).update(session.dirty)
    session.info.setdefault("supabase_deletes", set()).update(session.deleted)


@event.listens_for(RadarSession, "after_commit")
def _push_supabase_changes(session: RadarSession) -> None:
    upserts = list(session.info.pop("supabase_upserts", set()))
    deletes = list(session.info.pop("supabase_deletes", set()))
    if session.info.get("suppress_supabase_sync") or (not upserts and not deletes):
        return
    from .services.supabase_store import get_supabase_store

    get_supabase_store().push_changes(upserts, deletes)


@event.listens_for(RadarSession, "after_rollback")
def _discard_supabase_changes(session: RadarSession) -> None:
    session.info.pop("supabase_upserts", None)
    session.info.pop("supabase_deletes", None)


SessionLocal = sessionmaker(bind=engine, class_=RadarSession, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from . import models  # noqa: F401

    settings.ensure_directories()
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
