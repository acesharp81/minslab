/* Independent block glyphs: geometry, quantities, evidence and wheel behavior. Read-only. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const root=process.env.HOME_CHECK_URL||'https://www.minslab.kr/poc/home/';
const artifact='/tmp/home-block-glyph-check';fs.mkdirSync(artifact,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.HOME_CHECK_CHROME||undefined,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1100}}),errors=[];
  page.setDefaultTimeout(30000);page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await page.goto(root);await page.locator('#content').waitFor({state:'visible'});
  const response=await page.request.get(new URL('api/map/dashboard?measure=SUPPLY&horizon=10',root).href);assert.equal(response.status(),200);const data=await response.json();
  await page.locator('[data-bar-level="block"]').click();await page.locator('.independent-block-marker').first().waitFor({state:'visible'});
  await page.locator('#housing-map').scrollIntoViewIfNeeded();
  assert.equal(await page.locator('.native-block-scroll').count(),0);
  const glyphs=await page.locator('.independent-block-marker').evaluateAll(elements=>elements.map(e=>{
   const r=e.getBoundingClientRect();return {id:e.querySelector('[data-block-id]').dataset.blockId,x:r.x,y:r.y,w:r.width,h:r.height,text:e.textContent,background:getComputedStyle(e).backgroundColor};
  }));
  assert(glyphs.length>1);assert.equal(new Set(glyphs.map(g=>g.id)).size,glyphs.length);
  const map=await page.locator('#housing-map').boundingBox(),panel=await page.locator('.map-side-panel').boundingBox();
  for(const [i,g] of glyphs.entries()){
   assert.equal(g.w,82);assert.equal(g.h,142);assert.equal(g.background,'rgba(0, 0, 0, 0)');
   assert(g.x>=map.x&&g.x+g.w<=panel.x-1&&g.y>=map.y&&g.y+g.h<=map.y+map.height);
   const block=data.blocks.find(b=>b.id===g.id);assert(block);assert(g.text.includes(block.block));assert.equal(g.text.includes('목표'),block.progress.cumulative_goal_units!=null);assert.equal(g.text.includes('현재'),block.progress.observed_units!=null);assert(!/미확보|일정\?|\+[123]\?/.test(g.text));
   for(const f of block.projection.future.slice(0,3))assert.equal(g.text.includes(`+${f.offset}`),block.target_units>0&&block.progress.observed_units!=null&&f.cumulative_units!=null);
   for(const h of glyphs.slice(i+1))assert(!(g.x<h.x+h.w&&g.x+g.w>h.x&&g.y<h.y+h.h&&g.y+g.h>h.y),'glyphs may not overlap');
  }
  const actual=await page.locator('.block-glyph').first().evaluate(e=>e.getAttribute('aria-label'));assert.match(actual,/총 공급계획/);
  // A synthetic rendering check exercises known future increments without
  // inventing or writing fixture actuals to the production dataset.
  const rendered=await page.evaluate(()=>{
   const row={id:'fixture',name:'검증 A4',district_name:'검증 공공주택지구',block:'A4',target_units:100,
    progress:{observed_units:20,cumulative_goal_units:30,late_count:1,max_lag_months:2},
    projection:{future:[{offset:1,cumulative_units:40,increment_units:20},{offset:2,cumulative_units:60,increment_units:40},{offset:3,cumulative_units:80,increment_units:60}]},milestones:[]};
   const div=document.createElement('div');div.innerHTML=BlockMonitor.graph(row);
   return {status:BlockMonitor.status(row.progress),segments:[...div.querySelectorAll('.block-future-fill')].map(e=>({y:+e.getAttribute('y'),h:+e.getAttribute('height')})),current: +div.querySelector('.block-current-fill').getAttribute('y'),capacityBars:div.querySelectorAll('.block-capacity-bar').length,goal:div.querySelector('.block-goal-tick').dataset.goal,
    early:BlockMonitor.status({early_count:1,max_lead_months:2}).code,normal:BlockMonitor.status({on_time_count:1}).code,unknown:BlockMonitor.status({}).code};
  });
  assert.equal(rendered.status.code,'late');assert.equal(rendered.early,'early');assert.equal(rendered.normal,'normal');assert.equal(rendered.unknown,'unknown');assert.equal(rendered.goal,'30');
  assert.equal(rendered.segments.length,3);assert.equal(rendered.capacityBars,1);assert(Math.abs(rendered.segments[0].y+rendered.segments[0].h-rendered.current)<1e-8);
  for(let i=1;i<3;i++)assert(Math.abs(rendered.segments[i].y+rendered.segments[i].h-rendered.segments[i-1].y)<1e-8);
  for(let attempt=0;attempt<40&&await page.locator('.leaflet-tile:not(.leaflet-tile-loaded)').count();attempt++)await page.waitForTimeout(250);
  await page.locator('.housing-map-workspace').screenshot({path:artifact+'/independent-blocks.png'});
  await page.locator('.native-block-row').first().hover();await page.locator('.block-evidence-tooltip').first().waitFor({state:'visible'});
  assert.match(await page.locator('.block-evidence-tooltip').first().textContent(),/실제 블록 위치 미확정/);
  await page.locator('.native-block-row').first().click();assert.match(await page.locator('#map-project-detail').textContent(),/선택 블록/);
  await page.locator('.block-stage-details summary').click();assert(!/미확보/.test(await page.locator('.block-stage-details').textContent()));
  const csv=await page.request.get(new URL(await page.locator('#supply-export').getAttribute('href'),root).href);assert.equal(csv.status(),200);assert((await csv.text()).includes('early_count'));
  const largest=data.districts.map(d=>({...d,blocks:data.blocks.filter(b=>b.district_name===d.name&&b.coordinate_basis==='DISTRICT_REPRESENTATIVE')})).sort((a,b)=>b.blocks.length-a.blocks.length)[0];
  await page.evaluate(id=>{const b=document.createElement('button');b.dataset.mapProject=id;document.body.append(b);b.click();b.remove();},largest.blocks[0].project_ids[0]);
  await page.waitForTimeout(500);
  const dense=await page.locator('.block-glyph').evaluateAll(elements=>elements.map(e=>({id:e.dataset.blockId,text:e.textContent})));
  const largestVisible=dense.filter(g=>largest.blocks.some(b=>b.id===g.id)).length;
  assert.equal(largestVisible,largest.blocks.length,'focused district blocks should be independently visible');
  await page.mouse.move(20,20);await page.waitForTimeout(200);
  const textWidths=await page.locator('.block-year-tick').evaluateAll(elements=>elements.map(e=>e.getBBox().width));assert(textWidths.every(w=>w<=26),'forecast ticks must fit beside the bar');
  assert.equal(await page.locator('.block-capacity-bar').count(),dense.filter(g=>data.blocks.find(b=>b.id===g.id)?.target_units>0).length,'one vertical bar per known capacity');
  assert.deepEqual(await page.locator('.block-capacity-bar').evaluateAll(es=>[...new Set(es.map(e=>+e.getAttribute('width')))]),[10]);
  for(let attempt=0;attempt<40&&await page.locator('.leaflet-tile:not(.leaflet-tile-loaded)').count();attempt++)await page.waitForTimeout(250);
  await page.locator('.housing-map-workspace').screenshot({path:artifact+'/many-blocks.png'});
  const mobile=await browser.newPage({viewport:{width:390,height:844}});mobile.on('pageerror',e=>errors.push(e.message));
  await mobile.goto(root);await mobile.locator('#content').waitFor({state:'visible'});await mobile.locator('[data-bar-level="block"]').click();await mobile.locator('.independent-block-marker').first().waitFor({state:'visible'});
  assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  await mobile.locator('.housing-map-workspace').screenshot({path:artifact+'/mobile-blocks.png'});
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'PASS',visibleBlocks:glyphs.length,focusedDistrictBlocks:largestVisible,independent:true,oneVerticalBarPerBlock:true,nonOverlapping:true,currentGoalForecast:true,forecastStacked:true,statusComparison:true,detailSelection:true,mobileOverflow:false,consoleErrors:0,artifact}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
