"""Dry run by default; --apply deletes expired inspections, retaining token ledgers."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import sys,argparse,shutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.storage import Store
p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');a=p.parse_args();s=Settings();store=Store(s.data/'inspection.sqlite3')
cutoff=datetime.now(timezone.utc)-timedelta(days=s.integer('RETENTION_DAYS',30))
with store.connect() as c:
    import json
    jobs=[json.loads(r[0]) for r in c.execute('SELECT body FROM jobs WHERE created<?',(cutoff.isoformat(),))]
for j in jobs:
    if j['state'] in ('QUEUED','RUNNING'):continue
    print('DELETE' if a.apply else 'WOULD_DELETE',j['id'])
    if a.apply:
        with store.connect() as c:c.execute('DELETE FROM jobs WHERE id=?',(j['id'],))
        shutil.rmtree(s.data/j['id'],ignore_errors=True);store.audit('retention','DELETE',j['id'],{'retention_days':s.integer('RETENTION_DAYS',30)})
