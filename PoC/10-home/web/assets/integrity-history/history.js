'use strict';
(()=>{
 const flow=document.getElementById('flow'),detail=document.getElementById('detail');
 const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const types={dataset:'데이터셋',feedback:'조원 피드백',review:'내부 재검증',rules:'패턴 규칙',data:'데이터 보강'};
 let data,selected='1-dataset';
 const list=values=>'<ul>'+values.map(v=>'<li>'+escape(v)+'</li>').join('')+'</ul>';
 function node(r,type,title,sub){const id=r.version+'-'+type;return '<button type="button" class="node '+type+'" data-node="'+id+'" aria-controls="detail" aria-pressed="'+(id===selected)+'"><small>'+escape(types[type]+(type==='dataset'?' V'+r.version:type==='feedback'?' '+r.version:''))+'</small><strong>'+escape(title)+'</strong>'+(sub?'<span>'+escape(sub)+'</span>':'')+'</button>';}
 function render(){flow.innerHTML=data.rounds.map(r=>'<div class="flow-row">'+node(r,'dataset',r.name,r.version===1?r.date:r.scope)+'<span class="arrow" aria-hidden="true">→</span>'+node(r,'feedback',r.feedback,'의견·발견 사항')+'<span class="arrow" aria-hidden="true">→</span>'+node(r,'review','원문·기존 이력 대조','판정과 반영 여부 확인')+'<span class="arrow" aria-hidden="true">→</span><div class="improvements">'+node(r,'rules','판정·연결 기준 개선')+node(r,'data',r.result)+'</div></div>').join('')+'<div class="flow-row final">'+node(data.final,'dataset',data.final.name,'주요 검토 결과 반영')+'<span class="arrow" aria-hidden="true">✓</span><p class="final-note">'+escape(data.final.result)+'<br>남은 확인 항목은 보류 상태로 관리합니다.</p></div>';select(selected,false);}
 function select(id,scroll){
  selected=id;flow.querySelectorAll('[data-node]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.node===id)));
  const [version,type]=id.split('-'),r=data.rounds.find(r=>r.version===Number(version));
  if(!r){detail.innerHTML='<p class="origin">데이터셋 V6</p><h2 id="detail-title">근거·규칙 보강본</h2><p>주요 검토를 거쳐 사업 식별·물량·정책 관계의 근거를 보강했습니다.</p><div class="detail-block"><h3>반복 검토에서 달라진 점</h3>'+list(data.rounds.map(r=>r.result))+'</div><p class="limit">이 도식은 대표 검토 이력의 재구성입니다. 모든 미연결 후보와 상충 자료의 검증이 완료됐다는 뜻은 아닙니다. 각 회차의 노드에서 반영·보류·후속 정정을 확인하세요.</p>';}
  else {
   const sections={dataset:['이 버전의 검토 범위','<p>'+escape(r.scope)+'</p><p>'+escape(r.finding)+'</p>'],feedback:['피드백에서 발견한 문제','<p>'+escape(r.finding)+'</p>'],review:['내부에서 다시 확인한 내용','<p>'+escape(r.review)+'</p>'],rules:['개선한 패턴·판정 규칙',list(r.rules)],data:['보강·수정한 데이터',list(r.enrichment)]};
   const focus=sections[type]||sections.dataset;
   detail.innerHTML='<div class="detail-top"><p>검토 '+r.version+' / '+data.rounds.length+' · '+escape(types[type])+'</p><div><button type="button" data-prev '+(r.version===1?'disabled':'')+' aria-label="이전 검토">←</button> <button type="button" data-next '+(r.version===data.rounds.length?'disabled':'')+' aria-label="다음 검토">→</button></div></div><h2 id="detail-title">'+escape(type==='dataset'?'데이터셋 V'+r.version+' · '+r.name:type==='feedback'?'조원 피드백 '+r.version:r.result)+'</h2><span class="status">'+escape(r.status)+'</span><p class="origin">검토 자료: '+escape(r.origin)+'</p><section class="detail-block"><h3>'+escape(focus[0])+'</h3>'+focus[1]+'</section>'+(type==='review'?'':'<section class="detail-block"><h3>내부 재검증</h3><p>'+escape(r.review)+'</p></section>')+'<section class="detail-block"><h3>발견 사항 → 수정·보완 결과</h3>'+r.cases.map(c=>'<article class="case"><div class="case-title"><strong>'+escape(c[0])+'</strong><span>'+escape(c[3])+'</span></div><dl><dt>이전</dt><dd>'+escape(c[1])+'</dd><dt>반영</dt><dd>'+escape(c[2])+'</dd></dl></article>').join('')+'</section>'+(type==='rules'?'':'<section class="detail-block"><h3>패턴 규칙에 반영</h3>'+list(r.rules)+'</section>')+'<p class="limit">'+escape(r.limit)+'</p><section class="detail-block"><h3>분석 결과 근거</h3><p>보관된 분석 문서·검증 결과에서 발췌했습니다.</p>'+r.evidence.map(e=>'<details><summary>'+escape(e.title)+'</summary><pre>'+escape(e.excerpt)+'</pre><p class="hash">'+(e.line?'원문 '+e.line+'행 · ':'')+'파일 SHA-256 '+escape(e.sha256)+'</p></details>').join('')+'</section>';
   detail.querySelector('[data-prev]').onclick=()=>select((r.version-1)+'-'+type,false);
   detail.querySelector('[data-next]').onclick=()=>select((r.version+1)+'-'+type,false);
  }
  if(scroll&&window.matchMedia('(max-width:1100px)').matches){detail.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});detail.focus({preventScroll:true});}
  else detail.scrollTop=0;
 }
 flow.addEventListener('click',event=>{const b=event.target.closest('[data-node]');if(b)select(b.dataset.node,true);});
 async function load(){try{const response=await fetch('rounds.json?v=1');if(!response.ok)throw Error();data=await response.json();render();}catch(error){flow.innerHTML='<p class="error" role="alert">검토 이력을 불러오지 못했습니다.</p><button class="retry" type="button">다시 불러오기</button>';flow.querySelector('button').onclick=load;}}
 load();
})();
