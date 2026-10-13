'use strict';
/* Source-only supply flow. Month-dated source SUPPLY events are plans; unique
   official main notices are supply actuals. Neither construction nor move-in
   events become supplied units. Curves only connect monthly evidence snapshots. */
const PolicyDeliveryFlow=(()=>{
  const amount=value=>Number.isFinite(Number(value))&&value!=null?Math.max(0,Number(value)):null;
  const format=value=>value==null?'미확보':Math.round(value).toLocaleString('ko-KR')+'호';
  const escape=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const dateMonth=value=>/^\d{4}-\d{2}/.test(value||'')?value.slice(0,7):null;
  const monthKey=(year,month)=>String(year)+'-'+String(month).padStart(2,'0');
  const range=(start,end)=>Array.from({length:end-start+1},(_,index)=>start+index);
  const sum=rows=>rows.reduce((total,row)=>total+row.units,0);
  function model({group,items,asOf,selectedYear,announcedAt}){
    const now=Number(String(asOf||new Date().toISOString()).slice(0,4));
    const asOfMonth=dateMonth(asOf)||monthKey(now,12);
    const selected=Math.max(now-5,Math.min(now+5,Number(selectedYear)||now));
    const announcedMonth=dateMonth(announcedAt);
    const members=new Set(group?.project_ids||[]),scheduleIds=new Set(group?.chart_schedule_ids||[]);
    const source=(items||[]).filter(item=>members.has(item.id));
    const noticeIds=new Set(),notices=[],projects=[];
    for(const item of source){
      const plans=[];
      if(scheduleIds.has(item.id))for(const event of item.schedule_events||[]){
        const month=dateMonth(event.month),units=amount(event.units);
        if(event.stage==='SUPPLY'&&month&&units!=null&&(!announcedMonth||month>=announcedMonth))plans.push({month,units});
      }
      plans.sort((a,b)=>a.month.localeCompare(b.month));
      const projectNotices=[];
      const noticeMonth=dateMonth(item.notice_source_date),noticeUnits=amount(item.current_notice_units);
      if(item.notice_evidence_id&&noticeMonth&&noticeUnits!=null&&(!announcedMonth||noticeMonth>=announcedMonth)){
        const record={id:item.notice_evidence_id,month:noticeMonth,units:noticeUnits};
        projectNotices.push(record);
        if(!noticeIds.has(record.id)){noticeIds.add(record.id);notices.push(record);}
      }
      projects.push({id:item.id,name:item.name,plans,notices:projectNotices});
    }
    const schedules=projects.flatMap(project=>project.plans);
    const target=amount(group?.target_units);
    const years=range(now-5,now+5);
    const monthly=years.flatMap(year=>range(1,12).map(month=>monthKey(year,month)));
    function state(cutoff){
      const past=cutoff<asOfMonth,actualLimit=past?cutoff:asOfMonth;
      const observed=notices.filter(row=>row.month<=actualLimit);
      const actual=sum(observed);
      const cohorts={older:sum(observed.filter(row=>Number(row.month.slice(0,4))<now-1)),
        previous:sum(observed.filter(row=>Number(row.month.slice(0,4))===now-1)),
        current:sum(observed.filter(row=>Number(row.month.slice(0,4))===now))};
      let overdue=0,upcoming=0,duePlanned=0;
      const issues=[];
      for(const project of projects){
        const due=project.plans.filter(row=>past?row.month<=cutoff:row.month<asOfMonth);
        const linked=sum(project.notices.filter(row=>row.month<=actualLimit));
        const dueUnits=sum(due),missing=Math.max(0,dueUnits-linked);
        duePlanned+=dueUnits;overdue+=missing;
        if(missing)issues.push({id:project.id,name:project.name,units:missing,latestDueMonth:due.at(-1)?.month||null});
        if(!past){
          const future=sum(project.plans.filter(row=>row.month>=asOfMonth&&row.month<=cutoff));
          upcoming+=Math.max(0,future-Math.max(0,linked-sum(due)));
        }
      }
      const known=actual+overdue+upcoming;
      return {month:cutoff,year:Number(cutoff.slice(0,4)),actual,cohorts,overdue,duePlanned,upcoming,
        remaining:target==null?null:Math.max(0,target-known),
        total:target==null?known:Math.max(target,known),issues};
    }
    const monthlyPoints=monthly.map(state);
    const points=years.map(year=>state(monthKey(year,12)));
    const current=points[5],chosen=points[selected-now+5];
    const annualPlans=new Map(years.map(year=>[year,sum(schedules.filter(row=>Number(row.month.slice(0,4))===year))]));
    const planYears=new Set(schedules.map(row=>Number(row.month.slice(0,4))));
    const annualNotices=new Map(years.map(year=>[year,sum(notices.filter(row=>Number(row.month.slice(0,4))===year))]));
    const noticeYears=new Set(notices.map(row=>Number(row.month.slice(0,4))));
    const focusStart=Math.max(now-5,Math.min(now+2,selected-1));
    return {now,selected,asOf:asOfMonth,target,points,monthlyPoints,current,chosen,focusStart,
      annualPlans,planYears,annualNotices,noticeYears,hasNotices:notices.length>0,hasSchedules:schedules.length>0,
      issues:[...current.issues].sort((a,b)=>b.units-a.units)};
  }
  function smoothLine(points){
    if(!points.length)return '';
    let path='M'+points[0][0].toFixed(1)+' '+points[0][1].toFixed(1);
    for(let i=1;i<points.length;i++){
      const [x0,y0]=points[i-1],[x1,y1]=points[i],middle=(x0+x1)/2;
      path+=' C'+middle.toFixed(1)+' '+y0.toFixed(1)+' '+middle.toFixed(1)+' '+y1.toFixed(1)+' '+x1.toFixed(1)+' '+y1.toFixed(1);
    }
    return path;
  }
  function area(rows,x,y,low,high){
    const upper=rows.map((row,index)=>[x(index),y(high(row))]);
    const lower=rows.map((row,index)=>[x(index),y(low(row))]).reverse();
    return smoothLine(upper)+' L'+lower[0][0].toFixed(1)+' '+lower[0][1].toFixed(1)+smoothLine(lower).replace(/^M[^C]*/, '')+' Z';
  }
  function render(data){
    const start=data.focusStart,end=start+3;
    const rows=data.monthlyPoints.filter(row=>row.year>=start&&row.year<=end);
    const max=Math.max(1,data.target||0,...rows.map(row=>row.total));
    const x=index=>62+index*1000/Math.max(1,rows.length-1),y=value=>327-230*Math.max(0,value)/max;
    const boundary={older:row=>row.cohorts.older,previous:row=>row.cohorts.older+row.cohorts.previous,
      actual:row=>row.actual,due:row=>row.actual+row.overdue,
      scheduled:row=>row.actual+row.overdue+row.upcoming,total:row=>row.total};
    const zero=()=>0;
    const bands=[
      {key:'older',low:zero,high:boundary.older,fill:'#8865b5'},
      {key:'previous',low:boundary.older,high:boundary.previous,fill:'#df8233'},
      {key:'current',low:boundary.previous,high:boundary.actual,fill:'#29a59a'},
      {key:'overdue',low:boundary.actual,high:boundary.due,fill:'#d94b5d'},
      {key:'upcoming',low:boundary.due,high:boundary.scheduled,fill:'#6e9fce'},
      {key:'remaining',low:boundary.scheduled,high:boundary.total,fill:'url(#pr-flow-unknown)'}];
    const paths=bands.map(band=>'<path data-flow-layer="'+band.key+'" d="'+area(rows,x,y,band.low,band.high)+'" fill="'+band.fill+'"/>').join('');
    const overduePath=area(rows,x,y,boundary.actual,boundary.due);
    const futurePath=area(rows,x,y,boundary.due,boundary.scheduled);
    const remainingPath=area(rows,x,y,boundary.scheduled,boundary.total);
    const asOfIndex=rows.findIndex(row=>row.month===data.asOf),nowX=asOfIndex>=0?x(asOfIndex):null;
    const selectedStart=rows.findIndex(row=>row.month===monthKey(data.selected,1));
    const selectX=selectedStart<0?null:x(selectedStart),selectedWidth=selectedStart<0?0:x(Math.min(rows.length-1,selectedStart+11))-selectX;
    const yearHeaders=range(start,end).map(year=>{
      const first=rows.findIndex(row=>row.month===monthKey(year,1)),last=rows.findIndex(row=>row.month===monthKey(year,12));
      const centre=(x(first)+x(last))/2,hasPlan=data.planYears.has(year),planned=data.annualPlans.get(year),hasNotice=data.noticeYears.has(year),annualNotice=data.annualNotices.get(year);
      return '<g class="pr-flow-yearhead"><text x="'+centre.toFixed(1)+'" y="20" text-anchor="middle">'+year+'년 '+(hasPlan?escape(format(planned)):'예정량 미확보')+'</text><line x1="'+x(first).toFixed(1)+'" x2="'+x(last).toFixed(1)+'" y1="50" y2="50"/><path d="M'+x(first).toFixed(1)+' 45v5 M'+x(last).toFixed(1)+' 45v5"/><text x="'+centre.toFixed(1)+'" y="40" text-anchor="middle" class="pr-flow-yearsub">'+(year===data.now?'현재 기준연도':hasPlan?'원천 모집·공급 일정':'원천 연도 일정 미확보')+'</text></g>';
    }).join('');
    const months=rows.map((row,index)=>{const m=Number(row.month.slice(5));return m===1||m===7?'<text x="'+x(index).toFixed(1)+'" y="356" text-anchor="middle">'+row.month.replace('-', '.')+'</text>':'';}).join('');
    const targetLine=data.target==null?'':'<line x1="62" x2="1062" y1="'+y(data.target).toFixed(1)+'" y2="'+y(data.target).toFixed(1)+'" stroke="#446b93" stroke-width="1.5" stroke-dasharray="7 6"/><text x="1059" y="'+Math.max(77,y(data.target)-6).toFixed(1)+'" text-anchor="end" class="pr-flow-target">전체 연결 계획 '+escape(format(data.target))+'</text>';
    const present=nowX==null?'':'<line x1="'+nowX.toFixed(1)+'" x2="'+nowX.toFixed(1)+'" y1="61" y2="327" stroke="#183d63" stroke-width="2" stroke-dasharray="4 4"/><rect x="'+(nowX-54).toFixed(1)+'" y="58" width="108" height="22" rx="4" fill="#183d63"/><text x="'+nowX.toFixed(1)+'" y="73" text-anchor="middle" class="pr-flow-present">현재 '+data.asOf.replace('-', '.')+'</text>';
    const current=data.current,delayShare=current.duePlanned>0?(100*current.overdue/current.duePlanned).toFixed(1)+'%':null,callouts=nowX==null?'':'<g class="pr-flow-callouts"><circle cx="'+nowX.toFixed(1)+'" cy="'+y(current.actual).toFixed(1)+'" r="5"/><text x="'+Math.max(70,nowX-15).toFixed(1)+'" y="'+Math.max(103,y(current.actual)-12).toFixed(1)+'" text-anchor="end">공고 확인 '+escape(format(current.actual))+'</text>'+(current.overdue?'<circle cx="'+nowX.toFixed(1)+'" cy="'+y(current.actual+current.overdue).toFixed(1)+'" r="5" class="delay"/><text x="'+Math.min(1050,nowX+15).toFixed(1)+'" y="'+Math.max(103,y(current.actual+current.overdue)-12).toFixed(1)+'" class="delay">공고 미확인 '+escape(format(current.overdue))+'</text>':'')+'</g>';
    const selected=data.chosen,attainment=data.target>0?(100*selected.actual/data.target).toFixed(1)+'%':'미확보';
    const issueText=data.issues.length?data.issues.slice(0,3).map(row=>escape(row.name)+' '+format(row.units)).join(' · '):data.hasSchedules?'현재까지 공급 일정 경과 후 공고 미확인 물량 없음':'모집·공급 예정월 미확보 · 지연 여부 판정 보류';
    const issueList=data.issues.length?'<details class="pr-flow-problems"><summary>일정 경과·공고 미확인 사업 '+data.issues.length+'건 전체 보기</summary><div>'+data.issues.map(row=>'<div><span>'+escape(row.name)+' <small>예정 '+escape(row.latestDueMonth||'월 미확보')+'</small></span><strong>'+format(row.units)+'</strong></div>').join('')+'</div></details>':'';
    const all=data.points,maxAll=Math.max(1,data.target||0,...all.map(row=>row.total));
    const miniX=index=>40+index*1000/10,miniY=value=>61-36*value/maxAll;
    const miniLine=key=>smoothLine(all.map((row,index)=>[miniX(index),miniY(key(row))]));
    const miniStart=miniX(start-(data.now-5)),miniEnd=miniX(end-(data.now-5));
    const overview='<div class="pr-flow-overview"><span>11년 전체 흐름 · '+(data.now-5)+'–'+(data.now+5)+'년</span><svg viewBox="0 0 1080 83" role="img" aria-label="11년 전체 계획 대비 공고 확인과 지연 후보 개요"><rect x="'+(miniStart-27).toFixed(1)+'" y="8" width="'+(miniEnd-miniStart+54).toFixed(1)+'" height="58" rx="4" fill="#dcecfb"/><line x1="40" x2="1040" y1="'+miniY(data.target||maxAll)+'" y2="'+miniY(data.target||maxAll)+'" stroke="#8ea5bb" stroke-dasharray="5 5"/><path d="'+miniLine(row=>row.actual)+'" fill="none" stroke="#239a91" stroke-width="3"/><path d="'+miniLine(row=>row.actual+row.overdue)+'" fill="none" stroke="#d94b5d" stroke-width="2"/><path d="'+miniLine(row=>row.actual+row.overdue+row.upcoming)+'" fill="none" stroke="#5a90cc" stroke-width="2"/>'+all.map((row,index)=>'<text x="'+miniX(index).toFixed(1)+'" y="78" text-anchor="middle">'+String(row.year).slice(2)+'</text>').join('')+'</svg></div>';
    const legend='<div class="pr-flow-legend"><span><i class="older"></i>이전 연도 공고</span><span><i class="previous"></i>작년 공고</span><span><i class="current"></i>올해 공고</span><span><i class="overdue"></i>예정 경과·공고 미확인</span><span><i class="upcoming"></i>향후 예정</span><span><i class="remaining"></i>일정 미확보 잔여</span></div>';
    const chart='<div class="pr-chart-scroll pr-flow-scroll"><svg viewBox="0 0 1120 385" role="img" aria-label="'+escape(start+'–'+end+'년 월별 누적 공급 흐름 · 공고 '+format(selected.actual)+' · 지연 후보 '+format(selected.overdue))+'"><defs><linearGradient id="pr-flow-unknown" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#cfdfef" stop-opacity=".78"/><stop offset="1" stop-color="#f6faff" stop-opacity=".9"/></linearGradient><pattern id="pr-flow-future-hatch" patternUnits="userSpaceOnUse" width="9" height="9" patternTransform="rotate(40)"><line x1="0" y1="0" x2="0" y2="9" stroke="#fff" stroke-opacity=".55" stroke-width="3"/></pattern><clipPath id="pr-flow-after-now"><rect x="'+(nowX??1062).toFixed(1)+'" y="60" width="'+(1062-(nowX??1062)).toFixed(1)+'" height="268"/></clipPath></defs><rect x="54" y="59" width="1018" height="274" rx="6" fill="#fbfdff"/>'+yearHeaders+(selectX==null?'':'<rect x="'+selectX.toFixed(1)+'" y="61" width="'+selectedWidth.toFixed(1)+'" height="266" fill="#dbeafb" opacity=".43"/>')+'<line x1="62" x2="1062" y1="327" y2="327" stroke="#a8bfd1"/>'+paths+'<path d="'+overduePath+'" fill="url(#pr-flow-future-hatch)" clip-path="url(#pr-flow-after-now)" opacity=".72"/><path d="'+futurePath+'" fill="url(#pr-flow-future-hatch)" opacity=".7"/><path d="'+remainingPath+'" fill="url(#pr-flow-future-hatch)" opacity=".16"/>'+targetLine+present+callouts+months+'<text x="1058" y="377" text-anchor="end" class="pr-flow-axis">월별 원천 일정과 공고 날짜 기준 · 곡선은 시각적 연결</text></svg></div>';
    return legend+chart+overview+'<div class="pr-flow-readout"><div><small>전체 연결 계획</small><strong>'+format(data.target)+'</strong></div><div><small>선택 '+data.selected+'년 공고 확인</small><strong>'+format(selected.actual)+'</strong></div><div class="warn"><small>일정 경과·공고 미확인</small><strong>'+format(selected.overdue)+'</strong><small>'+(selected.duePlanned>0?'예정 경과 물량의 '+(100*selected.overdue/selected.duePlanned).toFixed(1)+'%':'비율 산정 근거 미확보')+'</small></div><div><small>선택 연도까지 추가 예정</small><strong>'+format(selected.upcoming)+'</strong></div><div><small>일정 미확보 잔여</small><strong>'+format(selected.remaining)+'</strong></div><div><small>전체 대비 공고 확인</small><strong>'+attainment+'</strong></div></div><p class="pr-flow-issue">'+issueText+'</p>'+issueList+'<p class="pr-note">빨간 면은 원천 모집 예정월이 지났지만 연결 공고가 확인되지 않은 물량입니다. 확정 지연이 아닌 검토 후보이며 공고 원천 누락·연결 오류일 수 있습니다. 큰 옅은 면은 연도 일정이 확보되지 않은 잔여 계획입니다. 곡선은 실제 월별 확인값을 연결한 시각적 보간이며 월 사이의 물량을 추정하지 않습니다.</p>';
  }
  return {model,render};
})();
if(typeof module!=='undefined')module.exports=PolicyDeliveryFlow;
