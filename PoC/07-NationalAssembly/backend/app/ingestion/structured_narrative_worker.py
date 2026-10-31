"""Explicit, single-report narrative repair; never schedules other reports."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import argparse
import json
import time
from itertools import count
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..config import get_settings
from ..db.connection import connect
from ..db.meeting_brief_repository import MeetingBriefRepository
from ..db.topic_structure_repository import TopicStructureRepository
from ..db.summary_repository import SummaryRepository
from ..db.openai_daily_budget import DailyTokenLimitReached
from ..services.structured_narrative import PROFILE, BATCH_START, inputs, saved, prompt, corrective_prompt, schema, validate, valid_subset, pending_batches, field_repair_prompt, merge_field_repair
from ..services.structure_retry import retry_allowance
from ..services.provider_retry_gate import blocked_provider
from ..services.narrative_retry import transient_delay
from .topic_structure_worker import clients, pace_nim


def post_with_nim_retry(client: Any, batch: list[dict[str, Any]], corrective: bool = False,
                        feedback: dict[str, Any] | None = None,
                        field_plan: dict[str, Any] | None = None) -> tuple[dict, dict]:
    make_prompt = (lambda items: corrective_prompt(items, feedback)) if corrective else prompt
    make_schema = schema
    if field_plan:
        make_prompt = lambda items: field_repair_prompt(field_plan)
        make_schema = lambda items: {'type': 'object', 'properties': {
            key: {'type': 'string'} for key in field_plan['fields']},
            'required': field_plan['fields'], 'additionalProperties': False}
    if client.provider == 'groq' and hasattr(client, 'fits_request'):
        # Work on complete issues, including every source/context. The caller's
        # validated-subset path persists these and leaves remaining issues pending.
        selected = []
        for issue in batch:
            candidate = selected + [issue]
            if client.fits_request(make_prompt(candidate), make_schema(candidate)):
                selected = candidate
        if not selected:
            from ..db.auxiliary_model_budget import AuxiliaryUnavailable
            raise AuxiliaryUnavailable('AUXILIARY_INPUT_TOO_LARGE')
        batch = selected
    # A slow NIM response is not a daily quota. Retry it once before fallback.
    if client.provider == 'nvidia':
        client.timeout_seconds = max(getattr(client, 'timeout_seconds', 120), 240)
    for attempt in range(2):
        pace_nim(client)
        try:
            instruction = make_prompt(batch)
            response, usage = client._post(instruction, make_schema(batch), 'structured_narrative')
            if field_plan:
                return merge_field_repair(field_plan, response), {**usage, 'field_repair_raw_response': response}
            return response, usage
        except Exception as exc:
            delay = transient_delay(exc) if client.provider == 'nvidia' else None
            if attempt or delay is None or delay > 60:
                if delay is not None:
                    exc.retry_after_seconds = delay
                raise
            print(json.dumps({'event': 'structured_narrative.nim_retry', 'delay_seconds': delay,
                              'error': type(exc).__name__}), flush=True)
            time.sleep(delay)
    raise RuntimeError('unreachable')


def process_one(broadcast_id: Any, batch_limit: int = 2) -> dict[str, Any]:
    from .meeting_brief_worker import safe_brief_error_code
    from .narrative_jobs import background_defer_reason
    settings = get_settings()
    label = str(broadcast_id)
    with connect(settings.database_url) as lease:
        lock = 'topic-structure:' + label
        if not lease.execute('SELECT pg_try_advisory_lock(hashtext(%s))', (lock,)).fetchone()[0]:
            return {'status': 'BUSY', 'broadcast_id': label}
        try:
            with connect(settings.database_url) as c:
                state = c.execute('SELECT lifecycle_status FROM live_broadcasts WHERE id=%s', (broadcast_id,)).fetchone()
                if not state or state[0] != 'ENDED':
                    return {'status': 'LIVE_DEFERRED', 'broadcast_id': label}
                item = MeetingBriefRepository(c).latest(broadcast_id)
                repo = TopicStructureRepository(c)
                brief = repo.ready_current(item) if item else None
                if not brief:
                    return {'status': 'STRUCTURE_PENDING', 'broadcast_id': label}
                sid = brief['topic_structure']['revision_id']
                history = repo.batches(sid)
                snapshot = repo.snapshot(sid)
            issues = inputs(brief, snapshot)
            done = saved(issues, [(h['index'], h['request'], h['response'])
                                 for h in history if h['status'] == 'READY'])
            if issues and len(done) == len(issues):
                return {'status': 'COMPLETE', 'broadcast_id': label, 'issues': len(done)}
            pending = [issue for issue in issues if issue['id'] not in done]
            batches, blocked = pending_batches(pending, history)
            if not batches:
                return {'status': 'REVIEW_REQUIRED' if blocked else 'NO_ISSUES',
                        'broadcast_id': label, 'blocked_issues': blocked}
            first_index = max([BATCH_START - 1] + [h['index'] for h in history]) + 1
            indices = count(first_index)
            def run_batch(request):
                batch = request['issues']
                prior = [h for h in history if h['request'] == request]
                allowed = retry_allowance(prior)
                if not allowed:
                    later_allowed = retry_allowance(prior, now=datetime.now(timezone.utc) + timedelta(days=1))
                    return {'status': 'RETRY_DEFERRED' if later_allowed else 'REVIEW_REQUIRED',
                            'broadcast_id': label, 'summarized': len(done)}
                # Isolated final validation repairs are hard verification work.
                # Keep the general pool for ordinary summaries; verification only
                # adds OpenAI when OpenRouter is exhausted, under existing budgets.
                pool = clients("verification") if request.get('repair_round') == 4 else clients()
                if not pool:
                    return {'status': 'NO_PROVIDER', 'broadcast_id': label}
                allowed = retry_allowance(prior, round_size=len(pool))
                index = prior[0]['index'] if prior else next(indices)
                attempt_base = max((h['attempt'] for h in prior), default=0)
                error, retry_after_seconds = None, 0
                for retry in range(allowed):
                    reason = background_defer_reason()
                    if reason:
                        return {'status': 'LIVE_DEFERRED', 'broadcast_id': label, 'reason': reason}
                    client = pool[retry % len(pool)]
                    blocked = blocked_provider(client, prior)
                    if blocked:
                        error = blocked
                        continue
                    response, usage, error = {}, {}, None
                    try:
                        response, usage = post_with_nim_retry(client, batch, bool(request.get('repair_round')),
                                                             request.get('validation_feedback'), request.get('field_repair'))
                        if client.provider == 'nvidia':
                            with connect(settings.database_url) as c:
                                SummaryRepository(c).record_monthly_token_usage('nvidia', client.model, usage)
                        validate(batch, response)
                    except DailyTokenLimitReached:
                        with connect(settings.database_url) as c:
                            TopicStructureRepository(c).record(sid,index,attempt_base+retry+1,request,{},
                                {'provider':client.provider,'model':client.model,'attempted_model':client.model,'additional_model_calls':0},'DAILY_TOKEN_LIMIT')
                        prior.append({'usage':{'provider':client.provider,'attempted_model':client.model},'error':'DAILY_TOKEN_LIMIT','created_at':datetime.now(timezone.utc)})
                        if getattr(settings, "model_workload_groups_enabled", False) and retry + 1 < allowed:
                            continue
                        return {'status': 'BUDGET_DEFERRED', 'broadcast_id': label,
                                'provider': client.provider, 'reason': 'UTC_DAILY_TOKEN_LIMIT'}
                    except Exception as exc:
                        error = str(exc) if isinstance(exc, ValueError) else safe_brief_error_code(exc)
                        usage = usage or getattr(exc, 'usage_metadata', {})
                        retry_after_seconds = max(retry_after_seconds, getattr(exc, 'retry_after_seconds', 0))
                    usage = {**usage,'provider':client.provider,'attempted_model':client.model,
                             'retry_after_seconds':retry_after_seconds}
                    usage.setdefault('model',client.model)
                    with connect(settings.database_url) as c:
                        TopicStructureRepository(c).record(sid, index, attempt_base + retry + 1,
                                                           request, response, usage, error)
                        subset = valid_subset(batch, response) if error else []
                        if subset:
                            partial_request = {**request, 'issues': subset,
                                               'salvaged_from': [index, attempt_base + retry + 1]}
                            TopicStructureRepository(c).record(sid, next(indices), 1, partial_request,
                                {i['id']: response[i['id']] for i in subset},
                                {'method': 'VALIDATED_SUBSET', 'additional_model_calls': 0}, None)
                    prior.append({'usage':usage,'error':error,'created_at':datetime.now(timezone.utc)})
                    print(json.dumps({'event': 'structured_narrative.batch', 'broadcast_id': label,
                        'issues': len(batch), 'completed_before': len(done), 'total': len(issues),
                        'provider': client.provider, 'error': error}, ensure_ascii=False), flush=True)
                    if subset:
                        # Do not resend seven good issues to another provider
                        # because one failed. The next pass isolates only failures.
                        return {'status': 'PARTIAL', 'broadcast_id': label, 'error': error,
                                'salvaged_issues': len(subset)}
                    if not error:
                        break
                transient = error in {'ReadTimeout', 'ConnectTimeout', 'ConnectionError', 'ConnectError',
                                      'HTTPError:HTTP_429', 'HTTPError:HTTP_500', 'HTTPError:HTTP_502',
                                      'HTTPError:HTTP_503', 'HTTPError:HTTP_504','DAILY_TOKEN_LIMIT','AUXILIARY_DAILY_LIMIT','AUXILIARY_RATE_WAIT','AUXILIARY_INPUT_TOO_LARGE'}
                return {'status': ('RETRY_DEFERRED' if transient else 'PARTIAL') if error else 'READY',
                        'broadcast_id': label, 'error': error, 'retry_after_seconds': retry_after_seconds}
            # The report lock covers the whole pool. Batch IDs are allocated before
            # work starts; shared NIM pacing and provider budgets still apply.
            with ThreadPoolExecutor(max_workers=3) as pool:
                results = list(pool.map(run_batch, batches[:batch_limit]))
            with connect(settings.database_url) as c:
                final = TopicStructureRepository(c).ready_current(item)
            return {'status': final['narrative_coverage']['status'], 'broadcast_id': label,
                    'coverage': final['narrative_coverage'], 'batches': results}
        finally:
            lease.execute('SELECT pg_advisory_unlock(hashtext(%s))', (lock,))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--broadcast-id', required=True)
    parser.add_argument('--batch-limit', type=int, default=2)
    parser.add_argument('--enqueue', action='store_true', help='Persist this explicitly authorized repair and resume after quota reset')
    args = parser.parse_args()
    if args.enqueue:
        from .narrative_jobs import enqueue, process_due
        enqueue(args.broadcast_id)
        result = process_due(args.broadcast_id, args.batch_limit)
    else:
        result = process_one(args.broadcast_id, args.batch_limit)
    print(json.dumps(result, ensure_ascii=False), flush=True)
