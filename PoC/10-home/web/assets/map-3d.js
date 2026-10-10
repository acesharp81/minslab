'use strict';
// Continuous 3D supply map. Apartment masses are illustrative, not surveyed
// buildings, official layouts, construction progress, or a source of unit counts.
const MapThreeD=(()=>{
  let library,gl,opening,active=false,data,selectedId,selectedDistrict,choose,onViewport;
  let markers=[],visibleIds=new Set(),modelSignature='',contextBlockId='',contextTicket=0,modelFeatures=[],generation=0;
  let infraBlockId='',infraTicket=0,infraItems=[],infraSource=null,infraState='loading',infraBound=false;
  let selectedRegionId='',selectedMunicipalityId='';
  const contextCache=new Map();
  const empty=()=>({type:'FeatureCollection',features:[]});
  const precise=row=>row?.coordinate_basis==='LH_PUBLIC_BLOCK_LABEL_POINT'&&Number.isFinite(row.latitude)&&Number.isFinite(row.longitude);
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
  function modelFor(block){
    if(!precise(block)||!Number.isFinite(block.target_units)||block.target_units<=0)return [];
    // The count, footprints, positions and heights are a deterministic visual
    // scale only. They must never feed HOME's supply/progress calculations.
    const count=Math.max(2,Math.min(8,Math.ceil(block.target_units/210)));
    const latStep=1/111320,lonStep=1/(111320*Math.cos(block.latitude*Math.PI/180));
    return Array.from({length:count},(_,index)=>{
      const col=index%3,row=Math.floor(index/3),cx=(col-1)*34,cy=(row-1)*54;
      const halfW=6.5,halfD=21,height=34+((index+block.block.length)%4)*7;
      const angle=((block.block.charCodeAt(0)+block.block.length)%4)*Math.PI/8;
      const corners=[[-halfW,-halfD],[halfW,-halfD],[halfW,halfD],[-halfW,halfD],[-halfW,-halfD]]
        .map(([x,y])=>{const east=cx+x*Math.cos(angle)-y*Math.sin(angle),north=cy+x*Math.sin(angle)+y*Math.cos(angle);return [block.longitude+east*lonStep,block.latitude+north*latStep];});
      return {type:'Feature',id:`${block.id}:${index}`,geometry:{type:'Polygon',coordinates:[corners]},
        properties:{block_id:block.id,block:block.block,district: block.district_name,target_units:block.target_units,
          render_height_m:height,model_status:'ILLUSTRATIVE',location_basis:'LH_PUBLIC_BLOCK_LABEL_POINT'}};
    });
  }
  function clearMarkers(){for(const marker of markers)marker.remove();markers=[];}
  function marker(element,longitude,latitude,anchor='bottom'){
    markers.push(new library.Marker({element,anchor}).setLngLat([longitude,latitude]).addTo(gl));
  }
  function selectedBlock(){return data?.blocks.find(row=>row.project_ids.includes(selectedId)&&row.district_name===selectedDistrict);}
  function selectBlock(block){const id=block.project_ids.find(value=>visibleIds.has(value));if(id)choose?.(id,block.district_name);}
  const infraTypes={gtx:{icon:'🚄',label:'GTX-A'},subway:{icon:'🚇',label:'지하철'},school:{icon:'🏫',label:'학교'},hospital:{icon:'🏥',label:'병원'}};
  const distanceText=metres=>metres>=1000?(metres/1000).toFixed(1)+'km':num(metres)+'m';
  function infraPopup(place){
    const node=document.createElement('div');node.className='map-3d-popup';
    node.innerHTML=`<strong>${esc(infraTypes[place.kind].icon+' '+place.name)}</strong><p>${esc(place.category)}</p><p>${esc(place.address||(place.kind==='gtx'?(place.location_basis==='VWORLD_STATION_EXIT_BUS_STOP_PROXY'?'역 출구 인근 버스정류장 위치':'기존 역 POI 대표 위치'):'주소 미확보'))}</p><small>선택 블록에서 직선거리 ${esc(distanceText(place.distance_m))} · 이동거리 아님</small>${place.kind==='gtx'?`<br><a href="${esc(safeUrl(place.service_status_source_url))}" target="_blank" rel="noopener">GTX-A 운영 구간 근거 ↗</a>`:''}`;
    new library.Popup({maxWidth:'270px'}).setLngLat([place.longitude,place.latitude]).setDOMContent(node).addTo(gl);
  }
  function focusInfrastructure(place){
    if(!active||!gl||!place)return;
    gl.flyTo({center:[place.longitude,place.latitude],zoom:15.8,pitch:58,bearing:-20,duration:700});
    infraPopup(place);
  }
  function renderInfrastructurePanel(){
    const count=$('map-infrastructure-count'),body=$('map-infrastructure-content');
    if(!count||!body)return;
    if(infraState==='unlocated'){count.textContent='위치 미연계';body.textContent='블록 위치가 확인되면 주변 시설을 조회합니다.';return;}
    if(infraState==='loading'){count.textContent='조회 중';body.textContent='VWorld 장소 정보를 확인하고 있습니다…';return;}
    if(infraState==='error'){count.textContent='조회 실패';body.textContent='공식 장소 정보를 지금 확인할 수 없습니다.';return;}
    count.textContent=`반경 ${((infraSource?.search_radius_metres||3500)/1000).toFixed(1)}km · GTX-A ${((infraSource?.gtx_search_radius_metres||12000)/1000).toFixed(0)}km`;
    body.innerHTML=Object.entries(infraTypes).map(([kind,info])=>{
      const places=infraItems.filter(row=>row.kind===kind),first=places[0],index=first?infraItems.indexOf(first):-1;
      return `<button type="button" class="map-infra-summary ${kind}" data-infra-index="${index}" ${first?'':'disabled'}><span class="map-infra-summary-icon">${info.icon}</span><span><b>${info.label} <small>${kind==='gtx'?'위치 확인된 운영역':'가까운'} ${places.length}곳</small></b><em>${first?esc(first.name)+(kind==='gtx'?' · 운영':''):'조회 결과 미확보'}</em></span><strong>${first?esc(distanceText(first.distance_m)):'—'}</strong></button>`;
    }).join('')+(infraSource?.planned_gtx||[]).map(row=>`<p class="map-infra-planned">🚄 ${esc(row.line+' '+row.name)} · 계획/미개통 · 위치 미연계 <a href="${esc(safeUrl(row.source_url))}" target="_blank" rel="noopener">근거 ↗</a></p>`).join('')+`<p>일반 시설 ${esc(((infraSource?.search_radius_metres||3500)/1000).toFixed(1))}km · GTX-A ${esc(((infraSource?.gtx_search_radius_metres||12000)/1000).toFixed(0))}km 이내, 선택 블록 기준 직선거리<br>GTX-A는 역 POI 또는 출구 인근 정류장 대표 위치 · 이동시간 미반영<br><a href="${esc(safeUrl(infraSource?.source_url))}" target="_blank" rel="noopener">VWorld 장소 검색 원천 ↗</a> · <a href="${esc(safeUrl(infraSource?.gtx_status_source_url))}" target="_blank" rel="noopener">GTX-A 운영 근거 ↗</a> · 조회 ${esc(infraSource?.collected_at||'미확보')}</p>`;
  }
  function drawInfrastructureMarkers(zoom){
    if(zoom<12)return;
    for(const place of infraItems){
      const info=infraTypes[place.kind];if(!info||(!Number.isFinite(place.latitude)||!Number.isFinite(place.longitude))||(place.kind!=='gtx'&&zoom<14.2))continue;
      const element=document.createElement('button');element.type='button';element.className='map-infra-marker '+place.kind;
      element.setAttribute('aria-label',`${info.label} ${place.name} · 직선거리 ${distanceText(place.distance_m)}`);
      element.title=`${place.name} · 선택 블록에서 직선거리 ${distanceText(place.distance_m)}`;
      element.innerHTML=`<span aria-hidden="true">${info.icon}</span>${(place.kind==='gtx'||zoom>=15.2)?`<b>${esc(place.kind==='gtx'?'GTX-A '+place.name:place.name)}</b>`:''}`;
      element.addEventListener('click',event=>{event.stopPropagation();infraPopup(place);});
      marker(element,place.longitude,place.latitude);
    }
  }
  async function updateInfrastructure(){
    const block=selectedBlock();
    if(!precise(block)){
      infraBlockId='';infraTicket++;infraItems=[];infraSource=null;infraState='unlocated';renderInfrastructurePanel();refreshMarkers();return;
    }
    if(infraBlockId===block.id)return;
    infraBlockId=block.id;const ticket=++infraTicket;infraItems=[];infraSource=null;infraState='loading';renderInfrastructurePanel();refreshMarkers();
    try{
      const response=await fetch(API+'/map/infrastructure?block_id='+encodeURIComponent(block.id),{credentials:'same-origin'});
      if(!response.ok)throw new Error('infrastructure unavailable');
      const result=await response.json();
      if(ticket!==infraTicket||infraBlockId!==block.id||!active)return;
      infraItems=result.items||[];infraSource=result;infraState='ready';renderInfrastructurePanel();refreshMarkers();
    }catch(_){if(ticket===infraTicket){infraState='error';renderInfrastructurePanel();}}
  }
  function bindInfrastructurePanel(){
    if(infraBound)return;infraBound=true;
    $('map-infrastructure-panel').addEventListener('click',event=>{
      const button=event.target.closest('[data-infra-index]');if(!button)return;
      focusInfrastructure(infraItems[Number(button.dataset.infraIndex)]);
    });
    if(window.matchMedia('(max-width:800px)').matches)$('map-infrastructure-panel').open=false;
  }
  function refreshMarkers(){
    if(!active||!gl||!data)return;
    clearMarkers();
    const zoom=gl.getZoom();
    const level=MapMonitor.levelAt(zoom);
    $('map-bar-level').textContent=({region:'시도별 3D 공간 현황',municipality:'시군구별 3D 공간 현황',block:'블록별 가상 아파트 3D'}[level])+` · 확대 ${zoom.toFixed(1)}`;
    $('map-view-status').textContent=level==='block'?'블록별 공급 현황':'시도·시군구 공급 현황';
    if(level==='region'){
      for(const region of data.groups.region.map(SupplyBars.scoped).filter(row=>row&&row.project_count)){
        const cities=data.municipalities.filter(row=>row.region===region.id&&row.project_ids.some(id=>visibleIds.has(id)));
        if(!cities.length)continue;
        const latitude=cities.reduce((sum,row)=>sum+row.latitude,0)/cities.length;
        const longitude=cities.reduce((sum,row)=>sum+row.longitude,0)/cities.length;
        const element=document.createElement('button');element.type='button';element.className='map-scene-region';
        element.innerHTML=`<b>${esc(region.name==='경기도'?'경기':'서울')}</b><small>계획 ${region.target_units==null?'미확보':num(region.target_units)+'호'}</small><small>공고 확인 ${region.current_notice_units==null?'미확보':num(region.current_notice_units)+'호'}</small>`;
        element.addEventListener('click',()=>{selectedRegionId=region.id;onViewport?.();gl.flyTo({center:[longitude,latitude],zoom:11,pitch:50,bearing:-20,duration:650});});
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
        const pct=row.projection?.baseline_pct;
        const radius=diameter/2-6,confirmed=Math.max(0,Math.min(100,pct||0));
        element.innerHTML=`<svg width="${diameter}" height="${diameter}" viewBox="0 0 ${diameter} ${diameter}" aria-hidden="true"><circle cx="${diameter/2}" cy="${diameter/2}" r="${radius}" fill="#eaf0f7" stroke="#8aa1bf" stroke-width="3"/><circle cx="${diameter/2}" cy="${diameter/2}" r="${radius}" fill="none" stroke="#2878df" stroke-width="9" pathLength="100" stroke-dasharray="${confirmed} ${100-confirmed}" transform="rotate(-90 ${diameter/2} ${diameter/2})"/></svg><b>${pct==null?'?':Math.round(pct)+'%'}</b><strong>${esc(row.name)}</strong><small>${row.target_units==null?'계획 미확보':'계획 '+num(row.target_units)+'호'}</small>`;
        element.addEventListener('click',()=>{selectedMunicipalityId=row.id;onViewport?.();gl.flyTo({center:[row.longitude,row.latitude],zoom:13.7,pitch:55,bearing:-20,duration:650});});
        marker(element,row.longitude,row.latitude,'center');
      }
      return;
    }
    const blocks=data.blocks.map(SupplyBars.scoped).filter(row=>row&&row.project_ids.some(id=>visibleIds.has(id)));
    for(const row of blocks){
      if(!precise(row))continue;
      const element=document.createElement('button');element.type='button';element.className='map-3d-block-marker map-scene-block';element.style.height=BlockMonitor.heightFor(row)+'px';
      element.setAttribute('aria-label',`${row.district_name} ${row.block} 블록 공급 현황`);
      element.title='LH 블록 라벨점 · 건물 배치와 높이는 가상 시각화';
      element.classList.toggle('selected',row.project_ids.includes(selectedId));
      element.innerHTML=BlockMonitor.graph(row);
      element.addEventListener('click',event=>{event.stopPropagation();selectBlock(row);});
      marker(element,row.longitude,row.latitude);
    }
    const unresolved=new Map();
    for(const row of blocks.filter(row=>!precise(row)&&Number.isFinite(row.latitude)&&Number.isFinite(row.longitude))){
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
    card.innerHTML=`<h3>3D 표현 근거 · ${esc(block?.block||'미선택')}</h3><p><strong>가상 아파트 동 배치</strong> · 공급 규모를 읽기 위한 개념 모델입니다. 동수·높이·배치·정확 경계는 공식 계획값이 아닙니다.</p><p>공식 사업계획량 ${total==null?'미확보':num(total)+'호'} · ${precise(block)?'LH 블록 라벨점 기준':'개별 위치 미연계 · 가상 동 미표시'}</p>${result?`<p>반경 ${num(result.search_radius_metres)}m 기존 건물 외곽선 ${num(result.feature_count)}개 · 공식 높이 ${num(result.height_count)}개 · 층수 추정 ${num(result.floor_estimate_count)}개 · 높이 미확보 참고 형상 ${num(result.visual_only_count)}개. 회색 건물은 선택 사업과 미연계입니다.</p><a href="${esc(safeUrl(result.source_url))}" target="_blank" rel="noopener">기존 건물 원천 ↗</a>`:'<p>주변 기존 건물 정보는 위치가 확인된 블록에서 확인합니다.</p>'}`;
  }
  async function updateContext(){
    const block=selectedBlock();
    if(!precise(block)){
      contextBlockId='';if(gl?.getSource('context-buildings'))gl.getSource('context-buildings').setData(empty());
      evidence(null,block);return;
    }
    if(contextBlockId===block.id)return;
    contextBlockId=block.id;const ticket=++contextTicket;
    if(gl?.getSource('context-buildings'))gl.getSource('context-buildings').setData(empty());
    evidence(null,block);
    try{
      let result=contextCache.get(block.id);
      if(!result){const response=await fetch(API+'/map/buildings?block_id='+encodeURIComponent(block.id),{credentials:'same-origin'});if(!response.ok)throw new Error('building context unavailable');result=await response.json();}
      contextCache.delete(block.id);contextCache.set(block.id,result);while(contextCache.size>3)contextCache.delete(contextCache.keys().next().value);
      if(ticket!==contextTicket||contextBlockId!==block.id||!active)return;
      gl.getSource('context-buildings').setData(result.geojson);
      evidence(result,block);
      status(`주변 기존 건물 ${num(result.feature_count)}개 · 공식 높이 ${num(result.height_count)}개 · 나머지 높이는 층수 추정 또는 낮은 참고 형상입니다.`);
    }catch(_){if(ticket===contextTicket)evidence(null,block);}
  }
  function render(value,ids,selectedProject,district,chooseProject){
    data=value;visibleIds=ids;selectedId=selectedProject;selectedDistrict=district;choose=chooseProject;
    if(!active||!gl)return;
    const blocks=data.blocks.filter(row=>row.project_ids.some(id=>ids.has(id))).map(SupplyBars.scoped).filter(Boolean);
    const signature=blocks.map(row=>`${row.id}:${row.target_units}`).join('|');
    if(signature!==modelSignature){modelFeatures=blocks.flatMap(modelFor);gl.getSource('simulated-apartments').setData({type:'FeatureCollection',features:modelFeatures});modelSignature=signature;}
    gl.setPaintProperty('simulated-towers','fill-extrusion-color',['case',['==',['get','block_id'],selectedBlock()?.id||''],'#c77967','#83a8bf']);
    refreshMarkers();updateContext();updateInfrastructure();
    status('파란 건물은 가상 배치·높이입니다. 공급 수량은 공식 원천 집계이며, 회색은 주변 기존 건물입니다.');
  }
  async function start(value,ids,selectedProject,district,chooseProject,viewport){
    data=value;visibleIds=ids;selectedId=selectedProject;selectedDistrict=district;choose=chooseProject;onViewport=viewport;
    if(active){render(value,ids,selectedProject,district,chooseProject);resize();return;}
    if(opening)return opening;
    const ticket=++generation;
    surface(true);bindInfrastructurePanel();status('3D 공급지도를 준비하고 있습니다…');
    opening=(async()=>{
      const mod=await loadLibrary();if(ticket!==generation)return false;
      const current=selectedBlock();const exact=data.blocks.filter(row=>precise(row)&&row.project_ids.some(id=>ids.has(id)));
      const center=precise(current)?[current.longitude,current.latitude]:exact.length?[exact[0].longitude,exact[0].latitude]:[127.02,37.52];
      const style={version:8,sources:{base:{type:'raster',tiles:[API+'/tiles/{z}/{x}/{y}.png'],tileSize:256,maxzoom:18,attribution:'© VWorld · 국토교통부'}},layers:[{id:'base',type:'raster',source:'base'}]};
      gl=new mod.Map({container:'housing-map-3d',style,center,zoom:precise(current)?16.1:exact.length?15.4:9,pitch:58,bearing:-20,minZoom:7,maxZoom:18,canvasContextAttributes:{antialias:true},attributionControl:false});
      gl.addControl(new mod.NavigationControl({visualizePitch:true}),'bottom-right');
      await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(new Error('3D 지도 초기화 시간 초과')),20000);gl.once('load',()=>{clearTimeout(timeout);resolve();});gl.once('error',event=>{if(!gl?.isStyleLoaded()){clearTimeout(timeout);reject(event.error||new Error('3D 초기화 실패'));}});});
      if(ticket!==generation)return false;
      gl.addSource('context-buildings',{type:'geojson',data:empty()});
      gl.addLayer({id:'context-buildings-3d',type:'fill-extrusion',source:'context-buildings',minzoom:13,paint:{'fill-extrusion-color':['match',['get','height_basis'],'OFFICIAL_HEIGHT','#8d969d','FLOOR_ESTIMATE','#abb3b8','#c8cdd0'],'fill-extrusion-height':['get','render_height_m'],'fill-extrusion-base':0,'fill-extrusion-opacity':.82}});
      gl.addSource('simulated-apartments',{type:'geojson',data:empty()});
      gl.addLayer({id:'simulated-towers',type:'fill-extrusion',source:'simulated-apartments',minzoom:13,paint:{'fill-extrusion-color':'#83a8bf','fill-extrusion-height':['get','render_height_m'],'fill-extrusion-base':0,'fill-extrusion-opacity':.89}});
      gl.on('click','simulated-towers',event=>{const feature=event.features?.[0],block=data?.blocks.find(row=>row.id===feature?.properties?.block_id);if(!block)return;selectBlock(block);const node=document.createElement('div');node.className='map-3d-popup';node.innerHTML=`<strong>${esc(block.district_name)} · ${esc(block.block)}</strong><p>공식 계획 ${block.target_units==null?'미확보':num(block.target_units)+'호'}</p><small>가상 동 배치·높이 · 실제 계획도 아님</small>`;new mod.Popup({maxWidth:'250px'}).setLngLat(event.lngLat).setDOMContent(node).addTo(gl);});
      gl.on('click','context-buildings-3d',event=>{const feature=event.features?.[0];if(!feature)return;const props=feature.properties||{},basis=props.height_basis;const detail=basis==='OFFICIAL_HEIGHT'?`공식 높이 ${props.height_m}m`:basis==='FLOOR_ESTIMATE'?`공식 층수 ${props.floors}층 · 층당 3m 추정`:'높이 미확보 · 지도 표현용 7.5m';const node=document.createElement('div');node.className='map-3d-popup';node.textContent=`주변 기존 건물 · ${detail} · 공급사업 건물 미연계`;new mod.Popup({maxWidth:'250px'}).setLngLat(event.lngLat).setDOMContent(node).addTo(gl);});
      for(const layer of ['simulated-towers','context-buildings-3d']){gl.on('mouseenter',layer,()=>{gl.getCanvas().style.cursor='pointer';});gl.on('mouseleave',layer,()=>{gl.getCanvas().style.cursor='';});}
      gl.on('zoomend',()=>{refreshMarkers();onViewport?.();});
      gl.on('moveend',()=>{if(gl&&active)onViewport?.();});
      active=true;render(data,visibleIds,selectedId,selectedDistrict,choose);resize();onViewport?.();
      return true;
    })().catch(error=>{if(ticket!==generation)return false;status('3D 지도를 열 수 없습니다. 브라우저의 WebGL 설정과 네트워크를 확인하세요.','missing');surface(false);if(gl){gl.remove();gl=null;}active=false;return false;}).finally(()=>{if(ticket===generation)opening=null;});
    return opening;
  }
  function focus(block,zoom=15.2){if(!active||!gl||!Number.isFinite(block?.latitude)||!Number.isFinite(block?.longitude))return;gl.flyTo({center:[block.longitude,block.latitude],zoom,pitch:55,bearing:-20,duration:650});}
  function setLevel(level){if(!active||!gl)return;if(level==='policy'){gl.flyTo({center:[127.02,37.52],zoom:8.6,pitch:45,bearing:0,duration:650});return;}if(level==='municipality'){const block=selectedBlock();const center=Number.isFinite(block?.latitude)?[block.longitude,block.latitude]:[127.02,37.52];gl.flyTo({center,zoom:11.1,pitch:50,bearing:-20,duration:650});return;}const block=selectedBlock()||data.blocks.find(row=>precise(row)&&row.project_ids.some(id=>visibleIds.has(id)));if(block)focus(block,15.3);}
  function fit(){if(!active||!gl)return;const points=data.blocks.filter(row=>precise(row)&&row.project_ids.some(id=>visibleIds.has(id)));if(points.length){const west=Math.min(...points.map(row=>row.longitude)),south=Math.min(...points.map(row=>row.latitude)),east=Math.max(...points.map(row=>row.longitude)),north=Math.max(...points.map(row=>row.latitude));gl.fitBounds([[west,south],[east,north]],{padding:90,maxZoom:10,pitch:45,bearing:0,duration:650});}else setLevel('policy');}
  function camera(view){if(!active||!gl)return;if(view==='overview'){const districtBlocks=data.blocks.filter(row=>row.district_name===selectedDistrict&&precise(row)&&row.project_ids.some(id=>visibleIds.has(id)));if(districtBlocks.length){const west=Math.min(...districtBlocks.map(row=>row.longitude)),south=Math.min(...districtBlocks.map(row=>row.latitude)),east=Math.max(...districtBlocks.map(row=>row.longitude)),north=Math.max(...districtBlocks.map(row=>row.latitude));gl.fitBounds([[west,south],[east,north]],{padding:110,maxZoom:14.8,pitch:50,bearing:0,duration:450});}else fit();}else{const settings={top:{pitch:0,bearing:0},oblique:{pitch:55,bearing:-20},north:{pitch:55,bearing:0}}[view];if(!settings)return;gl.easeTo({...settings,duration:450});}document.querySelectorAll('[data-map-3d-camera]').forEach(button=>{const selected=button.getAttribute('data-map-3d-camera')===view;button.classList.toggle('selected',selected);button.setAttribute('aria-pressed',String(selected));});}
  function resize(){if(active)gl?.resize();}
  function exit(){generation++;opening=null;contextTicket++;contextBlockId='';infraTicket++;infraBlockId='';infraItems=[];infraSource=null;infraState='loading';modelSignature='';modelFeatures=[];clearMarkers();if(gl){gl.remove();gl=null;}active=false;surface(false);}
  return {start,render,focus,setLevel,fit,camera,resize,exit,cancel:exit,status,active:()=>active,loading:()=>Boolean(opening),currentBlock:()=>selectedBlock()?.id,zoom:()=>gl?.getZoom()||0,view:()=>gl?{zoom:gl.getZoom(),level:MapMonitor.levelAt(gl.getZoom()),center:gl.getCenter(),regionId:selectedRegionId,municipalityId:selectedMunicipalityId}:null,modelStats:()=>({features:modelFeatures.length,simulated:modelFeatures.every(row=>row.properties.model_status==='ILLUSTRATIVE')})};
})();
