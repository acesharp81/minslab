"""One paid synthetic Solar question; record actual browser delta timings."""
import json,time
from pathlib import Path
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'test-results/streaming/live';out.mkdir(parents=True,exist_ok=True)
errors=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox']);page=b.new_page(viewport={'width':1600,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('https://www.minslab.kr/handover/#8160f1f002f24fff8d22b5ade2776c0c')
 if page.locator('#accessToken').is_visible():page.locator('#accessToken').fill(dotenv_values(ROOT/'.env')['HANDOVER_ACCESS_TOKEN']);page.get_by_role('button',name='접속하기',exact=True).click()
 page.locator('#reportToc a').first.wait_for();assert page.evaluate('state.revision.id').startswith('a59b6224')
 # Synthetic case identity is checked before a live model request.
 titles=page.evaluate('state.revision.payload.items.map(i=>i.fields.title.value)')
 assert set(titles)<={'생활문화 공모사업 추진','보조금 정산 승인','문화시설 안전점검','문화시설 통합예약 개선','예약포털 접근성 보완'}
 before=page.request.get('https://www.minslab.kr/handover/api/budget').json()
 page.evaluate('''()=>{const original=streamQuestion;window.__streamTiming={start:null,first:null,last:null,done:null,chunks:0};streamQuestion=async function(path,body,onText,signal){const t=window.__streamTiming;t.start=performance.now();const result=await original(path,body,text=>{const now=performance.now();if(t.first===null)t.first=now;t.last=now;t.chunks++;onText(text);},signal);t.done=performance.now();return result;};}''')
 page.locator('#readerConsent').check();page.locator('#readerQuestion').fill('가장 시급히 처리해야 할 업무와 바로 할 일을 알려줘.');page.locator('#readerAsk').click()
 expect(page.locator('.typing-cursor')).to_be_visible();page.wait_for_function("()=>document.querySelector('.live-text')?.textContent.length>3",timeout=120000)
 assert page.evaluate('window.__streamTiming.done') is None
 page.screenshot(path=str(out/'generating.png'))
 expect(page.locator('#readerAsk')).to_be_enabled(timeout=120000);expect(page.locator('.conversation-paragraph').first).to_be_visible();expect(page.locator('.typing-cursor')).to_have_count(0)
 answer=page.evaluate('state.readerAnswers[state.readerAnswers.length-1]');assert answer['paragraphs'] and '보조금 정산' in answer['paragraphs'][0]['text']
 timing=page.evaluate('window.__streamTiming');assert timing['chunks']>1 and timing['first']<timing['last']<timing['done']
 after=page.request.get('https://www.minslab.kr/handover/api/budget').json();assert after['calls']>=before['calls']+1 and after['used_usd']>before['used_usd']
 page.locator('#readerChatLog').evaluate('e=>e.scrollTop=0');page.screenshot(path=str(out/'complete.png'));assert not errors;assert page.evaluate('scrollY')==0
 b.close()
result={'model':answer['model'],'first_text_ms':round(timing['first']-timing['start']),'last_text_ms':round(timing['last']-timing['start']),'done_ms':round(timing['done']-timing['start']),'delta_chunks':timing['chunks'],'text_visible_before_done':True,'cursor_removed_after_done':True,'usage':answer['usage'],'cost_delta_usd':round(after['used_usd']-before['used_usd'],9),'javascript_errors':errors,'solar_calls':1,'gpt_calls':0}
(out/'answer.json').write_text(json.dumps(answer,ensure_ascii=False,indent=2));(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
