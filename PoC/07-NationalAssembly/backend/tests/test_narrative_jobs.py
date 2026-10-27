from contextlib import contextmanager
from types import SimpleNamespace

from app.ingestion import narrative_jobs as jobs, structured_narrative_worker


def test_persist_daily_deferral_release_lock_and_never_scan_other_reports(monkeypatch):
    queries, updates, called = [], [], []
    class Connection:
        def execute(self, query, params=None):
            queries.append(query)
            if 'pg_try_advisory_lock' in query:
                value = (True,)
            elif query.startswith('SELECT broadcast_id'):
                assert "next_attempt_at<=now()" in query
                assert "FROM structured_narrative_jobs" in query
                assert "ORDER BY created_at,next_attempt_at" in query
                value = ('authorized-report',)
            else:
                value = None
            if query.startswith('UPDATE'):
                updates.append(params)
            return SimpleNamespace(fetchone=lambda: value)
    @contextmanager
    def connect(_):
        yield Connection()
    def process(bid, batch_limit):
        called.append(bid)
        return {'status': 'PENDING', 'batches': [{'status': 'BUDGET_DEFERRED'}]}
    monkeypatch.setattr(jobs, 'connect', connect)
    monkeypatch.setattr(jobs, 'background_defer_reason', lambda: None)
    monkeypatch.setattr(jobs, 'get_settings', lambda: SimpleNamespace(database_url='fixture'))
    monkeypatch.setattr(structured_narrative_worker, 'process_one', process)
    result = jobs.process_due()
    assert called == ['authorized-report']
    assert result[0]['job_status'] == updates[0][0] == 'WAITING_DAILY_LIMIT'
    assert updates[0][1].hour == updates[0][1].minute == 0
    assert 'pg_advisory_unlock' in queries[-1]


def test_no_due_job_never_calls_models(monkeypatch):
    @contextmanager
    def connect(_):
        yield SimpleNamespace(execute=lambda q, p=None: SimpleNamespace(
            fetchone=lambda: (True,) if 'pg_try_advisory_lock' in q else None))
    monkeypatch.setattr(jobs, 'connect', connect)
    monkeypatch.setattr(jobs, 'background_defer_reason', lambda: None)
    monkeypatch.setattr(jobs, 'get_settings', lambda: SimpleNamespace(database_url='fixture'))
    monkeypatch.setattr(structured_narrative_worker, 'process_one', lambda *a, **k: (_ for _ in ()).throw(AssertionError('must not run')))
    assert jobs.process_due() == []


def test_live_priority_does_not_claim_or_reset_pending_repairs(monkeypatch):
    monkeypatch.setattr(jobs, 'get_settings', lambda: SimpleNamespace(database_url='fixture'))
    monkeypatch.setattr(jobs, 'background_defer_reason', lambda: 'LIVE_OR_RECENT_MEETING')
    monkeypatch.setattr(jobs, 'connect', lambda *a: (_ for _ in ()).throw(AssertionError('must not claim jobs')))
    assert jobs.process_due() == [{'status': 'LIVE_PRIORITY', 'reason': 'LIVE_OR_RECENT_MEETING'}]


def test_scheduled_priority_reads_database_without_worker_file_mount(monkeypatch):
    from datetime import datetime, date, time, timezone
    @contextmanager
    def connect(_):
        yield SimpleNamespace(execute=lambda q: SimpleNamespace(fetchone=lambda: (False,)))
    monkeypatch.setattr(jobs, 'connect', connect)
    monkeypatch.setattr(jobs, 'get_settings', lambda: SimpleNamespace(database_url='fixture'))
    monkeypatch.setattr(jobs, 'ScheduleRepository', lambda c: SimpleNamespace(list_schedule_for_date=lambda d: [
        {'is_target_committee': True, 'scheduled_date': date(2026,10,26), 'start_time': time(10)}]))
    assert jobs.background_defer_reason(now=datetime(2026,10,26,0,30,tzinfo=timezone.utc)) == 'UPCOMING_MEETING'
    assert jobs.background_defer_reason(now=datetime(2026,10,26,0,29,tzinfo=timezone.utc)) is None
