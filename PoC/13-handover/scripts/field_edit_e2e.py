"""Field-only edits with evidence, immutable history and stale-update protection; no LLM calls."""
import argparse,json,time
from pathlib import Path
from urllib.parse import urljoin
import httpx
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
a=argparse.ArgumentParser();a.add_argument('--url',default='http://127.0.0.1:18131/');a.add_argument('--stage',default='local');args=a.parse_args();out=ROOT/'test-results/field-edit'/args.stage;out.mkdir(parents=True,exist_ok=True)
token=dotenv_values(ROOT/'.env').get('HANDOVER_ACCESS_TOKEN','');client=httpx.Client(base_url=args.url,headers={'Authorization':'Bearer '+token},timeout=30)
def api(method,path,**kwargs):
 r=client.request(method,path,**kwargs);r.raise_for_status();return r.json()
case=api('POST','api/cases',json={'title':'항목별 수정·근거 확인 검증 (합성)'});base='api/cases/'+case['id'];api('POST',base+'/flow-demo');api('POST',base+'/generate',json={'mode':'rules','request_id':'field-edit-'+case['id']})
for _ in range(100):
 details=api('GET',base)
 if details['current']:break
 time.sleep(.1)
original=api('GET',base+'/revisions/current');item=next(i for i in original['payload']['items'] if i['fields']['title']['value']=='예약포털 접근성 보완');item_id=item['id']
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':1440,'height':1050});page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(args.url)
 if page.locator('#accessToken').is_visible():page.locator('#accessToken').fill(token);page.get_by_role('button',name='접속하기',exact=True).click()
 page.get_by_role('button',name='4개 업무 흐름 체험').wait_for();page.goto(args.url+'#'+case['id']);page.locator('.tab[data-tab="review"]').click()
 expect(page.locator('[data-action="edit"]')).to_have_count(0)
 owner=page.locator(f'[data-action="edit-field"][data-id="{item_id}"][data-field="owner"]');owner.click()
 expect(page.locator('#fieldEditValue')).to_have_value('미정')
 expect(page.locator('.related-candidate')).to_contain_text('디지털지원팀');expect(page.locator('.related-candidate')).to_contain_text('HB-004')
 expect(page.locator('.field-source-content .quote')).to_have_count(2)
 page.locator('.field-context summary').first.click();expect(page.locator('.field-context .quoted-block').first).to_be_visible();page.locator('.field-context summary').first.click()
 page.screenshot(path=str(out/'01-owner-evidence.png'))
 page.locator('#fieldEditValue').fill('디지털지원팀');page.get_by_role('button',name='이 항목 저장',exact=True).click();expect(page.locator('#fieldEditError')).to_contain_text('변경 사유')
 page.locator('#fieldEditReason').fill('HB-004 계획보고의 담당을 대조하고 전임자에게 확인한 합성 검증');page.get_by_role('button',name='이 항목 저장',exact=True).click();expect(page.locator('#dialog')).not_to_be_visible()
 changed=api('GET',base+'/revisions/current');new=next(i for i in changed['payload']['items'] if i['id']==item_id)
 assert new['fields']['owner']['value']=='디지털지원팀' and new['fields']['owner']['previous']==item['fields']['owner']
 assert {k:v for k,v in new['fields'].items() if k!='owner'}=={k:v for k,v in item['fields'].items() if k!='owner'}
 assert api('GET',base+'/revisions/'+original['id'])['payload']==original['payload']
 owner.click();expect(page.locator('.field-history')).to_contain_text('미정');expect(page.locator('.field-source-list')).to_contain_text('수정 전 원문')
 page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(150)
 assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
 assert page.locator('#dialog').evaluate('e=>e.scrollWidth<=e.clientWidth+1')
 page.screenshot(path=str(out/'02-mobile.png'))
 page.get_by_role('button',name='취소',exact=True).click();page.set_viewport_size({'width':1440,'height':1050})
 # A stale editor must not silently overwrite another revision, and must keep the typed draft.
 owner.click();page.locator('#fieldEditValue').fill('다른 입력값 보존 시험');page.locator('#fieldEditReason').fill('동시 수정 보호 검사')
 external=api('PATCH',base+f'/revisions/{changed["id"]}/items/{item_id}',json={'expected_hash':changed['hash'],'fields':{'notes':'동시 수정 검사 (합성)'},'reason':'별도 변경'})
 page.get_by_role('button',name='이 항목 저장',exact=True).click();expect(page.locator('#fieldEditError')).not_to_be_empty();expect(page.locator('#fieldEditValue')).to_have_value('다른 입력값 보존 시험')
 assert api('GET',base+'/revisions/current')['hash']==external['hash'];page.get_by_role('button',name='취소',exact=True).click();page.reload();page.locator('.tab[data-tab="review"]').click()
 # Title gets its own pencil. Cancel preserves it.
 page.locator(f'[data-action="edit-field"][data-id="{item_id}"][data-field="title"]').click();expect(page.locator('#fieldEditValue')).to_have_value('예약포털 접근성 보완');page.locator('#fieldEditValue').fill('취소될 업무명');page.keyboard.press('Escape');assert api('GET',base+'/revisions/current')['hash']==external['hash']
 # No evidence is shown as a gap, not fabricated; documents remain accessible in the same dialog.
 data=api('PATCH',base+f'/revisions/{external["id"]}/items/new',json={'expected_hash':external['hash'],'fields':{'title':'직접 입력 업무'},'reason':'근거 없음 화면 검사'});added=next(i for i in data['payload']['items'] if i['fields']['title']['value']=='직접 입력 업무')
 page.reload();page.locator('.tab[data-tab="review"]').click();expect(page.locator('[data-action="edit"]')).to_have_count(0);page.locator('.readiness summary').click();page.locator(f'.readiness [data-action="edit-field"][data-id="{added["id"]}"][data-field="owner"]').click();expect(page.locator('.field-no-source')).to_be_visible();page.get_by_role('button',name='취소',exact=True).click()
 # Confirmed view and successor stay read-only.
 api('POST',base+f'/revisions/{data["id"]}/confirm',json={'expected_hash':data['hash'],'acknowledge_warnings':True});page.reload();page.locator('#roleSelect').select_option('successor');page.locator('.tab[data-tab="confirmed"]').click();expect(page.locator('.work-card')).to_have_count(6);expect(page.locator('.field-pencil')).to_have_count(0)
 assert not errors,errors;browser.close()
result={'case_id':case['id'],'url':args.url+'#'+case['id'],'per_field_pencils':True,'related_plan_evidence':True,'neighbors_shown':True,'only_selected_field_changed':True,'history_preserved':True,'stale_update_keeps_input':True,'mobile_no_overflow':True,'no_evidence_state':True,'successor_read_only':True,'llm_calls':0,'javascript_errors':errors}
(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
