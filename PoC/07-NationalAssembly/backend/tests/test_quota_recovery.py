from datetime import datetime, timedelta, timezone
from uuid import uuid4

from test_shared_budget import ledger
from app.ingestion import summary_worker, live_discussion_worker


def test_old_ended_budget_work_resumes_through_summary_and_classification(ledger):
    connect,_ = ledger
    bid=uuid4();now=datetime.now(timezone.utc)
    with connect() as c:
        c.execute('CREATE TABLE live_broadcasts(id uuid,lifecycle_status text,institution text,source_system text,committee_name text,ended_at timestamptz,detected_at timestamptz)')
        c.execute('CREATE TABLE watch_sessions(id uuid,broadcast_id uuid)')
        c.execute('CREATE TABLE watch_topic_episodes(session_id uuid,status text)')
        c.execute('CREATE TABLE transcript_utterance_summary_failures(broadcast_id uuid,content_hash text,prompt_version text,last_error text,retry_after timestamptz,updated_at timestamptz)')
        c.execute('CREATE TABLE transcript_utterance_summaries(broadcast_id uuid,content_hash text,prompt_version text)')
        c.execute('CREATE TABLE live_discussion_classifications(broadcast_id uuid,profile text,state jsonb,created_at timestamptz)')
        c.execute('INSERT INTO live_broadcasts VALUES(%s,%s,%s,%s,%s,%s,%s)',
                  (bid,'ENDED','LEGISLATURE','assembly.webcast.go.kr','예산결산특별위원회',now-timedelta(days=1),now-timedelta(days=2)))
        c.execute('INSERT INTO transcript_utterance_summary_failures VALUES(%s,%s,%s,%s,%s,%s)',
                  (bid,'pending','current','BUDGET_WAIT',now+timedelta(hours=1),now))
        summary_sql=next(s for s in summary_worker.process_available.__code__.co_consts if isinstance(s,str) and 'AS watched' in s)
        args=(['예산결산특별위원회'],)
        assert c.execute(summary_sql,args).fetchall()==[]  # Before reset.
        c.execute('UPDATE transcript_utterance_summary_failures SET retry_after=%s',(now-timedelta(seconds=1),))
        assert c.execute(summary_sql,args).fetchone()[0]==bid  # Older than 1h still resumes.
        c.execute('INSERT INTO transcript_utterance_summaries VALUES(%s,%s,%s)',(bid,'pending','current'))
        assert c.execute(summary_sql,args).fetchall()==[]  # Completed summaries not regenerated.
        recovery_sql=next(s for s in live_discussion_worker.process_available.__code__.co_consts if isinstance(s,str) and 'SELECT b.id' in s)
        args=(['예산결산특별위원회'],[])
        assert c.execute(recovery_sql,args).fetchone()[0]==bid
        live_discussion_worker._clear_resumed(c,bid,[{'utterance_id':'u','content_hash':'pending'}],
            {'assignments':{'u':{'content_hash':'pending'}}})
        assert c.execute(recovery_sql,args).fetchall()==[]
