/* Uses production renderers in a separate frame; input handling never sends API requests. */
async function initTourPreview(){
 const step=Math.max(0,Math.min(4,Number(new URLSearchParams(location.search).get('walkthrough'))||0));
 const sample=await fetch('assets/tour-sample.json').then(r=>r.json());
 const d=sample.details,r=sample.revision;d.id='tour-only';d.title='한빛시 4개 업무 · 인수인계 상세실무편 (합성 시연)';d.predecessor_id='employee1';d.successor_id='employee2';d.predecessor='직원 1';d.successor='직원 2';d.jobs=[];d.current=r.id;d.confirmed=step>=2?r.id:null;d.accepted=null;d.deliveries=[];
 // Keep the same confirmed sample revision as the report shown below.
 if(step===4)d.deliveries=[{id:'tour-delivery',case_id:d.id,revision_id:r.id,revision_hash:r.hash,sender_id:'employee1',recipient_id:'employee2',message:'시설 점검의 미접수 증빙을 우선 확인해 주세요. 다음 주 일정은 관계 부서와 협의해 두었습니다.',sent_at:'2026-11-10T01:10:00+09:00'}];
 state.current=d.id;state.details=d;state.revision=r;state.cases=[d];state.employee=step===4?'employee2':'employee1';state.role=step===4?'successor':'predecessor';state.tab=['sources','review','report','deliver','report'][step];state.config={llm_available:true,vision_available:true};state.deliveryDrafts={'tour-only':'미접수 증빙을 우선 확인하고 다음 주 일정을 협의해 주세요.'};
 document.body.classList.add('case-workspace','tour-preview');document.body.classList.remove('inbox-mode');$('#roleSelect').value=state.employee;$('#roleSelect').disabled=true;$('#avatar').textContent=state.employee.slice(-1);
 $('#budgetBalance').textContent='사용 안내 · 호출 없음';$('#gptBudgetBalance').textContent='가상 화면';$('#creditBudgetBalance').textContent='실제 잔액 사용 없음';
 renderSidebar();renderCase();
 document.querySelectorAll('input[type=file]').forEach(e=>e.disabled=true);
 const next=()=>parent.postMessage({type:'handover-tour-next'},location.origin);
 const highlight=selector=>{document.querySelectorAll('.tour-live-highlight').forEach(e=>e.classList.remove('tour-live-highlight'));const el=document.querySelector(selector);if(el){el.classList.add('tour-live-highlight');el.scrollIntoView({block:'center',behavior:'instant'});}return el;};
 const targets=['.upload-zone','.report-work-actions .report-work-action:first-child','.report-work-confirm','.delivery-compose','.success-header'];
 requestAnimationFrame(()=>highlight(targets[step]));
 // Suppress navigation and forms before production handlers; only local grouping is allowed.
 document.addEventListener('drop',e=>{if(!e.target.closest('#groupingBoard')){e.preventDefault();e.stopImmediatePropagation();}},true);
 document.addEventListener('submit',e=>{e.preventDefault();e.stopImmediatePropagation();},true);
 document.addEventListener('click',e=>{
  const action=e.target.closest('[data-action]')?.dataset.action;
  if(step===1&&action==='group-open'){
   e.preventDefault();e.stopImmediatePropagation();groupingDialog();new MutationObserver(()=>requestAnimationFrame(()=>highlight('.grouping-columns'))).observe($('#groupingBoard'),{childList:true});requestAnimationFrame(()=>{highlight('.grouping-columns');const save=document.querySelector('[data-action="group-save"]');if(save)save.disabled=false;});return;
  }
  if(step===1&&$('#dialog').open&&action&&['group-select','group-place','group-separate','group-cancel-select','group-undo','group-reset'].includes(action))return;
  if(step===1&&$('#dialog').open&&!action&&e.target.closest('input,summary,details'))return;
  if(step===1&&action==='close'){e.preventDefault();e.stopImmediatePropagation();closeDialog();highlight(targets[step]);return;}
  if(step===3&&e.target.closest('#deliveryMessage,#deliveryAcknowledge'))return;
  e.preventDefault();e.stopImmediatePropagation();
  if(step===0&&e.target.closest('.upload-zone'))next();
  if(step===1&&action==='group-save')next();
  if(step===2&&action==='report-confirm')next();
  if(step===3&&action==='send-delivery'){
   if(!$('#deliveryMessage').value.trim()||!$('#deliveryAcknowledge').checked){$('#deliveryError').textContent='전달 의견을 적고 확인에 체크해 주세요.';return;}next();
  }
  if(step===4&&action==='accept')next();
 },true);
}
