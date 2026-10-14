'use strict';
const MapMonitor=(()=>{
  const colors=['#1665ee','#21a9ca','#8265d5','#ce649a'];
  const units=value=>value==null?'미확보':num(value)+'호';
  const percent=value=>value==null?'—':num(value)+'%';
  const wideZoom=zoom=>zoom-Math.log2(1.5);
  const levelAt=zoom=>zoom<wideZoom(10)?'region':zoom<wideZoom(13)?'municipality':'block';
  function initialize(){
    if($('map-policy-monitor'))return;
    const panel=document.createElement('section');panel.id='map-policy-monitor';panel.className='map-info-card policy-monitor';
    document.querySelector('#map-panel-content').prepend(panel);
  }
  function panel(data,viewport){
    initialize();
    MapProgressTracking.panel(data,viewport);
    MapAreaContext.panel(data,viewport);
  }
  function arc(cx,cy,r,start,end){
    if(end<=start)return '';
    if(end-start>=.9999)return `<circle cx="${cx}" cy="${cy}" r="${r}"/>`;
    const point=f=>[cx+r*Math.sin(f*2*Math.PI),cy-r*Math.cos(f*2*Math.PI)];
    const a=point(start),b=point(end);
    return `<path d="M${cx} ${cy}L${a[0]} ${a[1]}A${r} ${r} 0 ${end-start>.5?1:0} 1 ${b[0]} ${b[1]}Z"/>`;
  }
  function circle(row,r){return MapStageRing.svg(row,Math.max(48,2*r+14));}
  function tooltip(row,data){return `<b>${esc(row.name)}</b>${MapStageRing.details(row)}`;}
  function draw(map,pins,data,ids,choose,markerIndex,selectedId){
    const level=levelAt(map.getZoom());
    $('map-bar-level').textContent=({region:'시도 2D 현황',municipality:'시군구 2D 현황',district:'지구·블록 위치 검토',block:'블록 상세 · 용지 입체 참고'}[level])+' · 확대 '+map.getZoom();
    $('map-view-status').textContent={region:'시도별 2D 공급 현황',municipality:'시군구별 2D 공급 현황',district:'지구·블록 선택 · 2D',block:'블록별 공급 현황 · 용지도형 참고(건물 아님)'}[level];
    document.querySelectorAll('[data-bar-level]').forEach(button=>{button.classList.toggle('selected',button.dataset.barLevel===level);button.setAttribute('aria-pressed',String(button.dataset.barLevel===level));});
    if(level==='region'){
      for(const region of data.groups.region.map(SupplyBars.scoped).filter(row=>row&&row.project_count)){
        let cities=data.municipalities.filter(area=>area.region===region.id&&area.project_ids.some(id=>ids.has(id)));
        if(!cities.length)cities=data.municipalities.filter(area=>area.region===region.id&&Number.isFinite(area.latitude)&&Number.isFinite(area.longitude));
        if(!cities.length)continue;
        const latitude=cities.reduce((sum,row)=>sum+row.latitude,0)/cities.length;
        const longitude=cities.reduce((sum,row)=>sum+row.longitude,0)/cities.length;
        const value=region.projection?.baseline_pct;
        const icon=L.divIcon({className:'map-region-summary-marker',iconSize:[138,76],iconAnchor:region.id==='서울특별시'?[138,76]:[0,0],html:`<button class="map-region-summary-button" type="button" aria-label="${esc(region.name)} 시군구 보기"><b>${esc(({'서울특별시':'서울','인천광역시':'인천','경기도':'경기'}[region.name]||region.name))}</b><small>계획 ${units(region.target_units)}</small><small>${esc(MapStageRing.metric(region).label)} ${esc(MapStageRing.metric(region).text)}</small></button>`});
        const marker=L.marker([latitude,longitude],{icon,keyboard:true}).addTo(pins);
        marker.bindTooltip(tooltip(region,data),{direction:'top',className:'municipality-tooltip'});
        marker.on('click',()=>map.fitBounds(L.latLngBounds(cities.map(row=>[row.latitude,row.longitude])),{padding:[32,32],maxZoom:11}));
      }
      return;
    }
    if(level==='municipality'){
      const areas=data.municipalities.map(SupplyBars.scoped).filter(row=>row&&row.project_count);
      const max=Math.max(1,...areas.map(row=>row.target_units||0));
      const boxes=[];
      for(const area of areas.sort((a,b)=>(b.target_units||0)-(a.target_units||0))){
        const r=area.target_units?Math.max(6,48*Math.sqrt(area.target_units/max)):10,size=2*r+14;
        const label=area.target_units!=null?units(area.target_units):'';
        const future=area.projection.future.slice(0,3).filter(f=>f.cumulative_pct!=null).map(f=>`<span class="native-future f${f.offset}">+${f.offset} ${percent(f.cumulative_pct)}</span>`).join(' ');
        const point=map.latLngToContainerPoint([area.latitude,area.longitude]);
        const box={left:point.x-Math.max(size,120)/2,right:point.x+Math.max(size,120)/2,top:point.y-size/2-18,bottom:point.y+size/2+50};
        const annotate=map.getZoom()>=11||!boxes.some(other=>box.left<other.right&&box.right>other.left&&box.top<other.bottom&&box.bottom>other.top);
        if(annotate)boxes.push(box);
        const marker=L.marker([area.latitude,area.longitude],{icon:L.divIcon({className:'municipality-chart-marker'+(annotate?'':' quiet'),iconSize:[size+36,size+70],iconAnchor:[(size+36)/2,size/2+18],html:`<div class="native-municipality-label">${esc(area.name)}</div>${circle(area,r)}${label?`<div class="native-municipality-target native-extra">전체 ${label}</div>`:''}${area.progress.cumulative_goal_units!=null?`<div class="native-municipality-goal native-extra">누적 목표 ${units(area.progress.cumulative_goal_units)}</div>`:''}${future?`<div class="native-projection-label native-extra">${future}</div>`:''}`}),title:area.name+' · '+label,keyboard:true}).addTo(pins);
        marker.bindTooltip(tooltip(area,data),{direction:'top',className:'municipality-tooltip'});
        marker.on('click',()=>{const district=data.districts.find(d=>d.project_ids.some(id=>ids.has(id)&&area.project_ids.includes(id)));map.setView([area.latitude,area.longitude],13,{animate:false});if(district)choose(area.project_ids.find(id=>ids.has(id)),district.name);});
      }
      return;
    }
    const bounds=map.getBounds().pad(.12);
    const visibleDistricts=data.districts.filter(district=>district.project_ids.some(id=>ids.has(id))&&(bounds.contains([district.latitude,district.longitude])||data.blocks.some(block=>block.district_name===district.name&&['BLOCK_BOUNDARY','OFFICIAL_ADDRESS_POINT','LH_PUBLIC_BLOCK_LABEL_POINT','APPROXIMATE_ADDRESS','APPROXIMATE_AREA'].includes(block.coordinate_basis)&&Number.isFinite(block.latitude)&&Number.isFinite(block.longitude)&&bounds.contains([block.latitude,block.longitude]))));
    if(level==='district'){
      for(const district of visibleDistricts){
        const blocks=data.blocks.filter(block=>block.district_name===district.name&&block.project_ids.some(id=>ids.has(id)));
        if(!blocks.length)continue;
        const firstBlock=blocks.find(row=>row.coordinate_basis==='LH_PUBLIC_BLOCK_LABEL_POINT')||blocks[0];
        const first=firstBlock.project_ids.find(id=>ids.has(id));
        const selected=blocks.some(row=>row.project_ids.includes(selectedId));
        const marker=L.marker([district.latitude,district.longitude],{icon:L.divIcon({className:'map-district-marker',iconSize:[112,54],iconAnchor:[56,27],html:`<button class="map-district-choice${selected?' selected':''}" type="button" aria-label="${esc(district.name)} ${blocks.length}개 블록 선택"><b>${esc(district.name)}</b><small>${blocks.length}개 블록 · 위치 검토</small></button>`}),keyboard:true}).addTo(pins);
        marker.on('click',()=>{choose(first,district.name);map.setView([firstBlock.latitude,firstBlock.longitude],16,{animate:false});});
      }
      $('map-bar-level').textContent=`지구별 블록 선택 · 확대 ${map.getZoom()} · 위치 근거 검토`;
      return;
    }
    let located=0,unlocated=0;
    for(const district of visibleDistricts){
      const blocks=data.blocks.filter(block=>block.district_name===district.name&&block.project_ids.some(id=>ids.has(id)));
      const first=blocks[0]?.project_ids.find(id=>ids.has(id));
      const unresolved=blocks.filter(row=>!['BLOCK_BOUNDARY','OFFICIAL_ADDRESS_POINT','LH_PUBLIC_BLOCK_LABEL_POINT','APPROXIMATE_ADDRESS','APPROXIMATE_AREA'].includes(row.coordinate_basis));
      if(unresolved.length){
        unlocated+=unresolved.length;
        const selected=blocks.some(row=>row.project_ids.includes(selectedId));
        const marker=L.marker([district.latitude,district.longitude],{icon:L.divIcon({className:'map-district-marker',iconSize:[128,54],iconAnchor:[64,27],html:`<button class="map-district-choice${selected?' selected':''}" type="button" aria-label="${esc(district.name)} 블록 목록"><b>${esc(district.name)}</b><small>${unresolved.length}개 블록 · 위치 미연계</small></button>`}),keyboard:true}).addTo(pins);
        marker.on('click',()=>choose(first,district.name));
      }
      for(const row of blocks.map(SupplyBars.scoped).filter(Boolean)){
        if(!['BLOCK_BOUNDARY','OFFICIAL_ADDRESS_POINT','LH_PUBLIC_BLOCK_LABEL_POINT','APPROXIMATE_ADDRESS','APPROXIMATE_AREA'].includes(row.coordinate_basis)||!Number.isFinite(row.latitude)||!Number.isFinite(row.longitude))continue;
        located++;
        const point=[row.latitude,row.longitude],s=BlockMonitor.status(row.progress);
        const marker=L.marker(point,{icon:L.divIcon({className:'native-block-marker independent-block-marker status-'+s.code,iconSize:[BlockMonitor.width,BlockMonitor.height],iconAnchor:[BlockMonitor.width/2,BlockMonitor.height],html:`<button class="native-block-row" type="button" aria-label="${esc(row.name)} 상세 현황">${BlockMonitor.graph(row)}</button>`}),keyboard:true}).addTo(pins);
        marker.bindTooltip(BlockMonitor.tooltip(row,data),{direction:'top',className:'municipality-tooltip block-evidence-tooltip'});
        marker.on('click',()=>choose(row.project_ids.find(id=>ids.has(id)),district.name));
        markerIndex.set(row.id,marker);
      }
    }
    $('map-bar-level').textContent=`블록 상세 · 확대 ${map.getZoom()} · 개별 블록 라벨 ${located}개 · 위치 미연계 ${unlocated}개`;

  }

  function start(setLevel){document.addEventListener('click',event=>{const button=event.target.closest('[data-bar-level]');if(button)setLevel(button.dataset.barLevel);const tab=event.target.closest('[data-monitor-policy]');if(tab)MapSupply.select('policy',tab.dataset.monitorPolicy);});}
  return {draw,panel,start,levelAt,wideZoom};
})();
