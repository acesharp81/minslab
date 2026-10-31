"""HTTP admission to the existing shared ledger; durable, idempotent settlements."""
import json
import os
import httpx
from .ai_collection_store import BudgetExceeded


def required():
    return os.environ.get('POC10_SHARED_BUDGET_REQUIRED', 'true').lower() != 'false'


def request(action, payload=None):
    url=os.environ.get('USAGE_GATEWAY_URL','').rstrip('/')
    key=os.environ.get('USAGE_METER_TOKEN','')
    if not url or not key: raise BudgetExceeded('공통 예산 연결 설정 필요 · 모델 호출 중지')
    try:
        with httpx.Client(timeout=5,trust_env=False) as client:
            headers={'x-minslab-meter-token':key}
            r=client.get(url+'/internal/budget/status',headers=headers) if action=='status' else client.post(url+'/internal/budget/'+action,headers=headers,json=payload)
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError,ValueError):
        raise BudgetExceeded('공통 예산 잔여량 부족 또는 연결 확인 필요 · 모델 호출 중지') from None


def status():
    try: return request('status')
    except BudgetExceeded as error: return {'models':[],'error':str(error)}


def flush(store):
    with store.db() as c: rows=c.execute('SELECT event_id,payload FROM shared_settlements WHERE synced=0').fetchall()
    for row in rows:
        try: request('settle',json.loads(row['payload']))
        except BudgetExceeded: return False
        with store.db(True) as c: c.execute('UPDATE shared_settlements SET synced=1 WHERE event_id=?',(row['event_id'],))
    return True


def reserve(store, cid, model, inp, out):
    if not required(): return
    if not flush(store): raise BudgetExceeded('공통 사용량 미정산 · 동기화 후 재실행')
    request('reserve',dict(event_id='poc10-'+cid,project='poc10',model=model,input_bound=inp,output_bound=out))


def settle(store,cid,inp=None,out=None,cost=None,rejected=False):
    if not required(): return
    event='poc10-'+cid
    payload=dict(event_id=event,input_tokens=inp,output_tokens=out,cost_usd=cost,rejected=rejected)
    # First settlement wins: a later JSON parsing error must not overwrite actual usage.
    with store.db(True) as c:
        c.execute('INSERT OR IGNORE INTO shared_settlements VALUES (?,?,0)',(event,json.dumps(payload)))
    flush(store)
