"""Bounded live grouping on the existing meeting worker; no new service."""
from __future__ import annotations
import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from ..config import get_settings
from ..db.connection import connect
from ..db.live_repository import LiveRepository
from ..db.live_discussion_repository import LiveDiscussionRepository
from ..db.summary_repository import SummaryRepository
from ..db.openai_daily_budget import DailyTokenLimitReached
from ..domain.scope import TARGET_COMMITTEES, NATIONAL_ASSEMBLY_BODIES
from ..domain.assembly_expansion import meeting_ids
from ..services.summary_client import summary_identity
from ..services.live_discussion_classification import classification_request, build_prompt, response_schema, apply_classification, validated_partial_response

_retry_after: dict[str, float] = {}


def process_one(broadcast_id: Any) -> dict[str, Any]:
    from .meeting_brief_worker import prepare_brief_utterances, safe_brief_error_code
    from .topic_structure_worker import clients, pace_nim
    broadcast_id=UUID(str(broadcast_id))
    s=get_settings(); bid=str(broadcast_id)
    if time.monotonic() < _retry_after.get(bid,0):
        return {'broadcast_id':bid,'status':'RETRY_WAIT'}
    with connect(s.database_url) as c:
        locked=c.execute("SELECT pg_try_advisory_xact_lock(hashtext(%s))",('live-discussion:'+bid,)).fetchone()[0]
        if not locked:
            return {'broadcast_id':bid,'status':'BUSY'}
        row=c.execute('SELECT lifecycle_status FROM live_broadcasts WHERE id=%s',(broadcast_id,)).fetchone()
        if not row:
            return {'broadcast_id':bid,'status':'NOT_FOUND'}
        segments=LiveRepository(c).broadcast_transcript_snapshot(broadcast_id,lifecycle_status=row[0])['segments']
        provider,model,version=summary_identity(s)
        turns=prepare_brief_utterances(c,broadcast_id,segments,provider=provider,model=model,summary_prompt_version=version)
        repo=LiveDiscussionRepository(c); state=repo.latest(broadcast_id)
        request=classification_request(turns,state)
        targets=sum(r['target'] for r in request['turns'])
        if not targets:
            _clear_resumed(c, broadcast_id, turns, state)
            if state.get('_budget_wait'):
                resumed={k:v for k,v in state.items() if k!='_budget_wait'}
                repo.save(broadcast_id,resumed,{'profile':'live-classification-budget-resumed/1',
                    'retry_after':state['_budget_wait']['retry_after'],'assignments':len(state['assignments'])},
                    {},SimpleNamespace(provider='local',model='budget-resumed'),{'additional_model_calls':0})
            return {'broadcast_id':bid,'status':'CACHED','classified':len(state['assignments']),'groups':len(state['groups'])}
        errors=[]; budget_wait=False
        for client in clients():
            try:
                pace_nim(client)
                response,metadata=client._post(build_prompt(request),response_schema(),'live_discussion_classification')
                if client.provider=='nvidia':
                    # Record actual usage even when response validation rejects it.
                    with connect(s.database_url) as usage_connection:
                        SummaryRepository(usage_connection).record_monthly_token_usage('nvidia',client.model,metadata)
                subset,cleaned,coverage=validated_partial_response(request,response)
                updated=apply_classification(bid,state,subset,cleaned)
                updated.pop('_budget_wait',None)
                metadata={**metadata,'classification_coverage':coverage}
                repo.save(broadcast_id,updated,request,response,client,metadata)
                _clear_resumed(c,broadcast_id,turns,updated)
                return {'broadcast_id':bid,'status':'CLASSIFIED','provider':client.provider,
                        'processed':coverage['accepted_turns'],'pending_in_batch':len(coverage['pending_turn_ids']),'classified':len(updated['assignments']),'groups':len(updated['groups'])}
            except Exception as exc:
                budget_wait = budget_wait or isinstance(exc,DailyTokenLimitReached)
                errors.append({'provider':client.provider,'error':str(exc) if isinstance(exc,ValueError) else safe_brief_error_code(exc)})
        if budget_wait:
            reset=(datetime.now(timezone.utc)+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
            pending={**state,'_budget_wait':{'retry_after':reset}}
            repo.save(broadcast_id,pending,{'profile':'live-classification-budget-wait/1',
                'source_request':request,'retry_after':reset},{},SimpleNamespace(provider='local',model='budget-wait'),
                {'additional_model_calls':0,'retry_after':reset})
        _retry_after[bid]=time.monotonic()+120
        return {'broadcast_id':bid,'status':'RETRY_WAIT','errors':errors}


def _clear_resumed(c: Any, broadcast_id: Any, turns: list[dict[str, Any]], state: dict[str, Any]) -> None:
    hashes=[u['content_hash'] for u in turns
            if state.get('assignments',{}).get(str(u['utterance_id']),{}).get('content_hash')==u['content_hash']]
    if hashes:
        c.execute("UPDATE transcript_utterance_summary_failures SET last_error='BUDGET_RESUMED',updated_at=now() "
                  "WHERE broadcast_id=%s AND last_error='BUDGET_WAIT' AND content_hash=ANY(%s)", (broadcast_id,hashes))


def process_available() -> list[dict[str, Any]]:
    with connect(get_settings().database_url) as c:
        rows=c.execute("SELECT id FROM live_broadcasts WHERE institution='LEGISLATURE' AND source_system='assembly.webcast.go.kr' AND (committee_name=ANY(%s) OR external_id=ANY(%s)) AND (lifecycle_status='LIVE' OR (lifecycle_status='ENDED' AND ended_at>now()-interval '1 hour')) ORDER BY detected_at DESC LIMIT 2",([*TARGET_COMMITTEES,*NATIONAL_ASSEMBLY_BODIES], meeting_ids())).fetchall()
        recovery=c.execute("""SELECT b.id FROM live_broadcasts b WHERE b.institution='LEGISLATURE'
            AND b.source_system='assembly.webcast.go.kr' AND (b.committee_name=ANY(%s) OR b.external_id=ANY(%s))
            AND b.lifecycle_status='ENDED' AND NOT (b.id=ANY(%s::uuid[])) AND (
                EXISTS(SELECT 1 FROM transcript_utterance_summary_failures f WHERE f.broadcast_id=b.id
                    AND f.last_error='BUDGET_WAIT' AND f.retry_after<=now()) OR
                ((SELECT state FROM live_discussion_classifications d WHERE d.broadcast_id=b.id
                  AND d.profile='live-discussion-classification/1.0' ORDER BY created_at DESC LIMIT 1)
                  ->'_budget_wait'->>'retry_after')::timestamptz<=now())
            ORDER BY b.detected_at LIMIT 1""",([*TARGET_COMMITTEES,*NATIONAL_ASSEMBLY_BODIES], meeting_ids(), [r[0] for r in rows])).fetchall()
        rows+=recovery
    results=[]
    for (bid,) in rows:
        try:
            results.append(process_one(bid))
        except Exception as exc:
            from .meeting_brief_worker import safe_brief_error_code
            results.append({'broadcast_id':str(bid),'status':'FAILED','error':safe_brief_error_code(exc)})
    return results


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument('--broadcast-id',required=True);parser.add_argument('--batches',type=int,default=1)
    args=parser.parse_args()
    for _ in range(min(30,max(1,args.batches))):
        result=process_one(args.broadcast_id);print(json.dumps(result,ensure_ascii=False),flush=True)
        if result['status']!='CLASSIFIED':
            break


if __name__=='__main__':
    main()
