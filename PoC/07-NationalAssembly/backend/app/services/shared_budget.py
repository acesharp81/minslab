"""One admission ledger for PoC7/10/11; estimates, never provider billing balances."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any
from ..db.openai_group_budget import OpenAIGroupBudget
from .grouped_models import credit_period, daily_limit

RATES = {'gpt-5.4-mini': ('.75', '4.5'), 'gpt-5.4': ('2.5', '15'),
         'gpt-6.1-sol': ('2', '10'), 'gpt-6-astra': ('10', '50'),
         'gpt-6.1-terra': ('2.5', '7.5'), 'solar-pro4': ('.3', '1.2')}
SCOPE = 'PoC7 · PoC10 · PoC11 공통 원장'


class BudgetUnavailable(ValueError):
    pass


def _solar(settings: Any) -> tuple[str, Decimal]:
    grant = settings.shared_solar_grant_id
    cap = Decimal(str(settings.shared_solar_budget_usd))
    if not grant or not 0 < cap <= 110:
        raise BudgetUnavailable('Solar 공통 예산 설정 확인 필요')
    return grant, cap


def reserve(c: Any, settings: Any, event_id: str, project: str, model: str,
            input_bound: int, output_bound: int) -> dict[str, Any]:
    if project not in {'poc7', 'poc10', 'poc11'} or model not in RATES:
        raise BudgetUnavailable('지원하지 않는 프로젝트 또는 모델')
    if not 8 <= len(event_id) <= 100 or not 0 < input_bound <= 2_000_000 or not 0 < output_bound <= 100_000:
        raise BudgetUnavailable('유효하지 않은 예약 요청')
    # Serializes retries of one event, without serializing unrelated requests.
    c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (event_id,))
    old = c.execute('SELECT project,model,reserved_tokens,settled FROM shared_model_reservations WHERE event_id=%s', (event_id,)).fetchone()
    if old:
        if old[0] != project or old[1] != model or old[2] != input_bound + output_bound or old[3]:
            raise BudgetUnavailable('이미 사용되었거나 다른 내용의 예약 ID')
        return {'kind': 'shared_http', 'event_id': event_id}
    provider = 'upstage' if model == 'solar-pro4' else 'openai'
    if c.execute('SELECT 1 FROM model_provider_cooldowns WHERE scope=ANY(%s) AND blocked_until>now()',
                 ([provider, f'{provider}:{model}'],)).fetchone():
        raise BudgetUnavailable('제공사 공통 호출 대기 상태')
    tokens = input_bound + output_bound
    amount = Decimal('0')
    if model in {'gpt-5.4', 'gpt-5.4-mini'}:
        kind = 'mini' if model.endswith('-mini') else 'main'
        cap = daily_limit(settings, kind)
        if cap <= 0: raise BudgetUnavailable('공통 일일 토큰 배정 없음')
        period = str(OpenAIGroupBudget(c, kind).reserve(tokens, cap))
    else:
        kind = 'solar' if model == 'solar-pro4' else 'credit'
        if kind == 'solar':
            period, cap = _solar(settings)
            table = 'shared_solar_grant_usage'
        else:
            current = credit_period(settings)
            if not current: raise BudgetUnavailable('공통 크레딧 기간 확인 필요')
            period, value, _ = current
            cap = Decimal(str(value)); table = 'openai_credit_grant_usage'
        ir, out = (Decimal(v) for v in RATES[model])
        amount = (Decimal(input_bound)*ir*(1 if kind == 'solar' else Decimal('2.5')) + Decimal(output_bound)*out)/1_000_000
        # table is from the fixed allowlist above, never request data.
        if kind == 'solar' and settings.shared_solar_unlimited:
            row = c.execute(f'''INSERT INTO {table}(grant_id,reserved_usd) VALUES(%s,%s)
                ON CONFLICT(grant_id) DO UPDATE SET reserved_usd={table}.reserved_usd+EXCLUDED.reserved_usd,
                updated_at=now() RETURNING grant_id''', (period,amount)).fetchone()
        else:
            row = c.execute(f'''INSERT INTO {table}(grant_id,reserved_usd) SELECT %s,%s WHERE %s<=%s
                ON CONFLICT(grant_id) DO UPDATE SET reserved_usd={table}.reserved_usd+EXCLUDED.reserved_usd,updated_at=now()
                WHERE {table}.spent_usd+{table}.reserved_usd+{table}.unknown_usd+EXCLUDED.reserved_usd<=%s
                RETURNING grant_id''', (period, amount, amount, cap, cap)).fetchone()
        if not row: raise BudgetUnavailable('공통 예산 잔여량 부족')
    c.execute('''INSERT INTO shared_model_reservations(event_id,project,model,budget_kind,period_key,reserved_tokens,reserved_usd)
        VALUES(%s,%s,%s,%s,%s,%s,%s)''', (event_id, project, model, kind, period, tokens, amount))
    return {'kind': 'shared_http', 'event_id': event_id}


def settle(c: Any, event_id: str, input_tokens: int | None, output_tokens: int | None,
           cost_usd: float | None, rejected: bool = False) -> dict[str, bool]:
    if input_tokens is not None and (type(input_tokens) is not int or not 0 <= input_tokens <= 10_000_000):
        raise BudgetUnavailable('유효하지 않은 입력 사용량')
    if output_tokens is not None and (type(output_tokens) is not int or not 0 <= output_tokens <= 10_000_000):
        raise BudgetUnavailable('유효하지 않은 출력 사용량')
    if cost_usd is not None and (not Decimal(str(cost_usd)).is_finite() or not 0 <= cost_usd <= 100):
        raise BudgetUnavailable('유효하지 않은 비용')
    row = c.execute('''SELECT budget_kind,period_key,reserved_tokens,reserved_usd,settled
        FROM shared_model_reservations WHERE event_id=%s FOR UPDATE''', (event_id,)).fetchone()
    if not row: raise BudgetUnavailable('예약 이력을 찾을 수 없습니다')
    kind, period, tokens, amount, done = row
    if done: return {'settled': True, 'duplicate': True}
    known = input_tokens is not None and output_tokens is not None
    if rejected and (input_tokens or output_tokens or cost_usd):
        raise BudgetUnavailable('요청 거절 상태와 사용량이 충돌합니다')
    if kind in {'mini', 'main'}:
        metadata = {'usage': {'input_tokens': input_tokens or 0, 'output_tokens': output_tokens or 0,
                             'total_tokens': (input_tokens or 0)+(output_tokens or 0)}} if known else {}
        if rejected: metadata['request_rejected'] = True
        OpenAIGroupBudget(c, kind).settle(period, tokens, metadata)
    else:
        table = 'shared_solar_grant_usage' if kind == 'solar' else 'openai_credit_grant_usage'
        spent = Decimal(str(cost_usd)) if cost_usd is not None else Decimal('0')
        unknown = amount if cost_usd is None and not rejected else Decimal('0')
        updated = c.execute(f'''UPDATE {table} SET spent_usd=spent_usd+%s,unknown_usd=unknown_usd+%s,
            reserved_usd=reserved_usd-%s,request_count=request_count+1,updated_at=now()
            WHERE grant_id=%s AND reserved_usd>=%s''', (spent, unknown, amount, period, amount))
        if updated.rowcount != 1: raise BudgetUnavailable('공통 예산 예약 잔액 불일치')
    c.execute('''UPDATE shared_model_reservations SET settled=true,input_tokens=%s,output_tokens=%s,
        cost_usd=%s,settled_at=now() WHERE event_id=%s''', (input_tokens, output_tokens, cost_usd, event_id))
    return {'settled': True, 'duplicate': False}


def import_solar_history(c: Any, settings: Any, rows: list[dict[str, Any]]) -> None:
    """Idempotent accounting of already metered Solar calls, including late outbox delivery."""
    grant, _ = _solar(settings)
    c.execute('INSERT INTO shared_solar_grant_usage(grant_id) VALUES(%s) ON CONFLICT DO NOTHING', (grant,))
    for r in rows:
        # New centralized calls are already accounted. Legacy events are immutable.
        event = str(r['event_id'])
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (event,))
        if c.execute('SELECT 1 FROM shared_model_reservations WHERE event_id=%s', (event,)).fetchone(): continue
        cost = r.get('cost_usd')
        # An unmetered legacy request has no reliable upper bound: block remaining Solar budget.
        unknown = _solar(settings)[1] if cost is None else Decimal('0')
        spent = Decimal(str(cost or 0))
        c.execute('''INSERT INTO shared_model_reservations(event_id,project,model,budget_kind,period_key,
            settled,input_tokens,output_tokens,cost_usd,settled_at) VALUES(%s,%s,%s,'solar',%s,true,%s,%s,%s,now())''',
            (event, r['project'], r['model'], grant, r.get('input_tokens'), r.get('output_tokens'), cost))
        c.execute('''UPDATE shared_solar_grant_usage SET spent_usd=spent_usd+%s,unknown_usd=unknown_usd+%s,
            request_count=request_count+1,updated_at=now() WHERE grant_id=%s''', (spent, unknown, grant))


def snapshot(c: Any, settings: Any) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    reset = (now+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
    cards = []
    for kind, label, ident in [('mini','GPT 5.4 mini','gpt-5.4-mini'),('main','GPT 5.4','gpt-5.4')]:
        v = OpenAIGroupBudget(c, kind).today(); cap = daily_limit(settings, kind)
        used = v['total_tokens']; reserved = v['reserved_tokens']; unknown = v['unknown_tokens']
        cards.append(dict(id=ident,label=label,unit='tokens',limit=cap,used=used,reserved=reserved,unknown=unknown,
            remaining=max(0,cap-used-reserved-unknown),expires_at=reset,status='AVAILABLE',scope=SCOPE,
            note='공용 일일 토큰 · 입력+출력 · 한국시간 매일 09시 초기화'))
    current = credit_period(settings)
    money = [('credit','OpenAI 공용 크레딧','openai-shared',current,'openai_credit_grant_usage'),
             ('solar','Solar Pro 4','solar-pro4',(*_solar(settings),None),'shared_solar_grant_usage')]
    for kind,label,ident,period,table in money:
        if not period:
            cards.append(dict(id=ident,label=label,unit='USD',remaining=None,limit=None,status='UNAVAILABLE',
                scope=SCOPE,note='공통 예산 기간 확인 필요')); continue
        grant,cap,expiry = period; cap=float(cap)
        row=c.execute(f'SELECT spent_usd,reserved_usd,unknown_usd FROM {table} WHERE grant_id=%s',(grant,)).fetchone() or (0,0,0)
        spent,reserved,unknown=map(float,row)
        monthly = kind=='credit' and (settings.openai_credit_month_start_renewal or settings.openai_credit_month_end_renewal)
        display_limit = max(cap,float(settings.openai_credit_monthly_budget_usd)) if monthly else cap
        opening_used = display_limit-cap
        cards.append(dict(id=ident,label=label,unit='USD',limit=display_limit,current_period_allowance=cap,
            opening_used=opening_used,tracked_used=spent,used=opening_used+spent,
            reserved=reserved,unknown=unknown,remaining=max(0,cap-spent-reserved-unknown),expires_at=expiry,
            status='AVAILABLE',scope=SCOPE,note=('누적 $110 한도 · 자동 초기화 없음 · 제공사 실제 잔액 아님' if kind=='solar'
                else f'공용 월 ${display_limit:g} · 매월 1일 한국시간 00시 갱신 · 최초 잔액에서 후속 사용·예약·미확정 차감' if settings.openai_credit_month_start_renewal else '공통 운영 예산 · 설정된 지급 주기 기준 · 제공사 실제 잔액 아님')))
    if settings.shared_solar_unlimited:
        solar = next(m for m in cards if m['id']=='solar-pro4')
        row = c.execute("SELECT COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0),COUNT(*) FROM shared_model_reservations WHERE budget_kind='solar' AND settled").fetchone()
        solar.update(limit=None,remaining=None,current_period_allowance=None,status='UNLIMITED',
                     input_tokens=int(row[0]),output_tokens=int(row[1]),request_count=int(row[2]),
                     note='사용자 확인 무제한 키 · 공용 사용량만 기록 · 비용은 공개 단가 환산 추정치')
    return dict(models=cards,checked_at=now.isoformat(),scope=SCOPE,
        note='세 서비스의 사용·예약·미확정 사용량을 함께 차감합니다. 외부 호출과 제공사 실제 청구 잔액은 포함하지 않는 시스템 추정치입니다.')
