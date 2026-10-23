 'use strict';
const ProgressReport=(()=>{
 const stages={BUSINESS:'사업화',APPROVAL:'인허가',CONSTRUCTION:'착공',COMPLETION:'준공',SUPPLY:'공급',MOVE_IN:'입주'};
 const supported=new Set(['policy-progress','program-progress','projects']);
 const text=v=>String(v??'미확보').replace(/https?:\/\/[^\s<>"\])]+/gi,'').trim();
 const e=v=>text(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const amount=v=>v==null?'미확보':Number(v).toLocaleString('ko-KR')+'호';
 const md=v=>text(v).replace(/[\r\n]+/g,' ').replace(/\|/g,'\\|').replace(/</g,'&lt;');
 const later={BUSINESS:['BUSINESS','APPROVAL','CONSTRUCTION','COMPLETION','SUPPLY','MOVE_IN'],APPROVAL:['APPROVAL','CONSTRUCTION','COMPLETION','SUPPLY','MOVE_IN'],CONSTRUCTION:['CONSTRUCTION','COMPLETION','MOVE_IN'],COMPLETION:['COMPLETION','MOVE_IN'],SUPPLY:['SUPPLY','MOVE_IN'],MOVE_IN:['MOVE_IN']};
 const maxKnown=values=>{const vs=values.filter(Number.isFinite);return vs.length?Math.max(...vs):null;};
 const sumKnown=values=>{const vs=values.filter(Number.isFinite);return vs.length?vs.reduce((a,b)=>a+b,0):null;};
 const cap=p=>p.units??p.planned_units??Infinity;
 function reached(p,stage,date){
  const values=(p.events||[]).filter(r=>(later[stage]||[stage]).includes(r.stage)&&(r.status||'ACTUAL')==='ACTUAL'&&r.origin!=='PLANNED'&&r.event_date&&r.event_date<=date).map(r=>r.units);
  const v=maxKnown(values);return v==null?null:Math.min(cap(p),v);
 }
 const isActual=r=>(r.status||'ACTUAL')==='ACTUAL'&&r.origin!=='PLANNED';
 function measured(p,stage,date){const v=maxKnown((p.events||[]).filter(r=>r.stage===stage&&isActual(r)&&r.event_date&&r.event_date<=date).map(r=>r.units));return v==null?null:Math.min(cap(p),v);}
 function goalAt(p,stage,date){return (p.schedules||[]).filter(r=>r.stage===stage&&r.status!=='RELEASED'&&r.due_date&&r.due_date<=date&&Number.isFinite(r.units)).slice().sort((a,b)=>a.due_date.localeCompare(b.due_date)).at(-1);}
 function progressAt(projects,stage,date){
  const due=projects.map(p=>({p,goal:goalAt(p,stage,date)})).filter(r=>r.goal),known=due.filter(r=>measured(r.p,stage,date)!=null);
  const target=sumKnown(due.map(r=>Math.min(cap(r.p),r.goal.units))),actual=due.length&&known.length===due.length?sumKnown(known.map(r=>measured(r.p,stage,date))):null;
  return {target,actual,rate:target>0&&actual!=null?100*actual/target:null,gap:target!=null&&actual!=null?target-actual:null,known:known.length,due:due.length};
 }
 function progressModel(projects,cutoff){
  const rows=Object.entries(stages).map(([stage,label])=>({stage,label,...progressAt(projects,stage,cutoff)}));
  const charts=rows.map(r=>{
   const dates=[...new Set([cutoff,...projects.flatMap(p=>[...(p.events||[]).filter(e=>e.stage===r.stage&&isActual(e)&&e.event_date<=cutoff).map(e=>e.event_date),...(p.schedules||[]).filter(s=>s.stage===r.stage&&s.status!=='RELEASED').map(s=>s.due_date)])].filter(Boolean))].sort();
   return {type:'trend',step:true,title:r.label+' · 누적 목표 대비 이행 추이',unit:'호',series:[{key:'actual',label:'도래 목표 대상 실적',color:'#176d86'},{key:'target',label:'누적 목표',color:'#cb641d'}],rows:dates.map(date=>{const v=progressAt(projects,r.stage,date);return {label:date,target:v.target,actual:date<=cutoff?v.actual:null};}),note:'등록 목표일·실적일 기준 계단형 시계열. 미래 실적은 표시하지 않습니다. 실적은 해당 시점의 도래 목표 대상 사업과 동일 범위이며, 일부 사업의 실적이 미확보이면 합계·달성률을 보류합니다.'};
  });
  return {rows,charts};
 }
 const sourceRules=new Set(['SOURCE_ACCEPTED','BEST_SOURCE_SELECTED','MEASUREMENT_TO_TARGET']);
 function estimatedField(r,field){
  const proof=r.field_provenance||{},own=proof[field]||(field==='date'?proof.event_date:null);
  if(own?.rule)return !sourceRules.has(own.rule);
  const tag=r.field_tags?.[field]?.code;if(tag)return tag==='ESTIMATED';
  if(field==='date'&&r.input_rule==='SOURCE_ACCEPTED')return false;
  return Boolean(r.inferred||String(r.input_status||'').startsWith('ESTIMATED'));
 }
 const scheduleStages=['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'];
 const validDay=d=>typeof d==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(d)&&Number.isFinite(Date.parse(d));
 function stageSchedule(projects,cutoff){
  const rows=projects.map(p=>({name:p.name||'선택 사업',points:scheduleStages.map((stage,level)=>{
   const goals=(p.schedules||[]).filter(r=>r.stage===stage&&r.status!=='RELEASED'&&validDay(r.due_date)).slice().sort((a,b)=>a.due_date.localeCompare(b.due_date));
   const goal=goals.filter(r=>r.due_date<=cutoff).at(-1)||goals[0];
   const actual=(p.events||[]).filter(r=>r.stage===stage&&isActual(r)&&validDay(r.event_date)&&r.event_date<=cutoff&&(r.units==null||r.units>0)).slice().sort((a,b)=>a.event_date.localeCompare(b.event_date)).at(-1);
   return {stage,label:stages[stage],level,target:goal?.due_date||null,actual:actual?.event_date||null,actualEstimated:actual?estimatedField(actual,'date'):false};
  })}));
  const dates=projects.flatMap(p=>[...(p.schedules||[]).filter(r=>scheduleStages.includes(r.stage)&&r.status!=='RELEASED').map(r=>r.due_date),...(p.events||[]).filter(r=>scheduleStages.includes(r.stage)&&isActual(r)&&r.event_date<=cutoff&&(r.units==null||r.units>0)).map(r=>r.event_date)]).filter(validDay).sort();
  const start=dates[0]?.slice(0,7)||null,months=start?Array.from({length:120},(_,i)=>{const [y,m]=start.split('-').map(Number);return new Date(Date.UTC(y,m-1+i,1)).toISOString().slice(0,7);}):[];
  const end=months.at(-1)||null;
  return {type:'stage-schedule',title:'사업 단계별 목표·실적 일정 · 10년',rows,months,start,end,note:start?start.replace('-','.')+'~'+end.replace('-','.')+' · 월 단위. 목표는 옅은 파랑, 분홍은 측정·추정값입니다. 분홍 ●는 수집 측정일, ○는 사건 선후관계를 검증해 해당 단계 목표값을 적용한 추정일입니다.':'일정 데이터 미확보'};
 }
 function stageScheduleSvg(c){
  if(!c.start)return '<p class="report-note">일정 데이터 미확보</p>';
  const left=106,right=860,top=35,bottom=355,lo=Date.parse(c.start+'-01'),last=new Date(c.end+'-01T00:00:00Z');last.setUTCMonth(last.getUTCMonth()+1);
  const hi=last.getTime()-86400000,x=d=>left+(Date.parse(d)-lo)/(hi-lo)*(right-left),y=level=>bottom-level*(bottom-top)/4;
  let svg=svgStart(c.title,450);
  scheduleStages.forEach((stage,i)=>{svg+='<line x1="'+left+'" x2="'+right+'" y1="'+y(i)+'" y2="'+y(i)+'" stroke="#dfe8ef"/>'+label(left-16,y(i)+5,stages[stage],'text-anchor="end"');});
  c.months.forEach((month,i)=>{const xx=x(month+'-01');svg+='<line data-schedule-month="'+month+'" x1="'+xx+'" x2="'+xx+'" y1="'+top+'" y2="'+(bottom+7)+'" stroke="'+(i%12===0?'#d5e1e9':'#f0f4f7')+'"><title>'+month.replace('-','.')+'</title></line>';if(i%6===0||i===119)svg+=label(xx,bottom+24,month.replace('-','.'),'text-anchor="end" transform="rotate(-45 '+xx+' '+(bottom+24)+')" font-size="11"');});
  svg+='<line x1="'+left+'" x2="'+right+'" y1="'+bottom+'" y2="'+bottom+'" stroke="#91a8b8"/>';
  for(const [key,color,dash] of [['target','#a5cdee','7 4'],['actual','#e681a8','']])for(const project of c.rows){
   let active=false;const path=project.points.map(p=>{const d=p[key];if(!d||Date.parse(d)<lo||Date.parse(d)>hi){active=false;return '';}const part=(active?'L':'M')+x(d)+' '+y(p.level);active=true;return part;}).join(' ');
   svg+='<path data-schedule-series="'+key+'" d="'+path+'" stroke="'+color+'" stroke-width="'+(key==='target'?6:3.5)+'" fill="none"'+(dash?' stroke-dasharray="'+dash+'"':'')+'/>';
   for(const p of project.points){const d=p[key];if(!d||Date.parse(d)<lo||Date.parse(d)>hi)continue;svg+='<circle data-schedule-estimated="'+(key==='actual'&&p.actualEstimated)+'" cx="'+x(d)+'" cy="'+y(p.level)+'" r="'+(key==='target'?7:5)+'" fill="'+(key==='target'||p.actualEstimated?'white':color)+'" stroke="'+color+'" stroke-width="2"><title>'+e(project.name+' · '+p.label+' · '+(key==='target'?'목표 ':p.actualEstimated?'목표대체 추정 ':'수집 측정 ')+d)+'</title></circle>';}
  }
  svg+=label((left+right)/2,441,'연도.월 · 120개월','text-anchor="middle" font-size="12"');return svg+'</svg>';
 }
 function scheduleHtml(c){return '<figure class="report-figure report-schedule"><figcaption>'+e(c.title)+'</figcaption><div class="report-legend"><span>'+legendSymbol('#a5cdee',true,'7 4',true)+'목표</span><span>'+legendSymbol('#e681a8',true)+'수집 측정</span><span>'+legendSymbol('#e681a8',true,'',true)+'추정(선후관계 검증)</span></div>'+stageScheduleSvg(c)+'<p class="report-note">'+e(c.note)+'</p></figure>';}
 const numeric=(v,unit='')=>Number.isFinite(v)?v.toLocaleString('ko-KR')+unit:'미확보';
 function locationModel(c){
  const a=c.data.area||{},infra=c.data.infrastructure,place=c.data.area_place||a,scope=[place.region||c.scope.region,place.municipality].filter(Boolean).join(' ')||'지역 미선택';
  const notes=[scope+' 기준 지역 통계입니다. 지역 가구 수는 해당 사업의 입주 실적이나 확정 수요가 아닙니다.'],charts=[],sections=[];
  if(c.data.area_status==='QUERY_FAILED')notes.push('지역 통계 조회 실패 · 자료가 없는 것으로 판단하지 않습니다.');
  if(c.data.area_place?.note)notes.push(c.data.area_place.note);
  const years=(a.household_size||[]).filter(r=>Number(r.year)<=Number(c.scope.as_of_date.slice(0,4))).slice().sort((x,y)=>x.year-y.year),keys=['1','2','3','4'],colors=['#176d86','#cb641d','#6e55a3','#35845a'];
  const first=years[0],last=years.at(-1);
  if(years.length>1){const changes=keys.filter(k=>Number.isFinite(first.sizes?.[k])&&Number.isFinite(last.sizes?.[k])).map(k=>{const delta=last.sizes[k]-first.sizes[k];return k+'인 '+(delta>0?'+':'')+numeric(delta,'가구');});if(changes.length)notes.push(first.year+'~'+last.year+'년 가구 변화: '+changes.join(', ')+'.');}
  charts.push({type:'trend',title:'1~4인 가구의 연도별 변화',unit:'가구',rows:years.map(r=>({label:String(r.year),...Object.fromEntries(keys.map(k=>[k,r.sizes?.[k]??null]))})),series:keys.map((k,i)=>({key:k,label:k+'인 가구',color:colors[i]})),note:scope+' · '+(first?first.year+'~'+last.year+'년':'시계열 미확보')+' · 일반가구 기준. 5인 이상은 전체 가구에 포함되며 아래 비중의 분모는 전체 일반가구입니다.'});
  sections.push({title:'가구 규모별 증감과 구성비',headers:['가구 규모',first?first.year+'년':'시작연도',last?last.year+'년':'최근연도','증감 / 증감률','최근 구성비'],rows:keys.map(k=>{const before=first?.sizes?.[k],after=last?.sizes?.[k],comparable=years.length>1&&Number.isFinite(before)&&Number.isFinite(after),delta=comparable?after-before:null;return [k+'인',numeric(before,'가구'),numeric(after,'가구'),delta==null?'비교 미확보':numeric(delta,'가구')+' / '+(before>0?(100*delta/before).toFixed(1)+'%':'산출 불가'),Number.isFinite(after)&&last.total>0?(100*after/last.total).toFixed(1)+'%':'미확보'];}),note:'단일 연도만 있으면 증감을 계산하지 않습니다. 가구 구성 변화와 사업의 주택 규모·공급 유형을 함께 검토합니다.'});
  const types={subway:'지하철·GTX',bus:'버스 정류장',school:'학교',childcare:'어린이집',hospital:'병원',mart:'대형마트'},items=(infra?.items||[]).map(r=>({...r,kind:r.kind==='gtx'?'subway':r.kind})).filter(r=>r.service_status!=='PLANNED'&&Number.isFinite(r.distance_m)&&r.distance_m>=0);
  sections.push({title:'주변 시설과 접근성',headers:['시설','최근접 시설명','직선거리','1km 내 확인 시설'],rows:Object.entries(types).map(([kind,label])=>{const list=items.filter(r=>r.kind===kind).sort((x,y)=>x.distance_m-y.distance_m),near=list[0];return [label,near?near.name+(near.line?' · '+near.line:''):'조회 범위 내 미확인',near?numeric(Math.round(near.distance_m),'m'):'미확보',list.length?list.filter(r=>r.distance_m<=1000).length+'개':'미확인'];}),note:(c.data.infrastructure_status==='QUERY_FAILED'?'시설 조회 실패. ':!infra?'사업별 시설 자료 미확보. ':'조회 '+text(infra.collected_at)+' · ')+(infra?.origin?.approximate?'대표점 기준 참고 거리. ':'사업 위치 기준 직선거리. ')+'도보·통근시간이 아니며 시설 목록은 전수조사가 아닙니다. 지하철은 조회된 역 중 최근접 역입니다.'});
  const planned=[...(infra?.planned_facilities||[]),...(infra?.planned_gtx||[])];
  if(planned.length)sections.push({title:'계획 시설과 입주 일정 점검',headers:['예정 시설','종류 / 노선','개교·개통 예정','직선거리'],rows:planned.map(r=>[r.name,types[r.kind]||r.line||r.kind,r.opening_date||'일정 미확보',numeric(r.distance_m,'m')]),note:'계획 시설은 운영 시설에서 제외합니다. 입주 예정일 이전 개교·개통 여부는 별도 확인이 필요합니다.'});
  const balance=(a.housing_balance||[]).filter(r=>Number(r.year)<=Number(c.scope.as_of_date.slice(0,4))).slice().sort((x,y)=>x.year-y.year);
  if(balance.length)sections.push({title:'지역 인구·가구와 주택 재고',headers:['연도','인구','일반가구','주택 재고','주택보급률'],rows:balance.map(r=>[r.year,numeric(r.population,'명'),numeric(r.households,'가구'),numeric(r.housing_units,'호'),numeric(r.official_ratio??r.stock_to_household_pct,'%')]),note:scope+' · 공식 비율이 없으면 동일 행의 주택/가구 비율을 참고로 표시합니다. 재고와 가구 수의 단순 차이를 실제 가용 주택이나 수요 부족량으로 해석하지 않습니다.'});
  return {notes,charts,sections};
 }
 const assess=(target,actual)=>PolicyStageFlow.assessGap(target,actual);
 function risks(projects,date,issues=[]){
  const list=[];
  for(const p of projects){
   const found=[];
   for(const [stage,label] of Object.entries(stages)){
    const goals=(p.schedules||[]).filter(r=>r.stage===stage&&r.due_date&&r.due_date<=date&&Number.isFinite(r.units));
    if(!goals.length)continue;
    const goal=goals.slice().sort((a,b)=>b.due_date.localeCompare(a.due_date))[0],target=Math.min(cap(p),goal.units),actual=measured(p,stage,date),a=assess(target,actual);
    if(['DELAYED','WARNING'].includes(a.status)||a.status==='UNKNOWN'&&target>0)found.push({stage,label,date:goal.due_date,target,actual,gap:a.gap,status:a.status,reason:a.status==='UNKNOWN'?'목표 기한 경과 · 측정값 미확보':'도래 목표 대비 '+amount(a.gap)+' 부족',action:a.status==='UNKNOWN'?'단계 실적 등록 여부 확인':'미달 물량의 이행 일정 점검'});
   }
   for(const r of issues.filter(r=>r.project_id===p.id&&r.status==='DELAYED'&&r.due_date<=date)){
    const prior=found.find(v=>v.stage===r.stage);if(prior){prior.status='DELAYED';prior.reason+=' · 지연 등록';}else found.push({stage:r.stage,label:stages[r.stage]||r.stage,date:r.due_date,target:null,actual:measured(p,r.stage,date),gap:r.units??null,status:'DELAYED',reason:'등록된 지연 사항',action:'등록 조치와 회복 일정 확인'});
   }
   for(const r of (p.events||[]).filter(r=>r.status==='DELAYED'&&r.event_date&&r.event_date<=date))if(!found.some(v=>v.stage===r.stage&&v.status==='DELAYED'))found.push({stage:r.stage,label:stages[r.stage]||r.stage,date:r.event_date,target:null,actual:measured(p,r.stage,date),gap:null,status:'DELAYED',reason:'등록된 지연 사항',action:'등록 조치와 회복 일정 확인'});
   for(const r of found)list.push({...r,id:p.id,name:p.name,program:p.program||'미분류',region:[p.region,p.municipality].filter(Boolean).join(' ')});
  }
  return list.sort((a,b)=>({DELAYED:0,WARNING:1,UNKNOWN:2}[a.status]-{DELAYED:0,WARNING:1,UNKNOWN:2}[b.status])||(b.gap||0)-(a.gap||0)||a.name.localeCompare(b.name));
 }
 function projectStages(m,date,end){return Object.entries(stages).map(([stage,label])=>{
  const cell=m.cells?.[stage==='COMPLETION'?'CONSTRUCTION':stage]||{},filter=r=>stage==='COMPLETION'?r.milestone==='COMPLETION':stage==='CONSTRUCTION'?r.milestone!=='COMPLETION':true;
  const actual=(cell.management?.measurement||[]).filter(filter).filter(r=>r.date&&r.date<=date&&isActual(r)).sort((a,b)=>a.date.localeCompare(b.date)),plans=(cell.management?.target||[]).filter(filter);
  const latest=actual.at(-1),due=plans.filter(r=>r.date&&r.date<=date).sort((a,b)=>a.date.localeCompare(b.date)).at(-1),next=plans.filter(r=>r.date&&r.date>date).sort((a,b)=>a.date.localeCompare(b.date))[0];
  const target=due||next||plans[0],current=latest?.units??null,yearPlan=maxKnown(plans.filter(r=>r.date&&r.date<=end).map(r=>r.units)),expected=maxKnown([current,yearPlan]);
  const check=due?assess(due.units,current):null;
  return {stage,label,current,date:latest?.date||null,expected,target:target?.units??null,planDate:target?.date||null,plans,measurements:actual,estimated:latest?estimatedField(latest,'date')||estimatedField(latest,'units'):false,status:check?.status||(current>0?'MEASURED':next?'UPCOMING':'UNKNOWN')};
 });}
 const bar=(title,rows,series,note='',unit='호')=>({type:'bars',title,rows,series,note,unit});
 const currentSeries=[{key:'current',label:'현재 누적',color:'#176d86'},{key:'expected',label:'연말 누적 예상',color:'#b6cbd9',outline:true}];
 function model(input){
  if(input.kind!=='project')return PortfolioProgressReport.model(input);
  const c=JSON.parse(JSON.stringify(input)),d=c.data,s=c.scope,end=String(s.year)+'-12-31',cutoff=[s.as_of_date,end,s.data_as_of_date||s.as_of_date].sort()[0],sections=[],charts=[],comparisonDate=s.comparison_date||end,comparisonLabel=s.comparison_date?s.comparison_date+(s.comparison_date<=(s.data_as_of_date||s.as_of_date)?' 누적 측정':' 누적 예상'):s.year+'년 말',comparisonSeries=currentSeries.map(v=>v.key==='expected'?{...v,label:s.comparison_date?comparisonLabel:'연말 누적 예상'}:v);
  const add=(title,headers,rows,note='')=>sections.push({title,headers,rows,note});
  let projects=d.cohorts||[],stageRows=[],groups=[],riskRows=[],summary=[],meta=[];
  if(c.kind==='project'){
   const m=d.project,p=m.project;stageRows=projectStages(m,cutoff,end);
   projects=[{...p,events:stageRows.flatMap(r=>r.measurements.map(v=>({...v,stage:r.stage,event_date:v.date}))),schedules:stageRows.flatMap(r=>r.plans.map(v=>({...v,stage:r.stage,due_date:v.date,units:v.units})))}];
   riskRows=risks(projects,cutoff);
   charts.push({type:'steps',title:'사업화부터 입주까지 단계별 진행',rows:stageRows,note:'각 단계의 측정량과 예정일을 함께 표시합니다. 공급은 준공 전·후에 병행할 수 있습니다.'});
   charts.push(bar('단계별 실적과 목표 물량',stageRows,[{key:'current',label:'현재 측정량',color:'#176d86'},{key:'target',label:'단계 목표',color:'#b6cbd9',outline:true}],'측정량은 건설 공정률이 아닙니다. 목표를 확보하지 못한 단계는 달성률을 계산하지 않습니다.'));
   charts.push({type:'timeline',title:'단계별 실적일과 목표 일정',rows:stageRows,note:'● 측정일 · ◇ 목표·예정일. 시간축의 간격은 실제 날짜 간격입니다.'});
   meta=[['프로그램',m.parent?.name||p.program],['지역',[p.region,p.municipality].filter(Boolean).join(' ')],['시행자',p.developer],['공급 유형',p.supply_type_assessment?.label||p.supply_type],['공급 형태',p.tenure],['사업 계획량',amount(p.planned_units)]];
   const late=stageRows.map(r=>({row:r,done:r.measurements.find(v=>!estimatedField(v,'date')&&Number.isFinite(r.target)&&v.units>=r.target)})).filter(({row,done})=>done&&row.planDate&&done.date>row.planDate);
   const next=stageRows.filter(r=>r.planDate>cutoff).sort((a,b)=>a.planDate.localeCompare(b.planDate))[0];
   summary=[cutoff+' 기준 사업 계획량 '+amount(p.planned_units)+' · 현재 채택량은 착공 '+amount(stageRows.find(r=>r.stage==='CONSTRUCTION').current)+', 공급 '+amount(stageRows.find(r=>r.stage==='SUPPLY').current)+'입니다.',next?'다음 목표는 '+next.planDate+' '+next.label+' '+amount(next.target)+'입니다.':'기준일 이후의 다음 목표 일정은 미확보입니다.'];
   if(late.length)summary.push('목표량 도달과 별개로 '+late.map(({row,done})=>row.label+' 단계는 목표일보다 '+Math.round((Date.parse(done.date)-Date.parse(row.planDate))/86400000)+'일 늦게 이행').join(', ')+'했습니다.');
   add('목표일 대비 이행 일정',['단계','목표일','이행일','일정 차이'],stageRows.map(r=>{const done=r.measurements.find(v=>!estimatedField(v,'date')&&Number.isFinite(r.target)&&v.units>=r.target),days=done&&r.planDate?Math.round((Date.parse(done.date)-Date.parse(r.planDate))/86400000):null;return [r.label,r.planDate||'미확보',done?.date||'완료 미확인',days==null?(r.planDate>cutoff?'목표 미도래':'판단 보류'):days>0?days+'일 늦음':days<0?-days+'일 빠름':'목표일 이행'];}),'단계 목표량에 도달한 이행일을 목표일과 비교합니다. 일부 물량의 이행일을 단계 전체 완료일로 사용하지 않습니다.');
   add('향후 단계별 이행 일정',['단계','예정일','계획 물량'],stageRows.flatMap(r=>r.plans.filter(p=>p.date&&p.date>cutoff).map(p=>[r.label,p.date,amount(p.units)])).filter((r,i,a)=>a.findIndex(v=>JSON.stringify(v)===JSON.stringify(r))===i).sort((a,b)=>a[1].localeCompare(b[1])),'예정 일정이며 완료 실적에 포함하지 않습니다.');
  }else{
   stageRows=Object.entries(stages).filter(([key])=>d.summary_cards?.[key]).map(([stage,label])=>({stage,label,current:sumKnown(projects.map(p=>measured(p,stage,cutoff))),expected:d.summary_cards[stage].expected_units??null}));
   charts.push(bar(s.comparison_date?'두 기준일의 단계별 누적 비교':'단계별 누적 실적과 연말 전망',stageRows,comparisonSeries,'선택 화면과 같은 기준일·보조 기준일 수치입니다. 과거 연도 실적을 포함하며 단계 간 물량을 합산하지 않습니다.'));
   const grouped=new Map();for(const p of projects){const key=c.kind==='policy'?(p.program_id||p.program||'미분류'):[p.region,p.municipality].filter(Boolean).join(' ')||'지역 미분류';if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(p);}
   groups=[...grouped.values()].map(ps=>({label:c.kind==='policy'?(ps[0].program||'프로그램 미분류'):[ps[0].region,ps[0].municipality].filter(Boolean).join(' ')||'지역 미분류',count:ps.length,construction:sumKnown(ps.map(p=>measured(p,'CONSTRUCTION',cutoff))),supply:sumKnown(ps.map(p=>measured(p,'SUPPLY',cutoff))),knownConstruction:ps.filter(p=>measured(p,'CONSTRUCTION',cutoff)!=null).length,knownSupply:ps.filter(p=>measured(p,'SUPPLY',cutoff)!=null).length})).sort((a,b)=>(b.construction||0)-(a.construction||0)||(b.supply||0)-(a.supply||0)||a.label.localeCompare(b.label));
   for(let i=0;i<groups.length;i+=6)charts.push(bar((c.kind==='policy'?'프로그램':'지역')+'별 실적'+(groups.length>6?' · '+(i+1)+'–'+Math.min(i+6,groups.length):''),groups.slice(i,i+6),[{key:'construction',label:'누적 착공 실적',color:'#cb641d'},{key:'supply',label:'누적 공급 실적',color:'#176d86'}],'물량이 큰 묶음부터 비교합니다. 각 묶음은 해당 범위의 관리 사업을 한 번씩 집계합니다. 측정값 미확보 사업은 합계에 포함하지 않습니다.'));
   if(d.statistics?.monthly?.length)charts.push({type:'trend',title:'최근 12개월 착공·공급 증가 흐름',rows:d.statistics.monthly.slice(-12).map(r=>({label:r.month,construction:r.CONSTRUCTION??null,supply:r.SUPPLY??null})),series:[{key:'construction',label:'착공 증가',color:'#cb641d'},{key:'supply',label:'공급 증가',color:'#176d86'}],unit:'호',note:'단계별 누적 측정값의 월 증가분입니다. 현재 월은 기준일까지의 부분 실적입니다.'});
   riskRows=risks(projects,cutoff,d.issues||[]);
   const lead=groups.find(r=>r.construction!=null),c0={...d.summary_cards?.CONSTRUCTION,current_units:sumKnown(projects.map(p=>measured(p,'CONSTRUCTION',cutoff)))},s0={...d.summary_cards?.SUPPLY,current_units:sumKnown(projects.map(p=>measured(p,'SUPPLY',cutoff)))};
   summary=[cutoff+' 기준 '+projects.length+'개 사업의 현재 누적 착공 '+amount(c0?.current_units)+', 누적 공급 '+amount(s0?.current_units)+'입니다.',(s.comparison_date?comparisonLabel+' 착공 ':s.year+'년 말 착공 예상 ')+amount(c0?.expected_units)+(s.comparison_date?', 공급 ':', 공급 예상 ')+amount(s0?.expected_units)+'입니다.',lead?lead.label+'의 누적 착공 실적량이 '+amount(lead.construction)+'로 가장 큽니다.':'상위 묶음별 착공 실적은 미확보입니다.'];
  }
  const statusById=new Map();for(const r of riskRows){if(!statusById.has(r.id))statusById.set(r.id,r.status);}
  const counts={DELAYED:0,WARNING:0,UNKNOWN:0};for(const v of statusById.values())counts[v]++;
  const management=[{label:'지연',count:counts.DELAYED},{label:'주의',count:counts.WARNING},{label:'기한 경과·측정 미확보',count:counts.UNKNOWN}];
  summary.push('중점 점검 대상은 지연 '+counts.DELAYED+'개, 주의 '+counts.WARNING+'개 사업입니다. 기한 경과 후 측정 미확보 사업 '+counts.UNKNOWN+'개는 별도로 관리합니다.');
  const riskChart=bar('중점 점검 사업 현황',management,[{key:'count',label:'사업 수',color:'#9b3848'}],'사업별 가장 높은 관리 상태로 한 번만 집계합니다. 아래 표에서는 해당 단계들을 모두 표시합니다.','개');
  const riskNote='기한이 도래한 단계 목표 대비 부족률 2% 이상은 지연, 0% 초과~2% 미만은 주의입니다. 측정값 미확보는 지연으로 단정하지 않습니다. 등록 지연도 함께 반영합니다.';
  const exceptions=riskRows.filter(r=>r.status!=='UNKNOWN'),unknown=riskRows.filter(r=>r.status==='UNKNOWN');
  const riskSections=[{title:'지연·주의 사업 및 점검 단계',headers:['사업 / 상위 분류','상태·단계','목표일','목표 / 실적','부족 물량','후속 점검'],rows:exceptions.map(r=>[r.name+' / '+(c.kind==='policy'?r.program:r.region),({DELAYED:'지연',WARNING:'주의'}[r.status])+' · '+r.label,r.date,amount(r.target)+' / '+amount(r.actual),amount(r.gap),r.action]),note:riskNote}];
  if(unknown.length)riskSections.push({title:'기한 경과 후 실적 확인이 필요한 단계',headers:['사업','단계','목표일','목표량','확인 사항'],rows:unknown.map(r=>[r.name,r.label,r.date,amount(r.target),r.reason]),note:'현재 측정값이 없어 목표 대비 부족률을 산출할 수 없는 사업입니다.'});
  const cases=(c.operations?.cases||[]).filter(r=>r.status!=='RESOLVED');
  if(cases.length)riskSections.push({title:'등록된 후속 조치',headers:['대상','조치 내용','관리 상태'],rows:cases.map(r=>[r.project_name||r.name||r.project_id||r.scope_id,r.description||r.reason||r.basis,({OPEN:'진행 중',IN_PROGRESS:'진행 중',BLOCKED:'조치 필요'}[r.status]||r.status)]),note:'등록된 미완료 조치입니다.'});
  const progress=progressModel(projects,cutoff),location=locationModel(c);
  const evaluated=progress.rows.filter(r=>r.rate!=null);
  summary.unshift(evaluated.length?'도래 목표 대비 달성률'+(stageRows.some(r=>r.estimated)?'(추정 포함)':'')+'은 '+evaluated.map(r=>r.label+' '+r.rate.toFixed(1)+'%').join(', ')+'입니다.':'도래 목표와 같은 범위의 실적이 함께 확보되지 않아 목표 달성률은 판단을 보류합니다.');
  const progressSection={title:'기준일 현재 목표 대비 이행',headers:['단계','도래 목표','동일 대상 실적','달성률','목표 − 실적','판정 / 비교 범위'],rows:progress.rows.map(r=>[r.label,amount(r.target),amount(r.actual),r.rate==null?'판단 보류':r.rate.toFixed(1)+'%',amount(r.gap),r.due?assess(r.target,r.actual).label+' · '+r.known+'/'+r.due+'개 사업':'목표 미도래·미확보']),note:'달성률 = 동일 대상 실적 ÷ 도래 목표 × 100. 도래 목표가 없는 단계와 실적이 미확보인 단계는 판단을 보류합니다. 준공은 건설의 보조 이정표입니다.'};
  const notes=['사업 실적은 사업화·인허가·착공·공급·입주의 이행량과 이행일입니다. 데이터 수집·연결 건수는 사업 실적으로 계산하지 않습니다.','입주 실적은 입주 시작이 확인된 사업 물량이며 실제 거주 가구 수와 구분합니다.','기준일 현재의 실적과 미래 목표·예상을 구분합니다. 미확보는 0호가 아닙니다.','단계별 물량은 같은 주택을 포함할 수 있으므로 단계 간 합산하지 않습니다. 정책 연결 누적에는 이전 연도 실적도 포함됩니다.'];
  for(const r of c.availability||[])if(r.status!=='READY')notes.push(r.name+': 조회 미완료.');
  return {kind:c.kind,title:(s.name||'선택 범위')+' 추진현황 보고서',scope:s,summary,stageRows,groups,meta,charts,schedule:stageSchedule(projects,cutoff),progress,progressSection,location,riskChart,riskSections,sections,notes,counts};
 }
 function svgStart(title,h){return '<svg class="report-chart" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 '+h+'" role="img" aria-label="'+e(title)+'"><title>'+e(title)+'</title><rect width="900" height="'+h+'" fill="white"/>';}
 const label=(x,y,t,extra='')=>'<text x="'+x+'" y="'+y+'" font-family="sans-serif" font-size="14" fill="#29465c" '+extra+'>'+e(t)+'</text>';
 function wrapLabel(value,max=23){const a=Array.from(text(value)),lines=[];for(let i=0;i<a.length;i+=max)lines.push(a.slice(i,i+max).join(''));return lines;}
 function barSvg(c){
  const max=Math.max(1,...c.rows.flatMap(r=>c.series.map(s=>r[s.key]??0))),rowH=88,h=56+c.rows.length*rowH,x=274,w=455;
  let svg=svgStart(c.title,h);
  for(let i=0;i<=4;i++){const xx=x+w*i/4;svg+='<line x1="'+xx+'" x2="'+xx+'" y1="30" y2="'+(h-15)+'" stroke="#e0e8ed"/>'+label(xx,20,Math.round(max*i/4).toLocaleString('ko-KR'),'text-anchor="middle" font-size="11"');}
  c.rows.forEach((r,i)=>{const y=50+i*rowH;const lines=wrapLabel(r.label,22);lines.slice(0,3).forEach((line,j)=>{svg+=label(10,y+12+j*17,line);});if(r.count!=null&&c.unit!=='개')svg+=label(10,y+68,r.count+'개 사업 · 착공 확보 '+r.knownConstruction+' / 공급 확보 '+r.knownSupply,'font-size="11"');
   c.series.forEach((s,j)=>{const value=r[s.key],yy=y+j*28;svg+='<rect x="'+x+'" y="'+yy+'" width="'+(value==null?0:w*value/max)+'" height="17" rx="3" fill="'+s.color+'"'+(s.outline?' stroke="#5d8097" stroke-dasharray="4 3"':'')+'/>'+label(x+w+14,yy+14,value==null?'미확보':Number(value).toLocaleString('ko-KR')+c.unit,'font-size="13"');if(value==null)svg+=label(x+8,yy+14,'—');});
  });return svg+'</svg>';
 }
 function stepsSvg(c){
  let svg=svgStart(c.title,242);const labels={NORMAL:'목표 도달',MEASURED:'실적 확인',DELAYED:'지연',WARNING:'주의',UPCOMING:'추진 예정',UNKNOWN:'판정 미확보'};
  c.rows.forEach((r,i)=>{const x=8+i*149,color=r.status==='DELAYED'?'#b63b4b':r.status==='WARNING'?'#9e711a':r.current>0?'#176d86':'#718394';if(i<5)svg+='<path d="M'+(x+133)+' 47h16" stroke="#b4c8d5" stroke-width="3"/>';
   svg+='<rect x="'+x+'" y="18" width="133" height="202" rx="10" fill="#f6f9fc" stroke="#cedde7"/><circle cx="'+(x+25)+'" cy="47" r="15" fill="'+color+'"/>'+label(x+25,52,i+1,'text-anchor="middle" style="fill:white"')+label(x+49,52,r.label,'font-weight="700"')+label(x+12,88,(r.estimated?'추정 포함':labels[r.status]), 'style="fill:'+color+'"')+label(x+12,119,amount(r.current),'font-weight="700"')+label(x+12,141,r.date||'측정일 미확보','font-size="12"')+label(x+12,175,'목표 '+amount(r.target),'font-size="12"')+label(x+12,199,r.planDate||'일정 미확보','font-size="12"');
  });return svg+'</svg>';
 }
 function timelineSvg(c){
  const dates=c.rows.flatMap(r=>[r.date,r.planDate]).filter(Boolean).map(Date.parse).filter(Number.isFinite);if(!dates.length)return '<p class="report-note">일정 미확보</p>';
  const lo=Math.min(...dates),hi=Math.max(...dates),span=Math.max(86400000,hi-lo),x=d=>145+(Date.parse(d)-lo)/span*510;let svg=svgStart(c.title,382);
  for(let i=0;i<=4;i++){const xx=145+510*i/4,t=new Date(lo+span*i/4).toISOString().slice(0,7);svg+='<line x1="'+xx+'" x2="'+xx+'" y1="40" y2="351" stroke="#e0e8ed"/>'+label(xx,24,t,'text-anchor="middle" font-size="12"');}
  c.rows.forEach((r,i)=>{const y=65+i*49;svg+=label(12,y+5,r.label);if(r.date&&r.planDate)svg+='<line x1="'+x(r.date)+'" x2="'+x(r.planDate)+'" y1="'+y+'" y2="'+y+'" stroke="#b7cbd7" stroke-width="3"/>';if(r.planDate){const xx=x(r.planDate);svg+='<path d="M'+xx+' '+(y-8)+'l8 8 -8 8 -8 -8z" stroke="#597d96" fill="white" stroke-width="2"/>';}if(r.date)svg+='<circle cx="'+x(r.date)+'" cy="'+y+'" r="5" fill="#176d86"/>';svg+=label(686,y-3,'실적 '+(r.date||'미확보'),'font-size="12"')+label(686,y+15,'목표 '+(r.planDate||'미확보'),'font-size="12"');});return svg+'</svg>';
 }
 function trendSvg(c){
  const values=c.rows.flatMap(r=>c.series.map(s=>r[s.key])).filter(Number.isFinite);
  if(!values.length)return '<p class="report-note">시계열 미확보 · 자료가 없음을 0으로 표시하지 않습니다.</p>';
  const dates=c.rows.map(r=>Date.parse(r.label)),dated=dates.every(Number.isFinite),lo=dated?Math.min(...dates):0,span=dated?Math.max(1,Math.max(...dates)-lo):1;
  const max=Math.max(1,...values),x=i=>72+(dated?(dates[i]-lo)/span:i/Math.max(1,c.rows.length-1))*740,y=v=>235-v/max*180;
  let svg=svgStart(c.title,286);
  for(let i=0;i<=3;i++){const yy=y(max*i/3);svg+='<line x1="72" x2="812" y1="'+yy+'" y2="'+yy+'" stroke="#e0e8ed"/>'+label(64,yy+4,Math.round(max*i/3).toLocaleString('ko-KR'),'text-anchor="end" font-size="12"');}
  c.series.forEach((s,j)=>{let segment=false;const path=c.rows.map((r,i)=>{if(r[s.key]==null){segment=false;return '';}const part=segment?(c.step?'H'+x(i)+'V'+y(r[s.key]):'L'+x(i)+' '+y(r[s.key])):'M'+x(i)+' '+y(r[s.key]);segment=true;return part;}).join(' ');svg+='<path d="'+path+'" fill="none" stroke="'+s.color+'" stroke-width="3"'+(j?' stroke-dasharray="'+['','6 4','2 3','10 3 2 3'][j%4]+'"':'')+'/>';c.rows.forEach((r,i)=>{if(r[s.key]!=null)svg+='<circle cx="'+x(i)+'" cy="'+y(r[s.key])+'" r="4" fill="'+s.color+'"><title>'+e(r.label+' '+s.label+' '+numeric(r[s.key],c.unit))+'</title></circle>';});});
  let lastX=-Infinity;c.rows.forEach((r,i)=>{const xx=x(i);if(i===c.rows.length-1||xx-lastX>=120&&xx<720){svg+=label(xx,263,r.label,'text-anchor="middle" font-size="12"');lastX=xx;}});return svg+'</svg>';
 }

 const graphic=c=>c.type==='steps'?stepsSvg(c):c.type==='timeline'?timelineSvg(c):c.type==='trend'?trendSvg(c):barSvg(c);
 function legendSymbol(color,line=false,dash='',outline=false){
  return '<svg class="report-legend-swatch" xmlns="http://www.w3.org/2000/svg" width="34" height="16" viewBox="0 0 34 16" aria-hidden="true" style="width:34px;height:16px;flex:none;vertical-align:middle;print-color-adjust:exact;-webkit-print-color-adjust:exact">'+(line?'<line x1="2" x2="32" y1="8" y2="8" stroke="'+color+'" stroke-width="3"'+(dash?' stroke-dasharray="'+dash+'"':'')+'/><circle cx="17" cy="8" r="3.5" fill="'+(outline?'white':color)+'" stroke="'+color+'" stroke-width="2"/>':'<rect x="5" y="2" width="24" height="12" rx="1" fill="'+color+'" stroke="#57768b"/>')+'</svg>';
 }
 function chartHtml(c){return '<figure class="report-figure"><figcaption>'+e(c.title)+'</figcaption>'+(c.series?'<div class="report-legend">'+c.series.map((s,i)=>'<span>'+legendSymbol(s.color,c.type==='trend',c.type==='trend'?['','6 4','2 3','10 3 2 3'][i%4]:'')+e(s.label)+'</span>').join('')+'<span>단위: '+e(c.unit)+'</span></div>':'')+graphic(c)+'<p class="report-note">'+e(c.note)+'</p></figure>';}
 function tableHtml(s){return '<section class="report-section"><h3>'+e(s.title)+'</h3><p class="report-note">'+e(s.note||'')+'</p>'+(s.rows.length?'<table><thead><tr>'+s.headers.map(h=>'<th>'+e(h)+'</th>').join('')+'</tr></thead><tbody>'+s.rows.map(row=>'<tr>'+row.map(v=>'<td>'+e(v)+'</td>').join('')+'</tr>').join('')+'</tbody></table>':'<p>해당 조건으로 분류된 항목이 없습니다.</p>')+'</section>';}
 function body(m){
  if(m.kind!=='project')return PortfolioProgressReport.body(m);
  const steps=m.charts.find(c=>c.type==='steps')||{type:'steps',title:'사업화부터 입주까지 단계별 진행',rows:Object.entries(stages).map(([stage,label])=>({stage,label,...m.stageRows.find(r=>r.stage===stage),status:'UNKNOWN'})),note:'단계별 실적과 목표 일정입니다.'};
  return '<div class="report-content"><header><small>the주택 · 주택공급 디지털 상황판</small><h1>'+e(m.title)+'</h1><p>기준일 '+e(m.scope.as_of_date)+(m.scope.comparison_date?' · 보조 기준일 '+e(m.scope.comparison_date):'')+' · '+e([m.scope.region,m.scope.municipality].filter(Boolean).join(' ')||'선택 범위 전체')+'</p></header><h2>1부. 사업 진행 현황 · 목표 대비 이행</h2><section class="report-summary"><h3>추진 현황 요약</h3>'+m.summary.map(s=>'<p>'+e(s)+'</p>').join('')+'</section>'+(m.meta.length?'<dl class="report-meta">'+m.meta.map(([k,v])=>'<div><dt>'+e(k)+'</dt><dd>'+e(v)+'</dd></div>').join('')+'</dl>':'')+chartHtml(steps)+scheduleHtml(m.schedule)+'<h2 id="report-location" class="report-location-heading">2부. 지역 입지 · 생활 여건과 가구 변화</h2>'+m.location.notes.map(n=>'<p>'+e(n)+'</p>').join('')+m.location.charts.map(chartHtml).join('')+m.location.sections.map(tableHtml).join('')+'</div>';
 }

 function chartMd(c){
  const out=['### '+md(c.title),'',c.note,''];
  if(c.type==='steps'){out.push('```mermaid','flowchart LR',...c.rows.map((r,i)=>'  S'+i+'["'+md(r.label+' · '+amount(r.current)+' · '+(r.date||'측정일 미확보')).replace(/"/g,'＂')+'"]'),'  S0 --> S1 --> S2 --> S3','  S2 --> S4','  S3 --> S5','  S4 --> S5','```','');}
  else if(c.type==='trend'){if(c.rows.length&&c.rows.every(r=>c.series.every(s=>Number.isFinite(r[s.key])))){const max=Math.max(1,...c.rows.flatMap(r=>c.series.map(s=>r[s.key])));out.push('```mermaid','xychart-beta','  title "'+md(c.title)+'"','  x-axis ['+c.rows.map(r=>'"'+md(r.label)+'"').join(', ')+']','  y-axis "'+c.unit+'" 0 --> '+max,...c.series.map(s=>'  line ['+c.rows.map(r=>r[s.key]).join(', ')+']'),'```','',c.series.map((s,i)=>(i+1)+'번째 선: '+s.label).join(' · '),'');}else out.push('결측 구간을 보존한 시계열은 HTML 보고서에서 확인할 수 있습니다. 아래 표에 목표와 실적을 함께 표시합니다.','');}
  else if(c.series){for(const s of c.series){const known=c.rows.filter(r=>r[s.key]!=null);if(!known.length)continue;const axis=known.map(r=>'"'+md(r.label).replace(/"/g,'＂')+'"').join(', '),max=Math.max(1,...known.map(r=>r[s.key]));out.push('```mermaid','xychart-beta','  title "'+md(s.label)+'"','  x-axis ['+axis+']','  y-axis "'+c.unit+'" 0 --> '+max,'  '+(c.type==='trend'?'line':'bar')+' ['+known.map(r=>r[s.key]).join(', ')+']','```','');}}
  const headers=c.series?['구분',...c.series.map(s=>s.label)]:['단계','현재 측정량','측정일','목표량','목표일'];
  const rows=c.rows.map(r=>c.series?[r.label,...c.series.map(s=>r[s.key]==null?'미확보':Number(r[s.key]).toLocaleString('ko-KR')+c.unit)]:[r.label,amount(r.current),r.date||'미확보',amount(r.target),r.planDate||'미확보']);
  out.push(mdTable(headers,rows),'');return out.join('\n');
 }
 function mdTable(headers,rows){return rows.length?'| '+headers.map(md).join(' | ')+' |\n| '+headers.map(()=>'---').join(' | ')+' |\n'+rows.map(r=>'| '+r.map(md).join(' | ')+' |').join('\n'):'해당 조건으로 분류된 항목이 없습니다.';}
 function markdown(m){
  if(m.kind!=='project')return PortfolioProgressReport.markdown(m);
  const section=s=>['### '+md(s.title),'',s.note,'',mdTable(s.headers,s.rows),''];
  const steps=m.charts.find(c=>c.type==='steps'),schedule=m.schedule;
  // Embed the same categorical SVG in Markdown so stage positions and line colors survive export.
  return ['# '+md(m.title),'','the주택 · 주택공급 디지털 상황판','',`기준일: ${md(m.scope.as_of_date)} · 기준연도: ${md(m.scope.year)}${m.scope.comparison_date?' · 보조 기준일: '+md(m.scope.comparison_date):''}`,'','## 1부. 사업 진행 현황 · 목표 대비 이행','','### 추진 현황 요약','',...m.summary.map(v=>'- '+md(v)),'',...(m.meta.length?[mdTable(['사업 개요','내용'],m.meta),'']:[]),...(steps?[chartMd(steps)]:[]),'### '+md(schedule.title),'','<div style="display:flex;gap:18px;align-items:center">'+legendSymbol('#a5cdee',true,'7 4',true)+'목표 '+legendSymbol('#e681a8',true)+'수집 측정 '+legendSymbol('#e681a8',true,'',true)+'추정(선후관계 검증)</div>','',stageScheduleSvg(schedule),'',schedule.note,'','## 2부. 지역 입지 · 생활 여건과 가구 변화','',...m.location.notes.map(md),'',...m.location.charts.map(chartMd),...m.location.sections.flatMap(section),''].join('\n');
 }

 const style="@page{size:A4;margin:16mm}body{margin:0 auto;max-width:1050px;padding:24px}@media print{body{max-width:none;padding:0}}\n.report-content{color:#18344a;font:14px/1.65 system-ui,sans-serif;overflow-wrap:anywhere}.report-content h1{word-break:keep-all;font-size:26px;line-height:1.4;border-bottom:3px solid #194f7e;padding-bottom:16px}.report-content h2{font-size:20px;margin:28px 0 16px;color:#194f7e;break-after:avoid}.report-content h3{font-size:16px;break-after:avoid}.report-content .report-summary{padding:4px 22px 15px;border-left:5px solid #176d86;background:#f1f7fa}.report-content .report-summary p{margin:9px 0}.report-content .report-meta{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:24px 0}.report-content .report-meta>div{padding:10px;border-bottom:1px solid #d5e1e8}.report-content dt{font-size:12px;color:#647c8d}.report-content dd{margin:5px 0 0;font-weight:600}.report-content .report-figure{margin:20px 0 28px;border:1px solid #d8e3eb;border-radius:10px;padding:18px;background:white;break-inside:avoid}.report-content figcaption{font-size:17px;font-weight:700;line-height:1.5;margin:0 0 12px}.report-content .report-chart{display:block;width:100%;height:auto;overflow:visible}.report-content .report-legend{display:flex;gap:20px;flex-wrap:wrap;font-size:12px;margin-bottom:12px}.report-content .report-legend span{display:flex;align-items:center;gap:6px}.report-content .report-legend i{width:11px;height:11px;display:inline-block;border:1px solid #57768b}.report-content .report-note{font-size:12px;color:#546f83;margin:10px 0 0;line-height:1.7}.report-content table{width:100%;min-width:0;table-layout:fixed;border-collapse:collapse;font-size:12px}.report-content th,.report-content td{border:1px solid #d3dfeb;padding:9px;text-align:left;vertical-align:top;overflow-wrap:anywhere}.report-content th{background:#edf3f8}.report-content .report-section{margin:24px 0}.report-content .report-section .report-note{margin-bottom:12px;break-after:avoid}.report-content .report-section tr{break-inside:avoid}.report-content .report-section th:first-child{width:25%}.report-content .report-method{border-top:1px solid #d3dfeb;margin-top:28px;font-size:12px}.report-content .report-method h2{font-size:16px}.report-content .report-location-heading{border-top:3px solid #b9cbd7;padding-top:22px}.report-content small{color:#5f7283}\n@media(max-width:600px){.report-content .report-meta{grid-template-columns:repeat(2,minmax(0,1fr))}.report-content .report-figure{padding:10px}.report-content .report-summary{padding:4px 12px 12px}.report-content .report-chart{min-width:560px}.report-content .report-figure{overflow-x:auto}.report-content table{font-size:11px}.report-content th,.report-content td{padding:5px}}\n@media print{.report-content{font-size:10.5pt;line-height:1.5}.report-content h1{word-break:keep-all;font-size:22pt}.report-content h2{font-size:16pt}.report-content .report-figure{overflow:visible;padding:12px;break-inside:avoid}.report-content .report-chart{min-width:0;width:100%}.report-content .report-location-heading{break-before:page}.report-content th{print-color-adjust:exact;-webkit-print-color-adjust:exact}.report-content .report-legend,.report-content .report-note,.report-content table{font-size:9pt}.report-content thead{display:table-header-group}.report-content .report-meta{grid-template-columns:repeat(3,minmax(0,1fr))}.report-content p{orphans:3;widows:3}}\n";
 function html(m){if(m.kind!=='project')return PortfolioProgressReport.html(m);return '<!doctype html><html lang="ko"><meta charset="utf-8"><title>'+e(m.title)+'</title><style>'+style+'</style><body>'+body(m)+'</body></html>';}
 function save(text,type,name){const url=URL.createObjectURL(new Blob([text],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);}
 let busy=false;
 async function create(){
  if(typeof state!=='undefined'&&state.view==='policy-progress'&&typeof PolicyBriefReport!=='undefined'){try{await PolicyBriefReport.open();}catch(error){document.getElementById('error').textContent=error.message;document.getElementById('error').hidden=false;}return;}
  if(busy)return;const button=document.getElementById('progress-report-create');busy=true;button.disabled=true;button.textContent='보고서 구성 중…';
  try{
   const captured=ReportMD.clean(await ReportMD.capture()),m=model(captured),dialog=document.createElement('dialog');dialog.className='progress-report-dialog';dialog.setAttribute('aria-label','추진현황 보고서 미리보기');
   dialog.innerHTML='<div class="progress-report-toolbar"><strong>추진현황 보고서 미리보기</strong><button data-report-print>인쇄 / PDF 저장</button><button data-report-md>완성본 MD ↓</button><button data-report-html>HTML ↓</button><button data-report-close aria-label="보고서 닫기">닫기</button></div><article class="progress-report-document">'+body(m)+'</article>';
   document.body.append(dialog);dialog.querySelector('[data-report-close]').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{dialog.remove();button.focus();});
   const filename='the주택_'+m.title.replace(/[^\p{L}\p{N}._-]+/gu,'_').slice(0,80)+'_'+m.scope.as_of_date;
   dialog.querySelector('[data-report-md]').onclick=()=>save(markdown(m),'text/markdown;charset=utf-8',filename+'.md');
   dialog.querySelector('[data-report-html]').onclick=()=>save(html(m),'text/html;charset=utf-8',filename+'.html');
   dialog.querySelector('[data-report-print]').onclick=()=>{const frame=document.createElement('iframe');frame.className='progress-report-print-frame';frame.title='보고서 인쇄';frame.onload=()=>{frame.contentWindow.focus();frame.contentWindow.print();};frame.srcdoc=m.kind==='project'?html(m).replace(/<style>[\s\S]*?<\/style>/,'<link rel="stylesheet" href="/poc/home/assets/progress-report-print.css?v=20261022-estimate-legend">'):html(m);dialog.append(frame);dialog.addEventListener('close',()=>frame.remove(),{once:true});};dialog.showModal();
  }catch(error){document.getElementById('error').textContent=error.message;document.getElementById('error').hidden=false;}
  finally{busy=false;button.disabled=false;button.textContent='추진현황 보고서 만들기';}
 }
 function syncView(view){document.getElementById('progress-report-create').hidden=!supported.has(view);}
 function start(){document.getElementById('progress-report-create').addEventListener('click',create);}
 return {model,markdown,html,reached,risks,start,syncView};
})();
