"""Finish source classification before publishing a new meeting report as ready.

Reuse the durable structure/review batches; a retry never regenerates synthesis.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import get_settings
from ..db.connection import connect
from ..db.meeting_brief_repository import MeetingBriefRepository
from ..db.topic_structure_repository import TopicStructureRepository
from ..services.meeting_progress import stage_progress
from . import topic_structure_worker, structure_review_worker, ontology_review_worker, structured_narrative_worker

VERSION = 'meeting-finalization/1'


def initial_state() -> dict[str, Any]:
    return {'version': VERSION, 'status': 'PENDING', 'phase': 'STRUCTURING'}


def assess(structure: dict[str, Any] | None, progress: dict[str, Any], ontology_pending: list) -> dict[str, Any]:
    if not structure or progress.get('status') != 'COMPLETED':
        return {'status': 'PENDING', 'phase': 'STRUCTURING'}
    meta = structure.get('topic_structure') or {}
    review = meta.get('automatic_review') or {}
    if meta.get('rejected') or review.get('status') != 'COMPLETED':
        return {'status': 'PENDING', 'phase': 'REVIEWING',
                'pending_count': int(review.get('pending_atom_count') or 0) + len(meta.get('rejected') or [])}
    if ontology_pending:
        return {'status': 'PENDING', 'phase': 'ONTOLOGY', 'pending_count': len(ontology_pending)}
    narrative = structure.get('narrative_coverage') or {}
    if narrative.get('issue_count', 0) and narrative.get('status') != 'COMPLETE':
        return {'status': 'PENDING', 'phase': 'NARRATIVE'}
    # Reviewed source limitations are not transport/model errors. Never force a
    # false policy match just to reach 100% dictionary coverage.
    unclassified = int((structure.get('topic_grouping') or {}).get('unclassified_topic_count') or 0)
    return {'status': 'COMPLETED', 'phase': 'COMPLETED',
            'source_limited_topics': unclassified,
            'source_limited_discussions': len(meta.get('uncertain') or [])}


def _load(broadcast_id: Any):
    with connect(get_settings().database_url) as c:
        item = MeetingBriefRepository(c).latest(broadcast_id)
        if not item:
            return None, None, {}, []
        repo = TopicStructureRepository(c)
        structure = repo.ready_current(item)
        progress = repo.progress(item)
        prior = repo.batches(structure['topic_structure']['revision_id']) if structure else []
    return item, structure, progress, prior


def _save(broadcast_id: Any, state: dict[str, Any], expected_id: Any = None) -> dict[str, Any]:
    state = {'version': VERSION, **state, 'updated_at': datetime.now(timezone.utc).isoformat()}
    with connect(get_settings().database_url) as c:
        repo = MeetingBriefRepository(c)
        item = repo.latest(broadcast_id)
        if not item:
            return {'status': 'NOT_FOUND'}
        if expected_id is not None and item['brief_id'] != expected_id:
            return {'status': 'STALE_SOURCE', 'broadcast_id': str(broadcast_id)}
        brief = dict(item['brief'])
        prior=brief.get('finalization') or {}
        for key in ('integration_batches_done','integration_batches_total'):
            if key in prior and key not in state:state[key]=prior[key]
        if 'stages' not in state:
            state['stages'] = stage_progress({**prior, **state})
        repo.save_finalization(item['brief_id'], state)
    return {'broadcast_id': str(broadcast_id), **state}



def made_progress(outcome: dict[str, Any]) -> bool:
    if outcome.get('status') in {'PROCESSING', 'READY', 'CONSOLIDATED', 'CACHED', 'COMPLETED'}:
        return True
    return any(batch.get('status') == 'READY' or batch.get('salvaged_issues', 0) > 0
               for batch in outcome.get('batches', []) if isinstance(batch, dict)) if isinstance(outcome.get('batches'), list) else False


def process_one(broadcast_id: Any, *, request_limit: int = 4, batch_limit: int = 2) -> dict[str, Any]:
    # A separate lease covers the stage transitions. Individual workers retain
    # their existing topic-structure leases and per-provider budget reservations.
    with connect(get_settings().database_url) as lease:
        key = 'brief-finalization:' + str(broadcast_id)
        if not lease.execute('SELECT pg_try_advisory_lock(hashtext(%s))', (key,)).fetchone()[0]:
            return {'status': 'BUSY', 'broadcast_id': str(broadcast_id)}
        expected_id = None
        active_phase = 'STRUCTURING'
        def save(state):
            nonlocal active_phase
            active_phase = state.get('phase', active_phase)
            prior_state = (item or {}).get('brief', {}).get('finalization') or {}
            pending_topics = ontology_review_worker.pending_items(structure, []) if structure else None
            state['stages'] = stage_progress({**prior_state, **state}, structure, progress, pending_topics)
            return _save(broadcast_id, state, expected_id)
        item, structure, progress = None, None, {}
        try:
            item, structure, progress, prior = _load(broadcast_id)
            if not item:
                return {'status': 'NOT_FOUND'}
            expected_id = item['brief_id']
            state = item['brief'].get('finalization') or initial_state()
            retry = state.get('retry_after')
            if retry and datetime.fromisoformat(retry) > datetime.now(timezone.utc):
                return {'broadcast_id': str(broadcast_id), **state}
            if state.get('status') == 'COMPLETED':
                return {'status': 'CACHED', 'broadcast_id': str(broadcast_id)}
            save({'status': 'PROCESSING', 'phase': 'STRUCTURING'})
            outcome = topic_structure_worker.process_one(broadcast_id, request_limit=request_limit, repair=True)
            item, structure, progress, prior = _load(broadcast_id)
            if structure and progress.get('status') == 'COMPLETED':
                save({'status': 'PROCESSING', 'phase': 'REVIEWING'})
                outcome = structure_review_worker.process_one(broadcast_id, batch_limit=batch_limit)
                item, structure, progress, prior = _load(broadcast_id)
                if (structure.get('topic_structure', {}).get('automatic_review') or {}).get('status') == 'COMPLETED':
                    save({'status': 'PROCESSING', 'phase': 'ONTOLOGY'})
                    outcome = ontology_review_worker.process_one(broadcast_id, batch_limit=batch_limit)
                    item, structure, progress, prior = _load(broadcast_id)
            # Include items whose retry budget is temporarily exhausted: they
            # must not be mistaken for successfully reviewed source limitations.
            pending = ontology_review_worker.pending_items(structure, []) if structure else []
            state = assess(structure, progress, pending)
            if state.get('phase') == 'NARRATIVE':
                save({'status': 'PROCESSING', 'phase': 'NARRATIVE'})
                outcome = structured_narrative_worker.process_one(broadcast_id, batch_limit=batch_limit)
                item, structure, progress, prior = _load(broadcast_id)
                state = assess(structure, progress, pending)
            if state['status'] != 'COMPLETED' and made_progress(outcome):
                state.update(status='PROCESSING')
            elif state['status'] != 'COMPLETED':
                state.update(status='DEFERRED', retry_after=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),
                             last_result=outcome.get('status'))
            if state.get('phase') == 'ONTOLOGY' and pending and not ontology_review_worker.pending_items(structure, prior):
                state.update(status='DEFERRED', retry_after=(datetime.now(timezone.utc)+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0).isoformat(), last_result='DAILY_REVIEW_ATTEMPTS')
            return save(state)
        except Exception as exc:
            from .meeting_brief_worker import safe_brief_error_code
            return save({'status': 'DEFERRED', 'phase': active_phase,
                         'retry_after': (datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),
                         'error': safe_brief_error_code(exc)})
        finally:
            lease.execute('SELECT pg_advisory_unlock(hashtext(%s))', (key,))


def process_available(limit: int = 1) -> list[dict[str, Any]]:
    with connect(get_settings().database_url) as c:
        rows = c.execute("""SELECT b.broadcast_id FROM meeting_briefs b
            JOIN live_broadcasts live ON live.id=b.broadcast_id
            WHERE live.lifecycle_status='ENDED'
              AND meeting_brief_payload(b.id,b.brief) ? 'finalization'
              AND meeting_brief_payload(b.id,b.brief)->'finalization'->>'status' <> 'COMPLETED'
              AND NOT EXISTS(SELECT 1 FROM meeting_briefs newer WHERE newer.broadcast_id=b.broadcast_id
                  AND newer.provider <> 'deterministic' AND (newer.generated_at,newer.id)>(b.generated_at,b.id))
              AND COALESCE((meeting_brief_payload(b.id,b.brief)->'finalization'->>'retry_after')::timestamptz,'-infinity')<=now()
            ORDER BY COALESCE((meeting_brief_payload(b.id,b.brief)->'finalization'->>'updated_at')::timestamptz,b.generated_at),
                     b.generated_at DESC LIMIT %s""", (limit,)).fetchall()
    return [process_one(row[0]) for row in rows]
