'use strict';
// Policy-status thematic map. The existing HousingMap/MapThreeD supply view is independent.
const PolicyGeo3D=(()=>{
  let library,map,geometry,metrics,completionMetrics,mode='policy-progress',selected='',selectedPlace=null;
  let year=null,windowStart=null,active=false,opening=null,asOfKey='',ticket=0;
  const metricCache=new Map(),shapeCache=new Map(),seriesCache=new Map();
  let itemIndex=new Map();
  const currentYear=()=>Number(($('as-of').value||new Date().toISOString().slice(0,10)).slice(0,4));
  const groupKind=()=>mode==='program-progress'?'program_link':mode==='projects'?'project':'policy';
  const display=n=>n==null?'미확보':num(n)+'호';
  const apiParams=()=>{const qs=new URLSearchParams();if($('as-of').value)qs.set('as_of_date',$('as-of').value);return qs;};
  const metricMeasure=()=>$('policy-geo-measure').value==='CAPACITY'?'SUPPLY':$('policy-geo-measure').value;
  const analysisYear=()=>currentYear();
  const empty=()=>({type:'FeatureCollection',features:[]});
  const scopeRows=()=>groupKind()==='project'?metrics?.items||[]:groupKind()==='program_link'?Policy907.programs().map(p=>({...p,...metrics?.groups?.program_link?.find(g=>g.id===p.id)})):(metrics?.groups?.policy||[PolicyReport.policyInfo('POL_2025_0907')].filter(Boolean)).filter(p=>p.id==='POL_2025_0907');
  const scopeRow=()=>scopeRows().find(row=>row.id===selected);
  function scopedSeries(row){
    const scope=scopeRow();
    if(!scope||!row)return [];
    const key=`${groupKind()}:${selected}:${row.id}`;
    if(seriesCache.has(key))return seriesCache.get(key);
    const members=new Set(scope.project_ids||[scope.id]);
    const scheduled=new Set(scope.chart_schedule_ids||[scope.id]);
    const years=new Map(),seenNotices=new Set();
    for(const id of row.project_ids||[]){
      if(!members.has(id))continue;
      const item=itemIndex.get(id);
      if(!item)continue;
      for(const annual of item.annual_series||[]){
        const slot=years.get(annual.year)||{year:annual.year};
        if(scheduled.has(id))for(const stage of ['SUPPLY','COMPLETION','CONSTRUCTION']){
          if(annual[stage]!=null)slot[stage]=(slot[stage]||0)+annual[stage];
        }
        if(annual.notice_units!=null&&item.notice_evidence_id&&!seenNotices.has(item.notice_evidence_id)){
          slot.notice_units=(slot.notice_units||0)+annual.notice_units;
          seenNotices.add(item.notice_evidence_id);
        }
        years.set(annual.year,slot);
      }
    }
    const result=[...years.values()].sort((a,b)=>a.year-b.year);
    seriesCache.set(key,result);
    return result;
  }
  function scoped(row){
    if(!row)return null;
    const kind=groupKind();
    if(kind==='project'){
      const item=scopeRow();
      if(!item||!row.project_ids?.includes(item.id))return null;
      return {target_units:item.planned_units,current_notice_units:item.current_notice_units??null,
              actual_delivery_units:null,project_count:1,future:[],early_count:0,on_time_count:0,late_count:0,verification_count:0,
              annual_series:item.annual_series||[]};
    }
    if(kind==='program_link'){
      const scope=scopeRow();
      if(!scope)return null;
      const members=new Set(scope.project_ids||[]),targets=new Set(scope.chart_target_ids||[]);
      const ids=(row.project_ids||[]).filter(id=>members.has(id));
      if(!ids.length)return null;
      const planned=ids.filter(id=>targets.has(id)).map(id=>itemIndex.get(id)?.planned_units).filter(v=>v!=null);
      const notices=new Map();
      for(const id of ids){const item=itemIndex.get(id);if(item?.notice_evidence_id&&item.current_notice_units!=null)notices.set(item.notice_evidence_id,item.current_notice_units);}
      const annual_series=scopedSeries(row),stage=metricMeasure(),now=currentYear();
      const future=Array.from({length:10},(_,offset)=>{const end_year=now+offset+1,amounts=annual_series.filter(point=>point.year>now&&point.year<=end_year&&point[stage]!=null).map(point=>point[stage]);return {year:end_year,source_units:amounts.length?amounts.reduce((a,b)=>a+b,0):null};});
      return {target_units:planned.length?planned.reduce((a,b)=>a+b,0):null,current_notice_units:notices.size?[...notices.values()].reduce((a,b)=>a+b,0):null,actual_delivery_units:null,project_count:ids.length,future,annual_series,early_count:0,on_time_count:0,late_count:0,verification_count:0};
    }
    const q=row.by_scope?.[kind]?.[selected];
    return q?{...q,annual_series:scopedSeries(row)}:null;
  }
  function amount(q){
    if(!q)return {value:null,basis:'범위에 포함되지 않음',status:'OUTSIDE'};
    const measure=$('policy-geo-measure').value,period=$('policy-geo-period').value,now=currentYear();
    if(measure==='CAPACITY')return {value:q.target_units,basis:'현재 확보된 사업계획 · 연결 검토',status:'REVIEW'};
    if(year<=now){
      if(measure==='SUPPLY'){
        const series=q.annual_series||[],notices=series.filter(row=>period==='annual'?row.year===year:row.year<=year).map(row=>row.notice_units).filter(v=>v!=null);
        const value=notices.length?notices.reduce((sum,v)=>sum+v,0):year===now&&period==='cumulative'?q.current_notice_units:null;
        return {value,basis:'해당 연도까지 확인한 LH 본 모집공고 연결 검토 · 실입주 아님',status:value==null?'MISSING':'REVIEW'};
      }
      return {value:null,basis:period==='annual'?'연간 실제 물량 미확보':'해당 공급단계의 실제 물량 미확보',status:'MISSING'};
    }
    const future=q.future?.find(row=>row.year===year),previous=q.future?.find(row=>row.year===year-1);
    if(!future)return {value:null,basis:'연도별 일정 미정',status:'MISSING'};
    if(period==='annual'){
      const value=future.source_units==null?null:year===now+1?future.source_units:previous?.source_units==null?null:Math.max(0,future.source_units-previous.source_units);
      return {value,basis:'원천 연도별 예정 물량 · 실제 실적 아님',status:'FORECAST'};
    }
    const baseline=measure==='SUPPLY'?q.current_notice_units:null;
    const value=future.source_units==null?baseline:baseline==null?future.source_units:baseline+future.source_units;
    return {value,basis:baseline==null?'확인된 예정량만 표시 · 현재 실적 미확보':'공고 연결 검토량 + 원천 예정량 · 실제 실적 아님',status:'FORECAST'};
  }
  function scopeOptions(){
    const rows=scopeRows().filter(r=>r.selection_enabled!==false),enabled=rows;
    if(!enabled.some(row=>row.id===selected))selected=(mode==='policy-progress'?enabled.find(row=>row.id==='POL_2025_0907'):null)?.id||enabled.find(row=>row.project_count>0||groupKind()==='project')?.id||enabled[0]?.id||'';
    $('policy-geo-scope').innerHTML=rows.map(row=>`<option value="${esc(row.id)}" ${row.id===selected?'selected':''} ${row.selection_enabled===false?'disabled':''}>${esc(row.name)}${row.selection_enabled===false?' (비활성 · 목표·사업 없음)':''}</option>`).join('');
    if(mode==='program-progress'){$('report-program-select').innerHTML=rows.map(r=>`<option value="${esc(r.id)}" ${r.id===selected?'selected':''} ${r.selection_enabled===false?'disabled':''}>${esc(r.name)}${r.selection_enabled===false?' (비활성 · 목표·사업 없음)':''}</option>`).join('')||'<option value="">9.7 연결 프로그램 없음</option>';}
    $('policy-geo-context').textContent=(scopeRow()?.name||'선택 대상 미확보')+' · 서울·경기 연결 후보만 집계 · 인천 범위 외';
    document.dispatchEvent(new CustomEvent('home:policy-geo-scope',{detail:{view:mode,id:selected,metrics}}));
  }
  function regionQuantity(region){
    const row=metrics?.groups?.region.find(item=>item.id===region);
    return scoped(row);
  }
  function rowFor(kind,id){
    if(kind==='region')return metrics?.groups?.region.find(row=>row.id===id);
    if(kind==='municipality')return metrics?.municipalities.find(row=>row.id===id);
    if(kind==='land')return metrics?.housing_lands.find(row=>row.id===id);
    return metrics?.blocks.find(row=>row.id===id);
  }
  function features(kind,source,rows){
    return {type:'FeatureCollection',features:(source?.features||[]).map(feature=>{
      const row=rows(feature.properties.id),q=kind==='region'?regionQuantity(feature.properties.id):scoped(row),metric=amount(q),v=metric.value;
      const [base,scale,cap]=kind==='region'?[600,32,15000]:kind==='municipality'?[100,14,4500]:[20,7,1200];
      return {...feature,properties:{...feature.properties,amount:v,has_scope:Boolean(q),
        value_status:metric.status,height_m:v==null?0:Math.min(cap,Math.round(base+Math.sqrt(Math.max(v,0))*scale)),
        color:!q?'#b4bec5':v==null?'#a8b1b7':metric.status==='FORECAST'?'#55a9c4':'#276ee5',
        outline:!q?'#b3bac0':q.late_count?'#d05031':q.verification_count?'#df962d':'#496a91'}};
    })};
  }
  function blockFeatures(){
    return {type:'FeatureCollection',features:(geometry?.block_anchors||[]).filter(row=>row.geometry_role==='LH_PUBLIC_BLOCK_LABEL_POINT'&&Number.isFinite(row.longitude)&&Number.isFinite(row.latitude)).map(row=>{
      const q=scoped(rowFor('block',row.id)),v=amount(q).value;
      return {type:'Feature',id:row.id,geometry:{type:'Point',coordinates:[row.longitude,row.latitude]},
        properties:{id:row.id,name:row.block,has_scope:Boolean(q),amount:v,
          color:!q?'#b4bec5':v==null?'#9da9b3':'#207ae8',radius:v==null?4:Math.min(15,5+Math.sqrt(v)/12)}};
    })};
  }
  function drawMap(){
    if(mode==='program-progress'){Policy907.showProgram(selected);return;}
    if(mode==='policy-progress'&&selected==='POL_2025_0907'){Policy907.show();return;}
    PolicyRegionMap.suspend();
    if(mode==='policy-progress'){if(geometry&&metrics&&completionMetrics)PolicySchematic.draw(geometry,{SUPPLY:metrics,COMPLETION:completionMetrics},selected,PolicyReport.policyInfo(selected));return;}
    if(!map||!map.getSource('pg-region')||!geometry||!metrics)return;
    map.getSource('pg-region').setData(features('region',geometry.regions,id=>rowFor('region',id)));
    map.getSource('pg-municipality').setData(features('municipality',geometry.municipalities,id=>rowFor('municipality',id)));
    map.getSource('pg-land').setData(features('land',geometry.housing_lands,id=>rowFor('land',id)));
    map.getSource('pg-block').setData(blockFeatures());
    drawPanel();
  }
  function levelAt(z){return z<8.7?'시도':z<10.3?'시군구':z<12.1?'시군구·사업분포':z<14?'지구 용지':'블록 위치';}
  function panelRow(row,label){
    const q=label==='시도'?regionQuantity(row.id):scoped(row),a=amount(q);
    return `<button type="button" data-pg-place="${esc(label)}:${esc(row.id)}"><span>${esc(row.name)}</span><strong>${display(a.value)}</strong><small>${esc(a.basis)}</small></button>`;
  }
  function drawPanel(){
    if(!metrics)return;
    const chosen=selectedPlace&&rowFor(selectedPlace.kind,selectedPlace.id),q=chosen?(selectedPlace.kind==='region'?regionQuantity(chosen.id):scoped(chosen)):groupKind()==='project'?{target_units:scopeRow()?.planned_units,current_notice_units:scopeRow()?.current_notice_units,future:[]}:scopeRow();
    const a=amount(q),progress=q||{},scope=scopeRow();
    $('policy-geo-title').textContent=chosen?.name||scope?.name||'선택 대상 미확보';
    $('policy-geo-kpis').innerHTML=`<div class="pg-primary"><small>${$('policy-geo-measure').value==='CAPACITY'?'현재 기준':year+'년'} · ${$('policy-geo-period').selectedOptions[0].textContent} · ${$('policy-geo-measure').selectedOptions[0].textContent}</small><strong>${display(a.value)}</strong><span>${esc(a.basis)}</span></div><dl><dt>사업계획 · 검토</dt><dd>${display(progress.target_units)}</dd><dt>공고 확인 공급 실적 · 연결 검토</dt><dd>${display(progress.current_notice_units)}</dd><dt>실제 입주량</dt><dd>미확보</dd><dt>일정 비교상 지연</dt><dd>${progress.late_count?num(progress.late_count)+'건':'판정 자료 미확보 또는 해당 없음'}</dd><dt>이행 확인 필요</dt><dd>${progress.verification_count?num(progress.verification_count)+'건':'확인 대상 미집계'}</dd></dl>`;
    const zoom=map?.getZoom()??7.45;
    const list=zoom<8.7?metrics.groups.region:zoom<12.1?metrics.municipalities:zoom<14?metrics.housing_lands:metrics.blocks;
    const label=zoom<8.7?'시도':zoom<12.1?'시군구':zoom<14?'용지':'블록';
    const ranked=list.filter(row=>{const v=amount(label==='시도'?regionQuantity(row.id):scoped(row));return v.value!=null;}).sort((x,y)=>amount(label==='시도'?regionQuantity(y.id):scoped(y)).value-amount(label==='시도'?regionQuantity(x.id):scoped(x)).value).slice(0,10);
    $('policy-geo-places').innerHTML=`<h3>${esc(levelAt(map?.getZoom()||8))} 주요 대상</h3>${ranked.length?ranked.map(row=>panelRow(row,label)).join(''):'<p>선택 범위의 위치·연도별 물량이 미확보입니다.</p>'}`;
    $('policy-geo-basis').textContent='공급량 높이는 제곱근 눈금의 주제도이며 실제 건물 높이가 아닙니다. '+(geometry?.geometry_note||'')+' '+metrics.notice;
    $('policy-geo-legend').innerHTML='<b>3D 높이 = 선택 물량</b><span><i class="pg-review"></i>계획·공고 연결 검토</span><span><i class="pg-forecast"></i>예정</span><span><i class="pg-missing"></i>미확보/범위 외</span><small>인천: 수집 범위 외 · 실입주 미확보</small>';
  }
  function yearControls(){
    const years=Array.from({length:11},(_,i)=>windowStart+i),place=selectedPlace&&rowFor(selectedPlace.kind,selectedPlace.id);
    const row=place?(selectedPlace.kind==='region'?regionQuantity(place.id):scoped(place)):scopeRow();
    const series=new Map((row?.annual_series||[]).map(item=>[item.year,item]));
    const measure=$('policy-geo-measure').value==='CAPACITY'?'SUPPLY':$('policy-geo-measure').value;
    const planLabel=$('policy-geo-measure').value==='CAPACITY'?'모집·공급 일정':$('policy-geo-measure').selectedOptions[0].textContent;
    const totals=years.map(y=>({year:y,plan:[...series].filter(([year])=>year<=y).reduce((sum,[,item])=>sum+(item[measure]||0),0),notice:measure==='SUPPLY'?[...series].filter(([year])=>year<=Math.min(y,currentYear())).reduce((sum,[,item])=>sum+(item.notice_units||0),0):null}));
    const target=row?.target_units??null,maxBar=Math.max(1,...years.flatMap(y=>{const item=series.get(y)||{};return [item[measure]||0,measure==='SUPPLY'?item.notice_units||0:0];}));
    const maxCumulative=Math.max(1,target||0,...totals.flatMap(item=>[item.plan,item.notice]));
    const bar=years.map(y=>{
      const item=series.get(y)||{},plan=item[measure],notice=measure==='SUPPLY'?item.notice_units:null;
      const planHeight=plan==null?0:Math.max(2,Math.round(plan/maxBar*76));
      const noticeHeight=notice==null?0:Math.max(2,Math.round(notice/maxBar*76));
      const current=totals.find(point=>point.year===y);
      const title=`${y}년 · ${planLabel} 연간 ${display(plan)} · 공고 연간 ${display(notice)} · 계획 누적 ${display(current.plan)} · 공고 누적 ${display(current.notice)}`;
      return `<button type="button" data-pg-year="${y}" class="pg-year${y===year?' active':''}${y>currentYear()?' forecast':''}" title="${esc(title)}" aria-label="${esc(title)}"><span class="pg-bar-area">${plan==null?'':`<i class="pg-plan-bar" data-pg-height="${planHeight}"></i>`}${notice==null?'':`<i class="pg-notice-bar" data-pg-height="${noticeHeight}"></i>`}${plan==null&&notice==null?'<em>·</em>':''}</span><b>${String(y).slice(2)}</b></button>`;
    }).join('');
    const x=i=>5+i*90/10,y=v=>83-v/maxCumulative*76;
    const planLine=totals.some(item=>item.plan>0)?'<polyline points="'+totals.map((item,i)=>x(i)+','+y(item.plan)).join(' ')+'" fill="none" stroke="#1f66d6" stroke-width="1.7"/>':'';
    const observed=totals.filter(item=>item.year<=currentYear());
    const noticeLine=measure==='SUPPLY'&&observed.some(item=>item.notice>0)?'<polyline points="'+observed.map((item,i)=>x(i)+','+y(item.notice)).join(' ')+'" fill="none" stroke="#139683" stroke-width="1.7"/>':'';
    const goal=target==null?'':'<line x1="5" y1="'+y(target)+'" x2="95" y2="'+y(target)+'" stroke="#dd9651" stroke-width="1" stroke-dasharray="2 2"/>';
    $('policy-geo-series-chart').innerHTML=bar+'<svg class="pg-cumulative-overlay" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">'+goal+planLine+noticeLine+'</svg>';
    $('policy-geo-series-chart').querySelectorAll('[data-pg-height]').forEach(element=>{element.style.height=element.dataset.pgHeight+'%';});
    const selected=totals.find(point=>point.year===year),actual=totals.find(point=>point.year===Math.min(year,currentYear()))?.notice||0;
    const ratio=measure==='SUPPLY'&&target>0?Math.min(100,100*actual/target).toFixed(1)+'%':'미확보';
    $('policy-geo-year-label').textContent=`${windowStart}–${windowStart+10} · 선택 ${year} · 연결계획 대비 ${ratio}`;
    $('policy-geo-next-period').disabled=windowStart>=currentYear()-5;
    $('policy-geo-prev-period').disabled=windowStart<=Math.min(2018,currentYear()-10);
    const note=document.getElementById('policy-geo-cumulative-note');
    if(note)note.innerHTML='<span><i class="pg-line-plan"></i>계획 누적</span><span><i class="pg-line-actual"></i>공고 누적</span><span><i class="pg-line-goal"></i>연결 사업계획 목표</span><strong>'+(measure==='SUPPLY'?'현재 공고 누적 '+display(actual):'해당 단계 실제 누적 미확보')+' / 목표 '+display(target)+'</strong>';
  }
  async function fetchData(){
    if(!active)return;
    const stamp=$('as-of').value||'',generation=++ticket;
    // These workspaces draw the map and chart from Policy907's single ledger.
    // Their pickers already have the catalogue; the legacy supply projection
    // is a second, unrelated full calculation and is not needed here.
    if(['policy-progress','program-progress'].includes(mode)){
      geometry=null;metrics=null;completionMetrics=null;scopeOptions();
      if(map){map.remove();map=null;document.getElementById('policy-geo-map').innerHTML='';}
      $('policy-geo-map-fallback').hidden=true;drawMap();return;
    }
    const geoKey=stamp,measure=mode==='policy-progress'?'SUPPLY':metricMeasure(),reference=analysisYear(),metricKey=`${stamp}:${measure}:${reference}`;
    if(!metrics)$('policy-geo-context').textContent='지역 공급계획을 확인하고 있습니다…';
    try{
      const params=apiParams();params.set('analysis_year',String(reference));params.set('measure',measure);
      const completionParams=apiParams();completionParams.set('analysis_year',String(reference));completionParams.set('measure','COMPLETION');
      const completionKey=`${stamp}:COMPLETION:${reference}`;
      const workspace=['policy-progress','program-progress'].includes(mode);
      const [shape,values,completion]=await Promise.all([
        workspace?Promise.resolve(null):shapeCache.get(geoKey+':'+mode)||request('/policy-geo/geometry?'+apiParams()).then(data=>(shapeCache.set(geoKey+':'+mode,data),data)),
        metricCache.get(metricKey)||request('/policy-geo/metrics?'+params).then(data=>(metricCache.set(metricKey,data),data)),
        Promise.resolve(null)]);
      if(generation!==ticket||!active)return;
      geometry=shape;metrics=values;completionMetrics=completion;itemIndex=new Map((values.items||[]).map(row=>[row.id,row]));seriesCache.clear();scopeOptions();yearControls();
      if(mode==='policy-progress'||mode==='program-progress'){
        if(map){map.remove();map=null;document.getElementById('policy-geo-map').innerHTML='';}
        $('policy-geo-map-fallback').hidden=true;drawMap();renderProgram();return;
      }
      await ensureMap();if(generation!==ticket||!active)return;
      drawMap();drawPanel();renderProgram();
    }catch(error){if(generation!==ticket)return;$('policy-geo-context').textContent='지역 그래프 조회 실패: '+error.message;$('policy-geo-map-fallback').hidden=false;}
  }
  async function ensureMap(){
    if(map){map.resize();return;}
    if(opening)return opening;
    opening=(async()=>{
      if(!document.querySelector('[data-maplibre-css]')){const css=document.createElement('link');css.rel='stylesheet';css.href='/poc/home/assets/vendor/maplibre/maplibre-gl.css';css.dataset.maplibreCss='true';document.head.append(css);}
      library=await import('/poc/home/assets/vendor/maplibre/maplibre-gl.mjs');library.setWorkerUrl('/poc/home/assets/vendor/maplibre/maplibre-gl-worker.mjs');
      const style={version:8,sources:{base:{type:'raster',tiles:[API+'/tiles/{z}/{x}/{y}.png'],tileSize:256,maxzoom:18,attribution:'© VWorld · 국토교통부'}},layers:[{id:'base',type:'raster',source:'base'}]};
      map=new library.Map({container:'policy-geo-map',style,center:[126.95,37.55],zoom:7.45,pitch:45,bearing:-16,minZoom:7,maxZoom:18,attributionControl:false});
      map.addControl(new library.NavigationControl({visualizePitch:true}),'bottom-left');
      await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(new Error('지도 초기화 시간 초과')),20000);map.once('load',()=>{clearTimeout(t);resolve();});map.once('error',event=>{if(!map?.isStyleLoaded()){clearTimeout(t);reject(event.error||new Error('지도 오류'));}});});
      for(const id of ['region','municipality','land','block'])map.addSource('pg-'+id,{type:'geojson',data:empty()});
      const polygon=(id,from,to)=>{
        map.addLayer({id:'pg-'+id+'-ground',type:'fill',source:'pg-'+id,paint:{'fill-color':['get','color'],'fill-opacity':['interpolate',['linear'],['zoom'],from,0.22,from+.5,0.38,to-.4,0.28,to,0]}});
        map.addLayer({id:'pg-'+id+'-volume',type:'fill-extrusion',source:'pg-'+id,paint:{'fill-extrusion-color':['get','color'],'fill-extrusion-height':['get','height_m'],'fill-extrusion-base':0,'fill-extrusion-opacity':['interpolate',['linear'],['zoom'],from,0,from+.4,0.78,to-.35,0.78,to,0]}});
        map.addLayer({id:'pg-'+id+'-outline',type:'line',source:'pg-'+id,paint:{'line-color':['get','outline'],'line-width':1.15,'line-opacity':['interpolate',['linear'],['zoom'],from,0,from+.3,0.8,to-.3,0.8,to,0]}});
        map.on('click','pg-'+id+'-volume',event=>selectPlace(id,event.features?.[0]?.properties?.id));
        map.on('mouseenter','pg-'+id+'-volume',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','pg-'+id+'-volume',()=>map.getCanvas().style.cursor='');
      };
      polygon('region',7,9.1);polygon('municipality',8.5,12.1);polygon('land',11.6,17.9);
      map.addLayer({id:'pg-block-circles',type:'circle',source:'pg-block',minzoom:13.2,paint:{'circle-color':['get','color'],'circle-radius':['get','radius'],'circle-stroke-color':'#fff','circle-stroke-width':1.5,'circle-opacity':.9}});
      map.on('click','pg-block-circles',event=>selectPlace('block',event.features?.[0]?.properties?.id));
      map.on('zoomend',drawPanel);map.on('moveend',drawPanel);
      map.fitBounds([[125.85,36.65],[128.08,38.44]],{padding:35,pitch:45,bearing:-16,duration:0,maxZoom:8.4});
      $('policy-geo-map-fallback').hidden=true;
    })().catch(error=>{$('policy-geo-context').textContent='3D 지도 오류: '+error.message;$('policy-geo-map-fallback').hidden=false;if(map){map.remove();map=null;}}).finally(()=>opening=null);
    return opening;
  }
  function selectPlace(kind,id){if(!id)return;selectedPlace={kind,id};yearControls();drawPanel();const row=rowFor(kind,id);if(!row)return;
    const zoom={region:9.4,municipality:11.35,land:13.4,block:15.3}[kind];
    if(!map)return;
    if(Number.isFinite(row.longitude)&&Number.isFinite(row.latitude))map.flyTo({center:[row.longitude,row.latitude],zoom,pitch:50,duration:650});
    else if(kind==='region')map.flyTo({center:id==='서울특별시'?[126.98,37.57]:[127.17,37.42],zoom,pitch:48,duration:650});
  }
  function fit(){if(mode==='policy-progress'){if(selected==='POL_2025_0907')Policy907.reset();else PolicySchematic.reset();return;}if(!map||!metrics)return;const kind=groupKind(),members=kind==='project'?[selected]:scopeRow()?.project_ids||[];
    const cities=metrics.municipalities.filter(row=>row.project_ids.some(id=>members.includes(id)));
    if(!cities.length){map.fitBounds([[125.85,36.65],[128.08,38.44]],{padding:40,pitch:45,bearing:-16,maxZoom:8.4});return;}
    const west=Math.min(...cities.map(row=>row.longitude)),east=Math.max(...cities.map(row=>row.longitude));
    const south=Math.min(...cities.map(row=>row.latitude)),north=Math.max(...cities.map(row=>row.latitude));
    map.fitBounds([[west-.09,south-.08],[east+.09,north+.08]],{padding:65,pitch:45,bearing:-16,maxZoom:10.2,duration:650});
  }
  function renderProgram(){if(mode==='program-progress'&&metrics)PolicyReport.scopeChanged(mode,selected,metrics);}
  function visible(view){const previousKind=groupKind(),changed=mode!==view;mode=view;active=true;if(year==null)year=currentYear();if(windowStart==null)windowStart=currentYear()-5;
    if(changed&&previousKind!==groupKind()){selected='';selectedPlace=null;}yearControls();if(!$('content').hidden)fetchData();requestAnimationFrame(resize);
  }
  function hidden(){active=false;++ticket;PolicyRegionMap.suspend();}
  function resize(){if(active&&map)map.resize();}
  function dataChanged(){const stamp=$('as-of').value||'';metrics=null;completionMetrics=null;metricCache.clear();if(stamp!==asOfKey){asOfKey=stamp;geometry=null;shapeCache.clear();year=Math.min(year??currentYear(),currentYear());windowStart=currentYear()-5;}if(active)fetchData();}
  function start(){
    $('report-program-select').addEventListener('change',e=>choose('program-progress',e.target.value));
    $('policy-geo-scope').addEventListener('change',event=>{selected=event.target.value;selectedPlace=null;if(mode==='policy-progress'){PolicySchematic.reset();PolicyDashboard.select(selected);}scopeOptions();yearControls();drawMap();renderProgram();fit();});
    $('policy-geo-measure').addEventListener('change',fetchData);
    $('policy-geo-period').addEventListener('change',()=>{drawMap();yearControls();});
    $('policy-geo-fit').addEventListener('click',fit);
    $('policy-geo-panel-toggle').addEventListener('click',()=>{const closed=$('policy-geo-panel').classList.toggle('collapsed');$('policy-geo-panel-toggle').textContent=closed?'펼치기':'접기';$('policy-geo-panel-toggle').setAttribute('aria-expanded',String(!closed));setTimeout(resize,220);});
    $('policy-geo-prev-period').addEventListener('click',()=>{windowStart-=5;year=windowStart+5;yearControls();fetchData();});
    $('policy-geo-current-period').addEventListener('click',()=>{windowStart=currentYear()-5;year=currentYear();yearControls();fetchData();});
    $('policy-geo-next-period').addEventListener('click',()=>{windowStart=Math.min(currentYear()-5,windowStart+5);year=windowStart+5;yearControls();fetchData();});
    document.addEventListener('click',event=>{const button=event.target.closest('[data-pg-year]');if(button){year=Number(button.dataset.pgYear);yearControls();fetchData();}const place=event.target.closest('[data-pg-place]');if(place){const [label,...rest]=place.dataset.pgPlace.split(':');selectPlace(({시도:'region',시군구:'municipality',용지:'land',블록:'block'})[label],rest.join(':'));}});
    document.addEventListener('home:policy-selected',event=>{if(mode!=='policy-progress'||!metrics)return;if(metrics.groups.policy.some(row=>row.id===event.detail.id)){selected=event.detail.id;selectedPlace=null;PolicySchematic.reset();scopeOptions();yearControls();drawMap();}});
    window.addEventListener('resize',resize);
  }
  function choose(view,id){setView(view);selected=id;selectedPlace=null;if(['policy-progress','program-progress'].includes(mode)){scopeOptions();drawMap();return;}if(metrics){scopeOptions();yearControls();drawMap();renderProgram();fit();}}
  return {start,visible,hidden,resize,dataChanged,choose};
})();
