"""Additional per-evaluation cap; the normal PoC7 ledger remains authoritative."""
import json,sqlite3,time
from contextlib import contextmanager


def capped_usage(base,db_path,limits,rates,budget_error=RuntimeError,wait_seconds=0):
    class CappedUsage(base):
        @contextmanager
        def db(self):
            c=sqlite3.connect(db_path,timeout=30)
            try:
                with c:
                    c.execute('CREATE TABLE IF NOT EXISTS reservations(id TEXT PRIMARY KEY, model TEXT, pool TEXT, amount REAL, state TEXT, event TEXT)')
                    yield c
            finally:c.close()
        def reserve(self,eid,model,ib,ob):
            pool='openai-shared' if model in ('gpt-6.1-sol','gpt-6-astra') else 'openrouter-free' if model.endswith(':free') else model
            if pool not in limits:raise budget_error('평가 승인 범위에 없는 모델')
            amount=(ib*rates[model][0]*2.5+ob*rates[model][1])/1e6 if pool=='openai-shared' else 1 if pool=='openrouter-free' else ib+ob
            deadline=time.monotonic()+wait_seconds
            while True:
                with self.db() as c:
                    c.execute('BEGIN IMMEDIATE')
                    used,pending=c.execute("SELECT coalesce(sum(amount),0),coalesce(sum(case when state='RESERVED' then amount else 0 end),0) FROM reservations WHERE pool=?",(pool,)).fetchone()
                    cap=limits[pool]
                    if cap is None or used+amount<=cap:
                        c.execute('INSERT INTO reservations VALUES(?,?,?,?,?,?)',(eid,model,pool,amount,'RESERVED','{}'));break
                    # Concurrent conservative reservations may settle lower;
                    # wait without widening the cap or sending an extra call.
                    if not pending or used-pending+amount>cap or time.monotonic()>=deadline:
                        raise budget_error('평가 시작 시점 잔여 한도 도달: '+pool)
                time.sleep(.5)
            try:return super().reserve(eid,model,ib,ob)
            except Exception:
                with self.db() as c:c.execute("UPDATE reservations SET amount=0,state='REJECTED' WHERE id=?",(eid,))
                raise
        def record(self,event,reservation):
            with self.db() as c:
                row=c.execute('SELECT pool,amount FROM reservations WHERE id=?',(event['event_id'],)).fetchone()
                if row:
                    pool,bound=row;known=event.get('cost_usd') is not None
                    amount=event.get('cost_usd') if pool=='openai-shared' else 1 if pool=='openrouter-free' else event.get('input_tokens',0)+event.get('output_tokens',0)
                    c.execute('UPDATE reservations SET amount=?,state=?,event=? WHERE id=?',(amount if known else bound,event['status'] if known else 'UNKNOWN',json.dumps(event),event['event_id']))
            return super().record(event,reservation)
    return CappedUsage
