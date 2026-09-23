from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import AuditLog
from app.routers import reports


def test_statistics_cache_ignores_unrelated_audit_logs_and_refreshes_stale_data(
    monkeypatch,
):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    calls = []
    scheduled = []
    monkeypatch.setattr(
        reports,
        "build_statistics",
        lambda _db, period: calls.append(period) or {"period": period},
    )
    monkeypatch.setattr(
        reports,
        "_schedule_statistics_refresh",
        lambda period: scheduled.append(period),
    )
    reports._statistics_cache.clear()

    with Session(engine) as db:
        first = reports._cached_statistics(db, "30d")
        db.add(AuditLog(event_type="rule_filter"))
        db.commit()
        second = reports._cached_statistics(db, "30d")
        db.add(AuditLog(event_type="action_updated"))
        db.commit()
        stale = reports._cached_statistics(db, "30d")

    assert first is second is stale
    assert calls == ["30d"]
    assert scheduled == ["30d"]
    reports._statistics_cache.clear()
