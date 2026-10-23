'use strict';
/* Read-only policy brief. Every export is rendered from one pinned model. */
const PolicyBriefReport = (() => {
 const appendixFactories=new WeakMap(),appendixCache=new WeakMap();
 const VERSION='HOME_POLICY_BRIEF_V1_20261023';
 const STAGES={BUSINESS:'사업화',APPROVAL:'인허가',CONSTRUCTION:'착공',SUPPLY:'공급·분양',COMPLETION:'준공',MOVE_IN:'입주'};
 const LATER={BUSINESS:['BUSINESS','APPROVAL','CONSTRUCTION','COMPLETION','SUPPLY','MOVE_IN'],APPROVAL:['APPROVAL','CONSTRUCTION','COMPLETION','SUPPLY','MOVE_IN'],CONSTRUCTION:['CONSTRUCTION','COMPLETION','MOVE_IN'],SUPPLY:['SUPPLY','MOVE_IN'],COMPLETION:['COMPLETION','MOVE_IN'],MOVE_IN:['MOVE_IN']};
 const TYPES={PUBLIC:'공공주택',PURCHASE_NEW:'신축매입주택',PRIVATE_RENEWAL:'민간 정비사업',OTHER_PRIVATE:'일반 민간주택',OTHER:'기타 공급유형',UNKNOWN:'유형 미확인·복합'};
 const esc=v=>String(v??'미확보').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const num=v=>Number.isFinite(v)?v.toLocaleString('ko-KR'):'미확보';
 const qty=v=>Number.isFinite(v)?num(v)+'호':'미확보';
 const sum=vs=>vs.some(Number.isFinite)?vs.filter(Number.isFinite).reduce((a,b)=>a+b,0):null;
 const max=vs=>vs.some(Number.isFinite)?Math.max(...vs.filter(Number.isFinite)):null;
 const unique=vs=>[...new Set(vs.filter(v=>v!=null&&v!==''))];
 const dayBefore=d=>new Date(Date.parse(d+'T00:00:00Z')-86400000).toISOString().slice(0,10);
 const addMonths=(d,n)=>{const v=new Date(d+'T00:00:00Z'),day=v.getUTCDate();v.setUTCDate(1);v.setUTCMonth(v.getUTCMonth()+n+1);v.setUTCDate(0);v.setUTCDate(Math.min(day,v.getUTCDate()));return v.toISOString().slice(0,10);};
 const cap=p=>Number.isFinite(p.units)?p.units:Infinity;
 const scopeName=p=>[p.region,p.municipality].filter(Boolean).join(' ');
 const type=p=>{const a=p.report_metadata?.supply_type;if(!a||a.status!=='CONFIRMED')return 'UNKNOWN';return a.code in TYPES?a.code:'OTHER';};
 const tenure=p=>{const t=p.report_metadata?.tenure||'';return type(p)==='PUBLIC'&&/분양/.test(t)?'공공분양':type(p)==='PUBLIC'&&/임대|행복주택/.test(t)?'공공임대':'기타·미확인';};
 const precisionDate=r=>{const d=r.source_date_label||r.event_date||r.due_date;if(!d)return '일정 미확보';if(r.source_date_label)return d;return r.precision==='MONTH'?d.slice(0,7):r.precision==='YEAR'?d.slice(0,4):r.precision==='QUARTER'?d.slice(0,4)+'년 '+Math.ceil(Number(d.slice(5,7))/3)+'분기':d;};
 const actual=e=>(e.status||'ACTUAL')==='ACTUAL'&&e.origin!=='PLANNED'&&Number.isFinite(e.units)&&e.units>=0&&/^\d{4}-\d{2}-\d{2}$/.test(e.event_date||'');
 function category(e,stage){
  if(e.stage!==stage)return 'SEQUENCE';
  const proof=e.field_provenance||{},rules=[proof.units?.rule,(proof.event_date||proof.date)?.rule].filter(Boolean);
  const accepted=new Set(['SOURCE_ACCEPTED','BEST_SOURCE_SELECTED','OFFICER_VERIFIED_SOURCE','VERIFIED_SOURCE_EVENT','MEASUREMENT_TO_TARGET']);
  if(e.inferred||rules.some(r=>!accepted.has(r)))return 'ESTIMATE';
  if(e.origin==='MANUAL')return 'ADOPTED';
  if(['SOURCE','LINKED_EVIDENCE'].includes(e.origin)&&e.review_status!=='REVIEW')return 'SOURCE';
  return 'REVIEW';
 }
 const CATEGORY={SOURCE:'원천 사건',ADOPTED:'담당자 채택',ESTIMATE:'단계 추정',SEQUENCE:'후행 도달 근거',REVIEW:'확인 필요'};
 let calculationCache=null;
 function contribution(p,stage,date){
  const key=stage+'|'+date;let cache=calculationCache?.get(p);if(cache?.has(key))return cache.get(key);
  const result=calculateContribution(p,stage,date);if(calculationCache){if(!cache){cache=new Map();calculationCache.set(p,cache);}cache.set(key,result);}return result;
 }
 function calculateContribution(p,stage,date){
  const events=(p.events||[]).filter(e=>actual(e)&&(LATER[stage]||[stage]).includes(e.stage)&&e.event_date<=date);
  const amounts={},sources=[];let high=0;
  for(const k of Object.keys(CATEGORY)){
   const list=events.filter(e=>category(e,stage)===k),value=max(list.map(e=>Math.min(cap(p),e.units)));
   amounts[k]=value==null?0:Math.max(0,value-high);high=Math.max(high,value??0);
   for(const e of list)sources.push({...e,classification:k});
  }
  return {project_id:p.id,value:events.length?high:null,composition:amounts,events:sources};
 }
 // Mirrors backend.policy_delivery_comparison._schedule_targets; managed
 // revisions win and a physical block's capacity is consumed only once.
 function schedules(p,stage){
  let rows=(p.schedules||[]).filter(r=>r.stage===stage&&r.status!=='RELEASED'&&(r.origin==='SOURCE'||r.managed_schedule)&&Number.isFinite(r.units)&&r.due_date);
  const managed=rows.filter(r=>r.managed_schedule);if(managed.length)rows=managed;
  if(!rows.length)return [];
  const latest=rows.reduce((a,b)=>((b.source_base_date||'')+'|'+(b.source_object_id||''))>((a.source_base_date||'')+'|'+(a.source_object_id||''))?b:a);
  rows=rows.filter(r=>r.source_object_id===latest.source_object_id);
  rows=[...new Map(rows.map(r=>[r.due_date+'|'+r.units,r])).values()].sort((a,b)=>a.due_date.localeCompare(b.due_date));
  let left=cap(p);return rows.flatMap(r=>{const units=Math.min(left,r.units);left-=units;return units>0?[{...r,units}]:[];});
 }
 const planAt=(p,k,date)=>sum(schedules(p,k).filter(s=>s.due_date<=date).map(s=>s.units));
 const reached=(p,k,date)=>contribution(p,k,date).value;
 const periodActual=(p,k,start,end)=>{const v=reached(p,k,end);return v==null?null:Math.max(0,v-(reached(p,k,dayBefore(start))??0));};
 const periodPlan=(p,k,start,end)=>sum(schedules(p,k).filter(s=>s.due_date>=start&&s.due_date<=end).map(s=>s.units));
 function comparisons(ps,date){return Object.fromEntries(Object.keys(STAGES).map(k=>{
  const dates=unique(ps.flatMap(p=>(p.events||[]).filter(e=>actual(e)&&LATER[k].includes(e.stage)&&e.event_date<=date).map(e=>e.event_date))).sort();
  const targets=unique(ps.flatMap(p=>schedules(p,k).map(s=>s.due_date))).sort();
  return [k,{actual_points:dates.map(d=>({date:d,units:sum(ps.map(p=>reached(p,k,d)))})),target_points:targets.map(d=>({date:d,units:sum(ps.map(p=>planAt(p,k,d)))}))}];
 }));}
 function forecast(ps,date,end,cmp){
  const comparisonsModel=cmp||comparisons(ps,date),out={};
  const flow={comparisons:comparisonsModel,asOf:date,dataAsOf:date};
  for(const k of Object.keys(STAGES))out[k]=k==='COMPLETION'?sum(ps.map(p=>max([reached(p,k,date),planAt(p,k,end)]))):end<=date?sum(ps.map(p=>reached(p,k,end))):PolicyStageFlow.projectedValue(flow,k,end).units;
  return out;
 }
 const rate=(a,t)=>a==null||!(t>0)?'산정 불가':(a/t*100).toFixed(1)+'%';
 // Hide unavailable rate columns in presentation tables; retain the raw calculation ledger.
 function visibleRateColumns(t){
  const keep=t.headers.map((h,i)=>({i,rate:/달성률|목표 대비|참고비/.test(h)})).filter(c=>!c.rate||t.rows.some(r=>typeof r[c.i]==='string'&&/^\d+(?:\.\d+)?%$/.test(r[c.i])));
  return {...t,headers:keep.map(c=>t.headers[c.i]),rows:t.rows.map(r=>keep.map(c=>c.rate&&r[c.i]==='산정 불가'?'—':r[c.i]))};
 }
 function build(input,options={}){calculationCache=new WeakMap();try{return calculate(input,options);}finally{calculationCache=null;}}
 function calculate(input,options={}){
  const c=JSON.parse(JSON.stringify(input)),d=c.data||{},s={...c.scope,...options},date=s.as_of_date,year=Number(date.slice(0,4)),yearStart=year+'-01-01',end=year+'-12-31';
  if(!/^\d{4}-\d{2}-\d{2}$/.test(date||'')||!Number.isFinite(Date.parse(date)))throw Error('보고 기준일을 확인하세요.');
  const start=s.period_start||yearStart,periodEnd=s.period_end||date;
  if(start>periodEnd||periodEnd>date)throw Error('보고기간은 기준일까지의 유효한 기간으로 지정하세요.');
  const all=d.cohorts||[],duplicateIds=all.filter((p,i)=>all.findIndex(q=>q.id===p.id)!==i).map(p=>p.id),ps=[...new Map(all.map(p=>[p.id,p])).values()].filter(p=>(!s.region||s.region===p.region)&&(!s.municipality_id||s.municipality_id===p.municipality_id)&&(!s.project_id||s.project_id===p.id));
  const cmp=comparisons(ps,date),expected=forecast(ps,date,end,cmp),contributions=[],metrics=[],checks=[];
  const section=(id,title)=>({id,title,paragraphs:[],tables:[]}),table=(section,id,title,headers,rows,note='')=>section.tables.push(visibleRateColumns({id,title,headers,rows,note}));
  const sections=['주택공급 정책 추진현황 총괄','공급유형별 착공 추진현황','주요 사업별 추진상황','분양·임대 공급 추진현황','준공·입주 추진현황 및 전망','정책·프로그램별 과제 이행현황','향후 주요 일정 및 중점 관리사항'].map((t,i)=>section('section-'+(i+1),(i+1)+'. '+t));
  const stages=Object.entries(STAGES).map(([k,label])=>{
   const ledger=ps.map(p=>({...contribution(p,k,date),stage:k,target:planAt(p,k,date),plans:schedules(p,k),source_ids:p.source_ids||[],source_revisions:p.report_metadata?.source_revisions||[]}));contributions.push(...ledger);
   const current=sum(ledger.map(r=>r.value)),target=sum(ledger.map(r=>r.target));
   const due=ledger.filter(r=>r.target!=null),paired=due.filter(r=>r.value!=null),missingGoal=ledger.filter(r=>r.value!=null&&!r.plans.length);
   const comparableActual=sum(paired.map(r=>r.value)),comparableTarget=sum(paired.map(r=>r.target)),complete=due.length===paired.length&&!missingGoal.length;
   const breakdown=Object.fromEntries(Object.keys(CATEGORY).map(key=>[key,sum(ledger.filter(r=>r.value!=null).map(r=>r.composition[key]))]));
   const row={stage:k,label,current,target,expected:expected[k],rate:complete?rate(sum(due.map(r=>r.value)),target):'산정 불가',comparison:{target_projects:due.length,known_projects:paired.length,unknown_projects:due.length-paired.length,missing_goal_projects:missingGoal.length,current:comparableActual,target:comparableTarget,rate:rate(comparableActual,comparableTarget)},remaining:!complete||current==null||target==null?null:Math.max(0,target-(sum(due.map(r=>r.value))??0)),composition:breakdown,known:ledger.filter(r=>r.value!=null).length,count:ps.length};
   for(const [suffix,value,status] of [['current',current,'REACHED'],['target',target,'PLAN'],['expected',expected[k],'PROJECTION']])metrics.push({metric_id:k+'.'+suffix,name:label+' '+suffix,value,unit:'호',period:{start:suffix==='expected'?date:null,end:suffix==='expected'?end:date},geography:[s.region,s.municipality].filter(Boolean).join(' ')||'정책 전체',supply_type:'ALL',status:value==null?'MISSING':status,precision:'UNIT',source_ids:unique(ledger.flatMap(r=>[...r.source_ids,...r.events.flatMap(e=>[e.source_id,e.source_entity_id,...Object.values(e.field_provenance||{}).flatMap(f=>[f.source_id,f.source_entity_id,f.source_revision_id,f.target_revision_id])]),...r.plans.flatMap(t=>[t.source_id,t.source_object_id])])),project_ids:ledger.filter(r=>suffix==='current'?r.value!=null:suffix==='target'?r.target!=null:r.value!=null||r.plans.some(t=>t.due_date<=end)).map(r=>r.project_id),excluded_project_ids:all.filter(p=>!ps.some(x=>x.id===p.id)).map(p=>p.id),formula_version:VERSION,as_of_date:date,ledger_path:'contributions[stage='+k+']'});
   const displayed=d.summary_cards?.[k]?.current_units;
   if((options.region??c.scope.region??'')===(c.scope.region||'')&&(options.municipality_id??c.scope.municipality_id??'')===(c.scope.municipality_id||'')&&displayed!==undefined)checks.push({name:label+' 화면 누계 대조',status:displayed===current?'PASS':'DIFFERENCE',expected:displayed,actual:current,reason:displayed===current?'동일 사업 원장·기준일':'범위·원장·날짜 조건 확인 필요'});
   const displayedExpected=d.summary_cards?.[k];
   if((options.region??c.scope.region??'')===(c.scope.region||'')&&(options.municipality_id??c.scope.municipality_id??'')===(c.scope.municipality_id||'')&&displayedExpected?.comparison_date===end)checks.push({name:label+' 연말 전망 대조',status:displayedExpected.expected_units===expected[k]?'PASS':'DIFFERENCE',expected:displayedExpected.expected_units,actual:expected[k],reason:'대시보드와 동일 산식·기준일·연말'});
   checks.push({name:label+' 구성합 대조',status:current===sum(Object.values(breakdown))?'PASS':'FAIL',expected:current,actual:sum(Object.values(breakdown))});
   return row;
  });
  const currentStage=p=>Object.keys(STAGES).slice().reverse().find(k=>reached(p,k,date)>0);
  const future=ps.flatMap(p=>Object.keys(STAGES).flatMap(k=>schedules(p,k).filter(r=>r.due_date>date).map(r=>({...r,project:p,stage:k})))).sort((a,b)=>a.due_date.localeCompare(b.due_date)||a.project.name.localeCompare(b.project.name,'ko'));
  const risks=ps.flatMap(p=>Object.keys(STAGES).flatMap(k=>{
   const target=planAt(p,k,date),a=reached(p,k,date),assessment=PolicyStageFlow.assessGap(target,a),due=schedules(p,k).filter(r=>r.due_date<=date).at(-1);
   return due&&target>0&&assessment.status!=='NORMAL'?[{project:p,stage:k,target,actual:a,...assessment,due}]:[];
  }));
  const core=stages.find(r=>r.stage==='CONSTRUCTION');
  const summary=[`□ ${date} 현재 ${d.plan?.name||s.name}의 관리대상 ${ps.length}개 사업 중 착공 누적 도달량은 ${qty(core.current)}${core.rate==='산정 불가'?'':', 도래 관리목표 달성률은 '+core.rate}입니다.`, `ㅇ 연말 누적 착공 예상은 ${qty(core.expected)}입니다. 계획 일정에 따른 관리 전망이며 실현 확률을 반영한 통계 예측이 아닙니다.`, `ㅇ 착공 수치 중 원천 사건 ${qty(core.composition.SOURCE)}, 담당자 채택 ${qty(core.composition.ADOPTED)}, 단계 추정 ${qty(core.composition.ESTIMATE)}, 후행 도달 근거 ${qty(core.composition.SEQUENCE)}입니다.`];
  const overviewHeaders=['단계','도래 관리목표','누적 도달량','달성률','잔여 목표','연말 누적 예상'];
  const overviewRows=stages.map(r=>[r.label,qty(r.target),qty(r.current),r.rate,qty(r.remaining),qty(r.expected)]);
  table(sections[0],'scope','정책 목표 및 관리 범위',['항목','내용'],[
   ['정책 / 발표일',(d.plan?.name||s.name)+' / '+(d.plan?.announced_at||'미확보')],['정책 전체 목표',qty(d.plan?.target_units)+' · '+(STAGES[d.plan?.metric]||'착공')],['목표기간',(d.plan?.period_start||'미확보')+' ~ '+(d.plan?.period_end||'미확보')],['선택 범위',[s.region,s.municipality].filter(Boolean).join(' ')||'정책 전체'],['연결 프로그램 / 관리사업',unique(ps.map(p=>p.program_id)).length+'개 / '+ps.length+'개'],['공급유형',unique(ps.map(p=>TYPES[type(p)])).join(' · ')],['후속 정책과의 관계','선택 정책의 원문 목표 유지 · 후속 정책 통합목표와 합산하지 않음']]);
  table(sections[0],'stages','단계별 추진실적',overviewHeaders,overviewRows,'누적 도달량은 이전 연도 포함. 단계 간 합산 금지. 달성률의 분모는 연결 사업의 기준일까지 도래한 관리목표이며 정책 전체 목표와 다릅니다. 미확보 사업은 합계에서 제외되므로 확보 범위를 함께 확인하세요.');
  table(sections[0],'composition','누적 도달량 구성',['단계',...Object.values(CATEGORY),'확보 사업'],stages.map(r=>[r.label,...Object.keys(CATEGORY).map(k=>qty(r.composition[k])),r.known+'/'+r.count]),'동일 사업에서 원천 사건 → 담당자 채택 → 추정 → 후행 근거 순으로 추가 도달분만 배분합니다. 후행 단계로 입주를 생성하지 않습니다.');
  table(sections[0],'comparable-coverage','목표·실적 비교 범위 및 확보 부분',['단계','도래 목표 사업','실적 미확보','목표 미확보 도달사업','비교가능 목표 / 도달','확보 부분 달성률'],stages.map(r=>[r.label,r.comparison.target_projects,r.comparison.unknown_projects,r.comparison.missing_goal_projects,qty(r.comparison.target)+' / '+qty(r.comparison.current),r.comparison.rate]),'전체 달성률은 동일 모집단의 목표·실적이 모두 확보된 경우에 계산합니다. 확보 부분 달성률을 전체 달성률로 확대하지 않습니다. 추정·담당자 채택값은 기존 관리 도달량으로 보존합니다.');
  const low=stages.filter(r=>r.rate!=='산정 불가'&&r.target>0&&r.current!=null).sort((a,b)=>a.current/a.target-b.current/b.target)[0];
  if(low)sections[0].paragraphs.push('□ 도래 목표 대비 달성률이 가장 낮은 단계는 '+low.label+'('+low.rate+')입니다.');
  sections[0].paragraphs.push('ㅇ 물량 변경·원인 분석은 변경 전후 판본이 연결된 경우에만 확정합니다. 이번 보고서에 과거 보고서 기준본이 연결되지 않은 경우 전월 대비 개선·악화 판단을 보류합니다.');
  const typeRows=Object.entries(TYPES).map(([code,label])=>{
   const group=ps.filter(p=>type(p)===code),f=forecast(group,date,end),actual=sum(group.map(p=>periodActual(p,'CONSTRUCTION',yearStart,date))),target=sum(group.map(p=>periodPlan(p,'CONSTRUCTION',yearStart,end))),baseline=sum(group.map(p=>reached(p,'CONSTRUCTION',dayBefore(yearStart))));
   return [label,qty(target),qty(actual),rate(actual,target),f.CONSTRUCTION==null?'미확보':qty(Math.max(0,f.CONSTRUCTION-(baseline??0))),'비교 기준본 미확보'];
  });
  const yearActual=sum(ps.map(p=>periodActual(p,'CONSTRUCTION',yearStart,date))),yearTarget=sum(ps.map(p=>periodPlan(p,'CONSTRUCTION',yearStart,end))),yearBaseline=sum(ps.map(p=>reached(p,'CONSTRUCTION',dayBefore(yearStart))));
  typeRows.push(['전체 (중복 제외)',qty(yearTarget),qty(yearActual),rate(yearActual,yearTarget),core.expected==null?'미확보':qty(Math.max(0,core.expected-(yearBaseline??0))),'비교 기준본 미확보']);
  table(sections[1],'starts-by-type','공급유형별 금년 착공',['구분','연간 관리목표','금년 도달 증가','확보값/목표 참고비','연말 증가 전망','전월 대비'],typeRows,'연간 증가는 같은 원장에서 연초 전 누적을 뺀 값입니다. 추정 포함 관리 도달량이며 실제 착공 사건과 구성표에서 구분합니다. 유형별 전망은 각 유형 내부 산식으로 계산하여 전체 전망과 단순 합산하지 않습니다.');
  table(sections[1],'type-map','공급유형 대응표',['원장 분류','보고서 분류','합산 원칙'],Object.entries(TYPES).map(([k,v])=>[k,v,k==='UNKNOWN'?'미확인·복합을 임의 배분하지 않음':'대표 사업별 1회']), '공공택지·3기 신도시는 공공주택의 세부 분류이며 상위 합계와 중복 가산하지 않습니다.');
  const publicProjects=ps.filter(p=>type(p)==='PUBLIC');
  table(sections[1],'public-starts','공공주택 착공 세부현황',['지역 / 사업·블록','시행기관','세부 유형','착공 도달량','확인 사건일','당초 / 변경 예정','확인 상태'],publicProjects.map(p=>{
   const direct=(p.events||[]).filter(e=>actual(e)&&e.stage==='CONSTRUCTION'&&e.event_date<=date).sort((a,b)=>a.event_date.localeCompare(b.event_date)).at(-1),plan=schedules(p,'CONSTRUCTION').at(-1);
   const sub=/고양창릉|인천계양|하남교산|남양주왕숙|부천대장/.test(p.name)?'3기 신도시':/도심/.test(p.program||'')?'도심 공급사업':/공공택지/.test(p.program||'')?'기타 공공택지':'기타 공공주택';
   return [scopeName(p)+' / '+p.name+' '+(p.block||''),p.developer||'미확보',sub,qty(reached(p,'CONSTRUCTION',date)),direct?precisionDate(direct):'실제 착공일 미확보',(plan?.baseline?.due_date||'미확보')+' / '+(plan?precisionDate(plan):'미확보'),direct?CATEGORY[category(direct,'CONSTRUCTION')]:'후행 근거 또는 미확보'];
  }),'추정된 날짜는 실제 착공 확인일로 해석하지 않습니다. 계약·사업승인만으로 착공을 생성하지 않습니다.');
  table(sections[1],'other-regions','신축매입·민간정비·일반민간 지역별',['지역','유형','금년 착공 증가','연말 누적 전망'],['서울특별시','경기도','인천광역시'].flatMap(r=>['PURCHASE_NEW','PRIVATE_RENEWAL','OTHER_PRIVATE'].map(k=>{const g=ps.filter(p=>p.region===r&&type(p)===k);return [r,TYPES[k],qty(sum(g.map(p=>periodActual(p,'CONSTRUCTION',yearStart,date)))),qty(forecast(g,date,end).CONSTRUCTION)];})));
  const pinned=new Set(options.pinned_ids||[]),major=ps.slice().sort((a,b)=>Number(pinned.has(b.id))-Number(pinned.has(a.id))||(b.units||0)-(a.units||0)||a.name.localeCompare(b.name,'ko')).slice(0,s.report_type==='detail'?20:8);
  table(sections[2],'major','주요 사업 현황',['사업명 / 지역','관리물량','현재 단계','주요 실적','다음 일정','상태'],major.map(p=>{const k=currentStage(p),n=future.find(f=>f.project.id===p.id),r=risks.find(r=>r.project.id===p.id);return [p.name+' / '+scopeName(p),qty(p.units),STAGES[k]||'단계 미확보',k?STAGES[k]+' '+qty(reached(p,k,date)):'미확보',n?precisionDate(n)+' '+STAGES[n.stage]:'미확보',r?r.label:pinned.has(p.id)?'담당자 고정 지정':'도래 목표 점검'];}),'담당자 고정 지정 → 공급규모 순. 전 사업 및 단계별 근거는 붙임 2·3. 최근 단계 변경·지연·향후 일정 사업은 아래 표와 7장에 별도 표시합니다.');
  const changes=ps.flatMap(p=>(p.events||[]).filter(e=>actual(e)&&e.event_date>=start&&e.event_date<=periodEnd).map(e=>[p.name,STAGES[e.stage]||e.stage,precisionDate(e),qty(e.units),CATEGORY[category(e,e.stage)],e.reason||e.basis||'원인 미확인']));
  table(sections[2],'changes','보고기간의 단계 사건',['사업','사건','일자','물량','확인 상태','등록 사유'],changes,'같은 사업의 반복 사건 물량을 합산하지 않습니다. 사건 등록 사유는 물량 증감 원인과 다를 수 있습니다. 분할·통합·귀속 변경의 전후 원장이 없으면 변경 원인을 확정하지 않습니다.');
  const qStart=q=>year+'-'+String((q-1)*3+1).padStart(2,'0')+'-01',qEnd=q=>new Date(Date.UTC(year,q*3,0)).toISOString().slice(0,10);
  table(sections[3],'quarter-supply','분기별 공급·모집',['구분','1분기','2분기','3분기','4분기','4분기 잔여 계획'],['공공분양','공공임대','기타·미확인'].map(t=>{const g=ps.filter(p=>tenure(p)===t);return [t,...[1,2,3,4].map(q=>qStart(q)>date?'미도래':qty(sum(g.map(p=>periodActual(p,'SUPPLY',qStart(q),qEnd(q)<date?qEnd(q):date))))),qty(sum(g.map(p=>{const planned=periodPlan(p,'SUPPLY',qStart(4)>date?qStart(4):addDay(date),end);return planned==null?null:Math.min(planned,Math.max(0,(planAt(p,'SUPPLY',end)??0)-(reached(p,'SUPPLY',date)??0)));})))];}),'분기 실적은 신규 누적 도달 증가분(채택·추정 포함)입니다. 정정·추가 모집은 동일 사업 누적 최대와 관리 한도 내에서 처리하며 원천 모집공고 확인량은 아래에 별도 표시합니다.');
  table(sections[3],'notice-supply','원천 사건으로 확인된 공급 구성',['구분','원천 사건·담당자 채택','추정·후행 근거','확인 필요'],['공공분양','공공임대','기타·미확인'].map(t=>{const g=ps.filter(p=>tenure(p)===t).map(p=>contribution(p,'SUPPLY',date));return [t,qty(sum(g.filter(r=>r.value!=null).map(r=>r.composition.SOURCE+r.composition.ADOPTED))),qty(sum(g.filter(r=>r.value!=null).map(r=>r.composition.ESTIMATE+r.composition.SEQUENCE))),qty(sum(g.filter(r=>r.value!=null).map(r=>r.composition.REVIEW)))];}),'누적 기준. 담당자 채택은 공식 모집공고 원문 확인과 동일한 뜻이 아닙니다. 원문·입력 규칙은 붙임 3에서 확인합니다.');
  table(sections[3],'planned-supply','주요 공급예정 사업',['지역','사업지구·블록','유형 / 단위','계획량','예정시기','공고·도달 확인'],future.filter(f=>f.stage==='SUPPLY'&&f.due_date<=end).map(f=>[scopeName(f.project),f.project.name+' '+(f.project.block||''),tenure(f.project)+' / '+(f.project.report_metadata?.unit||'호'),num(f.units),precisionDate(f),qty(reached(f.project,'SUPPLY',date))]),'전체 사업호수와 분양·임대 부분호수는 합산하지 않습니다. 오피스텔은 실 단위를 병기하고 기존 원장의 관리 호수 환산 여부를 확인 대상으로 표시합니다.');
  const regions=unique(ps.map(p=>p.region));
  table(sections[4],'completion','준공 예정 및 확인',['지역','연도','당초 예정','현재 예정','준공 도달','변경량'],regions.flatMap(r=>[year,year+1].map(y=>{const g=ps.filter(p=>p.region===r),rows=g.flatMap(p=>schedules(p,'COMPLETION').filter(t=>t.due_date.startsWith(String(y)))),now=sum(rows.map(t=>t.units)),baseline=rows.length&&rows.every(t=>t.baseline?.units!=null&&t.baseline?.due_date?.startsWith(String(y)))?sum(rows.map(t=>t.baseline.units)):null;return [r,y,qty(baseline),qty(now),y>year?'미도래':qty(sum(g.map(p=>periodActual(p,'COMPLETION',y+'-01-01',date)))),baseline==null||now==null?'비교 미확보':qty(now-baseline)];})),'당초 예정은 연결된 기준선이 있는 일정만 비교합니다. 기준선 누락 또는 연도 이동은 전후 판본 연결이 필요합니다. 준공과 입주는 별도 사건입니다.');
  table(sections[4],'move-in','입주 예정 및 시작 확인',['지역','유형','금년 입주예정','차년도 입주예정','입주 시작 도달','실입주'],regions.flatMap(r=>unique(ps.filter(p=>p.region===r).map(type)).map(k=>{const g=ps.filter(p=>p.region===r&&type(p)===k);return [r,TYPES[k],qty(sum(g.map(p=>periodPlan(p,'MOVE_IN',yearStart,end)))),qty(sum(g.map(p=>periodPlan(p,'MOVE_IN',(year+1)+'-01-01',(year+1)+'-12-31')))),qty(sum(g.map(p=>reached(p,'MOVE_IN',date)))),'실입주 자료 미확보'];})), '입주 시작일 확인 사업의 물량은 실제 거주 세대수와 다릅니다. 준공·사용승인으로 실입주를 자동 생성하지 않습니다.');
  const programRows=unique([...ps.map(p=>p.program_id),...Object.keys(d.report_programs||{})]).map(id=>{const g=ps.filter(p=>p.program_id===id),profile=d.report_programs?.[id],v=profile?.values||{},programTarget=s.municipality_id?null:s.region?v['region:'+s.region]:v.target_units;return [profile?.name||g[0]?.program||id,Number.isFinite(programTarget)?num(programTarget)+(v.unit||' · 단위 미확보'):'미확보',g.length,Object.entries(STAGES).map(([k,label])=>label+' '+qty(sum(g.map(p=>reached(p,k,date))))).join(' / '),v.unit==='호'&&STAGES[v.metric]&&v.period_start&&v.period_end&&date>=v.period_start?rate(sum(g.map(p=>periodActual(p,v.metric,v.period_start,date<v.period_end?date:v.period_end))),programTarget):'산정 불가',risks.filter(r=>g.some(p=>p.id===r.project.id)).length+'개 단계 점검'];});
  table(sections[5],'programs','프로그램별 추진현황',['프로그램','목표물량','관리사업','현재 단계별 성과','목표 대비','중점 관리'],programRows,'대표 관리사업의 승인된 주 귀속 프로그램 기준. 관련성만 있는 프로그램에는 전체 물량을 중복 가산하지 않습니다. 목표는 프로그램의 정의된 단계·기간·단위와 일치할 때만 비교합니다.');
  table(sections[5],'tasks','행정과제 이행현황',['구분','전체','완료','진행','지연·점검필요'],[['행정과제','미확보','미확보','미확보','미확보']],'과제별 완료 근거 원장이 연결되지 않았습니다. 물량사업 진행률로 대체하거나 공식 브리프의 과제 건수를 복사하지 않습니다.');
  sections[5].paragraphs.push('□ 프로그램별 주요 성과는 연결 사업의 단계 사건으로, 개선과제는 도래 목표 부족·미확보 및 예정 일정으로 확인합니다. 변경 사유가 없는 경우 원인을 추측하지 않습니다.');
  table(sections[6],'future','향후 1·3·6개월 주요 일정',['시기','지역·사업','예정 사건','물량','담당기관'],future.filter(f=>f.due_date<=addMonths(date,6)).map(f=>[f.due_date<=addMonths(date,1)?'1개월 내':f.due_date<=addMonths(date,3)?'1~3개월':'3~6개월',scopeName(f.project)+' / '+f.project.name,STAGES[f.stage]+' · '+precisionDate(f),qty(f.units),f.project.developer||'미확보']),'구간을 서로 겹치지 않게 표시합니다. 월·분기 일정의 관리 날짜는 정렬용이며 정확한 사건일로 확정하지 않습니다.');
  table(sections[6],'risks','지연·위험 및 실적 확인 필요',['사업 / 단계','상태','당초 / 변경 일정','경과일','원인','검토 필요사항'],risks.map(r=>[r.project.name+' / '+STAGES[r.stage],r.label,(r.due.baseline?.due_date||'당초 미확보')+' / '+precisionDate(r.due),r.due.precision&&r.due.precision!=='DAY'?'정밀도 확인':Math.max(0,Math.floor((Date.parse(date)-Date.parse(r.due.due_date))/86400000))+'일',r.due.delay_reason||'원인 미확인',r.actual==null?'실적 등록·사건 근거 확인':'부족 '+qty(r.gap)+' · 회복 일정 점검']), '기존 시스템 기준: 도래 목표 대비 부족률 2% 이상 지연, 0% 초과~2% 미만 주의. 미측정은 지연으로 단정하지 않습니다. 경과일은 현재 계획 기한으로부터의 기간이며 실제 지연일 확정값과 다릅니다. 기준선은 담당자 채택 기준선일 수 있습니다.');
  const quality=[['사업 동일성 확인 필요',duplicateIds.length?'중복 ID '+unique(duplicateIds).length+'건 제거':'선택 원장 대표 ID 중복 없음'],['정책 귀속 확인 필요',ps.filter(p=>p.mapping_status!=='CONFIRMED').length+'개 · 미연결 후보는 본 집계 대상 아님'],['공급물량 상충','상충 후보 원장 미연결 · 전체 현황 산정 불가'],['전체·부분 물량 관계 미확정',ps.filter(p=>p.report_metadata?.supply_type?.code==='MIXED').length+'개 복합 유형 · 별도 확인'],['원천 수집 또는 문서 추출 미완료','선택 원장 밖의 수집 대기 목록 미연결 · 없음으로 간주하지 않음'],['담당자 승인 대기',ps.filter(p=>p.mapping_status==='REVIEW').length+'개 · 선택 원장 범위'],['원천 확보·귀속 미확정 후보','미연결 후보 현황은 정책 확정 실적과 분리 · 후보 목록 미연결'],['단위 확인',ps.filter(p=>p.report_metadata?.unit==='실').length+'개 실 단위 사업 · 기존 관리 원장과 호 단위 환산 검토']];
  table(sections[6],'quality','데이터 확인 필요 사업',['확인 유형','확보 상태 / 조치'],quality,'확보된 원천의 미연결과 원천 자체 미확보는 별개의 상태입니다. 후보를 확정 실적으로 추가하지 않습니다.');
  checks.push({name:'대표 사업 ID 유일성',status:duplicateIds.length?'DEDUPLICATED':'PASS',actual:ps.length,reason:duplicateIds.length?'동일 ID 중복 제거; 상이한 ID는 임의 병합 안 함':'원장 대표 ID 유지'});
  const sources=unique(ps.flatMap(p=>[p.evidence_url,...(p.events||[]).map(e=>e.evidence_url),...(p.schedules||[]).map(e=>e.evidence_url)]));
  const createAppendices=()=>{
  const appendices=['공급유형별·지역별 상세 집계표','개별 사업 추진현황 명세','원천자료·집계산식 및 데이터 검증 결과'].map((t,i)=>section('appendix-'+(i+1),'붙임 '+(i+1)+'. '+t));
  table(appendices[0],'region-types','지역·유형별 누적',['시도·시군구 / 유형','사업 수',...Object.values(STAGES)],unique(ps.map(p=>scopeName(p)+' / '+TYPES[type(p)])).sort().map(key=>{const g=ps.filter(p=>scopeName(p)+' / '+TYPES[type(p)]===key);return [key,g.length,...Object.keys(STAGES).map(k=>qty(sum(g.map(p=>reached(p,k,date)))))];}));
  table(appendices[0],'period-types','보고기간 계획·도달 증가',['지역 / 유형','단계','기간 계획','기간 도달 증가'],unique(ps.map(p=>scopeName(p)+' / '+TYPES[type(p)])).sort().flatMap(key=>{const g=ps.filter(p=>scopeName(p)+' / '+TYPES[type(p)]===key);return Object.keys(STAGES).map(k=>[key,STAGES[k],qty(sum(g.map(p=>periodPlan(p,k,start,periodEnd)))),qty(sum(g.map(p=>periodActual(p,k,start,periodEnd))))]);}),'보고기간 '+start+' ~ '+periodEnd+' · 같은 기준본의 사건일별 증가이며 과거 보고서의 공표값과 비교한 증감이 아닙니다.');
  table(appendices[0],'annual-quarters','기준연도 연간·분기별 지역 집계',['지역','기간','단계','계획물량','도달 증가'],regions.flatMap(region=>{const g=ps.filter(p=>p.region===region);return [{label:year+'년',start:yearStart,end},...[1,2,3,4].map(q=>({label:year+'년 '+q+'분기',start:qStart(q),end:qEnd(q)}))].flatMap(period=>Object.entries(STAGES).map(([k,label])=>[region,period.label,label,qty(sum(g.map(p=>periodPlan(p,k,period.start,period.end)))),period.start>date?'미도래':qty(sum(g.map(p=>periodActual(p,k,period.start,period.end<date?period.end:date))))]));}),'계획은 해당 기간 전체, 도달 증가는 보고 기준일까지입니다. 연간과 분기는 같은 물량의 다른 묶음이며 합산하지 않습니다.');
  table(appendices[1],'project-list','전 관리사업 명세',['사업 / 대표 ID','정책 / 프로그램 ID','지역 / 시행기관 / 블록','유형 / 전체·관리물량','원천 ID / 검토상태'],ps.map(p=>[p.name+' / '+p.id,s.policy_id+' / '+(p.program_id||'미연결'),scopeName(p)+' / '+(p.developer||'미확보')+' / '+(p.block||'미확보'),TYPES[type(p)]+' / '+qty(p.planned_units)+' / '+qty(p.units),(p.source_ids||[]).join(' · ')+' / '+(p.mapping_status||'미확보')]));
  table(appendices[1],'project-events','사업별 단계·일정 명세',['사업 / 단계','누적 도달 / 사건일','현재 계획 / 당초 기준선','변경·채택 사유'],contributions.filter(r=>r.value!=null||r.plans.length).map(r=>{const p=ps.find(p=>p.id===r.project_id);return [p.name+' / '+STAGES[r.stage],qty(r.value)+' / '+unique(r.events.map(precisionDate)).join(' · '),r.plans.map(t=>precisionDate(t)+' '+qty(t.units)+' / '+(t.baseline?.due_date||'당초 미확보')).join(' · ')||'미확보',unique([...r.events.map(e=>e.reason||e.basis),...r.plans.map(t=>t.basis)]).join(' · ')||'사유 미확보'];}));
  table(appendices[2],'metric-manifest','핵심 지표 산출명세',['지표 ID','산출값','구분 / 기준일','포함 사업 수','산식 버전'],metrics.map(m=>[m.metric_id,qty(m.value),m.status+' / '+m.period.end,m.project_ids.length,m.formula_version]),'JSON에 포함·제외 사업 ID, 원천 ID·판본·해시, 적용 필터, 원문 URL, 채택·추정 근거와 입력 원장을 함께 제공합니다. HTML·CSV·PDF는 동일 계산 모델을 사용합니다.');
  table(appendices[2],'checks','이번 보고서 검증',['검증 항목','결과','기준값','계산값','차이 사유'],checks.map(r=>[r.name,r.status,num(r.expected),num(r.actual),r.reason||'구성합 일치 여부']));
  table(appendices[2],'formula','집계산식 및 한계',['항목','산식·적용 규칙'],[
   ['누적 도달량','사업별 min(관리 한도, 해당·허용 후행 사건 최대 물량)의 합. 공급만으로 착공을 생성하지 않음.'],['도래 관리목표','담당자 채택 일정 우선 → 최신 원천 판본 → 날짜·물량 중복 제거 → 사업 한도 내 기준일까지 계획량 합.'],['연말 누적 전망','사업화·인허가·착공·공급·입주: 대시보드 PolicyStageFlow.projectedValue 재사용. 단계별 max(현재 단계 물량, 목표 단계 물량) + 이후 목표 증가 − 다음 단계 목표 증가, 다시 누적. 준공: 사업별 max(현재 도달, 연말 계획)의 합.'],['연말 전망의 범위','단계별 부족분 기준이므로 전체 전망과 유형별 전망을 다시 더하지 않음. 실제 실현 확률을 의미하지 않음.'],['보고기간 증가','동일 인지 기준본에서 기간 말 누적 − 기간 시작 전 누적. 별도 과거 보고서와의 증감·원인 비교는 미연결.'],['과거 기준본','기준일 KST 종료 전 등록되고 그 시점 유효한 판본, 귀속 감사 이력 복원. 미래 수집 판본을 과거 보고에 사용하지 않음.'],['결측·0','자료 미확보는 null, 실제 기록된 0만 0. 일부 확보 합계는 구성표의 확보 사업 수와 함께 해석.'],['실입주','입주 시작 사업 물량과 거주 세대수를 구분. 실입주 자료 미확보.'],['검증 범위','공식 비교의 32/32 사업 대응·26/31 수량·10/10 통계·185개 판정은 서로 다른 과거 검증. 이번 보고서 전체 정확도나 56개 지표 전체 일치로 확대하지 않음.']]);
  table(appendices[2],'sources','원천·판본 추적',['사업','원천 / 판본','등록일 / 원천 기준일','원문 URL'],ps.flatMap(p=>(p.report_metadata?.source_revisions||[]).map(r=>[p.name,(r.id||'')+' / '+(r.source_revision_id||r.revision_no||'미확보'),(r.recorded_at||'미확보')+' / '+(r.base_date||'미확보'),r.evidence_url||'미확보'])));
   return appendices;
  };
  const generation=c.created_at||new Date().toISOString();
  const result={kind:'policy-brief',title:'주택공급 정책 추진현황 보고서',formula_version:VERSION,scope:{...s,year,period_start:start,period_end:periodEnd},policy:d.plan,generated_at:generation,latest_collection_at:d.latest_collection_at||maxDate(ps.flatMap(p=>(p.report_metadata?.source_revisions||[]).map(r=>r.last_collection_at))),latest_revision_at:maxDate(ps.flatMap(p=>(p.report_metadata?.source_revisions||[]).map(r=>r.recorded_at))),snapshot:d.report_snapshot||null,summary,stages,sections,appendices:[],appendix_count:3,metrics,contributions,checks,project_count:ps.length,program_count:unique(ps.map(p=>p.program_id)).length,sources,input:c};
  appendixFactories.set(result,createAppendices);return result;
 }
 function appendixModel(model){
  if(!appendixCache.has(model)){
   let factory=appendixFactories.get(model);
   if(!factory){const rebuilt=build(model.input,model.scope);factory=appendixFactories.get(rebuilt);}
   calculationCache=new WeakMap();try{appendixCache.set(model,factory());}finally{calculationCache=null;}
  }
  return {...model,kind:'policy-brief-appendices',title:model.title+' · 붙임 자료',sections:[],summary:[],appendices:appendixCache.get(model)};
 }
 function appendixBody(m){return '<div class="policy-brief"><header class="pb-cover"><p class="pb-kicker">the주택 · 정책관리 브리프 별책</p><h1>'+esc(m.title)+'</h1><h2>'+esc(m.policy?.name||m.scope.name)+'</h2><p>기준일 '+esc(m.scope.as_of_date)+' · 보고기간 '+esc(m.scope.period_start)+' ~ '+esc(m.scope.period_end)+'</p><p>'+esc([m.scope.region,m.scope.municipality].filter(Boolean).join(' ')||'정책 전체')+' · '+m.project_count+'개 사업</p><p>본문과 같은 기준 데이터로 생성한 붙임입니다. 다운로드 요청 시 최신값을 다시 조회하지 않습니다.</p><p class="pb-note">입력 기준본 SHA-256: '+esc(m.snapshot?.input_sha256||'입력 원장 동봉')+'</p><p class="pb-note">PDF가 필요한 경우 이 파일을 열고 브라우저 인쇄에서 PDF로 저장하세요.</p></header><nav class="pb-toc" aria-label="붙임 목차"><h2>붙임 목차</h2>'+m.appendices.map(s=>'<a href="#'+s.id+'">'+esc(s.title)+'</a>').join('')+'</nav>'+m.appendices.map(s=>sectionHtml(s)).join('')+'<footer>the주택 · '+esc(VERSION)+' · '+esc(m.scope.as_of_date)+' 기준</footer></div>';}
 const addDay=d=>new Date(Date.parse(d+'T00:00:00Z')+86400000).toISOString().slice(0,10);
 const displayStamp=v=>!v?'미확보':Number.isFinite(Date.parse(v))?new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul',dateStyle:'short',timeStyle:'medium'}).format(new Date(v))+' (한국시간)':v;
 const maxDate=vs=>vs.filter(Boolean).sort().at(-1)||null;
 function tableHtml(t,limit=Infinity){t=visibleRateColumns(t);return '<section class="pb-table" id="'+esc(t.id)+'"><h3>'+esc(t.title)+'</h3>'+(t.note?'<p class="pb-note">'+esc(t.note)+'</p>':'')+(t.rows.length?'<table><thead><tr>'+t.headers.map(h=>'<th>'+esc(h)+'</th>').join('')+'</tr></thead><tbody>'+t.rows.slice(0,limit).map(row=>'<tr>'+row.map((v,i)=>'<td class="'+(typeof v==='number'||/^[-\d,.]+(?:호|%|개|일)$/.test(v)?'pb-number':'')+'">'+(t.id==='sources'&&i===3&&/^https?:\/\//.test(v)?'<a href="'+esc(v)+'" target="_blank" rel="noopener">원문 열기 ↗</a>':esc(v))+'</td>').join('')+'</tr>').join('')+'</tbody></table>'+(t.rows.length>limit?'<p class="pb-note">주요 '+limit+'행 / 전체 '+t.rows.length+'행. 전 사업 단계·일정은 붙임 2, 전체 표는 CSV·JSON에서 확인할 수 있습니다.</p>':''):'<p class="pb-note">선택 원장·조건에 해당하는 행이 없습니다. 자료 부재가 실적 0을 뜻하지 않습니다.</p>')+'</section>';}
 function sectionHtml(s,limit=Infinity){return '<section class="pb-section" id="'+s.id+'"><h2>'+esc(s.title)+'</h2>'+s.paragraphs.map(t=>'<p>'+esc(t)+'</p>').join('')+s.tables.map(t=>tableHtml(t,['public-starts','changes','planned-supply','future','risks'].includes(t.id)?limit:Infinity)).join('')+'</section>';}
 function chart(m){const peak=Math.max(1,...m.stages.flatMap(r=>[r.target||0,r.current||0,r.expected||0]));return '<figure class="pb-chart"><figcaption>단계별 관리목표·도달량·연말 전망 <span>단위: 호 · 단계 간 합산 금지</span></figcaption><div class="pb-legend"><span>━ 도래 관리목표</span><span>━ 누적 도달량</span><span>┄ 연말 전망</span></div><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 330" role="img" aria-label="단계별 목표·도달량·전망 비교">'+m.stages.map((r,i)=>{const y=24+i*50;return '<text x="0" y="'+(y+16)+'">'+r.label+'</text>'+[['target','#a9cce7'],['current','#176d86'],['expected','#c0d4e0']].map(([key,color],j)=>'<rect x="85" y="'+(y+j*11)+'" width="'+((r[key]||0)/peak*500)+'" height="8" fill="'+color+'"'+(key==='expected'?' stroke="#59788b" stroke-dasharray="4 3"':'')+'/><text x="595" y="'+(y+j*11+8)+'" font-size="10">'+esc(qty(r[key]))+'</text>').join('');}).join('')+'</svg></figure>';}
 function body(m){if(m.kind==='policy-brief-appendices')return appendixBody(m);return '<div class="policy-brief"><header class="pb-cover"><p class="pb-kicker">the주택 · 정책관리 브리프</p><h1>'+esc(m.title)+'</h1><h2>'+esc(m.policy?.name||m.scope.name)+'</h2><dl>'+[['보고 기준일',m.scope.as_of_date],['보고기간',m.scope.period_start+' ~ '+m.scope.period_end],['적용 지역',[m.scope.region,m.scope.municipality].filter(Boolean).join(' ')||'정책 전체'],['집계대상',m.program_count+'개 프로그램 · '+m.project_count+'개 사업'],['데이터 최종 수집일',m.latest_collection_at?displayStamp(m.latest_collection_at):'수집 완료시각 미연결'],['최신 원천 판본 등록일',displayStamp(m.latest_revision_at)],['생성일 / 출처',m.generated_at+' / the주택']].map(([k,v])=>'<div><dt>'+esc(k)+'</dt><dd>'+esc(v)+'</dd></div>').join('')+'</dl></header><section class="pb-summary"><h2>핵심 요약</h2>'+m.summary.map(t=>'<p>'+esc(t)+'</p>').join('')+tableHtml({id:'summary',title:'목표·현재 도달량·전망',headers:['지표','도래 목표','현재 누적','달성률','연말 누적 전망'],rows:m.stages.map(r=>[r.label,qty(r.target),qty(r.current),r.rate,qty(r.expected)])})+'<p class="pb-note">목표·도달·전망은 서로 다른 지표입니다. 채택·추정 구성은 1장, 개별 사업과 원천은 붙임에서 확인합니다.</p></section><nav class="pb-toc" aria-label="보고서 목차"><h2>목차</h2>'+m.sections.map(s=>'<a href="#'+s.id+'">'+esc(s.title)+'</a>').join('')+'</nav><p class="pb-note">붙임 1~3은 별도 자료입니다. 보고서 화면의 ‘붙임 자료 생성·다운로드’에서 받을 수 있습니다.</p>'+chart(m)+m.sections.map(s=>sectionHtml(s,m.scope.report_type==='detail'?Infinity:12)).join('')+'<footer>the주택 · '+esc(VERSION)+' · '+esc(m.scope.as_of_date)+' 기준</footer></div>';}
 let cssText='';
 function html(m){return '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(m.title)+'</title>'+(cssText?'<style>'+cssText+'</style>':'<link rel="stylesheet" href="https://www.minslab.kr/poc/home/assets/policy-brief-report.css?v=20261023-wrap-v2">')+'</head><body>'+body(m)+'</body></html>';}
 function csv(m){const quote=v=>'"'+String(v??'').replace(/^[=+@\-\t\r]/,"'$&").replace(/"/g,'""')+'"';return '\uFEFF'+[['보고서',m.title,'기준일',m.scope.as_of_date,'기간',m.scope.period_start,m.scope.period_end],...[...m.sections,...m.appendices].flatMap(s=>s.tables.flatMap(t=>[[s.title,t.id,t.title],t.headers,...t.rows,[]]))].map(r=>r.map(quote).join(',')).join('\r\n');}
 function markdown(m){return ['# '+m.title,'',m.policy?.name,'기준일 '+m.scope.as_of_date,'',...m.summary,...[...m.sections,...m.appendices].flatMap(s=>['','## '+s.title,...s.paragraphs,...s.tables.flatMap(t=>['','### '+t.title,t.note,'| '+t.headers.join(' | ')+' |','| '+t.headers.map(()=>'---').join(' | ')+' |',...t.rows.map(r=>'| '+r.map(v=>String(v??'미확보').replace(/\|/g,'\\|').replace(/\n/g,' ')).join(' | ')+' |')])])].join('\n');}
 function download(content,type,name){const u=URL.createObjectURL(new Blob([content],{type})),a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),60000);}
 async function get(url){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),180000);try{for(let attempt=0;attempt<3;attempt++){const r=await fetch(url,{credentials:'same-origin',signal:controller.signal});if([502,503,504].includes(r.status)&&attempt<2){await new Promise(resolve=>setTimeout(resolve,1000*(attempt+1)));continue;}if(!r.ok)throw Error('보고서 조회 실패 (HTTP '+r.status+') · 같은 기준일로 다시 생성해 주세요.');return await r.json();}}catch(error){if(error.name==='AbortError')throw Error('기준일 판본 조회 대기시간을 초과했습니다. 같은 기준일로 다시 생성해 주세요. 최신값으로 대체하지 않았습니다.');throw error;}finally{clearTimeout(timer);}}
 async function load(scope){
  const key=scope.project_id?'project:'+scope.project_id:scope.municipality_id?'city:'+scope.municipality_id:scope.region?'region:'+scope.region:'policy';
  const url='/poc/home/api/policy-delivery/view?'+new URLSearchParams({as_of_date:scope.as_of_date,group:'policy',scope:key,report:'true'});
  const d=await get(url);if(d.status!=='READY')throw Error('해당 기준일의 정책 원장 미확보: '+(d.notice||d.status));
  const ps=(d.portfolio_cohorts||[]).filter(p=>(!scope.region||p.region===scope.region)&&(!scope.municipality_id||p.municipality_id===scope.municipality_id)&&(!scope.project_id||p.id===scope.project_id));
  const metrics=d.portfolio_comparisons?.[key]?.metrics||{},cmp=Object.fromEntries(Object.entries(metrics).map(([k,v])=>[k,v.tracking?{...v,...v.tracking,management_points:[]}:v]));
  const summary=PolicyStageFlow.summaryValues({asOf:scope.as_of_date,dataAsOf:d.as_of_date,year:Number(scope.as_of_date.slice(0,4)),comparisonDate:scope.as_of_date.slice(0,4)+'-12-31',comparisons:cmp,stages:d.stages});
  return ReportMD.clean({kind:'policy',scope:{...scope,data_as_of_date:d.as_of_date},created_at:new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul',dateStyle:'short',timeStyle:'medium'}).format(new Date())+' Asia/Seoul',data:{plan:d.plan,cohorts:ps,comparisons:cmp,summary_cards:summary,report_programs:d.report_programs,report_snapshot:{...d.report_snapshot,request_url:location.origin+url},issues:d.issues}});
 }
 async function open(){
  const context=await Policy907.reportContext(),scope={...context.scope},dialog=document.createElement('dialog');dialog.className='progress-report-dialog pb-dialog';dialog.setAttribute('aria-label','정책 추진현황 보고서');
  const cities=unique(context.data.cohorts.map(p=>p.municipality_id)).map(id=>context.data.cohorts.find(p=>p.municipality_id===id));
  const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul'}).format(new Date());
  dialog.innerHTML='<div class="progress-report-toolbar"><strong>정책 추진현황 보고서</strong><button data-pb-close>닫기</button></div><form class="pb-form"><label>대상 정책<select name="policy"><option>'+esc(context.data.plan.name)+'</option></select></label><label>지역 범위<select name="region"><option value="">정책 전체</option>'+['서울특별시','경기도','인천광역시'].map(r=>'<option '+(r===scope.region?'selected':'')+'>'+r+'</option>').join('')+'</select></label><label>시군구<select name="city"><option value="">시도 전체</option>'+cities.map(p=>'<option value="'+esc(p.municipality_id)+'" data-region="'+esc(p.region)+'" '+(p.municipality_id===scope.municipality_id?'selected':'')+'>'+esc(scopeName(p))+'</option>').join('')+'</select></label><label>보고 기준일<input name="date" type="date" value="'+esc(scope.as_of_date)+'" max="'+today+'" required></label><label>보고기간<select name="period"><option value="month">월간</option><option value="quarter">분기</option><option value="year" selected>연간</option><option value="custom">직접 지정</option></select></label><label>시작일<input name="start" type="date" value="'+scope.as_of_date.slice(0,4)+'-01-01" required></label><label>종료일<input name="end" type="date" value="'+scope.as_of_date+'" required></label><label>보고서 유형<select name="type"><option value="brief">기본 정책 브리프</option><option value="detail">정책관리 상세보고서</option></select></label><details class="pb-pins"><summary>중요 사업 고정 지정</summary><label>사업 검색<input type="search" name="search" placeholder="사업명 검색"></label><div>'+context.data.cohorts.slice().sort((a,b)=>b.name.localeCompare(a.name,'ko')).map(p=>'<label><input type="checkbox" name="pin" value="'+esc(p.id)+'">'+esc(p.name)+'</label>').join('')+'</div></details><button type="submit" class="button primary">보고서 생성</button></form><p class="pb-status" role="status">조건을 선택한 뒤 보고서를 생성하세요. 데이터와 승인 상태는 변경되지 않습니다.</p><div class="pb-exports" hidden><button data-pb-print>인쇄 / PDF 저장</button><button data-pb-html>HTML ↓</button><button data-pb-csv>본문 CSV ↓</button><button data-pb-json>산출근거 JSON ↓</button><button data-pb-md>본문 MD ↓</button><label>붙임 형식 <select data-pb-appendix-format aria-label="붙임 다운로드 형식"><option value="html">HTML · 인쇄/PDF 가능</option><option value="csv">상세 CSV</option><option value="json">산출근거 JSON</option><option value="md">Markdown</option></select></label><button data-pb-appendices>붙임 자료 생성·다운로드 ↓</button></div><article class="progress-report-document"></article>';
  document.body.append(dialog);dialog.querySelector('[data-pb-close]').onclick=()=>dialog.close();dialog.addEventListener('close',()=>dialog.remove());dialog.showModal();
  const form=dialog.querySelector('form'),status=dialog.querySelector('.pb-status'),output=dialog.querySelector('article'),exports=dialog.querySelector('.pb-exports');let model=null,inflight=false;
  function period(){const date=form.elements.date.value,y=date.slice(0,4),month=Number(date.slice(5,7)),mode=form.elements.period.value;form.elements.start.readOnly=form.elements.end.readOnly=mode!=='custom';if(mode!=='custom'){form.elements.end.value=date;form.elements.start.value=mode==='year'?y+'-01-01':mode==='month'?date.slice(0,7)+'-01':y+'-'+String(Math.floor((month-1)/3)*3+1).padStart(2,'0')+'-01';}}
  period();form.elements.period.onchange=period;form.elements.date.onchange=period;
  form.elements.region.onchange=()=>{form.elements.city.value='';for(const o of form.elements.city.options)o.hidden=!!o.value&&!!form.elements.region.value&&o.dataset.region!==form.elements.region.value;};
  form.elements.search.oninput=()=>{const q=form.elements.search.value.trim();for(const el of form.querySelectorAll('.pb-pins div label'))el.hidden=!el.textContent.includes(q);};
  form.addEventListener('change',()=>{if(model){exports.hidden=true;status.textContent='조건이 변경되었습니다. 보고서 생성 버튼을 눌러 새 기준으로 집계하세요.';}});
  form.onsubmit=async ev=>{ev.preventDefault();if(inflight||!form.reportValidity())return;inflight=true;exports.hidden=true;const button=form.querySelector('[type=submit]');button.disabled=true;status.textContent='기준일의 원천 판본과 사업별 집계 근거를 조회하고 있습니다. 과거 기준일의 첫 조회는 시간이 더 걸릴 수 있습니다…';
   const city=form.elements.city.selectedOptions[0],selected={...scope,project_id:'',as_of_date:form.elements.date.value,region:city.value?city.dataset.region:form.elements.region.value,municipality_id:city.value,municipality:city.value?city.textContent.replace(city.dataset.region+' ',''):'',period_start:form.elements.start.value,period_end:form.elements.end.value,report_type:form.elements.type.value,pinned_ids:[...form.querySelectorAll('[name=pin]:checked')].map(n=>n.value)};
   const controls=[...form.elements];controls.forEach(n=>n.disabled=true);
   try{if(selected.period_start>selected.period_end||selected.period_end>selected.as_of_date)throw Error('기간 시작·종료일과 보고 기준일을 확인하세요.');const c=await load(selected);model=build(c,selected);const raw=JSON.stringify(c);model.snapshot={...model.snapshot,input_sha256:Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw)))).map(v=>v.toString(16).padStart(2,'0')).join('')};if(!cssText){const r=await fetch('/poc/home/assets/policy-brief-report.css?v=20261023-wrap-v2');if(!r.ok)throw Error('인쇄 스타일 조회 실패');cssText=await r.text();}output.innerHTML=body(model);exports.hidden=false;const bad=model.checks.filter(c=>['FAIL','DIFFERENCE'].includes(c.status));status.textContent=model.project_count+'개 사업 · 본문 7개 장 생성. 붙임 3종은 다운로드 버튼을 누를 때 별도로 생성합니다. '+(bad.length?bad.length+'개 수치 차이가 있습니다. 별도 붙임 3에서 확인하세요.':'누적 도달량·구성합 검증 통과.');}catch(e){status.textContent=e.message;output.innerHTML='';model=null;}finally{inflight=false;controls.forEach(n=>n.disabled=false);period();}
  };
  const file=()=> 'the주택_정책추진현황_'+model.scope.as_of_date;
  dialog.querySelector('[data-pb-html]').onclick=()=>download(html(model),'text/html;charset=utf-8',file()+'.html');
  dialog.querySelector('[data-pb-csv]').onclick=()=>download(csv(model),'text/csv;charset=utf-8',file()+'.csv');
  dialog.querySelector('[data-pb-json]').onclick=()=>download(JSON.stringify(model,null,2),'application/json;charset=utf-8',file()+'.json');
  dialog.querySelector('[data-pb-md]').onclick=()=>download(markdown(model),'text/markdown;charset=utf-8',file()+'.md');
  dialog.querySelector('[data-pb-print]').onclick=()=>{const frame=document.createElement('iframe');frame.className='progress-report-print-frame';frame.title='정책 보고서 인쇄';frame.onload=()=>{frame.contentWindow.focus();frame.contentWindow.print();};frame.srcdoc=html(model);dialog.append(frame);};
  dialog.querySelector('[data-pb-appendices]').onclick=async()=>{
   if(!model||inflight)return;
   const pinned=model,format=dialog.querySelector('[data-pb-appendix-format]').value,controls=[...form.elements,...exports.querySelectorAll('button,select')];
   inflight=true;controls.forEach(n=>n.disabled=true);status.textContent='본문과 같은 기준 데이터로 붙임 3종을 생성하고 있습니다…';
   try{
    await new Promise(resolve=>setTimeout(resolve,0));
    const attachment=appendixModel(pinned),content=format==='html'?html(attachment):format==='csv'?csv(attachment):format==='md'?markdown(attachment):JSON.stringify(attachment,null,2);
    const mime={html:'text/html',csv:'text/csv',md:'text/markdown',json:'application/json'}[format];
    download(content,mime+';charset=utf-8',file()+'_붙임.'+format);
    status.textContent='붙임 3종을 별도 파일로 생성했습니다. 본문은 7개 장으로 유지됩니다.';
   }catch(error){status.textContent='붙임 생성 실패: '+error.message;}finally{inflight=false;controls.forEach(n=>n.disabled=false);period();}
  };
 }
 return {build,appendixModel,body,html,csv,markdown,open,load,contribution,schedules,comparisons,forecast,periodActual,precisionDate,setStyle:s=>{cssText=s;}};
})();
