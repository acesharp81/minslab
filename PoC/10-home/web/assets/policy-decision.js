'use strict';
/* Decision tools consume the same scoped, de-duplicated cohorts as the map. */
const PolicyDecision=(()=>{
 const flow=typeof PolicyStageFlow!=='undefined'?PolicyStageFlow:require('./policy-stage-flow.js'),assessGap=flow.assessGap;
 function checks(metrics,day){const comparisons=Object.fromEntries(Object.entries(metrics||{}).map(([k,c])=>[k,c.tracking?{...c,...c.tracking,management_points:[]}:c]));return Object.keys(stages).map(stage=>flow.comparisonStatus({comparisons,asOf:day},stage));}
 function delayAt(metrics,day){const list=checks(metrics,day),known=list.some(c=>c.assessment.status!=='UNKNOWN');return {DELAYED:known?Math.max(0,...list.filter(c=>c.status==='DELAYED').map(c=>c.gap)):null,WARNING:known?Math.max(0,...list.filter(c=>c.status==='WARNING').map(c=>c.gap)):null,checks:list};}
 function mapDelay(metrics,day){const delayed=checks(metrics,day).filter(c=>c.status==='DELAYED');return {delayed:delayed.length>0,delayNote:delayed.map(c=>(stages[c.stage]||c.label)+' '+c.gap.toLocaleString('ko-KR')+'호 부족 ('+flow.formatGapRate(c.rate)+')').join(' · ')};}
 const stages={BUSINESS:'사업화',APPROVAL:'인허가',CONSTRUCTION:'건설',SUPPLY:'공급',COMPLETION:'준공',MOVE_IN:'입주 시작'};
 function events(c,s,day){return (c.events||[]).filter(e=>e.stage===s&&e.status!=='DELAYED'&&e.origin!=='PLANNED'&&e.event_date<=day);}
 function supply(c,day){const es=events(c,'SUPPLY',day);return es.length?Math.min(c.units,Math.max(...es.map(e=>e.units??c.units))):null;}
 function due(c,s){return (c.schedules||[]).filter(e=>e.stage===s&&e.due_date).sort((a,b)=>b.due_date.localeCompare(a.due_date))[0]||null;}
 function analyze(cohorts,asOf,year){
  const day=Math.min(year,Number(asOf.slice(0,4)))===Number(asOf.slice(0,4))?asOf:year+'-12-31';
  const projects=cohorts.map(c=>{const units=supply(c,day),move=events(c,'MOVE_IN',day).length>0,d=due(c,'MOVE_IN');return {...c,supplied:units,moveStarted:move,moveDue:d?.due_date||null,followup:units==null?'NO_SUPPLY':move?'STARTED':d?.due_date<day?'VERIFY_DUE':d?'UPCOMING':'NO_DATE'};});
  const supplied=projects.filter(c=>c.supplied!=null),pending=supplied.filter(c=>!c.moveStarted),pastDue=pending.filter(c=>c.followup==='VERIFY_DUE');
  const annual=Array.from({length:11},(_,i)=>Number(asOf.slice(0,4))-5+i).map(y=>{if(y>Number(asOf.slice(0,4)))return {year:y,pending:null,started:null};const d=y===Number(asOf.slice(0,4))?asOf:y+'-12-31';let unknown=0,started=0,known=false;for(const c of cohorts){const u=supply(c,d);if(u==null)continue;known=true;if(events(c,'MOVE_IN',d).length)started+=u;else unknown+=u;}return {year:y,pending:known?unknown:null,started:known?started:null};});
  return {day,projects,supplied,pending,pastDue,annual,suppliedUnits:supplied.length?supplied.reduce((a,c)=>a+c.supplied,0):null,pendingUnits:supplied.length?pending.reduce((a,c)=>a+c.supplied,0):null};
 }
 function forecast(cohorts,asOf,shift){
  const now=Number(asOf.slice(0,4));const years=Array.from({length:6},(_,i)=>({year:now+i,baseline:0,scenario:0,count:0}));let total=0,outside=0;
  for(const c of cohorts){const s=due(c,'SUPPLY');if(!s||s.due_date<=asOf||s.units==null)continue;const u=Math.max(0,Math.min(c.units,s.units)-(supply(c,asOf)||0));if(!u)continue;const y=Number(s.due_date.slice(0,4));const row=years.find(r=>r.year===y);if(!row)continue;row.baseline+=u;row.count++;total+=u;const [yy,mm]=s.due_date.split('-').map(Number);const moved=new Date(Date.UTC(yy,mm-1+shift,1)).getUTCFullYear(),target=years.find(r=>r.year===moved);if(target)target.scenario+=u;else outside+=u;}
  return {years,total,outside};
 }
 const e=v=>esc(String(v??'')),u=v=>v==null?'미확보':num(v)+'호';
 const metrics={APPROVAL:['인허가','#179f99'],CONSTRUCTION:['착공','#e67b21'],SUPPLY:['분양·모집','#758ab0'],COMPLETION:['준공','#5b9d36']};
 const monthKey=(day,shift=0)=>{const [y,m]=day.split('-').map(Number);return new Date(Date.UTC(y,m-1+shift,1)).toISOString().slice(0,7);};
 const monthEnd=month=>{const [y,m]=month.split('-').map(Number);return new Date(Date.UTC(y,m,0)).toISOString().slice(0,10);};
 const capacity=c=>Math.max(0,Number(c.units)||0);
 function measured(c,stage,day){const list=events(c,stage,day);return list.length?Math.min(capacity(c),Math.max(0,...list.map(v=>v.units??capacity(c)))):null;}
 function statusAt(c,day){
  let result={status:'UNKNOWN',units:0};
  for(const stage of Object.keys(stages)){
   const goals=(c.schedules||[]).filter(s=>s.stage===stage&&s.due_date<=day&&s.units!=null);
   if(!goals.length)continue;
   const target=Math.min(capacity(c),Math.max(...goals.map(s=>s.units))),actual=measured(c,stage,day),check=assessGap(target,actual),rank={UNKNOWN:0,NORMAL:1,WARNING:2,DELAYED:3};
   if(rank[check.status]>rank[result.status]||check.status===result.status&&(check.gap||0)>result.units)result={status:check.status,units:check.gap||0};
  }
  return result;
 }
 function agencyName(value){const v=String(value||'').trim();if(!v||/미확|확인 필요/.test(v))return '기관 미상';if(/한국토지주택공사|^LH$/i.test(v))return 'LH';if(/경기주택도시공사|^GH$/i.test(v))return 'GH';if(/서울주택도시|서울주택도시개발|^SH$/i.test(v))return 'SH';return v;}
 function statistics(cohorts,asOf,year,comparisons){
  const day=year&&year<Number(asOf.slice(0,4))?year+'-12-31':asOf;
  const months=Array.from({length:24},(_,i)=>monthKey(day,i-23));
  const monthly=months.map(month=>{const end=month===day.slice(0,7)?day:monthEnd(month),before=monthEnd(monthKey(month,-1)),values={};for(const stage of Object.keys(metrics)){const known=cohorts.some(c=>measured(c,stage,day)!=null);values[stage]=known?cohorts.reduce((sum,c)=>sum+Math.max(0,(measured(c,stage,end)||0)-(measured(c,stage,before)||0)),0):null;}return {month,...values};});
  const delays=months.map(month=>{const end=month===day.slice(0,7)?day:monthEnd(month);if(comparisons)return {month,...delayAt(comparisons,end)};return cohorts.reduce((r,c)=>{const s=statusAt(c,end);if(s.status==='DELAYED')r.DELAYED+=s.units;if(s.status==='WARNING')r.WARNING+=s.units;return r;},{month,DELAYED:0,WARNING:0});});
  const upcoming=Array.from({length:12},(_,i)=>({month:monthKey(day,i),units:0})),projectIds=new Set();let scheduled=0;
  for(const c of cohorts){let allocated=measured(c,'SUPPLY',day)||0;for(const s of [...(c.schedules||[])].filter(s=>s.stage==='SUPPLY'&&s.units!=null&&s.due_date).sort((a,b)=>a.due_date.localeCompare(b.due_date))){const target=Math.min(capacity(c),s.units),increment=Math.max(0,target-allocated);allocated=Math.max(allocated,target);if(s.due_date<=day)continue;const row=upcoming.find(r=>r.month===s.due_date.slice(0,7));if(!row)continue;scheduled++;row.units+=increment;if(increment)projectIds.add(c.id);}}
  const agencies=new Map();for(const c of cohorts){const name=agencyName(c.developer),r=agencies.get(name)||{name,total:0,count:0,NORMAL:0,WARNING:0,DELAYED:0,UNKNOWN:0},status=statusAt(c,day);r.total+=capacity(c);r.count++;r[status.status]+=capacity(c);agencies.set(name,r);}
  return {day,monthly,delays,upcoming,scheduled,projects:projectIds.size,total:upcoming.reduce((s,r)=>s+r.units,0),agencies:[...agencies.values()].sort((a,b)=>b.total-a.total)};
 }
 function chart(rows,series,bars=false){
  const max=Math.max(1,...rows.flatMap(r=>series.map(([k])=>r[k]||0))),x=i=>44+i*380/Math.max(1,rows.length-1),y=v=>174-v/max*137;
  const ticks=[0,.5,1].map(t=>'<line x1="42" x2="438" y1="'+y(t*max)+'" y2="'+y(t*max)+'" stroke="#dce6ef"/><text x="36" y="'+(y(t*max)+4)+'" text-anchor="end">'+(max*t>=10000?(max*t/10000).toFixed(1)+'만':num(Math.round(max*t)))+'</text>').join('');
  const lines=series.map(([key,label,color])=>bars?rows.map((r,i)=>'<rect x="'+(44+i*392/rows.length)+'" y="'+y(r[key]||0)+'" width="'+(392/rows.length-4)+'" height="'+(174-y(r[key]||0))+'" fill="'+color+'"><title>'+e(r.month+' '+label+' '+u(r[key]))+'</title></rect>').join(''):'<path d="'+rows.map((r,i)=>r[key]==null?'':(i&&rows[i-1][key]!=null?'L':'M')+x(i).toFixed(1)+' '+y(r[key]).toFixed(1)).join(' ')+'" fill="none" stroke="'+color+'" stroke-width="2.5"/>'+rows.filter((r,i)=>r[key]!=null).map(r=>{const i=rows.indexOf(r);return '<circle cx="'+x(i)+'" cy="'+y(r[key])+'" r="3" fill="'+color+'"><title>'+e(r.month+' '+label+' '+u(r[key]))+'</title></circle>';}).join('')).join('');
  return '<svg class="pd-stat-chart" viewBox="0 0 460 210" role="img" aria-label="'+e(series.map(s=>s[1]).join(' · ')+' 월별 호수')+'">'+ticks+lines+rows.map((r,i)=>i%Math.ceil(rows.length/4)===0||i===rows.length-1?'<text x="'+(bars?55+i*392/rows.length:x(i))+'" y="199" text-anchor="middle">'+r.month.replace('-','.')+'</text>':'').join('')+'</svg>';
 }
 const key=series=>'<div class="pd-stat-key">'+series.map(([k,name,color])=>'<span><svg width="10" height="10" aria-hidden="true"><rect width="10" height="10" fill="'+color+'"/></svg>'+e(name)+'</span>').join('')+'</div>';
 function render(host,context){
  if(!host)return;const {data,cohorts,scope,year,comparisons}=context,m=statistics(cohorts,data.as_of_date,year,comparisons),series=Object.entries(metrics).map(([k,[n,c]])=>[k,n,c]),statuses=[['NORMAL','목표 도달','#218267'],['WARNING','주의 · 2% 미만','#e8ad25'],['DELAYED','지연 · 2% 이상','#b51f38'],['UNKNOWN','판정 미확보','#cbd5e1']],latest=m.delays.at(-1);
  const card=(title,body,note)=>'<article class="pr-card pd-stat-card"><div class="pr-card-head"><h3>'+title+'</h3></div>'+body+'<p class="pr-note">'+note+'</p></article>';
  host.innerHTML='<div class="pd-heading"><div><h2>추진현황 통계</h2><small>선택 범위 연결 사업 '+cohorts.length+'개 · 단계별 물량은 합산하지 않습니다</small></div><strong>'+e(scope)+' · '+m.day+' 기준</strong></div><div class="pd-stat-grid">'+
   card('월별 실적 흐름',key(series.map(([k,n,c])=>[k,n+(m.monthly.every(r=>r[k]==null)?' · 미확보':''),c]))+chart(m.monthly,series),'최근 24개월 단계별 누적 측정값의 월 증가분 · 입력·추정 포함. 0은 등록된 증가분 없음, 미확보는 해당 단계 측정 자료 없음입니다.')+
   card('지연·주의 추이',key(statuses.slice(1,3))+chart(m.delays,statuses.slice(1,3))+'<div class="pd-stat-totals"><span class="pd-delay-total">지연 최대 <b>'+u(latest.DELAYED)+'</b></span><span class="pd-warning-total">주의 최대 <b>'+u(latest.WARNING)+'</b></span></div>'+ (latest.checks?'<div class="pd-stage-gaps">'+latest.checks.filter(c=>c.gap>0).map(c=>'<span class="'+(c.status==='DELAYED'?'pd-delay-total':'pd-warning-total')+'">'+e(stages[c.stage])+' '+e(c.assessment.label)+' '+u(c.gap)+' · '+flow.formatGapRate(c.rate)+'</span>').join('')+'</div>':''),'상단 누적 그래프와 같은 범위의 목표·측정값으로 월말을 재구성합니다. 부족률 2% 이상은 지연, 0% 초과~2% 미만은 주의입니다. 선과 합계는 상태별 단계 최대 부족량이며 단계 간 물량을 합산하지 않습니다. 비교 자료가 없으면 미확보로 표시합니다.')+
   card('향후 12개월 공급 예정','<div class="pd-stat-number">'+(m.scheduled?u(m.total):'예정 자료 미확보')+' <small>'+m.projects+'개 사업</small></div>'+chart(m.upcoming,[['units','공급 예정','#5d9c39']],true),'기준일 이후부터 '+m.upcoming.at(-1).month+' 말까지 · 누적 공급 목표 증가분에서 이미 측정된 물량 제외. 지난 기한의 미달량은 미래 예정에 재배분하지 않습니다.')+
   card('기관별 진행현황',key(statuses)+'<div class="pd-agencies">'+(m.agencies.map(r=>'<div class="pd-agency-row"><div><b>'+e(r.name)+'</b><small>'+u(r.total)+' · '+r.count+'개 사업</small></div><svg viewBox="0 0 200 16" role="img" aria-label="'+e(r.name+' '+statuses.map(([k,n])=>n+' '+u(r[k])).join(', '))+'">'+statuses.map(([k,n,color],i)=>'<rect x="'+(200*statuses.slice(0,i).reduce((s,[k])=>s+r[k],0)/Math.max(1,r.total))+'" y="0" width="'+(200*r[k]/Math.max(1,r.total))+'" height="16" fill="'+color+'"><title>'+n+' '+u(r[k])+'</title></rect>').join('')+'</svg><strong>'+ (r.total?(100*r.DELAYED/r.total).toFixed(1):'0.0')+'%<small>지연 사업 물량 비중</small></strong></div>').join('')||'<p class="pd-empty">연결 사업이 없습니다.</p>')+'</div>','시행기관별 사업 계획량을 분류합니다. 지연(2% 이상) → 주의(2% 미만) → 도래 목표 도달 순으로 사업당 한 번 집계합니다. 목표·일정 미확보 사업은 회색입니다.')+
   '<div data-pr-demography class="pd-stat-demography"><article class="pr-card"><h3>1·2·3·4인 이상 가구 변화</h3><p>지역 통계 확인 중…</p></article><article class="pr-card"><h3>인구·가구 변화와 주택 재고</h3><p>지역 통계 확인 중…</p></article></div></div>';
 }
 return {render,analyze,forecast,statistics,statusAt,checks,delayAt,mapDelay};
})();
if(typeof module!=='undefined')module.exports=PolicyDecision;
