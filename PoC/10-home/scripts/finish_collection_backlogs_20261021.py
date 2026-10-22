"""Drain authorized non-iH backfills, preserving upstream failure checkpoints."""
import json
import os
import time
import signal
import threading
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from backend.db import engine_for
from backend.service import HomeService
from backend.sources import SOURCES

FOLDER='final-non-ih-review-20261021'
STOP=threading.Event()


def run(source_id):
    assert not source_id.startswith('ih_')
    service=HomeService(engine_for())
    folder=Path(service.data_dir)/FOLDER;folder.mkdir(exist_ok=True)
    log=folder/(source_id+'.jsonl')
    source=next(s for s in SOURCES if s['id']==source_id)
    previous=None
    for index in range(3000):
        if STOP.is_set():return dict(source_id=source_id,stop='CHECKPOINT_STOP')
        if (folder/'stop-backfill').exists():return dict(source_id=source_id,stop='CHECKPOINT_STOP')
        result=service.collect_one(source)
        stats=service.latest_collection_stats(source_id)
        row=dict(checked_at=datetime.now(timezone.utc).isoformat(),source_id=source_id,
                 iteration=index,status=result.get('status'),
                 batch_id=result.get('batch_id') or result.get('id'),
                 completed=stats.get('scope_completed_dongs'),remaining=stats.get('scope_remaining_dongs'),
                 detail_remaining=stats.get('detail_remaining'),deferred=stats.get('details_deferred'),
                 checkpoints=stats.get('region_checkpoints'),failed_details=stats.get('failed_details'),
                 failures=stats.get('failures'),records=stats.get('record_count'))
        with log.open('a') as handle:handle.write(json.dumps(row,ensure_ascii=False)+'\n')
        print(json.dumps(row,ensure_ascii=False),flush=True)
        if result.get('status')=='BUSY':
            time.sleep(5);continue
        if result.get('status')!='SUCCESS':
            # Let the durable scheduler resume after upstream recovery; do not
            # turn an unavailable page into a completed or empty district.
            return dict(source_id=source_id,stop='UPSTREAM_FAILURE',last=row)
        if source_id=='lh_notice_detail':return dict(source_id=source_id,stop='RECOLLECTED',last=row)
        if source_id=='building_general_permit':
            current=stats.get('scope_completed_dongs')
            if stats.get('scope_remaining_dongs')==0:return dict(source_id=source_id,stop='ALL_DONGS_QUERIED',last=row)
        else:
            current=(stats.get('detail_remaining'),json.dumps(stats.get('region_checkpoints'),sort_keys=True))
            window=all(c.get('complete_window') for c in stats.get('region_checkpoints',{}).values())
            if window and stats.get('detail_remaining',0)<=stats.get('details_deferred',0):
                return dict(source_id=source_id,stop='AVAILABLE_DRAINED_FAILED_ATTACHMENTS_DEFERRED',last=row)
        if current==previous:return dict(source_id=source_id,stop='NO_CHECKPOINT_ADVANCE',last=row)
        previous=current
        time.sleep(1)
    return dict(source_id=source_id,stop='BATCH_GUARD')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--sources',nargs='+',default=['lh_notice_detail','building_general_permit','eum_housing_notices'])
    parser.add_argument('--retry-failed',action='store_true')
    args=parser.parse_args()
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:STOP.set())
    os.environ.setdefault('POC10_API_REQUEST_INTERVAL','0.35')
    os.environ.setdefault('POC10_GENERAL_PERMIT_DONGS_PER_BATCH','5')
    os.environ.setdefault('POC10_GENERAL_PERMIT_QUERY_WORKERS','1')
    os.environ.setdefault('POC10_EUM_BACKFILL_PAGES','10')
    os.environ.setdefault('POC10_EUM_DETAILS_PER_BATCH','60')
    os.environ.setdefault('POC10_EUM_DETAIL_WORKERS','2')
    folder=Path(os.environ.get('POC10_DATA_DIR','data'))/FOLDER
    sources=args.sources;result=[]
    while sources and not STOP.is_set():
        with ThreadPoolExecutor(max_workers=min(3,len(sources))) as pool:
            current=list(pool.map(run,sources))
        result=[r for r in result if r['source_id'] not in sources]+current
        (folder/'collection_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        print(json.dumps(current,ensure_ascii=False),flush=True)
        sources=[r['source_id'] for r in current if r['stop']=='UPSTREAM_FAILURE'] if args.retry_failed else []
        if sources:STOP.wait(900)
