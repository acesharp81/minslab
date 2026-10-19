'use strict';
const CollectionLineage=(()=>{
 const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const num=v=>Number(v||0).toLocaleString('ko-KR');
 const stages=[
  {id:'POLICY',name:'정책',inputs:['정책 발표·후속 계획','정책–프로그램–사업 배정 기록'],keys:['policy','program','project'],join:['발표 자료·사업 유형으로 정책·프로그램 배정','분류·매칭 후 내부 관리번호 부여'],outputs:['정책 목표·대상 사업·소속 프로그램','배정된 사업 ID로 사업화 자료 조회'],note:'저장된 정책·프로그램 배정에서 사업을 찾고, 해당 사업 ID로 이후 다섯 단계의 자료를 조회합니다.'},
  {id:'BUSINESS',name:'사업화',inputs:['사업 현황·공급계획·지구 지정 고시','사업명·지역·지구·블록을 대조'],keys:['project','block','municipality'],join:['사업명·지역·지구·블록 대조','원천 사업 등록 → 내부 사업번호 부여'],outputs:['사업 범위·계획 호수·사업화 일정','같은 사업 ID에 인허가 근거 연결'],note:'사업명·지역·지구·블록으로 대조한 원천을 사업 ID에 연결합니다. 사업명이나 호수가 같다는 이유만으로 다음 단계와 자동 결합하지 않습니다.'},
  {id:'APPROVAL',name:'인허가',inputs:['건축HUB 주택인허가·계획 승인','허가 PK · 법정동 코드 · 필지'],keys:['permit','legal_dong','pnu'],join:['사업명·주소·지역과 허가 자료 대조','채택한 허가 기록을 기준 사업에 연결'],outputs:['인허가일·허가 물량·해당 필지','같은 사업 ID로 건설 기록 대조'],note:'허가 원천의 관리번호(mgmHsrgstPk), 법정동 코드·지번 등으로 사업을 대조합니다. 저장된 원천 기록 ID가 허가 자료를 가리키며, 이후 단계는 공통 사업 ID로 이어집니다.'},
  {id:'CONSTRUCTION',name:'건설',inputs:['기관 건설현황·공정률·준공 근거','지구·블록·공사명과 사업을 대조'],keys:['block','project'],join:['지구·블록·공사명·물량 범위 대조','착공·공정·준공 자료를 사업에 연결'],outputs:['착공일·공정률·준공일','같은 사업 ID로 공급공고 연결'],note:'지구·블록·공사명 등을 대조한 건설 자료를 사업 ID에 연결합니다. 착공·공정률·준공은 건설 단계의 관측 정보이며 다음 단계의 연결 키로 쓰는 날짜가 아닙니다.'},
  {id:'SUPPLY',name:'공급',inputs:['청약홈·LH·GH 입주자 모집공고','주택관리번호 · 공고 기록 · 블록'],keys:['notice','block','project'],join:['지역·지구·블록·분양·임대 유형 대조','선택한 모집공고를 사업에 연결'],outputs:['모집공고일·공급 호수·주택형','공고의 입주 예정정보도 사업에 연결'],note:'주택관리번호(HOUSE_MANAGE_NO) 등 공고 식별자와 지구·블록으로 사업을 대조합니다. 공고는 저장된 원천 기록 ID로 참조하며, 같은 공고가 공급과 입주예정의 근거로 함께 연결될 수 있습니다.'},
  {id:'MOVE_IN',name:'입주',inputs:['모집공고 입주예정·기관 입주계획','입주 시작 확인·담당자 기록'],keys:['notice','block','project'],join:['연결 공고·입주계획·사업 지정 정보','입주 예정·실제 시작 근거를 연결'],outputs:['입주 예정월·실제 입주 시작일','사업·프로그램·정책별 추진현황 집계'],note:'사업 ID와 저장된 입주 계획·실적 근거를 연결합니다. 입주 예정월과 실제 시작일은 따로 관리하며, 준공일을 입주 실적으로 바꾸지 않습니다.'}
 ];
 const keyNames={policy:'정책 ID',program:'프로그램 ID',project:'사업 ID',block:'지구·블록',municipality:'시군구',permit:'허가 관리번호',legal_dong:'법정동 코드',pnu:'필지번호(PNU)',notice:'주택관리번호'};
 const valueNames={start:'착공일',progress:'공정률',completion:'준공일',supply:'모집공고일',move_plan:'입주 예정월',move_actual:'입주 시작일',target:'계획 호수',due:'목표·예정일',actual:'관측일'};
 const links=(p,s)=>p.lineage?.stage_links?.[s]||[];
 const connected=(p,s)=>s==='POLICY'?Boolean(p.lineage?.keys?.policy):links(p,s).length>0;
 const pairRows=(rows,a,b)=>rows.filter(p=>connected(p,a)&&connected(p,b));
 const matchFields={name:'사업·공고명',region:'시도',municipality:'시군구',district:'지구명',block:'블록',address:'주소',program:'사업 유형',source_object_id:'기관 원본 번호',house_manage_no:'주택관리번호',sigungu_code:'시군구 코드',bjdong_code:'법정동 코드',pnu:'필지 PNU',bun:'지번 본번',ji:'지번 부번',planned_units:'계획 호수',units:'원천 호수',tenure:'분양·임대 유형',developer:'시행기관'};
 const stageMethods={
  POLICY:['정책 발표문을 정책 목록에 등록하고 내부 정책번호를 부여합니다.','수집·분류한 사업 유형을 프로그램으로 묶고, 정책 범주와 프로그램의 연결을 제안하거나 담당자가 지정합니다.','사업–프로그램 배정 근거와 프로그램–정책 배정 근거를 각각 저장합니다.'],
  BUSINESS:['수집 출처와 출처별 사업 식별값으로 내부 사업번호를 생성합니다.','같은 사업을 설명하는 자료는 시도·지구·단일 블록, 상세 주소, 사업명·시군구 등의 규칙으로 대조합니다.','선택한 원천 기록과 매칭 사유를 사업화 단계에 저장합니다.'],
  APPROVAL:['사업과 인허가 자료의 시도·지구·블록 또는 상세 주소·사업명을 대조합니다.','명칭 공백·부가표기 등을 정리하고, 사업명 유사도나 전체·부분 승인 물량 관계도 규칙에 따라 확인합니다.','허가 관리번호는 해당 허가 원천을 찾는 번호이며, 채택한 연결 근거를 내부 사업번호에 저장합니다.'],
  CONSTRUCTION:['동일 수집 사업의 착공·공정률·준공 정보는 그 사업에 연결합니다.','별도 원천은 시도·지구·블록과 총호수·주택유형의 전체 또는 부분 범위를 대조합니다.','저장한 연결 근거와 선택 원천 판본을 사용해 건설 정보를 조회합니다.'],
  SUPPLY:['모집공고와 사업의 지역·지구·블록 표기, 시행기관, 분양·임대 유형 및 모집 물량을 규칙에 따라 대조합니다.','본 모집공고 연결 규칙은 재공고·추가 모집·복수 블록 등 중복 또는 범위가 다른 자료를 구분합니다.','선택 공고를 사업에 연결하고 공고일과 공급 호수를 해당 단계 정보로 사용합니다.'],
  MOVE_IN:['공급에 연결한 모집공고의 입주 예정정보 또는 기관별 입주계획을 같은 사업에 연결합니다.','담당자 입력은 대상 사업·단계를 지정해 저장하며 별도 명칭 매칭을 수행하지 않습니다.','입주 예정정보와 실제 입주 시작 근거를 구분해 연결합니다.']
 };
 const transitionLabels={POLICY:'정책 범주·사업 유형',BUSINESS:'사업명·지역·주소',APPROVAL:'사업 귀속·지구·블록',CONSTRUCTION:'지구·블록·공급 범위',SUPPLY:'공고·단지·입주 일정'};
 const fieldHtml=fields=>Object.entries(fields||{}).filter(([k])=>matchFields[k]).map(([k,v])=>'<span><b>'+escape(matchFields[k])+'</b> '+escape(v)+'</span>').join('')||'<span>저장된 대조 항목 없음</span>';
 const refsHtml=l=>'<details class="cl-match-refs"><summary>내부 연결번호·판본 보기</summary><span>내부 사업 ID: '+escape(l.project_id)+'</span><span>출처: '+escape(l.source_id)+'</span><span>원천 기록 ID: '+escape(l.source_entity_id||'사업·단계 직접 지정')+'</span><span>판본: '+escape(l.source_revision_no??'기준일 조회')+'</span></details>';
 function reasonHtml(l){const m=l.matching||{};return '<b>'+escape(m.label||'저장 연결')+'</b><p>'+escape(m.basis||l.basis||'저장된 상세 매칭 사유 없음')+'</p>'+(m.decision_basis?'<p>선택·확인 사유: '+escape(m.decision_basis)+'</p>':'')+(m.match_key?'<span>저장된 정규화 연결값: '+escape(m.match_key.join(' / '))+'</span>':'')+(m.score!=null?'<span>저장 당시 대조 점수: '+escape(m.score)+'</span>':'')+(m.version?'<small>연결 규칙 판본: '+escape(m.version)+'</small>':'');}
 const originalLink=(url,label='근거 원문 열기 ↗')=>/^https?:\/\//i.test(url||'')?'<a class="cl-evidence-link" href="'+escape(url)+'" target="_blank" rel="noopener noreferrer">'+escape(label)+'</a>':'<small>연결 기록에 원문 주소가 없습니다.</small>';
 function sourceProof(l){return '<section class="cl-proof"><h5>근거 자료</h5><b>'+escape(l.name||l.source_id)+'</b><p>'+escape(l.source_title||l.source_fields?.name||'자료 제목 미기록')+'</p>'+(l.source_date?'<small>자료 기준일 '+escape(l.source_date)+'</small>':'')+(l.date?'<small>연결한 사건·예정일 '+escape(l.date)+'</small>':'')+originalLink(l.source_url||l.evidence_url)+'</section>';}
 function confirmedFacts(l){
  const labels={...valueNames,permit:'허가 관리번호',notice:'주택관리번호',block:'지구·블록',legal_dong:'법정동 코드'},facts=Object.entries(l.source_facts||{}).filter(([k])=>labels[k]);
  const fields=Object.fromEntries(Object.entries(l.source_fields||{}).filter(([k])=>['region','municipality','district','block','address','tenure','units','planned_units','developer'].includes(k)));
  return '<section class="cl-proof"><h5>자료에서 확인한 내용</h5>'+(facts.length?facts.map(([k,v])=>'<span><b>'+escape(labels[k])+'</b> '+escape(v)+'</span>').join(''):fieldHtml(fields))+(l.matching?.match_key?'<p><b>저장된 대조 조합</b> '+escape(l.matching.match_key.join(' / '))+'</p>':'')+'</section>';
 }
 function evidenceCard(p,l,compact=false){const m=l.matching||{};
  const why=m.basis||l.basis||'저장된 상세 연결 사유가 없습니다.';
  const explanation={PREREQUISITE:'이 자료의 착공·진척 기록을 근거로 선행 단계에 도달한 것으로 연결했습니다.',STAGE_INFERENCE:'원천에 기재된 추진단계를 근거로 선행 단계에 연결했습니다.',DIRECT_INPUT:'대상 사업과 단계가 지정된 입력 기록을 사용했습니다.',SOURCE_RECORD:'같은 수집 사업 기록에 담긴 단계 정보를 사용했습니다.'}[m.method];
  return '<article class="cl-mapping-card"><header><h4>'+escape(compact?l.name||l.source_id:p.name)+'</h4><span>'+escape(m.label||'저장된 연결 근거')+'</span></header><section class="cl-why"><h5>왜 이 자료와 연결했나요?</h5>'+(explanation?'<p>'+escape(explanation)+'</p>':'')+'<p class="cl-saved-basis">'+escape(why)+'</p>'+(m.decision_basis?'<small>선택·확인 기록: '+escape(m.decision_basis)+'</small>':'')+'</section><div class="cl-proof-grid">'+sourceProof(l)+confirmedFacts(l)+'</div><details class="cl-match-extra"><summary>사업·원천의 전체 대조값과 내부 번호 보기</summary><div class="cl-proof-grid"><section><h5>기준 사업</h5>'+fieldHtml(p.lineage?.identity?.source_fields)+'</section><section><h5>연결한 수집 자료</h5>'+fieldHtml(l.source_fields)+'</section></div>'+refsHtml(l)+(m.score!=null?'<small>저장 당시 대조 점수 '+escape(m.score)+'</small>':'')+'</details></article>';
 }
 const orderedLinks=(p,s)=>[...links(p,s)].sort((a,b)=>Number(b.matching?.method!=='DIRECT_INPUT')-Number(a.matching?.method!=='DIRECT_INPUT')||Number(!!b.source_title)-Number(!!a.source_title));
 function classificationHtml(c){
  if(!c)return '';
  if(!c.checks)return '<section class="cl-assignment-row cl-classification"><h6>'+escape(c.label)+'</h6><p><b>'+escape(c.field)+': '+escape(c.value)+'</b></p><small>분류 기준: '+escape(c.criterion)+'</small><p>해당 항목: <b>'+escape(c.matched)+'</b> → 분류 결과: <b>'+escape(c.output)+'</b></p><small>'+(c.agrees?'수집기에 적용된 분류 기준과 저장된 사업 유형이 일치합니다.':'현재 수집 분류 기준의 결과와 저장된 사업 유형이 다릅니다. 저장된 배정 기록을 확인할 수 있습니다.')+'</small>'+(c.note?'<small>'+escape(c.note)+'</small>':'')+'</section>';
  const rows=c.extracted_rows||[];
  return '<section class="cl-assignment-row cl-classification cl-extraction"><h6>① 원문에서 추출한 항목과 값</h6><p>'+escape(c.source_name)+'</p><p>지구명/공급예정지역: <b>'+escape(c.source_title||'미기록')+'</b></p><p>유형: <b>'+escape(c.value||'미기록')+'</b></p>'+(rows.length?'<div class="cl-extracted-table" tabindex="0" aria-label="저장된 공급계획 추출 행"><table><thead><tr><th>유형</th><th>전용면적(㎡)</th><th>공급호수</th><th>공급예정시기</th></tr></thead><tbody>'+rows.map(r=>'<tr><td>'+escape(r.tenure??'미기록')+'</td><td>'+escape(r.area??'미기록')+'</td><td>'+escape(r.units??'미기록')+'</td><td>'+escape(r.supply_raw??'미기록')+'</td></tr>').join('')+'</tbody></table></div>':'<small>이 판본에 저장된 원문 행은 없습니다. 위의 저장 추출값을 표시합니다.</small>')+originalLink(c.source_url,'추출한 자료 원문 열기 ↗')+'<h6 class="cl-classification-step">② 추출값에 적용한 시스템 분류 조건</h6>'+c.checks.map(r=>'<div class="cl-classification-check"><b>'+escape(r.field)+': '+escape(r.value||'미기록')+'</b><small>'+escape(r.condition)+'</small><p>→ '+escape(r.result)+'</p></div>').join('')+'<p>'+escape(c.criterion)+'</p><p><b>분류 결과: '+escape(c.output||'수집 제외 대상')+'</b></p><small>'+escape(c.note)+'</small>'+(!c.agrees?'<small>분류 조건의 결과와 저장 분류값이 다릅니다. 아래 배정 기록을 함께 확인할 수 있습니다.</small>':'')+'</section>';
 }
 function assignmentHtml(value){
  if(!value)return '<p>저장된 항목 대조 정보를 불러오지 못했습니다.</p>';
  return '<div class="cl-assignment">'+classificationHtml(value.classification)+'<p class="cl-assignment-rule">'+escape(value.explanation)+'</p>'+(value.rows||[]).map(r=>'<section class="cl-assignment-row"><h6>'+escape(r.label)+' <em>'+escape(r.result)+'</em></h6><dl><div><dt>'+escape(r.left_label)+'</dt><dd>'+escape(r.left||'미기록')+'</dd></div><div><dt>'+escape(r.right_label)+'</dt><dd>'+escape(r.right||'미연결')+'</dd></div></dl></section>').join('')+(value.history?.length?'<div class="cl-assignment-history"><h6>저장된 배정·확인 과정</h6>'+value.history.map(h=>'<p><b>'+escape(h.label)+(h.rule?' · '+escape(({SOURCE_POLICY:'수집기에 설정된 정책 후보 적용',SOURCE_PROGRAMME:'사업 유형에 대응하는 프로그램 후보 적용',UNRESOLVED:'자동 후보 미결정'})[h.rule]||h.rule):'')+'</b><br>'+escape(h.basis)+'</p>').join('')+'</div>':'')+(value.note?'<small>'+escape(value.note)+'</small>':'')+'</div>';
 }
 function policyCard(p){const identity=p.lineage?.identity||{},m=identity.mapping||{},pm=identity.program_mapping||{},policy=links(p,'POLICY')[0]||{};
  return '<article class="cl-mapping-card"><header><h4>'+escape(p.name)+'</h4><span>프로그램·정책 배정</span></header><section class="cl-why"><h5>왜 이 프로그램·정책에 연결했나요?</h5><p>'+escape(p.name)+' → <b>'+escape(m.program_name||pm.name||p.program||'프로그램')+'</b> → <b>'+escape(p.policy_name||m.policy_id||'정책')+'</b></p></section><div class="cl-proof-grid"><section class="cl-proof"><h5>사업 → 프로그램 · 일치 항목과 배정 근거</h5>'+assignmentHtml(identity.assignment?.project)+'<h5>사업 배정의 근거 자료</h5><p>'+escape(identity.source_title||p.name)+'</p>'+(identity.source_date?'<small>자료 기준일 '+escape(identity.source_date)+'</small>':'')+originalLink(identity.source_url||m.evidence_url)+'<p><b>현재 사업 배정 기록</b><br>'+escape(m.basis||'저장된 사업 배정 사유가 없습니다.')+'</p></section><section class="cl-proof"><h5>프로그램 → 정책 · 대조 항목과 배정 근거</h5>'+assignmentHtml(identity.assignment?.policy)+'<h5>정책 배정의 근거 자료</h5><p>'+escape(p.policy_name||policy.source_title||'정책 발표 자료')+'</p>'+originalLink(pm.evidence_url||policy.source_url||policy.evidence_url)+'<p><b>현재 정책 배정 기록</b><br>'+escape(pm.basis||'저장된 프로그램–정책 배정 사유가 없습니다.')+'</p></section></div><details class="cl-match-extra"><summary>사업 분류값·내부 관리번호 보기</summary>'+fieldHtml(identity.source_fields)+'<p>정책 '+escape(m.policy_id||'미연결')+' / 프로그램 '+escape(m.program_id||'미연결')+' / 사업 '+escape(p.id)+'</p></details></article>';
 }
 function policyTable(rows){return rows.slice(0,20).map(policyCard).join('')+(rows.length>20?'<p>앞 20개 사업 표시 · 위에서 사업을 선택하면 해당 사업의 근거만 볼 수 있습니다.</p>':'');}
 function matchingTable(rows,s){const entries=rows.flatMap(p=>orderedLinks(p,s).map(l=>({p,l})));if(!entries.length)return '<p>저장된 연결 기록이 없습니다.</p>';return '<p>저장 연결 '+num(entries.length)+'건'+(entries.length>20?' 중 앞 20건 · 위에서 사업을 선택해 범위를 좁힐 수 있습니다.':'')+'</p>'+entries.slice(0,20).map(({p,l})=>evidenceCard(p,l)).join('')||'<p>저장된 연결 기록이 없습니다.</p>';}
 function stageExplanation(rows,s){return (s.id==='POLICY'?policyTable(rows):matchingTable(rows,s.id))+'<details class="cl-match-extra"><summary>이 단계의 일반적인 매칭 방식 보기</summary><p>정책·프로그램·사업 ID는 내부 관리번호이며, 자료를 대조하고 연결한 결과를 조회할 때 사용합니다.</p><ol>'+stageMethods[s.id].map(t=>'<li>'+escape(t)+'</li>').join('')+'</ol></details>';}
 function transitionTable(rows,s,next){if(!rows.length)return '<p>두 단계의 연결 기록을 함께 가진 사업이 없습니다.</p>';
  const evidence=(p,stage)=>{if(stage==='POLICY')return policyCard(p);const records=orderedLinks(p,stage);return records.slice(0,2).map(l=>evidenceCard(p,l,true)).join('')+(records.length>2?'<details class="cl-match-extra"><summary>추가 근거 자료 '+num(records.length-2)+'건 보기</summary>'+records.slice(2).map(l=>evidenceCard(p,l,true)).join('')+'</details>':'');};
  return '<p>두 단계에 각각 근거가 연결된 '+num(rows.length)+'개 사업'+(rows.length>10?' 중 앞 10개':'')+'입니다.</p>'+rows.slice(0,10).map(p=>{const left=new Set(links(p,s.id).map(l=>l.source_entity_id).filter(Boolean)),common=[...new Set(links(p,next.id).map(l=>l.source_entity_id).filter(id=>id&&left.has(id)))];return '<article class="cl-transition-card"><h4>'+escape(p.name)+'</h4><p class="cl-transition-reason"><b>두 단계가 이어지는 이유</b><br>'+(s.id==='POLICY'?'이 사업을 프로그램에 배정하고, 해당 프로그램을 상위 정책에 연결한 기록이 있습니다.':common.length?'같은 원천 기록이 양쪽 단계의 근거에 사용되었습니다. 아래에서 각 단계에 적용한 내용과 사유를 확인할 수 있습니다.':'양쪽 자료를 각각 같은 사업에 연결한 기록이 있습니다. 아래에 단계별로 사용한 자료와 연결 사유를 표시합니다.')+'</p><div class="cl-transition-grid"><section><h5>'+escape(s.name)+'의 근거 자료·연결 이유</h5>'+evidence(p,s.id)+'</section><section><h5>'+escape(next.name)+'의 근거 자료·연결 이유</h5>'+evidence(p,next.id)+'</section></div></article>';}).join('');}
 function table(rows,s){
  const entries=rows.flatMap(p=>links(p,s).map(l=>({p,l}))),shown=entries.slice(0,50);
  if(!entries.length)return '<p>선택 범위에 이 단계의 저장 연결 기록이 없습니다.</p>';
  const kv=(keys,names)=>Object.entries(keys||{}).filter(([k])=>names[k]).map(([k,v])=>'<span><b>'+escape(names[k])+'</b> '+escape(v)+'</span>').join('');
  return '<p>실제 저장 연결 '+num(entries.length)+'건'+(entries.length>50?' 중 앞 50건 · 사업을 선택하면 해당 사업만 조회':'')+'</p><div class="cl-link-table"><table><thead><tr><th>사업</th><th>원천 자료를 찾는 연결값</th><th>원천에 있는 대조 키</th><th>연결 후 활용하는 정보</th></tr></thead><tbody>'+shown.map(({p,l})=>'<tr><th>'+escape(p.name)+'<small>사업 ID: '+escape(l.project_id)+'</small></th><td><b>'+escape(l.name||l.source_id)+'</b><span>출처 ID: '+escape(l.source_id)+'</span>'+(l.source_object_id?'<span>기관 원본 번호: '+escape(l.source_object_id)+'</span>':'')+'<span>원천 기록 ID: '+escape(l.source_entity_id||'사업 ID·단계로 직접 저장')+'</span><span>원천 판본: '+escape(l.source_revision_no??'기준일에 조회한 판본')+'</span>'+(!l.source_record_available&&l.source_entity_id?'<span>참조 원문 필드 미조회</span>':'')+'</td><td>'+(kv(l.keys,keyNames)||'이 연결에 기록된 별도 대조 키 없음')+'</td><td>'+(kv(l.keys,valueNames)||escape(l.date||'일자 정보 없음'))+'<small>'+escape(l.basis||'')+'</small></td></tr>').join('')+'</tbody></table></div>';
 }
 function render({host,detailHost,data,rows,stage,projectName}){
  const info={},total=rows.length;let cards='',edges='';
  const text=(x,y,v,cls='',width)=>'<text x="'+x+'" y="'+y+'" class="'+cls+'"'+(width?' data-cl-width="'+width+'"':'')+'>'+escape(v)+'</text>';
  const node=(id,x,y,w,title,lines,cls)=>{cards+='<g data-cl-node="'+id+'" role="button" tabindex="0" aria-label="'+escape(title+' · 실제 연결값 보기')+'"><rect x="'+x+'" y="'+y+'" width="'+w+'" height="108" rx="8" class="'+cls+'"/>'+text(x+14,y+25,title,'cl-node-title',w-28)+lines.map((v,i)=>text(x+14,y+47+i*17,v,i===0?'cl-node-sub':'cl-node-muted',w-28)).join('')+'</g>';};
  const edge=(id,x1,y1,x2,y2,label,status)=>{edges+='<g data-cl-node="'+id+'" role="button" tabindex="0" aria-label="'+escape(label+' · 연결 방식 보기')+'"><path d="M'+x1+','+y1+' L'+x2+','+y2+'" class="cl-edge cl-'+status+'" marker-end="url(#cl-arrow-'+status+')"/><path d="M'+x1+','+y1+' L'+x2+','+y2+'" class="cl-edge-hit"/>'+text((x1+x2)/2,(y1+y2)/2-7,label,'cl-edge-label')+'</g>';};
  stages.forEach((s,i)=>{
   const y=100+i*163,n=rows.filter(p=>connected(p,s.id)).length,records=rows.flatMap(p=>links(p,s.id));
   const names=[...new Set(records.map(r=>r.name||data.lineage?.sources?.[r.source_id]?.name||r.source_id))];
   info['stage-'+s.id]={s,title:(i+1)+' '+s.name+' · 매칭 방법과 실제 저장 근거'};
   info['source-'+s.id]={s,title:s.name+' 단계에 들어오는 자료'};
   info['output-'+s.id]={s,title:s.name+' 단계에서 활용하는 정보'};
   info['input-'+s.id]=info['source-'+s.id];info['result-'+s.id]=info['output-'+s.id];
   node('source-'+s.id,20,y,340,s.inputs[0],[s.inputs[1],names.length?names.slice(0,2).join(' · '):'선택 범위에 저장 연결 없음','연결 원천 '+num(names.length)+'종 · 기록 '+num(records.length)+'건'],n?'cl-source':'cl-source-missing');
   cards+='<g data-cl-node="repair-'+s.id+'" data-cl-repair-count="true" role="button" tabindex="0" aria-label="'+escape(s.name+' 오류·조치 이력 보기')+'">'+text(245,y+98,'오류·조치 '+CollectionRepairs.relevant(data,rows,s.id).length+'건','cl-node-muted')+'</g>';
   if(s.id==='APPROVAL'){info['key-pnu']={s,title:'인허가 필지(PNU) 연결 근거',parcel:true};cards+='<g data-cl-node="key-pnu" role="button" tabindex="0" aria-label="필지 PNU 상세 보기">'+text(34,y+98,'필지(PNU) 상세 보기','cl-node-sub')+'</g>';}
   node('stage-'+s.id,480,y,320,(i+1)+' '+s.name,[...s.join,'단계 연결 '+num(n)+' / '+num(total)+'개 사업'],n?'cl-key':'cl-key-missing');
   node('output-'+s.id,920,y,320,'연결 후 확인하는 정보',[...s.outputs,'상자 선택 → 실제 키·수치 확인'],'cl-output');
   edge('input-'+s.id,360,y+54,480,y+54,'원천 연결',n?'connected':'missing');
   edge('result-'+s.id,800,y+54,920,y+54,'정보 조회',n?'connected':'missing');
   if(i<stages.length-1){const next=stages[i+1],paired=pairRows(rows,s.id,next.id);const id='transition-'+s.id;info[id]={s,next,paired,title:s.name+' → '+next.name+' · 단계 사이의 매칭 정보'};edge(id,640,y+108,640,y+163,transitionLabels[s.id]+' · '+num(paired.length)+'개',paired.length?'connected':'missing');}
  });
  const markers=['connected','missing'].map(s=>'<marker id="cl-arrow-'+s+'" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0L7 3.5L0 7" class="cl-arrow-'+s+'"/></marker>').join('');
  host.innerHTML='<svg class="cl-graph" viewBox="0 0 1260 1050" role="group" aria-label="'+escape((projectName||'조회 사업')+' 정책부터 입주까지 단계별 연결 키')+'"><defs>'+markers+'</defs>'+text(20,30,'단계별 입력 자료','cl-heading')+text(480,30,'원천 자료 대조 → 내부 사업 연결','cl-heading')+text(920,30,'연결한 자료의 활용','cl-heading')+text(20,61,'수집한 이름·지역·블록 등을 비교해 사업을 연결합니다.','cl-muted')+text(480,61,'네모: 매칭 방법 / 화살표: 단계 사이에 사용한 정보','cl-muted')+text(920,61,'일자·물량은 연결 후 확인하는 값입니다.','cl-muted')+edges+cards+'</svg>';
  const canvas=document.createElement('canvas').getContext('2d');
  const fit=[...host.querySelectorAll('text[data-cl-width]')].map(t=>{const style=getComputedStyle(t);return {t,full:t.textContent,max:Number(t.dataset.clWidth),width:t.getComputedTextLength(),font:`${style.fontWeight} ${style.fontSize} ${style.fontFamily}`};});
  for(const {t,full,max,width,font}of fit){if(width<=max||!canvas)continue;canvas.font=font;const scale=width/Math.max(1,canvas.measureText(full).width);let lo=0,hi=full.length;while(lo<hi){const mid=Math.ceil((lo+hi)/2);if(canvas.measureText(full.slice(0,mid)+'…').width*scale>max)hi=mid-1;else lo=mid;}t.textContent=full.slice(0,lo)+'…';const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=full;t.appendChild(title);}
  function activate(id,projectFilter=''){const item=info[id];if(!item)return;host.querySelectorAll('.cl-active').forEach(n=>n.classList.remove('cl-active'));host.querySelector('[data-cl-node="'+id+'"]')?.classList.add('cl-active');host.dataset.activeNode=id;
   const {s,next,paired,parcel}=item;
   const selectedRows=projectFilter?rows.filter(p=>p.id===projectFilter):rows,selectedPairs=projectFilter?(paired||[]).filter(p=>p.id===projectFilter):paired;
   let body=next?'<p>각 단계 원천을 기준 사업에 연결한 저장 근거를 확인합니다. 내부 사업번호는 이 연결의 결과입니다.</p>'+transitionTable(selectedPairs,s,next):stageExplanation(selectedRows,s);
   if(parcel)body+='<p>19자리 PNU는 법정동 코드·산 여부·본번·부번으로 구성하는 필지 식별자입니다.</p><div class="cl-parcel-list">'+rows.filter(p=>p.parcel_identity).map(p=>'<p>'+escape(p.name)+' · '+escape(p.parcel_identity.status==='CANDIDATE'?'PNU 후보':'필지 연결')+' · '+escape((p.parcel_identity.pnus||[]).join(' / ')||'필지 미확보')+' · '+escape(p.parcel_identity.basis||'')+'</p>').join('')+'</div>';
   if(parcel)body+=table(rows,s.id);
   const chooser=rows.length>1?'<label class="cl-project-choice">근거를 확인할 사업<select data-cl-project-choice><option value="">조회 범위 전체</option>'+rows.map(p=>'<option value="'+escape(p.id)+'"'+(p.id===projectFilter?' selected':'')+'>'+escape(p.name)+'</option>').join('')+'</select></label>':'';
   detailHost.innerHTML='<article class="cl-inspector" role="status"><strong>'+escape(item.title)+'</strong>'+chooser+body+'</article>'+CollectionRepairs.html(data,selectedRows,parcel?'ALL':s.id,null,parcel?['pnu']:id.startsWith('source-')?null:s.keys);
  }
  if(host.dataset.flowStage!==stage){delete host.dataset.activeNode;host.dataset.flowStage=stage;}
  const chosen=host.dataset.activeNode||(stage!=='ALL'?'stage-'+stage:null);
  if(chosen&&info[chosen])activate(chosen);else detailHost.innerHTML='<p class="cl-help">정책은 프로그램을 통해 사업에 배정되고, 사업화부터 입주까지의 원천 자료는 같은 사업 ID에 단계별로 연결됩니다. 상자를 선택하면 매칭 방법과 저장 근거를, 화살표를 선택하면 두 단계의 대조 정보를 팝업으로 볼 수 있습니다. 세로 흐름은 자료 조회 순서이며 실제 공사·분양 일정은 병행될 수 있습니다.</p>'+CollectionRepairs.html(data,rows,stage);
  detailHost.onchange=event=>{if(event.target.matches('[data-cl-project-choice]')){activate(host.dataset.activeNode,event.target.value);detailHost.querySelector('[data-cl-project-choice]')?.focus({preventScroll:true});}};
  const click=target=>{const n=target.closest('[data-cl-node]');if(!n)return;activate(n.dataset.clNode.replace(/^repair-/, 'source-'));if(n.hasAttribute('data-cl-repair-count')){const history=detailHost.querySelector('.pc-repair-overview');if(history){history.open=true;history.querySelector('summary').focus({preventScroll:true});}}};
  host.onclick=event=>click(event.target);host.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){const n=event.target.closest('[data-cl-node]');if(n){event.preventDefault();click(event.target);}}};
 }
 function popup(){
  let dialog=document.getElementById('pc-lineage-dialog');
  if(!dialog){
   dialog=document.createElement('dialog');dialog.id='pc-lineage-dialog';dialog.className='cl-detail-dialog';
   dialog.setAttribute('aria-labelledby','pc-lineage-dialog-title');
   dialog.innerHTML='<header><h3 id="pc-lineage-dialog-title">데이터 연결 상세</h3><button type="button" data-cl-close aria-label="데이터 연결 상세 닫기">닫기 ×</button></header><div id="pc-lineage-dialog-body" class="cl-dialog-body"></div>';
   dialog.querySelector('[data-cl-close]').onclick=()=>dialog.close();
   dialog.addEventListener('click',event=>{if(event.target!==dialog)return;const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();});
   document.body.appendChild(dialog);
  }
  return dialog;
 }
 function renderTab(options){
  const {host,stage,detailHost}=options,dialog=popup(),body=dialog.querySelector('.cl-dialog-body');
  if(host.dataset.flowStage!==stage&&dialog.open)dialog.close();
  if(host.dataset.flowStage!==stage){delete host.dataset.activeNode;host.dataset.flowStage=stage;}
  const legend=host.closest('.pc-diagram-card')?.querySelector('.pc-diagram-legend');
  if(legend)legend.innerHTML=stage==='ALL'
   ? '<span>━━ 저장된 단계 연결 있음</span><span class="cl-missing-legend">┄┄ 선택 범위에 연결 없음</span><span>세로 화살표: 단계 사이에 사용한 매칭 정보</span><span>상자·화살표 선택: 매칭 근거 팝업</span>'
   : '<span>━━ 필드·저장 연결 있음</span><span class="cl-review-legend">┄┄ 후보·추정 / 검토 필요</span><span class="cl-missing-legend">┄× 필드·연결 미확보</span><span class="cl-planned-legend">━━ 추가 확보·연결 보완</span><span>API · 파일 · 웹 · 내부</span>';
  detailHost.innerHTML='<p class="cl-help">상자와 화살표를 선택하면 상세 설명을 팝업에서 확인할 수 있습니다.</p>'+CollectionRepairs.html(options.data,options.rows,stage);
  body.onchange=null;
  const inner={...options,detailHost:body};
  if(stage==='ALL')render(inner);else CollectionStageLineage.render(inner);
  const click=host.onclick,keydown=host.onkeydown;
  const show=()=>{const inspector=body.querySelector('.cl-inspector');if(!inspector)return;dialog.querySelector('h3').textContent=inspector.querySelector('strong')?.textContent||'데이터 연결 상세';body.scrollTop=0;if(!dialog.open)dialog.showModal();};
  host.onclick=event=>{click?.(event);if(event.target.closest('[data-cl-node]'))show();};
  host.onkeydown=event=>{keydown?.(event);if((event.key==='Enter'||event.key===' ')&&event.target.closest('[data-cl-node]'))show();};
  if(dialog.open){const title=body.querySelector('.cl-inspector>strong');if(title)dialog.querySelector('h3').textContent=title.textContent;}

 }
 return {render:renderTab};
})();
