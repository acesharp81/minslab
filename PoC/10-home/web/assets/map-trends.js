'use strict';
// Geographic supply trends use the same canonical project IDs as the API's
// aggregates. An observed notice is a reviewed evidence lower bound, never
// physical completion or move-in.
const MapTrends=(()=>{
  const known=value=>Number.isFinite(value)&&value>=0;
  const units=value=>known(value)?num(value)+'호':'미확보';
  const pct=(value,total)=>known(value)&&known(total)&&total>0?(100*value/total).toFixed(1)+'%':'미확보';
  const add=(map,year,value)=>{if(!Number.isInteger(year)||!known(value))return;map.set(year,(map.get(year)||0)+value);};
  const radius=(a,b)=>{const east=(a.longitude-b.lng)*Math.cos(b.lat*Math.PI/180),north=a.latitude-b.lat;return east*east+north*north;};
  function quantityFor(row,selection){
    return selection.id?row.group_quantities?.[selection.kind]?.[selection.id]:row.quantities||row;
  }
  function scope(data,viewport,selection){
    const level=viewport?.level||'block',center=viewport?.center||{lng:127.02,lat:37.52};
    let candidates;
    if(level==='region'){
      candidates=data.groups.region.map(row=>({row,quantity:quantityFor(row,selection),point:(()=>{
        const areas=data.municipalities.filter(area=>area.region===row.id&&Number.isFinite(area.latitude)&&Number.isFinite(area.longitude)&&area.project_ids.some(id=>row.project_ids.includes(id)));
        return areas.length?{latitude:areas.reduce((sum,area)=>sum+area.latitude,0)/areas.length,longitude:areas.reduce((sum,area)=>sum+area.longitude,0)/areas.length}:null;
      })()}));
    }else if(level==='municipality'){
      candidates=data.municipalities.map(row=>({row,quantity:quantityFor(row,selection),point:row}));
    }else{
      candidates=data.blocks.map(row=>({row,quantity:quantityFor(row,selection),point:row}));
    }
    candidates=candidates.filter(entry=>entry.quantity?.project_count&&Number.isFinite(entry.point?.latitude)&&Number.isFinite(entry.point?.longitude));
    if(!candidates.length)return null;
    const explicit=level==='region'?viewport?.regionId:level==='municipality'?viewport?.municipalityId:viewport?.explicitBlockId;
    const chosen=candidates.find(entry=>entry.row.id===explicit)||candidates.sort((a,b)=>radius(a.point,center)-radius(b.point,center))[0];
    return {...chosen,level,automatic:chosen.row.id!==explicit};
  }
  function derive(data,quantity){
    const byId=new Map(data.items.map(item=>[item.id,item]));
    const targetIds=quantity.chart_target_ids||[];
    const scheduleIds=quantity.chart_schedule_ids||[];
    const manualIds=quantity.chart_manual_ids||[];
    const planned=new Map(),estimated=new Set(),manual=new Map(),observed=new Map();
    let missingSchedule=0,futureThisYear=0;
    for(const id of new Set([...scheduleIds,...targetIds.filter(id=>byId.get(id)?.supply_year_range)])){
      const item=byId.get(id);if(!item)continue;
      const sourceEvents=[...(item.earlier_events||[]),...(item.annual||[]).flatMap(year=>year.events||[])]
        .filter(event=>event.stage===data.measure&&event.origin==='SOURCE');
      for(const event of sourceEvents){
        if(known(event.units)){
          add(planned,event.year,event.units);
          if(data.measure==='SUPPLY'&&event.year===data.analysis_year&&event.month>data.reference_date.slice(0,7)
              &&!byId.get(id)?.notice_evidence)futureThisYear+=event.units;
        }else missingSchedule++;
      }
      // Preserve dated quantities. Only the remaining units in an evidenced
      // year range are spread over years that have no dated quantity.
      const range=item.supply_year_range;
      if(data.measure==='SUPPLY'&&range&&Number.isInteger(range.start_year)&&Number.isInteger(range.end_year)
          &&range.end_year>=range.start_year&&range.end_year-range.start_year<30&&Number.isInteger(range.units)&&range.units>=0){
        const dated=sourceEvents.filter(event=>known(event.units)&&event.year>=range.start_year&&event.year<=range.end_year);
        const datedYears=new Set(dated.map(event=>event.year));
        const undatedYears=Array.from({length:range.end_year-range.start_year+1},(_,index)=>range.start_year+index)
          .filter(year=>!datedYears.has(year));
        const remaining=Math.max(0,range.units-dated.reduce((sum,event)=>sum+event.units,0));
        if(remaining&&undatedYears.length){
          const base=Math.floor(remaining/undatedYears.length),remainder=remaining%undatedYears.length;
          undatedYears.forEach((year,index)=>{add(planned,year,base+(index<remainder?1:0));estimated.add(year);});
        }
      }
    }
    for(const id of manualIds){
      const item=byId.get(id);if(!item)continue;
      for(const event of [...(item.earlier_events||[]),...(item.annual||[]).flatMap(year=>year.events||[])])
        if(event.stage===data.measure&&event.origin==='MANUAL')add(manual,event.year,event.units);
    }
    if(data.measure==='SUPPLY'){
      const noticeIds=new Set();
      for(const id of targetIds){
        const notice=byId.get(id)?.notice_evidence;
        if(!notice?.source_date||!known(notice.units)||noticeIds.has(notice.id))continue;
        noticeIds.add(notice.id);add(observed,Number(notice.source_date.slice(0,4)),notice.units);
      }
    }
    // The selected year is the fifth of ten columns in every geographic scope.
    // Evidence before the visible window still feeds the cumulative lines.
    const first=data.analysis_year-4;
    const years=Array.from({length:10},(_,index)=>first+index);
    const before=(map)=>[...map].filter(([year])=>year<first);
    let plannedTotal=before(planned).reduce((sum,[,value])=>sum+value,0);
    let observedTotal=before(observed).reduce((sum,[,value])=>sum+value,0);
    let hasPlan=before(planned).length>0,hasObserved=before(observed).length>0;
    const rows=years.map(year=>{
      const p=planned.get(year),o=observed.get(year);if(p!=null){plannedTotal+=p;hasPlan=true;}if(o!=null){observedTotal+=o;hasObserved=true;}
      return {year,planned:p??null,manual:manual.get(year)??null,observed:o??null,
        plannedCumulative:hasPlan?plannedTotal:null,observedCumulative:hasObserved&&year<=data.analysis_year?observedTotal:null,
        estimated:estimated.has(year)};
    });
    return {rows,missingSchedule,futureThisYear,
      unallocated:known(quantity.target_units)&&planned.size?Math.max(0,quantity.target_units-[...planned.values()].reduce((sum,value)=>sum+value,0)):null};
  }
  function chart(data,quantity,series){
    const rows=series.rows,target=quantity.target_units,first=rows[0].year;
    const width=Math.max(318,rows.length*27+45),height=234,left=43,top=18,bottom=190,right=12;
    const plotWidth=width-left-right,plotHeight=bottom-top;
    const scale=Math.max(1,target||0,...rows.flatMap(row=>[row.plannedCumulative||0,row.observedCumulative||0,row.planned||0,row.observed||0]));
    const x=index=>left+plotWidth*(index+.5)/rows.length;
    const y=value=>bottom-Math.min(1,value/scale)*plotHeight;
    const currentIndex=rows.findIndex(row=>row.year===data.analysis_year);
    const currentBand=currentIndex<0?'':`<rect class="trend-current-band" x="${left+plotWidth*currentIndex/rows.length}" y="${top}" width="${plotWidth/rows.length}" height="${bottom-top+21}"/><path class="trend-current-line" d="M${x(currentIndex)} ${top}V${bottom}"/>`;
    const ticks=[0,.25,.5,.75,1].map(t=>`<g><path d="M${left} ${y(scale*t)}H${width-right}" stroke="#e6edf6"/><text x="${left-5}" y="${y(scale*t)+3}" text-anchor="end">${num(Math.round(scale*t))}</text></g>`).join('');
    const targetLine=known(target)?`<path d="M${left} ${y(target)}H${width-right}" class="trend-target"/><text x="${width-right-2}" y="${Math.max(12,y(target)-4)}" text-anchor="end" class="trend-target-label">목표 ${num(target)}</text>`:'';
    const bars=rows.map((row,index)=>{
      const center=x(index),plan=known(row.planned)?`<rect x="${center-8}" y="${y(row.planned)}" width="7" height="${bottom-y(row.planned)}" class="trend-plan-bar${row.estimated?' estimated':''}"/>`:'';
      const actual=known(row.observed)?`<rect x="${center+1}" y="${y(row.observed)}" width="7" height="${bottom-y(row.observed)}" class="trend-observed-bar"/>`:'';
      return plan+actual;
    }).join('');
    const segments=(key,className)=>rows.slice(1).map((row,index)=>{
      const previous=rows[index];if(!known(previous[key])||!known(row[key]))return '';
      const dash=key==='plannedCumulative'&&(row.estimated||previous.estimated)?' estimated':'';
      return `<path d="M${x(index)} ${y(previous[key])}L${x(index+1)} ${y(row[key])}" class="${className+dash}"/>`;
    }).join('');
    const dots=rows.map((row,index)=>[known(row.plannedCumulative)?`<circle cx="${x(index)}" cy="${y(row.plannedCumulative)}" r="2.5" class="trend-plan-dot"/>`:'',
      known(row.observedCumulative)?`<circle cx="${x(index)}" cy="${y(row.observedCumulative)}" r="2.5" class="trend-observed-dot"/>`:''].join('')).join('');
    const labels=rows.map((row,index)=>`<text x="${x(index)}" y="${bottom+15}" text-anchor="middle" class="${row.year===data.analysis_year?'trend-current-year':''}">${row.year===data.analysis_year?row.year:String(row.year).slice(2)}</text><rect x="${x(index)-plotWidth/rows.length/2}" y="${top}" width="${plotWidth/rows.length}" height="${bottom-top+21}" fill="transparent"><title>${row.year}년 · 계획 ${units(row.planned)}${row.estimated?' (기간 균등배분)':''} · 확인 공고 ${units(row.observed)} · 계획 누적 ${units(row.plannedCumulative)} · 공고 누적 ${units(row.observedCumulative)}</title></rect>`).join('');
    return `<div class="trend-chart-scroll"><svg class="trend-chart" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="${first}년부터 ${first+9}년까지 연도별 계획·확인 공고 누적 선과 당해 연도 계획·공고 막대 그래프 · 기준 ${data.analysis_year}년">${currentBand}${ticks}${targetLine}${bars}${segments('plannedCumulative','trend-plan-line')}${segments('observedCumulative','trend-observed-line')}${dots}${labels}<text x="${width-8}" y="${height-8}" text-anchor="end">연도</text></svg></div>`;
  }
  function milestones(row){
    if(!row?.milestones?.length)return '<p class="trend-note">블록 단계별 일정 미확보</p>';
    const progress=row.milestones.find(item=>item.stage==='CONSTRUCTION'&&known(item.progress_pct));
    const stages=row.milestones.map(item=>`<li class="${item.status==='OBSERVED'?'observed':item.status==='PLANNED'?'planned':'unknown'}"><b>${esc(item.label)}</b><small>${esc(item.actual_date||item.planned_month||'일정 미정')}</small></li>`).join('');
    return `<h4>사업 단계와 공정</h4><ol class="trend-stages">${stages}</ol>${progress?`<div class="trend-construction"><span>원천 공정률 <strong>${num(progress.progress_pct)}%</strong></span><div><i style="width:${Math.max(0,Math.min(100,progress.progress_pct))}%"></i></div><small>보고 기준 ${esc(progress.report_date||'미확보')}</small></div>`:'<p class="trend-note">원천 공정률 미확보</p>'}`;
  }
  function panel(data,viewport){
    const selection=MapSupply.selection();
    const chosen=scope(data,viewport,selection),node=document.getElementById('map-policy-monitor');
    const tabs=[{id:'',name:'전체'},...data.groups.policy.map(row=>({id:row.id,name:row.id==='UNMAPPED'?'귀속 미확인':row.name.match(/\(([^)]+)\)/)?.[1]||row.name}))];
    const tabMarkup=`<div class="monitor-policy-tabs" role="tablist" aria-label="공급 정책 선택">${tabs.map(tab=>`<button role="tab" aria-controls="monitor-policy-chart" aria-selected="${selection.kind==='policy'&&selection.id===tab.id}" data-monitor-policy="${esc(tab.id)}">${esc(tab.name)}</button>`).join('')}</div>`;
    if(!chosen){document.getElementById('map-method-summary').innerHTML='';node.classList.remove('trend-region');node.innerHTML=`<h3>공급 진척현황</h3>${tabMarkup}<p class="trend-note">현재 필터에서 위치와 공급량이 연결된 지역을 찾지 못했습니다.</p>`;return;}
    const {row,quantity,level,automatic}=chosen,series=derive(data,quantity),current=series.rows.find(item=>item.year===data.analysis_year);
    const progress=quantity.progress||{},yearGoal=current?.planned??current?.manual??null,yearObserved=current?.observed??null;
    const cumulativeGoal=progress.cumulative_goal_units,observed=progress.observed_units;
    const expectedYear=known(yearGoal)&&(known(yearObserved)||series.futureThisYear>0)?(yearObserved||0)+series.futureThisYear:null;
    const future=Array.from({length:5},(_,index)=>{const year=data.analysis_year+index+1,item=series.rows.find(r=>r.year===year);return `<span><b>+${index+1}년</b><small>${item&&known(item.planned)?units(item.planned):'일정 미정'}</small></span>`;}).join('');
    const levelName={region:'시도',municipality:'시군구',block:'블록'}[level];
    const label=level==='block'?`${row.district_name} · ${row.block}`:row.name;
    const target=quantity.target_units;
    const blockMeter=level==='block'?`<div class="trend-block-meter"><span>전체 계획 ${units(target)} <strong>공고 확인 ${units(observed)}${known(observed)&&known(target)&&target>0?` · ${pct(observed,target)}`:''}</strong></span><div><i style="width:${known(observed)&&known(target)&&target>0?Math.min(100,100*observed/target):0}%"></i></div><small>남은 계획 ${known(observed)&&known(target)?units(Math.max(0,target-observed)):'미확보'}</small></div>`:'';
    const selectedGroup=MapSupply.active(),policyQuantity=selectedGroup||data.summary;
    const policyOverview=level==='region'?`<div class="trend-policy-reference"><h4>${esc(selectedGroup?.name||'수도권 전체 연결 후보')}</h4>${selectedGroup?.announced_target_units!=null?`<p>발표 목표 ${units(selectedGroup.announced_target_units)} · ${esc(selectedGroup.target_scope||'')} · ${esc(selectedGroup.target_metric||'')}</p>`:''}${SupplyBars.chart({...policyQuantity,name:selectedGroup?.name||'수도권 전체'},true,true)}<h5>시도별 현황</h5><div class="monitor-region-charts">${data.groups.region.map(region=>{
      const amount=quantityFor(region,selection),ratio=amount?.progress?.observed_pct;
      return amount?.project_count?`<article class="trend-region-mini"><h5>${esc(region.name)}</h5><div><i style="width:${known(ratio)?Math.max(0,Math.min(100,ratio)):0}%"></i></div><small>계획 ${units(amount.target_units)} · 공고 ${units(amount.progress?.observed_units)}</small><small>올해까지 목표 ${units(amount.progress?.cumulative_goal_units)}</small></article>`:'';
    }).join('')}</div></div>`:'';
    const policyCapacity=policyQuantity.target_units;
    const policyOverflow=level==='region'&&known(policyCapacity)&&policyCapacity>0&&
      [policyQuantity.progress?.cumulative_goal_units,...(policyQuantity.projection?.future||[]).slice(0,3).map(item=>item.cumulative_units)]
        .some(value=>known(value)&&value>policyCapacity);
    document.getElementById('map-method-summary').innerHTML=`
      <p>${esc(data.reference_date)} 기준 · ${esc(data.measure_label)} 일정. 공고는 LH 본 모집공고 연결 검토량(하한)이며 실제 준공·입주 실적은 미확보입니다.</p>
      <p>올해 예상치는 확인 공고와 아직 공고되지 않은 올해 원천 예정월을 합한 전망입니다. 정확한 월이 없는 공식 기간만 균등배분하며 추정선으로 구분합니다. 예상치는 실제 공급 실적이 아닙니다.</p>
      ${level==='block'?'<p>블록의 남은 계획은 전체 계획에서 공고 확인량을 뺀 참고값이며 실제 입주 잔량이 아닙니다. 원천 공정률은 공사 진척이며 공급 실적이 아닙니다.</p>':''}
      ${series.unallocated!=null?`<p>전체 목표 중 일정 미배정 ${units(series.unallocated)}.</p>`:''}
      ${series.missingSchedule?`<p>일정 물량 미확보 ${num(series.missingSchedule)}건.</p>`:''}
      ${policyOverflow?'<p>예정량이 전체 계획량을 초과해 원천 범위 확인이 필요합니다.</p>':''}`;
    node.classList.toggle('trend-region',level==='region');
    node.innerHTML=`<h3>공급 진척현황</h3>${tabMarkup}${policyOverview}<div id="monitor-policy-chart" role="tabpanel"><div class="trend-heading"><div><small>${levelName} ${automatic?'· 화면 중심 자동 선택':'· 선택됨'}</small><h4>${esc(label)}</h4></div><span>${num(quantity.project_count)}개 사업</span></div><div class="trend-kpis"><div><small>전체 목표 · 사업계획</small><strong>${units(target)}</strong></div><div><small>올해까지 누적 목표</small><strong>${units(cumulativeGoal)}</strong></div><div><small>확인 공고 · 누적 하한</small><strong>${units(observed)}</strong></div><div><small>누적 목표 대비 공고</small><strong>${pct(observed,cumulativeGoal)}</strong></div><div><small>${data.analysis_year}년 목표</small><strong>${units(yearGoal)}</strong></div><div><small>올해 목표 대비 공고</small><strong>${pct(yearObserved,yearGoal)}</strong></div><div><small>올해 예상 달성률</small><strong>${pct(expectedYear,yearGoal)}</strong></div></div>${blockMeter}<h4 class="trend-chart-title">연도별 누적 계획·공고 / 당해 연도 물량</h4>${chart(data,quantity,series)}<div class="trend-legend"><span><i class="line plan"></i>누적 계획</span><span><i class="line observed"></i>누적 공고</span><span><i class="bar plan"></i>연도 계획</span><span><i class="bar observed"></i>연도 공고</span><span><i class="line estimated"></i>추정선</span></div><div class="trend-five">${future}</div>${level==='block'?milestones(row):''}</div>`;
  }
  return {panel,derive,scope};
})();
