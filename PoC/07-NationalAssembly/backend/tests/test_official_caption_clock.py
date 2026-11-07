"""Isolated database scenarios; never modify production broadcast or usage rows."""
import os
import uuid
from pathlib import Path
import pytest
import psycopg
from psycopg import sql
from app.db.live_repository import LiveRepository

@pytest.fixture
def repo():
    dsn=os.environ.get('SHARED_TEST_DATABASE_URL')
    if not dsn:pytest.skip('Explicit PostgreSQL test connection required')
    dsn=dsn.replace('postgresql+psycopg://','postgresql://')
    schema='test_caption_'+uuid.uuid4().hex
    with psycopg.connect(dsn,autocommit=True) as c:
        c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    try:
        with psycopg.connect(dsn,options=f'-c search_path={schema},public') as c:
            c.execute('CREATE TABLE live_broadcasts (LIKE public.live_broadcasts INCLUDING DEFAULTS)')
            c.execute('ALTER TABLE live_broadcasts ADD COLUMN IF NOT EXISTS last_official_caption_received_at timestamptz')
            c.execute('CREATE TABLE transcript_source_sessions (LIKE public.transcript_source_sessions INCLUDING DEFAULTS)')
            # Copy one valid source row solely into the isolated test schema.
            c.execute("INSERT INTO live_broadcasts SELECT * FROM public.live_broadcasts LIMIT 0") if False else None
            cols=[r[0] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='live_broadcasts' ORDER BY ordinal_position")]
            c.execute(sql.SQL('INSERT INTO live_broadcasts ({0}) SELECT {0} FROM public.live_broadcasts WHERE institution=\'LEGISLATURE\' LIMIT 1').format(sql.SQL(',').join(map(sql.Identifier,cols))))
            bid=c.execute('SELECT id FROM live_broadcasts').fetchone()[0]
            c.execute("UPDATE live_broadcasts SET lifecycle_status='LIVE',active_transcript_source='AI_STT',official_caption_state='RECOVERING',stt_fallback_status='CAPTURING',media_stream_url='https://example.test/audio',last_caption_received_at=now(),last_official_caption_received_at=now()-interval '60 seconds',official_caption_recovery_started_at=now()-interval '5 minutes'")
            yield LiveRepository(c),bid
    finally:
        with psycopg.connect(dsn,autocommit=True) as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

def test_stt_activity_does_not_mask_official_timeout(repo):
    r,bid=repo
    assert r.mark_official_caption_timeout(bid)
    assert r.connection.execute('SELECT official_caption_state,official_caption_recovery_started_at FROM live_broadcasts').fetchone()==('DEGRADED',None)

def test_reconnect_after_gap_restarts_stable_window(repo):
    r,bid=repo
    assert r.mark_official_caption_received(bid)=='RECOVERING'
    assert r.connection.execute("SELECT active_transcript_source,official_caption_recovery_started_at=now() FROM live_broadcasts").fetchone()==('AI_STT',True)

def test_continuous_feed_stops_stt_once_with_audit_event(repo):
    r,bid=repo
    r.connection.execute("UPDATE live_broadcasts SET last_official_caption_received_at=now()-interval '5 seconds'")
    assert r.mark_official_caption_received(bid)=='ACTIVE'
    assert r.connection.execute('SELECT active_transcript_source,stt_fallback_status FROM live_broadcasts').fetchone()==('OFFICIAL_CAPTION','STOP_REQUESTED')
    r.mark_official_caption_received(bid)
    assert r.connection.execute("SELECT count(*) FROM transcript_source_sessions WHERE transition='STOP'").fetchone()[0]==1


def test_live_endpoint_change_releases_old_socket_for_reclaim(repo):
    r,bid=repo
    r.connection.execute("UPDATE live_broadcasts SET caption_websocket_url='wss://smi-dw.webcast.go.kr/10'")
    assert r.caption_url_changed(bid,'wss://example.test/ai/hls')
    assert not r.caption_url_changed(bid,'wss://smi-dw.webcast.go.kr/10')
    r.connection.execute("UPDATE live_broadcasts SET lifecycle_status='ENDED'")
    assert not r.caption_url_changed(bid,'wss://example.test/ai/hls')
