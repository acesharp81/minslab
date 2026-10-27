import json,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
folder=Path('/home/ubuntu/apps/myservice/PoC/10-home/docs/evidence/PUBLICATION_REVIEW_CLARITY_20261026')
url='https://www.minslab.kr/poc/home/'
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path='/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':390,'height':844});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(url+'#publication-reviews',wait_until='domcontentloaded')
 expect(page.locator('.pr-question h4')).to_contain_text('면목·사당',timeout=60000)
 page.locator('.pr-question').scroll_into_view_if_needed()
 page.screenshot(path=str(folder/'mobile-question.png'))
 data=page.request.get(url+'api/publication-reviews').json()
 assert all(r['guidance']['decision'] and len(r['guidance']['checks'])==3 for r in data['items'])
 assert not errors
 result=dict(public_url=url+'#publication-reviews',total=data['total'],counts=data['counts'],mobile_errors=errors,all_cases_have_questions=True)
 (folder/'runtime.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps(result,ensure_ascii=False))
 browser.close()
