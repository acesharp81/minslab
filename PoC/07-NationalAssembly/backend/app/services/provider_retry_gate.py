"""Capacity failures are provider/input scoped, not answer-quality failures."""
from datetime import datetime, timedelta, timezone
from typing import Any


def blocked_provider(client: Any, history: list[dict], now: datetime | None = None) -> str | None:
    now = now or datetime.now(timezone.utc)
    for row in reversed(history):
        usage = row.get('usage') or {}
        if usage.get('provider') != client.provider or usage.get('attempted_model', usage.get('model')) != client.model:
            continue
        error = row.get('error')
        if error == 'AUXILIARY_INPUT_TOO_LARGE':
            return error  # A different request/model has its own history.
        created = row.get('created_at')
        if not isinstance(created, datetime):
            continue
        if error in {'DAILY_TOKEN_LIMIT', 'AUXILIARY_DAILY_LIMIT'}:
            if now < (created.astimezone(timezone.utc)+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0):
                return error
        if error in {'AUXILIARY_RATE_WAIT', 'HTTPError:HTTP_429'}:
            seconds = max(1, float(usage.get('retry_after_seconds') or 60))
            if now < created+timedelta(seconds=seconds):
                return error
        return None
    return None
