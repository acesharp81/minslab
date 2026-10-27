'use strict';
(()=>{
 const flow=document.getElementById('flow'),detail=document.getElementById('detail'),outcome=document.getElementById('outcome');
 const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const types={dataset:'데이터셋',feedback:'조원 피드백',review:'내부 재검증',rules:'패턴 규칙',data:'데이터 보강'};
 const shorts=['연결 구조·수집 공백 정리','8개 블록 계획 연결','95호 연결·사업 식별 정정','기존 승인 복원·추정값 정정','공식 근거·관계 보강'];
 const check='<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m5 12 4 4L19 6" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>';
 let data,selected='1-feedback';
 const list=values=>'<ul class="check-list">'+values.map(v=>'<li>'+escape(v)+'</li>').join('')+'</ul>';
 const attrs=(id,label)=>' type="button" data-node="'+id+'" aria-controls="detail" aria-label="'+escape(label)+'" aria-pressed="'+(id===selected)+'"';
 function render(){
  const versions=[...data.rounds,data.final];
  flow.innerHTML='<div class="timeline-line" aria-hidden="true"></div><div class="version-grid">'+versions.map(r=>'<div class="version-column" data-version="'+r.version+'"><div class="version-heading"><strong>'+escape(r.name)+'</strong><span>'+(r.version===1?escape(r.date):r.version===6?'주요 검토 결과 반영':escape(r.scope))+'</span></div><button class="version-node dataset '+(r.version===6?'final-node':'')+'"'+attrs(r.version+'-dataset','데이터셋 V'+r.version+' '+r.name)+'>'+(r.version===6?check+'<span>V6</span>':'<span>V'+r.version+'</span>')+'</button></div>').join('')+'</div><div class="transition-grid">'+data.rounds.map(r=>'<div class="transition" data-round="'+r.version+'"><div class="step-dots" role="group" aria-label="검토 '+r.version+' 세부 단계">'+['feedback','review','rules','data'].map(t=>'<button class="step-dot '+t+'"'+attrs(r.version+'-'+t,'검토 '+r.version+' · '+types[t])+' title="'+escape(types[t])+'"><span aria-hidden="true"></span></button>').join('')+'</div><button class="feedback-card feedback"'+attrs(r.version+'-feedback','조원 피드백 '+r.version+' · '+r.feedback)+'><span class="feedback-number">피드백 '+String(r.version).padStart(2,'0')+'</span><strong>'+escape(r.feedback)+'</strong><span class="card-result">'+check+escape(shorts[r.version-1])+'</span><span class="card-action">수정 내용 보기 <span aria-hidden="true">↗</span></span></button></div>').join('')+'</div>';
  outcome.innerHTML='<button class="outcome"'+attrs('6-dataset','V6 결과 자세히 보기')+'><span class="outcome-icon">'+check+'</span><strong>V6 · 검토 반영 결과</strong><span class="outcome-tags"><span>기존 승인 보존</span><span>중복 방지</span><span>근거 추적</span></span><span class="outcome-note">남은 확인 항목은 보류 상태로 관리합니다.</span><span class="outcome-action">자세히 <span aria-hidden="true">→</span></span></button>';
  select(selected,false);
 }
 function caseCards(r){return r.cases.map((c,i)=>'<article class="case"><div class="case-title"><span class="case-index">'+String(i+1).padStart(2,'0')+'</span><h4>'+escape(c[0])+'</h4><span class="case-badge">'+escape(c[3])+'</span></div><div class="case-before"><span>발견 · 이전</span><p>'+escape(c[1])+'</p></div><div class="case-after"><span>'+check+' 수정 · 반영</span><p>'+escape(c[2])+'</p></div></article>').join('');}
 function select(id,scroll=false){
  const [version,type]=id.split('-'),r=data.rounds.find(r=>r.version===Number(version));
  if(!types[type]||(!r&&id!=='6-dataset'))return;
  selected=id;
  document.querySelectorAll('[data-node]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.node===id)));
  flow.querySelectorAll('[data-round]').forEach(el=>el.classList.toggle('is-active',el.dataset.round===version));
  flow.querySelectorAll('[data-version]').forEach(el=>el.classList.toggle('is-active',el.dataset.version===version));
  const back='<button class="back-to-flow" type="button" data-back>흐름으로 돌아가기 <span aria-hidden="true">↑</span></button>';
  if(!r){
   detail.innerHTML='<div class="detail-heading"><div><p class="eyebrow">REVIEW OUTCOME · V6</p><h2 id="detail-title">검토를 거쳐 달라진 것들</h2><p>사업 식별과 물량, 정책 관계의 근거를 보강했습니다.</p></div>'+back+'</div><div class="final-results">'+data.rounds.map(r=>'<button type="button" class="result-card" data-jump="'+r.version+'-data"><span>검토 '+String(r.version).padStart(2,'0')+'</span><strong>'+escape(r.result)+'</strong><small>'+escape(r.status)+' <span aria-hidden="true">↗</span></small></button>').join('')+'</div><p class="limit">모든 미연결 후보와 상충 자료의 검증이 완료됐다는 뜻은 아닙니다. 각 회차에서 반영·보류·후속 정정 내용을 확인할 수 있습니다.</p>';
  }else{
   const focuses={dataset:[r.name,r.finding],feedback:[r.feedback,r.finding],review:['원문과 기존 이력을 다시 대조했습니다',r.review],rules:['같은 오류가 반복되지 않도록',r.rules.join(' · ')],data:[r.result,r.enrichment.join(' · ')]};
   const focus=focuses[type];
   detail.innerHTML='<div class="detail-heading"><div><p class="eyebrow">REVIEW '+String(r.version).padStart(2,'0')+' <span class="detail-status">'+escape(r.status)+'</span></p><h2 id="detail-title">'+escape(focus[0])+'</h2><p>데이터셋 V'+r.version+' → V'+(r.version+1)+' · '+escape(r.scope)+'</p></div><div class="detail-controls">'+back+'<div class="round-nav"><button type="button" data-prev '+(r.version===1?'disabled':'')+' aria-label="이전 검토">←</button><span>'+String(r.version).padStart(2,'0')+' / 05</span><button type="button" data-next '+(r.version===data.rounds.length?'disabled':'')+' aria-label="다음 검토">→</button></div></div></div><div class="detail-tabs" role="group" aria-label="선택 회차의 검토 단계">'+Object.entries(types).map(([t,label])=>'<button class="'+t+'"'+attrs(r.version+'-'+t,label)+'><span aria-hidden="true"></span>'+label+'</button>').join('')+'</div><div class="focus-note '+type+'"><span>'+escape(types[type])+'</span><p>'+escape(focus[1])+'</p></div><div class="analysis-grid"><section class="analysis-card"><p class="section-label feedback">01 · 피드백</p><h3>어떤 문제가 발견됐나요?</h3><p>'+escape(r.finding)+'</p><div class="origin"><span>검토 자료</span>'+escape(r.origin)+'</div></section><section class="analysis-card"><p class="section-label review">02 · 내부 재검증</p><h3>무엇을 다시 확인했나요?</h3><p>'+escape(r.review)+'</p></section></div><section class="changes"><div class="section-heading"><div><p class="section-label">BEFORE & AFTER</p><h3>발견 사항에서, 실제 수정까지</h3></div><span>'+r.cases.length+'개 확인 항목</span></div><div class="case-grid">'+caseCards(r)+'</div></section><div class="analysis-grid improvements"><section class="analysis-card rules"><p class="section-label">03 · 패턴 규칙</p><h3>다음 검토에 적용할 기준</h3>'+list(r.rules)+'</section><section class="analysis-card data"><p class="section-label">04 · 데이터 보강</p><h3>데이터셋에 반영한 변화</h3>'+list(r.enrichment)+'</section></div><p class="limit"><strong>확인 범위</strong>'+escape(r.limit)+'</p><section class="evidence"><div class="section-heading"><div><p class="section-label">EVIDENCE</p><h3>분석 결과의 근거</h3></div><span>원문 발췌 '+r.evidence.length+'건</span></div>'+r.evidence.map((e,i)=>'<details><summary><span class="evidence-index">'+String(i+1).padStart(2,'0')+'</span>'+escape(e.title)+'<span class="evidence-toggle" aria-hidden="true">＋</span></summary><div class="evidence-body"><pre>'+escape(e.excerpt)+'</pre><p class="hash">'+(e.line?'원문 '+e.line+'행 · ':'')+'SHA-256 '+escape(e.sha256)+'</p></div></details>').join('')+'</section>';
   detail.querySelector('[data-prev]').onclick=()=>select((r.version-1)+'-'+type,'detail');
   detail.querySelector('[data-next]').onclick=()=>select((r.version+1)+'-'+type,'detail');
  }
  document.getElementById('selection-status').textContent=r?'검토 '+version+' · '+types[type]+' 상세를 표시했습니다.':'V6 검토 반영 결과를 표시했습니다.';
  detail.querySelector('[data-back]').onclick=()=>{document.querySelector('.overview').scrollIntoView({behavior:motion(),block:'start'});flow.querySelector('[data-node="'+selected+'"]')?.focus({preventScroll:true});};
  if(scroll){detail.scrollIntoView({behavior:motion(),block:'start'});detail.focus({preventScroll:true});}
 }
 const motion=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth';
 document.addEventListener('click',event=>{
  const jump=event.target.closest('[data-jump]');if(jump){select(jump.dataset.jump,true);return;}
  const b=event.target.closest('[data-node]');if(!b)return;
  const inDetail=detail.contains(b);select(b.dataset.node,!inDetail);
  if(inDetail)detail.querySelector('[data-node="'+selected+'"]')?.focus({preventScroll:true});
 });
 async function load(){try{const response=await fetch('rounds.json?v=1');if(!response.ok)throw Error();data=await response.json();render();}catch(error){flow.innerHTML='<p class="error" role="alert">검토 이력을 불러오지 못했습니다.</p><button class="retry" type="button">다시 불러오기</button>';flow.querySelector('button').onclick=load;}}
 load();
})();
