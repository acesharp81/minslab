const isTourPreview = new URLSearchParams(location.search).has('walkthrough');
const $ = (s, parent = document) => parent.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {cases:[], config:{}, current:null, details:null, revision:null, tab:'sources', employee:localStorage.getItem('handover-employee') || 'employee1', role:'predecessor', timer:null};
const modelLabel = model => ({'solar-pro4':'Solar Pro 4','solar-mini4':'Solar Mini 4'}[model] || model);
const labels = {title:'업무명',status:'현재 상태',due_date:'기한',owner:'담당',next_action:'다음 행동',notes:'참고 사항',completed_work:'완료한 일·산출물',remaining_work:'남은 업무',issues:'현안·장애 사항',collaborators:'협의·협업 부서',contacts:'연락처'};
Object.assign(labels,{overview:'업무 개요',objectives:'목표',scope:'업무 범위',implementation_plan:'추진 계획',performance:'성과 지표',future_plan:'추후 계획',operating_steps:'실무 처리 순서',completion_criteria:'완료 기준',deliverables:'인계 산출물',issue_history:'현안 경과',approval_route:'보고·결재 체계',document_locations:'자료 위치·접근 방법',budget:'예산 현황'});
const statuses = {PENDING:['대기','gray'],SUCCESS:['추출 완료','green'],PARTIAL:['부분 추출','orange'],FAILED:['추출 실패','red'],UNSUPPORTED:['미지원','gray']};
const date = value => value ? new Date(value).toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) : '—';
const apiBase = new URL('api/', location.href);
const apiUrl = path => new URL(path.replace(/^\//,''), apiBase).href;
async function api(path, options={}) {
  if(isTourPreview)throw new Error('사용 안내에서는 실제 자료를 변경하지 않습니다.');
  const headers = {'X-Employee':state.employee,'X-Role':state.role, ...options.headers};
  if(options.body && !(options.body instanceof FormData)) {headers['Content-Type']='application/json';options.body=JSON.stringify(options.body);}
  const response = await fetch(apiUrl(path),{...options,headers});
  if(path!=='budget'&&options.method&&options.method!=='GET')setTimeout(refreshBudget,100);
  const value = await response.json().catch(()=>({detail:'서버 응답을 읽지 못했습니다.'}));
  if(!response.ok){if(response.status===401) loginDialog();throw new Error(typeof value.detail==='string'?value.detail:'입력값을 확인해 주세요.');}
  return value;
}
let toastTimer;
function toast(message){if($('#dialog').open){let alert=$('#dialog .modal-alert');if(!alert){alert=document.createElement('div');alert.className='modal-alert';alert.setAttribute('role','alert');alert.setAttribute('tabindex','-1');($('#dialog .modal-head>div')||$('#dialogBody')).append(alert);}alert.textContent=message;alert.hidden=false;alert.focus({preventScroll:true});return;}$('#toast').textContent=message;$('#toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),5500);}
function badge(text, tone=''){return `<span class="badge ${tone}">${esc(text)}</span>`;}
function button(action,text,style='',data=''){return `<button class="button ${style}" data-action="${action}" ${data}>${text}</button>`;}
function closeDialog(){state.fieldEdit=null;$('#dialog').close();$('#dialog').classList.remove('field-edit-dialog','grouping-dialog','tour-dialog');}
function modal(title,subtitle,body,actions){state.fieldEdit=null;$('#dialog').classList.remove('field-edit-dialog','grouping-dialog','tour-dialog');$('#dialogBody').innerHTML=`<div class="modal-head"><div><h2>${esc(title)}</h2><p>${esc(subtitle)}</p></div><button class="icon-button" data-action="close" aria-label="닫기">×</button></div><div class="modal-content">${body}</div><div class="modal-actions">${actions}</div>`;if(!$('#dialog').open)$('#dialog').showModal();}
async function init(){
  setEmployeeCookie();$('#roleSelect').value=state.employee;$('#avatar').textContent=state.employee.slice(-1);
  try{state.config=await api('config');refreshBudget();state.cases=await api('cases');renderSidebar();$('#modeFooter').textContent=state.config.llm_available?`LLM 연결 · ${modelLabel(state.config.model)}`:'로컬 규칙 추출 · LLM 미연결';const saved=location.hash.slice(1);if(saved&&state.cases.some(c=>c.id===saved))await openCase(saved);else renderHome();}catch(e){toast(e.message);}
}
function renderSidebar(){
  $('#caseCount').textContent=state.cases.filter(c=>!c.archived).length;
  if($('#caseList'))$('#caseList').innerHTML=state.cases.map(c=>`<button class="case-link ${c.id===state.current?'selected':''}" data-action="open-case" data-id="${c.id}">${esc(c.title)}</button>`).join('');
}
function renderHome(){
  state.role='predecessor';document.body.classList.add('inbox-mode');document.body.classList.remove('case-workspace');
  state.qaController?.abort();state.qaController=null;state.qaBusy=false;
  disposeReportReader();
  clearTimeout(state.timer);state.current=null;state.details=null;state.revision=null;location.hash='';renderSidebar();$('#breadcrumb').textContent='인수인계함';
  $('#main').innerHTML=`<div class="page-heading home-heading"><div class="welcome-decoration" aria-hidden="true"><svg viewBox="0 0 560 120" fill="none"><path d="M0 111C100 111 84 18 190 18S298 100 380 100 468 20 560 20" stroke="currentColor" stroke-width="1.3"/><path d="M0 120C108 120 96 30 195 30S300 112 385 112 472 32 560 32" stroke="currentColor" stroke-dasharray="3 6"/><circle cx="190" cy="18" r="5" fill="currentColor"/><circle cx="380" cy="100" r="5" fill="currentColor"/></svg></div><div class="home-welcome"><div class="home-illustration" aria-hidden="true"><div class="hero-art"><div class="art-sheet"><i></i><i></i><i></i><i></i><div class="art-seal">검토 완료 ✓</div></div><div class="art-baton"></div><div class="art-tag">✧ 업무의 다음 페이지</div></div></div><div class="welcome-copy"><div class="eyebrow">Your next chapter</div><h1>업무를 잇는 가장 좋은 <span class="welcome-highlight">시작.</span></h1><p class="subtitle">흩어진 자료를 하나의 보고서로.<br class="welcome-break"> <strong>진행 현황부터 다음 할 일까지</strong>, 다음 담당자가 바로 이어갑니다.</p></div></div><div class="welcome-journey" aria-label="자료를 모아 업무 맥락을 정리하고 다음 담당자에게 전달"><div class="journey-step"><span class="journey-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M7 4h9l4 4v13H7zM16 4v5h4M4 17H2V1h12v1M10 12h7M10 16h5"/></svg></span><span>자료 모으기</span></div><span class="journey-link" aria-hidden="true">→</span><div class="journey-step"><span class="journey-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="M7 8h10M7 12h3M13 12h4M7 16h7"/></svg></span><span>맥락 정리</span></div><span class="journey-link" aria-hidden="true">→</span><div class="journey-step journey-next"><span class="journey-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 7h6m-3-3 3 3-3 3"/></svg></span><span>다음 담당자</span></div></div><div class="welcome-action"><span class="welcome-action-note">다음 업무의 시작을 준비하세요</span>${state.role==='predecessor'?button('new-case','＋ 새 인수인계','primary'):''}</div></div>
  <div class="home-actions"><button type="button" class="demo-launch" data-action="demo-menu"><span class="demo-launch-mark" aria-hidden="true">▦</span><span>시연 및 샘플 데이터 다운</span><span class="demo-launch-arrow" aria-hidden="true">↗</span></button></div>
  <div class="section-heading"><h2>직원 ${esc(state.employee.slice(-1))} · 나의 인수인계함</h2><span>최신 생성순 · 완료 건은 아래에</span></div>
  ${inboxGroup('successor','인수')}${inboxGroup('predecessor','인계')}
  <div class="notice"><span>ⓘ</span><p><strong>직접 확인하는 인수인계</strong> · 추출 결과는 초안입니다. 원문과 다른 기한·담당은 전임자가 수정하고 확정합니다. 이 서비스의 역할 선택은 시연용이며 기관 인증·전자결재가 아닙니다.</p></div>`;
}
function setEmployeeCookie(){document.cookie=`handover_employee=${state.employee}; Path=${new URL('.',location.href).pathname}; SameSite=Lax`;}
function inboxGroup(role,label){
 const rows=state.cases.filter(c=>!c.archived&&c.my_role===role),active=rows.filter(c=>!c.accepted),done=rows.filter(c=>c.accepted);
 return `<section class="inbox-group"><h2>${label} <small>${active.length}건 진행 중</small></h2><div class="case-grid">${active.map(inboxCard).join('')||'<p class="muted">진행 중인 '+label+' 건이 없습니다.</p>'}</div>${done.length?`<details class="completed-inbox"><summary><span class="closed-label">완료된 ${label} 건 보기 ›</span><span class="open-label">완료된 ${label} ${done.length}건 ∨</span></summary><div class="case-grid">${done.map(inboxCard).join('')}</div></details>`:''}</section>`;
}
function inboxCard(c){
 const stage=c.accepted?3:c.confirmed?2:c.current?1:0;
 const delivered=c.delivery?.revision_id===c.confirmed;
 const steps=['자료 등록','초안 검토',delivered?'인계 완료':'확정·인계 준비','인수 완료'];
 return `<button class="case-card" data-action="open-case" data-id="${c.id}">${badge(c.accepted?'인수 완료':steps[stage],c.accepted?'green':'gray')}<h3>${esc(c.title)}</h3><p>직원 ${esc(c.predecessor_id.slice(-1))} → 직원 ${esc(c.successor_id.slice(-1))}${c.legacy_assignment?' · 이전 시연자료':''}</p><ol class="mini-flow" aria-label="현재 단계: ${steps[stage]}">${steps.map((step,i)=>`<li class="${i<stage?'past':i===stage?'current':''}" ${i===stage?'aria-current="step"':''}><b>${i<stage?'✓':i+1}</b><span>${step}</span></li>`).join('')}</ol><div class="card-bottom"><span>${date(c.created)}</span><span>${c.my_role==='successor'?'인수':'인계'}함 열기 ↗</span></div></button>`;
}
function caseDialog(){modal('새 인수인계함','현재 직원이 인계자가 됩니다.',`<label class="form-field">인수인계 이름<input id="caseTitle" maxlength="150" autofocus></label><label class="form-field">인계자<input id="predecessor" value="직원 ${state.employee.slice(-1)}" readonly></label><label class="form-field">인수자<select id="successor">${[1,2,3,4].filter(i=>'employee'+i!==state.employee).map(i=>`<option value="employee${i}" ${i===Number(state.employee.slice(-1))%4+1?'selected':''}>직원 ${i}</option>`).join('')}</select></label>`,button('close','취소')+button('create-case','만들기','primary'));}
async function createCase(title, predecessor, successor){const recipient=/^employee[1-4]$/.test(successor||'')?successor:'employee'+(Number(state.employee.slice(-1))%4+1);const c=await api('cases',{method:'POST',body:{title,predecessor:'직원 '+state.employee.slice(-1),successor:'직원 '+recipient.slice(-1),predecessor_id:state.employee,successor_id:recipient}});state.cases=await api('cases');return c;}
async function openCase(id, tab){
  document.body.classList.remove('inbox-mode');document.body.classList.add('case-workspace');
  if(state.current!==id){state.qaController?.abort();state.qaController=null;state.qaBusy=false;}
  state.role=state.cases.find(c=>c.id===id)?.my_role||'predecessor';
  clearTimeout(state.timer);state.current=id;location.hash=id;if(tab)state.tab=tab;else state.tab=state.cases.find(c=>c.id===id)?.confirmed?'report':state.role==='successor'?'report':'sources';
  await refresh();
}
async function refresh(){
  const id=state.current;if(!id)return;
  const details=await api(`cases/${id}`);if(state.current!==id)return;state.details=details;state.role=details.my_role||state.role;
  const pointer=state.role==='successor'||['confirmed','report','briefing','questions','deliver'].includes(state.tab)?'confirmed':'current';
  state.revision=await api(`cases/${id}/revisions/${pointer}`);
  if(state.tab==='briefing'&&details.confirmed)state.briefing=await api(`cases/${id}/briefing`);else state.briefing=null;
  const qaKey=id+':'+(details.confirmed||'');if(state.qaKey!==qaKey){state.qaKey=qaKey;state.answers=[];state.qaConsent=false;}
  if(state.current!==id)return;
  renderSidebar();renderCase();
  if(details.jobs.some(j=>['RUNNING','QUEUED'].includes(j.status)))state.timer=setTimeout(()=>refresh().catch(e=>toast(e.message)),1500);
}
function renderCase(){
  if(state.qaController&&state.tab!=='questions'){state.qaController.abort();state.qaController=null;state.qaBusy=false;}
  disposeReportReader();
  const d=state.details, rev=state.revision, items=rev?.payload.items||[];$('#breadcrumb').textContent=d.title;
  const docs=d.documents;const warnings=rev?.warnings.length||0;const active=d.jobs.find(j=>['RUNNING','QUEUED'].includes(j.status));
  const coverage=rev?.payload.coverage||[];const scanned=coverage.reduce((a,c)=>a+c.scanned_blocks,0),reviewed=coverage.reduce((a,c)=>a+c.reviewed_blocks,0);
  $('#main').innerHTML=`<div class="page-heading"><div><div class="eyebrow">Handover workspace</div><h1>${esc(d.title)}</h1><p class="subtitle">${esc(d.predecessor)} <span>→</span> ${esc(d.successor)} &nbsp;·&nbsp; ${date(d.created)} 생성</p></div><div class="buttons">${button('home','← 목록','small ghost')}${d.confirmed?button('open-report','인수인계 보고서 보기','primary'):''}${state.role==='predecessor'?button('generate',d.current?'새 초안 생성':'초안 생성','primary',active?'disabled':''):badge('후임자 열람','green')}</div></div>

  <div class="stats"><div class="stat"><div class="label">등록 자료</div><strong>${docs.length}<small> 개</small></strong><small>파일 판본 보존</small></div><div class="stat"><div class="label">정리된 업무</div><strong>${items.length}<small> 건</small></strong><small>${rev?rev.payload.mode==='llm'?'AI 문서별 추출':'로컬 규칙 추출':'초안 생성 후 표시'}</small></div><div class="stat"><div class="label">검토 범위</div><strong>${reviewed}<small> / ${scanned} 블록</small></strong><small>읽은 본문 중 추출 검토 범위</small></div><div class="stat"><div class="label">확인 필요</div><strong>${warnings}<small> 건</small></strong><small>미확인 값·부분 추출 포함</small></div></div>
  ${modelUsage(rev)}${imageReviewView(rev)}
  ${jobView(d.jobs[0])}
  ${caseSteps(d)}
  ${state.tab==='sources'?sourcesView():state.tab==='deliver'?deliveryView():state.tab==='history'?historyView():state.tab==='report'?reportView():state.tab==='briefing'?briefingView():state.tab==='questions'?questionsView():reviewView(state.tab==='confirmed')}`;
  const reportFrame=$('#reportFrame');if(reportFrame)mountReportReader(reportFrame);
  const zone=$('#dropZone');if(zone){zone.addEventListener('dragover',e=>{e.preventDefault();zone.classList.add('drag');});zone.addEventListener('dragleave',()=>zone.classList.remove('drag'));zone.addEventListener('drop',e=>{e.preventDefault();zone.classList.remove('drag');if(e.dataTransfer.files.length)uploadFiles(e.dataTransfer.files).catch(e=>toast(e.message));else toast('폴더는 폴더 선택 버튼으로 등록해 주세요.');});}
}
function caseSteps(d){
 const sent=(d.deliveries||[]).some(x=>x.revision_id===d.confirmed);
 const nodes=[['sources','자료 등록','1',d.documents.length>0],['review','초안 검토','2',!!d.current],['report','인수인계 보고서','3',!!d.confirmed],['history','변경 이력','◷',false],['deliver',state.role==='successor'?'인계 내용':'인계하기','4',sent||!!d.accepted]];
 return `<nav class="tabs workflow-tabs" aria-label="인수인계 단계">${nodes.map(([key,title,n,done])=>`<button type="button" class="tab workflow-step ${state.tab===key?'active':''} ${done?'step-complete':''} ${key==='history'?'history-step':''}" data-action="tab" data-tab="${key}" ${state.tab===key?'aria-current="step"':''}><b class="workflow-step-number">${n}</b><span>${title}</span>${key==='deliver'&&sent?'<small>전달 완료</small>':''}</button>`).join('')}</nav>`;
}
function deliveryNotice(){
 const r=state.revision,d=(state.details.deliveries||[]).find(x=>x.revision_id===r?.id);
 if(!d)return '';
 return `<details class="delivery-notice" ${state.role==='successor'?'open':''}><summary>직원 ${esc(d.sender_id.slice(-1))} → 직원 ${esc(d.recipient_id.slice(-1))} · 전달 의견 <small>${date(d.sent_at)}</small></summary><p>${esc(d.message)}</p></details>`;
}
function deliveryView(){
 const d=state.details,rev=state.revision,rows=d.deliveries||[],sent=rows.find(x=>x.revision_id===rev?.id),owner=state.role==='predecessor';
 const ready=!!rev&&d.current===rev.id&&!d.accepted&&!sent&&!d.jobs.some(j=>['RUNNING','QUEUED'].includes(j.status));
 const draft=state.deliveryDrafts?.[state.current]||'';
 return `<div class="delivery-page"><section class="delivery-compose panel"><div class="eyebrow">FINAL HANDOVER</div><h2>${owner?'최종 보고서를 다음 담당자에게':'전달받은 최종 보고서와 의견'}</h2><p class="subtitle">${owner?'확정 판본과 전달 의견을 한 번에 인계합니다.':'전달 의견을 확인하고 같은 확정 판본을 읽어 주세요.'}</p><div class="delivery-people"><span><small>인계자</small><b>직원 ${esc(d.predecessor_id.slice(-1))}</b></span><i>→</i><span><small>인수자</small><b>직원 ${esc(d.successor_id.slice(-1))}</b></span></div>
 <div class="delivery-report"><span class="delivery-document-icon" aria-hidden="true">▤</span><div><strong>${esc(d.title)}</strong><p>${rev?'확정 판본 '+esc(rev.id.slice(0,8))+' · '+date(rev.confirmation?.created):'아직 확정된 보고서가 없습니다.'}</p></div>${rev?button('tab','보고서 확인 ↗','small','data-tab="report"'):''}</div>
 ${sent?`<div class="delivery-sent"><b>✓ 인계 완료 · ${date(sent.sent_at)}</b><p class="delivery-message">${esc(sent.message)}</p><small>${d.accepted?'인수 확인 완료 · '+date(d.accepted):'인수자의 확인을 기다리고 있습니다.'}</small></div>`:owner?`<label class="form-field" for="deliveryMessage">전달 의견<textarea id="deliveryMessage" maxlength="2000" rows="6" placeholder="우선 확인할 현안, 다음 일정, 인수자에게 전할 내용을 적어 주세요." ${ready?'':'disabled'}>${esc(draft)}</textarea></label>${!ready?`<div class="notice">${d.accepted?'이미 인수 완료된 판본입니다.':!rev?'초안을 검토하고 보고서를 확정해 주세요.':d.current!==rev.id?'새 초안이 있습니다. 최신 초안을 검토·확정한 뒤 인계하세요.':'자료 처리가 끝나면 인계할 수 있습니다.'}${!d.accepted?button('tab','초안 검토로 이동','small','data-tab="review"'):''}</div>`:''}<label class="check-row"><input type="checkbox" id="deliveryAcknowledge" ${ready?'':'disabled'}><span>받을 직원과 확정 보고서, 전달 의견을 확인했습니다.</span></label><div id="deliveryError" role="alert"></div>${button('send-delivery','직원 '+esc(d.successor_id.slice(-1))+'에게 최종본 인계하기 →','primary',ready?'':'disabled')}`:'<div class="notice">이전 방식으로 공유된 확정본이거나 아직 전달 의견이 등록되지 않았습니다. 보고서에서 내용을 확인할 수 있습니다.</div>'}
 ${!owner&&rev?button('accept',d.accepted?'인수 확인 완료 ✓':'보고서·의견 확인 후 인수 완료','primary',d.accepted?'disabled':''):''}
 </section><aside class="delivery-history panel"><h3>인계 기록 <span>${rows.length}건</span></h3>${rows.map(x=>`<article><strong>직원 ${esc(x.sender_id.slice(-1))} → 직원 ${esc(x.recipient_id.slice(-1))}</strong><small>${date(x.sent_at)} · 판본 ${esc(x.revision_id.slice(0,8))}</small><p>${esc(x.message)}</p><a class="text-link" target="_blank" rel="noopener" href="${apiUrl(`cases/${state.current}/reports/${x.revision_id}`)}">이때 전달한 보고서 ↗</a></article>`).join('')||'<p class="muted">인계하면 전달 의견·시각·판본이 이곳에 보관됩니다.</p>'}<p class="delivery-record-note">전달한 판본과 의견은 이력으로 보존됩니다.</p></aside></div>`;
}
async function sendDelivery(){
 const error=$('#deliveryError'),message=$('#deliveryMessage').value.trim();error.textContent='';
 if(!message){error.textContent='전달 의견을 입력해 주세요.';$('#deliveryMessage').focus();return;}
 if(!$('#deliveryAcknowledge').checked){error.textContent='받을 직원과 보고서·의견 확인에 체크해 주세요.';return;}
 const control=$('[data-action="send-delivery"]');control.disabled=true;
 try{await api(`cases/${state.current}/deliver`,{method:'POST',body:{revision_id:state.revision.id,expected_hash:state.revision.hash,recipient_id:state.details.successor_id,message}});if(state.deliveryDrafts)delete state.deliveryDrafts[state.current];state.cases=await api('cases');await refresh();toast('최종 보고서와 전달 의견을 인수자에게 인계했습니다.');}catch(e){error.textContent=e.message;control.disabled=false;}
}
document.addEventListener('input',e=>{if(e.target.id==='deliveryMessage'){state.deliveryDrafts??={};state.deliveryDrafts[state.current]=e.target.value;}});
function modelUsage(revision){
  if(!revision || revision.payload.mode!=='llm')return '';
  const rows=revision.payload.coverage;
  const calls=rows.reduce((n,r)=>n+(r.calls?.length||0),0);
  const tokens=rows.reduce((n,r)=>n+(r.usage?.total_tokens||0),0);
  return `<details class="model-usage"><summary>모델 사용 기록</summary><p>${esc(modelLabel(revision.payload.model))} · ${calls}회 요청 · ${tokens.toLocaleString()} 토큰</p><p class="muted">이 판본을 생성할 때의 실제 호출 기록입니다. 모델의 검토가 의미 정확성을 보증하지는 않습니다.</p><a class="text-link" href="${apiUrl('demo.zip?expanded=true')}">비정형 문서 포함 확장 샘플 12개 받기 ↓</a></details>`;
}
function jobView(job){
  if(!job)return '';
  if(['QUEUED','RUNNING'].includes(job.status))return `<div class="job"><div class="job-header"><span><i class="spinner"></i>${({QUEUE:'자료 처리 준비',IMAGES:'채택된 최신본의 그림만 판독',PARSE:'파일별 원문 추출',DISCOVER:'문서별 업무 후보 추출',MERGE:'업무 통합·근거 연결'})[job.stage]||'처리 중'}</span><small>${job.progress}% · 새로 고쳐도 계속됩니다</small></div><progress class="progress" value="${job.progress}" max="100" aria-label="문서 처리 진행률"></progress></div>`;
  if(['FAILED','INTERRUPTED'].includes(job.status))return `<div class="notice"><span>!</span><div><strong>처리를 완료하지 못했습니다.</strong><p>${esc(job.error)}</p></div>${state.role==='predecessor'?button('retry','다시 시도','small',`data-id="${job.id}"`):''}</div>`;
  return '';
}
function sourcesView(){
  const docs=state.details.documents,coverage=state.revision?.payload.coverage||[];
  return `${state.role==='predecessor'?`<div class="upload-zone" id="dropZone"><span class="upload-icon">↥</span><div><h3>업무자료를 여기에 놓아주세요.</h3><p>ZIP · HWP/HWPX · PDF · DOCX · XLSX · TXT &nbsp;|&nbsp; 파일당 20MB, ZIP 80MB</p></div><div class="buttons">${button('upload','여러 파일 선택','small primary')}${button('upload-folder','폴더 선택','small')}${button('sample','샘플 자료 추가','small')}</div></div>`:''}
  <div class="section-heading"><h2>등록한 자료</h2><span>원문은 변경하지 않고 판본으로 보존합니다.</span></div>
  ${docs.length?`<div class="table-wrap"><table><thead><tr><th>자료명</th><th>추출 상태</th><th>검토 범위</th><th>원문</th></tr></thead><tbody>${docs.map(doc=>{const cov=coverage.find(c=>c.document_id===doc.id);return `<tr><td><div class="file-name"><span class="file-icon">${esc(doc.format.slice(1).toUpperCase())}</span>${esc(doc.path)}</div>${doc.warnings.length?`<div class="file-warning">${esc(doc.warnings.join(' '))}</div>`:''}<small class="muted">판본 ${doc.id.slice(0,8)}</small></td><td>${badge(...statuses[doc.status])}<div class="muted">${doc.block_count} 블록</div></td><td><span class="muted">${cov?`${cov.reviewed_blocks} / ${cov.scanned_blocks} 블록 검토`:'미검토'}</span>${cov?.unreviewed_block_ids.length?`<div class="file-warning">${cov.unreviewed_block_ids.length} 블록 추가 확인</div>`:''}</td><td><button class="text-link" data-action="document" data-id="${doc.id}">본문 보기 ↗</button><br><a class="text-link" href="${apiUrl(`cases/${state.current}/documents/${doc.id}/raw`)}">원본 받기 ↓</a></td></tr>`;}).join('')}</tbody></table></div>`:`<div class="empty"><h3>아직 등록한 자료가 없습니다.</h3><p>여러 파일을 담은 ZIP으로 시작하거나 샘플을 추가해 보세요.</p></div>`}
  <div class="notice"><span>ⓘ</span><p>텍스트 기반 문서와 단순 표를 우선 지원합니다. 그림은 최신본 선택 후 별도 동의 시 GPT-5.4로 판독합니다. 본문 없는 스캔 PDF의 최신본 자동 판단과 벡터 도형·수식은 지원하지 않습니다. 부분 추출 사유와 미검토 범위를 확인하세요.</p></div>`;
}
function fieldView(item,key,field,editable=false){
  const refs=field.evidence.length?field.evidence:field.previous?.evidence||[];
  const human=field.provenance==='HUMAN_ENTERED';const conflict=field.review_status==='CONFLICT';
  return `<div class="field ${!['title','status','owner','due_date'].includes(key)?'wide':''} ${conflict?'conflict':''} ${human?'human':''}"><div class="field-heading"><label>${labels[key]} ${human?badge('전임자 확인','green'):conflict?badge('기한 대조','orange'):field.review_status==='NEEDS_CONFIRMATION'&&field.value?badge('확인 필요','orange'):''}</label>${editable?pencil(item,key):''}</div><div class="value">${esc(field.value)||'<span class="muted">미확인</span>'}</div>${refs.length||field.previous?`<button class="source-button" data-action="evidence" data-id="${item.id}" data-field="${key}">${human?'수정 이력·과거 근거':'↗ 원문 근거 '+refs.length+'개'}</button>`:''}</div>`;
}
function versionChoice(item){
  const events=item.timeline||[];
  if(!events.some(e=>e.report_id))return '';
  const latest=events.find(e=>e.document_id===item.latest_document_id);
  const labels={selected:'현재 기준본',superseded:'이전·중복 기록',excluded:'현재 기준에서 제외',ambiguous:'확인 필요'};
  return `<div class="version-choice"><p><strong>${latest?'현재 기준본: '+esc(latest.path):'최신본 자동 선택 보류'}</strong>${latest?' · '+esc(latest.reported_at||'기준일 미상')+' / '+esc(latest.revision_no??'미상')+'차':''}</p><details><summary>본문 판본 비교 · ${events.length}개 자료</summary>${events.map(e=>`<p><strong>${esc(labels[e.selection_status]||'기록')} · ${esc(e.path)}</strong><br>본문 기준일 ${esc(e.reported_at||'미기재')} / ${esc(e.revision_no??'미기재')}차 / 수정 ${esc(e.issued_at||'미기재')} / ${esc(e.document_state||'미기재')}<br><small>${esc(e.selection_reason||'')}</small></p>`).join('')}</details></div>`;
}
function reportWorkActions(fromReport=false){
 return `<div class="report-work-actions"><section class="report-work-action"><div><strong>같은 업무끼리 하나의 흐름으로</strong><p>전체 업무와 근거를 보며 묶음을 정리하세요.</p></div>${button(fromReport?'report-group':'group-open','▤ 업무 전체 보고 묶기','small')}</section><section class="report-work-action report-work-confirm"><div><strong>확인한 내용을 다음 사람에게.</strong><p>${fromReport&&state.details.current!==state.revision.id?'최신 초안을 검토한 뒤 새 보고서로 확정합니다.':'현재 판본과 검토 이력을 함께 보관합니다.'}</p></div>${button(fromReport?'report-confirm':'confirm-dialog','검토 완료 · 확정하기 →','small primary')}</section></div>`;
}
function reviewView(confirmed){
  const rev=state.revision;if(!rev)return `<div class="empty"><h3>${confirmed?'아직 전달된 확정본이 없습니다.':'검토할 초안을 만들어 주세요.'}</h3><p>${confirmed?'전임자가 초안을 검토·확정하면 이곳에서 업무를 확인할 수 있습니다.':'자료를 등록한 뒤 초안 생성을 누르면, 원문과 연결된 업무 카드가 만들어집니다.'}</p>${!confirmed&&state.role==='predecessor'?button('generate','초안 생성','primary'):''}</div>`;
  const editable=!confirmed&&state.role==='predecessor';
  return `${editable?reportWorkActions():''}${confirmed?`<div class="success-header"><div class="success-icon">✓</div><div><h3>전임자가 확인한 인수인계본입니다.</h3><p>${date(rev.confirmation?.created)} 확정 · 판본 ${rev.id.slice(0,8)}${state.details.accepted?' · 후임자 확인 완료':''}</p></div><div class="buttons"><a class="button small" href="${apiUrl(`cases/${state.current}/exports/${rev.id}.md`)}">MD ↓</a><a class="button small" href="${apiUrl(`cases/${state.current}/exports/${rev.id}.html`)}">HTML ↓</a><a class="button small" href="${apiUrl(`cases/${state.current}/exports/${rev.id}.docx`)}">DOCX ↓</a>${state.role==='successor'?button('accept',state.details.accepted?'확인 완료 ✓':'인수 확인','small primary'):''}</div></div>`:`<div class="section-heading"><div><h2>원문에서 찾은 업무, 함께 확인해 주세요.</h2><p class="subtitle">${rev.payload.mode==='llm'?'AI가 문서별로 추출한':'로컬 규칙으로 추출한'} 초안입니다. 필드의 원문 근거를 눌러 확인할 수 있습니다.</p></div>${editable?button('add-item','＋ 업무 추가','small'):''}</div>`}
  ${editable?readinessView(rev):''}
  ${rev.warnings.length?`<div class="notice"><span>!</span><p><strong>${rev.warnings.length}개 확인 필요 사항이 있습니다.</strong> 기한 불일치·담당 미확인·부분 추출 내용은 확정 후에도 표시됩니다. ${button('warnings','자세히 보기','small ghost')}</p></div>`:''}
  <div class="review-layout"><div><div class="work-list">${rev.payload.items.map((item,index)=>`<article class="work-card"><div class="work-top"><div><div class="work-number">WORK ${String(index+1).padStart(2,'0')}</div><div class="work-title"><h3>${esc(item.fields.title.value)}</h3>${editable?pencil(item,'title'):''}</div></div>${editable?button('match','업무 묶기','small',`data-id="${item.id}"`):badge('확정본 수록','green')}</div><p class="tiny">${esc(item.chronology_note||'')}</p>${versionChoice(item)}<div class="work-grid">${Object.keys(labels).filter(k=>['status','owner','due_date','completed_work','remaining_work','next_action','issues','notes','collaborators'].includes(k)).map(key=>fieldView(item,key,item.fields[key]||{value:'',evidence:[]},editable)).join('')}</div><details class="practice-fields"><summary>업무 개요·계획·실무 절차·예산·연락망 확인 / 항목별 수정</summary><div class="work-grid">${Object.keys(labels).filter(k=>!['title','status','owner','due_date','completed_work','remaining_work','next_action','issues','notes','collaborators'].includes(k)).map(key=>fieldView(item,key,item.fields[key]||{value:'',evidence:[]},editable)).join('')}</div></details><div class="work-bottom"><span>${item.source_documents.length}개 자료 연결${item.merge_note?' · 같은 업무인지 검토 필요':''}</span><button class="text-link" data-action="evidence" data-id="${item.id}" data-field="title">업무명 근거 ↗</button>${editable?button('delete-dialog','업무 삭제','small ghost',`data-id="${item.id}"`):''}</div></article>`).join('')||'<div class="empty"><h3>자동 추출된 업무가 없습니다.</h3><p>비정형 문서는 LLM 모드로 재검토하거나 업무를 직접 추가하세요. 검토되지 않은 문서를 업무 없음으로 처리하지 않습니다.</p></div>'}</div>
  </div>
  <aside class="evidence-panel"><div class="evidence-head">원문 근거 <span class="muted">SOURCE</span></div><div class="evidence-body" id="evidenceBody"><div class="evidence-placeholder"><span>▤</span><p>업무 카드의 근거를 누르면<br>원문과 위치를 볼 수 있어요.</p></div></div><div class="evidence-body"><form id="searchForm" class="search-row"><input id="searchQuery" aria-label="본문 검색" placeholder="본문 키워드 검색" maxlength="300"><button class="button small" type="submit">검색</button></form><p class="muted">예: 영수증, 주민 수요조사</p><div id="searchResults"></div></div></aside></div>`;
}
function reportView(){
  const rev=state.revision;
  if(!rev)return `<div class="empty"><h3>아직 확정된 인수인계 보고서가 없습니다.</h3><p>초안 검토에서 진행 상황·완료한 일·남은 업무·현안을 보완하고 확정하면, 인계자와 인수자가 같은 완결된 보고서를 볼 수 있습니다.</p>${state.role==='predecessor'?button('tab','초안 검토로 이동','primary','data-tab="review"'):''}</div>`;
  const link=isTourPreview?'downloads/practice-report.html':apiUrl(`cases/${state.current}/reports/${rev.id}`);
  return `<div class="success-header"><div class="success-icon">✓</div><div><h3>전임자가 확인한 인수인계본입니다.</h3><p>인계자·인수자 공통 보고서 · ${date(rev.confirmation.created)} 확정 · 판본 ${rev.id.slice(0,8)}</p></div>${state.role==='successor'?button('accept',state.details.accepted?'확인 완료 ✓':'인수 확인','small primary'):''}</div>
  <div class="report-toolbar"><div><strong>업무 인수인계 보고서</strong><p>업무 개요 · 목표 · 추진 경과 · 실행 계획 · 공통 예산·연락망</p></div><div class="buttons"><button class="button small reader-panel-toggle" data-reader-panel="toc" aria-controls="reportToc" aria-expanded="false">☰ 목차</button><button class="button small reader-panel-toggle" data-reader-panel="chat" aria-controls="readerChatLog" aria-expanded="false">챗봇</button>${state.role==='predecessor'?button('tab','보고서 내용 보완','small','data-tab="review"'):''}<a class="button small" target="_blank" rel="noopener" href="${link}">보고서 새 창 ↗</a>${button('print-report','인쇄 / PDF 저장','small')}<a class="button small" href="${apiUrl(`cases/${state.current}/exports/${rev.id}.md`)}">MD ↓</a><a class="button small" href="${apiUrl(`cases/${state.current}/exports/${rev.id}.html`)}">HTML ↓</a><a class="button small" href="${apiUrl(`cases/${state.current}/exports/${rev.id}.docx`)}">DOCX ↓</a></div></div>
  ${state.role==='predecessor'&&state.details.current!==rev.id?'<div class="notice">새 초안이 있습니다. 아래 보고서는 양측에 전달된 기존 확정본입니다. 새 초안을 검토·확정해야 보고서가 갱신됩니다.</div>':''}
  ${deliveryNotice()}
  ${state.role==='predecessor'?reportWorkActions(true):''}
  ${reportReaderView(link)}`;
}
function readinessView(rev){
  const r=rev.readiness;if(!r?.missing_fields)return '<div class="notice green">보고서의 필수 설명란이 채워져 있습니다. 내용의 정확성과 근거를 검토한 후 확정하세요.</div>';
  return `<details class="readiness"><summary>보고서 보완: ${r.items.length}개 업무 · ${r.missing_fields}개 미기재 항목</summary><p>${esc(r.note)}</p>${r.items.map(i=>`<div class="readiness-row"><div><strong>${esc(i.title)}</strong><div class="readiness-fields">${i.missing.map(m=>`<span>${esc(m.label)} ${pencil({id:i.item_id},m.key)}</span>`).join('')}</div></div></div>`).join('')}</details>`;
}
function briefingView(){
  const b=state.briefing;if(!b)return '<div class="empty"><h3>보고서를 확정하면 일정과 연락망을 확인할 수 있습니다.</h3></div>';
  return `<div class="section-heading"><div><h2>후임자 일정·담당·연락망</h2><p class="subtitle">${esc(b.as_of)} 기준 · 최신 확정본에서 조회</p></div></div><p class="muted">${esc(b.note)}</p>
  <div class="schedule-grid">${Object.entries(b.groups).map(([name,items])=>`<section class="panel schedule-group"><h3>${esc(name)} <span>${items.length}</span></h3>${items.length?items.map(i=>`<article class="schedule-item"><h4>${esc(i.title)}</h4><p><b>일정</b> ${esc(i.due_date)||'미확인'} · <b>담당</b> ${esc(i.owner)||'미확인'}</p><p>${esc(i.next_action)||'다음 행동 확인 필요'}</p>${i.issues?`<small>현안: ${esc(i.issues)}</small>`:''}</article>`).join(''):'<p class="muted">해당 업무 없음</p>'}</section>`).join('')}</div>
  <div class="section-heading"><h2>업무별 담당·협업·연락처</h2></div><p class="muted">자료나 전임자가 기재한 연락처만 표시합니다. 협의 부서는 담당과 구분하며 빈 연락처를 추측하지 않습니다.</p><div class="table-wrap"><table><thead><tr><th>업무</th><th>담당</th><th>협의·협업</th><th>연락처</th><th>근거</th></tr></thead><tbody>${b.contacts.map(c=>`<tr><td>${esc(c.title)}</td><td>${esc(c.owner)||'미확인'}</td><td>${esc(c.collaborators)||'미기재'}</td><td>${esc(c.contacts)||'미기재'}</td><td>${['owner','collaborators','contacts'].map(k=>c.evidence[k].length?button('block',esc(labels[k])+' 근거','small',`data-id="${c.evidence[k][0].block_id}"`):c.provenance[k]==='HUMAN_ENTERED'?`<small>${esc(labels[k])}: 전임자 입력</small>`:'').join('')}</td></tr>`).join('')}</tbody></table></div>`;
}
function questionsView(){
  if(!state.revision)return '<div class="empty"><h3>확정된 보고서가 있어야 질문할 수 있습니다.</h3><p>초안이나 새로 올린 미확정 자료는 답변의 확정 사실로 사용하지 않습니다.</p></div>';
  const mode=state.qaMode||(state.config.llm_available?'llm':'local');
  return `<div class="section-heading"><div><h2>확정 보고서에 질문하기</h2><p class="subtitle">전임자가 수정·확정한 값이 과거 원문보다 우선합니다.</p></div></div><div class="panel question-panel"><form id="questionForm"><label class="form-field">질문<textarea id="questionText" maxlength="500" required placeholder="예: 생활문화 사업계획 기한은 언제인가요? 보조금 정산에서 막힌 부분은 무엇인가요?">${esc(state.questionDraft||'')}</textarea></label><label class="form-field">조회 방식<select id="questionMode">${state.config.llm_available?`<option value="llm" ${mode==='llm'?'selected':''}>Solar Pro 4 · 자연어 질의</option>`:''}<option value="local" ${mode==='local'?'selected':''}>확정본 키워드 조회 · 외부 전송 없음</option></select></label>${state.config.llm_available?`<label class="check-row"><input type="checkbox" id="questionConsent" ${state.qaConsent?'checked':''}><span>AI 질의 시 질문·공개/합성 확정본·관련 원문을 연결된 모델로 전송하는 데 동의합니다.</span></label>`:''}<button type="submit" class="button primary" ${state.qaBusy?'disabled':''}>${state.qaBusy?'보고서에서 확인 중…':'질문하기'}</button></form></div>
  <div class="question-answers">${state.qaBusy?liveAnswerHTML(state.questionDraft,state.qaLiveText||''):''}${(state.answers||[]).slice().reverse().map(a=>`<article class="panel question-answer"><h3>${esc(a.question)}</h3><p>${esc(a.message)}</p>${conversationHTML(a)}${a.paragraphs?.length?'<details><summary>답변 근거 확인</summary>':''}${a.facts.map(f=>`<div class="answer-fact"><strong>${esc(f.title)} · ${esc(f.label)}</strong><p>${esc(f.value)}</p><small>${f.provenance==='HUMAN_ENTERED'?'전임자 입력': '원문에서 추출한 보고서 기록'}${f.review_status!=='CONFIRMED'?' · 내용 검토 필요':''}${f.changed_reason?' · 사유: '+esc(f.changed_reason):''}</small>${f.evidence.map(ref=>button('block','원문 근거 ↗','small',`data-id="${ref.block_id}"`)).join('')}</div>`).join('')}${a.paragraphs?.length?'</details>':''}${a.background.length?`<details><summary>관련 원문 보충 · 확정 사실이 아님</summary><p class="muted">과거 자료일 수 있으며 위 확정값을 대체하지 않습니다.</p>${a.background.map(b=>`<div class="context-block"><strong>${esc(b.path)}</strong><p>${esc(b.text)}</p>${button('block','원문 확인','small',`data-id="${b.id}"`)}</div>`).join('')}</details>`:''}<small>${a.mode==='llm'?'Solar Pro 4':'키워드 조회'} · 판본 ${a.revision_id.slice(0,8)}${a.usage.total_tokens?' · '+a.usage.total_tokens.toLocaleString()+' 토큰':''}</small></article>`).join('')}</div>`;
}
async function askQuestion(event){
  event.preventDefault();if(state.qaBusy)return;
  const question=$('#questionText').value.trim();if(question.length<2)throw new Error('질문을 두 글자 이상 입력해 주세요.');
  const mode=$('#questionMode').value,consent=$('#questionConsent')?.checked||false;
  if(mode==='llm'&&!consent)throw new Error('AI 질의의 외부 전송 동의를 확인해 주세요.');
  const id=state.current,revision=state.revision.id;state.questionDraft=question;state.qaMode=mode;state.qaConsent=consent;state.qaBusy=true;state.qaLiveText='';renderCase();
  const controller=new AbortController();state.qaController=controller;
  const painter=textPainter(()=>state.current===id&&state.tab==='questions'?$('.question-answers .live-text'):null);
  controller.signal.addEventListener('abort',()=>painter.stop(),{once:true});
  try{const body={question,mode,external_consent:consent,expected_revision:revision};const answer=mode==='llm'?await streamQuestion(`cases/${id}/questions`,body,text=>{state.qaLiveText+=text;painter.push(text);},controller.signal):await api(`cases/${id}/questions`,{method:'POST',body});await painter.drain();if(state.current===id&&state.details.confirmed===revision&&!controller.signal.aborted){state.answers=[...(state.answers||[]),answer].slice(-10);state.questionDraft='';}}
  catch(e){if(e.name!=='AbortError')throw e;}
  finally{painter.stop();if(state.qaController===controller){state.qaController=null;state.qaBusy=false;state.qaLiveText='';if(state.current===id&&state.tab==='questions')renderCase();}}

}
document.addEventListener('submit',event=>{if(event.target.id==='questionForm')askQuestion(event).catch(e=>toast(e.message));});
function historyView(){const rows=state.details.history.filter(r=>state.role==='predecessor'||r.confirmed_at);return `<div class="section-heading"><h2>변경과 확정의 기록</h2><span>과거 판본은 수정되지 않습니다.</span></div><div class="panel timeline">${rows.map(r=>`<div class="history-row"><span class="history-dot"></span><div><h3>${esc(r.reason)} ${r.confirmed_at?badge('확정','green'):badge('초안','gray')}</h3><p>${date(r.created)} · ${r.actor==='SYSTEM'?'시스템':'전임자'} · 판본 ${r.id.slice(0,8)}</p><p>내용 해시 ${r.hash.slice(0,24)}…</p></div><div class="buttons">${button('history-detail','판본 보기','small',`data-id="${r.id}"`)}${r.confirmed_at?`<a class="button small" href="${apiUrl(`cases/${state.current}/exports/${r.id}.md`)}">MD ↓</a>`:''}</div></div>`).join('')||'<div class="empty">아직 변경 이력이 없습니다.</div>'}</div>`;}
async function uploadFiles(fileList){
  const files=Array.from(fileList);if(!files.length)return;
  if(state.uploading)throw new Error('이미 자료를 등록하고 있습니다. 완료 후 다시 선택해 주세요.');
  if(files.length>100)throw new Error('한 번에 100개 이하의 파일을 선택해 주세요.');
  if(files.reduce((n,f)=>n+f.size,0)>80*1024*1024)throw new Error('선택한 자료의 합계는 80MB 이하만 가능합니다.');
  const id=state.current;state.uploading=true;
  try{toast(`${files.length}개 파일을 등록하고 있습니다.`);const data=new FormData();for(const file of files)data.append('files',file,file.webkitRelativePath||file.name);
  const result=await api(`cases/${id}/documents/batch`,{method:'POST',body:data});toast(`${result.documents.filter(d=>!d.duplicate).length}개 자료 등록 · 중복 ${result.documents.filter(d=>d.duplicate).length}개`);if(state.current===id){state.tab='sources';await refresh();}}
  finally{state.uploading=false;}
}
async function generateDialog(){
  const options=await api(`cases/${state.current}/inheritance-options`);
  const selected=state.revision?.payload.inheritance?.source?.revision_id;
  const preferred=state.demoBasis?.target===state.current?state.demoBasis.source:null;
  const prior=`<div class="inheritance-option"><label class="check-row"><input type="checkbox" id="usePreviousReport" ${selected?'checked':''} ${options.length?'':'disabled'}><span><strong>이전에 인수한 보고서 이어서 작성</strong><small>기존 업무 현행화 + 신규 업무 추가 · 인수 완료된 확정본 사용</small></span></label>${options.length?`<label class="form-field">기준으로 사용할 이전 보고서<select id="previousReport" ${selected?'':'disabled'}>${options.map(o=>`<option value="${esc(o.revision_id)}" data-case="${esc(o.id)}" ${selected?selected===o.revision_id?'selected':'':preferred===o.id?'selected':''}>${esc(o.predecessor)} → ${esc(o.successor)} · ${esc(o.title)} · ${date(o.accepted)} 인수 완료</option>`).join('')}</select></label>`:'<p class="muted">현재 인계자가 인수 완료한 보고서가 없습니다. 인수함에서 보고서를 확인하고 인수 완료 후 선택할 수 있습니다.</p>'}</div>`;
  modal('자료에서 초안 만들기','이전 업무를 이어받거나 등록 자료에서 새로 시작합니다.',`${prior}<label class="form-field">추출 방식<select id="extractMode"><option value="rules">로컬 규칙 추출 · 외부 전송 없음</option>${state.config.llm_available?`<option value="llm" selected>AI 문서 해석 · ${esc(modelLabel(state.config.model))}</option>`:''}</select></label><p class="muted">로컬 모드는 ‘업무:’, ‘담당:’, ‘기한:’처럼 라벨이 있는 내용을 추출합니다. 일반적인 문장·표의 의미 추출은 LLM 연결이 필요합니다.</p>${state.config.llm_available?'<label class="check-row"><input type="checkbox" id="externalConsent"><span>AI 모드에서 공개·합성 자료를 설정된 외부 모델 API로 전송하는 것에 동의합니다.</span></label>':'<div class="notice"><p>현재 LLM 미연결입니다. 운영자에게 모델 설정을 요청하세요.</p></div>'}${state.details.demo_image_manual_only?'<div class="notice"><p>GPT-5.4 그림 분석은 자동 실행하지 않습니다. PoC7 우선 사용을 위해 기본값은 꺼짐이며, 필요할 때 아래 항목을 직접 체크해 실행하세요.</p></div>':''}${state.config.vision_available?'<label class="check-row"><input type="checkbox" id="imageConsent"><span>그림 분석 수동 실행 · 최신본 선택 후 채택된 파일의 그림만 판독합니다. GPT-5.4 일일 토큰 부족 시 GPT-6.1 Terra로 자동 전환하여 PoC7·10·11·13 공용 월 $100 예산을 사용합니다.</span></label>':''}${state.details.current?'<div class="notice">이어서 작성을 선택하면 이전 인수 완료 보고서의 수정값과 근거를 함께 가져옵니다. 이 인수인계함의 기존 초안 수정은 과거 판본에 보존됩니다. 이미 전달한 확정본은 유지됩니다.</div>':''}`,button('close','취소')+button('run-generate','초안 생성 시작','primary'));
  $('#usePreviousReport').addEventListener('change',e=>{if($('#previousReport'))$('#previousReport').disabled=!e.target.checked;});
}
function pencil(item,key){return `<button type="button" class="field-pencil" data-action="edit-field" data-id="${item.id}" data-field="${key}" aria-label="${esc(labels[key])} 수정" title="${esc(labels[key])} 수정 · 근거 함께 보기"><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="m15 5 4 4M4 20l4-1L20 7a2.8 2.8 0 0 0-4-4L4 15z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg></button>`;}
function fieldSources(item,key){
  const sources=[],seen=new Set(),history=[];
  function add(field,label,path='',reported='',related=false){
    for(const ref of field?.evidence||[]){const identity=ref.block_id+'\n'+ref.quote;if(seen.has(identity))continue;seen.add(identity);sources.push({ref,label,path,reported,related,value:field.value});}
  }
  let f=item.fields[key];add(f,'현재 값의 원문');
  while(f?.previous){history.push({value:f.value,before:f.previous.value,reason:f.reason,changed_at:f.changed_at});f=f.previous;add(f,'수정 전 원문');}
  for(const event of [...(item.timeline||[]),...(item.supporting_records||[])].sort((a,b)=>(b.reported_at||'').localeCompare(a.reported_at||'')))add(event.fields[key],`${event.stage||'단계 미기재'}보고 · 이전 기록 포함`,event.path,event.reported_at);
  const codes=new Set((item.timeline||[]).map(e=>e.work_code).filter(Boolean));
  for(const other of state.revision.payload.items){
    if(other.id===item.id)continue;
    for(const event of other.timeline||[])if(codes.has(event.work_code))add(event.fields[key],`관련 후보 · ${event.work_code} · 아직 매칭하지 않은 자료`,event.path,event.reported_at,true);
  }
  return {sources,history};
}
function fieldEditDialog(itemId,key){
  if(state.role!=='predecessor'||state.tab!=='review')return;
  const item=state.revision.payload.items.find(i=>i.id===itemId);if(!item||!labels[key])return;
  const field=item.fields[key]||{value:''};const {sources,history}=fieldSources(item,key);
  const edit={caseId:state.current,revisionId:state.revision.id,hash:state.revision.hash,itemId,key,value:field.value||'',sources};
  const docs=state.details.documents.filter(d=>item.source_documents.includes(d.id));
  modal(`${labels[key]} 수정`,item.fields.title.value,`<div class="field-edit-layout"><section class="field-edit-form"><div class="eyebrow">확인하고 수정하기</div><div class="field-before"><span>현재 값</span><p>${esc(edit.value)||'미기재'}</p>${badge(field.provenance==='HUMAN_ENTERED'?'전임자 입력':'추출값',field.provenance==='HUMAN_ENTERED'?'green':'gray')}</div><label class="form-field" for="fieldEditValue">확인한 ${esc(labels[key])}<textarea id="fieldEditValue" maxlength="2000" rows="${['title','owner','due_date','contacts'].includes(key)?2:5}">${esc(edit.value)}</textarea></label><label class="form-field" for="fieldEditReason">확인 근거·변경 사유 (필수)<textarea id="fieldEditReason" maxlength="1000" rows="3" placeholder="예: 계획보고의 담당 부서를 대조하고 전임자에게 확인"></textarea></label><p class="field-edit-help">이 항목만 새 판본에 저장합니다. 기존 값·원문 근거·변경 사유는 이력에 보존됩니다.${state.details.confirmed?' 보고서에 반영하려면 저장 후 다시 확정하세요.':''}</p><div id="fieldEditError" role="alert"></div>${history.length?`<details class="field-history"><summary>이 항목의 수정 이력 ${history.length}건</summary>${history.map(h=>`<div class="context-block"><b>${esc(h.before)||'미기재'} → ${esc(h.value)||'미기재'}</b><p>${esc(h.reason)}<br>${date(h.changed_at)}</p></div>`).join('')}</details>`:''}</section><section class="field-edit-evidence" aria-label="관련 근거 자료"><div class="field-evidence-heading"><h3>관련 근거 자료</h3><span>${sources.length}개 인용</span></div><p class="muted">현재 값과 이전 보고를 비교하세요. 같은 관리번호의 다른 업무는 참고 후보이며 자동으로 연결하지 않습니다.</p><div class="field-source-list">${sources.map((s,i)=>{const doc=state.details.documents.find(d=>d.id===s.ref.document_revision_id);return `<details class="field-source ${s.related?'related-candidate':''}" ${i===0||s.related?'open':''}><summary><span class="field-source-label">${esc(s.label)}</span><strong>${esc(s.path||doc?.path||'원문 자료')}</strong><span class="field-source-value">${esc(s.value)||'미기재'}</span>${s.reported?`<small>보고일 ${esc(s.reported)}</small>`:''}</summary><div id="fieldSource-${i}" class="field-source-content" aria-live="polite"><p class="muted">원문을 불러오는 중입니다…</p></div></details>`;}).join('')||'<div class="field-no-source">이 항목에 직접 연결된 원문 인용이 없습니다. 아래 업무 자료를 열어 확인하거나 전임자에게 확인한 내용을 사유와 함께 기록하세요.</div>'}</div><details class="field-documents" ${sources.length?'':'open'}><summary>이 업무의 자료 전체 확인 (${docs.length})</summary>${docs.map(d=>`<div class="field-document"><strong>${esc(d.path)}</strong><button class="text-link" data-action="field-document" data-id="${d.id}">추출 본문 보기</button><a class="text-link" href="${apiUrl(`cases/${edit.caseId}/documents/${d.id}/raw`)}" download>원본 다운로드 ↓</a><div class="field-document-body" id="fieldDocument-${d.id}"></div></div>`).join('')||'<p class="muted">연결된 자료가 없는 직접 입력 업무입니다.</p>'}</details></section></div>`,button('close','취소')+button('save-field','이 항목 저장','primary'));
  state.fieldEdit=edit;$('#dialog').classList.add('field-edit-dialog');$('#fieldEditValue').focus();
  for(let i=0;i<sources.length;i++)loadFieldSource(edit,i);
}
async function loadFieldSource(edit,index){
  const entry=edit.sources[index];
  try{
    const s=await api(`cases/${edit.caseId}/blocks/${entry.ref.block_id}`);
    if(state.fieldEdit!==edit||!$('#dialog').open)return;
    $(`#fieldSource-${index}`).innerHTML=`<div class="evidence-location">${esc(s.location)} · 자료 판본 ${esc(s.doc_id.slice(0,8))}</div><blockquote class="quote">${esc(entry.ref.quote)}</blockquote><details class="field-context"><summary>주변 본문</summary>${s.neighbors.map(n=>`<div class="context-block ${n.id===s.id?'quoted-block':''}"><small>${esc(n.location)}</small>${esc(n.text)}</div>`).join('')}</details><div class="field-source-actions"><a class="text-link" href="${apiUrl(`cases/${edit.caseId}/documents/${s.doc_id}/raw`)}" download>원본 다운로드 ↓</a></div>`;
  }catch(error){if(state.fieldEdit===edit&&$('#dialog').open)$(`#fieldSource-${index}`).innerHTML=`<p class="field-load-error">${esc(error.message)}</p>${button('retry-field-source','다시 불러오기','small',`data-index="${index}"`)}`;}
}
async function fieldDocument(el){
  const edit=state.fieldEdit;if(!edit)return;
  const blocks=await api(`cases/${edit.caseId}/documents/${el.dataset.id}/blocks`);
  if(state.fieldEdit!==edit||!$('#dialog').open)return;
  $(`#fieldDocument-${el.dataset.id}`).innerHTML=blocks.map(b=>`<div class="context-block"><small>${esc(b.location)}</small>${esc(b.text)}</div>`).join('')||'<p class="muted">추출된 본문이 없습니다.</p>';
}
async function saveField(){
  const edit=state.fieldEdit;if(!edit)return;
  const value=$('#fieldEditValue').value.trim(),reason=$('#fieldEditReason').value.trim();
  const fail=message=>{$('#fieldEditError').textContent=message;};
  if(edit.key==='title'&&!value){fail('업무명은 비워 둘 수 없습니다.');$('#fieldEditValue').focus();return;}
  if(!reason){fail('확인 근거·변경 사유를 입력해 주세요.');$('#fieldEditReason').focus();return;}
  try{
    await api(`cases/${edit.caseId}/revisions/${edit.revisionId}/items/${edit.itemId}`,{method:'PATCH',body:{expected_hash:edit.hash,fields:{[edit.key]:value},reason}});
  }catch(error){if(state.fieldEdit===edit)fail(error.message);return;}
  if(state.fieldEdit!==edit)return;
  closeDialog();await refresh();toast(`${labels[edit.key]} 항목을 저장했습니다.${state.details.confirmed?' 보고서 반영은 다시 확정해 주세요.':''}`);
}
function deleteDialog(itemId){const item=state.revision.payload.items.find(i=>i.id===itemId);modal('업무 삭제',item.fields.title.value,`<p>초안에서 이 업무를 제외합니다. 이전 판본은 보존됩니다.</p><label class="form-field">삭제 사유 (필수)<input id="editReason" maxlength="1000"></label>`,button('close','취소')+button('delete-item','업무 삭제','danger',`data-id="${itemId}"`));}

function editDialog(itemId){
  const item=state.revision.payload.items.find(i=>i.id===itemId);modal(item?'업무 내용 수정':'업무 직접 추가','변경된 값은 전임자 입력으로 기록하고, 이전 근거는 수정 이력에 보존합니다.',`<div class="form-grid">${Object.entries(labels).map(([key,label])=>`<label class="form-field ${['title','next_action','notes','completed_work','remaining_work','issues','collaborators','contacts'].includes(key)?'wide':''}">${label}${!['title','status','owner','due_date'].includes(key)?`<textarea id="edit_${key}" maxlength="2000">${esc(item?.fields[key]?.value||'')}</textarea>`:`<input id="edit_${key}" maxlength="2000" value="${esc(item?.fields[key]?.value||'')}" placeholder="${key==='due_date'?'예: 2026-11-27 또는 매월 5일':'확인된 내용을 입력하세요'}">`}</label>`).join('')}<label class="form-field wide">변경 사유 (필수)<input id="editReason" maxlength="1000" placeholder="예: 전임자가 최종 제출 일정을 확인"></label></div>`,(item?button('delete-item','업무 삭제','danger small',`data-id="${itemId}"`):'')+button('close','취소')+button('save-item','새 판본으로 저장','primary',`data-id="${itemId||'new'}"`));
}
async function saveItem(itemId,deleted=false){
  const reason=$('#editReason').value.trim();if(!reason)throw new Error('변경 사유를 입력해 주세요.');
  const item=state.revision.payload.items.find(i=>i.id===itemId), fields={};
  if(!deleted)for(const key of Object.keys(labels)){const value=$('#edit_'+key).value.trim();if(!item||value!==(item.fields[key]?.value||''))fields[key]=value;}
  if(!deleted&&!Object.keys(fields).length)throw new Error('변경할 내용을 입력해 주세요.');
  await api(`cases/${state.current}/revisions/${state.revision.id}/items/${itemId}`,{method:'PATCH',body:{expected_hash:state.revision.hash,fields,reason,delete:deleted}});closeDialog();toast('변경 내용을 새 판본으로 저장했습니다.');await refresh();
}
async function showEvidence(itemId,key){
  const item=state.revision.payload.items.find(i=>i.id===itemId);const field=item.fields[key];
  let refs=field.evidence;let history='';let previous=field;
  while(previous.previous){history+=`<div class="notice green"><div><strong>전임자 입력: ${esc(previous.value)}</strong><p>이전 값: ${esc(previous.previous.value)}<br>사유: ${esc(previous.reason)}<br>${date(previous.changed_at)}</p></div></div>`;previous=previous.previous;refs=refs.concat(previous.evidence);}
  if(!refs.length){$('#evidenceBody').innerHTML=history||'<p>원문 근거가 없는 전임자 입력 또는 미확인 항목입니다.</p>';return;}
  const source=await api(`cases/${state.current}/blocks/${refs[0].block_id}`);
  $('#evidenceBody').innerHTML=history+sourceView(source,refs[0].quote)+refs.slice(1).map(ref=>`<button class="search-result" data-action="block" data-id="${ref.block_id}">${esc(ref.quote)} <span>↗</span></button>`).join('');
  if(innerWidth<850)$('#evidenceBody').scrollIntoView({behavior:'smooth',block:'center'});
}
function sourceView(source,quote){return `<div class="evidence-source">${esc(source.path)}</div><div class="evidence-location">${esc(source.location)} · 판본 ${source.doc_id.slice(0,8)}</div><blockquote class="quote">${esc(quote||source.text)}</blockquote><a class="text-link" href="${apiUrl(`cases/${state.current}/documents/${source.doc_id}/raw`)}">원본 다운로드 ↓</a><div class="source-hash">원문 SHA-256<br>${source.source_sha}</div><details><summary class="text-link">주변 원문 함께 보기</summary>${source.neighbors.map(b=>`<div class="context-block"><small>${esc(b.location)}</small>${esc(b.text)}</div>`).join('')}</details>`;}
async function showBlock(id){const source=await api(`cases/${state.current}/blocks/${id}`);if($('#evidenceBody'))$('#evidenceBody').innerHTML=sourceView(source);else modal('원문 근거',source.path,sourceView(source),button('close','닫기'));}
function matchDialog(id){
 const source=state.revision.payload.items.find(i=>i.id===id);const targets=state.revision.payload.items.filter(i=>i.id!==id);
 modal('담당자 확인 후 업무 매칭','명칭이 다른 보고서가 같은 업무인지 원문과 담당자를 확인해 연결합니다.',`<p><b>연결할 업무:</b> ${esc(source.fields.title.value)}</p><p class="muted">${source.timeline?.map(e=>esc(e.path)+' · '+esc(e.work_code||'관리번호 미기재')).join('<br>')||''}</p><label class="form-field">합칠 기준 업무<select id="matchTarget">${targets.map(t=>`<option value="${t.id}">${esc(t.fields.title.value)} · ${esc(t.fields.owner.value||'담당 미확인')} · ${esc(t.timeline?.[0]?.work_code||'')}</option>`).join('')}</select></label><label class="form-field">확인한 담당 부서<input id="matchOwner" maxlength="200" placeholder="예: 디지털지원팀"></label><label class="form-field">확인 근거·매칭 사유<input id="matchReason" maxlength="1000" placeholder="예: HB-004 동일 사업임을 전임자에게 확인"></label><label class="check-row"><input type="checkbox" id="matchCheck"><span>담당자를 확인했고 같은 업무임을 확인했습니다. 기준 업무명으로 연결하고 각 보고 이력은 보존합니다.</span></label>`,button('close','취소')+button('save-match','확인 후 새 판본에 매칭','primary',`data-id="${id}"`));
}
function confirmationDialog(){const rev=state.revision;modal('인수인계본 확정','지금 보고 있는 판본을 최종본으로 고정합니다. 이후 인계하기에서 의견과 함께 전달하세요.',`<p>총 <strong>${rev.payload.items.length}개 업무</strong>를 판본 <strong>${rev.id.slice(0,8)}</strong>로 확정합니다.</p><div class="notice"><p>문서를 확정해도 미확인 사실이 자동으로 검증 완료되지는 않습니다. 남은 주의사항과 원문 근거를 함께 전달합니다.</p></div>${rev.readiness?.missing_fields?`<div class="notice"><p>보고서에 ${rev.readiness.missing_fields}개 항목이 미기재입니다. ${esc(rev.readiness.note)} 확인 필요 상태로 전달할 수 있습니다.</p></div>`:''}${rev.warnings.length?`<ul class="warning-list">${rev.warnings.map(w=>`<li>${esc(w)}</li>`).join('')}</ul>`:''}<label class="check-row"><input type="checkbox" id="confirmCheck"><span>수정 내용과 남은 확인 필요 사항을 확인했으며, 이 판본을 최종 인수인계본으로 확정합니다.</span></label>`,button('close','더 검토하기')+button('do-confirm','이 판본 확정','primary'));}
const demoSets={comprehensive:{name:'종합 인수인계 실무 시연',file:'comprehensive-kit.zip',detail:'5개 사업 · 원본 21개 · 표 95개 · 같은 날짜 판본·수정시각 비교 · 업무 묶기·이전 보고서 연결'},practice:{name:'4개 업무 복합 처리 시연',file:'practice-samples.zip',detail:'계획·착수·중간 보고를 하나의 업무 흐름으로'},versions:{name:'파일명, 버전 혼선 시연',file:'version-samples.zip',detail:'파일명 대신 본문으로 업무와 최신 판본 찾기'},inheritance:{name:'업무연결 시연',file:'inheritance-kit.zip',detail:'이전 인계 보고서 현행화 + 새로운 업무 추가'}};
function demoMenu(){modal('시연 및 샘플 데이터 다운','실행할 시연을 고르거나, 같은 원본 자료를 내려받으세요.',`<div class="demo-set-list">${Object.entries(demoSets).map(([key,d],i)=>`<section class="demo-set-row"><span class="demo-set-number">0${i+1}</span><div><small>샘플 ${i+1}</small><h3>${esc(d.name)}</h3><p>${esc(d.detail)}</p><div class="buttons">${button('demo-config','시연 수행','primary small',`data-kind="${key}"`)}<a class="button small" href="downloads/${d.file}">시연 데이터 다운 받기 ↓</a></div>${key==='comprehensive'?'<p><a class="text-link" href="downloads/comprehensive-report.html" target="_blank" rel="noopener">완성 보고서 예시 ↗</a> · <a class="text-link" href="downloads/comprehensive-guide.md">점검 순서·기대 결과 ↓</a></p>':''}</div></section>`).join('')}</div>`,button('close','닫기'));}
function demoConfig(el){const kind=el.dataset.kind,d=demoSets[kind];state.demoKind=kind;const owner=['inheritance','comprehensive'].includes(kind)?'employee2':state.employee,recipient='employee'+(Number(owner.slice(-1))%4+1);const options=selected=>[1,2,3,4].map(i=>`<option value="employee${i}" ${selected==='employee'+i?'selected':''}>직원 ${i}</option>`).join('');modal(d.name,'인계자와 인수자를 선택하세요. 시연 이름 뒤에 (1), (2) 순서로 번호가 붙습니다.',`<div class="demo-people"><label class="form-field">인계자<select id="demoPredecessor">${options(owner)}</select></label><span aria-hidden="true">→</span><label class="form-field">인수자<select id="demoSuccessor">${options(recipient)}</select></label></div><p class="muted">실행하면 선택한 인계자 화면으로 전환합니다. 기존 보고서는 유지하고 새 시연함을 만듭니다.</p>${['inheritance','comprehensive'].includes(kind)?'<div class="notice">이전 인수 완료 보고서와 현행화·신규 자료를 준비합니다. 이어지는 초안 생성 화면에서 <b>이전에 인수한 보고서 이어서 작성</b>을 체크하세요.</div>':'<p class="muted">자료 등록 후 초안 생성 화면에서 추출 방식과 외부 전송 여부를 선택합니다.</p>'}`,button('demo-menu','뒤로')+button('demo-run','시연 시작','primary'));}
async function runDemoSet(){const owner=$('#demoPredecessor').value,recipient=$('#demoSuccessor').value;if(owner===recipient)throw Error('인계자와 인수자를 서로 다르게 선택해 주세요.');state.employee=owner;localStorage.setItem('handover-employee',owner);$('#roleSelect').value=owner;$('#avatar').textContent=owner.slice(-1);setEmployeeCookie();const result=await api('demo-sets',{method:'POST',body:{kind:state.demoKind,predecessor_id:owner,successor_id:recipient}});closeDialog();state.demoBasis={target:result.target_case_id,source:result.source_case_id};state.cases=await api('cases');await openCase(result.target_case_id,'sources');await generateDialog();}
function helpDialog(){modal('처음이라면 이렇게 시작하세요','실제 화면을 따라 하는 5단계 · 자료와 잔액은 바뀌지 않습니다.',`<div class="support-list"><div><b>1. 자료 등록</b>‘새 인수인계’에서 제목과 받을 직원을 정하고 업무자료를 올립니다. 초안 생성은 분석 방식과 동의를 확인한 뒤 직접 실행합니다.</div><div><b>2. 같은 업무 묶기·초안 검토</b>상단 왼쪽 ‘업무 전체 보고 묶기’에서 같은 업무를 끌어 묶습니다. 항목 옆 연필을 눌러 원문과 수정값을 함께 확인합니다.</div><div><b>3. 보고서 확인·확정</b>목차와 진행 차트로 전체 흐름·현안·남은 일을 검토하고 상단 오른쪽 ‘검토 완료 · 확정하기’를 누릅니다.</div><div><b>4. 의견과 함께 인계</b>‘변경 이력’ 오른쪽 ‘인계하기’에서 받을 직원과 확정 판본을 확인하고 전달 의견과 함께 최종본을 보냅니다.</div><div><b>5. 받은 직원이 인수 확인</b>오른쪽 위에서 인수 직원으로 전환합니다. 인수함에서 전달 의견과 같은 최종 보고서를 읽고 ‘인수 확인’을 누릅니다.</div><p class="muted">직접 해 보려면 홈의 ‘시연 및 샘플 데이터 다운’에서 시연 4종 중 하나를 고르세요. 샘플4는 이전에 인수한 보고서에 새 자료를 반영하는 업무연결 체험입니다.</p></div>`,button('tour-start','시작하기','primary')+button('close','닫기'));}
function loginDialog(){modal('워크스페이스 접속','관리자가 제공한 접속 코드를 입력하세요. 역할 선택과 별도의 공유 접속 보호입니다.',`<label class="form-field">접속 코드<input type="password" id="accessToken" autocomplete="current-password"></label><p><a class="text-link" href="guide" target="_blank" rel="noopener">사용법·샘플·체험 자료는 로그인 없이 볼 수 있습니다 ↗</a></p>`,button('login','접속하기','primary'));}

const actions={
  'archived-cases':async()=>{state.archivedCases=(await api('cases?include_archived=true')).filter(c=>c.archived);modal('보관된 이전 자료','현재 시연 목록에서 분리해 보관한 자료입니다. 원본·확정본·인수 이력은 그대로 유지합니다.',state.archivedCases.map(c=>`<button class="archive-case" data-action="archive-open" data-id="${c.id}"><strong>${esc(c.title)}</strong><small>${esc(c.predecessor)} → ${esc(c.successor)} · ${date(c.created)}</small></button>`).join('')||'<p>보관된 이전 자료가 없습니다.</p>',button('close','닫기'));},'archive-open':async el=>{const c=state.archivedCases.find(c=>c.id===el.dataset.id);if(!state.cases.some(i=>i.id===c.id))state.cases.push(c);closeDialog();await openCase(c.id);},
  'tour-start':()=>startTour(0),'tour-next':()=>startTour((state.tourStep||0)+1),'tour-prev':()=>startTour((state.tourStep||0)-1),
  'demo-menu':demoMenu,'demo-config':demoConfig,'demo-run':runDemoSet,
  'close':closeDialog,'home':async()=>{state.cases=await api('cases');renderHome();},'new-case':caseDialog,'help':helpDialog,
  'open-report':async()=>{state.tab='report';await refresh();},'print-report':()=>$('#reportFrame').contentWindow.print(),
  'open-case':el=>openCase(el.dataset.id),'tab':el=>{state.tab=el.dataset.tab;return refresh();},
  'create-case':async()=>{const title=$('#caseTitle').value.trim();if(!title)throw new Error('인수인계 이름을 입력해 주세요.');const c=await createCase(title,$('#predecessor').value,$('#successor').value);closeDialog();await openCase(c.id,'sources');},
  'start-versions':async()=>{if(!state.config.llm_available){toast('이 비정형 샘플은 Solar 연결이 필요합니다.');return;}toast('HWPX·XLSX·PDF 13개를 본문 기준으로 분석합니다.');const c=await createCase('파일명·버전 혼선 검증 · 중앙부처 4개 사업','김전임 (가상)','이후임 (가상)');await api(`cases/${c.id}/versions-demo`,{method:'POST'});await api(`cases/${c.id}/generate`,{method:'POST',body:{mode:'llm',external_consent:true,request_id:crypto.randomUUID()}});await openCase(c.id,'review');},
  'start-demo':async()=>{toast('계획·착수·중간 보고서 샘플로 인수인계함을 만들고 있습니다.');const ai=state.config.llm_available;const c=await createCase(ai?'4개 업무 흐름 · Solar Pro 4 체험':'4개 업무 흐름 · 샘플','김전임 (가상)','이후임 (가상)');await api(`cases/${c.id}/practice-demo`,{method:'POST'});await api(`cases/${c.id}/generate`,{method:'POST',body:{mode:ai?'llm':'rules',external_consent:ai,request_id:crypto.randomUUID()}});await openCase(c.id,'review');},
  'upload':()=>$('#fileInput').click(),'upload-folder':()=>$('#folderInput').click(),'sample':async()=>{await api(`cases/${state.current}/practice-demo`,{method:'POST'});toast('단계별 보고·실무 기준·예산·연락망·증빙 자료 15개를 등록했습니다. 초안을 생성해 보세요.');await refresh();},
  'report-group':async()=>{await openCase(state.current,'review');groupingDialog();},'report-confirm':async()=>{await openCase(state.current,'review');confirmationDialog();},
  'send-delivery':sendDelivery,
  'match':groupingDialog,'group-open':groupingDialog,'group-save':saveGrouping,'group-select':el=>{state.grouping.selected=el.dataset.id;renderGrouping();},'group-place':el=>moveGroupedItem(state.grouping.selected,el.dataset.id),'group-separate':()=>moveGroupedItem(state.grouping.selected,null),'group-cancel-select':()=>{state.grouping.selected=null;renderGrouping();},'group-undo':()=>{const g=state.grouping;if(g.undo.length){g.groups=g.undo.pop();g.selected=null;g.dirty=true;renderGrouping();}},'group-reset':groupingDialog,
  'save-match':async el=>{if(!$('#matchCheck').checked)throw Error('동일 업무·담당자 확인에 체크해 주세요.');await api(`cases/${state.current}/revisions/${state.revision.id}/match`,{method:'POST',body:{expected_hash:state.revision.hash,source_id:el.dataset.id,target_id:$('#matchTarget').value,owner:$('#matchOwner').value,reason:$('#matchReason').value}});closeDialog();await refresh();toast('보고 이력을 연결한 새 판본을 저장했습니다.');},
  'inheritance-demo':async()=>{const r=await api('inheritance-demo',{method:'POST'});closeDialog();state.employee='employee2';localStorage.setItem('handover-employee',state.employee);$('#roleSelect').value=state.employee;setEmployeeCookie();state.cases=await api('cases');await openCase(r.target_case_id,'sources');toast('현행화·신규 자료를 준비했습니다. 초안 생성에서 이전 보고서 이어서 작성을 체크하세요.');},
  'ring-demo':async()=>{toast('순환 시연함을 준비합니다. 기존 시연함은 재사용합니다.');await api('employee-demo',{method:'POST'});state.cases=await api('cases');renderHome();},
  'generate':generateDialog,'run-generate':async()=>{await api(`cases/${state.current}/generate`,{method:'POST',body:{mode:$('#extractMode').value,external_consent:$('#externalConsent')?.checked||false,image_consent:$('#imageConsent')?.checked||false,basis_case_id:$('#usePreviousReport')?.checked?$('#previousReport').selectedOptions[0].dataset.case:null,basis_revision_id:$('#usePreviousReport')?.checked?$('#previousReport').value:null,request_id:crypto.randomUUID()}});closeDialog();state.tab='review';await refresh();},
  'retry':async el=>{await api(`cases/${state.current}/jobs/${el.dataset.id}/retry`,{method:'POST'});await refresh();},
  'edit-field':el=>fieldEditDialog(el.dataset.id,el.dataset.field),'save-field':saveField,'retry-field-source':el=>loadFieldSource(state.fieldEdit,Number(el.dataset.index)),'field-document':fieldDocument,'delete-dialog':el=>deleteDialog(el.dataset.id),'add-item':()=>editDialog('new'),'save-item':el=>saveItem(el.dataset.id),'delete-item':el=>saveItem(el.dataset.id,true),
  'evidence':el=>showEvidence(el.dataset.id,el.dataset.field),'block':el=>showBlock(el.dataset.id),
  'document':async el=>{const blocks=await api(`cases/${state.current}/documents/${el.dataset.id}/blocks`);const doc=state.details.documents.find(d=>d.id===el.dataset.id);modal('추출한 원문 본문',doc.path,blocks.length?blocks.map(b=>`<div class="context-block"><small>${esc(b.location)}</small>${esc(b.text)}</div>`).join(''):'<p>추출된 본문이 없습니다. 자료의 처리 상태를 확인하세요.</p>',button('close','닫기'));},
  'confirm-dialog':confirmationDialog,'do-confirm':async()=>{if(!$('#confirmCheck').checked)throw new Error('전달할 내용과 주의사항 확인에 체크해 주세요.');await api(`cases/${state.current}/revisions/${state.revision.id}/confirm`,{method:'POST',body:{expected_hash:state.revision.hash,acknowledge_warnings:true}});closeDialog();toast('최종본을 확정했습니다. 인계하기에서 의견과 함께 전달해 주세요.');state.tab='deliver';await refresh();},
  'accept':async()=>{await api(`cases/${state.current}/accept`,{method:'POST',body:{expected_hash:state.revision.hash}});toast('후임자 확인을 기록했습니다.');await refresh();},
  'warnings':()=>modal('확인 필요 사항','문서 확정 이후에도 이 항목은 함께 전달됩니다.',`<ul class="warning-list">${state.revision.warnings.map(w=>`<li>${esc(w)}</li>`).join('')}</ul>`,button('close','확인')),
  'history-detail':async el=>{const rev=await api(`cases/${state.current}/revisions/${el.dataset.id}`);modal('보관된 판본',`${date(rev.created)} · ${rev.id.slice(0,8)} · ${rev.reason}`,rev.payload.items.map(i=>`<div class="context-block"><h3>${esc(i.fields.title.value)}</h3>${Object.entries(i.fields).filter(([k])=>k!=='title').map(([k,f])=>`<p>${labels[k]}: ${esc(f.value)||'미확인'} <small>${esc(f.provenance)} / ${esc(f.review_status)}</small></p>`).join('')}</div>`).join(''),button('close','닫기'));},
  'login':async()=>{await api('login',{method:'POST',body:{token:$('#accessToken').value}});closeDialog();await init();},

  'switch-predecessor':async()=>{state.role='predecessor';localStorage.setItem('handover-role',state.role);await init();}
};
document.addEventListener('click',async event=>{const el=event.target.closest('[data-action]');if(!el||!actions[el.dataset.action])return;event.preventDefault();const disabled=el.disabled;el.disabled=true;const alert=$('#dialog .modal-alert');if(alert)alert.hidden=true;try{await actions[el.dataset.action](el);}catch(e){toast(e.message);}finally{el.disabled=disabled;}});
document.addEventListener('submit',async event=>{if(event.target.id!=='searchForm')return;event.preventDefault();try{const result=await api(`cases/${state.current}/search?q=${encodeURIComponent($('#searchQuery').value)}`);$('#searchResults').innerHTML=result.results.length?result.results.map(b=>`<button class="search-result" data-action="block" data-id="${b.id}">${esc(b.path)} <span>↗</span><p>${esc(b.text)}</p></button>`).join(''):'<p class="muted">일치하는 본문을 찾지 못했습니다. 다른 키워드로 검색해 보세요.</p>';}catch(e){toast(e.message);}});
$('#homeButton').addEventListener('click',()=>actions.home().catch(e=>toast(e.message)));$('#helpButton').addEventListener('click',helpDialog);

$('#fileInput').addEventListener('change',async e=>{if(e.target.files.length)try{await uploadFiles(e.target.files);}catch(err){toast(err.message);}e.target.value='';});
$('#folderInput').addEventListener('change',async e=>{if(e.target.files.length)try{await uploadFiles(e.target.files);}catch(err){toast(err.message);}e.target.value='';});
$('#roleSelect').addEventListener('change',async e=>{state.qaController?.abort();clearTimeout(state.timer);state.current=null;state.details=null;state.revision=null;state.employee=e.target.value;state.role='predecessor';localStorage.setItem('handover-employee',state.employee);setEmployeeCookie();location.hash='';closeDialog();try{await init();}catch(err){toast(err.message);}});
window.addEventListener('hashchange',()=>{
  const id=location.hash.slice(1);
  if(id===state.current||(!id&&!state.current))return;
  if(id&&state.cases.some(c=>c.id===id))openCase(id).catch(e=>toast(e.message));
  else if(!id)actions.home().catch(e=>toast(e.message));
  else toast('이 인수인계함을 찾을 수 없습니다. 목록을 새로 고친 뒤 확인해 주세요.');
});
$('#dialog').addEventListener('close',()=>{if(!$('#dialog').open){state.fieldEdit=null;$('#dialog').classList.remove('field-edit-dialog','grouping-dialog','tour-dialog');}});

let budgetBusy=false;
async function refreshBudget(){
 if(isTourPreview)return;
 refreshImageBudget();
 if(budgetBusy||document.hidden)return;budgetBusy=true;
 try{const response=await fetch(apiUrl('budget'));if(!response.ok)throw new Error();const b=await response.json();state.budget=b;setBudgetBar('solar',b.available&&b.budget_known!==false?b.used_usd+(b.reserved_usd||0)+(b.unknown_usd||0):null,b.budget_usd);$('#budgetBalance').textContent=b.available&&b.remaining_usd!=null?`$${b.remaining_usd.toFixed(4)} / $${b.budget_usd.toFixed(0)}`:b.available?'공유 잔액 확인 중':'모델 미연결';$('#budgetButton').title=b.available?b.note:'Solar 연결 후 표시됩니다.';}
 catch(e){$('#budgetBalance').textContent='잔액 확인 불가';setBudgetBar('solar',null);state.budget=null;}finally{budgetBusy=false;}
}
function budgetDialog(){const b=state.budget;if(!b){toast('사용량을 불러오지 못했습니다. 잠시 후 다시 확인하세요.');refreshBudget();return;}if(!b.available){toast('Solar 모델을 먼저 연결하세요.');return;}if(b.budget_known===false){toast(b.note);return;}modal(b.shared?'Solar · PoC10/13 공유 한도':'Solar 전용 키 · 사용량',b.shared?'두 서비스의 사용·예약·미확정 비용을 함께 차감합니다.':'이 앱의 기록으로 계산한 추정 잔액입니다.',`<div class="budget-summary"><strong>$${b.remaining_usd.toFixed(4)}</strong><p>$${b.budget_usd.toFixed(2)} 기준 · 기록된 추정 사용액 $${b.used_usd.toFixed(6)}</p></div>${b.shared?`<p>진행 중 예약 $${(b.reserved_usd||0).toFixed(6)} · 미확정 보수 차감 $${(b.unknown_usd||0).toFixed(6)}</p>`:''}<p>집계 시작: ${esc(new Date(b.tracked_since).toLocaleString('ko-KR'))}</p><p>호출 ${b.calls}회 · 사용량 미확인 ${b.unknown_calls}회</p><p>입력 ${b.prompt_tokens.toLocaleString()}토큰 (캐시 ${b.cached_tokens.toLocaleString()}) · 출력 ${b.completion_tokens.toLocaleString()}토큰</p><p class="notice">${esc(b.note)} ${b.shared?'공유 한도가 부족하면 새 모델 호출을 차단합니다.':'이 표시는 API의 결제 한도를 설정하거나 차단하는 기능이 아닙니다.'}</p><p>Solar Pro 4 정가: 100만 토큰당 입력 $0.30 · 캐시 $0.06 · 출력 $1.20</p><div class="buttons"><a class="button" href="${esc(b.console_url)}" target="_blank" rel="noopener">실제 잔액 · Upstage 콘솔 ↗</a><a class="button" href="${esc(b.pricing_url)}" target="_blank" rel="noopener">공식 요금표 ↗</a></div>`,button('close','닫기'));}
document.addEventListener('click',e=>{if(e.target.closest('#budgetButton'))budgetDialog();});
setInterval(refreshBudget,30000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshBudget();});

function imageReviewView(rev){
 if(!rev)return '';const rows=rev.payload.items.flatMap(i=>(i.image_reviews||[]).map(v=>({...v,title:i.fields.title.value})));
 if(!rows.length&&!rev.payload.image_notes?.length)return '';
 return `<details class="model-usage"><summary>최신본 그림 판독 참고 · ${rows.length}개</summary><p>본문 판본 선택 이후 채택된 파일만 판독했습니다. 확정 사실이 아닌 AI 전사이며 원본 대조가 필요합니다.</p>${rows.map(v=>`<details><summary>${esc(v.title)} · ${esc(v.path)} · ${v.cached?'저장 결과 재사용':esc(v.model||'gpt-5.4')}</summary><img src="${apiUrl(`cases/${state.current}/images/${v.image_sha}`)}" alt="판독한 원본 그림" class="image-review-original"><p class="quote">${esc(v.text)}</p></details>`).join('')}<ul>${(rev.payload.image_notes||[]).map(n=>`<li>${esc(n)}</li>`).join('')}</ul></details>`;
}
let imageBudgetBusy=false;
async function refreshImageBudget(){
 if(isTourPreview)return;
 if(imageBudgetBusy||document.hidden)return;imageBudgetBusy=true;
 try{const r=await fetch(apiUrl('budget/images'));if(!r.ok)throw Error();const b=await r.json();state.imageBudget=b;
 setBudgetBar('gpt',b.available?b.used:null,b.limit,b.remaining);
 $('#gptBudgetBalance').textContent=b.available&&b.remaining!=null?'공용 '+Number(b.remaining).toLocaleString()+' 토큰':b.note||'확인 불가';
 const c=b.monthly_credit;setBudgetBar('credit',c?.status==='AVAILABLE'?c.used:null,c?.limit,c?.remaining);
 $('#creditBudgetBalance').textContent=c?.remaining!=null?`공용 $${Number(c.remaining).toFixed(2)} / $${Number(c.limit).toFixed(0)}`:'공용 잔액 확인 불가';
 $('#imageRoute').textContent=b.available?(b.next_model==='gpt-5.4'?'그림분석 · 일일 토큰 우선':'그림분석 · Terra 전환 예정'):'그림분석 · 연결 확인';
 }catch(e){$('#gptBudgetBalance').textContent='확인 불가';$('#creditBudgetBalance').textContent='확인 불가';setBudgetBar('gpt',null);setBudgetBar('credit',null);state.imageBudget=null;}finally{imageBudgetBusy=false;}
}
document.addEventListener('click',e=>{
 if(!e.target.closest('#gptBudgetButton'))return;const b=state.imageBudget,c=b?.monthly_credit;
 modal('그림 분석 · 일일 토큰 + 월 공용 예산','PoC7·PoC10·PoC11·PoC13 공용 · 그림 분석을 직접 선택할 때만 실행합니다.',b?.available?`
 <p><b>GPT-5.4 → GPT-6.1 Terra 자동 전환</b><br>일일 잔여가 그림 1건의 예약량(${Number(b.reservation_tokens).toLocaleString()} 토큰)보다 적으면 Terra가 월 공용 예산으로 처리합니다. 일일 한도가 갱신되면 GPT-5.4를 먼저 사용합니다.</p>
 <h3>GPT-5.4 · 일일 공용 토큰</h3><p><strong>${Number(b.remaining).toLocaleString()} 토큰 남음</strong> / ${Number(b.limit).toLocaleString()} 토큰</p>
 <table class="budget-breakdown"><tbody><tr><th>실측 사용 · 입력+출력</th><td>${Number(b.used).toLocaleString()}</td></tr><tr><th>처리 중 예약</th><td>${Number(b.reserved).toLocaleString()}</td></tr><tr><th>사용량 미확정</th><td>${Number(b.unknown).toLocaleString()}</td></tr></tbody></table>
 <h3>GPT-6.1 Terra · 월 무료 예산 (공용)</h3>${c?.remaining!=null?`<p><strong>$${Number(c.remaining).toFixed(4)} 남음</strong> / 월 $${Number(c.limit).toFixed(0)}</p><p>누적 사용 $${Number(c.used).toFixed(4)} · 처리 중 예약 $${Number(c.reserved).toFixed(4)} · 미확정 $${Number(c.unknown).toFixed(4)}</p><p class="muted">${esc(c.note)}</p>`:'<p>월 공용 잔액을 확인할 수 없습니다. 예산 예약이 승인되어야 호출합니다.</p>'}
 <p class="muted">두 잔여량 모두 사용·예약·미확정을 차감한 공용 원장 추정치입니다. 제공사 확정 청구 잔액과 다를 수 있습니다. 월 예산까지 부족하면 그림 분석을 중단합니다.</p>
 ${b.own_image_usage?`<div class="notice"><b>업무바통 그림 판독 · 같은 UTC 날짜</b><br>${b.own_image_usage.calls}회 · 입력 ${Number(b.own_image_usage.input_tokens).toLocaleString()} + 출력 ${Number(b.own_image_usage.output_tokens).toLocaleString()} 토큰</div>`:''}
 <p>본문은 Solar, 최신 파일의 그림만 선택 모델로 처리합니다. 같은 그림의 저장 결과는 재사용합니다.</p><a class="text-link" href="downloads/employee-kit.zip" download>같은 파일명·최신 그림 판독 시연 자료 받기 ↓</a><p><small>조회 ${date(b.checked_at)}</small></p>`:`<p>${esc(b?.note||'공유 한도 확인 불가')}</p>`,button('close','닫기'));
});

if(isTourPreview)initTourPreview();else init();

function setBudgetBar(name,used,limit,remaining){const bar=$('#'+name+'UsageBar'),label=$('#'+name+'UsagePercent');if(!bar||!label)return;const known=used!=null&&Number.isFinite(Number(used))&&Number(limit)>0;const pct=known?Math.max(0,Math.min(100,100*Number(used)/Number(limit))):0;bar.value=known?(remaining!=null?Math.max(0,Math.min(100,100*Number(remaining)/Number(limit))):100-pct):0;label.textContent=known?`${pct.toFixed(pct<1?2:1)}% 사용`:'사용률 확인 불가';bar.setAttribute('aria-valuetext',known?`잔여 ${bar.value.toFixed(1)}% · ${label.textContent}`:'잔여량 확인 불가');}
