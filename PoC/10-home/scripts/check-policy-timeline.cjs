/* Public read-only check: policy overview, annual units and plan-over-report tree. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const root=process.env.HOME_CHECK_URL||'https://www.minslab.kr/poc/home/';
const artifact='/tmp/home-policy-timeline-check';fs.mkdirSync(artifact,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.HOME_CHECK_CHROME||undefined,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1100}}),errors=[];
  page.setDefaultTimeout(30000);page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await page.goto(root+'#policy-progress');await page.locator('#content').waitFor({state:'visible'});
  const res=await page.request.get(new URL('api/policy-monitor',root).href);assert.equal(res.status(),200);const data=await res.json();
  assert.equal(await page.locator('.policy-snapshot').count(),data.items.length);
  assert.deepEqual(await page.locator('#policy-monitor-detail>section').evaluateAll(es=>es.map(e=>e.id)),['policy-overview','policy-annual-supply','policy-block-timeline','policy-original-sources']);
  let totalBlocks=0,totalReports=0;
  for(const row of data.items){
   await page.locator('#policy-detail-select').selectOption(row.id);
   assert((await page.locator('#policy-overview h2').textContent()).includes(row.name));
   for(const label of ['목적','위치','기간','세부 공급 내역'])assert((await page.locator('#policy-overview').textContent()).includes(label));
   assert.equal(await page.locator('.policy-explorer-tabs [role="tab"][aria-selected="true"]').getAttribute('data-monitor-detail'),row.id);
   const blocks=row.timeline.regions.flatMap(r=>r.cities.flatMap(c=>c.blocks));totalBlocks+=blocks.length;
   assert.equal(await page.locator('.timeline-block').count(),blocks.length);
   assert.equal(await page.locator('.timeline-group.region').count(),row.timeline.regions.length);
   assert.equal(await page.locator('.timeline-group.municipality').count(),row.timeline.regions.reduce((n,r)=>n+r.cities.length,0));
   assert.equal(await page.locator('.timeline-year-column').count(),0);
   assert.equal(await page.locator('.policy-year-column').count(),row.timeline.years.length);
   assert.equal(await page.locator('[data-timeline-header]').first().getAttribute('data-timeline-header'),String(row.timeline.years[0]));
   for(const measure of ['SUPPLY','COMPLETION','MOVE_IN']){
    await page.locator('#policy-timeline-measure').selectOption(measure);
    assert.equal(await page.locator('.annual-supply-bar').count(),row.timeline.annual.filter(a=>a[measure].units!=null).length);
    for(const a of row.timeline.annual){
     const text=await page.locator(`[data-supply-year="${a.year}"] .annual-unit-label`).textContent();
     assert.equal(text,a[measure].units==null?'':a[measure].units.toLocaleString('en-US')+'호');
     if(a[measure].units!=null){const height=await page.locator(`[data-supply-year="${a.year}"] .annual-supply-bar rect`).getAttribute('height');const max=Math.max(...row.timeline.annual.map(y=>y[measure].units||0));assert(Math.abs(+height-a[measure].units/max*100)<.001);}
    }
   }
   const reportCount=blocks.reduce((n,b)=>n+b.actuals.length,0);totalReports+=reportCount;
   assert.equal(await page.locator('.actual-report').count(),reportCount);
   const reports=await page.locator('.actual-report').evaluateAll(es=>es.map(e=>{
    const plan=e.closest('td').querySelector('.block-year-plan');return {id:e.dataset.project,date:e.dataset.reportDate,pct:+e.dataset.progressPct,year:+e.closest('td').dataset.timelineYear,below:e.getBoundingClientRect().top>=plan.getBoundingClientRect().bottom};
   }));
   const widths=await page.locator('.actual-report').evaluateAll(es=>es.map(e=>({pct:+e.dataset.progressPct,ratio:e.querySelector('.actual-progress-fill').getBoundingClientRect().width/e.querySelector('.actual-progress-track').getBoundingClientRect().width*100})));
   for(const w of widths)assert(Math.abs(w.ratio-w.pct)<.1,'actual bar must match reported percentage');
   for(const a of reports){assert(a.below);assert.equal(a.year,+a.date.slice(0,4));assert(a.date<=data.reference_date);assert(blocks.some(b=>b.actuals.some(s=>s.project_id===a.id&&s.date===a.date&&s.pct===a.pct)));}
   assert.equal(await page.locator('#policy-original-sources a').count(),row.timeline.evidence.length);
  }
  await page.locator('#policy-detail-select').selectOption('MON_THIRD_NEW_TOWN');await page.locator('#policy-timeline-measure').selectOption('COMPLETION');
  const count=await page.locator('.timeline-block').count();assert(count>0);
  await page.locator('[data-timeline-expand="none"]').click();assert.equal(await page.locator('.timeline-block').count(),0);
  await page.locator('[data-timeline-expand="all"]').click();assert.equal(await page.locator('.timeline-block').count(),count);
  const city=page.locator('.timeline-group.municipality button').first();const cityID=await city.getAttribute('data-timeline-toggle');
  await city.click();assert.equal(await page.locator(`[data-timeline-toggle="${cityID}"]`).getAttribute('aria-expanded'),'false');assert((await page.locator('.timeline-block').count())<count);
  await page.locator(`[data-timeline-toggle="${cityID}"]`).click();assert.equal(await page.locator('.timeline-block').count(),count);
  const scroller=page.locator('.policy-tree-scroll');await scroller.evaluate(e=>{e.scrollLeft=400;});
  const left=await page.locator('.timeline-block .timeline-name').first().boundingBox(),bounds=await scroller.boundingBox();assert(Math.abs(left.x-bounds.x)<=2,'summary column stays pinned');
  const row=await page.locator('.timeline-block').filter({has:page.locator('.actual-report')}).first();await row.scrollIntoViewIfNeeded();
  const name=await row.locator('.timeline-block-name').textContent();await row.locator('.timeline-block-name').click();await page.locator('#detail-dialog').waitFor({state:'visible'});await page.locator('#close-detail').click();
  await page.locator('#pane-policy-progress').screenshot({path:artifact+'/policy-explorer.png'});
  await page.locator('#policy-block-timeline').screenshot({path:artifact+'/block-plan-actual.png'});
  await page.locator('#policy-original-sources').screenshot({path:artifact+'/original-sources.png'});
  const mobile=await browser.newPage({viewport:{width:390,height:844}});mobile.on('pageerror',e=>errors.push(e.message));mobile.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await mobile.goto(root+'#policy-progress');await mobile.locator('#content').waitFor({state:'visible'});
  assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  await mobile.locator('#policy-detail-select').selectOption('MON_THIRD_NEW_TOWN');
  await mobile.locator('[data-timeline-current]').click();await mobile.waitForTimeout(400);
  assert((await mobile.locator('.policy-tree-scroll').evaluate(e=>e.scrollLeft))>0);
  assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  await mobile.locator('#policy-overview').screenshot({path:artifact+'/mobile-overview.png'});
  await mobile.locator('#policy-block-timeline').screenshot({path:artifact+'/mobile-timeline.png'});
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'PASS',policies:data.items.length,blocksChecked:totalBlocks,reportsChecked:totalReports,planAboveActual:true,sourceLinksAtBottom:true,annualMeasures:3,treeCollapse:true,stickySummary:true,mobileOverflow:false,consoleErrors:0,artifact}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
