"""Korean off-hours policy for automatic bulk work; manual work stays explicit."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')
_scheduled_bulk = ContextVar('home_scheduled_bulk', default=False)

class NightWindowClosed(ValueError):
    pass

def night_open(instant=None):
    instant = instant or datetime.now(timezone.utc)
    return 1 <= instant.astimezone(KST).hour < 5

def next_night(instant=None):
    instant = instant or datetime.now(timezone.utc)
    local = instant.astimezone(KST)
    start = local.replace(hour=1, minute=0, second=0, microsecond=0)
    if night_open(instant):return instant
    if local >= start:start += timedelta(days=1)
    return start.astimezone(timezone.utc)

def scheduled_bulk():
    return _scheduled_bulk.get()

def check_window(enabled=None):
    if (scheduled_bulk() if enabled is None else enabled) and not night_open():
        raise NightWindowClosed('야간 일괄 처리 시간 종료 · 다음 01:00에 이어서 처리')

@contextmanager
def bulk_work(enabled=True):
    token = _scheduled_bulk.set(enabled)
    try:
        check_window()
        yield
    finally:_scheduled_bulk.reset(token)
