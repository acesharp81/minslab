'use strict';
/* Project analysis and all exports use one immutable, dated input. */
const ProjectBriefReport = (() => {
 const VERSION='HOME_PROJECT_BRIEF_V1_20261023';
 const STAGES={BUSINESS:'사업화',APPROVAL:'인허가',CONSTRUCTION:'착공',COMPLETION:'준공',SUPPLY:'공급',MOVE_IN:'입주'};
 const BASES={first:'최초 유효 관리계획',previous:'이전 보고시점',adopted:'현재 채택 관리계획'};
 const CAT={SOURCE:'원천 사건',ADOPTED:'등록 채택',ESTIMATE:'추정',SEQUENCE:'후행 근거',REVIEW:'확인 필요'};
 const clone=v=>JSON.parse(JSON.stringify(v));
 const esc=v=>String(v??'미확보').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const qty=v=>Number.isFinite(v)?v.toLocaleString('ko-KR')+'호':'미확보';
 const sum=vs=>vs.some(Number.isFinite)?vs.filter(Number.isFinite).reduce((a,b)=>a+b,0):null;
 const unique=vs=>[...new Set(vs.filter(Boolean))];
 const day=v=>/^\d{4}-\d{2}-\d{2}$/.test(v||'')&&Number.isFinite(Date.parse(v))&&new Date(v+'T00:00:00Z').toISOString().slice(0,10)===v;
 const diff=(a,b)=>day(a)&&day(b)?Math.round((Date.parse(a)-Date.parse(b))/86400000):null;
 const fmt=r=>r?PolicyBriefReport.precisionDate({...r,precision:r.precision||r.date_precision,event_date:r.event_date||r.date})+([r.date_basis,r.date_kind,r.date_conversion].includes('OBSERVED_BY')?'까지 확인 · 발생일 미확보':''):'미확보';
 const exact=r=>r&&day(r.due_date||r.event_date||r.date)&&[r.precision,r.date_precision,r.source_date_precision].every(v=>!v||v==='DAY')&&(!r.source_date_label||day(r.source_date_label))&&!['OBSERVED_BY','MONTH_END','QUARTER_END','YEAR_END'].includes(r.date_conversion)&&r.date_kind!=='OBSERVED_BY'&&r.date_basis!=='OBSERVED_BY';
 const t=(id,title,headers,rows,note='')=>({id,title,headers,rows,note});
 const sec=(id,title,paragraphs,tables)=>({id,title,paragraphs,tables});
 const short=(v,n=230)=>{const s=display(v);return s.length>n?s.slice(0,n)+'… (전체는 별도 붙임)':s;};
 const reason=r=>r?.reason||r?.input_basis||r?.basis||'사유 미기록';
 const acceptedDateRules=new Set(['SOURCE_ACCEPTED','BEST_SOURCE_SELECTED','OFFICER_VERIFIED_SOURCE','VERIFIED_SOURCE_EVENT']);
 function estimatedDate(r){const proof=r.field_provenance?.event_date||r.field_provenance?.date;return proof?.rule?!acceptedDateRules.has(proof.rule):Boolean(r.inferred);}
 function eventRows(p,k,date){return (p.events||[]).filter(e=>e.stage===k&&(e.status||'ACTUAL')==='ACTUAL'&&e.origin!=='PLANNED'&&day(e.event_date)&&e.event_date<=date).sort((a,b)=>a.event_date.localeCompare(b.event_date));}
 function baseline(input,stage,mode){
  const p=input.data.cohort,plans=PolicyBriefReport.schedules(p,stage);
  if(mode==='previous')return input.previous?PolicyBriefReport.schedules(input.previous.data.cohort,stage):[];
  if(mode==='adopted')return plans.filter(r=>r.managed_schedule);
  // A stored adoption baseline is not the original statutory/official plan.
  const explicit=plans.filter(r=>r.baseline?.due_date).map(r=>({...r,...r.baseline,baseline_label:r.baseline.label||'최초 저장 관리계획',inferred:r.inferred,source_date_label:null}));
  if(explicit.length)return explicit;
  const rows=(input.data.histories||[]).filter(h=>h.kind==='execution_schedule').flatMap(h=>h.revisions.map(r=>({...r.values,recorded_at:r.recorded_at,revision_no:r.revision_no,entity_id:h.entity_id}))).filter(r=>r.stage===stage&&r.status!=='RELEASED'&&day(r.due_date)).sort((a,b)=>a.recorded_at.localeCompare(b.recorded_at));
  return rows.length?[{...rows[0],baseline_label:'최초 저장 관리계획 · 최초 공식계획 여부 미확인'}]:[];
 }
 function changes(input){
  const out=[],keys=['planned_units','supply_units','start_plan_date','start_actual_date','completion_plan_date','schedule_month','progress_pct','progress_date','units','due_date','status'];
  for(const h of input.data.histories||[]){
   const rs=h.revisions.slice().sort((a,b)=>a.revision_no-b.revision_no);
   for(let i=1;i<rs.length;i++){
    const a=rs[i-1],b=rs[i],before=a.values||{},after=b.values||{};
    for(const key of keys)if(JSON.stringify(before[key])!==JSON.stringify(after[key])&&(before[key]!=null||after[key]!=null))out.push({entity_id:h.entity_id,kind:h.kind,field:key,before:before[key]??null,after:after[key]??null,date:b.recorded_at,revision:b.revision_no,reason:reason(after),hash:b.payload_hash,classification:'동일 객체 판본 차이 · 공식 변경 여부 별도 확인'});
    if(h.kind==='project_profile'&&JSON.stringify(before)!==JSON.stringify(after))out.push({entity_id:h.entity_id,kind:h.kind,field:'관리값·단계·채택',before:before.last_changes||before.progress||before.overrides,after:after.last_changes||after.progress||after.overrides,date:b.recorded_at,revision:b.revision_no,reason:reason(after),hash:b.payload_hash,classification:'관리값 변경 · 공식 승인과 구분'});
   }
  }
  return out.sort((a,b)=>b.date.localeCompare(a.date));
 }
 function build(raw,options={}){
  const input=clone(raw),p=input.data?.cohort;
  if(!p)throw Error('선택 사업의 원장이 없습니다.');
  const scope={...input.scope,comparison:'first',report_type:'detail',focus:'overall',evidence_level:'key',supply_scope:'whole',...options};
  if(!day(scope.as_of_date)||scope.as_of_date!==input.scope.as_of_date)throw Error('기준일과 입력 판본이 일치하지 않습니다.');
  if(!BASES[scope.comparison])throw Error('비교 기준을 확인하세요.');
  if(scope.comparison==='previous'&&(!input.previous||input.previous.scope.as_of_date>=scope.as_of_date||input.previous.data.cohort.id!==p.id))throw Error('같은 대표사업의 이전 기준일 원장이 필요합니다.');
  const scopes=scopeOptions(input);if(!scopes.some(r=>r.value===scope.supply_scope&&!r.disabled))throw Error('검증된 포함관계가 없는 범위를 독립 집계할 수 없습니다.');
  const date=scope.as_of_date,d=input.data,projects=d.projects||[],evidence=d.evidence||[],allChanges=changes(input),limit=scope.report_type==='brief'?3:6;
  const allPlans=Object.keys(STAGES).flatMap(k=>PolicyBriefReport.schedules(p,k));
  const stages=Object.entries(STAGES).map(([stage,label])=>{
   const c=PolicyBriefReport.contribution(p,stage,date),plans=PolicyBriefReport.schedules(p,stage),events=eventRows(p,stage,date),bases=baseline(input,stage,scope.comparison);
   const event=events.at(-1),currentPlan=plans.find(r=>r.due_date>date)||plans.at(-1),base=bases.length===1?bases[0]:null;
   // Compare a source date only for the same quantity, stage and exact precision.
   const measured=events.filter(r=>!r.inferred&&!estimatedDate(r)&&exact(r)&&Number.isFinite(r.units)&&r.units===base?.units).at(-1);
   const comparable=!!(base&&plans.length===1&&exact(base)&&!base.inferred&&exact(plans[0])&&!plans[0].inferred&&plans[0].units===base.units);
   const variance=base&&!base.inferred&&exact(base)&&measured?diff(measured.event_date,base.due_date):comparable?diff(plans[0].due_date,base.due_date):null;
   const due=sum(plans.filter(r=>r.due_date<=date).map(r=>r.units)),target=sum(plans.map(r=>r.units));
   const estimate=c.composition.ESTIMATE+c.composition.SEQUENCE+c.composition.REVIEW;
   const status=c.value===0?'0호 기록 · 도달 미확인':c.value!=null?(estimate?'관리 도달 · 추정 포함':'도달 근거 확보'):due!=null?'기한 도래 · 실적 확인 필요':plans.length?'추진 예정':'판정 미확보';
   return {stage,label,current:c.value,composition:c.composition,events,plans,baseline:bases,target,due_target:due,status,variance,variance_kind:variance==null?'동일 범위·정밀도 비교 불가':measured?'원천 사건일 − 비교 계획일':'현재 계획일 − 비교 계획일',date:event?.event_date||null,date_label:fmt(event),planDate:currentPlan?.due_date||null,plan_label:fmt(currentPlan),estimated:estimate>0||!!event?.inferred,baseline_label:base?.baseline_label||BASES[scope.comparison]};
  });
  const quantities=projects.map(r=>({id:r.id,name:r.name,block:r.block,tenure:r.tenure,units:r.planned_units,raw_units:r.source_values?.planned_units??r.planned_units,source_id:r.source_id,basis:r.unit_basis||r.supply_type_basis,source_revision_no:r.revision_no}));
  const checks=[{id:'policy-ledger',status:p.ledger_scope==='PROJECT_ONLY'?'REVIEW':'PASS',detail:p.ledger_note||'정책 보고서와 동일한 대표사업 원장'}, {id:'identity',status:unique(p.source_ids||[]).length===(p.source_ids||[]).length?'PASS':'REVIEW',detail:'대표사업 '+p.id+' · 원천 ID '+unique(p.source_ids||[]).length+'개. 원천별 호수 단순 합산 금지.'},
   {id:'quantity-scope',status:new Set(quantities.map(r=>r.raw_units).filter(Number.isFinite)).size>1?'REVIEW':'PASS',detail:'원천 총량·부분물량 차이는 범위 차이 또는 상충으로 보존. 대표 관리량 '+qty(p.units)},
   {id:'human-approval',status:'NOT_ASSERTED',detail:'CONFIRMED 및 actor는 시스템 연결·등록 상태. 기관 담당자의 실제 결재 증빙으로 해석하지 않음.'},
   ...stages.map(r=>({id:r.stage+'.composition',status:r.current==null?'UNAVAILABLE':Object.values(r.composition).reduce((a,b)=>a+b,0)===r.current?'PASS':'FAIL',detail:r.label+' 구성합 = 관리 도달량. '+Object.entries(r.composition).filter(([,v])=>v>0).map(([k,v])=>CAT[k]+' '+qty(v)).join(' / ')})),
   {id:'baseline',status:stages.every(r=>r.baseline.length)?'PASS':'UNAVAILABLE',detail:'비교 기준 미확보 '+stages.filter(r=>!r.baseline.length).map(r=>r.label).join(', ')},
   {id:'actual-occupancy',status:stages.find(r=>r.stage==='MOVE_IN').current==null?'UNAVAILABLE':'AVAILABLE',detail:'입주계획·준공·모집공고를 실입주로 대체하지 않음.'}];
  const risks=stages.filter(r=>r.due_target!=null&&(r.current==null||r.current<r.due_target)).map(r=>({stage:r.stage,label:r.label,level:'확인 필요',basis:qty(r.due_target)+' 도래 목표 / '+qty(r.current)+' 관리 도달',effect:'실제 이행 및 후속 일정 영향 미확정',action:'동일 범위의 사건 증빙·미달 물량 및 회복일정 확인'}));
  if(projects.some(r=>(r.warnings||[]).includes('STALE_SOURCE')))risks.push({stage:'FRESHNESS',label:'원천 최신성',level:'확인 필요',basis:'기존 원장의 STALE_SOURCE 표시 · 원천 기준일 30일 초과 기준',effect:'현재 현황과 관측시점 차이 가능',action:'원천 기준일·공표일·수집일을 분리하여 최신 판본 확인'});
  if(checks.find(r=>r.id==='quantity-scope').status==='REVIEW')risks.push({stage:'SCOPE',label:'물량·집계범위',level:'확인 필요',basis:'연결 원천의 계획 호수 차이',effect:'일부 유형·전체 사업 혼합 가능성',action:'포함관계와 채택 사유·변경 판본 대조'});
  if(stages.some(r=>r.estimated))risks.push({stage:'ESTIMATE',label:'추정·선후관계',level:'검토',basis:'관리 도달량에 추정 또는 후행 도달 근거 포함',effect:'원천 사건일·해당 물량의 직접 검증 필요',action:'추정 사유를 유지하고 실제 사건 근거 추가 확인'});
  const latest=unique((p.events||[]).filter(r=>(r.status||'ACTUAL')==='ACTUAL'&&r.event_date<=date).map(r=>r.event_date)).sort().at(-1);
  const future=allPlans.filter(r=>r.due_date>date).sort((a,b)=>a.due_date.localeCompare(b.due_date));
  const current=stages.filter(r=>r.current>0).map(r=>r.label).join('·')||'단계 도달량 미확보';
  const type=p.report_metadata?.supply_type||{},mapping=p.report_metadata?.mapping||{};
  const sourceRefs=p.report_metadata?.source_revisions||[];
  const sourceFacts=(d.histories||[]).filter(h=>h.kind==='linked_evidence').flatMap(h=>{const revision=h.revisions.slice().sort((a,b)=>b.revision_no-a.revision_no)[0],v=revision?.values||{};if(v.verification_status!=='SOURCE_CONTENT_CHECKED'||v.matched_project_ids?.length!==1||!unique([p.id,...(p.source_ids||[])]).includes(v.matched_project_ids[0]))return [];return (v.facts||[]).map(f=>({...f,entity_id:h.entity_id,evidence_url:v.evidence_url,source_revision_no:revision.revision_no}));});
  const admin=evidence.filter(r=>['BUSINESS','APPROVAL'].includes(r.report_stage));
  const construction=evidence.filter(r=>r.report_stage==='CONSTRUCTION'&&r.kind==='ACTUAL'&&!r.inferred&&r.source_id!=='officer'&&r.origin!=='MANUAL'&&Number.isFinite(r.pct)&&r.date<=date).sort((a,b)=>(a.date||'').localeCompare(b.date||'')).at(-1);
  const location=d.locations?.[0],address=location?.address||projects.find(r=>r.address)?.address;
  const position=address||([p.latitude,p.longitude].every(Number.isFinite)?p.latitude+', '+p.longitude:null);
  const note='기한 도래·자료 부재만으로 실제 지연을 확정하지 않습니다. 변경 원인과 후속 영향은 연결된 근거가 없으면 미확보로 표시합니다.';
  const overview=t('basics','사업 기본정보',['구분','내용'],[['대표사업',p.name+' · '+p.id],['정책 / 프로그램',(d.plan.name||scope.policy_id||'미연계')+' / '+(p.program||'미연계')],['지역 / 블록',[p.region,p.municipality,p.block].filter(Boolean).join(' / ')],['시행자 / 시공자',(p.developer||'미확보')+' / '+(projects.find(r=>r.contractor)?.contractor||'미확보')],['관리 사업량 / 공급유형',qty(p.units)+' / '+(type.label||'미확인')+' / '+(p.report_metadata?.tenure||'유형 미확보')],['정책 합산 원장',p.ledger_note||'정책 원장과 동일 대표사업'],['정책 연결 근거',short(mapping.basis||'미확보',350)],['위치 근거',position?position+' · '+(location?.coordinate_basis||p.coordinate_basis||'위치 정밀도 미확인'):'주소·좌표 미확보']]);
  const stageTable=t('stages','단계별 관리 도달량과 근거 구성',['단계','전체 목표','관리 도달량','원천 / 채택','추정 / 후행 / 확인','상태'],stages.map(r=>[r.label,qty(r.target),qty(r.current),qty(r.composition.SOURCE)+' / '+qty(r.composition.ADOPTED),[r.composition.ESTIMATE,r.composition.SEQUENCE,r.composition.REVIEW].map(qty).join(' / '),r.status]),'단계 간 중복되는 누적량이므로 단계별 값을 합산하지 않습니다. 등록 채택은 기관 결재 확인과 다릅니다.');
  const scheduleTable=t('schedule','계획·실적 일정 비교',['단계','비교 계획','현재 관리계획','등록 사건일','차이·비교 제한'],stages.map(r=>[r.label,r.baseline.map(fmt).join(' / ')||'비교 기준 미확보',r.plans.map(fmt).join(' / ')||'미확보',r.date_label+(r.events.at(-1)&&estimatedDate(r.events.at(-1))?' (추정)':''),r.variance==null?'동일 범위·정밀도 비교 불가':(r.variance>0?'+':'')+r.variance+'일 · '+r.variance_kind]),'최초 유효 관리계획은 저장된 관리 기준선입니다. 최초 공식계획과 구분하며, 추정 일정·월/분기 자료·부분 물량에는 일 단위 지연을 계산하지 않습니다.');
  const shortChange=allChanges.slice(0,limit).map(r=>[r.date.slice(0,10),r.field,short(r.before,100),short(r.after,100),short(r.reason)]);
  const futureRows=[1,3,6].map(n=>{const end=addMonths(date,n),rows=future.filter(r=>r.due_date<=end);return ['향후 '+n+'개월',end,rows.map(r=>STAGES[r.stage]+' '+fmt(r)+' '+qty(r.units)).join(' / ')||'등록 일정 없음'];});
  futureRows.push(['연말',date.slice(0,4)+'-12-31',future.filter(r=>r.due_date<=date.slice(0,4)+'-12-31').map(r=>STAGES[r.stage]+' '+fmt(r)+' '+qty(r.units)).join(' / ')||'등록 일정 없음']);
  const assessment=risks.length?'관리 확인 '+risks.length+'건. 계획대로 진행 중인지 확정하려면 원천 사건과 비교 기준의 보완이 필요합니다.':'도래 목표의 관리 도달량에서 미달·미확보 항목은 발견되지 않았습니다. 공식 이행 판정은 사건 증빙 범위 내에서 확인해야 합니다.';
  const sections=[sec('project-1','1. 사업 개요 및 정책 연계현황',['□ 대표사업 ID와 기존 정책 원장의 포함관계를 기준으로 분석했습니다. 지구명이 비슷한 별도 블록을 새로 합치지 않습니다.'],[overview]),
   sec('project-2','2. 사업 단계별 추진현황',['□ '+current+'에 관리 도달량이 등록되어 있습니다. 일부 물량의 단계 도달은 사업 전체 완료를 뜻하지 않습니다.'],[stageTable]),
   sec('project-3','3. 사업 추진일정 및 계획 대비 분석',['□ 비교 기준: '+BASES[scope.comparison]+(input.previous?' ('+input.previous.scope.as_of_date+')':'')+'. '+note],[scheduleTable]),
   sec('project-4','4. 공급물량 및 주요 변경 이력',['□ 대표 관리물량 '+qty(p.units)+'. 연결 원천 '+projects.length+'개는 같은 사업의 근거이며 원천 호수의 합계가 사업 총량은 아닙니다.','ㅇ 원천 판본의 차이와 공식 변경 승인을 구분합니다. 전체 변경 사유는 별도 붙임 3에 보존합니다.'],[t('quantities','원천별 물량·범위',['원천','블록 / 유형','원천 계획량','채택 계획량','범위 근거'],quantities.slice(0,limit).map(r=>[r.source_id,[r.block,r.tenure].filter(Boolean).join(' / '),qty(r.raw_units),qty(r.units),short(r.basis||'범위 미확인')])),t('change-summary','최근 주요 변경',['등록일','항목','이전','이후','변경 사유'],shortChange),t('verified-source-changes','원문에서 확인된 변경·관측 근거',['관측·고시 시점','단계 / 근거 구분','확인 물량','원문 확인 내용'],sourceFacts.filter(r=>r.method==='AMENDED_APPROVED_STOCK').map(r=>[fmt(r),STAGES[r.stage]+' / 변경승인 후 총량',qty(r.units),short(r.basis,420)]),'이 표의 변경승인 총량은 해당 날짜의 신규 승인량 또는 최초 승인일이 아닙니다.')]),
   sec('project-5','5. 인허가·행정절차 추진현황',['□ 인허가, 사업계획 승인, 지구 지정은 각각의 원문 사건으로 확인해야 합니다. 후행 단계의 도달 추정은 해당 인허가 원문을 확보했다는 의미가 아닙니다.'],[t('administration','연결된 행정절차 근거',['단계','자료 종류','시점','사건·연결 근거'],admin.slice(0,limit).map(r=>[STAGES[r.report_stage]||r.report_stage,r.kind,fmt(r),short(r.basis||r.name)]))]),
   sec('project-6','6. 건설·분양·준공·입주 추진현황',['□ 실제 관측 공정률: '+(construction?construction.pct+'% · '+fmt(construction)+' · '+construction.source_id:'미확보')+'. 경과기간 또는 행정단계 수를 실제 공정률로 환산하지 않습니다.','ㅇ 모집·공급량은 계약량과 다릅니다. 준공 또는 입주예정은 실제 입주가 아닙니다.'],[t('delivery','건설 이후 일정·도달량',['단계','관리 도달량','등록 사건 시점','현재 계획','근거 구분'],stages.filter(r=>['CONSTRUCTION','SUPPLY','COMPLETION','MOVE_IN'].includes(r.stage)).map(r=>[r.label,qty(r.current),r.date_label,r.plan_label,r.status]))]),
   sec('project-7','7. 사업 위험요인 및 지연 영향 분석',['□ 위험 등급은 공식 지연 판정이 아닌 관리 확인 수준입니다. '+note],[t('risk','확인할 위험요인',['대상 / 수준','근거','영향','필요 조치'],risks.map(r=>[r.label+' / '+r.level,r.basis,r.effect,r.action]))]),
   sec('project-8','8. 향후 주요 일정 및 조치 필요사항',['□ 예정 일정은 등록된 계획의 정밀도와 범위를 유지합니다. 담당 기관·완료기한이 지정되지 않은 조치는 제안으로 구분합니다.'],[t('future','시기별 주요 계획',['기간','조회 종료일','계획 일정·물량'],futureRows),t('actions','조치 관리 제안',['조치','확인 대상','담당 / 기한','상태'],(risks.length?risks:[{action:'다음 계획의 사건 증빙 확인',label:future[0]?STAGES[future[0].stage]:'후속 계획'}]).slice(0,limit).map(r=>[r.action,r.label,'미지정 / 미확정','보고서 제안 · 공식 배정 아님']))]),
   sec('project-9','9. 종합평가 및 정책관리 의견',['□ '+assessment,'ㅇ 가장 최근 등록 변경: '+(allChanges[0]?allChanges[0].date.slice(0,10)+' · '+short(allChanges[0].reason):'비교 가능한 변경 이력 미확보')+'.','ㅇ 우선 확인사항: '+(risks.map(r=>r.label).join(', ')||'후속 계획의 최신 증빙 확보')+'. 원인·회복일정·실제 기관 승인 여부는 근거 확인 후 판단합니다.'],[])];
  const summary=[...(p.ledger_note?[p.ledger_note]:[]),'관리 사업량 '+qty(p.units)+' · '+(type.label||'유형 미확인')+' · '+(p.block||'블록 미확보'),current+' · 최근 등록 사건일 '+(latest||'미확보')+' (추정 포함 가능)',future[0]?'다음 등록 계획: '+STAGES[future[0].stage]+' '+fmt(future[0])+' · '+qty(future[0].units):'향후 등록 계획 미확보',assessment];
  const metrics=stages.flatMap(r=>[{metric_id:r.stage+'.current',value:r.current,formula:'정책 원장 동일 사업의 유효 사건·선후관계 기여 최대량, 대표 관리량 상한',composition:r.composition,as_of_date:date,evidence:r.events},{metric_id:r.stage+'.schedule_difference',value:r.variance,formula:r.variance_kind,baseline:r.baseline,as_of_date:date}]);
  return {kind:'project-brief',version:VERSION,title:'개별 주택공급사업 추진현황 분석보고서',project:p.name,project_id:p.id,scope,summary,sections,appendices:[],appendix_count:4,stages,risks,checks,metrics,changes:allChanges,quantities,source_facts:sourceFacts,source_refs:sourceRefs,input,snapshot:{...input.snapshot,formula_version:VERSION},generated_at:options.generated_at||new Date().toISOString()};
 }
 function display(v){if(v==null)return '미확보';return typeof v==='object'?JSON.stringify(v):String(v);}
 function addMonths(date,n){const d=new Date(date+'T00:00:00Z'),day=d.getUTCDate();d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()+n+1);d.setUTCDate(0);d.setUTCDate(Math.min(day,d.getUTCDate()));return d.toISOString().slice(0,10);}
 function scopeOptions(input){const p=input.data.cohort,ps=input.data.projects||[],all=ps.length&&ps.every(r=>r.planned_units===p.units&&r.tenure===p.report_metadata?.tenure);return [{value:'whole',label:'사업 전체 분석 · 집계는 대표 관리범위'},{value:'block',label:p.block?'블록 '+p.block+' · 같은 대표 관리범위':'블록별 독립 명세 미확보',disabled:!p.block},{value:'type',label:all&&p.report_metadata?.tenure?p.report_metadata.tenure+' · 동일 단일 유형 범위':'공급유형별 독립 집계 미확보',disabled:!all||!p.report_metadata?.tenure||/확인|미확|복합/.test(p.report_metadata.tenure)}];}
 const appendixCache=new WeakMap();
 function appendixModel(m){
  if(!appendixCache.has(m)){
   const d=m.input.data,p=d.cohort;
   const sources=(d.evidence||[]).map(r=>[r.source_entity_id||r.source_id,r.name||r.source_id,STAGES[r.report_stage]||r.report_stage,r.evidence_url||'',r.kind,fmt(r),qty(r.units??r.source_units),reason(r),r.source_revision_no??'미연결']);
   const revisions=(d.histories||[]).flatMap(h=>h.revisions.map(r=>[h.entity_id,h.kind,r.revision_no,r.recorded_at,r.base_date,r.payload_hash,reason(r.values)]));
   const events=(p.events||[]).map(r=>[STAGES[r.stage]||r.stage,r.status||'ACTUAL',fmt(r),qty(r.units),r.inferred?'추정':r.origin,reason(r),r.actor||'미기록']);
   const parts=m.quantities.map(r=>[r.id,r.name,r.block,r.tenure,qty(r.raw_units),qty(r.units),r.basis||'포함관계 별도 확인']);
   const edits=m.changes.map(r=>[r.entity_id,r.date,r.field,display(r.before),display(r.after),r.reason,r.revision,r.hash]);
   const mapping=(d.mapping_history||[]).flatMap(h=>h.history.map(r=>[h.project_id,r.recorded_at,r.action,display(r.before),display(r.after),r.after?.basis||r.after?.reason||'사유 미기록']));
   const checks=m.checks.map(r=>[r.id,r.status,r.detail]);
   appendixCache.set(m,[sec('project-appendix-1','붙임 1. 사업 관련 원천자료 및 행정사건 이력',['본문과 동일한 입력 기준본으로 생성했습니다. 수집 시각·원천 기준일·사건일은 서로 다른 날짜입니다.'],[t('sources','연결 원천자료',['원천 ID','자료명','단계','원문 URL','자료 종류','시점','물량','근거·사유','판본'],sources),t('events','등록 사건',['단계','원장 상태','사건 시점','물량','출처 구분','등록 사유','등록 주체 표기'],events),t('revisions','원천·관리 판본',['객체 ID','종류','판본','등록 시각','원천 기준일','SHA-256','사유'],revisions)]),
    sec('project-appendix-2','붙임 2. 블록·공급유형별 물량 상세',['원천별 행은 합계 대상이 아닙니다. 대표사업 '+p.id+'에 연결된 증빙이며 부분·전체·중복 여부는 기존 채택 근거로 판단합니다.'],[t('parts','연결 원천·부분범위',['원천 사업 ID','명칭','블록','유형','원천 계획량','채택 계획량','물량 근거'],parts),t('all-schedules','모든 등록 계획',['단계','시점','물량','출처','원천 객체','근거'],(p.schedules||[]).map(r=>[STAGES[r.stage],fmt(r),qty(r.units),r.origin,r.source_object_id||r.scope_id,reason(r)]))]),
    sec('project-appendix-3','붙임 3. 일정 변경 및 물량 변경 명세',['동일 저장 객체의 이전·이후 값과 변경 사유를 보존합니다. 판본 차이를 공식 변경 승인으로 단정하지 않습니다.'],[t('edits','판본별 변경',['객체 ID','등록 시각','항목','이전','이후','사유','판본','SHA-256'],edits),t('mapping','정책·프로그램 연결 이력',['사업 ID','등록 시각','작업','이전','이후','근거·사유'],mapping),t('source-facts','원문 검증 사실',['원천 객체','시점·정밀도','단계','종류','물량','검토 내용','판본'],(m.source_facts||[]).map(r=>[r.entity_id,fmt(r),STAGES[r.stage],r.method||r.kind,qty(r.units),r.basis,r.source_revision_no]))]),
    sec('project-appendix-4','붙임 4. 데이터 정합성 및 검증 결과',['기관 결재 증빙은 별도로 확인해야 합니다. 미확보 값은 0으로 치환하지 않았습니다.'],[t('checks','검증 결과',['검증 ID','결과','설명'],checks),t('metrics','수치 산출근거',['지표 ID','값','산식','기준일'],m.metrics.map(r=>[r.metric_id,r.value,r.formula,r.as_of_date])),t('snapshot','재현 정보',['항목','내용'],[['보고서 ID',m.report_id],['생성 시각',m.generated_at],['생성 주체',m.generated_by||'현재 브라우저 사용자 · 인증 이름 미연결'],['저장 위치',m.file_location||'다운로드 JSON'],['계산 버전',m.version],['입력 SHA-256',m.snapshot.input_sha256],['선택 범위',m.scope.supply_scope],['인지 기준',m.snapshot.knowledge_rule]])])]);
  }
  return {...m,kind:'project-brief-appendices',title:m.title+' · 별도 붙임',summary:[],sections:[],appendices:appendixCache.get(m)};
 }
 let cssText='';
 function graphics(m){
  const p=m.input.data.cohort,rows=m.stages.map(r=>({...r,date:r.date?fmt(r.events.at(-1)):null,planDate:r.plan_label==='미확보'?null:r.plan_label,status:r.current!=null?'MEASURED':r.due_target!=null?'UNKNOWN':r.target!=null?'UPCOMING':'UNKNOWN'}));
  const selected={...p,schedules:m.stages.flatMap(r=>r.plans)};
  const timeline=ProgressReport.stageSchedule([selected],m.scope.as_of_date);
  timeline.note+=' 월·분기 원천은 원장에 보관된 축 배치용 날짜이며, 실제 날짜 정밀도는 일정 비교표와 붙임을 따릅니다.';
  return '<section class="pj-graphics" aria-label="사업 진행 그래프">'+ProgressReport.chartHtml({type:'steps',title:'사업화부터 입주까지 단계별 진행',rows,note:'각 단계의 관리 도달량과 목표를 함께 표시합니다. 추정 포함 여부를 구분하며 공급은 준공 전·후에 병행할 수 있습니다.'})+ProgressReport.scheduleHtml(timeline)+'</section>';
 }
 function body(m){const appendix=m.kind==='project-brief-appendices',detail=m.scope.report_type==='detail',focus={overall:'전체 추진현황',schedule:'일정·지연',quantity:'물량·변경'}[m.scope.focus];
  return '<div class="policy-brief project-brief"><header class="pb-cover"><p class="pb-kicker">the주택 · 사업관리 분석 '+(appendix?'별책':'보고서')+'</p><h1>'+esc(m.title)+'</h1><h2>'+esc(m.project)+'</h2><dl>'+[['보고 기준일',m.scope.as_of_date],['비교 기준',BASES[m.scope.comparison]],['분석 범위',scopeOptions(m.input).find(r=>r.value===m.scope.supply_scope)?.label],['분석 관점',focus],['대표사업 ID',m.project_id],['원천 최종 수집',unique((m.source_refs||[]).map(r=>r.last_collection_at)).sort().at(-1)||'완료시각 미연결'],['생성 시각',m.generated_at]].map(([k,v])=>'<div><dt>'+esc(k)+'</dt><dd>'+esc(v)+'</dd></div>').join('')+'</dl></header>'+(appendix?'<p class="pb-note">본문과 같은 기준 데이터에서 요청 시 별도로 생성한 붙임 4종입니다. 입력 SHA-256: '+esc(m.snapshot.input_sha256)+'</p>':'<section class="pb-summary"><h2>핵심 요약</h2>'+m.summary.map(s=>'<p>'+esc(s)+'</p>').join('')+'</section><p class="pb-note">붙임 1~4는 본문에 포함하지 않습니다. 화면 위의 ‘붙임 생성·다운로드’에서 별도로 받을 수 있습니다.</p>'+graphics(m)+'<nav class="pb-toc" aria-label="보고서 목차">'+m.sections.map(s=>'<a href="#'+s.id+'">'+esc(s.title)+'</a>').join('')+'<p class="pj-focus">분석 관점: '+esc(focus)+' · '+(m.scope.focus==='schedule'?'3·7·8장에서 일정 차이와 확인 조치를 중점 확인합니다.':m.scope.focus==='quantity'?'4장에서 물량·범위 차이와 변경 사유를 중점 확인합니다.':'단계·물량·일정과 근거를 함께 확인합니다.')+'</p>')+[...m.sections,...m.appendices].map(s=>PolicyBriefReport.sectionHtml(detail||appendix?s:{...s,tables:s.tables.map(t=>({...t,rows:t.rows.slice(0,4),note:[t.note,t.rows.length>4?'요약본은 주요 4행 / 전체 '+t.rows.length+'행을 표시합니다. 전체 표는 본문 CSV·JSON 또는 상세분석보고서에서 확인하세요.':''].filter(Boolean).join(' ')}))})).join('')+'<footer>'+esc(m.version)+' · '+esc(m.report_id||'미저장')+' · 입력 SHA-256 '+esc(m.snapshot.input_sha256||'JSON 입력 원장 참조')+'<br>공식 기관 승인보고서가 아닌 저장 원장 기반 분석입니다.</footer></div>';
 }
 function html(m){return '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(m.project)+' 추진현황</title><style>'+cssText+'</style></head><body>'+body(m)+'</body></html>';}
 const db=()=>new Promise((resolve,reject)=>{const r=indexedDB.open('the-jutaek-project-reports',1);r.onupgradeneeded=()=>r.result.createObjectStore('reports',{keyPath:'report_id'});r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});
 async function history(mode,value){const database=await db();try{return await new Promise((resolve,reject)=>{const tx=database.transaction('reports',mode==='put'?'readwrite':'readonly'),store=tx.objectStore('reports'),r=mode==='put'?store.put(value):mode==='get'?store.get(value):store.getAll();let result;r.onsuccess=()=>result=r.result;tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(tx.error);});}finally{database.close();}}
 async function load(id,date){const url='/poc/home/api/project-brief/'+encodeURIComponent(id)+'?'+new URLSearchParams({as_of_date:date}),deadline=Date.now()+240000;do{const value=await PolicyBriefReport.get(url);if(value.status!=='PENDING')return value;await new Promise(resolve=>setTimeout(resolve,2000));}while(Date.now()<deadline);throw Error('과거 기준일 보고서 준비가 계속되고 있습니다. 잠시 후 같은 기준일로 다시 생성하세요. 최신값으로 대체하지 않았습니다.');}
 async function open(){
  const selected=document.getElementById('pjt-project')?.value;if(!selected)throw Error('사업 조회를 먼저 완료하세요.');
  const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul'}).format(new Date()),dialog=document.createElement('dialog');dialog.className='progress-report-dialog pb-dialog pj-dialog';dialog.setAttribute('aria-label','사업 추진현황 분석보고서');
  const catalogue=await PolicyBriefReport.get('/poc/home/api/project-workspace');
  dialog.innerHTML='<div class="progress-report-toolbar"><strong>사업 추진현황 분석보고서</strong><button data-close>닫기</button></div><form class="pb-form"><label>사업명·대표 ID 검색<input name="search" type="search" placeholder="사업명 또는 ID"></label><label class="pj-project-select">대상 사업<select name="project">'+catalogue.items.slice().sort((a,b)=>b.name.localeCompare(a.name,'ko',{numeric:true})).map(p=>'<option value="'+esc(p.id)+'" '+(p.id===selected?'selected':'')+'>'+esc(p.name)+' · '+esc(p.id)+'</option>').join('')+'</select></label><label>보고 기준일<input name="date" type="date" value="'+today+'" max="'+today+'" required></label><label>비교 기준<select name="comparison">'+Object.entries(BASES).map(([v,l])=>'<option value="'+v+'">'+l+'</option>').join('')+'</select></label><label>이전 보고 기준일<input name="previous" type="date" max="'+today+'" disabled></label><label>분석 범위<select name="supply_scope"><option value="whole">사업 전체 분석 · 집계는 대표 관리범위</option></select></label><label>보고서 유형<select name="type"><option value="detail">상세분석보고서</option><option value="brief">요약보고서</option></select></label><label>분석 관점<select name="focus"><option value="overall">전체 추진현황</option><option value="schedule">일정·지연</option><option value="quantity">물량·변경</option></select></label><label>근거 표시<select name="evidence"><option value="key">핵심 근거</option><option value="all">전체 증빙 · 별도 붙임</option></select></label><button class="button primary" type="submit">보고서 생성</button></form><p class="pb-status" role="status">두 진행 그래프를 유지한 9개 장의 보고서를 생성합니다. 붙임 4종은 요청할 때 별도로 생성됩니다.</p><details class="pj-history"><summary>이 브라우저의 보고서 생성이력</summary><p>입력 기준본·산식 버전·생성 시각을 이 브라우저에 보관합니다. 공유·장기 보관은 JSON을 다운로드하세요.</p><div data-history></div></details><div class="pb-exports" hidden><button data-export="print">인쇄 / PDF 저장</button><button data-export="html">본문 HTML ↓</button><button data-export="csv">본문 CSV ↓</button><button data-export="json">산출근거 JSON ↓</button><label>붙임 형식 <select data-appendix-format><option value="html">HTML · 인쇄/PDF</option><option value="csv">CSV</option><option value="json">JSON</option></select></label><button data-appendix>붙임 생성·다운로드 ↓</button></div><article class="progress-report-document"></article>';
  document.body.append(dialog);dialog.showModal();dialog.querySelector('[data-close]').onclick=()=>dialog.close();dialog.onclose=()=>dialog.remove();
  const form=dialog.querySelector('form'),status=dialog.querySelector('.pb-status'),output=dialog.querySelector('article'),exports=dialog.querySelector('.pb-exports');let model=null,busy=false;
  async function refreshHistory(){try{const rs=(await history('list')).sort((a,b)=>b.generated_at.localeCompare(a.generated_at));dialog.querySelector('[data-history]').innerHTML=rs.slice(0,20).map(r=>'<button data-restore="'+esc(r.report_id)+'">'+esc(r.project)+' · 기준 '+esc(r.scope.as_of_date)+' · '+esc(r.generated_at.slice(0,16))+'</button>').join('')||'저장된 보고서가 없습니다.';}catch(e){dialog.querySelector('[data-history]').textContent='브라우저 저장소를 사용할 수 없습니다. JSON 파일로 보관하세요.';}}
  const locked=value=>{busy=value;for(const c of [...form.elements,...exports.querySelectorAll('button,select')])c.disabled=value;form.elements.previous.disabled=value||form.elements.comparison.value!=='previous';form.elements.previous.required=form.elements.comparison.value==='previous';};
  form.elements.search.oninput=()=>{const q=form.elements.search.value.toLowerCase();for(const o of form.elements.project.options)o.hidden=!o.textContent.toLowerCase().includes(q);};
  form.elements.comparison.onchange=()=>{form.elements.previous.disabled=form.elements.comparison.value!=='previous';form.elements.previous.required=form.elements.comparison.value==='previous';};
  form.addEventListener('change',()=>{exports.hidden=true;status.textContent='조건이 변경되었습니다. 보고서를 다시 생성하세요.';});
  form.elements.project.onchange=()=>{form.elements.supply_scope.innerHTML='<option value="whole">사업 전체 분석 · 집계는 대표 관리범위</option>';};
  form.onsubmit=async ev=>{ev.preventDefault();if(busy||!form.reportValidity())return;const opts={as_of_date:form.elements.date.value,comparison:form.elements.comparison.value,supply_scope:form.elements.supply_scope.value,report_type:form.elements.type.value,focus:form.elements.focus.value,evidence_level:form.elements.evidence.value},id=form.elements.project.value,previous=form.elements.previous.value;
   if(opts.comparison==='previous'&&(!previous||previous>=opts.as_of_date)){status.textContent='이전 보고 기준일은 현재 보고 기준일보다 앞서야 합니다.';return;}
   locked(true);exports.hidden=true;status.textContent='같은 기준일의 정책 원장·사업 판본·변경 사유를 조회하고 있습니다…';
   try{const input=await load(id,opts.as_of_date);if(opts.comparison==='previous')input.previous=await load(id,previous);model=build(input,opts);model.report_id=crypto.randomUUID();model.generated_by='현재 브라우저 사용자 · 인증 이름 미연결';model.file_location='이 브라우저 IndexedDB / the-jutaek-project-reports / '+model.report_id;model.snapshot.input_sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(input))))).map(v=>v.toString(16).padStart(2,'0')).join('');
    if(!cssText){const responses=await Promise.all(['/poc/home/assets/policy-brief-report.css?v=20261023-wrap-v2','/poc/home/assets/project-brief-report.css?v=20261023-v1'].map(u=>fetch(u)));if(responses.some(r=>!r.ok))throw Error('보고서 인쇄 스타일을 불러오지 못했습니다.');cssText=(await Promise.all(responses.map(r=>r.text()))).join('\n');}
    output.innerHTML=body(model);exports.hidden=false;form.elements.supply_scope.innerHTML=scopeOptions(input).map(r=>'<option value="'+r.value+'" '+(r.disabled?'disabled':'')+' '+(r.value===opts.supply_scope?'selected':'')+'>'+esc(r.label)+'</option>').join('');
    let saved=true;try{await history('put',model);await refreshHistory();}catch(e){saved=false;}
    status.textContent='진행 그래프 2개 · 본문 9개 장 생성 완료. 붙임 4종은 별도 버튼에서 생성합니다. '+(saved?'입력 기준본을 이 브라우저에 보관했습니다.':'브라우저 보관 실패 · JSON을 다운로드해 보관하세요.')+(opts.evidence_level==='all'?' 전체 증빙은 붙임 1~4에 수록됩니다.':'');
   }catch(e){model=null;output.innerHTML='';status.textContent=e.message;}finally{locked(false);}
  };
  dialog.querySelector('[data-history]').onclick=async e=>{const button=e.target.closest('[data-restore]');if(!button||busy)return;locked(true);try{const old=await history('get',button.dataset.restore);if(!old)throw Error('저장된 보고서를 찾을 수 없습니다. 생성이력을 다시 확인하세요.');if(old.version!==VERSION)throw Error('계산 버전이 달라 저장본을 현재 산식으로 다시 해석하지 않습니다. 기존 JSON을 확인하세요.');if(!cssText){const rs=await Promise.all(['/poc/home/assets/policy-brief-report.css?v=20261023-wrap-v2','/poc/home/assets/project-brief-report.css?v=20261023-v1'].map(u=>fetch(u)));if(rs.some(r=>!r.ok))throw Error('인쇄 스타일 조회 실패');cssText=(await Promise.all(rs.map(r=>r.text()))).join('\n');}model=old;const restoredId=old.scope.requested_project_id||old.project_id;if(![...form.elements.project.options].some(o=>o.value===restoredId))form.elements.project.add(new Option(old.project+' · '+restoredId,restoredId));form.elements.search.value='';for(const o of form.elements.project.options)o.hidden=false;form.elements.project.value=restoredId;form.elements.date.value=old.scope.as_of_date;form.elements.comparison.value=old.scope.comparison;form.elements.previous.value=old.input.previous?.scope.as_of_date||'';form.elements.type.value=old.scope.report_type;form.elements.focus.value=old.scope.focus;form.elements.evidence.value=old.scope.evidence_level;form.elements.supply_scope.innerHTML=scopeOptions(old.input).map(r=>'<option value="'+r.value+'" '+(r.disabled?'disabled':'')+' '+(r.value===old.scope.supply_scope?'selected':'')+'>'+esc(r.label)+'</option>').join('');output.innerHTML=body(old);exports.hidden=false;status.textContent='저장 보고서 복원 · '+old.project+' · 기준일 '+old.scope.as_of_date+' · 저장된 입력으로 표시합니다.';}catch(e){status.textContent=e.message;}finally{locked(false);}};
  function save(m,format){const filename='the주택_사업추진현황_'+m.project.replace(/[^\p{L}\p{N}._-]+/gu,'_').slice(0,50)+'_'+m.scope.as_of_date+(m.kind.endsWith('appendices')?'_붙임':'');if(format==='print'){const frame=document.createElement('iframe');frame.className='progress-report-print-frame';frame.title='사업 보고서 인쇄';frame.onload=()=>{frame.contentWindow.focus();frame.contentWindow.print();};frame.srcdoc=html(m);dialog.append(frame);return;}PolicyBriefReport.download(format==='html'?html(m):format==='csv'?PolicyBriefReport.csv(m):JSON.stringify(m,null,2),{html:'text/html',csv:'text/csv',json:'application/json'}[format]+';charset=utf-8',filename+'.'+format);}
  for(const b of exports.querySelectorAll('[data-export]'))b.onclick=()=>{if(model&&!busy)save(model,b.dataset.export);};
  exports.querySelector('[data-appendix]').onclick=async()=>{if(!model||busy)return;const pinned=model,format=exports.querySelector('select').value;locked(true);status.textContent='본문과 동일한 입력으로 붙임 4종을 별도 생성합니다…';try{await new Promise(r=>setTimeout(r,0));save(appendixModel(pinned),format);status.textContent='붙임 4종을 별도 파일로 생성했습니다. 본문과 입력 SHA-256이 같습니다.';}catch(e){status.textContent='붙임 생성 실패: '+e.message;}finally{locked(false);}};
  await refreshHistory();
 }
 return {build,appendixModel,body,html,open,load,scopeOptions,changes,setStyle:s=>{cssText=s;}};
})();
