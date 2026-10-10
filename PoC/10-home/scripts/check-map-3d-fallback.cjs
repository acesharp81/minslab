/* Conceptual supply buildings remain visible when existing-building context is unavailable. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const root=process.env.HOME_CHECK_URL||'http://127.0.0.1:18100/poc/home/';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.HOME_CHECK_CHROME||undefined,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/api/map/buildings?*',route=>route.fulfill({status:503,contentType:'application/json',body:'{"detail":"context temporarily unavailable"}'}));
  await page.goto(root);
  await page.locator('#housing-map-3d canvas').waitFor({state:'visible',timeout:60000});
  await page.locator('.map-scene-block').first().waitFor({state:'visible',timeout:60000});
  assert.equal(await page.evaluate(()=>MapThreeD.active()),true);
  assert((await page.evaluate(()=>MapThreeD.modelStats().features))>0);
  assert.match(await page.locator('#map-3d-evidence').textContent(),/가상 아파트 동 배치/);
  assert.equal(await page.locator('#housing-map-3d canvas').count(),1);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'PASS',conceptualModelsWithoutBuildingAPI:true}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
