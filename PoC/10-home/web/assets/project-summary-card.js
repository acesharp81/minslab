'use strict';
const ProjectSummaryCard=(()=>{
 const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const n=v=>v==null?'미확보':Number(v).toLocaleString('ko-KR');
 const stages=[['BUSINESS','사업화'],['APPROVAL','인허가'],['CONSTRUCTION','착공'],['COMPLETION','준공'],['MOVE_IN','입주']];
 const link=url=>/^https?:\/\//i.test(url||'')?'<a href="'+e(url)+'" target="_blank" rel="noopener noreferrer">원문 열기 ↗</a>':'';
 const valid=(r,asOf)=>Boolean(asOf&&r?.date&&r.date<=asOf&&(r.units==null||Number(r.units)>0));
 function data(m){
  const p=m.project,asOf=m.as_of_date;
  const milestones=stages.map(([key,label])=>{const cell=m.cells?.[key==='COMPLETION'?'CONSTRUCTION':key],saved=m.progress_defaults?.[key];
   const record=saved?.event_date?{date:saved.event_date,units:saved.units}:(cell?.management?.measurement||[]).find(r=>(r.milestone||key)===key&&valid(r,asOf));
   return {key,label,date:valid(record,asOf)?record.date:null};});
  const pct=m.cells?.CONSTRUCTION?.management?.progress_pct;
  const progress=pct?.date&&pct.date<=asOf&&pct.pct!=null?pct:null;
  const last=[...milestones].reverse().find(r=>r.date),key=last?.key||null;
  const status=key==='MOVE_IN'?'입주 진행':key==='COMPLETION'?'준공 확인':key==='CONSTRUCTION'||(!['MOVE_IN','COMPLETION'].includes(key)&&progress?.pct>0)?'건설 진행':key==='APPROVAL'?'인허가 진행':key==='BUSINESS'?'사업화 진행':'계획 · 진행 확인 전';
  const supply=m.progress_defaults?.SUPPLY;
  const supplyDate=valid({date:supply?.event_date,units:supply?.units},asOf)?supply.event_date:null;
  const developer=p.developer||m.supply_conditions?.developer;
  const publicDeveloper=/^(LH|SH|GH|한국토지주택공사|서울주택도시공사|서울주택도시개발공사|경기주택도시공사|인천도시공사|iH)$/i.test(developer||'');
  const groups=(m.supply_conditions?.groups||[]).filter(g=>g.name&&!/확인 필요|미확보|미분류/.test(g.name)&&g.units!=null);
  return {milestones,progress,last,status,supplyDate,developer,publicDeveloper,groups};
 }
 function records(m){return Object.entries(m.stages||{}).map(([key,label])=>{const seen=new Set(),rows=[];for(const r of m.cells?.[key]?.sources||[]){const id=JSON.stringify([r.source_id,r.source_entity_id,r.source_revision_no,r.kind,r.milestone,r.date,r.date_label,r.units,r.basis,r.evidence_url]);if(seen.has(id))continue;seen.add(id);rows.push(r);}return {key,label,rows};});}
 function render(m,{editable=false}={}){
  const p=m.project,d=data(m),count=records(m).reduce((sum,s)=>sum+s.rows.length,0);
  const narrative=[d.last?d.last.label+' 진행일 '+d.last.date:'현재까지 등록된 진행일이 없습니다.',d.progress?'공정률 '+n(d.progress.pct)+'% ('+d.progress.date+' 기준)':'',d.supplyDate?'공급·모집 진행일 '+d.supplyDate:''].filter(Boolean);
  const next=d.milestones.find(r=>!r.date&&(!d.last||stages.findIndex(x=>x[0]===r.key)>stages.findIndex(x=>x[0]===d.last.key)));
  const due=next&&m.schedules?.[next.key]?.due_date;
  if(due)narrative.push(next.label+' 목표일 '+due);
  return '<article class="pr-card pjt-summary-card pjt-story-card"><div class="pjt-story-top"><span class="pjt-story-badge">● '+e(d.status)+'</span>'+(editable?'<button class="button primary" type="button" data-pjt-edit>✎ 사업정보수정</button>':'')+'</div><div class="pjt-title"><h3>'+e(p.name)+'</h3></div><p class="pjt-story-subtitle">'+e([p.program,p.address||[p.region,p.municipality].filter(Boolean).join(' · '),p.planned_units!=null?n(p.planned_units)+'세대':null].filter(Boolean).join(' · '))+'</p><section class="pjt-story-section"><h4>진행 단계</h4><ol class="pjt-timeline">'+d.milestones.map(r=>'<li class="'+(r.date?'is-reached':'')+'"'+(d.last?.key===r.key?' aria-current="step"':'')+'><span class="pjt-step-dot" aria-hidden="true">'+(r.date?'✓':'')+'</span><b>'+e(r.label)+'</b><small>'+e(r.date?r.date.slice(0,7).replace('-','.'):'진행일 미확인')+'</small></li>').join('')+'</ol><div class="pjt-story-note">'+narrative.map(v=>'<p>'+e(v)+'</p>').join('')+'</div></section><div class="pjt-story-facts-grid"><section class="pjt-story-section"><h4>공급유형</h4><p><strong>'+e(p.supply_type_assessment?.label||'미확인')+'</strong></p><p class="pjt-story-muted">'+e(p.supply_type_assessment?.basis||'공급유형 근거 확인 필요')+'</p><h4>공공 여부</h4><p><strong>'+e(d.publicDeveloper?'공공 시행':'공공 여부 확인 필요')+'</strong>'+(d.developer?' · '+e(d.developer):'')+'</p>'+(p.tenure&&!/확인 필요|미확보/.test(p.tenure)?'<p>'+e(p.tenure)+'</p>':'')+'</section><section class="pjt-story-section"><h4>세대</h4><p><strong>'+n(p.planned_units)+(p.planned_units==null?'':'세대')+'</strong> <span class="pjt-story-muted">계획 규모</span></p><p>'+e(d.groups.length?d.groups.map(g=>g.name+' '+n(g.units)+'호').join(' · '):'세대 구성 미확보')+'</p>'+(p.contractor?'<p>시공사 '+e(p.contractor)+'</p>':'')+'</section></div><section class="pjt-story-section pjt-record-entry"><h4>연결된 기록</h4><button type="button" data-pjt-records aria-haspopup="dialog" aria-expanded="false">단계별 연결 기록 '+n(count)+'건 <span aria-hidden="true">↗</span></button></section></article>';
 }
 function renderRecords(m){return '<p class="pjt-record-intro">'+e(m.project.name)+' · 조회 기준 '+e(m.as_of_date)+'</p><div class="pjt-record-groups">'+records(m).map(s=>'<section data-pjt-record-stage="'+e(s.key)+'"><h4>'+e(s.label)+' <small>'+s.rows.length+'건</small></h4>'+(s.rows.length?s.rows.map(r=>'<article><div class="pjt-record-title"><b>'+e(r.link_origin==='POLICY_ASSIGNMENT'?'정책·프로그램 배정 기록':r.name||r.source_id||'출처 미기록')+'</b><span>'+e(({PLAN:'목표·예정 자료',PLAN_STATUS:'일정 상태',ACTUAL:'진행 기록',STATE:'상태 자료',DOCUMENT:'근거 문서',LINK:'배정·연결 자료'})[r.kind]||r.kind)+'</span></div><p>'+e([r.milestone==='COMPLETION'?'준공':r.milestone==='CONSTRUCTION'?'착공':null,r.date||r.date_label,r.units==null?null:n(r.units)+'호'].filter(Boolean).join(' · '))+'</p><p>'+e(r.basis||'상세 내용 미기록')+'</p>'+(r.actor?'<p>입력·확인: '+e(r.actor)+(r.changed_at?' · '+e(r.changed_at.slice(0,10)):'')+'</p>':'')+link(r.evidence_url)+(r.source_entity_id?'<details><summary>원천 기록 번호 보기</summary><p>'+e(r.source_entity_id)+(r.source_revision_no?' · 판본 '+e(r.source_revision_no):'')+'</p></details>':'')+'</article>').join(''):'<p class="pjt-story-muted">연결된 자료가 없습니다.</p>')+'</section>').join('')+'</div><footer class="pjt-record-footer"><button type="button" data-pjt-record-history>변경 이력 보기</button><button type="button" data-pjt-record-original>사업 원천 상세 보기 ↗</button></footer>';}
 return {data,records,render,renderRecords};
})();
