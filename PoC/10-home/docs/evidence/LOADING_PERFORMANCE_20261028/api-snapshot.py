import json,httpx,time,sys
from pathlib import Path
root=Path('PoC/10-home/docs/evidence/LOADING_PERFORMANCE_20261028');label=sys.argv[1];out=[]
paths={'policy':'/policy-delivery/view?as_of_date=2026-10-28&group=policy&scope=policy','monitor':'/policy-monitor?as_of_date=2026-10-28&policy_id=POL_2025_0907','mappings':'/mappings?as_of_date=2026-10-28&policy_id=POL_2025_0907&compact=true','project':'/project-information/PRO_97cb44fc1d3d65cddf98e848'}
with httpx.Client(base_url='http://127.0.0.1:18100/poc/home/api',timeout=90) as client:
 for key,path in paths.items():
  start=time.monotonic();response=client.get(path);response.raise_for_status();data=response.json()
  (root/(label+'-'+key+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2))
  out.append(dict(key=key,seconds=round(time.monotonic()-start,3),bytes=len(response.content),cache=response.headers.get('x-home-cache')))
(root/(label+'-api.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2));print(out)
