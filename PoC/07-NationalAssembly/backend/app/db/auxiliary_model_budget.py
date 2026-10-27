"""Durable PoC7 sub-budgets, not claims about a provider's account-wide quota."""
from __future__ import annotations
from typing import Any
from uuid import uuid4
from psycopg.types.json import Jsonb


class AuxiliaryUnavailable(RuntimeError):
    """Skip a restricted auxiliary and continue to the next provider."""


class AuxiliaryModelBudget:
    def __init__(self, connection: Any):
        self.connection = connection

    def reserve(self, provider: str, model: str, tokens: int, *, token_limit: int,
                request_limit: int, interval: int, zone: str) -> str:
        c = self.connection
        # Serializes admission across all workers and midnight boundaries.
        c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('aux-budget:' + provider,))
        c.execute('INSERT INTO auxiliary_model_pacing(provider) VALUES (%s) ON CONFLICT DO NOTHING', (provider,))
        ready = c.execute('SELECT next_request_at<=clock_timestamp() FROM auxiliary_model_pacing WHERE provider=%s', (provider,)).fetchone()[0]
        if not ready:
            raise AuxiliaryUnavailable('AUXILIARY_RATE_WAIT')
        day = c.execute("SELECT timezone(%s,clock_timestamp())::date", (zone,)).fetchone()[0]
        count, used = c.execute('SELECT count(*),coalesce(sum(charged_tokens),0) FROM auxiliary_model_calls WHERE provider=%s AND usage_date=%s', (provider, day)).fetchone()
        if tokens < 1 or count >= request_limit or used + tokens > token_limit:
            raise AuxiliaryUnavailable('AUXILIARY_DAILY_LIMIT')
        uid = str(uuid4())
        c.execute('INSERT INTO auxiliary_model_calls(id,provider,model,usage_date,reserved_tokens,charged_tokens) VALUES (%s,%s,%s,%s,%s,%s)', (uid,provider,model,day,tokens,tokens))
        c.execute("UPDATE auxiliary_model_pacing SET next_request_at=clock_timestamp()+(%s * interval '1 second') WHERE provider=%s", (interval,provider))
        return uid

    def settle(self, uid: str, metadata: dict, status: str) -> None:
        usage = metadata.get('usage') or {}
        total = int(usage.get('total_tokens') or 0)
        self.connection.execute('UPDATE auxiliary_model_calls SET charged_tokens=CASE WHEN %s>0 THEN %s ELSE reserved_tokens END,status=%s,usage_metadata=%s,completed_at=now() WHERE id=%s AND completed_at IS NULL', (total,total,status,Jsonb(metadata),uid))

    def cooldown(self, provider: str, seconds: int) -> None:
        self.connection.execute("UPDATE auxiliary_model_pacing SET next_request_at=greatest(next_request_at,clock_timestamp()+(%s * interval '1 second')) WHERE provider=%s", (seconds,provider))

    def today(self, provider: str, zone: str) -> dict[str, int]:
        row = self.connection.execute("""SELECT count(*),coalesce(sum(charged_tokens),0),
            count(*) FILTER (WHERE status='COMPLETED'),
            coalesce(sum(charged_tokens) FILTER (WHERE status IN ('RESERVED','UNKNOWN')),0)
            FROM auxiliary_model_calls WHERE provider=%s
            AND usage_date=timezone(%s,clock_timestamp())::date""", (provider,zone)).fetchone()
        return dict(zip(('request_count','charged_tokens','completed_requests','reserved_or_unknown_tokens'), map(int,row)))
