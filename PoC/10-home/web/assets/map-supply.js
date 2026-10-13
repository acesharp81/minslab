'use strict';
const MapSupply=(()=>{
  let data,grouping='policy',groupId='',redraw,refit;
  const textUnits=value=>value==null?'미확보':num(value)+'호';
  const units=value=>value==null?'<span class="quantity-unknown">미확보</span>':num(value)+'<small>호</small>';
  const cell=value=>value.start_date?`<b>${esc(value.start_date)} 입주 시작 예정</b><small>호수·달성률 집계 제외</small>`:`<b>${units(value.source_units)}</b>${value.source_units!=null?`<small>확보 일정 ${num(value.source_events)}개 · 누적</small>`:''}${value.manual_units!=null?`<small class="quantity-manual">관리자 ${num(value.manual_units)}호</small>`:''}${value.units_missing_events?'<small>일부 물량 미확보</small>':''}`;
  const currentCell=value=>`<b>${units(value.current_notice_units)}</b><small>${value.current_notice_units!=null?'LH 본 모집공고 확인 · 연결 검토':'연결된 본 모집공고 미확보'}</small><small>실입주·정책 실적 미확보</small>`;
  function active(){return data?.groups[grouping].find(row=>row.id===groupId);}
  function filter(rows){const group=active();return group?rows.filter(row=>group.project_ids.includes(row.id)):rows;}
  function set(value){data=value;if(groupId&&!active())groupId='';}
  function render(value){
    set(value);MapStageRing.legend();const groups=data.groups[grouping],offsets=Array.from({length:data.horizon},(_,index)=>index+1);
    $('map-group-select').innerHTML='<option value="">전체 그룹</option>'+groups.map(row=>`<option value="${esc(row.id)}">${esc(row.name)}</option>`).join('');$('map-group-select').value=groupId;
    document.querySelectorAll('[data-map-group]').forEach(button=>{button.classList.toggle('selected',button.dataset.mapGroup===grouping);button.setAttribute('aria-pressed',String(button.dataset.mapGroup===grouping));});
    const visible=active()?[active()]:groups;
    $('map-supply-table').innerHTML=`<table class="map-supply-table"><thead><tr><th>${{policy:'정책',program:'프로그램',region:'지역'}[grouping]} · 지도 선택</th><th>목표·계획 물량</th><th>현재 공급량<small>모집공고 확인 · 연결 검토</small></th>${offsets.map(offset=>`<th>향후 ${offset}년 내<small>~${data.analysis_year+offset}년 말 · ${esc(data.measure_label)}</small></th>`).join('')}</tr></thead><tbody>${visible.map(row=>`<tr class="${row.id===groupId?'selected':''}"><th><button data-map-group-id="${esc(row.id)}">${esc(row.name)}</button><small>원천 사업 ${num(row.project_count)}건</small></th><td><b>${units(row.announced_target_units??row.target_units)}</b><small>${row.announced_target_units!=null?esc(row.target_metric)+' · '+esc(row.target_scope):'확보 계획량 · 검토 합계'}</small>${row.announced_target_units!=null?`<small>수도권 사업계획 ${textUnits(row.target_units)}</small>`:''}<small>${num(row.target_counted_projects)}건 집계 · 중복/모호 ${num(row.target_excluded_projects)}건 제외</small></td><td>${currentCell(row)}</td>${offsets.map(offset=>`<td>${cell(row.future[offset-1])}</td>`).join('')}</tr>`).join('')||`<tr><td colspan="${3+offsets.length}">${data.analysis_year}년의 연결된 사업 자료가 없습니다. 지도 옆에서 정책 발표와 공고 이력을 확인하세요.</td></tr>`}</tbody></table>`;
    $('map-supply-note').textContent=data.reference_date+' 자료 기준 · '+data.future_basis+' · '+data.notice;
    $('map-analysis-year').innerHTML=Array.from({length:data.current_year-data.start_year+1},(_,index)=>data.start_year+index).map(value=>`<option value="${value}">${value}년${value===data.current_year?' (현재)':''}</option>`).join('');$('map-analysis-year').value=data.analysis_year;
    $('roadmap-export').hidden=data.analysis_year<data.current_year;$('roadmap-export').textContent='현재 사업 목표 CSV ↓';
    const csvParams=new URLSearchParams(window.query());
    for(const [key,value] of new URLSearchParams(query()))csvParams.set(key,value);
    csvParams.set('group_by',grouping);if(groupId)csvParams.set('group_id',groupId);
    $('supply-export').href=API+'/map/supply.csv?'+csvParams.toString();
  }
  function panels(){
    const selected=active(),quantity=selected||data.summary;
    const fact=(label,n)=>n==null?'':`<dt>${label}</dt><dd>${units(n)}</dd>`;
    $('map-policy-summary').innerHTML=`<h3><span class="map-summary-icon">◎</span>${esc(selected?.name||'수도권 공급량')}</h3><dl>${fact('확보 사업계획 · 검토',quantity.target_units)}${fact('현재 모집공고 확인',quantity.current_notice_units)}${quantity.future.slice(0,3).filter(item=>item.source_units!=null||item.manual_units!=null).map(item=>`<dt>${item.offset}년 내 ${esc(data.measure_label)}</dt><dd>${item.source_units!=null?units(item.source_units):''}${item.manual_units!=null?`<small class="quantity-manual">관리자 ${num(item.manual_units)}호</small>`:''}</dd>`).join('')}</dl><p>기준 ${data.reference_date} · 연도 말 누적 예정<br>공고 연결 검토 ${num(quantity.current_notice_count)}건 · 사전·잔여·추가 제외</p>`;
    $('map-policy-summary').insertAdjacentHTML('beforeend',MapStageRing.details(quantity));
    const history=data.history;
    const progress=quantity.progress;
    const issueButton=id=>{const row=data.items.find(item=>item.id===id);return row?`<button class="map-issue-link" data-map-project="${esc(id)}">${esc(row.name)} ↗</button>`:'';};
    $('map-policy-summary').insertAdjacentHTML('beforeend',`<div class="map-progress-issues">${progress.year_to_date_goal_units!=null?`<h4>올해 누적 ${esc(data.measure_label)} 목표 ${textUnits(progress.year_to_date_goal_units)}</h4>`:''}${progress.annual_manual_goal_units!=null?`<p>연간 관리자 목표 ${textUnits(progress.annual_manual_goal_units)} · 별도</p>`:''}${progress.late_count?`<b class="bar-status late">공고월 지연 확인 ${num(progress.late_count)}건 · 연결 검토</b>${progress.late_projects.map(issueButton).join('')}`:''}${progress.verification_count?`<details><summary>예정 경과 · 이행 확인 필요 ${num(progress.verification_count)}건</summary>${progress.verification_project_ids.map(issueButton).join('')}</details>`:''}<p>계획과 공고 날짜로 확인된 모집 일정 지연입니다. 준공·입주 지연은 실제 이행 자료 확보 후 판단합니다.</p></div>`);
    if(progress.schedule_gap_count)$('map-policy-summary').querySelector('.map-progress-issues').insertAdjacentHTML('afterbegin',`<p class="bar-status pending">지연 후보 ${num(progress.schedule_gap_count)}건 · 계획 대비 공고 최대 +${progress.max_gap_months}개월 · 연간 계획의 발표 이력 확인 필요</p>${progress.schedule_gap_project_ids.map(issueButton).join('')}`);
    $('map-policy-summary').querySelector('.map-progress-issues>p:last-child').textContent='공고월 차이는 계획 기준일의 정밀도와 발표 이력을 함께 검토합니다. 준공·입주 지연은 실제 이행 자료 확보 후 판단합니다.';
    $('map-history-summary').innerHTML=`<h3>${data.analysis_year}년 과거·원천 자료</h3><div class="map-history-counts"><span>공고 <b>${num(history.notice_count)}</b></span><span>인허가 <b>${num(history.permit_count)}</b></span><span>공사 <b>${num(history.report_rows)}행</b></span></div>${history.events.map(event=>`<a class="map-flow-event" href="${esc(safeUrl(event.evidence_url))}" target="_blank" rel="noopener"><small>${esc(event.event_date)}</small>${esc(event.name)} ↗</a>`).join('')||''}${history.report_dates.length?`<p>보고 기준: ${history.report_dates.join(', ')}</p>`:''}${grouping==='region'?data.groups.region.filter(row=>!groupId||row.id===groupId).map(row=>`<details class="map-market-reference"><summary>${({'서울특별시':'서울','인천광역시':'인천','경기도':'경기'}[row.name]||row.name)} 청약시장 참고 · 정책 미연결</summary><p>모집공고 확인 공급세대수 <b>${textUnits(row.market.announced_units)}</b> · ${num(row.market.notice_count)}개 주택관리번호 · ${data.reference_date}까지 누적</p>${row.market.future_move_in.slice(0,3).map(item=>`<p>${item.offset}년 내 공고상 입주 시작 예정 <b>${esc(item.start_date||'일정 미정')}</b> · ${num(item.notice_count)}개 공고</p>`).join('')}<p>${esc(row.market.basis)}</p></details>`).join(''):''}<a class="map-history-link" href="#history">연도별 원문·전체 누적 이력 ↗</a>`;
    $('map-region-cards').innerHTML=data.groups.region.map(region=>{
      const quantity=groupId?region.group_quantities[grouping][groupId]:region;
      if(!quantity?.project_count&&groupId)return '';
      return `<button class="map-region-card" data-map-region="${esc(region.id)}"><strong>▥ ${({'서울특별시':'서울','인천광역시':'인천','경기도':'경기'}[region.name]||region.name)}</strong><span>계획 · 검토 <b>${textUnits(quantity.target_units)}</b></span><span>공고 확인 · 검토 <b>${textUnits(quantity.current_notice_units)}</b></span><span>1년 내 ${esc(data.measure_label)} <b>${textUnits(quantity.future[0].source_units)}</b></span></button>`;
    }).join('');
  }
  function districtQuantity(district){return groupId?district.group_quantities?.[grouping]?.[groupId]||{target_units:null,future:[{source_units:null}]}:district.quantities;}
  function districtPanel(district){
    const quantity=districtQuantity(district),items=quantity.future.slice(0,3).filter(item=>item.source_units!=null);
    return items.length?`<div class="map-district-quantity"><b>선택 지구 · ${esc(data.measure_label)} 예정</b>${items.map(item=>`<span>${item.offset}년 내 <strong>${units(item.source_units)}</strong></span>`).join('')}</div>`:'';
  }

  function start(draw,fit,changeYear){
    redraw=draw;
    refit=fit;
    $('map-group-select').addEventListener('change',event=>{groupId=event.target.value;draw();fit();});
    $('map-measure').addEventListener('change',()=>{MapStageRing.legend();draw();});$('map-analysis-year').addEventListener('change',event=>changeYear(event.target.value));
    document.addEventListener('click',event=>{
      const tab=event.target.closest('[data-map-group]');if(tab){grouping=tab.dataset.mapGroup;groupId='';draw();fit();}
      const group=event.target.closest('[data-map-group-id]');if(group){groupId=groupId===group.dataset.mapGroupId?'':group.dataset.mapGroupId;draw();fit();}
    });
  }
  function query(){const params=new URLSearchParams({horizon:$('roadmap-horizon').value,measure:'SUPPLY',schedule_status:$('roadmap-status').value});const value=$('map-analysis-year').value;if(value&&Number(value)<Number($('as-of').value.slice(0,4)))params.set('analysis_year',value);return params.toString();}
  function reset(){groupId='';$('map-analysis-year').value='';}
  function select(kind,id){grouping=kind;groupId=id;redraw();refit();}
  return {set,render,panels,filter,start,query,reset,textUnits,districtQuantity,districtPanel,active,selection:()=>({kind:grouping,id:groupId}),select};
})();
