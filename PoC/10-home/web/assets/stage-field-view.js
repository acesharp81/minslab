'use strict';
const StageFieldView=(()=>{
 const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const val=(v,present=true)=>!present?'항목 없음':v===null||v===undefined?'미확보':typeof v==='object'?JSON.stringify(v,null,2):String(v);
 const time=v=>{if(!v)return '미기록';const d=new Date(v);return Number.isNaN(d.valueOf())?v:d.toLocaleString('ko-KR',{timeZone:'Asia/Seoul',hour12:false})+' (KST)';};
 function history(rows,note=''){
  if(!rows?.length)return '<small class="sf-muted">'+e(note||'변경 기록 없음')+'</small>';
  return '<details class="sf-history"><summary>항목 이력 '+rows.length+'건</summary>'+(note?'<p>'+e(note)+'</p>':'')+rows.map(h=>'<article><header><strong>'+e(h.action)+'</strong><span>'+e(time(h.changed_at))+'</span></header><dl><dt>이전 값</dt><dd><pre>'+e(val(h.before,h.before_present))+'</pre></dd><dt>변경 값</dt><dd><pre>'+e(val(h.after,h.after_present))+'</pre></dd><dt>담당자</dt><dd>'+e(h.actor)+'</dd><dt>사유</dt><dd>'+e(h.reason)+'</dd><dt>시각 기준</dt><dd>'+e(h.time_kind)+' · 판본 '+e(h.revision_no)+'</dd></dl></article>').join('')+'</details>';
 }
 function render(data){
  const table=(rows,heading='현재 값')=>'<div class="sf-table-wrap"><table class="sf-table"><thead><tr><th>항목</th><th>'+e(heading)+'</th><th>항목별 변경 이력</th></tr></thead><tbody>'+rows.map(r=>'<tr><th>'+e(r.label||r.field)+(r.tag?'<br>'+ProjectCollection.compactBadge(r.tag):'')+'</th><td><pre>'+e(val(r.value,r.present!==false))+'</pre></td><td>'+history(r.history,r.history_note)+(r.history?.length&&r.matches_management_record===false?'<small class="sf-muted">현재 채택값과 관리 입력 기록의 마지막 값은 다를 수 있습니다. 아래 원천을 함께 확인하세요.</small>':'')+'</td></tr>').join('')+'</tbody></table></div>';
  return '<p>'+e(data.notice)+'</p><h4>전체 항목 · 현재 채택값</h4>'+table(data.current)+(data.remaining.length?'<details><summary>남은 항목 '+data.remaining.length+'개</summary>'+data.remaining.map(r=>'<p>'+e(r.milestone+' · '+r.field+' · '+r.label)+'</p>').join('')+'</details>':'')+'<h4>원천별 전체 항목값</h4>'+data.sources.map(s=>'<section class="sf-source"><h5>'+e(s.name)+'</h5><small>'+e(s.id)+' · 연결 판본 '+e(s.revision_no)+'</small>'+(s.evidence_url?'<p>'+CollectedRecords.link(s.evidence_url,s.id,s.revision_no)+'</p>':'')+(s.missing?'<p>연결된 원천 판본 미확보</p>':table(s.fields,'연결 판본 값'))+'</section>').join('');
 }
 async function load(host,project,stage){
  if(!project)return;host.innerHTML='<p role="status">항목별 현재 값과 변경 기록을 불러오는 중…</p>';
  try{const data=await request('/projects/'+encodeURIComponent(project)+'/stage-fields/'+encodeURIComponent(stage));if(host.isConnected)host.innerHTML=render(data);}
  catch(error){if(host.isConnected){host.innerHTML='<p role="alert">항목 조회 실패: '+e(error.message)+'</p><button type="button" class="button secondary">다시 조회</button>';host.querySelector('button').onclick=()=>load(host,project,stage);}}
 }
 return {load,render};
})();
