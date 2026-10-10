/* Public progress evidence, year filtering, CSV and policy timeline validation. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const root=process.env.HOME_CHECK_URL||'https://www.minslab.kr/poc/home/';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.HOME_CHECK_CHROME||undefined,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1500,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(30000);
  async function api(path){const r=await page.request.get(root+'api/'+path);assert.equal(r.status(),200,path);return r.json();}
  const [sources,old,history,policies,projects]=await Promise.all([api('sources'),api('history?history_year=2018'),api('history?history_year=2024'),api('policy-monitor'),api('projects?page_size=200')]);
  const lh=sources.items.find(r=>r.id==='lh_progress'),reit=sources.items.find(r=>r.id==='lh_reit_progress');
  assert.equal(lh.status,'SUCCESS');assert.equal(reit.status,'SUCCESS');assert(lh.stats.complete_query);
  assert(lh.stats.scope_blocks>=93);assert(lh.stats.observations_by_year['2024']>=35);assert.equal(lh.key_env,null);
  assert(lh.snapshots.every(s=>s.sha256&&s.bytes>100));
  assert(old.reports.some(r=>r.name==='하남미사 A-24'&&r.progress_pct===100&&r.report_date==='2018-12-31'));
  assert(history.reports.some(r=>r.name==='양주회천 A25'&&r.progress_pct===38.22&&r.report_date==='2024-12-27'));
  assert(history.reports.some(r=>r.name==='위례 A2-7'&&r.date_precision==='MONTH'&&r.source_registration_date==='2026-06-29'));
  const enriched=projects.items.filter(p=>p.progress_evidence_url);
  assert(enriched.length>0);assert(enriched.every(p=>p.progress_date&&p.progress_pct>=0&&p.progress_pct<=100));
  const linked=policies.items.flatMap(p=>p.timeline.regions.flatMap(r=>r.cities.flatMap(c=>c.blocks.flatMap(b=>b.actuals))));
  assert(linked.some(a=>a.evidence_url&&a.evidence_url.includes('cwsttInfo.do')));
  await page.goto(root+'#history');await page.locator('#content').waitFor({state:'visible'});
  await page.locator('#history-year').selectOption('2024');
  await page.locator('#history-reports').getByText('양주회천 A25',{exact:false}).first().waitFor({state:'visible'});
  const text=await page.locator('#history-reports').textContent();assert(text.includes('38.22%'));assert(text.includes('사진 원본 파일명'));
  const url=await page.locator('#history-export').getAttribute('href');assert(url.includes('history_year=2024'));
  const csv=await page.request.get(new URL(url,root).href);assert.equal(csv.status(),200);assert((await csv.text()).includes('source_registration_date'));
  await page.locator('#history-year').selectOption('2018');
  await page.locator('#history-reports').getByText('하남미사 A-24',{exact:false}).waitFor({state:'visible'});
  assert((await page.locator('#history-reports').textContent()).includes('100%'));
  fs.mkdirSync('/tmp/home-progress-check',{recursive:true});await page.screenshot({path:'/tmp/home-progress-check/history-2018.png',fullPage:true});
  const mobile=await browser.newPage({viewport:{width:390,height:844}});mobile.on('pageerror',e=>errors.push(e.message));
  await mobile.goto(root+'#history');await mobile.locator('#content').waitFor({state:'visible'});
  assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'PASS',scopeBlocks:lh.stats.scope_blocks,observations:Object.values(lh.stats.observations_by_year).reduce((a,b)=>a+b,0)+1,history2024:history.report_total,enrichedProjects:enriched.length,policyProgressLinked:true,monthAndRegistrationSeparated:true,csv:true,mobileOverflow:false,errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
