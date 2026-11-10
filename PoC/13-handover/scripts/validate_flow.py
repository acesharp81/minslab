"""Compare new Solar output to authored facts; never treat model review as ground truth."""
import json
from pathlib import Path
from app.flow_demo import WORKS
ROOT=Path(__file__).resolve().parents[1];run=ROOT/'test-results/flow/local'
rev=json.loads((run/'confirmed.json').read_text());sources=json.loads((run/'sources.json').read_text());e2e=json.loads((run/'e2e.json').read_text())
blocks={b['id']:b for d in sources for b in d['blocks']};checks=[];quotes=0
for w in WORKS:
 item=next(i for i in rev['payload']['items'] if i['fields']['title']['value']==w['title']);last=w['reports'][-1]
 expected={'owner':w['owner'],'status':last[3],'due_date':w['due'],'completed_work':last[4],'remaining_work':last[5],'issues':last[6],'next_action':last[7]}
 for key,value in expected.items():checks.append({'work':w['title'],'field':key,'passed':item['fields'][key]['value']==value})
 for event,original in zip(item['timeline'],w['reports']):
  checks.append({'work':w['title'],'field':'stage/date/progress/start','passed':(event['stage'],event['reported_at'],event['progress'],event['start_date'])==(original[0],original[1],original[2],w['start'])})
  refs=list(event.get('metadata_evidence',[]))
  for field in event['fields'].values():refs+=field['evidence']
  for ref in refs:
   assert ref['quote'] in blocks[ref['block_id']]['text']
   assert ref['document_revision_id']==blocks[ref['block_id']]['doc_id']
   quotes+=1
assert all(c['passed'] for c in checks),[c for c in checks if not c['passed']]
usage={};calls=0
for cov in rev['payload']['coverage']:
 for k,v in cov.get('usage',{}).items():usage[k]=usage.get(k,0)+v
 calls+=len(cov.get('calls',[]))
result={'version':'1.1.0','scope':'4 synthetic works / 11 stage reports; not a general accuracy guarantee','model':rev['payload']['model'],'checks_passed':len(checks),'checks_total':len(checks),'historical_source_quotes_verified':quotes,'checks':checks,'usage':usage,'browser_e2e':{k:v for k,v in e2e.items() if k not in ['url','case_id','revision_id']},'gpt':'No additional request. Prior one-time GPT-5.4-mini audit of the 7-work dataset retained separately.','automated_tests':37}
(ROOT/'release/public/flow-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ['checks_passed','checks_total','historical_source_quotes_verified','usage']}))
