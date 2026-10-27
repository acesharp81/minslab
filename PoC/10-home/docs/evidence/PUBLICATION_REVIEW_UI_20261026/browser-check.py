import json,os,time,hmac,hashlib,tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
from sqlalchemy import create_engine,select
from sqlalchemy.pool import StaticPool
from backend.db import Base,Revision,Mapping,upsert_revision
from backend.service import HomeService
folder=Path('/home/ubuntu/apps/myservice/PoC/10-home/docs/evidence/PUBLICATION_REVIEW_UI_20261026')
URL='http://127.0.0.1:18100'
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path='/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':1050})
 errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
 page.goto(URL+'/poc/home/#publication-reviews',wait_until='domcontentloaded')
 page.wait_for_selector('.pr-item',timeout=60000)
 page.screenshot(path=str(folder/'review-inbox.png'),full_page=False)
 assert page.locator('#pr-form button[type=submit]').is_disabled()
 assert page.locator('.pr-detail').inner_text().find('2,121')>=0
 page.locator('#pr-priority').select_option('1');assert page.locator('.pr-item').count()==1
 page.locator('#pr-priority').select_option('2')
 case=page.locator('.pr-item').filter(has_text='신길4');case.click()
 page.locator('.pr-candidate').filter(has_text='신길4').locator('button').click()
 expect(page.locator("#mapping-review-detail h3")).to_have_text("신길4",timeout=60000)
 page.screenshot(path=str(folder/'existing-policy-link.png'))
 result=dict(guest_errors=errors,focused_project=page.locator('#mapping-review-detail h3').inner_text(),policy_notice=page.locator('#mapping-review-notice').inner_text())
 # All mutations below go to an isolated SQLite application, never production.
 engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine)
 s=HomeService(engine)
 with s.sessions.begin() as db:
  doc,_=upsert_revision(db,'document_evidence','seoul_press_watch','browser',dict(name='면목·사당 2027년 착공 검토 [격리 시험]',source_date='2026-10-23',evidence_url='https://www.seoul.go.kr/example',facts=[]),'test')
  project,_=upsert_revision(db,'project','test','project',dict(name='면목 실제 구역 [격리 시험]',region='서울특별시',planned_units=100),'test')
  db.add(Mapping(project_id=project.entity_id,policy_id='POL_TEST',status='REVIEW',basis='검토 이전 사유',evidence_url='https://seoul.go.kr/example'))
 with tempfile.TemporaryDirectory(prefix='review-browser-') as tmp,patch.dict(os.environ,{'POC10_INTERNAL_SECRET':'browser-test','POC10_DATA_DIR':tmp,'POC10_DATABASE_URL':'sqlite://'}),patch.object(HomeService,'mapping_policies',return_value=[dict(policy_id='POL_TEST',name='검토 정책 [격리 시험]',monitor_kind='POLICY')]):
  from fastapi.testclient import TestClient
  from backend.app import create_app
  with TestClient(create_app(engine,auto_collect=False)) as client:
   test=browser.new_page(viewport={'width':1440,'height':1050});test_errors=[];test.on('pageerror',lambda err:test_errors.append(str(err)))
   def route_api(route):
    req=route.request;path=urlsplit(req.url).path
    if path.endswith('/admin/status'):
     route.fulfill(json={'authenticated':True});return
    if '/publication-reviews' not in path:
     if req.method!='GET':route.fulfill(status=403,json={'detail':'격리 시험 외 쓰기 금지'});return
     route.continue_();return
    headers={}
    if req.method=='POST':
     stamp=str(int(time.time()));headers['x-home-admin']=stamp+':'+hmac.new(b'browser-test',f'{stamp}:POST:{path}'.encode(),hashlib.sha256).hexdigest()
    response=client.request(req.method,path,content=req.post_data,headers={'content-type':'application/json',**headers})
    route.fulfill(status=response.status_code,content_type='application/json',body=response.text)
   test.route('**/poc/home/api/**',route_api)
   test.goto(URL+'/poc/home/#publication-reviews',wait_until='domcontentloaded')
   test.wait_for_selector('#pr-form',timeout=60000)
   test.locator('#pr-form select[name=status]').select_option('APPROVED')
   test.locator('#pr-form select[name=policy_id]').select_option('POL_TEST')
   test.locator('#pr-form input[name=project_ids]').check()
   test.locator('#pr-form input[name=actor]').fill('격리 검증 담당자')
   test.locator('#pr-form textarea[name=reason]').fill('원문과 동일 구역·자료 범위를 확인했습니다.')
   test.locator('#pr-form input[name=source_checked]').check()
   test.locator('#pr-form button[type=submit]').click()
   expect(test.locator("#pr-save-result")).to_contain_text("저장 완료",timeout=30000)
   assert client.get('/poc/home/api/publication-reviews/summary').json()['counts']['APPROVED']==1
   test.screenshot(path=str(folder/'isolated-approval.png'))
   test.locator('#pr-form select[name=status]').select_option('HOLD')
   test.locator('#pr-form textarea[name=reason]').fill('범위 변경으로 공식 근거를 추가 확인합니다.')
   test.locator('#pr-form button[type=submit]').click()
   expect(test.locator("#pr-save-result")).to_contain_text("저장 완료",timeout=30000)
   test.locator('#pr-form select[name=status]').select_option('REGISTRATION_REQUIRED')
   test.locator('#pr-form input[name=project_ids]').uncheck()
   test.locator('#pr-form textarea[name=new_project_names]').fill('면목 실제 신규 구역\n사당 실제 신규 구역')
   test.locator('#pr-form input[name=source_checked]').check()
   test.locator('#pr-form button[type=submit]').click()
   expect(test.locator("#pr-save-result")).to_contain_text("저장 완료",timeout=30000)
   summary=client.get('/poc/home/api/publication-reviews/summary').json()
   assert summary['pending']==1 and summary['counts']['REGISTRATION_REQUIRED']==1
   test.locator('.pr-history summary').click();expect(test.locator("#pr-history-body")).to_contain_text("격리 검증 담당자",timeout=30000)
   result.update(isolated_errors=test_errors,isolated_summary=summary,history=client.get('/poc/home/api/publication-reviews/'+doc.entity_id+'/history').json())
   with s.sessions() as db:
    bridge=db.scalar(select(Revision).where(Revision.kind=='evidence_bridge',Revision.superseded_at.is_(None)))
    assert bridge.payload['status']=='RELEASED' and bridge.payload['facts']==[]
    assert db.scalar(select(Mapping)).status=='REVIEW'
   test.screenshot(path=str(folder/'isolated-registration-pending.png'))
  engine.dispose()
 (folder/'browser.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
 browser.close()
