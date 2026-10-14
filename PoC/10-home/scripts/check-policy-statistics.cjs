const assert=require('node:assert/strict');
const {chromium}=require('/tmp/poc07-playwright/node_modules/playwright');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader']});try{
 const page=await browser.newPage({viewport:{width:1720,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('https://www.minslab.kr/poc/home/#policy-progress');
 await page.locator('#policy-report-detail .pd-stat-grid .pr-house-row').first().waitFor({timeout:90000});
 async function check(scope){const grid=page.locator(scope+' .pd-stat-grid');assert.equal(await grid.locator('article').count(),6);const layout=await grid.locator('article').evaluateAll(ns=>ns.map(n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,overflow:n.scrollWidth>n.clientWidth+1}}));assert.equal(layout[0].y,layout[1].y);assert.equal(layout[1].y,layout[2].y);assert.equal(layout[3].y,layout[4].y);assert.equal(layout[4].y,layout[5].y);assert.ok(layout[3].y>layout[0].y,JSON.stringify({scope,layout}));assert.ok(layout.every(r=>!r.overflow));assert.ok(!await page.locator(scope).getByText('정책 판단과 우선 조치',{exact:true}).count());return {layout,text:await grid.innerText()};}
 const policy=await check('#policy-report-detail');assert.match(policy.text,/월별 실적 흐름/);assert.match(policy.text,/4인 이상/);assert.match(policy.text,/LH/);
 await page.locator('#policy-report-detail .pd-stat-grid').screenshot({path:'/tmp/home-policy-statistics.png'});
 await page.evaluate(()=>setView('program-progress'));
 await page.locator('#program-progress-detail .pd-stat-grid .pr-house-row').first().waitFor({timeout:90000});
 await page.waitForTimeout(1800);const program=await check('#program-progress-detail');
 const opts=await page.locator('#report-program-select option').evaluateAll(ns=>ns.filter(n=>!n.disabled).map(n=>({value:n.value,text:n.textContent})));
 if(opts.length>1){await page.locator('#report-program-select').selectOption(opts[1].value);await page.waitForTimeout(1500);assert.equal(await page.locator('#program-progress-detail .pd-stat-grid article').count(),6);}
 await page.setViewportSize({width:390,height:844});await page.waitForTimeout(400);
 assert.equal(await page.locator('#program-progress-detail .pd-stat-grid').evaluate(n=>n.scrollWidth<=n.clientWidth+1),true);
 assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,policy:policy.layout,program:program.layout,mobileNoOverflow:true,errors}));
 }finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
