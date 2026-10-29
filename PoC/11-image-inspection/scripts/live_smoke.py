"""Explicit, small paid API smoke test. Does not print any credentials or content."""
from pathlib import Path
import sys,time,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from app.config import Settings
s=Settings()
with httpx.Client(base_url='http://127.0.0.1:18110',timeout=15) as c:
    c.post('/api/login',json={'role':'admin','password':s.get('ADMIN_PASSWORD')}).raise_for_status()
    j=c.post('/api/demo').json();jid=j['id']
    r=c.post('/api/jobs/'+jid+'/runs',json={'mode':'live','vision_model':'gpt-6.1-sol','analysis_model':'solar-pro4','consent':True,'force':True,'rule_ids':['D-02-e','D-02-l','H-04-i']});r.raise_for_status()
    print('Started limited live smoke:',jid,flush=True)
    for _ in range(240):
        j=c.get('/api/jobs/'+jid).json()
        if j['state'] not in ('QUEUED','RUNNING'):break
        time.sleep(1)
    run=j['runs'][-1]
    summary={'job_id':jid,'state':j['state'],'calls':run['calls'],'results':[{k:r[k] for k in ('rule_id','instance_id','status','reason','cell_ids')} for r in run['results'] if r['rule_id'] in run['selected']],'analysis':run['analysis']}
    (s.data/'live-smoke.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False),flush=True)
