'use strict';
const AnnualSupply=(()=>{
  let data=null,pending=null;
  const colors={'서울특별시':'#245db8','경기도':'#ee834d','인천광역시':'#229b86'};
  const names={'서울특별시':'서울','경기도':'경기','인천광역시':'인천'};
  const methods={'분양승인':'공동주택 분양승인 순계','인허가':'주택건설 인허가','착공':'주택건설 착공','준공':'주택건설 준공·사용검사','멸실':'기존 주택 멸실 · 재고 감소'};
  const value=n=>Number.isFinite(n)?num(n)+'호':'미확보';
  const fmtChange=cell=>cell.change_yoy_pct==null?'':`<small class="annual-change ${cell.change_yoy_units>=0?'up':'down'}">전년 ${cell.change_yoy_units>=0?'+':''}${num(cell.change_yoy_units)}호 (${cell.change_yoy_pct>=0?'+':''}${cell.change_yoy_pct}%)</small>`;
  const note=cell=>cell.availability_status==='SOURCE_NOT_PUBLISHED'?'확인한 공식 원천에 아직 미공표':cell.units==null?'미입수 · 공표 여부 확인':cell.complete?(cell.expected_periods===12?'12개월 확보':'연간 자료'):`${cell.through_period?.slice(4)||'?'}월까지 · ${cell.periods}/${cell.expected_periods}개 기간`;
  function render(){
    if(!data)return;
    const region=$('annual-region').value,metric=$('annual-metric').value;
    const regions=region==='all'?['서울특별시','경기도','인천광역시']:[region],rows=data.rows.filter(r=>regions.includes(r.region));
    const fullYears=data.rows.filter(r=>['분양승인','인허가','착공','준공'].every(m=>r.metrics[m].complete)).map(r=>r.year);
    const latestFull=fullYears.length?Math.max(...fullYears):null;
    $('annual-status').textContent=`2018~${data.last_year||'미확보'}년 공식 관측 · ${latestFull||'미확보'}년까지 4개 공급단계 자료 확보 · 멸실은 별도 공표연도 확인`;
    $('annual-export').href='/poc/home/api/annual-supply/export.csv'+(region==='all'?'':'?region='+encodeURIComponent(region));
    $('annual-summary').innerHTML=regions.map(place=>{
      const row=data.rows.find(r=>r.region===place&&r.year===latestFull);
      const recent=data.rows.filter(r=>r.region===place).at(-1);
      return `<article class="annual-summary-card"><span class="annual-region-dot ${place==='서울특별시'?'seoul':'gyeonggi'}"></span><div><small>${names[place]||place} · ${latestFull||'미확보'}년</small><strong>준공 ${value(row?.metrics['준공'].units)}</strong><span>분양승인 ${value(row?.metrics['분양승인'].units)} · 착공 ${value(row?.metrics['착공'].units)}</span><small>${recent&&recent.year>latestFull?`${recent.year}년 최신: 준공 ${value(recent.metrics['준공'].units)} (${note(recent.metrics['준공'])})`:''}</small></div></article>`;
    }).join('');
    const years=[...new Set(rows.map(r=>r.year))].sort((a,b)=>a-b),max=Math.max(1,...rows.map(r=>r.metrics[metric].units||0));
    const yearBars=years.map(year=>{
      const rects=regions.map((place,index)=>{
        const cell=data.rows.find(r=>r.year===year&&r.region===place)?.metrics[metric];
        if(cell?.units==null)return '';
        const height=Math.max(2,220*cell.units/max),x=regions.length===1?19:2+index*19;
        return `<rect class="annual-svg-bar ${cell.complete?'':'partial'}" x="${x}" y="${244-height}" width="16" height="${height}" rx="3" fill="${colors[place]||"#245db8"}" opacity="${cell.complete?1:.42}"><title>${names[place]||place} ${year}년 ${metric} ${value(cell.units)} · ${note(cell)}</title></rect>`;
      }).join('');
      return `<div class="annual-year"><div class="annual-year-bars"><svg width="58" height="244" viewBox="0 0 58 244" role="img" aria-label="${year}년 ${metric}">${rects}</svg></div><strong>${year}</strong></div>`;
    }).join('');
    $('annual-chart').innerHTML=`<div class="annual-chart-title"><div><h3>${methods[metric]} · 연도별 물량</h3><p>선택한 지역을 동일한 세로 축에서 비교합니다. 옅은 막대는 미완결 연도입니다.</p></div><div class="annual-chart-legend">${regions.map(r=>`<span><i style="background:${colors[r]||'#245db8'}"></i>${names[r]||r}</span>`).join('')}</div></div><div class="annual-bars" role="group" aria-label="${metric} 연도별 서울·경기 비교">${yearBars}</div>`;
    $('annual-table').innerHTML=`<table><thead><tr><th>연도·지역</th>${data.metrics.map(m=>`<th>${m}</th>`).join('')}<th>준공−멸실 참고</th></tr></thead><tbody>${rows.map(row=>`<tr><th>${row.year} <small>${names[row.region]||row.region}</small></th>${data.metrics.map(m=>{const cell=row.metrics[m];return `<td><strong>${value(cell.units)}</strong><small>${note(cell)}</small>${fmtChange(cell)}</td>`}).join('')}<td><strong>${row.net_change_reference==null?'미산출':(row.net_change_reference>=0?'+':'')+num(row.net_change_reference)+'호'}</strong><small>공식 재고 순증 아님</small></td></tr>`).join('')}</tbody></table>`;
    $('annual-basis').innerHTML=`<p>분양승인은 공동주택의 분양·임대·조합 승인 순계입니다. 인허가·착공·준공은 주택건설 단계별 시도 전체 실적이며 민간 물량을 포함합니다. 각 지표는 단계와 의미가 달라 서로 더하지 않습니다. 멸실은 기존 재고에서 사라진 호수이며 시도별 공개된 연도별 원본을 수집했습니다. 준공도 실제 입주 가구 수와 같지 않습니다.</p><p>한 해에 12개월이 모두 확보된 월별 지표에만 전년 대비 증감을 계산합니다. ${data.last_year}년은 공개된 월까지만 표시하며 전년 전체와 비교하지 않습니다. 준공−멸실은 통계 보정 전 산술 대조로 공식 재고 증감이나 입주 가능 주택 수가 아닙니다. 멸실 공개본은 시도 단위여서 시군구·블록으로 배분하지 않습니다.</p><div>${data.metrics.map(m=>`<a href="${data.sources[m]}" target="_blank" rel="noopener">${m} 원천 ↗</a>`).join('')}</div>`;
  }
  async function visible(){
    if(data){render();return;}
    if(pending)return pending;
    $('annual-status').textContent='2018년부터 공식 공급 통계를 조회하고 있습니다…';
    pending=fetch('/poc/home/api/annual-supply').then(async response=>{if(!response.ok)throw Error('연도별 공급 통계 조회 실패');return response.json()})
      .then(result=>{data=result;const select=$("annual-region"),value=select.value;select.innerHTML='<option value="all">수도권 비교</option>'+data.regions.map(r=>'<option value="'+esc(r)+'">'+esc(r)+'</option>').join('');select.value=value;render();}).catch(error=>{$('annual-status').textContent=error.message;}).finally(()=>{pending=null;});
    return pending;
  }
  function start(){for(const id of ['annual-region','annual-metric'])$(id).addEventListener('change',render);}
  return {visible,start};
})();
