/* Verify the standalone report, including quantities, scope and offline use. */
const {chromium}=require('/tmp/poc07-playwright/node_modules/playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const evidence=path.join(root,'docs/evidence/HOME_PROJECT_COMPARISON_20261018');
const target=process.argv[2]||'file://'+path.join(root,'docs/HOME_OFFICIAL_PROJECT_COMPARISON_20261018.html');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1480,height:1000},acceptDownloads:true});
  const errors=[],requests=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.url()!==target)requests.push(r.url());});
  await page.goto(target,{waitUntil:'load'});
  const data=await page.locator('#comparison-data').textContent().then(JSON.parse);
  const view=()=>page.evaluate(()=>window.comparisonView);
  let v=await view();
  assert.equal(v.source_records,208);assert.equal(v.mentioned_records+v.unmentioned_records,208);
  assert.equal(await page.locator('tr.case').count(),16);
  assert.equal(new Set(data.groups.flatMap(g=>g.records.map(r=>r.id))).size,323);
  const row=id=>v.visible_cases.find(c=>c.id===id);
  assert.equal(row('S01').value,2306);assert.equal(row('S01').difference,6);
  assert.equal(row('S02').value,463);assert.equal(row('S02').difference,-1837);
  assert.equal(row('S03').value,null);assert.equal(row('S04').value,null);
  assert.equal(row('S04').difference,null);
  assert.equal(row('S05').value,null);assert.equal(row('S06').value,null);assert.equal(row('S07').value,null);
  if(data.estimate_update?.projects){
   assert.equal(data.estimate_update.projects,11);assert.equal(data.estimate_update.target_count,66);
   assert.equal(data.estimate_update.measurement_count,24);
   assert.equal(row('S05').estimate.value,3178);assert.equal(row('S05').estimate.difference,78);
   assert.ok(row('S05').estimate.eligible.every(r=>r.inferred&&r.date==='2026-08-15'));
   const added=data.groups.flatMap(g=>g.records).filter(r=>data.estimate_update.source_project_ids.includes(r.id));
   assert.equal(added.length,11);assert.ok(added.every(r=>Object.keys(r.managed_schedules).length===6));
   assert.ok(added.every(r=>Object.values(r.officer_progress).every(v=>v.inferred&&v.actor==='김민')));
   assert.equal(added.find(r=>r.name.includes('AA10')).managed_units,1458);
   assert.equal(await page.locator('thead th').count(),7);
  }
  assert.equal(row('S08').value,null);assert.equal(row('S09').value,null);
  assert.equal(row('S10').value,379);assert.equal(row('S10').difference,-21);
  assert.equal(row('S11').value,null);assert.equal(row('S12').value,null);
  assert.equal(row('S13').value,1424);assert.equal(row('S13').difference,24);
  assert.ok(row('S15').eligible.some(p=>p.due_date==='2027-12'));
  assert.ok(row('S16').eligible.some(p=>p.due_date.startsWith('2027-11')));
  assert.ok(data.cases.every(c=>c.comparable===false&&c.numeric_gap===null));
  const wangGroups=data.groups.filter(g=>g.official_areas.includes('남양주왕숙2'));
  assert.ok(wangGroups.every(g=>!g.official_areas.includes('남양주왕숙')));
  const starts=wangGroups.flatMap(g=>g.records).filter(r=>r.construction_start_evidence?.event_date==='2025-12-31');
  assert.equal(starts.reduce((n,r)=>n+r.construction_start_evidence.units,0),1498);
  assert.equal(wangGroups.flatMap(g=>g.events).filter(e=>e.event_type==='RECRUITMENT_PUBLISHED').reduce((n,e)=>n+e.quantity,0),1498);
  const ih=data.groups.filter(g=>g.records.some(r=>r.source_id==='ih_notice'));
  assert.equal(ih.length,7);assert.ok(ih.every(g=>!g.official_areas.length));
  assert.ok(ih.some(g=>g.records.some(r=>r.name.includes('S3')&&r.planned_units===749)));
  assert.ok(ih.some(g=>g.records.some(r=>r.name.includes('AA10')&&r.planned_units===null)));
  await page.screenshot({path:path.join(evidence,'desktop.png')});
  await page.locator('#search').fill('왕숙2');await page.waitForTimeout(200);
  assert.deepEqual((await view()).visible_cases.map(c=>c.id),['S04']);
  await page.locator('tr.detailrow details').first().locator('summary').first().click();
  assert.ok((await page.locator('tr.detailrow').first().textContent()).includes('812호'));
  await page.locator('#reset').click();await page.locator('#scope').selectOption('ALL');
  v=await view();assert.equal(v.source_records,322);assert.equal(v.mentioned_records+v.unmentioned_records,322);
  await page.locator('#search').fill('iH');await page.waitForTimeout(200);
  assert.equal((await view()).unmentioned_groups.length,7);
  const downloadPromise=page.waitForEvent('download');await page.locator('#download').click();
  const download=await downloadPromise;assert.equal(download.suggestedFilename(),'HOME_OFFICIAL_PROJECT_COMPARISON_20261018.json');
  await page.locator('#reset').click();await page.locator('#stage').selectOption('CONSTRUCTION');
  assert.equal(await page.locator('tr.case').count(),7);
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(evidence,'mobile.png')});
  assert.deepEqual(errors,[]);assert.deepEqual(requests.filter(u=>!u.startsWith('blob:')),[]);
  const report={target,known_at:data.known_at,source_records:323,default_policy_records:208,all_active_records:322,
   mentioned_records_default:(await page.evaluate(()=>groupsFor(D.default_policy).filter(g=>g.official_areas.length).reduce((n,g)=>n+g.records.length,0))),
   unmentioned_records_default:208-(await page.evaluate(()=>groupsFor(D.default_policy).filter(g=>g.official_areas.length).reduce((n,g)=>n+g.records.length,0))),
   ih_unmentioned_groups:7,official_cases:16,official_areas:12,wangsuk2_period_and_event_separation:'PASS',
   direct_events_and_source_plans:'PASS',estimates_separate:data.estimate_update?.projects?'PASS':'NOT_APPLIED',
   missing_is_not_zero:'PASS',scope_filters:'PASS',mobile:'PASS',download:'PASS',offline:'PASS',errors};
  fs.writeFileSync(path.join(evidence,target.startsWith('http')?'public-browser.json':'browser.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
