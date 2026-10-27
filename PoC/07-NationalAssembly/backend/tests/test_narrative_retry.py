from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import requests

from app.services.narrative_retry import next_run, transient_delay, near_scheduled_start
from app.ingestion import structured_narrative_worker as worker


def test_daily_budget_resumes_at_next_0900_kst_even_with_partial_success():
    now = datetime(2026, 10, 26, 23, 59, 59, tzinfo=timezone.utc)
    state, due = next_run({'status': 'PENDING', 'batches': [
        {'status': 'READY'}, {'status': 'BUDGET_DEFERRED'}]}, now)
    assert state == 'WAITING_DAILY_LIMIT'
    assert due == datetime(2026, 10, 27, tzinfo=timezone.utc)
    assert due.astimezone(timezone(timedelta(hours=9))).hour == 9


def test_quota_at_midnight_waits_until_next_day_and_completion_stops():
    now = datetime(2026, 10, 26, tzinfo=timezone.utc)
    assert next_run({'status': 'BUDGET_DEFERRED'}, now)[1] == now + timedelta(days=1)
    assert next_run({'status': 'COMPLETE'}, now)[0] == 'COMPLETE'
    assert next_run({'status': 'PENDING', 'batches': [{'status': 'REVIEW_REQUIRED'}]}, now)[0] == 'REVIEW_REQUIRED'


def test_rpm_and_timeouts_retry_same_day_and_honor_retry_after():
    now = datetime(2026, 10, 26, 1, tzinfo=timezone.utc)
    exc = requests.HTTPError(response=SimpleNamespace(status_code=429, headers={'Retry-After': '4000'}))
    assert transient_delay(exc) == 4000
    state, due = next_run({'status': 'PENDING', 'batches': [
        {'status': 'RETRY_DEFERRED', 'retry_after_seconds': 4000}]}, now)
    assert state == 'RETRY_WAIT' and due == now + timedelta(seconds=4000)
    exc.response.headers = {'Retry-After': 'Mon, 26 Oct 2026 01:01:00 GMT'}
    assert transient_delay(exc, now) == 60
    assert transient_delay(requests.ReadTimeout()) == 15
    assert transient_delay(ValueError('NARRATIVE_POINT_COVERAGE')) is None
    assert transient_delay(requests.HTTPError(response=SimpleNamespace(status_code=401, headers={}))) is None


def test_nim_retries_transient_without_fallback_or_repeating_validation(monkeypatch):
    sleeps, calls = [], []
    client = SimpleNamespace(provider='nvidia', timeout_seconds=120)
    def post(*args):
        calls.append(args)
        if len(calls) == 1:
            raise requests.ReadTimeout()
        return {'fixture': True}, {}
    client._post = post
    monkeypatch.setattr(worker, 'pace_nim', lambda c: None)
    monkeypatch.setattr(worker.time, 'sleep', sleeps.append)
    assert worker.post_with_nim_retry(client, []) == ({'fixture': True}, {})
    assert len(calls) == 2 and sleeps == [15] and client.timeout_seconds == 240


def test_long_retry_after_is_deferred_without_early_request(monkeypatch):
    import pytest
    calls = []
    def post(*args):
        calls.append(args)
        raise requests.HTTPError(response=SimpleNamespace(status_code=429, headers={'Retry-After': '120'}))
    client = SimpleNamespace(provider='nvidia', timeout_seconds=120, _post=post)
    monkeypatch.setattr(worker, 'pace_nim', lambda c: None)
    with pytest.raises(requests.HTTPError) as error:
        worker.post_with_nim_retry(client, [])
    assert len(calls) == 1 and error.value.retry_after_seconds == 120


def test_pre_broadcast_window_uses_kst_and_expires_after_start_grace():
    schedule = {'items': [{'is_target_committee': True, 'scheduled_date': '2026-10-26', 'start_time': '10:00'}]}
    assert not near_scheduled_start(schedule, datetime(2026,10,26,0,29,tzinfo=timezone.utc))
    assert near_scheduled_start(schedule, datetime(2026,10,26,0,30,tzinfo=timezone.utc))
    assert near_scheduled_start(schedule, datetime(2026,10,26,1,29,tzinfo=timezone.utc))
    assert not near_scheduled_start(schedule, datetime(2026,10,26,1,30,tzinfo=timezone.utc))
    assert not near_scheduled_start(schedule, datetime(2026,10,27,0,30,tzinfo=timezone.utc))
    schedule['items'][0]['start_time'] = None
    assert not near_scheduled_start(schedule, datetime(2026,10,26,0,30,tzinfo=timezone.utc))
