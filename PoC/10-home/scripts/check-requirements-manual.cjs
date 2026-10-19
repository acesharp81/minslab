const {chromium}=require('/tmp/poc07-playwright/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const script=path.join(__dirname,'../web/assets/requirements-manual.js');
const context={};vm.createContext(context);vm.runInContext(fs.readFileSync(script,'utf8')+';globalThis.review=RequirementsManual;',context);
const expected=context.review.summary(),base=process.env.HOME_CHECK_BASE||'http://127.0.0.1:18100';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',args:['--no-sandbox','--enable-webgl','--use-gl=angle','--use-angle=swiftshader']});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1080},acceptDownloads:true}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  if(process.env.HOME_CHECK_LOCAL_REQUIREMENTS==='1'){
   await page.route('**/assets/requirements-manual.js*',route=>route.fulfill({path:script,contentType:'application/javascript'}));
   await page.route('**/poc/home/',route=>route.fulfill({path:path.join(__dirname,'../web/index.html'),contentType:'text/html'}));
  }
  await page.goto(base+'/poc/home/#requirements');
  await page.waitForSelector('.req-item',{timeout:90000});
  await page.waitForFunction(()=>document.querySelector('#requirements-overview')?.textContent.includes('데이터 분모: 등록된 9·7 사업 기록')&&!document.querySelector('#requirements-overview')?.textContent.includes('조회 중'),{timeout:90000});
  assert.equal(await page.locator('.req-item').count(),12);
  assert.equal(await page.locator('.req-original ol li').count(),61);
  assert.equal(await page.locator('[data-nav-group="manual"]').getAttribute('aria-expanded'),'true');
  const actual=await page.evaluate(()=>RequirementsManual.summary());assert.deepEqual(actual,JSON.parse(JSON.stringify(expected)));
  const overview=await page.locator('#requirements-overview').innerText();
  assert.ok(overview.includes(expected.percent+'%'));assert.ok(overview.includes(expected.reviewed_at));assert.ok(overview.includes(expected.version));
  assert.ok((await page.locator('.req-now').textContent()).includes(expected.reviewed_at));
  const dataResponse=await page.request.get(base+'/poc/home/api/requirements-status');assert.equal(dataResponse.status(),200);const data=await dataResponse.json();
  for(const [id,assessment]of Object.entries(context.review.assessments)){
   assert.equal(await page.locator('#requirement-'+id+' .req-scores > div:first-child b').textContent(),context.review.score(id)+'%');
   assert.equal(await page.locator('#requirement-'+id+' .req-original ol li').count(),assessment.scores.length);
  }
  await page.locator('#requirements-status-filter').selectOption('function');assert.equal(await page.locator('.req-item').count(),4);
  await page.locator('#requirements-status-filter').selectOption('');
  await page.locator('#requirements-search').fill('f-06');assert.equal(await page.locator('.req-item').count(),1);await page.locator('.req-original summary').click();assert.equal(await page.locator('.req-original li').count(),5);
  await page.locator('#requirements-search').fill('');await page.locator('#requirements-priority').selectOption('중요');assert.equal(await page.locator('.req-item').count(),3);await page.locator('#requirements-priority').selectOption('');
  const [download]=await Promise.all([page.waitForEvent('download'),page.locator('#requirements-export').click()]);
  const csvPath='/tmp/home-requirements-latest.csv';await download.saveAs(csvPath);const csv=fs.readFileSync(csvPath,'utf8');
  assert.equal(csv.trim().split(/\r?\n/).length,13);for(const term of ['기능평가기준일','평가버전','세부점수','세부판정근거','구현·검증근거',expected.version,expected.reviewed_at])assert.ok(csv.includes(term));
  await page.screenshot({path:'/tmp/home-requirements-manual.png'});
  await page.locator('#requirement-F-10 [data-view="project-collection"]').click();assert.equal(await page.locator('#pane-project-collection').getAttribute('hidden'),null);
  if(process.env.HOME_CHECK_DETAILS==='1'){
   await page.evaluate(()=>setView('program-progress'));await page.waitForSelector('#program-scope-evidence .psr-scope',{timeout:90000});
   const program=await page.locator('#policy-geo-scope').inputValue();assert.equal(await page.locator('#program-scope-evidence .psr-scope').getAttribute('data-scope-id'),program);assert.equal(await page.locator('#program-scope-evidence .psr-stage').count(),6);
   const project=page.locator('#program-progress-detail [data-pr-project]').first(),id=await project.getAttribute('data-pr-project');await project.click();
   await page.waitForSelector('#project-scope-evidence .psr-scope',{timeout:90000});assert.equal(await page.locator('#project-scope-evidence .psr-scope').getAttribute('data-scope-id'),id);await page.waitForSelector('[data-scope-history] table',{timeout:90000});assert.equal(await page.locator('#project-scope-evidence .psr-stage').count(),6);assert.match(await page.locator('#project-scope-evidence [data-scope-location]').innerText(),/입지|시설/);
  }
  await page.evaluate(()=>setView('requirements'));await page.setViewportSize({width:390,height:844});await page.waitForTimeout(250);
  assert.equal(await page.locator('.req-item').count(),12);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
  await page.screenshot({path:'/tmp/home-requirements-mobile.png'});assert.deepEqual(errors,[]);
  const result={reviewed_at:expected.reviewed_at,base,local_asset_override:process.env.HOME_CHECK_LOCAL_REQUIREMENTS==='1',detail_scope_checks:process.env.HOME_CHECK_DETAILS==='1',summary:actual,data,checks:['12 requirements / 61 original subitems','review date/version/weighted denominator','per-requirement score and reasons','partial feature/priority/search filters','CSV score/reason/date/evidence columns','source collection navigation','390px overflow and desktop rendering'],errors,csv:csvPath};
  fs.writeFileSync('/tmp/home-requirements-browser-20261015.json',JSON.stringify(result,null,2));console.log(JSON.stringify({summary:actual,project_count:data.project_count,checks:result.checks,errors},null,2));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
