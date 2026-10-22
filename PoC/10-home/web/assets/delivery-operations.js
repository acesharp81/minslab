'use strict';
const DeliveryOperations=(()=>{
  const policyCache=new Map();
  const causes={PERMIT:'인허가',COMPENSATION:'보상',INFRASTRUCTURE:'기반시설',FINANCE:'재원',COORDINATION:'기관 협의',OTHER:'기타'};
  const statuses={REVIEW:'확인 필요',CONFIRMED:'담당자 승인',RELEASED:'사용 해제',OPEN:'접수',IN_PROGRESS:'조치 중',RESOLVED:'해결'};
  const units=n=>n==null?'미확인':num(n)+'호';
  async function mountPolicy(ids,target){const host=target||document.querySelector('.pane:not([hidden]) #policy-execution-panel');if(!host)return;try{const key=$('as-of').value;if(!policyCache.has(key))policyCache.set(key,request('/execution?as_of_date='+key).catch(e=>{policyCache.delete(key);throw e;}));const d=await policyCache.get(key);if(!host.isConnected)return;const cases=d.cases.filter(c=>ids.includes(c.project_id));host.innerHTML='<h3>선택 범위의 병목·기관 조치</h3>'+(cases.length?'<div class="ops-scroll"><table><thead><tr><th>사업·원인</th><th>담당기관·다음 조치</th><th>기한·상태</th></tr></thead><tbody>'+cases.map(c=>`<tr><td>${esc(c.name)}<small>${esc(causes[c.cause])} · ${units(c.units)}</small></td><td>${esc(c.responsible_org)}<small>${esc(c.action)}</small></td><td>${esc(c.due_date)}<small>${esc(statuses[c.status])}${c.overdue?' · 기한 초과':''}</small></td></tr>`).join('')+'</tbody></table></div>':'<p>등록된 병목·조치가 없습니다.</p>');}catch(e){host.textContent=e.message;}}
  return {mountPolicy};
})();
