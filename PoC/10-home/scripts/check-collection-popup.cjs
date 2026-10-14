const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('/tmp/poc07-playwright/node_modules/playwright');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',args:['--no-sandbox']});try{
 const p=await browser.newPage({viewport:{width:1500,height:1000}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
 if(process.env.HOME_CHECK_LOCAL_ASSETS)for(const name of ['project-collection.js','project-collection.css','project-information.js'])await p.route('**/assets/'+name+'*',route=>route.fulfill({contentType:name.endsWith('.js')?'application/javascript':'text/css',body:fs.readFileSync(path.join(__dirname,'../web/assets',name),'utf8')}));
 const base=(process.env.HOME_CHECK_BASE||'http://127.0.0.1:18100')+'/poc/home';
 await p.goto(base+'/#project-collection');await p.waitForSelector('#pc-table [data-pc-cell]',{timeout:90000});
 const data=await p.evaluate(async()=>await(await fetch('/poc/home/api/project-collection?policy_id=POL_2025_0907')).json());
 const id=await p.locator('#pc-table [data-pc-cell]').first().getAttribute('data-pc-cell'),project=data.items.find(r=>r.id===id);assert.ok(project);
 for(const stage of ['POLICY','BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN']){
  const cell=p.locator('#pc-table [data-pc-cell="'+id+'"][data-pc-stage="'+stage+'"]');await cell.click();await p.waitForSelector('.pc-source-dialog[open]');
  assert.ok((await p.locator('.pc-source-dialog h3').innerText()).includes(project.name));assert.match(await p.locator('.pc-source-dialog h3').innerText(),/근거·수집 원문·남은 항목 자세히 보기/);
  assert.equal(await p.locator('.pc-source-body>article').count(),project.cells[stage].sources.length);assert.ok(await p.locator('#pc-cell-detail').isHidden());
  await p.keyboard.press('Escape');await p.locator('.pc-source-dialog').waitFor({state:'detached'});assert.ok(await cell.evaluate(n=>document.activeElement===n));
 }
 await p.locator('#pc-table [data-pc-cell]').first().click();await p.locator('.pc-source-dialog footer button').click();await p.locator('.pc-source-dialog').waitFor({state:'detached'});assert.ok(await p.locator('#pc-cell-detail').isVisible());
 await p.setViewportSize({width:390,height:844});await p.locator('#pc-table [data-pc-cell]').first().click();await p.waitForSelector('.pc-source-dialog[open]');assert.ok(await p.locator('.pc-source-dialog').evaluate(n=>n.getBoundingClientRect().width<=innerWidth));await p.locator('.pc-source-dialog').screenshot({path:'/tmp/home-collection-source-popup.png'});await p.locator('.pc-source-dialog [aria-label="닫기"]').click();await p.locator('.pc-source-dialog').waitFor({state:'detached'});
 assert.equal(await p.locator('[data-pc-edit]').count(),0);
 await p.setViewportSize({width:1500,height:1000});await p.evaluate(async()=>{state.admin=true;await ProjectCollection.reload({preserveSelection:true});});
 await p.locator('#pc-search').fill(project.name);const originalSearch=await p.locator('#pc-search').inputValue();
 let saved=null,refreshes=0;
 await p.route('**/api/admin/project-information/*',async route=>{saved={id:route.request().url().split('/').at(-1),...route.request().postDataJSON()};await route.fulfill({json:{revision_no:2}});});
 await p.route(url=>url.pathname==='/poc/home/api/project-collection',async route=>{const response=await route.fetch();const value=await response.json();if(saved){refreshes++;value.items.find(x=>x.id===saved.id).name=saved.changes.name;}await route.fulfill({response,json:value});});
 await p.locator('[data-pc-edit="'+id+'"]').click();await p.waitForSelector('#project-information-dialog[open]');assert.equal(await p.locator('[data-pjt-field="name"]').inputValue(),project.name);assert.equal(await p.evaluate(()=>state.view),'project-collection');
 await p.locator('#project-information-dialog [data-pjt-evidence="planned_units"]').click();await p.waitForSelector('.pi-popup[open]');await p.locator('.pi-popup header button').click();await p.locator('.pi-popup').waitFor({state:'detached'});
 await p.locator('[data-pjt-field="name"]').fill(project.name+' · 화면 검증');await p.locator('#pjt-actor').fill('화면 검증');await p.locator('#pjt-reason').fill('요청만 확인 · 운영 DB 저장 차단');
 await p.locator('#project-information-dialog [type="submit"]').click();await p.locator('#project-information-dialog').waitFor({state:'detached'});await p.locator('#pc-table [data-pc-project="'+id+'"]').filter({hasText:'화면 검증'}).waitFor();
 assert.equal(saved.id,id);assert.equal(saved.actor,'화면 검증');assert.ok(refreshes>0);assert.equal(await p.locator('#pc-search').inputValue(),originalSearch);assert.equal(await p.evaluate(()=>state.view),'project-collection');
 await p.locator('#pc-search').fill('');const second=p.locator('[data-pc-edit]').nth(1);const secondId=await second.getAttribute('data-pc-edit');await second.click();await p.waitForSelector('#project-information-dialog[open]');assert.ok((await p.locator('#project-information-dialog').innerText()).includes(secondId));await p.locator('[data-pjt-close]').click();await p.locator('#project-information-dialog').waitFor({state:'detached'});
 await p.goto(base+'/#projects');await p.waitForSelector('.pjt-stages .pc-source-open',{timeout:90000});await p.locator('.pjt-stages .pc-source-open').first().click();await p.waitForSelector('.pc-source-dialog[open]');await p.keyboard.press('Escape');await p.locator('.pc-source-dialog').waitFor({state:'detached'});
 assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,stages:6,managementPreserved:true,mobile:true,sharedProjectPopup:true,editorFromCollection:true,saveIntercepted:true,errors}));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
