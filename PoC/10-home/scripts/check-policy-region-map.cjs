/* Browser acceptance checks use real read APIs; delay/fallback fixtures are intercepted locally. */
const {chromium}=require(process.env.PLAYWRIGHT_PACKAGE||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.HOME_CHECK_CHROME||undefined,args:['--no-sandbox','--enable-webgl','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 try{
  const base=process.env.HOME_CHECK_BASE||'http://127.0.0.1:18100',page=await browser.newPage({viewport:{width:1640,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));await page.goto(base+'/poc/home/#policy-progress');
  await page.waitForSelector('.prm-card[data-rendered="3d"]',{timeout:90000});
  await page.locator('[data-d907-scope="POLICY_PERIOD"]').click();
  const model=await (await page.request.get(base+'/poc/home/api/policy-delivery')).json();
  await page.locator('[data-d907-hover]').hover({position:{x:350,y:170}});
  assert.match(await page.locator('.d907-chart-tooltip').innerText(),/전체 1,350,000호/);
  assert.equal(await page.locator('.d907-chart-tooltip>div').count(),6);
  assert.equal(await page.locator('[data-d907-delay]').count(),model.issues.filter(i=>i.status==='DELAYED').length?1:0);
  await page.locator('.prm-stage-group [data-d907-stage="SUPPLY"]').click();
  const current=await page.locator('.prm-stats').allTextContents();
  await page.locator('.d907-map-controller [data-d907-year]').evaluate(n=>{n.value='2028';n.dispatchEvent(new Event('input',{bubbles:true}));});
  await page.waitForFunction(()=>document.querySelector('.prm-stats').textContent.includes('2028'));
  assert.notDeepEqual(await page.locator('.prm-stats').allTextContents(),current);
  for(const view of ['2d','3d','2d','3d']){await page.locator('[data-prm-mode="'+view+'"]').click();await page.waitForFunction(v=>[...document.querySelectorAll('.prm-card')].every(n=>n.dataset.rendered===v),view);}
  await page.locator('.d907-flow [data-d907-now]').click();await page.locator('.prm-stage-group [data-d907-stage="CONSTRUCTION"]').click();
  await page.screenshot({path:'/tmp/home-stage-review/region-cards-final.png'});
  await page.locator('.d907-chart-wrap').screenshot({path:'/tmp/home-stage-review/flow-final.png'});
  await page.setViewportSize({width:390,height:900});await page.waitForTimeout(250);
  assert(await page.locator('.prm-cards').evaluate(n=>n.getBoundingClientRect().right<=innerWidth+1));
  await page.setViewportSize({width:1640,height:1100});
  await page.locator('#home-main-nav [data-view="overview"]').click();
  await page.waitForSelector('#housing-map-3d canvas',{timeout:90000});
  for(let i=0;i<100&&!await page.evaluate(()=>MapThreeD.active());i++)await page.waitForTimeout(250);
  assert(await page.evaluate(()=>MapThreeD.active()),await page.locator('#map-3d-status').innerText());
  await page.evaluate(()=>MapThreeD.setLevel('policy'));
  await page.locator('.map-scene-region').filter({hasText:'인천'}).waitFor({timeout:60000});
  assert.equal(await page.locator('.map-scene-region').count(),3);
  await page.screenshot({path:'/tmp/home-stage-review/main-incheon-final.png'});
  await page.locator('#home-main-nav [data-view="policy-progress"]').click();
  await page.waitForFunction(()=>document.querySelectorAll('.prm-card[data-rendered="3d"] canvas').length===3,null,{timeout:60000});
  // Background tile failures must not suppress the locally computed supply markers.
  await page.route('**/api/tiles/**',r=>r.abort());
  await page.locator('#home-main-nav [data-view="overview"]').click();
  for(let i=0;i<100&&!await page.evaluate(()=>MapThreeD.active());i++)await page.waitForTimeout(250);
  assert(await page.evaluate(()=>MapThreeD.active()),'Supply map must survive unavailable raster tiles');
  await page.evaluate(()=>MapThreeD.setLevel('policy'));
  await page.locator('.map-scene-region').filter({hasText:'인천'}).waitFor({timeout:30000});
  await page.unroute('**/api/tiles/**');
  await page.locator('#home-main-nav [data-view="policy-progress"]').click();
  await page.waitForSelector('.prm-card[data-rendered="3d"]',{timeout:60000});
  // Confirmed delays overlay the affected band; no extra households are added.
  const fixture=structuredClone(model),cohort=fixture.cohorts.find(c=>c.parts.CONSTRUCTION>100);
  fixture.issues=[{project_id:cohort.id,name:cohort.name,stage:'CONSTRUCTION',units:100,due_date:'2026-01-01',status:'DELAYED'}];
  await page.route('**/api/policy-delivery?*',r=>r.fulfill({json:fixture}));await page.reload();
  await page.waitForSelector('[data-d907-delay="CONSTRUCTION"]',{timeout:90000});
  await page.locator('[data-d907-scope="POLICY_PERIOD"]').click();
  assert.notEqual(await page.locator('[data-d907-delay="CONSTRUCTION"]').getAttribute('d'),'');
  assert.match(await page.locator('.d907-flow-note').innerText(),/합계 1,350,000호/);
  await page.unroute('**/api/policy-delivery?*');
  const source=fs.readFileSync(require('node:path').join(__dirname,'../web/assets/policy-region-map.js'),'utf8').replace('const renderer=new T.WebGLRenderer','throw new Error("test: WebGL unavailable");const renderer=new T.WebGLRenderer');
  await page.route('**/assets/policy-region-map.js',r=>r.fulfill({body:source,contentType:'application/javascript'}));await page.reload();
  await page.waitForSelector('.prm-card[data-rendered="2d"]',{timeout:90000});assert.equal(await page.locator('.prm-surface svg').count(),3);
  assert.deepEqual(errors,[]);console.log('3D/2D, tooltip conservation, cached slider, resize, main Incheon marker, GPU resume, delay overlay and WebGL fallback passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
