const assert=require('node:assert/strict'),{chromium}=require('/tmp/poc07-playwright/node_modules/playwright');
(async()=>{const b=await chromium.launch({headless:true,executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader']});try{
 const p=await b.newPage({viewport:{width:1600,height:1100}}),errors=[];p.on('pageerror',e=>errors.push(e.message));const base=(process.env.HOME_CHECK_BASE||'http://127.0.0.1:18100')+'/poc/home';
 await p.goto(base+'/#requirements');await p.waitForSelector('#requirement-F-02 .req-data-score progress',{timeout:90000});
 assert.equal(await p.locator('.req-data-score').count(),24);const metrics=await p.evaluate(async()=>await (await fetch('/poc/home/api/requirements-status')).json());
 for(const v of Object.values(metrics.metrics)){assert.equal(v.with_estimates.total,v.without_estimates.total);assert.ok(v.with_estimates.count>=v.without_estimates.count);}
 await p.locator('#requirement-F-02').screenshot({path:'/tmp/requirements-split.png'});
 const download=p.waitForEvent('download');await p.locator('#requirements-export').click();const d=await download;await d.saveAs('/tmp/requirements-split.csv');assert.match(require('node:fs').readFileSync('/tmp/requirements-split.csv','utf8'),/추정제외 확보율/);
 await p.goto(base+'/#policy-progress');await p.waitForSelector('.d907-chart',{timeout:90000});await p.locator('[data-d907-chart-position=now]').click();
 const graph=await p.evaluate(()=>{const svg=document.querySelector('.d907-chart'),flow=svg.closest('.d907-flow'),s=svg.closest('.pw-flow-chart'),line=svg.querySelector('[data-d907-now-line]'),boxes=[...svg.querySelectorAll('[data-d907-callout-box]')].map(n=>({x:+n.getAttribute('x'),y:+n.getAttribute('y'),h:+n.getAttribute('height')}));return {height:svg.getBoundingClientRect().height,canvas:svg.viewBox.baseVal.height,scaleY:svg.getScreenCTM().d,center:line.getBoundingClientRect().x-s.getBoundingClientRect().x-s.clientWidth/2,boxes,shortages:[...flow.querySelectorAll('.d907-stage-gap.is-short')].length,callouts:svg.querySelectorAll('[data-d907-gap-callout]').length,curves:[...svg.querySelectorAll('[data-d907-actual-line]')].some(n=>n.getAttribute('d').includes('C')),legendBelow:flow.querySelector('.d907-pattern-legend').getBoundingClientRect().top>svg.getBoundingClientRect().bottom};});
 assert.equal(graph.height,450);assert.equal(graph.canvas,435);assert.ok(graph.scaleY<1.1);assert.ok(Math.abs(graph.center)<2);assert.ok(graph.curves);assert.ok(graph.legendBelow);assert.equal(graph.callouts,graph.shortages);for(let i=1;i<graph.boxes.length;i++)assert.ok(graph.boxes[i].y>=graph.boxes[i-1].y+graph.boxes[i-1].h);
 await p.locator('.d907-flow').screenshot({path:'/tmp/curves-all-gaps.png'});
 await p.goto(base+'/#overview');await p.waitForSelector('#map-policy-monitor .map-compact-stages',{timeout:90000});await p.waitForSelector('#map-area-context .pac-card',{timeout:90000});
 assert.equal(await p.locator('#map-policy-monitor .map-compact-stages>div').count(),6);assert.equal(await p.locator('#map-area-context .pac-card').count(),4);
 assert.ok(await p.locator('#map-area-context .pac-national').count()>0);assert.ok(await p.locator('#map-area-context .pac-benchmark-key').count()>0);
 assert.ok(await p.locator('#map-policy-monitor .map-compact-stages').isVisible());
 await p.locator('#map-policy-monitor').screenshot({path:'/tmp/map-progress-shared.png'});await p.locator('#map-area-context').screenshot({path:'/tmp/map-area-shared.png'});
 const option=await p.locator('[data-map-progress-program] option').nth(1).getAttribute('value');
 const switched=p.waitForResponse(r=>r.url().includes('/api/map/progress?')&&r.url().includes('program_id='));
 await p.locator('[data-map-progress-program]').selectOption(option);const selectionData=await (await switched).json();assert.ok(selectionData.project_count>0);await p.waitForSelector('#map-policy-monitor .map-compact-stages',{timeout:90000});
 await p.locator('[data-map-flow-now]').click();
 await p.goto(base+'/#program-progress');await p.waitForSelector('#program-progress-detail .d907-chart',{timeout:90000});assert.equal(await p.locator('#program-progress-detail .d907-stage-value').count(),6);
 await p.setViewportSize({width:390,height:844});await p.goto(base+'/#requirements');await p.waitForSelector('.req-data-score');assert.equal(await p.locator('.req-data-score').count(),24);
 assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,graph,metrics:Object.fromEntries(Object.entries(metrics.metrics).map(([k,v])=>[k,{without:v.without_estimates.percent,with:v.with_estimates.percent,counts:[v.without_estimates.count,v.with_estimates.count],total:v.total}])),errors}));
}finally{await b.close()}})().catch(e=>{console.error(e);process.exit(1)});
