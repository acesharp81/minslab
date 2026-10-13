'use strict';
/* Read persisted relationships and source observations; never rematch on navigation. */
const ScopeEvidence=(()=>{
 const cache=new Map(),names={BUSINESS:'사업화',APPROVAL:'인허가',CONSTRUCTION:'건설',SUPPLY:'공급',COMPLETION:'준공',MOVE_IN:'입주 시작'};
 const e=v=>esc(String(v??'')),u=v=>v==null?'미확보':num(v)+'호';
 const fetchOnce=url=>{if(!cache.has(url))cache.set(url,request(url).catch(err=>{cache.delete(url);throw err;}));return cache.get(url);};
 const anchor=(url,label)=>url&&safeUrl(url)!=='#'?'<a href="'+e(safeUrl(url))+'" target="_blank" rel="noopener">'+e(label)+' ↗</a>':'원문 미연계';
 function fallback(item,row){
  const events=[];if(item?.notice_source_date&&item.current_notice_units!=null)events.push({stage:'SUPPLY',event_date:item.notice_source_date,units:item.current_notice_units,evidence_url:item.evidence_url,origin:'SOURCE'});
  if(row.start_actual_date)events.push({stage:'CONSTRUCTION',event_date:row.start_actual_date,units:row.planned_units,evidence_url:row.evidence_url,origin:'SOURCE'});
  return {...row,units:row.planned_units??row.supply_units??0,source_ids:[row.id],events,schedules:(item?.schedule_events||[]).map(s=>({...s,due_date:s.month+'-01',precision:'MONTH'}))};
 }
 async function mount(host,{kind,row,rows,geo,year,group}){
  if(!host||!row)return;const day=$('as-of').value,now=Number(day.slice(0,4)),selectedYear=year||now;
  host.innerHTML='<article class="pr-card"><p>선택 범위의 단계별 원천·일정을 확인합니다…</p></article>';
  try{
   const d=await fetchOnce('/policy-delivery?as_of_date='+day);if(!host.isConnected)return;
   const ids=new Set(rows.map(p=>p.id)),parentProgram=kind==='program'?row.id:row.mapping?.program_id;
   const ledger=(d.portfolio_cohorts||[]).filter(c=>c.program_id===parentProgram&&(c.source_ids||[c.id]).some(id=>ids.has(id)));
   const covered=new Set(ledger.flatMap(c=>c.source_ids||[c.id]));const chosen=new Set(group?.chart_target_ids||rows.map(p=>p.id));
   const extras=rows.filter(p=>!covered.has(p.id)&&chosen.has(p.id));const seen=new Set();
   const cohorts=[...ledger,...extras.map(p=>{const item=geo.items.find(i=>i.id===p.id);const c=fallback(item,p);if(item?.notice_evidence_id){if(seen.has(item.notice_evidence_id))c.events=c.events.filter(ev=>ev.stage!=='SUPPLY');seen.add(item.notice_evidence_id);}return c;})];
   const goals=(d.settings?.targets||[]).filter(t=>t.scope_kind===kind&&t.scope_id===row.id);
   const end=cohorts.flatMap(c=>c.schedules||[]).map(s=>s.due_date).filter(Boolean).sort().at(-1);
   const knownPlans=cohorts.filter(c=>c.planned_units!=null);const total=knownPlans.length?knownPlans.reduce((n,c)=>n+c.planned_units,0):null;
   const analysis=PolicyDecision.analyze(cohorts,day,selectedYear);
   const amount=(c,stage)=>{const ev=(c.events||[]).filter(v=>v.stage===stage&&v.origin!=='PLANNED'&&v.status!=='DELAYED'&&v.event_date<=analysis.day&&(v.units!=null||c.planned_units!=null));return ev.length?Math.min(c.units,Math.max(...ev.map(v=>v.units??c.units))):null;};
   const body=Object.entries(names).map(([stage,label])=>{const inferred=cohorts.some(c=>(c.events||[]).some(v=>v.stage===stage&&v.event_date<=analysis.day&&(v.method==='PREREQUISITE'||v.review_status==='REVIEW')));const actuals=cohorts.map(c=>amount(c,stage)).filter(v=>v!=null),actual=actuals.length?actuals.reduce((a,b)=>a+b,0):null,targets=goals.filter(t=>t.stage===stage).sort((a,b)=>a.due_date.localeCompare(b.due_date)),goal=targets.filter(t=>t.due_date<=analysis.day).at(-1),last=targets.at(-1),dates=cohorts.flatMap(c=>c.schedules||[]).filter(s=>s.stage===stage).map(s=>s.due_date).sort();
    return '<div class="psr-stage"><b>'+label+'</b><strong>'+u(actual)+'</strong><span>선택연도까지 '+(inferred?'확인·추정 누적':'확인 누적')+'</span><small>등록 목표 '+u(goal?.units)+' · 최종 '+u(last?.units)+(last?' / '+e(last.due_date):'')+'</small><small>연결 예정 '+e(dates.length?dates[0]+' ~ '+dates.at(-1):'미확보')+'</small>'+(goal&&actual!=null&&goal.units>0?'<progress max="'+goal.units+'" value="'+Math.min(goal.units,actual)+'"></progress><small>등록 목표 대비 '+(actual/goal.units*100).toFixed(1)+'%</small>':'')+'</div>';}).join('');
   host.innerHTML='<article class="pr-card psr-scope" data-scope-id="'+e(row.id)+'"><div class="pr-card-head"><h3>'+e(row.name)+' · 목표와 진행 근거</h3><a href="#requirements">총리님 요구사항 매핑 →</a></div><div class="pd-kpis"><div><span>선택 범위 사업계획</span><b>'+u(total)+'</b><small>'+cohorts.length+'개 원장 · 상위 정책 목표와 구분</small></div><div><span>공급 확인 누적</span><b>'+u(analysis.suppliedUnits)+'</b><small>'+e(analysis.day)+'까지</small></div><div><span>마지막 확보 예정일</span><b>'+e(end||'미확보')+'</b><small>전체 완료 확정일과 구분</small></div><div><span>단계별 등록 목표</span><b>'+goals.length+'건</b><small>해당 '+(kind==='program'?'프로그램':'사업')+'에 직접 등록된 목표</small></div></div><div class="psr-stage-grid">'+body+'</div><p class="pr-note">단계별 누적은 동일 물량이 여러 단계에 포함되므로 합산하지 않습니다. 사업화·인허가 선행단계 추정은 아래 근거에 표시합니다. 입주는 시작 확인 사업의 물량이며 실입주 가구 수가 아닙니다.</p><button data-view="tree">목표·연결·일정 검토 및 입력 →</button></article><div data-scope-records></div><div data-scope-location></div><div data-scope-decisions></div>';
   const decisions=host.querySelector('[data-scope-decisions]');PolicyDecision.render(decisions,{data:{...d,policy_id:row.policy_id||row.mapping?.policy_id},cohorts,scope:row.name,year:selectedYear});
   DeliveryOperations.mountPolicy(cohorts.flatMap(c=>c.source_ids||[c.id]),decisions.querySelector('#policy-execution-panel'));
   if(kind==='project'){
    const rec=host.querySelector('[data-scope-records]');
    const evidence=cohorts.flatMap(c=>[...(c.events||[]).map(v=>({...v,date:v.event_date,type:v.origin==='PLANNED'?'예정':v.method==='PREREQUISITE'?'선행단계 추정 · 검토 필요':'확인 기록'})),...(c.schedules||[]).map(v=>({...v,date:v.due_date,type:'예정 · '+(v.precision==='MONTH'?'월 기준':'원천 일정')}))]).sort((a,b)=>(a.date||'').localeCompare(b.date||''));
    rec.innerHTML='<article class="pr-card"><h3>사업별 단계·일정 원장</h3><div class="pd-table-scroll"><table><thead><tr><th>단계</th><th>일자 / 관측일</th><th>물량</th><th>구분 / 근거</th></tr></thead><tbody>'+evidence.map(v=>'<tr><td>'+e(names[v.stage]||v.stage)+'</td><td>'+e(v.date||'사건일 미확보')+(v.date_basis==='OBSERVED_BY'?'<small>해당일까지 도달 추정 · 사건일 미확보</small>':'')+'</td><td>'+u(v.units)+'</td><td>'+e(v.type)+'<small>'+e(v.basis||v.source_id||'원천 기록')+'</small>'+anchor(v.evidence_url,'근거')+'</td></tr>').join('')+'</tbody></table>'+(evidence.length?'':'<p>연결된 단계 기록 미확보</p>')+'</div></article><article class="pr-card" data-scope-history><h3>수집·연결 변경 이력</h3><p>변경 이력을 조회합니다…</p></article>';
    ProjectLocation.mount(host.querySelector('[data-scope-location]'),row,geo);
    try{const detail=await fetchOnce('/projects/'+encodeURIComponent(row.id)+'?as_of_date='+day);if(!host.isConnected)return;rec.querySelector('[data-scope-history]').innerHTML='<h3>수집·연결 변경 이력</h3><div class="pd-table-scroll"><table><thead><tr><th>판본 / 수집일</th><th>원천 기준일</th><th>계획량 / 진행</th></tr></thead><tbody>'+(detail.history||[]).map(h=>'<tr><td>#'+h.revision_no+' · '+e(h.recorded_at)+'</td><td>'+e(h.base_date||'미확보')+'</td><td>'+u(h.values?.planned_units)+'<small>'+e(h.values?.stage_label||h.values?.stage||'')+'</small></td></tr>').join('')+'</tbody></table></div><p>DB 연결 변경 '+(detail.mapping_history||[]).length+'건 · <button data-view="tree">정책–프로그램–사업 연결에서 판본 검토 →</button></p>';}
    catch(err){if(rec.isConnected)rec.querySelector('[data-scope-history]').textContent='이력 조회 실패: '+err.message;}
   }
  }catch(err){if(host.isConnected)host.innerHTML='<article class="pr-card">단계별 근거 조회 실패: '+e(err.message)+'</article>';}
 }
 return {mount};
})();
