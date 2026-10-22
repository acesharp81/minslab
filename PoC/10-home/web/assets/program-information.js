'use strict';
const ProgramInformation=(()=>{
  let programId, model, dialog, changes={}, programChanges={}, busy=false, policyRows=[], programRows=[], selectorPolicyId='';
  const labels={name:'프로그램명',overview:'개요 · 서술식 목표',period_start:'추진 시작일',period_end:'추진 종료일',target_units:'프로그램 전체 목표',advice:'프로그램 조언',developer:'담당기관',metric:'목표 기준',unit:'목표 단위',target_mode:'목표 관리방식'};
  const icons={evidence:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h7l2 2h9v12H3z M6 6V3h12v5 M7 12h10 M7 16h7"/></svg>',edit:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 16-1 5 5-1L20 8l-4-4Z M14 6l4 4"/></svg>'};
  const own=(o,k)=>Object.prototype.hasOwnProperty.call(o,k),fmt=v=>v==null?'미확보':num(v)+(model?.fields?.unit?.value||'호');
  const housing=v=>v==null?'미확보':num(v)+'호';
  const label=k=>k==='parent'?'정책 연결':k==='programs'?'프로그램–사업 연결':k.startsWith('program:')?(model.programs.find(p=>p.id===k.slice(8))?.name||'프로그램 연결'):labels[k]||k.replace('region:','지역 목표 · ').replace('annual:','연간 목표 · ').replaceAll(':',' · ');
  const source=k=>model.fields[k]?.evidence.find(e=>e.origin==='SOURCE')||{value:null,basis:'지역·연간 개별 목표 미배분',origin:'SOURCE'};
  const value=k=>own(changes,k)?changes[k]===null?source(k).value:changes[k]:model.fields[k]?.value;
  let selectedScope='전체', tooltip;
  const shorten=(text,max=200)=>{const chars=Array.from(String(text||'').replace(/\s+/g,' ').trim());return chars.length>max?chars.slice(0,max-3).join('')+'...':chars.join('');};
  function cite(e){
    if(e.origin==='MANUAL')return '사용자 입력 · '+(e.actor||'담당자')+' · '+timeText(e.changed_at);
    if(e.document_name)return e.document_name+(e.printed_page?', '+e.printed_page+'쪽':e.pdf_page?', PDF '+e.pdf_page+'쪽':'');
    try{return new URL(e.evidence_url).hostname;}catch{return '수집 자료';}
  }
  function excerpt(e){return e.excerpt||(e.origin==='MANUAL'?(typeof e.value==='number'?fmt(e.value):e.value||e.reason)+' · '+(e.reason||''):e.basis||String(e.value??'개별 값 미확보'));}
  function preview(k){
    if(k==='parent')return model.parent_policy_name+' ('+model.parent_policy_id+') · '+model.parent_basis;
    if(k==='id')return '이 프로그램의 시스템 식별자는 '+model.policy_id+'입니다. 정책·프로그램 연결에서 같은 ID를 사용합니다.';
    if(k==='programs')return model.programs.filter(p=>p.selected).map(p=>p.name).join(', ')+' — 현재 저장된 프로그램 포함 사업';
    if(k.startsWith('program:')){const p=model.programs.find(p=>p.id===k.slice(8)),e=p.evidence?.[0]||{basis:p.basis};const citation=' ('+shorten(cite(e),100)+')';return shorten(excerpt(e),200-Array.from(citation).length)+citation;}
    if(k.startsWith('actual:')){const [,r,y]=k.split(':'),a=model.actual[r],rows=a.evidence.filter(e=>!y||e.date.startsWith(y));return rows.length?rows.map(e=>e.name+' · '+e.date+' 동일 단계 확인 '+fmt(e.value)).join('; ')+' (연결 사업 동일 단계 근거 · 사업 귀속 검토 중 포함)':'해당 지역·연도의 프로그램 연결 사업 동일 단계 확인량이 수집되지 않았습니다. 미확보는 0호를 뜻하지 않습니다.';}
    if(k==='progress'||k.startsWith('stage:')){const stage=k.slice(6);return stage==='POLICY'?'정책 단계는 전체 목표 '+fmt(model.fields.target_units.value)+'입니다. 이후 단계는 해당 단계와 이후 단계의 누적 도달량입니다.':Object.entries(model.progress).filter(([s])=>k==='progress'||s===stage).map(([s,v])=>model.stages[s]+' '+housing(v)).join(' · ')+' ('+model.as_of_date+' 기준 · 해당 단계와 이후 단계 누적 · 단계 간 합산 금지)';}
    const e=model.fields[k]?.evidence[0]||source(k),citation=' ('+cite(e)+')';
    return shorten(excerpt(e),Math.max(40,200-Array.from(citation).length))+citation;
  }
  const icon=(key,kind='evidence')=>'<button type="button" class="pi-icon" data-pi-'+kind+'="'+esc(key)+'" aria-label="'+esc((kind==='edit'?'수정: ':'근거: ')+label(key))+'" '+(kind==='evidence'?'data-pi-tooltip="'+esc(shorten(preview(key)))+'"':'title="입력칸으로 이동"')+'>'+icons[kind]+'</button>';
  function input(k,compact=false){
    const numeric=k==='target_units'||k.startsWith('region:')||k.startsWith('annual:'),isDate=k.startsWith('period_'),v=value(k),multi=k==='overview'||k==='advice';
    const choices=k==='target_mode'?{INDEPENDENT:'별도 관리목표',PROJECT_SUM:'사업 합산 기준 · 채택값'}:k==='metric'?{BUSINESS:'사업화',APPROVAL:'인허가',CONSTRUCTION:'착공',SUPPLY:'공급·모집',COMPLETION:'준공',MOVE_IN:'입주',CAPACITY:'전체 규모·개소'}:k==='unit'?{'호':'호','명':'명','개소':'개소'}:null;
    if(choices)return '<div class="pi-input-wrap" data-pi-wrap="'+esc(k)+'"><select data-pi-input="'+k+'" aria-label="'+label(k)+'">'+Object.entries(choices).map(([key,text])=>'<option value="'+key+'" '+(v===key?'selected':'')+'>'+text+'</option>').join('')+'</select><button type="button" class="pi-reset" data-pi-reset="'+esc(k)+'" title="사용자 입력 해제 · 원천값 사용" aria-label="'+esc(label(k))+' 원천값 사용">↺</button><span class="pi-input-state" data-pi-state="'+esc(k)+'">'+(model.fields[k]?.manual?'입력값':'')+'</span></div>';
    const attrs='data-pi-input="'+esc(k)+'" aria-label="'+esc(label(k))+'" '+(numeric?'type="number" min="0" max="100000000" step="1" inputmode="numeric"':isDate?'type="date"':'type="text"')+(k==='name'||k==='overview'||isDate?' required':'');
    return '<div class="pi-input-wrap '+(compact?'pi-compact-input ':'')+(model.fields[k]?.manual?'pi-has-manual':'')+'" data-pi-wrap="'+esc(k)+'">'+(multi?'<textarea '+attrs+' rows="2" maxlength="4000" placeholder="'+(k==='advice'?'프로그램 판단과 조치 방향을 입력하세요':'프로그램 목표를 입력하세요')+'">'+esc(v??'')+'</textarea>':'<input '+attrs+' value="'+esc(v??'')+'" '+(!numeric&&!isDate?'maxlength="150"':'')+' placeholder="미배분">')+'<button type="button" class="pi-reset" data-pi-reset="'+esc(k)+'" title="사용자 입력 해제 · 원천값 사용" aria-label="'+esc(label(k))+' 원천값 사용">↺</button><span class="pi-input-state" data-pi-state="'+esc(k)+'">'+(model.fields[k]?.manual?'입력값':'')+'</span></div>';
  }
  function field(k){return '<div class="pi-field pi-field-'+k+'"><div class="pi-label"><label for="pi-input-'+k+'">'+esc(label(k))+'</label>'+icon(k)+icon(k,'edit')+'</div>'+input(k)+'</div>';}
  function actual(scope,year){const data=model.actual[scope],v=year?data.annual[year]:data.value;return '<span class="'+(v==null?'pi-missing':'')+'">'+fmt(v)+'</span>'+icon('actual:'+scope+(year?':'+year:''));}
  function displayYears(){const start=Number(String(value('period_start')).slice(0,4)),end=Number(String(value('period_end')).slice(0,4));return start>=1900&&end<=2100&&end>=start&&end-start<=30?Array.from({length:end-start+1},(_,i)=>start+i):model.years;}
  function refreshYears(){dialog.querySelector('#pi-annual').innerHTML=annual();Object.keys(changes).forEach(mark);refreshManagement();}
  function addYear(){
    const box=dialog.querySelector('[data-pi-year]'),year=Number(box.value),years=displayYears();
    if(!Number.isInteger(year)||year<1900||year>2100){status('1900~2100 사이의 연도를 입력하세요.');box.focus();return;}
    const lo=Math.min(year,years[0]),hi=Math.max(year,years.at(-1));
    if(hi-lo>30){status('추진기간은 최대 31개 연도입니다.');return;}
    if(year<years[0]){changes.period_start=year+'-01-01';setInput('period_start',changes.period_start);}
    if(year>years.at(-1)){changes.period_end=year+'-12-31';setInput('period_end',changes.period_end);}
    refreshYears();box.value=Math.min(2100,hi+1);
    const input=dialog.querySelector('[data-pi-input="annual:'+selectedScope+':'+year+'"]');input?.focus();
    status(years.includes(year)?'이미 있는 연도입니다. 목표를 입력하세요.':'연도를 추가했습니다. 추진기간 확장과 연간 목표가 함께 저장됩니다.');
  }
  function annual(){return '<table class="pi-annual-table"><thead><tr><th>연도</th><th>연간 목표량 <small>직접 입력</small></th><th>연간 실제량</th></tr></thead><tbody>'+displayYears().map(y=>{const key='annual:'+selectedScope+':'+y;return '<tr><th>'+y+'</th><td><div class="pi-cell-input">'+input(key,true)+icon(key)+'</div></td><td>'+actual(selectedScope,String(y))+'</td></tr>';}).join('')+'</tbody></table>';}
  const selected=p=>own(programChanges,p.id)?programChanges[p.id].selected:p.selected;
  const projectName=p=>p.name.replace(/^\s*\[.*?\]\s*/, '').replace(/^\(\d+\)\s*/, '');
  function projectGroups(){
    const groups=new Map();
    for(const p of [...model.programs].sort((a,b)=>(a.region==='지역 미확인')-(b.region==='지역 미확인')||a.region.localeCompare(b.region,'ko')||projectName(a).localeCompare(projectName(b),'ko',{numeric:true})||a.id.localeCompare(b.id))){if(!groups.has(p.region))groups.set(p.region,[]);groups.get(p.region).push(p);}
    return [...groups].map(([region,items])=>'<section class="pgi-group" data-pgi-group="'+esc(region)+'"><header><label><input type="checkbox" data-pgi-region="'+esc(region)+'">'+esc(region)+'</label><span data-pgi-group-count></span></header><div class="pgi-group-rows">'+items.map(p=>'<div class="pi-program" data-pi-program-row data-project-id="'+esc(p.id)+'"><label><input type="checkbox" data-pi-program="'+esc(p.id)+'" '+(selected(p)?'checked':'')+'><span title="'+esc(p.name)+'">'+esc(p.name)+'<small>'+esc(p.municipality||'')+'</small></span></label><span class="pi-program-state" data-pi-program-state>'+esc(p.selected?p.status==='REVIEW'?'확인 필요':'포함':p.policy_id==='UNASSIGNED'||p.status==='RELEASED'?'미연결':'다른 프로그램')+'</span>'+icon('program:'+p.id)+icon('program:'+p.id,'edit')+'</div>').join('')+'</div></section>').join('');
  }
  function visibleProjects(region){
    const ids=new Set([...dialog.querySelectorAll('[data-pi-program-row]')].filter(n=>!n.hidden&&(!region||n.closest('[data-pgi-group]').dataset.pgiGroup===region)).map(n=>n.dataset.projectId));
    return model.programs.filter(p=>ids.has(p.id));
  }
  function groupState(){
    const sync=(box,items)=>{const n=items.filter(selected).length;box.checked=items.length>0&&n===items.length;box.indeterminate=n>0&&n<items.length;box.disabled=!items.length;return n;};
    sync(dialog.querySelector('[data-pgi-all]'),visibleProjects());
    dialog.querySelectorAll('[data-pgi-group]').forEach(group=>{const items=visibleProjects(group.dataset.pgiGroup);group.hidden=!items.length;const n=sync(group.querySelector('[data-pgi-region]'),items);group.querySelector('[data-pgi-group-count]').textContent=n+' / '+items.length+'개 선택';});
  }
  function selectBatch(region,checked){
    const items=visibleProjects(region),moving=items.filter(p=>checked&&!selected(p)&&p.policy_id!==model.policy_id&&p.policy_id!=='UNASSIGNED'&&p.status!=='RELEASED');
    if(moving.length&&!confirm('선택한 사업 중 '+moving.length+'개가 다른 프로그램에서 현재 프로그램으로 이동합니다. 일괄 선택할까요?')){groupState();return;}
    items.forEach(p=>updateProgram(p,checked,true));updateCount();
  }
  function managementHtml(){
    const m=model.management;if(!m)return '';
    const card=(name,v,unit='호')=>'<div><small>'+name+'</small><strong>'+(v==null?'미확보':num(v)+esc(unit))+'</strong></div>';
    const dirty=Object.keys(programChanges).length||['metric','unit','period_start','period_end'].some(k=>own(changes,k));
    const target=value('target_units'),gap=m.period_plan_units==null||target==null||m.target_kind==='EFFECT'||value('unit')!=='호'?null:target-m.period_plan_units;
    return '<div class="pi-section-head"><h3>관리목표와 사업계획 <span class="pgi-kind">'+esc(m.target_kind_label)+'</span></h3><button type="button" data-pgi-management-detail>판단 근거·추가 수집</button></div><div class="pgi-metrics">'+card('관리목표 · '+(value('target_mode')==='PROJECT_SUM'?'합산 채택값':'별도 목표'),target,value('unit'))+card('연결 사업 전체 계획',m.capacity_units)+card('동일 단계·기간 계획',m.period_plan_units)+card('계획 차이 · 지연 아님',gap)+'</div><div class="pgi-management-foot"><span>'+esc(m.case)+' · '+m.counted_project_count+'개 사업 · 귀속 검토 '+m.review_project_count+' · 물량 미확보 '+m.missing_quantity_count+' · 일정 미확보 '+m.missing_schedule_count+(dirty?' · 연결·범위 수정 후 저장하여 재계산':'')+'</span><button type="button" data-pgi-adopt '+(!m.aggregate_allowed||dirty?'disabled':'')+'>사업 합계를 목표로 채택</button></div>';
  }
  function refreshManagement(){const node=dialog.querySelector('#pgi-management');if(node)node.innerHTML=managementHtml();}
  function adoptAggregate(){
    const m=model.management;
    if(!m.aggregate_allowed||Object.keys(programChanges).length||['metric','unit','period_start','period_end'].some(k=>own(changes,k))){status('먼저 사업 연결·범위를 저장하고 동일 단계·기간의 계획을 확인하세요.');return;}
    changes.target_mode='PROJECT_SUM';changes.target_units=m.period_plan_units;
    setInput('target_mode','PROJECT_SUM');setInput('target_units',m.period_plan_units);refreshManagement();
    status('사업 합계 '+housing(m.period_plan_units)+'를 목표 채택값으로 저장합니다. 이후 사업 변경은 참고 합계에만 반영됩니다.');
  }
  function managementDetail(){
    const m=model.management;
    popup('프로그램 목표 판단·추가 자료 수집','<p><b>'+esc(m.case)+'</b><br>'+esc(m.guidance)+'</p><p>'+esc(m.notice)+'</p><p>전체 계획과 같은 단계·기간 계획을 구분합니다. 부분 합계는 전체 물량으로 확정하지 않습니다. 약량·최소목표·효과목표는 원문의 의미를 유지합니다.</p><h3>추가로 필요한 자료</h3>'+(m.required_data||[]).map(t=>'<p>• '+esc(t)+'</p>').join('')+'<h3>사업별 집계 근거</h3>'+m.rows.map(r=>'<article><b>'+esc(r.name)+'</b><p>전체 계획 '+housing(r.capacity)+' / 기간 내 계획 '+housing(r.period_plan_units)+' · '+esc({AVAILABLE:'계획 확인',OUTSIDE_PERIOD:'프로그램 기간 밖',SCHEDULE_NOT_ACQUIRED:'동일 단계 계획 일정 미확보'}[r.status]||r.status)+' · 귀속 '+esc(r.mapping_status)+'</p>'+link(r.evidence_url)+r.schedule_points.map(p=>'<p>'+esc(p.date)+' · '+housing(p.units)+' · '+esc(p.basis)+'</p>').join('')+'</article>').join('')+'<h3>API 신청·기관 제공 요청</h3>'+m.api_guides.map(g=>'<article><b>'+esc(g.name)+'</b><p>'+esc(g.org)+' · '+esc(g.mode==='DATA_REQUEST'?'기관 원장 제공 요청':g.collector.key_configured?'기존 키 설정됨 · 수집 '+g.collector.status:'해당 서비스 승인 확인 필요')+'</p><p>'+esc(g.fields)+'</p><p>'+esc(g.steps)+'</p><p>'+esc(g.limitation)+'</p>'+link(g.url)+'<p><a href="'+API+'/api-requests/'+encodeURIComponent(g.id)+'/draft.txt" target="_blank" rel="noopener">신청 초안 다운로드 ↓</a></p></article>').join(''));
  }
  function currentPrograms(){return programRows.filter(p=>p.id===programId||(p.policy_id===selectorPolicyId&&!['RELEASED','REJECTED'].includes(p.status))).sort((a,b)=>a.name.localeCompare(b.name,'ko',{numeric:true})||a.id.localeCompare(b.id));}
  function selectors(){
    const programs=currentPrograms();
    return '<div class="pi-basic-grid pgi-identities"><div class="pi-field"><div class="pi-label">정책 ID '+(model?icon('parent'):'')+'</div><input class="pi-readonly" data-pgi-policy-id value="'+esc(selectorPolicyId)+'" aria-label="정책 ID" readonly></div><div class="pi-field"><div class="pi-label"><label for="pgi-policy-select">정책명</label></div><select id="pgi-policy-select" data-pgi-policy aria-label="정책명">'+policyRows.map(p=>'<option value="'+esc(p.policy_id)+'" '+(p.policy_id===selectorPolicyId?'selected':'')+(p.policy_id!=='POL_2025_0907'?' disabled':'')+'>'+esc(p.name+(p.policy_id!=='POL_2025_0907'?' (비활성)':''))+'</option>').join('')+'</select></div><div class="pi-field"><div class="pi-label">프로그램 ID '+(model?icon('id'):'')+'</div><input class="pi-readonly" data-pgi-program-id value="'+esc(model?.program_id||model?.policy_id||'')+'" aria-label="프로그램 ID · 시스템 부여" readonly></div><div class="pi-field"><div class="pi-label"><label for="pgi-program-select">프로그램명</label>'+(model?icon('name')+icon('name','edit'):'')+'</div><select id="pgi-program-select" data-pgi-program-select aria-label="프로그램명" '+(!programs.length?'disabled':'')+'>'+(!programs.length?'<option value="">연결된 프로그램 없음</option>':programs.map(p=>'<option value="'+esc(p.id)+'" '+(p.id===programId?'selected':'')+'>'+esc(p.id===programId?value('name'):p.name)+'</option>').join(''))+'</select></div></div>';
  }
  function restoreSelectors(){const policy=dialog.querySelector('[data-pgi-policy]'),program=dialog.querySelector('[data-pgi-program-select]');if(policy)policy.value=selectorPolicyId;if(program)program.value=programId||'';}
  async function switchSelection(policyId,nextId){
    if(busy){restoreSelectors();return;}
    if(policyId!=='POL_2025_0907'){restoreSelectors();if(model)status('현재9.7 정책만 활성화되어 있습니다.');return;}
    if(policyId===selectorPolicyId&&nextId===programId)return;
    if((Object.keys(changes).length||Object.keys(programChanges).length)&&!confirm('저장하지 않은 변경 내용을 취소하고 다른 프로그램을 조회할까요?')){restoreSelectors();return;}
    busy=true;dialog.querySelector('.pi-body').inert=true;dialog.querySelector('[data-pi-save]')?.setAttribute('disabled','');if(model)status('선택한 정책의 프로그램을 조회합니다…');
    try{
      const list=await request('/programs?policy_id='+encodeURIComponent(policyId));
      const items=list.items.filter(p=>p.policy_id===policyId&&!['RELEASED','REJECTED'].includes(p.status)).sort((a,b)=>a.name.localeCompare(b.name,'ko',{numeric:true})||a.id.localeCompare(b.id));
      const pid=items.some(p=>p.id===nextId)?nextId:items[0]?.id;
      const loaded=pid?await request('/program-information/'+encodeURIComponent(pid)):null;
      if(!dialog.isConnected)return;
      if(loaded&&loaded.parent_policy_id!==policyId)throw new Error('프로그램 정책 연결이 변경됐습니다. 목록을 다시 선택하세요.');
      selectorPolicyId=policyId;programRows=items;programId=pid||'';model=loaded;changes={};programChanges={};selectedScope='전체';busy=false;
      if(model)render();else renderEmpty();
    }catch(e){restoreSelectors();if(model)status(e.message);else dialog.querySelector('[role="status"]').textContent=e.message;}
    finally{busy=false;dialog.querySelector('.pi-body').inert=false;const saveButton=dialog.querySelector('[data-pi-save]');if(saveButton)saveButton.disabled=false;}
  }
  function renderEmpty(){dialog.innerHTML='<header class="pi-head"><h2 id="pi-title">프로그램정보</h2><button type="button" data-pi-close aria-label="프로그램정보 닫기">×</button></header><div class="pi-body"><section class="pi-card pi-basics">'+selectors()+'</section><p role="status">선택한 정책에 연결된 프로그램이 없습니다. 정책정보의 프로그램 연결을 확인하세요.</p></div>';}
  function renameProgram(){
    const popupDialog=popup('프로그램명 수정','<label>프로그램명<input data-pgi-rename maxlength="150" value="'+esc(value('name'))+'" required></label><p>명칭 변경은 프로그램정보 저장 시 변경자·사유와 함께 반영됩니다.</p><button type="button" data-pgi-rename-apply>입력 적용</button>');
    const name=popupDialog.querySelector('[data-pgi-rename]');name.focus();name.select();
    popupDialog.querySelector('[data-pgi-rename-apply]').onclick=()=>{if(!name.checkValidity()||!name.value.trim()){name.reportValidity();return;}const text=name.value.trim();if(text===model.fields.name.value)delete changes.name;else changes.name=text;const option=dialog.querySelector('[data-pgi-program-select] option:checked');if(option)option.textContent=text;status('프로그램명 변경은 저장 후 반영됩니다.');popupDialog.close();};
  }
  function render(){
    const regions=['전체',...model.regions];
    dialog.innerHTML=`<header class="pi-head"><div><span class="pi-eyebrow">프로그램 관리</span><h2 id="pi-title">프로그램정보</h2><span class="pi-asof">실적 기준 ${esc(model.as_of_date)}</span></div><div><button type="button" class="pi-history-button" data-pi-history>변경 이력 <b>${model.history.length}</b></button><button type="button" data-pi-close aria-label="프로그램정보 닫기">×</button></div></header>
    <form class="pi-form" id="pi-form"><div class="pi-body">
      <section class="pi-card pi-basics">${selectors()}${field('overview')}<div class="pgi-meta">${field('period_start')}${field('period_end')}${field('developer')}${field('metric')}${field('unit')}${field('target_mode')}</div></section>
      <section class="pi-card pgi-management" id="pgi-management">${managementHtml()}</section>
      <section class="pi-card pi-targets"><div class="pi-section-head"><h3>지역별 목표·실제량</h3><span>${esc({CONSTRUCTION:'착공',SUPPLY:'공급·모집',BUSINESS:'사업화',APPROVAL:'인허가',COMPLETION:'준공',MOVE_IN:'입주',CAPACITY:'전체 규모·개소'}[model.fields.metric.value])} · ${esc(model.fields.unit.value)}</span></div><table class="pi-region-table"><thead><tr><th>지역</th><th>총 목표량 <small>직접 입력</small></th><th>실제 확인량</th></tr></thead><tbody>${regions.map(r=>{const key=r==='전체'?'target_units':'region:'+r;return '<tr data-pi-region-row="'+esc(r)+'" class="'+(r===selectedScope?'selected':'')+'"><th><button type="button" data-pi-scope="'+esc(r)+'" aria-pressed="'+(r===selectedScope)+'">'+esc(r)+'<span>›</span></button></th><td><div class="pi-cell-input">'+input(key,true)+icon(key)+'</div></td><td>'+actual(r)+'</td></tr>';}).join('')}</tbody></table>
      <div class="pi-section-head pi-annual-head"><h3><span id="pi-annual-scope">${esc(selectedScope)}</span> · 연도별 목표</h3><div class="pi-year-tools"><input type="number" data-pi-year min="1900" max="2100" step="1" value="${Math.min(2100,displayYears().at(-1)+1)}" aria-label="추가할 연도"><button type="button" data-pi-add-year>+ 연도 추가</button></div></div><div class="pi-annual-scroll" id="pi-annual">${annual()}</div><p class="pi-note">연간 목표는 그해 증가 물량 · 미확보 ≠ 0 · 빈칸/↺는 원천값 사용</p></section>
      <div class="pi-right">
        <section class="pi-card pi-mapping"><div class="pi-section-head"><h3>포함 사업 ${icon('programs')}${icon('programs','edit')}</h3><span id="pi-program-count" role="status"></span></div><input class="pi-program-search" type="search" data-pi-program-search aria-label="사업 찾기" placeholder="사업명으로 찾기"><div class="pgi-bulk"><label><input type="checkbox" data-pgi-all> 검색 결과 전체 선택</label><button type="button" data-pgi-apply>선택 사업 적용</button></div><div class="pi-programs pgi-groups">${projectGroups()}</div><p class="pi-note">지역별·이름순 목록입니다. 선택 사업 적용 시 변경자·사유와 함께 저장됩니다. 다른 프로그램 소속은 이동 여부를 확인합니다.</p></section>
        <section class="pi-card pi-progress"><div class="pi-section-head"><h3>누적 진행현황 ${icon('progress')}</h3><span>저장된 연결 기준</span></div><div class="pi-stages">${Object.entries(model.stages).map(([k,v])=>'<div class="pi-stage-'+k+'"><span>'+esc(v)+icon('stage:'+k)+'</span><strong>'+housing(model.progress[k])+'</strong></div>').join('')}</div><p class="pi-note">정책 = 전체 목표 · 각 단계 = 해당 단계 + 이후 단계 누적 도달량<br>단계 간 합산 금지 · 입주는 입주 시작 확인 사업 물량 · 원천 미확보를 실적으로 보정하지 않음</p></section>
        <section class="pi-card pi-advice-card">${field('advice')}</section>
      </div>
    </div><footer class="pi-footer"><label>변경자<input id="pi-actor" maxlength="100" placeholder="성명 / 부서" autocomplete="off"></label><label class="pi-reason-label">변경 사유<input id="pi-reason" maxlength="1000" placeholder="목표 조정·프로그램 연결 근거"></label><div class="pi-save-group"><p id="pi-status" role="status">입력값 우선 · 서류철에서 원문 근거 확인</p><button type="submit" class="pi-save" data-pi-save>변경 내용 저장</button></div></footer></form><div class="pi-tooltip" role="tooltip" id="pi-tooltip" hidden></div>`;
    tooltip=dialog.querySelector('#pi-tooltip');
    dialog.querySelectorAll('[data-pi-input]').forEach(n=>n.id='pi-input-'+n.dataset.piInput);
    dialog.querySelector('#pi-form').onsubmit=e=>{e.preventDefault();save();};
    dialog.querySelector('.pi-body').inert=busy;updateCount();
  }
  function updateCount(){const n=model.programs.filter(p=>own(programChanges,p.id)?programChanges[p.id].selected:p.selected).length;dialog.querySelector('#pi-program-count').textContent=n+' / '+model.programs.length+'개 선택'+(Object.keys(programChanges).length?' · 저장 전':'');groupState();refreshManagement();}
  function hideTip(){if(tooltip)tooltip.hidden=true;dialog?.querySelectorAll('[aria-describedby="pi-tooltip"]').forEach(n=>n.removeAttribute('aria-describedby'));}
  function showTip(b){if(!tooltip||!b)return;tooltip.textContent=b.dataset.piTooltip;tooltip.hidden=false;b.setAttribute('aria-describedby','pi-tooltip');const r=b.getBoundingClientRect(),t=tooltip.getBoundingClientRect();tooltip.style.left=Math.max(8,Math.min(r.left,innerWidth-t.width-8))+'px';tooltip.style.top=(r.bottom+t.height+10<innerHeight?r.bottom+6:Math.max(8,r.top-t.height-6))+'px';}
  function mark(k){dialog.querySelectorAll('[data-pi-wrap]').forEach(n=>{if(n.dataset.piWrap!==k)return;n.classList.toggle('pi-dirty',own(changes,k));n.querySelector('[data-pi-state]').textContent=own(changes,k)?changes[k]===null?'원천값 복원':'저장 전':model.fields[k]?.manual?'입력값':'';});}
  function setInput(k,v){dialog.querySelectorAll('[data-pi-input]').forEach(n=>{if(n.dataset.piInput===k)n.value=v??'';});mark(k);}
  function scope(r){const invalid=Array.from(dialog.querySelectorAll('#pi-annual input')).find(n=>!n.checkValidity());if(invalid){invalid.reportValidity();return;}hideTip();selectedScope=r;dialog.querySelector('#pi-annual-scope').textContent=r;dialog.querySelector('#pi-annual').innerHTML=annual();dialog.querySelectorAll('[data-pi-region-row]').forEach(n=>{const selected=n.dataset.piRegionRow===r;n.classList.toggle('selected',selected);n.querySelector('button').setAttribute('aria-pressed',String(selected));});Object.keys(changes).forEach(mark);}
  function popup(title,html){const d=document.createElement('dialog');d.className='pi-popup';d.innerHTML='<header><h3>'+esc(title)+'</h3><button type="button" aria-label="닫기" data-close>×</button></header>'+html;document.body.append(d);d.querySelector('[data-close]').onclick=()=>d.close();d.addEventListener('close',()=>d.remove());d.showModal();return d;}
  const link=u=>u&&safeUrl(u)!=='#'?'<a href="'+esc(safeUrl(u))+'" target="_blank" rel="noopener">출처 원문 ↗</a><small class="pi-source-url">'+esc(u)+'</small>':'';
  function evidence(k){
    let html='';
    if(k==='parent')html='<p>'+esc(model.parent_policy_name)+' · '+esc(model.parent_policy_id)+'</p><p>'+esc(model.parent_basis)+'</p>'+link(model.parent_policy_evidence_url);
    else if(k==='id')html='<p>프로그램 등록 시 시스템이 부여한 식별자입니다.</p><code>'+esc(model.policy_id)+'</code>';
    else if(k.startsWith('actual:')){const [,r,y]=k.split(':');const data=model.actual[r];html='<p>'+esc(data.basis)+'</p>'+data.evidence.filter(e=>!y||e.date.startsWith(y)).map(e=>'<article><b>'+esc(e.name)+'</b><p>동일 단계 확인 '+esc(e.date)+' · '+fmt(e.value)+' · 프로그램 연결 '+esc(e.mapping_status)+'</p>'+link(e.evidence_url)+'</article>').join('');}
    else if(k==='programs'||k.startsWith('program:')){const id=k.slice(8);html='<p>현재 저장된 프로그램–사업 연결입니다. 사용자 변경 근거를 먼저, 기존 매칭 근거를 이어서 표시합니다.</p>'+model.programs.filter(p=>k==='programs'||p.id===id).map(p=>'<article><b>'+esc(p.name)+'</b><p>'+esc(p.id)+' → '+esc(p.policy_id)+' · '+esc(p.status)+'</p>'+(p.evidence||[]).map(e=>'<article><b>'+esc(e.origin==='MANUAL'?'사용자 입력 · 변경 기록':'기존 수집·매칭 근거')+'</b><p>프로그램 ID: '+esc(e.value)+' · '+esc(e.status||'')+'</p>'+(e.origin==='MANUAL'?'<p>변경자: '+esc(e.actor)+'<br>변경일: '+esc(timeText(e.changed_at))+'</p>':'')+'<p>'+esc(e.reason||e.basis||'근거 미확보')+'</p>'+link(e.evidence_url)+'</article>').join('')+'</article>').join('');}
    else if(k==='progress'||k.startsWith('stage:')){const stage=k.slice(6),order=['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],included=order.slice(Math.max(0,order.indexOf(stage)));html='<p>기준일 '+esc(model.as_of_date)+' · 정책은 전체 목표 '+fmt(model.fields.target_units.value)+'입니다. 각 단계는 해당 단계와 이후 단계의 누적 도달량입니다. 단계 간 수치를 합산하지 않습니다. 후속 단계에 따른 포함은 조회 계산이며 원천 인허가·착공 실적을 생성하지 않습니다.</p>'+model.progress_evidence.filter(c=>k==='progress'||stage==='POLICY'||included.some(s=>c.parts[s]>0)).map(c=>'<article><b>'+esc(c.name)+'</b><p>'+esc(Object.entries(c.parts).map(([s,v])=>(model.stages[s]||'단계 미확인')+' 현재 '+housing(v)).join(' / '))+'</p>'+c.events.filter(e=>e.event_date<=model.as_of_date&&e.status!=='DELAYED').map(e=>'<p>'+esc(e.event_date)+' · '+esc(model.stages[e.stage]||e.stage)+' · '+esc(e.basis||e.origin||'수집 근거')+' '+link(e.evidence_url)+'</p>').join('')+link(c.evidence_url)+'</article>').join('');}
    else html=(model.fields[k]?.evidence||[source(k)]).map(e=>'<article><b>'+esc(e.origin==='MANUAL'?'사용자 입력값 · 우선 적용':'수집된 근거')+'</b><p class="pi-source-value">'+esc(e.value==null?'미확보 / 미배분':typeof e.value==='number'?fmt(e.value):e.value)+'</p>'+(e.origin==='MANUAL'?'<p>변경자: '+esc(e.actor)+' (담당자 입력 이름 · 관리자 권한 저장)</p><p>변경일: '+esc(timeText(e.changed_at))+'</p><p>사유: '+esc(e.reason)+'</p>'+(e.input_basis?'<p>'+esc(e.inferred?'추정 입력 · ':'판단 근거 · ')+esc(e.input_basis)+'</p>':''):'<blockquote>'+esc(e.excerpt||e.basis)+'</blockquote><p class="pi-citation">'+esc(cite(e))+(e.printed_page&&e.pdf_page?' · PDF '+e.pdf_page+'쪽':'')+(e.excerpt_type==='TABLE_VALUE'?' · 표의 값·단위 환산':'')+'</p>')+(e.calculation?'<p>사업 합계 채택 근거: '+housing(e.calculation.units)+' · '+esc(e.calculation.period_start)+'~'+esc(e.calculation.period_end)+' · 집계 사업 '+esc(e.calculation.project_ids.join(', '))+'</p>':'')+link(e.evidence_url?(e.pdf_page?e.evidence_url.split('#')[0]+'#page='+e.pdf_page:e.evidence_url):null)+'</article>').join('');
    popup('근거 조회 · '+label(k),html||'<p>확인된 근거가 없습니다.</p>');
  }
  function edit(k){
    if(!state.admin||busy)return;
    if(k==='name'){renameProgram();return;}
    if(k==='programs'){dialog.querySelector('[data-pi-program]')?.focus();return;}
    if(k.startsWith('program:')){Array.from(dialog.querySelectorAll('[data-pi-program]')).find(n=>n.dataset.piProgram===k.slice(8))?.focus();return;}
    const n=Array.from(dialog.querySelectorAll('[data-pi-input]')).find(n=>n.dataset.piInput===k);n?.focus();if(n?.type!=='date'&&n?.type!=='number')n?.select?.();
  }
  function history(){popup('프로그램정보·사업 연결 변경 이력',model.history.length?model.history.map(h=>'<article><b>'+esc(h.actor)+' · '+esc(timeText(h.recorded_at))+'</b><p>'+esc(h.reason)+'</p>'+h.changes.map(c=>'<p>'+esc(label(c.field))+' : '+esc(JSON.stringify(c.before?.value??'원천값'))+' → '+esc(JSON.stringify(c.after?.value??'원천값'))+'</p>').join('')+(h.program_changes||[]).map(c=>'<p>사업 '+esc(c.name)+' : '+esc(c.before.program_id)+' → '+esc(c.after.program_id)+'</p>').join('')+'</article>').join(''):'<p>아직 사용자 변경 이력이 없습니다.</p>');}
  function status(s){dialog.querySelector('#pi-status').textContent=s;}
  async function save(){
    if(busy)return;
    const actor=dialog.querySelector('#pi-actor').value.trim(),reason=dialog.querySelector('#pi-reason').value.trim();
    if(!Object.keys(changes).length&&!Object.keys(programChanges).length){status('변경한 항목이 없습니다.');return;}
    if(!actor||!reason){status('변경자와 변경 사유를 입력하세요.');dialog.querySelector(!actor?'#pi-actor':'#pi-reason').focus();return;}
    let committed=false;busy=true;dialog.querySelector('.pi-body').inert=true;dialog.querySelector('[data-pi-save]').disabled=true;status('프로그램정보와 사업 연결을 저장하고 있습니다…');
    try{await request('/admin/program-information/'+encodeURIComponent(programId),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision_no:model.revision_no,mapping_revision_no:model.mapping_revision_no,changes,program_changes:programChanges,actor,reason})});committed=true;changes={};programChanges={};status('저장했습니다. 최신 정보를 조회하고 있습니다…');model=await request('/program-information/'+encodeURIComponent(programId));const selectedRow=programRows.find(p=>p.id===programId);if(selectedRow)selectedRow.name=model.fields.name.value;render();status('저장했습니다. 프로그램정보와 사업 연결이 반영되었습니다.');const list=await request('/programs');Policy907.setPrograms(list.items);const option=document.querySelector('#report-program-select option[value="'+programId+'"]');if(option)option.textContent=model.fields.name.value;await Policy907.show(true);}
    catch(e){status((committed?'저장은 완료됐지만 화면 갱신에 실패했습니다. 창을 다시 열어 확인하세요. ':'')+e.message);}
    finally{busy=false;dialog.querySelector('.pi-body').inert=false;dialog.querySelector('[data-pi-save]').disabled=false;}
  }
  function updateProgram(p,selected,batch=false){
    if(!batch&&selected&&p.policy_id!==model.policy_id&&p.policy_id!=='UNASSIGNED'&&p.status!=='RELEASED'&&!confirm('이 사업을 '+p.policy_id+'에서 현재 프로그램으로 옮깁니다. 계속할까요?'))return false;
    if(selected===p.selected)delete programChanges[p.id];else programChanges[p.id]={selected,revision_no:p.revision_no};
    const input=Array.from(dialog.querySelectorAll('[data-pi-program]')).find(n=>n.dataset.piProgram===p.id);
    if(input){input.checked=selected;input.closest('.pi-program').querySelector('[data-pi-program-state]').textContent=own(programChanges,p.id)?'사용자 변경 · 저장 전':p.status==='REVIEW'?'담당자 확인 필요':p.status==='CONFIRMED'?'연결 확정':'연결 해제';}
    if(!batch)updateCount();return true;
  }
  function close(){if(busy)return;if((Object.keys(changes).length||Object.keys(programChanges).length)&&!confirm('저장하지 않은 변경 내용을 닫을까요?'))return;dialog.close();}
  async function open(id){
    if(!state.admin)return;
    if(document.querySelector('#program-information-dialog'))return;
    programId=id;
    dialog=document.createElement('dialog');dialog.id='program-information-dialog';dialog.className='pi-dialog';dialog.setAttribute('aria-labelledby','pi-title');dialog.innerHTML='<h2 id="pi-title">프로그램정보</h2><p>불러오는 중…</p>';document.body.append(dialog);dialog.showModal();changes={};programChanges={};selectedScope='전체';
    dialog.addEventListener('cancel',e=>{e.preventDefault();close();});dialog.addEventListener('close',()=>dialog.remove());
    dialog.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;hideTip();if(b.hasAttribute('data-pi-evidence')){e.preventDefault();evidence(b.dataset.piEvidence);}else if(b.hasAttribute('data-pi-edit'))edit(b.dataset.piEdit);else if(b.hasAttribute('data-pi-reset')){const k=b.dataset.piReset;changes[k]=null;setInput(k,source(k).value);if(k.startsWith('period_'))refreshYears();refreshManagement();status('원천값으로 되돌린 뒤 저장합니다.');}else if(b.hasAttribute('data-pgi-management-detail'))managementDetail();else if(b.hasAttribute('data-pgi-adopt'))adoptAggregate();else if(b.hasAttribute('data-pgi-apply')){if(dialog.querySelector('#pi-form').reportValidity())save();}else if(b.hasAttribute('data-pi-add-year'))addYear();else if(b.hasAttribute('data-pi-scope'))scope(b.dataset.piScope);else if(b.hasAttribute('data-pi-history'))history();else if(b.hasAttribute('data-pi-close'))close();});
    dialog.addEventListener('input',e=>{
      if(e.target.hasAttribute('data-pi-program-search')){const q=e.target.value.toLowerCase();dialog.querySelectorAll('[data-pi-program-row]').forEach(n=>n.hidden=!(n.textContent+' '+n.closest('[data-pgi-group]').dataset.pgiGroup).toLowerCase().includes(q));groupState();}
      const k=e.target.dataset.piInput;if(!k)return;
      if(k==='target_mode'&&e.target.value==='PROJECT_SUM'){adoptAggregate();setInput(k,value(k));return;}
      const raw=e.target.value,numeric=e.target.type==='number',v=raw===''?null:numeric?Number(raw):raw;
      if(v===model.fields[k]?.value)delete changes[k];else changes[k]=v;
      mark(k);if(k==='target_units'&&value('target_mode')==='PROJECT_SUM'){changes.target_mode='INDEPENDENT';setInput('target_mode','INDEPENDENT');}if(k.startsWith('period_'))refreshYears();refreshManagement();status('입력한 변경 내용은 저장 후 반영됩니다.');
    });
    dialog.addEventListener('change',e=>{if(e.target.hasAttribute('data-pgi-policy')){switchSelection(e.target.value,null);return;}if(e.target.hasAttribute('data-pgi-program-select')){switchSelection(selectorPolicyId,e.target.value);return;}if(e.target.hasAttribute('data-pgi-all')){selectBatch(null,e.target.checked);return;}if(e.target.hasAttribute('data-pgi-region')){selectBatch(e.target.dataset.pgiRegion,e.target.checked);return;}const id=e.target.dataset.piProgram;if(!id)return;const p=model.programs.find(p=>p.id===id);if(!updateProgram(p,e.target.checked))e.target.checked=own(programChanges,id)?programChanges[id].selected:p.selected;});
    dialog.addEventListener('pointerover',e=>{const b=e.target.closest('[data-pi-tooltip]');if(b&&!b.contains(e.relatedTarget))showTip(b);});
    dialog.addEventListener('pointerout',e=>{const b=e.target.closest('[data-pi-tooltip]');if(b&&!b.contains(e.relatedTarget))hideTip();});
    dialog.addEventListener('focusin',e=>{if(e.target.hasAttribute('data-pi-tooltip'))showTip(e.target);});
    dialog.addEventListener('focusout',hideTip);dialog.addEventListener('scroll',hideTip,true);
    dialog.addEventListener('keydown',e=>{if(e.key==='Escape'&&tooltip&&!tooltip.hidden){e.preventDefault();e.stopPropagation();hideTip();}});
    try{const [loaded,policies,programs]=await Promise.all([request('/program-information/'+encodeURIComponent(programId)),request('/policies'),request('/programs')]);const selected=loaded;model=selected;programId=model.program_id||model.policy_id;policyRows=policies.items.filter(p=>p.monitor_kind==='POLICY');if(!policyRows.some(p=>p.policy_id===model.parent_policy_id))policyRows.push({policy_id:model.parent_policy_id,name:model.parent_policy_name});selectorPolicyId=model.parent_policy_id;programRows=programs.items;render();}catch(e){dialog.innerHTML='<h2 id="pi-title">프로그램정보</h2><p>'+esc(e.message)+'</p><button data-pi-close>닫기</button>';}
  }
  return {open};
})();
