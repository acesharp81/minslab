from playwright.sync_api import sync_playwright
import json,time
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',args=['--no-sandbox']);page=b.new_page();events=[];phase=['initial'];start=time.monotonic();errors=[]
 def response(r):
  if '/api/ai-' in r.url:events.append({'phase':phase[0],'seconds':round(time.monotonic()-start,2),'path':r.url.split('/api/')[-1].split('?')[0],'status':r.status,'bytes':r.headers.get('content-length')})
 page.on('response',response);page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('https://www.minslab.kr/poc/home/#publication-reviews',wait_until='domcontentloaded');page.locator('.ai-collection > summary').wait_for(timeout=60000);page.locator('.ai-collection > summary').click();phase[0]='open';page.wait_for_timeout(17000)
 phase[0]='other_menu';page.evaluate("location.hash='policy-progress'");page.locator('.d907-flow').wait_for(timeout=60000);page.wait_for_timeout(17000)
 print(json.dumps({'events':events,'errors':errors,'note':'Read-only UI; no collection/run actions.'},ensure_ascii=False,indent=2));b.close()
