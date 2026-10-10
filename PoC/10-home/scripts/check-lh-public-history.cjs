/* Read-only live verification of historical file ingestion, UI filters, evidence and CSV. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const root=process.env.HOME_CHECK_URL||'https://www.minslab.kr/poc/home/';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.HOME_CHECK_CHROME||undefined,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1500,height:1000}}),errors=[];
  page.setDefaultTimeout(60000);page.on('pageerror',e=>errors.push(e.message));
  await page.goto(root+'#samples');await page.locator('#content').waitFor({state:'visible'});
  async function api(path){const r=await page.request.get(root+'api/'+path);assert.equal(r.status(),200,path);return r.json();}
  const [supply,movein,stock,older,sources,connections]=await Promise.all([
   api('samples?kind=lh_supply'),api('samples?kind=lh_movein_plan'),api('samples?kind=lh_stock'),api('samples?kind=lh_stock&source_year=2018'),api('sources'),api('connections')]);
  assert(supply.total>=76);assert(movein.total>=217);assert(stock.total>=1815);assert(older.total>0);
  assert(older.items.every(r=>r.source_date.startsWith('2018')&&r.dataset_version==='2026-08-10'&&r.warnings.includes('AGENCY_STOCK_NOT_SUPPLY')));
  for(const sid of ['lh_supply_history','lh_movein_history','lh_stock']){
   const source=sources.items.find(r=>r.id===sid);assert.equal(source.status,'SUCCESS');assert.equal(source.key_env,null);
   assert(source.snapshots.every(s=>s.sha256&&s.bytes>100));assert.equal(connections.planned.find(r=>r.id===sid).readiness,'CONNECTED');
  }
  const meta=sources.items.find(r=>r.id==='lh_movein_history').stats;
  assert.deepEqual(meta.missing_years,[2018,2019,2020,2021]);
  assert(meta.dataset_versions.find(r=>r.year===2026).summary_matches_details===false);
  await page.locator('#sample-kind').selectOption('lh_stock');
  await page.locator('#sample-year option[value="2018"]').waitFor({state:'attached'});
  await page.locator('#sample-year').selectOption('2018');
  await page.locator('#sample-list tbody tr').first().waitFor({state:'visible'});
  await page.getByRole('button',{name:older.items[0].name,exact:true}).first().waitFor({state:'visible'});
  await page.getByRole('button',{name:older.items[0].name,exact:true}).first().click();
  await page.locator('#detail-content').getByText('2018', {exact:false}).first().waitFor({state:'visible'});
  assert((await page.locator('#detail-content').textContent()).includes('2026-08-10'));
  const csv=await page.request.get(root+'api/samples/export.csv?kind=lh_stock&source_year=2018');assert.equal(csv.status(),200);
  const text=await csv.text();assert(text.includes('lh_stock')&&text.includes('2018-')&&text.includes('move_in_plan_month')&&text.includes('dates'));
  fs.mkdirSync('/tmp/home-lh-history-check',{recursive:true});await page.locator('#detail-dialog').screenshot({path:'/tmp/home-lh-history-check/historical-unit-detail.png'});
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'PASS',supply:supply.total,movein:movein.total,stock:stock.total,stock2018:older.total,missingMoveinYears:meta.missing_years,source2026TotalMismatchVisible:true,csv:true,errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
