"""Durable per-source collection, linking and snapshot jobs with lease recovery."""
from datetime import timedelta, timezone
import os
import threading
from sqlalchemy import select, text, func, or_, and_
from sqlalchemy.exc import IntegrityError
from .db import CollectionJob, Batch, now, uid
from .service import as_utc
from .sources import SOURCES
from .collection_policy import structural_failure, unchanged_collection, backfill_window_open, REPAIR_MARKER
from zoneinfo import ZoneInfo
from .operations_window import night_open, next_night, bulk_work, NightWindowClosed

ACTIVE = ('QUEUED', 'RUNNING', 'RETRY')
# Public notice changes are checked separately from expensive historic backfill.
FAST = {'molit_press_watch':3600, 'opm_press_watch':3600, 'sh_notice_watch':3600, 'lh_press_watch':3600, 'ih_press_watch':3600, 'seoul_press_watch':3600, 'newsis_housing_watch':3600,
        'lh_notice': 7200, 'lh_notice_detail': 14400, 'gh_notice': 7200, 'ih_notice':7200,
        'sh_inventory': 21600, 'seoul_cleanup': 21600, 'gh_completion_evidence': 21600}

DAYTIME = {k for k in FAST if k.endswith('_watch')} | {'lh_notice','gh_notice','ih_notice'}


def collection_context_unchanged(service, source_id):
    # Completeness/coverage/backfill metadata can change without a new fact row.
    # Preserve those changes and the first successful run in downstream views.
    with service.sessions() as db:
        rows=db.scalars(select(Batch).where(Batch.source_id==source_id, Batch.status=='SUCCESS').order_by(Batch.finished_at.desc()).limit(2)).all()
        if len(rows)<2:
            return False
        volatile={'new','changed','unchanged','record_count','entity_ids'}
        states=[{k:v for k,v in (row.stats or {}).items() if k not in volatile} for row in rows]
        return states[0]==states[1]


def enqueue(service, source_id, force=False):
    source = next((s for s in SOURCES if s['id'] == source_id), None)
    if source and source.get('collection_mode')=='AI_DISCOVERY':
        raise ValueError('신규 자료 검토의 AI 자료 수집 자동화에서 실행하세요')
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
                if last_batch and source.get('backfill_seconds') and ((last_batch.stats or {}).get('scope_remaining_dongs',0)>0 or (last_batch.stats or {}).get('backfill_pending')) and backfill_window_open(now()):
                    start = now().astimezone(ZoneInfo('Asia/Seoul')).replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc)
                    successes = db.scalar(select(func.count(Batch.id)).where(Batch.source_id==source_id, Batch.status=='SUCCESS', Batch.finished_at>=start))
                    if successes < 3:
                        seconds = max(3600, source['backfill_seconds'])
                if last and as_utc(last) > now()-timedelta(seconds=seconds):
                    return None
                failed = db.scalar(select(CollectionJob).where(CollectionJob.source_id == source_id, CollectionJob.status == 'FAILED').order_by(CollectionJob.finished_at.desc()).limit(1))
                cooldown = 24 if failed and (failed.error or '').startswith(REPAIR_MARKER) else 1
                if failed and failed.finished_at and as_utc(failed.finished_at) > now()-timedelta(hours=cooldown):
                    return None
            job = CollectionJob(source_id=source_id, status='QUEUED', stage='COLLECT', run_after=now(), result={'manual':bool(force)})
            db.add(job); db.flush()
            return job.id
    except IntegrityError:
        return None  # Another scheduler already queued this source.


def enqueue_due(service):
    """Read all due-state metadata once; recheck only eligible sources under enqueue."""
    instant=now()
    candidates=[s for s in SOURCES if not s.get('manual_only') and s.get('implemented',True)
        and (night_open(instant) or s['id'] in DAYTIME)
        and (not s.get('requires_key_for_schedule') or any(os.environ.get(k,'').strip() for k in (s.get('key_env') or '',s.get('fallback_key_env') or '')))]
    if not candidates:return []
    with service.sessions() as db:
        active=set(db.scalars(select(CollectionJob.source_id).where(CollectionJob.status.in_(ACTIVE))))
        success=dict(db.execute(select(Batch.source_id,func.max(Batch.finished_at)).where(Batch.status=='SUCCESS').group_by(Batch.source_id)).all())
        failed={}
        for sid,finished,error in db.execute(select(CollectionJob.source_id,CollectionJob.finished_at,CollectionJob.error).where(
                CollectionJob.status=='FAILED',CollectionJob.finished_at>=instant-timedelta(hours=24)).order_by(CollectionJob.finished_at.desc())):
            failed.setdefault(sid,(as_utc(finished),error))
    result=[]
    for source in sorted(candidates,key=lambda s:s['id'] not in DAYTIME):
        sid=source['id']
        if sid in active:continue
        seconds=FAST.get(sid,source.get('refresh_days',1)*86400)
        # Backfill's detailed quota/coverage check remains in enqueue().
        if not (source.get('backfill_seconds') and night_open(instant)) and success.get(sid) and as_utc(success[sid])>instant-timedelta(seconds=seconds):continue
        failure=failed.get(sid)
        if failure and failure[0]>instant-timedelta(hours=24 if (failure[1] or '').startswith(REPAIR_MARKER) else 1):continue
        identity=enqueue(service,sid)
        if identity:result.append(identity)
    return result


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
        if not night_open(instant):
            query=query.where(or_(CollectionJob.result['manual'].as_boolean().is_(True),
                and_(CollectionJob.stage=='COLLECT',CollectionJob.source_id.in_(DAYTIME))))
        if lane=='LATEST':query=query.where(CollectionJob.source_id.in_(FAST))
        elif lane=='BACKFILL':query=query.where(CollectionJob.source_id.not_in(FAST))
        job = db.scalar(query.order_by(CollectionJob.run_after, CollectionJob.created_at).with_for_update(skip_locked=True).limit(1))
        if job is None:return None
        job.status='RUNNING'; job.attempts+=1; job.lease_until=instant+timedelta(minutes=10)
        job.lease_token=uid()
        return dict(id=job.id, source_id=job.source_id, stage=job.stage, attempts=job.attempts,lease_token=job.lease_token,manual=bool((job.result or {}).get('manual')))


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
            with bulk_work(not job['manual'] and job['source_id'] not in DAYTIME):
                result=service.collect_one(source)
            if result.get('status')=='PAUSED':raise NightWindowClosed(result['error'])
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
            if result.get('status')!='SUCCESS':
                if structural_failure(result.get('error')):
                    with service.sessions.begin() as db:
                        row=db.get(CollectionJob,job['id'],with_for_update=True)
                        if row.status!='RUNNING' or row.lease_token!=job['lease_token']:
                            return dict(id=job['id'],status='STALE_WORKER')
                        row.status='FAILED';row.finished_at=now();row.lease_until=None
                        row.result=dict(row.result or {},COLLECT=result)
                        row.error=REPAIR_MARKER+str(result.get('error',''))[:240]
                    return dict(job,status='FAILED',reason='SOURCE_REPAIR_REQUIRED',retry_after_hours=24)
                raise RuntimeError('원천 수집 미완료 · 배치 이력 참조')
            # Preserve fresh collection history, but do not rebuild all business
            # projections or freeze another snapshot when no source fact changed.
            next_stage=None if source.get('discovery_only') or (unchanged_collection(result) and collection_context_unchanged(service,job['source_id'])) else 'LINK'
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
            row.run_after=(next_night(now()) if next_stage and not job['manual'] else now());row.attempts=0
            if not next_stage:row.finished_at=now()
        return dict(job, status='ADVANCED' if next_stage else 'SUCCESS', next_stage=next_stage)
    except NightWindowClosed:
        with service.sessions.begin() as db:
            row=db.get(CollectionJob,job['id'],with_for_update=True)
            if row.status=='RUNNING' and row.lease_token==job['lease_token']:
                row.status='QUEUED';row.run_after=next_night(now());row.lease_until=None
                row.attempts=max(0,row.attempts-1);row.error='야간 시간 대기 · 01:00~05:00 KST'
        return dict(job,status='PAUSED')
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
