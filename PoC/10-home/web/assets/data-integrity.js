'use strict';
window.DataIntegrity=(()=>{
 const api='/poc/home/api',root=()=>document.getElementById('integrity-content');let generation=0,selected='procedures',started=false,loaded=false,pending=null;
 const n=v=>v==null?'산정 불가':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:2});
 const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 async function get(path){const r=await fetch(api+path,{credentials:'same-origin'});if(!r.ok)throw Error('평가 자료 조회 실패');return r.json();}
 const table=(items,official)=>'<div class="di-table"><table><thead><tr><th>평가 항목</th><th>점수 / 배점</th><th>판정 근거</th></tr></thead><tbody>'+items.map(i=>'<tr><td><small>'+e(i.id)+'</small><strong>'+e(i.name)+'</strong>'+(official?'<small>'+e(i.evaluation_summary||('확인 '+n(i.numerator)+' / 대상 '+n(i.denominator)))+'</small>':'<small>'+e(i.assessment_mode)+'</small>')+'</td><td>'+n(i.score)+' / '+n(i.weight)+'</td><td>'+e(i.reason)+(i.evidence?'<small>증빙: '+e(i.evidence)+'</small>':'')+'</td></tr>').join('')+'</tbody></table></div>';
 async function loadAssessment(){const token=++generation;root().innerHTML='<p role="status">1차 채점 보고서를 불러오고 있습니다…</p>';try{const list=await get('/data-integrity'),item=list.items.find(i=>i.id.startsWith('HOME-INTEGRITY-FIRST-'));if(!item){root().innerHTML='<p>새 1차 채점 보고서를 준비하고 있습니다.</p>';return;}const d=await get('/data-integrity/rounds/'+item.id);if(token!==generation||!state.admin)return;loaded=true;const r=d.result,c=r.collection,m=r.classification_metrics,href=api+'/data-integrity/rounds/'+item.id;
  root().innerHTML='<div class="di-overview-grid"><section class="di-block"><h3>개요 · 수집실적</h3><div class="di-metrics">'+[['API 수집',c.api_sources+'개'],['공식 웹 수집',c.official_web_sources+'개'],['비공식 웹 수집',c.unofficial_web_sources+'개'],['등록 9·7 사업',n(r.project_count)+'건']].map(([l,v])=>'<article><span>'+l+'</span><strong>'+v+'</strong></article>').join('')+'</div><p>추출 데이터 '+n(c.extracted_cells)+'개 · 연결 데이터 '+n(c.linked_records)+'건 · 등록 경로 최근 성공 '+c.successful_sources+'/'+c.registered_sources+'개 · 오류 '+c.failed_sources+'개</p><small>추출량은 행 × 컬럼 수입니다. 수집 집계 시각 '+e(c.snapshot_at)+'</small></section><section class="di-block"><h3>4대 지표 · 고정 정답 표본 '+m.sample_size+'건</h3><div class="di-metrics">'+[['정확도','accuracy'],['정밀도','precision'],['재현율','recall'],['F1 스코어','f1']].map(([l,k])=>'<article><span>'+l+'</span><strong>'+n(m[k])+'%</strong></article>').join('')+'</div><p>'+e(r.classification_note)+'</p><small>TP '+m.tp+' · FP '+m.fp+' · FN '+m.fn+' · TN '+m.tn+' · 근거 평가 '+e(r.classification_evidence_as_of)+'</small></section></div><section class="di-hero"><div><span class="di-kicker">1차 채점 보고서</span><h3>공식자료 매핑 50% + 자체 항목 50%</h3><p>평가 '+e(r.assessed_at)+'</p></div><div class="di-score"><strong>'+n(r.total_score)+'</strong><span> / 100점</span></div></section><div class="di-metrics"><article><span>공식자료 매핑·대조</span><strong>'+n(r.official_score)+' / 50</strong></article><article><span>자체 항목</span><strong>'+n(r.self_score)+' / 50</strong></article></div><div class="di-actions"><a class="button primary" href="'+href+'/report.md">1차 채점 보고서 MD ↓</a><a class="button secondary" href="'+href+'/report.html" target="_blank" rel="noopener">보고서 보기·인쇄/PDF ↗</a><a class="button secondary" href="'+href+'" download="the주택_1차채점_근거.json">평가 근거 JSON ↓</a></div><section class="di-block"><h3>채점 기준</h3><p>'+e(r.scoring_note)+'</p><p>'+e(r.status_note)+'</p></section><section class="di-block"><h3>공식자료 매핑·대조 · '+r.official_items.length+'개 항목</h3>'+table(r.official_items,true)+'<p>공식 원문: '+r.official_verification.official_source_urls.map(u=>'<a href="'+e(u)+'" target="_blank" rel="noopener">공급계획 별첨 ↗</a>').join(' · ')+'</p></section><section class="di-block"><h3>자체 점검 · 40개 항목</h3>'+r.categories.map(c=>'<details open><summary>'+e(c.name)+' · '+n(c.score)+' / '+n(c.weight)+'점</summary>'+table(c.items,false)+'</details>').join('')+'</section><p class="di-muted">기존 회차는 운영 목록에서 제거하고 새 기준의 1차 보고서로 교체했습니다.</p>';
 }catch(error){if(token===generation)root().innerHTML='<p role="alert">'+e(error.message)+'</p>';}}
 function assessment(refresh=false){
  if(!state.admin)return Promise.resolve();
  if(pending)return pending;
  if(loaded&&!refresh)return Promise.resolve();
  pending=loadAssessment().finally(()=>{pending=null;});return pending;
 }
 function selectTab(key){
  if(!['procedures','reliability','history','assessment'].includes(key)||key==='assessment'&&!state.admin)return;
  selected=key;
  document.querySelectorAll('[data-integrity-tab]').forEach(b=>{const active=b.dataset.integrityTab===key;b.setAttribute('aria-selected',String(active));b.tabIndex=active?0:-1;document.getElementById(b.getAttribute('aria-controls')).hidden=!active;});
  if(key==='assessment'){assessment();return;}
  const frame=document.getElementById('integrity-doc-'+key);
  if(!frame.hasAttribute('src'))frame.src=frame.dataset.src;
 }
 function visible(){
  if(!started){
   started=true;
   const tabs=document.querySelector('#pane-data-integrity [role="tablist"]');
   tabs.addEventListener('click',event=>{const b=event.target.closest('[data-integrity-tab]');if(b&&!b.hidden)selectTab(b.dataset.integrityTab);});
   tabs.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;const buttons=[...tabs.querySelectorAll('[role="tab"]')].filter(b=>!b.hidden),current=buttons.indexOf(document.activeElement);if(current<0)return;event.preventDefault();const index=event.key==='Home'?0:event.key==='End'?buttons.length-1:(current+(event.key==='ArrowRight'?1:-1)+buttons.length)%buttons.length;buttons[index].focus();selectTab(buttons[index].dataset.integrityTab);});
   document.getElementById('integrity-refresh').onclick=()=>assessment(true);
  }
  document.getElementById('integrity-tab-assessment').hidden=!state.admin;
  if(!state.admin){if(selected==='assessment')selected='procedures';root().innerHTML='';loaded=false;++generation;}
  selectTab(selected);
 }
 return {visible};
})();
