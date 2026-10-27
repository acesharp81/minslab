"""Retry timing, independent of databases and model calls."""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from zoneinfo import ZoneInfo


def near_scheduled_start(snapshot: dict[str, Any], now: datetime) -> bool:
    """Reserve the half hour before/after a published meeting start for live work."""
    local = now.astimezone(ZoneInfo('Asia/Seoul'))
    for item in snapshot.get('items', []):
        day = str(item.get('scheduled_date'))
        if not item.get('is_target_committee') or day != local.date().isoformat():
            continue
        try:
            start = datetime.fromisoformat(day + 'T' + str(item['start_time'])).replace(tzinfo=local.tzinfo)
        except (KeyError, TypeError, ValueError):
            continue
        if start - timedelta(minutes=30) <= local < start + timedelta(minutes=30):
            return True
    return False


def transient_delay(exc: Exception, now: datetime | None = None) -> float | None:
    response = getattr(exc, 'response', None)
    status = getattr(response, 'status_code', None)
    if status not in {408, 429, 500, 502, 503, 504} and type(exc).__name__ not in {
        'ReadTimeout', 'ConnectTimeout', 'ConnectError', 'ConnectionError', 'TimeoutError',
    }:
        return None
    value = getattr(response, 'headers', {}).get('Retry-After', '')
    try:
        return max(6.0, float(value))
    except (TypeError, ValueError):
        try:
            return max(6.0, (parsedate_to_datetime(value) - (now or datetime.now(timezone.utc))).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 15.0


def next_run(result: dict[str, Any], now: datetime) -> tuple[str, datetime]:
    """UTC midnight is 09:00 Asia/Seoul. Never retry a daily cap before reset."""
    now = now.astimezone(timezone.utc)
    state = result.get('status')
    batches = result.get('batches', [])
    if state in {'COMPLETE', 'NO_ISSUES'}:
        return 'COMPLETE', now
    if state == 'BUDGET_DEFERRED' or any(b.get('status') == 'BUDGET_DEFERRED' for b in batches):
        return 'WAITING_DAILY_LIMIT', (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    if state == 'REVIEW_REQUIRED' or any(b.get('status') == 'REVIEW_REQUIRED' for b in batches):
        return 'REVIEW_REQUIRED', now
    if any(b.get('status') in {'RETRY_DEFERRED', 'NO_PROVIDER'} for b in batches) or state in {'FAILED', 'NO_PROVIDER'}:
        seconds = max([1800] + [b.get('retry_after_seconds', 0) for b in batches])
        return 'RETRY_WAIT', now + timedelta(seconds=seconds)
    return 'PENDING', now + timedelta(seconds=60)
