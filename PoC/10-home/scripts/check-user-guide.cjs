/* Read-only guide acceptance: lookup, keyboard navigation, printing and real menu handoff. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'/tmp/poc07-playwright/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/home/ubuntu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',args:['--no-sandbox','--enable-webgl','--use-gl=angle','--use-angle=swiftshader']});
try{
  const base=process.env.HOME_CHECK_BASE||'https://www.minslab.kr',page=await browser.newPage({viewport:{width:1600,height:1050},reducedMotion:'reduce'}),errors=[],apiCalls=[],writes=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.url().includes('/poc/home/api/')){apiCalls.push(r.url());if(!['GET','HEAD'].includes(r.method()))writes.push(r.url());}});
  if(process.env.HOME_LOCAL_ASSETS==='1'){
    const web=path.resolve(__dirname,'../web');
    await page.route('**/poc/home/',async r=>r.fulfill({response:await r.fetch(),body:fs.readFileSync(path.join(web,'index.html'),'utf8')}));
    for(const name of ['app.js','user-guide.js','user-guide.css'])await page.route('**/assets/'+name,r=>r.fulfill({body:fs.readFileSync(path.join(web,'assets',name),'utf8'),contentType:name.endsWith('.css')?'text/css':'application/javascript'}));
  }
  await page.goto(base+'/poc/home/#manual');await page.waitForSelector('#guide-start',{timeout:90000});await page.waitForSelector('#content',{state:'visible'});
  assert.equal(await page.locator('#page-label').innerText(),'사용 안내');
  assert.equal(await page.locator('[data-guide-topic]').count(),7);
  assert.equal(await page.locator('[data-guide-faq]').count(),10);
  assert.equal(await page.locator('.guide-tasks [data-view]').count(),4);
  assert.ok(await page.locator('.guide-chart-example figcaption').innerText().then(s=>s.includes('실제 정책·사업 수치가 아닙니다')));
  await page.screenshot({path:'/tmp/home-user-guide-top.png'});
  const guideRequestCount=apiCalls.length;
  await page.fill('#guide-search','하반기');assert.equal(await page.locator('.guide-block:visible').count(),1);assert.equal(await page.locator('.guide-block:visible').getAttribute('id'),'guide-meaning');
  await page.fill('#guide-search','FAQ');assert.equal(await page.locator('#guide-help [data-guide-faq]:visible').count(),10);
  await page.fill('#guide-search','미정');assert.ok(await page.locator('#guide-help [data-guide-faq]:visible').count()>0);assert.equal(await page.locator('#guide-help details:visible').first().getAttribute('open'),'');
  await page.fill('#guide-search','NOT_A_REAL_TOPIC_zzz');assert.equal(await page.locator('.guide-block:visible').count(),0);assert.ok(await page.locator('#guide-no-results').isVisible());
  await page.click('#guide-reset-search');assert.equal(await page.locator('.guide-block:visible').count(),7);
  await page.fill('#guide-search','하반기');await page.locator('.guide-nav [data-guide-section="guide-manage"]').focus();await page.keyboard.press('Enter');
  assert.equal(await page.locator('#guide-search').inputValue(),'');assert.equal(await page.locator('.guide-manager-details').getAttribute('open'),'');
  assert.equal(await page.evaluate(()=>document.activeElement.closest('article')?.id),'guide-manage');assert.equal(new URL(page.url()).hash,'#manual');
  await page.fill('#guide-search','미정');const beforePrint=await page.locator('#home-user-guide details').evaluateAll(ns=>ns.map(n=>n.open));
  await page.evaluate(()=>window.dispatchEvent(new Event('beforeprint')));assert.equal(await page.locator('.guide-block:visible').count(),7);assert.equal(await page.locator('#home-user-guide details[open]').count(),11);
  await page.emulateMedia({media:'print'});assert.ok(await page.locator('.guide-nav').isHidden());await page.emulateMedia({media:'screen'});
  await page.evaluate(()=>window.dispatchEvent(new Event('afterprint')));assert.equal(await page.locator('#guide-search').inputValue(),'미정');assert.deepEqual(await page.locator('#home-user-guide details').evaluateAll(ns=>ns.map(n=>n.open)),beforePrint);
  assert.equal(apiCalls.length,guideRequestCount,'Guide interactions must not load API projections');assert.deepEqual(writes,[]);
  await page.fill('#guide-search','');await page.locator('.guide-nav [data-guide-section="guide-meaning"]').click();await page.locator('#guide-meaning').screenshot({path:'/tmp/home-user-guide-graph.png'});
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'/tmp/home-user-guide-mobile.png'});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
  await page.locator('.guide-hero [data-view="policy-progress"]').click();await page.waitForSelector('#policy-report-detail .d907-chart',{timeout:90000});assert.equal(new URL(page.url()).hash,'#policy-progress');assert.equal(await page.evaluate(()=>scrollY),0);
  await page.goBack();await page.waitForSelector('#guide-start');assert.equal(new URL(page.url()).hash,'#manual');
  await page.locator('.guide-tasks [data-view="project-collection"]').click();await page.waitForSelector('#pc-table .pc-matrix',{timeout:90000});assert.equal(new URL(page.url()).hash,'#project-collection');
  await page.evaluate(()=>setView('manual'));await page.locator('.guide-tasks [data-view="projects"]').click();await page.waitForSelector('#project-list table',{timeout:90000});assert.equal(new URL(page.url()).hash,'#projects');
  await page.evaluate(()=>setView('manual'));await page.locator('.guide-tasks [data-view="overview"]').click();await page.waitForSelector('#housing-map-3d canvas',{timeout:90000});assert.equal(new URL(page.url()).hash,'#overview');
  await page.evaluate(()=>setView('manual'));await page.locator('.guide-more [data-view="requirements"]').click();await page.waitForSelector('#requirements-content .req-item',{timeout:90000});assert.equal(new URL(page.url()).hash,'#requirements');
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  console.log(JSON.stringify({passed:true,guideTopics:7,faqs:10,guideOnlyApiRequests:0,checks:['task actions','search and no results','keyboard contents','print all and restore','illustrative chart','mobile width','policy handoff and back','collection handoff','project lookup handoff','supply map handoff','requirements handoff'],browserErrors:errors}));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
