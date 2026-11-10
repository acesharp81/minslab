"""Read-only viewer checks against an existing synthetic confirmed case."""
import argparse,json
from pathlib import Path
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
a=argparse.ArgumentParser();a.add_argument('--url',default='http://127.0.0.1:18131/');a.add_argument('--case',default='17ccc800dc2b4cf6b20238b95f0a0638');a.add_argument('--stage',default='local');a.add_argument('--solar',action='store_true');args=a.parse_args();out=ROOT/'test-results/reader'/args.stage;out.mkdir(parents=True,exist_ok=True)
token=dotenv_values(ROOT/'.env')['HANDOVER_ACCESS_TOKEN'];errors=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox']);ctx=b.new_context(viewport={'width':1600,'height':1000},reduced_motion='reduce');page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(args.url+'#'+args.case)
 if page.locator('#accessToken').is_visible():page.locator('#accessToken').fill(token);page.get_by_role('button',name='접속하기',exact=True).click()
 page.locator('#reportToc a').first.wait_for();frame=page.frame_locator('#reportFrame');frame.locator('.gantt-svg').wait_for();assert page.evaluate('document.documentElement.scrollHeight<=innerHeight+1');assert page.locator('#reportFrame').bounding_box()['height']>500
 assert page.locator('#reportToc .toc-branch[open]').count()==0
 page.locator('#reportToc a').filter(has_text='업무별 예산과 공동 경비').click();expect(frame.locator('h2').filter(has_text='업무별 예산과 공동 경비')).to_be_in_viewport();page.wait_for_timeout(500)
 assert page.evaluate('scrollY')==0;assert page.locator('#reportFrame').evaluate('f=>f.contentWindow.scrollY')>1000
 assert page.locator('#reportToc [aria-current]').count()==1
 assert page.locator('#reportToc .toc-branch').count()>0
 branch=page.locator('#reportToc .toc-branch').first
 branch.locator('.toc-arrow').click();assert branch.get_attribute('open') is not None
 child=branch.locator('.toc-children a').first;expect(child).to_be_visible();child.click();page.wait_for_timeout(400)
 branch.locator('.toc-arrow').click();assert branch.get_attribute('open') is None
 page.locator('#reportToc a').filter(has_text='업무별 예산과 공동 경비').click();page.wait_for_timeout(500)
 page.screenshot(path=str(out/'desktop.png'))
 before=page.locator('#reportFrame').evaluate('f=>f.contentWindow.scrollY')
 page.locator('#readerMode').select_option('local');page.locator('#readerQuestion').fill('보조금 정산 남은 업무는?');page.locator('#readerAsk').click();expect(page.locator('.reader-exchange')).to_have_count(1);expect(page.locator('.reader-answer')).to_contain_text('누락 증빙');expect(page.locator('.reader-background')).to_be_visible();assert page.locator('#reportFrame').evaluate('f=>f.contentWindow.scrollY')==before
 page.locator('.reader-fact [data-action="block"]').first.click();expect(page.locator('#dialog')).to_be_visible();page.keyboard.press('Escape');assert page.locator('#reportFrame').evaluate('f=>f.contentWindow.scrollY')==before
 page.locator('#readerQuestion').fill('그럼 담당은?');page.locator('#readerAsk').click();expect(page.locator('.reader-exchange')).to_have_count(2);expect(page.locator('.reader-exchange').last).to_contain_text('사업지원팀');assert page.locator('#reportFrame').evaluate('f=>f.contentWindow.scrollY')==before
 if args.solar:
  page.locator('#readerMode').select_option('llm');page.locator('#readerConsent').check();page.locator('#readerQuestion').fill('보조금 정산 승인을 위해 지금 해야 할 일과 관련 원문 근거를 알려줘.');page.locator('#readerAsk').click();expect(page.locator('.reader-exchange')).to_have_count(3,timeout=120000);expect(page.locator('.reader-exchange').last).to_contain_text('영수증');assert page.locator('#reportFrame').evaluate('f=>f.contentWindow.scrollY')==before
 page.screenshot(path=str(out/'chat.png'))
 # Tablet panels and phone panels overlay the report; outer viewport stays still.
 for width,height in [(1100,800),(390,844)]:
  page.set_viewport_size({'width':width,'height':height});expect(page.locator('.reader-chat')).not_to_be_visible();page.locator('.reader-panel-toggle[data-reader-panel="chat"]').click();expect(page.locator('.reader-chat')).to_be_visible();assert page.locator('.reader-chat').bounding_box()['height']>350;page.locator('.reader-panel-close[data-reader-panel="chat"]').click();page.locator('.reader-panel-toggle[data-reader-panel="toc"]').click();expect(page.locator('#reportToc')).to_be_visible();parent=page.locator('#reportToc a').filter(has_text='우선순위와 실행 순서');parent.click();expect(page.locator('.reader-toc')).to_be_visible();leaf=parent.locator('xpath=../..').locator('.toc-children a').first;target=leaf.get_attribute('href');leaf.click();expect(page.locator('.reader-toc')).not_to_be_visible();expect(frame.locator(target)).to_be_in_viewport();assert page.evaluate('document.documentElement.scrollHeight<=innerHeight+1 && document.documentElement.scrollWidth<=innerWidth+1');page.screenshot(path=str(out/f'viewport-{width}.png'));page.locator('#reportToc a').filter(has_text='우선순위와 실행 순서').evaluate('a=>a.parentElement.parentElement.open=false')
 page.locator('.tab[data-tab="sources"]').click();expect(page.locator('body')).not_to_have_class('report-reading');assert page.evaluate('document.documentElement.scrollHeight>innerHeight');page.evaluate('window.scrollTo(0,500)');assert abs(page.locator('.topbar').bounding_box()['y'])<1;assert page.locator('#budgetButton').is_visible()
 page.locator('.tab[data-tab="report"]').click();page.locator('#reportToc a').first.wait_for(state='attached');expect(page.locator('body')).to_have_class('report-reading');assert not errors,errors;b.close()
result={'case_id':args.case,'url':args.url+'#'+args.case,'outer_page_no_scroll':True,'report_internal_scroll':True,'toc_jump_and_active_item':True,'toc_initially_collapsed_and_expandable':True,'topbar_pinned_on_other_tabs':True,'chat_report_facts_and_reference_sources':True,'followup_context':True,'report_position_preserved_on_question_and_source':True,'tablet_and_phone_panels':True,'other_tabs_normal_scroll':True,'solar_question_calls':1 if args.solar else 0,'javascript_errors':errors}
(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
