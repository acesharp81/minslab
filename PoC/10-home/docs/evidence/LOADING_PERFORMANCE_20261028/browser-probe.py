import json,time,sys
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
out=Path('PoC/10-home/docs/evidence/LOADING_PERFORMANCE_20261028');label=sys.argv[1]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',args=['--no-sandbox'])
 results=[]
 for view,selector in [('policy-progress','#policy-report-detail .d907-chart'),('policy-progress','#policy-report-detail .d907-chart'),('publication-reviews','#pr-list .pr-item'),('projects','#pjt-report .pjt-progress'),('program-progress','#program-progress-detail .d907-chart')]:
  context=browser.new_context(viewport={'width':1440,'height':1000});page=context.new_page();start=time.monotonic();requests=[];errors=[]
  def finished(req):
   if '/api/' not in req.url:return
   res=req.response();requests.append(dict(path=req.url.split('/api/')[1],finished_ms=round((time.monotonic()-start)*1000),duration_ms=round(req.timing['responseEnd']-req.timing['startTime']+req.timing['startTime'],1),timing=req.timing,status=res.status,cache=res.headers.get('x-home-cache')))
  page.on('requestfinished',finished);page.on('pageerror',lambda e:errors.append(str(e)))
  error=None
  try:
   page.goto('https://www.minslab.kr/poc/home/#'+view,wait_until='domcontentloaded',timeout=60000)
   page.locator(selector).first.wait_for(state='attached',timeout=90000)
   chart_ms=round((time.monotonic()-start)*1000)
   expect(page.locator('#loading')).to_be_hidden(timeout=90000)
  except Exception as e:error=str(e)[:250];chart_ms=None
  row=dict(view=view,ready_ms=chart_ms,done_ms=round((time.monotonic()-start)*1000),requests=requests,errors=errors,error=error)
  results.append(row);print(json.dumps(row,ensure_ascii=False),flush=True);context.close()
 browser.close();(out/(label+'-browser.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2))
