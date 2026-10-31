 'use strict';
const AICollection=(()=>{
 let timer=null,clockTimer=null,snapshot=null,root=null,selected='collection',filter='HOLD',inbox=null,loading=false;
 const e=v=>esc(v??''),dollars=v=>'$'+Number(v||0).toFixed(4),n=v=>Number(v||0).toLocaleString('ko-KR');
 const names={QUEUED:'실행 대기',RUNNING:'처리 중',STOPPING:'중지 중',CANCELLED:'중지됨',COMPLETED:'완료',PARTIAL:'일부 확인 필요',BUDGET_PAUSED:'한도 대기',FAILED:'실패',INTERRUPTED:'중단'};
 const roles=['algorithm','collection','officer'];
 const descriptions={algorithm:'수집 실패를 진단하고 추출 규칙 개선안을 기록합니다. 규칙 변경은 검증·반영 대기로 남깁니다.',collection:'공식 출처·뉴스를 탐색하고 원문, 사업명, 일정, 물량을 추출합니다. 모호한 자료는 보류합니다.',officer:'공식 원문과 사업명·독립 식별정보를 대조해 검증된 자료를 연결합니다. 단계·실적 제안은 보류합니다.'};
 const base='/poc/home/api/ai-agents/holds.csv?role=';
 async function mount(el){
  clearTimeout(timer);clearInterval(clockTimer);root=el;if(!root)return;
  root.innerHTML='<details class="ai-collection"><summary><span>AI 작업자 · 알고리즘 / 수집 / 업무담당</span><small>PoC7·10·11 공통 사용량</small></summary><div class="ai-panel"><p>설정을 불러오고 있습니다…</p></div></details>';
  try{snapshot=await request('/ai-agents');if(!el.isConnected)return;draw();}catch(err){el.querySelector('.ai-panel').textContent=err.message;}
 }
 function options(role,current,review=false){return snapshot.models.filter(m=>m.roles.includes(role)&&(!review||['gpt-5.4','gpt-6.1-terra'].includes(m.id))).map(m=>`<option value="${e(m.id)}" ${m.id===current?'selected':''} ${m.configured?'':'disabled'}>${e(m.label)}${m.configured?'':' · 연결 설정 필요'}</option>`).join('');}
 function draw(){
  root.querySelector('.ai-panel').innerHTML=`<section class="ai-shared-budget" data-ai-shared></section><div class="ai-agent-toolbar"><p>자동 일괄 작업은 한국시간 01:00~05:00에 실행합니다. 각 작업자를 선택하면 처리 결과·보류 사유·근거를 확인할 수 있습니다.</p><a class="button secondary" href="${base}all">수집 + 업무담당 판단보류 CSV</a></div>
   <div class="ai-workers-grid ai-three-workers">${roles.map((role,i)=>`<button type="button" class="ai-worker-card ai-agent-select ${role===selected?'is-selected':''}" data-agent="${role}" aria-pressed="${role===selected}"><span class="ai-worker-top"><span class="ai-worker-number">0${i+1}</span><span data-role-state="${role}"></span></span><span class="ai-worker-title"><strong>${e(snapshot.roles[role])}</strong><span data-role-hour="${role}"></span></span><span class="ai-worker-description">${e(descriptions[role])}</span><span class="ai-agent-model" data-role-model="${role}"></span></button>`).join('')}</div>
   <section class="ai-agent-console"><div data-agent-form></div><div data-ai-progress aria-live="polite"></div><p data-ai-message role="status"></p><div data-agent-results></div><details class="ai-settings"><summary>공통 수집 범위·호출량 설정</summary><div data-common-settings></div></details><details class="ai-runs"><summary>선택한 작업자의 실행 이력</summary><div data-agent-history></div><div data-agent-economics></div></details></section>`;
  root.querySelectorAll('[data-agent]').forEach(button=>button.onclick=()=>selectRole(button.dataset.agent));
  commonSettings();render();roleForm();root.querySelector(".ai-collection").addEventListener("toggle",()=>{if(root.querySelector(".ai-collection").open&&!inbox)loadItems();});schedule();
 }
 function roleForm(){
  const c=snapshot.agents[selected];
  root.querySelector('[data-agent-form]').innerHTML=`<h3>${e(snapshot.roles[selected])}</h3><form class="ai-agent-form"><fieldset ${state.admin?'':'disabled'}><div class="ai-grid"><label>역할 1 · ${selected==='algorithm'?'실패 진단·규칙 제안':selected==='collection'?'탐색 자료 분석':'근거 대조·연결 판단'}<select name="model">${options(selected,c.model)}</select></label><label data-review-choice>역할 2 · 필요한 건만 정밀 검토<select name="review_model"><option value="">사용 안 함 · 단일 모델</option>${options('collection',c.review_model,true)}</select></label><label>예약<select name="enabled"><option value="false">예약 끔</option><option value="true">매일 실행</option></select></label><label>예약 · 한국시간 01~05시<select name="hour_kst">${Array.from({length:4},(_,j)=>{const i=j+1;return `<option value="${i}">${String(i).padStart(2,'0')}:00</option>`;}).join('')}</select></label></div><p class="ai-budget-note">기본은 단일 모델입니다. mini/Nemotron 수집만 모호한 건을 정밀 모델에 보낼 수 있습니다. 정밀 검토 비중이 높으면 비용이 늘 수 있습니다. Solar 무제한 혜택은 경제성 판단에 포함하지 않습니다.</p><button class="button secondary" type="submit">작업자 설정 저장</button></fieldset></form><div class="ai-actions"><button class="button primary" data-agent-run ${state.admin?'':'disabled'}>지금 실행</button><button class="button secondary" data-ai-refresh>결과·사용량 새로고침</button>${selected!=='algorithm'?`<a class="button secondary" href="${base+selected}">판단보류 CSV</a>`:''}</div>`;
  const form=root.querySelector('.ai-agent-form');form.elements.enabled.value=String(c.enabled);form.elements.hour_kst.value=String(c.hour_kst);
  function secondary(){const allowed=selected==='collection'&&['gpt-5.4-mini','nvidia/nemotron-3.5-super-vl:free'].includes(form.elements.model.value);form.querySelector('[data-review-choice]').hidden=!allowed;if(!allowed)form.elements.review_model.value='';}
  form.elements.model.onchange=secondary;secondary();
  form.onsubmit=async ev=>{ev.preventDefault();const d=new FormData(form);await action(async()=>{const saved=await request('/admin/ai-agents/'+selected+'/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:d.get('model'),review_model:d.get('review_model')||'',enabled:d.get('enabled')==='true',hour_kst:Number(d.get('hour_kst')),version:c.version})});snapshot.agents[selected]=saved;c.version=saved.version;},'설정을 저장했습니다.');};
  root.querySelector('[data-agent-run]').onclick=()=>action(()=>request('/admin/ai-agents/'+selected+'/runs',{method:'POST'}),'실행 요청을 등록했습니다.');
  root.querySelector('[data-ai-refresh]').onclick=async()=>{await refresh();await loadItems();};
  activeButtons();
 }
 function commonSettings(){
  const s=snapshot.settings,fields=[['max_documents','한 번에 처리할 자료',1,100],['daily_usd','일 비용 상한 · USD',.01,20],['monthly_usd','월 비용 상한 · USD',.01,100]];
  root.querySelector('[data-common-settings]').innerHTML=`<form class="ai-common-form"><fieldset ${state.admin?'':'disabled'}><div class="ai-grid">${fields.map(([k,label,min,max])=>`<label>${label}<input name="${k}" type="number" min="${min}" max="${max}" step="${k==='max_documents'?1:.01}" value="${s[k]}" required></label>`).join('')}</div><label>추가 뉴스 탐색<select name="search_enabled"><option value="true">사용</option><option value="false">사용 안 함</option></select></label><label>추가 검색어 · 최대 5개<textarea name="queries" rows="3">${e(s.queries.join('\n'))}</textarea></label><label>추가 원문 URL · 최대 20개<textarea name="seed_urls" rows="3">${e(s.seed_urls.join('\n'))}</textarea></label><p>자료 수·비용 상한은 세 작업자가 공유합니다. 현재 Solar는 비용 상한 없이 사용량·유료 단가 추정액만 기록합니다. 유료 키 전환 시 공통 예산 설정을 함께 변경해야 합니다.</p><button type="submit" class="button secondary">공통 설정 저장</button></fieldset></form>`;
  const f=root.querySelector('.ai-common-form');f.elements.search_enabled.value=String(s.search_enabled);
  f.onsubmit=async ev=>{ev.preventDefault();const d=new FormData(f),value={...s,hour_kst:s.hour_kst>=1&&s.hour_kst<5?s.hour_kst:2};for(const [k,v] of d)value[k]=['queries','seed_urls'].includes(k)?String(v).split('\n').map(x=>x.trim()).filter(Boolean):k==='search_enabled'?v==='true':Number(v);await action(async()=>{const saved=await request('/admin/ai-collection/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});s.version=saved.version;},'공통 설정을 저장했습니다.');};
 }
 async function selectRole(role){selected=role;inbox=null;root.querySelectorAll('[data-agent]').forEach(b=>{b.classList.toggle('is-selected',b.dataset.agent===role);b.setAttribute('aria-pressed',String(b.dataset.agent===role));});roleForm();render();await loadItems();}
 async function loadItems(){const role=selected,target=root.querySelector('[data-agent-results]');target.innerHTML='<p>처리 결과를 확인하고 있습니다…</p>';try{const value=await request('/ai-agents/'+role+'/items');if(role!==selected||!root?.isConnected)return;inbox=value;renderItems();}catch(err){if(role===selected)target.textContent=err.message;}}
 function renderItems(){
  if(!inbox)return;const rows=inbox.items.filter(r=>r.state===filter);
  root.querySelector('[data-agent-results]').innerHTML=`<div class="ai-result-tabs"><button type="button" data-result-state="HOLD" aria-pressed="${filter==='HOLD'}">판단보류 · 사람 개입 필요 ${n(inbox.held)}</button><button type="button" data-result-state="DONE" aria-pressed="${filter==='DONE'}">처리 완료 ${n(inbox.done)}</button></div><div class="ai-result-list">${rows.map(r=>`<details><summary><strong>${e(r.title||r.subject)}</strong><span>${e(r.stage)}</span></summary><p><b>${e(r.reason)}</b></p><p>${e(r.action)}</p>${r.business_status_label?`<p><b>현재 업무판단 · ${e(r.business_status_label)}</b></p><p>${e(r.business_reason||"판단 기록 없음")}</p>`:""}<p>${e(r.model||'기존 담당자 기록')} · 판본 ${e(r.source_revision_no??'—')}</p>${/^https?:\/\//i.test(r.url||'')?`<a href="${e(r.url)}" target="_blank" rel="noopener noreferrer">원문 근거 열기 ↗</a>`:''}${(r.evidence||[]).map(q=>`<blockquote>${e(q)}</blockquote>`).join('')}<pre>${e(JSON.stringify(r.result||{},null,2))}</pre>${r.body_text?`<details><summary>수집 본문 · ${e(r.body_origin||"AI 수집")}</summary><pre>${e(r.body_text)}</pre></details>`:''}</details>`).join('')||'<p class="ai-empty">이 분류에 해당하는 결과가 없습니다. 아직 실행하지 않은 작업자는 처리 이력이 없습니다.</p>'}</div>`;
  root.querySelectorAll('[data-result-state]').forEach(b=>b.onclick=()=>{filter=b.dataset.resultState;renderItems();});
 }
 function quota(){
  const panel=root.querySelector('[data-ai-shared]'),opened=panel.querySelector('details')?.open,cards=snapshot.shared_budget?.models||[];
  const groups=[['OpenAI · 일일',['gpt-5.4-mini','gpt-5.4']],['OpenAI · 공용 크레딧',['openai-shared']],['OpenRouter · 일일',['openrouter']],['Solar · 사용량',['solar-pro4']]],aliases={'gpt-5.4-mini':'5.4 mini','gpt-5.4':'5.4','openai-shared':'6.1 Terra 등','openrouter':'Nemotron','solar-pro4':'Solar Pro 4'};
  const fmt=(m,v)=>m.unit==='USD'?'$'+Number(v||0).toFixed(2):Number(v||0)>=10000?(Math.floor(v/1000)/10)+'만':n(v);
  panel.innerHTML=`<details class="ai-quota-detail" ${opened?'open':''}><summary>${groups.map(([title,ids])=>`<span class="ai-quota-group"><b class="ai-quota-heading">${title}</b>${ids.map(id=>{const m=cards.find(x=>x.id===id),unlimited=m?.status==='UNLIMITED',known=m?.remaining!=null&&m.limit>0,percent=known?Math.min(100,Math.max(0,100*m.remaining/m.limit)):0;return `<span class="ai-quota-row ${known&&percent<10?'low':''}"><span>${aliases[id]}</span><strong>${unlimited?'무제한':known?percent.toFixed(1)+'%':'미확인'}</strong><span class="ai-quota-amount">${unlimited?'사용 '+n((m.input_tokens||0)+(m.output_tokens||0))+' 토큰':known?'잔여 '+fmt(m,m.remaining)+' / '+fmt(m,m.limit):'공통 원장 확인 필요'}</span>${unlimited?'':`<span class="ai-shared-meter ${known?'':'unknown'}" role="${known?'progressbar':'img'}" aria-label="${aliases[id]} 잔여량" ${known?`aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent.toFixed(1)}"`:''}><i data-quota-fill="${percent}"></i></span>`}</span>`;}).join('')}</span>`).join('')}</summary><div class="ai-quota-info"><b>PoC7 · PoC10 · PoC11 공용 원장</b>${cards.map(m=>`<p><b>${e(m.label)}</b> · 사용 ${fmt(m,m.used)}${m.unit==='USD'?' (표준 단가 환산, 실제 청구액 아님)':''} · 예약/미확정 ${fmt(m,(m.reserved||0)+(m.unknown||0))}<br>${m.status==='UNLIMITED'?'현재 무제한 키 · 유료 운영 경제성과 별개 · 호출 '+n(m.request_count)+'회':m.expires_at?e(new Date(m.expires_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}))+' 초기화/기간 종료':'초기화 정보 없음'}${m.official_limit?' · 공급자 한도 '+n(m.official_limit)+'회, 안전 여유를 뺀 운영 한도 표시':''}</p>`).join('')}<p>${e(snapshot.shared_budget?.error||'각 모델의 한도는 해당 그룹의 다른 모델·프로젝트와 공유됩니다. 같은 크레딧을 모델별로 중복 지급하지 않습니다.')}</p></div></details>`;
  panel.querySelectorAll('[data-quota-fill]').forEach(x=>x.style.width=x.dataset.quotaFill+'%');
 }
 function activeButtons(){const b=root.querySelector('[data-agent-run]');if(b)b.disabled=!state.admin||snapshot.runs.some(r=>['QUEUED','RUNNING','STOPPING'].includes(r.status));}
 function render(){
  quota();for(const role of roles){const c=snapshot.agents[role];root.querySelector(`[data-role-state="${role}"]`).textContent=c.enabled?'매일 예약':'직접 실행';root.querySelector(`[data-role-hour="${role}"]`).textContent=String(c.hour_kst).padStart(2,'0')+':00';root.querySelector(`[data-role-model="${role}"]`).textContent=(snapshot.models.find(m=>m.id===c.model)?.label||c.model)+(c.review_model?' → 필요 시 '+(snapshot.models.find(m=>m.id===c.review_model)?.label||c.review_model):'');}
  renderProgress();activeButtons();
  const history=root.querySelector('[data-agent-history]');history.innerHTML=snapshot.runs.filter(r=>(r.config.agent_role||'collection')===selected).map(r=>`<p><b>${e(names[r.status]||r.status)}</b> · ${e(new Date(r.created*1000).toLocaleString('ko-KR'))} · ${e(r.config.selected_model||r.config.profile)} · 유료 단가 추정 ${dollars(r.cost_usd)}${r.error?' · '+e(r.error):''}</p>`).join('')||'<p>실행 이력이 없습니다.</p>';
  const econ=root.querySelector('[data-agent-economics]');econ.innerHTML=selected==='collection'?(snapshot.economics||[]).map(x=>`<p>분할 운영 추정: 1차 ${n(x.first_calls)}회 / 정밀 ${n(x.review_calls)}회 · ${dollars(x.estimated_cost)} / 단독 가정 ${dollars(x.comparison_cost)} · ${x.estimated_saving_percent==null?'사용량 미확정':x.estimated_saving_percent>=0?x.estimated_saving_percent+'% 절감 추정':Math.abs(x.estimated_saving_percent)+'% 증가 · 단일 모델 검토'}<br><small>${e(x.note)}</small></p>`).join(''):'';
  root.querySelectorAll('[data-ai-stop]').forEach(b=>b.onclick=()=>action(()=>request('/admin/ai-collection/runs/'+encodeURIComponent(b.dataset.aiStop)+'/stop',{method:'POST'}),'중지를 요청했습니다.'));
 }
 async function action(fn,message){const el=root.querySelector('[data-ai-message]');try{await fn();el.textContent=message;await refresh();await loadItems();}catch(err){el.textContent=err.message;}}
 async function refresh(){if(loading||!visible())return;loading=true;try{const prior=snapshot?.runs.map(r=>r.id+':'+r.status).join();snapshot=await request('/ai-agents');if(root?.isConnected){render();if(prior!==snapshot.runs.map(r=>r.id+':'+r.status).join())await loadItems();}}catch(err){if(root?.isConnected)root.querySelector('[data-ai-message]').textContent=err.message;}finally{loading=false;schedule();}}
 function visible(){return !!root?.isConnected&&!document.hidden&&!!root.offsetParent;}
 function schedule(){clearTimeout(timer);timer=setTimeout(async()=>{if(!root?.isConnected)return;if(visible()&&root.querySelector('.ai-collection')?.open)await refresh();else schedule();},snapshot?.runs.some(r=>['QUEUED','RUNNING','STOPPING'].includes(r.status))?5000:60000);}
 document.addEventListener('visibilitychange',()=>{if(visible())refresh();});

 function renderProgress(){
  const runs=snapshot.runs.filter(r=>(r.config.agent_role||'collection')===selected);const run=runs.find(r=>['QUEUED','RUNNING','STOPPING'].includes(r.status))||runs[0];
  const target=root.querySelector('[data-ai-progress]');clearInterval(clockTimer);
  if(!run){target.innerHTML='';return;}
  const p=run.progress||{},active=['QUEUED','RUNNING','STOPPING'].includes(run.status),n=x=>Number(x||0).toLocaleString('ko-KR');
  const stages={QUEUED:'작업자 배정 대기',DISCOVERY:'1 / 2 · 출처·뉴스 탐색',FETCH:'2 / 2 · 원문 가져오기',ANALYZE:'2 / 2 · AI 분석',SAVE:'2 / 2 · 검토함 저장'};
  const stage=run.status==='STOPPING'?'중지 처리 · 현재 요청 종료 대기':active?(stages[p.stage]||'진행 상태 확인 중'):names[run.status]||run.status;
  const unit=p.unit==='sources'?'출처':'자료',known=Number.isFinite(p.percent);
  const estimate=p.estimated_remaining_tokens==null?(active?'첫 자료 처리 후 산정':'추정 불가'):'약 '+n(p.estimated_remaining_tokens)+' 토큰';
  target.innerHTML=`<section class="ai-progress-card ${active?'is-active':''}" aria-label="이번 수집 진행 현황"><div class="ai-progress-heading"><strong>${active?'<span class="ai-running-dot" aria-hidden="true"></span>':''}${e(stage)}${p.model?' · '+e(p.model):''}</strong><span data-ai-elapsed></span></div>
   <p class="ai-progress-current">${e(active?(p.current||'처리 준비 중입니다.'):run.error||'완료 자료와 분석 결과가 검토함에 보존되어 있습니다.')}</p>
   <div class="ai-progress-count"><span>${p.total==null?(active?unit+' 대상 확인 중':unit+' '+n(p.completed)+'건 처리 · 전체 대상 미기록'):unit+' '+n(p.completed)+' / '+n(p.total)+' 처리'}</span><b>${known?Math.floor(p.percent)+'%':''}</b></div>
   <div class="ai-progress-bar ${active?'is-busy':''}" role="progressbar" aria-label="${e(unit+' 처리 진행률')}" ${known?`aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.floor(p.percent)}"`:''}><i data-ai-progress-fill></i></div>
   <div class="ai-token-grid"><div><small>이번 실행 · 확인된 사용량</small><b>${n(p.confirmed_tokens)} 토큰</b><span>입력 + 출력 · 응답 완료 기준</span></div><div><small>진행 중 요청 · 예약 상한</small><b>${n(p.reserved_tokens)} 토큰</b><span>현재 생성량이 아닌 요청 예약량</span></div><div><small>${['BUDGET_PAUSED','CANCELLED','INTERRUPTED','FAILED'].includes(run.status)?'재실행 시 남은 작업 예상':'남은 작업 예상 사용량'}</small><b>${e(estimate)}</b><span>${p.documents_remaining==null?'탐색 후 분석 대상 확정':'자료 '+n(p.documents_remaining)+'건 남음'} · 확정값 아님</span></div></div>
   <p class="ai-estimate-note">${e(p.estimate_note||'토큰 사용량은 공급자 응답을 받은 뒤 갱신됩니다.')} ${p.unknown_tokens?'응답 미확정 예약 '+n(p.unknown_tokens)+' 토큰은 확인된 사용량과 별도입니다.':''}</p>
   ${(p.models||[]).length?`<div class="ai-model-tokens">${p.models.map(m=>`<span><b>${e(m.model)}</b> 입력 ${n(m.input_tokens)} · 출력 ${n(m.output_tokens)}${m.reserved_tokens?' · 예약 '+n(m.reserved_tokens):''}${m.unknown_tokens?' · 미확정 '+n(m.unknown_tokens):''}</span>`).join('')}</div>`:''}
   <p class="ai-progress-foot">${active?(snapshot.worker_online?'작업자 연결됨 · 2초마다 상태 확인':'작업자 연결 확인 필요 · 진행 정보가 지연될 수 있습니다.'):'이번 실행 종료'}${p.documents_skipped?' · 변경 없음 '+n(p.documents_skipped)+'건':''}${p.documents_failed?' · 자료 처리 실패 '+n(p.documents_failed)+'건':''}${p.documents_deferred?' · 심층 검토 대기 '+n(p.documents_deferred)+'건':''}${p.source_errors?' · 출처 확인 필요 '+n(p.source_errors)+'곳':''}</p>
   ${active?`<button type="button" class="button secondary" data-ai-stop="${e(run.id)}" ${state.admin&&run.status!=='STOPPING'?'':'disabled'}>현재 작업 중지</button>`:''}</section>`;
  target.querySelector('[data-ai-progress-fill]').style.width=(known?Math.max(0,Math.min(100,p.percent)):0)+'%';
  const received=Date.now(),elapsed=Number(p.elapsed_seconds||0);
  const clock=()=>{if(!root?.isConnected){clearInterval(clockTimer);return;}const seconds=elapsed+(active?Math.floor((Date.now()-received)/1000):0);const el=target.querySelector('[data-ai-elapsed]');if(el)el.textContent=Math.floor(seconds/60)+'분 '+seconds%60+'초 경과';};
  clock();if(active&&visible())clockTimer=setInterval(()=>{if(visible())clock();},1000);
 }
 function analysis(value){
  if(!value)return '';
  const r=value.result;
  return `<section class="ai-evidence"><h4>AI 수집·분석 결과 <small>담당자 미확인</small></h4><p>${e(value.profile)} · ${e((value.passes||[]).map(p=>p.model).join(' → '))} · ${e(new Date(value.collected_at).toLocaleString('ko-KR'))}</p>
   ${value.stale?'<p><b>원문 또는 담당자 판단이 변경됐습니다. 이전 분석을 그대로 적용하지 마세요.</b></p>':''}
   <p>${e(r?.summary||'원문을 수집했으나 AI 분석을 완료하지 못했습니다.')}</p>
   ${r?`<strong>확인할 질문</strong><p>${e(r.review_question)}</p><ul>${r.quantities.map(q=>`<li>${e(q.scope)} ${Number(q.value).toLocaleString('ko-KR')}${e(q.unit)}<blockquote>${e(q.quote)}</blockquote></li>`).join('')}</ul><details><summary>원문 근거 문장</summary>${r.evidence_quotes.map(q=>`<blockquote>${e(q)}</blockquote>`).join('')}</details>`:''}
   <ul>${[...(value.checks||[]),...(r?.issues||[])].map(q=>`<li>${e(q)}</li>`).join('')}</ul><p>자동 분석은 기존 승인·정책 귀속·실적을 변경하지 않습니다. 수집 본문과 분석 결과는 CSV에 포함됩니다.</p></section>`;
 }
 return {mount,analysis};
})();
