/* Read-only SH collection, historic versions, evidence dialog and CSV verification. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const root=process.env.HOME_CHECK_URL||'https://www.minslab.kr/poc/home/';
const artifact='/tmp/home-sh-api-check';fs.mkdirSync(artifact,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.HOME_CHECK_CHROME||undefined,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1100}}),errors=[];
  page.setDefaultTimeout(45000);page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await page.goto(root);await page.locator('#content').waitFor({state:'visible'});
  const get=async path=>{const r=await page.request.get(new URL('api/'+path,root).href);assert.equal(r.status(),200);return r.json();};
  const sources=(await get('sources')).items;
  for(const [id,count] of [['sh_supply_plan',20],['sh_redevelopment',16]]){
   const s=sources.find(s=>s.id===id);assert.equal(s.status,'SUCCESS');assert.equal(s.record_count,count);assert(s.key_configured);
   assert(s.snapshots.every(s=>!/[?&](key|serviceKey)=/i.test(s.url)));
  }
  const plans=await get('samples?kind=sh_plan');assert.equal(plans.total,20);assert.deepEqual(plans.source_years,[2026,2023,2020,2019]);
  const current=plans.items.filter(r=>r.is_latest_dataset);assert.equal(current.length,4);
  assert.equal(current.reduce((sum,r)=>sum+r.units,0),1686);
  assert(current.every(r=>r.units===r.pre_subscription_units+r.main_subscription_units));
  const projects=await get('samples?kind=sh_project');assert.equal(projects.total,16);
  assert(projects.items.every(r=>r.source_date==='2023-11-02'&&r.warnings.includes('SH_OLD_STATUS')));
  assert(projects.items.every(r=>r.policy_mapping_status==='UNMAPPED'));
  const monitor=await get('policy-monitor');assert.equal(monitor.project_count,150);assert.equal(monitor.confirmed_count,0);
  const connections=await get('connections');assert.equal(connections.connected.length,8);
  for(const id of ['sh_supply_plan','sh_redevelopment'])assert.equal(connections.planned.find(g=>g.id===id).readiness,'CONNECTED');
  await page.locator('.nav-item[data-view="keys"]').click();
  const sh=page.locator('.connection-plan').filter({hasText:'SH 주택분양 공급계획'});assert.match(await sh.textContent(),/2019-08-26/);assert.match(await sh.textContent(),/2026-06-22/);
  await page.locator('#pane-keys').screenshot({path:artifact+'/connections.png'});
  await page.locator('.nav-item[data-view="samples"]').click();
  const reload=async action=>{await Promise.all([page.waitForResponse(r=>r.url().includes('/api/samples?')&&r.ok()),action()]);await page.locator('#loading').waitFor({state:'hidden'});};
  await reload(()=>page.locator('#sample-kind').selectOption('sh_plan'));
  assert.match(await page.locator('#sample-total').textContent(),/20건/);
  await reload(()=>page.locator('#sample-year').selectOption('2026'));
  assert.match(await page.locator('#sample-total').textContent(),/4건/);
  await page.locator('#sample-list [data-sample]').first().click();
  await page.locator('#detail-content').filter({hasText:'사전청약 공급세대수'}).waitFor();
  assert.match(await page.locator('#detail-content').textContent(),/공급 예정월/);
  await page.locator('#detail-dialog').screenshot({path:artifact+'/plan-evidence.png'});
  await page.locator('#detail-dialog').evaluate(d=>d.close());
  await reload(()=>page.locator('#sample-year').selectOption('2019'));assert.match(await page.locator('#sample-total').textContent(),/6건/);
  const csv=await page.request.get(new URL(await page.locator('#sample-export').getAttribute('href'),root).href);
  assert.equal(csv.status(),200);const bytes=await csv.body();assert.equal(bytes.subarray(0,3).toString('hex'),'efbbbf');
  assert(bytes.toString().includes('native_fields'));assert(bytes.toString().includes('2019-08-26'));assert(bytes.toString().includes('2015-05'));
  await reload(()=>page.locator('#sample-year').selectOption(''));
  await reload(()=>page.locator('#sample-kind').selectOption('sh_project'));assert.match(await page.locator('#sample-total').textContent(),/16건/);
  await page.locator('#sample-list [data-sample]').first().click();
  await page.locator('#detail-content').filter({hasText:'원천 추진현황'}).waitFor();assert.match(await page.locator('#detail-content').textContent(),/2023-11-02/);
  assert.match(await page.locator('#detail-content').textContent(),/현재 상태 확인 필요/);
  await page.locator('#detail-dialog').screenshot({path:artifact+'/redevelopment-evidence.png'});
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'PASS',sources:{sh_supply_plan:20,sh_redevelopment:16},latestPlanRows:4,latestPlannedUnits:1686,policyProjects:150,consoleErrors:0,artifact}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
