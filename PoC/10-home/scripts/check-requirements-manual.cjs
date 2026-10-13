const {chromium}=require('/tmp/poc07-playwright/node_modules/playwright');
const assert=require('node:assert/strict');
(async()=>{const b=await chromium.launch({headless:true,executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',args:['--no-sandbox','--enable-webgl','--use-gl=angle','--use-angle=swiftshader']});try{
 const p=await b.newPage({viewport:{width:1440,height:1080}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.goto((process.env.HOME_CHECK_BASE||'http://127.0.0.1:18101')+'/poc/home/#requirements');await p.waitForSelector('.req-item',{timeout:90000});
 assert.equal(await p.locator('.req-item').count(),12);assert.equal(await p.locator('[data-nav-group="manual"]').getAttribute('aria-expanded'),'true');
 await p.locator('#requirements-search').fill('f-06');assert.equal(await p.locator('.req-item').count(),1);await p.locator('.req-original summary').click();assert.equal(await p.locator('.req-original li').count(),5);
 await p.locator('#requirements-search').fill('');await p.locator('#requirements-priority').selectOption('중요');assert.equal(await p.locator('.req-item').count(),3);
 await p.locator('#requirements-priority').selectOption('');await p.screenshot({path:'/tmp/home-requirements-manual.png'});
 await p.locator('#requirement-F-10 [data-view="project-collection"]').click();assert.equal(await p.locator('#pane-project-collection').getAttribute('hidden'),null);
 await p.evaluate(()=>setView('program-progress'));await p.waitForSelector('#program-scope-evidence .psr-scope',{timeout:90000});const prog=await p.locator('#policy-geo-scope').inputValue();assert.equal(await p.locator('#program-scope-evidence .psr-scope').getAttribute('data-scope-id'),prog);assert.equal(await p.locator('#program-scope-evidence .psr-stage').count(),6);
 const project=p.locator('#program-progress-detail [data-pr-project]').first();const id=await project.getAttribute('data-pr-project');await project.click();await p.waitForSelector('#project-scope-evidence .psr-scope',{timeout:90000});assert.equal(await p.locator('#project-scope-evidence .psr-scope').getAttribute('data-scope-id'),id);await p.waitForSelector('[data-scope-history] table',{timeout:90000});assert.equal(await p.locator('#project-scope-evidence .psr-stage').count(),6);assert.match(await p.locator('#project-scope-evidence [data-scope-location]').innerText(),/입지|시설/);
 await p.evaluate(()=>setView('requirements'));await p.setViewportSize({width:390,height:844});await p.screenshot({path:'/tmp/home-requirements-mobile.png'});assert.equal(await p.locator('.req-item').count(),12);
 assert.deepEqual(errors,[]);console.log(JSON.stringify({checks:['매뉴얼 하위 메뉴·직접 경로','F01–F12 원문·우선순위·검색·화면 연결','프로그램 선택 범위 원장·6단계','사업 상세 원장·이력·입지','모바일'],errors},null,2));
}finally{await b.close()}})().catch(e=>{console.error(e);process.exit(1)});
