from datetime import datetime,timedelta,timezone
from uuid import uuid4
from psycopg.types.json import Jsonb
from test_shared_budget import ledger
from app.ingestion import report_finalization as worker
from app.services.grouped_models import MONTHLY_CREDIT_POLICY


def test_new_monthly_route_wakes_old_daily_wait_once_and_keeps_other_backoff(ledger):
    connect,_=ledger;bid=uuid4();mid=uuid4();now=datetime.now(timezone.utc)
    query=next(q for q in worker.process_available.__code__.co_consts if isinstance(q,str) and 'SELECT b.broadcast_id' in q)
    state={'status':'DEFERRED','phase':'FINALIZING','retry_after':(now+timedelta(hours=2)).isoformat()}
    with connect() as c:
        c.execute('CREATE TABLE live_broadcasts(id uuid,lifecycle_status text)')
        c.execute('CREATE TABLE meeting_briefs(id uuid,broadcast_id uuid,provider text,generated_at timestamptz,brief jsonb)')
        c.execute("CREATE FUNCTION meeting_brief_payload(uuid,jsonb) RETURNS jsonb LANGUAGE sql AS 'SELECT $2'")
        c.execute("INSERT INTO live_broadcasts VALUES(%s,'ENDED')",(bid,))
        c.execute("INSERT INTO meeting_briefs VALUES(%s,%s,'openai',%s,%s)",(mid,bid,now,Jsonb({'finalization':state})))
        assert c.execute(query,(False,MONTHLY_CREDIT_POLICY,1)).fetchall()==[]
        assert c.execute(query,(True,MONTHLY_CREDIT_POLICY,1)).fetchone()[0]==bid
        state['monthly_credit_policy']=MONTHLY_CREDIT_POLICY
        c.execute('UPDATE meeting_briefs SET brief=%s',(Jsonb({'finalization':state}),))
        assert c.execute(query,(True,MONTHLY_CREDIT_POLICY,1)).fetchall()==[]
        state.pop('monthly_credit_policy');state['phase']='NARRATIVE'
        c.execute('UPDATE meeting_briefs SET brief=%s',(Jsonb({'finalization':state}),))
        assert c.execute(query,(True,MONTHLY_CREDIT_POLICY,1)).fetchall()==[]
        state['retry_after']=(now-timedelta(seconds=1)).isoformat()
        c.execute('UPDATE meeting_briefs SET brief=%s',(Jsonb({'finalization':state}),))
        assert c.execute(query,(True,MONTHLY_CREDIT_POLICY,1)).fetchone()[0]==bid
