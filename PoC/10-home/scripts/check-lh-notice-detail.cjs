const assert=require('node:assert/strict');const {chromium}=require('/tmp/poc07-playwright/node_modules/playwright');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',args:['--no-sandbox']});try{
 const base=process.env.HOME_CHECK_BASE||'http://127.0.0.1:18101',page=await browser.newPage({viewport:{width:1500,height:1050}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const response=await page.request.get(base+'/poc/home/api/project-collection?policy_id=POL_2025_0907');assert.equal(response.status(),200);const data=await response.json();
 const id='PRO_57f146c63d9864e7673d3456',p=data.items.find(r=>r.id===id);assert(p);assert(p.cells.APPROVAL.sources.some(r=>r.date==='2023-10-23'&&r.kind==='ACTUAL'));
 assert.equal(p.cells.MOVE_IN.actual_available,false);assert.equal(p.cells.MOVE_IN.targets.length,2);assert(p.cells.MOVE_IN.targets.every(t=>t.date==='2027-01'&&t.reference_only));
 assert(p.cells.MOVE_IN.targets.some(t=>t.label.includes('438호 / 전체 633호')));assert(p.cells.MOVE_IN.targets.some(t=>t.label.includes('195호 / 전체 633호')));
 assert.equal(p.evidence_bridges.filter(r=>r.source_id==='lh_notice_detail').length,4);
 await page.goto(base+'/poc/home/#project-collection');await page.waitForSelector('#pc-table [data-pc-cell]',{timeout:60000});await page.locator('#pc-search').fill('성남금토');
 const cell=page.locator('#pc-table [data-pc-cell="'+id+'"][data-pc-stage="MOVE_IN"]');await cell.click();
 assert.match(await page.locator('#pc-cell-detail').innerText(),/438호 \/ 전체 633호/);assert.match(await page.locator('#pc-cell-detail').innerText(),/195호 \/ 전체 633호/);
 assert.equal(await page.locator('.pc-bridge-form').count(),4);assert.equal(await page.locator('.pc-bridge-form button').count(),0);
 await page.locator('#pc-cell-detail').screenshot({path:'/tmp/home-geumto-detail.png'});
 await page.goto(base+'/poc/home/assets/reports/LH_NOTICE_GAPS_20261012.html');const report=await page.locator('body').innerText();assert.match(report,/추가 연결 63건/);assert.match(report,/2,997건/);assert.match(report,/최초 승인일 2021-12-31/);
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));assert.deepEqual(errors,[]);
 console.log(JSON.stringify({passed:true,geumtoTargets:p.cells.MOVE_IN.targets.map(t=>t.label+' '+t.date),errors}));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
