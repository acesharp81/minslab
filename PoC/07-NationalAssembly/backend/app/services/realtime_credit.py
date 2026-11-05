"""Use verified economical models only after the ordinary free routes exhaust.

The same organization-credit ledger is shared with advanced work. A separate
sub-limit and protected balance bound this project's realtime paid spillover.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

from ..db.connection import connect
from ..db.openai_daily_budget import DailyTokenLimitReached
from ..db.summary_repository import token_usage_from_metadata
from .grouped_models import GroupedOpenAIClient, credit_period, quota_client
from .openrouter_quota import gateway_usage

MODELS = {'gpt-6-luna', 'gpt-5.4-mini'}


def remaining_credit(settings: Any, c: Any) -> tuple[float, float]:
    period = credit_period(settings)
    cap = max(0, float(settings.openai_realtime_credit_monthly_limit_usd))
    if not period:
        return 0.0, cap
    grant, allowance, _ = period
    row = c.execute('SELECT spent_usd+reserved_usd+unknown_usd FROM openai_credit_grant_usage WHERE grant_id=%s', (grant,)).fetchone()
    total = float(row[0]) if row else 0.0
    used = c.execute("""SELECT COALESCE(SUM(CASE WHEN settled THEN COALESCE(cost_usd,reserved_usd)
        ELSE reserved_usd END),0) FROM shared_model_reservations WHERE project='poc7'
        AND budget_kind='credit' AND period_key=%s AND model=ANY(%s)""", (grant, sorted(MODELS))).fetchone()[0]
    return max(0, min(cap-float(used), allowance-total-settings.openai_realtime_credit_protected_usd)), cap


def unavailable(reason: str) -> DailyTokenLimitReached:
    error = DailyTokenLimitReached(reason)
    error.skip_input_count = True
    return error


def usage_cost(model: str, metadata: dict[str, Any]) -> Decimal:
    usage = token_usage_from_metadata(metadata)
    long = usage['input_tokens'] > 272_000
    ir, out = (Decimal('.2' if long else '.1'), Decimal('.75' if long else '.5')) if model == 'gpt-6-luna' else (Decimal('.75'), Decimal('4.5'))
    # Ignore cache discounts, but account conservatively for cache writes.
    details = ((metadata.get('usage') or {}).get('prompt_tokens_details') or {})
    writes = max(0, int(details.get('cache_write_tokens') or 0))
    return (usage['input_tokens']*ir + usage['output_tokens']*out + writes*ir*Decimal('1.5'))/1_000_000


def credit_client(settings: Any, model: str | None = None) -> GroupedOpenAIClient:
    from .shared_budget import reserve as reserve_shared, settle as settle_shared, RATES, BudgetUnavailable
    model = model or settings.openai_realtime_credit_model
    if model not in MODELS:
        raise ValueError('UNREVIEWED_REALTIME_CREDIT_MODEL')
    def reserve(tokens: int, schema_name: str = ""):
        period = credit_period(settings)
        if period is None:
            raise unavailable('PROMOTIONAL_CREDIT_UNCONFIRMED_OR_EXPIRED')
        grant, allowance, _ = period
        cap = min(Decimal(str(settings.openai_realtime_credit_monthly_limit_usd)), Decimal(str(allowance)))
        protected = max(Decimal('0'), Decimal(str(settings.openai_realtime_credit_protected_usd)))
        output_bound = 20_000 if schema_name in {"meeting_brief", "discussion_structure_consolidation", "meeting_parent_review"} else 8_000
        ib, ob = max(1, tokens-output_bound), min(tokens, output_bound)
        ir, out = map(Decimal, RATES[model])
        if model == "gpt-6-luna" and ib > 272_000:
            ir *= 2
        amount = (ib*ir*Decimal('2.5')+ob*out)/1_000_000
        event = 'poc7-realtime-credit:'+str(uuid4())
        with connect(settings.database_url) as c:
            c.execute('INSERT INTO openai_credit_grant_usage(grant_id) VALUES(%s) ON CONFLICT DO NOTHING', (grant,))
            spent = c.execute('SELECT spent_usd+reserved_usd+unknown_usd FROM openai_credit_grant_usage WHERE grant_id=%s FOR UPDATE', (grant,)).fetchone()[0]
            used = c.execute("""SELECT COALESCE(SUM(CASE WHEN settled THEN COALESCE(cost_usd,reserved_usd)
                ELSE reserved_usd END),0) FROM shared_model_reservations WHERE project='poc7'
                AND budget_kind='credit' AND period_key=%s AND model=ANY(%s)""", (grant, sorted(MODELS))).fetchone()[0]
            if cap <= 0 or Decimal(spent)+amount > Decimal(str(allowance))-protected or Decimal(used)+amount > cap:
                raise unavailable('REALTIME_CREDIT_LIMIT_OR_PROTECTED_BALANCE')
            try:
                return reserve_shared(c, settings, event, 'poc7', model, ib, ob, force_credit=True)
            except BudgetUnavailable as exc:
                raise unavailable('REALTIME_CREDIT_UNAVAILABLE') from exc
    def settle(reservation: dict[str, Any], tokens: int, metadata: dict[str, Any] | None):
        metadata = metadata or {}
        usage = token_usage_from_metadata(metadata)
        known = usage['total_tokens'] > 0
        rejected = bool(metadata.get('request_rejected'))
        with connect(settings.database_url) as c:
            settle_shared(c, reservation['event_id'], usage['input_tokens'] if known else None,
                          usage['output_tokens'] if known else None,
                          float(usage_cost(model, metadata)) if known else (0.0 if rejected else None), rejected)
    client = GroupedOpenAIClient(settings.openai_api_key, model=model, base_url=settings.openai_base_url,
                                reserve_tokens=reserve, settle_tokens=settle,
                                reserve_for_workload=lambda tokens, schema: reserve(tokens, schema))
    client.settings = settings
    client.reasoning_effort = 'none'
    return client


def router_exhausted(settings: Any) -> bool:
    if not settings.openrouter_api_key:
        return True
    try:
        usage = gateway_usage(settings)
        return usage is not None and usage['used'] >= min(950, usage['limit'])
    except Exception:
        return False  # An unknown free balance does not authorize paid traffic.


class RealtimeMiniClient:
    provider = 'openai'

    def __init__(self, settings: Any):
        self.settings = settings
        self.model = settings.openai_mini_model

    def _post(self, instruction, schema, schema_name, model_override=None):
        free = quota_client(self.settings, 'mini')
        try:
            answer, usage = free._post(instruction, schema, schema_name)
            self.model = free.model
            return answer, usage
        except DailyTokenLimitReached as exc:
            if not self.settings.openai_monthly_credit_fallback_enabled or 'COOLDOWN' in str(exc) or not router_exhausted(self.settings):
                raise
            paid = credit_client(self.settings)
            answer, usage = paid._post(instruction, schema, schema_name)
            self.model = paid.model
            return answer, {**usage, 'billing_route': 'MONTHLY_CREDIT_SPILLOVER',
                            'free_model': free.model}
