"""Bounded, resumable structure processing on the existing meeting worker."""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..config import get_settings
from ..db.connection import connect
from ..db.live_repository import LiveRepository
from ..db.meeting_brief_repository import MeetingBriefRepository
from ..db.migrate import apply_migrations
from ..db.openai_daily_budget import OpenAIDailyBudget, DailyTokenLimitReached
from ..db.summary_repository import SummaryRepository
from ..db.topic_structure_repository import TopicStructureRepository
from ..services.meeting_brief import (
    NvidiaMeetingBriefClient, OpenRouterMeetingBriefClient, OpenAIMeetingBriefClient,
)
from ..services.summary_client import summary_identity
from ..services.structure_retry import retry_allowance
from ..services.topic_structure import (
    build_snapshot, build_prompt, response_schema, validate_response, materialize, issue_catalog,
    consolidation_input, consolidation_prompt, consolidation_schema, apply_consolidation,
    CONSOLIDATION_BATCH, CONSOLIDATION_PROFILE, preserve_unmergeable_issues,
)


def clients(workload: str = "general") -> list[Any]:
    from .meeting_brief_worker import openrouter_brief_has_capacity, require_openai_fallback
    s = get_settings()
    result = []
    router_capacity = openrouter_brief_has_capacity(s)
    if s.meeting_brief_nvidia_enabled and s.nvidia_api_key:
        result.append(NvidiaMeetingBriefClient(
            s.nvidia_api_key, model=s.meeting_brief_nvidia_model, base_url=s.nvidia_base_url,
            min_interval_seconds=max(6.0, s.meeting_brief_nvidia_min_interval_seconds), timeout_seconds=120,
        ))
    if s.openrouter_api_key and router_capacity is not False:
        result.append(OpenRouterMeetingBriefClient(
            s.openrouter_api_key, model=s.meeting_brief_model, base_url=s.openrouter_base_url,
        ))
    from ..services.auxiliary_models import enabled_auxiliaries, AuxiliaryMeetingBriefClient
    result.extend(AuxiliaryMeetingBriefClient(s, p) for p in enabled_auxiliaries(s))
    if workload in {"integration", "verification"} and s.openai_api_key and router_capacity is False:
        def reserve(tokens: int):
            require_openai_fallback(s)
            with connect(s.database_url) as c:
                return OpenAIDailyBudget(c).reserve(tokens, s.openai_daily_token_limit)
        def settle(day: Any, tokens: int, metadata: Any):
            with connect(s.database_url) as c:
                OpenAIDailyBudget(c).settle(day, tokens, metadata)
        from ..services.model_workloads import reserve_openai_workload
        paid = OpenAIMeetingBriefClient(
            s.openai_api_key, model=s.meeting_brief_openai_model, base_url=s.openai_base_url,
            reserve_tokens=reserve, settle_tokens=settle,
            reserve_for_workload=lambda tokens, schema: reserve_openai_workload(s, tokens, schema),
        )
        if workload == "integration":
            result.insert(0, paid)
        else:
            result.append(paid)
    return result


def pace_nim(client: Any) -> None:
    if client.provider != 'nvidia':
        return
    # Across backfill processes: at most 10 starts/minute, leaving room for live work.
    with connect(get_settings().database_url) as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext('topic-structure-nim-rate'))")
        time.sleep(6)


def consolidate_partitioned(item, facets, items, prior):
    from ..services.partitioned_consolidation import PROFILE, BATCH_START, partitions, prompt, schema, normalize
    from .meeting_brief_worker import safe_brief_error_code
    from datetime import datetime, timedelta, timezone
    s=get_settings();sid=item['structure_id'];plan=partitions(items);combined={}
    pool=clients("integration")
    for index,indices in enumerate(plan):
        batch_index=BATCH_START+index
        request={'request_profile':PROFILE,'issues':items,'indices':indices,'partition_count':len(plan)}
        history=[h for h in prior if h['index']==batch_index and h['request']==request]
        good=next((h for h in reversed(history) if h['status']=='READY'),None)
        if not good:
            for previous in reversed(history):
                raw = previous['response'].get('raw_partition_response')
                if previous.get('error') != 'INVALID_PARTITION_MEMBER' or not raw:
                    continue
                try:
                    projected = normalize(items, indices, raw)
                except ValueError:
                    continue
                attempt = max(h['attempt'] for h in history) + 1
                with connect(s.database_url) as c:
                    TopicStructureRepository(c).record(sid,batch_index,attempt,request,projected,
                        {'method':'TARGET_MEMBERSHIP_PROJECTION','source_attempt':previous['attempt'],'additional_model_calls':0},None)
                good = {'response': projected}
                break
        if good:
            data=good['response']
        else:
            recent=[h for h in history if h.get('created_at') and datetime.now(timezone.utc)-h['created_at']<timedelta(minutes=5)]
            if pool and len(recent)>=len(pool):
                return {'status':'RETRY_DEFERRED','broadcast_id':str(item['broadcast_id']),'completed':index,'total':len(plan)}
            attempt=max([h['attempt'] for h in history]+[0]);success=False
            for client in pool:
                attempt+=1;data={};metadata={'provider':client.provider,'model':client.model};error=None
                try:
                    pace_nim(client)
                    raw,usage=client._post(prompt(items,indices),schema(items,indices),'discussion_structure_consolidation')
                    metadata.update(usage)
                    if client.provider=='nvidia':
                        with connect(s.database_url) as c:SummaryRepository(c).record_monthly_token_usage('nvidia',client.model,usage)
                    data={'raw_partition_response':raw}
                    data=normalize(items,indices,raw)
                except DailyTokenLimitReached:
                    error='DAILY_TOKEN_LIMIT'
                except Exception as exc:
                    error=str(exc) if isinstance(exc,ValueError) else safe_brief_error_code(exc)
                    metadata.update(getattr(exc,'usage_metadata',{}))
                with connect(s.database_url) as c:
                    TopicStructureRepository(c).record(sid,batch_index,attempt,request,data,metadata,error)
                print(json.dumps({'event':'topic_structure.integration_partition','broadcast_id':str(item['broadcast_id']),
                                  'batch':index+1,'total':len(plan),'provider':client.provider,'error':error}),flush=True)
                if not error:success=True;break
            if not success:return {'status':'RETRY_DEFERRED','broadcast_id':str(item['broadcast_id']),'completed':index,'total':len(plan)}
        # Validate cached source membership too; never trust a partial old result.
        checked=normalize(items,indices,data['raw_partition_response'])
        combined.update(checked['assignments'])
        with connect(s.database_url) as c:
            repo=MeetingBriefRepository(c);current=repo.latest(item['broadcast_id'])
            if current and current['brief_id']==item['brief_id'] and current['brief'].get('finalization'):
                brief=dict(current['brief']);state=dict(brief['finalization'])
                state.update(status='PROCESSING',phase='CONSOLIDATING',integration_batches_done=index+1,integration_batches_total=len(plan))
                state.pop('retry_after',None);brief['finalization']=state;repo.update_brief(current['brief_id'],brief)
    result={'assignments':combined,'partition_profile':PROFILE}
    reviewed=apply_consolidation(facets,result)
    attempt=max([h['attempt'] for h in prior if h['index']==CONSOLIDATION_BATCH]+[0])+1
    with connect(s.database_url) as c:
        TopicStructureRepository(c).record(sid,CONSOLIDATION_BATCH,attempt,
            {'issues':items,'request_profile':CONSOLIDATION_PROFILE},result,
            {'method':PROFILE,'partitions':len(plan),'additional_model_calls':0},None)
    return {'status':'CONSOLIDATED','broadcast_id':str(item['broadcast_id']),
            'issues_before':len(items),'issues_after':len(consolidation_input(reviewed))}


def consolidate_one(item: dict[str, Any], structure: dict[str, Any]) -> dict[str, Any]:
    from .meeting_brief_worker import safe_brief_error_code
    s = get_settings()
    structure_id = structure['topic_structure']['revision_id']
    with connect(s.database_url) as c:
        repo = TopicStructureRepository(c)
        prior = repo.batches(structure_id)
        snapshot = repo.snapshot(structure_id)
    attempts = [x for x in prior if x['index'] == CONSOLIDATION_BATCH]
    atoms = snapshot['atoms']
    by_id = {a['id']: a for a in atoms}
    facets = []
    # Use saved request partitions, including their original source positions.
    with connect(s.database_url) as c:
        rows = c.execute("SELECT request_snapshot,response FROM meeting_topic_structure_batches "
                         "WHERE structure_id=%s AND status='READY' AND batch_index<100000 ORDER BY batch_index",
                         (structure_id,)).fetchall()
    for request, response in rows:
        facets.extend(validate_response(response, request['atoms']))
    items = consolidation_input(facets)
    matching = [x for x in attempts if x['request'].get('issues') == items
                and x['request'].get('request_profile') == CONSOLIDATION_PROFILE]
    if any(x['status'] == 'READY' for x in matching):
        return {'status': 'CACHED', 'broadcast_id': str(item['broadcast_id'])}
    # Salvage validated parts of a previous response; invalid merge targets stay independent.
    for previous in reversed(matching):
        if previous.get('error') not in {'INVALID_CONSOLIDATION_ID', 'CYCLIC_CONSOLIDATION'}:
            continue
        try:
            data = preserve_unmergeable_issues(facets, previous['response'])
            apply_consolidation(facets, data)
        except ValueError:
            continue
        attempt = max((x['attempt'] for x in attempts), default=0) + 1
        with connect(s.database_url) as c:
            TopicStructureRepository(c).record(structure_id, CONSOLIDATION_BATCH, attempt,
                {'issues': items, 'request_profile': CONSOLIDATION_PROFILE}, data,
                {'projection_method': 'PRESERVE_SOURCE_FOR_INVALID_MERGE', 'source_attempt': previous['attempt']}, None)
        return {'status': 'CONSOLIDATED', 'broadcast_id': str(item['broadcast_id']),
                'preserved_independent_issues': len(data.get('unmerged_issue_ids', []))}
    if not items:
        with connect(s.database_url) as c:
            TopicStructureRepository(c).mark_review_required(structure_id)
        return {'status': 'NO_CLASSIFIED_ISSUES', 'broadcast_id': str(item['broadcast_id'])}
    if len(items) > 48:
        return consolidate_partitioned({**item, 'structure_id': structure_id}, facets, items, prior)
    pool = clients("integration")
    attempt = max((x['attempt'] for x in attempts), default=0)
    # Start each cooled retry round at NIM; never stick to an exhausted final provider.
    from datetime import datetime, timedelta, timezone
    recent = [x for x in matching if x.get('created_at') and datetime.now(timezone.utc)-x['created_at'] < timedelta(minutes=5)]
    if len(recent) >= len(pool) and pool:
        return {'status': 'RETRY_DEFERRED', 'broadcast_id': str(item['broadcast_id'])}
    last_attempt = attempt + len(pool)
    provider_attempt = 0
    while attempt < last_attempt and pool:
        attempt += 1
        client = pool[provider_attempt % len(pool)]
        provider_attempt += 1
        data, metadata, error = {}, {}, None
        try:
            pace_nim(client)
            from ..services.compact_consolidation import prompt as compact_prompt, schema as compact_schema, normalize
            data, metadata = client._post(compact_prompt(items), compact_schema(items), 'discussion_structure_consolidation')
            data = normalize(items, data)
            if client.provider == 'nvidia':
                with connect(s.database_url) as c:
                    SummaryRepository(c).record_monthly_token_usage('nvidia', client.model, metadata)
            data = preserve_unmergeable_issues(facets, data)
            reviewed = apply_consolidation(facets, data)
        except DailyTokenLimitReached:
            error = 'DAILY_TOKEN_LIMIT'
        except Exception as exc:
            error = str(exc) if isinstance(exc, ValueError) else safe_brief_error_code(exc)
            metadata = metadata or getattr(exc, 'usage_metadata', {})
        with connect(s.database_url) as c:
            TopicStructureRepository(c).record(structure_id, CONSOLIDATION_BATCH, attempt,
                                               {'issues': items, 'request_profile': CONSOLIDATION_PROFILE},
                                               data, metadata, error)
        if not error:
            return {'status': 'CONSOLIDATED', 'broadcast_id': str(item['broadcast_id']),
                    'issues_before': len(items), 'issues_after': len(consolidation_input(reviewed))}
    return {'status': 'CONSOLIDATION_REVIEW_REQUIRED', 'broadcast_id': str(item['broadcast_id'])}


def process_one(broadcast_id: Any, *, request_limit: int = 100, repair: bool = False) -> dict[str, Any]:
    from .meeting_brief_worker import prepare_brief_utterances, safe_brief_error_code
    s = get_settings()
    # Session lock prevents duplicate paid work by the backfill and the regular worker.
    with connect(s.database_url) as lease:
        locked = lease.execute('SELECT pg_try_advisory_lock(hashtext(%s))',
                               ('topic-structure:' + str(broadcast_id),)).fetchone()[0]
        if not locked:
            return {'status': 'BUSY', 'broadcast_id': str(broadcast_id)}
        try:
            with connect(s.database_url) as c:
                item = MeetingBriefRepository(c).latest(broadcast_id)
                repo = TopicStructureRepository(c)
                current = repo.current(item) if item else None
                repair_needed = bool(repair and current and current['topic_structure'].get('rejected'))
                if current and not repair_needed and current['topic_structure'].get('consolidation_status') != 'COMPLETED':
                    return consolidate_one(item, current)
                if not item or (current and not repair_needed):
                    return {'status': 'CACHED', 'broadcast_id': str(broadcast_id)}
                row = c.execute('SELECT lifecycle_status FROM live_broadcasts WHERE id=%s',
                                (broadcast_id,)).fetchone()
                if not row or row[0] != 'ENDED':
                    return {'status': 'LIVE_DEFERRED', 'broadcast_id': str(broadcast_id)}
                transcript = LiveRepository(c).ended_transcript_snapshot(broadcast_id)
                provider, model, prompt = summary_identity(s)
                utterances = prepare_brief_utterances(
                    c, broadcast_id, transcript['segments'], provider=provider, model=model,
                    summary_prompt_version=prompt,
                )
                structure_id = repo.start(item, build_snapshot(item, utterances))
                snapshot = repo.snapshot(structure_id)
                prior = repo.batches(structure_id)
            facets = []
            rejected = []
            requests = 0
            pool = clients()
            if not pool:
                return {'status': 'NO_PROVIDER', 'broadcast_id': str(broadcast_id)}
            atoms = snapshot['atoms']
            batches = []
            batch = []
            size = 0
            for atom in atoms:
                cost = len(atom['text']) + len(atom['before']) + len(atom['after'])
                if batch and (len(batch) >= 32 or size + cost > 28000):
                    batches.append(batch)
                    batch, size = [], 0
                batch.append(atom)
                size += cost
            if batch:
                batches.append(batch)
            for index, batch in enumerate(batches):
                history = [x for x in prior if x['index'] == index]
                completed = next((x for x in history if x['status'] == 'READY'), None)
                if completed:
                    facets.extend(validate_response(completed['response'], batch))
                    continue
                if requests >= request_limit:
                    return {'status': 'PROCESSING', 'broadcast_id': str(broadcast_id),
                            'batch': index, 'batches': len(batches)}
                last_error = 'RETRY_LIMIT'
                attempt = max((x['attempt'] for x in history), default=0)
                attempts_for_schema = sum(x['request'].get('schema_revision') == 2 for x in history)
                last_attempt = attempt + retry_allowance(history, round_size=len(pool))
                success = False
                provider_attempt = attempts_for_schema % max(3, len(pool))
                # At most three attempts per batch, persisted across process restarts.
                while attempt < last_attempt:
                    if requests >= request_limit:
                        return {'status': 'PROCESSING', 'broadcast_id': str(broadcast_id),
                                'batch': index, 'batches': len(batches)}
                    attempt += 1
                    client = pool[provider_attempt % len(pool)]
                    provider_attempt += 1
                    attempts_for_schema += 1
                    request = {'atoms': batch, 'catalog': issue_catalog(facets), 'schema_revision': 2}
                    data, metadata = {}, {}
                    try:
                        requests += 1
                        pace_nim(client)
                        data, metadata = client._post(
                            build_prompt(batch, request['catalog']), response_schema(batch), 'discussion_structure',
                        )
                        if client.provider == 'nvidia':
                            with connect(s.database_url) as c:
                                SummaryRepository(c).record_monthly_token_usage('nvidia', client.model, metadata)
                        validated = validate_response(data, batch, strict_labels=True)
                        last_error = ''
                    except DailyTokenLimitReached:
                        last_error = 'DAILY_TOKEN_LIMIT'
                    except Exception as exc:
                        last_error = str(exc) if isinstance(exc, ValueError) else safe_brief_error_code(exc)
                        metadata = metadata or getattr(exc, 'usage_metadata', {})
                    with connect(s.database_url) as c:
                        TopicStructureRepository(c).record(
                            structure_id, index, attempt, request, data, metadata, last_error or None,
                        )
                    print(json.dumps({'event': 'topic_structure.batch', 'broadcast_id': str(broadcast_id),
                                      'batch': index + 1, 'total': len(batches), 'attempt': attempt,
                                      'provider': client.provider, 'error': last_error or None}), flush=True)
                    if not last_error:
                        facets.extend(validated)
                        success = True
                        break
                if not success:
                    rejected.extend({'atom_id': a['id'], 'evidence_id': a['evidence_id'],
                                     'reason': last_error} for a in batch)
            result = materialize(item['brief'], snapshot, facets, rejected, str(structure_id))
            with connect(s.database_url) as c:
                TopicStructureRepository(c).finish(structure_id, result)
            consolidation = consolidate_one(item, result)
            return {'status': 'READY', 'broadcast_id': str(broadcast_id),
                    'consolidation': consolidation,
                    **{k: result['topic_structure'][k] for k in
                       ('source_atom_count', 'classified_atom_count', 'issue_count', 'parent_count', 'quality_status')}}
        finally:
            lease.execute('SELECT pg_advisory_unlock(hashtext(%s))',
                          ('topic-structure:' + str(broadcast_id),))


def process_available(limit: int = 1, request_limit: int = 2, workers: int = 4) -> list[dict[str, Any]]:
    s = get_settings()
    if not s.ai_enrichment_enabled:
        return []
    with connect(s.database_url) as c:
        repo = TopicStructureRepository(c)
        pending = [x for x in MeetingBriefRepository(c).latest_all()
                   if repo.progress(x)['status'] in ('PENDING', 'PROCESSING', 'RETRY_PENDING')]
        ended = {str(row[0]) for row in c.execute("SELECT id FROM live_broadcasts WHERE lifecycle_status='ENDED'").fetchall()}
        pending = [x for x in pending if str(x['broadcast_id']) in ended]
    pending.sort(key=lambda x: str(x['generated_at']), reverse=True)
    def run(item: dict[str, Any]) -> dict[str, Any]:
        try:
            result = process_one(item['broadcast_id'], request_limit=request_limit, repair=True)
        except Exception as exc:
            from .meeting_brief_worker import safe_brief_error_code
            result = {'status': 'FAILED', 'broadcast_id': str(item['broadcast_id']),
                      'error': safe_brief_error_code(exc)}
        print(json.dumps({'event': 'topic_structure.report', **result}, ensure_ascii=False), flush=True)
        return result
    with ThreadPoolExecutor(max_workers=min(workers, limit)) as executor:
        return list(executor.map(run, pending[:limit]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--broadcast-id')
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--drain', action='store_true')
    parser.add_argument('--repair', action='store_true')
    args = parser.parse_args()
    apply_migrations(get_settings().database_url)
    if args.broadcast_id:
        print(json.dumps(process_one(args.broadcast_id, repair=args.repair), ensure_ascii=False), flush=True)
        return
    while True:
        results = process_available(100 if args.all else 1, 100 if args.all else 2)
        print(json.dumps(results, ensure_ascii=False), flush=True)
        if not args.drain or not results:
            return
        if any(x['status'] in ('BUDGET_DEFERRED', 'CONSOLIDATION_REVIEW_REQUIRED', 'NO_CLASSIFIED_ISSUES') for x in results):
            return
        time.sleep(30)


if __name__ == '__main__':
    main()
