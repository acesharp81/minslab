'use strict';
const Roadmap = (() => {
  const stages={PLANNING:'계획',APPROVAL:'인허가',CONSTRUCTION:'착공',SUPPLY:'공급',COMPLETION:'준공',MOVE_IN:'입주'};
  let data=null, selectedYear=null, generation=0;
  function eventCard(event) {
    const title=`${event.origin==='MANUAL'?'관리자 목표':'원천 예정'} · ${event.basis}${event.past_due?' · 예정 경과·실적 확인 필요':''}`;
    return `<span class="annual-event stage-${esc(event.stage.toLowerCase())} ${event.origin==='MANUAL'?'manual-event':''}" title="${esc(title)}"><b>${esc(event.label)}</b><small>${event.month ? esc(event.month.slice(5))+'월 · ' : ''}${event.stage==='MOVE_IN'?'입주 시작 예정 · 호수 집계 제외':event.units==null?'물량 미확보':num(event.units)+'호'}</small>${event.origin==='MANUAL'?'<i>관리자</i>':''}${event.past_due?'<i>이행 확인</i>':''}</span>`;
  }
  function render(value) {
    data=value;
    if (selectedYear && !data.years.some(year=>year.year===selectedYear)) selectedYear=null;
    const condition='all';
    let rows=data.items.filter(row=>condition==='future'?row.has_future_target:condition==='missing'?!row.has_any_target:condition==='past'?row.past_due_count:condition==='manual'?row.manual_count:true);
    if (selectedYear) rows=rows.filter(row=>row.annual.some(year=>year.year===selectedYear && year.events.length));
    $('roadmap-total').textContent=`${num(rows.length)} / ${num(data.total)}개 원천 사업 후보`;
    $('roadmap-year-reset').hidden=!selectedYear;
    const max=Math.max(1,...data.years.map(year=>year.project_count));
    $('roadmap-summary').innerHTML=data.years.map(year=>`<button class="year-summary ${selectedYear===year.year?'selected':''}" data-target-year="${year.year}" aria-pressed="${selectedYear===year.year}"><small>+${year.offset}년</small><strong>${year.year}</strong><progress max="${max}" value="${year.project_count}" aria-label="${year.year} 목표 확보 사업 후보"></progress><b>${year.project_count?num(year.project_count)+'건':'미등록'}</b><span>원천 ${year.source_event_count} · 관리자 ${year.manual_event_count}</span></button>`).join('');
    const years=[data.current_year,...data.years.map(year=>year.year)];
    $('roadmap-list').innerHTML=rows.length ? `<table class="roadmap-table"><colgroup><col class="roadmap-name-col"><col class="roadmap-state-col"><col class="roadmap-units-col">${years.map(()=>'<col>').join('')}</colgroup><thead><tr><th>사업 / 정책 연결</th><th>현재 상태</th><th>전체 계획</th>${years.map((year,index)=>`<th class="${selectedYear===year?'selected-year':''}">${year}<small>${index===0?'당해연도':'+'+index+'년'}</small></th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr data-roadmap-project="${esc(row.id)}"><td><button class="project-name" data-project="${esc(row.id)}">${esc(row.name)}</button><small class="row-sub">${esc(row.region)} · ${esc(sourceNames.get(row.source_id)||row.source_id)}</small>${badge(row.mapping.status)} <button class="target-open" data-target-project="${esc(row.id)}">${state.admin?'목표 관리':'연도 목표'} ↗</button></td><td><span class="roadmap-current-stage">${esc(row.stage_label)}</span><small class="row-sub">${row.progress_pct==null?'공정률 미확보':num(row.progress_pct)+'%'} · ${esc(baseText(row))}</small>${row.past_due_count?'<small class="roadmap-overdue">예정 경과 · 확인 필요</small>':''}</td><td>${num(row.planned_units)}${row.planned_units==null?'':'호'}</td>${row.annual.map(year=>`<td class="annual-cell ${selectedYear===year.year?'selected-year':''}">${year.events.length?year.events.map(eventCard).join(''):'<span class="annual-unset">미등록</span>'}</td>`).join('')}</tr>`).join('')}</tbody></table>` : empty('선택한 조건의 사업 목표가 없습니다. 표시 조건과 연도 선택을 확인하세요.');
    $('roadmap-note').textContent=`향후 목표 확보 ${num(data.future_target_count)}건 · 일정 미확보 ${num(data.no_schedule_count)}건 · 관리자 목표 등록 ${num(data.manual_project_count)}건. ${data.notice}`;
    const params=query();params.set('horizon',10);params.set('target_filter',condition);
    if(selectedYear)params.set('target_year',selectedYear);
    $('roadmap-export').href=API+'/roadmap/export.csv?'+params;
  }
  async function open(projectId) {
    const version=++generation, dialog=$('target-dialog');
    $('target-content').innerHTML=empty('연도별 목표를 불러오는 중입니다.');
    if (!dialog.open) dialog.showModal();
    try {
      const plan=await request('/projects/'+encodeURIComponent(projectId)+'/targets?as_of_date='+encodeURIComponent($('as-of').value));
      if(version!==generation) return;
      const years=Array.from({length:11},(_,index)=>plan.current_year+index);
      const editable=state.admin && $('as-of').value===$('as-of').max;
      const goals=new Map(plan.targets.map(target=>[target.year,target]));
      const options=selected=>'<option value="">미등록</option>'+Object.entries(stages).filter(([key])=>key!=='MOVE_IN').map(([key,label])=>`<option value="${key}" ${key===selected?'selected':''}>${label} 목표</option>`).join('');
      $('target-content').innerHTML=`<h2 id="target-title" class="detail-title">${esc(plan.project_name)}</h2><p class="detail-sub">당해연도 + 향후 1~10년 · 공식 일정과 관리자 목표</p><p class="target-help">${editable?'사업별 목표 단계·물량·근거를 입력하고 저장하세요. 물량 공란은 미확보로 유지합니다. 단계에서 미등록을 선택하면 해당 연도의 관리자 목표를 해제합니다.':'관리자 로그인 후 오늘 기준일에서 추진목표를 등록할 수 있습니다.'} 원천 예정은 별도로 보존합니다.</p><form id="target-form"><div class="target-form-scroll"><table class="target-form-table"><thead><tr><th>연도</th><th>원천 예정</th><th>관리자 목표</th><th>목표 호수</th><th>근거·메모</th><th>근거 URL (선택)</th></tr></thead><tbody>${years.map((year,index)=>{const goal=goals.get(year)||{};const source=plan.source_annual.find(annual=>annual.year===year)?.events||[];return `<tr data-goal-year="${year}"><td>${year}<small class="row-sub">${index?'+'+index+'년':'당해연도'}</small></td><td>${source.length?source.map(eventCard).join(''):'<span class="annual-unset">미확보</span>'}</td><td><select class="goal-stage" aria-label="${year} 목표 단계" ${editable?'':'disabled'}>${options(goal.stage)}</select></td><td><input class="goal-units" type="number" min="0" max="10000000" step="1" value="${esc(goal.units??'')}" aria-label="${year} 목표 호수" ${editable?'':'disabled'}></td><td><input class="goal-basis" maxlength="500" value="${esc(goal.basis||'')}" aria-label="${year} 근거 메모" ${editable?'':'disabled'}></td><td><input class="goal-url" type="url" maxlength="500" placeholder="https://" value="${esc(goal.evidence_url||'')}" aria-label="${year} 근거 URL" ${editable?'':'disabled'}></td></tr>`;}).join('')}</tbody></table></div>${editable?'<button class="button primary" type="submit">연도별 목표 저장</button>':''}<p id="target-save-status" role="status"></p></form><div class="detail-section"><h3>관리자 목표 변경 이력</h3>${plan.history.length?plan.history.map(history=>`<details><summary>revision ${history.revision_no} · ${timeText(history.recorded_at)}</summary>${history.values.targets.map(goal=>`<p>${goal.year}년 ${esc(stages[goal.stage])} 목표 · ${num(goal.units)}${goal.units==null?'':'호'} · ${esc(goal.basis)}</p>`).join('')||'<p>목표 해제</p>'}<div class="hash">${esc(history.payload_hash)}</div></details>`).join(''):'<p>아직 등록한 관리자 목표가 없습니다.</p>'}</div>`;
      if(editable) $('target-form').addEventListener('submit',async event=>{
        event.preventDefault();
        const button=event.currentTarget.querySelector('button[type=submit]');button.disabled=true;
        try {
          const targets=plan.targets.filter(target=>!years.includes(target.year));
          for(const row of document.querySelectorAll('#target-form [data-goal-year]')) {
            const stage=row.querySelector('.goal-stage').value;
            if(!stage) continue;
            const units=row.querySelector('.goal-units').value;
            const basis=row.querySelector('.goal-basis').value.trim();
            if(!basis) throw new Error(row.dataset.goalYear+'년 근거·메모를 입력하세요.');
            targets.push({year:Number(row.dataset.goalYear),stage,units:units===''?null:Number(units),basis,evidence_url:row.querySelector('.goal-url').value.trim()||null});
          }
          await request('/admin/targets/'+encodeURIComponent(projectId),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision_no:plan.revision_no,targets})});
          await load();await open(projectId);
          $('target-save-status').textContent='연도별 목표를 저장했습니다.';
        } catch(error) {$('target-save-status').textContent=error.message+' 동시 수정이면 창을 다시 열어 확인하세요.';} finally {button.disabled=false;}
      });
    } catch(error) {if(version===generation) $('target-content').innerHTML=empty(error.message);}
  }
  function start() {
    $('roadmap-year-reset').addEventListener('click',()=>{selectedYear=null;if(data)render(data);});
    document.addEventListener('click',event=>{
      const year=event.target.closest('[data-target-year]');
      if(year) {selectedYear=selectedYear===Number(year.dataset.targetYear)?null:Number(year.dataset.targetYear);if(data)render(data);}
      const project=event.target.closest('[data-target-project]');if(project)open(project.dataset.targetProject);
    });
    $('close-target').addEventListener('click',()=>{$('target-dialog').close();++generation;});
  }
  return {render,open,start,selectYear:year=>{selectedYear=year;if(data)render(data);},reset:()=>{selectedYear=null;}};
})();
