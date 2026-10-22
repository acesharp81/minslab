'use strict';
const CollectionSchema=(()=>{
 const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const colors={stage:'#ffcc80',field:'#7ec2ff',source:'#80f3c3'};
 let generation=0,expanded=new Set(),dispose=()=>{};
 // Nodes describe the live field-provenance response, never the illustrative deck's sample.
 function graphData(data,stageId=''){
  const nodes=new Map(),edges=new Map();
  const add=node=>{if(!nodes.has(node.id))nodes.set(node.id,node);};
  const link=(from,to,count)=>{const id=JSON.stringify([from,to]);if(!edges.has(id))edges.set(id,{from,to,count});};
  for(const stage of data.stages||[]){
   if(stageId&&stage.id!==stageId)continue;
   const sid=JSON.stringify(['stage',stage.id]);add({id:sid,type:'stage',label:stage.label,stageId:stage.id,fieldCount:stage.fields.length});
   for(const field of stage.fields){
    const fid=JSON.stringify(['field',stage.id,field.field]);add({id:fid,type:'field',label:field.label,path:field.path,stageId:stage.id,stageLabel:stage.label});link(sid,fid);
    for(const source of field.sources){
     let host='';try{host=new URL(source.url).hostname;}catch(_){}
     const sourceId=JSON.stringify(['source',source.source_id,source.authority,host]);
     add({id:sourceId,type:'source',label:source.name,authority:source.authority,authorityLabel:source.authority_label,url:source.url});
     link(fid,sourceId,source.count);
    }
   }
  }
  return {nodes:[...nodes.values()],edges:[...edges.values()]};
 }
 function fieldsHtml(data){
  return '<div class="schema-stages">'+data.stages.map((stage,i)=>'<details class="schema-stage" data-stage="'+e(stage.id)+'"'+(expanded.has(stage.id)?' open':'')+'><summary><span class="schema-step">'+(i+1)+'</span><strong>'+e(stage.label)+'</strong><span>'+stage.fields.length+'개 수집 항목</span><span class="schema-chevron">펼치기</span></summary><div class="schema-fields">'+(stage.fields.length?stage.fields.map(field=>'<section class="schema-field"><div><strong>'+e(field.label)+'</strong><code>'+e(field.path)+'</code></div><span class="schema-arrow" aria-hidden="true">→</span><ul>'+field.sources.map(s=>'<li><span class="schema-authority '+e(s.authority.toLowerCase())+'">'+e(s.authority_label)+'</span> '+sourceLink(s.name,s.url)+' <strong>('+Number(s.count).toLocaleString('ko-KR')+'건)</strong></li>').join('')+'</ul></section>').join(''):'<p>이 범위에서 연결된 수집 원천 항목이 없습니다. 실제 실적 0을 의미하지 않습니다.</p>')+'</div></details>').join('')+'</div>';
 }
 function sourceLink(label,url){const safe=safeUrl(url);return safe?'<a href="'+e(safe)+'" target="_blank" rel="noopener noreferrer">'+e(label)+' ↗</a>':e(label);}
 function html(data){
  const graph=graphData(data),count=type=>graph.nodes.filter(n=>n.type===type).length;
  return '<div class="schema-map-heading"><div><span class="schema-eyebrow">COLLECTION STARMAP</span><h3>단계별 수집 항목과 출처</h3><p>흩어진 원천에서 수집 항목까지, 실제 데이터의 연결을 확인하세요.</p></div><div class="schema-actions"><button type="button" data-schema-expand>전체 확장</button><button type="button" data-schema-collapse>전체 축소</button><a href="'+API+'/collection-schema/export.csv">수집 항목 CSV ↓</a></div></div>'+
   '<div class="schema-map-controls"><div class="schema-stage-filters" role="group" aria-label="관계망 단계 선택"><button type="button" data-schema-stage="" aria-pressed="true">전체 단계</button>'+data.stages.map(s=>'<button type="button" data-schema-stage="'+e(s.id)+'" aria-pressed="false">'+e(s.label)+'</button>').join('')+'</div><button type="button" class="schema-view-toggle" data-schema-view aria-pressed="false">항목별로 펼쳐보기 ↗</button></div>'+
   '<div class="schema-map-layout"><div class="schema-star-visual"><canvas data-schema-canvas role="img" aria-label="단계, 수집 항목, 출처의 실제 연결 관계망. 항목별로 펼쳐보기에서 같은 정보를 목록으로 확인할 수 있습니다."></canvas><span class="schema-star-corner">● LIVE DATA · 3D RELATIONSHIP</span><div class="schema-star-actions"><button type="button" data-schema-replay>다시 재생 ↺</button><button type="button" data-schema-motion aria-pressed="true">Ⅱ 움직임 멈추기</button></div><div class="schema-star-legend"><span><i class="schema-dot-stage"></i>단계</span><span><i class="schema-dot-field"></i>수집 항목</span><span><i class="schema-dot-source"></i>출처</span></div><p class="schema-star-hint">노드 선택 · 마우스를 움직여 시점 변경 · 위치·깊이는 시각화 배치</p></div>'+
   '<aside class="schema-map-aside"><div class="schema-map-stats"><div><span>수집 항목</span><strong>'+count('field').toLocaleString('ko-KR')+'</strong><small>'+count('stage')+'개 단계</small></div><div><span>출처 경로</span><strong>'+count('source').toLocaleString('ko-KR')+'</strong><small>경로·도메인 중복 제거</small></div><div><span>항목 연결</span><strong>'+graph.edges.filter(l=>l.count!==undefined).length.toLocaleString('ko-KR')+'</strong><small>수집 항목 ↔ 출처</small></div></div>'+
   '<label class="schema-node-picker">연결 항목 선택<select data-schema-node aria-label="관계망 연결 항목 선택"></select></label><div class="schema-node-detail" data-schema-detail aria-live="polite"></div></aside></div>'+
   '<div class="schema-structured" hidden>'+fieldsHtml(data)+'</div><div class="schema-map-foot"><span>'+e(data.as_of_date)+' 기준 · '+e(data.project_count)+'개 사업 원천 기록'+(data.refreshing?' · 최신 변경 반영 중':'')+'</span><span>단계 → 수집 항목 → 출처</span></div>'+
   '<p class="schema-scope">'+e(data.scope)+'<br>'+e(data.count_note)+'</p>';
 }
 function mount(host,data){
  let graph,points=[],selected=null,hovered=null,stageId='',frame=0,resizeObserver,alive=true;
  const canvas=host.querySelector('[data-schema-canvas]'),ctx=canvas.getContext('2d'),picker=host.querySelector('[data-schema-node]'),detail=host.querySelector('[data-schema-detail]');
  const linkedIds=id=>new Set(graph.edges.flatMap(l=>l.from===id?[l.to]:l.to===id?[l.from]:[]));
  // Reference effect: seeded radial positions, 2.55s cubic reveal, twinkling and a pulsing core.
  // A perspective projection and shaded sphere sprites add depth without changing graph edges.
  function seed(id){let h=2166136261;for(let j=0;j<id.length;j++)h=Math.imul(h^id.charCodeAt(j),16777619);return h>>>0;}
  const motionQuery=window.matchMedia('(prefers-reduced-motion: reduce)');
  let motion=!motionQuery.matches,inView=true,sceneTime=0,entryStart=0,lastNow=0,lastDraw=0,yaw=0;
  let tiltX=0,tiltY=0,targetX=0,targetY=0,geometry=[],intersectionObserver;
  const sprites={};
  for(const type of ['stage','field','source']){
   const sprite=document.createElement('canvas');sprite.width=sprite.height=112;const gl=sprite.getContext('2d');
   const halo=gl.createRadialGradient(56,56,12,56,56,56);halo.addColorStop(0,colors[type]+'80');halo.addColorStop(.45,colors[type]+'30');halo.addColorStop(1,colors[type]+'00');gl.fillStyle=halo;gl.fillRect(0,0,112,112);
   const shade=gl.createRadialGradient(48,45,1,59,59,28);shade.addColorStop(0,'#ffffff');shade.addColorStop(.18,'#f0ffff');shade.addColorStop(.42,colors[type]);shade.addColorStop(.78,type==='stage'?'#a9702e':type==='field'?'#276697':'#247d72');shade.addColorStop(1,'#061626');gl.fillStyle=shade;gl.beginPath();gl.arc(56,56,25,0,Math.PI*2);gl.fill();
   gl.strokeStyle=colors[type]+'a0';gl.lineWidth=.8;gl.stroke();gl.strokeStyle='#ffffffb0';gl.lineWidth=1.1;gl.beginPath();gl.arc(54,54,21,Math.PI*1.05,Math.PI*1.6);gl.stroke();sprites[type]=sprite;
  }
  function makeGeometry(){
   geometry=graph.nodes.map(node=>{const h=seed(node.id),items=graph.nodes.filter(n=>n.type===node.type),index=items.findIndex(n=>n.id===node.id);
    const theta=node.type==='stage'?index/Math.max(items.length,1)*Math.PI*2-Math.PI/2:(h%100000)/100000*Math.PI*2;
    const latitude=(((h>>>13)%1000)/1000-.5)*(node.type==='stage'?.6:1.8),rank={stage:.38,field:.71,source:1}[node.type];
    const radius=rank*(.78+((h>>>7)%100)/470);
    return {...node,wx:Math.cos(theta)*Math.cos(latitude)*radius,wy:Math.sin(theta)*Math.cos(latitude)*radius,wz:Math.sin(latitude)*radius,seed:h%120/100};
   });
  }
  function draw(now){
   frame=0;
   if(!alive||!inView||document.hidden||!ctx||!canvas.clientWidth){lastNow=0;return;}
   if(motion&&now-lastDraw<32){schedule();return;} // Cap animation at 30 fps.
   const dt=lastNow?Math.min(64,now-lastNow):0;lastNow=now;lastDraw=now;
   if(motion){sceneTime+=dt;if(!hovered&&!selected)yaw+=dt*.000035;tiltX+=(targetX-tiltX)*.07;tiltY+=(targetY-tiltY)*.07;}
   const w=canvas.clientWidth,h=canvas.clientHeight,dpr=Math.min(window.devicePixelRatio||1,2);
   if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
   ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
   const progress=motion?Math.min(1,Math.max(.025,(sceneTime-entryStart)/2550)):1,ep=1-Math.pow(1-progress,3),cx=w/2,cy=h*.49;
   const cyaw=Math.cos(yaw+tiltX),syaw=Math.sin(yaw+tiltX),pitch=.22+tiltY,cp=Math.cos(pitch),sp=Math.sin(pitch),byId=new Map();
   points=geometry.map(node=>{const x=node.wx*cyaw+node.wz*syaw,z0=-node.wx*syaw+node.wz*cyaw,y=node.wy*cp-z0*sp,z=node.wy*sp+z0*cp,perspective=3.7/(3.7-z),depth=(z+1)/2;
    const p={...node,x:cx+x*w*.43*perspective*ep,y:cy+y*h*.39*perspective*ep,z,depth,perspective,r:({stage:11,field:6,source:3.8}[node.type])*perspective};byId.set(p.id,p);return p;});
   const focus=hovered||selected,neighbors=focus?linkedIds(focus):new Set();
   // Soft atmosphere, orbit ellipses, and the reference's breathing central ring.
   const atmosphere=ctx.createRadialGradient(cx,cy,10,cx,cy,Math.min(w,h)*.48);atmosphere.addColorStop(0,'#29dab813');atmosphere.addColorStop(.55,'#4b9dce0c');atmosphere.addColorStop(1,'#09142200');ctx.fillStyle=atmosphere;ctx.fillRect(0,0,w,h);
   ctx.save();ctx.translate(cx,cy);ctx.rotate(-.24+tiltX*.1);ctx.strokeStyle='#7ec2ff12';ctx.lineWidth=1;
   for(const r of [.62,.88]){ctx.beginPath();ctx.ellipse(0,0,w*.44*r,h*.30*r,0,0,Math.PI*2);ctx.stroke();}ctx.restore();
   ctx.strokeStyle='rgba(112,252,209,.45)';ctx.lineWidth=1;ctx.beginPath();ctx.arc(cx,cy,15+Math.sin(sceneTime*.0017)*4,0,Math.PI*2);ctx.stroke();
   const visibleEdges=graph.edges.slice(0,Math.floor(graph.edges.length*progress));
   visibleEdges.forEach((l,i)=>{const a=byId.get(l.from),b=byId.get(l.to),active=l.from===focus||l.to===focus,depth=(a.depth+b.depth)/2;
    ctx.globalAlpha=active?.9:focus?.055:(.18+depth*.3)*(.23+ep*.6);ctx.lineWidth=active?1.7:.45+depth*.6;
    const line=ctx.createLinearGradient(a.x,a.y,b.x,b.y);line.addColorStop(0,i%7===0?'#80f3c3':'#7ec2ff');line.addColorStop(1,i%7===0?'#b8ffe5':'#789ab9');ctx.strokeStyle=line;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();
    if((active||i%17===0)&&motion&&progress===1){const t=(sceneTime*.00017+i*.137)%1;ctx.globalAlpha=active?.9:.55;ctx.fillStyle='#d2fff0';ctx.shadowColor='#80f3c3';ctx.shadowBlur=6;ctx.beginPath();ctx.arc(a.x+(b.x-a.x)*t,a.y+(b.y-a.y)*t,active?1.7:1.1,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;}
   });
   // Keep stage/selected nodes in the foreground, with opaque sphere cores masking edges.
   const childIds=new Set(graph.edges.filter(l=>l.from===selected).map(l=>l.to)),labelPoints=[];
   const priority=p=>(p.id===selected?2:p.type==='stage'?1:0);
   for(const p of [...points].sort((a,b)=>priority(a)-priority(b)||a.z-b.z)){
    const active=!focus||p.id===focus||neighbors.has(p.id),twinkle=.55+.4*Math.sin(sceneTime*.001+p.seed*6)**2;
    const radius=(p.r+(p.id===focus?3:0)+Math.sin(sceneTime*.002+p.seed*5)*.35)*ep,size=radius*4.48;
    ctx.globalAlpha=1;ctx.fillStyle='#071424';ctx.beginPath();ctx.arc(p.x,p.y,radius*1.02,0,Math.PI*2);ctx.fill();
    ctx.globalAlpha=active?.9+twinkle*.1:.22;ctx.drawImage(sprites[p.type],p.x-size/2,p.y-size/2,size,size);
    if(p.id===focus){ctx.globalAlpha=.55+.3*Math.sin(sceneTime*.003)**2;ctx.strokeStyle=colors[p.type];ctx.lineWidth=1;ctx.beginPath();ctx.ellipse(p.x,p.y,radius+8,(radius+8)*.42,-.3,0,Math.PI*2);ctx.stroke();}
    if((p.type==='stage'&&active)||p.id===selected||childIds.has(p.id))labelPoints.push({...p,radius});
   }
   // Draw every direct child's name last so lines and other nodes cannot cover the labels.
   const labelBoxes=[];
   labelPoints.sort((a,b)=>priority(b)-priority(a)).forEach(p=>{
    ctx.font='600 '+(w<500?11:12)+'px system-ui';
    let label=w<500&&p.type==='stage'?p.label.replace('건축·',''):p.label;
    const maxWidth=Math.min(w-30,p.type==='source'?210:160);
    while(ctx.measureText(label).width>maxWidth&&label.length>2)label=label.slice(0,-2)+'…';
    const width=ctx.measureText(label).width+12,height=22,baseY=p.y+p.radius+8;
    const positions=[0,24,-38,48,-62,72,-86,96,-110].map(d=>({x:Math.max(8,Math.min(w-width-8,p.x-width/2)),y:Math.max(w<500?85:50,Math.min(h-height-58,baseY+d)),width,height}));
    const box=positions.find(b=>!labelBoxes.some(a=>b.x<a.x+a.width+4&&b.x+b.width+4>a.x&&b.y<a.y+a.height+3&&b.y+b.height+3>a.y))||positions[0];labelBoxes.push(box);
    ctx.globalAlpha=ep;
    if(Math.abs(box.y-baseY)>8){ctx.strokeStyle=colors[p.type]+'88';ctx.lineWidth=.8;ctx.beginPath();ctx.moveTo(p.x,p.y+p.radius);ctx.lineTo(box.x+box.width/2,box.y+height/2);ctx.stroke();}
    ctx.fillStyle=p.id===selected?'#153548f2':'#071725dc';ctx.fillRect(box.x,box.y,width,height);
    ctx.fillStyle=childIds.has(p.id)?'#d4f2ff':'#fff0ce';ctx.textAlign='left';ctx.fillText(label,box.x+6,box.y+15);
   });
   ctx.globalAlpha=1;
   if(hovered){const p=byId.get(hovered);ctx.font='600 12px system-ui';const width=Math.min(w-20,ctx.measureText(p.label).width+20),x=Math.max(10,Math.min(w-width-10,p.x-width/2)),y=Math.max(60,p.y-p.r-21);ctx.fillStyle='#163248ed';ctx.fillRect(x,y-16,width,27);ctx.fillStyle='#f3f8ff';ctx.textAlign='left';ctx.fillText(p.label,x+10,y+2,width-20);}
   if(motion)schedule();
  }
  function schedule(){if(!frame&&alive&&inView&&!document.hidden)frame=requestAnimationFrame(draw);}
  const motionButton=host.querySelector('[data-schema-motion]');
  function motionLabel(){motionButton.textContent=motion?'Ⅱ 움직임 멈추기':'▶ 움직임 켜기';motionButton.setAttribute('aria-pressed',String(motion));}
  motionButton.onclick=()=>{motion=!motion;lastNow=0;motionLabel();schedule();};motionLabel();
  host.querySelector('[data-schema-replay]').onclick=()=>{motion=true;motionLabel();entryStart=sceneTime;lastNow=0;schedule();};
  function visibility(){lastNow=0;if(document.hidden){cancelAnimationFrame(frame);frame=0;}else schedule();}
  function motionPreference(){motion=!motionQuery.matches;lastNow=0;motionLabel();schedule();}
  document.addEventListener('visibilitychange',visibility);motionQuery.addEventListener('change',motionPreference);
  intersectionObserver=new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;lastNow=0;if(inView)schedule();else {cancelAnimationFrame(frame);frame=0;}});intersectionObserver.observe(canvas);
  function show(id){
   selected=id||null;picker.value=id||'';const node=graph.nodes.find(n=>n.id===id);
   if(!node){detail.innerHTML='<span class="schema-detail-kicker">수집 원천을 따라가 보세요</span><h4>하나의 항목, 여러 출처</h4><p>단계 또는 노드를 선택하면 연결된 수집 항목과 실제 출처를 보여줍니다.</p><p class="schema-detail-note">건수는 원천 기록 수이며, 공급 호수나 전체 수집량이 아닙니다.</p>';schedule();return;}
   const neighbors=linkedIds(id),items=graph.nodes.filter(n=>neighbors.has(n.id));
   const relation=(n)=>graph.edges.find(l=>(l.from===id&&l.to===n.id)||(l.to===id&&l.from===n.id));
   detail.innerHTML='<span class="schema-detail-kicker">'+({stage:'공급 단계',field:'수집 항목',source:node.authorityLabel||'출처'})[node.type]+'</span><h4>'+e(node.label)+'</h4>'+(node.path?'<code>'+e(node.path)+'</code>':'')+(node.type==='field'?'<p>'+e(node.stageLabel)+' · '+items.filter(n=>n.type==='source').length+'개 출처</p>':'')+(node.type==='source'?'<p>'+sourceLink('출처 페이지 열기',node.url)+'</p>':'')+'<ul>'+items.map(n=>{const l=relation(n);return '<li><button type="button" data-schema-select="'+e(n.id)+'">'+e(n.type==='field'&&node.type==='source'?n.stageLabel+' · '+n.label:n.label)+'</button>'+(n.type==='source'?'<span class="schema-authority '+e((n.authority||'UNKNOWN').toLowerCase())+'">'+e(n.authorityLabel)+'</span>':'')+(l.count!==undefined?'<strong>'+Number(l.count).toLocaleString('ko-KR')+'건</strong>':'')+'</li>';}).join('')+'</ul>';
   detail.querySelectorAll('[data-schema-select]').forEach(b=>b.onclick=()=>show(b.dataset.schemaSelect));schedule();
  }
  function selectStage(id){
   stageId=id;hovered=null;graph=graphData(data,id);makeGeometry();entryStart=sceneTime;picker.innerHTML='<option value="">선택하세요</option>'+['stage','field','source'].map(type=>'<optgroup label="'+({stage:'단계',field:'수집 항목',source:'출처'})[type]+'">'+graph.nodes.filter(n=>n.type===type).map(n=>'<option value="'+e(n.id)+'">'+e((n.type==='field'?n.stageLabel+' · ':'')+n.label)+'</option>').join('')+'</optgroup>').join('');
   host.querySelectorAll('[data-schema-stage]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.schemaStage===id)));
   host.querySelectorAll('details[data-stage]').forEach(d=>d.hidden=!!id&&d.dataset.stage!==id);
   show(id?JSON.stringify(['stage',id]):'');
  }
  function structured(on){host.querySelector('.schema-map-layout').hidden=on;host.querySelector('.schema-structured').hidden=!on;const b=host.querySelector('[data-schema-view]');b.textContent=on?'수집 관계망 보기 ↺':'항목별로 펼쳐보기 ↗';b.setAttribute('aria-pressed',String(on));if(!on)schedule();}
  host.querySelector('[data-schema-view]').onclick=()=>structured(host.querySelector('.schema-structured').hidden);
  host.querySelector('[data-schema-expand]').onclick=()=>{selectStage('');structured(true);host.querySelectorAll('details').forEach(d=>{d.open=true;expanded.add(d.dataset.stage);});};
  host.querySelector('[data-schema-collapse]').onclick=()=>{selectStage('');structured(true);host.querySelectorAll('details').forEach(d=>{d.open=false;expanded.delete(d.dataset.stage);});};
  host.querySelectorAll('details[data-stage]').forEach(d=>d.addEventListener('toggle',()=>d.open?expanded.add(d.dataset.stage):expanded.delete(d.dataset.stage)));
  host.querySelectorAll('[data-schema-stage]').forEach(b=>b.onclick=()=>selectStage(b.dataset.schemaStage));picker.onchange=()=>show(picker.value);
  function hit(event){const rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;return points.map(p=>({p,d:Math.hypot(p.x-x,p.y-y)})).filter(v=>v.d<=v.p.r+7).sort((a,b)=>a.d-b.d||b.p.z-a.p.z)[0]?.p;}
  canvas.onpointermove=event=>{const bounds=canvas.getBoundingClientRect();targetX=((event.clientX-bounds.left)/bounds.width-.5)*.30;targetY=((event.clientY-bounds.top)/bounds.height-.5)*.18;const id=hit(event)?.id||null;if(hovered!==id){hovered=id;canvas.style.cursor=id?'pointer':'default';schedule();}};
  canvas.onpointerleave=()=>{hovered=null;targetX=targetY=0;schedule();};canvas.onclick=event=>show(hit(event)?.id||'');
  resizeObserver=new ResizeObserver(schedule);resizeObserver.observe(canvas);selectStage('');
  return ()=>{alive=false;cancelAnimationFrame(frame);resizeObserver.disconnect();intersectionObserver.disconnect();document.removeEventListener('visibilitychange',visibility);motionQuery.removeEventListener('change',motionPreference);};
 }
 async function load(sources){
  const token=++generation,host=document.getElementById('collection-schema-panel');dispose();
  host.innerHTML='<h3>단계별 수집 항목과 출처</h3><p role="status">수집 관계망을 불러오고 있습니다. 아래 출처 목록은 바로 이용할 수 있습니다.</p>';
  try{
   let data;
   for(let attempt=0;attempt<30;attempt++){
    data=await request('/collection-schema');if(token!==generation||state.view!=='sources')return;
    if(data.status==='READY')break;
    if(data.status==='RETRYING')throw Error('집계를 다시 확인해야 합니다.');
    await new Promise(resolve=>setTimeout(resolve,1500));
   }
   if(data.status!=='READY')throw Error('집계가 진행 중입니다. 잠시 후 다시 시도하세요.');
   host.innerHTML=html(data);dispose=mount(host,data);renderSources([...sources,...(data.document_sources||[])]);
  }catch(error){
   if(token!==generation)return;
   host.innerHTML='<h3>단계별 수집 항목과 출처</h3><p>'+e(error.message)+'</p><button type="button" data-schema-retry>다시 조회</button>';
   host.querySelector('button').onclick=()=>load(sources);
  }
 }
 return {load,html,graphData};
})();
