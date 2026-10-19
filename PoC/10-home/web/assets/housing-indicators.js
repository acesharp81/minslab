'use strict';
/* Standalone regional comparison workspace. Regional observations, dated outlooks and
   the selected project ledger remain separate series and scopes. */
const HousingIndicators=(()=>{
 const e=v=>esc(String(v??'')),n=v=>Number.isFinite(v)?num(Math.round(v)):'미확보',f=(v,d=1)=>Number.isFinite(v)?v.toLocaleString('ko-KR',{maximumFractionDigits:d}):'미확보';
 const colors=['#1867b8','#169a87','#df842d','#815bbb','#c64e67'],capital=['서울특별시','경기도','인천광역시'];
 const short=v=>Math.abs(v)>=10000?f(v/10000,1)+'만':f(v,1),known=Number.isFinite;
 const titles=['아파트 매매가격 변동률','주택보급률과 공급 배치','인허가·착공·준공과 장기 평균','공공주택·비아파트 공급 구성','월별·누계 착공실적','향후 입주예정물량과 공급 공백','전체·준공 후 미분양','장기 수요·적정 공급·부족분','과거 실적 대비 목표 규모'];
 const questions=['가격 상승 압력이 큰 지역에서 공급이 지연되고 있는가?','주택이 상대적으로 부족한 지역에 사업과 물량이 배치돼 있는가?','계획·승인은 늘지만 실제 건설은 따라오지 못하는가?','위축된 공급 부문을 해당 프로그램이 보완하고 있는가?','연간 목표를 달성할 추진속도가 나오고 있는가?','언제, 어디에 공급 공백이 생기며 어떤 사업을 점검해야 하는가?','공급 부족인가, 공급된 주택의 소화가 어려운가?','정책목표와 지역별 물량 배정의 근거는 무엇인가?','목표가 과거 추진 수준보다 얼마나 높은가?'];
 const topics=[
  {id:'households',title:'가구 구성과 주택 기반',note:'가구 변화와 주택 보급 수준',cards:['households',1]},
  {id:'market',title:'주택시장과 수급',note:'가격 흐름과 미분양 재고',cards:[0,6]},
  {id:'actuals',title:'공급 실적과 구성',note:'단계별 실적과 공급 유형',cards:[2,4,3]},
  {id:'outlook',title:'향후 공급과 목표',note:'입주 예정과 수요·목표 규모',cards:[5,7,8]}
 ];
 function topicLayout(cards){
  return topics.map((topic,index)=>{const keys=topic.cards.filter(key=>cards[key]);return '<section class="mi-topic" data-mi-topic="'+topic.id+'"><header class="mi-topic-heading"><span class="mi-topic-number">'+String(index+1).padStart(2,'0')+'</span><div><h3>'+topic.title+'</h3><p>'+topic.note+'</p></div></header><div class="mi-grid mi-topic-grid '+(keys.length<3?'mi-topic-pair':'')+'">'+keys.map(key=>cards[key]).join('')+'</div></section>';}).join('');
 }
 const states=new WeakMap(),observers=new Map();
 const link=(url,label)=>'<a href="'+e(safeUrl(url))+'" target="_blank" rel="noopener">'+e(label)+' ↗</a>';
 const legend=items=>'<div class="mi-legend">'+items.map((r,i)=>'<span><i style="background:'+e(r.color||colors[i%colors.length])+'"></i>'+e(r.label||r.name)+'</span>').join('')+'</div>';
 const kpis=items=>'<div class="mi-kpis">'+items.map(([label,value,unit=''])=>'<div><small>'+e(label)+'</small><b>'+e(value)+unit+'</b></div>').join('')+'</div>';
 const table=(headers,rows)=>'<div class="mi-table-scroll"><table><thead><tr>'+headers.map(h=>'<th>'+e(h)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+row.map(v=>'<td>'+e(v)+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';
 const details=(notes,links=[],values='')=>'<details class="mi-method"><summary>수치·기준·원천</summary>'+notes.map(note=>'<p>'+e(note)+'</p>').join('')+links.map(([url,label])=>link(url,label)).join(' · ')+values+'</details>';
 const empty=text=>'<div class="mi-empty">'+e(text)+'</div>';
 function plot(labels,series,{unit='호',guides=[],height=215}={}){
  const all=series.flatMap(s=>s.values).filter(known).concat(guides.map(g=>g.value).filter(known));
  if(!all.length)return empty('해당 범위의 비교 수치 미확보');
  const min=Math.min(0,...all),max=Math.max(1,...all)*1.08,W=410,H=height,left=48,right=391,top=22,bottom=H-32,step=(right-left)/Math.max(1,labels.length),x=i=>left+step*(i+.5),y=v=>bottom-(v-min)/(max-min)*(bottom-top);
  let body='<text x="'+left+'" y="12">'+e(unit)+'</text>';
  for(let i=0;i<=4;i++){const v=min+(max-min)*i/4;body+='<line x1="'+left+'" x2="'+right+'" y1="'+y(v)+'" y2="'+y(v)+'" stroke="#e2eaf2"/><text x="'+(left-5)+'" y="'+(y(v)+3)+'" text-anchor="end">'+e(short(v))+'</text>';}
  const bars=series.filter(s=>s.type==='bar'),bw=Math.min(18,step*.8/Math.max(1,bars.length));
  for(const [index,s] of series.entries()){
   const color=s.color||colors[index%colors.length];let path='',open=false;
   s.values.forEach((v,i)=>{if(!known(v)){open=false;return;}const xx=x(i),yy=y(v),title=e(labels[i]+' '+s.name+' '+f(v,2)+unit);
    if(s.type==='bar'){const pos=xx+(bars.indexOf(s)-(bars.length-1)/2)*bw;body+='<rect x="'+(pos-bw/2+1)+'" y="'+Math.min(yy,y(0))+'" width="'+Math.max(1,bw-2)+'" height="'+Math.max(1,Math.abs(y(0)-yy))+'" fill="'+color+'" opacity="'+(s.partial?.[i]?'.35':'1')+'"><title>'+title+(s.partial?.[i]?' · 부분 집계':'')+'</title></rect>';if(bars.length===1&&labels.length<=4)body+='<text x="'+pos+'" y="'+(yy-6)+'" text-anchor="middle" style="fill:'+color+'">'+e(short(v))+'</text>';}else{path+=(open?'L':'M')+xx+' '+yy;open=true;body+='<circle cx="'+xx+'" cy="'+yy+'" r="2.5" fill="'+color+'"><title>'+title+'</title></circle>';}
   });
   if(path)body+='<path d="'+path+'" fill="none" stroke="'+color+'" stroke-width="2.5" stroke-dasharray="'+(s.dash||'')+'"/>';
  }
  for(const guide of guides)if(known(guide.value))body+='<line x1="'+left+'" x2="'+right+'" y1="'+y(guide.value)+'" y2="'+y(guide.value)+'" stroke="'+(guide.color||'#997449')+'" stroke-width="1.7" stroke-dasharray="5 4"><title>'+e(guide.label+' '+f(guide.value)+unit)+'</title></line>';
  labels.forEach((label,i)=>{if(labels.length<=12||i%2===0)body+='<text x="'+x(i)+'" y="'+(H-11)+'" text-anchor="middle">'+e(label)+'</text>';});
  return '<svg class="mi-chart" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+e(series.map(s=>s.name).join(', ')+' 비교')+'">'+body+'</svg>'+legend([...series,...guides.map(g=>({name:g.label,color:g.color||'#997449'}))]);
 }
 function mapColor(type,value,quantity=0,maxQuantity=1){
  const blend=(hex,t)=>'#'+[1,3,5].map(i=>Math.round(255+(parseInt(hex.slice(i,i+2),16)-255)*t).toString(16).padStart(2,'0')).join('');
  if(type==='housing'){
   if(!known(value))return '#edf1f5';
   return blend(value>=100?'#218464':'#b63344',.12+.88*Math.min(Math.abs(value-100)/15,1));
  }
  const depth=.12+.88*Math.sqrt(Math.min(1,Math.max(0,quantity||0)/Math.max(1,maxQuantity)));
  return blend(!known(value)?'#81909e':value>0?'#b85b66':value<0?'#247ab3':'#657b8c',depth);
 }
 function map(data,type,calculated=false){
  const shapes=data.places.filter(p=>p.rings?.length),regionMap=new Map(data.places.filter(p=>!p.municipality).map(p=>[p.region,p]));
  if(!shapes.length)return empty('선택 범위의 지역 경계 미확보');
  // Offshore Ongjin islands have their own extent; they must not shrink the mainland.
  const islands=shapes.filter(p=>p.region==='인천광역시'&&p.name==='옹진군'),mainland=shapes.filter(p=>!islands.includes(p)),hasInset=islands.length&&mainland.length;
  function projection(rows,box){
   const points=rows.flatMap(p=>p.rings.flat()),xs=points.map(p=>p[0]),ys=points.map(p=>p[1]),minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys),scale=Math.min(box.width/Math.max(.01,maxX-minX),box.height/Math.max(.01,maxY-minY));
   return {X:v=>box.x+(box.width-(maxX-minX)*scale)/2+(v-minX)*scale,Y:v=>box.y+(box.height-(maxY-minY)*scale)/2+(maxY-v)*scale};
  }
  const mainView=projection(hasInset?mainland:shapes,hasInset?{x:126,y:14,width:272,height:198}:{x:25,y:14,width:360,height:198});
  const islandView=hasInset?projection(islands,{x:15,y:139,width:99,height:70}):null;
  const maxUnits=Math.max(1,...shapes.map(p=>p.target_units||0));const insetFrame='<g class="mi-map-inset-frame" aria-hidden="true"><rect x="8" y="105" width="113" height="111" rx="5" fill="#f8fbfd" stroke="#cad9e5"/><text x="15" y="120" font-size="10" fill="#52748d">옹진군 도서</text><text x="15" y="132" font-size="8" fill="#7890a3">별도 축척</text></g>';let body='';
  for(const p of shapes){
   const price=p.price.at(-1),local=calculated?p.housing.at(-1)?.calculated_ratio:p.official_housing?.official_ratio,province=regionMap.get(p.region)?.official_housing;
   const value=type==='price'?price?.change_pct:local??(!calculated?province?.official_ratio:null),label=type==='price'?f(value,2)+'% · '+(price?.period||'가격 미확보'):f(value)+'% · '+(calculated?'동일 정의 산출':local==null?'시도 공식값 참고':'공식 주택보급률');
   const fill=mapColor(type,value,p.target_units,maxUnits);
   const inset=hasInset&&islands.includes(p),{X,Y}=inset?islandView:mainView;
   const path=p.rings.map(r=>'M'+r.map(pt=>X(pt[0]).toFixed(1)+','+Y(pt[1]).toFixed(1)).join('L')+'Z').join('');
   const title=p.region+' '+p.name+' · '+label+' · 사업계획 '+n(p.target_units)+'호 · '+data.scope.year+'년 착공 예정 '+n(p.construction_planned)+'호 / 입주 예정 '+n(p.move_in_planned)+'호 · 지연 '+p.delayed_count+'개 / 주의 '+p.warning_count+'개';
   body+='<g role="button" tabindex="0" data-mi-place="'+e(p.id)+'" data-mi-map-area="'+(inset?'islands':'mainland')+'" aria-label="'+e(title)+'"><title>'+e(title)+'</title>'+(inset?insetFrame:'')+'<path d="'+path+'" fill="'+fill+'" stroke="'+(p.id===data.scope.municipality_id?'#164f87':'#7194aa')+'" stroke-width="'+(p.id===data.scope.municipality_id?'2':'0.6')+'"/>';
   if(p.delayed_count&&(inset||(known(p.longitude)&&known(p.latitude))))body+='<text x="'+(inset?108:X(p.longitude))+'" y="'+(inset?120:Y(p.latitude)+4)+'" text-anchor="middle" fill="#b51f38" font-weight="900" font-size="14">!</text>';
   body+='</g>';
  }
  return '<svg class="mi-map" viewBox="0 0 410 226" role="group" aria-label="'+e(type==='price'?'아파트 가격 변동과 공급사업·지연 지역':'주택보급률과 공급사업 배치')+'">'+body+'</svg><div class="mi-map-key">'+(type==='price'?'빨강: 가격 상승 · 파랑: 하락 · 진함: 공급계획 규모':'초록: 100% 이상 · 빨강: 100% 미만 · 진함: 100%와의 차이')+'<br><b class="mi-red">!</b> 지연 사업 · 지역을 눌러 비교'+(hasInset?' · 옹진군 도서는 별도 축척':'')+'</div>';
 }
 function card(index,body,method,badge=''){
  return '<article class="pr-card mi-card" data-housing-indicator="'+index+'"><header><h3>'+titles[index]+'</h3>'+(badge?'<small class="mi-badge">'+e(badge)+'</small>':'')+'</header><div class="mi-card-body">'+body+'</div><p class="mi-question">'+questions[index]+'</p>'+method+'</article>';
 }
 function selectedPlaces(d,key='price'){
  if(d.scope.municipality_id){const p=d.places.find(p=>p.id===d.scope.municipality_id);return p?[p]:[];}
  return d.places.filter(p=>!p.municipality);
 }
 function priceCard(d){
  const places=selectedPlaces(d),months=[...new Set(places.flatMap(p=>p.price.map(r=>r.period)))].sort(),latest=places.map(p=>({p,v:p.price.at(-1)})),risks=d.places.filter(p=>p.municipality&&p.price.at(-1)?.change_pct>0&&p.delayed_count);
  const body=map(d,'price')+kpis(latest.map(({p,v})=>[p.name+' · '+(v?.period||''),f(v?.change_pct,2),'%']))+plot(months.map(m=>m.slice(2).replace('-','.')),places.map((p,i)=>({name:p.name+' 월 변동률',color:colors[i],values:months.map(m=>p.price.find(r=>r.period===m)?.change_pct)})),{unit:'%',height:175})+'<p class="mi-result">가격 상승·지연 동반 <b>'+risks.length+'개 지역</b></p>';
  return card(0,body,details(['한국부동산원 월간 아파트 지수의 연속 두 달 변동률=(이번 달/이전 달−1)×100. 동일 조회 판본·기준시점만 비교합니다. 주간 변동률·거래 평균가격과 다릅니다.','색 계열은 최근 확보 가격 상승·하락이며 진함은 지도에 표시한 지역 중 최대 사업계획 대비 상대 규모입니다. 추가 원을 사용하지 않습니다. 느낌표는 기준일 목표 대비 2% 이상 부족입니다. 가격 기준월과 지연 기준일은 다릅니다.'],[[d.sources.price,'아파트 가격 원천']],table(['지역','가격 기준월','변동률','지연 사업'],latest.map(({p,v})=>[p.name,v?.period||'미확보',f(v?.change_pct,3)+'%',p.delayed_count]))),'월간 · 공개 지수');
 }
 function housingCard(d,calculated){
  const places=selectedPlaces(d),rows=places.map(p=>({p,r:calculated?p.housing.at(-1):p.official_housing})),values=rows.map(({r})=>calculated?r?.calculated_ratio:r?.official_ratio);
  const body='<div class="mi-segment" role="group" aria-label="주택보급률 기준"><button type="button" data-mi-housing="official" aria-pressed="'+!calculated+'">공식 공표값</button><button type="button" data-mi-housing="calculated" aria-pressed="'+calculated+'">최신 동일 정의 산출</button></div>'+map(d,'housing',calculated)+(values.some(known)?plot(rows.map(({p,r})=>p.name.replace('광역시','').replace('특별시','')+' '+(r?.year||'')),[{name:calculated?'주택수/일반가구 산출':'공식 주택보급률',type:'bar',values}],{unit:'%',guides:[{label:'100% 기준',value:100,color:'#79889b'}],height:180}):empty('시군구 공식 주택보급률 미확보 · 최신 산출 모드에서 자체 주택·가구를 비교하세요.'));
  return card(1,body,details(['공식값은 국토부가 공표한 주택보급률입니다. 최신 산출값은 같은 연도·지역의 다가구 구분거처 반영 주택수÷일반가구×100이며 공식 공표값으로 바꾸지 않습니다.','시군구 공식값 미확보 시 지도 배경은 시도 공식값을 참고합니다. 최신 산출 모드에서는 시군구 자체 자료만 칠합니다. 100% 이상은 초록, 미만은 빨강이며 100%에서 멀수록 진해지며 차이 15%p 이상은 가장 진한 색입니다. 100% 미만을 곧바로 공실 부족·정책 지연으로 단정하지 않습니다.'],[[d.sources.housing,'주택보급률 원천']],table(['지역','공식 연도/비율','최신 산출 연도/비율','사업계획'],places.map(p=>[p.name,(p.official_housing?.year||'—')+' / '+f(p.official_housing?.official_ratio)+'%',(p.housing.at(-1)?.year||'—')+' / '+f(p.housing.at(-1)?.calculated_ratio)+'%',n(p.target_units)+'호']))),calculated?'동일 정의 산출':'공식 공표값');
 }
 function supplyCard(d){
  const metrics=['인허가','착공','준공'],ref=d.reference.long_average,scope=d.reference.selected_market_scope,values=d.annual,bench=scope?ref[scope]:null;
  const series=metrics.map((name,i)=>({name,type:'bar',color:colors[i],values:values.map(r=>r.metrics[name].units),partial:values.map(r=>!r.metrics[name].complete)}));
  const guides=metrics.map((name,i)=>({label:name+' '+(bench?'10년 평균':'확보 기간 평균'),value:bench?.[name]??d.averages[name].value,color:colors[i]}));
  return card(2,plot(values.map(r=>String(r.year).slice(2)),series,{guides})+kpis(metrics.map(m=>[m+' 비교 평균',n(bench?.[m]??d.averages[m].value),'호'])),details(['지역 전체 인허가·착공·준공 실적은 서로 다른 단계입니다. 세 수치를 합산하거나 정책 인정 실적으로 배분하지 않습니다. 옅은 막대는 일부 월만 확보한 연도입니다.','서울·수도권의 10년 평균은 2025-09-07 발표 원문 2015~2024년 기준입니다. 다른 지역은 선택한 기준기간의 완결 연도 평균만 사용합니다.'],[[d.sources.supply['착공'],'국토부 공급 통계'],[d.reference.source.evidence_url,'장기 평균 발표 원문']],table(['연도',...metrics],values.map(r=>[r.year,...metrics.map(m=>n(r.metrics[m].units)+(r.metrics[m].complete?'':' · 부분'))]))),'지역 전체 · 시도');
 }
 function typeCard(d){
  const r=d.reference.types,c=d.classification;
  return card(3,plot(r.rows.map(r=>String(r.year)),[{name:'수도권 공공주택 착공',type:'bar',values:r.rows.map(r=>r.public),color:colors[1]},{name:'수도권 비아파트 착공',type:'bar',values:r.rows.map(r=>r.non_apartment),color:colors[0]}],{guides:[{label:'공공주택 10년 평균',value:r.public_average,color:colors[1]},{label:'비아파트 10년 평균',value:r.non_apartment_average,color:colors[0]}]})+'<h4>선택 원장의 사업계획 구성</h4>'+composition(c.sectors)+composition(c.housing_types),details(['위 추이는 R2509345의 수도권 전체 2022~2024년 실적과 2015~2024년 평균입니다. 선택 프로그램의 최신 실적과 같은 모집단으로 나누거나 합산하지 않습니다.',c.basis,'공공/민간과 아파트/비아파트는 서로 겹치는 두 분류축입니다. 분류 미확보 사업은 미분류로 남깁니다.'],[[d.reference.source.evidence_url,'유형별 착공 원문']],table(['연도','공공주택 착공','비아파트 착공'],r.rows.map(r=>[r.year,n(r.public),n(r.non_apartment)]))),'2025 발표 참고');
 }
 function composition(rows){const max=Math.max(1,...rows.map(r=>r.units));return '<div class="mi-composition">'+rows.map((r,i)=>'<div><span>'+e(r.label)+'</span><svg viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true"><rect width="100" height="8" rx="2" fill="#edf2f7"/><rect width="'+(r.units/max*100)+'" height="8" rx="2" fill="'+colors[i%colors.length]+'"/></svg><b>'+n(r.units)+'호</b></div>').join('')+'</div>';}
 function monthlyCard(d,cumulative){
  const rows=d.monthly_starts,key=cumulative?'cumulative':'regional',prior=cumulative?'prior_cumulative':'prior_regional',policy=rows.map((r,i)=>cumulative?r.confirmed_policy_cumulative:known(r.confirmed_policy_cumulative)?r.confirmed_policy_cumulative-(rows[i-1]?.confirmed_policy_cumulative||0):null),last=rows.filter(r=>known(r.cumulative)).at(-1);
  const guides=cumulative&&d.goal.scope_comparable&&known(d.goal.value)?[{label:d.scope.year+' 연간 목표',value:d.goal.value,color:'#b67a1f'}]:[];
  return card(4,'<div class="mi-segment"><button type="button" data-mi-monthly="monthly" aria-pressed="'+!cumulative+'">월별</button><button type="button" data-mi-monthly="cumulative" aria-pressed="'+cumulative+'">연초 누계</button></div>'+plot(rows.map(r=>r.month+'월'),[{name:'지역 전체 '+d.scope.year+'년',type:cumulative?undefined:'bar',values:rows.map(r=>r[key]),color:colors[0]},{name:'지역 전체 '+(d.scope.year-1)+'년',type:cumulative?undefined:'bar',values:rows.map(r=>r[prior]),color:'#a7b4c5',dash:'4 3'},{name:'정책 귀속·근거 확정 착공',values:policy,color:colors[1]}],{guides})+kpis([['최근 누계',n(last?.cumulative),'호'],['전년 동기',known(last?.yoy_pct)?(last.yoy_pct>0?'+':'')+f(last.yoy_pct):'미확보','%']])+(!policy.some(known)?'<p class="mi-result">정책 인정 착공은 근거 미확보로 계열을 비워 둡니다.</p>':''),details(['지역 전체는 국토부 시도 착공 통계입니다. 정책 계열은 선택 원장 중 정책 귀속·단계 근거가 확정되고 추정 표시가 없는 착공입니다. 두 계열은 더하지 않습니다.','전년 동기는 같은 월 구간만 비교합니다. 월이 누락되면 그 이후 누계를 연결하지 않습니다. 연간 목표는 누계 차트의 수평선으로 표시하며 월별 목표를 임의 분배하지 않습니다.'],[[d.sources.supply['착공'],'월별 착공 원천']],table(['월','지역 착공','지역 누계','전년 누계','정책 확정 누계'],rows.map(r=>[r.period,n(r.regional),n(r.cumulative),n(r.prior_cumulative),n(r.confirmed_policy_cumulative)]))),d.scope.year+'년 · 시도 비교');
 }
 function futureCard(d){
  const years=Array.from({length:5},(_,i)=>d.scope.year+i),p=d.future.points,series=[['CONSTRUCTION','착공 예정',colors[2]],['COMPLETION','준공 예정',colors[0]],['MOVE_IN','입주 예정',colors[3]]].map(([stage,name,color])=>({name,color,type:'bar',values:years.map(y=>p.some(p=>p.stage===stage)?p.filter(p=>p.stage===stage&&p.year===y).reduce((a,b)=>a+b.units,0):null)}));
  const move=p.filter(p=>p.stage==='MOVE_IN'&&years.includes(p.year)),check=move.filter(p=>p.status==='DELAYED'||p.status==='WARNING');
  const rows=move.slice().sort((a,b)=>a.date.localeCompare(b.date)).slice(0,8),source=d.reference.occupancy,scope=d.reference.selected_market_scope;
  const reference=scope?'<p class="mi-reference">2025 발표 전망 · '+(scope==='서울특별시'?'서울':'수도권')+' APT 2026년 '+n(source.rows.find(r=>r.year===2026)[scope==='서울특별시'?'seoul_units':'units'])+'호 / 10년 평균 '+n(scope==='서울특별시'?source.seoul_long_average:source.long_average)+'호</p>':'';
  return card(5,plot(years,series)+kpis([['입주 일정 미확보',n(d.future.missing_move_in_schedule_count),'개 사업'],['지연·주의 연결',n(check.length),'건']])+reference+'<div class="mi-project-list">'+rows.map(p=>'<button type="button" data-mi-project="'+e(p.source_ids[0])+'"><span>'+e(p.date.slice(0,7)+' · '+p.name)+'</span><b>'+n(p.units)+'호</b><small class="mi-status '+p.status.toLowerCase()+'">'+({DELAYED:'지연',WARNING:'주의',NORMAL:'확보 일정'}[p.status])+'</small></button>').join('')+'</div>',details(['막대는 선택 원장의 확보된 향후 일정입니다. 일정이 없는 연도의 확보량 0은 지역 전체 입주물량이 0이라는 뜻이 아닙니다. 전체 입주 일정 미확보는 빈 계열로 남깁니다.','동일 사업의 중복 일정은 제거하고 총 물량 한도 안에서 집계합니다. 입주 예정과 준공 예정은 더하지 않습니다. 사업을 눌러 일정과 단계 근거를 확인합니다.','입주 시장 전망은 2025-09-07 발표 당시의 수도권 아파트 참고값이며 이후 변경을 반영한 최신 전망이 아닙니다.'],[[d.reference.source.evidence_url,'원문 입주 전망']],table(['연도','단계','사업','호수','일정'],p.filter(p=>years.includes(p.year)).map(p=>[p.year,p.stage,p.name,n(p.units),p.date]))),'선택 원장 · 향후 일정');
 }
 function unsoldCard(d){
  const rows=d.unsold.history,last=rows.at(-1),months=rows.map(r=>r.period.slice(2).replace('-','.'));
  return card(6,plot(months,[{name:'전체 미분양',values:rows.map(r=>r.total),color:colors[0]},{name:'준공 후 미분양',type:'bar',values:rows.map(r=>r.completed),color:colors[4]}])+kpis([['전체 미분양',n(last?.total),'호'],['준공 후 비중',f(last?.completed_share_pct),'%'],['준공 후 전월 증감',known(last?.completed_change)?(last.completed_change>0?'+':'')+n(last.completed_change):'미확보','호']]),details(['준공 후 미분양은 전체 미분양의 일부입니다. 두 수치를 합산하지 않습니다. 비중=준공 후÷전체×100이며 전체 0이면 비중은 산정하지 않습니다.',d.unsold.fallback?'선택 시군구 원천이 없어 시도 전체 참고값을 표시합니다.':'선택 지역의 월말 재고 통계입니다. 개별 사업의 미분양으로 배분하지 않습니다.','향후 입주예정 카드와 함께 재고 소화와 공급 공백을 비교합니다.'],[[d.sources.unsold,'미분양 원천']],table(['월','전체','준공 후','준공 후 비중'],rows.map(r=>[r.period,n(r.total),n(r.completed),f(r.completed_share_pct)+'%']))),last?.period||'미확보');
 }
 function demandCard(d){
  const scope=d.reference.selected_market_scope||'수도권',r=d.reference.demand[scope],forecast=d.household_forecast,goal=d.goal.metric==='CONSTRUCTION'&&d.goal.unit==='호'&&d.scope.year>=2026&&d.scope.year<=2030?d.goal.value:null;
  const body=plot(['과거 착공','장기 수요','적정 공급','부족분'],[{name:scope+' 연간 기준',type:'bar',values:[r.baseline_starts,r.annual_demand,r.adequate_supply,r.annual_shortage],color:colors[0]}])+kpis([['연간 장기 수요',n(r.annual_demand),'호'],['연간 부족분',n(r.annual_shortage),'호']])+(known(goal)?'<p class="mi-result">선택 연도 목표 '+n(goal)+'호 · '+(d.scope.kind==='policy'&&d.goal.scope_comparable?'원문 과거 추세 대비 '+(goal-r.baseline_starts>=0?'+':'')+n(goal-r.baseline_starts)+'호 · 부족분 대비 증감 '+f((goal-r.baseline_starts)/r.annual_shortage*100)+'%':'목표 규모는 '+scope+' 기준 부족분의 '+f(goal/r.annual_shortage*100)+'% · 달성률 아님')+'</p>':'')+(forecast.length?'<h4>장래가구추계 · '+d.scope.regions.map(e).join(' + ')+'</h4>'+plot(forecast.slice(0,6).map(r=>r.year),[{name:'장래 일반가구',values:forecast.slice(0,6).map(r=>r.households),color:colors[2]}],{unit:'가구',height:160}):'');
  return card(7,body,details(['수요·적정 공급·부족분은 2025-09-07 원문의 2026~2030년 연간 기준입니다. 과거 추세 지속을 가정한 부족분이며 현재 재고−가구 차이로 대체하지 않습니다.','경기·인천 개별 수요 배분은 원문에 없어 수도권 공동 참고값을 표시합니다. 선택 프로그램·사업이 같은 단계·지역·연도에 기여하는 목표가 확보된 경우에만 규모를 비교합니다.','장래가구추계는 공식 가구 전망이며 주택수요·적정 공급량과 다른 지표입니다. 시군구로 임의 배분하지 않습니다.'],[[d.reference.source.evidence_url,'장기 수요·적정 공급 원문']],table(['범위','과거 평균','장기 수요','적정 공급','부족분'],[[scope,n(r.baseline_starts),n(r.annual_demand),n(r.adequate_supply),n(r.annual_shortage)]])),'2025 발표 · '+scope+' 참고');
 }
 function goalCard(d){
  const g=d.goal,s=d.goal_scale,a=d.averages['착공'],r=d.reference.goal_scale,labels=['기준기간 평균','선택연도 목표'],values=[s.baseline,g.metric==='CONSTRUCTION'&&g.unit==='호'?g.value:null];
  const body=plot(labels,[{name:'동일 범위 연간 착공 비교',type:'bar',values,color:colors[0]}])+kpis([[g.total_scope+' 총 목표',n(g.total_value),e(g.unit)],['목표 증감',known(s.increment)?(s.increment>0?'+':'')+n(s.increment):'비교 보류','호'],['과거 평균 대비',f(s.multiplier,2),'배']])+'<p class="mi-reference">원문 수도권 목표: 연 '+n(r.target_annual)+'호 · '+r.baseline_period+' 연평균 '+n(r.baseline_annual)+'호 대비 '+f(r.published_multiplier)+'배</p>';
  return card(8,body,details(['선택 비교는 '+a.start_year+'~'+a.end_year+'년 완결 실적의 평균과 '+d.scope.year+'년 같은 범위 착공 목표입니다. 현재 연도의 일부 월 실적을 연간 평균에 섞지 않습니다.','프로그램·사업 목표를 지역 전체 과거 실적과 나눠 배율로 표시하지 않습니다. 범위·단계·기간이 맞지 않으면 비교 보류로 표시하고 원문 정책 배율을 별도 참고합니다.','원문 1.7배와 연 11만호 증가량은 발표 당시 반올림 수치입니다. 선택 기준기간의 실제 계산값과 구분합니다.'],[[d.reference.source.evidence_url,'목표 규모 원문']],table(['기준','기간','수치'],[['확보 완결 연도',a.start_year+'~'+a.end_year,a.acquired_years+'/'+a.required_years+'개년'],[g.label,d.scope.year,n(g.value)+' '+g.unit],['비교 배율','동일 범위',f(s.multiplier,2)+'배']])),'목표와 기준기간');
 }
 function render(host,st){
  const d=st.data,cards={0:priceCard(d),1:housingCard(d,st.calculated),2:supplyCard(d),3:typeCard(d),4:monthlyCard(d,st.cumulative),5:futureCard(d),6:unsoldCard(d),7:demandCard(d),8:goalCard(d)};
  if(st.options.includeHouseholds)cards.households='<div class="mi-households" data-mi-households><article class="pr-card"><h3>1·2·3·4인 이상 가구 변화</h3><p>지역 통계 확인 중…</p></article></div>';
  host.querySelector('.mi-topics').innerHTML=topicLayout(cards);
  if(st.options.includeHouseholds)PolicyReport.statisticsDemographics(host.querySelector('[data-mi-households]'),[],d.scope.municipality_id,st.options.region,d.places.find(p=>p.id===d.scope.municipality_id),{householdsOnly:true,regions:d.scope.regions});
  host.querySelector('.mi-scope-label').textContent=d.scope.name+' · '+(d.scope.municipality||d.scope.regions.join(' + '));
  host.querySelector('.mi-status-line').textContent='실적 기준 '+d.as_of_date+' · 선택 원장 '+d.scope.project_count+'개 사업';
  if(d.scope.municipality_id){st.options.region=d.places.find(p=>p.id===d.scope.municipality_id)?.region||st.options.region;host.querySelector('[data-mi-filter=region]').value=st.options.region||'';}
  const city=host.querySelector('[data-mi-filter="municipality_id"]');city.innerHTML='<option value="">시도 전체</option>'+d.places.filter(p=>p.municipality).map(p=>'<option value="'+e(p.id)+'" '+(p.id===st.options.municipalityId?'selected':'')+'>'+e(p.region+' · '+p.name)+'</option>').join('');
 }
 async function load(host,st){
  const ticket=++st.ticket;st.loading=true;st.controller?.abort();st.controller=new AbortController();host.querySelector('.mi-status-line').textContent='비교 자료 조회 중…';
  const o=st.options,query=new URLSearchParams({kind:o.kind,scope_id:o.id,as_of_date:o.asOf,year:String(o.year),baseline_years:String(o.baselineYears||3),portfolio:String(!!o.portfolio)});
  if(o.region)query.set('region',o.region);if(o.municipalityId)query.set('municipality_id',o.municipalityId);
  try{const response=await fetch(API+'/housing-indicators?'+query,{credentials:'same-origin',signal:st.controller.signal});const data=await response.json();if(!response.ok)throw Error(data.detail||'지표 조회 실패');if(ticket!==st.ticket||!host.isConnected)return;if(data.status!=='READY')throw Error(data.notice);st.data=data;render(host,st);}
  catch(err){if(err.name==='AbortError'||ticket!==st.ticket||!host.isConnected)return;host.querySelector('.mi-status-line').textContent=err.message;host.querySelector('.mi-topics').innerHTML=empty('자료 연결을 확인한 뒤 다시 조회할 수 있습니다.')+'<button type="button" data-mi-retry>다시 조회</button>';}finally{if(ticket===st.ticket)st.loading=false;}
 }
 function mount(host,options){
  if(!host)return;for(const [node,observer] of observers)if(!node.isConnected){observer.disconnect();observers.delete(node);states.get(node)?.controller?.abort();}
  const currentYear=Number(options.asOf.slice(0,4));
  if(states.has(host)){const existing=states.get(host);existing.options={...options,baselineYears:existing.options.baselineYears,year:options.year||currentYear};host.querySelector('[data-mi-filter=year]').value=String(existing.options.year);host.querySelector('[data-mi-filter=region]').value=options.region||'';host.querySelector('[data-mi-filter=baseline_years]').value=String(existing.options.baselineYears||3);if(existing.started)load(host,existing);return;}
  const st={options:{...options,year:options.year||currentYear},ticket:0,calculated:false,cumulative:true,data:null};states.set(host,st);
  host.classList.add('housing-indicators');host.innerHTML='<header class="mi-section-heading"><div><small>주택시장·수급 비교</small><h2>'+(options.kind==='project'?'5. ':'')+(options.standalone?'지역여건':'공급 추진현황과 지역 여건')+'</h2><p class="mi-scope-label"></p></div></header><div class="mi-controls">'+(options.policies?'<label>정책<select data-mi-filter="policy" aria-label="지역 여건 정책 선택">'+options.policies.map(p=>'<option value="'+e(p.policy_id)+'" '+(p.policy_id===options.id?'selected':'')+' '+(p.policy_id!=='POL_2025_0907'?'disabled':'')+'>'+e(p.name)+(p.policy_id!=='POL_2025_0907'?' · 비활성':'')+'</option>').join('')+'</select></label>':'')+'<label>비교 지역<select data-mi-filter="region"><option value="">연결 범위 전체</option>'+capital.map(r=>'<option '+(options.region===r?'selected':'')+'>'+r+'</option>').join('')+'</select></label><label>시군구<select data-mi-filter="municipality_id"><option value="">시도 전체</option></select></label><label>예정·목표 연도<select data-mi-filter="year">'+Array.from({length:16},(_,i)=>currentYear-5+i).map(y=>'<option '+(y===st.options.year?'selected':'')+'>'+y+'</option>').join('')+'</select></label><label>평균 비교 기간<select data-mi-filter="baseline_years">'+[3,5,10].map(y=>'<option value="'+y+'">최근 '+y+'년</option>').join('')+'</select></label><p class="mi-status-line" role="status">아래 지표를 볼 때 자료를 조회합니다.</p></div><div class="mi-topics">'+topicLayout({...Object.fromEntries(titles.map((title,i)=>[i,'<article class="pr-card mi-card mi-placeholder"><header><h3>'+title+'</h3></header><div class="mi-empty">비교 자료 준비 중…</div></article>'])),...(options.includeHouseholds?{households:'<article class="pr-card mi-card mi-placeholder"><header><h3>1·2·3·4인 이상 가구 변화</h3></header><div class="mi-empty">비교 자료 준비 중…</div></article>'}:{})})+'</div>';
  host.addEventListener('change',event=>{const key=event.target.dataset.miFilter;if(!key)return;const value=event.target.value;if(key==='policy'){if(value!=='POL_2025_0907')return;st.options.id=value;st.options.region='';st.options.municipalityId='';host.querySelector('[data-mi-filter=region]').value='';host.querySelector('[data-mi-filter=municipality_id]').innerHTML='<option value="">시도 전체</option>';}if(key==='region'){st.options.region=value;st.options.municipalityId='';}if(key==='municipality_id')st.options.municipalityId=value;if(key==='year')st.options.year=Number(value);if(key==='baseline_years')st.options.baselineYears=Number(value);load(host,st);});
  host.addEventListener('click',event=>{const button=event.target.closest('[data-mi-housing],[data-mi-monthly],[data-mi-project],[data-mi-place],[data-mi-retry]');if(!button)return;if(button.hasAttribute('data-mi-retry')){load(host,st);return;}if(button.dataset.miProject){ProjectWorkspace.select(button.dataset.miProject);return;}if(button.dataset.miPlace){st.options.municipalityId=button.dataset.miPlace;load(host,st);return;}if(!st.data)return;if(button.dataset.miHousing)st.calculated=button.dataset.miHousing==='calculated';if(button.dataset.miMonthly)st.cumulative=button.dataset.miMonthly==='cumulative';render(host,st);});
  host.addEventListener('keydown',event=>{if((event.key==='Enter'||event.key===' ')&&event.target.hasAttribute('data-mi-place')){event.preventDefault();event.target.dispatchEvent(new MouseEvent('click',{bubbles:true}));}});
  const observer=new IntersectionObserver(entries=>{if(!entries.some(e=>e.isIntersecting))return;observer.disconnect();observers.delete(host);st.started=true;if(host.isConnected)load(host,st);},{rootMargin:'300px'});observers.set(host,observer);observer.observe(host);
 }
 function reportContext(){
  const host=document.getElementById('supply-conditions-report'),st=states.get(host);
  if(!st?.data||st.loading||!host.querySelector('[data-housing-indicator]'))throw Error('지역여건 조회가 끝난 뒤 다시 선택하세요.');
  const d=st.data;
  return {kind:'regional',root:host,scope:{policy_id:st.options.id,name:d.scope.name,region:st.options.region||'',municipality_id:d.scope.municipality_id||'',municipality:d.scope.municipality||'',year:d.scope.year,as_of_date:d.as_of_date,baseline_years:st.options.baselineYears||3,portfolio:!!st.options.portfolio,housing_mode:st.calculated?'calculated':'official',starts_mode:st.cumulative?'cumulative':'monthly'},
   data:JSON.parse(JSON.stringify({...d,places:d.places.map(({rings,...place})=>place)})),topics:JSON.parse(JSON.stringify(topics))};
 }
 return {mount,plot,priceCard,mapColor,map,reportContext};
})();

// This workspace owns market comparisons; management reports keep their operational charts.
const SupplyConditions=(()=>{
 let date='';
 function visible(){
  const asOf=$('as-of').value;if(date===asOf)return;date=asOf;
  HousingIndicators.mount($('supply-conditions-report'),{kind:'policy',id:'POL_2025_0907',asOf,standalone:true,includeHouseholds:true,policies:state.policies});
 }
 return {visible};
})();
