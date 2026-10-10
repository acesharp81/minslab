/* Read-only verification against HOME. Never sends API keys or mutates production data. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const root=process.env.HOME_CHECK_URL||'https://www.minslab.kr/poc/home/';
const artifact='/tmp/home-additional-api-check';
fs.mkdirSync(artifact,{recursive:true});
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.HOME_CHECK_CHROME||undefined,args:['--no-sandbox']});
  try{
    const page=await browser.newPage({viewport:{width:1600,height:1100}}),errors=[];
    page.setDefaultTimeout(45000);
    page.on('pageerror',e=>errors.push(e.message));
    page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
    await page.goto(root);await page.locator('#content').waitFor({state:'visible'});
    const fetchJSON=async path=>{const r=await page.request.get(new URL('api/'+path,root).href);assert.equal(r.status(),200);return r.json();};
    const sources=(await fetchJSON('sources')).items;
    const expected={building_register:320,lh_notice:3050,molit_statistics:432};
    for(const [id,count] of Object.entries(expected)){
      const source=sources.find(s=>s.id===id);
      assert.equal(source.status,'SUCCESS');assert.equal(source.record_count,count);assert(source.key_configured);
      assert(source.snapshots.every(s=>s.url.includes('/api/period.do')||s.credentials_removed));
      for(const snapshot of source.snapshots)assert(!/[?&](key|serviceKey)=/i.test(snapshot.url));
    }
    const connections=await fetchJSON('connections');
    assert.equal(connections.connected.length,8);
    for(const id of Object.keys(expected))assert.equal(connections.planned.find(g=>g.id===id).readiness,'CONNECTED');
    const monitor=await fetchJSON('policy-monitor');assert.equal(monitor.project_count,150);assert.equal(monitor.confirmed_count,0);
    await page.locator('.nav-item[data-view="keys"]').click();
    assert.equal(await page.locator('.connection-plan').filter({hasText:'연결 확인'}).count(),5);
    assert(!(await page.locator('#connection-guide').textContent()).includes('HTTP 403'));
    await page.locator('#pane-keys').screenshot({path:artifact+'/connections.png'});
    await page.locator('.nav-item[data-view="samples"]').click();
    const reload=async action=>{await Promise.all([page.waitForResponse(r=>r.url().includes('/api/samples?')&&r.ok()),action()]);await page.locator('#loading').waitFor({state:'hidden'});};
    for(const [kind,count] of [['register',320],['lh_notice',3050],['statistic',432]]){
      await reload(()=>page.locator('#sample-kind').selectOption(kind));
      assert((await page.locator('#sample-total').textContent()).includes(count.toLocaleString('ko-KR')));
    }
    await reload(()=>page.locator('#sample-year').selectOption('2018'));
    assert.match(await page.locator('#sample-total').textContent(),/50건/);
    const stats=await fetchJSON('samples?kind=statistic&source_year=2018');
    assert.equal(stats.total,50);assert(stats.items.every(r=>r.source_date.startsWith('2018')));
    assert(stats.items.every(r=>r.unit_basis.includes('직접 합산 제외')));
    assert(stats.items.every(r=>!('cert_id' in r)));
    const href=await page.locator('#sample-export').getAttribute('href');assert.match(href,/source_year=2018/);
    const csv=await page.request.get(new URL(href,root).href);assert.equal(csv.status(),200);
    const bytes=await csv.body();assert.equal(bytes.subarray(0,3).toString('hex'),'efbbbf');
    assert(bytes.toString().includes('statistic_frequency'));assert(bytes.toString().includes('201801'));
    await page.locator('#sample-list [data-sample]').first().click();
    await page.locator('#detail-content').filter({hasText:'통계 대상 기간'}).waitFor();
    assert.match(await page.locator('#detail-content').textContent(),/통계 대상 기간/);
    assert.match(await page.locator('#detail-content').textContent(),/민간 포함/);
    await page.locator('#detail-dialog').screenshot({path:artifact+'/statistics-evidence.png'});
    await page.locator('#detail-dialog').evaluate(d=>d.close());
    await reload(()=>page.locator('#sample-kind').selectOption('lh_notice'));
    assert.match(await page.locator('#sample-total').textContent(),/370건/);
    assert.match(await page.locator('#sample-list').textContent(),/2018/);
    await page.locator('#pane-samples').screenshot({path:artifact+'/lh-history-2018.png'});
    assert.deepEqual(errors,[]);
    const mobile=await browser.newPage({viewport:{width:390,height:844}});
    mobile.on('pageerror',e=>errors.push(e.message));
    await mobile.goto(root+'#samples');await mobile.locator('#content').waitFor({state:'visible'});
    assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({status:'PASS',mode:'PUBLIC_READONLY',sources:expected,totalSamples:8870,statistics2018:50,lhNotices2018:370,consoleErrors:0,mobileOverflow:false,artifact}));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
