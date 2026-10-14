const {chromium}=require('/tmp/poc07-playwright/node_modules/playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader']});try{
 const p=await browser.newPage({viewport:{width:1800,height:1050}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.route('**/assets/map-3d.js*',async route=>{const response=await route.fetch();await route.fulfill({response,body:(await response.text()).replace('return {start,render,focus,','return {inspectModels:()=>({models:modelFeatures,selected:selectedBlock(),source:gl?.getSource("simulated-apartments")?._data}),start,render,focus,')});});
 await p.goto('https://www.minslab.kr/poc/home/#manual');await p.locator('#pane-manual [data-view=overview]').first().click();await p.waitForSelector('#map-3d-block-picker option[value]:not([value=""])',{state:'attached',timeout:90000});
 const options=await p.locator('#map-3d-block-picker option').evaluateAll(ns=>ns.map(n=>({id:n.value,text:n.textContent})));const chosen=options.find(n=>n.text.includes('마곡')&&n.text.includes('17'));assert.ok(chosen,JSON.stringify(options.filter(n=>n.text.includes('마곡'))));
 await p.locator('#map-3d-block-picker').selectOption(chosen.id);await p.waitForSelector('.map-3d-block-marker.selected',{timeout:90000});await p.waitForTimeout(3000);
 const state=await p.evaluate(()=>MapThreeD.inspectModels());assert.equal(state.selected.id,chosen.id);assert.ok(state.models.length>0);
 const groups=new Map();for(const f of state.models){const props=f.properties;if(!groups.has(props.block_id))groups.set(props.block_id,[]);groups.get(props.block_id).push(props);}
 for(const rows of groups.values()){const units=rows[0].target_units;assert.equal(rows.length,Math.ceil(units/200));assert.ok(Math.abs(rows.reduce((s,r)=>s+r.represented_units,0)-units)<1e-6);assert.ok(Math.abs(rows.reduce((s,r)=>s+r.render_height_m,0)-units*3/8)<1e-6);}
 const source=state.source.geojson||state.source;assert.equal(source.features.length,state.models.length);assert.match(await p.locator('#map-3d-legend').textContent(),/200호당 1동/);
 const selected=groups.get(chosen.id);assert.equal(selected.length,2);assert.equal(selected[0].target_units,381);
 await p.locator('[data-map-3d-camera=north]').click();await p.waitForTimeout(700);const after=await p.evaluate(()=>MapThreeD.inspectModels().models);assert.equal(JSON.stringify(after),JSON.stringify(state.models));
 await p.locator('#housing-map-3d').screenshot({path:'/tmp/home-map-proportional-model.png'});assert.deepEqual(errors,[]);
 console.log(JSON.stringify({passed:true,blocks:groups.size,modelCount:state.models.length,selected:chosen.text,units:selected[0].target_units,masses:selected.length,height:selected[0].render_height_m,errors}));
 }finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
