const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('/tmp/poc07-playwright/node_modules/playwright');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',args:['--no-sandbox']});try{
 const ctx=await browser.newContext({viewport:{width:1440,height:900}});await ctx.addCookies(JSON.parse(fs.readFileSync('/tmp/project-editor-cookie.json','utf8')));
 const base='https://www.minslab.kr/poc/home',page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/admin/**',r=>r.request().method()==='GET'?r.continue():r.abort());
 const c=await (await ctx.request.get(base+'/api/project-workspace')).json();
 await page.goto(base+'/#projects');await page.waitForSelector('.pjt-stages',{timeout:90000});
 async function select(pid){const p=c.items.find(p=>p.id===pid);assert.ok(p);await page.locator('#pjt-program').selectOption(p.mapping.program_id);await page.locator('#pjt-project').selectOption(p.id);await page.locator('#pjt-mapping-note').filter({hasText:p.id}).waitFor();await page.waitForSelector('#pjt-location .psr-location-content',{timeout:45000});return p;}
 const bucheon=await select('PRO_69217405e9523695488434c1');
 await page.locator('[data-pjt-edit]').last().click();
 assert.equal(await page.locator('[data-pjt-field="progress_pct"]').inputValue(),'0');
 assert.equal(await page.locator('[data-pjt-field="progress_date"]').inputValue(),'2026-07-01');
 assert.equal(await page.locator('[data-pjt-actual-date="CONSTRUCTION"]').inputValue(),'2026-02-01');
 assert.equal(await page.locator('[data-pjt-due="SUPPLY"]').inputValue(),'2026-09-30');
 assert.equal(await page.locator('[data-pjt-units="SUPPLY"]').inputValue(),'548');
 assert.equal(await page.locator('[data-pjt-actual-units="CONSTRUCTION"]').inputValue(),'');
 assert.equal(await page.locator('[data-pjt-actual-date="SUPPLY"]').inputValue(),'');
 await page.locator('#project-information-dialog [data-pjt-evidence="progress_pct"]').click();assert.match(await page.locator('.pi-popup').innerText(),/연결된 원천 수집값/);assert.match(await page.locator('.pi-popup').innerText(),/검토 중/);await page.locator('.pi-popup header button').click();await page.screenshot({path:'/tmp/project-defaults-fixed.png'});await page.locator('[data-pjt-close]').click();
 const godeok=c.items.find(p=>p.name.includes('고덕강일')&&p.name.includes('3단지'));assert.ok(godeok);await select(godeok.id);
 const boxes=await page.locator('.pjt-overview').evaluate(n=>[...n.children].map(c=>{const r=c.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height};}));assert.equal(boxes.length,3);assert.ok(boxes.every(r=>Math.abs(r.y-boxes[0].y)<1));assert.ok(Math.abs(boxes[0].width-boxes[2].width)<1);assert.ok(boxes[0].x<boxes[1].x&&boxes[1].x<boxes[2].x);assert.equal(await page.locator('#pjt-location').count(),1);await page.locator('.pjt-overview').scrollIntoViewIfNeeded();await page.screenshot({path:'/tmp/project-summary-three-columns.png'});
 await select('PRO_70c16f89c02d428a47cc1de7');await page.waitForSelector('.pjt-facility-summary svg',{timeout:45000});assert.equal(await page.locator('.pjt-facility-summary .pd-kpis>div').count(),4);assert.equal(await page.locator('.pjt-facility-details').getAttribute('open'),null);await page.locator('.pjt-overview').scrollIntoViewIfNeeded();await page.screenshot({path:'/tmp/project-summary-radar.png'});
 await page.locator('.pjt-facility-details>summary').click();assert.ok(await page.locator('.pjt-facility-details table').isVisible());await page.locator('.pjt-facility-details>summary').click();await page.locator('[data-location-radius]').selectOption('1000');assert.match(await page.locator('.pjt-facility-summary svg').textContent(),/1.0km/);
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));const mobile=await page.locator('.pjt-overview').evaluate(n=>getComputedStyle(n).gridTemplateColumns.split(' ').length);assert.equal(mobile,1);await page.locator('.pjt-overview').scrollIntoViewIfNeeded();await page.screenshot({path:'/tmp/project-summary-mobile.png'});
 assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,columns:boxes,mobileColumns:mobile,radarPreserved:true,sourceDefaults:true,unknownActualsRemainEmpty:true,productionWrites:0,errors}));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
