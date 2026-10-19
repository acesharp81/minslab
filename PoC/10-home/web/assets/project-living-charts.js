'use strict';
const ProjectLivingCharts=(()=>{
 const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const valid=v=>typeof v==='number'&&Number.isFinite(v),n=v=>valid(v)?v.toLocaleString('ko-KR',{maximumFractionDigits:1}):'미확보';
 const colors=['#245e64','#46988e','#8ba056','#c49c54','#95768c'];
 const link=(r,label)=>r?.evidence_url?'<a href="'+e(r.evidence_url)+'" target="_blank" rel="noopener">▤ '+label+' 원천 ↗</a>':'';
 const swatch=color=>'<svg class="pac-swatch" viewBox="0 0 10 10" aria-hidden="true"><rect width="10" height="10" rx="2" fill="'+color+'"/></svg>';
 const note=r=>r?'<p class="pac-note">'+e(r.scope_label||r.region)+' · '+e(r.period)+'년'+(r.fallback?' · 상위 지역 참고':'')+'</p>':'';
 const svg=(body,w,h,label)=>'<svg viewBox="0 0 '+w+' '+h+'" role="img" aria-label="'+e(label)+'">'+body+'</svg>';
 const card=(title,body,cls)=>'<article class="pac-card pac-living '+cls+'"><h4>'+title+'</h4>'+body+'</article>';
 function income(r,pir,place){
  let body='<p class="pac-note">소득 분포 미확보</p>';
  if(r){
   const bins=r.bins,max=Math.ceil(Math.max(...bins.map(b=>b.pct))/5)*5,x=i=>66+i*52,y=p=>158-p/max*125;
   let plot=[0,.2,.4,.6,.8,1].map(f=>'<line x1="40" x2="345" y1="'+y(max*f)+'" y2="'+y(max*f)+'" stroke="#dce6e3"/><text x="35" y="'+(y(max*f)+3)+'" text-anchor="end">'+n(max*f)+'%</text>').join('');
   const short=['1천 미만','1~3천','3~5천','5~7천','7천~1억','1억 이상'];
   bins.forEach((b,i)=>{plot+='<rect x="'+(x(i)-17)+'" y="'+y(b.pct)+'" width="34" height="'+(158-y(b.pct))+'" rx="2" fill="#507d88"><title>'+e(b.label)+' · '+n(b.pct)+'%</title></rect><text x="'+x(i)+'" y="'+(y(b.pct)-8)+'" text-anchor="middle">'+n(b.pct)+'%</text><text x="'+x(i)+'" y="178" text-anchor="middle">'+short[i]+'</text>';});
   plot+='<text x="340" y="196" text-anchor="end">연소득 구간 · 원</text>';
   body='<p class="pac-note">전국 가구 · '+r.income_year+'년 소득 / '+r.year+'년 조사</p>'+svg(plot,365,205,'전국 가구의 연소득 구간별 비중 막대그래프')+'<div class="pac-income-stats"><div><small>평균소득 · 월 환산</small><b>'+n(r.mean_annual/12)+'만원</b><span>연 '+n(r.mean_annual)+'만원</span></div><div><small>중위소득 · 월 환산</small><b>'+n(r.median_annual/12)+'만원</b><span>연 '+n(r.median_annual)+'만원</span></div></div><p class="pac-note">막대 높이는 각 연소득 구간의 가구 비중입니다. 구간 폭은 서로 다르며 소득 금액 자체의 크기를 표시하지 않습니다. 중위소득은 조사 중앙값으로 복지 기준중위소득과 다릅니다.</p>'+link(r,'소득 분포')+' · '+(r.mean_source_url?'<a href="'+e(r.mean_source_url)+'" target="_blank" rel="noopener">▤ 평균·중앙값 원천 ↗</a>':'');
  }
  const capital=['서울특별시','인천광역시','경기도'].includes(place.region);
  body+='<section class="pac-pir"><h5>소득 대비 주택가격 비율 <span>PIR</span></h5>'+(pir?'<div><strong>'+n(capital?pir.capital:pir.national)+'<small>배</small></strong><span>'+(capital?'수도권 참고':'전국 참고')+' · '+pir.year+'년<br>전국 '+n(pir.national)+'배</span></div><p class="pac-note">자가가구 · 주택가격과 연 가구소득의 중위값 기준. 위 소득 그래프와 조사 대상·소득 정의가 다릅니다.</p>'+link(pir,'주거실태조사 PIR'):'<p class="pac-note">공식 PIR 미확보</p>')+'</section>';
  return card('평균 가구소득·주택가격 부담',body,'pac-income');
 }
 function distribution(r,title){
  if(!r)return '<h5>'+title+'</h5><p class="pac-note">자료 미확보</p>';
  let offset=0;const bars=r.bins.map((b,i)=>{if(!valid(b.pct))return '';const width=b.pct*3.6,part='<rect x="'+offset+'" width="'+width+'" height="18" fill="'+colors[i%colors.length]+'"><title>'+e(b.label)+' '+n(b.pct)+'%</title></rect>';offset+=width;return part;}).join('');
  return '<h5>'+title+'</h5>'+note(r)+'<svg class="pac-stacked" viewBox="0 0 360 18" preserveAspectRatio="none" role="img" aria-label="'+e(title+' 구성비')+'"><rect width="360" height="18" fill="#e6eae8"/>'+bars+'</svg><ul class="pac-living-legend">'+r.bins.map((b,i)=>'<li>'+swatch(colors[i%colors.length])+'<span>'+e(b.label)+'</span><b>'+n(b.pct)+(valid(b.pct)?'%':'')+'</b>'+(Object.hasOwn(b,'value')?'<small>'+n(b.value)+(valid(b.value)?'가구':'')+'</small>':'')+'</li>').join('')+'</ul>'+link(r,title);
 }
 function migration(r,duration){
  let body='<p class="pac-note">전입·전출 통계 미확보</p>';
  if(r){
   const history=r.history||[],max=Math.max(1,...history.flatMap(v=>[v.incoming,v.outgoing])),base=128,step=300/Math.max(1,history.length),y=v=>base-v/max*95;
   const plot=history.map((v,i)=>{const x=33+i*step;return '<g><title>'+e(v.period)+' 전입 '+n(v.incoming)+'명 / 전출 '+n(v.outgoing)+'명 / 순이동 '+n(v.net)+'명</title><rect x="'+x+'" y="'+y(v.incoming)+'" width="'+step*.35+'" height="'+(base-y(v.incoming))+'" fill="#245e64"/><rect x="'+(x+step*.4)+'" y="'+y(v.outgoing)+'" width="'+step*.35+'" height="'+(base-y(v.outgoing))+'" fill="#c49c54"/>'+((i%2===0&&i<history.length-2)||i===history.length-1?'<text x="'+(x+step*.4)+'" y="145" text-anchor="middle">'+v.period.slice(2,4)+'.'+v.period.slice(4)+'</text>':'')+'</g>';}).join('');
   body='<p class="pac-note">'+e(r.scope_label)+' · '+r.period.slice(0,4)+'.'+r.period.slice(4)+' · '+e(r.scope_note)+'</p><div class="pac-move-stats"><div><small>전입</small><b>'+n(r.incoming)+'명</b></div><div><small>전출</small><b>'+n(r.outgoing)+'명</b></div><div><small>순이동</small><b>'+ (r.net>0?'+':'')+n(r.net)+'명</b></div></div>'+svg('<text x="30" y="17">월별 전입·전출 (명)</text><text x="333" y="17" text-anchor="end">최대 '+n(max)+'</text>'+plot,365,155,'최근 12개월 전입·전출')+'<div class="pac-series"><span>'+swatch('#245e64')+'전입</span><span>'+swatch('#c49c54')+'전출</span></div>'+link(r,'인구이동');
  }
  body+='<section class="pac-residence">'+distribution(duration,'현재 주택 거주기간')+'</section>';
  return card('인구 유입·유출과 거주기간',body,'pac-migration');
 }
 function render(data,place){const l=data.living||{};return income(l.income,l.pir,place)+migration(l.migration,l.duration)+card('주거 형태·주택 유형',distribution(l.tenure,'주거 형태 · 자가·전세·월세')+'<section class="pac-housing-types">'+distribution(l.housing_type,'주택·거처 유형')+'</section><p class="pac-note">일반가구 기준 · 월세는 보증금 유무를 합산합니다. 주택 유형은 거주 가구 비율이며 빈집은 제외합니다. 기타는 전체에서 앞선 유형을 제외한 잔여 가구입니다. 비공개·미확보 수치는 0으로 대체하지 않습니다.</p>','pac-housing');}
 return {render};
})();
