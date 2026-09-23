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
        # Bound SQLite connections so PoC8 cannot evict PoC7's PostgreSQL and
        # gateway cache pages under burst traffic on the shared host.
        pool_size=3,
        max_overflow=1,
        pool_timeout=30,
        pool_use_lifo=True,
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
        # This service is a read-heavy cache. Keep temporary sorts and hot
        # pages in memory while retaining WAL durability semantics.
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA cache_size=-16384")
        cursor.execute("PRAGMA mmap_size=67108864")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


class RadarSession(Session):
    pass


@event.listens_for(RadarSession, "before_flush")
def _capture_supabase_changes(session: RadarSession, _flush_context, _instances) -> None:
    if session.info.get("suppress_supabase_sync"):
        return
    session.info.setdefault("pending_supabase_upserts", set()).update(session.new)
    session.info.setdefault("pending_supabase_upserts", set()).update(session.dirty)
    session.info.setdefault("pending_supabase_deletes", set()).update(session.deleted)


@event.listens_for(RadarSession, "after_commit")
def _push_supabase_changes(session: RadarSession) -> None:
    upserts = session.info.pop("pending_supabase_upserts", set())
    deletes = session.info.pop("pending_supabase_deletes", set())
    if session.info.get("suppress_supabase_sync") or (not upserts and not deletes):
        return
    if session.info.get("defer_supabase_sync"):
        session.info.setdefault("deferred_supabase_upserts", set()).update(upserts)
        session.info.setdefault("deferred_supabase_deletes", set()).update(deletes)
        return
    from .services.supabase_store import get_supabase_store

    get_supabase_store().push_changes(list(upserts), list(deletes))


@event.listens_for(RadarSession, "after_rollback")
def _discard_supabase_changes(session: RadarSession) -> None:
    # Preserve changes from earlier successful commits in a deferred batch.
    session.info.pop("pending_supabase_upserts", None)
    session.info.pop("pending_supabase_deletes", None)


def push_deferred_supabase_changes(session: Session) -> bool:
    upserts = list(session.info.pop("deferred_supabase_upserts", set()))
    deletes = list(session.info.pop("deferred_supabase_deletes", set()))
    if not upserts and not deletes:
        return True
    from .services.supabase_store import get_supabase_store

    return get_supabase_store().push_changes(upserts, deletes)


SessionLocal = sessionmaker(bind=engine, class_=RadarSession, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from . import models  # noqa: F401

    settings.ensure_directories()
    Base.metadata.create_all(bind=engine)
    # create_all() does not add newly declared indexes to existing tables.
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            index.create(bind=engine, checkfirst=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
