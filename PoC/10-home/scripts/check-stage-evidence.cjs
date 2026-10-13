const {chromium}=require(process.env.PLAYWRIGHT_PACKAGE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
const browser=await chromium.launch({headless:true,executablePath:process.env.HOME_CHECK_CHROME,args:['--no-sandbox','--enable-webgl','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
 const base=process.env.HOME_CHECK_BASE||'http://127.0.0.1:18101',page=await browser.newPage({viewport:{width:1600,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/poc/home/#policy-progress');await page.waitForSelector('.prm-card[data-rendered="3d"]',{timeout:90000});
 assert.equal(await page.locator('.prm-stage-group [data-d907-stage="SUPPLY"]').getAttribute('aria-pressed'),'true');
 assert.equal(await page.locator('.prm-inset').count(),0);
 await page.locator('[data-d907-scope="PORTFOLIO"]').click();
 const city=page.locator('.prm-accessible button').filter({hasText:'고양시'});
 assert.match(await city.textContent(),/4,967호/);
 const before=await page.locator('.prm-stats').allTextContents();
 await page.locator('.d907-map-controller [data-d907-year]').evaluate(n=>{n.value='2024';n.dispatchEvent(new Event('input',{bubbles:true}));});
 assert.notDeepEqual(await page.locator('.prm-stats').allTextContents(),before);
 await page.locator('.d907-flow [data-d907-now]').click();
 await page.locator('.prm-stage-group [data-d907-stage="APPROVAL"]').click();
 assert.match((await page.locator('.prm-stats').allTextContents()).join(' '),/[1-9][\d,]*호/);
 await page.locator('[data-d907-scope="POLICY_PERIOD"]').click();
 await page.locator('[data-d907-hover]').hover({position:{x:400,y:130}});assert.match(await page.locator('.d907-chart-tooltip').innerText(),/1,350,000호/);
 await page.locator('[data-d907-scope="PORTFOLIO"]').click();await page.locator('.prm-stage-group [data-d907-stage="SUPPLY"]').click();
 assert.equal(await page.locator('[data-d907-line]').count(),0);assert(await page.locator('[data-d907-target-area]').count()>0);
 assert.match(await page.locator('.d907-occupancy').innerText(),/161,000호/);assert.match(await page.locator('.d907-occupancy').innerText(),/지연 판정 대기/);
 await page.screenshot({path:'/tmp/home-stage-review/cumulative-map.png'});
 await page.evaluate(()=>{location.hash='tree';});
 // Existing app route is driven by nav, use the pane selector if needed.
 await page.evaluate(()=>{const b=document.querySelector('[data-tab="tree"]')||document.querySelector('[data-view="tree"]');if(b)b.click();});
 await page.waitForSelector('#mapping-tab-evidence',{state:'visible',timeout:60000});await page.locator('#mapping-tab-evidence').click();
 await page.waitForSelector('#stage-evidence-form',{timeout:60000});assert.match(await page.locator('#stage-evidence-counts').innerText(),/확인 필요/);
 await page.screenshot({path:'/tmp/home-stage-review/evidence-review.png'});
 // Test officer form payload with an intercepted POST: never modify real evidence.
 await page.evaluate(()=>{state.admin=true;StageEvidenceWorkbench.load();});
 await page.waitForSelector('#stage-evidence-form button[type="submit"]');
 let submitted;await page.route('**/api/admin/stage-evidence',async r=>{submitted=r.request().postDataJSON();await r.fulfill({json:{ok:true}});});
 await page.locator('#stage-evidence-form [name="status"]').selectOption('REVIEW');
 await page.locator('#stage-evidence-form [name="basis"]').fill('브라우저 검증 · 실제 저장하지 않음');
 // Existing source quantity may exceed the canonical block; an officer must adjust it.
 await page.locator('#stage-evidence-form [name="units"]').fill('');
 await page.locator('#stage-evidence-form button[type="submit"]').click();
 await page.locator('#stage-evidence-message').filter({hasText:'연결을 저장'}).waitFor();
 assert(submitted&&submitted.project_id&&submitted.stage&&submitted.revision_no>0);
 await page.locator('#stage-evidence-targets').click();await page.waitForSelector('#d907-occupancy-form');
 let saved;await page.route('**/api/admin/policy-delivery',async r=>{saved=r.request().postDataJSON();await r.fulfill({json:{ok:true}});});
 for(const [name,value] of Object.entries({year:'2025',as_of_date:'2025-12-31',units:'100',url:'https://example.org/test',basis:'검증용 · 실제 저장하지 않음'}))await page.locator('#d907-occupancy-form [name="'+name+'"]').fill(value);
 await page.locator('#d907-occupancy-form button').click();await Promise.all([page.waitForResponse(r=>r.url().includes('/api/admin/policy-delivery')&&r.request().method()==='POST'),page.locator('[data-d907-save]').click()]);
 assert(saved.occupancy_observations.some(o=>o.units===100));
 assert.deepEqual(errors,[]);console.log('Cumulative supply, scope reconciliation, small-island removal, default stage, approval links, occupancy targets and officer forms passed');
}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
