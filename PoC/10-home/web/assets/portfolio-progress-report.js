 'use strict';
const PortfolioProgressReport=(()=>{
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
 function measured(p,stage,date){const v=maxKnown((p.events||[]).filter(r=>r.stage===stage&&(r.status||'ACTUAL')==='ACTUAL'&&r.origin!=='PLANNED'&&r.event_date&&r.event_date<=date).map(r=>r.units));return v==null?null:Math.min(cap(p),v);}
 const assess=(target,actual)=>PolicyStageFlow.assessGap(target,actual);
 function risks(projects,date,issues=[]){
  const list=[];
  for(const p of projects){
   const found=[];
   for(const [stage,label] of Object.entries(stages)){
    const goals=(p.schedules||[]).filter(r=>r.stage===stage&&r.due_date&&r.due_date<=date&&Number.isFinite(r.units));
    if(!goals.length)continue;
    const goal=goals.slice().sort((a,b)=>b.units-a.units||b.due_date.localeCompare(a.due_date))[0],target=Math.min(cap(p),goal.units),actual=measured(p,stage,date),a=assess(target,actual);
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
  const actual=(cell.management?.measurement||[]).filter(filter).filter(r=>r.date&&r.date<=date&&(r.status||'ACTUAL')==='ACTUAL').sort((a,b)=>a.date.localeCompare(b.date)),plans=(cell.management?.target||[]).filter(filter);
  const latest=actual.at(-1),due=plans.filter(r=>r.date&&r.date<=date).sort((a,b)=>a.date.localeCompare(b.date)).at(-1),next=plans.filter(r=>r.date&&r.date>date).sort((a,b)=>a.date.localeCompare(b.date))[0];
  const target=due||next||plans[0],current=latest?.units??null,yearPlan=maxKnown(plans.filter(r=>r.date&&r.date<=end).map(r=>r.units)),expected=maxKnown([current,yearPlan]);
  const check=due?assess(due.units,current):null;
  return {stage,label,current,date:latest?.date||null,expected,target:target?.units??null,planDate:target?.date||null,plans,status:check?.status||(current>0?'MEASURED':next?'UPCOMING':'UNKNOWN')};
 });}
 const bar=(title,rows,series,note='',unit='호')=>({type:'bars',title,rows,series,note,unit});
 const currentSeries=[{key:'current',label:'현재 누적',color:'#176d86'},{key:'expected',label:'연말 누적 예상',color:'#b6cbd9',outline:true}];
 function model(input){
  const c=JSON.parse(JSON.stringify(input)),d=c.data,s=c.scope,end=String(s.year)+'-12-31',cutoff=s.as_of_date<end?s.as_of_date:end,sections=[],charts=[],comparisonDate=s.comparison_date||end,comparisonLabel=s.comparison_date?s.comparison_date+(s.comparison_date<=(s.data_as_of_date||s.as_of_date)?' 누적 측정':' 누적 예상'):s.year+'년 말',comparisonSeries=currentSeries.map(v=>v.key==='expected'?{...v,label:s.comparison_date?comparisonLabel:'연말 누적 예상'}:v);
  const add=(title,headers,rows,note='')=>sections.push({title,headers,rows,note});
  let projects=d.cohorts||[],stageRows=[],groups=[],riskRows=[],summary=[],meta=[];
  if(c.kind==='project'){
   const m=d.project,p=m.project;stageRows=projectStages(m,cutoff,end);
   projects=[{...p,events:stageRows.flatMap(r=>r.date?[{stage:r.stage,event_date:r.date,units:r.current,status:'ACTUAL'}]:[]),schedules:stageRows.flatMap(r=>r.plans.map(v=>({stage:r.stage,due_date:v.date,units:v.units})))}];
   riskRows=risks(projects,cutoff);
   charts.push({type:'steps',title:'사업화부터 입주까지 단계별 진행',rows:stageRows,note:'각 단계의 측정량과 예정일을 함께 표시합니다. 공급은 준공 전·후에 병행할 수 있습니다.'});
   charts.push(bar('단계별 실적과 목표 물량',stageRows,[{key:'current',label:'현재 측정량',color:'#176d86'},{key:'target',label:'단계 목표',color:'#b6cbd9',outline:true}],'측정량은 건설 공정률이 아닙니다. 목표를 확보하지 못한 단계는 달성률을 계산하지 않습니다.'));
   charts.push({type:'timeline',title:'단계별 실적일과 목표 일정',rows:stageRows,note:'● 측정일 · ◇ 목표·예정일. 시간축의 간격은 실제 날짜 간격입니다.'});
   meta=[['프로그램',m.parent?.name||p.program],['지역',[p.region,p.municipality].filter(Boolean).join(' ')],['시행자',p.developer],['공급 유형',p.supply_type_assessment?.label||p.supply_type],['공급 형태',p.tenure],['사업 계획량',amount(p.planned_units)]];
   const achieved=stageRows.filter(r=>r.current>0),next=stageRows.filter(r=>r.planDate>cutoff).sort((a,b)=>a.planDate.localeCompare(b.planDate))[0];
   summary=[cutoff+' 기준 사업 계획량 '+amount(p.planned_units)+' 중 착공 '+amount(stageRows.find(r=>r.stage==='CONSTRUCTION').current)+', 공급 '+amount(stageRows.find(r=>r.stage==='SUPPLY').current)+'를 측정했습니다.',achieved.length?'측정값이 있는 단계는 '+achieved.map(r=>r.label).join(' · ')+'입니다.':'현재 일자와 물량이 함께 확보된 단계 실적이 없습니다.',next?'다음 목표는 '+next.planDate+' '+next.label+' '+amount(next.target)+'입니다.':'기준일 이후의 다음 목표 일정은 미확보입니다.'];
   add('향후 단계별 이행 일정',['단계','예정일','계획 물량'],stageRows.flatMap(r=>r.plans.filter(p=>p.date&&p.date>cutoff).map(p=>[r.label,p.date,amount(p.units)])).filter((r,i,a)=>a.findIndex(v=>JSON.stringify(v)===JSON.stringify(r))===i).sort((a,b)=>a[1].localeCompare(b[1])),'예정 일정이며 완료 실적에 포함하지 않습니다.');
  }else{
   stageRows=Object.entries(stages).filter(([key])=>d.summary_cards?.[key]).map(([stage,label])=>({stage,label,current:d.summary_cards[stage].current_units??null,expected:d.summary_cards[stage].expected_units??null}));
   charts.push(bar(s.comparison_date?'두 기준일의 단계별 누적 비교':'단계별 누적 실적과 연말 전망',stageRows,comparisonSeries,'선택 화면과 같은 기준일·보조 기준일 수치입니다. 과거 연도 실적을 포함하며 단계 간 물량을 합산하지 않습니다.'));
   const grouped=new Map();for(const p of projects){const key=c.kind==='policy'?(p.program_id||p.program||'미분류'):[p.region,p.municipality].filter(Boolean).join(' ')||'지역 미분류';if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(p);}
   groups=[...grouped.values()].map(ps=>({label:c.kind==='policy'?(ps[0].program||'프로그램 미분류'):[ps[0].region,ps[0].municipality].filter(Boolean).join(' ')||'지역 미분류',count:ps.length,construction:sumKnown(ps.map(p=>reached(p,'CONSTRUCTION',cutoff))),supply:sumKnown(ps.map(p=>reached(p,'SUPPLY',cutoff))),knownConstruction:ps.filter(p=>reached(p,'CONSTRUCTION',cutoff)!=null).length,knownSupply:ps.filter(p=>reached(p,'SUPPLY',cutoff)!=null).length})).sort((a,b)=>(b.construction||0)-(a.construction||0)||(b.supply||0)-(a.supply||0)||a.label.localeCompare(b.label));
   for(let i=0;i<groups.length;i+=6)charts.push(bar((c.kind==='policy'?'프로그램':'지역')+'별 실적'+(groups.length>6?' · '+(i+1)+'–'+Math.min(i+6,groups.length):''),groups.slice(i,i+6),[{key:'construction',label:'누적 착공 도달',color:'#cb641d'},{key:'supply',label:'누적 공급 도달',color:'#176d86'}],'물량이 큰 묶음부터 비교합니다. 각 묶음은 해당 범위의 관리 사업을 한 번씩 집계합니다. 측정값 미확보 사업은 합계에 포함하지 않습니다.'));
   if(d.statistics?.monthly?.length)charts.push({type:'trend',title:'최근 12개월 착공·공급 증가 흐름',rows:d.statistics.monthly.slice(-12).map(r=>({label:r.month,construction:r.CONSTRUCTION??null,supply:r.SUPPLY??null})),series:[{key:'construction',label:'착공 증가',color:'#cb641d'},{key:'supply',label:'공급 증가',color:'#176d86'}],unit:'호',note:'단계별 누적 측정값의 월 증가분입니다. 현재 월은 기준일까지의 부분 실적입니다.'});
   riskRows=risks(projects,cutoff,d.issues||[]);
   const lead=groups.find(r=>r.construction!=null),c0=d.summary_cards?.CONSTRUCTION,s0=d.summary_cards?.SUPPLY;
   summary=[cutoff+' 기준 '+projects.length+'개 사업의 현재 누적 착공 '+amount(c0?.current_units)+', 누적 공급 '+amount(s0?.current_units)+'입니다.',(s.comparison_date?comparisonLabel+' 착공 ':s.year+'년 말 착공 예상 ')+amount(c0?.expected_units)+(s.comparison_date?', 공급 ':', 공급 예상 ')+amount(s0?.expected_units)+'입니다.',lead?lead.label+'의 누적 착공 도달량이 '+amount(lead.construction)+'로 가장 큽니다.':'상위 묶음별 착공 실적은 미확보입니다.'];
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
  const notes=['기준일 현재의 실적과 미래 목표·예상을 구분합니다. 미확보는 0호가 아닙니다.','단계별 값은 중복되는 누적 도달량이므로 단계 간 합산하지 않습니다. 정책 연결 누적에는 이전 연도 실적도 포함됩니다.'];
  for(const r of c.availability||[])if(r.status!=='READY')notes.push(r.name+': 조회 미완료.');
  return {kind:c.kind,title:(s.name||'선택 범위')+' 추진현황 보고서',scope:s,summary,stageRows,groups,meta,charts,riskChart,riskSections,sections,notes,counts};
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
   svg+='<rect x="'+x+'" y="18" width="133" height="202" rx="10" fill="#f6f9fc" stroke="#cedde7"/><circle cx="'+(x+25)+'" cy="47" r="15" fill="'+color+'"/>'+label(x+25,52,i+1,'text-anchor="middle" style="fill:white"')+label(x+49,52,r.label,'font-weight="700"')+label(x+12,88,labels[r.status], 'style="fill:'+color+'"')+label(x+12,119,amount(r.current),'font-weight="700"')+label(x+12,141,r.date||'측정일 미확보','font-size="12"')+label(x+12,175,'목표 '+amount(r.target),'font-size="12"')+label(x+12,199,r.planDate||'일정 미확보','font-size="12"');
  });return svg+'</svg>';
 }
 function timelineSvg(c){
  const dates=c.rows.flatMap(r=>[r.date,r.planDate]).filter(Boolean).map(Date.parse).filter(Number.isFinite);if(!dates.length)return '<p class="report-note">일정 미확보</p>';
  const lo=Math.min(...dates),hi=Math.max(...dates),span=Math.max(86400000,hi-lo),x=d=>145+(Date.parse(d)-lo)/span*510;let svg=svgStart(c.title,382);
  for(let i=0;i<=4;i++){const xx=145+510*i/4,t=new Date(lo+span*i/4).toISOString().slice(0,7);svg+='<line x1="'+xx+'" x2="'+xx+'" y1="40" y2="351" stroke="#e0e8ed"/>'+label(xx,24,t,'text-anchor="middle" font-size="12"');}
  c.rows.forEach((r,i)=>{const y=65+i*49;svg+=label(12,y+5,r.label);if(r.date&&r.planDate)svg+='<line x1="'+x(r.date)+'" x2="'+x(r.planDate)+'" y1="'+y+'" y2="'+y+'" stroke="#b7cbd7" stroke-width="3"/>';if(r.planDate){const xx=x(r.planDate);svg+='<path d="M'+xx+' '+(y-8)+'l8 8 -8 8 -8 -8z" stroke="#597d96" fill="white" stroke-width="2"/>';}if(r.date)svg+='<circle cx="'+x(r.date)+'" cy="'+y+'" r="5" fill="#176d86"/>';svg+=label(686,y-3,'실적 '+(r.date||'미확보'),'font-size="12"')+label(686,y+15,'목표 '+(r.planDate||'미확보'),'font-size="12"');});return svg+'</svg>';
 }
 function trendSvg(c){const max=Math.max(1,...c.rows.flatMap(r=>c.series.map(s=>r[s.key]??0))),x=i=>72+i*740/Math.max(1,c.rows.length-1),y=v=>235-v/max*180;let svg=svgStart(c.title,286);
  for(let i=0;i<=3;i++){const yy=y(max*i/3);svg+='<line x1="72" x2="812" y1="'+yy+'" y2="'+yy+'" stroke="#e0e8ed"/>'+label(64,yy+4,Math.round(max*i/3).toLocaleString('ko-KR'),'text-anchor="end" font-size="12"');}
  c.series.forEach((s,j)=>{let segment=false;const path=c.rows.map((r,i)=>{if(r[s.key]==null){segment=false;return '';}const part=(segment?'L':'M')+x(i)+' '+y(r[s.key]);segment=true;return part;}).join(' ');svg+='<path d="'+path+'" fill="none" stroke="'+s.color+'" stroke-width="3"'+(j?' stroke-dasharray="6 4"':'')+'/>';c.rows.forEach((r,i)=>{if(r[s.key]!=null)svg+='<circle cx="'+x(i)+'" cy="'+y(r[s.key])+'" r="4" fill="'+s.color+'"><title>'+e(r.label+' '+s.label+' '+amount(r[s.key]))+'</title></circle>';});});c.rows.forEach((r,i)=>{if(i%2===0||i===c.rows.length-1)svg+=label(x(i),263,r.label,'text-anchor="middle" font-size="12"');});return svg+'</svg>';}
 const graphic=c=>c.type==='steps'?stepsSvg(c):c.type==='timeline'?timelineSvg(c):c.type==='trend'?trendSvg(c):barSvg(c);
 function legendSymbol(color,line=false,dash='',outline=false){
  return '<svg class="report-legend-swatch" xmlns="http://www.w3.org/2000/svg" width="34" height="16" viewBox="0 0 34 16" aria-hidden="true" style="width:34px;height:16px;flex:none;vertical-align:middle;print-color-adjust:exact;-webkit-print-color-adjust:exact">'+(line?'<line x1="2" x2="32" y1="8" y2="8" stroke="'+color+'" stroke-width="3"'+(dash?' stroke-dasharray="'+dash+'"':'')+'/><circle cx="17" cy="8" r="3.5" fill="'+(outline?'white':color)+'" stroke="'+color+'" stroke-width="2"/>':'<rect x="5" y="2" width="24" height="12" rx="1" fill="'+color+'" stroke="#57768b"/>')+'</svg>';
 }
 function chartHtml(c){return '<figure class="report-figure"><figcaption>'+e(c.title)+'</figcaption>'+(c.series?'<div class="report-legend">'+c.series.map((s,i)=>'<span>'+legendSymbol(s.color,c.type==='trend',c.type==='trend'&&i?'6 4':'')+e(s.label)+'</span>').join('')+'<span>단위: '+e(c.unit)+'</span></div>':'')+graphic(c)+'<p class="report-note">'+e(c.note)+'</p></figure>';}
 function tableHtml(s){return '<section class="report-section"><h3>'+e(s.title)+'</h3><p class="report-note">'+e(s.note||'')+'</p>'+(s.rows.length?'<table><thead><tr>'+s.headers.map(h=>'<th>'+e(h)+'</th>').join('')+'</tr></thead><tbody>'+s.rows.map(row=>'<tr>'+row.map(v=>'<td>'+e(v)+'</td>').join('')+'</tr>').join('')+'</tbody></table>':'<p>해당 조건으로 분류된 항목이 없습니다.</p>')+'</section>';}
 function body(m){return '<div class="report-content"><header><small>the주택 · 주택공급 디지털 상황판</small><h1>'+e(m.title)+'</h1><p>기준일 '+e(m.scope.as_of_date)+(m.scope.comparison_date?' · 보조 기준일 '+e(m.scope.comparison_date):'')+' · 기준연도 '+e(m.scope.year)+' · '+e([m.scope.region,m.scope.municipality].filter(Boolean).join(' ')||'선택 범위 전체')+'</p></header><section class="report-summary"><h2>Ⅰ. 실적 요약</h2>'+m.summary.map(s=>'<p>'+e(s)+'</p>').join('')+'</section>'+(m.meta.length?'<dl class="report-meta">'+m.meta.map(([k,v])=>'<div><dt>'+e(k)+'</dt><dd>'+e(v)+'</dd></div>').join('')+'</dl>':'')+'<h2>Ⅱ. '+(m.kind==='project'?'사업 단계별 추진현황':'상위 분류별 실적과 전망')+'</h2>'+m.charts.map(chartHtml).join('')+'<h2 class="report-risk-heading">Ⅲ. 지연·주의 사업 점검</h2>'+chartHtml(m.riskChart)+m.riskSections.map(tableHtml).join('')+m.sections.map(tableHtml).join('')+'<section class="report-method"><h2>집계 기준</h2>'+m.notes.map(n=>'<p>'+e(n)+'</p>').join('')+'</section></div>';}
 function chartMd(c){
  const out=['### '+md(c.title),'',c.note,''];
  if(c.type==='steps'){out.push('```mermaid','flowchart LR',...c.rows.map((r,i)=>'  S'+i+'["'+md(r.label+' · '+amount(r.current)+' · '+(r.date||'측정일 미확보')).replace(/"/g,'＂')+'"]'),'  S0 --> S1 --> S2 --> S3','  S2 --> S4','  S3 --> S5','  S4 --> S5','```','');}
  else if(c.series){for(const s of c.series){const known=c.rows.filter(r=>r[s.key]!=null);if(!known.length)continue;const axis=known.map(r=>'"'+md(r.label).replace(/"/g,'＂')+'"').join(', '),max=Math.max(1,...known.map(r=>r[s.key]));out.push('```mermaid','xychart-beta','  title "'+md(s.label)+'"','  x-axis ['+axis+']','  y-axis "'+c.unit+'" 0 --> '+max,'  '+(c.type==='trend'?'line':'bar')+' ['+known.map(r=>r[s.key]).join(', ')+']','```','');}}
  const headers=c.series?['구분',...c.series.map(s=>s.label)]:['단계','현재 측정량','측정일','목표량','목표일'];
  const rows=c.rows.map(r=>c.series?[r.label,...c.series.map(s=>r[s.key]==null?'미확보':Number(r[s.key]).toLocaleString('ko-KR')+c.unit)]:[r.label,amount(r.current),r.date||'미확보',amount(r.target),r.planDate||'미확보']);
  out.push(mdTable(headers,rows),'');return out.join('\n');
 }
 function mdTable(headers,rows){return rows.length?'| '+headers.map(md).join(' | ')+' |\n| '+headers.map(()=>'---').join(' | ')+' |\n'+rows.map(r=>'| '+r.map(md).join(' | ')+' |').join('\n'):'해당 조건으로 분류된 항목이 없습니다.';}
 function markdown(m){return ['# '+md(m.title),'','the주택 · 주택공급 디지털 상황판','',`기준일: ${md(m.scope.as_of_date)} · 기준연도: ${md(m.scope.year)}${m.scope.comparison_date?' · 보조 기준일: '+md(m.scope.comparison_date):''}`,'','## Ⅰ. 실적 요약','',...m.summary.map(v=>'- '+md(v)),'',...(m.meta.length?[mdTable(['사업 개요','내용'],m.meta),'']:[]),'## Ⅱ. '+(m.kind==='project'?'사업 단계별 추진현황':'상위 분류별 실적과 전망'),'','차트는 Mermaid 지원 뷰어에서 표시됩니다. 각 차트의 수치는 표로도 제공합니다.','',...m.charts.map(chartMd),'## Ⅲ. 지연·주의 사업 점검','',chartMd(m.riskChart),...[...m.riskSections,...m.sections].flatMap(s=>['### '+md(s.title),'',s.note,'',mdTable(s.headers,s.rows),'']),'## 집계 기준','',...m.notes.map(n=>'- '+md(n)),''].join('\n');}
 const style="@page{size:A4;margin:16mm}body{margin:0 auto;max-width:1050px;padding:24px}@media print{body{max-width:none;padding:0}}\n.report-content{color:#18344a;font:14px/1.65 system-ui,sans-serif;overflow-wrap:anywhere}.report-content h1{word-break:keep-all;font-size:26px;line-height:1.4;border-bottom:3px solid #194f7e;padding-bottom:16px}.report-content h2{font-size:20px;margin:28px 0 16px;color:#194f7e;break-after:avoid}.report-content h3{font-size:16px;break-after:avoid}.report-content .report-summary{padding:4px 22px 15px;border-left:5px solid #176d86;background:#f1f7fa}.report-content .report-summary p{margin:9px 0}.report-content .report-meta{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:24px 0}.report-content .report-meta>div{padding:10px;border-bottom:1px solid #d5e1e8}.report-content dt{font-size:12px;color:#647c8d}.report-content dd{margin:5px 0 0;font-weight:600}.report-content .report-figure{margin:20px 0 28px;border:1px solid #d8e3eb;border-radius:10px;padding:18px;background:white;break-inside:avoid}.report-content figcaption{font-size:17px;font-weight:700;line-height:1.5;margin:0 0 12px}.report-content .report-chart{display:block;width:100%;height:auto;overflow:visible}.report-content .report-legend{display:flex;gap:20px;flex-wrap:wrap;font-size:12px;margin-bottom:12px}.report-content .report-legend span{display:flex;align-items:center;gap:6px}.report-content .report-legend i{width:11px;height:11px;display:inline-block;border:1px solid #57768b}.report-content .report-note{font-size:12px;color:#546f83;margin:10px 0 0;line-height:1.7}.report-content table{width:100%;min-width:0;table-layout:fixed;border-collapse:collapse;font-size:12px}.report-content th,.report-content td{border:1px solid #d3dfeb;padding:9px;text-align:left;vertical-align:top;overflow-wrap:anywhere}.report-content th{background:#edf3f8}.report-content .report-section{margin:24px 0}.report-content .report-section .report-note{margin-bottom:12px}.report-content .report-section tr{break-inside:avoid}.report-content .report-section th:first-child{width:25%}.report-content .report-method{border-top:1px solid #d3dfeb;margin-top:28px;font-size:12px}.report-content .report-method h2{font-size:16px}.report-content .report-risk-heading{border-top:3px solid #b9cbd7;padding-top:22px}.report-content small{color:#5f7283}\n@media(max-width:600px){.report-content .report-meta{grid-template-columns:repeat(2,minmax(0,1fr))}.report-content .report-figure{padding:10px}.report-content .report-summary{padding:4px 12px 12px}.report-content .report-chart{min-width:560px}.report-content .report-figure{overflow-x:auto}.report-content table{font-size:11px}.report-content th,.report-content td{padding:5px}}\n@media print{.report-content{font-size:10.5pt;line-height:1.5}.report-content h1{word-break:keep-all;font-size:22pt}.report-content h2{font-size:16pt}.report-content .report-figure{overflow:visible;padding:12px;break-inside:avoid}.report-content .report-chart{min-width:0;width:100%}.report-content .report-risk-heading{break-before:page}.report-content th{print-color-adjust:exact;-webkit-print-color-adjust:exact}.report-content .report-legend,.report-content .report-note,.report-content table{font-size:9pt}.report-content thead{display:table-header-group}.report-content .report-meta{grid-template-columns:repeat(3,minmax(0,1fr))}.report-content p{orphans:3;widows:3}}\n";
 function html(m){return '<!doctype html><html lang="ko"><meta charset="utf-8"><title>'+e(m.title)+'</title><style>'+style+'</style><body>'+body(m)+'</body></html>';}
 return {model,markdown,html,body};
})();
