"""One actual Solar extraction pass; replay extracted evidence for permutation tests."""
import json,time,copy,random,sys,hashlib
from pathlib import Path
import httpx
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.timeline import reported_progress,project_latest
from app.engine import merge_candidates,annotate_items,FIELDS
OUT=ROOT/'test-results/versions/live';OUT.mkdir(parents=True,exist_ok=True)
c=httpx.Client(base_url='http://127.0.0.1:18130/',headers={'Authorization':'Bearer '+dotenv_values(ROOT/'.env')['HANDOVER_ACCESS_TOKEN']},timeout=60)
def req(method,path,**kw):
 r=c.request(method,path,**kw);r.raise_for_status();return r.json()
cp=OUT/'checkpoint.json'
if cp.exists():cid=json.loads(cp.read_text())['case_id']
else:
 cid=req('POST','api/cases',json={'title':'본문으로 최신본 찾기 · 중앙부처 4개 사업 (합성 시연)','predecessor':'김전임 (가상)','successor':'이후임 (가상)'})['id'];cp.write_text(json.dumps({'case_id':cid}))
base='api/cases/'+cid;d=req('GET',base)
if not d['documents']:req('POST',base+'/versions-demo')
if not d['current'] or any(j['status'] in ['RUNNING','QUEUED'] for j in d['jobs']):
 jobs=req('GET',base)['jobs'];active=any(j['status'] in ['RUNNING','QUEUED'] for j in jobs)
 if jobs and jobs[0]['status'] in ['FAILED','INTERRUPTED']:raise RuntimeError('Existing failed job: inspect before retry')
 if not active:req('POST',base+'/generate',json={'mode':'llm','external_consent':True,'request_id':'versions-live-'+cid})
 last=None
 for _ in range(1800):
  d=req('GET',base);job=d['jobs'][0];stage=(job['stage'],job['progress'])
  if stage!=last:print('Solar',stage,flush=True);last=stage
  if job['status'] not in ['RUNNING','QUEUED']:break
  time.sleep(1)
 assert job['status']=='SUCCEEDED',job
rev=req('GET',base+'/revisions/current');(OUT/'extracted.json').write_text(json.dumps(rev,ensure_ascii=False,indent=2))
expected=json.loads((ROOT/'release/public/version-expected.json').read_text())['expected_works']
items=rev['payload']['items'];checks=[]
checks.append({'check':'4개 사업으로 자동 연결','pass':len(items)==4})
for e in expected:
 item=next((i for i in items if i['fields']['title']['value']==e['title']),None)
 checks.append({'work':e['title'],'check':'본문 사업명','pass':item is not None})
 if not item:continue
 latest=next((t for t in item['timeline'] if t['document_id']==item.get('latest_document_id')),None)
 checks.append({'work':e['title'],'check':'최신 파일 선택','pass':bool(latest and latest['path']==e['file']),'actual':latest['path'] if latest else None})
 checks.append({'work':e['title'],'check':'진행률','pass':reported_progress(item)==e['progress'],'actual':reported_progress(item)})
 for key in ['status','owner','due_date','issues','remaining_work','next_action']:
  actual=item['fields'][key]['value'];checks.append({'work':e['title'],'check':key,'pass':actual==e[key],'actual':actual,'expected':e[key]})
 for key in ['overview','objectives','scope','implementation_plan','completed_work','future_plan','operating_steps','completion_criteria','deliverables','approval_route','document_locations','budget','contacts','collaborators']:
  value=item['fields'][key]['value'];checks.append({'work':e['title'],'check':'상세 항목 '+key,'pass':bool(value),'actual':value})
 if e['work_code']=='MB26-01':
  checks.append({'work':e['title'],'check':'PDF 예산 잔액까지 인용','pass':'144,000,000' in item['fields']['budget']['value']})
  checks.append({'work':e['title'],'check':'PDF 추후 계획 끝까지 인용','pass':'변경 일정 별도 승인' in item['fields']['future_plan']['value']})
# A replay uses the raw per-document evidence already extracted by Solar; zero new model calls.
raw=[]
for item in items:
 for event in item.get('timeline',[]):
  raw.append({'candidates':[{'id':event['document_id'],'fields':copy.deepcopy(event['fields']),'timeline':[copy.deepcopy(event)],'source_documents':[event['document_id']]}]})
def fingerprint(values):return sorted((i['fields']['title']['value'],reported_progress(i),tuple((k,i['fields'][k]['value']) for k in FIELDS if k!='title')) for i in values)
baseline=fingerprint(items)
for seed in range(20):
 data=copy.deepcopy(raw);random.Random(seed).shuffle(data)
 for n,r in enumerate(data):
  e=r['candidates'][0]['timeline'][0];e['path']=f'{999-n}_아무제목.tmp';e['document_id']=f'renamed-{seed}-{n}';r['candidates'][0]['source_documents']=[e['document_id']]
 replay=annotate_items([project_latest(i) for i in merge_candidates(data)])
 checks.append({'check':f'추출 결과 재사용 · 파일명/문서ID/순서 변경 {seed+1}','pass':fingerprint(replay)==baseline})
# Validate every persisted quote against its actual source block.
blocks={};quote_count=0
for i in items:
 for field in i['fields'].values():
  for ref in field['evidence']:
   bid=ref['block_id']
   if bid not in blocks:blocks[bid]=req('GET',base+'/blocks/'+bid)
   assert ref['quote'] in blocks[bid]['text'];quote_count+=1
coverage=rev['payload']['coverage']
result={'case_id':cid,'revision_id':rev['id'],'model':rev['payload']['model'],'resolved_models':sorted({r.get('resolved_model','') for r in coverage}),'documents':len(coverage),'works':len(items),'checks':checks,'all_checks_pass':all(x['pass'] for x in checks),'verified_quotes':quote_count,'model_calls':sum(len(r.get('calls',[])) for r in coverage),'usage':{k:sum(r.get('usage',{}).get(k,0) for r in coverage) for k in ['prompt_tokens','completion_tokens','total_tokens']},'permutation_method':'동일 Solar 원문 추출 결과를 재사용한 20회 재연결·판본선택 검사. 20회 모델 재호출은 하지 않음.','sample_sha256':hashlib.sha256((ROOT/'release/public/version-samples.zip').read_bytes()).hexdigest()}
(OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({'case_id':cid,'works':len(items),'checks':len(checks),'failed':[x for x in checks if not x['pass']],'usage':result['usage']},ensure_ascii=False),flush=True)
assert result['all_checks_pass'],'Inspect extracted.json and result.json before confirming'
if not req('GET',base)['confirmed']:req('POST',base+f'/revisions/{rev["id"]}/confirm',json={'expected_hash':rev['hash'],'acknowledge_warnings':True})
confirmed=req('GET',base+'/revisions/confirmed');(OUT/'confirmed.json').write_text(json.dumps(confirmed,ensure_ascii=False,indent=2))
for fmt in ['html','md','docx']:
 r=c.get(base+f'/exports/{confirmed["id"]}.{fmt}');r.raise_for_status();(OUT/('version-report.'+fmt)).write_bytes(r.content)
html=c.get(base+'/reports/confirmed');second=c.get(base+'/reports/confirmed',headers={'X-Role':'successor'});assert html.content==second.content
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox']);ctx=browser.new_context(extra_http_headers={'Authorization':c.headers['Authorization']});page=ctx.new_page();page.goto(str(c.base_url)+base+'/reports/confirmed');page.locator('.gantt-svg').wait_for()
 assert page.get_by_text('최신본 채택·구판 및 초안 제외 근거',exact=False).count()==4
 page.pdf(path=str(OUT/'version-report.pdf'),format='A4',print_background=True,prefer_css_page_size=True)
 page.screenshot(path=str(OUT/'report-desktop.png'),full_page=True)
 page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');browser.close()
result.update(same_report_both_roles=True,mobile_no_page_overflow=True,report_formats=['html','pdf','md','docx'])
(OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print('CONFIRMED',cid,flush=True)
