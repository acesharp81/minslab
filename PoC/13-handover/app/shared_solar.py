"""PoC10/13 admission to one limited Solar key; durable settlement outbox."""
import hashlib
import json
import threading
import time
import httpx
from .store import dump,now


def fingerprint(config):
    return hashlib.sha256((config['url'].rstrip('/')+'\0'+config['key']).encode()).hexdigest()


class SharedSolar:
    def __init__(self,store,url,token,config):
        self.store,self.url,self.token=store,url.rstrip('/'),token
        self.key_fingerprint=fingerprint(config)
        self.lock=threading.Lock();self.cached=None;self.checked=0
        with store.connect(write=True) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS solar_shared_calls (
                id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, settlement TEXT,
                synced INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL)''')

    def enabled(self,config):
        return bool(self.url and self.token and config.get('key') and fingerprint(config)==self.key_fingerprint)

    def request(self,action,payload=None):
        try:
            with httpx.Client(timeout=8,trust_env=False) as client:
                headers={'x-minslab-meter-token':self.token}
                endpoint=self.url+'/internal/budget/'+action
                response=client.get(endpoint,headers=headers,params={'solar_pool':'key2'}) if payload is None else client.post(endpoint,headers=headers,json=payload)
            if not response.is_success:raise ValueError('공유 한도 부족 또는 예산 서비스 연결 확인 필요')
            return response.json()
        except (httpx.HTTPError,ValueError):
            raise ValueError('PoC10·13 Solar 공유 한도 부족 또는 연결 확인 필요 · 모델 호출 중지') from None

    def flush(self):
        # Replaying the same event is safe at the central ledger.
        for row in self.store.rows('SELECT * FROM solar_shared_calls WHERE synced=0 AND settlement IS NOT NULL'):
            self.request('settle',json.loads(row['settlement']))
            with self.store.connect(write=True) as db:db.execute('UPDATE solar_shared_calls SET synced=1 WHERE id=?',(row['id'],))

    def reserve(self,event,config,payload):
        if not self.enabled(config):return
        self.flush()
        bound=len(json.dumps(payload,ensure_ascii=False).encode())+4096
        output=payload.get('max_tokens') or payload.get('max_completion_tokens')
        if type(output) is not int or not 0<output<=100000 or bound>2000000:
            raise ValueError('Solar 요청 크기·최대 출력 설정 확인 필요')
        # Persist a stable event before admission. A lost response is never retried as a new paid call.
        with self.store.connect(write=True) as db:
            db.execute('INSERT INTO solar_shared_calls VALUES (?,?,NULL,0,?)',(event,fingerprint(config),now()))
        self.request('reserve',dict(event_id='poc13-'+event,project='poc13',model=config['model'],
                     solar_pool='key2',input_bound=bound,output_bound=output))
        self.checked=0

    def finish(self,event,config,response):
        if not self.enabled(config):return
        row=self.store.one('SELECT * FROM llm_costs WHERE id=?',(event,))
        if not row:return
        rejected=response is not None and response.status_code in (400,401,403,404,422,429)
        known=row['status']=='ESTIMATED'
        value=dict(event_id='poc13-'+event,input_tokens=row['prompt'] if known else 0 if rejected else None,
                   output_tokens=row['completion'] if known else 0 if rejected else None,
                   cost_usd=row['nano_usd']/1e9 if known else 0 if rejected else None,rejected=rejected and not known)
        with self.store.connect(write=True) as db:
            db.execute('UPDATE solar_shared_calls SET settlement=COALESCE(settlement,?) WHERE id=?',(dump(value),event))
        self.checked=0
        try:self.flush()
        except ValueError:pass  # Durable outbox; next admission waits until settlement succeeds.

    def summary(self,config):
        if not self.enabled(config):return None
        with self.lock:
            if self.cached and time.monotonic()-self.checked<20:return self.cached
            try:
                data=self.request('status');card=next(m for m in data['models'] if m['id']=='solar-pro4')
                result=dict(shared=True,budget_known=True,budget_usd=card['limit'],used_usd=card['used'],
                    remaining_usd=card['remaining'],reserved_usd=card['reserved'],unknown_usd=card['unknown'],
                    scope=card['scope'],note='PoC10·13 동일 키의 사용·예약·미확정 비용을 함께 차감합니다. 누적 $100, 자동 초기화 없음. 제공사 실제 잔액과 다를 수 있습니다.')
            except (ValueError,KeyError,StopIteration):
                result=dict(shared=True,budget_known=False,remaining_usd=None,
                    note='공유 잔액 확인 불가 · 예약 성공 전에는 모델을 호출하지 않습니다.')
            self.cached=result;self.checked=time.monotonic();return result

    def import_history(self,config):
        """Explicit maintenance only, with the app stopped; never run on page reads."""
        if not self.enabled(config):raise ValueError('공유 키 불일치')
        self.flush();imported=0
        for row in self.store.rows('SELECT * FROM llm_costs WHERE fingerprint=? ORDER BY created',(fingerprint(config),)):
            existing=self.store.one('SELECT * FROM solar_shared_calls WHERE id=?',(row['id'],))
            if existing and existing['settlement'] is not None:continue
            known=row['status']=='ESTIMATED' and row['nano_usd'] is not None
            # Old calls had no reservation bound. Preserve one conservative maximum
            # supported request per unknown call; never claim that this is actual spend.
            inp,out=(max(1,row['prompt']),max(1,row['completion'])) if known else (2000000,100000)
            with self.store.connect(write=True) as db:
                db.execute('INSERT OR IGNORE INTO solar_shared_calls VALUES (?,?,NULL,0,?)',(row['id'],fingerprint(config),row['created']))
            self.request('reserve',dict(event_id='poc13-'+row['id'],project='poc13',model=row['model'],
                         solar_pool='key2',input_bound=inp,output_bound=out))
            value=dict(event_id='poc13-'+row['id'],input_tokens=row['prompt'] if known else None,
                       output_tokens=row['completion'] if known else None,
                       cost_usd=row['nano_usd']/1e9 if known else None,rejected=False)
            with self.store.connect(write=True) as db:
                db.execute('UPDATE solar_shared_calls SET settlement=? WHERE id=?',(dump(value),row['id']))
            self.flush();imported+=1
        self.checked=0
        return {'imported':imported}
