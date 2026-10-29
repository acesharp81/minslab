"""Protect final integration capacity while ordinary work stays in the free pool."""
from __future__ import annotations
from typing import Any
from ..db.connection import connect
from ..db.openai_daily_budget import OpenAIDailyBudget, DailyTokenLimitReached

INTEGRATION_SCHEMAS = frozenset({'meeting_brief','meeting_reduction','discussion_structure_consolidation'})


def openai_limit(settings: Any, schema_name: str) -> int:
    limit = int(settings.openai_daily_token_limit)
    protected = min(limit, max(0, int(getattr(settings,'openai_integration_reserved_tokens',100000))))
    return limit if schema_name in INTEGRATION_SCHEMAS else limit-protected


def reserve_openai_workload(settings: Any, estimated_tokens: int, schema_name: str):
    # Retain the user's shared-OpenRouter-exhaustion rule at admission time.
    from ..ingestion.meeting_brief_worker import require_openai_fallback
    require_openai_fallback(settings)
    limit = openai_limit(settings,schema_name)
    output = 20000 if schema_name in {'meeting_brief','discussion_structure_consolidation'} else 8000
    with connect(settings.database_url) as c:
        budget=OpenAIDailyBudget(c);usage=budget.today()
        used=usage['total_tokens']+usage['unknown_tokens']+usage['reserved_tokens']
        if limit-used < output:
            error=DailyTokenLimitReached('OPENAI_INTEGRATION_CAPACITY_PROTECTED' if schema_name not in INTEGRATION_SCHEMAS else 'OPENAI_OUTPUT_BUDGET_UNAVAILABLE')
            error.skip_input_count=True
            raise error
        return budget.reserve(estimated_tokens,limit)
