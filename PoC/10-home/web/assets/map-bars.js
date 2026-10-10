'use strict';
const SupplyBars=(()=>{
  const amount=value=>value==null?'미확보':num(value)+'호';
  function chart(row,compact=false,concise=false){
    const p=row.progress,capacity=row.target_units,h=compact?96:136,base=h+22;
    const y=value=>base-Math.min(1,Math.max(0,value/(capacity||1)))*h;
    const known=capacity!=null&&capacity>0, observed=p.observed_units;
    const fill=known&&observed!=null?base-y(observed):0;
    const goal=p.cumulative_goal_units;
    const projected=row.projection.future.slice(0,3),colors=['#21a9ca','#8265d5','#ce649a'];
    let previous=observed;
    const stack=projected.map((future,index)=>{
      const value=future.cumulative_units;if(!known||value==null||previous==null)return '';
      const top=y(value),bottom=y(previous),height=Math.max(0,bottom-top);previous=value;
      return height?`<rect class="bar-projected-segment" data-offset="${future.offset}" x="23" y="${top}" width="20" height="${height}" fill="${colors[index]}"/><path d="M43 ${top}l8 -6v${height}l-8 6z" fill="${colors[index]}" opacity=".6"/>`:'';
    }).join('');
    const labelPositions=[];
    const ticks=projected.map((future,index)=>{
      if(!known||future.cumulative_units==null)return '';
      const at=y(future.cumulative_units),color=colors[index];
      let label=at;while(labelPositions.some(other=>Math.abs(other-label)<12))label+=12;labelPositions.push(label);
      return `<path d="M47 ${at}h5l5 ${label-at}h3" fill="none" stroke="${color}" stroke-width="1.5"/><text x="62" y="${label+4}" fill="${color}" font-size="9">+${future.offset}년</text>`;
    }).join('');
    const svg=`<svg viewBox="0 0 112 ${base+42}" role="img" aria-label="${esc(row.name)}${capacity!=null?' 계획 '+amount(capacity):''}${observed!=null?', 확인 '+amount(observed):''}${goal!=null?', 누적 목표 '+amount(goal):''}">
      <path d="M23 22l8 -6h20l-8 6z" fill="#e1ebf6" stroke="#adbfda"/>
      <path d="M43 22l8 -6v${h}l-8 6z" fill="#d9e4f2" fill-opacity=".65" stroke="#adbfda"/>
      <rect x="23" y="22" width="20" height="${h}" fill="#eaf0f8" fill-opacity=".7" stroke="#adbfda"/>
      ${fill?`<rect x="23" y="${base-fill}" width="20" height="${fill}" fill="#1665ee"/><path d="M43 ${base-fill}l8 -6v${fill}l-8 6z" fill="#1346b2"/><path d="M23 ${base-fill}l8 -6h20l-8 6z" fill="#4a98ff"/>`:''}
      ${stack}
      ${known&&goal!=null?`<path d="M19 ${y(goal)}h28l8 -6" fill="none" stroke="#d79516" stroke-width="2.5"/>`:''}
      ${ticks}
      <path d="M17 ${base+5}h63" stroke="#cbd6e7"/>
      </svg>`;
    const status=p.late_count?`<span class="bar-status late">공고월 지연 ${num(p.late_count)}건 · 최대 ${p.max_lag_months}개월${concise?'':' · 연결 검토'}</span>`:'';
    const overflow=known&&[goal,...projected.map(f=>f.cumulative_units)].some(value=>value!=null&&value>capacity);
    const futureValues=projected.map(f=>{
      const manual=row.future?.[f.offset-1]?.manual_units;
      if(f.cumulative_units==null&&manual==null)return '';
      return `<span class="bar-future f${f.offset}">+${f.offset}년 예상 누적 ${f.cumulative_pct!=null?`<b>${num(f.cumulative_pct)}%</b>`:''}${f.cumulative_units!=null?`<small>${amount(f.cumulative_units)}${f.increment_units!=null?' · 추가 '+amount(f.increment_units):''}</small>`:''}${manual!=null?`<small class="bar-manual">관리자 ${amount(manual)} · 별도</small>`:''}</span>`;
    }).join('');
    return `<div class="supply-bar-chart ${compact?'compact':''}">${known?`<div class="bar-column">${svg}<strong>${amount(capacity)}</strong><small>${concise?'전체 계획':'전체 계획 · 검토'}</small></div>`:''}<div class="bar-values">${p.observed_pct!=null?`<b class="bar-ratio">${num(p.observed_pct)}%</b><small>${p.measure==='SUPPLY'?(concise?'확인 공고 비율':'확인 공고 비율(하한)'):'확인 실적 비율'}</small>`:''}${observed!=null?`<span>${p.measure==='SUPPLY'?'비율 대상 공고':'실적 확인'} <b>${amount(observed)}</b></span>`:''}${goal!=null?`<span class="bar-goal">현재 누적 목표 <b>${amount(goal)}</b></span>`:''}${futureValues}${status}${overflow&&!concise?'<small>예정량이 계획량 초과 · 원천 범위 확인</small>':''}</div></div>`;
  }

  function scoped(row){if(!row)return null;const selection=MapSupply.selection();const quantity=selection.id?row.group_quantities?.[selection.kind]?.[selection.id]:row;return quantity?{...row,...quantity}:null;}

  return {chart,scoped};
})();
