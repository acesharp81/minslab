/* Read-only live audit: counts, bounded scope, GH archives and policy attachment plans. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const root=process.env.HOME_CHECK_URL||'https://www.minslab.kr/poc/home/';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.HOME_CHECK_CHROME||undefined,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1100}}),errors=[];
  page.setDefaultTimeout(60000);page.on('pageerror',e=>errors.push(e.message));
  await page.goto(root+'#validation');await page.locator('#content').waitFor({state:'visible'});
  async function api(path){const r=await page.request.get(root+'api/'+path);assert.equal(r.status(),200,path);return r.json();}
  const [validation,sources,overview,monitor,gh]=await Promise.all([api('validation'),api('sources'),api('overview'),api('policy-monitor'),api('samples?kind=gh_notice')]);
  assert.equal(validation.coverage.complete_population,false);
  assert.equal(await page.locator('#coverage-list tbody tr').count(),sources.items.length);
  assert((await page.locator('#coverage-note').textContent()).includes('전체 페이지'));
  const register=validation.coverage.items.find(r=>r.source_id==='building_register');
  assert.equal(register.query_status,'PARTIAL');assert.equal(register.provided_records,register.fetched_records);
  assert(register.collected_records>320);assert(register.scope.includes('공식 법정동'));assert(register.scope.includes('2,629'));assert.equal(register.complete_population,false);
  const urban=sources.items.find(r=>r.id==='urban_930');assert.equal(urban.stats.missing_candidate_names,0);assert.equal(urban.stats.progress_list_in_scope,40);
  const stock=await api('samples?kind=agency_stock');assert.equal(stock.total,2385);
  const stockSource=sources.items.find(r=>r.id==='sh_files');assert.equal(stockSource.record_count,2364);
  const connections=await api('connections');assert(connections.planned.filter(r=>['sh_files','gh_files'].includes(r.id)).every(r=>r.readiness==='CONNECTED'));
  const codes=await api('samples?kind=legal_dong');assert.equal(codes.total,2629);
  const stockCsv=await page.request.get(root+'api/samples/export.csv?kind=agency_stock&source_year=2026');assert.equal(stockCsv.status(),200);assert((await stockCsv.text()).includes('agency_stock'));
  const ghSource=sources.items.find(r=>r.id==='gh_notice');
  assert.equal(ghSource.stats.provided,ghSource.stats.fetched);assert.equal(gh.total,ghSource.stats.collected);
  assert(gh.total>0);assert(gh.items.every(r=>r.units==null));
  const sh=await api('projects?source_id=sh_inventory&page_size=200');
  assert(sh.items.length>0);assert(sh.items.every(r=>r.mapping.status==='REVIEW'&&r.mapping.policy_id==='UNASSIGNED'));
  assert.equal(sh.items.filter(r=>r.source_dataset==='sh_supply_plan').length,2);
  assert.equal(sh.items.filter(r=>r.source_dataset==='sh_supply_plan').reduce((n,r)=>n+r.main_subscription_units,0),421);
  const polSource=sources.items.find(r=>r.id==='policy_129');assert.equal(polSource.stats.attachment_table_rows,34);assert.equal(polSource.stats.attachment_table_in_scope,32);
  const pol=monitor.items.find(r=>r.id==='POL_2026_0129');assert(pol.timeline.block_count>8);
  assert.equal(pol.timeline.regions.flatMap(r=>r.cities.flatMap(c=>c.blocks)).flatMap(b=>b.events).filter(e=>e.stage==='CONSTRUCTION').length,32);
  await page.locator('[data-view="policy-progress"]').first().click();await page.locator('#policy-detail-select').selectOption('POL_2026_0129');
  await page.locator('#policy-timeline-measure').selectOption('CONSTRUCTION');assert(await page.locator('.annual-supply-bar').count()>0);
  const csv=await page.request.get(root+'api/samples/export.csv?kind=gh_notice');assert.equal(csv.status(),200);assert((await csv.text()).includes('gh_notice'));
  await page.locator('[data-view="samples"]').first().click();await page.locator('#sample-kind').selectOption('gh_notice');
  await page.locator('#sample-list').getByText('GH 주택 공고').first().waitFor({state:'visible'});
  const mobile=await browser.newPage({viewport:{width:390,height:844}});mobile.on('pageerror',e=>errors.push(e.message));
  await mobile.goto(root+'#validation');await mobile.locator('#content').waitFor({state:'visible'});
  assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  fs.mkdirSync('/tmp/home-coverage-check',{recursive:true});await page.locator('[data-view="validation"]').first().click();
  await page.locator('.coverage-panel').screenshot({path:'/tmp/home-coverage-check/source-coverage.png'});
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'PASS',projects:overview.project_count,apiRecords:overview.api_sample_count,registerRecords:register.collected_records,registerPagesComplete:true,ghNotices:gh.total,policy129Blocks:pol.timeline.block_count,policyStartEvents:32,shInventory:sh.total,populationComplete:false,stockRecords:stock.total,legalDongs:codes.total,urbanCandidatesComplete:true,ghCsv:true,mobileOverflow:false,errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
