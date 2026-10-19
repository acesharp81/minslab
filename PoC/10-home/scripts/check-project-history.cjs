'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('/tmp/poc07-playwright/node_modules/playwright');
const base=(process.env.HOME_CHECK_BASE||'http://127.0.0.1:18100')+'/poc/home';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],writes=[];
  page.on('pageerror',err=>errors.push(err.message));
  // Exercise editor controls without credentials or production writes.
  await page.route('**/api/**',route=>{
   const req=route.request();if(req.method()!=='GET'){writes.push(req.method()+' '+req.url());return route.abort();}
   if(new URL(req.url()).pathname.endsWith('/admin/status'))return route.fulfill({json:{authenticated:true}});
   return route.continue();
  });
  if(process.env.HOME_CHECK_LOCAL_HISTORY==='1')await page.route('**/assets/project-information.js*',route=>route.fulfill({path:path.join(__dirname,'../web/assets/project-information.js'),contentType:'application/javascript'}));
  await page.goto(base+'/#projects',{waitUntil:'domcontentloaded'});
  await page.locator('[data-pjt-edit]').last().waitFor({timeout:90000});
  const id=await page.locator('#pjt-project').inputValue();
  const response=await page.request.get(base+'/api/project-information/'+encodeURIComponent(id));assert.equal(response.status(),200);const actual=await response.json();assert.ok(actual.history.length>0);
  let fixture=actual;
  await page.route('**/api/project-information/*',route=>route.fulfill({json:fixture}));
  const editor=page.locator('#project-information-dialog'),popup=page.locator('dialog.pi-popup');
  await page.locator('[data-pjt-edit]').last().click();
  const name=editor.locator('[data-pjt-field="name"]');await name.fill('저장하지 않은 입력 유지 확인');
  await editor.locator('[data-pjt-history]').click();await popup.waitFor();
  assert.equal(await popup.locator('article').count(),actual.history.length);
  assert.ok((await popup.innerText()).includes('목표:'));
  await popup.locator('header button').click();await popup.waitFor({state:'detached'});
  assert.equal(await name.inputValue(),'저장하지 않은 입력 유지 확인');assert.ok(await editor.isVisible());
  await editor.locator('[data-pjt-history]').click();await popup.waitFor();await page.keyboard.press('Escape');await popup.waitFor({state:'detached'});assert.ok(await editor.isVisible());
  await editor.locator('[data-pjt-evidence="name"]').click();await popup.waitFor();await page.keyboard.press('Escape');assert.ok(await editor.isVisible());
  // Close the unchanged server record without submitting the form.
  page.once('dialog',dialog=>dialog.accept());await editor.locator('[data-pjt-close]').click();await editor.waitFor({state:'detached'});
  fixture=structuredClone(actual);fixture.history=[{recorded_at:'2026-10-15T01:00:00Z',values:{actor:'<script>test</script>',reason:'일반 수정 검증',last_changes:{mapping:{before:null,after:{program_id:'TEST',status:'CONFIRMED'}},schedules:[{before:{due_date:'2027-01-01'},after:{stage:'COMPLETION',due_date:'2027-02-01',units:100}},{before:{due_date:'2028-01-01'},after:{stage:'MOVE_IN',status:'RELEASED'}}],progress:{SUPPLY:null},retracted_progress:['MOVE_IN'],approvals:{BUSINESS:false}}}}];
  await page.evaluate(id=>ProjectWorkspace.openEditor(id),id);await editor.locator('[data-pjt-history]').click();await popup.waitFor();
  const text=await popup.innerText();for(const term of ['2027-01-01 → 2027-02-01','원천값 복원','승인 해제','미연결 → TEST','<script>test</script>'])assert.ok(text.includes(term),term);assert.equal(await popup.locator('script').count(),0);
  await page.keyboard.press('Escape');await editor.locator('[data-pjt-close]').click();await editor.waitFor({state:'detached'});
  fixture=structuredClone(actual);fixture.history=[];
  await page.evaluate(id=>ProjectWorkspace.openEditor(id),id);await editor.locator('[data-pjt-history]').click();assert.match(await popup.innerText(),/사용자 변경 이력이 없습니다/);
  await page.keyboard.press('Escape');await editor.locator('[data-pjt-close]').click();await editor.waitFor({state:'detached'});
  fixture=actual;await page.setViewportSize({width:390,height:844});await page.evaluate(id=>ProjectWorkspace.openEditor(id),id);await editor.locator('[data-pjt-history]').click();await popup.waitFor();assert.ok(await popup.evaluate(n=>n.getBoundingClientRect().left>=0&&n.getBoundingClientRect().right<=innerWidth));
  await page.screenshot({path:'/tmp/home-project-history-mobile.png'});
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  console.log(JSON.stringify({passed:true,base,local_asset_override:process.env.HOME_CHECK_LOCAL_HISTORY==='1',project:id,revisions:actual.history.length,checks:['batch schedule objects','interactive before/after lists','source restoration','empty history','HTML escaping','close and Escape preserve unsaved editor values','evidence popup','390px history popup'],errors,writes}));
 }finally{await browser.close();}
})().catch(err=>{console.error(err);process.exit(1)});
