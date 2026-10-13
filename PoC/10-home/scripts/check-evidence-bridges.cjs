const assert=require('node:assert/strict');const {chromium}=require('/tmp/poc07-playwright/node_modules/playwright');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',args:['--no-sandbox']});try{
const base=process.env.HOME_CHECK_BASE||'http://127.0.0.1:18101',page=await browser.newPage({viewport:{width:1500,height:1050}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
const response=await page.request.get(base+'/poc/home/api/project-collection?policy_id=POL_2025_0907');assert.equal(response.status(),200);const data=await response.json();
const p=data.items.find(p=>p.id==='PRO_89b769c87e8d8ee8f6a837bf');assert(p);assert(p.cells.CONSTRUCTION.actual_available);assert(p.cells.MOVE_IN.targets.some(t=>t.date==='2029-07'));assert(p.cells.APPROVAL.sources.some(s=>s.kind==='DOCUMENT'&&s.date===null));assert.equal(p.cells.APPROVAL.actual_available,false);assert.equal(p.evidence_bridges.length,4);
assert.equal((await page.request.post(base+'/poc/home/api/admin/evidence-bridge',{data:{link_id:p.evidence_bridges[0].id,revision_no:1,status:'CONFIRMED',basis:'no write'}})).status(),401);
await page.goto(base+'/poc/home/#project-collection');await page.waitForSelector('#pc-table [data-pc-cell]',{timeout:60000});await page.locator('#pc-search').fill('평택고덕 A31');
await page.locator('#pc-table [data-pc-stage=CONSTRUCTION]').click();assert.match(await page.locator('#pc-cell-detail').innerText(),/추가 연결 근거/);assert.equal(await page.locator('.pc-bridge-form button').count(),0);
await page.locator('#pc-table [data-pc-stage=MOVE_IN]').click();assert.match(await page.locator('#pc-cell-detail').innerText(),/2029-07/);
await page.locator('#pc-table [data-pc-stage=APPROVAL]').click();assert.match(await page.locator('#pc-cell-detail').innerText(),/제2025-000호/);await page.locator('#pc-cell-detail').screenshot({path:'/tmp/home-a31-bridge-approval.png'});
await page.evaluate(()=>{state.admin=true;ProjectCollection.visible();});await page.waitForSelector('.pc-bridge-form button');let payload;
await page.route('**/api/admin/evidence-bridge',async r=>{payload=r.request().postDataJSON();await r.fulfill({json:{status:payload.status,revision_no:2}});});
const form=page.locator('.pc-bridge-form').first();await form.locator('[name=status]').selectOption('RELEASED');await form.locator('[name=basis]').fill('브라우저 검증 · 실제 저장하지 않음');await form.locator('button').click();await page.locator('#pc-message').filter({hasText:'검토 상태와 근거'}).waitFor();assert.equal(payload.status,'RELEASED');
await page.goto(base+'/poc/home/assets/reports/EVIDENCE_LINK_REPAIR_20261012.html');assert.match(await page.locator('body').innerText(),/131개 연결/);assert.match(await page.locator('body').innerText(),/보류·추가 확인 목록/);await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));assert.deepEqual(errors,[]);
console.log(JSON.stringify({passed:true,projects:data.total,a31Links:p.evidence_bridges.length,errors,writeIntercepted:true}));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
