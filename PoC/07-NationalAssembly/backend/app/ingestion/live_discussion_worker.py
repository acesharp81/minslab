"""Bounded live grouping on the existing meeting worker; no new service."""
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
from ..db.summary_repository import SummaryRepository
from ..domain.scope import TARGET_COMMITTEES, NATIONAL_ASSEMBLY_BODIES
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
            return {'broadcast_id':bid,'status':'CACHED','classified':len(state['assignments']),'groups':len(state['groups'])}
        errors=[]
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
                metadata={**metadata,'classification_coverage':coverage}
                repo.save(broadcast_id,updated,request,response,client,metadata)
                return {'broadcast_id':bid,'status':'CLASSIFIED','provider':client.provider,
                        'processed':coverage['accepted_turns'],'pending_in_batch':len(coverage['pending_turn_ids']),'classified':len(updated['assignments']),'groups':len(updated['groups'])}
            except Exception as exc:
                errors.append({'provider':client.provider,'error':str(exc) if isinstance(exc,ValueError) else safe_brief_error_code(exc)})
        _retry_after[bid]=time.monotonic()+120
        return {'broadcast_id':bid,'status':'RETRY_WAIT','errors':errors}


def process_available() -> list[dict[str, Any]]:
    with connect(get_settings().database_url) as c:
        rows=c.execute("SELECT id FROM live_broadcasts WHERE institution='LEGISLATURE' AND source_system='assembly.webcast.go.kr' AND committee_name=ANY(%s) AND (lifecycle_status='LIVE' OR (lifecycle_status='ENDED' AND ended_at>now()-interval '1 hour')) ORDER BY detected_at DESC LIMIT 2",([*TARGET_COMMITTEES,*NATIONAL_ASSEMBLY_BODIES],)).fetchall()
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
