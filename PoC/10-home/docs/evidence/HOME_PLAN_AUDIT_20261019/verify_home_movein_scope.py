import json,re
from pathlib import Path
from datetime import datetime,timezone
from backend.sources import SOURCES
from backend.collectors import Fetcher
from backend.lh_public_history import attachments,movein_rows,name_area
src=next(r for r in SOURCES if r['id']=='lh_movein_history');f=Fetcher(src['id'],Path('/app/data/plan-audit-raw-20261019'))
result={'checked_at':datetime.now(timezone.utc).isoformat(),'files':[]}
try:
 for label,url in attachments(src,f):
  m=re.search(r'(20\d{2})',label)
  if not(m and '입주계획' in label and re.search(r'\.(hwpx|docx)',label,re.I)):continue
  year=int(m[1]);suffix='hwpx' if '.hwpx' in label else 'docx'
  rows,content=movein_rows(f.get(url,suffix));excluded=[r for r in rows if not name_area(r[0])[0]]
  explicit=[r for r in rows if re.sub(r'\s','',r[0]).startswith('인천')]
  item={'year':year,'url':url,'original_file':f.manifest[-1]['file'],'rows':rows,'name_unlocated_rows':excluded,'explicit_incheon_rows':explicit}
  result['files'].append(item)
  print(year,'national',len(rows),'explicit_incheon',len(explicit),'units',sum(int(r[4].replace(',','')) for r in explicit),'names',sorted(set(r[0] for r in explicit)),flush=True)
finally:
 result['manifest']=f.manifest;f.close();Path('/app/data/plan-audit-movein-20261019.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
