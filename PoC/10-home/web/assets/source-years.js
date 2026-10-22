'use strict';
const SourceYears=(()=>{
 let loaded=false,loading=false,generation=0;
 const statuses={ACQUIRED:'확보',NO_SOURCE_RECORD:'원본 행 없음',SOURCE_NOT_PUBLISHED:'미공표',NOT_ACQUIRED:'미입수',NOT_STARTED:'미시작',FAILED:'실패'};
 function render(data){
  const root=document.getElementById('source-years');
  root.innerHTML='<p class="source-volume-note">'+esc(data.notice)+' · '+esc(data.as_of_date)+' 기준</p><p class="source-years-legend">'+Object.entries(statuses).map(([key,label])=>'<span class="data-gap-legend '+key+'">'+label+'</span>').join(' ')+'</p><table class="data-gap-matrix source-years-matrix" style="--source-years-min-width:'+(240+data.years.length*76)+'px"><colgroup><col class="source-years-label">'+data.years.map(()=>'<col>').join('')+'</colgroup><thead><tr><th scope="col">자료 · 지역</th>'+data.years.map(y=>'<th scope="col">'+y+(y===data.years.at(-1)?'<small>진행 연도</small>':'<small aria-hidden="true">&nbsp;</small>')+'</th>').join('')+'</tr></thead><tbody>'+data.rows.map(r=>'<tr><th scope="row">'+esc(r.label)+'<small>'+esc(r.region)+(r.source_url?' · <a href="'+esc(safeUrl(r.source_url))+'" target="_blank" rel="noopener noreferrer">원천 ↗</a>':'')+'</small></th>'+r.cells.map(c=>{const label=statuses[c.status]||c.status,description=r.label+' · '+r.region+' · '+c.year+'년 '+label+(c.status==='ACQUIRED'?' · 저장 '+num(c.count)+'건':'');return '<td><span class="data-gap-cell '+esc(c.status)+'" title="'+esc(description)+'" aria-label="'+esc(description)+'">'+(c.status==='ACQUIRED'?'●':esc(label))+'</span></td>';}).join('')+'</tr>').join('')+'</tbody></table>';
 }
 async function load(){
  if(loaded||loading||state.view!=='sources'||!document.getElementById('source-volume-details').open)return;
  const token=++generation,root=document.getElementById('source-years');loading=true;root.innerHTML='<p role="status">자료연도별 수집현황을 불러오는 중…</p>';
  try{const data=await request('/sources/year-coverage');if(token!==generation)return;render(data);loaded=true;}
  catch(error){if(token!==generation)return;root.innerHTML='<p>연도별 수집현황 조회 실패: '+esc(error.message)+'</p><button type="button" class="button secondary" data-source-years-retry>다시 조회</button>';root.querySelector('button').onclick=()=>load();}
  finally{if(token===generation)loading=false;}
 }
 function invalidate(){loaded=false;loading=false;generation++;load();}
 function start(){document.getElementById('source-volume-details').addEventListener('toggle',load);}
 return {start,invalidate,render};
})();
