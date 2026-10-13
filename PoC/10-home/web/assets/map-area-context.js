'use strict';
// Compact map companion for the same official area series shown in the full analysis page.
const MapAreaContext=(()=>{
  let signature='',request=0;
  const known=n=>Number.isFinite(n);
  const fmt=value=>known(value)?num(value):'미확보';
  const label=(name,value,unit,date)=>`<div class="area-context-kpi"><small>${esc(name)}</small><strong>${fmt(value)}${known(value)?unit:''}</strong><span>${esc(date||'기준 미확보')}</span></div>`;
  function integratedTrend(data,supply,place){
    const population=new Map((data.population_history||data.census).map(row=>[row.year,row.population]));
    const balance=new Map(data.housing_balance.map(row=>[row.year,row]));
    const annual=new Map((supply?.rows||[]).filter(row=>row.region===place.region).map(row=>[row.year,row.metrics?.['분양승인']]));
    const years=[...new Set([...population.keys(),...balance.keys(),...annual.keys()])].filter(year=>year>=2018&&year<=new Date().getFullYear()).sort((a,b)=>a-b);
    if(!years.length)return '<p class="area-context-empty">비교 가능한 시계열 미확보</p>';
    const maxPop=Math.max(1,...[...population.values()].filter(known));
    const maxHome=Math.max(1,...data.housing_balance.flatMap(row=>[row.households,row.housing_units]).filter(known));
    const supplyRows=(!supply||place.municipality)?[]:years.map(year=>annual.get(year)?.units).filter(known);
    const maxSupply=Math.max(1,...supplyRows),left=48,right=335,top=26,lineBottom=175,barTop=190,barBottom=230;
    const x=i=>left+i*(right-left)/Math.max(1,years.length-1);
    const yPop=value=>lineBottom-(value/maxPop)*(lineBottom-top);
    const yHome=value=>lineBottom-(value/maxHome)*(lineBottom-top);
    const points=(access,y)=>years.map((year,i)=>({year,x:x(i),v:access(year)})).filter(row=>known(row.v));
    const path=(access,y)=>{let result='';years.forEach((year,i)=>{const value=access(year);if(!known(value))return;const segment=(i&&known(access(years[i-1]))?'L':'M')+x(i).toFixed(1)+' '+y(value).toFixed(1);result+=segment;});return result;};
    const lines=[['인구',year=>population.get(year),yPop,'#1766c2','명'],['일반가구',year=>balance.get(year)?.households,yHome,'#e28740','가구'],['주택 재고',year=>balance.get(year)?.housing_units,yHome,'#209584','호']];
    const guide=[0,.5,1].map(f=>'<g><line x1="'+left+'" x2="'+right+'" y1="'+(lineBottom-f*(lineBottom-top))+'" y2="'+(lineBottom-f*(lineBottom-top))+'" stroke="#e4ebf2"/><text x="'+(left-5)+'" y="'+(lineBottom-f*(lineBottom-top)+3)+'" text-anchor="end">'+(maxPop*f/10000).toFixed(0)+'만</text><text x="'+(right+5)+'" y="'+(lineBottom-f*(lineBottom-top)+3)+'">'+(maxHome*f/10000).toFixed(0)+'만</text></g>').join('');
    const paths=lines.map(([name,get,y,color,unit])=>'<path d="'+path(get,y)+'" fill="none" stroke="'+color+'" stroke-width="2.6"/>'+points(get,y).map(row=>'<circle cx="'+row.x+'" cy="'+y(row.v)+'" r="2.3" fill="'+color+'"><title>'+row.year+'년 '+name+' '+fmt(row.v)+unit+'</title></circle>').join('')).join('');
    const bars=(!supply||place.municipality)?'':years.map((year,i)=>{const cell=annual.get(year);if(!known(cell?.units))return '';const height=Math.max(2,cell.units/maxSupply*(barBottom-barTop));return '<rect x="'+(x(i)-5)+'" y="'+(barBottom-height)+'" width="10" height="'+height+'" rx="2" fill="#9675c8" opacity="'+(cell.complete?'1':'.45')+'"><title>'+year+'년 분양승인 '+fmt(cell.units)+'호'+(cell.complete?'':' · 부분 집계')+'</title></rect>';}).join('');
    const tick=years.map((year,i)=>'<text x="'+x(i)+'" y="251" text-anchor="middle">'+String(year).slice(2)+'</text>').join('');
    const note='인구·일반가구·주택 재고는 지역 수요의 참고 지표이며 정책 공급 실적과 구분합니다.';
    return '<div class="area-context-trends"><h4>인구 · 가구 · 주택 재고 흐름</h4><div class="area-context-legend"><span><i class="people"></i>인구(왼쪽)</span><span><i class="house"></i>일반가구(오른쪽)</span><span><i class="stock"></i>주택 재고(오른쪽)</span>'+((!supply||place.municipality)?'':'<span><i class="supply"></i>연간 분양승인(아래 막대)</span>')+'</div><svg viewBox="0 0 380 267" role="img" aria-label="연도별 인구, 일반가구, 주택 재고 및 연간 분양승인 통합 그래프"><text x="5" y="12">인구</text><text x="336" y="12">가구·호</text>'+guide+paths+'<line x1="'+left+'" x2="'+right+'" y1="'+barBottom+'" y2="'+barBottom+'" stroke="#c8d7e6"/>'+bars+tick+'</svg><small>'+note+'</small></div>';
  }
  function shareRows(items,total){return '<div class="area-share-rows">'+items.map(r=>{const pct=known(r.count)&&known(total)&&total>0?Math.round(r.count/total*1000)/10:null;return '<div><span>'+esc(r.label)+'</span><progress max="100" value="'+(pct??0)+'" aria-label="'+esc(r.label)+' 비율"></progress><b>'+(pct==null?'산정 불가':pct+'%')+'</b><small>'+fmt(r.count)+'</small></div>';}).join('')+'</div>';}
  function householdShares(data){const row=(data.household_size||[]).at(-1);if(!row)return '<section class="area-demographic-card" data-demographic="household"><h4>가구원수 비율</h4><p>선택 지역의 일반가구 가구원수 자료 미확보</p></section>';return '<section class="area-demographic-card" data-demographic="household"><h4>가구원수 비율 · '+row.year+'년</h4>'+shareRows(['1','2','3','4','5+'].map(k=>({label:k==='5+'?'다인가구 · 5인 이상':k+'인 가구',count:row.sizes[k]})),row.total)+'<p>일반가구 '+fmt(row.total)+'가구가 분모입니다. 5인 이상을 다인가구로 표시하며 주민등록 세대와 구분합니다.</p></section>';}
  function ageShares(data){const age=data.age_distribution,current=age?.current;if(!current)return '<section class="area-demographic-card" data-demographic="age"><h4>연령 비율</h4><p>선택 지역의 연령 분포 미확보</p></section>';return '<section class="area-demographic-card" data-demographic="age"><h4>연령 비율 · '+esc(current.period)+'</h4>'+(age.fallback?'<p>해당 시군구 미확보 · 시도 전체 참고값</p>':'')+shareRows(current.bands,current.total)+'<p>주민등록인구 '+fmt(current.total)+'명이 분모입니다. 인구총조사·일반가구 통계와 기준·범위가 다릅니다.</p><a href="'+esc(safeUrl(current.evidence_url))+'" target="_blank" rel="noopener noreferrer">연령 통계 원문 ↗</a></section>';}
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
    const method=document.getElementById('map-location-method-content');
    if(method&&!method.querySelector('.area-context-method'))method.insertAdjacentHTML('beforeend',`<p class="area-context-method">지역 통계: <a href="https://sgis.mods.go.kr/developer/html/newOpenApi/api/dataApi/census.html" target="_blank" rel="noopener">SGIS 원천 ↗</a> · <a href="https://kosis.kr/openapi/devGuide/devGuide_0201List.do" target="_blank" rel="noopener">KOSIS 원천 ↗</a>. 주택 재고−일반가구는 단순 수량 차이이며 공실·가용 주택 수나 정책 공급 실적이 아닙니다.</p>`);
  }
  function render(node,data,place,supply){
    const census=data.census.at(-1),population=(data.population_history||data.census).at(-1);
    const employment=data.employment.at(-1),future=data.household_forecast;
    const housing=data.housing_balance.filter(row=>known(row.housing_units)&&known(row.households)).at(-1);
    const title=place.municipality||place.region;
    const industry=Object.values(census?.industry_workers||{}).sort((a,b)=>b.workers-a.workers).slice(0,3);
    const gap=housing?.gap_units,ratio=housing?.stock_to_household_pct;
    const balance=known(gap)?`<div class="area-context-balance ${gap<0?'short':'surplus'}"><small>${housing.year}년 주택 재고−일반가구</small><strong>${gap<0?`가구보다 ${num(-gap)}호 적음`:`가구보다 ${num(gap)}호 많음`}</strong><div class="area-context-meter"><i style="width:${Math.min(100,ratio)}%"></i></div><span>재고 ${fmt(housing.housing_units)}호 / 일반가구 ${fmt(housing.households)}가구 · ${ratio}%</span></div>`:'<p class="area-context-empty">같은 연도의 주택 재고·가구 비교 미확보</p>';
    node.innerHTML=`<h3>지역 생활·수요 지표</h3><p class="area-context-location">${esc(title)} <small>${esc(place.note)}</small></p>${balance}
      <div class="area-context-grid">${label('인구',population?.population,'명',population?.year?population.year+'년 '+(population.source||'SGIS'):'')}${label('일반가구',data.housing_balance.at(-1)?.households,'가구',data.housing_balance.at(-1)?.year?data.housing_balance.at(-1).year+'년 KOSIS':'')}${label('사업체 종사자',census?.workplace_workers,'명',census?.year?census.year+'년 SGIS':'')}${label('거주지 취업자',employment?.resident_employed,'명',employment?.period?employment.period.slice(0,4)+'년 '+Number(employment.period.slice(-2))+'반기 KOSIS':'')}</div>
      ${place.municipality?`<p class="area-context-rate">고용률 <strong>${known(employment?.employment_rate)?employment.employment_rate+'%':'미확보'}</strong> <small>거주지 기준 · ${employment?.period?employment.period.slice(0,4)+'년 '+Number(employment.period.slice(-2))+'반기':'기준 미확보'}</small></p>`:''}
      ${householdShares(data)}${ageShares(data)}${integratedTrend(data,null,place)}<section class="unsold-context">${UnsoldIndicators.html(data.unsold)}</section>
      ${industry.length?`<div class="area-context-industry"><b>산업별 종사자 상위 3개</b>${industry.map(item=>`<span>${esc(item.name)} <strong>${fmt(item.workers)}명</strong></span>`).join('')}</div>`:''}
      ${future.length?`<div class="area-context-forecast"><b>시도 장래가구 추계</b><div>${future.filter((_,i)=>i===0||i===4||i===9).map(item=>`<span>${item.year}년 <strong>${fmt(item.households)}가구</strong></span>`).join('')}</div></div>`:place.municipality?'<p class="area-context-definition">시군구 장래가구 추계 미확보 · 시도 단위에서만 조회 가능</p>':''}
      <button type="button" class="area-context-open" data-view="area">인구·가구·고용 전체 분석 보기 ↗</button><p class="area-context-definition">주택 재고와 가구 수의 차이는 실제 공급 부족·공실 수가 아닙니다. 인구·가구·고용은 정책 실적에 합산하지 않습니다.</p>`;
    ensureMethod();
  }
  async function panel(supply,viewport){
    let node=document.getElementById('map-area-context');
    if(!node){node=document.createElement('section');node.id='map-area-context';node.className='map-info-card map-area-context';document.getElementById('map-location-content')?.prepend(node);}
    const place=scope(supply,viewport);
    if(!place){request++;signature='';document.getElementById('map-location-status').textContent='사업이 속한 지역 확인 필요';node.innerHTML='<h3>지역 생활·수요 지표</h3><p>사업이 속한 시군구 미연계</p>';return;}
    document.getElementById('map-location-status').textContent=(place.municipality||place.region)+' · '+place.note;
    const key=[place.region,place.municipality||'',new Date().getFullYear()].join('|');
    if(key===signature){ensureMethod();return;}
    signature=key;node.innerHTML='<h3>지역 생활·수요 지표</h3><p>공식 통계를 조회하고 있습니다…</p>';
    const query=new URLSearchParams({region:place.region,year:String(new Date().getFullYear())});
    if(place.municipality)query.set('municipality',place.municipality);
    const current=++request;
    try{
      const response=await fetch('/poc/home/api/area-context?'+query.toString());
      if(!response.ok)throw Error('조회 실패');
      const data=await response.json();
      if(current===request)render(node,data,place,null);
    }catch(_){if(current===request){node.innerHTML='<h3>지역 생활·수요 지표</h3><p>통계 연결 확인 필요</p>';signature='';}}
  }
  return {panel,householdShares,ageShares};
})();
