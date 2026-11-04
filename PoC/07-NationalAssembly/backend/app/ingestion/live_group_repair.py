"""Explicitly approved two-broadcast repair. Never called by scheduled workers."""
from __future__ import annotations

import argparse
import json
import time
from typing import Any
from uuid import UUID

from ..config import get_settings
from ..db.connection import connect
from ..db.live_repository import LiveRepository
from ..db.live_discussion_repository import LiveDiscussionRepository
from ..services.summary_client import summary_identity
from ..services.grouped_models import quota_client
from ..services.live_group_review import PROFILE, MAX_INPUT_BYTES, review_request, prompt, schema, apply_review

APPROVED_BROADCASTS = {
    'e79d3383-55ae-428d-821f-96d15ce35294',
    '1d00ebf4-24da-4443-9eb9-907864e59829',
}


def process_one(broadcast_id: Any, *, preview: bool = False) -> dict[str, Any]:
    from .meeting_brief_worker import prepare_brief_utterances, safe_brief_error_code
    if str(broadcast_id) not in APPROVED_BROADCASTS:
        raise ValueError('BROADCAST_NOT_APPROVED')
    bid = UUID(str(broadcast_id)); settings = get_settings()
    with connect(settings.database_url) as lease:
        key = 'live-discussion:' + str(bid)
        if not lease.execute('SELECT pg_try_advisory_lock(hashtext(%s))', (key,)).fetchone()[0]:
            return {'status': 'BUSY'}
        lease.commit()
        try:
            with connect(settings.database_url) as c:
                prior = c.execute("SELECT usage_metadata FROM live_discussion_classifications "
                    "WHERE broadcast_id=%s AND request_snapshot->>'profile'=%s ORDER BY created_at DESC LIMIT 1",
                    (bid, PROFILE)).fetchone()
                if prior:
                    return {'status': 'ALREADY_ATTEMPTED', 'usage': prior[0]}
                row = c.execute('SELECT lifecycle_status FROM live_broadcasts WHERE id=%s', (bid,)).fetchone()
                if not row or row[0] not in {'LIVE', 'ENDED'}:
                    return {'status': 'NOT_AVAILABLE'}
                repo = LiveDiscussionRepository(c); state = repo.latest(bid)
                segments = LiveRepository(c).broadcast_transcript_snapshot(bid, lifecycle_status=row[0])['segments']
                provider, model, version = summary_identity(settings)
                turns = prepare_brief_utterances(c, bid, segments, provider=provider, model=model, summary_prompt_version=version)
            request = review_request(state, turns)
            instruction = prompt(request)
            if len(instruction.encode()) > MAX_INPUT_BYTES:
                return {'status': 'INPUT_LIMIT'}
            if preview:
                return {'status': 'PREVIEW', 'groups': len(request['groups']),
                        'assignments': len(state['assignments']), 'input_bytes': len(instruction.encode())}
            client = quota_client(settings, 'main')
            client.reasoning_effort = 'low'
            response, usage, error, updated = {}, {}, None, state
            started = time.monotonic()
            try:
                response, usage = client._post(instruction, schema(), 'live_group_repair')
                updated = apply_review(state, request, response)
            except Exception as exc:
                error = (str(exc) if isinstance(exc, ValueError) and str(exc).startswith('LIVE_REVIEW_')
                         else safe_brief_error_code(exc))
                usage = usage or getattr(exc, 'usage_metadata', {}) or {}
            usage = {**usage, 'repair_profile': PROFILE, 'error': error,
                     'elapsed_seconds': round(time.monotonic()-started, 3), 'full_source_sent': False}
            with connect(settings.database_url) as c:
                LiveDiscussionRepository(c).save(bid, updated, request, response, client, usage)
            return {'status': 'FAILED' if error else 'READY', 'error': error,
                    'broadcast_id': str(bid), 'groups_before': len(request['groups']),
                    'groups_after': len(updated['groups']), 'assignments': len(updated['assignments']),
                    'usage': usage}
        finally:
            lease.execute('SELECT pg_advisory_unlock(hashtext(%s))', (key,))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--broadcast-id', required=True, choices=sorted(APPROVED_BROADCASTS))
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args()
    print(json.dumps(process_one(args.broadcast_id, preview=args.preview), ensure_ascii=False), flush=True)
