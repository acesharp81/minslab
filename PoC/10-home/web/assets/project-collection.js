'use strict';
const ProjectCollection=(()=>{
  const stages={POLICY:'정책',BUSINESS:'사업화',APPROVAL:'인허가',CONSTRUCTION:'건설',SUPPLY:'공급',MOVE_IN:'입주'};
  const kinds={LINK:'정책 연결',STATE:'단계 근거',ACTUAL:'실적·진척',PLAN:'예정·목표',PLAN_STATUS:'일정 제공 상태',DOCUMENT:'문서 확보 · 사건일 미확정'};
  let data=null,loaded=false,generation=0,page=1,stage='ALL',selected=null,detail=null,version=null,dirty=false,polling=false,pendingCell=null;
  const el=id=>document.getElementById(id),e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n=v=>Number(v||0).toLocaleString('ko-KR');
  function params(){const p=new URLSearchParams();if(el('pc-policy').value)p.set('policy_id',el('pc-policy').value);return p;}
  function rows(){return (data?.items||[]).filter(p=>(!el('pc-region').value||p.region===el('pc-region').value)&&(!el('pc-search').value||[p.name,p.program,p.municipality].join(' ').toLowerCase().includes(el('pc-search').value.toLowerCase()))&&(!el('pc-status').value||Object.values(p.cells).some(c=>c.status===el('pc-status').value)));}
  async function load(options={}){
    const token=++generation;el('pc-message').textContent='사업별 저장 근거를 조회하고 있습니다…';el('pc-reload').disabled=true;
    try{const observed=await request('/project-collection/version');const value=await request('/project-collection?'+params());if(token!==generation)return;if(options.automatic&&dirty){el('pc-message').textContent='새 변경이 있습니다. 작성 중인 입력을 보존하며 저장·닫기 후 반영합니다.';return;}data=value;version=observed.version;loaded=true;dirty=false;
      if(!options.preserveSelection){page=1;selected=null;detail=null;}
      else {if(selected&&!value.items.some(p=>p.id===selected))selected=null;if(detail&&!value.items.some(p=>p.id===detail.id))detail=null;page=Math.min(page,Math.max(1,Math.ceil(rows().length/30)));}
      const chosen=el('pc-policy').value;el('pc-policy').innerHTML='<option value="POL_2025_0907">9·7 정책</option><option value="">정책 전체</option>'+(value.policies||[]).filter(p=>p.policy_id!=='POL_2025_0907').map(p=>'<option value="'+e(p.policy_id)+'">'+e(p.name)+'</option>').join('');el('pc-policy').value=chosen;
      const oldStatus=el('pc-status').value;el('pc-status').innerHTML='<option value="">자료 상태 전체</option>'+Object.entries(value.statuses).map(([k,label])=>'<option value="'+k+'">'+e(label)+'</option>').join('');el('pc-status').value=oldStatus;
      const oldGap=el('pc-gap-kind').value;el('pc-gap-kind').innerHTML='<option value="">상태·과제 전체</option>'+Object.entries({COLLECTION_REQUIRED:'원천 수집 필요',LINK_REQUIRED:'출처 확인 · 연결 필요',METHOD_UNKNOWN:'조회 방법 미확인',UPCOMING:'예정 · 기한 전',NOT_REACHED_REPORTED:'미진행 · 원천 추진단계 기준',SCHEDULE_PENDING:'일정 미정 · 원문 확인'}).map(([k,label])=>'<option value="'+k+'">'+e(label)+'</option>').join('');el('pc-gap-kind').value=oldGap;
      render();if(pendingCell){const choice=pendingCell;pendingCell=null;focusCell(choice.id,choice.stage);}el('pc-message').textContent=value.as_of_date+' 기준 · '+n(value.total)+'개 사업 기록 · DB 변경 20초 간격 확인 · 조회 시 재매칭 없음';
    }catch(error){el('pc-message').textContent='조회 실패 · '+error.message;}finally{if(token===generation)el('pc-reload').disabled=false;}
  }
  function constructionPlanHtml(plan,compact=false){
    if(!plan)return '';
    if(compact)return '<span class="pc-progress-mini"><strong>계획 공정률 '+plan.current_planned_pct+'%</strong><small>0% 착공 → 100% 준공 · 기간 비례 추정</small><progress class="pc-progress-track" max="100" value="'+plan.current_planned_pct+'" aria-label="기간 비례 추정 계획 공정률"></progress></span>';
    const first=Date.parse(plan.start_date),last=Date.parse(plan.completion_date),x=d=>45+550*Math.max(0,Math.min(1,(Date.parse(d)-first)/(last-first))),y=p=>135-p;
    const actual=plan.comparison,point=actual?'<circle cx="'+x(actual.date)+'" cy="'+y(actual.actual_pct)+'" r="5" fill="#15775f"><title>'+e(actual.date)+' 원천 공정률 '+actual.actual_pct+'%</title></circle>':'';
    return '<section class="pc-construction-plan"><h4>건설 공정계획 · 0~100%</h4><p>'+e(plan.basis)+'</p><svg viewBox="0 0 640 165" role="img" aria-label="착공 0%부터 준공 100%까지 기간 비례 추정 계획과 원천 공정률"><path d="M45 135 L595 35 L595 135Z" fill="#f1b35f" opacity=".3"/><path d="M45 135 L595 35" stroke="#d48927" stroke-width="2" stroke-dasharray="5 4"/>'+[0,25,50,75,100].map(v=>'<text x="36" y="'+(y(v)+4)+'" text-anchor="end">'+v+'%</text>').join('')+point+'<text x="45" y="157">'+e(plan.start_date)+'</text><text x="595" y="157" text-anchor="end">'+e(plan.completion_date)+'</text></svg><div class="pc-progress-milestones">'+plan.milestones.map(m=>'<span><strong>'+m.pct+'%</strong><small>'+e(m.date)+'</small></span>').join('')+'</div>'+(actual?'<p>원천 공정률 <b>'+actual.actual_pct+'%</b> · '+e(actual.date)+' 기준 / 같은 날 추정 계획 '+actual.planned_pct+'% · 차이 '+actual.gap_percentage_points+'%p (공식 지연 판정 아님)</p>':'<p>실제 공정률 미확보</p>')+'<details><summary>월별 계획 공정률 보기 ('+plan.monthly.length+'개월)</summary><div class="pc-progress-months"><table><thead><tr><th>연월</th><th>추정 계획 공정률</th></tr></thead><tbody>'+plan.monthly.map(m=>'<tr><td>'+e(m.month)+'</td><td>'+m.planned_pct+'%</td></tr>').join('')+'</tbody></table></div></details></section>';
  }
  function progressHtml(c,s,detail=false){
    const p=c.progress;if(!p||s==='POLICY')return '';
    return '<span class="pc-progress-state pc-progress-'+e(p.code)+'"><strong>'+e(p.label)+'</strong>'+(p.source_phase?'<small>원천 단계 '+e(p.source_phase)+' · '+e(p.observed_at||'기준일 미확인')+'</small>':p.due_date?'<small>예정 '+e(p.due_date)+'</small>':'')+(detail&&p.reason?'<small>'+e(p.reason)+'</small>':'')+'</span>';
  }
  function researchHtml(p){
    const rows=(p.research||[]).slice().sort((a,b)=>(b.checked_at||'').localeCompare(a.checked_at||'')||(b.iteration||1)-(a.iteration||1));
    return rows.length?'<section class="pc-research"><h4>인터넷 조회 · 케이스별 점검 이력</h4>'+rows.map(r=>'<details><summary>'+e(r.case_label||'개별 원문 점검')+' · '+n(r.iteration||1)+'차 조회 · '+e(r.checked_at||r.base_date)+' · '+e(r.status_label||r.status)+'</summary><p>검색어: '+e(r.query||r.term)+'</p><p>'+e(r.result_note||'검색 결과는 원문·사업 범위 검증 후 연결합니다.')+'</p>'+(r.candidates||[]).map(c=>'<p><a href="'+e(safeUrl(c.url))+'" target="_blank" rel="noopener">'+e(c.title||c.url)+'</a> <small>'+e(c.verification_label||'원문 확인 대상')+'</small></p>').join('')+'</details>').join('')+'</section>':'';
  }
  function cellContent(c,s){
    const targets=c.targets||[],records=c.sources.filter(r=>r.kind!=='PLAN'&&r.kind!=='PLAN_STATUS');
    const targetHtml=targets.length?'<span class="pc-cell-target"><span class="pc-cell-caption">목표 · 예정 일정</span>'+targets.map(t=>'<span class="pc-target-item"><strong>'+e(t.label)+' · '+e((t.date||t.date_label)+(t.date_conversion==='PERIOD_END'?' · 원문 '+t.date_label+' → 마지막 달':''))+'</strong><small>'+e(t.name)+(t.reference_only?' · 일부 범위: 전체 목표 아님':'')+(t.review_status==='REVIEW'?' · 연결 검토':'')+'</small></span>').join('')+'</span>':'';
    const actuals=records.filter(r=>r.kind==='ACTUAL');
    const actualText=actuals.length?actuals.map(r=>(r.units!=null?'확인 물량 '+n(r.units)+'호 · ':'')+(r.pct!=null?'공정률 '+r.pct+'%':r.basis||'실적 확인')+(r.date?' · '+r.date:'')).join(' / '):
      records.some(r=>r.kind==='DOCUMENT')?records.filter(r=>r.kind==='DOCUMENT').map(r=>r.basis).join(' / '):records.some(r=>r.kind==='PLAN_STATUS')?records.filter(r=>r.kind==='PLAN_STATUS').map(r=>r.basis).join(' / '):c.inferred_available?'선행 단계 추정':s==='POLICY'?'정책 연결 근거':'단계 근거 · 실적 여부 검토';
    const evidenceHtml=records.length?'<span class="pc-cell-evidence"><span class="pc-cell-caption">확보된 '+stages[s]+' 정보</span><strong>'+e([...new Set(records.map(r=>r.name))].join(' / '))+'</strong><small>'+e(actualText)+(records.some(r=>r.review_status==='REVIEW')?' · 연결 확인 필요':'')+'</small></span>':'';
    return progressHtml(c,s)+((targetHtml?targetHtml.replace(/<\/span>$/,constructionPlanHtml(c.construction_plan,true)+'</span>'):c.construction_plan?'<span class="pc-cell-target">'+constructionPlanHtml(c.construction_plan,true)+'</span>':'')+evidenceHtml||'<span class="pc-cell-evidence pc-cell-missing"><strong>'+e(c.label)+'</strong><small>'+e(c.reason)+'</small></span>');
  }

  function renderGaps(list){
    const groups=new Map(),kind=el('pc-gap-kind').value;
    for(const p of list)for(const gap of p.gaps||[]){
      if(kind&&gap.code!==kind)continue;
      const key=JSON.stringify([p.collection_owner,gap.stage,gap.code,gap.reason]);
      if(!groups.has(key))groups.set(key,{...gap,owner:p.collection_owner,projects:[],planned:0});
      const g=groups.get(key);g.projects.push(p);g.planned+=Number(Boolean(p.cells[gap.stage].targets?.length));
    }
    const values=[...groups.values()].sort((a,b)=>b.projects.length-a.projects.length||a.owner.localeCompare(b.owner)||a.stage.localeCompare(b.stage));
    const required=values.filter(g=>g.action_required!==false).reduce((n,g)=>n+g.projects.length,0);
    el('pc-gap-note').textContent='실제 수집·연결 과제 '+n(required)+'개 사업×단계 · 조회 조건에 해당하는 '+n(list.length)+'개 사업 전체를 기관·단계·미확보 사유로 묶었습니다. '+n(values.length)+'개 상태·과제 유형 · '+n(values.reduce((v,g)=>v+g.projects.length,0))+'개 사업×단계. 예정자료가 있어도 실적은 별도로 확인합니다.';
    el('pc-gap-groups').innerHTML=values.length?values.map(g=>'<details class="pc-gap-group"><summary><span class="pc-gap-owner">'+e(g.owner)+' · '+stages[g.stage]+'</span><span><strong>'+e(g.label)+'</strong><small>'+e(g.reason)+'</small></span><span class="pc-gap-count">'+n(g.projects.length)+'개 사업<small>목표 일정 확보 '+n(g.planned)+'개</small></span></summary><div class="pc-gap-projects"><p>현재 DB에 연결된 근거 기준입니다. 기관 전체에 자료가 없다는 의미는 아닙니다.</p>'+g.projects.map(p=>'<button type="button" data-pc-cell="'+e(p.id)+'" data-pc-stage="'+g.stage+'">'+e(p.name)+'<small>'+e(p.region)+' · '+e(p.municipality||'지역 상세 미확인')+'</small></button>').join('')+'</div></details>').join(''):'<p class="pc-gap-empty">조회 범위에 해당하는 공통 수집 과제가 없습니다.</p>';
  }
  function render(){
    const list=rows();if(!list.some(p=>p.id===selected))selected=null;
    const exportParams=params();for(const [id,key] of [['pc-region','region'],['pc-search','q'],['pc-status','collection_status']])if(el(id).value)exportParams.set(key,el(id).value);el('pc-export').href=API+'/project-collection/export.csv?'+exportParams;
    const count=Object.fromEntries(Object.keys(data.statuses).map(s=>[s,list.reduce((v,p)=>v+Object.values(p.cells).filter(c=>c.status===s).length,0)]));
    el('pc-summary').innerHTML='<div><span>조회 사업</span><strong>'+n(list.length)+'개</strong><small>사업 기록 기준</small></div>'+Object.entries(data.statuses).map(([s,label])=>'<div class="pc-count-'+s+'"><span>'+e(label)+'</span><strong>'+n(count[s])+'</strong><small>사업 × 단계 셀</small></div>').join('');
    let coverage=el('pc-stage-coverage');if(!coverage){coverage=document.createElement('div');coverage.id='pc-stage-coverage';el('pc-summary').after(coverage);}
    const metrics=[['dated_plan_available','날짜 있는 목표'],['actual_available','실적·진척 확인'],['partial_actual_available','일부 범위 실적'],['inferred_available','선행 단계 추정']];
    coverage.innerHTML='<h3>단계별 확보 내용 <small>조회 사업 기록 기준</small></h3><table><thead><tr><th>확보 구분</th>'+Object.values(stages).map(label=>'<th>'+label+'</th>').join('')+'</tr></thead><tbody>'+metrics.map(([key,label])=>'<tr><th>'+label+'</th>'+Object.keys(stages).map(s=>'<td>'+n(list.filter(p=>p.cells[s][key]).length)+'개</td>').join('')+'</tr>').join('')+'<tr><th>연결 근거</th>'+Object.keys(stages).map(s=>'<td>'+n(list.reduce((v,p)=>v+(p.cells[s].evidence_count||0),0))+'건</td>').join('')+'</tr></tbody></table><p>원천 확보는 자료가 있는 칸 수입니다. 같은 칸에 근거를 추가해도 칸 수는 늘지 않습니다. 각 행은 중복될 수 있으며 합산하지 않습니다. 원문에 명시된 ‘미정’은 자료 확보로 유지하고, 항목 미제공·공란만 있는 칸은 제외합니다. 실적·진척에는 착공·공정률 등이 포함되며 단계 완료나 주택 호수와 다릅니다.</p>';
    const size=30,totalPages=Math.max(1,Math.ceil(list.length/size));page=Math.min(page,totalPages);const shown=list.slice((page-1)*size,page*size);
    el('pc-table').innerHTML='<table class="pc-matrix"><thead><tr><th>사업 / 지역</th>'+Object.entries(stages).map(([s,label])=>'<th><span class="pc-stage-dot" data-stage="'+s+'"></span>'+label+'</th>').join('')+'</tr></thead><tbody>'+shown.map(p=>'<tr class="'+(selected===p.id?'pc-selected':'')+'"><th><button type="button" data-pc-project="'+e(p.id)+'">'+e(p.name)+'</button><small>'+e(p.region+' · '+(p.municipality||'지역 상세 미확인'))+'</small><small>'+e(p.program||'프로그램 미연결')+'</small></th>'+Object.keys(stages).map(s=>{
      const c=p.cells[s];return '<td><button class="pc-cell pc-'+c.status+(detail?.id===p.id&&detail?.stage===s?' pc-cell-active':'')+'" type="button" data-pc-cell="'+e(p.id)+'" data-pc-stage="'+s+'">'+cellContent(c,s)+'</button></td>';
    }).join('')+'</tr>').join('')+'</tbody></table>'+(shown.length?'':'<p>조건에 맞는 사업이 없습니다.</p>');
    el('pc-page').textContent=page+' / '+totalPages+' · '+n(list.length)+'개';el('pc-prev').disabled=page<=1;el('pc-next').disabled=page>=totalPages;
    renderGaps(list);drawDiagram();renderDetail();
  }
  function drawDiagram(){
    const list=rows(),p=list.find(p=>p.id===selected);
    el('pc-diagram-context').textContent=p?p.name+' · 저장된 사업 연결':'조회 범위 '+n(list.length)+'개 사업 · 저장된 연결';el('pc-clear-project').hidden=!p;
    el('pc-stage-tabs').innerHTML='<button type="button" data-pc-diagram="ALL" aria-pressed="'+(stage==='ALL')+'">전체 흐름</button>'+Object.entries(stages).map(([s,label],i)=>'<button type="button" data-pc-diagram="'+s+'" aria-pressed="'+(stage===s)+'">'+(i+1)+' '+label+'</button>').join('');
    CollectionLineage.render({host:el('pc-diagram'),detailHost:el('pc-diagram-detail'),data,rows:p?[p]:list,stage,projectName:p?.name});
  }
  function renderDetail(){
    const host=el('pc-cell-detail'),p=(data.items||[]).find(p=>p.id===detail?.id);host.hidden=!p;if(!p)return;
    const c=p.cells[detail.stage];const checks=(p.sequence_checks||[]).filter(x=>x.stage===detail.stage||x.downstream===detail.stage);host.innerHTML='<div class="pc-detail-head"><h3>'+e(p.name)+' · '+stages[detail.stage]+'</h3><button type="button" data-pc-detail-close>닫기</button></div><p><strong>'+e(c.label)+'</strong>'+(c.review_required?' · 연결 확인 필요':'')+'</p>'+progressHtml(c,detail.stage,true)+researchHtml(p)+((c.targets||[]).length?'<div class="pc-detail-targets"><h4>목표 · 예정 일정</h4>'+c.targets.map(t=>'<p><strong>'+e(t.label)+' · '+e((t.date||t.date_label)+(t.date_conversion==='PERIOD_END'?' · 원문 '+t.date_label+' → 마지막 달':''))+'</strong><small> '+e(t.name)+(t.reference_only?' · 일부 유형 참고 일정: 전체 사업 목표·실적으로 집계하지 않음':'')+(t.review_status==='REVIEW'?' · 연결 확인 필요':'')+'</small></p>').join('')+'</div>':'')+(checks.length?'<div class="pc-detail-targets"><h4>선후 관계 수집 점검</h4>'+checks.map(x=>'<p><strong>'+e(x.label)+'</strong><small>'+e(x.reason)+'</small></p>').join('')+'</div>':'')+(c.sources.length?'<div class="pc-evidence-list">'+c.sources.map(r=>'<article><strong>'+e(r.name)+'</strong><span class="badge neutral">'+e(kinds[r.kind])+'</span><p>'+e(r.basis||'저장된 원천 근거')+'</p><small>'+e(r.date||r.date_label||'사건일 미확인')+(r.units!=null?' · 확인 물량 '+n(r.units)+'호':'')+(r.pct!=null?' · 공정률 '+r.pct+'%':'')+(r.review_status==='REVIEW'?' · 담당자 확인 필요':'')+'</small></article>').join('')+'</div>':'<p>'+e(c.reason)+'</p>')+constructionPlanHtml(c.construction_plan)+(c.assessment?'<p class="pc-assessment-basis">담당자 판정: '+e(c.assessment.basis)+(c.assessment_conflict?' · 이후 자료 확보로 재검토 필요':'')+'</p>':'')+'<div class="pc-detail-actions"><button type="button" data-pc-open-project="'+e(p.id)+'">사업 상세 보기</button><button type="button" data-pc-open-mapping="'+e(p.id)+'">정책–프로그램–사업 연결에서 검토</button></div>';
    host.insertAdjacentHTML('beforeend',CollectionRepairs.html(data,[p],detail.stage));
    const bridges=(p.evidence_bridges||[]).filter(b=>b.facts.some(f=>f.stage===detail.stage));
    if(bridges.length)host.insertAdjacentHTML('beforeend','<section class="pc-bridge-review"><h4>추가 연결 근거 · 담당자 검토</h4><p>지역·지구·블록을 대조한 후보입니다. 일부 유형 연결은 적용 호수와 전체 호수를 별도로 표시합니다. 확정은 자료 연결의 확인이며, 예정일을 실적으로 바꾸지 않습니다.</p>'+bridges.map(b=>'<form class="pc-bridge-form" data-bridge-id="'+e(b.id)+'" data-bridge-revision="'+b.revision_no+'"><strong>'+e(b.source_name)+'</strong><p>'+e(b.basis)+'</p><small>고정 원천 판본 '+b.source_revision_no+' · '+e(b.base_date)+'</small><p><a href="'+e(safeUrl(b.evidence_url))+'" target="_blank" rel="noopener">연결 원문 ↗</a></p><label>연결 상태<select name="status" '+(state.admin?'':'disabled')+'>'+Object.entries({REVIEW:'검토 후보',CONFIRMED:'담당자 확정',RELEASED:'연결 해제'}).map(([v,label])=>'<option value="'+v+'" '+(v===b.status?'selected':'')+'>'+label+'</option>').join('')+'</select></label><label>검토 기록<textarea name="basis" required maxlength="2000" '+(state.admin?'':'disabled')+'>'+e(b.review_basis||b.basis)+'</textarea></label>'+(state.admin?'<button type="submit" class="button primary">연결 검토 저장</button>':'')+'<p role="status" class="pc-bridge-result"></p></form>').join('')+'</section>');
    if(state.admin){host.insertAdjacentHTML('beforeend','<form id="pc-assessment-form"><h4>미확보 원인 확인</h4><p>원천 또는 담당자 확인 근거를 남겨 수집 상태를 관리합니다. 확보된 자료가 있으면 해당 자료를 우선 표시합니다.</p><label>판정<select name="status"><option value="COLLECTION_REQUIRED">제공처 확인 · 수집/연결 필요</option><option value="NOT_PLANNED">확인됨 · 아직 계획 미수립</option><option value="METHOD_UNKNOWN">수집 방안 미확인</option><option value="RELEASED">담당자 판정 해제</option></select></label><label>확인 근거<textarea name="basis" required maxlength="2000" placeholder="확인한 자료명·담당기관·확인일 또는 제공처 조사 결과"></textarea></label><button type="submit" class="button primary">판정 저장</button><p id="pc-save-status" role="status"></p></form>');if(c.assessment){host.querySelector('[name="status"]').value=c.assessment.status;host.querySelector('[name="basis"]').value=c.assessment.basis;}}
  }
  async function refreshIfChanged(){
    if(polling||!loaded||document.hidden||!el('pane-project-collection').offsetParent||el('pc-reload').disabled)return;
    polling=true;try{const next=await request('/project-collection/version');if(next.version!==version){if(dirty){el('pc-message').textContent='새 변경이 있습니다. 작성 중인 입력을 보존하며 저장·닫기 후 반영합니다.';}else await load({preserveSelection:true,automatic:true});}}catch(error){el('pc-message').textContent='변경 확인 실패 · 기존 화면 유지. 다음 주기에 재시도합니다.';}finally{polling=false;}
  }
  function setup(){
    setInterval(refreshIfChanged,20000);document.addEventListener('visibilitychange',refreshIfChanged);
    el('pc-cell-detail').addEventListener('input',event=>{if(event.target.closest('form'))dirty=true;});
    el('pc-cell-detail').addEventListener('change',event=>{if(event.target.closest('form'))dirty=true;});
    el('pc-gap-kind').addEventListener('change',()=>renderGaps(rows()));
    el('pc-policy').addEventListener('change',load);el('pc-reload').addEventListener('click',load);
    for(const id of ['pc-region','pc-status'])el(id).addEventListener('change',()=>{page=1;render();});el('pc-search').addEventListener('input',()=>{page=1;render();});
    el('pc-prev').addEventListener('click',()=>{page--;render();});el('pc-next').addEventListener('click',()=>{page++;render();});
    el('pane-project-collection').addEventListener('click',event=>{
      const t=event.target.closest('button');if(!t)return;
      if(t.dataset.pcDiagram){stage=t.dataset.pcDiagram;drawDiagram();}
      if(t.dataset.pcProject){selected=t.dataset.pcProject;drawDiagram();render();}
      if(t.id==='pc-clear-project'){selected=null;render();}
      if(t.dataset.pcCell){
        const fromGroup=Boolean(t.closest('.pc-gap-projects'));
        detail={id:t.dataset.pcCell,stage:t.dataset.pcStage};selected=detail.id;stage=detail.stage;
        if(fromGroup){const index=rows().findIndex(p=>p.id===detail.id);if(index>=0)page=Math.floor(index/30)+1;}
        render();
        if(fromGroup){const cell=el('pc-table').querySelector('[data-pc-cell="'+CSS.escape(detail.id)+'"][data-pc-stage="'+detail.stage+'"]');cell?.focus({preventScroll:true});cell?.scrollIntoView({behavior:'smooth',block:'center',inline:'center'});}
        else el('pc-cell-detail').scrollIntoView({behavior:'smooth',block:'nearest'});
      }
      if(t.hasAttribute('data-pc-detail-close')){detail=null;dirty=false;renderDetail();refreshIfChanged();}
      if(t.dataset.pcOpenProject)openDetail(t.dataset.pcOpenProject);
      if(t.dataset.pcOpenMapping){setView('tree');MappingWorkbench.focusProject(t.dataset.pcOpenMapping);}
    });
    el('pane-project-collection').addEventListener('submit',async event=>{
      if(event.target.matches('.pc-bridge-form')){
        event.preventDefault();const form=event.target,v=new FormData(form),out=form.querySelector('.pc-bridge-result'),button=form.querySelector('button');button.disabled=true;
        try{await request('/admin/evidence-bridge',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({link_id:form.dataset.bridgeId,revision_no:Number(form.dataset.bridgeRevision),status:v.get('status'),basis:v.get('basis')})});dirty=false;await load({preserveSelection:true});el('pc-message').textContent='추가 연결의 검토 상태와 근거를 DB에 기록했습니다.';}
        catch(error){out.textContent=error.message;button.disabled=false;}return;
      }
      if(event.target.id!=='pc-assessment-form')return;event.preventDefault();const form=event.target,v=new FormData(form),cell=data.items.find(p=>p.id===detail.id).cells[detail.stage],out=el('pc-save-status');
      form.querySelector('button').disabled=true;
      try{await request('/admin/project-collection/assessment',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project_id:detail.id,stage:detail.stage,revision_no:cell.assessment?.revision_no||0,status:v.get('status'),basis:v.get('basis')})});dirty=false;await load({preserveSelection:true});el('pc-message').textContent='수집 원인 판정을 DB에 저장했습니다.';}catch(error){out.textContent=error.message;form.querySelector('button').disabled=false;}
    });
  }
  function focusCell(id,cellStage){
    if(!Object.hasOwn(stages,cellStage))return;
    const policyChanged=el('pc-policy').value!=='POL_2025_0907';el('pc-policy').value='POL_2025_0907';
    setView('project-collection');
    if(policyChanged&&loaded){pendingCell={id,stage:cellStage};load({preserveSelection:true});return;}
    if(!loaded){pendingCell={id,stage:cellStage};return;}
    el('pc-policy').value='POL_2025_0907';el('pc-region').value='';el('pc-status').value='';el('pc-search').value='';
    const index=rows().findIndex(p=>p.id===id);if(index<0){el('pc-message').textContent='선택 사업을 현재 수집 범위에서 확인할 수 없습니다.';return;}
    page=Math.floor(index/30)+1;selected=id;stage=cellStage;detail={id,stage};render();el('pc-cell-detail').scrollIntoView({block:'start',behavior:'smooth'});
  }
  let ready=false;return {visible(options={}){if(!ready){setup();ready=true;}if(loaded)refreshIfChanged();else load({preserveSelection:true});},reload:load,refreshIfChanged,constructionPlanHtml,focusCell};
})();
