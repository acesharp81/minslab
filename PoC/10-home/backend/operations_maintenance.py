"""Resumable night-only compaction and reference inventory; no source deletion."""
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import time
from sqlalchemy import select
from .db import MetricSnapshot, Batch, CollectionJob
from .operations_window import night_open
from .raw_archive import atomic_write


def compact_snapshots(service,state,limit=10):
    from .independent_metrics import digest
    from .snapshot_content import store_content,restore_content
    cursor=state.get('snapshot_cursor','');count=0
    with service.sessions.begin() as db:
        rows=db.scalars(select(MetricSnapshot).where(MetricSnapshot.id>cursor).order_by(MetricSnapshot.id).limit(limit)).all()
        for row in rows:
            if not night_open():break
            if '_content_ref' not in row.result:
                before=row.result
                if digest(dict(context=row.context,result=before))!=row.digest:raise ValueError('SNAPSHOT_DIGEST_MISMATCH')
                reference=store_content(db,row.context,before)
                restored=restore_content(db,row.context,reference)
                if restored!=before:raise ValueError('SNAPSHOT_RESTORE_MISMATCH')
                row.result=reference;count+=1
            # Save cursor only after commit (state file is written by step()).
            cursor=row.id
    state['snapshot_cursor']=cursor
    state['snapshots_compacted']=state.get('snapshots_compacted',0)+count
    if not rows:state['snapshots_scan_complete']=True
    return count


def inventory(service,state,limit=20):
    root=Path(service.data_dir)/'runtime';root.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(root/'archive-inventory.sqlite3',timeout=5) as inventory:
        inventory.executescript('''CREATE TABLE IF NOT EXISTS raw_references(file TEXT,batch_id TEXT,PRIMARY KEY(file,batch_id));
            CREATE TABLE IF NOT EXISTS raw_files(file TEXT PRIMARY KEY,bytes INTEGER,source TEXT,checked REAL);
            ''')
        # Completed batches are a bounded first source of references. Other
        # document/report references may exist; this inventory never authorizes deletion.
        cursor=state.get('manifest_cursor')
        with service.sessions() as db:
            query=select(Batch.id,Batch.finished_at,Batch.manifest).where(Batch.finished_at.is_not(None))
            if cursor:
                from sqlalchemy import or_,and_
                stamp=datetime.fromisoformat(cursor[0])
                query=query.where(or_(Batch.finished_at>stamp,and_(Batch.finished_at==stamp,Batch.id>cursor[1])))
            for identity,finished,manifest in db.execute(query.order_by(Batch.finished_at,Batch.id).limit(limit)):
                if not night_open():return
                for item in manifest or []:
                    file=item.get('file')
                    if file:inventory.execute('INSERT OR IGNORE INTO raw_references VALUES (?,?)',(file,identity))
                if finished.tzinfo is None:finished=finished.replace(tzinfo=timezone.utc)
                state['manifest_cursor']=[finished.isoformat(),identity]
        # One source directory per step, bounded to 500 files, resume after 05:00.
        raw=Path(service.data_dir)/'raw'
        folders=sorted(p for p in raw.iterdir() if p.is_dir() and not p.name.startswith('.')) if raw.exists() else []
        source=state.get('raw_source','');last=state.get('raw_file','');chosen=next((p for p in folders if p.name>=source),None)
        if chosen:
            files=sorted(p for p in chosen.iterdir() if p.is_file() and p.name>(last if chosen.name==source else ''))[:500]
            for path in files:
                if not night_open():return
                inventory.execute('INSERT OR REPLACE INTO raw_files VALUES (?,?,?,?)',
                    (str(path.relative_to(raw)),path.stat().st_size,chosen.name,time.time()))
                state['raw_source']=chosen.name;state['raw_file']=path.name
            if not files:
                next_source=next((p.name for p in folders if p.name>chosen.name),None)
                if next_source:state['raw_source']=next_source;state['raw_file']=''
                else:state['raw_scan_complete']=True
        state['inventory_files']=inventory.execute('SELECT count(*) FROM raw_files').fetchone()[0]
        state['inventory_references']=inventory.execute('SELECT count(*) FROM raw_references').fetchone()[0]
        state['inventory_note']='배치 원문 참조 목록 · 기타 판본/보고서 참조 확인 전 삭제 대상 아님'


def step(service):
    if not night_open():return {'status':'NIGHT_WAIT'}
    with service.sessions() as db:
        if db.scalar(select(CollectionJob.id).where(CollectionJob.status=='RUNNING').limit(1)):
            return {'status':'COLLECTION_PRIORITY'}
    path=Path(service.data_dir)/'runtime'/'operations-maintenance.json'
    try:state=json.loads(path.read_text())
    except (OSError,ValueError):state={}
    try:
        if not state.get('snapshots_scan_complete'):compact_snapshots(service,state)
        if night_open():inventory(service,state)
        state.update(status='READY',last_error=None,checked_at=datetime.now(timezone.utc).isoformat())
    except Exception as error:
        state.update(status='RETRY',last_error=type(error).__name__)
    atomic_write(path,json.dumps(state,ensure_ascii=False).encode())
    return state
