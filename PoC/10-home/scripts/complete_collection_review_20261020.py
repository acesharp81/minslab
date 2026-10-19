"""Drain unfinished official building scopes; resumable batch evidence on disk.

Only existing collectors write records. Source locks, pagination validation and
provenance rules remain in force. A repeated failure stops that source instead
of declaring its remaining districts empty.
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend.db import engine_for
from backend.service import HomeService
from backend.sources import SOURCES
from scripts.review_policy_readmission_20261019 import protected

IDS=('building_general_permit','building_register','building_register_recap','building_hub_details')

def slim(stats):
    return {k:v for k,v in stats.items() if k.startswith('scope_') and not isinstance(v,(list,dict))
            or k in ('detail_remaining','backfill_pending','complete_scope')}

def main():
    service=HomeService(engine_for());out=service.data_dir/'completion-20261020';out.mkdir(exist_ok=True)
    baseline=out/'protected-before.json'
    if not baseline.exists():baseline.write_text(json.dumps(protected(service),ensure_ascii=False))
    scopefile=out/'scope-before.json'
    if not scopefile.exists():scopefile.write_text(json.dumps({sid:slim(service.latest_collection_stats(sid)) for sid in IDS},ensure_ascii=False,indent=2))
    def run(sid):
        s=HomeService(engine_for());source=next(x for x in SOURCES if x['id']==sid)
        failures=0;busy=0
        while True:
            if (out/'stop-after-batch').exists():return dict(source_id=sid,status='CHECKPOINT_STOP')
            stats=s.latest_collection_stats(sid)
            if stats.get('complete_scope') or stats.get('scope_remaining_dongs')==0:
                return dict(source_id=sid,status='SCOPE_QUERIED',scope=slim(stats))
            start=time.monotonic();result=s.collect_one(source);status=result.get('status')
            state=slim(s.latest_collection_stats(sid))
            item=dict(source_id=sid,status=status,result=result,scope=state,elapsed_seconds=round(time.monotonic()-start,2))
            with (out/(sid+'.jsonl')).open('a') as f:f.write(json.dumps(item,ensure_ascii=False,default=str)+'\n')
            print(json.dumps({k:v for k,v in item.items() if k!='result'},ensure_ascii=False),flush=True)
            if status=='BUSY':
                busy+=1
                if busy>=60:return dict(source_id=sid,status='SOURCE_BUSY',scope=state)
                time.sleep(10);continue
            busy=0
            if status!='SUCCESS':
                failures+=1
                if failures>=int(os.environ.get('POC10_COMPLETION_MAX_FAILURES','3')):
                    return dict(source_id=sid,status='SOURCE_FAILURE',scope=state)
                time.sleep(min(60,10*failures));continue
            failures=0
    with ThreadPoolExecutor(max_workers=int(os.environ.get('POC10_COMPLETION_WORKERS','3'))) as pool:result=list(pool.map(run,IDS))
    (out/'drain-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
