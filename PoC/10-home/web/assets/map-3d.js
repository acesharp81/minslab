'use strict';
// Continuous 3D supply map. Apartment masses are illustrative, not surveyed
// buildings, official layouts, construction progress, or a source of unit counts.
const MapThreeD=(()=>{
  let library,gl,opening,active=false,data,selectedId,selectedDistrict,choose,onViewport;
  let markers=[],visibleIds=new Set(),modelSignature='',contextBlockId='',contextTicket=0,modelFeatures=[],generation=0;
  let infraBlockId='',infraTicket=0,infraItems=[],infraSource=null,infraState='loading',infraBound=false;
  let selectedRegionId='',selectedMunicipalityId='',overlapPopup=null,resizeObserver=null;
  let radiusSignature='',contextRadius=500,contextRadiusLinked=false;
  let blockMarkers=[],leaderSvg=null,layoutFrame=0;
  let contextTransparency=50,markerLevel='',requestedLevel='region';
  let pendingFocus=null;
  const cameraMotion={duration:1200,easing:t=>t*t*(3-2*t)};
  function moveCamera(options){gl.easeTo({...cameraMotion,...options});}
  const transparencyKey='home-map-existing-building-transparency';
  const withinContext=p=>Number.isFinite(p.distance_m)&&p.distance_m<=contextRadius;
  const visibleInfrastructure=()=>{const nearest=infraItems.filter(p=>p.kind==='subway').sort((a,b)=>a.distance_m-b.distance_m)[0];return infraItems.filter(p=>withinContext(p)||p===nearest);};
  const planned=()=>(infraSource?.planned_facilities||[]).filter(p=>withinContext(p)||p.distance_m==null);
  const planStamp=p=>(p.kind==='school'?'개교':'개원')+' 예정 '+(p.opening_date||'미정');
  const contextCache=new Map();
  const facilityMethods=new Map();
  const empty=()=>({type:'FeatureCollection',features:[]});
  const located=row=>['LH_PUBLIC_BLOCK_LABEL_POINT','BLOCK_BOUNDARY','OFFICIAL_ADDRESS_POINT','APPROXIMATE_ADDRESS','APPROXIMATE_AREA'].includes(row?.coordinate_basis)&&Number.isFinite(row.latitude)&&Number.isFinite(row.longitude);
  const precise=row=>row?.coordinate_basis==='LH_PUBLIC_BLOCK_LABEL_POINT'&&located(row);
  const locationLabel=row=>row?.location_label||(precise(row)?'LH 블록 라벨 위치':row?.coordinate_basis?.startsWith('APPROXIMATE')?'근사 위치':'사업 대표 위치');
  function status(message,kind='info'){
    const node=$('map-3d-status');if(!node)return;
    node.hidden=!message;node.textContent=message||'';node.dataset.kind=kind;
  }
  function surface(visible){
    document.querySelector('.housing-map-body')?.classList.toggle('map-3d-active',visible);
    $('map-3d-camera').hidden=!visible;$('map-3d-legend').hidden=!visible;
    $('map-3d-exit').hidden=true;$('map-infrastructure-panel').hidden=!visible;
  }
  async function loadLibrary(){
    if(library)return library;
    if(!document.querySelector('[data-maplibre-css]')){
      const css=document.createElement('link');css.rel='stylesheet';css.href='/poc/home/assets/vendor/maplibre/maplibre-gl.css';css.dataset.maplibreCss='true';document.head.append(css);
    }
    library=await import('/poc/home/assets/vendor/maplibre/maplibre-gl.mjs');
    library.setWorkerUrl('/poc/home/assets/vendor/maplibre/maplibre-gl-worker.mjs');
    return library;
  }
  // Geodesic rings stay on the ground, independent of marker display offsets.
  function radiusGeometry(block){
    if(!located(block))return empty();
    const lat=block.latitude*Math.PI/180,lon=block.longitude*Math.PI/180;
    return {type:'FeatureCollection',features:[500,1000,3000].map(radius=>{
      const angular=radius/6371000,coordinates=[];
      for(let i=0;i<=128;i++){
        const bearing=2*Math.PI*i/128;
        const phi=Math.asin(Math.sin(lat)*Math.cos(angular)+Math.cos(lat)*Math.sin(angular)*Math.cos(bearing));
        const lambda=lon+Math.atan2(Math.sin(bearing)*Math.sin(angular)*Math.cos(lat),Math.cos(angular)-Math.sin(lat)*Math.sin(phi));
        coordinates.push([lambda*180/Math.PI,phi*180/Math.PI]);
      }
      return {type:'Feature',properties:{radius_m:radius,label:radius===500?'500m':radius===1000?'1km':'3km'},geometry:{type:'LineString',coordinates}};
    })};
  }
  function updateRadius(){
    const block=selectedBlock(),signature=located(block)?block.id+':'+block.latitude+':'+block.longitude:'';
    if(signature===radiusSignature)return;
    radiusSignature=signature;gl.getSource('selection-radius')?.setData(radiusGeometry(block));
  }
  function radiusLabels(){
    const block=selectedBlock();if(!located(block))return;
    if(MapMonitor.levelAt(gl.getZoom())!=='block'){const origin=document.createElement('span');origin.className='map-radius-origin';origin.textContent=block.block==='대표 위치'?block.district_name:block.district_name+' '+block.block;marker(origin,block.longitude,block.latitude,'bottom');}
    for(const feature of radiusGeometry(selectedBlock()).features){
      const node=document.createElement('span');node.className='map-radius-label radius-'+feature.properties.radius_m;
      node.textContent=feature.properties.label;node.title='선택 사업 대표 위치 기준 직선 반경';
      const [lon,lat]=feature.geometry.coordinates[32];marker(node,lon,lat,'center');
    }
  }
  function blockProjectId(block){
    return (block.chart_target_ids||[]).find(id=>visibleIds.has(id))||block.project_ids.find(id=>visibleIds.has(id));
  }
  function blockButton(row,id){
    const element=document.createElement('button');element.type='button';element.className='map-3d-block-marker map-scene-block';
    element.style.height=BlockMonitor.heightFor(row)+'px';element.dataset.mapBarProject=id;element.dataset.mapBarBlock=row.id;element.dataset.mapBarSources=JSON.stringify(row.project_ids);
    element.setAttribute('aria-label',row.name+' · '+(row.target_units==null?'물량 미확보':num(row.target_units)+'호'));
    element.setAttribute('aria-pressed',String(row.project_ids.includes(selectedId)));element.title=row.name+' · '+locationLabel(row)+' · 연결 원천 '+row.project_ids.length+'건';
    element.classList.toggle('selected',row.project_ids.includes(selectedId));element.innerHTML=BlockMonitor.graph(row);
    element.addEventListener('click',event=>{event.stopPropagation();overlapPopup?.remove();overlapPopup=null;choose?.(id,row.district_name);});
    return element;
  }
  function modelFor(block,offset=[0,0]){
    if(!located(block)||!Number.isFinite(block.target_units)||block.target_units<=0)return [];
    // One shared volume scale: at most 200 homes per mass, 8 homes / 3m.
    // Equal footprints and no count/height clamp preserve total volume ratios.
    // These are visual equivalents, never actual building plans or supply facts.
    const count=Math.ceil(block.target_units/200),columns=Math.ceil(Math.sqrt(count)),rows=Math.ceil(count/columns);
    const unitsPerMass=block.target_units/count;
    const latStep=1/111320,lonStep=1/(111320*Math.cos(block.latitude*Math.PI/180));
    return Array.from({length:count},(_,index)=>{
      const col=index%columns,row=Math.floor(index/columns),rowCount=Math.min(columns,count-row*columns);
      const cx=(col-(rowCount-1)/2)*34+offset[0],cy=(row-(rows-1)/2)*54+offset[1];
      const halfW=6.5,halfD=21,height=unitsPerMass/8*3,angle=0;
      const corners=[[-halfW,-halfD],[halfW,-halfD],[halfW,halfD],[-halfW,halfD],[-halfW,-halfD]]
        .map(([x,y])=>{const east=cx+x*Math.cos(angle)-y*Math.sin(angle),north=cy+x*Math.sin(angle)+y*Math.cos(angle);return [block.longitude+east*lonStep,block.latitude+north*latStep];});
      return {type:'Feature',id:`${block.id}:${index}`,geometry:{type:'Polygon',coordinates:[corners]},
        properties:{block_id:block.id,block:block.block,district: block.district_name,target_units:block.target_units,
          render_height_m:height,represented_units:unitsPerMass,units_per_full_mass:200,model_status:'ILLUSTRATIVE',location_basis:block.coordinate_basis,location_label:locationLabel(block),units_known:Number.isFinite(block.target_units),display_offset_east_m:offset[0],display_offset_north_m:offset[1],original_longitude:block.longitude,original_latitude:block.latitude}};
    });
  }
  // Layout only intersecting screen rectangles. Geographic anchors never move.
  function layoutBlockMarkers(){
    if(!gl||!active||!blockMarkers.length)return;
    if(!leaderSvg){leaderSvg=document.createElementNS('http://www.w3.org/2000/svg','svg');leaderSvg.classList.add('map-block-leaders');gl.getCanvasContainer().append(leaderSvg);}
    leaderSvg.replaceChildren();
    const placed=[],gap=6,canvas=gl.getContainer();
    const intersects=(a,b)=>a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;
    for(const entry of blockMarkers){
      const point=gl.project([entry.row.longitude,entry.row.latitude]),w=BlockMonitor.width,h=BlockMonitor.heightFor(entry.row);
      const original={x:point.x-w/2,y:point.y-h-16,w,h};let box=original;
      if(point.x>-w&&point.x<canvas.clientWidth+w&&point.y>-h&&point.y<canvas.clientHeight+h){
        // Candidate edges give the smallest translation needed to clear a bar.
        if(placed.some(other=>intersects(original,other))){
          const candidates=[];
          for(const other of placed){
            const xs=[original.x,other.x-w-gap,other.x+other.w+gap],ys=[original.y,other.y-h-gap,other.y+other.h+gap];
            for(const x of xs)for(const y of ys)candidates.push({x,y,w,h,d:(x-original.x)**2+(y-original.y)**2});
          }
          candidates.sort((a,b)=>a.d-b.d||a.x-b.x||a.y-b.y);
          box=candidates.find(c=>!placed.some(other=>intersects(c,other)))||original;
        }
        placed.push(box);
      }
      const dx=box.x-original.x,dy=box.y-original.y;entry.marker.setOffset([dx,dy-16]);entry.element.dataset.displayOffset=dx.toFixed(1)+','+dy.toFixed(1);
      const selected=entry.row.project_ids?.includes(selectedId),color=selected?'#d8432f':'#27658c';
      const line=document.createElementNS('http://www.w3.org/2000/svg','line');
      for(const [key,value] of Object.entries({x1:point.x,y1:point.y,x2:point.x+dx,y2:point.y+dy-16,stroke:color,'stroke-width':selected?2.5:1.5,'data-anchor-block':entry.row.id}))line.setAttribute(key,String(value));
      leaderSvg.append(line);
      const dot=document.createElementNS('http://www.w3.org/2000/svg','circle');
      for(const [key,value] of Object.entries({cx:point.x,cy:point.y,r:selected?6:4,fill:color,stroke:'#fff','stroke-width':2,'data-ground-block':entry.row.id}))dot.setAttribute(key,String(value));
      leaderSvg.append(dot);

    }
  }
  function scheduleBlockLayout(){if(layoutFrame)return;layoutFrame=requestAnimationFrame(()=>{layoutFrame=0;layoutBlockMarkers();});}
  function openOverlap(rows,lngLat){
    overlapPopup?.remove();
    const node=document.createElement('div');node.className='map-overlap-picker';
    const choices=rows.filter(row=>blockProjectId(row));
    const heading=document.createElement('strong');heading.textContent='이 위치의 블록 '+choices.length+'개';node.append(heading);
    const explanation=document.createElement('p');explanation.textContent='위치가 겹치는 블록을 각각 선택할 수 있습니다. 같은 블록의 분양·건설 원천은 하나의 막대로 표시합니다.';node.append(explanation);
    const list=document.createElement('div');list.className='map-overlap-list';node.append(list);
    for(const row of choices){
      const id=blockProjectId(row),button=document.createElement('button');button.type='button';button.dataset.overlapProject=id;button.setAttribute('aria-pressed',String(row.project_ids.includes(selectedId)));
      const name=document.createElement('b');name.textContent=row.name;
      const info=document.createElement('small');info.textContent=(row.target_units!=null?num(row.target_units)+'호':'물량 미확보')+' · '+locationLabel(row)+' · 연결 원천 '+row.project_ids.length+'건';
      button.append(name,info);button.addEventListener('click',()=>{overlapPopup?.remove();overlapPopup=null;choose?.(id,row.district_name);});list.append(button);
      const sources=document.createElement('details'),summary=document.createElement('summary');summary.textContent='연결 원천 '+row.project_ids.length+'건 보기';sources.append(summary);
      for(const sourceId of row.project_ids){const item=data.items?.find(p=>p.id===sourceId);if(!item)continue;const entry=document.createElement('p');entry.textContent=item.name+' · '+(item.planned_units==null?'물량 미확보':num(item.planned_units)+'호');sources.append(entry);}
      list.append(sources);
    }
    overlapPopup=new library.Popup({maxWidth:'370px',closeOnClick:false,focusAfterOpen:true}).setLngLat(lngLat||[rows[0].longitude,rows[0].latitude]).setDOMContent(node).addTo(gl);
    list.querySelector('button')?.focus();
  }
  function clearMarkers(){for(const marker of markers)marker.remove();markers=[];blockMarkers=[];leaderSvg?.replaceChildren();}
  function marker(element,longitude,latitude,anchor='bottom'){
    const result=new library.Marker({element,anchor}).setLngLat([longitude,latitude]).addTo(gl);markers.push(result);return result;
  }
  function selectedBlock(){return data?.blocks.find(row=>row.project_ids.includes(selectedId)&&row.district_name===selectedDistrict);}
  function selectBlock(block){const id=block.project_ids.find(value=>visibleIds.has(value));if(id)choose?.(id,block.district_name);}
  const infraTypes={subway:{icon:'🚇',label:'지하철'},bus:{icon:'🚌',label:'버스 정류장'},school:{icon:'🏫',label:'학교'},childcare:{icon:'🧸',label:'어린이집'},hospital:{icon:'🏥',label:'병원'},mart:{icon:'🛒',label:'대형마트'}};
  const distanceText=metres=>metres>=1000?(metres/1000).toFixed(1)+'km':num(metres)+'m';
  function recordFacilityMethod(place,result,blockId){
    if(blockId!==infraBlockId)return;
    facilityMethods.set(place.kind+':'+place.id,{place,result});renderFacilityMethods();
  }
  function renderFacilityMethods(){
    const host=$('map-facility-detail-methods');if(!host)return;
    host.innerHTML=[...facilityMethods.values()].map(({place,result})=>`<section><h5>${esc(place.name)}</h5><p>${esc(result.as_of||'기준일 미확보')} · 조회 ${esc(result.collected_at||'미확보')}</p>${result.source_url?`<a href="${esc(safeUrl(result.source_url))}" target="_blank" rel="noopener">${esc(result.source_name||'상세 원천')} ↗</a>`:''}${(result.notes||[]).map(note=>`<p>${esc(note)}</p>`).join('')}</section>`).join('');
  }
  function infraPopup(place){
    const node=document.createElement('div');node.className='map-3d-popup';
    node.innerHTML=`<strong>${esc(infraTypes[place.kind].icon+' '+place.name)}</strong><p>${esc(place.address||'')}</p><div class="map-facility-fields" aria-live="polite"></div>`;
    const fields=node.querySelector('.map-facility-fields'),block=selectedBlock(),blockId=infraBlockId;
    const popup=new library.Popup({maxWidth:'330px'}).setLngLat([place.longitude,place.latitude]).setDOMContent(node).addTo(gl);
    let closed=false;popup.on('close',()=>{closed=true;});
    if(place.service_status==='PLANNED'){
      fields.innerHTML=`<p><b>${esc(planStamp(place))}</b></p>`;
      recordFacilityMethod(place,{as_of:place.source_date,source_name:place.source_name,source_url:place.source_url,notes:[place.location_note].filter(Boolean)},blockId);return;
    }
    fields.textContent='상세정보 조회 중…';
    if(!block){fields.textContent='상세정보 미확보';return;}
    const query=new URLSearchParams({place_id:place.id,kind:place.kind});
    query.set(precise(block)?'block_id':'project_id',precise(block)?block.id:selectedId);
    fetch(API+'/map/facility-details?'+query,{credentials:'same-origin'}).then(async response=>{
      if(!response.ok)throw Error('상세정보 조회 실패');return response.json();
    }).then(result=>{
      if(closed||blockId!==infraBlockId)return;
      recordFacilityMethod(place,result,blockId);
      fields.innerHTML=result.fields?.length?`<dl>${result.fields.map(f=>`<div><dt>${esc(f.label)}</dt><dd>${esc(f.value)}</dd></div>`).join('')}</dl>`:'<p>상세정보 미확보</p>';
    }).catch(()=>{if(!closed)fields.textContent='상세정보를 지금 조회할 수 없습니다.';});
  }
  function focusInfrastructure(place){
    if(!active||!gl||!place||!Number.isFinite(place.longitude)||!Number.isFinite(place.latitude))return;
    gl.flyTo({center:[place.longitude,place.latitude],zoom:MapMonitor.wideZoom(15.8),pitch:58,bearing:-20,duration:700});
    infraPopup(place);
  }
  function renderInfrastructurePanel(){
    const count=$('map-infrastructure-count'),body=$('map-infrastructure-content');
    if(!count||!body)return;
    if(infraState==='approximate'){count.textContent='근사 위치';body.textContent='사업 대표점으로 지도에 표시했습니다. 주변 시설 거리는 개별 블록 위치를 확인한 뒤 제공합니다.';return;}
    if(infraState==='unlocated'){count.textContent='위치 미연계';body.textContent='블록 위치가 확인되면 주변 시설을 조회합니다.';return;}
    if(infraState==='loading'){count.textContent='조회 중';body.textContent='VWorld 장소 정보를 확인하고 있습니다…';return;}
    if(infraState==='error'){count.textContent='조회 실패';body.textContent='공식 장소 정보를 지금 확인할 수 없습니다.';return;}
    count.textContent=`${selectedBlock()?.district_name||''} ${selectedBlock()?.block||''} · ${visibleInfrastructure().length}곳`;
    const summary=(entries)=>entries.map(([kind,info])=>{
      const places=visibleInfrastructure().filter(row=>row.kind===kind),first=places[0],index=first?infraItems.indexOf(first):-1;
      return `<button type="button" class="map-infra-summary ${kind}" data-infra-index="${index}" ${first?'':'disabled'}><span class="map-infra-summary-icon">${info.icon}</span><span><b>${info.label} <small>가까운 ${places.length}곳</small></b><em>${first?esc(first.name)+(first.line?' · '+esc(first.line):'')+(!withinContext(first)?' · 반경 밖 최근접 역':''):'조회 결과 미확보'}</em></span><strong>${first?esc(distanceText(first.distance_m)):'—'}</strong></button>`;
    }).join('');
    body.innerHTML=summary(Object.entries(infraTypes));
    const method=$('map-infrastructure-method');if(method)method.innerHTML=`<h4>주변 시설·거리·원천</h4><p>시설 표시 반경 ${esc(distanceText(contextRadius))} · ${contextRadiusLinked?'주변 3D 건물 조회 반경과 동일':'건물 조회 전·미확보 시 기본 반경'}<br>지하철은 반경 밖이라도 최근접 역 1곳 안내 · 대표 위치 기준 직선거리<br>GTX-A는 역 POI 또는 출구 인근 정류장 대표점. 시설 상세의 기준일·연계 상태는 클릭하여 확인합니다.</p><p><a href="${esc(safeUrl(infraSource?.source_url))}" target="_blank" rel="noopener">장소 정보 원천 ↗</a> · 조회 ${esc(infraSource?.collected_at||'미확보')}</p><p>${esc(infraSource?.plan_coverage_note||'공식 개교·개원 계획 확인분만 표시하며 전수 자료가 아닙니다.')} 좌표가 확인된 예정 시설만 지도 반경 안에 표시합니다.</p><div id="map-facility-detail-methods"></div>`;
    renderFacilityMethods();

  }
  function drawInfrastructureMarkers(zoom){
    if(zoom<MapMonitor.wideZoom(12))return;
    for(const place of [...visibleInfrastructure(),...planned().filter(withinContext)]){
      const info=infraTypes[place.kind];if(!info||(!Number.isFinite(place.latitude)||!Number.isFinite(place.longitude))||(!place.line?.startsWith('GTX')&&zoom<MapMonitor.wideZoom(14.2)))continue;
      const element=document.createElement('button');element.type='button';element.className='map-infra-marker '+place.kind+(place.service_status==='PLANNED'?' planned':'');
      element.dataset.distanceMetres=place.distance_m;element.dataset.facilityKind=place.kind;element.dataset.contextRadius=contextRadius;
      element.setAttribute('aria-label',`${info.label} ${place.name} · 직선거리 ${distanceText(place.distance_m)}`);
      element.title=place.name+(place.service_status==='PLANNED'?' · '+planStamp(place):'');
      element.innerHTML=`<span aria-hidden="true">${info.icon}</span>${place.service_status==='PLANNED'?'<small>예정</small>':(place.line?.startsWith('GTX')||zoom>=MapMonitor.wideZoom(15.2))?`<b>${esc(place.line?.startsWith('GTX')?'GTX-A '+place.name:place.name)}${place.service_status==='PLANNED'?' · '+esc(planStamp(place)):''}</b>`:''}`;
      element.addEventListener('click',event=>{event.stopPropagation();infraPopup(place);});
      marker(element,place.longitude,place.latitude);
    }
  }
  async function updateInfrastructure(){
    const block=selectedBlock();
    if(!located(block)){
      facilityMethods.clear();if($('map-infrastructure-method'))$('map-infrastructure-method').replaceChildren();infraBlockId='';infraTicket++;infraItems=[];infraSource=null;infraState=located(block)?'approximate':'unlocated';renderInfrastructurePanel();refreshMarkers();return;
    }
    if(infraBlockId===block.id)return;
    facilityMethods.clear();if($('map-infrastructure-method'))$('map-infrastructure-method').replaceChildren();infraBlockId=block.id;const ticket=++infraTicket;infraItems=[];infraSource=null;infraState='loading';renderInfrastructurePanel();refreshMarkers();
    try{
      const response=await fetch(API+'/map/infrastructure?'+(precise(block)?'block_id='+encodeURIComponent(block.id):'project_id='+encodeURIComponent(selectedId)),{credentials:'same-origin'});
      if(!response.ok)throw new Error('infrastructure unavailable');
      const result=await response.json();
      if(ticket!==infraTicket||infraBlockId!==block.id||!active)return;
      infraItems=(result.items||[]).map(p=>p.kind==='gtx'?{...p,kind:'subway',line:p.line||'GTX-A'}:p);infraSource=result;infraState='ready';renderInfrastructurePanel();refreshMarkers();
    }catch(_){if(ticket===infraTicket){infraState='error';renderInfrastructurePanel();}}
  }
  function setContextTransparency(value,persist=false){
    const parsed=Number(value);if(!Number.isFinite(parsed))return;
    contextTransparency=Math.max(0,Math.min(100,Math.round(parsed)));
    const slider=$('map-building-transparency'),output=$('map-building-transparency-value');
    if(slider){slider.value=String(contextTransparency);slider.setAttribute('aria-valuetext',contextTransparency+'% 투명'+(contextTransparency===100?' · 기존 건물 숨김':contextTransparency===0?' · 불투명':''));}
    if(output)output.textContent=contextTransparency+'%';
    if(gl?.getLayer('context-buildings-3d'))gl.setPaintProperty('context-buildings-3d','fill-extrusion-opacity',1-contextTransparency/100);
    if(persist)try{localStorage.setItem(transparencyKey,String(contextTransparency));}catch(_){}
  }
  function bindInfrastructurePanel(){
    if(infraBound)return;infraBound=true;
    try{const saved=localStorage.getItem(transparencyKey);if(saved!==null&&saved.trim()!=='')setContextTransparency(saved);}catch(_){}
    setContextTransparency(contextTransparency);
    $('map-building-transparency')?.addEventListener('input',event=>setContextTransparency(event.target.value,true));
    const radiusButton=document.createElement('button');radiusButton.type='button';radiusButton.textContent='반경 전체';radiusButton.title='선택 위치의 500m · 1km · 3km 반경 보기';radiusButton.dataset.mapRadiusFit='true';radiusButton.addEventListener('click',()=>{const block=selectedBlock();if(!active||!located(block))return;const points=radiusGeometry(block).features[2].geometry.coordinates;gl.fitBounds([[Math.min(...points.map(p=>p[0])),Math.min(...points.map(p=>p[1]))],[Math.max(...points.map(p=>p[0])),Math.max(...points.map(p=>p[1]))]],{padding:60,pitch:0,bearing:0,duration:600});});$('map-3d-camera').append(radiusButton);
    const legend=document.createElement('span');legend.className='map-radius-legend';legend.textContent='직선 반경 500m · 1km · 3km';$('map-3d-legend').append(legend);
    $('map-infrastructure-panel').addEventListener('click',event=>{
      const plan=event.target.closest('[data-plan-index]');if(plan){focusInfrastructure(planned()[Number(plan.dataset.planIndex)]);return;}
      const button=event.target.closest('[data-infra-index]');if(!button)return;
      focusInfrastructure(infraItems[Number(button.dataset.infraIndex)]);
    });
    if(window.matchMedia('(max-width:800px)').matches)$('map-infrastructure-panel').open=false;
  }
  function refreshMarkers(){
    // Keep current markers moving with the camera; rebuild after the transition.
    if(gl?.isMoving())return;
    if(!active||!gl||!data)return;
    clearMarkers();radiusLabels();
    const zoom=gl.getZoom();
    const level=MapMonitor.levelAt(zoom);markerLevel=level;
    document.querySelectorAll('[data-map-level]').forEach(button=>{const selected=button.dataset.mapLevel===level;button.classList.toggle('selected',selected);button.setAttribute('aria-pressed',String(selected));});
    $('map-bar-level').textContent=({region:'시도별 3D 공간 현황',municipality:'시군구별 3D 공간 현황',block:'블록별 가상 아파트 3D'}[level])+` · 확대 ${zoom.toFixed(1)}`;
    $('map-view-status').textContent=level==='block'?'블록별 공급 현황':'시도·시군구 공급 현황';
    if(level==='region'){
      for(const region of data.groups.region.map(SupplyBars.scoped).filter(row=>row&&row.project_count)){
        let cities=data.municipalities.filter(row=>row.region===region.id&&row.project_ids.some(id=>visibleIds.has(id)));
        if(!cities.length)cities=data.municipalities.filter(row=>row.region===region.id&&Number.isFinite(row.latitude)&&Number.isFinite(row.longitude));
        if(!cities.length)continue;
        const latitude=cities.reduce((sum,row)=>sum+row.latitude,0)/cities.length;
        const longitude=cities.reduce((sum,row)=>sum+row.longitude,0)/cities.length;
        const element=document.createElement('button');element.type='button';element.className='map-scene-region';
        element.innerHTML=`<b>${esc(({'서울특별시':'서울','인천광역시':'인천','경기도':'경기'}[region.name]||region.name))}</b><small>계획 ${region.target_units==null?'미확보':num(region.target_units)+'호'}</small><small>${esc(MapStageRing.metric(region).label)} ${esc(MapStageRing.metric(region).text)}</small>`;
        element.title=MapStageRing.description(region);
        element.addEventListener('click',()=>{selectedRegionId=region.id;onViewport?.();moveCamera({center:[longitude,latitude],zoom:MapMonitor.wideZoom(11),pitch:50,bearing:-20});});
        marker(element,longitude,latitude,'center');
      }
      return;
    }
    if(level==='municipality'){
      const areas=data.municipalities.map(SupplyBars.scoped).filter(row=>row&&row.project_count&&Number.isFinite(row.latitude)&&Number.isFinite(row.longitude));
      const max=Math.max(1,...areas.map(row=>row.target_units||0));
      for(const row of areas){
        const diameter=Math.round((24+Math.sqrt((row.target_units||0)/max)*37)*1.5);
        const element=document.createElement('button');element.type='button';element.className='map-scene-municipality';element.style.setProperty('--pie-diameter',diameter+'px');
        element.title=MapStageRing.description(row);
        element.setAttribute('aria-label',element.title);
        element.innerHTML=MapStageRing.svg(row,Math.max(48,diameter))+`<strong>${esc(row.name)}</strong><small>${esc(MapStageRing.metric(row).label)} 도달 확인</small><small>${row.target_units==null?'계획 미확보':'계획 '+num(row.target_units)+'호'}</small>`;
        element.addEventListener('click',()=>{selectedMunicipalityId=row.id;onViewport?.();moveCamera({center:[row.longitude,row.latitude],zoom:MapMonitor.wideZoom(13.7),pitch:55,bearing:-20});});
        marker(element,row.longitude,row.latitude,'center');
      }
      return;
    }
    const blocks=data.blocks.map(SupplyBars.scoped).filter(row=>row&&row.project_ids.some(id=>visibleIds.has(id)));
    for(const row of blocks.filter(located).sort((a,b)=>a.id.localeCompare(b.id))){
      const id=blockProjectId(row);if(!id)continue;
      const element=blockButton(row,id),pin=marker(element,row.longitude,row.latitude);
      blockMarkers.push({row,element,marker:pin});
    }
    layoutBlockMarkers();
    const unresolved=new Map();
    for(const row of blocks.filter(row=>!located(row)&&Number.isFinite(row.latitude)&&Number.isFinite(row.longitude))){
      const key=row.district_name;if(!unresolved.has(key))unresolved.set(key,{latitude:row.latitude,longitude:row.longitude,count:0});unresolved.get(key).count++;
    }
    for(const [name,row] of unresolved){
      const element=document.createElement('div');element.className='map-scene-unlocated';element.textContent=`${name} · 위치 미연계 ${row.count}개`;
      marker(element,row.longitude,row.latitude,'center');
    }
    drawInfrastructureMarkers(zoom);
  }
  function evidence(result,block){
    const card=$('map-3d-evidence');if(!card)return;
    card.hidden=false;
    const total=block?.target_units;
    card.innerHTML=`<h3>3D 표현 근거 · ${esc(block?.block||'미선택')}</h3><p><strong>가상 아파트 동 배치</strong> · 총 공급계획 200호당 1동(올림), 물량을 각 동에 균등 배분해 8호당 높이 3m로 표현합니다. 전체 가상 건물 부피는 공급 호수에 비례합니다. 동수·높이·배치는 실제 건축계획이 아닙니다. 물량 미확보 시 가상 건물을 만들지 않습니다.</p><p>공식 사업계획량 ${total==null?'미확보':num(total)+'호'} · ${located(block)?esc(locationLabel(block))+' · 대표점 인근 가상 배치':'개별 위치 미연계 · 가상 동 미표시'}</p>${result?`<p>반경 ${num(result.search_radius_metres)}m 기존 건물 외곽선 ${num(result.feature_count)}개 · 공식 높이 ${num(result.height_count)}개 · 층수 추정 ${num(result.floor_estimate_count)}개 · 높이 미확보 참고 형상 ${num(result.visual_only_count)}개. 회색 건물은 선택 사업과 미연계입니다.</p><a href="${esc(safeUrl(result.source_url))}" target="_blank" rel="noopener">기존 건물 원천 ↗</a>`:'<p>주변 기존 건물 정보는 위치가 확인된 블록에서 확인합니다.</p>'}`;
  }
  async function updateContext(){
    const block=selectedBlock();
    if(!located(block)){
      contextTicket++;contextRadius=500;contextRadiusLinked=false;contextBlockId='';if(gl?.getSource('context-buildings'))gl.getSource('context-buildings').setData(empty());
      evidence(null,block);return;
    }
    if(contextBlockId===block.id)return;
    contextBlockId=block.id;const ticket=++contextTicket;contextRadius=500;contextRadiusLinked=false;renderInfrastructurePanel();refreshMarkers();
    if(gl?.getSource('context-buildings'))gl.getSource('context-buildings').setData(empty());
    evidence(null,block);
    try{
      let result=contextCache.get(block.id);
      if(!result){const response=await fetch(API+'/map/buildings?'+(precise(block)?'block_id='+encodeURIComponent(block.id):'project_id='+encodeURIComponent(selectedId)),{credentials:'same-origin'});if(!response.ok)throw new Error('building context unavailable');result=await response.json();}
      contextCache.delete(block.id);contextCache.set(block.id,result);while(contextCache.size>3)contextCache.delete(contextCache.keys().next().value);
      if(ticket!==contextTicket||contextBlockId!==block.id||!active)return;
      contextRadius=result.search_radius_metres||500;contextRadiusLinked=true;
      gl.getSource('context-buildings').setData(result.geojson);renderInfrastructurePanel();refreshMarkers();
      evidence(result,block);
      status(`주변 기존 건물 ${num(result.feature_count)}개 · 공식 높이 ${num(result.height_count)}개 · 나머지 높이는 층수 추정 또는 낮은 참고 형상입니다.`);
    }catch(_){if(ticket===contextTicket)evidence(null,block);}
  }
  function render(value,ids,selectedProject,district,chooseProject){
    data=value;visibleIds=ids;selectedId=selectedProject;selectedDistrict=district;choose=chooseProject;
    if(!active||!gl)return;
    const blocks=data.blocks.filter(row=>row.project_ids.some(id=>ids.has(id))).map(SupplyBars.scoped).filter(Boolean);
    const signature=blocks.map(row=>`${row.id}:${row.target_units}:${row.longitude}:${row.latitude}:${row.coordinate_basis}`).join('|');
    if(signature!==modelSignature){modelFeatures=blocks.flatMap(row=>modelFor(row));gl.getSource('simulated-apartments').setData({type:'FeatureCollection',features:modelFeatures});modelSignature=signature;}
    gl.setPaintProperty('simulated-towers','fill-extrusion-color',['case',['==',['get','block_id'],selectedBlock()?.id||''],'#c77967','#83a8bf']);
    updateRadius();refreshMarkers();updateContext();updateInfrastructure();
    status('가상 배치·높이: 총 공급계획 200호당 1동 · 물량에 비례한 부피 · 실제 건축계획 아님. 회색은 주변 기존 건물입니다.');
  }
  async function start(value,ids,selectedProject,district,chooseProject,viewport){
    data=value;visibleIds=ids;selectedId=selectedProject;selectedDistrict=district;choose=chooseProject;onViewport=viewport;
    if(active){render(value,ids,selectedProject,district,chooseProject);resize();return;}
    if(opening)return opening;
    const ticket=++generation;
    surface(true);bindInfrastructurePanel();status('3D 공급지도를 준비하고 있습니다…');
    opening=(async()=>{
      const mod=await loadLibrary();if(ticket!==generation)return false;
      const current=selectedBlock();const exact=data.blocks.filter(row=>located(row)&&row.project_ids.some(id=>ids.has(id)));
      const center=located(current)?[current.longitude,current.latitude]:exact.length?[exact[0].longitude,exact[0].latitude]:[127.02,37.52];
      const style={version:8,sources:{base:{type:'raster',tiles:[API+'/tiles/{z}/{x}/{y}.png'],tileSize:256,maxzoom:18,attribution:'© VWorld · 국토교통부'}},layers:[{id:'base',type:'raster',source:'base'}]};
      const map=gl=new mod.Map({container:'housing-map-3d',style,center:[126.97,37.48],zoom:MapMonitor.wideZoom(9.8),pitch:45,bearing:-20,minZoom:7,maxZoom:18,canvasContextAttributes:{antialias:true},attributionControl:false});
      gl.addControl(new mod.NavigationControl({visualizePitch:true}),'bottom-right');
      // Prepare supply layers when the local style is ready; raster tile failures must not remove the entire map.
      await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(new Error('3D 지도 초기화 시간 초과')),20000);const ready=()=>{clearTimeout(timeout);resolve();};if(map.isStyleLoaded())ready();else map.once('style.load',ready);map.once('remove',ready);});
      if(ticket!==generation)return false;
      resizeObserver=new ResizeObserver(()=>{if(gl===map)map.resize();});resizeObserver.observe($('housing-map-3d'));
      gl.addSource('selection-radius',{type:'geojson',data:empty()});
      gl.addLayer({id:'selection-radius-line',type:'line',source:'selection-radius',paint:{'line-color':['match',['get','radius_m'],500,'#087f8c',1000,'#2875c7','#8150a7'],'line-width':2,'line-opacity':.85,'line-dasharray':[3,2]}});
      gl.addSource('context-buildings',{type:'geojson',data:empty()});
      gl.addLayer({id:'context-buildings-3d',type:'fill-extrusion',source:'context-buildings',minzoom:MapMonitor.wideZoom(13),paint:{'fill-extrusion-color':['match',['get','height_basis'],'OFFICIAL_HEIGHT','#8d969d','FLOOR_ESTIMATE','#abb3b8','#c8cdd0'],'fill-extrusion-height':['get','render_height_m'],'fill-extrusion-base':0,'fill-extrusion-opacity':1-contextTransparency/100}});
      gl.addSource('simulated-apartments',{type:'geojson',data:empty()});
      gl.addLayer({id:'simulated-towers',type:'fill-extrusion',source:'simulated-apartments',minzoom:MapMonitor.wideZoom(13),paint:{'fill-extrusion-color':'#83a8bf','fill-extrusion-height':['get','render_height_m'],'fill-extrusion-base':0,'fill-extrusion-opacity':.89}});
      gl.on('click','simulated-towers',event=>{const block=data?.blocks.find(row=>row.id===event.features?.[0]?.properties?.block_id);if(block)openOverlap([SupplyBars.scoped(block)||block],event.lngLat);});
      gl.on('click','context-buildings-3d',event=>{const feature=event.features?.[0];if(!feature)return;const props=feature.properties||{},basis=props.height_basis;const detail=basis==='OFFICIAL_HEIGHT'?`공식 높이 ${props.height_m}m`:basis==='FLOOR_ESTIMATE'?`공식 층수 ${props.floors}층 · 층당 3m 추정`:'높이 미확보 · 지도 표현용 7.5m';const node=document.createElement('div');node.className='map-3d-popup';node.textContent=`주변 기존 건물 · ${detail} · 공급사업 건물 미연계`;new mod.Popup({maxWidth:'250px'}).setLngLat(event.lngLat).setDOMContent(node).addTo(gl);});
      for(const layer of ['simulated-towers','context-buildings-3d']){gl.on('mouseenter',layer,()=>{gl.getCanvas().style.cursor='pointer';});gl.on('mouseleave',layer,()=>{gl.getCanvas().style.cursor='';});}
      gl.on('move',scheduleBlockLayout);
      gl.on('zoom',()=>{if(active&&MapMonitor.levelAt(gl.getZoom())!==markerLevel)refreshMarkers();});
      gl.on('zoomend',()=>{refreshMarkers();onViewport?.();});
      gl.on('moveend',()=>{if(gl&&active)onViewport?.();});
      active=true;render(data,visibleIds,selectedId,selectedDistrict,choose);resize();if(pendingFocus)focus(pendingFocus.block,pendingFocus.zoom);else setLevel(requestedLevel);onViewport?.();
      return true;
    })().catch(error=>{if(ticket!==generation)return false;console.warn('3D 지도 초기화 실패',error);status('3D 지도를 열 수 없습니다. 브라우저의 WebGL 설정과 네트워크를 확인하세요.','missing');surface(false);if(gl){gl.remove();gl=null;}active=false;return false;}).finally(()=>{if(ticket===generation)opening=null;});
    return opening;
  }
  function focus(block,zoom=15.2){
    if(!Number.isFinite(block?.latitude)||!Number.isFinite(block?.longitude))return;
    requestedLevel='block';
    if(!active||!gl){pendingFocus={block,zoom};return;}
    pendingFocus=null;
    moveCamera({center:[block.longitude,block.latitude],zoom:MapMonitor.wideZoom(zoom),pitch:55,bearing:-20});
  }
  function setLevel(level){
    requestedLevel=level==='policy'?'region':level;
    pendingFocus=null;
    if(!active||!gl)return;
    if(requestedLevel==='region'){
      selectedRegionId='';selectedMunicipalityId='';
      moveCamera({center:[126.97,37.48],zoom:MapMonitor.wideZoom(9.8),pitch:45,bearing:-20});return;
    }
    if(requestedLevel==='municipality'){
      const group=MapSupply.selection(),block=selectedBlock();
      const regionId=group.kind==='region'&&group.id?group.id:selectedRegionId;
      const cities=data.municipalities.filter(row=>(!regionId||row.region===regionId)&&row.project_ids.some(id=>visibleIds.has(id))&&Number.isFinite(row.latitude)&&Number.isFinite(row.longitude));
      const center=regionId&&cities.length?[cities.reduce((n,r)=>n+r.longitude,0)/cities.length,cities.reduce((n,r)=>n+r.latitude,0)/cities.length]:[126.95,37.52];
      moveCamera({center,zoom:MapMonitor.wideZoom(11.3),pitch:50,bearing:-20});return;
    }
    const block=selectedBlock()||data.blocks.find(row=>located(row)&&row.project_ids.some(id=>visibleIds.has(id)));
    if(located(block))focus(block,15.3);
    else moveCamera({zoom:MapMonitor.wideZoom(13.7),pitch:50,bearing:0});
  }
  function fit(){if(!active||!gl)return;const points=data.blocks.filter(row=>located(row)&&row.project_ids.some(id=>visibleIds.has(id)));if(points.length){const west=Math.min(...points.map(row=>row.longitude)),south=Math.min(...points.map(row=>row.latitude)),east=Math.max(...points.map(row=>row.longitude)),north=Math.max(...points.map(row=>row.latitude));gl.fitBounds([[west,south],[east,north]],{padding:90,maxZoom:MapMonitor.wideZoom(10),pitch:45,bearing:0,duration:650});}else setLevel('policy');}
  function camera(view){if(!active||!gl)return;if(view==='overview'){const districtBlocks=data.blocks.filter(row=>row.district_name===selectedDistrict&&located(row)&&row.project_ids.some(id=>visibleIds.has(id)));if(districtBlocks.length){const west=Math.min(...districtBlocks.map(row=>row.longitude)),south=Math.min(...districtBlocks.map(row=>row.latitude)),east=Math.max(...districtBlocks.map(row=>row.longitude)),north=Math.max(...districtBlocks.map(row=>row.latitude));gl.fitBounds([[west,south],[east,north]],{padding:110,maxZoom:MapMonitor.wideZoom(14.8),pitch:50,bearing:0,duration:450});}else fit();}else{const settings={top:{pitch:0,bearing:0},oblique:{pitch:55,bearing:-20},north:{pitch:55,bearing:0}}[view];if(!settings)return;gl.easeTo({...settings,duration:450});}document.querySelectorAll('[data-map-3d-camera]').forEach(button=>{const selected=button.getAttribute('data-map-3d-camera')===view;button.classList.toggle('selected',selected);button.setAttribute('aria-pressed',String(selected));});}
  function resize(){gl?.resize();scheduleBlockLayout();}
  function exit(){pendingFocus=null;cancelAnimationFrame(layoutFrame);layoutFrame=0;leaderSvg?.remove();leaderSvg=null;contextRadius=500;contextRadiusLinked=false;resizeObserver?.disconnect();resizeObserver=null;radiusSignature='';overlapPopup?.remove();overlapPopup=null;generation++;opening=null;contextTicket++;contextBlockId='';infraTicket++;infraBlockId='';infraItems=[];infraSource=null;infraState='loading';modelSignature='';modelFeatures=[];clearMarkers();if(gl){gl.remove();gl=null;}active=false;surface(false);}
  return {start,render,focus,setLevel,fit,camera,resize,exit,cancel:exit,status,active:()=>active,loading:()=>Boolean(opening),currentBlock:()=>selectedBlock()?.id,zoom:()=>gl?.getZoom()||0,view:()=>gl?{zoom:gl.getZoom(),level:MapMonitor.levelAt(gl.getZoom()),center:gl.getCenter(),regionId:selectedRegionId,municipalityId:selectedMunicipalityId}:null,modelStats:()=>({features:modelFeatures.length,approximateFeatures:modelFeatures.filter(row=>row.properties.location_basis?.startsWith('APPROXIMATE')).length,selectedFeatures:modelFeatures.filter(row=>row.properties.block_id===selectedBlock()?.id).length,simulated:modelFeatures.every(row=>row.properties.model_status==='ILLUSTRATIVE')})};
})();
