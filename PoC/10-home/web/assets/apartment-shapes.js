'use strict';
// A cartographic extrusion of official residential LAND parcels. Display height
// is a screen-space visual effect: it never represents building height/floors.
const ApartmentShapes=(()=>{
  const ns='http://www.w3.org/2000/svg';
  function polygons(geometry){
    if(!geometry)return [];
    if(geometry.type==='Feature')return polygons(geometry.geometry);
    if(geometry.type==='Polygon')return [geometry.coordinates];
    if(geometry.type==='MultiPolygon')return geometry.coordinates;
    if(geometry.type==='GeometryCollection')return geometry.geometries.flatMap(polygons);
    return [];
  }
  function path(rings,dx=0,dy=0){return rings.map(ring=>'M'+ring.map(p=>`${(p.x+dx).toFixed(1)},${(p.y+dy).toFixed(1)}`).join('L')+'Z').join('');}
  function draw(map,layer,districts,selectedName,choose){
    if(map.getZoom()<16)return;
    const size=map.getSize(),height=Math.min(48,24+(map.getZoom()-13)*6),dx=-height*.32,dy=-height;
    const parcels=[];
    for(const district of districts)for(const coordinates of polygons(district.geometry)){
      const rings=coordinates.map(ring=>{
        const points=ring.filter(c=>Number.isFinite(c[0])&&Number.isFinite(c[1])).map(c=>map.latLngToContainerPoint([c[1],c[0]]));
        // Preserve the official outline; remove only redundant subpixel points.
        return L.LineUtil.simplify(points,1.1);
      }).filter(r=>r.length>=3);
      if(!rings.length)continue;
      const points=rings[0],xs=points.map(p=>p.x),ys=points.map(p=>p.y);
      const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
      if(maxX<0||minX>size.x||maxY<0||minY+dy>size.y||maxX-minX<3||maxY-minY<3)continue;
      parcels.push({district,rings,minX,maxX,minY,maxY});
    }
    // Nearest parcels first for the cap, then rear-to-front for occlusion.
    parcels.sort((a,b)=>((a.minX+a.maxX-size.x)**2+(a.minY+a.maxY-size.y)**2)-((b.minX+b.maxX-size.x)**2+(b.minY+b.maxY-size.y)**2));
    const visible=parcels.slice(0,160).sort((a,b)=>a.maxY-b.maxY);
    if(!visible.length)return;
    const svg=document.createElementNS(ns,'svg');
    svg.setAttribute('viewBox',`0 0 ${size.x} ${size.y}`);
    svg.setAttribute('class','apartment-shape-layer');svg.setAttribute('data-geometry-basis','LAND_PARCEL');
    svg.innerHTML=`<defs><pattern id="home-facade-windows" width="9" height="8" patternUnits="userSpaceOnUse"><rect x="2" y="2" width="3" height="4" rx=".4" fill="#294961" opacity=".72"/><path d="M2 4h3" stroke="#aec7d6" stroke-width=".5"/></pattern><linearGradient id="home-parcel-roof" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#fbfcfd"/><stop offset="1" stop-color="#b9ccda"/></linearGradient></defs>`;
    for(const {district,rings} of visible){
      const selected=district.name===selectedName,group=document.createElementNS(ns,'g');
      group.setAttribute('class','apartment-parcel');group.setAttribute('data-district',district.name);
      let walls='';
      for(const ring of rings){
        const signedArea=ring.reduce((sum,a,i)=>{const b=ring[(i+1)%ring.length];return sum+a.x*b.y-b.x*a.y;},0);
        for(let i=0;i<ring.length;i++){
        const a=ring[i],b=ring[(i+1)%ring.length];
        const d=`M${a.x},${a.y}L${b.x},${b.y}L${b.x+dx},${b.y+dy}L${a.x+dx},${a.y+dy}Z`;
        // Only camera-facing edges. Holes retain their void in the roof.
        if(((b.x-a.x)*dy-(b.y-a.y)*dx)*signedArea<=0)continue;
        const shade=b.x-a.x>0?'#bacbd7':'#829baa';
        walls+=`<path class="apartment-wall" d="${d}" fill="${shade}" stroke="#738da0" stroke-width=".65"/><path d="${d}" fill="url(#home-facade-windows)"/>`;
      }
      }
      group.innerHTML=`<path class="apartment-shadow" d="${path(rings,9,8)}" fill="#263e52" fill-opacity=".24" fill-rule="evenodd"/><path d="${path(rings)}" fill="#99adbd" fill-rule="evenodd"/>${walls}<path class="apartment-roof" d="${path(rings,dx,dy)}" fill="url(#home-parcel-roof)" fill-rule="evenodd" stroke="${selected?'#1684ed':'#698ea9'}" stroke-width="${selected?2:1.1}" tabindex="0" role="button" aria-label="${esc(district.name)} 공동주택 용지도형 · 입체 표현"/><path d="${path(rings,dx,dy)}" fill="none" stroke="#fff" stroke-opacity=".6" stroke-width=".5"/>`;
      const roof=group.querySelector('.apartment-roof');
      roof.addEventListener('click',event=>{L.DomEvent.stopPropagation(event);choose(district);});
      roof.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();choose(district);}});
      const title=document.createElementNS(ns,'title');title.textContent=district.name+' · 용지도형 기반 입체 표현';roof.append(title);
      svg.append(group);
    }
    L.svgOverlay(svg,map.getBounds(),{className:'apartment-extrusion-overlay',interactive:false}).addTo(layer);
  }
  return {draw,polygons};
})();
