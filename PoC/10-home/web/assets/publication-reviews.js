'use strict';
const PublicationReviews=(()=>{
 let data=null,selected=null,filter='OPEN',search='',priority='',busy=false,dirty=false,generation=0,exporting=false;
 const e=v=>esc(v),host=()=>$('publication-review-root');
 const stateLabel=s=>data?.status_labels[s]||s;
 async function refreshBadge(){try{const r=await request('/publication-reviews/summary');const badge=$('publication-review-badge');badge.textContent=r.pending;badge.hidden=!r.pending;badge.title='검토 대기·보류·사업 등록 대기';}catch{$('publication-review-badge').textContent='!';$('publication-review-badge').hidden=false;}}
 function canLeave(){return !dirty||window.confirm('저장하지 않은 검토 내용이 있습니다. 변경 내용을 버리고 이동할까요?');}
 async function load(){
  const token=++generation;host().innerHTML='<p role="status">신규 자료와 검토 기록을 불러오고 있습니다.</p>';
  try{const value=await request('/publication-reviews');if(token!==generation)return;data=value;if(!selected||!data.items.some(r=>r.id===selected))selected=data.items.find(r=>r.status==='REVIEW')?.id||data.items[0]?.id;dirty=false;render();refreshBadge();}
  catch(error){if(token!==generation)return;host().innerHTML='<p role="alert">'+e(error.message)+'</p><button type="button" class="button secondary" data-pr-retry>다시 조회</button>';host().querySelector('button').onclick=load;}
 }
 function render(){
  host().innerHTML='<header class="pr-head"><div><p class="pr-eyebrow">자료 발견 → 담당자 검토 → 사업 연결</p><h2>신규 자료 검토</h2><p>새로 수집한 자료가 어느 주택사업의 근거인지 판단하는 화면입니다. 왼쪽에서 자료를 고르면 오른쪽에 확인할 질문과 처리 방법이 나옵니다.</p></div><button type="button" class="button secondary" data-pr-refresh>새로고침</button></header>'+
   '<div id="ai-collection-root"></div>'+
   '<div class="pr-counts">'+[['REVIEW','검토 대기'],['HOLD','보류'],['REGISTRATION_REQUIRED','사업 등록 대기'],['APPROVED','자료 연결 승인'],['EXCLUDED','제외']].map(([k,l])=>'<button type="button" data-pr-status="'+k+'" aria-pressed="'+(filter===k)+'"><span>'+l+'</span><strong>'+num(data.counts[k]||0)+'</strong></button>').join('')+'</div>'+
   '<div class="pr-toolbar"><label>검토 상태<select id="pr-status"><option value="OPEN">미완료 전체</option><option value="ALL">전체</option>'+Object.entries(data.status_labels).map(([v,t])=>'<option value="'+v+'">'+e(t)+'</option>').join('')+'</select></label><label>우선순위<select id="pr-priority"><option value="">전체</option><option value="1">1 · 계획 누락 확인</option><option value="2">2 · 귀속·단계 확인</option><option value="3">3 · 범위·중복 확인</option><option value="4">참고·관련성 분류</option></select></label><label class="pr-search">자료 검색<input id="pr-search" type="search" maxlength="500" placeholder="제목·출처·검토 내용"></label></div><p id="pr-result" role="status"></p>'+
   '<div class="pr-export"><div><strong>외부 검증용 CSV</strong><p>상태별 목록·원문 URL·검토 사유·사업 정보·판단 이력을 받습니다. 저장된 결과 기준이며, 현재 목록에는 검색·우선순위 조건도 적용됩니다.</p></div><div class="pr-export-actions"><button type="button" class="button secondary" id="pr-export-current">현재 목록 CSV</button><button type="button" class="button secondary" id="pr-export-all">전체 상태 CSV</button></div></div><p id="pr-export-result" role="status" aria-live="polite"></p>'+
   '<div class="pr-workspace"><div id="pr-list" aria-label="검토 대상 목록"></div><article id="pr-detail" class="pr-detail" aria-label="원문과 검토 결과"></article></div>';
  $('pr-status').value=filter;$('pr-priority').value=priority;$('pr-search').value=search;
  $('pr-status').onchange=event=>{filter=event.target.value;renderList();};$('pr-priority').onchange=event=>{priority=event.target.value;renderList();};$('pr-search').oninput=event=>{search=event.target.value;renderList();};
  host().querySelector('[data-pr-refresh]').onclick=()=>{if(canLeave())load();};
  host().querySelectorAll('[data-pr-status]').forEach(b=>b.onclick=()=>{filter=b.dataset.prStatus;$('pr-status').value=filter;renderList();});
  $('pr-export-current').onclick=()=>downloadCsv(false);$('pr-export-all').onclick=()=>downloadCsv(true);
  renderList();renderDetail();AICollection.mount($('ai-collection-root'));
 }
 function renderList(){
  const open=new Set(['REVIEW','HOLD','REGISTRATION_REQUIRED']);
  const rows=data.items.filter(r=>(filter==='ALL'||filter==='OPEN'&&open.has(r.status)||r.status===filter)&&(!priority||String(r.priority)===priority)&&(!search||[r.title,r.source_name,r.question,r.decision?.reason].join(' ').toLowerCase().includes(search.toLowerCase())));
  const exportLabel=filter==='ALL'?'전체':filter==='OPEN'?'미완료':stateLabel(filter);
  $('pr-export-current').textContent=exportLabel+' CSV · '+num(rows.length)+'건';
  $('pr-export-current').disabled=exporting;$('pr-export-all').disabled=exporting;
  $('pr-result').textContent='조회 '+rows.length+'건 / 전체 '+data.total+'건 · 우선순위는 제목 기반 검토 제안이며 사업 동일성 확정이 아닙니다.';
  $('pr-list').innerHTML=rows.map(r=>'<button type="button" class="pr-item" data-pr-id="'+e(r.id)+'" aria-pressed="'+(selected===r.id)+'"><span class="pr-item-top"><span class="pr-priority p'+r.priority+'">'+(r.priority<4?'우선 '+r.priority:'참고')+'</span><span class="pr-state">'+e(r.status_label)+'</span></span><strong>'+e(r.title)+'</strong><small>'+e(r.source_date)+' · '+e(r.authority==='OFFICIAL'?'공식 자료':'언론 자료')+'</small><span>'+e(r.guidance?.decision||r.review_topic)+'</span>'+(r.source_changed?'<em>원문 새 판본 · 재검토 필요</em>':'')+'</button>').join('')||'<p class="pr-empty">조건에 맞는 자료가 없습니다.</p>';
  $('pr-list').querySelectorAll('[data-pr-id]').forEach(b=>b.onclick=()=>{if(!canLeave())return;selected=b.dataset.prId;dirty=false;renderList();renderDetail();});
  host().querySelectorAll('[data-pr-status]').forEach(b=>b.setAttribute('aria-pressed',String(filter===b.dataset.prStatus)));
 }
 async function downloadCsv(all){
  if(exporting)return;
  const params=new URLSearchParams({status:all?'ALL':filter});
  if(!all&&priority)params.set('priority',priority);
  if(!all&&search)params.set('search',search);
  exporting=true;$('pr-export-current').disabled=true;$('pr-export-all').disabled=true;
  $('pr-export-result').textContent='저장된 검토 결과와 근거를 모아 CSV를 생성하고 있습니다…';
  try{
   const response=await fetch(API+'/publication-reviews/export.csv?'+params,{credentials:'same-origin'});
   if(!response.ok){const error=await response.json().catch(()=>({}));throw new Error(typeof error.detail==='string'?error.detail:'CSV 생성에 실패했습니다. 다시 시도해 주세요.');}
   const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');
   link.href=url;link.download=response.headers.get('content-disposition')?.match(/filename="([^"]+)"/)?.[1]||'home-publication-reviews.csv';
   document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
   $('pr-export-result').textContent='CSV 다운로드 완료 · 본문 미보유 자료는 원문 URL에서 확인하세요. 외부 검증결과·검증사유·추가확인사항 열에 검토 내용을 적을 수 있습니다.';
  }catch(error){$('pr-export-result').textContent=error.message;}
  finally{exporting=false;if($('pr-export-current'))renderList();}
 }
 function renderDetail(){
  const r=data.items.find(r=>r.id===selected),root=$('pr-detail');if(!r){root.innerHTML='<p>검토할 자료를 선택하세요.</p>';return;}
  const d=r.decision||{},g=r.guidance||{decision:r.question,why:r.review_topic,checks:[],dataset_summary:'원문과 기존 사업을 대조하세요.',basis:'수집 제목 기준 안내',event:'원문 확인 필요',reason_hint:'확인한 사실과 판단 사유를 적어 주세요.',next_step:'확인 결과에 맞는 처리를 선택하세요.'},chosen=new Set(d.project_ids||[]),proposed=new Set(r.candidates.map(p=>p.id));
  const projects=[...data.projects].sort((a,b)=>Number(proposed.has(b.id))-Number(proposed.has(a.id))||a.name.localeCompare(b.name,'ko'));
  const actionLabels={REVIEW:'아직 검토 전 · 아래에서 처리 방법 선택',APPROVED:'기존 사업의 자료로 연결',REGISTRATION_REQUIRED:'새 사업 등록 검토로 넘기기',HOLD:'근거가 더 필요하여 보류',EXCLUDED:'사업 검토 대상에서 제외'};
  const mappingLabels={CONFIRMED:'확정',REVIEW:'검토 중',UNASSIGNED:'미지정',EXCLUDED:'제외',REJECTED:'반려'};
  root.innerHTML=`<div class="pr-detail-top"><span class="pr-priority p${r.priority}">${r.priority<4?'우선순위 '+r.priority:'참고 분류'}</span><span>${e(r.status_label)}</span></div>
   <h3 tabindex="-1">${e(r.title)}</h3><p class="pr-meta">${e(r.source_name)} · 게시일 ${e(r.source_date)} · 원문 판본 ${r.source_revision_no}</p>
   ${AICollection.analysis(r.ai_analysis)}
   <section class="pr-question"><span class="pr-kicker">이번 자료에서 결정할 한 가지</span><h4>${e(g.decision)}</h4><p>${e(g.why)}</p><small>${e(g.basis)}</small>
    ${r.link_changed?'<p><strong>다른 화면에서 연결이 변경됐습니다.</strong> 현재 연결 상태를 다시 확인하세요.</p>':''}
    ${r.source_changed?'<p><strong>새 원문 판본이 수집됐습니다.</strong> 이전 결정은 보존되며 현재 자료는 재검토 대기입니다.</p>':''}</section>
   <section class="pr-source-step"><h4><span class="pr-step">1</span> 원문에서 이 항목을 확인하세요</h4>
    <p class="pr-event">자료의 주제 <strong>${e(g.event)}</strong></p>
    <ol class="pr-checklist">${g.checks.map(t=>`<li>${e(t)}</li>`).join('')}</ol>
    <a class="button secondary" href="${e(safeUrl(r.evidence_url))}" target="_blank" rel="noopener noreferrer">${r.authority==='OFFICIAL'?'공식 원문':'언론 원문'} 열고 대조하기 ↗</a>
    ${r.supplement?`<details class="pr-basis pr-collected"><summary>수동 수집 원문·첨부 확인${r.supplement.stale?' · 이전 판본 재확인 필요':''}</summary><p>${e(r.supplement.summary)}</p><small>원문 판본 ${r.supplement.source_revision_no} · 수집 ${e(new Date(r.supplement.collected_at).toLocaleString('ko-KR'))} · 사업·실적 승인과 별도</small><ul>${r.supplement.attachments.map(a=>`<li><a href="${e(safeUrl(a.url))}" target="_blank" rel="noopener noreferrer">${e(a.name)} ↗</a></li>`).join('')}</ul><p>수집 본문과 첨부 정보는 외부 검증용 CSV에도 포함됩니다.</p></details>`:''}
   </section>
   <section><h4><span class="pr-step">2</span> 현재 데이터와 비교하세요</h4><p class="pr-dataset-summary">${e(g.dataset_summary)}</p>
    ${r.candidates.length?r.candidates.map(p=>`<div class="pr-candidate"><div class="pr-candidate-heading"><strong>${e(p.name)}</strong><span>이름 유사 · 동일성 미확정</span></div>
     <dl class="pr-existing"><div><dt>등록 지역</dt><dd>${e(p.region||'미확인')}</dd></div><div><dt>등록 계획량</dt><dd>${p.units==null?'미확인':num(p.units)+'호'}</dd></div><div><dt>연결 정책</dt><dd>${e(p.policy_name||'미지정')}</dd></div><div><dt>정책 연결 상태</dt><dd>${e(mappingLabels[p.mapping_status]||p.mapping_status||'미확인')}</dd></div></dl>
     <details class="pr-basis"><summary>이전 판단 사유 보기</summary><p>${e(p.mapping_basis||'저장된 연결 사유 없음')}</p></details>
     <button type="button" class="text-button" data-pr-mapping="${e(p.id)}">사업 상세·정책 연결 검토 →</button></div>`).join(''):'<div class="pr-no-match">후보가 없다는 이유만으로 미수집·신규 사업으로 확정하지 않습니다. 아래에서 「기존 사업의 자료로 연결」을 선택하면 전체 사업을 검색할 수 있습니다.</div>'}
   </section>
   <section class="pr-decision"><h4><span class="pr-step">3</span> 확인 결과에 맞게 처리하세요</h4><p class="pr-next-step">${e(g.next_step)}</p>
    <div class="pr-action-guide"><div><strong>같은 사업을 찾았다면</strong><span>기존 사업에 자료 연결</span></div><div><strong>새 사업 등록이 필요하면</strong><span>사업 등록 검토로 전달</span></div><div><strong>아직 판단이 어려우면</strong><span>필요한 근거를 적고 보류</span></div><div><strong>사업과 관계없는 소식이면</strong><span>제외 사유를 남기고 제외</span></div></div>
    ${!state.admin?'<p class="pr-login">검토 안내와 기존 자료는 로그인 없이 볼 수 있습니다. 결과 저장은 상단 관리자 로그인 후 가능합니다.</p>':''}
    <form id="pr-form"><fieldset ${state.admin?'':'disabled'}><label>이 자료를 어떻게 처리할까요?<select name="status">${Object.entries(actionLabels).map(([v,t])=>`<option value="${v}" ${v===r.status?'selected':''}>${e(t)}</option>`).join('')}</select></label><p id="pr-effect" class="pr-effect"></p>
     <div data-pr-fields="policy"><label>검토 대상 정책<select name="policy_id"><option value="">정책 선택</option><option value="UNASSIGNED" ${d.policy_id==='UNASSIGNED'?'selected':''}>정책 미지정 · 귀속 별도 확인</option>${data.policies.map(p=>`<option value="${e(p.id)}" ${p.id===d.policy_id?'selected':''}>${e(p.name)}</option>`).join('')}</select></label></div>
     <div data-pr-fields="existing"><label>자료를 연결할 기존 사업 검색<input type="search" id="pr-project-search" placeholder="등록 사업명·지역으로 검색"></label><small>주소·별칭은 사업 상세와 원문을 함께 확인하세요. 이름 유사 후보는 자동 선택하지 않습니다.</small>
      <div class="pr-project-options" role="group" aria-label="연결할 기존 사업 복수 선택">${projects.map(p=>`<label data-pr-project="${e(p.name+' '+(p.region||''))}"><input type="checkbox" name="project_ids" value="${e(p.id)}" ${chosen.has(p.id)?'checked':''}><span>${e(p.name)}${proposed.has(p.id)?' <small>이름 유사 후보 · 구역 대조 필요</small>':''}<small>${e(p.region||'')} · ${e(mappingLabels[p.mapping_status]||p.mapping_status||'미연결')}</small></span></label>`).join('')}</div></div>
     <div data-pr-fields="new"><label>등록 검토할 정확한 사업명<textarea name="new_project_names" rows="2" maxlength="3000" placeholder="원문에서 확인한 구역·단지별 사업명을 한 줄에 하나씩 적어 주세요.">${e((d.new_project_names||[]).join('\n'))}</textarea></label><small>후속 등록 대기에 남습니다. 이 버튼만으로 사업·호수·일정이 등록되지는 않습니다.</small></div>
     <div data-pr-fields="record"><label>담당자<input name="actor" required maxlength="100" value="${e(d.actor||'')}" autocomplete="name"></label><label>확인한 내용과 판단 사유<textarea name="reason" required minlength="5" maxlength="2000" rows="4" placeholder="${e(g.reason_hint)}">${e(d.reason||'')}</textarea></label></div>
     <div data-pr-fields="checked"><label class="pr-check"><input type="checkbox" name="source_checked">현재 원문과 선택한 사업·정책의 적용 범위를 확인했습니다.</label></div>
     <button class="button primary" type="submit">검토 결과 저장</button></fieldset><p id="pr-save-result" role="status" aria-live="polite"></p></form></section>
   <details class="pr-history"><summary>이 자료의 이전 검토 이력 보기</summary><div id="pr-history-body">펼치면 이력을 조회합니다.</div></details>`;
  root.querySelectorAll('[data-pr-mapping]').forEach(b=>b.onclick=()=>{if(canLeave()){MappingWorkbench.focusProject(b.dataset.prMapping);setView('tree');}});
  const form=$('pr-form');form.oninput=()=>{dirty=true;};form.onchange=()=>{dirty=true;effect();};form.onsubmit=save;
  $('pr-project-search').oninput=event=>{const q=event.target.value.toLowerCase();root.querySelectorAll('[data-pr-project]').forEach(el=>{el.hidden=!el.dataset.prProject.toLowerCase().includes(q);});};
  function effect(){
   const status=form.elements.status.value,approved=['APPROVED','REGISTRATION_REQUIRED'].includes(status),registration=status==='REGISTRATION_REQUIRED';
   const visible={policy:approved,existing:approved,new:registration,record:status!=='REVIEW',checked:approved};
   root.querySelectorAll('[data-pr-fields]').forEach(el=>{const show=visible[el.dataset.prFields];el.hidden=!show;el.querySelectorAll('input,select,textarea').forEach(input=>{input.disabled=!show;});});
   form.elements.policy_id.required=approved;form.elements.source_checked.required=approved;form.elements.new_project_names.required=registration;
   form.querySelector('button[type=submit]').disabled=!state.admin||status==='REVIEW';
   const messages={REGISTRATION_REQUIRED:'식별된 사업·주택자산을 등록 검토 대기에 남깁니다. 정책 귀속이 확인되지 않았다면 ‘정책 미지정’을 선택하세요. 사업·호수·실적은 자동 생성되지 않습니다.',HOLD:'무엇을 더 확인해야 하는지 적어 주세요. 보류 목록에서 계속 확인할 수 있습니다.',EXCLUDED:'개별 주택사업의 검토 근거로 사용하지 않는 이유를 적어 주세요.'};
   messages.REVIEW='1번 원문 확인과 2번 기존 사업 대조를 마치면 위에서 처리 방법을 선택하세요.';
   messages.APPROVED='선택한 기존 사업에 이 자료를 연결합니다. 정책 귀속·목표·실적 수치 변경은 별도 검토가 필요합니다.';
   $('pr-effect').textContent=messages[status]+(d.status==='APPROVED'&&!['REVIEW','APPROVED'].includes(status)?' 저장하면 이 검토함에서 승인했던 자료 연결은 해제됩니다.':'');
   form.elements.reason.placeholder=status==='HOLD'?'미확인 항목 / 판단을 위해 추가로 필요한 자료·담당자 확인 내용을 적어 주세요.':status==='EXCLUDED'?'예: 개별 주택사업의 추진 사실과 관련 없는 교육·홍보 소식임. 실제 확인한 제외 사유를 적어 주세요.':g.reason_hint;
  }
  effect();const detail=root.querySelector('.pr-history');detail.ontoggle=async()=>{if(!detail.open)return;try{const value=await request('/publication-reviews/'+encodeURIComponent(r.id)+'/history');if(selected!==r.id)return;$('pr-history-body').innerHTML=value.items.map(i=>'<div><strong>'+e(stateLabel(i.status))+' · '+e(i.actor)+'</strong><small>'+e(new Date(i.recorded_at).toLocaleString('ko-KR'))+' · 원문 판본 '+i.source_revision_no+'</small><p>'+e(i.reason)+'</p><p>'+e(i.effect)+'</p></div>').join('')||'<p>아직 저장된 검토 이력이 없습니다.</p>';}catch(error){if(selected===r.id)$('pr-history-body').textContent=error.message;}};
 }
 async function save(event){
  event.preventDefault();if(busy||!state.admin)return;const form=event.target;if(!form.reportValidity())return;const r=data.items.find(x=>x.id===selected),values=new FormData(form),payload={source_revision_no:r.source_revision_no,review_revision_no:r.review_revision_no,status:values.get('status'),policy_id:values.get('policy_id')||null,project_ids:values.getAll('project_ids'),new_project_names:String(values.get('new_project_names')||'').split('\n').map(v=>v.trim()).filter(Boolean),actor:values.get('actor'),reason:values.get('reason'),source_checked:values.get('source_checked')==='on'};
  if(payload.status==='APPROVED')payload.new_project_names=[];
  if(payload.status==='APPROVED'&&!payload.project_ids.length){$('pr-save-result').textContent='기존 사업을 선택하세요. 대응 사업이 없으면 사업 등록 대기로 검토 승인하세요.';return;}
  busy=true;form.querySelector('button[type=submit]').disabled=true;$('pr-save-result').textContent='검토 결과를 저장하고 있습니다…';
  try{const saved=await request('/admin/publication-reviews/'+encodeURIComponent(r.id),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});dirty=false;await load();$('pr-save-result').textContent='저장 완료 · '+saved.effect;}
  catch(error){$('pr-save-result').textContent=error.message+' 입력 내용은 유지됩니다. 원문·검토 기록 충돌이면 새로고침 후 다시 확인하세요.';}
  finally{busy=false;const button=host().querySelector('button[type=submit]');if(button)button.disabled=!state.admin||host().querySelector('[name=status]').value==='REVIEW';}
 }
 return {load,refreshBadge,canLeave};
})();
