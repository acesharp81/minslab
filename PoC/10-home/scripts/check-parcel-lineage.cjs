const assert=require('node:assert/strict');
const {chromium}=require('/tmp/poc07-playwright/node_modules/playwright');
(async()=>{const b=await chromium.launch({headless:true,executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',args:['--no-sandbox']});try{
 const base=process.env.HOME_CHECK_BASE||'http://127.0.0.1:18101',page=await b.newPage({viewport:{width:1550,height:1100}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const res=await page.request.get(base+'/poc/home/api/project-collection?policy_id=POL_2025_0907');assert.equal(res.status(),200);const data=await res.json();
 const candidates=data.items.filter(p=>p.lineage?.keys.pnu);assert(candidates.length>0);assert(candidates.every(p=>p.parcel_identity?.status==='CANDIDATE'));
 const gwangju=candidates.find(p=>p.name==='광주역세권');assert(gwangju);assert.match(gwangju.lineage.keys.pnu,/4161011200104170002/);
 await page.goto(base+'/poc/home/#project-collection');await page.waitForSelector('#pc-table [data-pc-cell]',{timeout:60000});
 await page.locator('#pc-diagram [data-cl-node="key-pnu"]').click();assert.match(await page.locator('#pc-diagram-detail').innerText(),/PNU 후보/);
 await page.locator('#pc-search').fill('광주역세권');await page.locator('#pc-diagram [data-cl-node="key-pnu"]').click();assert.match(await page.locator('#pc-diagram-detail').innerText(),/4161011200104170002/);
 await page.screenshot({path:'/tmp/home-parcel-lineage.png',fullPage:false});assert.deepEqual(errors,[]);
 console.log(JSON.stringify({passed:true,projects:data.items.length,pnuCandidates:candidates.length,errors}));
}finally{await b.close();}})().catch(e=>{console.error(e);process.exit(1)});
