'use strict';
const BlockMonitor=(()=>{
  const width=82,height=142,gap=12;
  const barHeightFor=row=>row.target_units>0?Math.max(10,Math.min(180,Math.round(65*row.target_units/1000))):65;
  const heightFor=row=>45+barHeightFor(row)+32;
  const value=n=>n==null?'—':num(n)+'호';
  const forecastColors=['#0085a4','#7955c6','#bc397c'];
  function status(p){
    if(p.late_count)return {code:'late',label:`지연 ${p.max_lag_months}개월`,color:'#cf402d'};
    if(p.schedule_gap_count)return {code:'review',label:`지연 검토 +${p.max_gap_months}개월`,color:'#a46c0b'};
    if(p.verification_count)return {code:'unknown',label:'이행 확인 필요',color:'#66758b'};
    if(p.early_count)return {code:'early',label:`조기 ${p.max_lead_months}개월`,color:'#087f67'};
    if(p.on_time_count)return {code:'normal',label:'정상 · 동월',color:'#1761bd'};
    return {code:'unknown',label:'일정 비교 미확보',color:'#66758b'};
  }
  function graph(row){
    const p=row.progress,projection=row.projection,capacity=row.target_units;
    const known=capacity!=null&&capacity>0,observed=p.observed_units,goal=p.cumulative_goal_units,s=status(p);
    const left=31,barWidth=10,top=45,barHeight=barHeightFor(row),base=top+barHeight,svgHeight=heightFor(row);
    const y=n=>base-(known?Math.min(1,Math.max(0,n/capacity)):0)*barHeight;
    let previous=observed;
    let segments=known&&observed!=null?`<rect class="block-current-fill" x="${left}" y="${y(observed)}" width="${barWidth}" height="${base-y(observed)}" fill="${['early','normal','late'].includes(s.code)?s.color:'#1665ee'}"/>`:'';
    projection.future.slice(0,3).forEach((f,i)=>{
      if(!known||previous==null||f.cumulative_units==null)return;
      const height=Math.max(0,y(previous)-y(f.cumulative_units));
      segments+=`<rect class="block-future-fill" data-offset="${f.offset}" x="${left}" y="${y(f.cumulative_units)}" width="${barWidth}" height="${height}" fill="${forecastColors[i]}"/>`;
      previous=f.cumulative_units;
    });
    // Move only the text when forecast ticks coincide. The tick itself keeps
    // its exact quantity position, with a connector to its +N label.
    const ticks=projection.future.slice(0,3).filter(f=>known&&f.cumulative_units!=null&&observed!=null).map((f,i)=>({f,i,known:known&&f.cumulative_units!=null,
      at:known&&f.cumulative_units!=null?y(f.cumulative_units):top+12+i*12})).sort((a,b)=>a.at-b.at||a.i-b.i);
    ticks.forEach((tick,i)=>{tick.label=Math.max(top+5,tick.at,i?ticks[i-1].label+12:top+5);});
    if(ticks.length&&ticks[ticks.length-1].label>base-4){
      ticks[ticks.length-1].label=base-4;
      for(let i=ticks.length-2;i>=0;i--)ticks[i].label=Math.min(ticks[i].label,ticks[i+1].label-12);
    }
    const future=ticks.map(({f,i,known,at,label})=>`<g class="block-future-value" data-offset="${f.offset}" data-cumulative="${f.cumulative_units??''}" data-increment="${f.increment_units??''}">${known?`<path class="block-future-tick" data-value="${f.cumulative_units}" d="M${left+barWidth} ${at}h5l5 ${label-at}h3" fill="none" stroke="${forecastColors[i]}" stroke-width="1.5"/>`:''}<text x="55" y="${label+3}" class="block-year-tick" fill="${known?forecastColors[i]:'#687b91'}">+${f.offset}${known?'':'?'}</text></g>`).join('');
    const district=row.district_name.replace(/(?:공공주택지구|택지개발지구)$/,'');
    const name=district.length>10?district.slice(0,9)+'…':district;
    const shortStatus={early:'조기',normal:'정상',late:'지연',review:'검토',unknown:''}[s.code];
    const statusKnown=['early','normal','late'].includes(s.code);
    const facts=[capacity!=null?'총 공급계획 '+value(capacity):'',goal!=null?'누적 목표 '+value(goal):'',observed!=null?'현재 확인 '+value(observed):'',statusKnown?s.label:''].filter(Boolean);
    return `<svg viewBox="0 0 ${width} ${svgHeight}" role="img" data-capacity-scale="1000" aria-label="${esc(row.name)}: ${esc(facts.join(', '))}" class="block-glyph block-vertical-glyph" data-block-id="${esc(row.id)}" data-status="${statusKnown?s.code:'unclassified'}"><text x="41" y="10" text-anchor="middle" class="block-district">${esc(name)}</text><text x="41" y="28" text-anchor="middle" class="block-code">${esc(row.block)}</text>${statusKnown?`<circle cx="6" cy="24" r="3" fill="${s.color}"/><text x="79" y="26" text-anchor="end" class="block-status-text" fill="${s.color}">${shortStatus}</text>`:''}${capacity!=null?`<text x="41" y="40" text-anchor="middle" class="block-total">총 ${value(capacity)}</text>`:''}${known?`<rect class="block-capacity-bar" x="${left}" y="${top}" width="${barWidth}" height="${barHeight}" rx="1.5" fill="#d4dfe9" fill-opacity=".45" stroke="#7791a9"/>`:''}${segments}${known&&goal!=null?`<path class="block-goal-tick" data-goal="${goal}" d="M${left-4} ${y(goal)}h${barWidth+8}" stroke="#cb8c17" stroke-width="2"/><text x="5" y="${y(goal)+3}" class="block-goal-label">목표</text>`:''}${future}${observed!=null?`<text x="41" y="${base+14}" text-anchor="middle" class="block-observed">현재 ${value(observed)}</text>`:''}${goal!=null?`<text x="41" y="${base+27}" text-anchor="middle" class="block-goal">목표 ${value(goal)}</text>`:''}</svg>`;
  }
  const fact=(label,v,suffix='호')=>v==null?'':`<dt>${esc(label)}</dt><dd>${num(v)}${suffix}</dd>`;
  const knownMilestones=row=>(row.milestones||[]).filter(m=>m.actual_date||m.planned_month||['OBSERVED','REPORTED'].includes(m.status)||m.progress_pct!=null);
  function stages(row){
    return knownMilestones(row).map(m=>{
      const confirmed=['OBSERVED','REPORTED'].includes(m.status);
      const stamp=m.actual_date||(confirmed?'원천 확인'+(m.report_date?' · '+m.report_date:''):m.planned_month?'예정 '+m.planned_month:'');
      return `<dt>${esc(m.label)}</dt><dd>${esc(stamp)}${m.progress_pct!=null?(stamp?' · ':'')+'공사 '+num(m.progress_pct)+'%':''}</dd>`;
    }).join('');
  }
  function tooltip(row,data){
    const p=row.progress,s=status(p),statusKnown=['early','normal','late'].includes(s.code);
    return `<b>${esc(row.name)}${statusKnown?' · '+esc(s.label):''}</b><dl>${fact('총 공급계획',row.target_units)}${fact('현재 누적 목표',p.cumulative_goal_units)}${fact('올해 관리자 목표',p.annual_manual_goal_units)}${fact('현재 확인 '+(data.measure==='SUPPLY'?'모집공고':'실적'),p.observed_units)}${fact('확인 비율 · 하한',p.observed_pct,'%')}${row.projection.future.slice(0,3).map(f=>fact('+'+f.offset+'년 예상 누적',f.cumulative_units)+fact('+'+f.offset+'년까지 추가 예정',f.increment_units)+fact('+'+f.offset+'년 관리자 누적 목표',row.future?.[f.offset-1]?.manual_units)).join('')}${stages(row)}</dl><small>${esc(data.measure_label)} 기준 · 원천 연결 검토<br>지구 대표점 주변에 펼친 그래프 · 실제 블록 위치 미확정</small>`;
  }
  function stageDetails(row){
    const content=stages(row);
    return content?`<details class="block-stage-details"><summary>단계별 일정·공사율</summary><dl class="map-milestone-details">${content}</dl></details>`:'';
  }

  function layout(entries,bounds){
    const placed=[],hidden=[];
    const intersects=(a,b)=>a.x<b.x+b.width+gap&&a.x+a.width+gap>b.x&&a.y<b.y+b.height+gap&&a.y+a.height+gap>b.y;
    for(const entry of entries){
      const candidates=[];
      // A screen-space lattice keeps each graph independent. It never changes
      // geographic coordinates: each leader line ends at the district anchor.
      for(let y=bounds.top;y<=bounds.bottom-height;y+=height+gap)
        for(let x=bounds.left;x<=bounds.right-width;x+=width+gap)
          candidates.push({x,y,width,height,distance:(x+width/2-entry.point.x)**2+(y+height/2-entry.point.y)**2});
      candidates.sort((a,b)=>a.distance-b.distance||a.y-b.y||a.x-b.x);
      const slot=candidates.find(c=>!placed.some(other=>intersects(c,other.box)));
      if(slot)placed.push({...entry,box:slot});else hidden.push(entry);
    }
    return {placed,hidden};
  }
  return {width,height,status,graph,tooltip,stageDetails,layout,barHeightFor,heightFor};
})();
