/* Live reads, browser save interception; persistence covered by backend tests. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('/tmp/poc07-playwright/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',args:['--no-sandbox','--enable-webgl','--use-gl=angle','--use-angle=swiftshader']});
 try{
  const guest=await browser.newContext(),g=await guest.newPage();
  await g.goto('https://www.minslab.kr/poc/home/#policy-progress');await g.waitForSelector('#policy-report-summary h3',{timeout:90000});
  assert.equal(await g.locator('[data-policy-information]').count(),0);
  assert.equal((await guest.request.get('https://www.minslab.kr/poc/home/api/policy-information')).status(),401);await guest.close();
  const context=await browser.newContext({viewport:{width:1440,height:900}});await context.addCookies(JSON.parse(fs.readFileSync(process.env.HOME_CHECK_COOKIE_FILE||'/tmp/pi-redesign-cookie.json','utf8')));
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('https://www.minslab.kr/poc/home/#policy-progress');await page.waitForSelector('[data-policy-information]',{timeout:90000});
  await page.locator('[data-policy-information]').click();await page.waitForSelector('.pi-stages',{timeout:90000});
  const fetched=await context.request.get('https://www.minslab.kr/poc/home/api/policy-information');assert.equal(fetched.status(),200);const model=await fetched.json();
  assert.equal(await page.locator('.pi-stages>div').count(),6);assert.equal(await page.locator('[data-pi-scope]').count(),4);
  assert.equal(await page.locator('[data-pi-program]:checked').count(),model.programs.filter(p=>p.selected).length);
  assert.equal(await page.locator('[data-pi-program]').first().isDisabled(),false);
  assert.match(await page.locator('[data-pi-input="overview"]').inputValue(),/선호 입지에 내집 마련/);
  const tooltipButton=page.locator('[data-pi-evidence="overview"]');await tooltipButton.hover();
  const tip=await page.locator('#pi-tooltip').innerText();assert.match(tip,/선호 입지에 내집 마련/);assert.match(tip,/주택공급 확대방안.pdf.*4쪽/);assert.ok(Array.from(tip).length<=200);
  assert.ok(await page.locator('[data-pi-tooltip]').evaluateAll(ns=>ns.every(n=>Array.from(n.dataset.piTooltip).length<=200)));
  await page.screenshot({path:'/tmp/pi-redesign-tooltip.png'});
  await tooltipButton.click();assert.match(await page.locator('.pi-popup').innerText(),/PDF 7쪽/);assert.match(await page.locator('.pi-popup a').last().getAttribute('href'),/#page=7/);await page.locator('.pi-popup [data-close]').click();
  await page.locator('.pi-head h2').click();
  const layouts=[];
  for(const size of [{width:1440,height:900},{width:1366,height:768}]){
   await page.setViewportSize(size);
   const layout=await page.locator('.pi-body').evaluate(n=>({scroll:n.scrollHeight,height:n.clientHeight,width:n.scrollWidth,clientWidth:n.clientWidth,footer:document.querySelector('.pi-footer').getBoundingClientRect().bottom,advice:document.querySelector('.pi-advice-card').getBoundingClientRect().bottom}));
   const annual=await page.locator('#pi-annual').evaluate(n=>({scroll:n.scrollHeight,height:n.clientHeight}));assert.ok(annual.scroll<=annual.height+2,JSON.stringify(annual));layouts.push({size,...layout,annual});assert.ok(layout.scroll<=layout.height+2,JSON.stringify(layout));assert.ok(layout.width<=layout.clientWidth+2);assert.ok(layout.advice<layout.footer&&layout.footer<=size.height);
   await page.screenshot({path:'/tmp/pi-redesign-'+size.width+'.png'});
  }
  await page.locator('[data-pi-input="name"]').fill('정책 관리 검증 <안전>');
  await page.locator('[data-pi-scope="서울특별시"]').click();assert.equal(await page.locator('#pi-annual-scope').innerText(),'서울특별시');
  await page.locator('[data-pi-input="annual:서울특별시:2026"]').fill('68001');
  await page.locator('[data-pi-scope="경기도"]').click();await page.locator('[data-pi-scope="서울특별시"]').click();
  assert.equal(await page.locator('[data-pi-input="annual:서울특별시:2026"]').inputValue(),'68001');
  const selected=model.programs.find(p=>p.selected);await page.locator('[data-pi-program="'+selected.id+'"]').uncheck();
  await page.locator('[data-pi-evidence="program:'+selected.id+'"]').click();assert.match(await page.locator('.pi-popup').innerText(),/기존 수집·매칭 근거/);await page.locator('.pi-popup [data-close]').click();
  await page.locator('[data-pi-save]').click();assert.match(await page.locator('#pi-status').innerText(),/변경자와 변경 사유/);
  let saved=null;
  await page.route('**/api/admin/policy-information',async route=>{saved=route.request().postDataJSON();await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({revision_no:1})});});
  const updated=structuredClone(model);updated.revision_no=1;updated.fields.name={value:'정책 관리 검증 <안전>',manual:true,evidence:[{origin:'MANUAL',value:'정책 관리 검증 <안전>',actor:'브라우저 테스트',changed_at:new Date().toISOString(),reason:'화면 검증'},...model.fields.name.evidence]};
  await page.route('**/api/policy-information',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(updated)}));
  await page.locator('#pi-actor').fill('브라우저 테스트');await page.locator('#pi-reason').fill('화면 검증');await page.locator('[data-pi-save]').click();
  await page.waitForSelector('.pi-has-manual');assert.equal(saved.changes.name,'정책 관리 검증 <안전>');assert.equal(saved.changes['annual:서울특별시:2026'],68001);assert.deepEqual(saved.program_changes[selected.id],{selected:false,revision_no:selected.revision_no});
  await page.locator('[data-pi-evidence="name"]').click();assert.match(await page.locator('.pi-popup').innerText(),/사용자 입력값 · 우선 적용/);await page.locator('.pi-popup [data-close]').click();
  await page.locator('[data-pi-reset="name"]').click();assert.match(await page.locator('[data-pi-input="name"]').inputValue(),/9·7 주택공급/);
  await page.setViewportSize({width:390,height:844});assert.ok(await page.locator('.pi-body').evaluate(n=>n.scrollWidth<=n.clientWidth+2));
  await page.screenshot({path:'/tmp/pi-redesign-mobile.png'});
  assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,layouts,tooltip:tip,guestBlocked:true,saveIntercepted:true,productionWrites:0,mobile:true,errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
