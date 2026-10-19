const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('/tmp/poc07-playwright/node_modules/playwright');
const dest=path.resolve(__dirname,'../docs/evidence',process.env.HOME_CHECK_EVIDENCE||'HOME_POLICY_SCOPE_AUDIT_20261019');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1600,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto((process.env.HOME_CHECK_BASE||'http://127.0.0.1:18100')+'/poc/home/#policy-progress');
 await page.locator('.d907-stage-SUPPLY').waitFor({timeout:90000});
 await page.evaluate(()=>{const original=PolicyRegionMap.render;PolicyRegionMap.render=(host,m)=>{window.__auditMap=m;return original(host,m);};Policy907.show();});
 const restored=await page.evaluate(async()=>{const c=await Policy907.reportContext();return {portfolio:c.scope.portfolio,ids:c.data.cohorts.map(c=>c.id),alignment:c.data.official_alignment};});
 assert.equal(restored.portfolio,true);
 assert.equal(restored.alignment.cases.length,16);
 assert.ok(restored.alignment.named_prior_start_ids.length>0);
 for(const id of restored.alignment.named_prior_start_ids)assert.ok(restored.ids.includes(id),'official named past-start project retained: '+id);
 assert.ok(restored.alignment.cases.find(c=>c.id==='S03').members.length>0);
 assert.ok(restored.alignment.cases.find(c=>c.id==='S04').members.length>0);
 const results=[];
 async function verify(label){
   const r=await page.evaluate(async()=>{const c=await Policy907.reportContext(),m=window.__auditMap;const end=c.scope.year===Number(c.scope.as_of_date.slice(0,4))?c.scope.as_of_date:c.scope.year+'-12-31';
    const values=c.data.comparisons[m.stage]?.actual_points||[],measurement=values.filter(p=>p.date<=end&&p.date<=c.scope.as_of_date).at(-1)?.units??null;
    const selected=c.scope.municipality_id?m.values[c.scope.municipality_id]?.value:c.scope.region?m.regions[c.scope.region]?.value:Object.values(m.regions).reduce((n,r)=>n+r.value,0);
    const target=c.data.comparisons[m.stage]?.target_points?.filter(p=>p.date<=c.scope.year+'-12-31').at(-1)?.units??null;
    const card=document.querySelector('.d907-stage-'+m.stage);return {exported:c.data.summary_cards[m.stage],scope:c.scope,map:selected,measurement,expected:target,card:card.innerText,values:[...card.querySelectorAll('.d907-stage-number b')].map(n=>Number(n.textContent.replace(/[^\d]/g,''))),regions:Object.fromEntries(Object.entries(m.regions).map(([k,v])=>[k,v.value]))};});
   assert.equal(r.map,r.measurement??0,label+' map/model');if(r.measurement!=null)assert.equal(r.values[0],r.measurement,label+' actual card');if(r.expected!=null)assert.equal(r.values[1],r.expected,label+' December plan');
   assert.equal(r.exported.current_units,r.measurement);assert.equal(r.exported.expected_units,r.expected);assert.match(r.card,/현재 누적 측정량/);assert.match(r.card,/12월 말 기준 누적 예상량/);results.push({label,...r});
 }
 for(const stage of ['SUPPLY','CONSTRUCTION','BUSINESS','APPROVAL','MOVE_IN']){await page.locator('[data-d907-stage="'+stage+'"]').click();await verify('policy '+stage);}
 await page.locator('[data-d907-stage="SUPPLY"]').click();
 await page.evaluate(()=>{const b=document.createElement('button');b.dataset.d907Region='경기도';document.body.append(b);b.click();b.remove();});await verify('Gyeonggi supply');
 await page.evaluate(()=>{const city=Object.entries(window.__auditMap.values).find(([id,v])=>v.value>0);const b=document.createElement('button');b.dataset.d907City=city[0];document.body.append(b);b.click();b.remove();});await verify('municipality supply');
 await page.evaluate(()=>Policy907.reset());
 await page.locator('[data-d907-year]').evaluate(n=>{n.value='2027';n.dispatchEvent(new Event('input',{bubbles:true}));});await verify('2027 plans, measurements capped at current date');
 await page.locator('[data-d907-now]').click();
 await page.locator('.d907-stage-table').screenshot({path:path.join(dest,'cards.png')});
 await page.locator('#policy-geo-map').screenshot({path:path.join(dest,'map.png')});
 await page.evaluate(()=>{state.view='program-progress';Policy907.showProgram(Policy907.programs().find(p=>p.project_count>0)?.id||Policy907.programs()[0].id);});
 await page.waitForFunction(()=>document.querySelector('#program-progress-detail .d907-stage-SUPPLY'));
 await verify('program supply');
 await page.setViewportSize({width:390,height:844});await page.evaluate(()=>{state.view='policy-progress';Policy907.reset();});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(dest,'browser.json'),JSON.stringify({restored,results,errors,mobileOverflow:false},null,2));console.log(JSON.stringify({checks:results.length,first:results[0],errors}));
 }finally{await browser.close();}})().catch(e=>{console.error(e.stack);process.exit(1)});
