/* The same zoom thresholds drive map symbols and supply details in both directions. */
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
    assert.deepEqual(await page.evaluate(()=>[9.999,10,12.999,13].map(MapMonitor.levelAt)),['region','municipality','municipality','block']);
    const sample=await page.evaluate(()=>MapTrends.derive({analysis_year:2026,start_year:2025,horizon:10,measure:'SUPPLY',reference_date:'2026-10-04',items:[{id:'p',base_date:'2025-01-01',supply_year_range:{start_year:2025,end_year:2027,units:2000},annual:[],earlier_events:[],notice_evidence:{id:'n',source_date:'2026-05-01',units:300}}]},
      {chart_target_ids:['p'],chart_schedule_ids:[],chart_manual_ids:[],target_units:2000}));
    assert.deepEqual(sample.rows.filter(row=>row.year>=2025&&row.year<=2027).map(row=>row.planned),[667,667,666]);
    assert.equal(sample.rows.find(row=>row.year===2026).observed,300);
    assert.deepEqual(sample.rows.map(row=>row.year),[2022,2023,2024,2025,2026,2027,2028,2029,2030,2031]);
    const partial=await page.evaluate(()=>MapTrends.derive({analysis_year:2026,start_year:2025,horizon:10,measure:'SUPPLY',reference_date:'2026-10-04',items:[{id:'p',base_date:'2025-01-01',supply_year_range:{start_year:2025,end_year:2027,units:2000},annual:[],earlier_events:[{year:2025,month:'2025-06',stage:'SUPPLY',origin:'SOURCE',units:500}]}]},
      {chart_target_ids:['p'],chart_schedule_ids:['p'],chart_manual_ids:[],target_units:2000}));
    assert.deepEqual(partial.rows.filter(row=>row.year>=2025&&row.year<=2027).map(row=>row.planned),[500,750,750]);
    const carry=await page.evaluate(()=>MapTrends.derive({analysis_year:2026,start_year:2018,horizon:10,measure:'SUPPLY',reference_date:'2026-10-04',items:[{id:'p',earlier_events:[{year:2021,stage:'SUPPLY',origin:'SOURCE',units:600},{year:2033,stage:'SUPPLY',origin:'SOURCE',units:400}],annual:[],notice_evidence:{id:'old',source_date:'2021-06-01',units:250}}]},
      {chart_target_ids:['p'],chart_schedule_ids:['p'],chart_manual_ids:[],target_units:1000}));
    assert.equal(carry.rows[0].plannedCumulative,600);
    assert.equal(carry.rows[0].observedCumulative,250);
    assert.equal(carry.unallocated,0);
    const historical=await page.evaluate(()=>MapTrends.derive({analysis_year:2024,start_year:2018,horizon:10,measure:'SUPPLY',reference_date:'2024-10-04',items:[]},
      {chart_target_ids:[],chart_schedule_ids:[],chart_manual_ids:[],target_units:null}));
    assert.deepEqual(historical.rows.map(row=>row.year),[2020,2021,2022,2023,2024,2025,2026,2027,2028,2029]);
    const setLevel=async(level)=>{
      await page.evaluate(level=>MapThreeD.setLevel(level==='region'?'policy':level),level);
      let matched=false;
      for(let attempt=0;attempt<90;attempt++){
        matched=await page.evaluate(level=>MapThreeD.view()?.level===level&&document.querySelector('.trend-heading small')?.textContent.includes(({region:'시도',municipality:'시군구',block:'블록'})[level]),level);
        if(matched)break;
        await page.waitForTimeout(150);
      }
      assert(matched,`map and panel did not reach ${level}`);
      const result=await page.evaluate(()=>({zoom:MapThreeD.zoom(),mapLevel:MapThreeD.view().level,panel:document.querySelector('.trend-heading small').textContent}));
      assert.equal(result.mapLevel,await page.evaluate(()=>MapMonitor.levelAt(MapThreeD.zoom())));
      assert.equal(await page.locator('.trend-five span').count(),5);
      const chart=page.locator('.trend-chart');
      assert.match(await chart.getAttribute('aria-label'),/2022년부터 2031년까지/);
      assert.equal(await chart.locator('.trend-current-year').textContent(),'2026');
      assert.equal(await chart.locator('.trend-current-band').count(),1);
      return result;
    };
    const out1=await setLevel('municipality');
    assert((await page.locator('.map-scene-municipality').count())>0);
    const in1=await setLevel('block');
    assert((await page.locator('.map-scene-block').count())>0);
    assert((await page.locator('.trend-stages li').count())>0);
    const preferred=await page.locator('#map-3d-block-picker option').evaluateAll(options=>options.map(row=>row.value).find(value=>value.endsWith('|S1')));
    assert(preferred);
    await page.locator('#map-3d-block-picker').selectOption(preferred);
    assert.match(await page.locator('.trend-heading h4').textContent(),/S1/);
    assert.match(await page.locator('.trend-heading small').textContent(),/선택됨/);
    assert.match(await page.locator('#map-method-block').textContent(),/블록별 위치 근거/);
    const out2=await setLevel('municipality');
    const region=await setLevel('region');
    assert((await page.locator('.trend-policy-reference .supply-bar-chart').count())>0);
    assert((await page.locator('.trend-chart').count())===1);
    assert.equal(await page.locator('#map-panel-content > :last-child').getAttribute('id'),'map-panel-methodology');
    assert.equal(await page.locator('#monitor-policy-chart > .trend-note').count(),0);
    assert.match(await page.locator('#map-method-summary').textContent(),/모집공고 연결 검토량/);
    assert(await page.locator('#map-3d-evidence').evaluate(node=>Boolean(node.closest('#map-panel-methodology'))));
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({status:'PASS',zoomThresholds:[10,13],levels:[out1.mapLevel,in1.mapLevel,out2.mapLevel,region.mapLevel],intervalAllocation:[667,667,666]}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
