'use strict';
const MapStageRing=(()=>{
  const stages=['POLICY','BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN','UNKNOWN'];
  const labels={ALL:'전체 단계',POLICY:'정책',BUSINESS:'사업화',APPROVAL:'인허가',CONSTRUCTION:'건설',SUPPLY:'공급',MOVE_IN:'입주',UNKNOWN:'단계 미확인'};
  const colors={POLICY:'#74839b',BUSINESS:'#ad7100',APPROVAL:'#007bb5',CONSTRUCTION:'#df6800',SUPPLY:'#00886b',MOVE_IN:'#773faf',UNKNOWN:'#d7dfe9'};
  const selected=()=>document.getElementById('map-measure')?.value||'ALL';
  function metric(row){
    const d=row.stage_distribution||{},stage=selected(),total=d.total_units;
    const units=stage==='ALL'?d.advanced_units:d.cumulative?.[stage];
    const unknown=d.parts?.UNKNOWN||0;
    const pct=total>0&&units!=null?100*units/total:null;
    return {d,stage,total,units,unknown,pct,label:labels[stage],text:pct==null?'물량 미확인':units===0&&unknown===total?'단계 미확인':Math.round(pct)+'%'};
  }
  function description(row){
    const m=metric(row),p=m.d.parts||{};
    return `${row.name} · ${m.label} 도달 확인 ${m.text} · 계획 ${m.total==null?'미확보':num(m.total)+'호'}\n`+
      stages.map(s=>`${labels[s]} ${num(p[s]||0)}호`).join(' · ')+
      `\n물량 미확인 사업 ${num(m.d.missing_quantity_projects||0)}건 별도`+
      '\n선택 단계 이후의 물량 포함 · 전체는 사업화~입주 합계 · 입주는 실제 입주 시작이 확인된 사업의 계획물량';
  }
  function svg(row,size=72){
    const m=metric(row),c=size/2,r=c-6;
    let offset=0;
    const slices=m.stage==='ALL'?stages.map(s=>({stage:s,units:m.d.parts?.[s]||0})):
      [{stage:m.stage,units:m.units||0}];
    const segments=slices.filter(s=>s.units>0&&m.total>0).map(s=>{
      const length=s.units/m.total*100;
      const result=`<circle data-stage="${s.stage}" data-units="${s.units}" cx="${c}" cy="${c}" r="${r}" fill="none" stroke="${colors[s.stage]}" stroke-width="9" pathLength="100" stroke-dasharray="${length} ${100-length}" stroke-dashoffset="${-offset}" transform="rotate(-90 ${c} ${c})"/>`;
      offset+=length;return result;
    }).join('');
    return `<svg class="map-stage-ring" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="${esc(description(row))}" data-stage="${m.stage}" data-total="${m.total??''}" data-reached="${m.units??''}"><circle cx="${c}" cy="${c}" r="${r}" fill="#f6f9fd" stroke="#d7dfe9" stroke-width="9"/>${segments}<text x="${c}" y="${c+4}" text-anchor="middle" fill="#183a60" font-size="${m.text.includes('%')?12:8}" font-weight="700">${esc(m.text)}</text></svg>`;
  }
  function legend(){
    const element=document.getElementById('map-stage-legend');if(!element)return;
    element.innerHTML=stages.map(s=>`<span><i class="map-stage-swatch stage-${s}"></i>${labels[s]}</span>`).join('')+
      `<small>${selected()==='ALL'?'전체 비율 = 사업화·인허가·건설·공급·입주 물량 합계 / 계획 물량':'선택 단계 도달률 = 해당 단계 및 이후 단계 물량 / 계획 물량'} · 중복 제외 · 단계 미확인 별도 · 공정률과 구분</small>`;
  }
  function details(row){
    const m=metric(row);return `<h4>${esc(m.label)} 도달 확인 ${esc(m.text)}</h4><p>계획 ${m.total==null?'미확보':num(m.total)+'호'} 중 ${num(m.units||0)}호 · 이후 단계 포함</p><dl>`+
      stages.map(s=>`<dt><i class="map-stage-swatch stage-${s}"></i> ${labels[s]}</dt><dd>${num(m.d.parts?.[s]||0)}호</dd>`).join('')+
      '</dl><p>한 물량은 가장 뒤에 확인된 단계에 한 번만 배정합니다. 입주는 입주 시작 확인 사업의 계획물량이며 실제 입주 세대수와 구분합니다.</p>';
  }
  return {svg,description,metric,legend,details,selected};
})();
