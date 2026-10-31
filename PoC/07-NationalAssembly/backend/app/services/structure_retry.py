"""Bounded recovery for transient structure failures; no network or database I/O."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

MAX_ATTEMPTS = 9
RETRY_COOLDOWN = timedelta(minutes=30)
_TRANSIENT = {'ConnectionError', 'ConnectError', 'ReadTimeout', 'ConnectTimeout',
              'TimeoutError', 'RemoteProtocolError', 'HTTPError:HTTP_429',
              'HTTPError:HTTP_500', 'HTTPError:HTTP_502', 'HTTPError:HTTP_503',
              'HTTPError:HTTP_504', 'AuxiliaryUnavailable', 'DAILY_TOKEN_LIMIT',
              'AUXILIARY_RATE_WAIT', 'AUXILIARY_DAILY_LIMIT',
              'REVIEW_TOPIC_SOURCE_MISMATCH'}


def retry_allowance(history: list[dict[str, Any]], *, now: datetime | None = None, round_size: int = 3) -> int:
    """Initial three attempts, then at most two cooled-down transient retry rounds."""
    if any(h['status'] == 'READY' for h in history):
        return 0
    attempts = [h for h in history if h['request'].get('schema_revision') == 2]
    count = len(attempts)
    size = min(5, max(3, round_size))
    if count < size:
        return size - count
    if count >= MAX_ATTEMPTS:
        return 0
    latest = max(attempts, key=lambda h: (h.get('created_at') or datetime.min.replace(tzinfo=timezone.utc), h['attempt']))
    if latest.get('error') not in _TRANSIENT:
        return 0
    created = latest.get('created_at')
    if not isinstance(created, datetime):
        return 0
    current = now or datetime.now(timezone.utc)
    if current - created < RETRY_COOLDOWN:
        return 0
    return min(size, MAX_ATTEMPTS - count)


def failed_batch_status(history: list[dict[str, Any]], *, now: datetime | None = None) -> str | None:
    """Successful later attempts supersede failures without deleting their history."""
    indices = {h['index'] for h in history if h['index'] < 100000}
    failed = [[h for h in history if h['index'] == i] for i in indices
              if not any(h['index'] == i and h['status'] == 'READY' for h in history)]
    if not failed:
        return None
    return 'RETRY_PENDING' if any(retry_allowance(batch, now=now) for batch in failed) else 'REVIEW_REQUIRED'


def retry_pool(pool: list[Any], histories: list[list[dict[str, Any]]]) -> list[Any]:
    """One bounded provider round; cooled rounds restart at the preferred model."""
    histories = [review_retry_history(h) for h in histories]
    if not pool:
        return []
    if not min((retry_allowance(h, round_size=len(pool)) for h in histories), default=1):
        return []
    latest = max((h.get('created_at') for rows in histories for h in rows
                  if isinstance(h.get('created_at'), datetime)), default=None)
    cooled = latest is not None and datetime.now(timezone.utc) - latest >= RETRY_COOLDOWN
    offset = 0 if cooled else max((len(h) for h in histories), default=0) % len(pool)
    remaining = MAX_ATTEMPTS - max((len(h) for h in histories), default=0)
    return (pool[offset:] + pool[:offset])[:max(0, remaining)]


def review_retry_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Review failures have a daily retry allowance; successful evidence stays cached."""
    today = datetime.now(timezone.utc).date()
    return [h for h in history if h['status'] == 'READY'
            or not isinstance(h.get('created_at'), datetime)
            or h['created_at'].astimezone(timezone.utc).date() == today]
