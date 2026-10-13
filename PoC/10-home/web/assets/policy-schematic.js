'use strict';
// Official municipality outlines, drawn as bounded prisms without map tiles.
const PolicySchematic=(()=>{
  let shape=null,metrics=null,policyId='',policyMeta=null,region='all',zoom=1,selectedCity='',stage='COMPLETION',focusYear=null;
  const fmt=n=>n==null?'미확보':num(n)+'호';
  const regions={'all':'전체','서울특별시':'서울','경기도':'경기','인천광역시':'인천'};
  const stages={CAPACITY:'계획',COMPLETION:'준공',SUPPLY:'모집'};
  const host=()=>document.getElementById('policy-geo-map');
  const now=()=>Number(($('as-of').value||new Date().toISOString().slice(0,10)).slice(0,4));
  const quantity=row=>row?.by_scope?.policy?.[policyId]||null;
  function bounds(rows){
    const points=rows.flatMap(row=>row.rings.flat());
    if(!points.length)return [126,36.8,128,38.4];
    return [Math.min(...points.map(p=>p[0])),Math.min(...points.map(p=>p[1])),Math.max(...points.map(p=>p[0])),Math.max(...points.map(p=>p[1]))];
  }
  function facts(city,group,itemIndex){
    const q=quantity(city),ids=new Set(city.project_ids||[]),scheduled=new Set(group?.chart_schedule_ids||[]);
    const noticeIds=new Set(),notices=[],completion=[],supply=[],moveIn=[];
    for(const id of ids){
      const item=itemIndex.get(id);if(!item)continue;
      if(item.notice_evidence_id&&item.current_notice_units!=null&&item.notice_source_date&&(!policyMeta?.announced_at||item.notice_source_date>=policyMeta.announced_at)&&!noticeIds.has(item.notice_evidence_id)){
        noticeIds.add(item.notice_evidence_id);notices.push({year:Number(item.notice_source_date.slice(0,4)),units:item.current_notice_units});
      }
      if(item.move_in_start?.date)moveIn.push({year:Number(item.move_in_start.date.slice(0,4))});
      if(!scheduled.has(id))continue;
      for(const point of item.annual_series||[]){
        for(const [key,list] of [['COMPLETION',completion],['SUPPLY',supply]])
          if(point[key]!=null)list.push({year:point.year,units:point[key]});
      }
    }
    const total=(rows,limit,after=-Infinity)=>{const values=rows.filter(row=>row.year<=limit&&row.year>after);return values.length?values.reduce((sum,row)=>sum+row.units,0):null;};
    const observed=total(notices,Math.min(focusYear,now()));
    const supplyPlanned=total(supply,focusYear);
    const completionPlanned=total(completion,focusYear);
    const futureSupply=focusYear>now()?total(supply,focusYear,now()):null;
    let visible=null,basis='';
    if(stage==='CAPACITY'){visible=supplyPlanned;basis=supplyPlanned==null?'연도별 공급 계획 미확보 · 전체 목표만 확인':'원천 연도가 확인된 공급 계획 누적';}
    else if(stage==='COMPLETION'){visible=completionPlanned;basis=completionPlanned==null?'준공 예정 연도·호수 미확보':'원천 준공 예정 누적 · 실제 준공량 아님';}
    else {visible=focusYear>now()?(observed==null?futureSupply:observed+(futureSupply||0)):observed;basis=focusYear>now()?'공고 확인 + 이후 모집 예정 · 예측 합계':'발표 이후 공고 확인 누적 · 연결 검토';}
    const annualRows=stage==='CAPACITY'?supply:stage==='COMPLETION'?completion:focusYear>now()?supply:notices;
    const hasAnnualChange=annualRows.some(row=>row.year===focusYear);
    const completionEnd=completion.length?Math.max(...completion.map(row=>row.year)):null;
    const moveInEnd=moveIn.length?Math.max(...moveIn.map(row=>row.year)):null;
    return {target:q?.target_units??null,observed,visible,basis,completionEnd,moveInEnd,hasAnnualChange,projectCount:q?.project_count||0};
  }
  function render(keepControls=false){
    if(!shape||!metrics||!host())return;
    if(focusYear==null)focusYear=now();
    focusYear=Math.min(now()+5,Math.max(now()-5,focusYear));
    const rows=shape.shapes.filter(row=>region==='all'||row.region===region).sort((a,b)=>(b.latitude||0)-(a.latitude||0));
    if(!rows.length){host().innerHTML='<div class="ps-head"><strong>지역별 정책 공급 분포</strong></div><div class="ps-regions">'+Object.entries(regions).map(([id,label])=>'<button data-ps-region="'+id+'" class="'+(id===region?'active':'')+'">'+label+'</button>').join('')+'</div><div class="pd-geometry-empty">'+esc(regions[region]||region)+' 지역의 연결 도형·지표 미확보<br>다른 지역을 선택하거나 원천 연결을 확인하세요.</div>';return;}
    const [west,south,east,north]=bounds(rows),dx=Math.max(.001,east-west),dy=Math.max(.001,north-south);
    const scale=Math.min(535/dx,330/dy)*zoom,cx=(west+east)/2,cy=(south+north)/2;
    const X=v=>310+(v-cx)*scale,Y=v=>260-(v-cy)*scale;
    const stageMetrics=stage==='COMPLETION'?metrics.COMPLETION:metrics.SUPPLY;
    if(!stageMetrics){host().textContent='선택 기준의 지역 자료 미확보';return;}
    const byId=new Map(stageMetrics.municipalities.map(row=>[row.id,row]));
    const itemIndex=new Map(stageMetrics.items.map(row=>[row.id,row]));
    const group=stageMetrics.groups.policy.find(row=>row.id===policyId);
    const enriched=rows.map(row=>({row,facts:facts(byId.get(row.id)||{},group,itemIndex)}));
    const max=Math.max(1,...enriched.flatMap(item=>[item.facts.target||0,item.facts.visible||0]));
    const face=(p,q,offsetA,offsetB,color)=>'<path d="M'+(p[0]+offsetA[0]).toFixed(1)+' '+(p[1]+offsetA[1]).toFixed(1)+'L'+(q[0]+offsetA[0]).toFixed(1)+' '+(q[1]+offsetA[1]).toFixed(1)+'L'+(q[0]+offsetB[0]).toFixed(1)+' '+(q[1]+offsetB[1]).toFixed(1)+'L'+(p[0]+offsetB[0]).toFixed(1)+' '+(p[1]+offsetB[1]).toFixed(1)+'Z" fill="'+color+'" stroke="'+color+'" stroke-width=".3"/>';
    const paths=enriched.map(({row,facts:f})=>{
      const target=f.target,reference=target??(f.visible>0?f.visible:null);
      const ratio=reference==null?0:Math.sqrt(Math.max(0,reference)/max),height=reference==null?5:Math.round(23+48*ratio);
      const offset=[Math.round(height*.16),height],visibleRatio=reference>0&&f.visible!=null?Math.min(1,Math.max(0,f.visible/reference)):0;
      const ghostFill=target==null?'#e6eef2':f.visible==null?'url(#ps-unknown)':'#e5f1f6';
      const ghostWall=target==null?'#d3e0e6':'#9ebed0';
      const topColor=stage==='CAPACITY'?'#4c9cc9':stage==='COMPLETION'?'#47aea8':'#357ed4';
      const wallColor=stage==='CAPACITY'?'#286b9d':stage==='COMPLETION'?'#168b86':'#1b5fa6';
      const top=[],progressTop=[],sides=[];
      const progressOffset=[offset[0]*(1-visibleRatio),offset[1]*(1-visibleRatio)];
      for(const ring of row.rings){
        const points=ring.map(p=>[X(p[0]),Y(p[1])]);
        if(points.length<4)continue;
        const area=points.slice(0,-1).reduce((sum,p,i)=>sum+p[0]*points[i+1][1]-points[i+1][0]*p[1],0);
        const pathAt=shift=>points.map((p,i)=>(i?'L':'M')+(p[0]+shift[0]).toFixed(1)+' '+(p[1]+shift[1]).toFixed(1)).join('')+'Z';
        top.push(pathAt([0,0]));
        if(visibleRatio>0)progressTop.push(pathAt(progressOffset));
        for(let i=0;i<points.length-1;i++){
          const a=points[i],b=points[i+1],cross=(b[0]-a[0])*offset[1]-(b[1]-a[1])*offset[0];
          if(cross*Math.sign(area)>=0)continue;
          sides.push(face(a,b,[0,0],offset,ghostWall));
          if(visibleRatio>0)sides.push(face(a,b,progressOffset,offset,wallColor));
        }
      }
      const selected=row.id===selectedCity;
      const aria=row.name+' · 전체 사업계획 '+fmt(target)+' · '+focusYear+'년 '+stages[stage]+' 누적 '+fmt(f.visible)+' · '+f.basis;
      return '<g class="ps-district'+(target!=null?' has-supply':'')+(selected?' selected':'')+'" data-ps-city="'+esc(row.id)+'" data-ps-visible="'+(f.visible==null?'missing':f.visible)+'" data-ps-height="'+Math.round(height*visibleRatio)+'" tabindex="0" role="button" aria-label="'+esc(aria)+'">'+sides.join('')+'<path class="ps-top" d="'+top.join(' ')+'" fill="'+ghostFill+'" stroke="'+(selected?'#f5a13a':'#f8fcff')+'" stroke-width="'+(selected?2.5:1.2)+'"/>'+(progressTop.length?'<path class="ps-progress-top" d="'+progressTop.join(' ')+'" fill="'+topColor+'" stroke="'+(selected?'#f5a13a':'#f8fcff')+'" stroke-width="'+(selected?1.5:.8)+'"/>':'')+'<title>'+esc(aria)+'</title></g>';
    }).join('');
    const marked=enriched.filter(item=>item.facts.target!=null).sort((a,b)=>b.facts.target-a.facts.target);
    const names=new Set(marked.slice(0,region==='all'?13:24).map(item=>item.row.id));
    if(selectedCity)names.add(selectedCity);
    const text=enriched.filter(item=>names.has(item.row.id)).map(({row,facts:f})=>{
      const longitude=row.longitude??row.rings[0][0][0],latitude=row.latitude??row.rings[0][0][1];
      const title=row.name.replace(/^(서울특별시|경기도)\s*/,'');
      return '<g class="ps-label" transform="translate('+X(longitude).toFixed(1)+' '+(Y(latitude)-11).toFixed(1)+')"><text text-anchor="middle">'+esc(title)+'</text>'+(f.visible==null?'':'<text y="13" text-anchor="middle" class="ps-units">'+esc(fmt(f.visible))+'</text>')+'</g>';
    }).join('');
    const chosen=selectedCity&&enriched.find(item=>item.row.id===selectedCity);
    const detail=chosen?'<div class="ps-selected"><b>'+esc(chosen.row.name)+'</b><span>전체 목표 '+fmt(chosen.facts.target)+' · '+focusYear+'년 '+stages[stage]+' 누적 '+fmt(chosen.facts.visible)+'</span><small>'+esc(chosen.facts.basis)+' · 발표 이후 공고 '+fmt(chosen.facts.observed)+'</small><button type="button" data-ps-close aria-label="지역 선택 해제">×</button></div>':'<div class="ps-hint">시군구를 선택하면 전체 목표와 선택 연도의 값을 비교할 수 있습니다.</div>';
    const controls='<div class="ps-controls"><fieldset class="ps-stage-control"><legend>지역 그래프 기준</legend>'+Object.entries(stages).map(([value,label])=>'<label><input type="radio" name="ps-stage" value="'+value+'"'+(stage===value?' checked':'')+'><span>'+label+'</span></label>').join('')+'</fieldset><div class="ps-year-control"><label for="ps-year">기준 연도 <strong id="ps-year-value">'+focusYear+(focusYear===now()?' · 현재':focusYear<now()?' · 과거':' · 미래')+'</strong></label><input id="ps-year" type="range" min="'+(now()-5)+'" max="'+(now()+5)+'" step="1" value="'+focusYear+'" aria-label="정책 지역 그래프 기준 연도"><div class="ps-year-limits"><span>'+(now()-5)+' · 과거 5년</span><span>'+now()+' · 현재</span><span>'+(now()+5)+' · 미래 5년</span></div></div></div>';
    const known=enriched.filter(item=>item.facts.visible!=null).length;
    const changed=enriched.filter(item=>item.facts.hasAnnualChange).length;
    const status=stages[stage]+' · '+focusYear+'년: 연도별 값 확인 '+known+'/'+enriched.length+'개 시군구 · '+(changed?focusYear+'년 새 근거 '+changed+'개 시군구':'이 연도에 새로 확인된 일정 없음');
    const basis=status+'. 진한 입체 높이는 선택 연도 누적, 옅은 외형은 사업계획 전체 목표입니다. '+(stage==='COMPLETION'?'원천 준공 예정이며 실제 준공량은 미연계입니다.':stage==='SUPPLY'?'미래 물량은 공식 모집 예정 일정이며 실제 공고와 구분합니다.':'연도별 공급 계획이 없는 사업의 물량은 전체 목표에만 남습니다.');
    const svgBody='<defs><linearGradient id="ps-water" x2="1" y2="1"><stop stop-color="#f7fbfe"/><stop offset="1" stop-color="#eaf4f9"/></linearGradient><pattern id="ps-unknown" width="6" height="6" patternUnits="userSpaceOnUse"><rect width="6" height="6" fill="#e8f1f5"/><path d="M0 6L6 0" stroke="#cddfe7" stroke-width="1"/></pattern></defs><rect width="620" height="500" fill="url(#ps-water)"/>'+paths+text;
    if(keepControls&&host().querySelector('.ps-map')){
      host().querySelector('.ps-map').innerHTML=svgBody;
      host().querySelector('.ps-selected, .ps-hint').outerHTML=detail;
      host().querySelector('.ps-basis').textContent=basis;
      return;
    }
    host().innerHTML='<div class="ps-head"><div><strong>지역별 정책 공급 분포</strong><small>진한 높이: 선택 연도 누적 · 옅은 외형: 전체 목표</small></div><div class="ps-zoom"><button type="button" data-ps-zoom="out" aria-label="축소">−</button><button type="button" data-ps-zoom="in" aria-label="확대">＋</button></div></div><div class="ps-regions" role="group" aria-label="지도 범위">'+Object.entries(regions).map(([id,label])=>'<button type="button" data-ps-region="'+id+'" class="'+(id===region?'active':'')+'">'+label+'</button>').join('')+'</div><div class="ps-canvas"><svg class="ps-map" viewBox="0 0 620 500" preserveAspectRatio="xMidYMid meet" role="img" aria-label="서울·경기 공식 시군구 경계별 정책 공급 입체 지도">'+svgBody+'</svg>'+detail+'</div>'+controls+'<p class="ps-basis">'+basis+'</p>';
  }
  function emit(){document.dispatchEvent(new CustomEvent('home:policy-schematic-change',{detail:{stage,year:focusYear,cityId:selectedCity||null,region}}));}
  function draw(nextShape,nextMetrics,nextPolicy,nextMeta){
    const changedPolicy=policyId!==nextPolicy;
    shape=nextShape;metrics=nextMetrics;policyId=nextPolicy;policyMeta=nextMeta||null;
    if(changedPolicy){selectedCity='';region='all';focusYear=now();}
    render();emit();
  }
  function reset(){region='all';zoom=1;selectedCity='';render();emit();}
  function clearSelection(){selectedCity='';render();emit();}
  function start(){
    const node=host();
    node.addEventListener('click',event=>{
      const scope=event.target.closest('[data-ps-region]');if(scope){region=scope.dataset.psRegion;zoom=1;selectedCity='';render();emit();return;}
      const button=event.target.closest('[data-ps-zoom]');if(button){zoom=Math.min(1.35,Math.max(1,zoom+(button.dataset.psZoom==='in'?.12:-.12)));render();return;}
      if(event.target.closest('[data-ps-close]')){selectedCity='';render();emit();return;}
      const place=event.target.closest('[data-ps-city]');if(place){selectedCity=place.dataset.psCity;render();emit();}
    });
    node.addEventListener('change',event=>{
      if(event.target.name==='ps-stage'){stage=event.target.value;render();emit();}
      if(event.target.id==='ps-year'){focusYear=Number(event.target.value);render();emit();}
    });
    node.addEventListener('input',event=>{if(event.target.id==='ps-year'){
      focusYear=Number(event.target.value);
      const label=node.querySelector('#ps-year-value');
      if(label)label.textContent=focusYear+(focusYear===now()?' · 현재':focusYear<now()?' · 과거':' · 미래');
      render(true);emit();
    }});
    node.addEventListener('keydown',event=>{const city=event.target.closest('[data-ps-city]');if(city&&(event.key==='Enter'||event.key===' ')){event.preventDefault();selectedCity=city.dataset.psCity;render();emit();}});
    node.addEventListener('wheel',event=>{if(!document.body.classList.contains('policy-summary-view'))return;event.preventDefault();const next=Math.min(1.35,Math.max(1,zoom+(event.deltaY<0?.08:-.08)));if(next!==zoom){zoom=next;render();}},{passive:false});
  }
  return {start,draw,reset,clearSelection};
})();
