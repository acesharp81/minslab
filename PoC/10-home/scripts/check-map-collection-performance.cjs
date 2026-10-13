/* Read-only browser regression: scoped requests, map controls, and menu navigation. */
const assert=require('node:assert/strict');
const {chromium}=require('/tmp/poc07-playwright/node_modules/playwright');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',args:['--no-sandbox','--enable-webgl','--use-gl=angle','--use-angle=swiftshader']});
  const base=process.env.HOME_CHECK_BASE||'http://127.0.0.1:18101',results=[];
  try{
    for(const view of ['overview','project-collection']){
      const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],requests=[];
      page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.url().includes('/api/'))requests.push(r.url());});
      const start=Date.now();await page.goto(base+'/poc/home/#'+view);
      await page.waitForSelector(view==='overview'?'#map-supply-table tbody tr':'#pc-table [data-pc-cell]',{state:'attached',timeout:60000});
      const readyMs=Date.now()-start;
      assert.equal(await page.locator('#content').evaluate(n=>n.hidden),false);
      assert(!requests.some(u=>/\/api\/(samples|overview|history|identities|identity-options|mappings|policy-monitor|validation|tree)\?/.test(u)));
      assert.equal(requests.filter(u=>u.includes('/api/project-collection?')).length,view==='project-collection'?1:0);
      assert.equal(requests.filter(u=>u.includes('/api/map/dashboard?')).length,view==='overview'?1:0);
      if(view==='overview'){
        assert(requests.some(u=>u.includes('compact=true')));
        await page.waitForSelector('.map-scene-block,.map-scene-region,.map-scene-municipality',{timeout:45000});
        for(const measure of ['COMPLETION','SUPPLY']){
          const response=page.waitForResponse(r=>r.url().includes('/api/map/dashboard?')&&r.url().includes('measure='+measure));
          await page.locator('#map-measure').selectOption(measure);
          const r=await response;assert.equal(r.status(),200);assert.equal((await r.json()).measure,measure);
        }
        // Region map buttons update this hidden shared filter and dispatch change.
        const [response]=await Promise.all([
          page.waitForResponse(r=>r.url().includes('/api/map/dashboard?')&&decodeURIComponent(r.url()).includes('region=인천광역시')),
          page.evaluate(()=>{$('region').value='인천광역시';$('region').dispatchEvent(new Event('change'));})]);
        const data=await response.json();assert(data.items.length>0);assert(data.items.every(p=>p.region==='인천광역시'));
        await page.evaluate(()=>setView('project-collection'));
        await page.waitForSelector('#pc-table [data-pc-cell]',{timeout:45000});
        await page.evaluate(()=>setView('policy-progress'));
        await page.waitForSelector('#policy-report-detail .d907-chart',{timeout:60000});
        assert.equal(await page.locator('#report-policy-select').inputValue(),'POL_2025_0907');
        await page.evaluate(()=>setView('overview'));
        await page.waitForSelector('.map-scene-block,.map-scene-region,.map-scene-municipality',{timeout:45000});
      }else{
        await page.locator('#pc-search').fill('고양창릉 S-02');
        assert.match(await page.locator('#pc-table').innerText(),/고양창릉 S-02/);
        const response=page.waitForResponse(r=>r.url().includes('/api/project-collection?'));
        await page.evaluate(()=>setView('manual'));await page.evaluate(()=>setView('project-collection'));
        assert.equal((await response).status(),200);
        assert.equal(await page.locator('#pc-search').inputValue(),'고양창릉 S-02');
        await page.setViewportSize({width:390,height:844});
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
      }
      assert.deepEqual(errors,[]);results.push({view,readyMs,errors});await page.close();
    }
    console.log(JSON.stringify({passed:true,results}));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
