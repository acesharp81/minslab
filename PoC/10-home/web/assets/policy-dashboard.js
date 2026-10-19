'use strict';
const PolicyDashboard=(()=>{
  let payload,selected='POL_2025_0907',measure='COMPLETION';
  const collapsed=new Set();
  const units=n=>n==null?'':num(n)+'호';
  const labels={SUPPLY:'모집·공급 예정',COMPLETION:'준공 예정',CONSTRUCTION:'착공 예정'};
  const stages={PLANNING:'계획',APPROVAL:'인허가',CONSTRUCTION:'착공',SUPPLY:'공급',COMPLETION:'준공',MOVE_IN:'입주'};
  const blocks=row=>(row.timeline?.regions||[]).flatMap(r=>r.cities.flatMap(c=>c.blocks));
  function render(data){
    data={...data,items:data.items.filter(r=>r.id==='POL_2025_0907')};payload=data;if(!data.items.some(r=>r.id===selected))selected=data.items[0]?.id;
    $('policy-monitor-date').textContent=data.reference_date+' 자료 기준';
    $('policy-monitor-cards').innerHTML=`<label class="policy-picker-label">정책 선택 <select id="policy-detail-select" aria-label="진행현황 정책 선택">${data.items.map(r=>`<option value="${esc(r.id)}" ${r.id===selected?'selected':''}>${esc(r.name)}</option>`).join('')}</select></label><div class="policy-explorer-tabs" role="tablist" aria-label="관리 정책">${data.items.map(r=>`<button class="policy-snapshot ${r.id===selected?'selected':''}" id="policy-tab-${esc(r.id)}" role="tab" aria-selected="${r.id===selected}" aria-controls="policy-monitor-detail" data-monitor-detail="${esc(r.id)}"><small>${r.kind==='PROGRAMME'?'프로그램':r.kind==='UNMAPPED'?'미연계':'공급대책'}</small><b>${esc(r.name)}</b></button>`).join('')}</div>`;
    detail();
  }
  function overview(row){
    const o=row.overview||{},list=blocks(row),reports=list.filter(b=>b.actuals.length);
    return `<section id="policy-overview" class="panel policy-overview"><div class="panel-head"><div><p class="section-kicker">POLICY OVERVIEW</p><h2>${esc(row.name)}</h2></div><button class="text-button" data-policy-workbench="${esc(row.id)}">사업 연결 조정 ↗</button></div><div class="policy-overview-facts">${[['목적',o.purpose],['위치',o.location],['기간',o.period]].filter(([,v])=>v).map(([k,v])=>`<div><span>${k}</span><p>${esc(v)}</p></div>`).join('')}</div><div class="policy-delivery-totals">${row.announced_target_units!=null?`<div><span>공식 발표 목표</span><strong>${units(row.announced_target_units)}</strong><small>${esc(row.announced_target_scope)} · ${esc(row.announced_target_metric)}</small></div>`:''}${row.target_units!=null?`<div><span>서울·경기 연결 사업계획</span><strong>${units(row.target_units)}</strong><small>${num(list.length)}개 블록·사업 묶음 · 승인 대기 포함</small></div>`:''}<div><span>실제 공정률 보고 확보</span><strong>${num(reports.length)}<small>개 블록·사업</small></strong><small>원천 보고 기준 · 공급 달성률과 구분</small></div></div><div class="policy-supply-breakdown"><h3>세부 공급 내역</h3><p>${(o.details||[]).map(v=>`<span>${esc(v)}</span>`).join('')}</p><div>${(o.breakdown||[]).filter(v=>v.units!=null).map(v=>`<span>${esc(v.name)} <b>${units(v.units)}</b></span>`).join('')}</div></div></section>`;
  }
  function annual(row){
    const series=row.timeline?.annual||[],max=Math.max(1,...series.map(y=>y[measure].units||0));
    const official=series.filter(y=>y.official_start_units!=null);
    return `<section id="policy-annual-supply" class="panel"><div class="panel-head"><div><p class="section-kicker">ANNUAL SUPPLY</p><h2>연도별 공급계획</h2><p class="policy-section-caption">해당 연도의 예정 물량 · 현재 정책에 연결된 서울·경기 사업</p></div><label class="policy-measure-label">일정 기준 <select id="policy-timeline-measure" aria-label="연도별 공급계획 기준">${Object.entries(labels).map(([k,v])=>`<option value="${k}" ${measure===k?'selected':''}>${v}</option>`).join('')}</select></label></div><div class="policy-annual-scroll"><div class="policy-annual-columns">${series.map(y=>{const v=y[measure];return `<div class="policy-year-column ${y.year===payload.year?'current-year':''}" data-supply-year="${y.year}"><div class="annual-unit-label">${v.units!=null?`<b>${units(v.units)}</b>`:''}</div><div class="annual-bar-track">${v.units!=null?`<svg class="annual-supply-bar" viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="${y.year}년 ${labels[measure]} ${units(v.units)}"><rect x="24" y="${100-v.units/max*100}" width="52" height="${v.units/max*100}" rx="3" fill="#2e7fe7"/></svg>`:''}</div><strong>${y.year}</strong>${v.manual_units!=null?`<small>관리자 ${units(v.manual_units)}</small>`:''}</div>`;}).join('')}</div></div><p class="policy-chart-basis">${labels[measure]}만 집계하며 준공·모집 물량을 합산하지 않습니다. 입주는 시작 예정월만 관리합니다. 빈 연도는 미확보입니다.${official.length?`<br>공식 수도권 착공 목표: ${official[0].year}~${official.at(-1).year}년 연 ${units(official[0].official_start_units)} · 위 사업별 예정량과 지표·범위가 다릅니다.`:''}</p></section>`;
  }
  function range(block,year){
    const a=Date.UTC(year,0,1),b=Date.UTC(year+1,0,1),day=86400000;
    return block.intervals.map(i=>{
      const start=Date.parse(i.start),end=Date.parse(i.end)+day,left=Math.max(a,start),right=Math.min(b,end);
      return right>left?`<rect class="planned-span" x="${(left-a)/(b-a)*100}" y="0" width="${(right-left)/(b-a)*100}" height="5" rx="1" fill="#dfbc7e"><title>${esc(i.name)} · 계획 ${i.start}~${i.end}</title></rect>`:'';
    }).join('');
  }
  function cell(block,year){
    const events=block.events.filter(e=>e.year===year),actual=block.actuals.filter(a=>a.year===year);
    return `<td data-timeline-year="${year}" class="${year===payload.year?'current-year':''}"><div class="block-year-plan"><div class="block-plan-labels">${events.map(e=>`<span class="planned-event ${e.stage===measure?'focus-measure':''} ${e.origin==='MANUAL'?'manual-goal':''}" title="${esc(e.basis||'')}" data-plan-stage="${esc(e.stage)}">${stages[e.stage]}${e.month?' '+Number(e.month.slice(5,7))+'월':''}${e.stage==='MOVE_IN'?' · 시작일만 관리':e.units!=null?' · '+units(e.units):''}${e.origin==='MANUAL'?' 목표':''}</span>`).join('')}</div><div class="block-plan-axis"><svg class="planned-spans" viewBox="0 0 100 5" preserveAspectRatio="none" aria-hidden="true">${range(block,year)}${events.filter(e=>e.month).map(e=>`<circle class="plan-milestone" cx="${(Number(e.month.slice(5,7))-.5)/12*100}" cy="2.5" r="1.5" fill="#bd8e36" stroke="#fff" stroke-width=".5"><title>${esc(e.label)} · ${esc(e.month)}</title></circle>`).join('')}</svg></div></div><div class="block-year-actual">${actual.map(a=>`<button class="actual-report" data-project="${esc(a.project_id)}" data-report-date="${esc(a.date)}" data-progress-pct="${a.pct}" aria-label="${esc(a.name)} ${a.date} 실제 공정률 ${num(a.pct)}%" title="${esc(a.name)} · ${a.date} 보고"><b>${num(a.pct)}%</b><svg class="actual-progress-track" viewBox="0 0 100 4" preserveAspectRatio="none" aria-hidden="true"><rect width="100" height="4" rx="2" fill="#e5eef8"/><rect class="actual-progress-fill" width="${a.pct}" height="4" rx="2" fill="#297ce1"/></svg><small>${a.date.slice(5).replace('-','.')}</small></button>`).join('')}</div></td>`;
  }
  function subtotal(children,year){
    const known=children.flatMap(b=>b.events.filter(e=>e.year===year&&e.stage===measure&&e.units!=null)).map(e=>e.units);
    return known.length?`<b class="timeline-subtotal">${units(known.reduce((a,b)=>a+b,0))}</b>`:'';
  }
  function tree(row){
    const t=row.timeline||{years:[],regions:[],block_count:0};
    const groupRow=(kind,id,name,children,level)=>`<tr class="timeline-group ${kind}" data-tree-level="${level}"><th scope="row" class="timeline-name"><button data-timeline-toggle="${esc(id)}" aria-expanded="${!collapsed.has(id)}"><span>${collapsed.has(id)?'▸':'▾'}</span> ${esc(name)}</button><small>${num(children.length)}개 블록·사업${children.some(b=>b.target_units!=null)?' · '+units(children.reduce((n,b)=>n+(b.target_units||0),0)):''}</small></th>${t.years.map(y=>`<td class="${y===payload.year?'current-year':''}">${subtotal(children,y)}</td>`).join('')}</tr>`;
    const rows=t.regions.map(r=>{
      let html=groupRow('region',r.id,r.name,r.cities.flatMap(c=>c.blocks),1);
      if(collapsed.has(r.id))return html;
      for(const c of r.cities){
        html+=groupRow('municipality',c.id,c.name,c.blocks,2);if(collapsed.has(c.id))continue;
        for(const b of c.blocks)html+=`<tr class="timeline-block" data-tree-level="3" data-timeline-block="${esc(b.id)}"><th scope="row" class="timeline-name"><button class="timeline-block-name" data-project="${esc(b.project_ids[0])}">${esc(b.name)}</button><div class="timeline-block-capacity">${b.target_units!=null?`<b>공급계획 ${units(b.target_units)}</b>`:''}${!b.block?'<small>사업 단위</small>':''}</div><div class="timeline-lane-labels"><span>계획</span><span>실제 공정률</span></div></th>${t.years.map(y=>cell(b,y)).join('')}</tr>`;
      }
      return html;
    }).join('');
    return `<section id="policy-block-timeline" class="panel"><div class="panel-head"><div><p class="section-kicker">REGION & BLOCK TIMELINE</p><h2>지역·블록별 계획 대비 진행현황</h2><p class="policy-section-caption">시도 › 시군구 › 블록 · ${num(t.block_count)}개 묶음 · 상단 계획 / 하단 실제 공정률</p></div><div class="policy-tree-tools"><button data-timeline-expand="all">전체 펼침</button><button data-timeline-expand="none">전체 접기</button><button data-timeline-current>현재 연도</button></div></div><div class="policy-timeline-legend"><span><i class="plan-key"></i> 계획 기간·예정 물량</span><span><i class="actual-key"></i> 원천 보고 공정률</span><span>보고가 없는 연도는 비워둡니다.</span></div><div class="policy-tree-scroll" tabindex="0" aria-label="블록별 연도 시계열표 · 가로·세로 스크롤"><table class="policy-timeline-table" role="treegrid" aria-label="시도 시군구 블록별 계획과 실제 공정률"><colgroup><col class="timeline-name-col">${t.years.map(()=>'<col class="timeline-year-col">').join('')}</colgroup><thead><tr><th class="timeline-name" scope="col">지역·블록 / 공급수량</th>${t.years.map(y=>`<th scope="col" data-timeline-header="${y}" class="${y===payload.year?'current-year':''}">${y}${y===payload.year?'<small>올해</small>':''}</th>`).join('')}</tr></thead><tbody>${rows||`<tr><td colspan="${t.years.length+1}" class="timeline-empty">선택 정책에 연결된 사업이 없습니다.</td></tr>`}</tbody></table></div><p class="policy-chart-basis">${esc(t.basis||'')}<br>${esc(payload.notice)}</p></section>`;
  }
  function evidence(row){
    const sources=row.timeline?.evidence||[];
    const categories=[...new Set(sources.map(s=>s.kind))];
    return `<section id="policy-original-sources" class="panel"><div class="panel-head"><div><p class="section-kicker">ORIGINAL SOURCES</p><h2>관련 자료 원본</h2><p class="policy-section-caption">정책·공급계획·기준일별 공사 보고서 · ${num(sources.length)}개 원문</p></div></div><div class="policy-source-groups">${categories.map((kind,index)=>`<details ${index<2?'open':''}><summary>${esc(kind)} <small>${sources.filter(s=>s.kind===kind).length}개</small></summary><ul>${sources.filter(s=>s.kind===kind).map(s=>`<li><a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">${esc(s.label)} ↗</a></li>`).join('')}</ul></details>`).join('')}</div></section>`;
  }
  function detail(){
    const row=payload.items.find(r=>r.id===selected);if(!row){$('policy-monitor-detail').innerHTML='';return;}
    $('policy-monitor-detail').setAttribute('aria-labelledby','policy-tab-'+row.id);
    $('policy-monitor-detail').innerHTML='<div id="policy-report-detail"></div><details id="policy-program-members" class="pr-extra-data"><summary>선택 범위의 프로그램 펼쳐보기</summary><div data-pr-program-members></div></details><details class="pr-extra-data"><summary>지역·블록 상세 시계열과 원본 자료 펼쳐보기</summary>'+tree(row)+evidence(row)+'</details>';
    PolicyReport.policyChanged(row);
    document.dispatchEvent(new CustomEvent('home:policy-selected',{detail:{id:row.id}}));
  }
  function start(){
    document.addEventListener('change',event=>{
      if(event.target.id==='policy-detail-select'){selected=event.target.value;collapsed.clear();render(payload);}
      if(event.target.id==='policy-timeline-measure'){measure=event.target.value;detail();}
    });
    document.addEventListener('click',event=>{
      const button=event.target.closest('[data-monitor-detail]');if(button&&payload){selected=button.dataset.monitorDetail;collapsed.clear();render(payload);}
      const work=event.target.closest('[data-policy-workbench]');if(work){setView('tree');MappingWorkbench.focusPolicy(work.dataset.policyWorkbench);}
      const toggle=event.target.closest('[data-timeline-toggle]');
      const expand=event.target.closest('[data-timeline-expand]');
      if(toggle||expand){
        const scroller=document.querySelector('.policy-tree-scroll'),left=scroller.scrollLeft,top=scroller.scrollTop;
        if(toggle){const key=toggle.dataset.timelineToggle;collapsed.has(key)?collapsed.delete(key):collapsed.add(key);}
        else{collapsed.clear();if(expand.dataset.timelineExpand==='none')for(const r of payload.items.find(r=>r.id===selected).timeline.regions)collapsed.add(r.id);}
        const container=$('policy-block-timeline'),holder=document.createElement('div');holder.innerHTML=tree(payload.items.find(r=>r.id===selected));container.replaceWith(holder.firstElementChild);
        const next=document.querySelector('.policy-tree-scroll');next.scrollLeft=left;next.scrollTop=top;
      }
      if(event.target.closest('[data-timeline-current]')){
        const scroller=document.querySelector('.policy-tree-scroll'),head=scroller.querySelector(`[data-timeline-header="${payload.year}"]`);
        if(head)scroller.scrollTo({left:head.offsetLeft-scroller.querySelector('.timeline-name').getBoundingClientRect().width,behavior:'smooth'});
      }
    });
  }
  function select(id){if(!payload||!payload.items.some(row=>row.id===id))return;selected=id;collapsed.clear();render(payload);}
  return {render,start,select};
})();

const ConnectionGuide=(()=>{
  function render(data){
    const statusText=g=>g.readiness==='CONNECTED'?`${num(g.record_count)}건 수집 정상 · ${timeText(g.last_success)}`:
      g.readiness==='CONNECTOR_READY'?`수집기 연결됨 · ${g.status==='FAILED'?'최근 수집 실패':g.status==='RUNNING'?'수집 중':'수집 대기'}`:
      g.mode==='FILE'?'API 키 불필요 · 파일 수집기 연결 대기':g.key_configured?'키 설정됨 · 수집기 연결 대기':g.existing_key_configured?'기존 포털 키 있음 · 서비스 승인 확인 필요':'추가 키 미설정 · 대상 서비스 신청 필요';
    const scope=g=>g.stats?.scope_note||'';
    const cards=data.planned.map(g=>`<article class="connection-plan"><div><span class="badge ${g.readiness==='CONNECTED'?'confirmed':'review'}">${esc(g.readiness==='CONNECTED'?'연결 확인':g.priority)}</span><h3>${esc(g.name)}</h3></div><p>${esc(g.purpose)}</p><p class="connection-gap">${esc(g.gap)}</p><small>${esc(statusText(g))}</small>${g.error?`<p class="connection-gap">${esc(g.error)}</p>`:''}${scope(g)?`<p>${esc(scope(g))}</p>`:''}${g.stats?.dataset_versions?`<p>${g.stats.dataset_versions.map(r=>`${esc(r.version)} · ${num(r.records)}건${r.is_latest?' · 최신 공개본':' · 과거 공개본'}`).join('<br>')}</p>`:''}${g.stats?.series?`<p>${g.stats.series.map(r=>`${esc(r.metric)} ${esc(r.period_start)}~${esc(r.period_end)} · ${num(r.records)}건${r.complete_query?'':' · 일부 기간 미확보'}`).join('<br>')}</p>`:''}<details><summary>신청·연결 방법</summary><ol>${g.steps.map(s=>`<li>${esc(s)}</li>`).join('')}</ol>${g.key_env?`<p>HOME 서버 설정: <code>${esc(g.key_env)}</code></p>`:''}<p>${g.readiness==='DATASET_SELECTION_REQUIRED'?'대상 데이터셋 선택 필요':g.readiness==='CONNECTED'?'실제 수집 응답·이력으로 검증됨':g.readiness==='CONNECTOR_READY'?'수집기 연결 완료 · 배치 결과 확인':'수집기 연결 준비 단계'}</p></details><a href="${esc(safeUrl(g.url))}" target="_blank" rel="noopener noreferrer">공식 데이터·신청 안내 ↗</a></article>`).join('');
    $('connection-guide').innerHTML=`<div class="section-title"><div><h2>추가 연결 점검</h2><p>${esc(data.notice)}</p></div><span class="tag">${esc(data.checked_date)} 점검</span></div><div class="connection-grid">${cards}</div>`;
    $('validation-connections').innerHTML=`<div><strong>API 연결 점검</strong><p>${data.connected.filter(r=>r.status==='SUCCESS').length}/${data.connected.length}개 API 수집 정상. 건축물대장·LH·SH·통계누리의 실제 연결 상태와 자료 기준일을 확인하세요.</p><button class="text-button" data-view="keys">신청 방법·연결 상태 보기 ↗</button></div>`;
  }
  return {render};
})();
