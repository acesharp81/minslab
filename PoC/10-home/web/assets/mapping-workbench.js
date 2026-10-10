'use strict';
const MappingWorkbench=(()=>{
  let payload, stage='policy', selectedProgram, selectedProject, page=1, saving=false, generation=0;
  const checked=new Set();
  const realPolicies=()=>payload.policies.filter(p=>p.monitor_kind==='POLICY');
  const policyName=id=>id==='UNASSIGNED'||!id?'정책 미연계':payload.policies.find(p=>p.policy_id===id)?.name||'정책 미확인';
  const seedName=id=>id?.startsWith('MON_')?'프로그램 원점: '+policyName(id):policyName(id);
  const program=id=>payload.programs.find(p=>p.id===id);
  const programName=id=>id==='UNASSIGNED'||!id?'프로그램 미연계':program(id)?.name||'프로그램 확인 필요';
  const options=(rows,selected,key,label)=>rows.map(row=>`<option value="${esc(row[key])}" ${row[key]===selected?'selected':''}>${esc(label(row))}</option>`).join('');
  const programLabel=p=>`${p.name} · ${policyName(p.policy_id)}${p.seed_policy_id!==p.policy_id?' (원천 제안과 다름)':''}`;
  function setStage(value){
    stage=value;
    $('mapping-policy-workspace').hidden=stage!=='policy';
    $('mapping-project-workspace').hidden=stage!=='project';
    $('mapping-tab-policy').setAttribute('aria-selected',String(stage==='policy'));
    $('mapping-tab-project').setAttribute('aria-selected',String(stage==='project'));
    if(payload)stage==='policy'?renderPrograms():renderProjects();
  }
  function render(data){
    payload=data;
    for(const id of checked)if(!data.items.some(r=>r.id===id))checked.delete(id);
    const policy=$('mapping-program-policy').value;
    $('mapping-program-policy').innerHTML='<option value="">정책 전체</option><option value="UNASSIGNED">정책 미연계</option>'+options(realPolicies(),null,'policy_id',p=>p.name);
    $('mapping-program-policy').value=policy;
    const queuePolicy=$('mapping-queue-policy').value;
    $('mapping-queue-policy').innerHTML='<option value="">상위 정책 전체</option><option value="UNASSIGNED">정책 미연계</option>'+options(realPolicies(),null,'policy_id',p=>p.name);
    $('mapping-queue-policy').value=queuePolicy;
    const queueProgram=$('mapping-queue-programme').value;
    $('mapping-queue-programme').innerHTML='<option value="">프로그램 전체</option><option value="UNASSIGNED">프로그램 미연계</option>'+[...new Set(data.programs.map(p=>p.name))].sort().map(name=>`<option value="NAME:${esc(name)}">동일 이름 전체 · ${esc(name)}</option>`).join('')+options(data.programs,null,'id',programLabel);
    $('mapping-queue-programme').value=queueProgram;
    $('mapping-bulk-program').innerHTML='<option value="">현재 연결 유지</option>'+options(data.programs,null,'id',programLabel);
    $('mapping-queue-counts').innerHTML=[['사업 승인 대기',data.counts.REVIEW||0],['사업 확정',data.counts.CONFIRMED||0],['정책 미연계 사업',data.audit.unlinked_policy_projects]].map(([name,n])=>`<div><span>${esc(name)}</span><strong>${num(n)}건</strong></div>`).join('');
    $('mapping-program-counts').innerHTML=[['정책–프로그램 확인 필요',data.audit.review_programs],['프로그램–사업 확인 필요',data.audit.review_projects],['정책 미연계 프로그램',data.audit.unlinked_programs]].map(([name,n])=>`<div><span>${esc(name)}</span><strong>${num(n)}건</strong></div>`).join('');
    $('mapping-queue-notice').textContent=data.notice;
    $('mapping-bulk').hidden=!state.admin;
    setStage(stage);
  }
  function filteredPrograms(){return payload.programs.filter(p=>(!$('mapping-program-status').value||p.status===$('mapping-program-status').value)&&(!$('mapping-program-policy').value||p.policy_id===$('mapping-program-policy').value));}
  function renderPrograms(){
    const rows=filteredPrograms();
    if(!rows.some(p=>p.id===selectedProgram))selectedProgram=rows[0]?.id;
    $('mapping-program-list').innerHTML=rows.length?`<table><thead><tr><th>프로그램 / 연결 사업</th><th>상위 정책</th><th>상태</th></tr></thead><tbody>${rows.map(p=>`<tr class="${p.id===selectedProgram?'selected':''}"><td><button class="mapping-program-list-row" data-program-edit="${esc(p.id)}"><b>${esc(p.name)}</b><small>연결 ${num(p.project_count)}건 · 통계 반영 ${num(p.active_project_count)}건</small></button></td><td class="${p.policy_id==='UNASSIGNED'?'mapping-program-unlinked':''}">${esc(policyName(p.policy_id))}<small class="row-sub">원천 제안 ${esc(seedName(p.seed_policy_id))}</small></td><td>${badge(p.status)}</td></tr>`).join('')}</tbody></table>`:empty('해당 정책·상태의 프로그램이 없습니다.');
    renderProgramEditor();
  }
  function renderProgramEditor(){
    const p=program(selectedProgram),node=$('mapping-program-editor'),revision=++generation;
    if(!p){node.innerHTML=empty('프로그램을 선택하세요.');return;}
    const members=payload.items.filter(r=>r.mapping.program_id===p.id);
    node.innerHTML=`<p class="section-kicker">POLICY ↔ PROGRAMME</p><h3>${esc(p.name)}</h3><p>연결 사업 ${num(p.project_count)}건 · 원천 정책 제안 ${esc(seedName(p.seed_policy_id))}</p>${p.status==='REVIEW'?'<p class="mapping-program-alert">자동 임시 연결 · 담당자 확인 필요. 개별 사업의 공식 정책 귀속은 미확정입니다.</p>':''}${p.policy_id==='UNASSIGNED'?'<p class="mapping-program-alert">상위 정책이 미연계되어 정책별 진행현황의 “정책 미연계”에 표시됩니다.</p>':''}${state.admin?'':'<p class="mapping-login">담당자 승인·수정은 <a href="/admin">관리자 로그인</a> 후 가능합니다.</p>'}<form id="program-policy-form" class="review-form"><label>상위 정책<select name="policy_id" ${state.admin?'':'disabled'}><option value="UNASSIGNED" ${p.policy_id==='UNASSIGNED'?'selected':''}>정책 미연계 · 확인 필요</option>${options(realPolicies(),p.policy_id,'policy_id',r=>r.name)}</select></label><label>정책–프로그램 검토<select name="status" ${state.admin?'':'disabled'}><option value="REVIEW">확인 필요 · 검토 통계 포함</option><option value="CONFIRMED">담당자 확정</option><option value="RELEASED">정책 연결 해제</option></select></label><label>매칭 근거<textarea name="basis" maxlength="2000" required ${state.admin?'':'disabled'}>${esc(p.basis)}</textarea></label><label>공식 근거 URL<input name="evidence_url" type="url" maxlength="2000" required value="${esc(p.evidence_url)}" ${state.admin?'':'disabled'}></label>${state.admin?'<div class="mapping-editor-actions"><button class="button primary" type="submit">정책–프로그램 저장</button><button id="program-policy-approve" class="button secondary" type="button">담당자 최종 승인</button></div>':''}<p id="program-policy-status" role="status"></p></form><div class="mapping-editor-links"><button type="button" class="text-button" data-show-program-projects="${esc(p.id)}">연결 사업 ${num(members.length)}건 보기 ↗</button></div><details open><summary>상위 정책 변경 이력</summary><div id="program-policy-history">불러오는 중…</div></details>`;
    const form=$('program-policy-form');form.elements.status.value=p.status;
    if(state.admin){form.addEventListener('submit',saveProgram);$('program-policy-approve').addEventListener('click',()=>{form.elements.status.value='CONFIRMED';form.requestSubmit();});}
    request('/programs/'+encodeURIComponent(p.id)+'/history?as_of_date='+encodeURIComponent($('as-of').value)).then(result=>{
      if(revision!==generation||!$('program-policy-history'))return;
      $('program-policy-history').innerHTML=result.items.length?result.items.map(r=>`<div class="mapping-audit"><b>${r.action==='PROGRAM_POLICY_AUTO'?'자동 임시 제안':'담당자 조정'} · ${timeText(r.recorded_at)}</b><p>${esc(policyName(r.before.policy_id))} → ${esc(policyName(r.after.policy_id))} · ${badge(r.after.status)}</p><small>${esc(r.after.basis)}</small></div>`).join(''):'<p>초기 자동 연결 · 담당자 변경 없음</p>';
    }).catch(error=>{if(revision===generation&&$('program-policy-history'))$('program-policy-history').textContent=error.message;});
  }
  function filteredProjects(){return payload.items.filter(r=>(!$('mapping-queue-status').value||r.mapping.status===$('mapping-queue-status').value)&&(!$('mapping-queue-policy').value||r.mapping.policy_id===$('mapping-queue-policy').value)&&(!$('mapping-queue-programme').value||($('mapping-queue-programme').value.startsWith('NAME:')?r.program===$('mapping-queue-programme').value.slice(5):r.mapping.program_id===$('mapping-queue-programme').value)));}
  function renderProjects(){
    const rows=filteredProjects();page=Math.max(1,Math.min(page,Math.ceil(rows.length/30)||1));
    if(!rows.some(r=>r.id===selectedProject))selectedProject=rows[0]?.id;
    const visible=rows.slice((page-1)*30,page*30);
    $('mapping-queue-list').innerHTML=visible.length?`<table><thead><tr><th><input type="checkbox" id="mapping-select-page" aria-label="현재 페이지 전체 선택" ${visible.every(r=>checked.has(r.id))?'checked':''} ${state.admin?'':'disabled'}></th><th>사업 / 원천 프로그램</th><th>연결 프로그램 → 정책</th></tr></thead><tbody>${visible.map(r=>`<tr class="${r.id===selectedProject?'selected':''}"><td><input type="checkbox" data-mapping-check="${esc(r.id)}" aria-label="${esc(r.name)} 선택" ${checked.has(r.id)?'checked':''} ${state.admin?'':'disabled'}></td><td><button class="project-name" data-mapping-edit="${esc(r.id)}">${esc(r.name)}</button><small class="row-sub">${esc(r.region)} · 원천 ${esc(r.source_program||r.program)}</small></td><td>${esc(programName(r.mapping.program_id))}<small class="row-sub">${esc(policyName(r.mapping.policy_id))} · ${badge(r.mapping.status)}</small></td></tr>`).join('')}</tbody></table>`:empty('해당 조건의 사업이 없습니다.');
    $('mapping-queue-page').textContent=`${page}/${Math.ceil(rows.length/30)||1} · 조회 ${num(rows.length)}건 · 선택 ${num(checked.size)}건`;
    $('mapping-queue-prev').disabled=page===1;$('mapping-queue-next').disabled=page*30>=rows.length;$('mapping-bulk-save').disabled=saving||!checked.size;
    renderProjectEditor();
  }
  function renderProjectEditor(){
    const r=payload.items.find(x=>x.id===selectedProject),node=$('mapping-editor'),revision=++generation;
    if(!r){node.innerHTML=empty('사업을 선택하세요.');return;}
    const p=program(r.mapping.program_id);
    node.innerHTML=`<p class="section-kicker">PROGRAMME ↔ PROJECT</p><h3>${esc(r.name)}</h3><p>${esc(r.region)} · 원천 프로그램 ${esc(r.source_program||r.program)} · 계획 ${r.planned_units==null?'미확보':num(r.planned_units)+'호'}</p><div class="mapping-auto"><b>현재 연결 흐름</b><p>${esc(policyName(r.mapping.policy_id))} → ${esc(programName(r.mapping.program_id))} → ${esc(r.name)}</p><small>정책–프로그램 ${p?badge(p.status):'미연계'} · 프로그램–사업 ${badge(r.mapping.status)}</small>${p&&r.source_program===p.name&&r.mapping.status==='REVIEW'?'<small>원천 프로그램명 일치로 자동 연결 · 담당자 확인 필요</small>':''}</div>${state.admin?'':'<p class="mapping-login">담당자 승인·수정은 <a href="/admin">관리자 로그인</a> 후 가능합니다.</p>'}<form id="workbench-form" class="review-form"><label>연결 프로그램<select name="program_id" ${state.admin?'':'disabled'}><option value="UNASSIGNED" ${r.mapping.program_id==='UNASSIGNED'?'selected':''}>프로그램 미연계</option>${options(payload.programs,r.mapping.program_id,'id',programLabel)}</select></label><label>프로그램–사업 검토<select name="status" ${state.admin?'':'disabled'}><option value="REVIEW">확인 필요 · 검토 통계 포함</option><option value="CONFIRMED">담당자 확정</option><option value="RELEASED">연결 해제 · 통계 제외</option></select></label><label>검토 근거<textarea name="basis" required maxlength="2000" ${state.admin?'':'disabled'}>${esc(r.mapping.basis)}</textarea></label><label>공식 근거 URL<input name="evidence_url" type="url" required maxlength="2000" value="${esc(r.mapping.evidence_url)}" ${state.admin?'':'disabled'}></label>${state.admin?'<div class="mapping-editor-actions"><button class="button primary" type="submit">프로그램–사업 저장</button><button class="button secondary" type="button" id="mapping-approve">담당자 최종 승인</button></div>':''}<p id="workbench-save-status" role="status"></p></form><div class="mapping-editor-links"><button class="text-button" data-project="${esc(r.id)}">사업 원문·수집 근거 ↗</button><button class="text-button" data-target-project="${esc(r.id)}">연도별 목표 ↗</button></div><details open><summary>프로그램 연결 변경 이력</summary><div id="mapping-audit-list">불러오는 중…</div></details>`;
    const form=$('workbench-form');form.elements.status.value=r.mapping.status;
    if(state.admin){form.addEventListener('submit',saveProject);$('mapping-approve').addEventListener('click',()=>{form.elements.status.value='CONFIRMED';form.requestSubmit();});}
    request('/projects/'+encodeURIComponent(r.id)+'?as_of_date='+encodeURIComponent($('as-of').value)).then(result=>{
      if(revision!==generation||!$('mapping-audit-list'))return;
      $('mapping-audit-list').innerHTML=(result.mapping_history||[]).map(h=>`<div class="mapping-audit"><b>${h.action==='MAPPING_AUTO'?'자동 제안':'담당자 조정'} · ${timeText(h.recorded_at)}</b><p>${esc(programName(h.before.program_id))} → ${esc(programName(h.after.program_id))} · ${badge(h.after.status)}</p><small>${esc(h.after.basis)}</small></div>`).join('')||'<p>원천 자동 연결 · 이후 담당자 변경 없음</p>';
    }).catch(error=>{if(revision===generation&&$('mapping-audit-list'))$('mapping-audit-list').textContent=error.message;});
  }
  async function saveProgram(event){
    event.preventDefault();if(saving)return;
    const p=program(selectedProgram),form=event.currentTarget,values=Object.fromEntries(new FormData(form));values.revision_no=p.revision_no;
    saving=true;$('program-policy-status').textContent='저장 중…';
    try{await request('/admin/programs/'+encodeURIComponent(p.id)+'/policy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(values)});await load();if($('program-policy-status'))$('program-policy-status').textContent='저장했습니다. 연결 사업의 정책 화면에도 반영됐습니다.';}
    catch(error){$('program-policy-status').textContent=error.message;}finally{saving=false;}
  }
  async function saveProject(event){
    event.preventDefault();if(saving)return;
    const r=payload.items.find(x=>x.id===selectedProject),values=Object.fromEntries(new FormData(event.currentTarget));values.revision_no=r.mapping.revision_no;
    saving=true;$('workbench-save-status').textContent='저장 중…';
    try{await request('/admin/projects/'+encodeURIComponent(r.id)+'/program',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(values)});await load();if($('workbench-save-status'))$('workbench-save-status').textContent='저장했습니다. 정책–프로그램–사업 흐름에 반영됐습니다.';}
    catch(error){$('workbench-save-status').textContent=error.message;}finally{saving=false;}
  }
  async function saveBulk(event){
    event.preventDefault();if(saving||!checked.size)return;
    const values=Object.fromEntries(new FormData(event.currentTarget)),selected=payload.items.filter(r=>checked.has(r.id));
    saving=true;let success=0,failures=[];
    for(const r of selected){
      try{await request('/admin/projects/'+encodeURIComponent(r.id)+'/program',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...values,program_id:values.program_id||r.mapping.program_id||'UNASSIGNED',revision_no:r.mapping.revision_no})});success++;checked.delete(r.id);}
      catch(error){failures.push(r.name+': '+error.message);}
      $('mapping-bulk-status').textContent=`${success}/${selected.length}건 저장 · 오류 ${failures.length}건`;
    }
    saving=false;await load();$('mapping-bulk-status').textContent=`${success}건 저장${failures.length?' · '+failures.join(' / '):' · 통계 반영 완료'}`;
  }
  function focusPolicy(id){
    if(!payload)return;
    if(id==='MON_THIRD_NEW_TOWN'||id==='MON_URBAN_COMPLEX'){
      setStage('project');$('mapping-queue-policy').value='';$('mapping-queue-programme').value='NAME:'+(id==='MON_THIRD_NEW_TOWN'?'3기 신도시':'도심 공공주택 복합사업');renderProjects();
    }else{setStage('policy');$('mapping-program-policy').value=id;renderPrograms();}
  }
  function focusProject(id){
    if(!payload)return;
    $('mapping-queue-status').value='';$('mapping-queue-policy').value='';$('mapping-queue-programme').value='';
    selectedProject=id;page=Math.floor(Math.max(0,payload.items.findIndex(r=>r.id===id))/30)+1;
    setStage('project');
  }
  function start(){
    $('mapping-tab-policy').addEventListener('click',()=>setStage('policy'));
    $('mapping-tab-project').addEventListener('click',()=>setStage('project'));
    for(const id of ['mapping-program-policy','mapping-program-status'])$(id).addEventListener('change',renderPrograms);
    for(const id of ['mapping-queue-status','mapping-queue-programme','mapping-queue-policy'])$(id).addEventListener('change',()=>{page=1;renderProjects();});
    $('mapping-queue-prev').addEventListener('click',()=>{page--;renderProjects();});$('mapping-queue-next').addEventListener('click',()=>{page++;renderProjects();});
    $('mapping-bulk').addEventListener('submit',saveBulk);
    document.addEventListener('click',event=>{
      const p=event.target.closest('[data-program-edit]');if(p){selectedProgram=p.dataset.programEdit;renderPrograms();}
      const r=event.target.closest('[data-mapping-edit]');if(r){selectedProject=r.dataset.mappingEdit;renderProjects();}
      const jump=event.target.closest('[data-show-program-projects]');if(jump){setStage('project');$('mapping-queue-programme').value=jump.dataset.showProgramProjects;renderProjects();}
    });
    document.addEventListener('change',event=>{
      const box=event.target.closest('[data-mapping-check]');if(box){box.checked?checked.add(box.dataset.mappingCheck):checked.delete(box.dataset.mappingCheck);$('mapping-bulk-save').disabled=saving||!checked.size;}
      if(event.target.id==='mapping-select-page'){for(const r of filteredProjects().slice((page-1)*30,page*30))event.target.checked?checked.add(r.id):checked.delete(r.id);renderProjects();}
    });
  }
  return {render,start,focusPolicy,focusProject};
})();
