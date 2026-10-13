'use strict';
/* Source-led policy report. Supply actual means a linked public main sale/rental notice,
   not a plan, construction percentage, completion, or occupancy. */
const PolicyReport=(()=>{
  let monitor=null,mappings=null,geo=null,view='policy-progress',selected='',measure='SUPPLY',focusYear=null,mapStage='COMPLETION',selectedCityId='',selectedRegion='',projectTicket=0;
  const outlookCache=new Map(),areaCache=new Map();
  const label={SUPPLY:'모집·공급',COMPLETION:'준공 예정'};
  const fmt=value=>value==null?'미확보':num(value)+'호';
  const safe=value=>esc(value==null?'':String(value));
  const link=(url,text)=>url&&safeUrl(url)!=='#'?'<a href="'+safe(safeUrl(url))+'" target="_blank" rel="noopener noreferrer">'+safe(text)+' ↗</a>':'<span>원문 미연계</span>';
  const yearNow=()=>Number(($('as-of').value||new Date().toISOString().slice(0,10)).slice(0,4));
  const group=()=>geo?.groups?.[view==='program-progress'?'program_link':'policy']?.find(row=>row.id===selected);
  const selectedCity=()=>view==='policy-progress'&&selectedCityId?geo?.municipalities?.find(row=>row.id===selectedCityId):null;
  function scopedGroup(){
    const base=group(),city=selectedCity()||(selectedRegion?{project_ids:(geo?.items||[]).filter(p=>p.region===selectedRegion).map(p=>p.id),by_scope:{}}:null);if(!base||!city)return base;
    const memberIds=new Set(base.project_ids||[]),ids=(city.project_ids||[]).filter(id=>memberIds.has(id));
    const chosen=new Set(base.chart_schedule_ids||[]),itemIndex=new Map((geo.items||[]).map(item=>[item.id,item]));
    const annual=new Map();
    for(const id of ids){if(!chosen.has(id))continue;
      for(const point of itemIndex.get(id)?.annual_series||[]){
        const row=annual.get(point.year)||{year:point.year};
        for(const stage of ['SUPPLY','COMPLETION','CONSTRUCTION'])if(point[stage]!=null)row[stage]=(row[stage]||0)+point[stage];
        annual.set(point.year,row);
      }
    }
    const amount=city.by_scope?.policy?.[selected]||{};
    return {...base,project_ids:ids,chart_target_ids:(base.chart_target_ids||[]).filter(id=>ids.includes(id)),chart_schedule_ids:(base.chart_schedule_ids||[]).filter(id=>ids.includes(id)),target_units:amount.target_units??null,current_notice_units:amount.current_notice_units??null,annual_series:[...annual.values()].sort((a,b)=>a.year-b.year)};
  }

  const policy=()=>monitor?.items?.find(row=>row.id===selected);
  const program=()=>mappings?.programs?.find(row=>row.id===selected);
  const project=()=>mappings?.items?.find(row=>row.id===selected);
  const members=ids=>{const set=new Set(ids||[]);return (mappings?.items||[]).filter(row=>set.has(row.id));};
  function canonicalTotals(rows,groupRow){
    const ids=new Set(groupRow?.chart_target_ids||[]);
    const known=rows.filter(row=>ids.has(row.id)&&row.planned_units!=null);
    return known.length?known.reduce((sum,row)=>sum+row.planned_units,0):null;
  }
  function summary(regionRows){
    return regionRows.map(row=>{
      const total=row.units==null?0:row.units,ratio=total?Math.max(1,Math.round(total/Math.max(1,...regionRows.map(x=>x.units||0))*100)):0;
      return '<div class="pr-region-row"><div><strong>'+safe(row.name)+'</strong><span>'+fmt(row.units)+' · '+num(row.count)+'건</span></div><svg viewBox="0 0 100 7" preserveAspectRatio="none" role="img" aria-label="'+safe(row.name)+' 연결 사업계획 '+fmt(row.units)+'"><rect width="100" height="7" rx="3" fill="#e5edf5"/><rect width="'+ratio+'" height="7" rx="3" fill="#2a78bd"/></svg></div>';
    }).join('');
  }
  function regionRows(rows,groupRow){
    const result=['서울특별시','경기도','인천광역시'].map(name=>{
      const matches=rows.filter(row=>row.region===name);
      return {name,units:canonicalTotals(matches,groupRow),count:matches.length,projects:matches};
    });
    return result.filter(row=>row.count);
  }
  function summaryPanel(row,rows,kind){
    const spot=$('policy-report-summary');if(!spot)return;
    const regions=regionRows(rows,kind==='project'?{chart_target_ids:[row?.id]}:group());
    if(kind==='policy'){
      const facts=row?.overview||{},begin=(row?.announced_at||'').slice(0,4),finish=row?.official_target_end_year;
      const period=begin&&finish?begin+'–'+finish+'년 · '+(finish-Number(begin)+1)+'년':facts.period||'기간 미확보';
      const groupRow=group(),membersSet=new Set(groupRow?.project_ids||[]),scheduled=new Set(groupRow?.chart_schedule_ids||[]);
      const progress=regions.map(place=>{
        const notices=new Set();let actual=0,hasActual=false,completionEnd=null,moveInStart=null;
        for(const item of geo?.items||[]){
          if(item.region!==place.name||!membersSet.has(item.id))continue;
          if(item.notice_evidence_id&&item.current_notice_units!=null&&item.notice_source_date&&item.notice_source_date>=row.announced_at&&!notices.has(item.notice_evidence_id)){
            notices.add(item.notice_evidence_id);actual+=item.current_notice_units;hasActual=true;
          }
          if(!scheduled.has(item.id))continue;
          for(const point of item.annual_series||[]){
            if(point.COMPLETION!=null)completionEnd=Math.max(completionEnd||0,point.year);
            if(item.move_in_start?.date)moveInStart=!moveInStart||item.move_in_start.date<moveInStart?item.move_in_start.date:moveInStart;
          }
        }
        return '<div class="pr-brief-place"><b>'+safe(place.name)+'</b><div><span>연결 사업계획</span><strong>'+fmt(place.units)+'</strong></div><div><span>공고 확인 공급</span><strong>'+fmt(hasActual?actual:null)+'</strong></div><small>전체 완료 '+(completionEnd?completionEnd+'년 예정':'시점 미확보')+(moveInStart?' · 이른 입주 시작 '+moveInStart+' 예정':'')+'</small></div>';
      }).join('');
      const finishText=finish?finish+'년':'일정 미정';
      spot.innerHTML='<div class="pd-overview"><small>정책 개요 · 발표 '+safe(row.announced_at)+'</small><h3>'+safe(row.name)+'</h3><div class="pd-main-target"><span>'+safe(row.announced_target_metric||'공식 발표 목표')+'</span><strong class="d907-total">'+fmt(row.announced_target_units)+'</strong><b>'+safe(period)+'</b></div><p class="pd-joint">대상 지역 · '+safe(row.announced_target_scope||facts.location||'미확보')+'</p><div class="pd-region-targets">'+regions.map(r=>'<button data-pr-region="'+safe(r.name)+'"><b>'+safe(r.name)+'</b><strong>지역 목표 미확보</strong><span>'+safe(period)+'</span></button>').join('')+'</div><p class="pr-note">연결 사업계획은 지역별 공식 배정 목표로 대체하지 않습니다.</p><div class="pd-summary-foot">'+link(row.evidence_url,'발표 자료 원본 보기')+'</div></div>';
      return;
    }
    const source=kind==='program'?row?.evidence_url:row?.evidence_url;
    const sourceText=kind==='program'?'프로그램 연결 근거':'사업 원천 자료';
    spot.innerHTML='<div class="pr-side-summary"><small>'+safe(kind==='program'?'프로그램 개요':'사업 개요')+'</small><p>'+safe(kind==='program'?(row?.basis||'정책 연결 검토 중'):row?.stage_label)+'</p><div class="pr-side-link">'+link(source,sourceText)+'</div><div class="pr-side-regions"><b>연결 사업계획</b>'+summary(regions)+'</div></div>';
  }
  function seriesFor(groupRow){
    const years=new Map();
    for(const point of groupRow?.annual_series||[])years.set(Number(point.year),{...point});
    const announced=view==='policy-progress'?policy()?.announced_at:null;
    if(announced&&geo&&groupRow){
      for(const point of years.values())delete point.notice_units;
      const members=new Set(groupRow.project_ids||[]),seen=new Set();
      for(const item of geo.items||[]){
        if(!members.has(item.id)||!item.notice_evidence_id||seen.has(item.notice_evidence_id)||item.current_notice_units==null||!item.notice_source_date||item.notice_source_date<announced)continue;
        seen.add(item.notice_evidence_id);
        const year=Number(item.notice_source_date.slice(0,4)),point=years.get(year)||{year};
        point.notice_units=(point.notice_units||0)+item.current_notice_units;years.set(year,point);
      }
    }
    return years;
  }
  function flowModel(groupRow){
    const announcement=view==='policy-progress'?policy()?.announced_at:null;
    return PolicyDeliveryFlow.model({group:groupRow,items:geo?.items||[],asOf:$('as-of')?.value||new Date().toISOString().slice(0,10),selectedYear:focusYear??yearNow(),announcedAt:announcement});
  }
  function graphCard(groupRow){
    const model=flowModel(groupRow);
    return '<article class="pr-card pr-chart-card"><div class="pr-card-head"><div><small>DELIVERY PROGRESS</small><h3>계획 대비 공급 흐름 · 4년 확대 / 11년 전체</h3></div><span class="pr-chart-stage">선택 '+model.selected+'년 · 공급 실적은 본 공고 기준</span></div>'+PolicyDeliveryFlow.render(model)+'</article>';
  }
  function periodActual(groupRow){
    const values=[...seriesFor(groupRow).values()].filter(row=>row.year<=yearNow()&&row.notice_units!=null);
    return values.length?values.reduce((sum,row)=>sum+row.notice_units,0):null;
  }
  function status(groupRow){
    const flow=flowModel(groupRow),due=flow.current.overdue,actual=flow.current.actual;
    if(!flow.hasSchedules)return {text:'공급 일정 미확보 · 판정 보류',className:'missing',basis:'원천 모집·공급 예정월이 없어 일정 대비 차이를 판정할 수 없습니다.'};
    if(due)return {text:'지연 후보 · 담당자 검토',className:'attention',basis:'예정월 경과 후 공고 미확인 '+fmt(due)+' · 공고 누락·연결 상태 확인 필요'};
    return {text:'일정 경과 미확인 물량 없음',className:'good',basis:'현재월 전까지의 원천 모집 일정과 연결 공고 기준 · 담당자 검토 필요'};
  }
  function cards(row,groupRow,kind){
    const s=status(groupRow),city=selectedCity(),official=kind==='policy'&&!city?'<div class="pr-stat"><span>발표 당시 공식 목표</span><strong>'+fmt(row?.announced_target_units)+'</strong><small>'+(city?'상위 정책 전체 · 시군구별 공식 배정량 미확보':safe(row?.announced_target_scope)+' · '+safe(row?.announced_target_metric))+'</small></div>':'';
    const supply=kind==='policy'?(city?periodActual(groupRow):row?.actual_supply_period_units):groupRow?.current_notice_units;
    const context=kind==='policy'?(city?city.name+' · 발표 이후 공식 공고 확인 · 귀속 검토':'발표 전 포함 연결 사업 공고 '+fmt(row?.actual_supply_units)):'분양·모집 단계 도달 · 실입주와 구분';
    return '<div class="pr-stats">'+official+'<div class="pr-stat"><span>'+(city?safe(city.name)+' 연결 사업계획':'연결 사업계획')+'</span><strong>'+fmt(groupRow?.target_units)+'</strong><small>정책·프로그램 귀속 검토 중</small></div><div class="pr-stat"><span>'+(kind==='policy'?'정책 발표 이후 ':'')+'공고 확인 공급 실적</span><strong>'+fmt(supply)+'</strong><small>'+safe(context)+'</small></div><div class="pr-stat '+s.className+'"><span>추진 판정</span><strong>'+safe(s.text)+'</strong><small>'+safe(s.basis)+'</small></div></div>';
  }
  function regionsCard(rows,groupRow){
    const places=regionRows(rows,groupRow);
    const muni=new Map();
    for(const row of rows){const key=(row.region||'미확보')+'|'+(row.municipality||'시군구 미확보');if(!muni.has(key))muni.set(key,[]);muni.get(key).push(row);}
    const sub=[...muni].map(([key,items])=>({name:key.replace('|',' · '),units:canonicalTotals(items,groupRow),count:items.length})).sort((a,b)=>(b.units||0)-(a.units||0));
    return '<article class="pr-card"><div class="pr-card-head"><div><small>REGION BREAKDOWN</small><h3>지역별 연결 공급계획</h3></div><span>서울·경기 한정</span></div>'+summary(places)+'<details><summary>시군구별 '+sub.length+'곳 보기</summary><div class="pr-region-scroll">'+summary(sub)+'</div></details><p class="pr-note">공식 정책 목표의 지역 배정량이 아니라 현재 연결된 사업계획 물량입니다. 동일 사업 원천 중복 제외 기준을 적용했습니다.</p></article>';
  }
  function programmeList(policyId,regionFilter='',scopeIds){
    const city=selectedCity(),scopeSet=scopeIds?new Set(scopeIds):null;
    const selectedProjects=(mappings?.items||[]).filter(p=>(!scopeSet||scopeSet.has(p.id))&&(!city||(city.project_ids||[]).includes(p.id))&&(!regionFilter||p.region===regionFilter));
    const programs=new Set(selectedProjects.map(p=>p.mapping?.program_id)),rows=(mappings?.programs||[]).filter(p=>p.policy_id===policyId&&(!(scopeSet||city||regionFilter)||programs.has(p.id)));
    return '<article class="pr-card"><div class="pr-card-head"><h3>선택 범위의 프로그램</h3><span>'+rows.length+'개 · 연결 검토 포함</span></div><div class="pr-member-scroll">'+(rows.map(p=>'<button type="button" class="pr-member" data-pr-program="'+safe(p.id)+'"><span><b>'+safe(p.name)+'</b><small>'+selectedProjects.filter(r=>r.mapping?.program_id===p.id).length+'개 연결 사업</small></span><strong>열기 →</strong></button>').join('')||'<p>연결된 프로그램 미확보</p>')+'</div></article>';
  }
  function projectTree(programId,scopeIds){
    const rows=(mappings?.items||[]).filter(row=>row.mapping?.program_id===programId&&(!scopeIds||scopeIds.includes(row.id)));
    const regions=new Map();
    for(const row of rows){const region=row.region||'지역 미확보',city=row.municipality||'시군구 미확보';if(!regions.has(region))regions.set(region,new Map());const cities=regions.get(region);if(!cities.has(city))cities.set(city,[]);cities.get(city).push(row);}
    const markup=[...regions].map(([region,cities])=>'<details open class="pr-tree-region"><summary>'+safe(region)+' · '+num([...cities.values()].flat().length)+'건</summary>'+[...cities].map(([city,items])=>'<details open class="pr-tree-city"><summary>'+safe(city)+' · '+num(items.length)+'건</summary>'+items.map(row=>'<button type="button" class="pr-member" data-pr-project="'+safe(row.id)+'"><span><b>'+safe(row.name)+'</b><small>'+safe(row.district||'지구 미확보')+' '+safe(row.block||'')+' · 계획 '+fmt(row.planned_units)+'</small></span><strong>열기 →</strong></button>').join('')+'</details>').join('')+'</details>').join('');
    return '<article class="pr-card"><div class="pr-card-head"><div><small>REGION → CITY → PROJECT</small><h3>소속 사업</h3></div><span>'+num(rows.length)+'건 · 10개 행 높이에서 스크롤</span></div><div class="pr-member-scroll pr-tree-scroll">'+(markup||'<p>연결된 사업 미확보</p>')+'</div></article>';
  }
  function programmePeriod(groupRow){const years=[...seriesFor(groupRow).keys()];return years.length?Math.min(...years)+'–'+Math.max(...years)+'년 연결 사업 일정 · 프로그램 독립 기간 미확보':'프로그램 독립 기간 미확보';}
  function phase(row){const start=Number((row?.announced_at||'').slice(0,4)),end=Number(row?.official_target_end_year),now=yearNow();if(!start||!end||end<start)return '<p class="pr-note">정책 전체 기간 미확보</p>';const elapsed=Math.max(0,Math.min(end-start+1,now-start+1)),total=end-start+1;return '<div class="pr-phase"><div><b>정책 기간의 현재 위치</b><span>'+start+'–'+end+' · '+elapsed+'/'+total+'년 경과</span></div><progress value="'+elapsed+'" max="'+total+'"></progress><small>시간 경과이며 공급 달성률이 아닙니다.</small></div>';}
  function overviewCard(row,kind){
    if(kind==='policy'){const facts=row?.overview||{};return '<article class="pr-card"><div class="pr-card-head"><div><small>POLICY SOURCE</small><h3>정책 개요와 추출 근거</h3></div>'+link(row?.evidence_url,'발표 자료 원본')+'</div><dl class="pr-facts"><dt>목적</dt><dd>'+safe(facts.purpose||'미확보')+'</dd><dt>위치</dt><dd>'+safe(facts.location||'미확보')+'</dd><dt>기간</dt><dd>'+safe(facts.period||'일정 미정')+'</dd><dt>추출한 정책 목표</dt><dd>'+fmt(row?.announced_target_units)+' · '+safe(row?.announced_target_metric)+'</dd><dt>추출한 사업 범위</dt><dd>서울·경기 연결 후보 '+num(row?.project_count||0)+'건 · 사업계획 '+fmt(row?.target_units)+'</dd></dl>'+phase(row)+'</article>';}
    const parent=(mappings?.policies||[]).find(item=>item.policy_id===row?.policy_id);
    return '<article class="pr-card"><div class="pr-card-head"><div><small>PROGRAMME SOURCE</small><h3>프로그램 개요와 상위 정책</h3></div>'+link(row?.evidence_url,'연결 근거 원본')+'</div><dl class="pr-facts"><dt>상위 정책</dt><dd>'+(parent?'<button data-pr-policy="'+safe(row.policy_id)+'">'+safe(parent.name)+' →</button>':'미연계')+'</dd><dt>정책 연결 상태</dt><dd>'+safe(row?.status==='CONFIRMED'?'담당자 확정':'연결됨 · 승인 대기')+'</dd><dt>소속 사업</dt><dd>'+num(row?.active_project_count??row?.project_count??0)+'건</dd><dt>기간</dt><dd>'+safe(programmePeriod(group()))+'</dd></dl></article>';
  }
  function projectionMembers(groupRow){
    const chosen=new Set(groupRow?.chart_schedule_ids||[]);
    const projectIds=new Set(groupRow?.project_ids||[]);
    return (geo?.items||[]).filter(item=>projectIds.has(item.id)&&chosen.has(item.id));
  }
  function outlook(region){
    if(!outlookCache.has(region))outlookCache.set(region,request('/area-outlook?region='+encodeURIComponent(region)));
    return outlookCache.get(region);
  }
  function projectionChart(groupRow,token){
    const target=document.querySelector((view==='program-progress'?'#program-progress-detail':'#policy-report-detail')+' [data-pr-projection]');
    if(!target)return;
    if(selectedRegion==='인천광역시'){target.innerHTML='<p>인천 가구 추계·주택 재고의 동일 범위 비교 자료는 미확보입니다.</p>';return;}
    const city=selectedCity();if(city){target.innerHTML='<p>'+safe(city.name)+'의 연도별 미래 가구 추계는 미확보입니다. 시도 가구 추계를 시군구 공급량과 합쳐 부족·잔여를 산출하지 않습니다.</p>';return;}
    const items=projectionMembers(groupRow),memberIds=new Set(groupRow?.project_ids||[]),regions=[...new Set((geo?.items||[]).filter(item=>memberIds.has(item.id)).map(item=>item.region).filter(region=>region==='서울특별시'||region==='경기도'))];
    if(!regions.length){target.innerHTML='<p>연결 지역 또는 준공 일정이 미확보되어 지역 가구 추계와 비교할 수 없습니다.</p>';return;}
    target.innerHTML='<p>서울·경기 가구 추계와 연결된 준공 일정 확인 중…</p>';
    Promise.all(regions.map(outlook)).then(data=>{
      if(token!==projectTicket||!target.isConnected)return;
      const now=yearNow(),years=Array.from({length:6},(_,i)=>now+i),scheduled=new Map(),regionRows=new Map(data.map(row=>[row.region,row]));
      for(const item of items){
        const future=(item.annual_series||[]).filter(event=>event.year>now),stage='COMPLETION';
        for(const event of future){if(event[stage]==null)continue;
          const key=item.region+'|'+event.year;scheduled.set(key,(scheduled.get(key)||0)+event[stage]);
        }
      }
      const hasSchedule=scheduled.size>0,rows=years.map(year=>{
        let households=0,stock=0,planned=0,delayed=0,available=true;
        for(const region of regions){const data=regionRows.get(region),sample=data?.years?.find(point=>point.year===year);
          const observed=(data?.years||[]).filter(point=>point.year<=year&&point.observed_completion_since_baseline!=null).at(-1)?.observed_completion_since_baseline;
          if(sample?.forecast_households==null||data?.baseline?.housing_units==null||observed==null){available=false;break;}
          households+=sample.forecast_households;stock+=data.baseline.housing_units+observed;
          for(let y=now+1;y<=year;y++)planned+=scheduled.get(region+'|'+y)||0;
          for(let y=now+1;y<year;y++)delayed+=scheduled.get(region+'|'+y)||0;
        }
        return available?{year,households,stock,planned:stock+planned,delayed:stock+delayed}:null;
      }).filter(Boolean);
      if(!rows.length){target.innerHTML='<p>해당 범위의 가구 추계 또는 주택 재고 기준값 미확보</p>';return;}
      const min=Math.min(...rows.flatMap(row=>[row.households,row.stock])),max=Math.max(...rows.flatMap(row=>[row.households,row.planned]))+1;
      const x=i=>65+i*170,y=v=>225-(v-min)/(max-min)*175;
      const line=key=>rows.map((row,i)=>(i?'L':'M')+x(i)+' '+y(row[key])).join(' ');
      const legend='<div class="pr-chart-key"><span><i class="households"></i>가구 추계</span><span><i class="stock"></i>현재 재고 + 관측 준공</span>'+(hasSchedule?'<span><i class="plan"></i>연결 준공 예정 반영</span><span><i class="delay"></i>1년 지연 가정</span>':'')+'</div>';
      const svg='<div class="pr-chart-scroll"><svg viewBox="0 0 1000 275" role="img" aria-label="지역 가구 추계와 주택 재고 및 연결 예정 준공 비교"><g class="pr-chart-grid">'+[0,.5,1].map(f=>'<line x1="60" x2="930" y1="'+(225-f*175)+'" y2="'+(225-f*175)+'" stroke="#e4ebf4"/><text x="55" y="'+(229-f*175)+'" text-anchor="end">'+num(Math.round(min+(max-min)*f))+'</text>').join('')+'</g><path d="'+line('households')+'" fill="none" stroke="#d67a30" stroke-width="3"/><path d="'+line('stock')+'" fill="none" stroke="#71889b" stroke-width="3"/>'+(hasSchedule?'<path d="'+line('planned')+'" fill="none" stroke="#1766db" stroke-width="3"/><path d="'+line('delayed')+'" fill="none" stroke="#b34c65" stroke-width="2" stroke-dasharray="5 4"/>':'')+rows.map((row,i)=>'<text x="'+x(i)+'" y="252" text-anchor="middle">'+row.year+'</text>').join('')+'</svg></div>';
      const final=rows.at(-1),gap=hasSchedule?final.planned-final.households:null;
      target.innerHTML=legend+svg+'<div class="pr-projection-outcome"><strong>'+safe(hasSchedule?(gap>=0?'가구 추계 대비 단순 잔여 '+fmt(gap):'가구 추계 대비 단순 부족 '+fmt(-gap)):'정책 효과 산정 미확보')+'</strong><span>'+safe(regions.join(' + '))+' · '+final.year+'년 기준</span></div><p class="pr-note">가구 추계와 주택 재고는 시도 합계입니다. 연결 사업의 확인된 향후 준공 예정 물량만 100% 재고 증가로 가정한 참고 시나리오이며, 멸실·공실·타 사업 공급·중복 사업·가구당 주택 수를 반영하지 않았습니다. 1년 지연선은 확인된 준공 일정만 1년 이동한 가정입니다. 사업별 정책 효과나 시군구 수급 판정으로 사용하지 마세요.</p>';
    }).catch(error=>{if(target.isConnected)target.textContent='지역 추계 조회 실패: '+error.message;});
  }
  function areaContext(region,municipality){
    const key=region+'|'+(municipality||'')+'|'+yearNow();
    if(!areaCache.has(key))areaCache.set(key,request('/area-context?region='+encodeURIComponent(region)+(municipality?'&municipality='+encodeURIComponent(municipality):'')+'&year='+yearNow()).catch(error=>{areaCache.delete(key);throw error;}));
    return areaCache.get(key);
  }
  function demographicCard(){
    return '<div class="pr-grid pr-demographic-grid" data-pr-demography><article class="pr-card"><h3>가구 규모별 변화</h3><p>공식 시도 가구 통계를 확인하고 있습니다…</p></article></div>';
  }
  function demographicCharts(groupRow,token){
    const host=document.querySelector('#policy-report-detail [data-pr-demography]');if(!host)return;
    const city=selectedCity(),memberIds=new Set(groupRow?.project_ids||[]),regions=city?[city.region]:selectedRegion?[selectedRegion]:[...new Set((geo?.items||[]).filter(item=>memberIds.has(item.id)).map(item=>item.region).filter(region=>region==='서울특별시'||region==='경기도'))];
    const scopeLabel=city?city.region+' · '+city.name:regions.join(' + ');
    if(regions.includes('인천광역시')){host.innerHTML='<article class="pr-card"><h3>'+safe(scopeLabel)+' 인구·가구</h3><p>동일 범위의 인구·가구·주택 재고 통계는 아직 미확보입니다.</p></article>';return;}
    if(!regions.length){host.innerHTML='<article class="pr-card"><h3>인구·가구 비교</h3><p>정책 연결 지역 미확보</p></article>';return;}
    Promise.all(regions.map(region=>areaContext(region,city?.name))).then(data=>{
      if(token!==projectTicket||!host.isConnected)return;
      const sizes=['1','2','3','4','5+'],colors=['#20589a','#3f8aba','#6db7c8','#e5a259','#a9c1d2'];
      const allYears=[...new Set(data.flatMap(item=>item.household_size.map(point=>point.year)))].sort((a,b)=>a-b);
      const household=allYears.map(year=>{
        const parts=data.map(item=>item.household_size.find(point=>point.year===year));
        if(parts.some(point=>!point))return null;
        return {year,total:parts.reduce((sum,point)=>sum+point.total,0),sizes:Object.fromEntries(sizes.map(size=>[size,parts.reduce((sum,point)=>sum+(point.sizes[size]||0),0)]))};
      }).filter(Boolean);
      const max=Math.max(1,...household.map(point=>point.total));
      const stacks=household.map(point=>'<div class="pr-house-row"><b>'+point.year+'</b><div class="pr-house-stack" title="'+point.year+'년 '+fmt(point.total)+'">'+sizes.map((size,i)=>'<i class="pr-size-'+size.replace('+','plus')+'" data-pr-width="'+(100*(point.sizes[size]||0)/max).toFixed(2)+'" title="'+size+'인 가구 '+fmt(point.sizes[size])+'"></i>').join('')+'</div><strong>'+num(point.total)+'가구</strong></div>').join('');
      const latest=household.at(-1),first=household[0],one=latest?.sizes['1'],change=first&&latest?one-first.sizes['1']:null;
      const householdCard='<article class="pr-card"><div class="pr-card-head"><div><small>HOUSEHOLD COMPOSITION</small><h3>1·2·3·4인 이상 가구 변화</h3></div><span>'+safe(scopeLabel)+'</span></div><div class="pr-house-legend">'+sizes.map((size,i)=>'<span><i class="pr-size-'+size.replace('+','plus')+'"></i>'+size+'인'+(size==='5+'?' 이상':'')+'</span>').join('')+'</div><div class="pr-house-rows">'+(stacks||'<p>가구원수별 자료 미확보</p>')+'</div><p class="pr-insight">'+(latest?'최근 '+latest.year+'년 1인 가구 '+fmt(one)+' · '+first.year+'년 대비 '+(change>=0?'+':'')+fmt(change):'가구원수별 통계 미확보')+'</p><p class="pr-note">KOSIS 일반가구 가구원수별 통계. 인구와 정책 공급 실적은 별도 지표입니다.</p></article>';
      const popYears=[...new Set(data.flatMap(item=>item.population_history.map(point=>point.year)))].sort((a,b)=>a-b);
      const trend=popYears.map(year=>{
        const pops=data.map(item=>item.population_history.find(point=>point.year===year)?.population),homes=data.map(item=>item.housing_balance.find(point=>point.year===year));
        return {year,population:pops.every(Number.isFinite)?pops.reduce((a,b)=>a+b,0):null,households:homes.every(point=>point?.households!=null)?homes.reduce((a,b)=>a+b.households,0):null,housing:homes.every(point=>point?.housing_units!=null)?homes.reduce((a,b)=>a+b.housing_units,0):null};
      });
      const valid=trend.filter(row=>row.population!=null&&row.households!=null),start=valid[0];
      const index=trend.map(row=>({year:row.year,population:start&&row.population!=null?100*row.population/start.population:null,households:start&&row.households!=null?100*row.households/start.households:null}));
      const xx=i=>56+i*445/Math.max(1,index.length-1),yy=v=>150-(v-85)/35*120;
      const path=key=>{let result='';index.forEach((point,i)=>{if(point[key]==null)return;result+=(result?' L':'M')+xx(i).toFixed(1)+' '+yy(point[key]).toFixed(1);});return result;};
      const latestBalance=[...trend].reverse().find(row=>row.households!=null&&row.housing!=null),difference=latestBalance?latestBalance.housing-latestBalance.households:null;
      const balance=difference==null?'재고·가구 동년 비교 미확보':difference<0?'주택 재고가 가구보다 '+fmt(-difference)+' 적음':'주택 재고가 가구보다 '+fmt(difference)+' 많음';
      const popCard='<article class="pr-card"><div class="pr-card-head"><div><small>PEOPLE & HOMES</small><h3>인구·가구 변화와 주택 재고</h3></div><span>'+safe(scopeLabel)+'</span></div><div class="pr-chart-key"><span><i class="plan"></i>인구 지수</span><span><i class="households"></i>일반가구 지수</span></div><svg class="pr-demographic-line" viewBox="0 0 540 185" role="img" aria-label="정책 포함 지역 인구와 가구 변화 지수"><line x1="55" x2="505" y1="150" y2="150" stroke="#d8e4ef"/><path d="'+path('population')+'" fill="none" stroke="#1766db" stroke-width="3"/><path d="'+path('households')+'" fill="none" stroke="#d67a30" stroke-width="3"/>'+index.map((row,i)=>'<text x="'+xx(i)+'" y="174" text-anchor="middle">'+String(row.year).slice(2)+'</text>').join('')+'</svg><div class="pr-insight"><strong>'+safe(balance)+'</strong><span>'+(latestBalance?latestBalance.year+'년 · 재고 '+fmt(latestBalance.housing)+' / 일반가구 '+fmt(latestBalance.households):'같은 연도 자료 미확보')+'</span></div><p class="pr-note">인구·가구는 첫 공통 확보연도=100으로 지수화했습니다. 재고−가구는 공가·주택 품질을 반영하지 않은 단순 수량 차이입니다.</p></article>';
      host.innerHTML=householdCard+popCard;
      host.querySelectorAll('[data-pr-width]').forEach(element=>{element.style.width=element.dataset.prWidth+'%';});
    }).catch(error=>{if(token===projectTicket&&host.isConnected)host.innerHTML='<article class="pr-card"><h3>인구·가구 비교</h3><p>자료 조회 실패: '+safe(error.message)+'</p></article>';});
  }
  function projectionCard(){
    return '<article class="pr-card pr-projection"><div class="pr-card-head"><div><small>HOUSEHOLDS & SUPPLY</small><h3>가구 증가와 공급 일정 비교</h3></div><span>'+(selectedCity()?'시군구 미래 추계 미확보':'시도 단위 참고 시나리오')+'</span></div><div data-pr-projection></div></article>';
  }
  function report(kind,row,groupRow){
    if(!row)return '';
    const ids=groupRow?.project_ids||row.project_ids||[],rows=members(ids),city=kind==='policy'?selectedCity():null;
    const start=kind==='policy'?Number((row.announced_at||'').slice(0,4)):Math.min(yearNow(),...[...seriesFor(groupRow).keys()]);
    const end=kind==='policy'?row.official_target_end_year:null;
    summaryPanel(row,kind==='policy'?members(group()?.project_ids||[]):rows,kind);
    const note=kind==='policy'?'공식 정책 목표는 '+safe(row.announced_target_scope)+' · '+safe(row.announced_target_metric)+' 기준입니다. 아래 계획·실적은 '+(city?safe(city.name):'서울·경기')+' 연결 사업의 모집·공급 기준이므로 공식 목표 달성률로 나누지 않습니다.':'프로그램의 정책 귀속은 담당자 확인 전 제안입니다. 연결 사업의 중복·지역 배분을 검토해야 합니다.';
    if(kind==='policy')return '<div class="pr-report">'+graphCard(groupRow,{start,end})+'<section id="policy-decision-workspace"></section><h2 class="pr-section-title">지역 수요와 공급 비교</h2>'+demographicCard()+'<div class="pr-grid">'+projectionCard()+programmeList(row.id,selectedRegion)+'</div><details class="pr-card"><summary>집계 기준과 원천</summary><p>'+note+'</p></details></div>';
    return '<div class="pr-report">'+(city?'<div class="pr-scope-banner"><strong>'+safe(city.region)+' · '+safe(city.name)+' 추진현황</strong><span>지도 선택 지역의 연결 사업만 집계</span><button type="button" data-pr-clear-city>전체 정책 보기 ×</button></div>':'')+cards(row,groupRow,kind)+(kind==='policy'?'':'<div class="pr-grid">'+overviewCard(row,kind)+regionsCard(rows,groupRow)+'</div>')+'<h2 class="pr-section-title">추진현황'+(city?' · '+safe(city.name):'')+'</h2>'+graphCard(groupRow,{start,end})+(kind==='policy'?'<h2 class="pr-section-title">지역 수요와 공급 비교'+(city?' · '+safe(city.name):'')+'</h2>'+demographicCard():'')+'<div class="pr-grid">'+projectionCard()+(kind==='policy'?programmeList(row.id):projectTree(row.id))+'</div><p class="pr-report-basis">'+note+'</p></div>';
  }
  function renderScope(){
    if(view==='policy-progress'){
      if(selected==='POL_2025_0907'){Policy907.show();return;}
      const target=$('policy-report-detail');if(!target)return;
      if(!geo){target.innerHTML='<article class="pr-card">지역·공급 근거를 불러오는 중입니다…</article>';return;}
      const row=policy();target.innerHTML=report('policy',row,scopedGroup())||'<p>정책 자료 미확보</p>';
      const token=++projectTicket;projectionChart(scopedGroup(),token);demographicCharts(scopedGroup(),token);genericDecision();
    }else if(view==='program-progress'){
      Policy907.showProgram(selected);return;
      const target=$('program-progress-detail');if(!target)return;
      const row=program();target.innerHTML=report('program',row,group())||'<p>프로그램 연결 자료 미확보</p>';
      projectionChart(group(),++projectTicket);
      if(row){target.insertAdjacentHTML('beforeend','<section id="program-scope-evidence"></section>');ScopeEvidence.mount($('program-scope-evidence'),{kind:'program',row,rows:members(group()?.project_ids),geo,group:group(),year:geo?.analysis_year});}
    }else if(view==='projects')renderProject();
  }
  function renderProject(){
    const target=$('project-report-detail');if(!target)return;
    const row=project(),item=geo?.items?.find(item=>item.id===selected);
    if(!row){target.innerHTML='<article class="pr-card"><h3>사업을 선택하면 계획과 실제 공급 단계를 볼 수 있습니다.</h3></article>';return;}
    const parent=(mappings?.programs||[]).find(p=>p.id===row.mapping?.program_id);
    const status=row.progress_pct==null?'원천 공정률 미확보':num(row.progress_pct)+'% · '+safe(row.progress_date||row.base_date)+' 원천 보고 · 공급량과 구분';
    const events=item?.annual_series||[];
    const schedule=events.flatMap(point=>['SUPPLY','COMPLETION','CONSTRUCTION'].filter(stage=>point[stage]!=null).map(stage=>({year:point.year,stage,units:point[stage]})));
    const marks=schedule.sort((a,b)=>a.year-b.year).map(event=>'<div class="pr-milestone"><b>'+event.year+'</b><span>'+safe(label[event.stage]||event.stage)+' 예정</span><strong>'+fmt(event.units)+'</strong></div>').join('')+(item?.move_in_start?.date?'<div class="pr-milestone"><b>'+safe(item.move_in_start.date)+'</b><span>입주 시작 예정</span><strong>시작월만 관리</strong></div>':'');
    const notice=item?.current_notice_units;
    const stageRows=[['인허가','하단 단계별 원장에서 확인·추정 근거 조회'],['착공',row.start_actual_date||'미확보'],['준공 전 공정률',row.progress_pct==null?'공정률 미확보':num(row.progress_pct)+'% · '+safe(row.progress_date||row.base_date)+' 원천 보고'],['분양·모집',notice==null?'공고 연결 미확보':'공식 공고 '+fmt(notice)+' · 연결 검토'],['준공',row.completion_plan_date?'예정 '+safe(row.completion_plan_date):'일정 미정'],['입주 시작',item?.move_in_start?.date?'예정 '+safe(item.move_in_start.date)+' · 월 단위 원천':'일정 미정']];
    summaryPanel(row,[row],'project');
    target.innerHTML='<div class="pr-report"><div class="pr-project-head"><div><small>PROJECT DELIVERY</small><h2>'+safe(row.name)+'</h2><p>'+safe(row.region)+' · '+safe(row.municipality||'시군구 미확보')+' · '+safe(row.district||'지구 미확보')+' '+safe(row.block||'')+'</p></div>'+link(row.evidence_url,'사업 원천')+'</div><div class="pr-stats"><div class="pr-stat"><span>계획 공급량</span><strong>'+fmt(row.planned_units)+'</strong><small>'+safe(row.unit_basis)+'</small></div><div class="pr-stat"><span>공고 확인 공급 실적</span><strong>'+fmt(notice)+'</strong><small>분양·모집 단계 기준 · 정책 연결 검토</small></div><div class="pr-stat"><span>준공 전 공정률</span><strong>'+safe(row.progress_pct==null?'미확보':num(row.progress_pct)+'%')+'</strong><small>'+safe(status)+'</small></div></div><div class="pr-grid"><article class="pr-card"><div class="pr-card-head"><div><small>PROJECT SOURCE</small><h3>사업 개요</h3></div></div><dl class="pr-facts"><dt>상위 프로그램</dt><dd>'+(parent?'<button data-pr-program="'+safe(parent.id)+'">'+safe(parent.name)+' →</button>':'미연계')+'</dd><dt>원천 진행단계</dt><dd>'+safe(row.stage_label)+'</dd><dt>건설 주체</dt><dd>'+safe(row.developer||'미확보')+'</dd><dt>시공사</dt><dd>'+safe(row.contractor||'미확보')+'</dd><dt>원천 기준일</dt><dd>'+safe(row.base_date||'미확보')+'</dd><dt>시작 근거</dt><dd>'+safe(row.start_actual_date||'미확보')+'</dd><dt>준공 계획</dt><dd>'+safe(row.completion_plan_date||'일정 미정')+'</dd><dt>예정일의 의미</dt><dd>'+safe(row.schedule_basis||'원천 설명 미확보')+'</dd></dl></article><article class="pr-card"><div class="pr-card-head"><div><small>STAGE EVIDENCE</small><h3>단계별 계획과 확인 현황</h3></div></div><div class="pr-stage-list">'+stageRows.map(([name,value])=>'<div><b>'+name+'</b><span>'+value+'</span></div>').join('')+'</div></article></div><article class="pr-card"><div class="pr-card-head"><div><small>YEARLY MILESTONES</small><h3>연도별 계획과 공고 확인</h3></div></div><div class="pr-milestones">'+(marks||'<p>사업별 예정 일정 미확보</p>')+'</div>'+graphCard({project_ids:[row.id],chart_schedule_ids:[row.id],target_units:row.planned_units,current_notice_units:notice},{start:Number((row.start_actual_date||row.base_date||'').slice(0,4)),end:Number((row.completion_plan_date||'').slice(0,4))})+'</article><p class="pr-report-basis">공사 공정률은 주택 공급 실적이 아닙니다. 공식 본 모집·분양공고가 확인된 호수만 공급 실적으로 표시합니다. 예정일이 지나도 최신 완료 근거가 없으면 지연 확정 대신 이행 확인 필요입니다.</p></div>';
    target.insertAdjacentHTML('beforeend','<section id="project-scope-evidence"></section>');ScopeEvidence.mount($('project-scope-evidence'),{kind:'project',row,rows:[row],geo,year:geo?.analysis_year});
  }
  function selectProject(id){selected=id;view='projects';++projectTicket;renderProject();}
  function genericDecision(){
    const g=scopedGroup();if(!g)return;const wanted=new Set(g.chart_target_ids||g.project_ids||[]),seen=new Set();
    const cohorts=(geo?.items||[]).filter(i=>wanted.has(i.id)).map(i=>{const events=[];if(i.notice_evidence_id&&!seen.has(i.notice_evidence_id)&&i.notice_source_date&&i.current_notice_units!=null){seen.add(i.notice_evidence_id);events.push({stage:'SUPPLY',event_date:i.notice_source_date,units:i.current_notice_units});}return {...i,units:i.planned_units||0,source_ids:[i.id],events,schedules:(i.annual_series||[]).flatMap(p=>['SUPPLY','COMPLETION'].filter(k=>p[k]!=null).map(k=>({stage:k,due_date:p.year+'-12-31',units:p[k]})))};});
    PolicyDecision.render($('policy-decision-workspace'),{data:{as_of_date:$('as-of').value},cohorts,scope:selectedCity()?.name||selectedRegion||'정책 연결 지역 전체',year:focusYear||yearNow()});
    const panel=$('policy-execution-panel');if(panel)panel.innerHTML='<h3>담당기관 조치</h3><p class="pd-empty">이 정책의 일정 기준선·병목 조치 자료는 아직 연결되지 않았습니다.</p>';
  }
  function supplemental907(cityId,region,sourceIds){
    const host=$('d907-context');if(!host||!geo)return;selectedCityId=cityId||'';selectedRegion=region||'';++projectTicket;
    if(region==='인천광역시'||(cityId&&!geo.municipalities.some(c=>c.id===cityId))){
      host.innerHTML='<article class="pr-card"><h3>인천 인구·가구와 공급 비교</h3><p>인천 인구·가구 추계는 아직 미확보입니다. 확보한 착공·주택 공급 통계와 별도로 표시합니다.</p></article>';return;
    }
    selectedCityId=cityId||'';
    let scoped=scopedGroup();
    if(region&&!cityId&&scoped){
      const eligible=new Set(scoped.project_ids),items=geo.items.filter(item=>eligible.has(item.id)&&item.region===region),ids=items.map(item=>item.id),idSet=new Set(ids);
      const targets=scoped.chart_target_ids.filter(id=>idSet.has(id)),schedules=scoped.chart_schedule_ids.filter(id=>idSet.has(id)),scheduleSet=new Set(schedules),annual=new Map();
      for(const item of items)if(scheduleSet.has(item.id))for(const point of item.annual_series||[]){const entry=annual.get(point.year)||{year:point.year};for(const k of ['SUPPLY','COMPLETION','CONSTRUCTION'])if(point[k]!=null)entry[k]=(entry[k]||0)+point[k];annual.set(point.year,entry);}
      scoped={...scoped,project_ids:ids,chart_target_ids:targets,chart_schedule_ids:schedules,annual_series:[...annual.values()],target_units:items.filter(i=>targets.includes(i.id)).reduce((s,i)=>s+(i.planned_units||0),0)};
    }
    if(scoped&&sourceIds){const allow=new Set(sourceIds);scoped={...scoped,project_ids:scoped.project_ids.filter(id=>allow.has(id)),chart_target_ids:scoped.chart_target_ids.filter(id=>allow.has(id)),chart_schedule_ids:scoped.chart_schedule_ids.filter(id=>allow.has(id))};}
    host.innerHTML='<h2 class="pr-section-title">지역 수요와 주택 공급 비교</h2>'+(!region?'<p class="pr-note">서울·경기 확보 통계만 비교합니다. 인천 인구·가구 통계는 미확보로 합계에서 제외됩니다.</p>':'')+demographicCard()+'<div class="pr-grid">'+projectionCard()+programmeList('POL_2025_0907',region,sourceIds)+'</div>';
    const token=++projectTicket;demographicCharts(scoped,token);projectionChart(scoped,token);
  }
  function policyChanged(row){if(!row)return;if(selected!==row.id){selectedCityId='';selectedRegion='';}view='policy-progress';selected=row.id;measure='SUPPLY';renderScope();}
  function scopeChanged(nextView,id,metrics){if(!id)return;geo=metrics;view=nextView;selected=id;renderScope();}
  function setData(policyData,mappingData){monitor=policyData;mappings=mappingData;Policy907.setPrograms(mappingData.programs);outlookCache.clear();if(selected)renderScope();}
  function start(){
    document.addEventListener('home:policy-geo-scope',event=>{const {view,id,metrics}=event.detail;if(['policy-progress','program-progress','projects'].includes(view))scopeChanged(view,id,metrics);});
    document.addEventListener('home:policy-schematic-change',event=>{if(selected==='POL_2025_0907')return;focusYear=event.detail.year;mapStage=event.detail.stage;const cityId=event.detail.cityId||'',region=event.detail.region==='all'?'':event.detail.region||'';if(cityId!==selectedCityId||region!==selectedRegion){selectedCityId=cityId;selectedRegion=region;if(view==='policy-progress'&&selected)renderScope();return;}if(view==='policy-progress'&&selected){const node=document.querySelector('#policy-report-detail .pr-chart-card');if(node)node.outerHTML=graphCard(scopedGroup(),{start:Number((policy()?.announced_at||'').slice(0,4)),end:policy()?.official_target_end_year});genericDecision();}});
    document.addEventListener('click',event=>{
      if(event.target.closest('[data-pr-clear-city]')){PolicySchematic.reset();return;}
      const area=event.target.closest('[data-pr-region]');if(area){document.querySelector('[data-ps-region="'+area.dataset.prRegion+'"]')?.click();return;}
      const p=event.target.closest('[data-pr-program]');if(p){PolicyGeo3D.choose('program-progress',p.dataset.prProgram);return;}
      const project=event.target.closest('[data-pr-project]');if(project){PolicyGeo3D.choose('projects',project.dataset.prProject);selectProject(project.dataset.prProject);return;}
      const policy=event.target.closest('[data-pr-policy]');if(policy){PolicyGeo3D.choose('policy-progress',policy.dataset.prPolicy);PolicyDashboard.select(policy.dataset.prPolicy);}
    });
  }
  return {programMembers:projectTree,start,setData,policyChanged,scopeChanged,selectProject,supplemental907,policyInfo:id=>monitor?.items?.find(row=>row.id===id)||null};
})();
