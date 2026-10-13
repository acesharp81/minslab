'use strict';
const CollectionLineage=(()=>{
 const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const num=v=>Number(v||0).toLocaleString('ko-KR');
 const groups=[
  {id:'policy',name:'정책 발표·후속 계획',sources:['policy_907','policy_907_plan','policy_129','policy_813','policy_history','urban_930'],fields:'정책 ID · 발표일 · 목표량',key:'policy',label:'정책 → 프로그램'},
  {id:'plans',name:'LH·SH·GH 공급계획',sources:['lh_sale','lh_rent','lh_incheon_sale','lh_incheon_rent','sh_supply_plan','gh_supply_plan'],fields:'시도명 · 지구/블록 · 공급 예정월',key:'block',label:'지구명 + 블록'},
  {id:'business',name:'정비사업·계획 고시',sources:['molit_renewal_inventory','sh_inventory','sh_redevelopment','seoul_plan_notice_pilot','gyeonggi_plan_notice_pilot'],fields:'지역 · 사업명 · 지정/승인 현황',key:'municipality',label:'지역명 · 사업명'},
  {id:'permit',name:'건축HUB 주택인허가',sources:['building_hub','building_hub_incheon','building_hub_details'],fields:'sigunguCd · bjdongCd · mgmHsrgstPk',key:'legal_dong',label:'법정동 코드 / 허가 PK'},
  {id:'construction',name:'건설·공정·준공 근거',sources:['lh_construction','lh_incheon_construction','lh_progress','lh_reit_progress','lh_completion_plan','building_register_recap','gh_completion_evidence'],fields:'공사명 · 지구/블록 · 착공일 · 공정률',key:'block',label:'블록 · 공사기록'},
  {id:'notice',name:'청약홈·LH·GH 모집공고',sources:['cheongyak','lh_notice','lh_notice_detail','gh_notice'],fields:'지구·블록 · 공고일 · 유형별 입주 예정월',key:'notice',label:'블록 · 주택관리번호'},
  {id:'move',name:'LH 연간 입주계획',sources:['lh_movein_history','lh_stock'],fields:'지구/블록 · 입주 예정월',key:'block',label:'블록 + 예정월'},
  {id:'document',name:'공식 고시·공모·일정 문서',sources:['official_document'],fields:'지구·블록 · 사건일 · 전체/부분 호수',key:'block',label:'검증 문서 → 단계 근거'},
  {id:'officer',name:'담당자 목표·실적 기록',sources:['officer','manual_delivery'],fields:'사업 ID · 단계 · 목표일 · 관측일',key:'project',label:'사업 ID로 저장'}
 ];
 const chains={
  ALL:['region','municipality','legal_dong','pnu','block','project'],
  POLICY:['policy','program','project','target','due','actual'],
  BUSINESS:['region','municipality','block','project','target','due'],
  APPROVAL:['region','legal_dong','pnu','permit','project','actual'],
  CONSTRUCTION:['block','project','start','progress','completion','due'],
  SUPPLY:['region','block','project','notice','supply','due'],
  MOVE_IN:['block','project','move_plan','completion','move_actual','actual']
 };
 const keyNotes={region:'지역명 · 행정코드와 구분',municipality:'이름 표준화·코드 대조',legal_dong:'시군구 5자리 + 법정동 5자리',pnu:'법정동 + 산 여부 + 본번·부번',block:'같은 지구의 블록만 비교',project:'HOME 내부 사업 기록 식별자',policy:'발표 정책별 식별자',program:'저장된 정책–프로그램 연결',permit:'mgmHsrgstPk · 원천 허가 PK',notice:'HOUSE_MANAGE_NO',start:'실제 착공일 · 예정일 제외',progress:'원천 공정률 0~100%',completion:'실제 준공일 근거',supply:'본 모집공고일',move_plan:'예정일 · 실제 시작과 구분',move_actual:'실제 입주 시작일 근거',target:'사업 계획량 · 단계별 목표 별도',due:'원천 예정·담당자 목표일',actual:'실적 관측일 · 같은 단계 대조'};
 const transforms={
  'region:municipality':['지역명 표준화','지역명 → 행정코드 검토','review'],
  'municipality:legal_dong':['코드 교차표 필요','이름만으로 10자리 코드를 확정하지 않음','planned'],
  'region:legal_dong':['지역·법정동 조회','허가 원천의 조회 코드','review'],
  'legal_dong:pnu':['본번·부번 결합','원천 산 여부·지번과 공식 법정동 코드 대조; 저장된 후보는 사업 동일성 검토 필요','review'],
  'pnu:block':['필지 ↔ 블록 경계','토지 경계와 대지 필지 교차 확인','planned'],
  'block:project':['지구·블록 후보 연결','저장된 연결의 동일 사업 여부 검토','review'],
  'policy:program':['정책 연결 DB','담당자 확인 필요 연결 포함','review'],
  'program:project':['프로그램 연결 DB','담당자 확인 필요 연결 포함','review'],
  'project:notice':['저장된 공고 연결','공고 중복·재공고·공급 유형 검토','review'],
  'notice:supply':['공고일 추출','입주가 아닌 공급 단계의 관측일','connected'],
  'project:move_plan':['입주 예정 연결','원천 예정월을 유지','review'],
  'move_plan:completion':['준공 근거 대조','예정월만으로 준공을 확정하지 않음','planned'],
  'completion:move_actual':['시작일 추가 확인','준공으로 실제 입주를 대체하지 않음','planned']
 };
 function render({host,detailHost,data,rows,stage,projectName}){
  const labels={...data.lineage.key_labels,project:'HOME 사업 ID'};const chain=chains[stage]||chains.ALL,total=rows.length,inspect={};
  const keys=p=>stage==='ALL'?p.lineage?.keys||{}:p.lineage?.stage_keys?.[stage]||{};
  const count=k=>rows.filter(p=>keys(p)[k]!=null).length;
  const has=p=>stage==='ALL'?Object.values(p.cells).flatMap(c=>c.sources):p.cells[stage].sources;
  const countSource=sources=>rows.filter(p=>sources.some(s=>stage==='ALL'&&p.lineage?.sources[s]?.base||has(p).some(e=>e.source_id===s))).length;
  const allSources=data.lineage.sources||{};
  const covered=new Set(groups.flatMap(g=>g.sources));
  const extraSources=Object.keys(allSources).filter(s=>!covered.has(s)&&countSource([s])>0);
  const availableGroups=extraSources.length?[...groups,{id:'other',name:'기타 연결된 원천',sources:extraSources,fields:'저장된 사업·단계별 원천 키',key:'project',label:'DB 사업 연결'}]:groups;
  const sourceGroups=availableGroups.filter(g=>stage==='ALL'||(data.diagram.find(d=>d.stage===stage)?.sources||[]).some(s=>g.sources.includes(s.id))||countSource(g.sources)>0);
  const descriptors=sourceGroups.map(g=>{const connected=countSource(g.sources),known=g.sources.filter(s=>allSources[s]?.record_count>0||s==='officer'&&connected);return {...g,connected,known};});
  let svg='',edges='',cards='';
  const text=(x,y,value,cls='')=>'<text x="'+x+'" y="'+y+'" class="'+cls+'">'+escape(value)+'</text>';
  const rect=(x,y,w,h,cls='')=>'<rect x="'+x+'" y="'+y+'" width="'+w+'" height="'+h+'" rx="8" class="'+cls+'"/>';
  const node=(id,x,y,w,h,title,lines,cls='',badge='')=>{
   cards+='<g data-cl-node="'+id+'" role="button" tabindex="0" aria-label="'+escape(title+' · 상세 보기')+'">'+rect(x,y,w,h,cls)+text(x+14,y+24,title,'cl-node-title').replace('<text ','<text data-cl-width="'+(w-28-(badge?55:0))+'" ')+lines.map((l,i)=>text(x+14,y+42+i*16,l,i===0?'cl-node-sub':'cl-node-muted').replace('<text ','<text '+(id.startsWith('source-')&&i===2?'data-cl-repair-count="true" role="button" tabindex="0" aria-label="오류·조치 건수 펼치기" ':'')+'data-cl-width="'+(w-28)+'" ')).join('')+(badge?text(x+w-12,y+22,badge,'cl-method'):'')+'</g>';
  };
  function edge(id,x1,y1,x2,y2,label,status,info,lx,ly){
   inspect[id]={title:label,lines:[info,'표시 상태: '+({connected:'필드/저장 연결 있음',review:'후보·추정 또는 동일성 검토',missing:'필드/연결 근거 없음',planned:'보완 경로 · 연결 완료 아님'})[status]]};
   edges+='<g data-cl-node="'+id+'" role="button" tabindex="0" aria-label="'+escape(label)+'"><path d="M'+x1+','+y1+' L'+x2+','+y2+'" class="cl-edge cl-'+status+'" marker-end="url(#cl-arrow-'+status+')"/><path d="M'+x1+','+y1+' L'+x2+','+y2+'" class="cl-edge-hit"/>'+text(lx??(x1+x2)/2,ly??(y1+y2)/2-6,label,'cl-edge-label cl-label-'+status)+'</g>';
  }
  const positions=Object.fromEntries(chain.map((k,i)=>[k,{x:526,y:126+i*121,w:218,h:68}]));
  const yOf=k=>(positions[k]||positions.project||positions[chain.at(-1)]).y+34;
  const chooseKey=g=>stage==='ALL'?({policy:'region',plans:'region',business:'municipality',permit:'legal_dong',construction:'block',notice:'project',move:'block',officer:'project'}[g.id]||'project'):chain.includes(g.key)?g.key:chain.includes('project')?'project':chain[0];
  svg+=text(20,31,'지금 가진 자료 · 수집 원천','cl-heading')+text(543,31,'연결 고리 · 실제 확보 필드','cl-heading')+text(902,31,'추가 확보·연결 보완 자료','cl-heading cl-gold');
  svg+=text(20,53,'원천 수집 여부와 선택 사업 연결을 함께 확인','cl-muted')+text(902,53,'노란 경로는 보완 방법 · 이미 확보한 원천도 포함','cl-muted');
  descriptors.forEach((g,i)=>{
   const y=85+i*(descriptors.length>8?87:96),target=chooseKey(g),sids=g.sources.filter(s=>allSources[s]),methods=[...new Set(sids.map(s=>allSources[s].method))].join('·')||'내부';
   const names=g.known.slice(0,2).map(s=>s==='officer'?'담당자 입력':(data.diagram.flatMap(d=>d.sources).find(r=>r.id===s)?.name||allSources[s]?.name||s));
   const inferred=rows.some(p=>has(p).some(e=>g.sources.includes(e.source_id)&&['PREREQUISITE','STAGE_INFERENCE'].includes(e.method)));
   const review=rows.some(p=>has(p).some(e=>g.sources.includes(e.source_id)&&e.review_status==='REVIEW'));
   const matchedFields=rows.filter(p=>g.sources.some(s=>p.lineage?.sources[s]?.keys[target]!=null)).length;
   const status=!g.connected?'missing':inferred||review||!matchedFields?'review':'connected';
   const edgeLabel=!g.connected?'사업 연결 없음 ×':inferred?'선행 단계 추정':stage==='ALL'&&g.id==='policy'?'정책 적용 지역':stage==='ALL'&&g.id==='plans'?'시도명 · 지구명':g.label;
   node('source-'+g.id,20,y,335,81,g.name,[names.join(' · ')||'선택 범위의 저장 연결 없음',g.fields,'연결 '+num(g.connected)+' / '+num(total)+'개 · 조치 '+CollectionRepairs.relevant(data,rows,stage,g.sources).length+'건'],g.connected?'cl-source':'cl-source-missing',methods);
   inspect['source-'+g.id]={title:g.name,sources:g.sources,lines:['수집된 원천: '+(g.known.map(s=>allSources[s]?.name||'담당자 입력').join(' / ')||'확인 필요'),'연결에 사용하는 필드: '+g.fields,'선택 범위에서 저장 자료를 가진 사업: '+num(g.connected)+'개',inferred?'착공·진척으로 선행 단계를 추정한 근거 포함 · 허가 원문 확보와 구분':'사업명·지구·블록 후보는 담당자 확인 필요','연결키 확보: '+(matchedFields?labels[target]+' '+num(matchedFields)+'개 사업':'이 경로의 연결키 추가 확인 필요')]};
   edge('source-edge-'+g.id,355,y+41,526,yOf(target),edgeLabel,status,g.fields+' → '+labels[target]+'; '+(inferred?'추정 근거임':g.connected?'선택 범위 DB 연결 참조':'원천이 있어도 해당 사업의 연결 근거가 없음'),432,y+32);
  });
  chain.forEach((k,i)=>{
   const p=positions[k],available=count(k);node('key-'+k,p.x,p.y,p.w,p.h,labels[k],[num(available)+' / '+num(total)+'개 사업에 필드 있음',keyNotes[k]],available?'cl-key':'cl-key-missing');
   const examples=rows.filter(r=>keys(r)[k]!=null).slice(0,3).map(r=>r.name+' → '+keys(r)[k]);
   inspect['key-'+k]={title:labels[k],keys:[k],lines:[keyNotes[k],num(available)+'개 확보 / '+num(total-available)+'개 미확보',...examples,'필드가 있다는 사실과 다른 자료와의 결합이 검증됐다는 사실은 구분합니다.']};
   if(k==='pnu'){const pending=rows.filter(r=>r.parcel_identity?.status==='CANDIDATE');inspect['key-'+k].lines.push('구성된 PNU 후보 '+num(pending.length)+'개 사업 · 필지/사업 동일성 확정 전',...rows.filter(r=>r.parcel_identity).slice(0,20).map(r=>r.name+' · '+(r.parcel_identity.pnus?.join(' / ')||'지번 구성 보류')+' · '+(r.parcel_identity.missing_reason_labels||[]).join(', ')+' · '+r.parcel_identity.basis));}
   if(i<chain.length-1){const next=chain[i+1],t=transforms[k+':'+next]||['같은 사업의 기록 대조','서로 다른 단계·시점의 자료를 사업 ID로 대조','review'];const status=!available||!count(next)?'missing':t[2];
    edge('key-edge-'+k,635,p.y+68,635,positions[next].y,t[0]+(status==='missing'?' ×':''),status,t[1],635,p.y+101);inspect['key-edge-'+k].keys=[k,next];
   }
  });
  const supplemental=[
   {id:'codes',name:'법정동 코드·행정구역 대조',sources:['legal_dongs','incheon_legal_dongs'],target:'legal_dong',fields:'시군구 5자리 + 법정동 5자리',action:'이름 → 코드',note:'행정명 변경·폐지 코드·지역 범위 확인'},
   {id:'hub',name:'건축HUB 인허가·동별 자료',sources:['building_hub','building_hub_incheon','building_hub_details'],target:'permit',fields:'mgmHsrgstPk · 허가일 · 착공일',action:'허가 PK 대조',note:'남은 법정동 수집 및 사업 동일성 검토'},
   {id:'parcel',name:'대지위치·총괄표제부',sources:['building_hub_details','building_register_recap'],target:'pnu',fields:'법정동 · 산 여부 · 본번/부번',action:'필지 PNU 구성',note:'19자리 PNU 결합과 합필 관계 검증 필요'},
   {id:'boundary',name:'공공주택지구 경계·블록',sources:['vworld_district','lh_block_location'],target:'block',fields:'지구명 · 블록 · 필지/경계',action:'경계·블록 교차',note:'용지 경계와 법정 사업 경계의 의미 구분'},
   {id:'identity',name:'사업 식별자·별칭 검토',sources:[],target:'project',fields:'원천 사업번호 ↔ HOME 사업 ID',action:'동일 사업 확인',note:'저장된 후보 연결을 담당자가 확인·조정'},
   {id:'goal',name:'단계별 목표·기준 일정',sources:[],target:'due',fields:'사업·단계 · 목표량 · 목표일',action:'목표·기한 입력',note:'발표 자료 또는 담당자 확인 근거로 입력'},
   {id:'occupancy',name:'기관별 입주 시작 확인',sources:[],target:'move_actual',fields:'실제 시작일 · 사업/단지 식별자',action:'실제일 확인',note:'입주 예정월·준공일만으로 실제 시작을 확정하지 않음'},
   {id:'geo',name:'주소·좌표 교차 검증',sources:['vworld'],target:'project',fields:'도로명/지번 주소 → 좌표',action:'사업 위치 대조',note:'사업 자체 좌표와 시군구 대표점을 구분'}
  ];
  supplemental.forEach((s,i)=>{
   const y=85+i*96,target=chain.includes(s.target)?s.target:s.target==='permit'&&chain.includes('legal_dong')?'legal_dong':'project',targetKey=positions[target]?target:chain.at(-1),sources=s.sources.map(id=>allSources[id]).filter(Boolean),acquired=sources.filter(s=>s.record_count>0),method=s.sources.length?[...new Set(sources.map(s=>s.method))].join('·')||'자료':'내부';
   const ready=s.sources.length?(acquired.length?'원천 '+acquired.length+'종 확보 · 사업 연결 보완':'원천 확보·조회 범위 확인'):'담당자 확인·자료 입력';
   node('extra-'+s.id,900,y,340,81,s.name,[s.fields,ready,s.note], 'cl-extra',method);
   inspect['extra-'+s.id]={title:s.name,keys:s.id==='parcel'?['pnu']:null,sources:s.sources.length?s.sources:null,lines:['보완 목적: '+s.action,s.fields,s.note,...sources.map(r=>r.name+' · 저장 '+num(r.record_count)+'행 · '+(r.status==='FAILED'?'최근 수집 실패':r.record_count?'수집 이력 있음':'미수집')),'수집된 행 수는 정책 주택 수나 사업 연결 완료 수가 아닙니다.']};
   edge('extra-edge-'+s.id,900,y+41,744,yOf(targetKey),s.action,'planned',s.note,819,y+32);
  });
  const bottom=Math.max(885,85+descriptors.length*(descriptors.length>8?87:96)+15);
  edges+='<path d="M635 '+(positions[chain.at(-1)].y+68)+' V'+bottom+' H165 M635 '+bottom+' H1098" class="cl-edge cl-connected"/>';
  const dated=rows.filter(p=>has(p).some(e=>e.date)),comparable=rows.filter(p=>(stage==='ALL'?Object.values(p.cells):[p.cells[stage]]).some(c=>c.plan_available&&c.actual_available)),baseline=rows.filter(p=>(p.lineage?.baseline_stages||[]).some(s=>stage==='ALL'||s===stage));
  const outputs=[
   {id:'flow',title:'① 연도별 추진 현황',a:'일자 근거 '+num(dated.length)+' / '+num(total)+'개',b:'예정·실적·추정 구분 후 시계열',lines:['정책 → 사업화 → 인허가 → 건설 → 공급 → 입주','실제 사건일·관측일·예정일을 분리합니다.','날짜가 없는 단계를 균등 배분하지 않습니다.']},
   {id:'comparison',title:'② 계획 대비 실적',a:'같은 단계 계획·관측 '+num(comparable.length)+'개',b:'기간·물량 단위 일치 추가 검토',lines:['같은 사업·단계에서 계획과 실제 관측이 함께 있어야 비교 후보가 됩니다.','목표량·관측량·누적 기준이 같아야 달성률을 계산합니다.']},
   {id:'delay',title:'③ 지연·병목 추적',a:'승인 기준 일정 '+num(baseline.length)+'개 사업',b:'기준일·목표·관측 부족 시 판정 대기',lines:['처음 승인한 기한과 변경된 기한을 보존합니다.','관측 근거 없이 실적 0 또는 지연 호수를 생성하지 않습니다.','책임기관·조치기한은 일정·병목 관리에서 입력합니다.']},
   {id:'map',title:'④ 지도·지역 분석',a:'지역명 '+num(count('region'))+' · 자체 좌표 '+num(count('coordinates'))+'개',b:'지역 집계 ↔ 개별 사업 위치 구분',lines:['시도·시군구 그래프는 지역 귀속 정보를 이용합니다.','사업 자체 좌표가 없으면 주소·블록·공간 원천으로 보완합니다.','이 수치는 원본 사업/선택된 근거의 좌표 보유 수입니다. 지도에서 보완한 대표 위치 수와는 다릅니다.']}
  ];
  outputs.forEach((o,i)=>{const x=20+i*311;edge('output-edge-'+o.id,x+145,bottom,x+145,bottom+29,'','connected','연결된 자료로 분석 가능 범위를 판단합니다.');node('output-'+o.id,x,bottom+29,292,86,o.title,[o.a,o.b],'cl-output');inspect['output-'+o.id]={title:o.title,lines:[o.a,...o.lines]};});
  const markers=['connected','review','missing','planned'].map(s=>'<marker id="cl-arrow-'+s+'" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0L7 3.5L0 7" class="cl-arrow-'+s+'"/></marker>').join('');
  host.innerHTML='<svg class="cl-graph" viewBox="0 0 1260 '+(bottom+135)+'" role="group" aria-label="'+escape((projectName||'조회 사업')+' 필드와 연결 단절·보완 경로 다이어그램')+'"><defs>'+markers+'</defs>'+svg+edges+cards+'</svg>';
  // Read layout once, then measure candidates off-DOM. Alternating text writes
  // and SVG geometry reads here used to force hundreds of page layouts.
  const canvas=document.createElement('canvas').getContext('2d');
  const labelsToFit=[...host.querySelectorAll('text[data-cl-width]')].map(t=>{
    const style=getComputedStyle(t);return {t,full:t.textContent,max:Number(t.dataset.clWidth),width:t.getComputedTextLength(),font:`${style.fontWeight} ${style.fontSize} ${style.fontFamily}`};
  });
  for(const {t,full,max,width,font} of labelsToFit){
    if(width<=max||!canvas)continue;canvas.font=font;
    const scale=width/Math.max(1,canvas.measureText(full).width);let lo=0,hi=full.length;
    while(lo<hi){const mid=Math.ceil((lo+hi)/2);if(canvas.measureText(full.slice(0,mid)+'…').width*scale>max)hi=mid-1;else lo=mid;}
    t.textContent=full.slice(0,lo)+'…';
  }
  detailHost.innerHTML='<p class="cl-help">상자 또는 화살표를 선택하면 실제 필드 예시, 연결 근거와 보완 방법을 볼 수 있습니다. '+escape(data.lineage.note)+'</p>'+CollectionRepairs.html(data,rows,stage);
  function activate(target){const node=target.closest('[data-cl-node]');if(!node)return;host.querySelectorAll('.cl-active').forEach(n=>n.classList.remove('cl-active'));node.classList.add('cl-active');const info=inspect[node.dataset.clNode];if(info){host.dataset.activeNode=node.dataset.clNode;detailHost.innerHTML='<article class="cl-inspector" role="status"><strong>'+escape(info.title)+'</strong><ul>'+info.lines.filter(Boolean).map(t=>'<li>'+escape(t)+'</li>').join('')+'</ul></article>'+CollectionRepairs.html(data,rows,stage,info.sources,info.keys);if(target.closest('[data-cl-repair-count]')){const history=detailHost.querySelector('.pc-repair-overview');if(history){history.open=true;history.querySelector('summary').focus({preventScroll:true});history.scrollIntoView({behavior:'smooth',block:'nearest'});}}}}
  const active=host.querySelector('[data-cl-node="'+CSS.escape(host.dataset.activeNode||'')+'"]');if(active)activate(active);
  host.onclick=event=>activate(event.target);host.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();activate(event.target);}};
 }
 return {render};
})();
