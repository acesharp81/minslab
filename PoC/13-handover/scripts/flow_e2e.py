"""Downloaded synthetic reports -> Solar -> human matching -> same final report."""
import argparse, json, time, hashlib
from pathlib import Path
from urllib.parse import urljoin
import httpx
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:18131/');p.add_argument('--stage',default='local');p.add_argument('--mode',choices=['llm','rules'],default='llm');args=p.parse_args()
out=ROOT/'test-results/flow'/args.stage;out.mkdir(parents=True,exist_ok=True)
token=dotenv_values(ROOT/'.env').get('HANDOVER_ACCESS_TOKEN','')
c=httpx.Client(base_url=args.url,headers={'Authorization':'Bearer '+token},timeout=30)
def request(method,path,**kw):
 r=c.request(method,path,**kw);r.raise_for_status();return r.json()
cp=out/'checkpoint.json'
if cp.exists():case_id=json.loads(cp.read_text())['case_id']
else:
 case_id=request('POST','api/cases',json={'title':'4개 업무 흐름 · 간트 차트 시연','predecessor':'김전임 (합성)','successor':'이후임 (합성)'})['id'];cp.write_text(json.dumps({'case_id':case_id}))
base='api/cases/'+case_id;details=request('GET',base)
if not details['documents']:
 sample=c.get('samples/flow.zip');sample.raise_for_status();(out/'downloaded-samples.zip').write_bytes(sample.content)
 request('POST',base+'/documents',files={'file':('flow-samples.zip',sample.content)})
if not details['current']:
 jobs=request('GET',base)['jobs'];active=next((j for j in jobs if j['status'] in ['RUNNING','QUEUED']),None)
 if not active:
  request('POST',base+'/generate',json={'mode':args.mode,'external_consent':args.mode=='llm','request_id':'flow-e2e-'+case_id})
 print('Analysis started',case_id,flush=True)
 for i in range(600):
  details=request('GET',base);job=details['jobs'][0]
  if job['status'] not in ['RUNNING','QUEUED']:break
  time.sleep(1)
 assert job['status']=='SUCCEEDED',job
rev=request('GET',base+'/revisions/current')
if not (out/'revision.json').exists():(out/'revision.json').write_text(json.dumps(rev,ensure_ascii=False,indent=2))
print('Analysis finished',len(rev['payload']['items']),flush=True)
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True);page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(args.url)
 if page.locator('#accessToken').is_visible():page.locator('#accessToken').fill(token);page.get_by_role('button',name='접속하기',exact=True).click()
 page.get_by_role('button',name='4개 업무 흐름 체험').wait_for()
 page.goto(args.url+'#'+case_id);page.locator('.tab[data-tab="review"]').click()
 if len(rev['payload']['items'])==5:
  card=page.locator('.work-card').filter(has=page.get_by_role('heading',name='예약포털 접근성 보완',exact=True));card.get_by_role('button',name='같은 업무로 매칭',exact=True).click()
  target=next(i for i in rev['payload']['items'] if i['fields']['title']['value']=='문화시설 통합예약 개선')
  page.locator('#matchTarget').select_option(target['id']);page.locator('#matchOwner').fill('디지털지원팀');page.locator('#matchReason').fill('HB-004 동일 사업이며 디지털지원팀 담당임을 전임자에게 확인한 합성 시나리오');page.locator('#matchCheck').check();page.screenshot(path=str(out/'01-match.png'))
  page.get_by_role('button',name='확인 후 새 판본에 매칭',exact=True).click();page.locator('#dialog').wait_for(state='hidden')
  expect(page.locator('.work-card')).to_have_count(4)
 rev=request('GET',base+'/revisions/current');assert len(rev['payload']['items'])==4
 if not request('GET',base)['confirmed']:
  page.get_by_role('button',name='검토 완료 · 확정하기').click();page.locator('#confirmCheck').check();page.get_by_role('button',name='이 판본 확정',exact=True).click()
 page.locator('.tab[data-tab="report"]').click();report=page.frame_locator('#reportFrame');report.locator('.gantt-svg').wait_for()
 text=report.locator('body').inner_text();page.screenshot(path=str(out/'02-report.png'))
 for needle in ['65%','40%','100%','75%','키보드 탐색 오류 2건 미해결']:assert needle in text,needle
 confirmed=request('GET',base+'/revisions/confirmed');(out/'confirmed.json').write_text(json.dumps(confirmed,ensure_ascii=False,indent=2))
 for fmt in ['html','md','docx']:
  r=c.get(base+f'/exports/{confirmed["id"]}.{fmt}');r.raise_for_status();(out/('flow-report.'+fmt)).write_bytes(r.content)
 page.locator('#roleSelect').select_option('successor');report.locator('.gantt-svg').wait_for();assert report.locator('body').inner_text()==text
 if not request('GET',base)['accepted']:page.get_by_role('button',name='인수 확인',exact=True).click()
 page.get_by_role('button',name='확인 완료 ✓',exact=True).wait_for()
 rp=ctx.new_page();rp.goto(urljoin(args.url,base+'/reports/confirmed'));rp.locator('.gantt-svg').screenshot(path=str(out/'03-gantt.png'));rp.pdf(path=str(out/'flow-report.pdf'),format='A4',print_background=True,margin={'top':'12mm','bottom':'12mm','left':'12mm','right':'12mm'})
 page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(500);assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1');page.screenshot(path=str(out/'04-mobile.png'))
 assert not errors,errors
 browser.close()
sources=[]
for doc in request('GET',base)['documents']:sources.append({'id':doc['id'],'path':doc['path'],'blocks':request('GET',base+'/documents/'+doc['id']+'/blocks')})
(out/'sources.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2))
result={'case_id':case_id,'revision_id':confirmed['id'],'url':args.url+'#'+case_id,'mode':args.mode,'documents':len(sources),'tasks':4,'same_report_both_roles':True,'matched_by_human':True,'gantt':True,'mobile_no_page_overflow':True,'javascript_errors':errors,'model':confirmed['payload']['model']}
(out/'e2e.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False),flush=True)
