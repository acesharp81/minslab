'use strict';
/* Official administrative outlines; housing quantities never come from mesh geometry. */
const PolicyRegionMap = (() => {
  const regions = ['서울특별시', '인천광역시', '경기도'];
  const short = {'서울특별시':'SEOUL', '인천광역시':'INCHEON', '경기도':'GYEONGGI'};
  let threePromise, mode = '3d', generation = 0, lastHost, lastModel, cards = [], shellKey="";
  const escape = value => esc(String(value ?? ''));
  const units = value => num(value) + '호';
  const ringArea = ring => Math.abs(ring.reduce((a,p,i) => {const q=ring[(i+1)%ring.length];return a+p[0]*q[1]-q[0]*p[1];},0));
  const center = ring => ring.reduce((a,p) => [a[0]+p[0]/ring.length,a[1]+p[1]/ring.length],[0,0]);
  function layout(shapes) {
    const largestArea=Math.max(...shapes.flatMap(p=>p.rings.map(ringArea)),0);
    const visible=p=>p.rings.filter(r=>r.some(v=>v[0]>126.1)&&ringArea(r)>=largestArea*.003).sort((a,b)=>ringArea(b)-ringArea(a)).slice(0,p.aggregate?999:1);
    const mainland = shapes.flatMap(visible);
    const points = mainland.flat(), xs=points.map(p=>p[0]), ys=points.map(p=>p[1]);
    const mid=[(Math.min(...xs)+Math.max(...xs))/2,(Math.min(...ys)+Math.max(...ys))/2];
    const scale=164/Math.max((Math.max(...xs)-Math.min(...xs))*.79,Math.max(...ys)-Math.min(...ys));
    const project=p=>[(p[0]-mid[0])*.79*scale,(p[1]-mid[1])*scale];
    return shapes.map(p => {
      const rings=visible(p);
      const largest=rings.slice().sort((a,b)=>ringArea(b)-ringArea(a))[0];
      let anchor=[p.longitude,p.latitude];
      if(largest && (anchor[0]<126.1 || !Number.isFinite(anchor[0])))anchor=center(largest);
      return {...p,rings:rings.map(r=>r.map(project)),holes:rings.map(r=>(p.holes?.[p.rings.indexOf(r)]||[]).filter(h=>ringArea(h)>largestArea*.00002).map(h=>h.map(project))),anchor:project(anchor),islands:[]};
    });
  }
  function dispose(){for(const c of cards){c.observer?.disconnect();c.scene?.traverse(o=>{o.geometry?.dispose();if(o.material){for(const m of [o.material].flat())m.dispose();}});c.intentionalLoss=true;c.renderer?.dispose();c.renderer?.forceContextLoss();}cards=[];}
  function color(value,max){if(!value)return '#acd1e1';const t=Math.sqrt(value/Math.max(max,1));return `hsl(201, ${48+37*t}%, ${78-48*t}%)`;}
  function islandInset(shapes){
    const islands=shapes.flatMap(p=>p.islands.map(r=>({id:p.id,name:p.name,ring:r})));if(!islands.length)return '';
    const all=islands.flatMap(p=>p.ring),xs=all.map(p=>p[0]),ys=all.map(p=>p[1]),w=Math.min(...xs),e=Math.max(...xs),s=Math.min(...ys),n=Math.max(...ys),scale=Math.min(85/(e-w),55/(n-s));
    return '<div class="prm-inset"><svg viewBox="0 0 100 70" aria-label="인천 서해 도서 별도 위치">'+islands.map(p=>'<path data-d907-city="'+escape(p.id)+'" d="'+p.ring.map((v,i)=>(i?'L':'M')+(7+(v[0]-w)*scale).toFixed(1)+','+(62-(v[1]-s)*scale).toFixed(1)).join('')+'Z"><title>'+escape(p.name)+'</title></path>').join('')+'</svg><span>서해 도서 · 별도 위치</span></div>';
  }
  function createShell(host,model){
    dispose();const control=document.getElementById('policy-map-controls'),places=model.allowedRegions||regions;
    control.innerHTML='<div class="prm-heading"><h3>지역·표시 기준</h3><div class="prm-view-tabs" role="tablist" aria-label="지역 그래프 표현 방식"><button role="tab" data-prm-mode="2d">2D</button><button role="tab" data-prm-mode="3d">3D</button></div></div><div class="pd-region-tabs" role="tablist" aria-label="추진현황 조회 지역">'+[['','전체'],['서울특별시','서울'],['경기도','경기'],['인천광역시','인천']].filter(([r])=>r?places.includes(r):places.length>1).map(([r,n])=>'<button role="tab" data-d907-region="'+r+'">'+n+'</button>').join('')+'</div><div class="d907-map-controller"><div class="prm-stage-group" role="group" aria-label="추진 단계">'+Object.entries(model.stages).map(([k,label])=>'<button data-d907-stage="'+k+'"><i class="d907-color-'+k+'"></i>'+label+'</button>').join('')+'</div><label>기준 연도 <b>'+model.year+'</b><input aria-label="지도·진행현황 기준 연도" data-d907-year type="range" min="'+(model.currentYear-5)+'" max="'+(model.currentYear+5)+'" value="'+model.year+'"></label></div><div class="prm-year-limits"><span>'+ (model.currentYear-5)+'</span><span>'+model.currentYear+' 현재</span><span>'+(model.currentYear+5)+'</span></div><button class="pw-now" data-d907-now>현재 연도로</button><div class="d907-map-readout"></div>';
    const displayRegion=model.region||'수도권';
    host.innerHTML='<h3 class="pw-map-title">'+(model.region?escape(model.region)+' 시군구별 추진현황':'수도권 지역별 추진현황')+'</h3><div class="prm-cards pd-single-region"><article class="prm-card" data-prm-region="'+escape(displayRegion)+'"><header><span class="prm-selected-tag" hidden></span></header><div class="prm-stats"></div><div class="prm-scene"><div class="prm-surface"></div><div class="prm-labels"></div><div class="prm-hover" role="status" hidden></div><div class="prm-scale"><span>적음</span><i></i><span>많음</span></div></div><footer></footer><details class="prm-accessible"><summary>지역별 수치 보기</summary><div></div></details></article></div>';
    cards=[{region:displayRegion,node:host.querySelector('.prm-card'),shapes:layout(model.shapes),meshes:[],labels:[]}];
    control.querySelectorAll('[data-prm-mode]').forEach(b=>b.addEventListener('click',()=>{mode=b.dataset.prmMode;render(host,lastModel.rawModel||lastModel);}));
  }
  function mapModel(raw){
    if(raw.allowedRegions?.length===1&&!raw.region)raw={...raw,region:raw.allowedRegions[0]};
    if(raw.region)return {...raw,rawModel:raw,shapes:raw.shapes.filter(s=>s.region===raw.region)};
    const anchors={'서울특별시':[126.98,37.56],'경기도':[127.08,37.32],'인천광역시':[126.63,37.48]},places=raw.allowedRegions||regions;
    const shapes=places.map(r=>raw.regionShapes?.find(s=>s.region===r)||({id:r,name:r,region:r,aggregate:true,rings:raw.shapes.filter(p=>p.region===r).flatMap(p=>p.rings.filter(ring=>ring.some(v=>v[0]>126.1)).sort((a,b)=>ringArea(b)-ringArea(a)).slice(0,1)),longitude:anchors[r][0],latitude:anchors[r][1]})).filter(p=>p.rings.length);
    const values=Object.fromEntries(places.map(r=>[r,raw.regions[r]])),sum=Object.values(raw.regions).reduce((t,r)=>({target:t.target+r.target,value:t.value+r.value,known:t.known+r.known,unplaced:t.unplaced+r.unplaced}),{target:0,value:0,known:0,unplaced:0});
    return {...raw,rawModel:raw,aggregate:true,shapes,values,regions:{...raw.regions,'수도권':sum},max:raw.regionMax||raw.max};
  }
  function values(c,model){
    // Keep relief low: tall foreground districts obscure the regions behind them.
    const max=model.max||1;
    return c.shapes.map(p=>({...p,...model.values[p.id],height:3+(model.values[p.id]?.value>0?12*Math.sqrt(Math.min(model.values[p.id].value/max,1)):0),color:color(model.values[p.id]?.value||0,max)}));
  }
  function labels(c,items,project){
    const layer=c.node.querySelector('.prm-labels');layer.innerHTML='';const used=[];
    for(const p of items.slice().sort((a,b)=>(b.id===lastModel.city)-(a.id===lastModel.city)||Number(!!b.delayed)-Number(!!a.delayed)||(b.value||0)-(a.value||0))){
      if(!p.rings.length)continue;
      const xy=project(p),value=p.value||0,width=(value?56:46)+(p.delayed?20:0),height=value?29:20;
      if(xy[0]<8||xy[0]>layer.clientWidth-8||xy[1]<6||xy[1]>layer.clientHeight-20)continue;
      const box=[xy[0]-width/2,xy[1]-height/2,width,height];
      const overlaps=()=>used.some(b=>box[0]<b[0]+b[2]+2&&box[0]+box[2]+2>b[0]&&box[1]<b[1]+b[3]+2&&box[1]+box[3]+2>b[1]);
      if(!lastModel.aggregate&&overlaps()){if(!p.delayed&&p.id!==lastModel.city)continue;for(let step=1;step<12&&overlaps();step++){box[1]=xy[1]-height/2+(step%2?1:-1)*Math.ceil(step/2)*(height+3);}xy[1]=box[1]+height/2;}
      used.push(box);const b=document.createElement('button');b.className='prm-label'+(value?' has-value':'')+(p.id===lastModel.city?' selected':'');b.dataset.d907City=p.id;b.style.left=xy[0]+'px';b.style.top=xy[1]+'px';
      b.innerHTML=(p.delayed?'<span class="prm-delay-marker" aria-hidden="true">!</span>':'')+escape(p.name.replace(c.region+' ',''))+(value?'<strong>'+units(value)+'</strong>':lastModel.aggregate?'<strong>확인량 미확보</strong>':'');b.title=p.name+' · '+lastModel.stages[lastModel.stage]+' '+(value?units(value):'확인 물량 없음');if(p.delayed)b.title+=' · 지연: '+p.delayNote;b.setAttribute('aria-label',b.title);layer.append(b);
    }
  }
  function draw2d(c,items){
    const surface=c.node.querySelector('.prm-surface'),w=surface.clientWidth,h=surface.clientHeight;if(!w||!h)return;
    const points=items.flatMap(p=>p.rings.flat()),xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
    const left=Math.min(...xs),right=Math.max(...xs),bottom=Math.min(...ys),top=Math.max(...ys),scale=Math.min(Math.max(w-40,1)/Math.max(right-left,1),Math.max(h-48,1)/Math.max(top-bottom,1));
    const x=v=>w/2+(v-(left+right)/2)*scale,y=v=>h/2-(v-(bottom+top)/2)*scale;
    surface.innerHTML='<svg viewBox="0 0 '+w+' '+h+'" aria-label="'+c.region+' 2D 단계별 공급량">'+items.map(p=>'<path data-d907-city="'+p.id+'" d="'+[...p.rings,...(p.holes||[]).flat()].map(r=>r.map((v,i)=>(i?'L':'M')+x(v[0]).toFixed(2)+','+y(v[1]).toFixed(2)).join('')+'Z').join(' ')+'" fill-rule="evenodd" fill="'+p.color+'" stroke="'+(p.id===lastModel.city?'#fba843':lastModel.aggregate?'#4d7184':'#708f9f')+'" stroke-width="'+(p.id===lastModel.city?2.4:lastModel.aggregate?1.6:1)+'"><title>'+escape(p.name)+' · '+(p.value?units(p.value):'확인 물량 없음')+'</title></path>').join('')+'</svg>';
    labels(c,items,p=>[x(p.anchor[0]),y(p.anchor[1])]);
  }
  function create3d(T,c){
    const surface=c.node.querySelector('.prm-surface');surface.innerHTML='';
    const renderer=new T.WebGLRenderer({alpha:true,antialias:true,powerPreference:'low-power'});renderer.setPixelRatio(Math.min(devicePixelRatio,1.6));renderer.shadowMap.enabled=true;renderer.shadowMap.type=T.PCFSoftShadowMap;renderer.outputColorSpace=T.SRGBColorSpace;renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1.05;renderer.domElement.setAttribute('role','img');renderer.domElement.setAttribute('aria-label',c.region+' 공식 경계 3D 공급 현황');surface.append(renderer.domElement);
    const scene=new T.Scene(),camera=new T.OrthographicCamera(-120,120,120,-120,.1,900);camera.up.set(0,0,1);camera.position.set(28,-145,185);camera.lookAt(0,0,7);
    const ambient=new T.HemisphereLight(0xe9f7ff,0x6e91a8,1.9);ambient.position.set(0,0,1);scene.add(ambient);
    const light=new T.DirectionalLight(0xffffff,2.2);light.position.set(-80,-70,200);light.castShadow=true;light.shadow.mapSize.set(1024,1024);Object.assign(light.shadow.camera,{left:-140,right:140,top:140,bottom:-140,near:1,far:450});light.shadow.normalBias=.3;light.shadow.bias=-.0002;light.shadow.radius=4;scene.add(light);
    const floor=new T.Mesh(new T.PlaneGeometry(900,900),new T.ShadowMaterial({opacity:.2}));floor.position.z=-1;floor.receiveShadow=true;scene.add(floor);
    for(const p of c.shapes){
      for(const [index,ring] of p.rings.entries()){if(ring.length<4)continue;const shape=new T.Shape(ring.map(v=>new T.Vector2(...v)));for(const hole of p.holes?.[index]||[])if(hole.length>=4&&ringArea(hole)>1e-8)shape.holes.push(new T.Path(hole.map(v=>new T.Vector2(...v))));const geometry=new T.ExtrudeGeometry(shape,{depth:1,steps:1,bevelEnabled:false,curveSegments:1});
        const top=new T.MeshStandardMaterial({color:0xb4ddeb,roughness:.72,metalness:.05});const side=new T.MeshStandardMaterial({color:0x78acbf,roughness:.85});
        const mesh=new T.Mesh(geometry,[top,side]);mesh.castShadow=true;mesh.receiveShadow=true;mesh.userData.id=p.id;scene.add(mesh);c.meshes.push(mesh);
        const edge=new T.LineLoop(new T.BufferGeometry().setFromPoints(ring.map(v=>new T.Vector3(v[0],v[1],1.005))),new T.LineBasicMaterial({color:0x4d7184,depthTest:true,depthWrite:false}));edge.renderOrder=1;mesh.add(edge);
      }
    }
    c.renderer=renderer;c.scene=scene;c.camera=camera;c.THREE=T;c.intentionalLoss=false;
    const ray=new T.Raycaster(),pointer=new T.Vector2(),tooltip=c.node.querySelector('.prm-hover');
    function pick(e){const rect=renderer.domElement.getBoundingClientRect();pointer.set((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1);ray.setFromCamera(pointer,camera);return ray.intersectObjects(c.meshes,false)[0]?.object.userData.id;}
    renderer.domElement.addEventListener('pointermove',e=>{const id=pick(e),p=c.shapes.find(p=>p.id===id),v=lastModel.values[id];renderer.domElement.style.cursor=id?'pointer':'default';tooltip.hidden=!id;if(id)tooltip.textContent=p.name+' · '+lastModel.stages[lastModel.stage]+' '+(v?.value?units(v.value):'확인 물량 없음');});
    renderer.domElement.addEventListener('pointerleave',()=>tooltip.hidden=true);
    renderer.domElement.addEventListener('click',e=>{const id=pick(e);if(id){const button=document.createElement('button');button.dataset.d907City=id;button.hidden=true;c.node.append(button);button.click();button.remove();}});
    renderer.domElement.addEventListener('webglcontextlost',e=>{e.preventDefault();if(c.renderer===renderer&&!c.intentionalLoss&&lastHost?.isConnected){mode='2d';render(lastHost,lastModel);}});
  }
  function draw3d(T,c,items){
    if(!c.renderer)create3d(T,c);
    const byId=Object.fromEntries(items.map(p=>[p.id,p]));
    for(const mesh of c.meshes){const p=byId[mesh.userData.id];mesh.scale.z=p.height;mesh.material[0].color.set(p.color);mesh.material[1].color.copy(mesh.material[0].color).multiplyScalar(.78);mesh.children[0]?.material.color.set(p.id===lastModel.city?'#ffae4e':'#4d7184');}
    const surface=c.node.querySelector('.prm-surface'),w=surface.clientWidth,h=surface.clientHeight;if(!w||!h)return;
    // Fit the visible footprint AND extruded heights in camera space. A fixed
    // frustum leaves unused space and shifts tall regions toward the top.
    c.camera.updateMatrixWorld();
    let left=Infinity,right=-Infinity,bottom=Infinity,top=-Infinity;
    const point=new T.Vector3();
    for(const p of items)for(const ring of p.rings)for(const xy of ring)for(const z of [0,p.height]){
      point.set(xy[0],xy[1],z).applyMatrix4(c.camera.matrixWorldInverse);
      left=Math.min(left,point.x);right=Math.max(right,point.x);bottom=Math.min(bottom,point.y);top=Math.max(top,point.y);
    }
    if(!Number.isFinite(left))return;
    const aspect=w/h,cx=(left+right)/2,cy=(bottom+top)/2;
    const extent=Math.max((top-bottom)/2/Math.max(1-48/h,.1),(right-left)/2/aspect/Math.max(1-40/w,.1),1);
    c.renderer.setSize(w,h);Object.assign(c.camera,{left:cx-extent*aspect,right:cx+extent*aspect,top:cy+extent,bottom:cy-extent});c.camera.updateProjectionMatrix();c.renderer.render(c.scene,c.camera);
    labels(c,items,p=>{const v=new T.Vector3(p.anchor[0],p.anchor[1],p.height+1).project(c.camera);return [(v.x+1)*w/2,(1-v.y)*h/2];});
    c.node.dataset.rendered='3d';
  }
  async function render(host,raw){
    const model=mapModel(raw);
    lastHost=host;lastModel=model;const token=++generation;
    const key=(model.region||'ALL')+'|'+model.shapes.map(p=>p.id).join(',');
    if(!host.querySelector('.prm-cards')||key!==shellKey){shellKey=key;createShell(host,model);}
    const control=document.getElementById('policy-map-controls');
    control.querySelectorAll('.pd-region-tabs button').forEach(b=>b.setAttribute('aria-selected',b.dataset.d907Region===model.region));
    control.querySelectorAll('[data-prm-mode]').forEach(b=>{b.classList.toggle('selected',b.dataset.prmMode===mode);b.setAttribute('aria-selected',b.dataset.prmMode===mode);});
    control.querySelectorAll('[data-d907-stage]').forEach(b=>{b.classList.toggle('selected',b.dataset.d907Stage===model.stage);b.setAttribute('aria-pressed',b.dataset.d907Stage===model.stage);});
    const readout=control.querySelector('.d907-map-readout');readout.innerHTML='<strong>'+escape(model.stages[model.stage])+' 누적 · '+model.year+'년'+(model.year>model.currentYear?' 예정':' 확인')+'</strong><small>면 높이·색 농도는 누적 도달량 · <span class="prm-delay-key">🔴 !</span> 지연 단계 있음 (부족률 2% 이상)</small><button data-d907-clear>지역 선택 해제</button>';
    const range=control.querySelector('[data-d907-year]');range.value=model.year;range.parentElement.querySelector('b').textContent=model.year;
    if(!model.shapes.length){host.querySelector('.prm-surface').innerHTML='<p class="pd-empty">선택 프로그램의 위치 연결 자료가 없습니다.</p>';return;}
    let T;if(mode==='3d'){try{threePromise??=import('./vendor/three/three.module.js');T=await threePromise;}catch(e){mode='2d';readout.insertAdjacentHTML('beforeend','<small>3D 모듈을 불러오지 못해 2D로 표시합니다.</small>');}if(token!==generation)return;}
    for(const c of cards){
      if(c.node.hidden)continue;
      const items=values(c,model),sum=model.regions[c.region],top=items.filter(p=>p.value>0).sort((a,b)=>b.value-a.value).slice(0,3);
      c.node.classList.toggle('selected',model.region===c.region||c.shapes.some(p=>p.id===model.city));c.node.querySelector('.prm-selected-tag').hidden=!c.node.classList.contains('selected');
      c.node.querySelector('.prm-stats').innerHTML='<div><small>연결 사업계획</small><strong>'+units(sum.target)+'</strong></div><div><small>'+escape(model.stages[model.stage])+' 누적 · '+model.year+'</small><strong>'+(sum.value?units(sum.value):'미확보')+'</strong></div><div><small>단계 확인 비율</small><strong>'+(sum.target?(sum.known/sum.target*100).toFixed(1)+'%':'미확보')+'</strong></div>';
      c.node.querySelector('footer').innerHTML='<span>'+escape(model.stages[model.stage])+' 확인 상위</span><b>'+(top.map(p=>escape(p.name)).join(' · ')||'지역별 확인 물량 없음')+'</b>'+(sum.unplaced?'<small>시군구 미연계 '+units(sum.unplaced)+'</small>':'');
      c.node.querySelector('.prm-accessible>div').innerHTML=items.map(p=>'<button data-d907-city="'+p.id+'"><span>'+escape(p.name)+(p.delayed?' · 지연 !':'')+'</span><b>'+(p.value?units(p.value):'확인 없음')+'</b></button>').join('');
      try{if(mode==='3d')draw3d(T,c,items);else{if(c.renderer){c.intentionalLoss=true;c.renderer.dispose();c.renderer.forceContextLoss();c.renderer=null;c.scene?.traverse(o=>{o.geometry?.dispose();for(const m of [o.material].flat())m?.dispose();});c.meshes=[];}draw2d(c,items);c.node.dataset.rendered='2d';}}
      catch(e){console.warn('지역 3D 지도 표시 실패; 2D로 전환합니다.',e);mode='2d';c.node.dataset.rendered='2d';draw2d(c,items);readout.insertAdjacentHTML('beforeend','<small>3D 표시를 지원하지 않아 2D로 전환했습니다.</small>');}
      if(!c.observer){c.observer=new ResizeObserver(()=>{if(!c.node.isConnected)return;if(lastModel.region&&c.region!==lastModel.region)return;const latest=values(c,lastModel);if(mode==='3d'&&c.renderer)draw3d(c.THREE,c,latest);else draw2d(c,latest);});c.observer.observe(c.node.querySelector('.prm-surface'));}
    }
    control.querySelectorAll('[data-prm-mode]').forEach(b=>{b.classList.toggle('selected',b.dataset.prmMode===mode);b.setAttribute('aria-selected',b.dataset.prmMode===mode);});
  }
  function suspend(){++generation;dispose();if(lastHost?.querySelector('.prm-cards'))lastHost.innerHTML='';}
  return {render,suspend};
})();
