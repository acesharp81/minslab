'use strict';
/* Stage residence from adjacent cumulative values; targets and sources remain unchanged. */
const PolicyStageFlow = (() => {
  const order=['MOVE_IN','SUPPLY','CONSTRUCTION','APPROVAL','BUSINESS','POLICY'];
  // Bottom to top: each stage's actual residence, then its positive target shortfall.
  const stackOrder=['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN','POLICY'];
  const models=new Map();
  function totals(point){return Object.fromEntries(order.map(k=>[k,k==='POLICY'?(point.totals.POLICY||0)+(point.totals.UNKNOWN||0):(point.totals[k]||0)]));}
  // Reuse sorted source series within one synchronous calculation only. A new
  // render/axis calculation sees edits even when the caller reuses its arrays.
  let calculationSeries=null,calculationLayouts=null;
  function withSeriesCache(calculate){
    if(calculationSeries)return calculate();
    calculationSeries=new WeakMap();calculationLayouts=new WeakMap();
    try{return calculate();}finally{calculationSeries=null;calculationLayouts=null;}
  }
  function sortedSeries(points){
    if(!points)return [];
    let sorted=calculationSeries?.get(points);
    if(!sorted){sorted=points.slice().sort((a,b)=>a.date.localeCompare(b.date));calculationSeries?.set(points,sorted);}
    return sorted;
  }
  function lastAt(points,when){
    let lo=0,hi=points.length;
    while(lo<hi){const mid=(lo+hi)>>>1;if(points[mid].date<=when)lo=mid+1;else hi=mid;}
    return points[lo-1];
  }
  function goalSeries(m,stage){
    const c=m.comparisons?.[stage];
    return sortedSeries(c?.management_points?.length?c.management_points:c?.target_points);
  }
  function goalAt(m,stage,when){
    const ps=goalSeries(m,stage);if(!ps.length)return null;
    const time=Date.parse(when),next=ps.find(p=>p.date>=when),prev=ps.filter(p=>p.date<=when).at(-1);
    if(prev&&(!next||prev.date===next.date))return prev.units;
    if(!next)return null;
    const left=prev||{date:next.date.slice(0,4)+'-01-01',units:0};
    if(when<left.date)return null;
    const fraction=(time-Date.parse(left.date))/Math.max(1,Date.parse(next.date)-Date.parse(left.date));
    return Math.round(left.units+(next.units-left.units)*Math.max(0,Math.min(1,fraction)));
  }
  const measuredAt=(m,stage,when)=>lastAt(sortedSeries(m.comparisons?.[stage]?.actual_points),when<m.asOf?when:m.asOf);
  const targetAt=(m,stage,when)=>lastAt(goalSeries(m,stage),when)?.units??null;
  const stagesInOrder=stackOrder.filter(k=>k!=='POLICY');
  const cutoffDate=m=>m.asOf;
  // A cumulative milestone is not a stack thickness. Subtract its immediate successor.
  // Missing successor values allocate the known remainder, without claiming a measured zero.
  function retained(values){
    return Object.fromEntries(stagesInOrder.map((stage,i)=>{
      const cumulative=values[stage]??null,next=values[stagesInOrder[i+1]]??null;
      const raw=cumulative==null?null:cumulative-(next??0);
      return [stage,{cumulative,units:raw==null?null:Math.max(0,raw),raw,nextMissing:i<stagesInOrder.length-1&&next==null}];
    }));
  }
  function projectedStages(m,when){
    const today=m.dataAsOf||m.asOf,source={...m,asOf:today},date=when<today?today:when;
    const actual=retained(Object.fromEntries(stagesInOrder.map(k=>[k,measuredAt(source,k,today)?.units??null])));
    const targets=retained(Object.fromEntries(stagesInOrder.map(k=>[k,targetAt(m,k,today)])));
    const increases=Object.fromEntries(stagesInOrder.map(k=>[k,Math.max(0,(targetAt(m,k,date)??0)-(targetAt(m,k,today)??0))]));
    const values=Object.fromEntries(stagesInOrder.map((k,i)=>{
      const a=actual[k].units,t=targets[k].units,initial=a==null&&t==null?null:Math.max(a??0,t??0);
      const change=increases[k]-(increases[stagesInOrder[i+1]]??0),raw=initial==null&&!change?null:(initial??0)+change;
      return [k,{initial,raw,units:raw==null?null:Math.max(0,raw),nextMissing:actual[k].nextMissing}];
    }));
    let cumulative=null,baseline=null;
    for(const k of stagesInOrder.slice().reverse()){
      const v=values[k];
      cumulative=v.units==null&&cumulative==null?null:(v.units??0)+(cumulative??0);
      baseline=v.initial==null&&baseline==null?null:(v.initial??0)+(baseline??0);
      Object.assign(v,{cumulative,base_cumulative:baseline,increment_units:increases[k]});
    }
    return values;
  }
  function projectedValue(m,stage,when){
    const p=projectedStages(m,when)[stage];
    return {units:p.cumulative,base_units:p.base_cumulative,increment_units:p.increment_units,date:when};
  }
  function stageLayout(m,when,projected=false){
    if(!calculationLayouts)return calculateStageLayout(m,when,projected);
    let layouts=calculationLayouts.get(m);
    if(!layouts){layouts=new Map();calculationLayouts.set(m,layouts);}
    const key=when+'|'+projected;
    if(!layouts.has(key))layouts.set(key,calculateStageLayout(m,when,projected));
    return layouts.get(key);
  }
  function calculateStageLayout(m,when,projected=false){
    const future=projected||when>cutoffDate(m);
    const actual=future?projectedStages(m,when):retained(Object.fromEntries(stagesInOrder.map(k=>[k,measuredAt(m,k,when)?.units??null])));
    const target=retained(Object.fromEntries(stagesInOrder.map(k=>[k,targetAt(m,k,when)])));
    let base=0;
    return Object.fromEntries(stagesInOrder.map(k=>{
      const a=actual[k],t=target[k],lo=base;
      const gap=a.units==null||t.units==null?null:Math.max(0,t.units-a.units);
      base+=(a.units??0)+(future?0:gap??0);
      return [k,{actual:{...a,lo,hi:a.units==null?null:lo+a.units},target:{...t,lo:lo+(a.units??0),hi:t.units==null?null:base},gap,future}];
    }));
  }
  function stageBands(m,when,kind='target'){
    return Object.fromEntries(Object.entries(stageLayout(m,when,kind==='forecast')).map(([k,v])=>[k,v[kind==='actual'||kind==='forecast'?'actual':'target']]));
  }
  // One boundary curve spans history and forecast; clipping changes color, never its tangent.
  function envelopeBands(m,when){
    return Object.fromEntries(Object.entries(stageLayout(m,when)).map(([k,b])=>[k,{lo:b.actual.lo,hi:b.actual.hi==null&&b.target.hi==null?null:Math.max(b.actual.hi??b.actual.lo,b.target.hi??b.target.lo)}]));
  }
  function stackExtent(m,when){
    return Math.max(0,...Object.values(stageLayout(m,when)).flatMap(b=>[b.actual.hi??b.actual.lo,b.target.hi??b.target.lo]));
  }
  function shortageRate(gap,cumulative){
    if(!Number.isFinite(gap)||gap<0||!Number.isFinite(cumulative)||cumulative<0)return null;
    return gap+cumulative>0?100*gap/(gap+cumulative):0;
  }
  function gapBand(m,stage,when){
    if(when>cutoffDate(m))return null;
    const band=stageLayout(m,when)[stage];
    return band.gap>0?{date:when,lo:band.target.lo,hi:band.target.hi,units:band.gap,status:assessGap(band.target.units,band.actual.units).status}:null;
  }

  // Goals change on their saved deadline; no fabricated monthly milestones.
  function trackingPoints(m,sampleDates=null){
    const dates=new Set(sampleDates||[m.start+'-01-01',m.end+'-12-31',m.asOf]);
    if(!sampleDates)for(const c of Object.values(m.comparisons||{}))for(const p of [...(c.target_points||[]),...(c.actual_points||[]),...(c.forecast_points||[])])dates.add(p.date);
    return [...dates].filter(d=>d>=m.start+'-01-01'&&d<=m.end+'-12-31').sort().map(date=>{
      let reached=0;const totals={POLICY:0,UNKNOWN:0},cumulative={};
      for(const k of order.filter(k=>k!=='POLICY')){
        const observed=measuredAt(m,k,date);cumulative[k]=observed?.units??null;
        const amount=Math.max(reached,observed?.units||0);totals[k]=amount-reached;reached=amount;
      }
      return {date,totals,cumulative,forecast:date>m.asOf};
    });
  }
  function monthlyPoints(m){
    const dates=[m.start+'-01-01',m.asOf,m.end+'-12-31'];
    for(let year=m.start;year<=m.end;year++)for(let month=1;month<=12;month++)dates.push(new Date(Date.UTC(year,month,0)).toISOString().slice(0,10));
    // Monthly samples give curves room to connect; exact observations remain in trackingPoints/tooltips.
    // Query cursors never change the fixed monthly samples or the actual/target boundary.
    return trackingPoints(m,dates);
  }
  // Scale to active quantities near the reference date, excluding the unstarted pool.
  function referenceAxis({points=[],comparisons={},asOf,fullMax=1}){
    const reference=new Date(asOf+'T00:00:00Z');
    if(!Number.isFinite(reference.getTime()))return {max:Math.max(1,fullMax),focused:false};
    const shift=months=>{const d=new Date(reference);d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()+months);const end=new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,0)).getUTCDate();d.setUTCDate(Math.min(reference.getUTCDate(),end));return d.toISOString().slice(0,10);};
    const start=shift(-3),end=shift(3),active=p=>order.filter(k=>k!=='POLICY').reduce((sum,k)=>sum+Math.max(0,Number(p.totals?.[k])||0),0);
    const sorted=points.slice().sort((a,b)=>a.date.localeCompare(b.date));
    const at=when=>{
      const before=sorted.filter(p=>p.date<=when).at(-1),after=sorted.find(p=>p.date>=when);
      if(!before)return 0;if(!after||before.date===after.date)return active(before);
      const fraction=(Date.parse(when)-Date.parse(before.date))/(Date.parse(after.date)-Date.parse(before.date));
      return active(before)+(active(after)-active(before))*fraction;
    };
    const values=[at(start),at(asOf),at(end),...sorted.filter(p=>p.date>=start&&p.date<=end).map(active)];
    for(const stage of order.filter(k=>k!=='POLICY')){
      const m={comparisons},series=goalSeries(m,stage);
      for(const day of [start,asOf,end,...series.filter(p=>p.date>=start&&p.date<=end).map(p=>p.date)])values.push(goalAt(m,stage,day)||0);
      const observed=(comparisons[stage]?.actual_points||[]).filter(p=>p.date<=asOf).slice().sort((a,b)=>a.date.localeCompare(b.date));
      values.push(observed.filter(p=>p.date<start).at(-1)?.units||0,...observed.filter(p=>p.date>=start&&p.date<=end).map(p=>p.units));
    }
    const peak=Math.max(0,...values.filter(Number.isFinite));
    const business=targetAt({comparisons},'BUSINESS',asOf)??goalSeries({comparisons},'BUSINESS').find(p=>p.date>asOf)?.units??0;
    if(!peak&&!business)return {max:Math.max(1,fullMax),focused:false,start,end};
    const layout={comparisons,asOf,tracking:true};
    const extent=Math.max(...[start,asOf,end].map(day=>stackExtent(layout,day)));
    return {max:axisMaximum(business,Math.max(peak,extent)),focused:true,start,end,peak,business};
  }
  function axisMaximum(business,extent=0){
    const desired=Math.max((business||extent)/.7,extent/0.95,1);
    // Keep four integer tick intervals; rounding changes the requested 70% only slightly.
    const unit=4*10**Math.max(0,Math.floor(Math.log10(desired))-3);
    return Math.ceil(desired/unit)*unit;
  }

  function windowAxis(m,start,end){return withSeriesCache(()=>calculateWindowAxis(m,start,end));}
  function calculateWindowAxis(m,start,end){
    const dates=new Set([start,end]);
    if(m.asOf>=start&&m.asOf<=end)dates.add(m.asOf);
    for(const c of Object.values(m.comparisons||{}))for(const p of [...(c.target_points||[]),...(c.management_points||[]),...(c.actual_points||[])])if(p.date>=start&&p.date<=end)dates.add(p.date);
    const peak=Math.max(0,...[...dates].map(day=>stackExtent(m,day)));
    const desired=Math.max(1,peak*1.3),unit=4*10**Math.max(0,Math.floor(Math.log10(desired))-3);
    return {max:Math.ceil(desired/unit)*unit,peak,start,end};
  }
  function visibleAxis(svg,start,end){
    const m=models.get(svg.dataset.d907Model);return m?windowAxis(m,start,end):null;
  }

  // Shared management rule. Classify before rounding; missing measurements are never zero.
  function formatGapRate(rate){return rate==null?'미확보':rate>0&&rate<.05?'0.1% 미만':rate<2&&rate>=1.95?'2% 미만':rate.toFixed(1)+'%';}
  function assessGap(target,actual){
    if(!Number.isFinite(target)||target<=0||!Number.isFinite(actual)||actual<0)return {status:'UNKNOWN',label:'판정 미확보',gap:null,rate:null,color:'#8795a5',text:'#fff'};
    const gap=Math.max(0,target-actual),rate=100*gap/target;
    if(!gap)return {status:'NORMAL',label:'목표 도달',gap,rate,color:'#218267',text:'#fff'};
    return gap*100>=target*2?{status:'DELAYED',label:'지연',gap,rate,color:'#b51f38',text:'#fff'}:{status:'WARNING',label:'주의',gap,rate,color:'#e8ad25',text:'#503700'};
  }
  function comparisonStatus(m,stage){
    const c=m.comparisons?.[stage]||{},targets=goalSeries(m,stage),due=targets.filter(t=>t.date<=m.asOf).at(-1);
    const actual=(c.actual_points||[]).filter(a=>a.date<=m.asOf).slice().sort((a,b)=>a.date.localeCompare(b.date)).at(-1);
    const confirmed=new Map();for(const d of m.delays||[])if((d.stage==='COMPLETION'?'CONSTRUCTION':d.stage)===stage)confirmed.set(d.project_id,Math.max(confirmed.get(d.project_id)||0,d.units));
    const confirmedUnits=[...confirmed.values()].reduce((a,b)=>a+b,0);
    let status='NO_TARGET',assessment=assessGap(null,null);
    if(targets.length&&!due)status='NOT_DUE';
    if(due){assessment=assessGap(due.units,actual?.units);status=!actual?'NO_ACTUAL':assessment.status==='NORMAL'?'REACHED':assessment.status;}
    return {difference:due&&actual?due.units-actual.units:null,stage,label:stage==='MOVE_IN'?'입주':c.label||m.stages?.[stage]||stage,status,due,actual,gap:assessment.gap,confirmedUnits,next:targets.find(t=>t.date>m.asOf),rate:assessment.rate,assessment,stale:!!(due&&actual&&actual.date<due.date)};
  }
  function delaySummary(m){
    const checks=['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'].map(k=>comparisonStatus(m,k));
    const delayed=checks.filter(c=>c.status==='DELAYED').length,warning=checks.filter(c=>c.status==='WARNING').length;
    return '<section class="d907-delay-summary" aria-label="기준일 목표 대비 지연·주의"><header><strong>목표 대비 지연 '+delayed+'개 · 주의 '+warning+'개 단계</strong><span>기준일 '+esc(m.asOf)+' · 입력·추정 포함</span></header><div class="d907-delay-cards">'+checks.map(c=>{
      const label=c.gap>0?c.assessment.label+' · 부족률 '+formatGapRate(c.rate):({NO_TARGET:'판단 불가 · 목표 미확보',NOT_DUE:'목표 기한 전',NO_ACTUAL:'판단 불가 · 실적 미확보',UNKNOWN:'판정 미확보',REACHED:'확인량 기준 목표 도달'})[c.status];
      const target=c.due||c.next,rawGap=target&&c.actual?target.units-c.actual.units:null;
      const gapText=rawGap==null?'갭 산정 불가':rawGap>0?(c.due?'목표 대비 부족 ':'다음 목표까지 ')+num(rawGap)+'호':rawGap<0?'목표 초과 '+num(-rawGap)+'호':'목표와 일치 · 0호';
      return '<button type="button" data-d907-delay-stage="'+c.stage+'" data-delay-status="'+c.status+'" class="d907-delay-card '+(c.status==='DELAYED'?'alert':c.status==='WARNING'?'warn':'neutral')+'"><span>'+esc(c.label)+'</span><div class="d907-pair-values"><small>'+(c.due?'도래 목표':'다음 목표')+'<b>'+(target?num(target.units)+'호':'미확보')+'</b>'+esc(target?.date||'')+'</small><small>측정값<b>'+(c.actual?num(c.actual.units)+'호':'미측정')+'</b>'+esc(c.actual?.date||'')+'</small></div><strong>'+esc(gapText)+'</strong><small>'+esc(label)+'</small>'+(c.stale?'<small>최근 측정값 기준 · 갱신 필요</small>':'')+(c.actual?.manual_units?'<small>입력값 '+num(c.actual.manual_units)+'호'+(c.actual.inferred_units?' · 추정 포함 '+num(c.actual.inferred_units)+'호':'')+'</small>':'')+'</button>';
    }).join('')+'</div><p>부족률 = (도래 목표 − 최근 측정값) ÷ 도래 목표. 2% 이상은 지연(빨강), 0% 초과~2% 미만은 주의(노랑)입니다. 목표 도달은 정상이며 미측정은 판정에서 제외합니다. 단계 간 갭은 합산하지 않습니다.</p></section>';
  }

  function targetAreas(m,plot,x,y){
    const area=d3.area().defined(p=>p.hi!=null).x(p=>x(p.date)).y0(p=>y(p.lo)).y1(p=>y(p.hi)).curve(d3.curveMonotoneX);
    const line=d3.line().defined(p=>p.hi!=null).x(p=>x(p.date)).y(p=>y(p.hi)).curve(d3.curveMonotoneX);
    // Future projections start from the larger current stage value (actual or target) and add only subsequent goal increments.
    return stagesInOrder.map(stage=>{
      const values=plot.map(p=>({date:p.date,...envelopeBands(m,p.date)[stage]}));
      return '<g data-d907-target-area="'+stage+'" clip-path="url(#d907-future)"><path data-d907-forecast-area="'+stage+'" data-projection-basis="max-stage-plus-target-increments" d="'+(area(values)||'')+'" fill="'+m.colors[stage]+'" fill-opacity=".30" clip-path="url(#d907-future)"><title>'+esc(m.stages[stage])+' 실적·목표 중 큰 물량 + 예정일별 증감</title></path><path data-d907-forecast-line="'+stage+'" d="'+(line(values)||'')+'" fill="none" stroke="'+m.colors[stage]+'" stroke-opacity=".35" stroke-width="1.5"/></g>';
    }).join('');
  }
  function gapAreas(m,plot,x,y){
    const area=d3.area().defined(p=>p.hi!=null).x(p=>x(p.date)).y0(p=>y(p.lo)).y1(p=>y(p.hi)).curve(d3.curveMonotoneX);
    return stagesInOrder.map(stage=>{
      const values=plot.map(p=>{const b=stageLayout(m,p.date)[stage];return {date:p.date,lo:b.target.lo,hi:b.gap==null?null:b.target.hi};});
      return '<path data-d907-gap="'+stage+'" d="'+(area(values)||'')+'" fill="url(#d907-gap-'+stage+')" clip-path="url(#d907-past)"><title>미달성('+esc(m.stages[stage])+') · 목표 물량 − 실적 물량의 양수 부족분</title></path>';
    }).join('');
  }
  function layoutCallouts(items,top,bottom){
    const height=36,gap=8,sorted=items.slice().sort((a,b)=>a.anchor-b.anchor);
    let next=top;
    const placed=sorted.map(item=>{const y=Math.max(next,Math.min(bottom-height,item.anchor-height/2));next=y+height+gap;return {...item,y};});
    for(let i=placed.length-1;i>=0;i--)placed[i].y=Math.min(placed[i].y,i===placed.length-1?bottom-height:placed[i+1].y-height-gap);
    return placed;
  }
  function quarterEnd(day){const [y,month]=day.split('-').map(Number);return new Date(Date.UTC(y,Math.ceil(month/3)*3,0)).toISOString().slice(0,10);}
  function summaryValues(m){
    const yearEnd=m.comparisonDate||String(m.year||m.asOf.slice(0,4))+'-12-31',dataDate=m.dataAsOf||m.asOf;
    return Object.fromEntries(Object.entries(m.stages).filter(([k])=>k!=='POLICY').map(([k,label])=>{
      const actual=measuredAt(m,k,m.asOf);
      const comparisonKind=yearEnd<=dataDate?'MEASUREMENT':'FORECAST';
      const expected=comparisonKind==='MEASUREMENT'?measuredAt({...m,asOf:dataDate},k,yearEnd):projectedValue({...m,dataAsOf:dataDate},k,yearEnd);
      return [k,{label,comparison_kind:comparisonKind,comparison_date:yearEnd,as_of_date:m.asOf,measurement_date:actual?.date||null,current_units:actual?.units??null,year_end:yearEnd,expected_units:expected?.units??null,plan_date:expected?.date||null,remaining_plan_units:expected?.increment_units??null,basis:comparisonKind==='MEASUREMENT'?'보조 기준일까지 누적 측정량':'단계별 max(현재 실적 물량, 목표 물량)에서 출발하여 이후 예정일별 단계 이동 반영'}];
    }));
  }
  function summaryTable(m){
    const {policyTarget}=m,summary=summaryValues(m),yearEnd=m.comparisonDate||String(m.year||m.asOf.slice(0,4))+'-12-31';
    return Object.entries(m.stages).map(([k,v])=>{
      const value=summary[k],actual=value?.current_units==null?null:{units:value.current_units},expected=value?.expected_units==null?null:{units:value.expected_units};
      const remainder=actual&&expected?expected.units-actual.units:null;
      const note=remainder==null?'':m.comparisonDate?'기준일 대비 '+(remainder>0?'+':'')+num(remainder)+'호':remainder>0?'연말까지 추가 예상 '+num(remainder)+'호':remainder<0?'선택 연도·기준일 확인 필요':'현재 누적 유지 · 추가 계획량 0호';
      return '<button type="button" class="d907-stage-value d907-stage-'+k+'" data-d907-highlight="'+k+'" aria-pressed="false" title="'+v+' 단계 강조 · 다시 누르면 전체 보기"><span class="d907-stage-name">'+esc(k==='CONSTRUCTION'?'착공(건설)':v)+'<span aria-hidden="true">▤</span></span>'+(k==='POLICY'?'<span class="d907-stage-number"><small>전체 목표</small><b>'+num(policyTarget??m.max)+'호</b></span><small>입력 목표 · 그래프 배경 기준</small>'+(m.projectCount==null?'':'<span class="d907-stage-number" data-d907-project-count="'+m.projectCount+'" title="현재 선택 범위에 포함된 사업 수 · 같은 사업의 수집 원천은 중복 제외"><small>포함 사업</small><b>'+num(m.projectCount)+'개</b></span>'):'<span class="d907-stage-number"><small>'+('누적 측정량(&#39;'+esc(m.asOf.slice(2).replaceAll('-','.'))+'. 기준)')+'</small><b>'+(actual?num(actual.units)+'호':'미측정')+'</b></span><span class="d907-stage-number"><small>'+((value.comparison_kind==='MEASUREMENT'?'누적 측정량':'예상 누적량')+'(&#39;'+esc(yearEnd.slice(2).replaceAll('-','.'))+'. 기준)')+'</small><b>'+(expected?num(expected.units)+'호':value.comparison_kind==='MEASUREMENT'?'미측정':'계획 미확보')+'</b></span>'+(note?'<strong class="d907-stage-gap">'+note+'</strong>':''))+'</button>';
    }).join('');
  }

  function render(m){return withSeriesCache(()=>renderChart(m));}
  function renderChart(m){
    const model=m;models.set(m.instanceKey||'policy',m);const width=m.axisUnit==='month'?Math.max(1100,(m.end-m.start+1)*12*30+148):1100;model.plotRight=width-58;const max=m.max,left=90,right=model.plotRight,top=85,bottom=410,first=Date.parse(m.start+'-01-01'),last=Date.parse(m.end+'-12-31');
    const x=date=>left+(Date.parse(date)-first)/(last-first)*(right-left),y=value=>bottom-(bottom-top)*value/max;
    if(m.tracking)m.points=trackingPoints(m);
    const points=(m.tracking?monthlyPoints(m):m.points).map(p=>({...p,display:totals(p)}));
    // Duplicate the first/last observation at the plot edge, not across missing internal dates.
    const plot=points.length?[{...points[0],date:m.start+'-01-01'},...points,{...points.at(-1),date:m.end+'-12-31'}]:[];
    const stacked=d3.stack().keys(stackOrder).value((p,k)=>p.display[k]||0)(plot);
    const area=d3.area().x(p=>x(p.data.date)).y0(p=>y(p[0])).y1(p=>y(p[1])).curve(d3.curveMonotoneX);
    const cutoff=Math.max(left,Math.min(right,x(cutoffDate(m))));
    const gapDefs=stagesInOrder.map(key=>{const color='#b51f38';return '<pattern id="d907-gap-'+key+'" width="8" height="8" patternUnits="userSpaceOnUse"><path d="M-2 2L2 -2M0 8L8 0M6 10L10 6" stroke="'+color+'" stroke-width="1.2"/></pattern>';}).join('');
    const defs=gapDefs+'<clipPath id="d907-past"><rect x="90" y="85" width="'+(cutoff-left)+'" height="325"/></clipPath><clipPath id="d907-future"><rect x="'+cutoff+'" y="85" width="'+(right-cutoff)+'" height="325"/></clipPath>';
    let paths=stacked.filter(series=>!m.tracking||series.key!=='POLICY').map(series=>'<g data-d907-band="'+series.key+'">'+(m.tracking?'':'<path d="'+(area(series)||'')+'" fill="'+m.colors[series.key]+'" fill-opacity=".18" clip-path="url(#d907-future)" stroke="#fff" stroke-width="1.2"/>')+'<path d="'+(area(series)||'')+'" fill="'+m.colors[series.key]+'" clip-path="url(#d907-past)" stroke="#fff" stroke-width="1.2"/></g>').join('');
    if(m.tracking){
      const cumulativeArea=d3.area().defined(p=>p.hi!=null).x(p=>x(p.date)).y0(p=>y(p.lo)).y1(p=>y(p.hi)).curve(d3.curveMonotoneX);
      paths=stackOrder.filter(k=>k!=='POLICY').map(stage=>{
        const values=plot.map(p=>({date:p.date,...stageBands(m,p.date,'actual')[stage]}));
        return '<g data-d907-band="'+stage+'"><path data-d907-cumulative-area="'+stage+'" d="'+(cumulativeArea(values)||'')+'" fill="'+m.colors[stage]+'" fill-opacity=".75" clip-path="url(#d907-past)"/></g>';
      }).join('');
    }
    // Missing classifications remain a neutral portion of the verification pool.
    const uncertainty=plot.map(p=>({data:p,lo:Math.max(0,Object.values(p.totals).reduce((a,b)=>a+b,0)-(p.totals.UNKNOWN||0)),hi:Object.values(p.totals).reduce((a,b)=>a+b,0)}));
    const unknownArea=d3.area().x(p=>x(p.data.date)).y0(p=>y(p.lo)).y1(p=>y(p.hi));
    if(!m.tracking)paths+='<path data-d907-uncertain d="'+(unknownArea(uncertainty)||'')+'" fill="#edf0f3"/>';
    const referenceDate=m.referenceDate||m.asOf,nowX=Date.parse(referenceDate)>=first&&Date.parse(referenceDate)<=last?x(referenceDate):null;

    let callouts='';
    const gapX=Date.parse(m.asOf)>=first&&Date.parse(m.asOf)<=last?x(m.asOf):null;
    const gapChecks=stagesInOrder.map(k=>{const b=stageLayout(m,m.asOf)[k],c=comparisonStatus(m,k),assessment=assessGap(b.target.units,b.actual.units);return {...c,gap:b.gap,rate:shortageRate(b.gap,b.actual.cumulative),assessment,status:assessment.status};}).filter(c=>c.gap>0);
    if(gapX!=null){
      const cx=Math.max(left+155,Math.min(right-155,gapX+160));
      const referenceBands=stageBands(m,m.asOf);
      const labels=layoutCallouts(gapChecks.map(c=>({...c,anchor:Math.max(top,Math.min(bottom,y(referenceBands[c.stage].hi??0)))})),top+4,bottom-4);
      for(const c of labels){
        const color='#b51f38',text='#fff';
        const title=(m.stages[c.stage]||c.label)+' 목표대비 '+num(c.gap)+'호 부족 ('+(c.rate==null?'비율 미확보':c.rate.toFixed(1)+'%')+')';
        const note=c.due.date.slice(0,7)+' 목표 기준';
        callouts+='<g data-d907-gap-callout="'+c.stage+'" data-gap-status="'+c.status+'"><path d="M'+gapX+' '+c.anchor+' L'+(cx-149)+' '+(c.y+18)+'" stroke="'+color+'" stroke-width="1.3" fill="none"/><circle cx="'+gapX+'" cy="'+c.anchor+'" r="4" fill="white" stroke="'+color+'" stroke-width="1.5"/><rect data-d907-callout-box x="'+(cx-149)+'" y="'+c.y+'" width="298" height="36" rx="5" fill="'+color+'"/><text x="'+cx+'" y="'+(c.y+14)+'" text-anchor="middle" fill="'+text+'" font-size="12" font-weight="800">'+esc(title)+'</text><text x="'+cx+'" y="'+(c.y+28)+'" text-anchor="middle" fill="'+text+'" font-size="10">'+esc(note)+'</text></g>';
      }
    }
    const dense=m.axisUnit!=='month';
    const headers='';
    const ticks=[0,.25,.5,.75,1].map(r=>'<line x1="'+left+'" x2="'+right+'" y1="'+y(max*r)+'" y2="'+y(max*r)+'" stroke="'+(r===1?'#476f99':'#fff')+'" stroke-dasharray="3 4"/><text x="80" y="'+(y(max*r)+4)+'" text-anchor="end">'+num(max*r)+'</text>').join('');
    const labels=Array.from({length:(m.end-m.start+1)*(dense?1:12)},(_,i)=>{
      const year=m.start+(dense?i:Math.floor(i/12)),month=dense?1:i%12+1,date=year+'-'+String(month).padStart(2,'0')+'-01';
      const label=dense?String(year):String(month).padStart(2,'0');
      return '<g data-d907-month="'+date.slice(0,7)+'"><line x1="'+x(date)+'" x2="'+x(date)+'" y1="410" y2="415" stroke="#90a9bf"/><text x="'+x(date)+'" y="431" text-anchor="middle">'+label+'</text>'+(!dense&&month===1?'<text x="'+(x(date)+12)+'" y="451" font-weight="700">'+year+'년</text>':'')+'</g>';
    }).join('');
    let bandLabels='';
    const labelStep=(right-left)/(m.end-m.start+1)<120?2:1;
    for(let year=m.start;year<=m.end;year+=labelStep){
      const date=year+'-07-01',nearest=points.reduce((a,b)=>!a?b:Math.abs(Date.parse(a.date)-Date.parse(date))<Math.abs(Date.parse(b.date)-Date.parse(date))?a:b,null);
      if(!nearest)continue;
      const kind=date<=m.asOf?'actual':'forecast',bands=stageBands(m,date,'actual');
      const visible=stackOrder.filter(k=>k!=='POLICY'&&bands[k].hi!=null);
      for(let i=0;i<visible.length;i++){
        const key=visible[i],{hi,lo}=bands[key];
        if((hi-lo)/max*(bottom-top)<23||hi>max)continue;
        bandLabels+='<text data-d907-label="'+key+'" class="d907-band-label" x="'+x(date)+'" y="'+(y((hi+lo)/2)+4)+'" text-anchor="middle">'+esc(m.stages[key])+(kind==='actual'?'':' 예상')+'</text>';
      }
    }

    for(let year=m.start;year<=m.end;year+=labelStep){
      const date=year+'-07-01';if(date>m.asOf)continue;
      for(const key of stagesInOrder){
        const band=gapBand(m,key,date);if(!band||(band.hi-band.lo)/max*(bottom-top)<16||band.hi>max)continue;
        bandLabels+='<text data-d907-label="'+key+'" data-d907-gap-label="'+key+'" class="d907-band-label d907-gap-band-label" x="'+x(date)+'" y="'+(y((band.hi+band.lo)/2)+4)+'" text-anchor="middle">미달성('+esc(m.stages[key])+')</text>';
      }
    }

    let boundaries='';
    if(m.tracking){
      const line=d3.line().defined(p=>p.units!=null).x(p=>x(p.date)).y(p=>y(p.units)).curve(d3.curveMonotoneX);
      for(const k of order.filter(k=>k!=='POLICY')){
        const goals=goalSeries(m,k),observed=(m.comparisons[k]?.actual_points||[]).filter(p=>p.date<=m.asOf);
        const target=goals.length?plot.map(p=>({date:p.date,units:envelopeBands(m,p.date)[k].hi})):[];
        const actual=observed.length?plot.map(p=>({date:p.date,units:stageBands(m,p.date,'actual')[k].hi})):[];
        for(const [kind,ps,dash] of [['target',target,'7 4'],['actual',actual,'']]){
          if(!ps.length)continue;
          boundaries+='<path data-d907-comparison-line="'+kind+'" data-stage="'+k+'" d="'+line(ps)+'" fill="none" stroke="white" stroke-width="4" stroke-dasharray="'+dash+'" clip-path="url(#d907-past)"/><path data-d907-'+kind+'-line="'+k+'" d="'+line(ps)+'" fill="none" stroke="'+m.colors[k]+'" stroke-width="2.3" stroke-dasharray="'+dash+'" clip-path="url(#d907-past)"><title>'+esc(m.stages[k])+' '+(kind==='target'?'목표':'측정값')+'</title></path>';
        }
        const t=targetAt(m,k,referenceDate),a=measuredAt(m,k,referenceDate)?.units;
        for(const [kind,value] of [['target',t],['actual',a]])if(value!=null)boundaries+='<circle data-d907-reference-value="'+kind+'" data-stage="'+k+'" data-units="'+value+'" data-base="'+stageBands(m,referenceDate,kind)[k].lo+'" data-stage-units="'+stageBands(m,referenceDate,kind)[k].units+'" data-gap-units="'+(stageLayout(m,referenceDate)[k].gap??'')+'" data-height="'+stageBands(m,referenceDate,kind)[k].hi+'" cx="'+x(referenceDate)+'" cy="'+y(stageBands(m,referenceDate,kind)[k].hi)+'" r="'+(kind==='target'?4:3)+'" fill="'+(kind==='target'?'white':m.colors[k])+'" stroke="'+m.colors[k]+'" stroke-width="1.5"><title>'+esc(m.stages[k])+' '+(kind==='target'?'도래 목표 ':'측정값 ')+num(value)+'호</title></circle>';
      }
    }
    const selectedX=x(m.year+'-07-01'),selection='<rect data-d907-selection="'+m.year+'" x="'+(selectedX-4)+'" y="85" width="8" height="325" fill="#1967c0" opacity=".15"/>';
    const reference=nowX==null?'':'<rect x="'+(nowX-10)+'" y="72" width="20" height="339" fill="#193d63" opacity=".13"/><line data-d907-now-line x1="'+nowX+'" x2="'+nowX+'" y1="72" y2="416" stroke="#173a60" stroke-width="1.8" stroke-dasharray="4 3"/><rect x="'+(nowX-70)+'" y="450" width="140" height="22" rx="4" fill="#183c61"/><text x="'+nowX+'" y="465" text-anchor="middle" fill="white">기준일 '+referenceDate+'</text>';
    let auxiliary='';
    if(m.comparisonDate){const ax=x(m.comparisonDate),values=summaryValues({...m,asOf:referenceDate,dataAsOf:m.asOf}),comparisonBands=stageBands(m,m.comparisonDate,'actual');auxiliary='<line data-d907-aux-line data-date="'+m.comparisonDate+'" x1="'+ax+'" x2="'+ax+'" y1="72" y2="416" stroke="#773da5" stroke-width="2" stroke-dasharray="8 4"/><text x="'+ax+'" y="489" text-anchor="middle" fill="#773da5">보조 '+m.comparisonDate+'</text>';for(const [k,entry] of Object.entries(values)){const v={...entry,expected_units:comparisonBands[k].cumulative};if(v.expected_units!=null)auxiliary+='<circle data-d907-aux-value data-stage="'+k+'" data-units="'+v.expected_units+'" cx="'+ax+'" cy="'+y(comparisonBands[k].hi)+'" r="4" fill="white" stroke="'+m.colors[k]+'" stroke-width="2"><title>'+esc(v.label)+' '+num(v.expected_units)+'호</title></circle>';}}
    const html='<div class="d907-chart-wrap '+(m.axisUnit==='month'?'d907-monthly':'')+'"><svg class="d907-chart" data-d907-model="'+esc(m.instanceKey||'policy')+'" data-y-max="'+max+'" data-actual-through="'+m.asOf+'" data-end-year="'+m.end+'" data-start-year="'+m.start+'" data-first-project-date="'+esc(m.firstProjectDate||m.start+'-01-01')+'" data-first-project-x="'+x(m.firstProjectDate||m.start+'-01-01')+'" data-current-x="'+x(m.asOf)+'" data-axis-unit="'+m.axisUnit+'" width="'+width+'" viewBox="0 60 '+width+' 435" preserveAspectRatio="none" role="img" data-value-mode="retained" data-stack-order="BUSINESS,APPROVAL,CONSTRUCTION,SUPPLY,MOVE_IN" data-curve="monotone-x" aria-label="사업화·인허가·착공·공급·입주의 단계별 물량과 목표 부족분, '+esc(m.axisBasis||'정책 목표')+' '+num(max)+'호"><defs>'+defs+'<clipPath id="d907-plot"><rect x="90" y="85" width="'+(right-left)+'" height="325"/></clipPath></defs>'+headers+'<text x="34" y="72">(호)</text>'+'<g clip-path="url(#d907-plot)">'+(m.tracking?'<rect data-d907-policy-background x="'+left+'" y="'+Math.max(top,y(m.policyTarget??max))+'" width="'+(right-left)+'" height="'+Math.min(bottom-top,(bottom-top)*(m.policyTarget??max)/max)+'" fill="#eef2f6"/>':'')+targetAreas(m,plot,x,y)+paths+gapAreas(m,plot,x,y)+bandLabels+boundaries+'</g>'+ticks+selection+reference+auxiliary+callouts+labels+'<line class="d907-hover-line" x1="0" x2="0" y1="85" y2="410" stroke="#142d4b" stroke-width="1" visibility="hidden"/><rect data-d907-hover x="90" y="72" width="'+(right-left)+'" height="343" fill="transparent"/></svg><div class="d907-chart-tooltip" role="status" hidden></div></div>';
    return m.instanceKey?html.replaceAll('id="d907-','id="d907-'+m.instanceKey+'-').replaceAll('url(#d907-','url(#d907-'+m.instanceKey+'-'):html;
  }
  function applyHighlight(host,key){
    if(!host)return;
    host.querySelectorAll('[data-d907-highlight]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.d907Highlight===key)));
    host.querySelectorAll('[data-d907-band],[data-d907-forecast-area],[data-d907-target-area],[data-d907-gap],[data-d907-delay],[data-d907-label],[data-d907-comparison-line],[data-d907-target-line],[data-d907-actual-line],[data-d907-reference-value],[data-d907-gap-callout],[data-d907-policy-background]').forEach(n=>n.classList.toggle('d907-dimmed',Boolean(key)&&(n.hasAttribute('data-d907-policy-background')?'POLICY':n.dataset.stage||Object.values(n.dataset)[0])!==key));
  }
  function start(){
    document.addEventListener('pointermove',e=>{
      const hit=e.target.closest('[data-d907-hover]');if(!hit)return;const model=models.get(hit.ownerSVGElement.dataset.d907Model);if(!model||!model.points.length)return;const svg=hit.ownerSVGElement,wrap=svg.parentElement,tip=wrap.querySelector('.d907-chart-tooltip'),pt=svg.createSVGPoint();pt.x=e.clientX;pt.y=e.clientY;const local=pt.matrixTransform(svg.getScreenCTM().inverse());
      const f=Date.parse(model.start+'-01-01'),l=Date.parse(model.end+'-12-31'),date=f+(Math.max(90,Math.min(model.plotRight,local.x))-90)/(model.plotRight-90)*(l-f),sample=model.points.reduce((a,b)=>!a?b:Math.abs(Date.parse(a.date)-date)<Math.abs(Date.parse(b.date)-date)?a:b),p=model.tracking?{...sample,date:new Date(date).toISOString().slice(0,10)}:sample,t=totals(p);
      const plans=(model.constructionPlans||[]).filter(c=>p.date>=c.plan.start_date),weight=plans.reduce((n,c)=>n+c.units,0);
      const plannedPct=weight?plans.reduce((n,c)=>n+c.units*Math.max(0,Math.min(100,(Date.parse(p.date)-Date.parse(c.plan.start_date))/(Date.parse(c.plan.completion_date)-Date.parse(c.plan.start_date))*100)),0)/weight:null;
      const progressNote=plannedPct==null?'':'<br>연결 사업 추정 계획 공정률 '+plannedPct.toFixed(1)+'% · '+num(weight)+'호 기준 (기간 비례, 공식 목표 아님)';
      tip.hidden=false;tip.innerHTML=model.tracking?'<h4>'+p.date.slice(0,7).replace('-','.')+' · 단계 물량 / 목표</h4>'+stagesInOrder.slice().reverse().map(k=>{const b=stageLayout(model,p.date)[k];return '<div><i class="d907-color-'+k+'"></i>'+esc(model.stages[k])+'<b>'+(b.actual.units==null?'미측정':num(b.actual.units)+'호')+' / '+(b.target.units==null?'목표 미확보':num(b.target.units)+'호')+'<small>'+(b.future?'목표 기반 예상 · ':'')+'부족분 '+(b.gap==null?'산정 불가':num(b.gap)+'호')+'<br>누적 '+(b.actual.cumulative==null?'미측정':num(b.actual.cumulative)+'호')+' / 목표 '+(b.target.cumulative==null?'미확보':num(b.target.cumulative)+'호')+(b.actual.nextMissing?'<br>후속 단계 미측정 · 확인된 잔여량 표시':'')+(b.actual.raw<0?'<br>단계 누적량 역전 · 면적은 0으로 표시':'')+'</small></b></div>';}).join('')+'<span class="d907-tip-foot">물량 = 해당 단계 누적 − 다음 단계 누적<br>빗금 = 목표 물량 대비 부족분 · 입력·추정 포함<br>예상 = 단계별 max(현재 실적, 목표) + 이후 예정일별 증감</span>' :'<h4>'+p.date.slice(0,7).replace('-','.')+' <small>'+(p.forecast?'계획·일정':'확인 기준')+'</small></h4><p>전체 '+num(Object.values(t).reduce((a,b)=>a+b,0))+'호</p><div class="d907-tip-head"><span>단계</span><span>현재 단계 물량 / 누적 목표</span></div>'+Object.entries(model.stages).map(([k,v])=>'<div><i class="d907-color-'+k+'"></i>'+v+'<b>'+num(t[k]||0)+'호'+(goalAt(model,k,p.date)==null?'':'<small>누적 목표 '+num(goalAt(model,k,p.date))+'호</small>')+'</b></div>').join('')+'<span class="d907-tip-foot">정책 구간: 목표 잔여 '+num(p.totals.POLICY||0)+'호 · 단계 미확인 '+num(p.totals.UNKNOWN||0)+'호'+(p.forecast?'<br>미래 영역은 공식 목표와 일정에 따른 전망':'')+progressNote+'<br>입주는 시작일 확인 사업의 물량 · 실제 입주 가구 수 아님</span>';
      const rect=wrap.getBoundingClientRect();tip.style.left=Math.max(wrap.parentElement.scrollLeft+8,Math.min(wrap.parentElement.scrollLeft+wrap.parentElement.clientWidth-tip.offsetWidth-8,e.clientX-rect.left+18))+'px';tip.style.top=Math.max(0,Math.min(78,svg.getBoundingClientRect().height-tip.offsetHeight-4))+'px';const line=svg.querySelector('.d907-hover-line');line.setAttribute('x1',local.x);line.setAttribute('x2',local.x);line.setAttribute('visibility','visible');
    });
    document.addEventListener('pointerout',e=>{if(!e.target.hasAttribute?.('data-d907-hover'))return;const wrap=e.target.closest('.d907-chart-wrap');wrap?.querySelector('.d907-chart-tooltip')?.setAttribute('hidden','');wrap?.querySelector('.d907-hover-line')?.setAttribute('visibility','hidden');});
  }
  return {windowAxis,visibleAxis,quarterEnd,assessGap,formatGapRate,render,start,totals,trackingPoints,monthlyPoints,referenceAxis,comparisonStatus,delaySummary,layoutCallouts,summaryTable,summaryValues,stageBands,gapBand,stackExtent,stageLayout,axisMaximum,shortageRate,projectedValue,projectedStages,envelopeBands,applyHighlight};
})();

if(typeof module!=='undefined')module.exports=PolicyStageFlow;
