"""Durable per-source collection, linking and snapshot jobs with lease recovery."""
from datetime import timedelta
import os
import threading
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from .db import CollectionJob, Batch, now, uid
from .service import as_utc
from .sources import SOURCES

ACTIVE = ('QUEUED', 'RUNNING', 'RETRY')
# Public notice changes are checked separately from expensive historic backfill.
FAST = {'molit_press_watch':3600, 'opm_press_watch':3600, 'sh_notice_watch':3600, 'lh_press_watch':3600, 'ih_press_watch':3600, 'seoul_press_watch':3600, 'newsis_housing_watch':3600,
        'lh_notice': 900, 'lh_notice_detail': 1800, 'gh_notice': 1800, 'ih_notice':3600,
        'sh_inventory': 3600, 'seoul_cleanup': 3600, 'gh_completion_evidence': 3600}


def enqueue(service, source_id, force=False):
    source = next((s for s in SOURCES if s['id'] == source_id), None)
    if source is None or source.get('implemented', True) is False:
        raise ValueError('지원하지 않는 원천입니다')
    try:
        with service.sessions.begin() as db:
            if db.scalar(select(CollectionJob.id).where(CollectionJob.source_id == source_id, CollectionJob.status.in_(ACTIVE))):
                return None
            if not force:
                last_batch = db.scalar(select(Batch).where(Batch.source_id == source_id, Batch.status == 'SUCCESS').order_by(Batch.finished_at.desc()).limit(1))
                last = last_batch.finished_at if last_batch else None
                seconds = FAST.get(source_id, source.get('refresh_days', 1)*86400)
                if last_batch and source.get('backfill_seconds') and ((last_batch.stats or {}).get('scope_remaining_dongs',0)>0 or (last_batch.stats or {}).get('backfill_pending')):
                    seconds = source['backfill_seconds']
                if last and as_utc(last) > now()-timedelta(seconds=seconds):
                    return None
                failed = db.scalar(select(CollectionJob.finished_at).where(CollectionJob.source_id == source_id, CollectionJob.status == 'FAILED').order_by(CollectionJob.finished_at.desc()).limit(1))
                if failed and as_utc(failed) > now()-timedelta(hours=1):
                    return None
            job = CollectionJob(source_id=source_id, status='QUEUED', stage='COLLECT', run_after=now())
            db.add(job); db.flush()
            return job.id
    except IntegrityError:
        return None  # Another scheduler already queued this source.


def enqueue_due(service):
    return [identity for s in sorted(SOURCES, key=lambda s:s['id'] not in FAST)
            if not s.get('manual_only') and s.get('implemented', True)
            if not s.get('requires_key_for_schedule') or any(os.environ.get(name,'').strip() for name in (s.get('key_env') or '',s.get('fallback_key_env') or ''))
            if (identity := enqueue(service, s['id']))]


def claim(service, lane=None):
    instant = now()
    with service.sessions.begin() as db:
        if service.engine.dialect.name == 'postgresql':
            db.execute(text('SELECT pg_advisory_xact_lock(1019112)'))
        expired = db.scalars(select(CollectionJob).where(CollectionJob.status == 'RUNNING', CollectionJob.lease_until < instant)).all()
        for job in expired:
            job.status='RETRY'; job.run_after=instant; job.error='작업 임대 만료 · 같은 단계부터 재시도'
        db.flush()
        query=select(CollectionJob).where(CollectionJob.status.in_(('QUEUED','RETRY')), CollectionJob.run_after <= instant)
        if lane=='LATEST':query=query.where(CollectionJob.source_id.in_(FAST))
        elif lane=='BACKFILL':query=query.where(CollectionJob.source_id.not_in(FAST))
        job = db.scalar(query.order_by(CollectionJob.run_after, CollectionJob.created_at).with_for_update(skip_locked=True).limit(1))
        if job is None:return None
        job.status='RUNNING'; job.attempts+=1; job.lease_until=instant+timedelta(minutes=10)
        job.lease_token=uid()
        return dict(id=job.id, source_id=job.source_id, stage=job.stage, attempts=job.attempts,lease_token=job.lease_token)


def run_next(service, lane=None):
    job=claim(service,lane)
    if not job:return None
    done=threading.Event()
    def heartbeat():
        while not done.wait(30):
            try:
                with service.sessions.begin() as db:
                    row=db.get(CollectionJob, job['id'])
                    if row.status=='RUNNING' and row.lease_token==job['lease_token']:row.lease_until=now()+timedelta(minutes=10)
                    else:return
            except Exception:pass
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    try:
        source=next(s for s in SOURCES if s['id']==job['source_id'])
        if job['stage']=='COLLECT':
            result=service.collect_one(source)
            if result.get('status')=='BUSY':
                # Manual backfills hold the same source lock. Contention is not
                # a source failure and must not exhaust the five retry attempts.
                with service.sessions.begin() as db:
                    row=db.get(CollectionJob,job['id'],with_for_update=True)
                    if row.status!='RUNNING' or row.lease_token!=job['lease_token']:
                        return dict(id=job['id'],status='STALE_WORKER')
                    row.status='QUEUED';row.attempts=max(0,row.attempts-1)
                    row.run_after=now()+timedelta(seconds=60);row.lease_until=None;row.error=None
                return dict(job,status='BUSY',next_stage='COLLECT')
            if result.get('status')!='SUCCESS':raise RuntimeError('원천 수집 미완료 · 배치 이력 참조')
            # Discovery has no approved business facts to reconcile.
            next_stage=None if source.get('discovery_only') else 'LINK'
        elif job['stage']=='LINK':
            from .stage_evidence import refresh
            from .project_collection import refresh_links
            from .evidence_bridge import reconcile
            # Readiness changes at any primary source must reach downstream views.
            attribution=dict(actor='김민',reason='담당자 확인(자동연결)')
            stage=refresh(service,refresh_candidates=True,**attribution)
            collection=refresh_links(service,**attribution)
            bridge=reconcile(service,apply=True,**attribution)
            result=dict(stage=stage,collection=collection,bridges={k:v for k,v in bridge.items() if k not in ('proposals','held')})
            next_stage='SNAPSHOT'
        else:
            from .independent_metrics import freeze
            frozen=freeze(service,'자동 수집','원천 갱신 후 독립 사건 집계 기준본 생성')
            result=dict(snapshot_id=frozen['id'], counts=frozen['result']['counts'])
            next_stage=None
        with service.sessions.begin() as db:
            row=db.get(CollectionJob,job['id'],with_for_update=True)
            if row.status!='RUNNING' or row.lease_token!=job['lease_token']:return dict(id=job['id'],status='STALE_WORKER')
            row.result=dict(row.result or {},**{job['stage']:result});row.error=None;row.lease_until=None
            row.stage=next_stage or job['stage'];row.status='QUEUED' if next_stage else 'SUCCESS'
            row.run_after=now();row.attempts=0
            if not next_stage:row.finished_at=now()
        return dict(job, status='ADVANCED' if next_stage else 'SUCCESS', next_stage=next_stage)
    except Exception as error:
        with service.sessions.begin() as db:
            row=db.get(CollectionJob,job['id'],with_for_update=True)
            if row.status!='RUNNING' or row.lease_token!=job['lease_token']:return dict(id=job['id'],status='STALE_WORKER')
            row.status='FAILED' if row.attempts>=5 else 'RETRY'
            row.error=f'{job["stage"]}: {type(error).__name__} · 배치/작업 이력 확인'
            row.lease_until=None;row.run_after=now()+timedelta(seconds=min(3600,60*2**row.attempts))
            if row.status=='FAILED':row.finished_at=now()
        return dict(job,status='RETRY' if job['attempts']<5 else 'FAILED')
    finally:
        done.set();thread.join(timeout=1)


def status(service):
    with service.sessions() as db:
        rows=db.scalars(select(CollectionJob).order_by(CollectionJob.created_at.desc()).limit(100)).all()
        return [dict(id=r.id,source_id=r.source_id,status=r.status,stage=r.stage,attempts=r.attempts,
                     created_at=as_utc(r.created_at).isoformat(),run_after=as_utc(r.run_after).isoformat(),
                     finished_at=as_utc(r.finished_at).isoformat() if r.finished_at else None,error=r.error) for r in rows]
