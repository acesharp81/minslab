// Browser regression: refresh, retry, cache expiry and 3D resource reuse.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const base=process.env.KJON_BASE||'http://127.0.0.1:18070';
(async()=>{const b=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH || undefined,args:['--no-sandbox','--enable-webgl','--use-gl=angle','--use-angle=swiftshader']});try{
 const p=await b.newPage({viewport:{width:1440,height:1000}});const errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.addInitScript(()=>{window.__timeOffset=0;const now=Date.now.bind(Date);Date.now=()=>now()+window.__timeOffset});
 const original=await (await fetch(base+'/api/policy/ontology')).json();let calls=0;
 await p.route('**/api/policy/ontology',async route=>{calls++;if(calls===3)return route.fulfill({status:503,body:'{}'});const data=structuredClone(original);data.metrics.semantic_reviewed_topic_count=700+calls;data.groups[0].topic_count=900+calls;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)})});
 await p.goto(base+'/#extras');await p.locator('#assemblyOntologyOpen').click();await p.locator('#assemblyOntologyCanvas[data-renderer=three]').waitFor({timeout:45000});
 assert.match(await p.locator('#assemblyOntologyDetail').innerText(),/701건/);
 await p.locator('#assemblyOntologyRefresh').click();await p.getByText(/저장된 AI 의미 검토 702건/).waitFor();await p.locator('#assemblyOntologyCanvas[data-renderer=three]').waitFor();assert.equal(calls,2);
 await p.locator('#assemblyOntologyRefresh').click();await p.getByRole('button',{name:'다시 시도',exact:true}).waitFor();await p.getByRole('button',{name:'다시 시도',exact:true}).click();await p.getByText(/저장된 AI 의미 검토 704건/).waitFor();await p.locator('#assemblyOntologyCanvas[data-renderer=three]').waitFor();
 await p.locator('#assemblyOntologyClose').click();await p.locator('#assemblyOntologyOpen').click();assert.equal(calls,4);
 await p.locator('#assemblyOntologyClose').click();await p.evaluate(()=>window.__timeOffset=61000);await p.locator('#assemblyOntologyOpen').click();await p.getByText(/저장된 AI 의미 검토 705건/).waitFor();await p.locator('#assemblyOntologyCanvas[data-renderer=three]').waitFor();assert.equal(calls,5);
 await p.locator('#assemblyOntologyLegend button').first().click();await p.locator('#assemblyOntologyDetail .assembly-ontology-keywords button').filter({hasText:original.groups[0].title}).click();assert.ok((await p.locator('#assemblyOntologyDetail').innerText()).includes('905'));
 await p.setViewportSize({width:390,height:844});const box=await p.locator('#assemblyOntologyRefresh').boundingBox();assert.ok(box.x>=0&&box.x+box.width<=390&&box.y+box.height<=844);assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));if(process.env.ONTOLOGY_SCREENSHOT)await p.screenshot({path:process.env.ONTOLOGY_SCREENSHOT});
 assert.equal(await p.locator('#assemblyOntologyCanvas').count(),1);assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,base,refresh:true,refresh_failure_retry:true,cache_within_minute:true,reopen_after_minute:true,updated_3d_node:true,mobile:true,requests:calls,errors}));
}finally{await b.close()}})().catch(e=>{console.error(e);process.exit(1)});
