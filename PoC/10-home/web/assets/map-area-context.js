'use strict';
// Compact map companion for the same official area series shown in the full analysis page.
const MapAreaContext=(()=>{
  let signature='',request=0;
  const known=n=>Number.isFinite(n);
  const fmt=value=>known(value)?num(value):'미확보';
  const label=(name,value,unit,date)=>`<div class="area-context-kpi"><small>${esc(name)}</small><strong>${fmt(value)}${known(value)?unit:''}</strong><span>${esc(date||'기준 미확보')}</span></div>`;
  function spark(rows,key,aria){
    const knownRows=rows.filter(row=>known(row[key]));
    if(knownRows.length<2)return '<span class="area-context-empty">연속 시계열 미확보</span>';
    const values=knownRows.map(row=>row[key]),lo=Math.min(...values),hi=Math.max(...values),span=Math.max(1,hi-lo);
    const x=i=>8+i*284/(rows.length-1||1),y=value=>54-(value-lo)/span*44;
    const lines=rows.slice(1).map((row,i)=>known(row[key])&&known(rows[i][key])?`<path d="M${x(i)} ${y(rows[i][key])}L${x(i+1)} ${y(row[key])}" stroke="#1769c2" stroke-width="3" fill="none"/>`:'').join('');
    const dots=rows.map((row,i)=>known(row[key])?`<circle cx="${x(i)}" cy="${y(row[key])}" r="2.5" fill="#1769c2"><title>${esc(String(row.year||row.period))} · ${fmt(row[key])}</title></circle>`:'').join('');
    return `<svg viewBox="0 0 300 72" role="img" aria-label="${esc(aria)}">${lines}${dots}<text x="7" y="70">${esc(String(rows[0].year||rows[0].period))}</text><text x="291" y="70" text-anchor="end">${esc(String(rows.at(-1).year||rows.at(-1).period))}</text></svg>`;
  }
  function scope(data,viewport){
    const chosen=MapTrends.scope(data,viewport,MapSupply.selection());
    if(!chosen)return null;
    const row=chosen.row;
    if(chosen.level==='region')return {region:row.id,municipality:null,note:'시도 기준'};
    if(chosen.level==='municipality')return {region:row.region,municipality:row.name,note:'시군구 기준'};
    const matches=data.municipalities.filter(area=>row.project_ids?.some(id=>area.project_ids.includes(id)));
    if(matches.length!==1)return null;
    return {region:matches[0].region,municipality:matches[0].name,note:'선택 블록이 속한 시군구 기준'};
  }
  function ensureMethod(){
    const method=document.getElementById('map-method-summary');
    if(method&&!method.querySelector('.area-context-method'))method.insertAdjacentHTML('beforeend',`<p class="area-context-method">지역 통계: <a href="https://sgis.mods.go.kr/developer/html/newOpenApi/api/dataApi/census.html" target="_blank" rel="noopener">SGIS 원천 ↗</a> · <a href="https://kosis.kr/openapi/devGuide/devGuide_0201List.do" target="_blank" rel="noopener">KOSIS 원천 ↗</a>. 주택 재고−일반가구는 단순 수량 차이이며 공실·가용 주택 수나 정책 공급 실적이 아닙니다.</p>`);
  }
  function render(node,data,place){
    const census=data.census.at(-1),population=(data.population_history||data.census).at(-1);
    const employment=data.employment.at(-1),future=data.household_forecast;
    const housing=data.housing_balance.filter(row=>known(row.housing_units)&&known(row.households)).at(-1);
    const title=place.municipality||place.region;
    const industry=Object.values(census?.industry_workers||{}).sort((a,b)=>b.workers-a.workers).slice(0,3);
    const gap=housing?.gap_units,ratio=housing?.stock_to_household_pct;
    const balance=known(gap)?`<div class="area-context-balance ${gap<0?'short':'surplus'}"><small>${housing.year}년 주택 재고−일반가구</small><strong>${gap<0?`가구보다 ${num(-gap)}호 적음`:`가구보다 ${num(gap)}호 많음`}</strong><div class="area-context-meter"><i style="width:${Math.min(100,ratio)}%"></i></div><span>재고 ${fmt(housing.housing_units)}호 / 일반가구 ${fmt(housing.households)}가구 · ${ratio}%</span></div>`:'<p class="area-context-empty">같은 연도의 주택 재고·가구 비교 미확보</p>';
    node.innerHTML=`<h3>지역 생활·고용 지표</h3><p class="area-context-location">${esc(title)} <small>${esc(place.note)}</small></p>${balance}
      <div class="area-context-grid">${label('인구',population?.population,'명',population?.year?population.year+'년 '+(population.source||'SGIS'):'')}${label('일반가구',data.housing_balance.at(-1)?.households,'가구',data.housing_balance.at(-1)?.year?data.housing_balance.at(-1).year+'년 KOSIS':'')}${label('사업체 종사자',census?.workplace_workers,'명',census?.year?census.year+'년 SGIS':'')}${label('거주지 취업자',employment?.resident_employed,'명',employment?.period?employment.period.slice(0,4)+'년 '+Number(employment.period.slice(-2))+'반기 KOSIS':'')}</div>
      ${place.municipality?`<p class="area-context-rate">고용률 <strong>${known(employment?.employment_rate)?employment.employment_rate+'%':'미확보'}</strong> <small>거주지 기준 · ${employment?.period?employment.period.slice(0,4)+'년 '+Number(employment.period.slice(-2))+'반기':'기준 미확보'}</small></p>`:''}
      <div class="area-context-trends"><h4>연도·반기별 변화</h4><b>인구 ${population?.year||'미확보'}년까지</b>${spark(data.population_history||data.census,'population','공식 연도별 인구 추이')}<b>일반가구 ${data.housing_balance.at(-1)?.year||'미확보'}년까지</b>${spark(data.housing_balance,'households','KOSIS 연도별 일반가구 추이')}<b>거주지 취업자 ${employment?.period||'미확보'}까지</b>${spark(data.employment,'resident_employed','KOSIS 반기별 취업자 추이')}</div>
      ${industry.length?`<div class="area-context-industry"><b>산업별 종사자 상위 3개</b>${industry.map(item=>`<span>${esc(item.name)} <strong>${fmt(item.workers)}명</strong></span>`).join('')}</div>`:''}
      ${future.length?`<div class="area-context-forecast"><b>시도 장래가구 추계</b><div>${future.filter((_,i)=>i===0||i===4||i===9).map(item=>`<span>${item.year}년 <strong>${fmt(item.households)}가구</strong></span>`).join('')}</div></div>`:place.municipality?'<p class="area-context-definition">시군구 장래가구 추계 미확보 · 시도 단위에서만 조회 가능</p>':''}
      <button type="button" class="area-context-open" data-view="area">인구·가구·고용 전체 분석 보기 ↗</button><p class="area-context-definition">주택 재고와 가구 수의 차이는 실제 공급 부족·공실 수가 아닙니다. 인구·가구·고용은 정책 실적에 합산하지 않습니다.</p>`;
    ensureMethod();
  }
  async function panel(supply,viewport){
    let node=document.getElementById('map-area-context');
    if(!node){node=document.createElement('section');node.id='map-area-context';node.className='map-info-card map-area-context';document.getElementById('map-policy-monitor')?.insertAdjacentElement('afterend',node);}
    const place=scope(supply,viewport);
    if(!place){request++;signature='';node.innerHTML='<h3>지역 생활·고용 지표</h3><p>사업이 속한 시군구 미연계</p>';return;}
    const key=[place.region,place.municipality||'',supply.analysis_year].join('|');
    if(key===signature){ensureMethod();return;}
    signature=key;node.innerHTML='<h3>지역 생활·고용 지표</h3><p>공식 통계를 조회하고 있습니다…</p>';
    const query=new URLSearchParams({region:place.region,year:String(Math.min(supply.analysis_year,new Date().getFullYear()))});
    if(place.municipality)query.set('municipality',place.municipality);
    const current=++request;
    try{
      const response=await fetch('/poc/home/api/area-context?'+query.toString());
      if(!response.ok)throw Error('조회 실패');
      const data=await response.json();
      if(current===request)render(node,data,place);
    }catch(_){if(current===request){node.innerHTML='<h3>지역 생활·고용 지표</h3><p>통계 연결 확인 필요</p>';signature='';}}
  }
  return {panel};
})();
