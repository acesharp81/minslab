"""Central usage outbox and atomic reservations against PoC7's existing credit ledger."""
import json
from decimal import Decimal
from datetime import datetime, timezone
import httpx
import psycopg
from .storage import now
from . import token_budget

RATES={'nvidia/nemotron-3.5-super-vl:free':(0,0),'gpt-5.4':(2.5,15),'gpt-5.4-mini':(.75,4.5),'gpt-6.1-sol':(2,10),'gpt-6-astra':(10,50),'solar-pro4':(.30,1.20)}

class BudgetError(RuntimeError):pass

class Usage:
    def __init__(self, settings, store):self.s,self.store=settings,store
    def central(self):
        url=self.s.get('USAGE_GATEWAY_URL')
        if not url:raise BudgetError('공용 사용량 URL 미설정')
        try:
            r=httpx.get(url.rstrip('/')+'/internal/status',timeout=5);r.raise_for_status()
            return r.json()
        except (httpx.HTTPError,ValueError) as exc:raise BudgetError('PoC7 공용 사용량 서비스 연결 실패') from exc
    def preflight(self, provider):
        if self.s.flag('USAGE_REQUIRE_SHARED',True):
            if not self.s.get('USAGE_METER_TOKEN'):raise BudgetError('공용 사용량 인증 미설정')
            self.central()
            self.flush()
            with self.store.connect() as c:
                if c.execute('SELECT count(*) FROM usage_events WHERE synced=0').fetchone()[0]:
                    raise BudgetError('공용 사용량 미전송 기록을 먼저 동기화해야 합니다.')
        if provider=='openai' and not self.shared_http() and self.s.flag('SHARED_BUDGET_REQUIRED',True):
            if not self.s.get('SHARED_BUDGET_DATABASE_URL'):raise BudgetError('PoC7 공용 OpenAI 예산 연결 미설정')
    def shared_http(self):
        return self.s.flag('SHARED_BUDGET_HTTP',True)
    def shared_request(self,action,payload=None):
        url=self.s.get('USAGE_GATEWAY_URL').rstrip('/')
        token=self.s.get('USAGE_METER_TOKEN')
        if not url or not token:raise BudgetError('공통 예산 연결 설정 필요')
        try:
            headers={'x-minslab-meter-token':token}
            r=httpx.get(url+'/internal/budget/status',headers=headers,timeout=5) if action=='status' else httpx.post(url+'/internal/budget/'+action,json=payload,headers=headers,timeout=5)
            r.raise_for_status();return r.json()
        except (httpx.HTTPError,ValueError):raise BudgetError('공통 예산 부족 또는 중앙 연결 확인 필요') from None
    def period_details(self):
        grant=self.s.get('SHARED_CREDIT_GRANT_ID')
        try:
            expiry=datetime.fromisoformat(self.s.get('SHARED_CREDIT_EXPIRES_AT').replace('Z','+00:00'))
            amount=Decimal(self.s.get('SHARED_CREDIT_BUDGET_USD','0'))
            if not grant or not expiry.tzinfo or amount<=0:raise ValueError()
            current=datetime.now(timezone.utc)
            if current>=expiry:
                if not (self.s.flag('SHARED_CREDIT_MONTH_START_RENEWAL') or self.s.flag('SHARED_CREDIT_MONTH_END_RENEWAL')):raise ValueError()
                from calendar import monthrange
                from zoneinfo import ZoneInfo
                local=current.astimezone(ZoneInfo('Asia/Seoul'))
                boundary=local.replace(day=monthrange(local.year,local.month)[1],hour=0,minute=0,second=0,microsecond=0)
                if self.s.flag('SHARED_CREDIT_MONTH_START_RENEWAL'):
                    start=local.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
                    y,m=(start.year+1,1) if start.month==12 else (start.year,start.month+1)
                    expiry=start.replace(year=y,month=m)
                elif local<boundary:
                    y,m=(local.year-1,12) if local.month==1 else (local.year,local.month-1)
                    start=boundary.replace(year=y,month=m,day=monthrange(y,m)[1]);expiry=boundary
                else:
                    start=boundary;y,m=(local.year+1,1) if local.month==12 else (local.year,local.month+1)
                    expiry=boundary.replace(year=y,month=m,day=monthrange(y,m)[1])
                grant=f'{grant}:renew:{start.date()}'
                amount=Decimal(self.s.get('SHARED_CREDIT_MONTHLY_BUDGET_USD','0'))
            if not 0<amount<=100:raise ValueError()
        except (ValueError,ArithmeticError):raise BudgetError('공용 크레딧 기간·한도를 확인해야 합니다. 확인된 갱신 설정이 없으면 만료 후 호출을 차단합니다.')
        return grant,amount,expiry.isoformat()
    def period(self):
        grant,amount,_=self.period_details()
        return grant,amount
    def reserve(self, event_id, model, input_bound, output_bound):
        if model not in RATES:raise BudgetError('가격 분류가 없는 모델입니다.')
        if model.endswith(':free'):return None
        if self.shared_http():
            return self.shared_request('reserve',dict(event_id=event_id,project='poc11',model=model,input_bound=input_bound,output_bound=output_bound))
        if model=='solar-pro4':raise BudgetError('Solar는 공통 예산 HTTP 연결이 필요합니다')
        url=self.s.get('SHARED_BUDGET_DATABASE_URL')
        if not url:
            if self.s.flag('SHARED_BUDGET_REQUIRED',True):raise BudgetError('공용 예산 연결 필요')
            return None
        if model in ('gpt-5.4','gpt-5.4-mini'):
            try:
                with psycopg.connect(url,connect_timeout=5) as c:
                    blocked=c.execute("SELECT 1 FROM model_provider_cooldowns WHERE scope=ANY(%s) AND blocked_until>now()",(['openai',f'openai:{model}'],)).fetchone()
                    if blocked:raise BudgetError('공용 OpenAI 호출 대기 상태')
                    return token_budget.reserve(c,event_id,input_bound+output_bound,'mini' if model=='gpt-5.4-mini' else 'main')
            except psycopg.Error as exc:raise BudgetError('GPT-5.4 공용 토큰 예약 연결 실패') from exc
        grant,limit=self.period()
        ir,orr=RATES[model]
        # Conservative standard rate, including cache-write surcharge; requests bounded below 272K.
        amount=(Decimal(input_bound)*Decimal(str(ir))*Decimal('2.5')+Decimal(output_bound)*Decimal(str(orr)))/1_000_000
        try:
            with psycopg.connect(url,connect_timeout=5) as c:
                blocked=c.execute("SELECT 1 FROM model_provider_cooldowns WHERE scope=ANY(%s) AND blocked_until>now()",(['openai',f'openai:{model}'],)).fetchone()
                if blocked:raise BudgetError('공용 OpenAI 호출 대기 상태')
                row=c.execute('''INSERT INTO openai_credit_grant_usage(grant_id,reserved_usd)
                  SELECT %s,%s WHERE %s<=%s ON CONFLICT(grant_id) DO UPDATE
                  SET reserved_usd=openai_credit_grant_usage.reserved_usd+EXCLUDED.reserved_usd,updated_at=now()
                  WHERE openai_credit_grant_usage.spent_usd+openai_credit_grant_usage.unknown_usd+
                  openai_credit_grant_usage.reserved_usd+EXCLUDED.reserved_usd<=%s RETURNING grant_id''',
                  (grant,amount,amount,limit,limit)).fetchone()
                if not row:raise BudgetError('PoC7·PoC11 공용 크레딧 예산 부족')
                c.execute('INSERT INTO poc11_credit_reservations(event_id,grant_id,reserved_usd) VALUES(%s,%s,%s)',(event_id,grant,amount))
        except psycopg.Error as exc:raise BudgetError('공용 예산 예약 실패: 연결 및 마이그레이션 확인 필요') from exc
        return {'event_id':event_id,'grant_id':grant,'amount':str(amount)}
    def settle(self, reservation, cost, event=None):
        if not reservation:return
        if reservation.get('kind')=='shared_http':
            e=event or {}
            rejected=e.get('http_status') in (400,401,403,404,422,429) and cost==0
            return self.shared_request('settle',dict(event_id=reservation['event_id'],input_tokens=e.get('input_tokens'),output_tokens=e.get('output_tokens'),cost_usd=cost,rejected=rejected))
        if reservation.get('kind')=='daily_tokens':
            with psycopg.connect(self.s.get('SHARED_BUDGET_DATABASE_URL'),connect_timeout=5) as c:
                token_budget.settle(c,reservation,event or {'cost_usd':cost})
            return
        with psycopg.connect(self.s.get('SHARED_BUDGET_DATABASE_URL'),connect_timeout=5) as c:
            row=c.execute('SELECT grant_id,reserved_usd,settled FROM poc11_credit_reservations WHERE event_id=%s FOR UPDATE',(reservation['event_id'],)).fetchone()
            if not row or row[2]:return
            grant,amount,_=row
            updated=c.execute('''UPDATE openai_credit_grant_usage SET spent_usd=spent_usd+%s,unknown_usd=unknown_usd+%s,
                reserved_usd=reserved_usd-%s,request_count=request_count+1,updated_at=now()
                WHERE grant_id=%s AND reserved_usd>=%s''',(Decimal(str(cost)) if cost is not None else 0,amount if cost is None else 0,amount,grant,amount))
            if updated.rowcount!=1:raise BudgetError('공용 예산 정산 불일치: 예약을 확인해야 합니다.')
            c.execute('UPDATE poc11_credit_reservations SET settled=true WHERE event_id=%s',(reservation['event_id'],))
    def record(self,event,reservation):
        body={**event,'recorded_at':now(),'reservation':reservation,'budget_settled':not bool(reservation)}
        # Durable record before remote accounting. A crash can only retain a reservation, never free unpaid budget.
        with self.store.connect() as c:c.execute('INSERT INTO usage_events(id,body) VALUES(?,?)',(event['event_id'],json.dumps(body)))
        self.flush()
    def flush(self):
        with self.store.connect() as c:rows=c.execute('SELECT id,body FROM usage_events WHERE synced=0 LIMIT 50').fetchall()
        done=0
        for row in rows:
            b=json.loads(row['body'])
            try:
                if not b['budget_settled']:
                    self.settle(b['reservation'],b['cost_usd'],b);b['budget_settled']=True
                    with self.store.connect() as c:c.execute('UPDATE usage_events SET body=? WHERE id=?',(json.dumps(b),row['id']))
                payload={k:b[k] for k in ('event_id','project','workload','provider','model','status','http_status','input_tokens','output_tokens','cost_usd')}
                r=httpx.post(self.s.get('USAGE_GATEWAY_URL').rstrip('/')+'/internal/usage-events',json=payload,
                             headers={'x-minslab-meter-token':self.s.get('USAGE_METER_TOKEN')},timeout=5)
                r.raise_for_status()
                with self.store.connect() as c:c.execute('UPDATE usage_events SET synced=1 WHERE id=?',(row['id'],))
                done+=1
            except (httpx.HTTPError,psycopg.Error,ValueError,RuntimeError):break
        return done
    def budget_snapshot(self):
        if self.shared_http():
            try:
                card=next(m for m in self.shared_request('status')['models'] if m['id']=='openai-shared')
                if card['remaining'] is None:return {'budget':None,'budget_error':'공통 크레딧 기간 확인 필요'}
                return {'budget':dict(limit_usd=card['limit'],remaining_usd=card['remaining'],spent_usd=card['used'],reserved_usd=card['reserved'],unknown_usd=card['unknown'],scope=card['scope'],expires_at=card['expires_at'])}
            except (BudgetError,KeyError,StopIteration):return {'budget':None,'budget_error':'공통 예산 연결 확인 필요'}
        result={'budget':None}
        if self.s.get('SHARED_BUDGET_DATABASE_URL'):
            try:
                grant,cap=self.period()
                with psycopg.connect(self.s.get('SHARED_BUDGET_DATABASE_URL'),connect_timeout=5) as c:
                    row=c.execute('SELECT spent_usd,reserved_usd,unknown_usd FROM openai_credit_grant_usage WHERE grant_id=%s',(grant,)).fetchone() or (0,0,0)
                result['budget']={'limit_usd':float(cap),'remaining_usd':max(0,float(cap)-float(sum(row))),'spent_usd':float(row[0]),'reserved_usd':float(row[1]),'unknown_usd':float(row[2]),'scope':'PoC7·PoC11 동일 크레딧 원장','expires_at':self.period_details()[2],
                    'monthly_limit_usd':float(self.s.get('SHARED_CREDIT_MONTHLY_BUDGET_USD','100')) if (self.s.flag('SHARED_CREDIT_MONTH_START_RENEWAL') or self.s.flag('SHARED_CREDIT_MONTH_END_RENEWAL')) else float(cap),
                    'renewal':'KST_MONTH_FIRST_DAY_00:00' if self.s.flag('SHARED_CREDIT_MONTH_START_RENEWAL') else 'KST_MONTH_LAST_DAY_00:00' if self.s.flag('SHARED_CREDIT_MONTH_END_RENEWAL') else None}
            except (BudgetError,psycopg.Error):result['budget_error']='공용 예산 연결 또는 기간 확인 필요'
        return result

    def remaining(self):
        if self.shared_http():
            try:result=self.shared_request('status')
            except BudgetError:
                result={'models':[dict(id=i,label=l,unit=u,remaining=None,limit=None,status='UNAVAILABLE',note='공통 예산 연결 확인 필요') for i,l,u in [('gpt-5.4','GPT 5.4','tokens'),('gpt-5.4-mini','GPT 5.4 mini','tokens'),('openai-shared','OpenAI 공용 크레딧','USD'),('solar-pro4','Solar Pro 4','USD')]],'checked_at':now()}
            from .naver_ocr import snapshot as ocr_snapshot
            result['models'] += [self.openrouter_remaining(),ocr_snapshot(self.s,self.store)]
            return result
        snapshot=self.budget_snapshot()
        budget=snapshot['budget']
        models=[{'id':'openai-shared','label':'GPT 6.0·6.1','unit':'USD','scope':'POC7_SHARED_OPENAI_CREDIT',
            'remaining':budget['remaining_usd'] if budget else None,'limit':budget.get('monthly_limit_usd',budget['limit_usd']) if budget else None,
            'current_period_allowance':budget['limit_usd'] if budget else None,
            'expires_at':budget['expires_at'] if budget else None,'status':'AVAILABLE' if budget else 'UNAVAILABLE',
            'note':('PoC7 공용 · 월 $100 · '+('매월 1일' if budget.get('renewal')=='KST_MONTH_FIRST_DAY_00:00' else '매월 말일')+' 한국시간 00시 갱신. 최초 잔액 $'+format(budget['limit_usd'],'.2f')+'에서 사용액을 차감합니다.') if budget and budget.get('renewal') else 'GPT 6.0·6.1은 PoC7과 같은 크레딧 예산을 사용합니다. GPT-5.4 일별 토큰과 별도입니다.'}]
        models.insert(0,self.gpt54_remaining())
        models.insert(1,self.gpt54_remaining('mini'))
        models.append({'id':'solar-pro4','label':'Solar Pro 4','unit':'USD','scope':'USAGE_ONLY',
            'remaining':None,'limit':None,'expires_at':None,'status':'UNCONFIRMED',
            'note':'사용량은 중앙 집계 중입니다. 공급자 잔액이 연동되지 않아 잔여량은 확인할 수 없습니다.'})
        models.append(self.openrouter_remaining())
        from .naver_ocr import snapshot
        models.append(snapshot(self.s,self.store))
        return {'models':models,'checked_at':now()}

    def gpt54_remaining(self,group='main'):
        mini=group=='mini'
        card={'id':'gpt-5.4-mini' if mini else 'gpt-5.4','label':'GPT 5.4 mini' if mini else 'GPT 5.4','unit':'tokens','scope':'POC7_SHARED_OPENAI_'+group.upper()+'_TOKENS',
              'remaining':None,'limit':None,'status':'UNAVAILABLE',
              'note':f'PoC7·PoC11 공용 일 {token_budget.LIMITS[group]:,} 토큰 · 입력+출력 합산 · 예약·미확정 포함 · 한국시간 09시 초기화'}
        if not self.s.get('SHARED_BUDGET_DATABASE_URL'):return card
        try:
            with psycopg.connect(self.s.get('SHARED_BUDGET_DATABASE_URL'),connect_timeout=5) as c:
                card.update(token_budget.snapshot(c,group),status='AVAILABLE')
        except psycopg.Error:card['note']='GPT-5.4 공용 일별 토큰 조회 실패'
        return card

    def openrouter_remaining(self):
        card={'id':'openrouter-free','label':'Nemotron 3.5 Super VL','unit':'requests','scope':'OPENROUTER_ACCOUNT_FREE',
              'remaining':None,'limit':None,'status':'UNCONFIRMED','note':'API 키 설정 후 무료 요청 잔여 횟수를 조회합니다.'}
        key=self.s.get('OPENROUTER_API_KEY')
        gateway=self.s.get('OPENROUTER_GATEWAY_URL').rstrip('/')
        if not key:return {**card,'display':'키 미설정'}
        try:
            url=gateway+'/api/v1/key' if gateway else self.s.get('OPENROUTER_BASE_URL','https://openrouter.ai/api/v1').rstrip('/')+'/key'
            r=httpx.get(url,headers={} if gateway else {'Authorization':'Bearer '+key},timeout=5)
            r.raise_for_status();daily=r.json().get('data',{}).get('free_model_daily_requests') or {}
            if all(isinstance(daily.get(k),(int,float)) and not isinstance(daily[k],bool) and daily[k]>=0 for k in ('limit','remaining')) and daily['limit']>0:
                card.update(remaining=daily['remaining'],limit=daily['limit'],status='AVAILABLE',note='OpenRouter 계정의 무료 모델 공용 요청 횟수 · UTC 일별 한도')
            else:card.update(note='공급자가 무료 요청 잔여량을 반환하지 않았습니다.',display='잔여량 미확인')
            if gateway and card['remaining'] is not None:
                r=httpx.get(gateway+'/internal/status',timeout=5);r.raise_for_status();shared=r.json()
                available=max(0,int(shared['remaining']))
                card.update(official_remaining=card['remaining'],remaining=min(card['remaining'],available),
                    operational_limit=shared['operational_limit'],safety_reserve=shared['safety_reserve'],scope='POC7_SHARED_OPENROUTER_REQUESTS',
                    note=f"PoC7·PoC11 공용 · 공식 {card['limit']}회/일, 운영 {shared['operational_limit']}회, 안전 여유 {shared['safety_reserve']}회 · 한국시간 09시 초기화")
        except (httpx.HTTPError,ValueError,TypeError,KeyError):card.update(remaining=None,limit=None,status='UNCONFIRMED',note='OpenRouter 공용 한도 조회 실패',display='확인 불가')
        return card

    def summary(self):
        with self.store.connect() as c:
            rows=[{**json.loads(r['body']),'synced':bool(r['synced'])} for r in c.execute('SELECT body,synced FROM usage_events')]
        public=[{k:v for k,v in r.items() if k not in ('reservation',)} for r in rows]
        result={'events':public,'pending':sum(not x['synced'] for x in public),
                'cost_usd':round(sum(x['cost_usd'] or 0 for x in rows),6),'unknown_cost_calls':sum(x['cost_usd'] is None for x in rows),
                'cost_basis':'Standard 요금의 보수적 추정치 · 공급자 청구서 아님','shared':None,'shared_error':None,'budget':None}
        try:result['shared']=self.central()
        except BudgetError as exc:result['shared_error']=str(exc)
        result.update(self.budget_snapshot())
        from .naver_ocr import snapshot,history
        result['naver_ocr']=snapshot(self.s,self.store)
        result['naver_ocr_events']=history(self.store)
        return result


def token_cost(model,usage):
    it=int(usage.get('input_tokens',usage.get('prompt_tokens',0)) or 0)
    ot=int(usage.get('output_tokens',usage.get('completion_tokens',0)) or 0)
    if not it and not ot:return it,ot,None
    ir,orr=RATES[model];long=it>272000
    details=usage.get('input_tokens_details') or usage.get('prompt_tokens_details') or {}
    writes=int(details.get('cache_write_tokens',0) or 0)
    cost=(it*ir*(2 if long else 1)+ot*orr*(1.5 if long else 1)+writes*ir*1.5*(2 if long else 1))/1_000_000
    return it,ot,round(cost,8)
