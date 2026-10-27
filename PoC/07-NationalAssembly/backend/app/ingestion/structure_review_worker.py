"""Automatically resolve pending source facets on the existing meeting worker."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..config import get_settings
from ..db.connection import connect
from ..db.meeting_brief_repository import MeetingBriefRepository
from ..db.topic_structure_repository import TopicStructureRepository
from ..db.summary_repository import SummaryRepository
from ..db.openai_daily_budget import DailyTokenLimitReached
from ..services.structure_review import (
    PROFILE, VERIFY_PROFILE, BATCH_START, review_candidates, review_prompt, review_schema, validated_review, valid_review_subset,
)
from ..services.structure_retry import retry_allowance, retry_pool
from ..services.topic_structure import materialize
from .topic_structure_worker import clients, pace_nim


def process_one(broadcast_id: Any, batch_limit: int = 1) -> dict[str, Any]:
    from .meeting_brief_worker import safe_brief_error_code
    settings = get_settings()
    label = str(broadcast_id)
    with connect(settings.database_url) as lease:
        lock = 'topic-structure:' + label
        if not lease.execute('SELECT pg_try_advisory_lock(hashtext(%s))', (lock,)).fetchone()[0]:
            return {'status': 'BUSY', 'broadcast_id': label}
        try:
            completed = 0
            while completed < batch_limit:
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
                    prior = repo.batches(sid)
                    snapshot = repo.snapshot(sid)
                    pending = review_candidates(brief, snapshot, prior)
                if not pending:
                    return {'status': 'COMPLETED', 'broadcast_id': label, 'batches': completed}
                for old in reversed(prior):
                    if old.get('error') != 'REVIEW_TOPIC_SOURCE_MISMATCH':
                        continue
                    try:
                        pending_ids = {i['atom']['id'] for i in pending if i['profile'] == old['request'].get('profile')}
                        recovered = valid_review_subset(old['request'], old['response'], snapshot, pending_ids)
                    except (KeyError, ValueError, TypeError):
                        continue
                    if recovered:
                        index = max([BATCH_START - 1] + [h['index'] for h in prior if h['index'] >= BATCH_START]) + 1
                        with connect(settings.database_url) as c:
                            TopicStructureRepository(c).record(sid,index,1,*recovered,
                                {'method':'VALIDATED_REVIEW_SUBSET','source_index':old['index'],
                                 'source_attempt':old['attempt'],'additional_model_calls':0},None)
                        return {'status':'PROCESSING','broadcast_id':label,'batches':completed,
                                'recovered_atoms':len(recovered[0]['atoms'])}
                profile = pending[0]['profile']
                batch = [i for i in pending if i['profile'] == profile][:4]
                request = {'profile': profile, 'schema_revision': 2,
                           'atoms': [i['atom'] for i in batch],
                           'targets': [f for i in batch for f in i['targets']],
                           'catalog': [{'parent': g['title'], 'issue': t['title']}
                               for g in brief['topic_groups'] for t in brief['topics']
                               if t['id'] in g['topic_ids']][:200]}
                histories = [[h for h in prior if h['request'].get('profile') == profile
                              and i['atom']['id'] in [a['id'] for a in h['request'].get('atoms', [])]] for i in batch]
                index = max([BATCH_START - 1] + [h['index'] for h in prior if h['index'] >= BATCH_START]) + 1
                pool = clients("verification")
                if profile == VERIFY_PROFILE:
                    # A substantive source retained as uncertain gets one independent model pass.
                    pool = [p for p in pool if p.provider != 'nvidia'] or pool
                if not pool:
                    return {'status': 'NO_PROVIDER', 'broadcast_id': label}
                round_pool = retry_pool(pool, histories)
                errors = []
                for attempt, client in enumerate(round_pool, start=1):
                    response, usage, error = {}, {}, None
                    sent_request = deepcopy(request)
                    try:
                        pace_nim(client)
                        response, usage = client._post(review_prompt(request), review_schema(request['atoms']), 'discussion_context_review')
                        if client.provider == 'nvidia':
                            with connect(settings.database_url) as c:
                                SummaryRepository(c).record_monthly_token_usage('nvidia', client.model, usage)
                        verified = validated_review(request, response)
                        probe = materialize({'topics': [], 'tasks': []}, snapshot, verified, [], 'review-validation')
                        unsupported = [f for f in probe['topic_structure']['uncertain'] if f.get('uncertainty_reason')]
                        if unsupported:
                            request['validation_feedback'] = [
                                {'issue': f['issue'], 'reason': f['uncertainty_reason']} for f in unsupported]
                            raise ValueError('REVIEW_TOPIC_SOURCE_MISMATCH')
                    except DailyTokenLimitReached:
                        error = 'DAILY_TOKEN_LIMIT'
                    except Exception as exc:
                        error = str(exc) if isinstance(exc, ValueError) else safe_brief_error_code(exc)
                        usage = usage or getattr(exc, 'usage_metadata', {})
                    with connect(settings.database_url) as c:
                        TopicStructureRepository(c).record(sid, index, attempt, sent_request, response,
                            {**usage, 'provider': client.provider, 'model': client.model}, error)
                    print(json.dumps({'event': 'structure_review.batch', 'broadcast_id': label,
                                      'atoms': len(batch), 'provider': client.provider, 'error': error}), flush=True)
                    if not error:
                        break
                    errors.append(error)
                else:
                    return {'status': 'BUDGET_DEFERRED' if errors and all(e == 'DAILY_TOKEN_LIMIT' for e in errors) else 'RETRY_DEFERRED', 'broadcast_id': label, 'batches': completed}
                completed += 1
            return {'status': 'PROCESSING', 'broadcast_id': label, 'batches': completed}
        finally:
            lease.execute('SELECT pg_advisory_unlock(hashtext(%s))', (lock,))


def process_available(limit: int = 1, batch_limit: int = 1, workers: int = 1) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.ai_enrichment_enabled:
        return []
    ids = []
    with connect(settings.database_url) as c:
        repo = TopicStructureRepository(c)
        ended = {str(r[0]) for r in c.execute("SELECT id FROM live_broadcasts WHERE lifecycle_status='ENDED'").fetchall()}
        for item in sorted(MeetingBriefRepository(c).latest_all(), key=lambda i: i['generated_at'], reverse=True):
            if str(item['broadcast_id']) not in ended:
                continue
            brief = repo.ready_current(item)
            if not brief:
                continue
            sid = brief['topic_structure']['revision_id']
            if review_candidates(brief, repo.snapshot(sid), repo.batches(sid)):
                ids.append(item['broadcast_id'])
            if len(ids) >= limit:
                break
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 3))) as executor:
        return list(executor.map(lambda bid: process_one(bid, batch_limit), ids))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--broadcast-id')
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--batch-limit', type=int, default=1)
    parser.add_argument('--workers', type=int, default=1)
    args = parser.parse_args()
    result = process_one(args.broadcast_id, args.batch_limit) if args.broadcast_id else process_available(100 if args.all else 1, args.batch_limit, args.workers)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
