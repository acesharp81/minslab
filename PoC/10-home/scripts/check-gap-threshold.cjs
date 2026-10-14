const assert=require('node:assert/strict'),{chromium}=require('/tmp/poc07-playwright/node_modules/playwright');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader']});try{
 const p=await browser.newPage({viewport:{width:1720,height:1100}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.goto('https://www.minslab.kr/poc/home/#policy-progress');
 await p.locator('#policy-report-detail [data-d907-gap-callout="BUSINESS"]').waitFor({timeout:90000});
 await p.waitForTimeout(1000);
 const labels=await p.locator('#policy-report-detail [data-d907-gap-callout]').evaluateAll(ns=>ns.map(n=>({stage:n.dataset.d907GapCallout,status:n.dataset.gapStatus,text:n.textContent,fill:n.querySelector('rect').getAttribute('fill')})));
 assert.equal(labels.find(n=>n.stage==='BUSINESS').status,'DELAYED');
 for(const stage of ['APPROVAL','SUPPLY'])assert.equal(labels.find(n=>n.stage===stage).status,'WARNING');
 for(const n of labels)assert.equal(n.fill,n.status==='WARNING'?'#e8ad25':'#b51f38');
 const legend=await p.locator('#policy-report-detail .d907-pattern-legend').innerText();assert.match(legend,/노란 격자/);assert.doesNotMatch(legend,/지연 검토/);
 const trend=await p.locator('#policy-report-detail .pd-stat-grid article').nth(1).innerText();assert.doesNotMatch(trend,/확인 필요/);assert.match(trend,/주의/);assert.match(trend,/2% 이상/);
 await p.locator('#policy-report-detail .pw-flow-chart').screenshot({path:'/tmp/home-gap-threshold-policy.png'});
 const fixtures=await p.evaluate(()=>{
  const cell=units=>ProjectCollection.cellContent({management:{target:[{milestone:'SUPPLY',date:'2026-09-30',units:1000}],measurement:[{milestone:'SUPPLY',date:'2026-09-30',units}],remaining:[]}},'SUPPLY');
  return {warning:cell(981),delay:cell(980),missing:cell(null),map:MapProgressTracking.checks({as_of_date:'2026-10-14',stages:{SUPPLY:'공급'},comparisons:{SUPPLY:{target_points:[{date:'2026-09-30',units:1000}],actual_points:[{date:'2026-09-30',units:981}]}},delays:[]}).find(c=>c.stage==='SUPPLY').status};
 });assert.match(fixtures.warning,/data-management-status="WARNING"/);assert.match(fixtures.delay,/data-management-status="DELAYED"/);assert.doesNotMatch(fixtures.missing,/gap-management/);assert.equal(fixtures.map,'WARNING');
 await p.evaluate(()=>setView('program-progress'));await p.locator('#program-progress-detail .pd-stat-grid').waitFor({timeout:90000});await p.waitForTimeout(1800);
 assert.doesNotMatch(await p.locator('#program-progress-detail .pd-stat-grid article').nth(1).innerText(),/확인 필요/);
 assert.equal(await p.locator('#program-progress-detail .pd-stat-grid article').count(),6);
 await p.setViewportSize({width:390,height:844});await p.waitForTimeout(300);assert.ok(await p.locator('#program-progress-detail .pd-stat-grid').evaluate(n=>n.scrollWidth<=n.clientWidth+1));
 assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,labels,projectAndMapRule:true,trendSeries:['DELAYED','WARNING'],errors}));
 }finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
