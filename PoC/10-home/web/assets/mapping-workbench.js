'use strict';
const MappingWorkbench=(()=>{
  let payload, stage='policy', selectedProgram, selectedProject, page=1, saving=false, generation=0;
  let pendingFocus=null;
  const checked=new Set();
  const policyId='POL_2025_0907';
  const enabledProgram=p=>Boolean(p&&p.policy_id===policyId&&p.selection_enabled!==false&&!['RELEASED','REJECTED'].includes(p.status));
  const enabledProject=p=>Boolean(p&&p.mapping.policy_id===policyId&&Number.isFinite(p.planned_units)&&p.planned_units>0&&!['RELEASED','REJECTED'].includes(p.mapping.status));
  const editButton=(kind,id,label,enabled=true)=>state.admin?`<button type="button" class="button primary mapping-info-edit ${kind}" data-mapping-info="${kind}" data-info-id="${esc(id)}" aria-haspopup="dialog" ${enabled?'':'disabled'}>✎ ${label}수정</button>`:'';
  const realPolicies=()=>payload.policies.filter(p=>p.monitor_kind==='POLICY');
  const policyName=id=>id==='UNASSIGNED'||!id?'정책 미연계':payload.policies.find(p=>p.policy_id===id)?.name||'정책 미확인';
  const seedName=id=>id?.startsWith('MON_')?'프로그램 원점: '+policyName(id):policyName(id);
  const program=id=>payload.programs.find(p=>p.id===id);
  const programName=id=>id==='UNASSIGNED'||!id?'프로그램 미연계':program(id)?.name||'프로그램 확인 필요';
  const options=(rows,selected,key,label)=>rows.map(row=>`<option value="${esc(row[key])}" ${row[key]===selected?'selected':''} ${(key==='policy_id'?row.policy_id!==policyId:!enabledProgram(row))?'disabled':''}>${esc(label(row))}${(key==='policy_id'?row.policy_id!==policyId:!enabledProgram(row))?' (비활성)':''}</option>`).join('');
  const programLabel=p=>`${p.name} · ${policyName(p.policy_id)}${p.seed_policy_id!==p.policy_id?' (원천 제안과 다름)':''}`;
  function setStage(value){
    stage=value;
    $('mapping-operations-workspace').hidden=stage!=='operations';
    $('mapping-tab-operations').setAttribute('aria-selected',String(stage==='operations'));
    $('mapping-evidence-workspace').hidden=stage!=='evidence';
    $('mapping-tab-evidence').setAttribute('aria-selected',String(stage==='evidence'));
    $('mapping-policy-workspace').hidden=stage!=='policy';
    $('mapping-project-workspace').hidden=stage!=='project';
    $('mapping-tab-policy').setAttribute('aria-selected',String(stage==='policy'));
    $('mapping-tab-project').setAttribute('aria-selected',String(stage==='project'));
    if(stage==='evidence')StageEvidenceWorkbench.load();
    else if(stage==='operations')DeliveryOperations.load();
    else if(payload)stage==='policy'?renderPrograms():renderProjects();
  }
  function render(data){
    payload=data;
    for(const id of checked)if(!data.items.some(r=>r.id===id))checked.delete(id);
    $('mapping-program-policy').innerHTML=''+options(realPolicies(),null,'policy_id',p=>p.name);
    $('mapping-program-policy').value=policyId;
    $('mapping-queue-policy').innerHTML=''+options(realPolicies(),null,'policy_id',p=>p.name);
    $('mapping-queue-policy').value=policyId;
    const queueProgram=$('mapping-queue-programme').value;
    $('mapping-queue-programme').innerHTML='<option value="">프로그램 전체</option>'+options(data.programs,null,'id',programLabel);
    $('mapping-queue-programme').value=enabledProgram(program(queueProgram))?queueProgram:'';
    $('mapping-bulk-program').innerHTML='<option value="">현재 연결 유지</option>'+options(data.programs,null,'id',programLabel);
    $('mapping-queue-counts').innerHTML=[['사업 승인 대기',data.counts.REVIEW||0],['사업 확정',data.counts.CONFIRMED||0],['프로그램 미연계 사업',data.audit.unlinked_projects],['정책 미연계 사업',data.audit.unlinked_policy_projects]].map(([name,n])=>`<div><span>${esc(name)}</span><strong>${num(n)}건</strong></div>`).join('');
    $('mapping-program-counts').innerHTML=[['정책–프로그램 승인 대기',data.audit.review_programs],['프로그램–사업 승인 대기',data.audit.review_projects],['정책 미연계 프로그램',data.audit.unlinked_programs]].map(([name,n])=>`<div><span>${esc(name)}</span><strong>${num(n)}건</strong></div>`).join('');
    $('mapping-queue-notice').textContent='현재 정책–프로그램 미연계 '+num(data.audit.unlinked_programs)+'건 · 프로그램–사업 미연계 '+num(data.audit.unlinked_projects)+'건. 연결된 REVIEW는 미연계가 아니라 담당자 승인 대기입니다. '+data.notice;
    $('mapping-bulk').hidden=true;
    if(pendingFocus){const focus=pendingFocus;pendingFocus=null;focus.kind==='project'?focusProject(focus.id):focusPolicy(focus.id);}else setStage(stage);
  }
  function filteredPrograms(){return payload.programs.filter(p=>(!$('mapping-program-status').value||p.status===$('mapping-program-status').value)&&(!$('mapping-program-policy').value||p.policy_id===$('mapping-program-policy').value));}
  function renderPrograms(){
    const rows=filteredPrograms();
    if(!rows.some(p=>p.id===selectedProgram&&enabledProgram(p)))selectedProgram=rows.find(enabledProgram)?.id;
    $('mapping-program-list').innerHTML=rows.length?`<table><thead><tr><th>프로그램 / 연결 사업</th><th>상위 정책</th><th>상태</th></tr></thead><tbody>${rows.map(p=>`<tr class="${p.id===selectedProgram?'selected':''}"><td><button class="mapping-program-list-row" data-program-edit="${esc(p.id)}" ${enabledProgram(p)?'':'disabled'}><b>${esc(p.name)}</b><small>연결 ${num(p.project_count)}건 · 통계 반영 ${num(p.active_project_count)}건</small></button>${editButton('program',p.id,'프로그램정보',enabledProgram(p))}</td><td class="${p.policy_id==='UNASSIGNED'?'mapping-program-unlinked':''}">${esc(policyName(p.policy_id))}${editButton('policy',p.policy_id,'정책정보',p.policy_id===policyId)}<small class="row-sub">원천 제안 ${esc(seedName(p.seed_policy_id))}</small></td><td>${badge(p.status)}</td></tr>`).join('')}</tbody></table>`:empty('해당 정책·상태의 프로그램이 없습니다.');
    renderProgramEditor();
  }
  function renderProgramEditor(){
    const p=program(selectedProgram),node=$('mapping-program-editor');generation++;
    if(!enabledProgram(p)){node.innerHTML=empty('활성 프로그램을 선택하세요.');return;}
    node.innerHTML=`<p class="section-kicker">정책 → 프로그램</p><div class="mapping-info-heading"><h3>${esc(policyName(p.policy_id))}</h3>${editButton('policy',p.policy_id,'정책정보')}</div><div class="mapping-info-heading"><h3>${esc(p.name)}</h3>${editButton('program',p.id,'프로그램정보')}</div><p>연결 사업 ${num(p.project_count)}건 · ${badge(p.status)}</p><p>수정 버튼에서 정보·목표·연결을 편집하며 기존 변경 이력을 함께 확인할 수 있습니다.</p><button type="button" class="text-button" data-show-program-projects="${esc(p.id)}">연결 사업 보기 ↗</button>`;
  }
  function filteredProjects(){return payload.items.filter(r=>(!$('mapping-queue-status').value||r.mapping.status===$('mapping-queue-status').value)&&(!$('mapping-queue-policy').value||r.mapping.policy_id===$('mapping-queue-policy').value)&&(!$('mapping-queue-programme').value||($('mapping-queue-programme').value.startsWith('NAME:')?r.program===$('mapping-queue-programme').value.slice(5):r.mapping.program_id===$('mapping-queue-programme').value)));}
  function renderProjects(){
    const rows=filteredProjects();page=Math.max(1,Math.min(page,Math.ceil(rows.length/30)||1));
    if(!rows.some(r=>r.id===selectedProject&&enabledProject(r)))selectedProject=rows.find(enabledProject)?.id;
    const visible=rows.slice((page-1)*30,page*30);
    $('mapping-queue-list').innerHTML=visible.length?`<table><thead><tr><th>사업 / 원천 프로그램</th><th>연결 프로그램 → 정책</th></tr></thead><tbody>${visible.map(r=>`<tr class="${r.id===selectedProject?'selected':''}"><td><button class="project-name" data-mapping-edit="${esc(r.id)}" ${enabledProject(r)?'':'disabled'}>${esc(r.name)}${enabledProject(r)?'':' (비활성)'}</button>${editButton('project',r.id,'사업정보',enabledProject(r))}<small class="row-sub">${esc(r.region)} · 목표 ${r.planned_units==null?'미확보':num(r.planned_units)+'호'}</small></td><td>${esc(programName(r.mapping.program_id))}${editButton('program',r.mapping.program_id,'프로그램정보',enabledProgram(program(r.mapping.program_id)))}<small class="row-sub">${esc(policyName(r.mapping.policy_id))} · ${badge(r.mapping.status)}</small>${editButton('policy',r.mapping.policy_id,'정책정보',r.mapping.policy_id===policyId)}</td></tr>`).join('')}</tbody></table>`:empty('해당 조건의 사업이 없습니다.');
    $('mapping-queue-page').textContent=`${page}/${Math.ceil(rows.length/30)||1} · 조회 ${num(rows.length)}건 · 선택 ${num(checked.size)}건`;
    $('mapping-queue-prev').disabled=page===1;$('mapping-queue-next').disabled=page*30>=rows.length;$('mapping-bulk-save').disabled=saving||!checked.size;
    renderProjectEditor();
  }
  function renderProjectEditor(){
    const r=payload.items.find(x=>x.id===selectedProject),node=$('mapping-editor');generation++;
    if(!enabledProject(r)){node.innerHTML=empty('목표량이 있는 활성 사업을 선택하세요.');return;}
    const p=program(r.mapping.program_id);
    node.innerHTML=`<p class="section-kicker">정책 → 프로그램 → 사업</p><div class="mapping-info-heading"><h3>${esc(policyName(r.mapping.policy_id))}</h3>${editButton('policy',r.mapping.policy_id,'정책정보')}</div><div class="mapping-info-heading"><h3>${esc(programName(r.mapping.program_id))}</h3>${editButton('program',r.mapping.program_id,'프로그램정보',enabledProgram(p))}</div><div class="mapping-info-heading"><h3>${esc(r.name)}</h3>${editButton('project',r.id,'사업정보')}</div><p>목표 ${num(r.planned_units)}호 · ${badge(r.mapping.status)}</p><p>사업정보수정에서 상위 프로그램 연결·목표·측정값을 수정합니다.</p>`;
  }
  async function openInformation(kind,id){
    if(!state.admin||document.querySelector('dialog[open]'))return;
    if(kind==='policy'&&id===policyId)await PolicyInformation.open();
    else if(kind==='program'&&enabledProgram(program(id)))await ProgramInformation.open(id);
    else if(kind==='project'&&enabledProject(payload.items.find(p=>p.id===id))){await ProjectWorkspace.openEditor(id,async()=>load());return;}
    else return;
    document.querySelector('#'+kind+'-information-dialog')?.addEventListener('close',()=>load(),{once:true});
  }
  function focusPolicy(id){
    if(!payload){pendingFocus={kind:'policy',id};return;}
    if(id!==policyId)return;
    setStage('policy');$('mapping-program-policy').value=id;renderPrograms();
  }
  function focusProject(id){
    if(!payload){pendingFocus={kind:'project',id};return;}
    if(!enabledProject(payload.items.find(r=>r.id===id)))return;
    $('mapping-queue-status').value='';$('mapping-queue-policy').value=policyId;$('mapping-queue-programme').value='';
    selectedProject=id;page=Math.floor(Math.max(0,filteredProjects().findIndex(r=>r.id===id))/30)+1;
    setStage('project');
  }
  function start(){
    $('mapping-tab-operations').addEventListener('click',()=>setStage('operations'));
    $('mapping-tab-evidence').addEventListener('click',()=>setStage('evidence'));
    $('mapping-tab-policy').addEventListener('click',()=>setStage('policy'));
    $('mapping-tab-project').addEventListener('click',()=>setStage('project'));
    for(const id of ['mapping-program-policy','mapping-program-status'])$(id).addEventListener('change',renderPrograms);
    for(const id of ['mapping-queue-status','mapping-queue-programme','mapping-queue-policy'])$(id).addEventListener('change',()=>{page=1;renderProjects();});
    $('mapping-queue-prev').addEventListener('click',()=>{page--;renderProjects();});$('mapping-queue-next').addEventListener('click',()=>{page++;renderProjects();});

    document.addEventListener('click',event=>{
      const info=event.target.closest('[data-mapping-info]');if(info&&!info.disabled){openInformation(info.dataset.mappingInfo,info.dataset.infoId);return;}
      const p=event.target.closest('[data-program-edit]');if(p&&!p.disabled){selectedProgram=p.dataset.programEdit;renderPrograms();}
      const r=event.target.closest('[data-mapping-edit]');if(r&&!r.disabled){selectedProject=r.dataset.mappingEdit;renderProjects();}
      const jump=event.target.closest('[data-show-program-projects]');if(jump){setStage('project');$('mapping-queue-programme').value=jump.dataset.showProgramProjects;renderProjects();}
    });

  }
  return {render,start,focusPolicy,focusProject};
})();
