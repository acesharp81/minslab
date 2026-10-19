'use strict';
const ProjectFacilityMap=(()=>{
 const types={subway:['🚇','지하철'],bus:['🚌','버스 정류장'],school:['🏫','학교'],childcare:['🧸','어린이집'],hospital:['🏥','병원'],mart:['🛒','대형마트']};
 const e=v=>esc(String(v??''));
 const located=p=>Number.isFinite(p.latitude)&&Number.isFinite(p.longitude);
 function visiblePlanned(rows,radius){return (rows||[]).filter(p=>located(p)&&Number.isFinite(p.distance_m)&&p.distance_m<=radius);}
 function create(map){let layer=null,markers=new Map(),generation=0;
  function clear(){generation++;if(layer)layer.remove();layer=null;markers.clear();}
  function update({items,planned,origin,radius,query}){map.stop();map.closePopup();clear();const token=generation;layer=L.layerGroup().addTo(map);
   let circle=null;if(located(origin))circle=L.circle([origin.latitude,origin.longitude],{radius,color:'#6c91b5',weight:1,dashArray:'5 5',fillColor:'#eaf2fb',fillOpacity:.14,interactive:false,className:'pjt-facility-radius'}).addTo(layer);
   for(const item of [...items,...visiblePlanned(planned,radius)]){
    if(!located(item)||!types[item.kind])continue;const [symbol,label]=types[item.kind],isPlanned=item.service_status==='PLANNED'||planned.includes(item);
    const icon=L.divIcon({className:'pjt-facility-marker pjt-facility-'+item.kind+(isPlanned?' is-planned':''),html:isPlanned?'<span aria-hidden="true">'+symbol+'</span><small>예정</small>':'',iconSize:isPlanned?[26,26]:[12,12],iconAnchor:isPlanned?[13,13]:[6,6]});
    const marker=L.marker([item.latitude,item.longitude],{icon,title:label+' · '+item.name+(isPlanned?' · 예정':''),keyboard:true,zIndexOffset:isPlanned?150:50}).addTo(layer);
    marker.getElement()?.setAttribute('data-facility-kind',item.kind);marker.getElement()?.setAttribute('data-facility-id',item.id||item.name);
    marker.bindTooltip(e(item.name+(item.line?' · '+item.line:'')),{direction:'top'});
    marker.bindPopup(()=>{const node=document.createElement('div');node.className='pjt-facility-popup';node.innerHTML='<strong>'+e(label+' · '+item.name)+'</strong>'+(item.address?'<p>'+e(item.address)+'</p>':'')+(item.line?'<p>'+e(item.line)+'</p>':'')+'<div class="pjt-facility-fields" aria-live="polite"></div>';const fields=node.querySelector('.pjt-facility-fields');
     if(isPlanned){fields.innerHTML='<p>'+e((item.kind==='school'?'개교':'개원')+' 예정 '+(item.opening_date||'미정'))+'</p>';return node;}
     if(!item.id){fields.textContent='상세정보 미확보';return node;}fields.textContent='상세정보 조회 중…';
     request('/map/facility-details?'+query+'&'+new URLSearchParams({place_id:item.id,kind:item.kind})).then(result=>{if(token!==generation||!node.isConnected)return;fields.innerHTML=result.fields?.length?'<dl>'+result.fields.map(f=>'<div><dt>'+e(f.label)+'</dt><dd>'+e(f.value)+'</dd></div>').join('')+'</dl>':'<p>상세정보 미확보</p>';}).catch(()=>{if(token===generation&&node.isConnected)fields.textContent='상세정보를 지금 조회할 수 없습니다.';});return node;
    },{maxWidth:280});markers.set(item,marker);
   }
   if(circle){map.invalidateSize({pan:false});map.fitBounds(circle.getBounds(),{padding:[16,16],maxZoom:16,animate:false});}
  }
  function focus(item){const marker=markers.get(item);if(!marker)return;map.setView(marker.getLatLng(),Math.max(map.getZoom(),15),{animate:false});marker.openPopup();}
  return {update,focus,clear};
 }
 function legend(){return '<section class="pjt-map-legend" aria-label="지도 범례"><h4>지도 범례</h4><ul>'+Object.entries(types).map(([kind,info])=>'<li><i class="pjt-legend-dot pjt-facility-'+kind+'" aria-hidden="true"></i><span>'+info[1]+'</span></li>').join('')+'<li><i class="pjt-legend-project" aria-hidden="true"></i><span>사업 위치</span></li><li><i class="pjt-legend-radius" aria-hidden="true"></i><span>선택한 조회 반경</span></li><li class="pjt-legend-planned"><i aria-hidden="true">🏫 🧸</i><span>개교·개원 예정 <small>지도에 ‘예정’ 표시</small></span></li></ul><p>마커 또는 시설 목록을 누르면 상세정보를 확인합니다.</p></section>';}
 return {create,visiblePlanned,legend};
})();
