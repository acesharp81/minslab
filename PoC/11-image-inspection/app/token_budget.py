"""GPT-5.4 / mini share PoC7 main / mini ledgers with idempotent settlement."""
from datetime import datetime, timezone, timedelta

LIMIT = 1_000_000
LIMITS = {"main": LIMIT, "mini": 10_000_000}


def reserve(connection, event_id, amount, group="main"):
    limit=LIMITS[group]
    if amount < 1:
        raise ValueError('토큰 예약량은 양수여야 합니다.')
    row = connection.execute('''INSERT INTO openai_group_daily_usage(budget_group,usage_date,reserved_tokens)
        SELECT %s,timezone('UTC',now())::date,%s WHERE %s<=%s
        ON CONFLICT(budget_group,usage_date) DO UPDATE
        SET reserved_tokens=openai_group_daily_usage.reserved_tokens+EXCLUDED.reserved_tokens,updated_at=now()
        WHERE openai_group_daily_usage.total_tokens+openai_group_daily_usage.unknown_tokens+
          openai_group_daily_usage.reserved_tokens+EXCLUDED.reserved_tokens<=%s
        RETURNING usage_date''', (group,amount,amount,limit,limit)).fetchone()
    if not row:
        raise RuntimeError(f'GPT-5.4 {group} PoC7·PoC11 공용 일 {limit//10000:,}만 토큰 한도 부족 · 한국시간 09시 초기화')
    day = row[0]
    connection.execute('''INSERT INTO poc11_token_reservations(event_id,usage_date,reserved_tokens,budget_group)
        VALUES(%s,%s,%s,%s)''', (event_id,day,amount,group))
    return {'kind':'daily_tokens','event_id':event_id,'usage_date':day.isoformat(),'tokens':amount,'budget_group':group}


def settle(connection, reservation, event):
    row = connection.execute('''SELECT usage_date,reserved_tokens,settled,budget_group FROM poc11_token_reservations
        WHERE event_id=%s FOR UPDATE''',(reservation['event_id'],)).fetchone()
    if not row or row[2]:
        return
    day,amount,_,group = row
    it,ot = int(event.get('input_tokens',0)),int(event.get('output_tokens',0))
    known = it+ot>0 or event.get('cost_usd')==0
    updated = connection.execute('''UPDATE openai_group_daily_usage SET
        request_count=request_count+1,input_tokens=input_tokens+%s,output_tokens=output_tokens+%s,
        total_tokens=total_tokens+%s,unknown_tokens=unknown_tokens+%s,
        reserved_tokens=reserved_tokens-%s,updated_at=now()
        WHERE budget_group=%s AND usage_date=%s AND reserved_tokens>=%s''',
        (it if known else 0,ot if known else 0,it+ot if known else 0,0 if known else amount,amount,group,day,amount))
    if updated.rowcount!=1:
        raise RuntimeError('GPT-5.4 공용 토큰 정산 불일치')
    connection.execute('UPDATE poc11_token_reservations SET settled=true WHERE event_id=%s',(reservation['event_id'],))


def snapshot(connection, group="main"):
    limit=LIMITS[group]
    row = connection.execute('''SELECT total_tokens,unknown_tokens,reserved_tokens
        FROM openai_group_daily_usage WHERE budget_group=%s
        AND usage_date=timezone('UTC',now())::date''',(group,)).fetchone() or (0,0,0)
    reset = (datetime.now(timezone.utc)+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
    return dict(remaining=max(0,limit-sum(row)),limit=limit,used_tokens=row[0],
                unknown_tokens=row[1],reserved_tokens=row[2],resets_at=reset.isoformat())
