'use strict';
const HousingMap = (() => {
  const stages={PLANNING:'계획',APPROVAL:'인허가',CONSTRUCTION:'착공',SUPPLY:'공급',COMPLETION:'준공',MOVE_IN:'입주'};
  const icons={PLANNING:'▤',APPROVAL:'✓',CONSTRUCTION:'⌁',SUPPLY:'▥',COMPLETION:'◇',MOVE_IN:'⌂'};
  let payload, roadmap, supply, selectedId, selectedDistrict, year, mode='current', timer, userSelected=false, pickerSignature='';
  const hasLocation=row=>['LH_PUBLIC_BLOCK_LABEL_POINT','BLOCK_BOUNDARY','OFFICIAL_ADDRESS_POINT','APPROXIMATE_ADDRESS','APPROXIMATE_AREA'].includes(row?.coordinate_basis)&&Number.isFinite(row.latitude)&&Number.isFinite(row.longitude);
  const events=row=>row.annual.find(a=>a.year===year)?.events||[];
  const currentStage=row=>({CANDIDATE:'PLANNING',PLANNED_SUPPLY:'SUPPLY',COMPLETED:'COMPLETION'}[row.stage]||row.stage);
  function rows(){return MapSupply.filter(supply.items);}
  function selectedBlock(){return supply?.blocks.find(row=>row.project_ids.includes(selectedId)&&row.district_name===selectedDistrict);}
  function update3DBlockPicker(){
    const select=$('map-3d-block-picker');if(!select||!supply)return;
    const visible=new Set(rows().map(row=>row.id));
    const blocks=supply.blocks.filter(row=>row.project_ids.some(id=>visible.has(id)))
      .sort((a,b)=>(a.district_name+' '+a.block).localeCompare(b.district_name+' '+b.block,'ko',{numeric:true}));
    const signature=blocks.map(row=>row.id+':'+row.coordinate_basis).join('|');
    if(signature!==pickerSignature){select.innerHTML='<option value="">블록으로 이동</option>'+blocks.map(row=>`<option value="${esc(row.id)}">${esc(row.district_name)} · ${esc(row.block)}${hasLocation(row)?(row.coordinate_basis.startsWith('APPROXIMATE')?' · 근사 위치':''):' · 위치 미연계'}</option>`).join('');pickerSignature=signature;}
    select.value=selectedBlock()?.id||'';
  }
  function init(){
    if(state.view!=='overview'||!supply)return;
    MapThreeD.start(supply,new Set(rows().map(row=>row.id)),selectedId,selectedDistrict,choose,()=>draw(true));
  }
  function fit(){MapThreeD.setLevel(MapThreeD.view()?.level||'region');}
  function districtRows(district) {
    const linked=new Set(district.project_ids);
    return rows().filter(row=>linked.has(row.id));
  }
  function stageFor(group) {
    const found=mode==='current'?group.map(currentStage):group.flatMap(row=>events(row).map(event=>event.stage));
    const distinct=[...new Set(found.filter(stage=>stages[stage]))];
    return distinct.length===1?distinct[0]:distinct.length?'MIXED':'UNKNOWN';
  }
  function choose(id,districtName) {
    userSelected=true;selectedId=id;selectedDistrict=districtName||payload.districts.find(d=>d.project_ids.includes(id))?.name||null;
    draw();init();
    const block=selectedBlock();
    if(hasLocation(block))MapThreeD.focus(block);
    else {const district=payload.districts.find(row=>row.name===selectedDistrict);if(district)MapThreeD.focus(district,13.5);}
  }
  function selectDistrict(district) {
    const group=districtRows(district);
    const preferred=group.find(row=>events(row).length)||group[0];
    if(preferred)choose(preferred.id,district.name);
  }
  function draw(geographyOnly=false) {
    if(state.view!=='overview'||!payload || !roadmap)return;
    const filtered=rows(), ids=new Set(filtered.map(row=>row.id));
    if(!ids.has(selectedId)) {
      const counts=new Map();
      for(const block of supply.blocks.filter(row=>hasLocation(row)&&row.project_ids.some(id=>ids.has(id))))counts.set(block.district_name,(counts.get(block.district_name)||0)+1);
      const districtName=[...counts].filter(([name])=>payload.districts.some(row=>row.name===name)).sort((a,b)=>b[1]-a[1])[0]?.[0];
      const firstBlock=supply.blocks.find(row=>row.district_name===districtName&&hasLocation(row)&&row.project_ids.some(id=>ids.has(id)));
      const first=payload.districts.find(row=>row.name===districtName)||payload.districts.find(row=>row.project_ids.some(id=>ids.has(id)));
      const group=first?districtRows(first):filtered;
      selectedId=firstBlock?.project_ids.find(id=>ids.has(id))||(group.find(row=>events(row).length)||group[0])?.id;
      selectedDistrict=first?.name||null;
    }
    const viewport=MapThreeD.view();
    if(viewport?.level==='block'&&!userSelected){
      const near=supply.blocks.filter(block=>hasLocation(block)&&block.project_ids.some(id=>ids.has(id)))
        .sort((a,b)=>{const distance=point=>((point.longitude-viewport.center.lng)*Math.cos(viewport.center.lat*Math.PI/180))**2+(point.latitude-viewport.center.lat)**2;return distance(a)-distance(b);})[0];
      if(near){selectedId=near.project_ids.find(id=>ids.has(id));selectedDistrict=near.district_name;}
    }
    MapThreeD.render(supply,ids,selectedId,selectedDistrict,choose);
    if(!geographyOnly){MapSupply.render(supply);renderPanels(filtered);}
    else renderBlockList(filtered);
    MapMonitor.panel(supply,{...(MapThreeD.view()||{}),explicitBlockId:userSelected?selectedBlock()?.id:null});
    const located=new Set(payload.districts.flatMap(d=>d.project_ids.filter(id=>ids.has(id))));
    const municipal=supply.municipalities.map(SupplyBars.scoped).filter(area=>area&&area.project_count);
    const assigned=new Set(supply.municipalities.flatMap(area=>area.project_ids.filter(id=>ids.has(id))));
    $('map-caption').innerHTML=`<b>${mode==='forecast'?year+'년 추진목표':supply.analysis_year+'년 자료 현황'}</b><span>시군구 ${num(municipal.length)}곳 · 지역 귀속 ${num(assigned.size)} / ${num(filtered.length)}건 · 지구 위치 연결 ${num(located.size)}건${supply.analysis_year<supply.current_year?' · 현재 확보 경계 참고':''}</span>`;
    $('map-header-date').textContent='자료 '+supply.reference_date+' · 수집 조회 '+supply.knowledge_date;
    document.querySelector('.map-color-legend').innerHTML=Object.entries(stages).map(([stage,label])=>`<span class="map-stage-dot ${stage.toLowerCase()}"></span>${mode==='current'?({CONSTRUCTION:'공사',SUPPLY:'공급계획',COMPLETION:'공사완료'}[stage]||label):label}`).join('')+'<span class="map-stage-dot mixed"></span>여러 단계 <span class="map-stage-dot unknown"></span>미등록';
    document.querySelectorAll('[data-map-mode]').forEach(button=>{button.classList.toggle('selected',button.dataset.mapMode===mode);button.setAttribute('aria-pressed',String(button.dataset.mapMode===mode));});
    update3DBlockPicker();

  }
  function eventMarkup(event) {
    return `<div class="map-event ${event.origin==='MANUAL'?'manual':''}"><span class="map-stage-dot ${event.stage.toLowerCase()}"></span><div><b>${esc(event.label)}</b><small>${event.origin==='MANUAL'?'관리자 목표':'원천 예정'} · ${esc(event.month||event.year+'년')}${event.units!=null?' · '+num(event.units)+'호':''}</small><small>${esc(event.basis)}</small></div></div>`;
  }
  function renderBlockList(filtered) {
    const list=$('map-block-list'),methodBlock=$('map-method-block');
    methodBlock.hidden=true;methodBlock.textContent='';
    const level=MapMonitor.levelAt(MapThreeD.zoom()||14);
    list.hidden=level==='region'||level==='municipality';
    if(list.hidden)return;
    const visibleIds=new Set(filtered.map(row=>row.id));
    const blocks=supply.blocks.filter(block=>block.district_name===selectedDistrict&&block.project_ids.some(id=>visibleIds.has(id)))
      .map(SupplyBars.scoped).filter(row=>row&&row.project_count)
      .sort((a,b)=>a.block.localeCompare(b.block,'en',{numeric:true}));
    if(!blocks.length){list.innerHTML='<h3>지구별 블록</h3><p class="map-block-empty">지구를 선택하면 연결된 블록을 각각 볼 수 있습니다.</p>';return;}
    const labelled=blocks.filter(block=>['BLOCK_BOUNDARY','OFFICIAL_ADDRESS_POINT','LH_PUBLIC_BLOCK_LABEL_POINT','APPROXIMATE_ADDRESS','APPROXIMATE_AREA'].includes(block.coordinate_basis)).length;
    const locationFor=block=>block.coordinate_basis==='BLOCK_BOUNDARY'?'블록 경계 확인':block.coordinate_basis==='OFFICIAL_ADDRESS_POINT'?'공식 주소 위치':block.coordinate_basis==='LH_PUBLIC_BLOCK_LABEL_POINT'?'LH 블록 라벨 위치':block.coordinate_basis?.startsWith('APPROXIMATE')?(block.location_label||'근사 위치'):'블록 위치 미연계';
    methodBlock.textContent=`각 블록의 공급량과 일정은 별도 항목입니다. 블록별 위치 근거 ${labelled}/${blocks.length}개 · ${blocks.map(block=>block.block+' '+locationFor(block)).join(' · ')}. LH 라벨점은 경계나 건물 위치가 아닙니다. 미연계 블록은 지구 대표 위치에서 목록으로만 표시합니다.`;
    methodBlock.hidden=false;
    list.innerHTML=`<h3>${esc(selectedDistrict)} · ${blocks.length}개 블록</h3>${blocks.map(block=>{
      const capacity=block.target_units,observed=block.progress.observed_units,goal=block.progress.cumulative_goal_units;
      const known=capacity!=null&&capacity>0;
      const fillHeight=known&&observed!=null?Math.round(Math.min(1,Math.max(0,observed/capacity))*32):0;
      const goalY=known&&goal!=null?34-Math.round(Math.min(1,Math.max(0,goal/capacity))*32):null;
      const id=block.project_ids.find(value=>visibleIds.has(value));
      const active=block.project_ids.includes(selectedId);
      const future=block.projection.future.slice(0,3).filter(row=>row.increment_units!=null&&row.increment_units>0).map(row=>'+'+row.offset+'년 '+num(row.increment_units)+'호').join(' · ');
      return `<button class="map-block-choice${active?' active':''}" data-map-block-id="${esc(block.id)}" type="button" aria-current="${active?'true':'false'}"><svg class="map-block-mini${!known?' unknown':''}" viewBox="0 0 18 36" aria-hidden="true"><rect x="3" y="1" width="12" height="34" rx="2" fill="#e7eef8" stroke="#a5b8d4"/><rect x="4" y="${34-fillHeight}" width="10" height="${fillHeight}" fill="#1665ee"/>${goalY==null?'':`<path d="M1 ${goalY}h16" stroke="#db8e21" stroke-width="2"/>`}</svg><span><strong>${esc(block.block)} · ${esc(block.name)}</strong><small>${esc(BlockMonitor.status(block.progress).label)}</small><small>올해까지 목표 ${goal==null?'미확보':num(goal)+'호'} · 현재 확인 ${observed==null?'미확보':num(observed)+'호'}</small>${future?`<small>예정 증가 ${esc(future)}</small>`:''}</span><span class="map-block-quantity">${capacity==null?'미확보':num(capacity)+'호'}</span></button>`;
    }).join('')}`;
  }
  function renderPanels(filtered) {
    MapSupply.panels();
    renderBlockList(filtered);
    const row=filtered.find(item=>item.id===selectedId);
    if(!row) {$('map-project-detail').innerHTML='<h3>연결된 사업 자료 없음</h3><p>이 연도의 정책 발표·공고 자료는 위 이력에서 확인하세요. 사업 위치가 확보되면 지도에 표출됩니다.</p>';}
    else {
      const district=payload.districts.find(item=>item.name===selectedDistrict);
      const group=district?districtRows(district):[];
      const annual=events(row);
      $('map-project-detail').innerHTML=`<div class="map-detail-title"><span class="map-stage-dot ${stageFor([row]).toLowerCase()}"></span><h3>${esc(row.name)}</h3></div>${group.length>1?`<label class="map-business-select">지구 내 원천 사업 <select id="map-project-select" aria-label="선택 지구의 사업">${group.map(item=>`<option value="${esc(item.id)}" ${item.id===row.id?'selected':''}>${esc(item.name)}</option>`).join('')}</select></label>`:''}<dl><dt>${row.historical_report?'당시 보고 상태':'원천 상태'}</dt><dd>${esc(row.stage_label)}</dd><dt>원천 기준일</dt><dd>${esc(baseText(row))}</dd><dt>계획 물량</dt><dd>${row.planned_units!=null?num(row.planned_units)+'호':'개별 물량 미입수'}</dd><dt>실제 공정률</dt><dd>${row.progress_pct!=null?num(row.progress_pct)+'%'+(row.progress_date?' · '+esc(row.progress_date_precision==='MONTH'?row.progress_date.slice(0,7):row.progress_date):''):'미입수 · 0%나 미착수 확인 아님'}</dd></dl>${district?MapSupply.districtPanel(district):''}${annual.length?`<h4>${year}년 추진목표</h4>${annual.map(eventMarkup).join('')}`:''}${row.past_due_count?'<p class="map-schedule-warning">! 지난 예정일의 실제 이행 확인 필요</p>':''}<p class="map-coordinate-note">${district?'지구 공동주택용지 대표 위치 · 블록 연결 검토':'위치 근거 미연결 · 지도 표식 없음'}${row.historical_report?' · 마지막 보고 기준 상태, 이후 이행 미확인':''}</p><div class="map-detail-actions"><button type="button" data-view="project-collection">단계별 수집현황 보기</button>${row.historical_report?`<a href="${esc(safeUrl(row.evidence_url))}" target="_blank" rel="noopener">당시 보고서 원문 ↗</a>`:`<button data-project="${esc(row.id)}">원천·변경이력 ↗</button>`}${row.master_id?`<button data-target-project="${esc(row.master_id)}">${row.historical_report?'현재 사업 목표':state.admin?'목표 관리':'연도별 목표'} ↗</button>`:''}</div>`;
      $('map-project-select')?.addEventListener('change',event=>choose(event.target.value,selectedDistrict));
      if(row.notice_evidence){
        const notice=row.notice_evidence;
        $('map-project-detail').insertAdjacentHTML('beforeend',`<div class="map-notice-evidence"><b>모집공고 확인 ${num(notice.units)}호</b><p>${esc(notice.source_date)} · ${esc(notice.name)} · 사업 연결 검토</p><button class="text-button" data-sample="${esc(notice.id)}">모집공고 근거 보기 ↗</button></div>`);
      }
      const block=SupplyBars.scoped(supply.blocks.find(block=>block.project_ids.includes(row.id)));
      if(block)$('map-project-detail').insertAdjacentHTML('beforeend',`<div class="map-block-progress"><h4>선택 블록 · ${esc(block.block)} · ${esc(supply.measure_label)}</h4>${SupplyBars.chart(block,true)}${BlockMonitor.stageDetails(block)}<p>${esc(block.progress.goal_basis)}<br>확인 비율 대상 ${num(block.progress.observed_projects)} / ${num(block.progress.capacity_projects)}건 · 원천 연결 검토</p></div>`);
    }
    const located=new Set(payload.districts.flatMap(district=>district.project_ids));
    const pending=filtered.filter(row=>!located.has(row.id));
    $('map-pending-summary').textContent='위치 미연결 사업 '+num(pending.length)+'건';
    $('map-pending-list').innerHTML=pending.length?pending.map(row=>`<button data-map-project="${esc(row.id)}"><span>${esc(row.name)}</span><small>${esc(row.region)} · ${esc(row.stage_label)}</small></button>`).join(''):'<p>조회한 모든 후보에 지구 대표 위치가 연결되어 있습니다.</p>';
  }
  function stop() {clearInterval(timer);timer=null;}
  function start() {
    $('map-3d-block-picker').addEventListener('change',event=>{const block=supply?.blocks.find(row=>row.id===event.target.value);const visible=new Set(rows().map(row=>row.id));const id=block?.project_ids.find(value=>visible.has(value));if(id)choose(id,block.district_name);});
    const panelBody=document.querySelector('.housing-map-body'),panel=document.querySelector('.map-side-panel'),locationPanel=document.querySelector('.map-location-panel');
    if(localStorage.getItem('home-map-panel-collapsed')==='true')panelBody.classList.add('panel-collapsed');
    if(localStorage.getItem('home-map-location-collapsed')==='true')panelBody.classList.add('location-collapsed');
    const syncPanels=()=>{const mobile=window.matchMedia('(max-width:800px)').matches;for(const [kind,node,collapsed,id] of [['progress',panel,'panel-collapsed','map-panel-toggle'],['location',locationPanel,'location-collapsed','map-location-toggle']]){const opened=mobile?node.classList.contains('panel-open'):!panelBody.classList.contains(collapsed);$(id).setAttribute('aria-expanded',String(opened));$(id).textContent=opened?'접기':'펼치기';document.querySelector('[data-map-panel="'+kind+'"]').setAttribute('aria-expanded',String(opened));}};
    const togglePanel=kind=>{const target=kind==='progress'?panel:locationPanel,other=kind==='progress'?locationPanel:panel;if(window.matchMedia('(max-width:800px)').matches){const was=target.classList.contains('panel-open');other.classList.remove('panel-open');target.classList.toggle('panel-open',!was);}else{const cls=kind==='progress'?'panel-collapsed':'location-collapsed';panelBody.classList.toggle(cls);localStorage.setItem(kind==='progress'?'home-map-panel-collapsed':'home-map-location-collapsed',String(panelBody.classList.contains(cls)));setTimeout(()=>MapThreeD.resize(),220);}syncPanels();};
    $('map-panel-toggle').addEventListener('click',()=>togglePanel('progress'));
    $('map-location-toggle').addEventListener('click',()=>togglePanel('location'));
    document.querySelectorAll('[data-map-panel]').forEach(b=>b.addEventListener('click',()=>togglePanel(b.dataset.mapPanel)));
    locationPanel.addEventListener('click',event=>{const button=event.target.closest('[data-location-jump]');if(!button)return;const selectors={employment:'[data-demographic=employment], .area-context-rate, .area-context-grid',household:'[data-demographic="household"]',age:'[data-demographic="age"]',unsold:'.unsold-context',infrastructure:'#map-infrastructure-panel'};const target=locationPanel.querySelector(selectors[button.dataset.locationJump]);if(!target)return;if(target.tagName==='DETAILS')target.open=true;locationPanel.scrollTo({top:locationPanel.scrollTop+target.getBoundingClientRect().top-locationPanel.getBoundingClientRect().top-125,behavior:'smooth'});});
    window.addEventListener('resize',syncPanels);syncPanels();
    for(const id of ['map-land-layer','map-observation-layer'])$(id).addEventListener('change',draw);
    MapSupply.start(draw,fit);
    MapMonitor.start(setLevel);
    document.addEventListener('click',event=>{
      const camera=event.target.closest('[data-map-3d-camera]');if(camera)MapThreeD.camera(camera.getAttribute('data-map-3d-camera'));
      const blockChoice=event.target.closest('[data-map-block-id]');if(blockChoice){const block=supply.blocks.find(row=>row.id===blockChoice.dataset.mapBlockId);const id=block?.project_ids.find(value=>rows().some(row=>row.id===value));if(id)choose(id,block.district_name);}
      const pending=event.target.closest('[data-map-project]');if(pending){choose(pending.dataset.mapProject);if(selectedDistrict)setLevel('block');}
      const region=event.target.closest('[data-map-region]');if(region){$('region').value=region.dataset.mapRegion;$('region').dispatchEvent(new Event('change'));}
    });
  }
  function render(value,annual,dashboard) {
    supply=dashboard;payload={...value,districts:dashboard.districts};roadmap=annual;pickerSignature='';
    MapSupply.set(dashboard);
    if(year==null)year=dashboard.analysis_year;
    year=Math.min(Math.max(year,dashboard.start_year),annual.current_year+annual.horizon);
    draw();init();requestAnimationFrame(()=>MapThreeD.resize());
  }
  function visible(){requestAnimationFrame(()=>{if(state.view!=='overview')return;init();MapThreeD.resize();});}
  function hidden(){MapThreeD.exit();stop();}
  function reset(){MapThreeD.exit();MapSupply.reset();year=null;mode='current';userSelected=false;stop();}
  function setLevel(level){MapThreeD.setLevel(level);draw(true);}
  return {render,start,visible,hidden,reset,setLevel,query:()=>MapSupply.query()};
})();
