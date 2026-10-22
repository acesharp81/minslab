"""Periodic regional materialization, isolated from API and external collectors."""
import fcntl
import json
import os
import signal
import threading
from datetime import datetime,timezone
from .area_snapshot import folder,refresh,atomic_json,CHECK_SECONDS
from .db import engine_for
from .service import HomeService

def main():
    service=HomeService(engine_for(),os.environ.get('POC10_DATA_DIR','data'))
    root=folder(service);root.mkdir(parents=True,exist_ok=True)
    stop=threading.Event();state={'status':'STARTING'}
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stop.set())
    with (root/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        def heartbeat():
            while not stop.is_set():
                atomic_json(root/'health.json',dict(state,checked_at=datetime.now(timezone.utc).isoformat(),pid=os.getpid()))
                stop.wait(10)
        thread=threading.Thread(target=heartbeat,name='area-snapshot-heartbeat',daemon=True);thread.start()
        try:
            while not stop.is_set():
                try:
                    changed=refresh(service,state,stop)
                    print(json.dumps(dict(event='area_snapshot_refresh',years=changed,status=state['status'])),flush=True)
                except Exception as error:
                    state.update(status='RETRYING',last_error=type(error).__name__)
                    print(json.dumps(dict(event='area_snapshot_retry',error_type=type(error).__name__)),flush=True)
                stop.wait(60 if state['status']=='RETRYING' else CHECK_SECONDS)
        finally:stop.set();thread.join(timeout=2)

if __name__=='__main__':main()
