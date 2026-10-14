'use strict';
const CollectionRepairs=(()=>{
 const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const stages={POLICY:'정책',BUSINESS:'사업화',APPROVAL:'인허가',CONSTRUCTION:'건설',SUPPLY:'공급',MOVE_IN:'입주'};
 const status={APPLIED_REVIEW_PENDING:'조치 반영 · 담당자 검토 남음',OPEN:'미해결 · 조사 필요',RECOVERED:'수집 복구 · 내용 확인 별도',REVIEW:'연결 검토',CONFIRMED:'담당자 확정',RELEASED:'연결 해제',UNMATCHED:'미연결'};
 const fallbackTypes={IDENTITY_LINK:'사업 식별·원천 연결 오류',SCOPE_QUANTITY:'전체·유형별 물량 범위 오류',COLLECTION_GAP:'수집 범위·상세자료 누락',STAGE_DATE:'단계·일정 분류 오류',AVAILABILITY_STATE:'미확보 상태 구분 오류',COLLECTION_FAILURE:'수집 실패·복구',OTHER:'기타 오류'};
 const expanded=new Set();
 document.addEventListener('toggle',event=>{const target=event.target,key=target.dataset?.repairOpenKey;if(!key||!target.isConnected)return;if(target.open)expanded.add(key);else expanded.delete(key);},true);
 const open=key=>expanded.has(key)?' open':'';
 function relevant(data,rows,stage='ALL',sources=null,keys=null){
  const ids=new Set(rows.flatMap(p=>p.repair_ids||[]));
  return (data.repairs||[]).filter(r=>ids.has(r.id)&&(stage==='ALL'||r.stages.includes(stage))&&(!sources||(r.source_ids||[]).some(s=>sources.includes(s)))&&(!keys||(r.related_keys||[]).some(k=>keys.includes(k))));
 }
 function scope(rows,stage,sources,keys){
  const value=[rows.map(p=>p.id).sort().join(','),stage,(sources||[]).slice().sort().join(','),(keys||[]).slice().sort().join(',')].join('|');let hash=2166136261;
  for(const c of value)hash=Math.imul(hash^c.charCodeAt(0),16777619);return String(hash>>>0);
 }

 const qualityKinds={VALIDITY:'데이터 유효성',CONSISTENCY:'원천 간 정합성',COVERAGE:'수집 범위',PROCESSING:'시스템 처리'};
 const qualityLayers={SOURCE:'원천값 문제',SOURCE_LIMIT:'원천 제공 범위·형식의 한계',COLLECTION:'수집·정규화 문제',LINKAGE:'사업·필지 연결 문제',DISPLAY:'화면·집계 처리 문제'};
 const qualityResults={PASS:'확인·조치 완료',FAIL:'미해결',PARTIAL:'일부 보완·확인 필요',PENDING:'추가 확인 필요',NOT_APPLICABLE:'현재 원천으로 적용 불가'};
 function quality(r){
  if(!r.quality_checks?.length)return '<p class="pc-quality-unrecorded">유효성·정합성 점검 항목 미기록 · 원천이 정상이라고 확인된 것은 아닙니다.</p>';
  return '<section class="pc-quality-checks"><h6>데이터 유효성·정합성 점검</h6>'+r.quality_checks.map(c=>'<article class="pc-quality-check" data-quality-check="'+e(c.id)+'"><div class="pc-quality-head"><strong>'+e(c.title)+'</strong><span class="pc-quality-result pc-quality-'+e(c.result)+'">'+e(qualityResults[c.result]||c.result)+'</span></div><p class="pc-quality-layer">'+e(qualityKinds[c.kind]||c.kind)+' · '+e(qualityLayers[c.layer]||c.layer)+'</p><small>확인일 '+e(c.checked_at)+' · 점검 범위 '+e(c.checked_scope)+'</small>'+((c.metrics||[]).length?'<div class="pc-quality-metrics">'+c.metrics.map(m=>'<span>'+e(m.label)+' <b>'+Number(m.value).toLocaleString('ko-KR')+(m.total!=null?' / '+Number(m.total).toLocaleString('ko-KR'):'')+'</b> '+e(m.unit)+'</span>').join('')+'</div>':'')+'<dl><dt>판정 기준</dt><dd>'+e(c.rule)+'</dd><dt>확인 근거·문제</dt><dd>'+e(c.evidence)+'</dd><dt>정비 방법</dt><dd>'+e(c.repair)+'</dd><dt>완료 판단 기준</dt><dd>'+e(c.completion_criteria)+'</dd></dl>'+((c.evidence_refs||[]).length?'<details class="pc-quality-proof"><summary>점검 근거 식별정보</summary>'+c.evidence_refs.map(ref=>'<small>'+e(ref.name)+' · SHA256 '+e(ref.sha256)+'</small>').join('')+'</details>':'')+'</article>').join('')+'</section>';
 }
 function guideUrl(){
  const params=new URLSearchParams();for(const [id,key] of [['pc-policy','policy_id'],['pc-region','region'],['pc-search','q']]){const value=document.getElementById(id)?.value;if(value)params.set(key,value);}
  return '/poc/home/api/project-collection/quality-guide.json?'+params;
 }
 function record(r){
  return '<article class="pc-repair-record" data-repair-id="'+e(r.id)+'"><h5>'+e(r.title)+'</h5><small>'+e(status[r.status]||r.status)+' · '+e(r.base_date)+'</small><dl><dt>관련 단계</dt><dd>'+r.stages.map(s=>e(stages[s])).join(' · ')+'</dd><dt>오류·누락 원인</dt><dd>'+e(r.cause)+'</dd><dt>조치 내용</dt><dd>'+e(r.action)+'</dd><dt>영향 범위</dt><dd>'+e(r.impact)+'</dd><dt>남은 확인사항</dt><dd>'+e(r.remaining)+'</dd></dl>'+quality(r)+'<small>저장 판본 '+r.revision_no+' · '+e(r.recorded_at)+'</small>'+(r.report_url&&/^\/poc\/home\/assets\/reports\/[A-Z0-9_]+\.html$/.test(r.report_url)?'<p><a href="'+e(r.report_url)+'" target="_blank" rel="noopener">상세 점검 보고서 ↗</a></p>':'')+((r.history||[]).length>1?'<details><summary>이전 조치 판본 <span class="pc-repair-count">'+(r.history.length-1)+'개</span></summary>'+r.history.slice(1).map(h=>'<p><b>'+e(h.base_date)+' · '+e(status[h.status]||h.status)+'</b><br>원인: '+e(h.cause)+'<br>조치: '+e(h.action)+'<br>남은 확인: '+e(h.remaining)+'</p>'+quality(h)).join('')+'</details>':'')+'</article>';
 }
 function reports(){return '<details class="pc-link-changes pc-research-reports"><summary>원천 조사·정비 보고서 <span class="pc-repair-count">3건</span></summary>'+[
 ['EVIDENCE_LINK_REPAIR_20261012','원천 간 연결 정비 기록 · 추가 연결 및 보류 사유'],
 ['LH_NOTICE_GAPS_20261012','성남금토·유사 사례 진단 및 전체 보완 대책'],
 ['APPROVAL_LINK_REPAIR_20261012','과천주암·전체 인허가 연결 정비 및 수집 사각지대 개선']
 ].map(([file,title])=>'<details class="pc-report-entry"><summary>'+e(title)+'</summary><p>작성 당시의 점검 결과입니다. 최신 상태는 오류·조치 이력에서 확인합니다. <a href="/poc/home/assets/reports/'+file+'.html" target="_blank" rel="noopener">새 창에서 크게 보기 ↗</a></p><iframe loading="lazy" title="'+e(title)+'" src="/poc/home/assets/reports/'+file+'.html"></iframe></details>').join('')+'</details>';}
 function html(data,rows,stage='ALL',sources=null,keys=null){
  const repairs=relevant(data,rows,stage,sources,keys),changes=rows.length===1?(rows[0].link_changes||[]).filter(c=>stage==='ALL'||!c.stages.length||c.stages.includes(stage)):[];
  const types={...fallbackTypes,...data.repair_types},groups=new Map(),context=scope(rows,stage,sources,keys);
  for(const r of repairs){const kind=types[r.repair_type]?r.repair_type:'OTHER';if(!groups.has(kind))groups.set(kind,[]);groups.get(kind).push(r);}
  const overviewKey=context+':overview';
  const groupHtml=Object.entries(types).filter(([kind])=>groups.has(kind)).map(([kind,label])=>{const entries=groups.get(kind),key=context+':'+kind;return '<details class="pc-repair-type" data-repair-type="'+e(kind)+'" data-repair-open-key="'+key+'"'+open(key)+'><summary><strong>'+e(label)+'</strong><span class="pc-repair-count">'+entries.length+'건</span></summary><div class="pc-repair-type-records">'+entries.map(record).join('')+'</div></details>';}).join('');
  return '<section class="pc-repair-history"><details class="pc-repair-overview" data-repair-open-key="'+overviewKey+'"'+open(overviewKey)+'><summary><strong>오류·조치 이력</strong><span class="pc-repair-count">'+repairs.length+'건</span></summary><p>건수를 누르면 오류 유형별 이력이 펼쳐집니다. 건수는 조치 기록 수이며 사업·블록 수와 다릅니다. 점검 숫자는 각 기록의 확인일·점검 범위 기준입니다.</p><p><a class="pc-quality-export" href="'+e(guideUrl())+'" download>조회 범위 품질·정비 기록 내려받기 (JSON)</a></p>'+(repairs.length?groupHtml:'<p>선택 범위에 등록된 진단 기록이 없습니다. 오류가 없다는 의미는 아닙니다.</p>')+'</details>'+(changes.length?'<details class="pc-link-changes"><summary>실제 연결 변경 기록 <span class="pc-repair-count">'+changes.length+'건</span> · 연결별 최근 3건</summary>'+changes.map(c=>'<article><b>'+e(c.title)+'</b><small>'+e(c.recorded_at)+' · '+e(status[c.status]||c.status||'상태 미기록')+'</small><p>'+e(c.basis||'저장된 연결 상태 변경')+'</p><p>이전: '+e(status[c.before.status]||c.before.status||'미등록')+' / '+e(c.before.date||'사건일 미확인')+' → 이후: '+e(status[c.after.status]||c.after.status||'미기록')+' / '+e(c.after.date||'사건일 미확인')+'</p></article>').join('')+'</details>':'<details class="pc-link-changes"><summary>실제 연결 변경 기록 <span class="pc-repair-count">0건</span></summary><p>선택한 범위에서 표시할 변경 기록이 없습니다.</p></details>')+reports()+'</section>';
 }
 return {html,relevant};
})();
