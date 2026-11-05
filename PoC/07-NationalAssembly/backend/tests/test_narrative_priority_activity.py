"""Freshness checks run against an isolated schema, with no model requests."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from uuid import uuid4
from test_shared_budget import ledger
from app.ingestion import narrative_jobs as jobs


def test_priority_requires_recent_source_activity_and_keeps_meeting_lifecycle(ledger,monkeypatch):
    connect,_=ledger;now=datetime.now(timezone.utc);bid=uuid4();old=now-timedelta(hours=7)
    with connect() as c:
        c.execute("CREATE TABLE live_broadcasts(id uuid,source_system text,lifecycle_status text,last_caption_received_at timestamptz,last_seen_at timestamptz,detected_at timestamptz,ended_at timestamptz,updated_at timestamptz)")
        c.execute("INSERT INTO live_broadcasts VALUES(%s,'assembly.webcast.go.kr','LIVE',%s,%s,%s,NULL,%s)",(bid,old,old,old,now))
    monkeypatch.setattr(jobs,'connect',lambda _:connect())
    monkeypatch.setattr(jobs,'get_settings',lambda:SimpleNamespace(database_url='fixture'))
    monkeypatch.setattr(jobs,'ScheduleRepository',lambda c:SimpleNamespace(list_schedule_for_date=lambda d:[]))
    assert jobs.background_defer_reason(now=now) is None
    for field in ['last_caption_received_at','last_seen_at','detected_at']:
        # Fields are fixed test names, never external input.
        with connect() as c:c.execute(f'UPDATE live_broadcasts SET {field}=%s',(now-timedelta(minutes=2),))
        assert jobs.background_defer_reason(now=now)=='LIVE_OR_RECENT_MEETING'
        with connect() as c:c.execute(f'UPDATE live_broadcasts SET {field}=%s',(old,))
        assert jobs.background_defer_reason(now=now) is None  # Priority expires again.
    with connect() as c:c.execute('UPDATE live_broadcasts SET last_caption_received_at=%s',(now-timedelta(minutes=15),))
    assert jobs.background_defer_reason(now=now)=='LIVE_OR_RECENT_MEETING'
    with connect() as c:c.execute('UPDATE live_broadcasts SET last_caption_received_at=%s',(now-timedelta(minutes=15,microseconds=1),))
    assert jobs.background_defer_reason(now=now) is None
    with connect() as c:c.execute('UPDATE live_broadcasts SET last_caption_received_at=NULL,last_seen_at=NULL,detected_at=NULL')
    assert jobs.background_defer_reason(now=now) is None
    with connect() as c:
        assert c.execute('SELECT lifecycle_status FROM live_broadcasts').fetchone()[0]=='LIVE'
        c.execute("UPDATE live_broadcasts SET lifecycle_status='ENDED',ended_at=%s",(now-timedelta(minutes=3),))
    assert jobs.background_defer_reason(now=now)=='LIVE_OR_RECENT_MEETING'
    with connect() as c:c.execute('UPDATE live_broadcasts SET ended_at=%s',(old,))
    assert jobs.background_defer_reason(now=now) is None
