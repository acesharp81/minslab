"""One cached GPT-5.4 editorial pass after detailed summaries are complete."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import time
from typing import Any

from ..config import get_settings
from ..db.connection import connect
from ..db.meeting_brief_repository import MeetingBriefRepository
from ..db.topic_structure_repository import TopicStructureRepository
from ..db.openai_daily_budget import DailyTokenLimitReached
from ..services.grouped_models import quota_client
from ..services.report_parent_review import (
    PROFILE, BATCH_START, MAX_INPUT_BYTES, request_for, prompt, schema, project,
)


def retry_at(*, daily: bool = False) -> str:
    now = datetime.now(timezone.utc)
    return ((now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            if daily else now + timedelta(minutes=15)).isoformat()


def process_one(broadcast_id: Any) -> dict[str, Any]:
    from .meeting_brief_worker import safe_brief_error_code
    settings = get_settings()
    with connect(settings.database_url) as lease:
        lock = 'topic-structure:' + str(broadcast_id)
        if not lease.execute('SELECT pg_try_advisory_lock(hashtext(%s))', (lock,)).fetchone()[0]:
            return {'status': 'BUSY', 'retry_after': retry_at()}
        # The session lock survives commit; no idle transaction during the API call.
        lease.commit()
        try:
            with connect(settings.database_url) as c:
                row = c.execute('SELECT lifecycle_status FROM live_broadcasts WHERE id=%s', (broadcast_id,)).fetchone()
                if not row or row[0] != 'ENDED':
                    return {'status': 'LIVE_DEFERRED', 'retry_after': retry_at()}
                item = MeetingBriefRepository(c).latest(broadcast_id)
                repo = TopicStructureRepository(c)
                brief = repo.ready_current(item) if item else None
                if not brief or (brief.get('narrative_coverage') or {}).get('status') != 'COMPLETE':
                    return {'status': 'NARRATIVE_PENDING', 'retry_after': retry_at()}
                if brief.get('parent_review', {}).get('status') in {'READY', 'RETAINED'}:
                    return {**brief['parent_review'], 'status': 'CACHED'}
                sid = brief['topic_structure']['revision_id']
                snapshot, history = repo.snapshot(sid), repo.batches(sid)
            request = request_for(brief, snapshot)
            prior = [h for h in history if h['request'] == request]
            latest = prior[-1] if prior else {}
            retry = (latest.get('usage') or {}).get('retry_after')
            if retry and datetime.fromisoformat(retry) > datetime.now(timezone.utc):
                return {'status': 'DEFERRED', 'retry_after': retry}
            index = prior[0]['index'] if prior else max([BATCH_START-1] + [h['index'] for h in history]) + 1
            attempt = max([0] + [h['attempt'] for h in prior]) + 1
            instruction = prompt(request)
            input_bytes = len(instruction.encode())
            errors = sum(bool(h.get('error')) and h.get('error') != 'DAILY_TOKEN_LIMIT' for h in prior)
            reason = ('SINGLE_PARENT' if len(request['groups']) < 2 else
                      'INPUT_LIMIT' if input_bytes > MAX_INPUT_BYTES else
                      'RETRY_LIMIT' if errors >= 3 else None)
            if reason:
                with connect(settings.database_url) as c:
                    TopicStructureRepository(c).record(sid, index, attempt, request,
                        {'status': 'RETAINED', 'reason': reason}, {'additional_model_calls': 0}, None)
                return {'status': 'RETAINED', 'reason': reason}
            if not settings.openai_api_key:
                return {'status': 'NO_PROVIDER', 'retry_after': retry_at(daily=True)}
            client = quota_client(settings, 'main')  # No paid/Terra fallback.
            response, usage, error = {}, {}, None
            start = time.monotonic()
            try:
                response, usage = client._post(instruction, schema(), 'meeting_parent_review')
                result = project(brief, request, response)  # Exact partition + both display coverages.
            except DailyTokenLimitReached as exc:
                error = 'DAILY_TOKEN_LIMIT'
                usage = {'additional_model_calls': 0, 'retry_after': retry_at(daily='COOLDOWN' not in str(exc))}
            except Exception as exc:
                error = (str(exc) if isinstance(exc, ValueError) and str(exc).startswith('PARENT_REVIEW_')
                         else safe_brief_error_code(exc))
                usage = usage or getattr(exc, 'usage_metadata', {}) or {}
                usage['retry_after'] = retry_at()
            usage = {**usage, 'provider': client.provider, 'model': client.model,
                     'attempted_model': client.model, 'elapsed_seconds': round(time.monotonic()-start, 3),
                     'input_bytes': input_bytes, 'full_source_sent': False}
            with connect(settings.database_url) as c:
                TopicStructureRepository(c).record(sid, index, attempt, request, response, usage, error)
            if error:
                return {'status': 'DEFERRED', 'error': error, 'retry_after': usage['retry_after']}
            return {'status': 'READY', 'broadcast_id': str(broadcast_id),
                    'review': result['parent_review'], 'usage': usage}
        finally:
            lease.execute('SELECT pg_advisory_unlock(hashtext(%s))', (lock,))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--broadcast-id', required=True)
    args = parser.parse_args()
    print(json.dumps(process_one(args.broadcast_id), ensure_ascii=False), flush=True)
