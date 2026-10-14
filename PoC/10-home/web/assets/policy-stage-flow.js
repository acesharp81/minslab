'use strict';
/* One conserved target ledger, six process stages, shared two-percent shortfall management. */
const PolicyStageFlow = (() => {
  const order=['MOVE_IN','SUPPLY','CONSTRUCTION','APPROVAL','BUSINESS','POLICY'];
  const models=new Map();
  function totals(point){return Object.fromEntries(order.map(k=>[k,k==='POLICY'?(point.totals.POLICY||0)+(point.totals.UNKNOWN||0):(point.totals[k]||0)]));}
  function goalSeries(m,stage){
    const c=m.comparisons?.[stage];
    return (c?.management_points?.length?c.management_points:c?.target_points||[]).slice().sort((a,b)=>a.date.localeCompare(b.date));
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
  const measuredAt=(m,stage,when)=>(m.comparisons?.[stage]?.actual_points||[]).filter(p=>p.date<=when&&p.date<=m.asOf).slice().sort((a,b)=>a.date.localeCompare(b.date)).at(-1);
  const targetAt=(m,stage,when)=>goalSeries(m,stage).filter(p=>p.date<=when).at(-1)?.units??null;
  // Goals change on their saved deadline; no fabricated monthly milestones.
  function trackingPoints(m,sampleDates=null){
    const dates=new Set(sampleDates||[m.start+'-01-01',m.end+'-12-31',m.asOf]);
    if(!sampleDates)for(const c of Object.values(m.comparisons||{}))for(const p of [...(c.target_points||[]),...(c.actual_points||[])])dates.add(p.date);
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
    if(!peak)return {max:Math.max(1,fullMax),focused:false,start,end};
    // Four whole-number intervals and headroom keep labels readable at every scale.
    const raw=peak*1.12/4,power=10**Math.floor(Math.log10(raw));
    const step=Math.max(1,[1,2,2.5,5,10].map(n=>n*power).find(n=>n>=raw));
    return {max:Math.ceil(step)*4,focused:true,start,end,peak};
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
    let svg='';
    for(const stage of order.filter(k=>k!=='POLICY')){
      const targets=goalSeries(m,stage);if(!targets.length)continue;
      const values=plot.map(p=>{
        const valueAt=m.tracking?targetAt:goalAt,target=valueAt(m,stage,p.date),later=order.slice(0,order.indexOf(stage)).map(k=>valueAt(m,k,p.date)).filter(v=>v!=null);
        const floor=Math.min(m.max,Math.max(0,...later)),hi=target==null?null:Math.min(m.max,target);
        return {date:p.date,lo:floor,hi:hi!=null&&hi>=floor?hi:null};
      });
      svg+='<path data-d907-target-area="'+stage+'" d="'+(area(values)||'')+'" fill="url(#d907-target-'+stage+')"><title>'+m.stages[stage]+' 누적 목표 구성 · 날짜 사이 면은 곡선 연결 · 중간값은 시각적 보간</title></path>';
      const observations=m.comparisons?.[stage]?.actual_points||[];
      const gap=values.map(p=>{
        const due=targets.filter(t=>t.date<=p.date&&t.date<=m.asOf).at(-1),actual=observations.filter(a=>a.date<=p.date).at(-1);
        // Show the numerical gap using the last observation; the cards separately assess freshness.
        const known=p.hi!=null&&p.date<=m.asOf&&due&&actual;
        const hi=known?Math.min(p.hi,due.units):null;
        return {...p,hi,lo:known?Math.max(p.lo,Math.min(hi,actual.units)):0,status:known?assessGap(due.units,actual.units).status:'UNKNOWN'};
      });
      for(const status of ['DELAYED','WARNING']){const band=gap.map(p=>({...p,hi:p.status===status?p.hi:null}));if(band.some(p=>p.hi!=null&&p.hi>p.lo))svg+='<path data-d907-gap="'+stage+'" data-gap-status="'+status+'" d="'+(area(band)||'')+'" fill="url(#d907-gap-'+(status==='WARNING'?'warning':'grid')+')"><title>'+m.stages[stage]+' '+(status==='WARNING'?'주의 · 부족률 2% 미만':'지연 · 부족률 2% 이상')+'</title></path>';}
    }
    return svg;
  }
  function layoutCallouts(items,top,bottom){
    const height=36,gap=8,sorted=items.slice().sort((a,b)=>a.anchor-b.anchor);
    let next=top;
    const placed=sorted.map(item=>{const y=Math.max(next,Math.min(bottom-height,item.anchor-height/2));next=y+height+gap;return {...item,y};});
    for(let i=placed.length-1;i>=0;i--)placed[i].y=Math.min(placed[i].y,i===placed.length-1?bottom-height:placed[i+1].y-height-gap);
    return placed;
  }
  function summaryTable(m){
    const {comparisons,policyTarget,originalComparisons={}}=m;
    return Object.entries(m.stages).map(([k,v])=>{
      const check=PolicyStageFlow.comparisonStatus({comparisons,asOf:m.asOf},k),goal=check.due||check.next,actual=check.actual;
      const official=PolicyStageFlow.comparisonStatus({comparisons:originalComparisons,asOf:m.asOf},k),scopeGoal=official.due||official.next;
      const gap=goal&&actual?goal.units-actual.units:null;
      const gapLabel=(check.gap>0?check.assessment.label+' · ':'')+(gap==null?'갭 산정 불가':gap>0?(check.due?'부족 ':'다음 목표까지 ')+num(gap)+'호':gap<0?'초과 '+num(-gap)+'호':'일치 · 0호');
      const referenceLabel=scopeGoal?.basis?.startsWith('연결 사업')?'기간 내 사업 목표':(m.scopeGoalLabel||'정책 연간 목표');
      const reference=scopeGoal&&goal&&scopeGoal.units!==goal.units?'<small class="d907-scope-goal">'+referenceLabel+' '+num(scopeGoal.units)+'호 · '+esc(scopeGoal.date)+'</small>':'';
      return '<button type="button" class="d907-stage-value d907-stage-'+k+'" data-d907-highlight="'+k+'" aria-pressed="false" title="'+v+' 단계 강조 · 다시 누르면 전체 보기"><span class="d907-stage-name">'+esc(k==='CONSTRUCTION'?'착공(건설)':v)+'<span aria-hidden="true">▤</span></span>'+(k==='POLICY'?'<span class="d907-stage-number"><small>전체 목표</small><b>'+num(policyTarget??m.max)+'호</b></span><small>입력 목표 · 그래프 배경 기준</small>':'<span class="d907-stage-number"><small>'+(check.due?'도래 목표':'다음 목표')+'</small><b>'+(goal?num(goal.units)+'호':'미확보')+'</b></span><small>'+esc(goal?.date||'목표일 미확보')+'</small><span class="d907-stage-number"><small>누적 측정</small><b>'+(actual?num(actual.units)+'호':'미측정')+'</b></span><small>'+esc(actual?.date||'측정일 미확보')+'</small><strong class="d907-stage-gap '+(check.status==='DELAYED'?'is-short':check.status==='WARNING'?'is-warning':'')+'">'+gapLabel+'</strong>'+(check.stale?'<small>측정 갱신 필요</small>':'')+reference)+'</button>';
    }).join('');
  }
  function render(m){
    const model=m;models.set(m.instanceKey||'policy',m);const width=m.axisUnit==='month'?Math.max(1100,(m.end-m.start+1)*12*30+148):1100;model.plotRight=width-58;const max=m.max,left=90,right=model.plotRight,top=85,bottom=410,first=Date.parse(m.start+'-01-01'),last=Date.parse(m.end+'-12-31');
    const x=date=>left+(Date.parse(date)-first)/(last-first)*(right-left),y=value=>bottom-(bottom-top)*value/max;
    if(m.tracking)m.points=trackingPoints(m);
    const points=(m.tracking?monthlyPoints(m):m.points).map(p=>({...p,display:totals(p)}));
    // Duplicate the first/last observation at the plot edge, not across missing internal dates.
    const plot=points.length?[{...points[0],date:m.start+'-01-01'},...points,{...points.at(-1),date:m.end+'-12-31'}]:[];
    const stacked=d3.stack().keys(order).value((p,k)=>p.display[k]||0)(plot);
    const area=d3.area().x(p=>x(p.data.date)).y0(p=>y(p[0])).y1(p=>y(p[1])).curve(d3.curveMonotoneX);
    const targetDefs=order.map(k=>'<pattern id="d907-target-'+k+'" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(40)"><rect width="10" height="10" fill="'+m.colors[k]+'" fill-opacity=".18"/><line y2="10" stroke="'+m.colors[k]+'" stroke-width="2.5"/></pattern>').join('');
    const defs=targetDefs+'<clipPath id="d907-past"><rect x="90" y="85" width="'+Math.max(0,Math.min(right,x(m.asOf))-left)+'" height="325"/></clipPath><pattern id="d907-gap-grid" width="9" height="9" patternUnits="userSpaceOnUse"><rect width="9" height="9" fill="#fff1f3"/><path d="M0 0L9 9M9 0L0 9" stroke="#c4203a" stroke-width="1.2"/></pattern>';
    const warningDef='<pattern id="d907-gap-warning" width="9" height="9" patternUnits="userSpaceOnUse"><rect width="9" height="9" fill="#fff8df"/><path d="M0 0L9 9M9 0L0 9" stroke="#d99b13" stroke-width="1.2"/></pattern>';
    let paths=stacked.filter(series=>!m.tracking||series.key!=='POLICY').map(series=>'<g data-d907-band="'+series.key+'">'+(m.tracking?'':'<path d="'+(area(series)||'')+'" fill="url(#d907-target-'+series.key+')" stroke="#fff" stroke-width="1.2"/>')+'<path d="'+(area(series)||'')+'" fill="'+m.colors[series.key]+'" clip-path="url(#d907-past)" stroke="#fff" stroke-width="1.2"/></g>').join('');
    // Missing classifications are a hatched portion of the policy/verification pool, not invented policy achievements.
    const uncertainty=plot.map(p=>({data:p,lo:Math.max(0,Object.values(p.totals).reduce((a,b)=>a+b,0)-(p.totals.UNKNOWN||0)),hi:Object.values(p.totals).reduce((a,b)=>a+b,0)}));
    const unknownArea=d3.area().x(p=>x(p.data.date)).y0(p=>y(p.lo)).y1(p=>y(p.hi));
    if(!m.tracking)paths+='<path data-d907-uncertain d="'+(unknownArea(uncertainty)||'')+'" fill="url(#d907-unknown)"/>';
    const nowX=Date.parse(m.asOf)>=first&&Date.parse(m.asOf)<=last?x(m.asOf):null;

    let callouts='';
    const gapChecks=['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'].map(k=>comparisonStatus(m,k)).filter(c=>c.gap>0);
    if(nowX!=null){
      const cx=Math.max(left+155,Math.min(right-155,nowX+160));
      const labels=layoutCallouts(gapChecks.map(c=>({...c,anchor:Math.max(top,Math.min(bottom,y(c.due.units)))})),top+4,bottom-4);
      for(const c of labels){
        const {color,text,label}=c.assessment;
        const title=(m.stages[c.stage]||c.label)+' '+num(c.gap)+'호 부족 · '+formatGapRate(c.rate);
        const note=c.due.date.slice(0,7)+' 목표 · '+label+(c.stale?' · 측정 갱신 필요':'');
        callouts+='<g data-d907-gap-callout="'+c.stage+'" data-gap-status="'+c.status+'"><path d="M'+nowX+' '+c.anchor+' L'+(cx-149)+' '+(c.y+18)+'" stroke="'+color+'" stroke-width="1.3" fill="none"/><circle cx="'+nowX+'" cy="'+c.anchor+'" r="4" fill="white" stroke="'+color+'" stroke-width="1.5"/><rect data-d907-callout-box x="'+(cx-149)+'" y="'+c.y+'" width="298" height="36" rx="5" fill="'+color+'"/><text x="'+cx+'" y="'+(c.y+14)+'" text-anchor="middle" fill="'+text+'" font-size="12" font-weight="800">'+esc(title)+'</text><text x="'+cx+'" y="'+(c.y+28)+'" text-anchor="middle" fill="'+text+'" font-size="10">'+esc(note)+'</text></g>';
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
      const goalBands=order.filter(k=>k!=='POLICY').map(key=>{
        const valueAt=m.tracking?targetAt:goalAt,hi=valueAt(m,key,date),later=order.slice(0,order.indexOf(key)).map(k=>valueAt(m,k,date)).filter(v=>v!=null);
        return {key,lo:Math.min(max,Math.max(0,...later)),hi:hi==null?null:Math.min(max,hi)};
      }).filter(b=>b.hi!=null&&b.hi>b.lo);
      const covered=mid=>goalBands.some(b=>mid>=b.lo&&mid<=b.hi);
      const label=(key,mid,text)=>'<text data-d907-label="'+key+'" class="d907-band-label" x="'+x(date)+'" y="'+(y(mid)+4)+'" text-anchor="middle">'+esc(text)+'</text>';
      let base=0;
      for(const key of order){
        const value=key==='POLICY'?(nearest.totals.POLICY||0):nearest.display[key],mid=base+value/2;
        if((!m.tracking||date<=m.asOf)&&value/max*(bottom-top)>=23&&mid<=max&&!covered(mid))bandLabels+=label(key,mid,(6-order.indexOf(key))+' '+m.stages[key]+(key==='POLICY'?' · 목표 잔여':date>m.asOf?' 예정':''));
        base+=value;
      }
      const unknown=nearest.totals.UNKNOWN||0,mid=base+unknown/2;
      if(unknown/max*(bottom-top)>=23&&mid<=max&&!covered(mid))bandLabels+=label('UNKNOWN',mid,'단계 미확인');
      for(const b of goalBands)if((!m.tracking||date>m.asOf)&&(b.hi-b.lo)/max*(bottom-top)>=23)bandLabels+=label(b.key,(b.hi+b.lo)/2,(6-order.indexOf(b.key))+' '+m.stages[b.key]+' 목표');
    }
    let boundaries='';
    if(m.tracking){
      const line=d3.line().x(p=>x(p.date)).y(p=>y(p.units)).curve(d3.curveMonotoneX);
      for(const k of order.filter(k=>k!=='POLICY')){
        const goals=goalSeries(m,k),observed=(m.comparisons[k]?.actual_points||[]).filter(p=>p.date<=m.asOf);
        const target=goals.length?plot.map(p=>({date:p.date,units:targetAt(m,k,p.date)})).filter(p=>p.units!=null):[];
        const actual=observed.length?plot.filter(p=>p.date<=m.asOf).map(p=>({date:p.date,units:measuredAt(m,k,p.date)?.units})).filter(p=>p.units!=null):[];
        for(const [kind,ps,dash] of [['target',target,'7 4'],['actual',actual,'']]){
          if(!ps.length)continue;
          boundaries+='<path data-d907-comparison-line="'+kind+'" data-stage="'+k+'" d="'+line(ps)+'" fill="none" stroke="white" stroke-width="4" stroke-dasharray="'+dash+'"/><path data-d907-'+kind+'-line="'+k+'" d="'+line(ps)+'" fill="none" stroke="'+m.colors[k]+'" stroke-width="2.3" stroke-dasharray="'+dash+'"><title>'+esc(m.stages[k])+' '+(kind==='target'?'목표':'측정값')+'</title></path>';
        }
        const t=targetAt(m,k,m.asOf),a=observed.at(-1)?.units;
        for(const [kind,value] of [['target',t],['actual',a]])if(value!=null)boundaries+='<circle data-d907-reference-value="'+kind+'" data-stage="'+k+'" data-units="'+value+'" cx="'+x(m.asOf)+'" cy="'+y(value)+'" r="'+(kind==='target'?4:3)+'" fill="'+(kind==='target'?'white':m.colors[k])+'" stroke="'+m.colors[k]+'" stroke-width="1.5"><title>'+esc(m.stages[k])+' '+(kind==='target'?'도래 목표 ':'측정값 ')+num(value)+'호</title></circle>';
      }
    }
    const selectedX=x(m.year+'-07-01'),selection='<rect data-d907-selection="'+m.year+'" x="'+(selectedX-4)+'" y="85" width="8" height="325" fill="#1967c0" opacity=".15"/>';
    const reference=nowX==null?'':'<rect x="'+(nowX-10)+'" y="72" width="20" height="339" fill="#193d63" opacity=".13"/><line data-d907-now-line x1="'+nowX+'" x2="'+nowX+'" y1="72" y2="416" stroke="#173a60" stroke-width="1.8" stroke-dasharray="4 3"/><rect x="'+(nowX-54)+'" y="450" width="108" height="22" rx="4" fill="#183c61"/><text x="'+nowX+'" y="465" text-anchor="middle" fill="white">기준일 '+m.asOf.slice(0,7)+'</text>';
    const html='<div class="d907-chart-wrap '+(m.axisUnit==='month'?'d907-monthly':'')+'"><svg class="d907-chart" data-d907-model="'+esc(m.instanceKey||'policy')+'" data-y-max="'+max+'" data-start-year="'+m.start+'" data-axis-unit="'+m.axisUnit+'" width="'+width+'" viewBox="0 60 '+width+' 435" preserveAspectRatio="none" role="img" aria-label="정책·사업화·인허가·건설·공급·입주 월별 누적 구성, '+esc(m.axisBasis||'정책 목표')+' '+num(max)+'호"><defs>'+defs+warningDef+'<clipPath id="d907-plot"><rect x="90" y="85" width="'+(right-left)+'" height="325"/></clipPath><pattern id="d907-hatch" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(40)"><line x1="0" y1="0" x2="0" y2="10" stroke="white" stroke-width="2" opacity=".44"/></pattern><pattern id="d907-unknown" width="7" height="7" patternUnits="userSpaceOnUse"><rect width="7" height="7" fill="#edf0f3"/><circle cx="2" cy="2" r="1.2" fill="#8795a5"/></pattern></defs>'+headers+'<text x="34" y="72">(호)</text>'+'<g clip-path="url(#d907-plot)">'+(m.tracking?'<rect data-d907-policy-background x="'+left+'" y="'+Math.max(top,y(m.policyTarget??max))+'" width="'+(right-left)+'" height="'+Math.min(bottom-top,(bottom-top)*(m.policyTarget??max)/max)+'" fill="#eef2f6"/>':'')+paths+targetAreas(m,plot,x,y)+bandLabels+boundaries+'</g>'+ticks+selection+reference+callouts+labels+'<line class="d907-hover-line" x1="0" x2="0" y1="85" y2="410" stroke="#142d4b" stroke-width="1" visibility="hidden"/><rect data-d907-hover x="90" y="72" width="'+(right-left)+'" height="343" fill="transparent"/></svg><div class="d907-chart-tooltip" role="status" hidden></div></div>';
    return m.instanceKey?html.replaceAll('id="d907-','id="d907-'+m.instanceKey+'-').replaceAll('url(#d907-','url(#d907-'+m.instanceKey+'-'):html;
  }
  function start(){
    document.addEventListener('click',e=>{
      const button=e.target.closest('[data-d907-highlight]');if(!button)return;
      const host=button.closest('.d907-flow'),key=button.getAttribute('aria-pressed')==='true'?'':button.dataset.d907Highlight;
      host.querySelectorAll('[data-d907-highlight]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.d907Highlight===key)));
      host.querySelectorAll('[data-d907-band],[data-d907-target-area],[data-d907-gap],[data-d907-delay],[data-d907-label],[data-d907-comparison-line],[data-d907-target-line],[data-d907-actual-line],[data-d907-reference-value],[data-d907-gap-callout],[data-d907-policy-background]').forEach(n=>n.classList.toggle('d907-dimmed',Boolean(key)&&(n.hasAttribute('data-d907-policy-background')?'POLICY':n.dataset.stage||Object.values(n.dataset)[0])!==key));
    });
    document.addEventListener('pointermove',e=>{
      const hit=e.target.closest('[data-d907-hover]');if(!hit)return;const model=models.get(hit.ownerSVGElement.dataset.d907Model);if(!model||!model.points.length)return;const svg=hit.ownerSVGElement,wrap=svg.parentElement,tip=wrap.querySelector('.d907-chart-tooltip'),pt=svg.createSVGPoint();pt.x=e.clientX;pt.y=e.clientY;const local=pt.matrixTransform(svg.getScreenCTM().inverse());
      const f=Date.parse(model.start+'-01-01'),l=Date.parse(model.end+'-12-31'),date=f+(Math.max(90,Math.min(model.plotRight,local.x))-90)/(model.plotRight-90)*(l-f),p=model.points.reduce((a,b)=>!a?b:Math.abs(Date.parse(a.date)-date)<Math.abs(Date.parse(b.date)-date)?a:b),t=totals(p);
      const plans=(model.constructionPlans||[]).filter(c=>p.date>=c.plan.start_date),weight=plans.reduce((n,c)=>n+c.units,0);
      const plannedPct=weight?plans.reduce((n,c)=>n+c.units*Math.max(0,Math.min(100,(Date.parse(p.date)-Date.parse(c.plan.start_date))/(Date.parse(c.plan.completion_date)-Date.parse(c.plan.start_date))*100)),0)/weight:null;
      const progressNote=plannedPct==null?'':'<br>연결 사업 추정 계획 공정률 '+plannedPct.toFixed(1)+'% · '+num(weight)+'호 기준 (기간 비례, 공식 목표 아님)';
      tip.hidden=false;tip.innerHTML=model.tracking?'<h4>'+p.date.slice(0,7).replace('-','.')+' · 누적 목표 / 측정값</h4>'+order.filter(k=>k!=='POLICY').reverse().map(k=>{const t=targetAt(model,k,p.date),a=measuredAt(model,k,p.date),future=p.date>model.asOf;return '<div><i class="d907-color-'+k+'"></i>'+esc(model.stages[k])+'<b>'+(t==null?'목표 미확보':num(t)+'호')+' / '+(future?'미도래':a?num(a.units)+'호':'미측정')+'<small>'+(t!=null&&a&&!future?assessGap(t,a.units).label+' · 갭 '+num(t-a.units)+'호':'')+'</small></b></div>';}).join('')+'<span class="d907-tip-foot">등록 사업 · 사용자 입력·추정 포함<br>갭 = 목표 − 최근 측정값 · 단계 간 합산 금지</span>':'<h4>'+p.date.slice(0,7).replace('-','.')+' <small>'+(p.forecast?'계획·일정':'확인 기준')+'</small></h4><p>전체 '+num(Object.values(t).reduce((a,b)=>a+b,0))+'호</p><div class="d907-tip-head"><span>단계</span><span>현재 단계 물량 / 누적 목표</span></div>'+Object.entries(model.stages).map(([k,v])=>'<div><i class="d907-color-'+k+'"></i>'+v+'<b>'+num(t[k]||0)+'호'+(goalAt(model,k,p.date)==null?'':'<small>누적 목표 '+num(goalAt(model,k,p.date))+'호</small>')+'</b></div>').join('')+'<span class="d907-tip-foot">정책 구간: 목표 잔여 '+num(p.totals.POLICY||0)+'호 · 단계 미확인 '+num(p.totals.UNKNOWN||0)+'호'+(p.forecast?'<br>미래 영역은 공식 목표와 일정에 따른 전망':'')+progressNote+'<br>입주는 시작일 확인 사업의 물량 · 실제 입주 가구 수 아님</span>';
      const rect=wrap.getBoundingClientRect();tip.style.left=Math.max(wrap.parentElement.scrollLeft+8,Math.min(wrap.parentElement.scrollLeft+wrap.parentElement.clientWidth-290,e.clientX-rect.left+18))+'px';tip.style.top='78px';const line=svg.querySelector('.d907-hover-line');line.setAttribute('x1',local.x);line.setAttribute('x2',local.x);line.setAttribute('visibility','visible');
    });
    document.addEventListener('pointerout',e=>{if(!e.target.hasAttribute?.('data-d907-hover'))return;const wrap=e.target.closest('.d907-chart-wrap');wrap?.querySelector('.d907-chart-tooltip')?.setAttribute('hidden','');wrap?.querySelector('.d907-hover-line')?.setAttribute('visibility','hidden');});
  }
  return {assessGap,formatGapRate,render,start,totals,trackingPoints,monthlyPoints,referenceAxis,comparisonStatus,delaySummary,layoutCallouts,summaryTable};
})();

if(typeof module!=='undefined')module.exports=PolicyStageFlow;
