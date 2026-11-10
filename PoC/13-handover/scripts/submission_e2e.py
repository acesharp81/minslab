"""Opt-in browser E2E with downloaded synthetic files. No video and no private files."""
import argparse,hashlib,json,re,sys,time
from pathlib import Path
from urllib.parse import urljoin
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
a=argparse.ArgumentParser();a.add_argument('--url',default='http://127.0.0.1:18131/');a.add_argument('--stage',default='baseline');a.add_argument('--ai-questions',action='store_true');args=a.parse_args()
out=ROOT/'test-results/submission'/args.stage;out.mkdir(parents=True,exist_ok=True)
settings=dotenv_values(ROOT/'.env');token=settings.get('HANDOVER_ACCESS_TOKEN','')
checkpoint=out/'checkpoint.json'
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True);page=ctx.new_page();errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(urljoin(args.url,'guide'))
 with page.expect_download() as d:page.get_by_role('link',name='업무용 샘플 7개 받기 ↓',exact=True).click()
 sample=out/'downloaded-samples.zip';d.value.save_as(sample)
 assert hashlib.sha256(sample.read_bytes()).hexdigest()==json.loads((ROOT/'release/public/expected.json').read_text())['sample_sha256']
 page.goto(args.url)
 if token:page.locator('#accessToken').fill(token);page.get_by_role('button',name='접속하기',exact=True).click()
 page.get_by_role('button',name='샘플로 시작하기').wait_for()
 if checkpoint.exists():
  case_id=json.loads(checkpoint.read_text())['case_id'];page.goto(args.url+'#'+case_id)
 else:
  page.get_by_role('button',name='＋ 새 인수인계',exact=True).click();page.locator('#caseTitle').fill('문화기획팀 인수인계 · 다운로드 샘플 E2E');page.locator('#predecessor').fill('김전임 (합성)');page.locator('#successor').fill('이후임 (합성)');page.get_by_role('button',name='만들기',exact=True).click()
  page.wait_for_url(re.compile(r'#[a-f0-9]{32}$'));page.locator('#main h1').filter(has_text='문화기획팀 인수인계 · 다운로드 샘플 E2E').wait_for();case_id=page.url.split('#')[-1]
  checkpoint.write_text(json.dumps({'case_id':case_id,'url':args.url+'#'+case_id}));print('Created',case_id,flush=True)
 base=urljoin(args.url,'api/cases/'+case_id)
 def get(suffix=''):
  r=ctx.request.get(base+suffix);assert r.ok,(suffix,r.status);return r.json()
 details=get()
 if not details['documents']:
  page.locator('#fileInput').set_input_files(sample)
  page.locator('.file-name').filter(has_text='07_시스템개선_업무표.xlsx').wait_for()
  assert len(get()['documents'])==7
  page.screenshot(path=str(out/'01-upload.png'),full_page=True)
 if not get()['current']:
  page.get_by_role('button',name='초안 생성',exact=True).click();page.locator('#extractMode').select_option('llm');page.locator('#externalConsent').check();page.get_by_role('button',name='초안 생성 시작',exact=True).click()
  print('Solar generation started',flush=True)
  for _ in range(240):
   details=get()
   if not details['jobs']:page.wait_for_timeout(500);continue
   job=details['jobs'][0]
   if job['status'] not in ('QUEUED','RUNNING'):break
   page.wait_for_timeout(1000)
  assert job['status']=='SUCCEEDED',job['error']
 details=get()
 original=out/'revision.json'
 if not original.exists():original.write_text(json.dumps(get('/revisions/current'),ensure_ascii=False,indent=2))
 source=[]
 for doc in details['documents']:source.append({'id':doc['id'],'path':doc['path'],'blocks':get('/documents/'+doc['id']+'/blocks')})
 (out/'sources.json').write_text(json.dumps(source,ensure_ascii=False,indent=2))
 if not details['confirmed']:
  page.locator('[data-action="tab"][data-tab="review"]').click()
  card=page.locator('.work-card').filter(has=page.get_by_role('heading',name='2027년 생활문화 사업계획',exact=True));card.wait_for()
  card.locator('[data-action="evidence"][data-field="due_date"]').click();page.locator('#evidenceBody .quote').wait_for()
  page.screenshot(path=str(out/'02-evidence.png'),full_page=True)
  card.get_by_role('button',name='수정',exact=True).click();page.locator('#edit_due_date').fill('2026-11-27');page.locator('#editReason').fill('전임자 확인 · 최종 협의 일정 반영');page.get_by_role('button',name='새 판본으로 저장').click();page.get_by_text('2026-11-27',exact=True).wait_for()
  page.get_by_role('button',name='검토 완료 · 확정하기').click();page.locator('#confirmCheck').check();page.get_by_role('button',name='이 판본 확정').click()
 page.get_by_role('heading',name='전임자가 확인한 인수인계본입니다.').wait_for()
 report=page.frame_locator('#reportFrame');report.get_by_role('heading',name='업무 인수인계 보고서',exact=True).wait_for()
 text=report.locator('body').inner_text();assert '2026-11-27' in text
 for needle in ['저작권 사용 동의서 미접수','키보드 탐색 오류 2건 미해결','예산 협의와 사업계획 결재 상신']:assert needle in text,needle
 confirmed=get('/revisions/confirmed');(out/'confirmed.json').write_text(json.dumps(confirmed,ensure_ascii=False,indent=2))
 page.screenshot(path=str(out/'03-report.png'),full_page=False)
 for fmt in ['html','md','docx']:
  with page.expect_download() as d:page.get_by_role('link',name=fmt.upper()+' ↓',exact=True).click()
  d.value.save_as(out/('sample-report.'+fmt))
 page.locator('#roleSelect').select_option('successor');page.get_by_role('heading',name='전임자가 확인한 인수인계본입니다.').wait_for()
 assert report.locator('body').inner_text()==text
 if not get()['accepted']:
  page.get_by_role('button',name='인수 확인',exact=True).wait_for()
  page.get_by_role('button',name='인수 확인',exact=True).click()
 page.get_by_role('button',name='확인 완료 ✓').wait_for()
 page.locator('[data-tab="questions"]').click();page.locator('#questionText').fill('생활문화 사업계획 최종 기한은 언제인가요?');page.locator('#questionMode').select_option('llm' if args.ai_questions else 'local')
 if args.ai_questions:page.locator('#questionConsent').check()
 page.get_by_role('button',name='질문하기',exact=True).click();page.locator('.answer-fact').get_by_text('2026-11-27',exact=True).wait_for(timeout=120000)
 assert '2026-11-20' not in page.locator('.answer-fact').inner_text()
 page.locator('[data-tab="briefing"]').click();page.get_by_role('heading',name='후임자 일정·담당·연락망').wait_for()
 page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(300)
 assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'),'Mobile overflow'
 page.screenshot(path=str(out/'04-mobile.png'),full_page=True)
 report_page=ctx.new_page();report_page.goto(base+'/reports/confirmed');report_page.pdf(path=str(out/'sample-report.pdf'),format='A4',print_background=True)
 assert not errors,errors
 result={'case_id':case_id,'url':args.url+'#'+case_id,'revision_id':confirmed['id'],'items':len(confirmed['payload']['items']),'downloads':['html','md','docx','pdf'],'same_final_report':True,'question_uses_final':True,'accepted':bool(get()['accepted']),'javascript_errors':errors}
 (out/'e2e.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False),flush=True)
 browser.close()
