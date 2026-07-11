const API_BASE = '/api/portfolio/multiagent-harness';

const fallbackWorkflow = {
  waves: [
    ['collect-facts', 'collect-public'],
    ['summarize-evidence'],
    ['technical-analysis', 'legal-review'],
    ['executive-brief'],
    ['risk-check'],
    ['final-package'],
  ],
  items: [
    ['collect-facts', '장애 사실관계 수집'], ['collect-public', '민원·언론 쟁점 수집'],
    ['summarize-evidence', '공용 근거 요약'], ['technical-analysis', '기술 원인·조치 분석'],
    ['legal-review', '법령·제도 검토'], ['executive-brief', '실장급 보고자료'],
    ['risk-check', '리스크 교차검증'], ['final-package', '최종 패키지 통합'],
  ].map(([id, title]) => ({ id, title })),
};

const els = Object.fromEntries([
  'connectionLabel','missionPrompt','playbackSpeed','startRun','pauseRun','openSettings','openLiveRun',
  'liveRunDialog','confirmLiveRun','demoFromLiveDialog','cancelLiveRun','closeLiveRun','liveRunAvailability',
  'pipeline','phaseBadge','brokerPanel','poolPanel','officeCanvas','officeHeadline',
  'cinemaCaption','runProgress','hierarchy','taskDag','taskCounter','artifactCounter',
  'artifactList','eventLog','runClock','eventCounter','settingsDialog','providerHealth',
  'agentSettings','saveSettings','liveAccessPassword','authorizeLiveRun','liveAuthStatus',
  'credentialModeOwner','credentialModePersonal','ownerCredentialPanel','personalCredentialPanel',
  'personalOpenRouterKey','personalHuggingFaceKey','personalKeyStatus',
  'qualityGates','reviewOverlay','reviewGateLabel',
  'reviewTitle','reviewChecks','reviewStamp','artifactDialog','artifactViewerTitle',
  'artifactViewerFile','artifactViewerStatus','artifactViewerMeta','artifactViewerSummary',
  'artifactViewerContent','artifactViewerSources','artifactViewerDependencies','artifactViewerRevisions','copyArtifact','closeArtifact',
].map(id => [id, document.getElementById(id)]));

const canvas = els.officeCanvas;
const LOGICAL_CANVAS_WIDTH = 920;
const LOGICAL_CANVAS_HEIGHT = 560;
const CANVAS_RENDER_SCALE = 2;
canvas.width = LOGICAL_CANVAS_WIDTH * CANVAS_RENDER_SCALE;
canvas.height = LOGICAL_CANVAS_HEIGHT * CANVAS_RENDER_SCALE;
const ctx = canvas.getContext('2d');
ctx.setTransform(CANVAS_RENDER_SCALE,0,0,CANVAS_RENDER_SCALE,0,0);
ctx.imageSmoothingEnabled = false;

const state = {
  config: null,
  run: null,
  actors: new Map(),
  assignments: {},
  providerStats: {},
  tasks: new Map(),
  artifacts: new Map(),
  phase: '',
  eventIndex: 0,
  startedAt: 0,
  pausedAt: 0,
  pausedTotal: 0,
  playing: false,
  paused: false,
  speed: 4,
  handoffQueue: [],
  handoffBusy: false,
  activeHandoff: null,
  activeArtifactId: null,
  activeReview: null,
  reviewHideTimer: null,
  gateStates: new Map(),
  livePolling: false,
  livePollTimer: null,
  liveAuthorizationToken: '',
  liveAuthorizationExpiresAt: 0,
  liveCredentialMode: 'owner',
};

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}

function formatTime(ms) {
  const seconds = Math.max(0, ms) / 1000;
  const mins = Math.floor(seconds / 60);
  return `${String(mins).padStart(2,'0')}:${(seconds % 60).toFixed(1).padStart(4,'0')}`;
}

function providerFromModel(model) {
  return String(model || '').split(':', 1)[0] || 'unknown';
}

async function readJson(response) {
  const text = await response.text();
  let body = {};
  try { body = text ? JSON.parse(text) : {}; } catch { body = { error: text }; }
  if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
  return body;
}

async function loadConfig() {
  try {
    const response = await fetch(`${API_BASE}/config`, { cache: 'no-store' });
    state.config = await readJson(response);
    els.connectionLabel.textContent = 'HARNESS READY · 이벤트 계약 연결됨';
    initializeStaticUI();
  } catch (error) {
    els.connectionLabel.textContent = `연결 실패 · ${error.message}`;
    els.startRun.disabled = true;els.openLiveRun.disabled=true;
  }
}

function initializeStaticUI() {
  const config = state.config;
  renderPipeline(config.phases || []);
  renderPools(config.pools || []);
  renderHierarchy(config.agents || []);
  renderWorkflow(config.workflow || fallbackWorkflow);
  renderSettings();
  resetBroker(config.model_registry?.providers || {});
  createActors(config.agents || []);
  renderLiveRunAvailability();
}

function hasLiveAuthorization(){
  if(!state.liveAuthorizationToken||Date.now()>=state.liveAuthorizationExpiresAt){
    state.liveAuthorizationToken='';state.liveAuthorizationExpiresAt=0;
    if(state.config?.live_execution)state.config.live_execution.enabled=false;
    return false;
  }
  return true;
}

function selectedCredentialMode(){
  return document.querySelector('input[name="liveCredentialMode"]:checked')?.value||state.liveCredentialMode||'owner';
}

function personalKeys(){
  return {
    openrouter:els.personalOpenRouterKey?.value.trim()||'',
    huggingface:els.personalHuggingFaceKey?.value.trim()||'',
  };
}

function hasPersonalKeys(){const keys=personalKeys();return Boolean(keys.openrouter||keys.huggingface)}

function canStartLive(){
  if(selectedCredentialMode()==='personal')return hasPersonalKeys();
  return Boolean(state.config?.live_execution?.enabled&&hasLiveAuthorization());
}

function renderLiveRunAvailability(){
  const live=state.config?.live_execution||{enabled:false,reason:'실제 LLM 실행 엔진 연결 전입니다.'};
  const mode=selectedCredentialMode(),ready=canStartLive();
  els.confirmLiveRun.disabled=!ready;
  els.liveRunAvailability.className=`live-run-availability ${ready?'ready':'unavailable'}`;
  if(ready)els.liveRunAvailability.textContent=mode==='personal'?'개인 API Key 실행 준비 완료 · 입력 키는 이번 실행에만 사용됩니다.':'사이트 오너 API Key 준비 완료 · 인증은 10분 동안 유효합니다.';
  else els.liveRunAvailability.textContent=mode==='personal'?'현재 실행 불가 · 모델 설정에서 개인 API Key를 입력해 주세요.':`현재 실행 불가 · ${live.reason||'모델 설정에서 암호 인증이 필요합니다.'}`;
  renderLiveAuthSettings();
}

function openLiveRunConfirmation(){renderLiveRunAvailability();els.liveRunDialog.showModal()}
function closeLiveRunConfirmation(){els.liveRunDialog.close()}
function runDemoFromConfirmation(){closeLiveRunConfirmation();startRun('demo')}
function runLiveFromConfirmation(){if(!canStartLive())return;closeLiveRunConfirmation();startRun('live')}

function renderLiveAuthSettings(message='',kind=''){
  if(!els.liveAuthStatus)return;
  const live=state.config?.live_execution||{};
  const mode=selectedCredentialMode(),ownerMode=mode==='owner';
  state.liveCredentialMode=mode;
  els.ownerCredentialPanel.hidden=!ownerMode;els.personalCredentialPanel.hidden=ownerMode;
  const ownerAvailable=Boolean(live.owner_available??live.available);
  const authorized=Boolean(ownerMode&&live.enabled&&hasLiveAuthorization());
  els.liveAccessPassword.disabled=!ownerMode||!ownerAvailable||authorized||kind==='working';
  els.authorizeLiveRun.disabled=!ownerMode||!ownerAvailable||authorized||kind==='working';
  els.authorizeLiveRun.textContent=authorized?'활성화 완료':'10분간 활성화';
  els.liveAuthStatus.className=`live-auth-status ${ownerMode?(kind||(authorized?'ready':ownerAvailable?'':'error')):''}`;
  els.liveAuthStatus.textContent=ownerMode?(message||(authorized?'인증 완료 · 사이트 오너 API Key가 10분 동안 활성화됩니다.':ownerAvailable?'암호 인증 후 사이트 오너 API Key를 사용할 수 있습니다.':live.reason||'사이트 오너 API Key를 사용할 수 없습니다.')):'사이트 오너 키 모드가 선택되지 않았습니다.';
  const keys=personalKeys(),personalReady=Boolean(keys.openrouter||keys.huggingface);
  els.personalKeyStatus.className=`live-auth-status ${personalReady?'ready':''}`;
  els.personalKeyStatus.textContent=personalReady?`${keys.openrouter?'OpenRouter ':''}${keys.huggingface?'Hugging Face ':''}개인 키 준비 완료 · 저장하지 않고 이번 실행에만 사용합니다.`:'하나 이상의 개인 API Key를 입력해 주세요. 키는 저장되지 않습니다.';
}

async function authorizeLiveExecution(){
  const live=state.config?.live_execution||{};
  if(selectedCredentialMode()!=='owner')return;
  const password=els.liveAccessPassword.value;
  if(!password){renderLiveAuthSettings('실행 암호를 입력해 주세요.','error');els.liveAccessPassword.focus();return}
  els.authorizeLiveRun.disabled=true;renderLiveAuthSettings('서버에서 암호를 확인하고 있습니다.','working');
  try{
    const response=await fetch(`${API_BASE}${live.authorize_endpoint||'/live/authorize'}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});
    const body=await readJson(response);
    state.liveAuthorizationToken=body.authorization_token||'';
    state.liveAuthorizationExpiresAt=Date.now()+Number(body.expires_in_seconds||600)*1000;
    state.config.live_execution={...live,...body.live_execution,enabled:true};
    els.liveAccessPassword.value='';
    renderLiveRunAvailability();
  }catch(error){
    state.liveAuthorizationToken='';state.liveAuthorizationExpiresAt=0;
    if(state.config?.live_execution)state.config.live_execution.enabled=false;
    els.liveAccessPassword.value='';renderLiveAuthSettings(`인증 실패 · ${error.message}`,'error');els.liveAccessPassword.focus();
  }
}

function renderPipeline(phases) {
  els.pipeline.innerHTML = phases.map((phase, index) => `
    <div class="phase-step" data-phase="${escapeHtml(phase.id)}">
      <i>${String(index + 1).padStart(2,'0')}</i><span>${escapeHtml(phase.label)}</span><small>WAIT</small>
    </div>`).join('');
}

function renderPools(pools) {
  els.poolPanel.innerHTML = pools.map(pool => `
    <div class="pool-card"><div><b>${escapeHtml(pool.label)}</b><br><span>${escapeHtml(pool.capability)}</span></div><strong>${pool.replicas} replicas</strong></div>
  `).join('');
}

function renderHierarchy(agents) {
  const ordered = [...agents].sort((a,b) => {
    const rank = {manager:0,coordinator:1,worker:2};
    return (rank[a.layer] - rank[b.layer]) || a.team.localeCompare(b.team);
  });
  els.hierarchy.innerHTML = ordered.map(agent => {
    const depth = agent.layer === 'manager' ? 0 : agent.layer === 'coordinator' ? 1 : 2;
    return `<div class="hierarchy-node ${escapeHtml(agent.layer)}" style="--depth:${depth}"><b>${escapeHtml(agent.role)}</b><span>${escapeHtml(agent.team)} · ${escapeHtml(agent.capability)}</span></div>`;
  }).join('');
}

function renderWorkflow(workflow) {
  const byId = new Map((workflow.items || []).map(item => [item.id, item]));
  els.taskDag.innerHTML = (workflow.waves || []).map((wave, index) => `
    <div class="dag-wave"><span>W${index + 1}</span>${wave.map(id => `<div class="dag-node" data-task-node="${escapeHtml(id)}">${escapeHtml(byId.get(id)?.title || id)}</div>`).join('')}</div>
  `).join('');
  els.taskCounter.textContent = `0 / ${(workflow.items || []).length}`;
}

function resetBroker(providers) {
  state.providerStats = {};
  for (const [provider, info] of Object.entries(providers)) {
    state.providerStats[provider] = { active: 0, queued: 0, completed: 0, max: Number(info.max_in_flight || 1), label: info.label || provider };
  }
  for (const provider of ['ollama','huggingface','openrouter']) {
    if (!state.providerStats[provider]) state.providerStats[provider] = {active:0,queued:0,completed:0,max:provider==='openrouter'?2:1,label:provider};
  }
  renderBroker();
}

function renderBroker() {
  els.brokerPanel.innerHTML = Object.entries(state.providerStats).map(([provider, stat]) => {
    const width = Math.min(100, stat.max ? (stat.active / stat.max) * 100 : 0);
    return `<article class="broker-card" data-provider="${provider}"><header><span>${escapeHtml(stat.label)}</span><b>${stat.active}/${stat.max}</b></header><div class="broker-bar"><i style="width:${width}%"></i></div><div class="broker-meta"><span>QUEUE ${stat.queued}</span><span>DONE ${stat.completed}</span></div></article>`;
  }).join('');
}

function renderSettings() {
  const registry = state.config.model_registry || { models: state.config.models || [], providers: {} };
  const mode=selectedCredentialMode(),keys=personalKeys();
  els.providerHealth.innerHTML = Object.entries(registry.providers || {}).map(([id, item]) => `
    ${(()=>{const ready=mode==='personal'&&id!=='ollama'?Boolean(keys[id]):item.configured;return `<span class="provider-pill ${ready?'ready':''}">${escapeHtml(item.label||id)} · ${ready?'READY':mode==='personal'&&id!=='ollama'?'개인 키 필요':'설정 필요'} · SLOT ${item.max_in_flight||1}</span>`})()}
  `).join('');
  renderLiveAuthSettings();
  const models = registry.models || [];
  els.agentSettings.innerHTML = (state.config.agents || []).map(agent => {
    const selected = state.assignments[agent.id] || agent.model;
    state.assignments[agent.id] = selected;
    return `<label class="agent-setting"><span><b>${escapeHtml(agent.role)}</b><span>${escapeHtml(agent.name)} · ${escapeHtml(agent.capability)}</span></span><select data-agent-model="${escapeHtml(agent.id)}">${models.map(model => {const available=mode==='personal'&&model.provider!=='ollama'?Boolean(keys[model.provider]):model.available;return `<option value="${escapeHtml(model.value)}" ${model.value===selected?'selected':''} ${!available&&model.value!==selected?'disabled':''}>${escapeHtml(model.label)}${available?'':' · 설정 필요'}</option>`}).join('')}</select></label>`;
  }).join('');
}

function createActors(agents) {
  state.actors.clear();
  for (const agent of agents) {
    const [x,y] = agent.home;
    state.actors.set(agent.id, {
      ...agent, x, y, homeX:x, homeY:y, targetX:x, targetY:y, move:null,
      status:'idle', task:'', bubble:'', bubbleUntil:0,
      model:state.assignments[agent.id] || agent.model,
    });
  }
}

function resetRunUI() {
  state.tasks.clear(); state.artifacts.clear(); state.phase=''; state.eventIndex=0;
  state.handoffQueue=[]; state.handoffBusy=false; state.activeHandoff=null;
  state.activeArtifactId=null;if(els.artifactDialog.open)els.artifactDialog.close();
  state.activeReview=null; state.gateStates.clear();
  state.livePolling=false;if(state.livePollTimer)clearTimeout(state.livePollTimer);state.livePollTimer=null;
  if(state.reviewHideTimer)clearTimeout(state.reviewHideTimer);
  els.reviewOverlay.className='review-overlay';els.reviewChecks.innerHTML='';els.reviewStamp.textContent='CHECK';
  document.querySelectorAll('[data-gate-chip]').forEach((chip,index)=>{chip.className='gate-chip';chip.querySelector('small').textContent='WAIT';chip.querySelector('i').textContent=String(index+1)});
  els.eventLog.innerHTML=''; els.artifactList.innerHTML='<p class="empty-copy">실행 중 생성된 파일이 여기에 쌓입니다.</p>';
  els.artifactCounter.textContent='0'; els.eventCounter.textContent='0 events'; els.runClock.textContent='00:00.0';
  els.runProgress.style.width='0'; els.taskCounter.textContent=`0 / ${(state.config.workflow?.items || fallbackWorkflow.items).length}`;
  document.querySelectorAll('.phase-step').forEach(row => {row.className='phase-step';row.querySelector('small').textContent='WAIT'});
  document.querySelectorAll('.dag-node').forEach(node => node.className='dag-node');
  createActors(state.run?.agents || state.config.agents || []);
  resetBroker(state.config.model_registry?.providers || {});
}

async function startRun(mode='demo') {
  const isLive=mode==='live',live=state.config?.live_execution||{};
  if(isLive&&!canStartLive()){openLiveRunConfirmation();return}
  const prompt = els.missionPrompt.value.trim();
  if (!prompt) { els.missionPrompt.focus(); return; }
  els.startRun.disabled=true;els.openLiveRun.disabled=true;els.pauseRun.disabled=false;els.officeHeadline.textContent=isLive?'실제 LLM 하네스가 계층형 실행을 준비합니다.':'데모 하네스가 계층형 실행 계획을 준비합니다.';
  try {
    const endpoint=isLive?`${API_BASE}${live.endpoint||'/live'}`:`${API_BASE}/demo`;
    const payload={prompt,assignments:state.assignments,mode:isLive?'live':'demo'};
    const credentialMode=selectedCredentialMode();
    if(isLive){
      payload.credential_mode=credentialMode;
      if(credentialMode==='owner')payload.authorization_token=state.liveAuthorizationToken;
      else payload.personal_keys=personalKeys();
    }
    const response = await fetch(endpoint, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    state.run = await readJson(response);
    if(isLive&&credentialMode==='owner'){state.liveAuthorizationToken='';state.liveAuthorizationExpiresAt=0;state.config.live_execution.enabled=false;state.config.live_execution.reason='실행 인증이 사용되었습니다. 다음 실행 전에 다시 인증해 주세요.'}
    if(isLive&&credentialMode==='personal'){els.personalOpenRouterKey.value='';els.personalHuggingFaceKey.value='';renderSettings()}
    if(isLive)renderLiveRunAvailability();
    for (const agent of state.run.agents || []) agent.model = state.assignments[agent.id] || agent.model;
    const assigned = new Map((state.run.agents || []).map(agent => [agent.id, agent.model]));
    for (const event of state.run.events || []) {
      const agentId = event.data?.agent_id;
      if (agentId && event.type.startsWith('inference.') && assigned.has(agentId)) event.data.provider = providerFromModel(assigned.get(agentId));
    }
    resetRunUI();
    if(isLive){
      state.playing=true;state.paused=false;state.livePolling=true;els.pauseRun.disabled=true;els.phaseBadge.textContent='LIVE';els.cinemaCaption.textContent='실제 LLM 응답을 기다리며 하네스 이벤트를 수신합니다.';
      applyLiveSnapshot(state.run);return;
    }
    state.speed=Number(els.playbackSpeed.value)||4;state.startedAt=performance.now();state.pausedTotal=0;state.playing=true;state.paused=false;
    els.pauseRun.textContent='일시정지';
  } catch(error) {
    els.officeHeadline.textContent=`실행 실패 · ${error.message}`;els.startRun.disabled=false;els.openLiveRun.disabled=false;els.pauseRun.disabled=true;
  }
}

function applyLiveSnapshot(snapshot){
  state.run=snapshot;const events=snapshot.events||[];
  while(state.eventIndex<events.length){handleEvent(events[state.eventIndex]);state.eventIndex++}
  const elapsed=events.at(-1)?.at_ms||0;els.runClock.textContent=formatTime(elapsed);
  const artifactProgress=Math.min(95,((snapshot.artifacts||[]).length/9)*100);els.runProgress.style.width=`${snapshot.status==='complete'?100:artifactProgress}%`;
  if(snapshot.status==='running'||snapshot.status==='queued')scheduleLivePoll();
  else{state.livePolling=false;if(state.livePollTimer)clearTimeout(state.livePollTimer);state.livePollTimer=null}
}

function scheduleLivePoll(){
  if(!state.livePolling||!state.run?.run_id)return;
  if(state.livePollTimer)clearTimeout(state.livePollTimer);
  state.livePollTimer=setTimeout(pollLiveRun,700);
}

async function pollLiveRun(){
  if(!state.livePolling||!state.run?.run_id)return;
  try{
    const response=await fetch(`${API_BASE}/runs/${encodeURIComponent(state.run.run_id)}`,{cache:'no-store'});
    applyLiveSnapshot(await readJson(response));
  }catch(error){
    state.livePolling=false;state.playing=false;els.startRun.disabled=false;els.openLiveRun.disabled=false;els.pauseRun.disabled=true;els.phaseBadge.textContent='ERROR';els.officeHeadline.textContent=`실제 실행 상태 확인 실패 · ${error.message}`;els.cinemaCaption.textContent='실제 실행을 데모로 대체하지 않았습니다.';
  }
}

function togglePause() {
  if (!state.playing) return;
  if (!state.paused) {state.paused=true;state.pausedAt=performance.now();els.pauseRun.textContent='계속 재생';}
  else {state.paused=false;state.pausedTotal+=performance.now()-state.pausedAt;els.pauseRun.textContent='일시정지';}
}

function setPhase(phase,label) {
  state.phase=phase;els.phaseBadge.textContent=phase.toUpperCase();
  const rows=[...document.querySelectorAll('.phase-step')];
  const current=rows.findIndex(row=>row.dataset.phase===phase);
  rows.forEach((row,index)=>{row.className=`phase-step ${index<current?'done':index===current?'active':''}`;row.querySelector('small').textContent=index<current?'DONE':index===current?'LIVE':'WAIT'});
  els.officeHeadline.textContent=label;els.cinemaCaption.textContent=`현재 하네스 단계 · ${label}`;
}

function actor(id){return state.actors.get(id)}
function setActorStatus(id,status,message='') {const a=actor(id);if(!a)return;a.status=status;if(message){a.bubble=message;a.bubbleUntil=performance.now()+2600}}
function moveActor(id,x,y,duration=700,onArrive=null){const a=actor(id);if(!a)return;a.move={fromX:a.x,fromY:a.y,toX:x,toY:y,start:performance.now(),duration,onArrive}}
function returnHome(id,delay=0){setTimeout(()=>{const a=actor(id);if(a)moveActor(id,a.homeX,a.homeY,650,()=>{a.status='idle'})},delay)}

function updateActorMovement(now){for(const a of state.actors.values()){if(!a.move)continue;const p=Math.min(1,(now-a.move.start)/a.move.duration);const eased=p<.5?2*p*p:1-Math.pow(-2*p+2,2)/2;a.x=a.move.fromX+(a.move.toX-a.move.fromX)*eased;a.y=a.move.fromY+(a.move.toY-a.move.fromY)*eased;if(p>=1){const done=a.move.onArrive;a.move=null;if(done)done()}}}

function enqueueHandoff(data){state.handoffQueue.push(data);playNextHandoff()}
function playNextHandoff(){if(state.handoffBusy||!state.handoffQueue.length)return;state.handoffBusy=true;const data=state.handoffQueue.shift();const from=actor(data.from_id),to=actor(data.to_id);if(!from||!to){state.handoffBusy=false;playNextHandoff();return}const red=data.severity==='red';const meetX=460,meetY=330;from.status='handoff';to.status='handoff';from.bubble=red?'필수 수정 문서를 반송합니다.':'산출물을 전달합니다.';from.bubbleUntil=performance.now()+2500;to.bubble=red?'수정 후 다시 제출하겠습니다.':'확인했습니다.';to.bubbleUntil=performance.now()+2700;state.activeHandoff={...data,from_id:from.id,to_id:to.id,visible:false,red};moveActor(from.id,meetX-38,meetY,700);moveActor(to.id,meetX+38,meetY,700,()=>{state.activeHandoff.visible=true;setTimeout(()=>{if(state.activeHandoff)state.activeHandoff.visible=false;returnHome(from.id);returnHome(to.id);setTimeout(()=>{state.activeHandoff=null;state.handoffBusy=false;playNextHandoff()},800)},800)})}

function startMeeting(data){const ids=[data.host,...(data.participants||[])];const whiteboard=[675,115];ids.forEach((id,index)=>{const angle=Math.PI+(index/(Math.max(ids.length-1,1)))*Math.PI;moveActor(id,whiteboard[0]+Math.cos(angle)*90,whiteboard[1]+Math.sin(angle)*55,800);setActorStatus(id,'meeting',index===0?data.message:'브리핑 확인')})}
function endMeeting(data){[data.host,...(data.participants||[])].forEach(id=>returnHome(id))}

function updateGateChip(gate,status){
  if(!gate)return;
  state.gateStates.set(gate,status);
  const chip=document.querySelector(`[data-gate-chip="${CSS.escape(gate)}"]`);
  if(!chip)return;
  chip.className=`gate-chip ${status}`;
  chip.querySelector('small').textContent=status==='active'?'CHECK':status==='pass'?'PASS':status==='fail'?'REWORK':'WAIT';
  chip.querySelector('i').textContent=status==='pass'?'✓':status==='fail'?'!':chip.querySelector('i').textContent;
}

function beginReview(data){
  if(state.reviewHideTimer)clearTimeout(state.reviewHideTimer);
  const gate=data.gate||'risk';
  state.activeReview={...data,gate,items:[],outcome:'active'};
  updateGateChip(gate,'active');
  els.reviewGateLabel.textContent=data.gate_label||'QUALITY GATE · 중간 검수';
  els.reviewTitle.textContent=data.title||'중간 산출물을 꼼꼼히 확인합니다';
  els.reviewChecks.innerHTML='<span class="review-check">⌕ 체크리스트를 펼치는 중...</span>';
  els.reviewStamp.textContent='CHECK';
  els.reviewOverlay.className='review-overlay active';
  setActorStatus(data.reviewer_id,'inspecting','제가 꼼꼼히 볼게요!');
  setActorStatus(data.target_id,'reviewing','검수 결과를 기다립니다.');
  els.cinemaCaption.textContent=`🔎 ${data.gate_label||'중간 검수'} · ${actor(data.reviewer_id)?.name||'검수 에이전트'}가 ${data.artifact_id||'산출물'}을 확인합니다.`;
}

function addReviewItem(data){
  if(!state.activeReview||state.activeReview.gate!==(data.gate||'risk'))beginReview({gate:data.gate||'risk',gate_label:'QUALITY GATE · 체크리스트',title:'산출물 검수 중'});
  state.activeReview.items.push(data);
  els.reviewChecks.innerHTML=state.activeReview.items.map(item=>`<span class="review-check ${item.result==='pass'?'pass':'fail'}">${item.result==='pass'?'✓':'!'} ${escapeHtml(item.label)}</span>`).join('');
  els.cinemaCaption.textContent=`${data.result==='pass'?'✅':'⚠️'} 검수 항목 · ${data.label}`;
}

function finishReview(data,outcome){
  const gate=data.gate||state.activeReview?.gate||'risk';
  if(!state.activeReview||state.activeReview.gate!==gate){
    state.activeReview={...data,gate,items:[],outcome};
    els.reviewGateLabel.textContent='QUALITY GATE · 검수 결과';
    els.reviewTitle.textContent=data.message||'검수 결과가 등록되었습니다.';
    els.reviewChecks.innerHTML='';
  }
  state.activeReview={...state.activeReview,...data,outcome};
  updateGateChip(gate,outcome);
  els.reviewOverlay.className=`review-overlay active ${outcome}`;
  els.reviewStamp.textContent=outcome==='pass'?'APPROVED':'REWORK';
  els.reviewTitle.textContent=data.message||els.reviewTitle.textContent;
  const reviewer=data.agent_id||state.activeReview.reviewer_id;
  if(reviewer)setActorStatus(reviewer,outcome==='pass'?'done':'blocked',outcome==='pass'?'검수 통과! 참 잘했어요 ✦':'수정할 곳을 찾았어요!');
  if(data.target_id)setActorStatus(data.target_id,outcome==='pass'?'done':'blocked',data.message);
  els.cinemaCaption.textContent=outcome==='pass'?`✅ ${data.message}`:`↩️ 검수 반송 · ${data.message}`;
  state.reviewHideTimer=setTimeout(()=>{els.reviewOverlay.className='review-overlay';state.activeReview=null},outcome==='pass'?1050:1500);
}

const artifactStatusLabels={created:'작성 완료',revised:'수정본 작성',rework:'수정 필요',approved:'검수 통과',archived:'보관 완료'};

function artifactDefinition(id){return (state.run?.artifacts||[]).find(item=>item.id===id)||{}}
function artifactAgentLabel(id){const item=actor(id)||(state.run?.agents||[]).find(agent=>agent.id===id);return item?`${item.name} · ${item.role}`:(id||'알 수 없음')}

function addArtifact(data,type){
  const id=data.artifact_id;if(!id)return;const definition=artifactDefinition(id),existing=state.artifacts.get(id)||{};
  const version=Number(data.revision||existing.version||1),status=type==='revised'?'revised':existing.status||'created';
  state.artifacts.set(id,{...definition,...existing,...data,id,artifact_id:id,type,version,status});renderArtifacts();
  if(state.activeArtifactId===id)renderArtifactViewer(id);
}

function updateArtifactStatus(id,status,extra={}){
  if(!id)return;const existing=state.artifacts.get(id);if(!existing)return;
  state.artifacts.set(id,{...existing,...extra,status});renderArtifacts();if(state.activeArtifactId===id)renderArtifactViewer(id);
}

function renderArtifacts(){
  els.artifactCounter.textContent=String(state.artifacts.size);
  els.artifactList.innerHTML=[...state.artifacts.values()].reverse().map(item=>`<button type="button" class="artifact-item ${item.severity||''} ${item.status||''}" data-artifact-id="${escapeHtml(item.artifact_id)}" aria-label="${escapeHtml(item.title||item.artifact_id)} 열기"><i aria-hidden="true"></i><div><b>${escapeHtml(item.artifact_id)}</b><span>${escapeHtml(item.title||item.message||'산출물 등록')} · ${escapeHtml(artifactStatusLabels[item.status]||'작성 완료')}</span></div></button>`).join('')||'<p class="empty-copy">실행 중 생성된 파일이 여기에 쌓입니다.</p>';
}

function artifactLinkMarkup(items){
  if(!items?.length)return '<span class="empty">연결 없음</span>';
  return items.map(raw=>{const ref=String(raw),id=ref.replace(/ v\d+$/,'');return state.artifacts.has(id)?`<button type="button" data-artifact-link="${escapeHtml(id)}">${escapeHtml(ref)}</button>`:`<span>${escapeHtml(ref)}</span>`}).join('');
}

function renderArtifactViewer(id){
  const item=state.artifacts.get(id);if(!item)return;
  state.activeArtifactId=id;els.artifactViewerTitle.textContent=item.title||id;els.artifactViewerFile.textContent=id;
  els.artifactViewerStatus.className=`artifact-status ${item.status||'created'}`;els.artifactViewerStatus.textContent=artifactStatusLabels[item.status]||'작성 완료';
  els.artifactViewerMeta.innerHTML=`<dt>작성자</dt><dd>${escapeHtml(artifactAgentLabel(item.agent_id))}</dd><dt>버전</dt><dd>v${escapeHtml(item.version||1)}</dd><dt>형식</dt><dd>${escapeHtml((item.format||'markdown').toUpperCase())}</dd><dt>실행 ID</dt><dd>${escapeHtml(state.run?.run_id?.slice(0,8)||'-')}</dd>`;
  els.artifactViewerSummary.textContent=item.summary||item.message||'요약 정보가 없습니다.';els.artifactViewerContent.textContent=item.content||'# 내용 준비 중\n\n산출물 본문이 아직 등록되지 않았습니다.';
  els.artifactViewerSources.innerHTML=artifactLinkMarkup(item.sources);els.artifactViewerDependencies.innerHTML=artifactLinkMarkup(item.depends_on);
  const revisions=item.revisions||[];els.artifactViewerRevisions.innerHTML=revisions.length?revisions.map(revision=>`<article class="artifact-revision"><b>v${escapeHtml(revision.version)} · ${escapeHtml(revision.label)}</b><p>${escapeHtml(revision.note)}</p></article>`).join(''):`<article class="artifact-revision"><b>v${escapeHtml(item.version||1)} · 현재본</b><p>추가 수정 이력이 없습니다.</p></article>`;
}

function openArtifact(id){if(!state.artifacts.has(id))return;renderArtifactViewer(id);if(!els.artifactDialog.open)els.artifactDialog.showModal()}

async function copyActiveArtifact(){
  const item=state.artifacts.get(state.activeArtifactId);if(!item)return;
  const original=els.copyArtifact.textContent;
  try{await navigator.clipboard.writeText(item.content||'');els.copyArtifact.textContent='복사 완료 ✓'}catch{els.copyArtifact.textContent='복사 실패'}
  setTimeout(()=>{els.copyArtifact.textContent=original},1200);
}

function updateTask(data,status){const id=data.task_id||data.artifact_id;if(!id)return;const current=state.tasks.get(id)||{};state.tasks.set(id,{...current,...data,status});const node=document.querySelector(`[data-task-node="${CSS.escape(id)}"]`);if(node)node.className=`dag-node ${status==='done'?'done':'active'}`;const total=(state.config.workflow?.items||fallbackWorkflow.items).length;const done=[...state.tasks.values()].filter(item=>item.status==='done').length;els.taskCounter.textContent=`${Math.min(done,total)} / ${total}`}

function logEvent(event){const row=document.createElement('div');const critical=['handoff.requested','review.started','review.failed','review.passed','run.completed','meeting.requested'].includes(event.type);const review=event.type.startsWith('review.');const result=event.type==='review.passed'?'pass':event.type==='review.failed'?'fail':'';row.className=`event-row ${critical?'important':''} ${event.type==='review.failed'?'error':''} ${review?'review':''} ${result}`;row.innerHTML=`<span class="time">${formatTime(event.at_ms)}</span><span class="type">${escapeHtml(event.type)}</span><span>${escapeHtml(eventDescription(event))}</span>`;els.eventLog.append(row);els.eventLog.scrollTop=els.eventLog.scrollHeight;els.eventCounter.textContent=`${event.seq} events`}

function eventDescription(event){const d=event.data||{};return d.message||d.title||d.label||d.artifact_id||d.task_id||d.phase||''}

function handleEvent(event){const d=event.data||{};logEvent(event);
  if(event.type==='phase.changed')setPhase(d.phase,d.label);
  else if(event.type==='task.assigned'){setActorStatus(d.agent_id,'assigned',d.title);const a=actor(d.agent_id);if(a)a.task=d.title;updateTask(d,'active')}
  else if(event.type==='task.rework'){setActorStatus(d.agent_id,'rework',d.title);updateTask(d,'active')}
  else if(event.type==='agent.status')setActorStatus(d.agent_id,d.status,d.message);
  else if(event.type==='inference.queued'){const p=state.providerStats[d.provider];if(p){p.queued++;renderBroker()}setActorStatus(d.agent_id,'queued','모델 슬롯을 기다립니다.')}
  else if(event.type==='inference.started'){const p=state.providerStats[d.provider];if(p){p.queued=Math.max(0,p.queued-1);p.active++;renderBroker()}setActorStatus(d.agent_id,'working',`${d.provider} 추론 중`) }
  else if(event.type==='inference.completed'){const p=state.providerStats[d.provider];if(p){p.active=Math.max(0,p.active-1);p.completed++;renderBroker()}setActorStatus(d.agent_id,'writing','결과를 문서화합니다.')}
  else if(event.type==='inference.failed'){const p=state.providerStats[d.provider];if(p){p.active=Math.max(0,p.active-1);renderBroker()}setActorStatus(d.agent_id,'blocked',d.message)}
  else if(event.type==='model.fallback')setActorStatus(d.agent_id,'queued',d.message);
  else if(event.type==='artifact.created'){addArtifact(d,'created');setActorStatus(d.agent_id,'done',`${d.artifact_id} 생성 완료`);const a=actor(d.agent_id);if(a&&a.task){for(const [id,item] of state.tasks){if(item.agent_id===d.agent_id&&item.status!=='done')updateTask({...item,task_id:id},'done')}}}
  else if(event.type==='artifact.revised'){addArtifact(d,'revised');setActorStatus(d.agent_id,'done','수정본 작성 완료')}
  else if(event.type==='handoff.requested'){enqueueHandoff(d);els.cinemaCaption.textContent=`${actor(d.from_id)?.role||d.from_id} → ${actor(d.to_id)?.role||d.to_id} · ${d.artifact_id}`}
  else if(event.type==='meeting.requested'){startMeeting(d);els.cinemaCaption.textContent='PM 브리핑 · Coordinator들이 Whiteboard에 모입니다.'}
  else if(event.type==='meeting.completed')endMeeting(d);
  else if(event.type==='review.started')beginReview(d);
  else if(event.type==='review.item')addReviewItem(d);
  else if(event.type==='review.failed'){finishReview(d,'fail');updateArtifactStatus(d.artifact_id,'rework',{severity:'red',review_message:d.message})}
  else if(event.type==='review.passed'){finishReview(d,'pass');updateArtifactStatus(d.artifact_id,'approved',{severity:'green',review_message:d.message})}
  else if(event.type==='submission.requested'){updateArtifactStatus(d.artifact_id,'archived',{destination:d.destination});const a=actor(d.agent_id);if(a){a.status='submission';a.bubble='최종 패키지를 보관합니다.';a.bubbleUntil=performance.now()+3000;moveActor(a.id,845,430,1100)}els.cinemaCaption.textContent='Final Synthesizer가 Filing Cabinet으로 최종 패키지를 제출합니다.'}
  else if(event.type==='run.completed'){updateArtifactStatus(d.artifact_id,'archived');state.livePolling=false;if(state.livePollTimer)clearTimeout(state.livePollTimer);state.playing=false;els.startRun.disabled=false;els.openLiveRun.disabled=false;els.pauseRun.disabled=true;els.phaseBadge.textContent='COMPLETE';els.officeHeadline.textContent=d.message;els.cinemaCaption.textContent=d.message;document.querySelectorAll('.phase-step').forEach(row=>{row.className='phase-step done';row.querySelector('small').textContent='DONE'})}
  else if(event.type==='run.failed'){state.livePolling=false;if(state.livePollTimer)clearTimeout(state.livePollTimer);state.playing=false;els.startRun.disabled=false;els.openLiveRun.disabled=false;els.pauseRun.disabled=true;els.phaseBadge.textContent='FAILED';els.officeHeadline.textContent=`실제 LLM 실행 실패 · ${d.message}`;els.cinemaCaption.textContent='실패한 실제 실행은 데모 결과로 대체되지 않습니다.'}
}

function playbackLoop(now){updateActorMovement(now);if(state.playing&&!state.paused&&state.run&&state.run.mode!=='live-llm'){const elapsed=(now-state.startedAt-state.pausedTotal)*state.speed;const events=state.run.events||[];while(state.eventIndex<events.length&&events[state.eventIndex].at_ms<=elapsed){handleEvent(events[state.eventIndex]);state.eventIndex++}const duration=events.at(-1)?.at_ms||1;els.runClock.textContent=formatTime(elapsed);els.runProgress.style.width=`${Math.min(100,(elapsed/duration)*100)}%`}drawOffice(now);requestAnimationFrame(playbackLoop)}

function roundedRect(x,y,w,h,r,fill,stroke=''){ctx.beginPath();ctx.roundRect(x,y,w,h,r);ctx.fillStyle=fill;ctx.fill();if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=2;ctx.stroke()}}
function drawCuteDecor(now){
  ctx.fillStyle='#36506f';ctx.fillRect(0,0,920,62);ctx.fillStyle='#182840';ctx.fillRect(0,58,920,5);
  for(let x=22;x<590;x+=48){ctx.fillStyle=((x/48)%2<1)?'#ff9fbd':'#ffe082';ctx.beginPath();ctx.moveTo(x,8);ctx.lineTo(x+16,8);ctx.lineTo(x+8,22);ctx.fill()}
  ctx.strokeStyle='#8db1d1';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(18,7);ctx.lineTo(610,7);ctx.stroke();
  drawPlant(32,492);drawPlant(603,486);
  const glow=(Math.sin(now/450)+1)/2;ctx.globalAlpha=.25+glow*.18;ctx.fillStyle='#ffb4d0';ctx.beginPath();ctx.ellipse(460,338,120,54,0,0,Math.PI*2);ctx.fill();ctx.globalAlpha=1;
}

function drawPlant(x,y){
  ctx.fillStyle='#d4866d';ctx.fillRect(x-10,y+17,20,18);ctx.fillStyle='#f3a68f';ctx.fillRect(x-13,y+15,26,6);
  ctx.fillStyle='#77d68c';ctx.fillRect(x-3,y-7,7,25);ctx.fillRect(x-13,y-2,11,7);ctx.fillRect(x+4,y-12,12,8);ctx.fillStyle='#a5ed9e';ctx.fillRect(x-10,y-8,7,7);ctx.fillRect(x+5,y-3,8,7);
}

function drawQualityStation(now){
  const active=Boolean(state.activeReview);const pulse=(Math.sin(now/120)+1)/2;
  roundedRect(720,148,164,88,12,active?'#263d50':'#203248',active?'#ffd166':'#506b87');
  ctx.fillStyle=active?'#fff0ad':'#91a9c3';ctx.font='900 10px monospace';ctx.fillText('QUALITY CHECK DESK',734,166);
  ctx.fillStyle='#dfe9f3';ctx.fillRect(757,181,42,34);ctx.fillStyle=active?'#ffd166':'#7790aa';ctx.fillRect(764,188,28,3);ctx.fillRect(764,196,22,3);ctx.fillRect(764,204,25,3);
  ctx.strokeStyle=active?'#ff8fab':'#6c829b';ctx.lineWidth=4;ctx.beginPath();ctx.arc(820,193,14,0,Math.PI*2);ctx.stroke();ctx.beginPath();ctx.moveTo(831,204);ctx.lineTo(842,215);ctx.stroke();
  if(active){ctx.globalAlpha=.3+pulse*.5;ctx.strokeStyle=state.activeReview.outcome==='fail'?'#ff7096':'#a6f750';ctx.lineWidth=3;ctx.strokeRect(748,174,60,48);ctx.globalAlpha=1}
}

function drawOfficeMascot(now){
  const x=68+Math.sin(now/2800)*28,y=520+Math.sin(now/180)*1.5,tail=Math.sin(now/160)*5;
  ctx.fillStyle='rgba(0,0,0,.25)';ctx.beginPath();ctx.ellipse(x,y+14,24,6,0,0,Math.PI*2);ctx.fill();
  ctx.strokeStyle='#f7b8c8';ctx.lineWidth=6;ctx.beginPath();ctx.moveTo(x-17,y+3);ctx.quadraticCurveTo(x-30,y-8+tail,x-20,y-18);ctx.stroke();
  ctx.fillStyle='#ffd2dc';ctx.fillRect(x-17,y-4,34,18);ctx.fillRect(x-12,y-19,25,20);ctx.beginPath();ctx.moveTo(x-12,y-17);ctx.lineTo(x-7,y-28);ctx.lineTo(x-2,y-18);ctx.fill();ctx.beginPath();ctx.moveTo(x+3,y-18);ctx.lineTo(x+9,y-28);ctx.lineTo(x+13,y-16);ctx.fill();
  ctx.fillStyle='#4d3b55';ctx.fillRect(x-6,y-11,3,3);ctx.fillRect(x+6,y-11,3,3);ctx.fillRect(x+1,y-6,3,2);ctx.fillStyle='#ff8fab';ctx.fillRect(x-10,y-6,4,2);ctx.fillRect(x+10,y-6,4,2);
  ctx.font='800 7px monospace';roundedRect(x-20,y+19,42,12,5,'rgba(8,16,30,.75)');ctx.fillStyle='#ffd9e4';ctx.fillText('MOCHI',x-12,y+28);
}

function drawReviewLink(now){
  const review=state.activeReview;if(!review)return;const reviewer=actor(review.reviewer_id||review.agent_id),target=actor(review.target_id);if(!reviewer||!target)return;
  const color=review.outcome==='fail'?'#ff7096':review.outcome==='pass'?'#a6f750':'#ffd166';ctx.save();ctx.strokeStyle=color;ctx.lineWidth=2;ctx.setLineDash([5,5]);ctx.lineDashOffset=-(now/45)%10;ctx.beginPath();ctx.moveTo(reviewer.x,reviewer.y-18);ctx.quadraticCurveTo(765,130,target.x,target.y-18);ctx.stroke();ctx.restore();
  const x=(reviewer.x+target.x)/2,y=(reviewer.y+target.y)/2-24;ctx.fillStyle='#f8fbff';ctx.fillRect(x-9,y-12,18,24);ctx.fillStyle=color;ctx.fillRect(x-5,y-7,10,2);ctx.fillRect(x-5,y-1,8,2);ctx.strokeStyle=color;ctx.strokeRect(x-10,y-13,20,26);
}

function drawOffice(now){
  ctx.clearRect(0,0,LOGICAL_CANVAS_WIDTH,LOGICAL_CANVAS_HEIGHT);ctx.fillStyle='#101b31';ctx.fillRect(0,0,LOGICAL_CANVAS_WIDTH,LOGICAL_CANVAS_HEIGHT);
  for(let y=60;y<560;y+=32){for(let x=0;x<920;x+=32){ctx.fillStyle=((x+y)/32)%2?'#1b304c':'#172943';ctx.fillRect(x,y,32,32)}}
  drawCuteDecor(now);drawZone(25,85,300,350,'EVIDENCE · SHARED','#235b75');drawZone(335,85,210,350,'ANALYSIS','#286143');drawZone(535,285,170,235,'DOCUMENT','#594b80');drawZone(700,285,195,235,'QUALITY','#783c54');
  drawWhiteboard();drawMeetingTable();drawQualityStation(now);drawCabinet();for(const a of state.actors.values())drawDesk(a);for(const a of state.actors.values())drawAvatar(a,now);drawReviewLink(now);drawHandoffDocument(now);drawOfficeMascot(now);
}
function drawZone(x,y,w,h,label,color){ctx.globalAlpha=.35;roundedRect(x,y,w,h,12,color,'#476183');ctx.globalAlpha=1;ctx.fillStyle='#83a2c9';ctx.font='700 10px monospace';ctx.fillText(label,x+10,y+17)}
function drawWhiteboard(){roundedRect(620,22,245,84,7,'#e9f3e5','#7390a4');ctx.fillStyle='#26415b';ctx.font='800 11px monospace';ctx.fillText('MISSION WHITEBOARD',640,43);ctx.fillStyle='#ef665e';ctx.fillRect(642,57,55,8);ctx.fillStyle='#57b9db';ctx.fillRect(706,57,78,8);ctx.fillStyle='#89cb63';ctx.fillRect(642,73,105,8);ctx.fillStyle='#f0ba52';ctx.fillRect(755,73,82,8)}
function drawMeetingTable(){ctx.fillStyle='rgba(4,10,20,.25)';ctx.beginPath();ctx.ellipse(460,346,95,38,0,0,Math.PI*2);ctx.fill();ctx.fillStyle='#795839';ctx.beginPath();ctx.ellipse(460,330,88,34,0,0,Math.PI*2);ctx.fill();ctx.strokeStyle='#bd8a55';ctx.lineWidth=4;ctx.stroke();ctx.fillStyle='#cbd6e2';ctx.fillRect(448,317,24,18)}
function drawCabinet(){roundedRect(822,370,70,120,5,'#425978','#7f9ab9');ctx.fillStyle='#20334f';for(let y=389;y<470;y+=27){ctx.fillRect(832,y,50,18);ctx.fillStyle='#8ca2bd';ctx.fillRect(854,y+7,8,3);ctx.fillStyle='#20334f'}ctx.fillStyle='#a6f750';ctx.font='800 9px monospace';ctx.fillText('FILING',834,482)}
function drawDesk(a){
  if(a.layer==='manager')return;ctx.globalAlpha=.68;ctx.fillStyle='#5b4050';ctx.fillRect(a.homeX-30,a.homeY+18,60,18);ctx.fillStyle='#b07966';ctx.fillRect(a.homeX-34,a.homeY+14,68,8);
  ctx.fillStyle='#223751';ctx.fillRect(a.homeX-16,a.homeY+4,25,14);ctx.fillStyle='#9ee7ff';ctx.fillRect(a.homeX-13,a.homeY+7,19,8);ctx.fillStyle='#ffef9d';ctx.fillRect(a.homeX-5,a.homeY+10,4,3);
  ctx.fillStyle='#f7d6a5';ctx.fillRect(a.homeX+18,a.homeY+7,8,9);ctx.fillStyle='#ff9fbd';ctx.fillRect(a.homeX+17,a.homeY+5,10,3);ctx.globalAlpha=1;
}

function actorVariant(id){return [...String(id)].reduce((sum,ch)=>sum+ch.charCodeAt(0),0)%5}
function drawPixelHeart(x,y,color){ctx.fillStyle=color;ctx.fillRect(x-5,y,4,4);ctx.fillRect(x+1,y,4,4);ctx.fillRect(x-7,y+3,14,4);ctx.fillRect(x-4,y+7,8,3);ctx.fillRect(x-1,y+10,2,2)}
function drawSparkle(x,y,color){ctx.fillStyle=color;ctx.fillRect(x-1,y-6,3,13);ctx.fillRect(x-6,y-1,13,3);ctx.fillStyle='#fff';ctx.fillRect(x,y,1,1)}


const statusColors={idle:'#8aa0bd',assigned:'#51d7ff',queued:'#ffd166',working:'#a6f750',writing:'#b8a9ff',done:'#8ee75b',meeting:'#51d7ff',handoff:'#ff8fab',rework:'#ffad66',blocked:'#ff5964',submission:'#f15bb5',inspecting:'#ffd166',reviewing:'#ffb3ca'};

function drawAvatarAccessory(a,x,y,now){
  const cap=a.capability||'';ctx.lineWidth=2;
  if(cap==='orchestrate'){ctx.fillStyle='#ffe075';ctx.fillRect(x-10,y-33,20,5);ctx.fillRect(x-9,y-39,4,7);ctx.fillRect(x-2,y-42,4,10);ctx.fillRect(x+5,y-39,4,7)}
  else if(cap.includes('collect')){ctx.strokeStyle='#fff0a8';ctx.beginPath();ctx.arc(x+15,y+2,6,0,Math.PI*2);ctx.stroke();ctx.beginPath();ctx.moveTo(x+19,y+7);ctx.lineTo(x+24,y+13);ctx.stroke()}
  else if(cap.includes('summar')){ctx.fillStyle='#fff2a8';ctx.fillRect(x-14,y+2,12,13);ctx.fillStyle='#ff8fab';ctx.fillRect(x-8,y+2,2,13)}
  else if(cap.includes('technical')){ctx.strokeStyle='#dff8ff';ctx.strokeRect(x-10,y-16,8,6);ctx.strokeRect(x+2,y-16,8,6);ctx.beginPath();ctx.moveTo(x-2,y-13);ctx.lineTo(x+2,y-13);ctx.stroke()}
  else if(cap.includes('legal')){ctx.fillStyle='#fff0a8';ctx.fillRect(x+13,y+4,12,10);ctx.fillStyle='#9c6c56';ctx.fillRect(x+16,y+1,6,4)}
  else if(cap.includes('write')){ctx.strokeStyle='#ffe075';ctx.lineWidth=4;ctx.beginPath();ctx.moveTo(x+15,y-2);ctx.lineTo(x+24,y+10);ctx.stroke();ctx.fillStyle='#ff8fab';ctx.fillRect(x+13,y-5,4,5)}
  else if(cap.includes('risk')){ctx.fillStyle='#ff8fab';ctx.beginPath();ctx.moveTo(x+13,y-2);ctx.lineTo(x+24,y+2);ctx.lineTo(x+21,y+13);ctx.lineTo(x+13,y+17);ctx.fill();ctx.fillStyle='#fff';ctx.fillRect(x+17,y+3,3,8);ctx.fillRect(x+14,y+6,9,3)}
  else if(cap.includes('synth')){drawSparkle(x+19,y+3,'#ffe075')}
  else if(cap.includes('coordinate')){ctx.strokeStyle='#b9f2ff';ctx.beginPath();ctx.arc(x,y-15,15,Math.PI,Math.PI*2);ctx.stroke();ctx.fillStyle='#b9f2ff';ctx.fillRect(x+13,y-16,4,8)}
}

function drawAvatar(a,now){
  const energetic=a.move||['working','writing','inspecting'].includes(a.status),bob=energetic?Math.sin(now/105+a.x)*2:Math.sin(now/650+a.x)*.6,x=Math.round(a.x),y=Math.round(a.y+bob),v=actorVariant(a.id),step=a.move?Math.sin(now/70)>0:0;
  ctx.fillStyle='rgba(0,0,0,.3)';ctx.beginPath();ctx.ellipse(x,y+25,19,6,0,0,Math.PI*2);ctx.fill();
  ctx.fillStyle='#eef5ff';ctx.fillRect(x-12,y+17+(step?1:0),9,7);ctx.fillRect(x+3,y+17+(step?0:1),9,7);
  ctx.fillStyle=a.color;ctx.fillRect(x-12,y-4,24,23);ctx.fillStyle='rgba(255,255,255,.32)';ctx.fillRect(x-9,y-2,18,4);ctx.fillStyle='#fff7e8';ctx.fillRect(x-4,y-4,8,5);
  const skin=['#ffd3b6','#f5c49f','#f1b997','#ffd8c2','#dba982'][v];roundedRect(x-15,y-29,30,27,7,skin,'#47394f');
  const hair=['#51405d','#31445f','#6a473d','#40334b','#72543f'][v];ctx.fillStyle=hair;ctx.fillRect(x-14,y-29,28,7);ctx.fillRect(x-15,y-24,4,10);if(v%2===0)ctx.fillRect(x+10,y-24,5,7);if(v===1){ctx.fillRect(x-12,y-34,7,7);ctx.fillRect(x+5,y-34,7,7)}
  if(a.status==='done'){ctx.fillStyle='#3c3044';ctx.fillRect(x-8,y-15,6,2);ctx.fillRect(x+3,y-15,6,2)}else{ctx.fillStyle='#302b3c';ctx.fillRect(x-8,y-17,4,5);ctx.fillRect(x+4,y-17,4,5);ctx.fillStyle='#fff';ctx.fillRect(x-7,y-16,1,1);ctx.fillRect(x+5,y-16,1,1)}
  ctx.fillStyle='#ff8f9f';ctx.fillRect(x-12,y-11,5,2);ctx.fillRect(x+7,y-11,5,2);ctx.fillStyle='#704456';if(a.status==='blocked'){ctx.fillRect(x-3,y-8,7,2)}else{ctx.fillRect(x-2,y-8,5,2);ctx.fillRect(x-1,y-6,3,1)}
  drawAvatarAccessory(a,x,y,now);
  const sc=statusColors[a.status]||statusColors.idle;ctx.fillStyle=sc;ctx.beginPath();ctx.arc(x+17,y-28,6,0,Math.PI*2);ctx.fill();ctx.strokeStyle='#0c1526';ctx.lineWidth=2;ctx.stroke();
  if(a.status==='done')drawPixelHeart(x+23,y-42,'#ff8fab');else if(['working','writing'].includes(a.status))drawSparkle(x-21,y-29,'#fff0a8');else if(a.status==='queued'){ctx.fillStyle='#ffe28a';ctx.fillRect(x-23,y-32,3,3);ctx.fillRect(x-18,y-37,4,4);ctx.fillRect(x-11,y-41,5,5)}else if(a.status==='blocked'){ctx.fillStyle='#7de0ff';ctx.fillRect(x+18,y-17,4,7)}else if(a.status==='inspecting'){ctx.strokeStyle='#ffe075';ctx.lineWidth=3;ctx.beginPath();ctx.arc(x-19,y-15,7,0,Math.PI*2);ctx.stroke();ctx.beginPath();ctx.moveTo(x-14,y-10);ctx.lineTo(x-9,y-5);ctx.stroke()}
  ctx.font='800 9px sans-serif';const name=`${a.name} · ${a.role}`,tw=ctx.measureText(name).width;roundedRect(x-tw/2-6,y+30,tw+12,17,7,'rgba(7,15,29,.9)',a.status==='inspecting'?'#ffd166':'');ctx.fillStyle='#f5f8ff';ctx.fillText(name,x-tw/2,y+42);if(a.bubble&&a.bubbleUntil>now)drawBubble(x,y-49,a.bubble);
}

function drawBubble(x,y,text){
  ctx.font='700 9px sans-serif';const clean=String(text).slice(0,34),w=Math.min(220,ctx.measureText(clean).width+24),bx=Math.max(4,Math.min(LOGICAL_CANVAS_WIDTH-w-4,x-w/2));roundedRect(bx,y-23,w,21,9,'rgba(255,249,253,.98)','#ffb3cc');ctx.fillStyle='#362b45';ctx.fillText(clean,bx+12,y-9);ctx.fillStyle='#fff9fd';ctx.beginPath();ctx.moveTo(x-5,y-3);ctx.lineTo(x+5,y-3);ctx.lineTo(x,y+5);ctx.fill();
}
function drawHandoffDocument(now){const h=state.activeHandoff;if(!h||!h.visible)return;const from=actor(h.from_id),to=actor(h.to_id);if(!from||!to)return;const pulse=(Math.sin(now/100)+1)/2;const x=from.x+(to.x-from.x)*(.35+pulse*.3),y=from.y-12;ctx.fillStyle=h.red?'#ff6b7d':'#eff6ff';ctx.fillRect(x-8,y-10,16,20);ctx.fillStyle=h.red?'#fff':'#58708f';ctx.fillRect(x-5,y-6,10,2);ctx.fillRect(x-5,y-1,8,2);ctx.strokeStyle=h.red?'#ffb1ba':'#51d7ff';ctx.strokeRect(x-9,y-11,18,22)}

els.startRun.addEventListener('click',()=>startRun('demo'));els.pauseRun.addEventListener('click',togglePause);els.openSettings.addEventListener('click',()=>{renderLiveAuthSettings();els.settingsDialog.showModal();});els.saveSettings.addEventListener('click',()=>{document.querySelectorAll('[data-agent-model]').forEach(select=>state.assignments[select.dataset.agentModel]=select.value);for(const [id,model] of Object.entries(state.assignments)){const a=actor(id);if(a)a.model=model}});els.playbackSpeed.addEventListener('change',()=>state.speed=Number(els.playbackSpeed.value)||4);
els.authorizeLiveRun.addEventListener('click',authorizeLiveExecution);els.liveAccessPassword.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();authorizeLiveExecution()}});
document.querySelectorAll('input[name="liveCredentialMode"]').forEach(input=>input.addEventListener('change',()=>{state.liveCredentialMode=selectedCredentialMode();renderSettings();renderLiveRunAvailability()}));
[els.personalOpenRouterKey,els.personalHuggingFaceKey].forEach(input=>input.addEventListener('input',()=>{renderSettings();renderLiveRunAvailability()}));
els.openLiveRun.addEventListener('click',openLiveRunConfirmation);
els.confirmLiveRun.addEventListener('click',runLiveFromConfirmation);
els.demoFromLiveDialog.addEventListener('click',runDemoFromConfirmation);
els.cancelLiveRun.addEventListener('click',closeLiveRunConfirmation);
els.closeLiveRun.addEventListener('click',closeLiveRunConfirmation);
els.liveRunDialog.addEventListener('click',event=>{if(event.target===els.liveRunDialog)closeLiveRunConfirmation()});
els.artifactList.addEventListener('click',event=>{const button=event.target.closest('[data-artifact-id]');if(button)openArtifact(button.dataset.artifactId)});
els.artifactDialog.addEventListener('click',event=>{const link=event.target.closest('[data-artifact-link]');if(link)openArtifact(link.dataset.artifactLink);else if(event.target===els.artifactDialog)els.artifactDialog.close()});
els.closeArtifact.addEventListener('click',()=>els.artifactDialog.close());
els.copyArtifact.addEventListener('click',copyActiveArtifact);
els.artifactDialog.addEventListener('close',()=>{state.activeArtifactId=null});

loadConfig();requestAnimationFrame(playbackLoop);
