"""Dedicated scheduled collection process, isolated from API requests."""
from contextlib import contextmanager
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import signal
import threading
from sqlalchemy import text
from .db import engine_for
from .service import HomeService
from .collection_jobs import enqueue_due,run_next

LEADER_LOCK=1019113


def worker_loop(service,lane,stop):
    while not stop.is_set():
        try:result=run_next(service,lane)
        except Exception as error:
            print(json.dumps(dict(event='collection_worker_retry',lane=lane,error_type=type(error).__name__)),flush=True)
            result=None
        if not result and lane=='BACKFILL':
            from .operations_maintenance import step
            try:step(service)
            except Exception as error:print(json.dumps(dict(event='maintenance_retry',error_type=type(error).__name__)),flush=True)
        stop.wait(1 if result else 30)


def scheduler_loop(service,stop):
    while not stop.is_set():
        try:enqueue_due(service)
        except Exception as error:
            print(json.dumps(dict(event='collection_scheduler_retry',error_type=type(error).__name__)),flush=True)
        stop.wait(60)


@contextmanager
def leader(service):
    connection=service.engine.connect().execution_options(isolation_level='AUTOCOMMIT')
    try:
        if not connection.scalar(text('SELECT pg_try_advisory_lock(:key)'),dict(key=LEADER_LOCK)):
            raise RuntimeError('다른 수집 작업자가 실행 중입니다')
        yield connection
    finally:
        try:connection.execute(text('SELECT pg_advisory_unlock(:key)'),dict(key=LEADER_LOCK))
        finally:connection.close()


def main():
    service=HomeService(engine_for(),os.environ.get('POC10_DATA_DIR','data'))
    stop=threading.Event()
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stop.set())
    folder=Path(service.data_dir)/'runtime';folder.mkdir(parents=True,exist_ok=True)
    threads=[]
    with leader(service) as connection:
        service.recover_interrupted_batches()
        if os.environ.get('POC10_AUTO_COLLECT','true').lower()=='true':
            threads.append(threading.Thread(target=scheduler_loop,args=(service,stop),name='home-collector',daemon=True))
        for lane in ('LATEST','BACKFILL'):
            threads.append(threading.Thread(target=worker_loop,args=(service,lane,stop),name='home-source-worker-'+lane,daemon=True))
        for thread in threads:thread.start()
        print(json.dumps(dict(event='collection_worker_started',pid=os.getpid(),lanes=['LATEST','BACKFILL'])),flush=True)
        try:
            while not stop.is_set():
                # Losing the leader connection exits this process. Docker then
                # restarts it; job/source leases retain idempotent recovery.
                connection.execute(text('SELECT 1'))
                state=dict(checked_at=datetime.now(timezone.utc).isoformat(),pid=os.getpid(),lanes=['LATEST','BACKFILL'],running_threads=[t.name for t in threads if t.is_alive()])
                temporary=folder/'collection-worker-health.tmp';temporary.write_text(json.dumps(state))
                os.replace(temporary,folder/'collection-worker-health.json')
                stop.wait(10)
        finally:
            stop.set()
            for thread in threads:thread.join(timeout=5)


if __name__=='__main__':main()
