/* Staged grouping: cancel/undo are local; save writes one immutable revision. */
function groupingDialog(){
 if(state.role!=='predecessor'||!state.revision)return;
 const items=state.revision.payload.items;
 state.grouping={caseId:state.current,revisionId:state.revision.id,hash:state.revision.hash,items:structuredClone(items),groups:items.map(i=>({id:i.id,item_ids:[i.id],title:i.fields.title.value,owner:i.fields.owner.value||'',automatic:autoGroup(i)})),undo:[],selected:null,dirty:false};
 modal('같은 업무끼리 묶기','', '<div id="groupingBoard"></div>',button('group-reset','처음대로','ghost')+button('close','취소')+button('group-save','묶음 저장','primary'));
 $('#dialog').classList.add('grouping-dialog');renderGrouping();
}
function autoGroup(i){const es=i.timeline||[],codes=new Set(es.map(e=>e.work_code).filter(Boolean));return i.source_documents.length>1&&codes.size===1&&es.every(e=>e.work_code);}
function groupTile(id,compact=false){const g=state.grouping,item=g.items.find(i=>i.id===id),codes=[...new Set((item.timeline||[]).map(e=>e.work_code).filter(Boolean))];
 return `<div class="group-tile ${compact?'compact-tile':''} ${g.selected===id?'chosen':''}" draggable="true" data-group-item="${id}" tabindex="0" role="button" aria-label="${esc(item.fields.title.value)} 선택 후 대상 묶음으로 이동"><span class="drag-grip" aria-hidden="true">⠿</span><div><strong title="${esc(item.fields.title.value)}">${esc(item.fields.title.value)}</strong><small>${esc(item.fields.owner.value||'담당 확인 필요')} · ${item.source_documents.length}개 자료</small>${codes.length?`<span class="group-code">${esc(codes.join(' · '))}</span>`:''}<details><summary>원문 ${item.source_documents.length}개 보기</summary>${(item.timeline||[]).map(e=>`<p><b>${esc(e.path)}</b><br>${esc(e.reported_at||'기준일 미상')} · ${esc(e.fields.status?.value||'')}<br>${esc(e.fields.scope?.value||'')}</p>`).join('')}</details></div><button class="group-move-button" type="button" data-action="group-select" data-id="${id}" aria-label="${esc(item.fields.title.value)} 이동할 묶음 선택">이동 ↗</button></div>`;
}
function renderGrouping(){const g=state.grouping;if(!g||!$('#groupingBoard'))return;const grouped=g.groups.filter(x=>x.automatic||x.item_ids.length>1),pending=g.groups.filter(x=>!x.automatic&&x.item_ids.length===1);
 const scrolls=[...document.querySelectorAll('.group-stack')].map(e=>e.scrollTop);
 const card=x=>`<section class="group-drop ${x.automatic?'auto-group':''} ${g.lastMoved===x.id?'just-moved':''}" data-group-target="${x.id}"><div class="group-box-head"><span>${x.item_ids.length>1?'직접 묶음':x.automatic?'✓ 자동 매칭 · 사업번호 일치':'확인할 업무'}</span><b>${x.item_ids.reduce((n,id)=>n+g.items.find(i=>i.id===id).source_documents.length,0)}개 자료</b></div><div class="group-edit-row"><label class="sr-only" for="group-title-${x.id}">묶음 업무명</label><input id="group-title-${x.id}" class="group-name" value="${esc(x.title)}" data-group-field="title" data-group="${x.id}" aria-label="묶음 업무명" maxlength="200"><label class="group-owner">담당<input value="${esc(x.owner)}" data-group-field="owner" data-group="${x.id}" aria-label="묶음 담당자" maxlength="200" placeholder="담당자 확인"></label></div><div class="group-members">${x.item_ids.map(id=>groupTile(id,x.item_ids.length===1)).join('')}</div><div class="drop-hint">＋ 같은 업무를 여기에 놓기</div>${g.selected?button('group-place','선택한 업무를 여기에 묶기','small',`data-id="${x.id}"`):''}</section>`;
 $('#groupingBoard').innerHTML=`<div class="grouping-overview"><div><strong>${g.items.length}</strong>개 후보 <span>→</span> <strong>${g.groups.length}</strong>개 업무</div><p>카드를 끌어 같은 업무에 놓으세요 · 목록 끝에서 자동 스크롤</p>${button('group-undo','↶ 되돌리기','small',g.undo.length?'':'disabled')}</div><div class="grouping-columns"><section><h3>묶인 업무 <span>${grouped.length}</span></h3><div class="group-stack" data-group-scroll="grouped" tabindex="0" aria-label="묶인 업무 목록">${grouped.map(card).join('')||'<div class="group-empty">▤ + ▤ → ▤<br>같은 업무를 모으면 여기에 표시됩니다.</div>'}</div></section><section><h3>확인하고 묶을 업무 <span>${pending.length}</span></h3><div class="group-stack" data-group-scroll="pending" tabindex="0" aria-label="확인할 업무 목록">${pending.map(card).join('')||'<div class="group-empty">✓ 모든 후보가 묶음에 들어 있습니다.</div>'}</div></section></div>${g.selected?`<div class="group-selected-bar">이동할 묶음을 고르세요 ${button('group-separate','별도 업무로 분리','small')}${button('group-cancel-select','선택 해제','small ghost')}</div>`:''}<p class="group-save-note">원문과 보고 이력은 모두 보존됩니다. 저장 후 초안에서 최신 기준본과 적용값을 확인하세요.</p><div id="groupingError" role="alert"></div>`;
 document.querySelectorAll('.group-stack').forEach((el,i)=>{el.scrollTop=scrolls[i]||0;});
 const save=$('[data-action="group-save"]');save.textContent=`${g.groups.length}개 업무로 저장`;save.disabled=!g.dirty;
}
function rememberGroups(){const g=state.grouping;g.undo.push(structuredClone(g.groups));g.dirty=true;}
function moveGroupedItem(id,targetId){const g=state.grouping,source=g.groups.find(x=>x.item_ids.includes(id)),target=g.groups.find(x=>x.id===targetId);if(!source||source===target)return;
 rememberGroups();source.item_ids=source.item_ids.filter(x=>x!==id);
 if(target){target.item_ids.push(id);target.automatic=false;}else{const item=g.items.find(i=>i.id===id);g.groups.push({id:'g'+crypto.randomUUID(),item_ids:[id],title:item.fields.title.value,owner:item.fields.owner.value||'',automatic:autoGroup(item)});}
 g.groups=g.groups.filter(x=>x.item_ids.length);g.selected=null;g.lastMoved=target?.id;renderGrouping();
}
async function saveGrouping(){const g=state.grouping;if(!g)return;if(g.groups.some(x=>!x.title.trim()||!x.owner.trim())){$('#groupingError').textContent='묶음의 업무명과 담당자를 확인해 주세요.';return;}
 try{await api(`cases/${g.caseId}/revisions/${g.revisionId}/groups`,{method:'POST',body:{expected_hash:g.hash,groups:g.groups.map(({item_ids,title,owner})=>({item_ids,title,owner}))}});closeDialog();state.grouping=null;state.tab='review';await refresh();toast('업무 묶음을 새 초안에 저장했습니다. 확정 보고서는 검토 후 다시 확정하세요.');}catch(e){$('#groupingError').textContent=e.message;}
}
// Keep the two lists independently scrollable while a native drag is held at an edge.
const groupingDrag={id:null,x:0,y:0,frame:null,lastTime:0};
function stopGroupingDrag(){
 cancelAnimationFrame(groupingDrag.frame);groupingDrag.id=null;groupingDrag.frame=null;groupingDrag.lastTime=0;
 document.querySelectorAll('.drag-over,.dragging').forEach(x=>x.classList.remove('drag-over','dragging'));
 $('#groupingBoard')?.classList.remove('is-dragging');
}
function scrollGroupingDrag(time){
 if(!groupingDrag.id||!$('#dialog').open||!$('#groupingBoard')){stopGroupingDrag();return;}
 const elapsed=groupingDrag.lastTime?Math.min(32,time-groupingDrag.lastTime):16;groupingDrag.lastTime=time;
 const {x,y}=groupingDrag;
 for(const stack of document.querySelectorAll('.group-stack')){
  const r=stack.getBoundingClientRect(),edge=Math.min(64,r.height/4);
  if(x<r.left||x>r.right||y<r.top-30||y>r.bottom+30)continue;
  const speed=y<r.top+edge?-Math.min(1,(r.top+edge-y)/edge):y>r.bottom-edge?Math.min(1,(y-r.bottom+edge)/edge):0;
  if(speed)stack.scrollTop+=speed*elapsed*.85;
 }
 // The pointer can remain stationary while the list moves underneath it.
 const target=document.elementFromPoint(x,y)?.closest('[data-group-target]');
 document.querySelectorAll('.drag-over').forEach(el=>{if(el!==target)el.classList.remove('drag-over');});
 if(target)target.classList.add('drag-over');
 groupingDrag.frame=requestAnimationFrame(scrollGroupingDrag);
}
document.addEventListener('dragstart',e=>{
 const tile=e.target.closest('[data-group-item]');if(!tile||!state.grouping)return;
 if(e.target.closest('input,button,summary,details')){e.preventDefault();return;}
 groupingDrag.id=tile.dataset.groupItem;groupingDrag.x=e.clientX;groupingDrag.y=e.clientY;
 e.dataTransfer.setData('text/plain',groupingDrag.id);e.dataTransfer.effectAllowed='move';tile.classList.add('dragging');$('#groupingBoard').classList.add('is-dragging');
 groupingDrag.frame=requestAnimationFrame(scrollGroupingDrag);
});
document.addEventListener('dragover',e=>{
 if(!groupingDrag.id)return;groupingDrag.x=e.clientX;groupingDrag.y=e.clientY;
 if(e.target.closest('#groupingBoard')){e.preventDefault();e.dataTransfer.dropEffect='move';}
});
document.addEventListener('drop',e=>{
 if(!groupingDrag.id)return;const id=groupingDrag.id,target=e.target.closest('[data-group-target]');
 e.preventDefault();stopGroupingDrag();if(target&&state.grouping)moveGroupedItem(id,target.dataset.groupTarget);
});
document.addEventListener('dragend',stopGroupingDrag);
document.getElementById('dialog').addEventListener('close',stopGroupingDrag);
document.addEventListener('change',e=>{if(!e.target.matches('[data-group-field]')||!state.grouping)return;rememberGroups();state.grouping.groups.find(x=>x.id===e.target.dataset.group)[e.target.dataset.groupField]=e.target.value;const b=$('[data-action="group-save"]');if(b)b.disabled=false;});
document.addEventListener('keydown',e=>{if(!e.target.matches('[data-group-item]')||!['Enter',' '].includes(e.key))return;e.preventDefault();state.grouping.selected=e.target.dataset.groupItem;renderGrouping();});
