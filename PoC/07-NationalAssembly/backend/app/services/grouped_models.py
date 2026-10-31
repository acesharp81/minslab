"""Workload routing, independent quotas and a finite confirmed promotional grant.

OpenAI ledgers are shared by PoC7, PoC10 and PoC11 through the existing gateway.
Other organization traffic is excluded; these are not account balance APIs.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from calendar import monthrange
from zoneinfo import ZoneInfo
from decimal import Decimal
from typing import Any
import requests

from ..db.connection import connect
from ..db.openai_daily_budget import DailyTokenLimitReached
from ..db.openai_group_budget import OpenAIGroupBudget
from ..db.summary_repository import token_usage_from_metadata
from .meeting_brief import OpenAIMeetingBriefClient, OpenRouterMeetingBriefClient
from .model_workloads import INTEGRATION_SCHEMAS

INTEGRATION = INTEGRATION_SCHEMAS | {'live_topic_mapping', 'topic_report',
    'gukjeongbomi_topic_report', 'official_brief_delta', 'gukjeongbomi_official_change_report'}


def credit_period(settings: Any, now: datetime | None = None) -> tuple[str, float, str] | None:
    """User-authorized local allowance, not an assertion of an actual billing grant."""
    now = now or datetime.now(timezone.utc)
    try:
        expiry = datetime.fromisoformat(settings.openai_credit_expires_at.replace('Z', '+00:00'))
        if not expiry.tzinfo or not settings.openai_credit_grant_id:
            return None
        if now < expiry:
            amount = float(settings.openai_credit_budget_usd)
            return (settings.openai_credit_grant_id, amount, expiry.isoformat()) if 0 < amount <= 100 else None
        if getattr(settings, 'openai_credit_month_start_renewal', False):
            local = now.astimezone(ZoneInfo('Asia/Seoul'))
            start = local.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
            year, month = (start.year+1,1) if start.month == 12 else (start.year,start.month+1)
            end = start.replace(year=year,month=month)
            amount = float(settings.openai_credit_monthly_budget_usd)
            return (f'{settings.openai_credit_grant_id}:renew:{start.date()}', amount, end.isoformat()) if 0 < amount <= 100 else None
        if not getattr(settings, 'openai_credit_month_end_renewal', False):
            return None
        local = now.astimezone(ZoneInfo('Asia/Seoul'))
        boundary = local.replace(day=monthrange(local.year,local.month)[1],hour=0,minute=0,second=0,microsecond=0)
        if local < boundary:
            year, month = (local.year-1,12) if local.month == 1 else (local.year,local.month-1)
            start = boundary.replace(year=year,month=month,day=monthrange(year,month)[1])
            end = boundary
        else:
            start = boundary
            year, month = (local.year+1,1) if local.month == 12 else (local.year,local.month+1)
            end = boundary.replace(year=year,month=month,day=monthrange(year,month)[1])
        amount = float(settings.openai_credit_monthly_budget_usd)
        return (f'{settings.openai_credit_grant_id}:renew:{start.date()}', amount, end.isoformat()) if 0 < amount <= 100 else None
    except (ValueError, AttributeError):
        return None


def credit_active(settings: Any) -> bool:
    return credit_period(settings) is not None


def daily_limit(settings: Any, group: str) -> int:
    if group == 'mini':
        return max(0, min(10_000_000, settings.openai_mini_daily_token_limit)
                   - settings.openai_other_projects_mini_tokens)
    return max(0, min(1_000_000, settings.openai_daily_token_limit)
               - settings.openai_other_projects_main_tokens)


class GroupedOpenAIClient(OpenAIMeetingBriefClient):
    def _post(self, *args, **kwargs):
        try:
            return super()._post(*args, **kwargs)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 429:
                try:
                    error = exc.response.json().get('error') or {}
                    code = str(error.get('code') or error.get('type') or '')
                except (ValueError, AttributeError):
                    code = ''
                quota = code in {'insufficient_quota','billing_hard_limit_reached','monthly_budget_exceeded','usage_limit_reached'}
                now = datetime.now(timezone.utc)
                period = credit_period(self.settings)
                until = datetime.fromisoformat(period[2]) if quota and period else now + timedelta(seconds=90)
                with connect(self.settings.database_url) as c:
                    c.execute("""INSERT INTO model_provider_cooldowns(scope,blocked_until,reason)
                        VALUES (%s,%s,%s) ON CONFLICT(scope) DO UPDATE SET
                        blocked_until=GREATEST(model_provider_cooldowns.blocked_until,EXCLUDED.blocked_until),
                        reason=EXCLUDED.reason,updated_at=now()""",
                        ('openai' if quota else f'openai:{self.model}',until,
                         'ORGANIZATION_SPEND_LIMIT' if quota else 'RATE_LIMIT'))
            raise


def quota_client(settings: Any, group: str) -> OpenAIMeetingBriefClient:
    model = {'mini': settings.openai_mini_model, 'main': settings.openai_integration_model,
             'paid': settings.openai_advanced_model}[group]
    # Eligibility is an exact allowlist from this organization's account banner.
    if model != {'mini': 'gpt-5.4-mini', 'main': 'gpt-5.4', 'paid': 'gpt-6.1-terra'}[group]:
        raise ValueError('Model requires a reviewed budget classification')

    def reserve(tokens: int):
        with connect(settings.database_url) as c:
            blocked = c.execute("SELECT 1 FROM model_provider_cooldowns WHERE scope=ANY(%s) AND blocked_until>now()",
                                (['openai', f'openai:{model}'],)).fetchone()
        if blocked:
            error = DailyTokenLimitReached('PROVIDER_COOLDOWN')
            error.skip_input_count = True
            raise error
        if group != 'paid':
            cap = daily_limit(settings, group)
            if cap < 1:
                error = DailyTokenLimitReached('GROUP_ALLOCATION_EXHAUSTED')
                error.skip_input_count = True
                raise error
            with connect(settings.database_url) as c:
                return OpenAIGroupBudget(c, group).reserve(tokens, cap)
        period = credit_period(settings)
        if period is None:
            error = DailyTokenLimitReached('PROMOTIONAL_CREDIT_UNCONFIRMED_OR_EXPIRED')
            error.skip_input_count = True
            raise error
        grant_id, allowance, _ = period
        # Upper bound at the highest Standard Terra token rate (long-context output).
        amount = Decimal(tokens) * Decimal('0.0000075')
        with connect(settings.database_url) as c:
            row = c.execute('''INSERT INTO openai_credit_grant_usage(grant_id,reserved_usd)
                SELECT %s,%s WHERE %s <= %s
                ON CONFLICT(grant_id) DO UPDATE
                SET reserved_usd=openai_credit_grant_usage.reserved_usd+EXCLUDED.reserved_usd,updated_at=now()
                WHERE openai_credit_grant_usage.spent_usd+openai_credit_grant_usage.unknown_usd
                    +openai_credit_grant_usage.reserved_usd+EXCLUDED.reserved_usd <= %s
                RETURNING grant_id''', (grant_id,amount,amount,allowance,allowance)).fetchone()
        if not row:
            raise DailyTokenLimitReached('PROMOTIONAL_CREDIT_BUDGET_EXHAUSTED')
        return row[0]

    def settle(period: Any, tokens: int, metadata: Any):
        with connect(settings.database_url) as c:
            if group != 'paid':
                OpenAIGroupBudget(c, group).settle(period, tokens, metadata)
                return
            usage = token_usage_from_metadata(metadata)
            long = usage['input_tokens'] > 272_000
            # Ignore cache discounts: conservative budget accounting.
            cost = (Decimal(usage['input_tokens']) * (2 if long else 1)
                    + Decimal(usage['output_tokens']) * (Decimal('7.5') if long else 5)) / 1_000_000
            details = ((metadata or {}).get('usage') or {}).get('prompt_tokens_details') or {}
            writes = max(0, int(details.get('cache_write_tokens') or 0))
            # Use 12h retention pricing as an upper bound when retention is not reported.
            cost += Decimal(writes) * (Decimal('3') if long else Decimal('1.5')) / 1_000_000
            amount = Decimal(tokens) * Decimal('0.0000075')
            known = usage['total_tokens'] > 0 or bool((metadata or {}).get('request_rejected'))
            row = c.execute('''UPDATE openai_credit_grant_usage
                SET spent_usd=spent_usd+%s,unknown_usd=unknown_usd+%s,
                    reserved_usd=reserved_usd-%s,request_count=request_count+1,updated_at=now()
                WHERE grant_id=%s AND reserved_usd >= %s''',
                (cost if known else 0, 0 if known else amount, amount, period, amount))
            if row.rowcount != 1:
                raise RuntimeError('Credit reservation could not be settled')

    client = GroupedOpenAIClient(settings.openai_api_key, model=model,
        base_url=settings.openai_base_url, reserve_tokens=reserve, settle_tokens=settle)
    client.settings = settings
    client.reasoning_effort = 'none' if group == 'mini' else 'medium'
    return client


def pool(settings: Any, workload: str = 'general') -> list[Any]:
    if workload in {'integration', 'verification'}:
        result = [quota_client(settings, 'main')] if settings.openai_api_key else []
        if settings.openai_api_key and credit_active(settings):
            result.append(quota_client(settings, 'paid'))
        return result
    result = [quota_client(settings, 'mini')] if settings.openai_api_key else []
    if settings.openrouter_api_key:
        result.append(OpenRouterMeetingBriefClient(settings.openrouter_api_key,
            model=settings.meeting_brief_model, base_url=settings.openrouter_base_url))
    return result


class WorkloadBriefClient(OpenAIMeetingBriefClient):
    """Preserve the existing report contract and validation; route each request."""
    def __init__(self, settings: Any):
        self.settings = settings
        self.model = settings.openai_integration_model
        self.responses: list[dict[str, Any]] = []
        self.escalated_schemas: set[str] = set()

    def on_quality_failure(self, schema_name: str) -> None:
        self.escalated_schemas.add(schema_name)

    def _post(self, prompt, schema, schema_name, model_override=None):
        workload = 'integration' if schema_name in INTEGRATION or 'topic_report' in schema_name else 'general'
        candidates = pool(self.settings, workload)
        if not candidates:
            raise DailyTokenLimitReached('NO_MODEL_AVAILABLE')
        if schema_name in self.escalated_schemas and workload == 'integration' and len(candidates) > 1:
            candidates = candidates[1:]
        last = None
        for client in candidates:
            try:
                data, usage = client._post(prompt, schema, schema_name)
                usage = {**usage, 'provider': client.provider, 'model': client.model,
                         'workload': schema_name}
                self.responses.append(usage)
                return data, usage
            except Exception as exc:
                last = exc
        raise last


def usage_groups(settings: Any, connection: Any, *, router_left: int, router_limit: int,
                 mistral_left: float) -> list[dict[str, Any]]:
    entries = {}
    for group, label in [('mini', 'GPT-5.4 mini'), ('main', 'GPT-5.4')]:
        usage = OpenAIGroupBudget(connection, group).today()
        cap = daily_limit(settings, group)
        left = max(0, cap-usage['total_tokens']-usage['unknown_tokens']-usage['reserved_tokens'])
        entries[group] = {'id': group, 'label': label, 'remaining': left, 'limit': cap,
            'unit': 'tokens', 'scope': 'POC7_10_11_SHARED', 'period': 'DAILY_UTC', **usage}
    period = credit_period(settings)
    grant_id, allowance, expiry = period or ('',0,None)
    grant = connection.execute("""SELECT spent_usd,reserved_usd,unknown_usd
        FROM openai_credit_grant_usage WHERE grant_id=%s""", (grant_id,)).fetchone()
    active = period is not None
    paid = {'id':'terra', 'label':'6.1 Terra', 'unit':'USD', 'period':'CREDIT_GRANT',
        'scope':'POC7_10_11_SHARED', 'status':'AVAILABLE' if active else 'CREDIT_UNCONFIRMED',
        'limit':max(allowance,settings.openai_credit_monthly_budget_usd) if active else None,
        'opening_remaining_usd':allowance if active else None,
        'remaining':max(0, allowance-float(sum(grant or (0,0,0)))) if active else None,
        'expires_at':expiry, 'renewal_basis':'USER_CONFIGURED_MONTH_START_KST' if settings.openai_credit_month_start_renewal else 'USER_CONFIGURED_MONTH_END_KST'}
    return [
        {'id':'realtime','label':'실시간 부분요약','models':[entries['mini'],
            {'id':'openrouter','label':({'nvidia/nemotron-3.5-super-vl:free':'Nemo3.5 VL','dots-studio/dots-3-note-preview:free':'Dots3 Note'}.get(settings.llm_model,settings.llm_model.rsplit('/',1)[-1].split(':')[0][:10])),'model':settings.llm_model,'provider':'OpenRouter','remaining':router_left,'limit':router_limit,
             'unit':'requests','scope':'SHARED_GATEWAY','period':'DAILY_UTC'}]},
        {'id':'integration','label':'통합+공식자료 대조','models':[entries['main'],paid]},
        {'id':'audio','label':'음성','models':[
            {'id':'mistral','label':'Mistral','remaining':max(0,mistral_left),
             'limit':settings.mistral_monthly_credit_usd,'unit':'USD','scope':'POC7_ALLOCATION','period':'MONTHLY'}]},
    ]
