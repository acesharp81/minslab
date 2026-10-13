'use strict';
const AreaDashboard=(()=>{
  let places=null, generation=0, loadedKey='', regionCache=new Map(), supplyCache=new Map(), outlookCache=new Map();
  const known=n=>Number.isFinite(n);
  const count=n=>known(n)?num(n):'미확보';
  const pct=n=>known(n)?n.toFixed(1)+'%':'미확보';
  const textGap=n=>!known(n)?'비교 미확보':n<0?`일반가구보다 ${num(-n)}호 적음`:n>0?`일반가구보다 ${num(n)}호 많음`:'주택 수와 일반가구 수 동일';
  const gapClass=n=>!known(n)?'unknown':n<0?'short':'surplus';
  const compact=n=>!known(n)?'—':Math.abs(n)>=1000000?(n/1000000).toFixed(1)+'백만':Math.abs(n)>=10000?(n/10000).toFixed(1)+'만':num(Math.round(n));
  async function get(region,municipality,year){
    const q=new URLSearchParams({region,year:String(year)});if(municipality)q.set('municipality',municipality);
    const response=await fetch('/poc/home/api/area-context?'+q);
    if(!response.ok)throw Error('지역 공식 통계 조회 실패');
    return response.json();
  }
  function plot(rows,lines,title,{index=false,unit='',labels=4,zero=true}={}){
    const width=690,height=240,left=53,right=14,top=17,bottom=205;
    const mapped=rows.map(row=>({...row,label:String(row.label??row.year??row.period)}));
    const values=lines.flatMap(line=>mapped.map(row=>row[line.key]).filter(known));
    if(!values.length)return '<p class="area-empty">해당 기간의 관측값 미확보</p>';
    const lo=index?Math.min(90,...values):zero?Math.min(0,...values):Math.floor(Math.min(...values)*.94),hi=Math.max(...values),span=Math.max(1,hi-lo);
    const x=i=>left+(width-left-right)*(i/(mapped.length-1||1));
    const y=v=>bottom-(v-lo)/span*(bottom-top);
    const grid=[0,.5,1].map(t=>{const value=lo+span*t;return `<g><line x1="${left}" x2="${width-right}" y1="${y(value)}" y2="${y(value)}" stroke="#e3ebf2"/><text x="${left-7}" y="${y(value)+4}" text-anchor="end">${index?value.toFixed(0):compact(value)}</text></g>`;}).join('');
    const paths=lines.map((line,li)=>{
      const color=line.color||['#1865bd','#eb8539','#208f79'][li%3];
      const segments=mapped.slice(1).map((row,i)=>known(row[line.key])&&known(mapped[i][line.key])?`<path d="M${x(i)} ${y(mapped[i][line.key])}L${x(i+1)} ${y(row[line.key])}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round"/>`:'').join('');
      const dots=mapped.map((row,i)=>known(row[line.key])?`<circle cx="${x(i)}" cy="${y(row[line.key])}" r="3" fill="${color}"><title>${esc(row.label)} ${esc(line.name)} ${count(row[line.key])}${esc(unit)}</title></circle>`:'').join('');
      return segments+dots;
    }).join('');
    const step=Math.max(1,Math.ceil(mapped.length/labels));
    const xs=mapped.map((row,i)=>i%step===0||i===mapped.length-1?`<text x="${x(i)}" y="${bottom+17}" text-anchor="middle">${esc(row.label.replace(/^20/,'').replace('01',' 상').replace('02',' 하'))}</text>`:'').join('');
    return `<div class="area-chart-scroll"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(title)}">${grid}${paths}${xs}</svg></div><div class="area-chart-legend">${lines.map((line,i)=>`<span><i style="background:${line.color||['#1865bd','#eb8539','#208f79'][i%3]}"></i>${esc(line.name)}</span>`).join('')}</div>`;
  }
  async function getSupply(region,year){
    const key=region+'|'+year;
    if(!supplyCache.has(key))supplyCache.set(key,fetch('/poc/home/api/annual-supply?'+new URLSearchParams({region,through_year:String(year)})).then(response=>{if(!response.ok)throw Error('연도별 공식 공급 통계 조회 실패');return response.json()}));
    return supplyCache.get(key);
  }
  async function getOutlook(region){
    if(!outlookCache.has(region))outlookCache.set(region,fetch('/poc/home/api/area-outlook?region='+encodeURIComponent(region)).then(response=>{if(!response.ok)throw Error('주택·가구 미래 비교 조회 실패');return response.json()}));
    return outlookCache.get(region);
  }
  function renderHouseholdSizes(data){
    const rows=data.household_size||[],keys=['1','2','3','4','5+'];
    const colors={'1':'#2766c0','2':'#34a09a','3':'#eaa54d','4':'#d77362','5+':'#9d79bc'};
    const label=key=>key==='5+'?'5인 이상':key+'인';
    if(!rows.length){$('area-household-size-chart').innerHTML='<h3>가구원수별 일반가구</h3><p class="area-empty">해당 지역의 가구원수별 시계열 미확보</p>';return;}
    const maximum=Math.max(...rows.map(r=>r.total)),first=rows[0],last=rows.at(-1);
    const bars=rows.map(row=>{
      let bottom=220;
      const parts=keys.map(key=>{
        const height=220*row.sizes[key]/maximum;
        bottom-=height;
        return `<rect x="0" y="${bottom}" width="42" height="${height}" fill="${colors[key]}"><title>${row.year}년 ${label(key)} 가구 ${count(row.sizes[key])}가구</title></rect>`;
      }).join('');
      return `<div class="area-size-year"><svg class="area-size-stack" width="42" height="220" viewBox="0 0 42 220" role="img" aria-label="${row.year}년 가구원수별 총 ${count(row.total)}가구">${parts}</svg><strong>${row.year}</strong></div>`;
    }).join('');
    $('area-household-size-chart').innerHTML=`<h3>1·2·3·4·5인 이상 가구 변화</h3><p>${esc(data.municipality||data.region)} · ${first.year}~${last.year}년 일반가구 수. 막대의 전체 높이는 가구 총수입니다.</p><div class="area-size-scroll"><div class="area-size-bars" role="group" aria-label="가구원수별 일반가구 연도별 누적 막대그래프">${bars}</div></div><div class="area-size-legend">${keys.map(key=>`<span><i class="size-color-${key.replace('+','plus')}"></i>${label(key)} 가구</span>`).join('')}</div><div class="area-size-deltas">${keys.map(key=>{const change=last.sizes[key]-first.sizes[key];return `<div><b>${label(key)}</b><strong>${count(last.sizes[key])}가구</strong><small>${first.year}년 대비 ${change>=0?'+':''}${num(change)}가구 · ${pct(100*last.sizes[key]/last.total)}</small></div>`}).join('')}</div><small>KOSIS 일반가구 가구원수별 표 <code>DT_1JC1516</code>. 5인 이상은 5·6·7인 이상 합계입니다.</small>`;
  }
  function renderSupplyFlow(data,supply){
    const rows=supply.rows.filter(row=>row.region===data.region),max=Math.max(1,...rows.flatMap(row=>['준공','분양승인','멸실'].map(m=>row.metrics[m].units||0)));
    const bars=rows.map(row=>{
      const rects=['준공','분양승인','멸실'].map((metric,index)=>{
        const cell=row.metrics[metric];
        if(cell.units==null)return '';
        const height=Math.max(2,220*cell.units/max);
        return `<rect x="${4+index*23}" y="${220-height}" width="18" height="${height}" rx="2" fill="${['#327ac1','#e79a5a','#8a789f'][index]}" opacity="${cell.complete?1:.42}"><title>${row.year}년 ${metric} ${count(cell.units)}호${cell.complete?'':' · 부분 집계'}</title></rect>`;
      }).join('');
      return `<div class="area-flow-year"><svg width="70" height="220" viewBox="0 0 70 220" role="img" aria-label="${row.year}년 준공·분양승인·멸실">${rects}</svg><strong>${row.year}</strong></div>`;
    }).join('');
    $('area-supply-flow').innerHTML=`<h3>${esc(data.region)} 공급·멸실 흐름</h3><p>준공·공동주택 분양승인·기존 주택 멸실 · 시도 전체(민간 포함). ${data.municipality?esc(data.municipality)+' 단독 실적은 미확보입니다.':''}</p><div class="area-flow-scroll"><div class="area-flow-bars" role="group" aria-label="2018년부터 준공·분양승인·멸실 흐름 비교">${bars}</div></div><div class="area-size-legend"><span><i class="size-color-completion"></i>준공</span><span><i class="size-color-sale"></i>분양승인</span><span><i class="size-color-demolition"></i>멸실</span></div><button type="button" class="area-flow-link" data-view="annual-supply">인허가·착공·멸실 연도별 상세 비교 ↗</button><small>준공은 멸실 차감 전 총량이고 분양승인은 실제 입주량이 아닙니다. 멸실 자료는 ${supply.demolition_latest_year||'미확보'}년까지 공개됐으며 이후 빈칸은 현재 확인한 원천의 미공표입니다. 12개월 미만 연도는 옅게 표시합니다.</small>`;
  }
  function renderOutlook(outlook,municipality){
    const node=$('area-outlook-chart');
    if(!outlook.baseline){node.innerHTML='<h3>주택 재고·장래가구 비교</h3><p class="area-empty">같은 연도 주택 재고·가구 자료 미확보</p>';return;}
    const base=outlook.baseline;
    const rows=[{year:base.year,observed:base.housing_units,scenario:base.housing_units,households:base.households,static_stock:base.housing_units},...outlook.years.map(r=>({year:r.year,scenario:r.scenario_housing_units,households:r.forecast_households,static_stock:base.housing_units}))];
    const targets=[outlook.years[0],outlook.years[1],outlook.years.find(r=>r.year===base.year+5)].filter(Boolean);
    node.innerHTML=`<h3>${esc(outlook.region)} 주택 재고 + 확인된 준공 예정 vs 장래가구</h3><p>${municipality?esc(municipality)+' 장래가구 추계는 미확보되어 시도 전체를 표시합니다. ':''}${base.year}년 주택 재고를 기준으로 당해연도 관측 준공과 사업별 준공 예정 일정을 구분해 쌓습니다.</p><div class="area-outlook-cards">${targets.map(r=>`<div><b>${r.year}년 · ${r.coverage==='PARTIAL_YEAR'?'현재까지 관측':'사업 일정 검토'}</b><strong class="${r.scenario_gap_units==null?'':r.scenario_gap_units<0?'short':'surplus'}">${r.scenario_gap_units==null?'준공 예정 물량 미확보':r.scenario_gap_units<0?`산술상 ${count(-r.scenario_gap_units)}호 적음`:`산술상 ${count(r.scenario_gap_units)}호 많음`}</strong><small>가구 추계 ${count(r.forecast_households)} · ${r.scenario_housing_units==null?'비교 미확보':'확인분 반영 '+count(r.scenario_housing_units)+'호'}</small></div>`).join('')}</div>${plot(rows,[{key:'households',name:'관측 가구 → 장래가구 추계',color:'#df8152'},{key:'static_stock',name:`${base.year}년 재고 유지 기준선`,color:'#aab9c4'},{key:'scenario',name:'관측 준공 + 확인된 준공 예정 반영',color:'#236cc0'}],'주택 재고·준공 예정과 장래가구 비교',{zero:false,labels:9,unit:'호/가구'})}<p class="area-outlook-note">${esc(outlook.note)} ${base.year}년 이후 공식 준공 관측 ${outlook.completion_current_year?.units==null?'미확보':count(outlook.completion_current_year.units)+'호('+outlook.completion_current_year.periods+'/12개월)'} · 장래가구 추계 공표 원본 ${esc(outlook.forecast_published_at||'미확보')}.</p>`;
  }
  function balanceCard(row,label){
    if(!row||!known(row.housing_units)||!known(row.households))return `<div class="area-balance-card unknown"><small>${esc(label)}</small><strong>같은 연도 비교 미확보</strong><p>주택 재고 시계열은 확보된 연도만 비교합니다.</p></div>`;
    const maximum=Math.max(row.housing_units,row.households,1),gap=row.gap_units;
    return `<div class="area-balance-card ${gapClass(gap)}"><div class="area-balance-top"><div><small>${esc(label)} · ${row.year}년</small><strong>${gap<0?'통계상 부족':gap>0?'통계상 여유':'수량 동일'}</strong></div><b>${pct(row.stock_to_household_pct)}</b></div><p>${textGap(gap)}</p><div class="area-compare-bars"><div><span>주택 재고</span><i><b class="housing" style="width:${100*row.housing_units/maximum}%"></b></i><strong>${count(row.housing_units)}호</strong></div><div><span>일반가구</span><i><b class="households" style="width:${100*row.households/maximum}%"></b></i><strong>${count(row.households)}가구</strong></div></div><small class="area-basis">다가구 구분거처 반영 주택 재고 · 공가/가용 주택 수나 정책 공급실적이 아닙니다.</small></div>`;
  }
  function regionCards(regions){
    $('area-region-compare').innerHTML=['서울특별시','경기도','인천광역시'].map(region=>{
      const row=regions[region]?.housing_balance.at(-1),gap=row?.gap_units;
      return `<button type="button" class="area-region-quick ${gapClass(gap)}" data-area-region="${region}"><small>${region} · ${row?.year||'연도 미확보'}년</small><strong>${textGap(gap)}</strong><span>주택 ${count(row?.housing_units)}호 / 가구 ${count(row?.households)}가구</span></button>`;
    }).join('');
  }
  function render(data,regions,supply){
    const housing=data.housing_balance,latest=housing.filter(row=>known(row.housing_units)&&known(row.households)).at(-1);
    const census=data.census,population=data.population_history||census,employment=data.employment;
    const latestCensus=census.at(-1),latestPopulation=population.at(-1),latestEmployment=employment.at(-1);
    const place=data.municipality||data.region;
    regionCards(regions);
    $('area-scope-name').textContent=place;
    $('area-balance').innerHTML=balanceCard(latest,place);
    $('area-kpis').innerHTML=[
      ['인구',latestPopulation?.population,'명',latestPopulation?.year?`${latestPopulation.year}년 ${latestPopulation.source||'SGIS'}`:'기준 미확보'],
      ['일반가구',housing.at(-1)?.households,'가구',housing.at(-1)?.year?`${housing.at(-1).year}년 KOSIS`:'기준 미확보'],
      ['거주지 취업자',latestEmployment?.resident_employed,'명',latestEmployment?.period?`${latestEmployment.period.slice(0,4)}년 ${Number(latestEmployment.period.slice(-2))}반기 KOSIS`:'기준 미확보'],
      ['사업체 종사자',latestCensus?.workplace_workers,'명',latestCensus?.year?`${latestCensus.year}년 SGIS`:'기준 미확보']
    ].map(([name,value,unit,period])=>`<article><small>${name}</small><strong>${count(value)}${known(value)?unit:''}</strong><span>${period}</span></article>`).join('');
    let market=$('area-unsold');if(!market){market=document.createElement('article');market.id='area-unsold';market.className='panel';$('area-balance').after(market);}market.innerHTML=UnsoldIndicators.html(data.unsold);
    renderHouseholdSizes(data);
    renderSupplyFlow(data,supply);
    $('area-outlook-chart').innerHTML='<h3>주택 재고 + 예정 공급 vs 장래가구</h3><p class="area-empty">확인된 사업 일정과 공식 가구 추계를 조회하고 있습니다…</p>';
    $('area-housing-chart').innerHTML=`<h3>주택 재고와 일반가구</h3><p>같은 연도·행정구역의 수량을 비교합니다.</p>${plot(housing,[{key:'census_housing_units',name:'주택총조사 주택_계',color:'#2b977a'},{key:'housing_units',name:'다가구 반영 주택 재고',color:'#1665bc'},{key:'households',name:'일반가구',color:'#ea8140'}],'연도별 주택총조사·보정 재고·일반가구',{unit:'호/가구',zero:false})}<small>주택총조사 주택_계는 2018년부터 확보했습니다. 다가구 구분거처 반영 재고와 집계 기준이 달라 별도 선으로 표시하며, 수급 차이·미래 전망에는 보정 재고가 있는 연도만 사용합니다. 세로축은 0에서 시작하지 않습니다.</small>`;
    const years=[...new Set([...population.map(r=>r.year),...housing.map(r=>r.year)])].sort((a,b)=>a-b);
    const popBase=population.find(r=>known(r.population))?.population,hBase=housing.find(r=>known(r.households))?.households;
    const demographic=years.map(year=>({year,population_index:popBase?100*population.find(r=>r.year===year)?.population/popBase:null,household_index:hBase?100*housing.find(r=>r.year===year)?.households/hBase:null}));
    $('area-demographic-chart').innerHTML=`<h3>인구와 가구 변화</h3><p>각 자료의 첫 확보연도=100. 연도별 변화 방향을 비교합니다.</p>${plot(demographic,[{key:'population_index',name:'인구 지수',color:'#2768bf'},{key:'household_index',name:'가구 지수',color:'#ed8845'}],'인구·가구 변화 지수',{index:true,unit:'',labels:8})}<small>인구 ${population[0]?.year||'미확보'}~${latestPopulation?.year||'미확보'}년 SGIS/KOSIS · 가구 ${housing[0]?.year||'미확보'}~${housing.at(-1)?.year||'미확보'}년 KOSIS</small>`;
    $('area-employment-chart').innerHTML=`<h3>반기별 취업자</h3><p>거주지 기준으로 집계한 취업자 수입니다.</p>${plot(employment.map(r=>({...r,label:r.period.slice(0,4)+' '+(r.period.slice(-2)==='01'?'상':'하')})),[{key:'resident_employed',name:'거주지 취업자',color:'#168d80'}],'반기별 거주지 취업자',{unit:'명',labels:8})}${data.municipality&&known(latestEmployment?.employment_rate)?`<div class="area-employment-rate"><span>최신 고용률</span><strong>${pct(latestEmployment.employment_rate)}</strong><small>${latestEmployment.period.slice(0,4)}년 ${Number(latestEmployment.period.slice(-2))}반기</small></div>`:''}<small>서울 일부 시군구의 2018~2020년 원천 값은 미제공입니다. 공백은 연결하지 않습니다.</small>`;
    const industries=Object.values(latestCensus?.industry_workers||{}).sort((a,b)=>b.workers-a.workers).slice(0,7),max=Math.max(1,...industries.map(r=>r.workers));
    $('area-industry-chart').innerHTML=`<h3>산업별 사업체 종사자</h3><p>${latestCensus?.year||'자료연도 미확보'}년 · 사업체 소재지 기준 · 상위 업종</p>${industries.length?industries.map(row=>`<div class="area-industry-row"><span>${esc(row.name)}</span><i><b style="width:${100*row.workers/max}%"></b></i><strong>${count(row.workers)}명</strong></div>`).join(''):'<p class="area-empty">산업별 통계 미확보</p>'}<small>산업 대분류이며 개인 직종 분류가 아닙니다. 비공개 지역은 합산하지 않습니다.</small>`;
    const future=data.household_forecast;
    $('area-forecast-chart').innerHTML=future.length?`<h3>장래가구 추계</h3><p>시도 전망 자료 · 관측 가구 수와 구분</p>${plot(future.map(r=>({...r,forecast:r.households})),[{key:'forecast',name:'장래가구 추계',color:'#8652bd'}],'시도별 장래가구 추계',{unit:'가구',labels:6})}<small>원천 최종 수정 ${esc(future[0].published_at)} · 공급 물량 추정치가 아닙니다.</small>`:`<h3>장래가구 추계</h3><p class="area-empty">시군구 추계 미확보 · 시도 단위에서 조회하세요.</p>`;
    $('area-evidence').innerHTML=`<a href="https://kosis.kr/openapi/devGuide/devGuide_0201List.do" target="_blank" rel="noopener">KOSIS 원천·API ↗</a><a href="https://sgis.mods.go.kr/developer/html/newOpenApi/api/dataApi/census.html" target="_blank" rel="noopener">SGIS 원천·API ↗</a><p>주택 재고는 기존 전체 주택을 포함합니다. 재고−일반가구는 단순 수량 차이이며 공실, 사용 가능 여부, 임대료, 통근 범위나 정책별 신규 공급을 반영한 실제 수급 부족량이 아닙니다. 사업체 종사자는 소재지, 취업자는 거주지 기준입니다.</p>`;
  }
  async function load(){
    const id=++generation,region=$('area-region').value,municipality=$('area-municipality').value,year=Number($('area-year').value);
    const key=[region,municipality,year].join('|');if(key===loadedKey)return;
    $('area-dashboard-status').textContent='공식 시계열을 조회하고 있습니다…';
    try{
      const [data,seoul,gyeonggi,incheon,supply]=await Promise.all([get(region,municipality,year),
        regionCache.get('서울특별시|'+year)||get('서울특별시',null,year),
        regionCache.get('경기도|'+year)||get('경기도',null,year),regionCache.get('인천광역시|'+year)||get('인천광역시',null,year),getSupply(region,year)]);
      if(id!==generation)return;
      regionCache.set('서울특별시|'+year,seoul);regionCache.set('경기도|'+year,gyeonggi);regionCache.set('인천광역시|'+year,incheon);
      loadedKey=key;render(data,{'서울특별시':seoul,'경기도':gyeonggi,'인천광역시':incheon},supply);
      if(year===new Date().getFullYear())getOutlook(region).then(outlook=>{if(id===generation)renderOutlook(outlook,municipality)}).catch(error=>{if(id===generation)$('area-outlook-chart').innerHTML='<h3>주택 재고·장래가구 비교</h3><p class="area-empty">'+esc(error.message)+'</p>'});
      else $('area-outlook-chart').innerHTML='<h3>주택 재고·장래가구 비교</h3><p class="area-empty">과거 연도 선택 중입니다. 현재 연도를 선택하면 최신 장래가구·준공 예정 비교가 표시됩니다.</p>';
      $('area-dashboard-status').textContent=`${data.municipality||data.region} · ${year}년까지 확보된 원천 자료`;
    }catch(error){if(id===generation)$('area-dashboard-status').textContent=error.message;}
  }
  async function visible(){
    if(!places){
      try{const response=await fetch('/poc/home/api/area-places');if(!response.ok)throw Error('지역 목록 조회 실패');places=await response.json();}
      catch(_){$('area-dashboard-status').textContent='지역 목록 연결 확인 필요';return;}
      const now=new Date().getFullYear();$('area-year').innerHTML=Array.from({length:now-2018+1},(_,i)=>now-i).map(year=>`<option value="${year}">${year}년 기준</option>`).join('');
      const topRegion=$('region').value;if(topRegion in places.regions)$('area-region').value=topRegion;
      updateMunicipalities();
    }
    load();
  }
  function updateMunicipalities(){
    const region=$('area-region').value,selected=$('area-municipality').value;
    $('area-municipality').innerHTML='<option value="">시도 전체</option>'+(places?.regions?.[region]||[]).map(name=>`<option value="${esc(name)}">${esc(name)}</option>`).join('');
    if((places?.regions?.[region]||[]).includes(selected))$('area-municipality').value=selected;
  }
  function start(){
    $('area-region').addEventListener('change',()=>{updateMunicipalities();load();});
    for(const id of ['area-municipality','area-year'])$(id).addEventListener('change',load);
    $('area-region-compare').addEventListener('click',event=>{const button=event.target.closest('[data-area-region]');if(button){$('area-region').value=button.dataset.areaRegion;updateMunicipalities();$('area-municipality').value='';load();}});
  }
  return {start,visible};
})();
