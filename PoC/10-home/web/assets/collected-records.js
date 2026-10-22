'use strict';
const CollectedRecords=(()=>{
 const apiUrl=url=>{try{const u=new URL(url);return u.hostname==='apis.data.go.kr'||(u.hostname==='data.go.kr'||u.hostname.endsWith('.data.go.kr'))&&/openapi/i.test(u.pathname);}catch{return false;}};
 function link(url,id,revision,project){
  if(!apiUrl(url))return '<a href="'+esc(safeUrl(url))+'" target="_blank" rel="noopener noreferrer">출처 원문 ↗</a>';
  return '<button type="button" class="button secondary" data-collected-record="'+esc(id||'')+'" data-record-revision="'+esc(revision||'')+'" data-record-project="'+esc(project||'')+'" data-record-url="'+esc(url)+'">실제 수집 필드·값 보기</button> <a href="'+esc(safeUrl(url))+'" target="_blank" rel="noopener noreferrer">API 안내 ↗</a>';
 }
 function fields(value,prefix=''){
  if(value&&typeof value==='object'&&!Array.isArray(value))return Object.entries(value).flatMap(([k,v])=>fields(v,prefix?prefix+'.'+k:k));
  return [[prefix,value===null?'null':typeof value==='object'?JSON.stringify(value,null,2):String(value)]];
 }
 function render(r){return '<article><h4>'+esc(r.source_name)+' · '+esc(r.id)+'</h4><p>판본 '+r.revision_no+' · 원천 기준일 '+esc(r.base_date||'미기록')+' · 원천 자료일 '+esc(r.source_date||'미기록')+'<br>이 판본 저장시각 '+esc(r.recorded_at)+'</p><table><thead><tr><th>수집 필드</th><th>저장된 값</th></tr></thead><tbody>'+fields(r.data).map(([k,v])=>'<tr><th>'+esc(k)+'</th><td><pre>'+esc(v)+'</pre></td></tr>').join('')+'</tbody></table></article>';}
 document.addEventListener('click',async event=>{
  const b=event.target.closest('[data-collected-record]');if(!b)return;
  const dialog=document.createElement('dialog');dialog.className='collected-record-dialog';dialog.innerHTML='<header><h3>실제 수집 필드·값</h3><button type="button" class="button secondary">닫기</button></header><div role="status">연결된 원천 레코드를 불러오는 중…</div>';document.body.append(dialog);dialog.querySelector('button').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{dialog.remove();if(b.isConnected)b.focus();},{once:true});dialog.showModal();const body=dialog.querySelector('[role=status]');
  try{let items=[];if(b.dataset.recordProject){const r=await request('/projects/'+encodeURIComponent(b.dataset.recordProject)+'/collected-records?source_url='+encodeURIComponent(b.dataset.recordUrl));items=r.items;}else if(b.dataset.collectedRecord){items=[await request('/collected-records/'+encodeURIComponent(b.dataset.collectedRecord)+(b.dataset.recordRevision?'?revision_no='+encodeURIComponent(b.dataset.recordRevision):''))];}
   if(!dialog.isConnected)return;body.innerHTML=items.length?'<p>해당 근거를 수집·정형화하여 저장한 필드와 값입니다. 원천 값은 화면의 관리·추정값과 다를 수 있습니다.</p>'+items.map(render).join(''):'<p>이 근거에 연결된 개별 원천 레코드가 확인되지 않습니다. API 전체 샘플을 해당 값의 증빙으로 대신 표시하지 않습니다.</p>';
  }catch(e){body.textContent='원천 조회 실패: '+e.message;}
 });
 return {link,apiUrl};
})();
