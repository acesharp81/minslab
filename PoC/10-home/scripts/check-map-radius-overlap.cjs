const assert=require('node:assert/strict');
const {chromium}=require('/tmp/poc07-playwright/node_modules/playwright');
const base=(process.env.HOME_CHECK_BASE||'http://127.0.0.1:18100')+'/poc/home';
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader']});try{
 const p=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.route('**/assets/map-3d.js*',async route=>{const res=await route.fetch();const body=(await res.text()).replace('return {start,render,focus,','return {inspect:()=>({selectedId,block:selectedBlock(),radii:radiusGeometry(selectedBlock()),source:gl?.getSource("selection-radius")?._data,infra:infraSource}),start,render,focus,');await route.fulfill({response:res,body});});
 const ready=async()=>{for(let i=0;i<100;i++){if(await p.evaluate(()=>MapThreeD.active()))return;await p.waitForTimeout(300);}throw Error('Map did not become active: '+await p.locator('#map-3d-status').textContent());};
 await p.goto(base+'/#manual');await p.locator('#pane-manual [data-view=overview]').first().click();await ready();
 assert.equal(await p.locator('#housing-map-3d canvas').count(),1);
 const options=await p.locator('#map-3d-block-picker option').evaluateAll(ns=>ns.map(n=>({value:n.value,text:n.textContent})));
 const target=options.find(n=>n.text.includes('성남금토')&&n.text.includes('A2'));assert.ok(target);await p.locator('#map-3d-block-picker').selectOption(target.value);await p.waitForTimeout(1500);
 let inspect=await p.evaluate(()=>MapThreeD.inspect());assert.equal(inspect.radii.features.length,3);
 assert.deepEqual(inspect.radii.features.map(f=>f.properties.radius_m),[500,1000,3000]);
 const hav=(a,b)=>{const d=Math.PI/180,x=Math.sin((b[1]-a[1])*d/2)**2+Math.cos(a[1]*d)*Math.cos(b[1]*d)*Math.sin((b[0]-a[0])*d/2)**2;return 6371000*2*Math.asin(Math.sqrt(x));};
 const origin=[inspect.block.longitude,inspect.block.latitude];for(const f of inspect.radii.features)for(const c of f.geometry.coordinates)assert.ok(Math.abs(hav(origin,c)-f.properties.radius_m)<.01);
 const bars=[];
 for(const [name,code,units] of [['성남금토','A2',438],['고양창릉','S3',1282],['고양창릉','S4',1024]]){
  const option=options.find(n=>n.text.includes(name)&&n.text.includes(code));assert.ok(option);await p.locator('#map-3d-block-picker').selectOption(option.value);await p.waitForTimeout(800);
  const block=await p.evaluate(()=>MapThreeD.inspect().block),bar=p.locator('[data-map-bar-block="'+block.id+'"]');
  assert.equal(await bar.count(),1);assert.match(await bar.getAttribute('aria-label'),new RegExp(units.toLocaleString('en-US')+'호'));assert.equal(JSON.parse(await bar.getAttribute('data-map-bar-sources')).length,2);
  for(const id of block.project_ids){await p.evaluate(id=>{const select=document.querySelector('#map-project-select');select.value=id;select.dispatchEvent(new Event('change'));},id);await p.waitForTimeout(200);assert.equal(await bar.count(),1);assert.equal(await bar.getAttribute('aria-pressed'),'true');}
  bars.push({label:await bar.getAttribute('aria-label')});
 }
 await p.locator('#housing-map-3d').screenshot({path:'/tmp/home-map-single-s3-s4.png'});
 await p.locator('#map-3d-block-picker').selectOption(target.value);await p.waitForTimeout(800);
 await p.waitForSelector('.map-facility-plans article',{timeout:90000});assert.match(await p.locator('.map-facility-plans').innerText(),/금토초등학교.*2027-03/s);
 inspect=await p.evaluate(()=>MapThreeD.inspect());assert.ok(inspect.infra.items.some(r=>r.kind==='childcare'));assert.ok(inspect.infra.planned_facilities.some(r=>r.name==='금토초등학교'));
 await p.evaluate(()=>document.querySelector('#map-infrastructure-panel').open=true);
 await p.locator('[data-plan-index="0"]').click();await p.waitForSelector('.maplibregl-popup');assert.match(await p.locator('.maplibregl-popup').innerText(),/개교 예정 2027-03/);await p.locator('.maplibregl-popup-close-button').click();
 await p.evaluate(async()=>{const current=MapThreeD.inspect(),host=document.createElement('div');host.id='facility-check';document.body.append(host);await ProjectLocation.mount(host,{id:current.selectedId,region:'경기도'},{blocks:[current.block]},{compact:true,showUnsold:false});});
 assert.equal(await p.locator('#facility-check [data-location-radius]').inputValue(),'500');assert.match(await p.locator('#facility-check>.pr-card .pjt-planned-facilities').innerText(),/금토초등학교.*2027-03/s);assert.equal(await p.locator('#facility-check .pjt-facility-details .pjt-planned-facilities').count(),0);assert.equal(await p.locator('#facility-check [data-facility-kind=childcare]').count(),1);await p.locator('#facility-check').evaluate(n=>n.remove());
 await p.locator('#map-3d-block-picker').selectOption(target.value);await p.waitForTimeout(900);
 await p.locator('#housing-map-3d').screenshot({path:'/tmp/home-map-separated-bars.png'});
 await p.locator('[data-map-radius-fit]').click();await p.waitForTimeout(1000);for(const label of ['500m','1km','3km']){const node=p.locator('.map-radius-label').filter({hasText:label}).first();assert.ok(await node.isVisible());}
 await p.locator('#housing-map-3d').screenshot({path:'/tmp/home-map-radius.png'});
 const approximate=options.find(n=>n.text.includes('광주역세권'));assert.ok(approximate);await p.locator('#map-3d-block-picker').selectOption(approximate.value);await p.waitForTimeout(1000);assert.equal((await p.evaluate(()=>MapThreeD.inspect())).block.id,approximate.value);
 // Interrupt initialization and return through the feature navigation.
 for(let i=0;i<3;i++){await p.evaluate(()=>{setView('manual');setView('overview');setView('manual');});await p.waitForTimeout(30);await p.evaluate(()=>setView('overview'));await ready();assert.equal(await p.locator('#housing-map-3d canvas').count(),1);}
 await p.setViewportSize({width:1250,height:850});await p.waitForTimeout(500);const size=await p.locator('#housing-map-3d').evaluate(n=>({w:n.clientWidth,h:n.clientHeight,cw:n.querySelector('canvas').clientWidth,ch:n.querySelector('canvas').clientHeight}));assert.equal(size.w,size.cw);assert.equal(size.h,size.ch);
 assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,individualBars:bars.map(r=>r.label),rings:[500,1000,3000],childcare:true,openingPlans:true,navigation:true,resize:size,errors}));
 }finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
