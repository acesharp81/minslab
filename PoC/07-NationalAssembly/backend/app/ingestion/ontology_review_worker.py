"""Bounded ontology review on the existing database and meeting worker."""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..config import get_settings
from ..db.connection import connect
from ..db.live_repository import LiveRepository
from ..db.meeting_brief_repository import MeetingBriefRepository
from ..db.official_integration_repository import OfficialIntegrationRepository
from ..db.openai_daily_budget import DailyTokenLimitReached
from ..db.summary_repository import SummaryRepository
from ..db.topic_structure_repository import TopicStructureRepository
from ..services.meeting_topic_groups import TARGET_ONTOLOGY, _ontology_match
from ..services.ontology_context import match_topic_context
from ..services.ontology_sources import select_current_ontology_brief
from ..services.ontology_semantic import (
    PROFILE, BATCH_START, catalog_snapshot, review_input, prompt, schema,
    validate_proposals, validate_verification,
)
from .topic_structure_worker import clients, pace_nim


def counts_failure(batch: dict[str, Any]) -> bool:
    return batch['status'] == 'FAILED' and batch.get('error') not in {
        'NIM_RATE_DEFERRED', 'HTTPError:HTTP_429', 'DAILY_TOKEN_LIMIT',
        'VERIFICATION_PENDING',
    }


def is_rate_limited(error: Exception) -> bool:
    response = getattr(error, 'response', None)
    return getattr(response, 'status_code', getattr(error, 'code', None)) == 429


def pending_items(brief: dict[str, Any], prior: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failed: dict[str, int] = {}
    today = datetime.now(timezone.utc).date()
    for batch in prior:
        created = batch.get('created_at')
        if isinstance(created, datetime) and created.astimezone(timezone.utc).date() < today:
            continue
        if batch['index'] >= BATCH_START and counts_failure(batch) and batch['request'].get('profile') == PROFILE:
            for item in batch['request'].get('items', []):
                failed[item['fingerprint']] = failed.get(item['fingerprint'], 0) + 1
    pending = []
    for topic in brief.get('topics', []):
        if _ontology_match(topic) or match_topic_context(topic, TARGET_ONTOLOGY):
            continue
        item = review_input(topic, TARGET_ONTOLOGY)
        cached = topic.get('ontology_semantic_review') or {}
        if item and cached.get('fingerprint') != item['fingerprint'] and failed.get(item['fingerprint'], 0) < 3:
            pending.append(item)
    return pending


def selected_structure(connection: Any, item: dict[str, Any]) -> dict[str, Any] | None:
    context = LiveRepository(connection).broadcast_official_context(item['broadcast_id'])
    document = (context or {}).get('official_document_id')
    integration = OfficialIntegrationRepository(connection).latest_for_brief_document(item['brief_id'], document) if document else None
    if select_current_ontology_brief(item, integration, document)[1] != 'PROVISIONAL':
        return None
    return TopicStructureRepository(connection).ready_current(item)


def process_one(broadcast_id: Any, batch_limit: int = 1) -> dict[str, Any]:
    from .meeting_brief_worker import safe_brief_error_code
    settings = get_settings()
    label = str(broadcast_id)
    with connect(settings.database_url) as lease:
        lock = 'topic-structure:' + label
        if not lease.execute('SELECT pg_try_advisory_lock(hashtext(%s))', (lock,)).fetchone()[0]:
            return {'status': 'BUSY', 'broadcast_id': label}
        try:
            with connect(settings.database_url) as c:
                cooldown = c.execute("SELECT EXISTS(SELECT 1 FROM meeting_topic_structure_batches "
                                     "WHERE batch_index>=200000 AND error_code IN ('NIM_RATE_DEFERRED','HTTPError:HTTP_429') "
                                     "AND usage_metadata->>'provider'='nvidia' AND created_at>now()-interval '120 seconds')").fetchone()[0]
                state = c.execute('SELECT lifecycle_status FROM live_broadcasts WHERE id=%s', (broadcast_id,)).fetchone()
                if not state or state[0] != 'ENDED':
                    return {'status': 'LIVE_DEFERRED', 'broadcast_id': label}
                item = MeetingBriefRepository(c).latest(broadcast_id)
                brief = selected_structure(c, item) if item else None
                if not brief:
                    return {'status': 'NO_CURRENT_STRUCTURE', 'broadcast_id': label}
                structure_id = brief['topic_structure']['revision_id']
                prior = TopicStructureRepository(c).batches(structure_id)
            pending = pending_items(brief, prior)
            next_index = max([BATCH_START - 1] + [x['index'] for x in prior if BATCH_START <= x['index'] < 400000]) + 1
            completed = accepted = 0
            base_pool = clients("verification")
            nim_retry_at = time.monotonic() + 120 if cooldown else 0
            if pending and not base_pool:
                return {'status': 'NO_PROVIDER', 'broadcast_id': label}
            while pending and completed < batch_limit:
                pool = [client for client in base_pool
                        if client.provider != 'nvidia' or time.monotonic() >= nim_retry_at]
                if not pool:
                    return {'status': 'RATE_DEFERRED', 'broadcast_id': label}
                batch = pending[:16]
                request = {'profile': PROFILE, 'catalog': catalog_snapshot(TARGET_ONTOLOGY), 'items': batch}
                success = False
                # Persist each response, including a proposal whose verification failed.
                prior_failures = max((sum(counts_failure(x) and (not isinstance(x.get('created_at'), datetime) or x['created_at'].astimezone(timezone.utc).date() == datetime.now(timezone.utc).date()) and x['request'].get('profile') == PROFILE
                                           and any(i.get('fingerprint') == b['fingerprint'] for i in x['request'].get('items', []))
                                          for x in prior if x['index'] >= BATCH_START) for b in batch), default=0)
                errors = []
                for attempt in range(1, len(pool) + 1):
                    client = pool[(prior_failures + attempt - 1) % len(pool)]
                    response: dict[str, Any] = {}
                    metadata: dict[str, Any] = {'provider': client.provider, 'model': client.model}
                    error = None
                    try:
                        for stage in ('proposals', 'verification'):
                            pace_nim(client)
                            data, usage = client._post(
                                prompt(batch, TARGET_ONTOLOGY, response.get('proposals') if stage == 'verification' else None),
                                schema(batch, verification=stage == 'verification'), 'ontology_' + stage,
                            )
                            response[stage], metadata[stage] = data, usage
                            if client.provider == 'nvidia':
                                with connect(settings.database_url) as c:
                                    SummaryRepository(c).record_monthly_token_usage('nvidia', client.model, usage)
                            if stage == 'proposals':
                                validate_proposals(batch, data, TARGET_ONTOLOGY)
                                # Preserve the first raw response before another network call.
                                with connect(settings.database_url) as c:
                                    TopicStructureRepository(c).record(
                                        structure_id, next_index, attempt * 2 - 1, request,
                                        response, metadata, 'VERIFICATION_PENDING',
                                    )
                            else:
                                validate_verification(batch, data)
                    except DailyTokenLimitReached:
                        error = 'DAILY_TOKEN_LIMIT'
                    except Exception as exc:
                        error = safe_brief_error_code(exc)
                        if client.provider == 'nvidia' and is_rate_limited(exc):
                            error = 'NIM_RATE_DEFERRED'
                            nim_retry_at = time.monotonic() + 120
                            upstream = getattr(exc, 'response', None)
                            if upstream is not None:
                                metadata['rate_limit_response'] = upstream.text[:2000]
                        metadata['failure_usage'] = getattr(exc, 'usage_metadata', {})
                    with connect(settings.database_url) as c:
                        TopicStructureRepository(c).record(structure_id, next_index, attempt * 2, request, response, metadata, error)
                    if error:
                        errors.append(error)
                    if error == 'DAILY_TOKEN_LIMIT':
                        continue
                    if error == 'NIM_RATE_DEFERRED':
                        if len(pool) == 1:
                            return {'status': 'RATE_DEFERRED', 'broadcast_id': label}
                        continue
                    if not error:
                        count = 0
                        for b in batch:
                            proposal, verification = response['proposals'][b['topic_id']], response['verification'][b['topic_id']]
                            if (verification['approve'] and proposal['target'] != 'UNRESOLVED'
                                and verification['target'] == proposal['target']
                                and len(verification['support_quote'].strip()) >= 12
                                and verification['support_quote'] in b['spans'][proposal['span_index']]['quote']):
                                count += 1
                        accepted += count
                        print(json.dumps({'event': 'ontology_review.batch', 'broadcast_id': label, 'batch': next_index,
                                          'reviewed': len(batch), 'accepted': count, 'provider': client.provider}), flush=True)
                        success = True
                        break
                if not success:
                    return {'status': 'BUDGET_DEFERRED' if errors and all(e == 'DAILY_TOKEN_LIMIT' for e in errors) else 'REVIEW_REQUIRED', 'broadcast_id': label, 'error': error}
                pending = pending[len(batch):]
                next_index += 1
                completed += 1
            return {'status': 'PROCESSING' if pending else 'COMPLETED', 'broadcast_id': label,
                    'batches': completed, 'accepted': accepted, 'remaining': len(pending)}
        finally:
            lease.execute('SELECT pg_advisory_unlock(hashtext(%s))', (lock,))


def process_available(limit: int = 1, batch_limit: int = 1, workers: int = 1) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.ai_enrichment_enabled:
        return []
    ids = []
    with connect(settings.database_url) as c:
        ended = {str(r[0]) for r in c.execute("SELECT id FROM live_broadcasts WHERE lifecycle_status='ENDED'").fetchall()}
        for item in MeetingBriefRepository(c).latest_all():
            if str(item['broadcast_id']) not in ended:
                continue
            brief = selected_structure(c, item)
            if brief and pending_items(brief, TopicStructureRepository(c).batches(brief['topic_structure']['revision_id'])):
                ids.append(item['broadcast_id'])
            if len(ids) >= limit:
                break
    def run(identifier: Any) -> dict[str, Any]:
        try:
            return process_one(identifier, batch_limit)
        except Exception as exc:
            from .meeting_brief_worker import safe_brief_error_code
            return {'status': 'FAILED', 'broadcast_id': str(identifier), 'error': safe_brief_error_code(exc)}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        return list(executor.map(run, ids))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--broadcast-id')
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--batch-limit', type=int, default=1)
    parser.add_argument('--drain', action='store_true')
    args = parser.parse_args()
    while True:
        result = (process_one(args.broadcast_id, args.batch_limit) if args.broadcast_id else
                  process_available(100 if args.all else 1, args.batch_limit, 1))
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if not args.drain or not result or args.broadcast_id:
            return
        if any(x['status'] in {'BUDGET_DEFERRED', 'FAILED', 'NO_PROVIDER'} for x in result):
            return
        time.sleep(30)


if __name__ == '__main__':
    main()
