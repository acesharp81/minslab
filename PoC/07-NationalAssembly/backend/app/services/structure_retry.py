"""Bounded recovery for transient structure failures; no network or database I/O."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

MAX_ATTEMPTS = 9
RETRY_COOLDOWN = timedelta(minutes=30)
_TRANSIENT = {'ConnectionError', 'ConnectError', 'ReadTimeout', 'ConnectTimeout',
              'TimeoutError', 'RemoteProtocolError', 'HTTPError:HTTP_429',
              'HTTPError:HTTP_500', 'HTTPError:HTTP_502', 'HTTPError:HTTP_503',
              'HTTPError:HTTP_504'}


def retry_allowance(history: list[dict[str, Any]], *, now: datetime | None = None) -> int:
    """Initial three attempts, then at most two cooled-down transient retry rounds."""
    if any(h['status'] == 'READY' for h in history):
        return 0
    attempts = [h for h in history if h['request'].get('schema_revision') == 2]
    count = len(attempts)
    if count < 3:
        return 3 - count
    if count >= MAX_ATTEMPTS:
        return 0
    latest = max(attempts, key=lambda h: h['attempt'])
    if latest.get('error') not in _TRANSIENT:
        return 0
    created = latest.get('created_at')
    if not isinstance(created, datetime):
        return 0
    current = now or datetime.now(timezone.utc)
    if current - created < RETRY_COOLDOWN:
        return 0
    return min(3, MAX_ATTEMPTS - count)


def failed_batch_status(history: list[dict[str, Any]], *, now: datetime | None = None) -> str | None:
    """Successful later attempts supersede failures without deleting their history."""
    indices = {h['index'] for h in history if h['index'] < 100000}
    failed = [[h for h in history if h['index'] == i] for i in indices
              if not any(h['index'] == i and h['status'] == 'READY' for h in history)]
    if not failed:
        return None
    return 'RETRY_PENDING' if any(retry_allowance(batch, now=now) for batch in failed) else 'REVIEW_REQUIRED'
