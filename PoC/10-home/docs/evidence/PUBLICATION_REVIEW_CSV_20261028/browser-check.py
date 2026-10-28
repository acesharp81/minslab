import csv,json,io,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
out=Path('PoC/10-home/docs/evidence/PUBLICATION_REVIEW_CSV_20261028');out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',args=['--no-sandbox'])
 context=browser.new_context(viewport={'width':1440,'height':1100},accept_downloads=True)
 page=context.new_page();errors=[];requests=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.on('request',lambda r:requests.append(r.url))
 page.goto('https://www.minslab.kr/poc/home/#publication-reviews',wait_until='domcontentloaded')
 page.locator('#pr-export-current').wait_for()
 assert not any('/export.csv' in url for url in requests)
 page.screenshot(path=str(out/'desktop.png'),full_page=False)
 counts={};timings={}
 for state in ('REVIEW','HOLD','REGISTRATION_REQUIRED','APPROVED','EXCLUDED'):
  page.locator('[data-pr-status="'+state+'"]').click()
  expected=page.locator('#pr-list .pr-item').count();start=time.monotonic()
  with page.expect_download() as info:page.locator('#pr-export-current').click()
  download=info.value;path=out/(state+'.csv');download.save_as(path)
  rows=list(csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig'))))
  assert len(rows)==expected,(state,len(rows),expected)
  assert all(r['현재상태코드']==state for r in rows)
  counts[state]=len(rows);timings[state]=round(time.monotonic()-start,3)
  expect(page.locator('#pr-export-current')).to_be_enabled()
 page.locator('[data-pr-status="APPROVED"]').click()
 page.locator('#pr-priority').select_option('2');page.locator('#pr-search').fill('고덕')
 expected=page.locator('#pr-list .pr-item').count()
 with page.expect_download() as info:page.locator('#pr-export-current').click()
 path=out/'filtered.csv';info.value.save_as(path)
 rows=list(csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig'))))
 assert len(rows)==expected and expected>0
 assert all(r['우선순위']=='2' for r in rows)
 expect(page.locator('#pr-export-current')).to_be_enabled()
 with page.expect_download() as info:page.locator('#pr-export-all').click()
 path=out/'ALL.csv';info.value.save_as(path)
 rows=list(csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig'))))
 assert len(rows)==sum(counts.values())
 expect(page.locator('#pr-export-current')).to_be_enabled()
 page.set_viewport_size({'width':390,'height':844})
 page.locator('.pr-export').scroll_into_view_if_needed();page.screenshot(path=str(out/'mobile.png'),full_page=False)
 assert not errors,errors
 result=dict(counts=counts,total=len(rows),download_seconds=timings,filtered_rows=expected,errors=errors,generated_only_on_click=True)
 (out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
 browser.close()
