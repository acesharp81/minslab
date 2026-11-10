/* Report reading workspace: DOM-only navigation, isolated scroll, cited answers. */
let readerCleanup=()=>{};
function disposeReportReader(){if(state.readerController){state.readerController.abort();state.readerController=null;state.readerBusy=false;}readerCleanup();readerCleanup=()=>{};document.body.classList.remove('report-reading');}
function readerPanel(panel){const root=$('#reportReader');if(!root)return;root.dataset.panel=root.dataset.panel===panel?'':panel;const toggle=$(`[data-reader-panel="${panel}"]`);if(toggle)toggle.setAttribute('aria-expanded',String(root.dataset.panel===panel));if(root.dataset.panel===panel){const focus=panel==='chat'?$('#readerQuestion'):$('#reportToc a');focus?.focus({preventScroll:true});}}
function reportReaderView(link){
 return `<div class="report-reader" id="reportReader" data-panel=""><aside class="reader-toc" aria-label="보고서 목차"><div class="reader-panel-heading"><strong>보고서 목차</strong><button type="button" class="reader-panel-close" data-reader-panel="toc" aria-label="목차 닫기">×</button></div><nav id="reportToc" aria-label="보고서 항목 바로 이동"><p class="muted">목차를 불러오는 중입니다.</p></nav></aside><iframe id="reportFrame" class="report-frame" title="확정 인수인계 보고서" src="${link}"></iframe><aside class="reader-chat" aria-label="보고서 챗봇"><div class="reader-panel-heading"><strong>보고서 챗봇</strong><button type="button" class="reader-panel-close" data-reader-panel="chat" aria-label="챗봇 닫기">×</button></div><p class="reader-chat-intro">확정 보고서 우선 · 참고자료 근거 함께 확인</p><div id="readerChatLog" class="reader-chat-log" role="log" aria-label="보고서 질문과 답변" aria-live="polite"></div><form id="readerChatForm" class="reader-chat-form"><label for="readerMode">답변 방식</label><select id="readerMode">${state.config.llm_available?'<option value="llm">Solar Pro 4 · AI 질의</option>':''}<option value="local">키워드 검색 · 외부 전송 없음</option></select>${state.config.llm_available?'<label class="reader-consent"><input type="checkbox" id="readerConsent"><span>AI 질의 시 질문·이전 질문·보고서·관련 자료 전송에 동의합니다.</span></label>':''}<label for="readerQuestion" class="sr-reader">보고서 질문</label><textarea id="readerQuestion" rows="2" maxlength="500" required placeholder="예: 정산에서 당장 처리할 일은?" aria-describedby="readerChatError"></textarea><p id="readerChatError" role="alert"></p><button type="submit" class="button primary" id="readerAsk">질문하기</button></form></aside></div>`;
}
function mountReportReader(frame){
 document.body.classList.add('report-reading');window.scrollTo(0,0);
 const key=state.current+':'+state.revision.id;
 if(state.readerKey!==key){state.readerKey=key;state.readerAnswers=[];state.readerDraft='';state.readerConsent=false;state.readerMode=state.config.llm_available?'llm':'local';state.readerBusy=false;}
 const textarea=$('#readerQuestion'),mode=$('#readerMode'),consent=$('#readerConsent');
 textarea.value=state.readerDraft||'';mode.value=state.readerMode;if(consent)consent.checked=!!state.readerConsent;
 textarea.addEventListener('input',()=>{state.readerDraft=textarea.value;});mode.addEventListener('change',()=>{state.readerMode=mode.value;});consent?.addEventListener('change',()=>{state.readerConsent=consent.checked;});
 renderReaderChat();
 let offScroll=()=>{},disposed=false;
 const loaded=()=>{
  if(disposed)return;offScroll();
  const doc=frame.contentDocument,win=frame.contentWindow;if(!doc?.body)return;
  // Modify only this displayed DOM; exported/confirmed report stays immutable.
  const headings=[...doc.querySelectorAll('h1,h2,h3')].filter(h=>!h.closest('details')&&h.textContent.trim());
  let parent=-1;const rows=[];
  headings.forEach((h,i)=>{if(!h.id)h.id='reader-heading-'+i;const label=h.textContent.trim();let ancestor=-1;
   if(h.tagName==='H3')ancestor=parent;
   else if(h.tagName==='H2'&&label.includes(' · 다음 담당자의 실행서'))ancestor=rows.findIndex(r=>r.label===label.split(' · 다음 담당자의 실행서')[0]);
   const level=ancestor>=0?rows[ancestor].level+1:1;
   rows.push({element:h,id:h.id,label,level,parent:ancestor});if(h.tagName!=='H3')parent=i;
  });
  const link=(r,i)=>`<a class="toc-level-${r.level}" href="#${esc(r.id)}" data-reader-index="${i}">${esc(r.label)}</a>`;
  const branchHTML=(r,i)=>{const children=rows.map((child,j)=>child.parent===i?branchHTML(child,j):'').join('');return children?`<details class="toc-branch" data-toc-parent="${i}"><summary aria-label="${esc(r.label)} 하위 목차 펼치기 또는 접기"><span class="toc-arrow" aria-hidden="true">▸</span>${link(r,i)}</summary><div class="toc-children">${children}</div></details>`:link(r,i);};
  $('#reportToc').innerHTML=rows.map((r,i)=>r.parent<0?branchHTML(r,i):'').join('');
  $('#reportToc').querySelectorAll('.toc-branch').forEach(branch=>{const a=branch.querySelector(':scope > summary > a');a.setAttribute('aria-expanded','false');branch.addEventListener('toggle',()=>a.setAttribute('aria-expanded',String(branch.open)));});
  const links=rows.map((r,i)=>$('#reportToc').querySelector(`[data-reader-index="${i}"]`));let scheduled=0,last=-1;
  const update=()=>{scheduled=0;let active=0;for(let i=0;i<rows.length;i++){if(rows[i].element.getBoundingClientRect().top<=100)active=i;else break;}if(active===last)return;last=active;links.forEach((a,i)=>{if(i===active)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');});const ancestors=[];let ancestor=rows[active].parent;while(ancestor>=0){ancestors.push(ancestor);ancestor=rows[ancestor].parent;}$('#reportToc').querySelectorAll('.toc-branch').forEach(branch=>branch.classList.toggle('contains-active',ancestors.includes(Number(branch.dataset.tocParent))));const nav=$('#reportToc'),target=[active,...ancestors].map(i=>links[i]).find(a=>a.checkVisibility()),ar=target?.getBoundingClientRect(),nr=nav.getBoundingClientRect();if(ar&&ar.top<nr.top)nav.scrollTop+=ar.top-nr.top-8;else if(ar&&ar.bottom>nr.bottom)nav.scrollTop+=ar.bottom-nr.bottom+8;};
  const onScroll=()=>{if(!scheduled)scheduled=win.requestAnimationFrame(update);};win.addEventListener('scroll',onScroll,{passive:true});update();
  $('#reportToc').onclick=event=>{const a=event.target.closest('[data-reader-index]');if(!a)return;event.preventDefault();const branch=a.parentElement.tagName==='SUMMARY'?a.parentElement.parentElement:null;if(branch){branch.open=!branch.open;a.setAttribute('aria-expanded',String(branch.open));}const r=rows[Number(a.dataset.readerIndex)];r.element.setAttribute('tabindex','-1');if(event.detail===0&&!branch)r.element.focus({preventScroll:true});win.scrollTo({top:Math.max(0,win.scrollY+r.element.getBoundingClientRect().top-18),behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'});if(!branch&&matchMedia('(max-width:1250px)').matches)$('#reportReader').dataset.panel='';};
  offScroll=()=>{win.removeEventListener('scroll',onScroll);if(scheduled)win.cancelAnimationFrame(scheduled);};
 };
 frame.addEventListener('load',loaded);if(frame.contentDocument?.readyState==='complete'&&frame.contentDocument.querySelector('h1'))loaded();
 readerCleanup=()=>{disposed=true;offScroll();frame.removeEventListener('load',loaded);};
}
function conversationHTML(a){
 return (a.paragraphs||[]).map(p=>`<div class="conversation-paragraph"><p>${esc(p.text)}</p><details class="conversation-citations"><summary>근거 확인</summary>${(p.fact_ids||[]).map(id=>{const f=a.facts.find(f=>f.id===id);if(!f)return '';return `<section><b>${esc(f.title)} · ${esc(f.label)}</b><p>${esc(f.value)}</p><small>${f.provenance==='HUMAN_ENTERED'?'인계자 수정값':'확정 보고서 기록'}${f.review_status!=='CONFIRMED'?' · 항목 검토 필요':''}</small>${f.evidence.map(ref=>button('block','원문 근거 ↗','small',`data-id="${esc(ref.block_id)}"`)).join('')}</section>`;}).join('')}${(p.background_ids||[]).map(id=>{const b=a.background.find(b=>b.ref_id===id);return b?`<section><b>미확정 참고자료 · ${esc(b.path)}</b><p>${esc(b.text)}</p>${button('block','자료 열기 ↗','small',`data-id="${esc(b.id)}"`)}</section>`:'';}).join('')}</details></div>`).join('');
}
function renderReaderChat(){
 const log=$('#readerChatLog');if(!log)return;
 const answers=state.readerAnswers||[];
 log.innerHTML=answers.length?answers.map(a=>`<article class="reader-exchange"><p class="reader-question">${esc(a.question)}</p><div class="reader-answer"><p class="muted">${esc(a.message)}</p>${conversationHTML(a)}${a.paragraphs?.length?'<details class="reader-evidence"><summary>답변 근거 '+a.facts.length+'개 확인</summary>':''}${a.facts.map(f=>`<section class="reader-fact"><h4>${esc(f.title)} · ${esc(f.label)}</h4><p>${esc(f.value)}</p><small>${f.provenance==='HUMAN_ENTERED'?'인계자 입력':'확정 보고서 기록'}</small>${f.evidence.map(ref=>button('block','원문 근거 ↗','small',`data-id="${ref.block_id}"`)).join('')}</section>`).join('')}${a.paragraphs?.length?'</details>':''}${a.background.length?`<details class="reader-background"><summary>참고자료 ${a.background.length}건 확인</summary><p class="muted">원문 보충 자료입니다. 과거 기록일 수 있으며 확정값을 대체하지 않습니다.</p>${a.background.map(b=>`<section><h4>${esc(b.path)}</h4><small>${esc(b.location)}</small><p>${esc(b.text)}</p>${button('block','자료 열기 ↗','small',`data-id="${b.id}"`)}</section>`).join('')}</details>`:''}<small>${a.mode==='llm'?'Solar Pro 4':'키워드 검색'} · 판본 ${esc(a.revision_id.slice(0,8))}</small></div></article>`).join(''):`<div class="reader-chat-welcome"><b>보고서를 읽다가 바로 물어보세요.</b><p>예: 당장 처리할 현안은?<br>공모사업 예산은?<br>정산 G05의 영수증 상태는?</p><small>답변은 확정본의 값과 출처를 표시합니다. 근거가 없으면 확인이 필요하다고 안내합니다.</small></div>`;
 if(state.readerBusy)log.insertAdjacentHTML('beforeend',liveAnswerHTML(state.readerPending||'',state.readerLiveText||''));
 $('#readerAsk').disabled=!!state.readerBusy;$('#readerAsk').textContent=state.readerBusy?'확인 중…':'질문하기';log.scrollTop=log.scrollHeight;
}
async function askReader(event){
 event.preventDefault();if(state.readerBusy)return;
 const question=$('#readerQuestion').value.trim(),mode=$('#readerMode').value,consent=$('#readerConsent')?.checked||false,error=$('#readerChatError');error.textContent='';
 if(question.length<2){error.textContent='질문을 두 글자 이상 입력해 주세요.';return;}
 if(mode==='llm'&&!consent){error.textContent='AI 질의의 자료 전송 동의를 확인해 주세요.';return;}
 const key=state.readerKey,id=state.current,revision=state.revision.id;state.readerBusy=true;state.readerLiveText='';state.readerPending=question;state.readerDraft=question;state.readerMode=mode;state.readerConsent=consent;renderReaderChat();
 const controller=new AbortController();state.readerController=controller;
 const painter=textPainter(()=>state.readerKey===key?$('#readerChatLog .live-text'):null,()=>$('#readerChatLog'));
 controller.signal.addEventListener('abort',()=>painter.stop(),{once:true});
 try{
  const body={question,mode,external_consent:consent,expected_revision:revision,include_sources:true,previous_questions:(state.readerAnswers||[]).slice(-4).map(a=>a.question)};
  const answer=mode==='llm'?await streamQuestion(`cases/${id}/questions`,body,text=>{if(state.readerKey===key){state.readerLiveText+=text;painter.push(text);}},controller.signal):await api(`cases/${id}/questions`,{method:'POST',body});
  await painter.drain();
  if(state.readerKey===key&&!controller.signal.aborted){state.readerAnswers=[...(state.readerAnswers||[]),answer].slice(-10);state.readerDraft='';if($('#readerQuestion'))$('#readerQuestion').value='';}
 }catch(e){if(e.name!=='AbortError'&&state.readerKey===key&&$('#readerChatError'))$('#readerChatError').textContent=e.message;}
 finally{painter.stop();if(state.readerController===controller){state.readerController=null;state.readerBusy=false;state.readerPending='';state.readerLiveText='';if(state.tab==='report')renderReaderChat();}}

}
document.addEventListener('click',event=>{const b=event.target.closest('[data-reader-panel]');if(b){event.preventDefault();readerPanel(b.dataset.readerPanel);}});
document.addEventListener('submit',event=>{if(event.target.id==='readerChatForm')askReader(event);});
