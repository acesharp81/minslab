"""Local delayed-provider UI check; no paid model calls. Start the dev fixture first."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
out=Path('test-results/streaming/local');out.mkdir(parents=True,exist_ok=True)
errors=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox']);page=b.new_page(viewport={'width':1600,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:18131/#17ccc800dc2b4cf6b20238b95f0a0638');page.locator('#reportToc a').first.wait_for()
 page.locator('#readerConsent').check();page.locator('#readerQuestion').fill('시급한 업무는?');page.locator('#readerAsk').click()
 expect(page.locator('.typing-cursor')).to_be_visible();page.wait_for_function("()=>document.querySelector('.live-text')?.textContent.includes('보조금')")
 first=page.locator('.live-text').inner_text();assert page.locator('#readerAsk').is_disabled();assert not page.locator('.conversation-paragraph').count()
 page.wait_for_timeout(400);second=page.locator('.live-text').inner_text();assert len(second)>len(first)
 page.screenshot(path=str(out/'generating.png'));expect(page.locator('.conversation-paragraph')).to_have_count(1,timeout=15000);expect(page.locator('.typing-cursor')).to_have_count(0)
 assert page.evaluate('scrollY')==0;assert page.locator('.conversation-citations').count()==1
 page.locator('#readerQuestion').fill('오류 처리 시험');page.locator('#readerAsk').click();page.wait_for_function("()=>document.querySelector('.live-text')?.textContent.includes('보조금')")
 expect(page.locator('#readerChatError')).to_contain_text('확인되지 않은 근거',timeout=15000);expect(page.locator('.live-text')).to_have_count(0);expect(page.locator('.conversation-paragraph')).to_have_count(1)
 # The separate question tab must use the same incremental renderer.
 page.locator('.tab[data-tab="questions"]').click();page.locator('#questionMode').select_option('llm');page.locator('#questionConsent').check();page.locator('#questionText').fill('정산 업무는?');page.locator('#questionForm button').click()
 page.wait_for_function("()=>document.querySelector('.live-text')?.textContent.includes('보조금')");expect(page.locator('.typing-cursor')).to_be_visible();expect(page.locator('.conversation-paragraph')).to_have_count(1,timeout=15000);expect(page.locator('.typing-cursor')).to_have_count(0)
 # Navigating away cancels a request and cannot append a late answer.
 page.locator('.tab[data-tab="report"]').click();page.locator('#readerQuestion').fill('중단 시험');page.locator('#readerAsk').click();page.wait_for_function("()=>document.querySelector('.live-text')?.textContent.includes('보조금')");page.locator('.tab[data-tab="sources"]').click();page.wait_for_timeout(500);assert page.evaluate('state.readerBusy') is False
 assert not errors,errors;b.close()
result={'incremental_before_done':True,'text_grows_during_request':True,'cursor_during_generation_only':True,'validated_citations_on_completion':True,'invalid_preview_removed':True,'both_question_screens':True,'navigation_cancels':True,'javascript_errors':errors,'paid_calls':0}
(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
