"""Polling parity using isolated temporary PostgreSQL tables; no business writes."""
import os
import pytest
import psycopg
from app.ingestion.watch_worker import has_pending_revisions

@pytest.mark.parametrize('cursors,checkpoint,expected', [
    ([],0,False),([2,9],9,False),([2,9],2,True),([2,9],None,False),
    ([2,9],20,False),([2,9,25],9,True),([],None,False),
])
def test_pending_matches_existing_semantics(cursors,checkpoint,expected):
    dsn=os.environ.get('SHARED_TEST_DATABASE_URL')
    if not dsn:pytest.skip('explicit test DB connection required')
    with psycopg.connect(dsn) as c:
        c.execute('CREATE TEMP TABLE transcript_segment_revisions(event_cursor bigint PRIMARY KEY)')
        c.execute('CREATE TEMP TABLE watch_worker_state(worker_name text PRIMARY KEY,event_cursor bigint)')
        for cursor in cursors:c.execute('INSERT INTO transcript_segment_revisions VALUES(%s)',(cursor,))
        if checkpoint is not None:
            c.execute("INSERT INTO watch_worker_state VALUES('watch-alerts',%s)",(checkpoint,))
        old=c.execute("SELECT EXISTS (SELECT 1 FROM transcript_segment_revisions WHERE event_cursor > (SELECT event_cursor FROM watch_worker_state WHERE worker_name='watch-alerts'))").fetchone()[0]
        assert has_pending_revisions(c) == old == expected
