'use strict';
const HistoryPanel=(()=>{
  let data;
  function render(value){
    data=value;
    const selected=$('history-year').value;
    $('history-year').innerHTML='<option value="">자료연도 전체</option>'+data.years.map(row=>`<option value="${row.year}">${row.year}년</option>`).join('');
    $('history-year').value=selected;
    const exportParams=query();if(selected)exportParams.set('history_year',selected);$('history-export').href=API+'/history/export.csv?'+exportParams;
    $('history-period').textContent=`${data.start_year}년부터 ${data.end_year}년까지 · 원천 자료연도 기준`;
    $('history-origins').innerHTML=data.origins.map(origin=>`<article class="history-origin"><span>정책·사업의 기원</span><h3>${esc(origin.name)}</h3><strong>${origin.origin_date.slice(0,4)}년</strong><p>${esc(origin.date_basis)} · ${esc(origin.origin_date)}</p><a href="${esc(safeUrl(origin.evidence_url))}" target="_blank" rel="noopener noreferrer">최초 공식 자료 ↗</a></article>`).join('');
    $('history-years').innerHTML=`<table><thead><tr><th>자료연도</th><th>정책 발표·후속조치</th><th>공사 보고서 / 행</th><th>청약공고</th><th>인허가 자료</th></tr></thead><tbody>${data.years.map(row=>`<tr class="${String(row.year)===selected?'history-selected':''}"><td><button class="project-name" data-history-year="${row.year}">${row.year}년</button></td><td>${row.policy_event_count?num(row.policy_event_count)+'건':'자료 미확보'}</td><td>${row.report_count?num(row.report_count)+'개 / '+num(row.project_report_rows)+'행':'자료 미확보'}</td><td>${row.notice_count?num(row.notice_count)+'건':'자료 미확보'}</td><td>${row.permit_count?num(row.permit_count)+'건':'자료 미확보'}</td></tr>`).join('')}</tbody></table>`;
    $('history-events').innerHTML=data.events.length?data.events.map(row=>`<div class="history-event"><time>${esc(row.event_date)}</time><div><h3><a href="${esc(safeUrl(row.evidence_url))}" target="_blank" rel="noopener noreferrer">${esc(row.name)} ↗</a></h3><p>${esc(row.basis)}</p><small>${esc(row.date_basis)} · 저장 ${timeText(row.recorded_at)}</small></div></div>`).join(''):empty('이 연도에 확보한 정책 발표 자료가 없습니다.');
    $('history-reports').innerHTML=data.reports.length?`<table><thead><tr><th>원천 기준일</th><th>사업 / 지구</th><th>당시 상태</th><th>당시 공정률</th><th>원천 계획호수</th><th>저장일 · 근거</th></tr></thead><tbody>${data.reports.map(row=>`<tr><td>${esc(row.report_period||row.report_date)}<small class="row-sub">${esc(row.progress_date_basis||"공식 보고서 기준일")}</small></td><td>${esc(row.name)}<small class="row-sub">${esc(row.region)} · ${esc(row.district)} · ${esc(row.block||"")}</small>${row.current_project_id?`<button class="text-button" data-project="${esc(row.current_project_id)}">현재 사업 상세 ↗</button>`:''}</td><td>${esc(row.stage_label)}</td><td>${row.progress_pct==null?'미확보':num(row.progress_pct)+'%'}</td><td>${row.planned_units==null?'미확보':num(row.planned_units)+'호'}</td><td>${timeText(row.recorded_at)}<small class="row-sub"><a href="${esc(safeUrl(row.evidence_url))}" target="_blank" rel="noopener noreferrer">공정률 원본 ↗</a></small></td></tr>`).join('')}</tbody></table>`:empty('선택한 자료연도의 공사 보고서를 아직 확보하지 못했습니다. 실적이 0이라는 의미는 아닙니다.');
    $('history-page-info').textContent=`${data.page} / ${Math.max(1,Math.ceil(data.report_total/data.page_size))} · 보고서 행 ${num(data.report_total)}건`;
    $('history-prev').disabled=data.page===1;$('history-next').disabled=data.page*data.page_size>=data.report_total;
    $('history-note').textContent=data.notice+' 인허가는 허가일 우선, 미제공 시 생성일로 자료연도를 분류합니다. '+(data.unclassified_or_earlier_permits?num(data.unclassified_or_earlier_permits)+'건은 기원 이전 또는 날짜 미확보로 연도표에서 제외합니다. ':'')+'API 표본은 정책에 연결하기 전의 별도 자료입니다.';
  }
  function select(year){$('history-year').value=year;state.historyPage=1;load();}
  function start(){
    $('history-year').addEventListener('change',event=>select(event.target.value));
    document.addEventListener('click',event=>{const button=event.target.closest('[data-history-year]');if(button)select(button.dataset.historyYear);});
    $('history-prev').addEventListener('click',()=>{if(data?.page>1){state.historyPage--;load();}});
    $('history-next').addEventListener('click',()=>{if(data?.page*data.page_size<data.report_total){state.historyPage++;load();}});
  }
  return {render,start};
})();
