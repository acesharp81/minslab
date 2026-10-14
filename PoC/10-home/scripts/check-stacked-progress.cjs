const assert=require('node:assert/strict');const {chromium}=require('/tmp/poc07-playwright/node_modules/playwright');
(async()=>{const b=await chromium.launch({headless:true,executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',args:['--no-sandbox']});try{
 const page=await b.newPage({viewport:{width:1600,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));const base=(process.env.HOME_CHECK_BASE||'http://127.0.0.1:18100')+'/poc/home';
 await page.goto(base+'/#project-collection');await page.waitForSelector('#pc-diagram svg',{timeout:90000});
 for(const stage of ['ALL','POLICY','BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN']){await page.locator('[data-pc-diagram="'+stage+'"]').click();assert.ok(await page.locator('#pc-diagram [data-cl-node]').count()>10);await page.locator('#pc-diagram [data-cl-node^="source-"]:has(rect)').first().click();assert.ok(await page.locator('#pc-diagram-detail .cl-inspector').count());}
 await page.locator('[data-pc-diagram=ALL]').click();await page.locator('.pc-diagram-card').screenshot({path:'/tmp/lineage-restored.png'});
 await page.goto(base+'/#policy-progress');await page.waitForSelector('.d907-chart',{timeout:90000});await page.locator('[data-d907-chart-position=now]').click();
 assert.equal(await page.locator('.d907-stage-value').count(),6);assert.equal(await page.locator('.d907-delay-summary').count(),0);
 assert.equal(await page.locator('[data-d907-policy-background]').count(),1);
 for(const s of ['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN']){
  assert.equal(await page.locator('[data-d907-target-line="'+s+'"]').count(),1);if(s!=='MOVE_IN')assert.equal(await page.locator('[data-d907-actual-line="'+s+'"]').count(),1);
  const card=page.locator('[data-d907-highlight="'+s+'"]');assert.match(await card.innerText(),/목표/);assert.match(await card.innerText(),/누적 측정/);
  await card.click();assert.equal(await card.getAttribute('aria-pressed'),'true');assert.equal(await page.locator('[data-d907-actual-line="'+s+'"].d907-dimmed').count(),0);
  assert.ok(await page.locator('[data-d907-actual-line].d907-dimmed').count()>=3);
 }
 await page.locator('[data-d907-highlight=""]').click();assert.equal(await page.locator('.d907-dimmed').count(),0);
 await page.locator('.d907-flow').screenshot({path:'/tmp/stacked-target-measured.png'});
 const values=await page.locator('.d907-stage-value').allTextContents();
 await page.goto(base+'/#program-progress');await page.waitForSelector('.d907-chart',{timeout:90000});assert.equal(await page.locator('.d907-stage-value').count(),6);assert.equal(await page.locator('.d907-delay-summary').count(),0);
 await page.locator('[data-d907-highlight=CONSTRUCTION]').click();assert.equal(await page.locator('[data-d907-highlight=CONSTRUCTION]').getAttribute('aria-pressed'),'true');
 await page.setViewportSize({width:390,height:844});await page.locator('.d907-stage-table').screenshot({path:'/tmp/stage-table-mobile.png'});
 assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,lineageTabs:7,stageCells:6,values,errors}));
 }finally{await b.close()}})().catch(e=>{console.error(e);process.exit(1)});
