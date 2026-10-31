"""Independent lightweight worker; no LLM or HTTP work in page requests."""
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import signal
import threading
from .db import engine_for
from .service import HomeService
from .ai_collection import process_run
from .ai_collection_store import Store


def tick(service, store):
    store.heartbeat()
    from .ai_collection_budget import flush, required
    if required(): flush(store)
    from .ai_agents_store import settings,enqueue
    from .ai_agent_catalog import ROLES
    from .ai_agent_workflows import process
    current=datetime.now(ZoneInfo('Asia/Seoul'))
    for role,config in settings(store).items():
        if config['enabled'] and current.hour>=config['hour_kst']:
            day=current.date().isoformat()
            try: enqueue(store,role,day if role=='collection' else role+':'+day)
            except ValueError: continue
    run=store.claim()
    if run:
        if run['config'].get('agent_role','collection')=='collection':process_run(service,store,run)
        else:process(service,store,run)



def main():
    service=HomeService(engine_for(),os.environ.get('POC10_DATA_DIR','data'))
    store=Store(service.data_dir); stop=threading.Event()
    for sig in (signal.SIGTERM,signal.SIGINT): signal.signal(sig,lambda *_:stop.set())
    def heartbeat():
        while not stop.is_set():
            store.heartbeat(); stop.wait(20)
    thread=threading.Thread(target=heartbeat,daemon=True); thread.start()
    while not stop.is_set():
        try: tick(service,store)
        except Exception as error: print('ai_collection_worker: '+type(error).__name__,flush=True)
        stop.wait(10)


if __name__=='__main__': main()
