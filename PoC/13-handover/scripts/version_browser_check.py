"""Read-only public app checks. Never triggers a model request."""
import json
from pathlib import Path
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'test-results/versions/browser';OUT.mkdir(parents=True,exist_ok=True)
cid=json.loads((ROOT/'test-results/versions/live/checkpoint.json').read_text())['case_id'];errors=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox']);ctx=b.new_context(viewport={'width':1600,'height':1000});page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('https://www.minslab.kr/handover/')
 if page.locator('#accessToken').is_visible():page.locator('#accessToken').fill(dotenv_values(ROOT/'.env')['HANDOVER_ACCESS_TOKEN']);page.get_by_role('button',name='접속하기',exact=True).click()
 expect(page.get_by_role('button',name='파일명·버전 혼선 체험',exact=True)).to_be_visible()
 page.goto('https://www.minslab.kr/handover/#'+cid)
 frame=page.frame_locator('#reportFrame');frame.locator('.gantt-svg').wait_for()
 expect(frame.get_by_text('최신본 채택·구판 및 초안 제외 근거',exact=False)).to_have_count(4)
 for text in ['65%','70%','90%','55%']:assert text in frame.locator('body').inner_text()
 for node in page.locator('#reportToc > details').all():assert node.get_attribute('open') is None
 page.screenshot(path=str(OUT/'desktop.png'))
 page.locator('.tabs [data-tab="review"]').click()
 expect(page.locator('.version-choice')).to_have_count(4)
 first=page.locator('.version-choice details').first;first.locator('summary').click();assert first.get_attribute('open') is not None
 assert '1234.pdf' in page.locator('.version-choice').first.inner_text()
 page.screenshot(path=str(OUT/'version-review.png'))
 page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
 page.screenshot(path=str(OUT/'mobile.png'))
 guide=ctx.new_page();guide.goto('https://www.minslab.kr/handover/guide');expect(guide.locator('#versions')).to_be_visible();expect(guide.locator('a[href="downloads/version-report.html"]').first).to_be_visible()
 assert not errors;b.close()
result={'new_demo_button':True,'confirmed_report_four_versions':True,'progress':[65,70,90,55],'review_version_choice_count':4,'version_comparison_expands':True,'mobile_no_page_overflow':True,'downloads_available':True,'javascript_errors':errors,'model_calls':0}
(OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
