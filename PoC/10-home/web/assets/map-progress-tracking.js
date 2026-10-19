'use strict';
// Narrow map summaries reuse the canonical stage ledger, with no time-axis scrolling.
const MapProgressTracking=(()=>{
 const order=['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],colors={BUSINESS:'#a66b00',APPROVAL:'#0072b2',CONSTRUCTION:'#d55e00',SUPPLY:'#00856a',MOVE_IN:'#7a3e9d'};
 const units=v=>v==null?'미측정':num(v)+'호';
 let signature='',ticket=0,timer,refreshed=0;
 function checks(data){return order.map(stage=>PolicyStageFlow.comparisonStatus({comparisons:data.comparisons,stages:data.stages,asOf:data.as_of_date,delays:data.delays},stage));}
 function periodLabel(period){
  const month=value=>{const match=/^(\d{4})-(\d{2})(?:-\d{2})?$/.exec(value||'');return match?match[1]+'.'+Number(match[2])+'.':'';};
  const start=month(period?.start),end=month(period?.end);return start&&end&&start!==end?start+'~'+end:start||end;
 }
 function summary(data,label){
  return '<div class="map-compact-stages"><div style="--stage-color:#718096"><small>'+esc(label)+' · 전체 목표</small><b>'+units(data.policy_target)+'</b></div>'+order.map(stage=>{
   const metric=data.comparisons[stage]||{},points=metric.display_actual_points||metric.actual_points||[],actual=points.filter(p=>p.date<=data.as_of_date).slice().sort((a,b)=>a.date.localeCompare(b.date)).at(-1),period=periodLabel(metric.actual_period),check=PolicyStageFlow.comparisonStatus({comparisons:{[stage]:{...metric,actual_points:points}},asOf:data.as_of_date},stage);
   return '<div style="--stage-color:'+colors[stage]+'" data-map-stage="'+stage+'"><small>'+esc(metric.label||data.stages?.[stage]||stage)+'</small><b>'+units(actual?.units)+'</b>'+(period?'<span class="map-stage-period">'+esc(period)+'</span>':'')+(actual?.inferred_units?'<span>추정 포함 '+units(actual.inferred_units)+'</span>':'')+(check.gap>0?'<span class="gap-management '+check.status.toLowerCase()+'">'+check.assessment.label+' · 부족 '+num(check.gap)+'호 ('+PolicyStageFlow.formatGapRate(check.rate)+')</span>':'')+'</div>';
  }).join('')+'</div>';
 }
 function detailTable(title,headings,body,extra=''){
  return '<table class="map-project-table '+extra+'"><caption>'+esc(title)+'</caption><thead><tr>'+headings.map(h=>'<th scope="col">'+esc(h)+'</th>').join('')+'</tr></thead><tbody>'+body+'</tbody></table>';
 }
 function conditionsHtml(data){
  const c=data.supply_conditions||{},groups=c.groups||[],prices=c.prices||[];
  const link=url=>url?'<a href="'+esc(safeUrl(url))+'" target="_blank" rel="noopener">원문 ↗</a>':'';
  const groupHtml=groups.map(g=>'<article><div class="map-condition-heading"><b>'+esc(g.name)+' <span>'+units(g.units)+'</span></b>'+link(g.source_url)+'</div>'+((g.areas||[]).length?detailTable('주택형별 공급',['전용면적','공급 호수'],g.areas.map(a=>'<tr><td>'+(a.area?esc(a.area)+'㎡':'미수집')+'</td><td class="map-table-number">'+(a.units==null?'미수집':units(a.units))+'</td></tr>').join(''),'map-condition-areas'):'<p class="map-table-empty">면적별 호수 미수집</p>')+(g.area_total!=null&&g.area_total!==g.units?'<small>면적별 공급계획 합계 '+units(g.area_total)+' · 총 목표와 범위가 다릅니다.</small>':'')+'</article>').join('');
  const facts='<table class="map-project-table map-condition-facts"><caption>사업 관계자</caption><tbody>'+[['시행기관',c.developer],['사업부서',c.departments?.join(' · ')],['시공업체',c.contractors?.join(' · ')]].map(([label,value])=>'<tr><th scope="row">'+label+'</th><td>'+esc(value||'미수집')+'</td></tr>').join('')+'</tbody></table>';
  const sources=[];for(const p of prices){const key=(p.source_date||'')+'|'+(p.source_url||'');if(!sources.some(v=>v.key===key))sources.push({key,date:p.source_date,url:p.source_url});}
  const priceHtml=prices.length?detailTable('분양가',['전용면적',prices.every(p=>p.area)?'평균 분양가':'분양가'],prices.map(p=>{const i=sources.findIndex(v=>v.key===(p.source_date||'')+'|'+(p.source_url||''));return '<tr><td>'+(p.area?esc(p.area)+'㎡':'—')+'</td><td class="map-table-number">'+esc(p.value)+(sources.length>1?'<sup class="map-price-reference">['+(i+1)+']</sup>':'')+'</td></tr>';}).join(''),'map-condition-prices')+'<div class="map-price-sources">'+sources.map((v,i)=>'<small>'+(sources.length>1?'['+(i+1)+'] ':'')+(v.date?esc(v.date)+' 공고 기준 ':'')+link(v.url)+'</small>').join('')+'</div>':'<p class="map-table-empty">분양가 원문 미수집</p>';
  return '<section class="map-supply-conditions"><h4>분양·임대 조건</h4>'+groupHtml+facts+priceHtml+'</section>';
 }
 function scheduleHtml(data){
  const actual=data.progress_defaults||{},labels=data.schedule_stages||{};
  return detailTable('단계별 일정',['단계','목표','실적'],Object.entries(labels).map(([key,label])=>'<tr><th scope="row">'+esc(label)+'</th><td>'+esc(data.target_defaults?.[key]?.due_date||'미확보')+'</td><td'+(!actual[key]?.event_date?' class="map-table-pending"':'')+'>'+esc(actual[key]?.event_date||(actual[key]?.not_due?'미도래':'미측정'))+'</td></tr>').join(''),'map-project-schedule');
 }
 async function projectInfo(host,ids,current){
  if(!ids.length){host.innerHTML='<p>연결된 개별 사업 미확보</p>';return;}
  try{const data=await request('/project-information/'+encodeURIComponent(ids[0]));if(current!==ticket||!host.isConnected)return;
   const p=data.project,stage=ProjectWorkspace.currentStage(data),actual=data.progress_defaults||{};
   host.innerHTML='<h4>'+esc(p.name)+'</h4><p class="map-project-stage">현재 '+esc(data.stages[stage]||'단계 미확인')+' · '+esc(p.developer||'시행사 미확보')+'</p><div class="map-project-quantities"><span>총 목표 <b>'+units(p.planned_units)+'</b></span><span>공급 <b>'+units(actual.SUPPLY?.units)+'</b></span><span>입주 <b>'+units(actual.MOVE_IN?.units)+'</b></span></div>'+conditionsHtml(data)+scheduleHtml(data)+'<button type="button" data-map-project-open="'+esc(p.id)+'">사업 상세·입력값 보기 ↗</button>'+(ids.length>1?'<p class="trend-note">이 블록에 '+ids.length+'개 원천 사업이 연결되어 있습니다.</p><select aria-label="블록 내 사업 선택" data-map-linked-project>'+ids.map(id=>'<option value="'+esc(id)+'">'+esc(id===p.id?p.name:id)+'</option>').join('')+'</select>':'');
   host.querySelector('[data-map-project-open]').onclick=()=>ProjectWorkspace.select(p.id);
   const select=host.querySelector('[data-map-linked-project]');if(select)select.onchange=()=>projectInfo(host,[select.value,...ids.filter(id=>id!==select.value)],current);
  }catch(error){if(current===ticket&&host.isConnected)host.innerHTML='<p>사업 상세 연결 확인 필요 · '+esc(error.message)+'</p>';}
 }
 function render(node,data,chosen,supply,selection,ids,current){
  if(!data.comparisons){node.innerHTML='<h3>추진현황</h3><p>'+esc(data.notice||'선택 기준일 자료 미확보')+'</p>';return;}
  const name=chosen.level==='block'?chosen.row.district_name+' · '+chosen.row.block:chosen.row.name;
  const programs=supply.groups.program.filter(p=>p.project_count>0),quantity=chosen.quantity;
  const select='<label class="map-progress-program">프로그램<select data-map-progress-program><option value="">9·7 정책 전체</option>'+programs.map(p=>'<option value="'+esc(p.id)+'" '+(selection.kind==='program'&&selection.id===p.id?'selected':'')+'>'+esc(p.name)+'</option>').join('')+'</select></label>';
  const bars=chosen.level==='region'&&selection.kind!=='program'&&quantity?.progress&&quantity?.projection?'<details class="map-original-supply" open><summary>공급 계획·공고 막대 현황</summary>'+SupplyBars.chart({...quantity,name},true,true)+'</details>':'';
  node.innerHTML='<div class="map-compact-progress" data-map-scope="'+chosen.level+'"><h3>'+(chosen.level==='block'?'개별 사업 추진현황':selection.kind==='program'?'프로그램 추진현황':'정책 추진현황')+'</h3>'+select+'<div class="trend-heading"><div><small>'+esc(chosen.scopeLabel||({region:'시도',municipality:'시군구',block:'사업 블록'}[chosen.level]))+' · '+(chosen.automatic?'지도 중심':'선택됨')+'</small><h4>'+esc(name)+'</h4></div><span>'+num(data.project_count)+'개 사업</span></div>'+summary(chosen.level==='block'&&quantity?.target_units!=null?{...data,policy_target:quantity.target_units}:data,chosen.level==='block'?'사업':selection.kind==='program'?'프로그램':'정책')+bars+(chosen.level==='block'?'<section class="map-selected-project"><p>개별 사업 정보를 불러옵니다…</p></section>':'')+'<p class="pw-axis-note">'+esc(data.as_of_date)+' 기준 · 측정은 담당자 입력·추정 포함. 단계 카드는 해당 단계의 실적이며 서로 합산하지 않습니다. 날짜는 해당 단계에서 확인된 시점만 표시합니다. 추진 그래프는 후속 단계 포함 누적량입니다.</p>'+(data.unmatched_count?'<p class="pw-axis-note">원장 미연결 '+num(data.unmatched_count)+'건 집계 제외</p>':'')+'</div>';
  node.querySelector('[data-map-progress-program]').onchange=e=>MapSupply.select(e.target.value?'program':'policy',e.target.value||'POL_2025_0907');
  if(chosen.level==='block'){const selectedId=document.querySelector('.map-3d-block-marker.selected')?.dataset.mapBarProject;const ordered=ids.includes(selectedId)?[selectedId,...ids.filter(id=>id!==selectedId)]:ids;projectInfo(node.querySelector('.map-selected-project'),ordered,current);}
  const method=document.getElementById('map-method-summary');if(method)method.textContent='정책·프로그램과 동일한 단계별 원장입니다. 기본 범위에서는 정책·프로그램 전체, 확대하면 시군구·블록 범위를 표시합니다. 공급 공고 막대는 원천 계획·공고 기준이며 담당자 추정 포함 측정량과 구분됩니다.';
 }
 function panel(supply,viewport){
  const node=document.getElementById('map-policy-monitor'),selection=MapSupply.selection();let chosen=MapTrends.scope(supply,viewport,selection);
  if(!node)return;
  const selected=MapSupply.active();
  if(viewport?.level==='region'&&selection.kind!=='region'){
   const group=selected||supply.groups.policy.find(p=>p.id==='POL_2025_0907');
   if(group)chosen={level:'region',row:{...group,name:group.name},quantity:group,automatic:false,scopeLabel:selection.kind==='program'?'프로그램 전체':'정책 전체'};
  }
  if(!chosen){ticket++;clearTimeout(timer);signature='';node.innerHTML='<h3>추진현황</h3><p>현재 지도 범위에 연결된 사업이 없습니다.</p>';return;}
  let ids=chosen.quantity.project_ids||chosen.row.project_ids||[];if(selected)ids=ids.filter(id=>selected.project_ids.includes(id));
  const region=chosen.scopeLabel?null:chosen.level==='region'?chosen.row.id:chosen.row.region;
  const qs=new URLSearchParams({as_of_date:supply.reference_date||document.getElementById('as-of').value,level:chosen.level});
  if(region)qs.set('region',region);if(selection.kind==='program'&&selection.id)qs.set('program_id',selection.id);
  [...new Set(ids)].sort().forEach(id=>qs.append('project_ids',id));
  const key=qs.toString();if(key===signature&&Date.now()-refreshed<20000)return;
  signature=key;refreshed=Date.now();const current=++ticket;clearTimeout(timer);
  node.innerHTML='<h3>추진현황</h3><p>선택 범위의 목표·측정값을 조회합니다…</p>';
  timer=setTimeout(async()=>{try{const data=await request('/map/progress?'+key);if(current===ticket)render(node,data,chosen,supply,selection,ids,current);}catch(error){if(current===ticket){signature='';node.innerHTML='<h3>추진현황</h3><p>'+esc(error.message)+'</p>';}}},180);
 }
 return {panel,checks,conditionsHtml,summary,periodLabel};
})();
