/* Exercise the real map controls against a tiny source-evidence fixture. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');

(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.HOME_CHECK_CHROME||undefined,args:['--no-sandbox']});
  try{
    const page=await browser.newPage({viewport:{width:1000,height:900}});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.setContent('<input id="as-of" value="2026-10-10"><div id="policy-geo-map"></div>');
    await page.evaluate(()=>{window.$=id=>document.getElementById(id);window.num=n=>Number(n).toLocaleString('ko-KR');window.esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));});
    await page.addScriptTag({path:path.join(__dirname,'../web/assets/policy-schematic.js')});
    await page.evaluate(()=>{
      PolicySchematic.start();
      const shape={shapes:[{id:'M1',name:'시험시',region:'경기도',latitude:37,longitude:127,
        rings:[[[126.9,36.9],[127.1,36.9],[127.1,37.1],[126.9,37.1],[126.9,36.9]]]}]};
      const make=annual=>({groups:{policy:[{id:'P',chart_schedule_ids:['I']}]},municipalities:[{id:'M1',project_ids:['I'],by_scope:{policy:{P:{target_units:100,project_count:1}}}}],items:[{id:'I',notice_evidence_id:'N',notice_source_date:'2026-07-01',current_notice_units:5,annual_series:annual}]});
      PolicySchematic.draw(shape,{SUPPLY:make([{year:2026,SUPPLY:10},{year:2028,SUPPLY:20}]),COMPLETION:make([{year:2026,COMPLETION:20},{year:2028,COMPLETION:60}])},'P',{announced_at:'2025-09-07'});
    });
    const city=page.locator('[data-ps-city="M1"]');
    assert.equal(await city.getAttribute('data-ps-visible'),'20');
    const firstHeight=Number(await city.getAttribute('data-ps-height'));
    const slider=page.locator('#ps-year');
    await slider.evaluate(input=>{input.value='2028';input.dispatchEvent(new Event('input',{bubbles:true}));});
    assert.equal(await slider.evaluate(input=>input.isConnected),true,'dragging must not replace the slider');
    assert.equal(await city.getAttribute('data-ps-visible'),'80');
    assert(Number(await city.getAttribute('data-ps-height'))>firstHeight);
    await page.locator('input[name="ps-stage"][value="CAPACITY"]').check();
    assert.equal(await city.getAttribute('data-ps-visible'),'30','plan must use dated supply schedule, not total target');
    await page.locator('#ps-year').evaluate(input=>{input.value='2026';input.dispatchEvent(new Event('input',{bubbles:true}));});
    assert.equal(await city.getAttribute('data-ps-visible'),'10');
    await page.locator('input[name="ps-stage"][value="SUPPLY"]').check();
    assert.equal(await city.getAttribute('data-ps-visible'),'5');
    await page.locator('#ps-year').evaluate(input=>{input.value='2028';input.dispatchEvent(new Event('input',{bubbles:true}));});
    assert.equal(await city.getAttribute('data-ps-visible'),'25');
    assert.match(await page.locator('.ps-basis').textContent(),/연도별 값 확인/);
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({status:'PASS',completion:'20→80',plan:'10→30',recruitment:'5→25',sliderPreserved:true}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
