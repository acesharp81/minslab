'use strict';
/* One target ledger backs both the timeline and the thematic map. */
const Policy907=(()=>{
  const ID='POL_2025_0907',colors={POLICY:'#718096',BUSINESS:'#a66b00',APPROVAL:'#0072b2',CONSTRUCTION:'#d55e00',SUPPLY:'#00856a',MOVE_IN:'#7a3e9d',UNKNOWN:'#dce5ed'};
  let data=null,pending=null,stamp='',year=null,city='',region='',stage='SUPPLY',metric='SUPPLY',zoom=1,projectId='',full=true,flowWindow='11',axisUnit='month',fullAxis=false,programId='',programRows=[];
  const fmt=v=>v==null?'미확보':num(v)+'호',safe=v=>esc(v),current=()=>Number((data?.as_of_date||$('as-of').value).slice(0,4));
  const isProgram=()=>state.view==='program-progress';
  const active=()=>['policy-progress','program-progress'].includes(state.view);
  const program=()=>programRows.find(p=>p.id===programId);
  const detailHost=()=>$(isProgram()?'program-progress-detail':'policy-report-detail');
  const portfolio=()=>!full, allRows=()=>{const list=portfolio()?(data?.portfolio_cohorts||data?.cohorts||[]):(data?.cohorts||[]);return isProgram()?list.filter(c=>c.program_id===programId):list;};
  const rows=()=>allRows().filter(c=>(!city||c.municipality_id===city)&&(!region||c.region===region)&&(!projectId||c.id===projectId))||[];
  const cutoff=()=>year===current()?data.as_of_date:year+'-12-31';
  const amount=(items,k)=>items.reduce((a,c)=>a+(c.parts?.[k]||0),0);
  function stateAt(items,when){
    const future=when>data.as_of_date,result={};
    for(const key of Object.keys(colors))result[key]=0;
    for(const c of items){
      const events=c.events.filter(e=>e.status!=='DELAYED'&&e.event_date<= (future?data.as_of_date:when));
      if(future)for(const s of c.schedules)if(s.units!=null&&s.stage!=='MOVE_IN'&&s.due_date>data.as_of_date&&s.due_date<=when)events.push({...s,event_date:s.due_date,origin:'PLANNED'});
      let supply=Math.min(c.units,Math.max(0,...events.filter(e=>e.stage==='SUPPLY').map(e=>e.units??c.units)));
      const entry=Math.min(c.units,Math.max(0,...events.filter(e=>e.stage==='MOVE_IN'&&e.origin!=='PLANNED').map(e=>e.units??c.units)));
      supply=Math.max(supply,entry);result.MOVE_IN+=entry;result.SUPPLY+=supply-entry;let assigned=supply;
      for(const k of ['CONSTRUCTION','APPROVAL','BUSINESS']){
        const reached=Math.min(c.units,Math.max(0,...events.filter(e=>e.stage===k).map(e=>e.units??c.units)));
        const amount=Math.max(0,reached-assigned);result[k]+=amount;assigned+=amount;
      }
      result.UNKNOWN+=c.units-assigned;
    }
    return result;
  }
  function reached(items,key,when){
    if(key==='POLICY')return items.reduce((a,c)=>a+(c.planned_units??0),0);
    const t=stateAt(items,when);
    // Stages on the map are cumulative reached quantities. The stacked flow stays exclusive.
    if(key==='SUPPLY')return t.SUPPLY+t.MOVE_IN;
    if(key==='MOVE_IN')return t.MOVE_IN;
    return items.reduce((sum,c)=>{
      const events=c.events.filter(e=>e.stage===key&&e.status!=='DELAYED'&&e.event_date<= (when>data.as_of_date?data.as_of_date:when));
      if(when>data.as_of_date)events.push(...c.schedules.filter(e=>e.stage===key&&e.units!=null&&e.due_date>data.as_of_date&&e.due_date<=when));
      return sum+Math.min(c.units,Math.max(0,...events.map(e=>e.units??c.units)));
    },0);
  }
  function snapshot(when){
    if(!isProgram()&&!city&&!region&&!projectId&&full)return data.snapshots.find(p=>p.date===when)||data.snapshots.filter(p=>p.date<=when).at(-1)||data.current;
    const totals=stateAt(rows(),when),p=program()?.profile;if(isProgram()&&!city&&!region&&!projectId&&p?.unit==='호'&&p.target_units!=null)totals.POLICY=Math.max(0,p.target_units-Object.values(totals).reduce((a,b)=>a+b,0));
    return {date:when,totals,forecast:when>data.as_of_date};
  }
  function macroSummary(){const last=data.regional_start_months?.at(-1);return last?'<div class="d907-macro"><small>수도권 누적 착공 · '+last.month+'까지 공식 지역 통계</small><b>'+fmt(last.cumulative_units)+'</b><span>전체 목표 대비 '+(last.cumulative_units/data.target_units*100).toFixed(2)+'% · 사업별 식별 물량과 별도 대조</span></div>':'';}
  const pencil=(kind,id)=>!state.admin?'':'<button type="button" class="pw-pencil" data-d907-edit data-edit-kind="'+kind+'" data-edit-id="'+safe(id)+'" aria-label="'+(kind==='program'?'프로그램':kind==='region'?'지역':'정책')+' 목표 편집" title="목표와 관련 정보 편집"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 16-1 5 5-1L20 8l-4-4Z M14 6l4 4" fill="none" stroke="currentColor" stroke-width="2"/></svg></button>';
  function programPlanSummary(){
    if(!isProgram())return '';const m=data.program_assessments?.[programId];if(!m)return '';
    return '<div class="pgi-public-plan"><small>'+safe(m.target_kind_label)+' · '+safe(m.case)+'</small><div><span>연결 사업 전체 계획 <b>'+fmt(m.capacity_units)+'</b></span><span>같은 단계·기간 계획 <b>'+fmt(m.period_plan_units)+'</b></span><span>계획 차이 <b>'+fmt(m.plan_gap_units)+'</b></span></div><small>귀속 검토 '+m.review_project_count+' · 물량 미확보 '+m.missing_quantity_count+' · 일정 미확보 '+m.missing_schedule_count+' · 계획 차이는 지연 실적과 별도</small></div>';
  }
  function summary(){
    const plan=data.plan,is=isProgram(),r=program(),profile=is?r?.profile:null,period=(profile?.period_start||plan.period_start).slice(0,4)+'–'+(profile?.period_end||plan.period_end).slice(0,4)+'년';
    const units=is?(profile?.target_units??null):data.target_units;
    const themes={'서울특별시':'노후 임대·공공청사·유휴부지 재정비와 재개발·재건축으로 도심 공급 확대. 서울 유휴부지 즉시 개발 4천 호 포함.', '경기도':'3기 신도시 등 공공택지 조기화와 LH 직접 시행, 노후계획도시 정비. 과천지구는 2029년 착공 추진.', '인천광역시':'수도권 공공택지 공급 확대·조기화 정책 적용. 인천 단독 테마별 물량은 원문에서 분리되지 않아 개별 배정 목표 확인 필요.'};
    const regions=is?[...new Set([...allRows().map(c=>c.region),...(r?.source_profile?.geography||[])])]:['서울특별시','경기도','인천광역시'];
    $('policy-report-summary').innerHTML='<div class="d907-summary pd-overview"><small>'+(is?'9.7 정책 · 프로그램 개요':'정책 개요 · 발표 '+safe(plan.announced_at))+'</small>'+'<h3>'+safe(is?r?.name||'연결 프로그램 없음':plan.name||'9·7 주택공급 확대방안')+(state.admin?(is?' <button type="button" class="button primary mapping-info-edit program" data-program-information>✎ 프로그램정보수정</button>':' <button type="button" class="button primary mapping-info-edit policy" data-policy-information>✎ 정책정보수정</button>'):'')+'</h3>'+((is?profile?.overview:plan.overview)?'<p class="pi-summary-overview">'+safe(is?profile.overview:plan.overview)+'</p>':'')+'<div class="pd-main-target"><span>'+(is?'프로그램 목표 · '+({CONSTRUCTION:'착공',SUPPLY:'공급·모집',BUSINESS:'사업화',APPROVAL:'인허가',COMPLETION:'준공',MOVE_IN:'입주',CAPACITY:'전체 규모·개소'}[profile?.metric]||'기준 미입력'):'수도권 신규 착공 목표')+'</span>'+pencil(is?'program':'policy',is?programId:ID)+'<strong class="d907-total">'+(units==null?'미확보':num(units)+'<span>'+safe(is?profile?.unit||'호':'호')+'</span>')+'</strong><b>'+period+'</b></div>'+programPlanSummary()+'<div class="pw-region-briefs">'+regions.map(place=>{const cap=is?profile?.['region:'+place]:plan.region_allocations[place];return '<div><header><button data-d907-region="'+place+'">'+place+'</button><strong>'+ (cap!=null?fmt(cap):'개별 목표 미배분')+'</strong>'+(is?'':pencil('region',place))+'</header><p>'+safe(is?'이 프로그램에 연결된 사업계획 · '+allRows().filter(c=>c.region===place).length+'개 사업':themes[place])+'</p></div>';}).join('')+'</div>'+(!is?'<p class="pd-joint">경기·인천 공동 <b>'+fmt(plan.joint_region_units)+'</b></p>':'<p class="pd-joint">프로그램 목표와 연결 사업계획은 별도입니다. 사업 미연결은 실적 0을 뜻하지 않습니다.</p>')+'<div class="pd-summary-foot"><a href="'+safe(plan.evidence_url)+'" target="_blank" rel="noopener">발표 원문 ↗</a><a href="https://www.korea.kr/news/policyNewsView.do?newsId=148948818" target="_blank" rel="noopener">공급 방향 설명 ↗</a></div></div>';
  }
  const scopeKey=()=>{const sub=projectId?'project:'+projectId:city?'city:'+city:region?'region:'+region:'';return isProgram()?'program:'+programId+(sub?'|'+sub:''):sub||'policy';};
  const comparisonIndex=()=>(portfolio()?data.portfolio_comparisons:data.yearly_comparisons)||{};
  const comparison=()=>comparisonIndex()[scopeKey()]?.metrics[metric]||{label:'공급(분양·모집)',annual:[],target_points:[],actual_points:[],management_points:[]};
  const scopeName=()=>comparisonIndex()[scopeKey()]?.name||(isProgram()?program()?.name:'수도권 전체')||'선택 범위';
  function comparisonLines(start,end,y){
    const c=comparison(),left=Date.parse(start+'-01-01'),right=Date.parse(end+'-12-31'),X=d=>90+952*(Date.parse(d)-left)/(right-left);
    const path=ps=>ps.map((p,i)=>(i?'L':'M')+X(p.date).toFixed(1)+' '+y(p.units).toFixed(1)).join(' ');
    const target=c.target_points;
    const manual=c.management_points;
    // Actual points end at their latest observation; never project them into future years.
    const line=(name,ps,color,width,dash='')=>'<path data-d907-line="'+name+'" d="'+path(ps)+'" fill="none" stroke="'+color+'" stroke-width="'+width+'" stroke-dasharray="'+dash+'"/>';
    const dots=(name,ps,color,label)=>ps.filter(p=>p.date>=start+'-01-01'&&p.date<=end+'-12-31').map(p=>'<circle data-d907-point="'+name+'" cx="'+X(p.date)+'" cy="'+y(p.units)+'" r="4" fill="'+color+'" stroke="white"><title>'+p.date+' '+label+' '+fmt(p.units)+'</title></circle>').join('');
    return '<g clip-path="url(#d907-plot)">'+line('target',target,'white',6)+line('official-target',target,'#164c98',3,'7 4')+dots('target',target,'#164c98','누적 원천 목표')+line('management',manual,'#bc6509',3,'2 5')+dots('management',manual,'#bc6509','담당자 누적 목표')+line('actual-halo',c.actual_points,'white',7)+line('actual',c.actual_points,'#073c37',3.5)+dots('actual',c.actual_points,'#073c37','누적 실적')+'</g>';
  }
  function comparisonPanel(){
    const c=comparison(),a=c.annual.find(a=>a.year===year),now=c.actual_points.at(-1),target=a?.target_cumulative_units??a?.management_cumulative_units;
    const rate=a?.actual_cumulative_units!=null&&target>0?(a.actual_cumulative_units/target*100).toFixed(2)+'%':'산정 보류';
    const cells=(label,value,sub)=>'<div><small>'+label+'</small><b>'+fmt(value)+'</b><span>'+sub+'</span></div>';
    const years=c.annual;
    return '<div class="d907-comparison" data-d907-comparison><div class="d907-comparison-head"><h4>'+safe(scopeName())+' · '+safe(c.label)+' 목표와 실적</h4><span>'+year+'년 선택</span></div><div class="d907-compare-cards">'+cells('연간 원천 목표',a?.target_units,'보고서·사업 일정 기준')+cells('연간 도달량',a?.actual_units,a?.actual_through? a.actual_through+'까지':year>current()?'미래 실적 미확보':'동일 단계 기록 미확보')+cells('누적 원천 목표',a?.target_cumulative_units,'해당 연도 말 기준')+cells('누적 도달량',a?.actual_cumulative_units,a?.actual_through?'관측 '+a.actual_through:'동일 단계 기록 미확보')+'</div><div class="d907-comparison-status">'+(a?.management_cumulative_units!=null?'담당자 누적 목표 '+fmt(a.management_cumulative_units)+' · ':'')+'연말 누적 목표 대비 확인량 <b>'+rate+'</b>'+(year>current()&&now?' · 현재까지 확인 '+fmt(now.units)+' ('+now.date+')':'')+'</div><div class="d907-scroll"><table class="d907-annual-pairs"><caption>연도별 목표·실적 · '+safe(c.label)+'</caption><thead><tr><th>연도</th><th>연간 목표</th><th>연간 실적</th><th>누적 목표</th><th>누적 실적</th><th>담당자 누적 목표</th><th>확인 기준일</th></tr></thead><tbody>'+years.map(a=>'<tr class="'+(a.year===year?'selected':'')+'" data-d907-pair-year="'+a.year+'"><th>'+a.year+'</th><td>'+fmt(a.target_units)+'</td><td>'+fmt(a.actual_units)+'</td><td>'+fmt(a.target_cumulative_units)+'</td><td>'+fmt(a.actual_cumulative_units)+'</td><td>'+fmt(a.management_cumulative_units)+'</td><td>'+(a.actual_through||'미확보')+'</td></tr>').join('')+'</tbody></table></div><div class="d907-comparison-basis"><span>목표: '+safe(c.target_basis||'원천 목표 미확보')+'</span><span>실적: '+safe(c.actual_basis||'실적 미확보')+(now?.review_units?' · 단계 근거 확인 필요 '+fmt(now.review_units):'')+(now?.policy_confirmed_units!=null?' · 정책 귀속 확정 '+fmt(now.policy_confirmed_units)+' / 검토 포함 '+fmt(now.units):'')+'</span></div></div>';
  }
  function axisForScope(points,comparisons){
    const scopeUnits=rows().reduce((sum,c)=>sum+c.units,0),officialGoal=!isProgram()&&region&&!city&&!projectId?data.plan.region_allocations?.[region]:null;
    const goals=Object.values(comparisons).flatMap(c=>[...(c.target_points||[]),...(c.management_points||[]),...(c.actual_points||[])]).map(p=>p.units).filter(Number.isFinite);
    const stacks=points.map(p=>Object.values(PolicyStageFlow.totals(p)).reduce((a,b)=>a+b,0));
    const normal=!isProgram()&&!city&&!region&&!projectId?data.target_units:Math.max(1,scopeUnits,officialGoal||0,...goals,...stacks);
    const auto=PolicyStageFlow.referenceAxis({points,comparisons,asOf:data.as_of_date,fullMax:normal});
    return fullAxis?{max:normal,basis:'전체 물량·목표 기준',cropped:false,fullMax:normal}:
      {max:auto.max,basis:auto.focused?'기준일 전후 3개월 · 목표·진행 물량 자동 확대':'기준일 부근 진행 물량 없음 · 전체 범위',cropped:auto.max<normal,fullMax:normal};
  }
  function flow(){
    const originalComparisons=comparisonIndex()[scopeKey()]?.metrics||{};
    const comparisons=Object.fromEntries(Object.entries(originalComparisons).map(([k,c])=>[k,c.tracking?{...c,...c.tracking,management_points:[]}:c]));
    const dates=rows().flatMap(c=>[...c.events.map(e=>e.event_date),...c.schedules.map(s=>s.due_date)]).concat(Object.values(comparisons).flatMap(c=>[...(c.target_points||[]),...(c.management_points||[]),...(c.actual_points||[])].map(p=>p.date))).filter(Boolean);
    if(!region&&!city&&!projectId){if(!isProgram())dates.push(data.plan.period_start,data.plan.period_end);else if(program()?.profile)dates.push(program().profile.period_start,program().profile.period_end);}
    const years=dates.filter(Boolean).map(d=>Number(d.slice(0,4))),start=years.length?Math.min(...years):current(),end=Math.max(current(),...years);
    const points=PolicyStageFlow.trackingPoints({comparisons,start,end,asOf:data.as_of_date});
    const c=comparisons[metric]||comparison(),delays=data.issues.filter(i=>i.status==='DELAYED'&&rows().some(c=>c.id===i.project_id));
    const axis=axisForScope(points,comparisons);
    const policyTarget=projectId||city?rows().reduce((n,c)=>n+c.units,0):isProgram()?(region?program()?.profile?.['region:'+region]:program()?.profile?.target_units):region?data.plan.region_allocations?.[region]:data.target_units;
    const legend=PolicyStageFlow.summaryTable({stages:data.stages,asOf:data.as_of_date,comparisons,originalComparisons,policyTarget,max:axis.fullMax,scopeGoalLabel:isProgram()?'프로그램 목표':'정책 연간 목표'});
    const metricButtons=Object.entries(data.yearly_comparisons?.policy.metrics||{}).map(([k,v])=>'<button data-d907-metric="'+k+'" aria-pressed="'+(metric===k)+'" class="'+(metric===k?'selected':'')+'">'+safe(v.label)+'</button>').join('');
    const chart=PolicyStageFlow.render({tracking:true,policyTarget:policyTarget??axis.fullMax,max:axis.max,axisBasis:axis.basis,start,end,year,axisUnit,constructionPlans:rows().filter(c=>c.construction_plan).map(c=>({units:c.units,plan:c.construction_plan})),asOf:data.as_of_date,points,colors,stages:data.stages,comparison:c,comparisons,delays,metric});
    const fixedAxis=axisUnit==='month'?'<svg class="pw-fixed-y-axis" viewBox="0 60 90 435" preserveAspectRatio="none" aria-hidden="true"><rect x="0" y="60" width="90" height="435" fill="#f8fbff"/><text x="34" y="72">(호)</text>'+[0,.25,.5,.75,1].map(r=>'<text x="80" y="'+(414-325*r)+'" text-anchor="end">'+num(axis.max*r)+'</text>').join('')+'</svg>':'';
    const guide='<p class="pw-axis-note">사업 단계는 등록 사업 전체의 누적값입니다(정책기간 전 사업·입력·추정 포함). 단계 간 물량과 갭은 합산하지 않습니다. 기간 내 사업 목표와 정책·프로그램 자체 목표는 별도 표기합니다.</p><div class="d907-pattern-legend"><span><i class="d907-key-solid"></i><b>실색·실선</b> 측정값 (입력·추정 포함)</span><span><i class="d907-key-plan"></i><b>사선·점선</b> 단계 목표</span><span><i class="d907-key-unknown"></i><b>회색 배경</b> 정책·프로그램 목표</span><span><i class="d907-key-gap"></i><b>빨간 격자</b> 지연 · 부족률 2% 이상</span><span><i class="d907-key-warning"></i><b>노란 격자</b> 주의 · 부족률 0% 초과~2% 미만</span></div><p class="d907-reading-guide">사업화→인허가→착공→공급→입주를 시간축에 쌓습니다. 실선은 누적 측정값, 점선은 같은 단계의 누적 목표입니다. 실색 면은 해당 단계에 머문 물량이며 회색 배경은 정책·프로그램 목표입니다. 기준일 이후에는 목표만 표시합니다.</p>';
    return '<article class="pr-card d907-flow"><div class="pr-card-head"><div><small>Y축 0–'+num(axis.max)+'호 · '+safe(axis.basis)+' · 전체 범위 '+num(axis.fullMax)+'호</small><h3>'+safe(scopeName())+' · '+(isProgram()?'프로그램':'정책')+' 진행현황</h3></div><label class="pw-annual-axis"><input type="checkbox" data-d907-full-axis '+(fullAxis?'checked':'')+'>전체 목표 범위</label></div><div class="d907-legend d907-stage-table" aria-label="단계별 누적 목표·측정·갭 · 선택하면 해당 면 강조">'+legend+'<button type="button" data-d907-highlight="" aria-pressed="true" class="d907-highlight-all">전체 강조</button></div><div class="pw-flow-body"><div class="pw-flow-viewport"><div class="pw-flow-chart">'+chart+'</div>'+fixedAxis+'</div><div class="d907-metric-controls" aria-label="단계별 목표 비교"><label class="pw-time-unit">시간 단위<select data-d907-axis-unit aria-label="그래프 시간 단위"><option value="month" '+(axisUnit==='month'?'selected':'')+'>월</option><option value="year" '+(axisUnit==='year'?'selected':'')+'>년</option></select></label><strong>목표 비교</strong>'+metricButtons+'</div></div>'+(axisUnit==='month'?'<div class="pw-month-nav"><button type="button" data-d907-chart-position="first">← 처음</button><button type="button" data-d907-chart-position="now">현재 시점</button><button type="button" data-d907-chart-position="last">마지막 →</button></div>':'')+guide+'<p class="pw-axis-note">담당자 입력 목표·현재값 반영 · 추정 입력 포함. 현재값에서 채택한 목표는 변경 기준선이며 최초 계획 대비 지연과 구분합니다.</p><p class="pw-axis-note">'+start+'년부터 자료 표시 · '+(axisUnit==='month'?'월 단위 · 좌우로 이동하여 전체 기간 확인':'연 단위 눈금 · 월별 자료에 마우스를 올려 확인')+' · 월 사이 변화는 곡선으로 연결합니다. 곡선 중간값은 시각적 보간이며 목표·측정·갭 수치는 저장된 날짜와 값으로 계산합니다. 측정값은 기준일까지만 표시합니다.</p>'+(axis.cropped?'<p class="pw-axis-note">기준일 전후 3개월에 맞춰 Y축을 확대했습니다. 상한을 넘는 면은 잘려 보이며 원래 수치는 마우스를 올리거나 전체 목표 범위에서 확인할 수 있습니다.</p>':'')+'<details class="pd-comparison-detail"><summary>정책·프로그램 연간 목표와 공식 통계 · 별도 기준</summary>'+comparisonPanel()+'</details></article>';
  }
  function occupancyPanel(){
    const monitor=data.occupancy_monitor;if(!monitor?.source?.annual?.length)return '';
    const marketRegion=region==='서울특별시'?'서울특별시':'수도권',scope=monitor.scopes.find(s=>s.region===marketRegion),annual=scope.annual;
    const max=Math.max(...annual.map(a=>a.target_cumulative_units),1),X=i=>75+i*650/Math.max(1,annual.length-1),Y=v=>185-150*v/max;
    const targetPath=annual.map((a,i)=>(i?'L':'M')+X(i)+' '+Y(a.target_cumulative_units)).join(' ');
    const actualPath=annual.filter(a=>a.actual_cumulative_units!=null).map((a,i)=>(i?'L':'M')+X(annual.indexOf(a))+' '+Y(a.actual_cumulative_units)).join(' ');
    const bands=annual.filter(a=>a.status==='DELAYED').map(a=>{const i=annual.indexOf(a);return '<rect x="'+(X(i)-16)+'" y="'+Y(a.target_cumulative_units)+'" width="32" height="'+(150*a.gap_units/max)+'" fill="#d64357" opacity=".55"><title>입주 지연 '+fmt(a.gap_units)+'</title></rect>';}).join('');
    const chart='<svg class="d907-occupancy-chart" viewBox="0 0 810 220" role="img" aria-label="입주 전망 기반 누적 관리목표와 확인 실적"><path d="M75 35V185H755" fill="none" stroke="#b4c6dc"/><path d="M75 185 '+targetPath.replace(/^M/,'L')+' L'+X(annual.length-1)+' 185 Z" fill="#7a3e9d" fill-opacity=".28"/>'+bands+(actualPath?'<path d="'+actualPath+'" fill="none" stroke="#157c75" stroke-width="4"/>':'<text x="350" y="120" text-anchor="middle" fill="#7a6170">입주 실적 미확보 · 갭/지연 판정 대기</text>')+annual.map((a,i)=>'<circle cx="'+X(i)+'" cy="'+Y(a.target_cumulative_units)+'" r="5" fill="#7a3e9d"/><text x="'+X(i)+'" y="'+(Y(a.target_cumulative_units)-10)+'" text-anchor="middle">'+fmt(a.target_cumulative_units)+'</text><text x="'+X(i)+'" y="207" text-anchor="middle">'+a.year+'</text>').join('')+'</svg>';
    return '<article class="pr-card d907-occupancy"><div class="pr-card-head"><div><small>입주 전망 → 관리목표</small><h3>'+marketRegion+' 아파트 · 입주 목표와 갭</h3></div>'+(state.admin?'<button data-d907-edit>목표·입주 실적 입력</button>':'')+'</div>'+(city||projectId?'<p>아래는 수도권 시장 전체 비교입니다. 선택 사업·시군구의 입주 예정량은 위 연도별 표의 입주 예정에서 확인할 수 있습니다.</p>':'')+chart+'<div class="d907-scroll"><table><thead><tr><th>연도</th><th>연간 입주 목표</th><th>누적 목표</th><th>연간 확인량</th><th>연간 갭</th><th>관리 상태</th></tr></thead><tbody>'+annual.map(a=>'<tr><th>'+a.year+'</th><td>'+fmt(a.target_units)+'</td><td>'+fmt(a.target_cumulative_units)+'</td><td>'+fmt(a.actual_units)+'</td><td>'+fmt(a.gap_units)+'</td><td>'+({DELAYED:'지연',VERIFY:'지연 판정 대기',UPCOMING:'목표 기한 전',ACHIEVED:'목표 달성'}[a.status])+'</td></tr>').join('')+'</tbody></table></div><details><summary>목표 출처·비교 범위</summary><p>'+safe(monitor.notice)+'</p><a href="'+safe(monitor.source.evidence_url)+'" target="_blank" rel="noopener">9·7 원문 '+monitor.source.printed_page+'쪽 · 전망치 기반 관리목표 ↗</a></details></article>';
  }
  function report(){
    return flow()+'<section class="pw-decisions"></section><div id="d907-context"></div><article class="pr-card"><details class="d907-evidence"><summary>정책 원문·공식 유형별 목표·수집 범위</summary>'+macroSummary()+'<div class="d907-programs">'+data.plan.programs.map(p=>'<div><b>'+safe(p.name)+'</b><strong>'+fmt(p.target_units)+'</strong><small>정책 전체 · '+data.plan.period_start.slice(0,4)+'–'+data.plan.period_end.slice(0,4)+'</small></div>').join('')+'</div><p>'+safe(data.stage_note)+'</p><p>사업 미특정 목표 잔여 '+fmt(data.reserve_units)+' · 해당 물량을 임의로 시군구에 배분하지 않습니다.</p><p>입주 시작일과 실제 입주 세대수는 다릅니다. 도래 목표 대비 측정값 부족률 2% 이상은 지연, 0% 초과~2% 미만은 주의로 관리합니다. 미측정은 0호로 간주하지 않습니다.</p><a href="'+safe(data.plan.evidence_url)+'" target="_blank" rel="noopener">정책 원문 ↗</a> · <a href="/poc/home/api/policy-delivery/export.csv">전체 원장 CSV ↓</a></details></article>';
  }
  function decision(){const host=detailHost()?.querySelector('.pw-decisions');PolicyDecision.render(host,{data,cohorts:rows(),scope:scopeName(),year});PolicyReport.statisticsDemographics(host?.querySelector('[data-pr-demography]'),rows(),city,region);}
  function map(){
    const host=$('policy-geo-map');if(!host||!active())return;
    const selectedStage=stage in data.stages?stage:'SUPPLY',values={},regions={};
    const allowedRegions=isProgram()?[...new Set([...allRows().map(c=>c.region),...(program()?.source_profile?.geography||[])])]:data.plan.geography;
    const shapes=data.geometry.shapes.filter(p=>allowedRegions.includes(p.region));
    for(const p of shapes){const cs=allRows().filter(c=>c.municipality_id===p.id),t=stateAt(cs,cutoff());values[p.id]={value:reached(cs,selectedStage,cutoff()),target:cs.reduce((a,c)=>a+(c.planned_units??0),0)};}
    for(const r of ['서울특별시','인천광역시','경기도']){const cs=allRows().filter(c=>c.region===r),t=stateAt(cs,cutoff()),target=cs.reduce((a,c)=>a+(c.planned_units??0),0);regions[r]={target,value:reached(cs,selectedStage,cutoff()),known:target-t.UNKNOWN,unplaced:cs.filter(c=>!c.municipality_id).reduce((a,c)=>a+c.units,0)};}
    // Stable scale for a stage across the entire 11-year slider prevents re-normalising away changes.
    const maxima=data.geometry.shapes.flatMap(p=>{const cs=allRows().filter(c=>c.municipality_id===p.id);return Array.from({length:11},(_,i)=>{return reached(cs,selectedStage,(current()-5+i)+'-12-28');});});
    PolicyRegionMap.render(host,{shapes,regionShapes:data.geometry.region_shapes,allowedRegions,values,regions,max:Math.max(1,...maxima),regionMax:Math.max(1,...allowedRegions.flatMap(r=>Array.from({length:11},(_,i)=>reached(allRows().filter(c=>c.region===r),selectedStage,(current()-5+i)+'-12-28')))),year,currentYear:current(),city,region,stage:selectedStage,stages:data.stages,scope:portfolio()?'PORTFOLIO':'POLICY_PERIOD',scopeNote:portfolio()?'연결 사업 전체 · 정책기간 전 착공 포함 · 공급현황 지도와 같은 집계':'135만 목표 원장 · 2026년 이전 착공 제외'});
  }
  function positionFlow(mode){
    const host=detailHost(),scroller=host?.querySelector('.pw-flow-chart'),svg=scroller?.querySelector('svg');if(!scroller||!svg)return;
    if(mode==='first')scroller.scrollLeft=0;
    else if(mode==='last')scroller.scrollLeft=scroller.scrollWidth;
    else{const line=svg.querySelector('[data-d907-now-line]');scroller.scrollLeft=line?Number(line.getAttribute('x1'))*svg.getBoundingClientRect().width/svg.viewBox.baseVal.width-scroller.clientWidth*.5:0;}
  }
  function render(sliding=false){
    if(!data||!active())return;summary();const host=detailHost();if(!host)return;
    // Keep other views from retaining duplicate detail ids or stale chart models.
    const oldScroller=host.querySelector('.pw-flow-chart'),scrollKey=state.view+':'+scopeKey()+':'+axisUnit,oldPosition=oldScroller?.dataset.scope===scrollKey?oldScroller.scrollLeft:null;
    const other=$(isProgram()?'policy-report-detail':'program-progress-detail');if(other)other.innerHTML='';
    if(sliding&&host.querySelector('.d907-flow')){const temp=document.createElement('div');temp.innerHTML=flow();host.querySelector('.d907-flow').replaceWith(temp.firstElementChild);}else host.innerHTML=report();
    const scroller=host.querySelector('.pw-flow-chart');scroller.dataset.scope=scrollKey;if(oldPosition!=null)scroller.scrollLeft=oldPosition;else if(axisUnit==='month')positionFlow('now');
    map();decision();
    if(isProgram()){const context=host.querySelector('#d907-context');context.innerHTML=PolicyReport.programMembers(programId,rows().flatMap(c=>c.source_ids));}
    else if(!sliding)PolicyReport.supplemental907(city,region,rows().flatMap(c=>c.source_ids));
    DeliveryOperations.mountPolicy(rows().flatMap(c=>c.source_ids),host.querySelector('#policy-execution-panel'));
  }
  async function show(force=false){
    if(!active())return;const next=$('as-of').value;
    if(data&&stamp===next&&!force){render();return;}
    if(!pending||stamp!==next||force){stamp=next;pending=request('/policy-delivery?compact=true&as_of_date='+next).finally(()=>pending=null);}
    try{const value=await pending;if(stamp!==next)return;if(value.status!=='READY')throw new Error(value.notice);data=value;year=year??current();render();}
    catch(e){const h=detailHost();if(h)h.innerHTML='<article class="pr-card">'+safe(e.message)+'</article>';}
  }
  function editor(focusId,focusKind){
    const management=data.management_projects||data.portfolio_cohorts||data.cohorts;
    let node=$('d907-editor');if(node)node.remove();node=document.createElement('dialog');node.id='d907-editor';node.className='d907-editor';
    node.innerHTML='<form method="dialog"><button class="d907-dialog-close" aria-label="닫기">×</button></form><h2>9·7 단계별 목표·실제 사건 관리</h2><p>목표는 누적 호수로 입력합니다. 공식 원문과 별도로 보관하며 변경 이력을 남깁니다.</p><div class="d907-editor-list"></div><form id="d907-target-form"><h3>누적 목표 추가</h3><label>범위<select name="kind"><option value="policy">전체 정책</option><option value="region">시도</option><option value="program">프로그램</option><option value="project">사업</option></select></label><label>대상<select name="scope"></select></label><label>단계<select name="stage">'+Object.entries({...data.stages,COMPLETION:'준공'}).filter(([k])=>k!=='POLICY').map(([k,v])=>'<option value="'+k+'">'+v+'</option>').join('')+'</select></label><label>목표일<input name="due" type="date" required></label><label>누적 목표 호수<input name="units" type="number" min="0" max="1350000"></label><label>또는 목표 비율(%)<input name="pct" type="number" min="0" max="100" step="0.01" placeholder="예: 사업화 100%"></label><label>구분<select name="origin"><option value="MANUAL">담당자 확정 목표</option><option value="SOURCE_REVIEW">자료 기반 임시 목표 · 확인 필요</option></select></label><label>근거·메모<input name="basis" required maxlength="1000"></label><label>근거 URL<input name="url" type="url" placeholder="https://"></label><button>목표 추가</button></form><form id="d907-event-form"><h3>실제 단계·지연 확인 추가</h3><label>사업<select name="project">'+management.map(c=>'<option value="'+c.id+'">'+safe(c.name)+'</option>').join('')+'</select></label><label>단계<select name="stage">'+Object.entries({...data.stages,COMPLETION:'준공'}).filter(([k])=>k!=='POLICY').map(([k,v])=>'<option value="'+k+'">'+v+'</option>').join('')+'</select></label><label>확인일<input name="date" type="date" max="'+data.as_of_date+'" required></label><label>해당 누적 호수<input name="units" type="number" min="0" placeholder="전체 사업은 공란"></label><label>상태<select name="status"><option value="ACTUAL">단계 도달 확인</option><option value="DELAYED">지연 확인</option></select></label><label>근거·메모<input name="basis" required></label><label>공식 근거 URL<input name="url" type="url" required placeholder="https://"></label><button>확인 추가</button></form><p id="d907-save-status" role="status"></p><button class="d907-admin" data-d907-save>변경 내용 저장</button>';
    node.querySelector('#d907-event-form').insertAdjacentHTML('afterend','<form id="d907-occupancy-form"><h3>입주 전망 관리목표의 확인 실적</h3><p>수도권·서울 아파트 전체의 해당 연도 입주량을 입력합니다. 개별 사업 합계를 전체 실적으로 입력하지 않습니다.</p><label>지역<select name="region"><option>수도권</option><option>서울특별시</option></select></label><label>실적 연도<input name="year" type="number" min="2025" max="2035" required></label><label>실적 기준일<input name="as_of_date" type="date" max="'+data.as_of_date+'" required></label><label>해당 연도 확인 입주량<input name="units" type="number" min="0" max="1350000" required></label><label>근거 URL<input name="url" type="url" required></label><label>집계 범위·근거<input name="basis" required></label><button>입주 확인량 추가</button></form>');
    document.body.append(node);const draft=structuredClone(data.settings);draft.occupancy_observations??=[];
    $('d907-occupancy-form').onsubmit=e=>{e.preventDefault();const f=e.target.elements;draft.occupancy_observations.push({region:f.region.value,year:Number(f.year.value),as_of_date:f.as_of_date.value,units:Number(f.units.value),evidence_url:f.url.value,basis:f.basis.value});targets();$('d907-save-status').textContent='입주 확인량 추가됨 · 변경 내용 저장을 누르면 반영됩니다';};draft.targets??=[];draft.events??=[];
    function targets(){node.querySelector('.d907-editor-list').innerHTML=draft.targets.map((t,i)=>'<div>'+safe(t.scope_id)+' · '+safe(data.stages[t.stage]||'준공')+' · '+t.due_date+' · '+fmt(t.units)+' <button type="button" data-remove-goal="'+i+'">삭제</button></div>').join('')+draft.occupancy_observations.map((o,i)=>'<div>'+safe(o.region)+' '+o.year+'년 입주 '+fmt(o.units)+' · '+o.as_of_date+' <button type="button" data-remove-occupancy="'+i+'">삭제</button></div>').join('')+draft.events.map((e,i)=>'<div>'+safe(management.find(c=>c.id===e.project_id)?.name)+' · '+e.stage+' · '+e.event_date+' <button type="button" data-remove-event="'+i+'">삭제</button></div>').join('');}
    const form=node.querySelector('#d907-target-form');function scopes(){const kind=form.elements.kind.value;form.elements.scope.innerHTML=(kind==='policy'?[[ID,'9·7 전체 135만 호']]:kind==='region'?data.plan.geography.map(r=>[r,r]):kind==='project'?management.map(c=>[c.id,c.name]):[...data.plan.programs.map(p=>[p.id,p.name]),...programRows.filter(p=>!p.profile||p.profile.unit==='호').map(p=>[p.id,p.name])]).map(([id,name])=>'<option value="'+safe(id)+'">'+safe(name)+'</option>').join('');}
    form.elements.kind.addEventListener('change',scopes);form.addEventListener('input',()=>form.elements.units.setCustomValidity(''));scopes();targets();
    form.addEventListener('submit',e=>{e.preventDefault();const f=form.elements,denominator=f.kind.value==='policy'?data.target_units:f.kind.value==='project'?management.find(c=>c.id===f.scope.value)?.units:f.kind.value==='region'?data.plan.region_allocations[f.scope.value]:data.plan.programs.find(p=>p.id===f.scope.value)?.target_units;const units=f.units.value!==''?Number(f.units.value):f.pct.value!==''&&denominator?Math.round(denominator*Number(f.pct.value)/100):null;if(units==null){f.units.setCustomValidity('목표 호수 또는 분모가 확인된 범위의 비율을 입력하세요');f.units.reportValidity();return;}f.units.setCustomValidity('');draft.targets.push({scope_kind:f.kind.value,scope_id:f.scope.value,stage:f.stage.value,due_date:f.due.value,units,origin:f.origin.value,basis:f.basis.value,evidence_url:f.url.value||null});targets();});
    node.querySelector('#d907-event-form').addEventListener('submit',e=>{e.preventDefault();const f=e.target.elements;draft.events.push({project_id:f.project.value,stage:f.stage.value,event_date:f.date.value,units:f.units.value===''?null:Number(f.units.value),status:f.status.value,basis:f.basis.value,evidence_url:f.url.value});targets();});
    node.addEventListener('click',async e=>{if(e.target.dataset.removeOccupancy!=null){draft.occupancy_observations.splice(Number(e.target.dataset.removeOccupancy),1);targets();}if(e.target.dataset.removeGoal!=null){draft.targets.splice(Number(e.target.dataset.removeGoal),1);targets();}if(e.target.dataset.removeEvent!=null){draft.events.splice(Number(e.target.dataset.removeEvent),1);targets();}if(e.target.hasAttribute('data-d907-save')){e.target.disabled=true;try{await request('/admin/policy-delivery',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision_no:draft.revision_no,targets:draft.targets,events:draft.events,occupancy_observations:draft.occupancy_observations})});node.close();stamp='';await show(true);}catch(err){$('d907-save-status').textContent=err.message;e.target.disabled=false;}}});if(focusId){form.elements.kind.value=focusKind||"project";scopes();form.elements.scope.value=focusId;}
    if(!state.admin){node.querySelectorAll('input,select,button[data-d907-save],form:not([method="dialog"]) button').forEach(n=>n.disabled=true);node.insertAdjacentHTML('afterbegin','<p class="pw-editor-login">현재 목표 조회 화면입니다. 편집·저장은 <a href="/admin">관리자 로그인</a> 후 사용할 수 있습니다.</p>');}node.showModal();
  }
  function start(){
    PolicyStageFlow.start();
    document.addEventListener('click',e=>{if(!active()&&!e.target.closest('#d907-editor'))return;const b=e.target.closest('button,[data-d907-city]');if(!b||b.hasAttribute('data-d907-highlight'))return;
      if(b.dataset.d907ChartPosition){positionFlow(b.dataset.d907ChartPosition);return;}
      if(b.hasAttribute('data-program-information')){ProgramInformation.open(programId);return;}
      if(b.hasAttribute('data-policy-information')){PolicyInformation.open();return;}
      if(b.hasAttribute('data-d907-edit')){editor(b.dataset.editId,b.dataset.editKind);return;}
      if(b.dataset.d907City){if(data.plan.geography.includes(b.dataset.d907City)){region=b.dataset.d907City;city='';}else{city=b.dataset.d907City;region=data.geometry.shapes.find(p=>p.id===city)?.region||'';}projectId='';}
      if(b.hasAttribute('data-d907-region')){region=b.dataset.d907Region;city='';projectId='';zoom=1;}
      if(b.dataset.d907Stage){stage=b.dataset.d907Stage;if(data.yearly_comparisons.policy.metrics[stage])metric=stage;}
      if(b.dataset.d907Metric||b.dataset.d907DelayStage){metric=b.dataset.d907Metric||b.dataset.d907DelayStage;stage=metric==='COMPLETION'?'CONSTRUCTION':metric;}
      if(b.dataset.d907YearButton)year=Number(b.dataset.d907YearButton);
      if(b.hasAttribute('data-d907-now'))year=current();
      if(b.hasAttribute('data-d907-clear')){city='';region='';projectId='';}
      if(b.hasAttribute('data-d907-full'))full=!full;
      if(b.dataset.d907Window)flowWindow=b.dataset.d907Window;
      if(b.dataset.d907Scope){full=b.dataset.d907Scope==='POLICY_PERIOD';projectId='';}
      if(b.dataset.d907Zoom)zoom=Math.max(.85,Math.min(1.5,zoom+Number(b.dataset.d907Zoom)*.1));
      if(b.dataset.d907Project){projectId=b.dataset.d907Project;city=allRows().find(c=>c.id===projectId)?.municipality_id||'';region=allRows().find(c=>c.id===projectId)?.region||'';}
      if(b.dataset.d907Issues){document.querySelector('.d907-issue-list')?.scrollIntoView({behavior:'smooth'});return;}
      if([...b.attributes].some(a=>a.name.startsWith('data-d907-')))render();
    });
    document.addEventListener('input',e=>{if(active()&&e.target.hasAttribute('data-d907-year')){year=Number(e.target.value);render(true);}});
    document.addEventListener('change',e=>{if(active()&&e.target.hasAttribute('data-d907-axis-unit')){axisUnit=e.target.value;render(true);return;}if(active()&&e.target.hasAttribute('data-d907-full-axis')){fullAxis=e.target.checked;render(true);return;}if(e.target.hasAttribute('data-d907-map-stage')){stage=e.target.value;if(data.yearly_comparisons.policy.metrics[stage])metric=stage;render();}});
    document.addEventListener('keydown',e=>{const g=e.target.closest('[data-d907-city]');if(g&&['Enter',' '].includes(e.key)){e.preventDefault();city=g.dataset.d907City;region=data.geometry.shapes.find(p=>p.id===city)?.region||'';projectId='';render();}});
  }
  return {start,show,programs:()=>programRows,setPrograms:list=>{programRows=(list||[]).filter(p=>p.policy_id===ID&&p.status!=='REJECTED'&&p.status!=='RELEASED');stamp='';},showProgram:id=>{if(!isProgram())return;if(programId!==id){programId=id;city='';region='';projectId='';fullAxis=false;const m=program()?.profile?.metric;if(m&&m!=='CAPACITY')metric=m;}show();},invalidate:()=>{stamp='';},openEditor:async(projectId)=>{data=await request('/policy-delivery?as_of_date='+$('as-of').value);editor(projectId);},reset:()=>{city='';region='';projectId='';zoom=1;render();}};
})();
