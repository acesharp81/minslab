"""Durable retry queue for explicitly authorized narrative repairs only."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any

from psycopg.types.json import Jsonb

from ..config import get_settings
from ..db.connection import connect
from ..db.schedule_repository import ScheduleRepository
from ..services.narrative_retry import next_run, near_scheduled_start


def background_defer_reason(*, now: datetime | None = None) -> str | None:
    """Old report repairs yield to current live collection and fresh reports."""
    settings = get_settings()
    current = now or datetime.now(timezone.utc)
    with connect(settings.database_url) as c:
        active = c.execute("SELECT EXISTS (SELECT 1 FROM live_broadcasts "
            "WHERE source_system IN ('assembly.webcast.go.kr','ktv.go.kr') "
            "AND (lifecycle_status='LIVE' OR (lifecycle_status='ENDED' AND ended_at>=now()-interval '15 minutes')))").fetchone()[0]
        if active:
            return 'LIVE_OR_RECENT_MEETING'
        entries = ScheduleRepository(c).list_schedule_for_date(current.astimezone(ZoneInfo('Asia/Seoul')).date())
    if near_scheduled_start({'items': entries}, current):
        return 'UPCOMING_MEETING'
    return None


def enqueue(broadcast_id: Any) -> None:
    with connect(get_settings().database_url) as c:
        c.execute('INSERT INTO structured_narrative_jobs (broadcast_id) VALUES (%s) '
                  'ON CONFLICT (broadcast_id) DO NOTHING', (broadcast_id,))


def process_due(broadcast_id: Any = None, batch_limit: int = 8) -> list[dict[str, Any]]:
    from .structured_narrative_worker import process_one
    from .meeting_brief_worker import safe_brief_error_code
    url = get_settings().database_url
    reason = background_defer_reason()
    if reason:
        return [{'status': 'LIVE_PRIORITY', 'reason': reason}]
    # Session lock releases even when the worker crashes. The pending row and all
    # completed source-fingerprinted batches survive container restarts.
    with connect(url) as lease:
        if not lease.execute("SELECT pg_try_advisory_lock(hashtext('narrative-job-runner'))").fetchone()[0]:
            return []
        try:
            with connect(url) as c:
                row = c.execute("SELECT broadcast_id FROM structured_narrative_jobs "
                    "WHERE status IN ('PENDING','WAITING_DAILY_LIMIT','RETRY_WAIT') AND next_attempt_at<=now() "
                    "AND (%s::uuid IS NULL OR broadcast_id=%s::uuid) ORDER BY created_at,next_attempt_at LIMIT 1",
                    (broadcast_id, broadcast_id)).fetchone()
            if not row:
                return []
            try:
                result = process_one(row[0], batch_limit=batch_limit)
            except Exception as exc:
                result = {'status': 'FAILED', 'broadcast_id': str(row[0]), 'error': safe_brief_error_code(exc)}
            status, due = next_run(result, datetime.now(timezone.utc))
            with connect(url) as c:
                c.execute('UPDATE structured_narrative_jobs SET status=%s,next_attempt_at=%s,last_result=%s,'
                          'run_count=run_count+1,updated_at=now() WHERE broadcast_id=%s',
                          (status, due, Jsonb(result), row[0]))
            return [{**result, 'job_status': status, 'next_attempt_at': due.isoformat()}]
        finally:
            lease.execute("SELECT pg_advisory_unlock(hashtext('narrative-job-runner'))")
