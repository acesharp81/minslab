/* Official nearby facilities remain separate from supply facts and keep the 3D map alive. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const root=process.env.HOME_CHECK_URL||'http://127.0.0.1:18100/poc/home/';
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.HOME_CHECK_CHROME||undefined,args:['--no-sandbox']});
  try{
    const page=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(root);
    await page.locator('.map-scene-block').first().waitFor({state:'visible',timeout:60000});
    await page.locator('#map-infrastructure-count').getByText('반경 3.5km').waitFor({timeout:30000});
    assert.equal(await page.locator('.map-infra-summary').count(),4);
    assert.match(await page.locator('.map-infra-summary.gtx').textContent(),/GTX-A.*운영/);
    assert((await page.locator('.map-infra-marker').count())>0);
    const data=await (await page.request.get(new URL('api/map/infrastructure?block_id='+encodeURIComponent('경기도|고양창릉|A4'),root).href)).json();
    assert.equal(data.distance_basis.includes('직선거리'),true);
    assert(data.counts.subway>0&&data.counts.school>0&&data.counts.hospital>0&&data.counts.gtx>0);
    assert(data.planned_gtx.some(row=>row.name==='창릉역'&&row.service_status==='PLANNED'&&row.location_status==='UNLINKED'));
    assert((await page.locator('.map-infra-planned').textContent()).includes('위치 미연계'));
    assert(data.items.every(row=>Number.isFinite(row.latitude)&&Number.isFinite(row.longitude)&&row.distance_m<=(row.kind==='gtx'?12000:3500)));
    assert((await page.locator('.map-infra-marker.gtx').count())>0);
    const canvas=await page.locator('#housing-map-3d canvas').elementHandle();
    await page.locator('.map-infra-summary.subway').click();
    await page.locator('.maplibregl-popup').last().waitFor({state:'visible'});
    assert.match(await page.locator('.maplibregl-popup').last().textContent(),/직선거리/);
    assert.equal(await canvas.evaluate(node=>node.isConnected),true);
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({status:'PASS',facilityCounts:data.counts,facilityMarkers:await page.locator('.map-infra-marker').count(),canvasRetained:true}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
