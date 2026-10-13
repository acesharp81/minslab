'use strict';
/* One conserved target ledger, six process stages, evidence-only delay overlays. */
const PolicyStageFlow = (() => {
  const order=['MOVE_IN','SUPPLY','CONSTRUCTION','APPROVAL','BUSINESS','POLICY'];
  let model;
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
  function comparisonStatus(m,stage){
    const c=m.comparisons?.[stage]||{},targets=goalSeries(m,stage),due=targets.filter(t=>t.date<=m.asOf).at(-1);
    const actual=(c.actual_points||[]).filter(a=>a.date<=m.asOf).slice().sort((a,b)=>a.date.localeCompare(b.date)).at(-1);
    const confirmed=new Map();for(const d of m.delays||[])if(d.stage===stage)confirmed.set(d.project_id,Math.max(confirmed.get(d.project_id)||0,d.units));
    const confirmedUnits=[...confirmed.values()].reduce((a,b)=>a+b,0);
    let status='NO_TARGET',gap=null;
    if(targets.length&&!due)status='NOT_DUE';
    if(due){
      if(!actual)status='NO_ACTUAL';
      else if(actual.units>=due.units){status='REACHED';gap=0;}
      else if(actual.date<due.date)status='STALE_ACTUAL';
      else {gap=Math.max(0,due.units-actual.units);status=gap?'GAP':'REACHED';}
    }
    return {stage,label:stage==='MOVE_IN'?'입주':c.label||m.stages?.[stage]||stage,status,due,actual,gap,confirmedUnits,next:targets.find(t=>t.date>m.asOf),rate:gap!=null&&due?.units>0?100*gap/due.units:null};
  }
  function delaySummary(m){
    const stages=['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],checks=stages.map(k=>comparisonStatus(m,k));
    const alerts=checks.filter(c=>c.gap>0||c.confirmedUnits>0),unknown=checks.filter(c=>['NO_ACTUAL','STALE_ACTUAL'].includes(c.status));
    const heading=alerts.length?'계획 대비 부족·지연 '+alerts.length+'개 단계':unknown.length?'기한 경과 · 실적 확인이 필요한 '+unknown.length+'개 단계':'현재 비교 가능한 범위의 지연 점검';
    return '<section class="d907-delay-summary" aria-label="기준일 계획 대비 지연 점검"><header><strong>'+heading+'</strong><span>기준일 '+esc(m.asOf)+' · 기한이 도래한 누적 목표 기준</span></header><div class="d907-delay-cards">'+checks.map(c=>{
      const alert=c.gap>0||c.confirmedUnits>0,warn=['NO_ACTUAL','STALE_ACTUAL'].includes(c.status);
      const label=c.confirmedUnits?'지연 확인 '+num(c.confirmedUnits)+'호':c.gap>0?'목표 대비 '+num(c.gap)+'호 부족':({NO_TARGET:'판단 불가 · 목표 미확보',NOT_DUE:'목표 기한 전',NO_ACTUAL:'판단 불가 · 실적 미확보',STALE_ACTUAL:'판단 불가 · 실적 갱신 필요',REACHED:'확인량 기준 목표 도달'})[c.status];
      const target=c.due?'목표 '+num(c.due.units)+'호 · '+c.due.date:c.next?'다음 목표 '+num(c.next.units)+'호 · '+c.next.date:'기한·목표 입력 필요';
      return '<button type="button" data-d907-delay-stage="'+c.stage+'" data-delay-status="'+c.status+'" class="d907-delay-card '+(alert?'alert':warn?'warn':'neutral')+'"><span>'+esc(c.label)+(c.rate!=null&&c.rate>0?' · 부족 '+c.rate.toFixed(1)+'%':'')+'</span><strong>'+esc(label)+'</strong><small>'+esc(target)+'</small><small>'+(c.actual?'확인 '+num(c.actual.units)+'호 · '+c.actual.date+(c.actual.review_units?' · 연결 검토 '+num(c.actual.review_units)+'호 포함':''):'실적 미확보 · 0호로 간주하지 않음')+'</small>'+(alert?'<em>'+(c.confirmedUnits?'지연 근거 확인':'지연 검토 · 미연결 실적 확인 필요')+'</em>':'')+'</button>';
    }).join('')+'</div><p>부족량은 기한 도래 목표 − 같은 단계의 누적 확인량입니다. 단계 간 부족량은 합산하지 않습니다. 연말 목표를 월별로 보간한 값은 지연 판정에 사용하지 않습니다.</p></section>';
  }
  function targetAreas(m,plot,x,y){
    const area=d3.area().defined(p=>p.hi!=null).x(p=>x(p.date)).y0(p=>y(p.lo)).y1(p=>y(p.hi)).curve(d3.curveLinear);
    let svg='';
    for(const stage of order.filter(k=>k!=='POLICY')){
      const targets=goalSeries(m,stage);if(!targets.length)continue;
      const values=plot.map(p=>{
        const target=goalAt(m,stage,p.date),later=order.slice(0,order.indexOf(stage)).map(k=>goalAt(m,k,p.date)).filter(v=>v!=null);
        const floor=Math.min(m.max,Math.max(0,...later)),hi=target==null?null:Math.min(m.max,target);
        return {date:p.date,lo:floor,hi:hi!=null&&hi>=floor?hi:null};
      });
      svg+='<path data-d907-target-area="'+stage+'" d="'+(area(values)||'')+'" fill="url(#d907-target-'+stage+')"><title>'+m.stages[stage]+' 누적 목표 구성 · 날짜 사이 면은 직선 연결</title></path>';
      const observations=m.comparisons?.[stage]?.actual_points||[];
      const gap=values.map(p=>{
        const due=targets.filter(t=>t.date<=p.date&&t.date<=m.asOf).at(-1),actual=observations.filter(a=>a.date<=p.date).at(-1);
        // Missing values and observations older than the deadline do not prove lateness.
        const known=p.hi!=null&&p.date<=m.asOf&&due&&actual&&actual.date>=due.date;
        const hi=known?Math.min(p.hi,due.units):null;
        return {...p,hi,lo:known?Math.max(p.lo,Math.min(hi,actual.units)):0};
      });
      if(gap.some(p=>p.hi!=null&&p.hi>p.lo))svg+='<path data-d907-gap="'+stage+'" d="'+(area(gap)||'')+'" fill="url(#d907-gap-grid)"><title>'+m.stages[stage]+' 목표 대비 확인량 차이 · 지연 검토</title></path>';
    }
    return svg;
  }
  function render(m){
    model=m;const width=m.axisUnit==='month'?Math.max(1100,(m.end-m.start+1)*12*30+148):1100;model.plotRight=width-58;const max=m.max,left=90,right=model.plotRight,top=85,bottom=265,first=Date.parse(m.start+'-01-01'),last=Date.parse(m.end+'-12-31');
    const x=date=>left+(Date.parse(date)-first)/(last-first)*(right-left),y=value=>bottom-(bottom-top)*value/max;
    const points=m.points.map(p=>({...p,display:totals(p)}));
    // Duplicate the first/last observation at the plot edge, not across missing internal dates.
    const plot=points.length?[{...points[0],date:m.start+'-01-01'},...points,{...points.at(-1),date:m.end+'-12-31'}]:[];
    const stacked=d3.stack().keys(order).value((p,k)=>p.display[k]||0)(plot);
    const area=d3.area().x(p=>x(p.data.date)).y0(p=>y(p[0])).y1(p=>y(p[1])).curve(d3.curveLinear);
    const targetDefs=order.map(k=>'<pattern id="d907-target-'+k+'" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(40)"><rect width="10" height="10" fill="white"/><rect width="10" height="10" fill="'+m.colors[k]+'" fill-opacity=".18"/><line y2="10" stroke="'+m.colors[k]+'" stroke-width="2.5"/></pattern>').join('');
    const defs=targetDefs+'<clipPath id="d907-past"><rect x="90" y="85" width="'+Math.max(0,Math.min(right,x(m.asOf))-left)+'" height="180"/></clipPath><pattern id="d907-gap-grid" width="9" height="9" patternUnits="userSpaceOnUse"><rect width="9" height="9" fill="#fff1f3"/><path d="M0 0L9 9M9 0L0 9" stroke="#c4203a" stroke-width="1.2"/></pattern>';
    let paths=stacked.map(series=>'<g data-d907-band="'+series.key+'"><path d="'+(area(series)||'')+'" fill="url(#d907-target-'+series.key+')" stroke="#fff" stroke-width="1.2"/><path d="'+(area(series)||'')+'" fill="'+m.colors[series.key]+'" clip-path="url(#d907-past)" stroke="#fff" stroke-width="1.2"/></g>').join('');
    // Missing classifications are a hatched portion of the policy/verification pool, not invented policy achievements.
    const uncertainty=plot.map(p=>({data:p,lo:Math.max(0,Object.values(p.totals).reduce((a,b)=>a+b,0)-(p.totals.UNKNOWN||0)),hi:Object.values(p.totals).reduce((a,b)=>a+b,0)}));
    const unknownArea=d3.area().x(p=>x(p.data.date)).y0(p=>y(p.lo)).y1(p=>y(p.hi));
    paths+='<path data-d907-uncertain d="'+(unknownArea(uncertainty)||'')+'" fill="url(#d907-unknown)"/>';
    const nowX=Date.parse(m.asOf)>=first&&Date.parse(m.asOf)<=last?x(m.asOf):null;

    // The overlay is capped to the affected stage; repeated issues for one cohort never inflate the band.
    let red='',callouts='';for(const s of stacked){if(s.key==='POLICY')continue;const delayed=m.delays.filter(d=>(d.stage==='COMPLETION'?'CONSTRUCTION':d.stage)===s.key);const byProject=new Map();for(const d of delayed)byProject.set(d.project_id,Math.max(byProject.get(d.project_id)||0,d.units));const n=[...byProject.values()].reduce((a,b)=>a+b,0);if(!n)continue;
      const overlay=s.map(p=>({data:p.data,lo:p[1]-Math.min(n,p[1]-p[0]),hi:p[1]})).filter(p=>p.data.date>=m.asOf);
      red+='<path data-d907-delay="'+s.key+'" d="'+(unknownArea(overlay)||'')+'" fill="#c4203a"><title>'+m.stages[s.key]+' 지연 확인 '+num(n)+'호</title></path>';
      if(nowX!=null){const at=s.find(p=>p.data.date>=m.asOf)||s.at(-1),cy=Math.max(top+30,Math.min(bottom-25,y(at[1])-20)),cx=Math.max(left+105,Math.min(right-105,nowX+108));callouts+='<g data-d907-delay-label><rect x="'+(cx-98)+'" y="'+(cy-14)+'" width="196" height="26" rx="4" fill="#283d59" fill-opacity=".94"/><rect x="'+(cx-95)+'" y="'+(cy-10)+'" width="4" height="18" rx="2" fill="#ef5369"/><text x="'+cx+'" y="'+(cy+3)+'" fill="white" text-anchor="middle" font-weight="700">'+m.stages[s.key]+' 지연 '+num(n)+'호</text></g>';}
    }
    const gapChecks=['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'].map(k=>comparisonStatus(m,k)).filter(c=>c.gap>0);
    const focusGap=gapChecks.find(c=>c.stage===m.metric)||gapChecks.sort((a,b)=>b.gap-a.gap)[0];
    if(focusGap&&nowX!=null){
      const cx=Math.max(left+155,Math.min(right-155,nowX+160)),cy=top+38,anchor=Math.max(top,Math.min(bottom,y(focusGap.due.units)));
      callouts+='<g data-d907-gap-callout="'+focusGap.stage+'"><path d="M'+nowX+' '+anchor+' L'+cx+' '+(cy+28)+'" stroke="#c4203a" stroke-width="2" fill="none"/><circle cx="'+nowX+'" cy="'+anchor+'" r="5" fill="white" stroke="#c4203a" stroke-width="2"/><rect x="'+(cx-149)+'" y="'+(cy-22)+'" width="298" height="50" rx="6" fill="#a61b32"/><text x="'+cx+'" y="'+(cy-3)+'" text-anchor="middle" fill="white" font-size="14" font-weight="800">'+esc(focusGap.label)+' '+num(focusGap.gap)+'호 부족 · '+focusGap.rate.toFixed(1)+'%</text><text x="'+cx+'" y="'+(cy+16)+'" text-anchor="middle" fill="white" font-size="11">'+focusGap.due.date.slice(0,7)+' 목표 대비 · 지연 검토</text></g>';
    }
    const dense=m.axisUnit!=='month';
    const headers='';
    const ticks=[0,.25,.5,.75,1].map(r=>'<line x1="'+left+'" x2="'+right+'" y1="'+y(max*r)+'" y2="'+y(max*r)+'" stroke="'+(r===1?'#476f99':'#fff')+'" stroke-dasharray="3 4"/><text x="80" y="'+(y(max*r)+4)+'" text-anchor="end">'+num(max*r)+'</text>').join('');
    const labels=Array.from({length:(m.end-m.start+1)*(dense?1:12)},(_,i)=>{
      const year=m.start+(dense?i:Math.floor(i/12)),month=dense?1:i%12+1,date=year+'-'+String(month).padStart(2,'0')+'-01';
      const label=dense?String(year):String(month).padStart(2,'0');
      return '<g data-d907-month="'+date.slice(0,7)+'"><line x1="'+x(date)+'" x2="'+x(date)+'" y1="265" y2="270" stroke="#90a9bf"/><text x="'+x(date)+'" y="286" text-anchor="middle">'+label+'</text>'+(!dense&&month===1?'<text x="'+(x(date)+12)+'" y="306" font-weight="700">'+year+'년</text>':'')+'</g>';
    }).join('');
    let bandLabels='';
    const labelStep=(right-left)/(m.end-m.start+1)<120?2:1;
    for(let year=m.start;year<=m.end;year+=labelStep){
      const date=year+'-07-01',nearest=points.reduce((a,b)=>!a?b:Math.abs(Date.parse(a.date)-Date.parse(date))<Math.abs(Date.parse(b.date)-Date.parse(date))?a:b,null);
      if(!nearest)continue;
      const goalBands=order.filter(k=>k!=='POLICY').map(key=>{
        const hi=goalAt(m,key,date),later=order.slice(0,order.indexOf(key)).map(k=>goalAt(m,k,date)).filter(v=>v!=null);
        return {key,lo:Math.min(max,Math.max(0,...later)),hi:hi==null?null:Math.min(max,hi)};
      }).filter(b=>b.hi!=null&&b.hi>b.lo);
      const covered=mid=>goalBands.some(b=>mid>=b.lo&&mid<=b.hi);
      const label=(key,mid,text)=>'<text data-d907-label="'+key+'" class="d907-band-label" x="'+x(date)+'" y="'+(y(mid)+4)+'" text-anchor="middle">'+esc(text)+'</text>';
      let base=0;
      for(const key of order){
        const value=key==='POLICY'?(nearest.totals.POLICY||0):nearest.display[key],mid=base+value/2;
        if(value/max*(bottom-top)>=23&&mid<=max&&!covered(mid))bandLabels+=label(key,mid,(6-order.indexOf(key))+' '+m.stages[key]+(key==='POLICY'?' · 목표 잔여':date>m.asOf?' 예정':''));
        base+=value;
      }
      const unknown=nearest.totals.UNKNOWN||0,mid=base+unknown/2;
      if(unknown/max*(bottom-top)>=23&&mid<=max&&!covered(mid))bandLabels+=label('UNKNOWN',mid,'단계 미확인');
      for(const b of goalBands)if((b.hi-b.lo)/max*(bottom-top)>=23)bandLabels+=label(b.key,(b.hi+b.lo)/2,(6-order.indexOf(b.key))+' '+m.stages[b.key]+' 목표');
    }
    const selectedX=x(m.year+'-07-01'),selection='<rect data-d907-selection="'+m.year+'" x="'+(selectedX-4)+'" y="85" width="8" height="180" fill="#1967c0" opacity=".15"/>';
    const reference=nowX==null?'':'<rect x="'+(nowX-10)+'" y="72" width="20" height="194" fill="#193d63" opacity=".13"/><line data-d907-now-line x1="'+nowX+'" x2="'+nowX+'" y1="72" y2="271" stroke="#173a60" stroke-width="1.8" stroke-dasharray="4 3"/><rect x="'+(nowX-54)+'" y="305" width="108" height="22" rx="4" fill="#183c61"/><text x="'+nowX+'" y="320" text-anchor="middle" fill="white">기준일 '+m.asOf.slice(0,7)+'</text>';
    return '<div class="d907-chart-wrap '+(m.axisUnit==='month'?'d907-monthly':'')+'"><svg class="d907-chart" data-y-max="'+max+'" data-start-year="'+m.start+'" data-axis-unit="'+m.axisUnit+'" width="'+width+'" viewBox="0 60 '+width+' 290" preserveAspectRatio="none" role="img" aria-label="정책·사업화·인허가·건설·공급·입주 월별 누적 구성, '+esc(m.axisBasis||'정책 목표')+' '+num(max)+'호"><defs>'+defs+'<clipPath id="d907-plot"><rect x="90" y="85" width="'+(right-left)+'" height="180"/></clipPath><pattern id="d907-hatch" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(40)"><line x1="0" y1="0" x2="0" y2="10" stroke="white" stroke-width="2" opacity=".44"/></pattern><pattern id="d907-unknown" width="7" height="7" patternUnits="userSpaceOnUse"><rect width="7" height="7" fill="#edf0f3"/><circle cx="2" cy="2" r="1.2" fill="#8795a5"/></pattern></defs>'+headers+'<text x="34" y="72">(호)</text>'+'<g clip-path="url(#d907-plot)">'+paths+targetAreas(m,plot,x,y)+red+bandLabels+'</g>'+ticks+selection+reference+callouts+labels+'<line class="d907-hover-line" x1="0" x2="0" y1="85" y2="265" stroke="#142d4b" stroke-width="1" visibility="hidden"/><rect data-d907-hover x="90" y="72" width="'+(right-left)+'" height="198" fill="transparent"/></svg><div class="d907-chart-tooltip" role="status" hidden></div></div>';
  }
  function start(){
    document.addEventListener('click',e=>{
      const button=e.target.closest('[data-d907-highlight]');if(!button)return;
      const host=button.closest('.d907-flow'),key=button.getAttribute('aria-pressed')==='true'?'':button.dataset.d907Highlight;
      host.querySelectorAll('[data-d907-highlight]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.d907Highlight===key)));
      host.querySelectorAll('[data-d907-band],[data-d907-target-area],[data-d907-gap],[data-d907-delay],[data-d907-label]').forEach(n=>n.classList.toggle('d907-dimmed',Boolean(key)&&Object.values(n.dataset)[0]!==key));
    });
    document.addEventListener('pointermove',e=>{
      const hit=e.target.closest('[data-d907-hover]');if(!hit||!model||!model.points.length)return;const svg=hit.ownerSVGElement,wrap=svg.parentElement,tip=wrap.querySelector('.d907-chart-tooltip'),pt=svg.createSVGPoint();pt.x=e.clientX;pt.y=e.clientY;const local=pt.matrixTransform(svg.getScreenCTM().inverse());
      const f=Date.parse(model.start+'-01-01'),l=Date.parse(model.end+'-12-31'),date=f+(Math.max(90,Math.min(model.plotRight,local.x))-90)/(model.plotRight-90)*(l-f),p=model.points.reduce((a,b)=>!a?b:Math.abs(Date.parse(a.date)-date)<Math.abs(Date.parse(b.date)-date)?a:b),t=totals(p);
      const plans=(model.constructionPlans||[]).filter(c=>p.date>=c.plan.start_date),weight=plans.reduce((n,c)=>n+c.units,0);
      const plannedPct=weight?plans.reduce((n,c)=>n+c.units*Math.max(0,Math.min(100,(Date.parse(p.date)-Date.parse(c.plan.start_date))/(Date.parse(c.plan.completion_date)-Date.parse(c.plan.start_date))*100)),0)/weight:null;
      const progressNote=plannedPct==null?'':'<br>연결 사업 추정 계획 공정률 '+plannedPct.toFixed(1)+'% · '+num(weight)+'호 기준 (기간 비례, 공식 목표 아님)';
      tip.hidden=false;tip.innerHTML='<h4>'+p.date.slice(0,7).replace('-','.')+' <small>'+(p.forecast?'계획·일정':'확인 기준')+'</small></h4><p>전체 '+num(Object.values(t).reduce((a,b)=>a+b,0))+'호</p><div class="d907-tip-head"><span>단계</span><span>현재 단계 물량 / 누적 목표</span></div>'+Object.entries(model.stages).map(([k,v])=>'<div><i class="d907-color-'+k+'"></i>'+v+'<b>'+num(t[k]||0)+'호'+(goalAt(model,k,p.date)==null?'':'<small>누적 목표 '+num(goalAt(model,k,p.date))+'호</small>')+'</b></div>').join('')+'<span class="d907-tip-foot">정책 구간: 목표 잔여 '+num(p.totals.POLICY||0)+'호 · 단계 미확인 '+num(p.totals.UNKNOWN||0)+'호'+(p.forecast?'<br>미래 영역은 공식 목표와 일정에 따른 전망':'')+progressNote+'<br>입주는 시작일 확인 사업의 물량 · 실제 입주 가구 수 아님</span>';
      const rect=wrap.getBoundingClientRect();tip.style.left=Math.max(wrap.parentElement.scrollLeft+8,Math.min(wrap.parentElement.scrollLeft+wrap.parentElement.clientWidth-290,e.clientX-rect.left+18))+'px';tip.style.top='78px';const line=svg.querySelector('.d907-hover-line');line.setAttribute('x1',local.x);line.setAttribute('x2',local.x);line.setAttribute('visibility','visible');
    });
    document.addEventListener('pointerout',e=>{if(!e.target.hasAttribute?.('data-d907-hover'))return;const wrap=e.target.closest('.d907-chart-wrap');wrap?.querySelector('.d907-chart-tooltip')?.setAttribute('hidden','');wrap?.querySelector('.d907-hover-line')?.setAttribute('visibility','hidden');});
  }
  return {render,start,totals,comparisonStatus,delaySummary};
})();
