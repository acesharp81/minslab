"""Actual Solar extraction of the frozen practical sample; resumable, no GPT calls."""
import json,time,argparse,hashlib
from pathlib import Path
import httpx
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:18131/');p.add_argument('--mode',default='llm');args=p.parse_args()
out=ROOT/'test-results/practice'/args.mode;out.mkdir(parents=True,exist_ok=True)
c=httpx.Client(base_url=args.url,headers={'Authorization':'Bearer '+dotenv_values(ROOT/'.env').get('HANDOVER_ACCESS_TOKEN','')},timeout=60)
def request(method,path,**kw):
 r=c.request(method,path,**kw);r.raise_for_status();return r.json()
cp=out/'checkpoint.json'
if cp.exists():case_id=json.loads(cp.read_text())['case_id']
else:
 case_id=request('POST','api/cases',json={'title':'한빛시 4개 업무 · 인수인계 상세실무편 (합성 시연)','predecessor':'김전임 (가상)','successor':'이후임 (가상)'})['id'];cp.write_text(json.dumps({'case_id':case_id}))
base='api/cases/'+case_id;details=request('GET',base)
if not details['documents']:
 sample=c.get('samples/practice.zip');sample.raise_for_status();(out/'downloaded-samples.zip').write_bytes(sample.content)
 request('POST',base+'/documents',files={'file':('practice-samples.zip',sample.content)})
if not details['current']:
 jobs=request('GET',base)['jobs'];active=next((j for j in jobs if j['status'] in ['RUNNING','QUEUED']),None)
 if not active and jobs and jobs[0]['status'] in ['FAILED','INTERRUPTED']:
  request('POST',base+'/jobs/'+jobs[0]['id']+'/retry');active=True
 if not active:
  request('POST',base+'/generate',json={'mode':args.mode,'external_consent':args.mode=='llm','request_id':'practice-e2e-'+case_id})
 print('Analysis started',case_id,flush=True)
 for i in range(1800):
  details=request('GET',base);job=details['jobs'][0]
  if i%30==0:print(job['stage'],job['progress'],flush=True)
  if job['status'] not in ['RUNNING','QUEUED']:break
  time.sleep(1)
 assert job['status']=='SUCCEEDED',job
rev=request('GET',base+'/revisions/current');(out/'extracted.json').write_text(json.dumps(rev,ensure_ascii=False,indent=2))
print('Extracted',len(rev['payload']['items']),flush=True)
if len(rev['payload']['items'])==5:
 target=next(i for i in rev['payload']['items'] if i['fields']['title']['value']=='문화시설 통합예약 개선');source=next(i for i in rev['payload']['items'] if i['fields']['title']['value']=='예약포털 접근성 보완')
 rev=request('POST',base+f'/revisions/{rev["id"]}/match',json={'expected_hash':rev['hash'],'target_id':target['id'],'source_id':source['id'],'owner':'디지털지원팀','reason':'합성 시연: 09_업무동일성_담당확인.txt의 확인자 기록을 대조. 같은 전체 사업 범위의 계획 20% → 중간 75% 보고이며 담당은 디지털지원팀으로 확인하여 연결.'})
assert len(rev['payload']['items'])==4
# Validate the exact source-authored practical brief before confirmation.
import sys
sys.path.insert(0,str(ROOT))
from app.practice_demo import PROFILES,resources
from app.flow_demo import WORKS
from app.timeline import reported_progress
checks=[]
for i,w in enumerate(WORKS):
 item=next(x for x in rev['payload']['items'] if x['fields']['title']['value']==w['title'])
 for k,v in (PROFILES[i]|resources(i)).items():
  actual=item['fields'][k]['value'];checks.append({'work':w['title'],'field':k,'exact':actual==v})
 assert reported_progress(item)==[65,40,100,75][i]
(out/'field-checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
assert all(x['exact'] for x in checks),[x for x in checks if not x['exact']]
assert rev['readiness']['missing_fields']==0
if not request('GET',base)['confirmed']:request('POST',base+f'/revisions/{rev["id"]}/confirm',json={'expected_hash':rev['hash'],'acknowledge_warnings':True})
confirmed=request('GET',base+'/revisions/confirmed');(out/'confirmed.json').write_text(json.dumps(confirmed,ensure_ascii=False,indent=2))
for fmt in ['html','md','docx']:
 r=c.get(base+f'/exports/{confirmed["id"]}.{fmt}');r.raise_for_status();(out/('practice-report.'+fmt)).write_bytes(r.content)
sources=[]
for doc in request('GET',base)['documents']:sources.append({'id':doc['id'],'path':doc['path'],'blocks':request('GET',base+'/documents/'+doc['id']+'/blocks')})
(out/'sources.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2))
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox']);ctx=browser.new_context(extra_http_headers={'Authorization':c.headers['Authorization']});page=ctx.new_page();page.goto(args.url+base+'/reports/confirmed');page.locator('.gantt-svg').wait_for();page.pdf(path=str(out/'practice-report.pdf'),format='A4',print_background=True,prefer_css_page_size=True)
 page.screenshot(path=str(out/'report-desktop.png'),full_page=True);ctx.set_extra_http_headers({'Authorization':c.headers['Authorization'],'X-Role':'successor'});second=ctx.new_page();second.goto(args.url+base+'/reports/confirmed');assert page.locator('body').inner_text()==second.locator('body').inner_text()
 page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');page.screenshot(path=str(out/'report-mobile.png'));browser.close()
result={'case_id':case_id,'revision_id':confirmed['id'],'mode':args.mode,'model':confirmed['payload']['model'],'documents':len(sources),'works':4,'profile_fields_exact':len(checks),'same_report_both_roles':True,'mobile_no_page_overflow':True,'sample_sha256':hashlib.sha256((out/'downloaded-samples.zip').read_bytes()).hexdigest()}
(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False),flush=True)
