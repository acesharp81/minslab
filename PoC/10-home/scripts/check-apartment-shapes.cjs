/* Official parcel extrusion, unknown-value omission and physical interaction. Read-only. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const root=process.env.HOME_CHECK_URL||'https://www.minslab.kr/poc/home/';
const artifact='/tmp/home-apartment-shapes-check';fs.mkdirSync(artifact,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.HOME_CHECK_CHROME||undefined,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1100}}),errors=[];
  page.setDefaultTimeout(30000);page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await page.goto(root);await page.locator('#content').waitFor({state:'visible'});
  assert.equal(await page.locator('.apartment-roof').count(),0);
  await page.locator('[data-bar-level="block"]').click();await page.locator('.apartment-roof').first().waitFor({state:'visible'});
  const shapes=await page.locator('.apartment-roof').count();assert(shapes>0&&shapes<=160);
  assert.equal(await page.locator('.apartment-shape-layer').getAttribute('data-geometry-basis'),'LAND_PARCEL');
  assert(await page.locator('.apartment-wall').count()>0);assert.equal(await page.locator('.apartment-shadow').count(),shapes);
  assert.equal(await page.locator('.apartment-roof').first().getAttribute('fill-rule'),'evenodd');
  assert((await page.locator('.apartment-roof').first().getAttribute('aria-label')).includes('용지도형'));
  const omission=await page.evaluate(()=>{
   const row={id:'unknown',name:'테스트 S1',district_name:'테스트 공공주택지구',block:'S1',target_units:100,
    progress:{measure:'SUPPLY',observed_units:null,observed_pct:null,cumulative_goal_units:null,verification_count:1},
    projection:{future:[1,2,3].map(offset=>({offset,cumulative_units:null,cumulative_pct:null,increment_units:null}))},future:[],
    milestones:[{label:'인허가',status:'UNKNOWN'},{label:'착공',status:'REPORTED',report_date:'2026-01-01',progress_pct:20}]};
   const div=document.createElement('div');div.innerHTML=BlockMonitor.graph(row);
   const policy=document.createElement('div');policy.innerHTML=SupplyBars.chart(row);
   const mixed=ApartmentShapes.polygons({type:'GeometryCollection',geometries:[{type:'Polygon',coordinates:[[[1,1],[2,1],[2,2],[1,1]],[[1.2,1.2],[1.3,1.2],[1.2,1.3],[1.2,1.2]]]},{type:'MultiLineString',coordinates:[]}]});
   return {text:div.textContent,aria:div.querySelector('svg').getAttribute('aria-label'),current:div.querySelectorAll('.block-current-fill').length,goals:div.querySelectorAll('.block-goal-tick').length,future:div.querySelectorAll('.block-future-value').length,policy:policy.textContent,ratio:policy.querySelectorAll('.bar-ratio').length,stages:BlockMonitor.stageDetails(row),polygons:mixed.length,holes:mixed[0].length};
  });
  assert(!/미확보|일정\?|미확인|—|\+[123]|현재|目標|목표/.test(omission.text));assert(!/미확보|—/.test(omission.aria));
  assert.equal(omission.current,0);assert.equal(omission.goals,0);assert.equal(omission.future,0);assert.equal(omission.ratio,0);
  assert(!/미확보|미확인/.test(omission.policy));assert(!omission.stages.includes('인허가'));assert(omission.stages.includes('착공'));assert.equal(omission.polygons,1);assert.equal(omission.holes,2);
  await page.locator('#housing-map').scrollIntoViewIfNeeded();await page.mouse.move(20,20);
  for(let attempt=0;attempt<40&&await page.locator('.leaflet-tile:not(.leaflet-tile-loaded)').count();attempt++)await page.waitForTimeout(250);
  await page.locator('.housing-map-workspace').screenshot({path:artifact+'/parcel-3d.png'});
  const target=await page.evaluate(()=>{
   const map=document.querySelector('#housing-map').getBoundingClientRect(),panel=document.querySelector('.map-side-panel').getBoundingClientRect();
   for(const roof of document.querySelectorAll('.apartment-roof')){
    const r=roof.getBoundingClientRect();
    for(let y=Math.max(r.top,map.top+90);y<Math.min(r.bottom,map.bottom,innerHeight-20);y+=5)
     for(let x=Math.max(r.left,map.left+15);x<Math.min(r.right,panel.left-15);x+=5)
      if(document.elementFromPoint(x,y)===roof)return {x,y,name:roof.closest('.apartment-parcel').dataset.district};
   }
   return null;
  });
  assert(target,'a real roof must be clickable on the map');
  await page.mouse.click(target.x,target.y);await page.waitForTimeout(600);
  assert((await page.locator('#map-project-detail').textContent()).includes(target.name.replace(/공공주택지구$/,'')));
  await page.locator('.map-layer-menu summary').click();await page.locator('#map-land-layer').uncheck();assert.equal(await page.locator('.apartment-roof').count(),0);
  await page.locator('#map-land-layer').check();assert(await page.locator('.apartment-roof').count()>0);
  await page.locator('.map-layer-menu summary').click();
  await page.locator('[data-bar-level="municipality"]').click();assert.equal(await page.locator('.apartment-roof').count(),0);
  const mobile=await browser.newPage({viewport:{width:390,height:844}});mobile.on('pageerror',e=>errors.push(e.message));
  await mobile.goto(root);await mobile.locator('#content').waitFor({state:'visible'});await mobile.locator('[data-bar-level="block"]').click();await mobile.locator('.apartment-roof').first().waitFor({state:'visible'});
  assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  for(let attempt=0;attempt<40&&await mobile.locator('.leaflet-tile:not(.leaflet-tile-loaded)').count();attempt++)await mobile.waitForTimeout(250);
  await mobile.locator('#housing-map').screenshot({path:artifact+'/mobile-parcel-3d.png'});
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'PASS',visibleShapes:shapes,landParcelBasis:true,roofClick:true,layerToggle:true,unknownValuesOmitted:true,holesPreserved:true,mobileOverflow:false,consoleErrors:0,artifact}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
