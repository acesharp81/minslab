'use strict';
const API = '/poc/home/api';
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
const num = v => v == null ? '미확보' : Number(v).toLocaleString('ko-KR');
const baseText = r => r.date_precision === 'YEAR' ? r.base_date.slice(0,4) + '년 연간 계획' : r.base_date;
const revisionText = r => `<p>계획호수 ${num(r.planned_units)}${r.planned_units == null ? '' : '호'} · ${esc(r.stage_label)} · 공정률 ${r.progress_pct == null ? '미확보' : num(r.progress_pct) + '%'}</p>`;
const sourceNames = new Map();
const warningNames = {POLICY_PLAN_NOT_ACTUAL:'정책 계획 · 실적 미확인',JOINT_QUANTITY_UNALLOCATED:'여러 지구 합계 · 개별 물량 미확보',AGENCY_PLAN_NOT_ACTUAL:'기관 계획 · 실적 미확인',MUNICIPALITY_UNVERIFIED:'시군구 연결 검토',MAPPING_REVIEW:'정책 귀속 검토 필요', STALE_SOURCE:'원천 기준일 30일 초과', PAST_PLAN_UNVERIFIED:'지난 예정일 · 실제 이행 미확인', UNITS_UNKNOWN:'개별 물량 미확보', TOTAL_CONFLICT:'총세대수 불일치', SUPPLY_EXCEEDS_TOTAL:'공급호수 > 총세대수', MISSING_IN_LATEST_SOURCE:'최신 원천에서 미발견', MULTI_SITE_CONTRACT:'복수 현장 계약 · 지역별 물량 확인', USE_INSPECTION_FIELD_REVIEW:'사용검사 필드 의미 검토 · 준공으로 확정하지 않음', ZERO_UNITS_REVIEW:'원천 세대수 0 · 용도·집계 기준 확인', ADDRESS_APPROXIMATE:'주소 일부를 정리해 검색 · 사업 경계 확인 필요', GEOCODE_NOT_FOUND:'주소 좌표 미발견'};
const labels = {'supply-conditions':'지역여건',overview:'공급현황 지도','annual-supply':'연도별 공급 비교',area:'인구·가구·고용 분석','policy-progress':'정책 추진현황','program-progress':'프로그램 추진현황',history:'정책 흐름·과거 자료', projects:'사업 추진현황', tree:'정책-프로그램-사업 연결', sources:'출처와 수집현황', 'project-collection':'사업별 수집연계',manual:'사용법',requirements:'요구사항정의'};
labels['data-integrity']='데이터 정합성 확인';
warningNames.PHOTO_MONTH_BASIS='사진 원본의 현장 기준월 · 등록일과 구분';
warningNames.PLAN_NOT_ACTUAL='입주계획 · 실제 입주실적 아님';
warningNames.ANNOUNCEMENT_NOT_OCCUPANCY='공고 공급호수 · 준공·실입주량 아님';
warningNames.SOURCE_TOTAL_MISMATCH='원천의 전국 총계와 상세행 합계 불일치';
warningNames.ADDRESS_MISSING='주소 미제공 · 지구명으로 시도 범위 확인';
warningNames.ZERO_STOCK_UNITS_UNVERIFIED='원천 세대수 0 · 실제 공급 0호로 해석하지 않음';
warningNames.AGENCY_STOCK_NOT_SUPPLY='기존 관리·매입 재고 · 신규 공급실적 아님';
warningNames.STAGE_UNVERIFIED='진행 단계 미확인';
warningNames.ZERO_PLANNED_UNITS_UNVERIFIED='예정 세대수 0 · 실제 공급 0호 아님';
warningNames.UNCONFIRMED_UNITS='준공예정 세대수 미확정 · 실적 아님';
warningNames.PARCEL_LOT_MISSING='원천 대지위치에 지번 누락 · 허가 관리번호로만 연결';
Object.assign(warningNames, {SH_PLAN_NOT_ACTUAL:'SH 계획 물량 · 공급 실적 미확인', SH_HISTORY_SNAPSHOT:'과거 공개본 · 다른 공개본과 물량 중복 합산 금지', SH_OLD_STATUS:'과거 기준일의 추진현황 · 현재 상태 확인 필요', SH_SCHEDULE_NOT_ACTUAL:'공급 예정월 · 실제 공급·지연 확인 필요', REGISTER_STOCK_NOT_SUPPLY:'건축물대장 기존 재고 · 신규 공급 실적과 구분', USE_APPROVAL_NOT_MOVE_IN:'건축물 사용승인일 · 주택법 사용검사·실입주와 구분', NOTICE_DETAIL_UNITS_REQUIRED:'공고 상세 세대수·정정·재공고 중복 확인 필요', REGIONAL_TOTAL_NOT_POLICY_ACTUAL:'시도 전체 통계 · 개별 정책 실적 합산 제외'});
const state = {view:'overview', page:1, total:0, policies:[], sources:[], admin:false, generation:0, detailGeneration:0};
const empty = text => `<div class="empty">${esc(text)}</div>`;
const badge = status => `<span class="badge ${status === 'CONFIRMED' ? 'confirmed' : status === 'RELEASED' ? 'neutral' : 'review'}">${status === 'CONFIRMED' ? '담당자 확정' : status === 'RELEASED' ? '연결 해제' : '확인 필요'}</span>`;
function safeUrl(value) {try {const u = new URL(value); return u.protocol === 'https:' ? u.href : '#';} catch {return '#';}}
function timeText(value) {return value ? new Date(value).toLocaleString('ko-KR', {timeZone:'Asia/Seoul', dateStyle:'short', timeStyle:'short'}) : '미수집';}
// Share simultaneous identical reads; never reuse a response after an edit.
const pendingReads = new Map();
async function request(path, options = {}) {
  // Active menus are restricted to 9·7; raw statistics and source inventories retain their own scope.
  const scopePaths=new Set(['/overview','/projects','/mappings','/policy-monitor','/policy-metrics','/map/dashboard','/tree','/history','/roadmap','/annual-supply','/project-collection','/stage-evidence']);
  if((!options.method||options.method==='GET')&&scopePaths.has(path.split('?')[0])){const [base,query]=path.split('?');const params=new URLSearchParams(query||'');params.set('policy_id','POL_2025_0907');path=base+'?'+params;}
  const share = (!options.method || options.method === 'GET') && !options.signal;
  if (share && pendingReads.has(path)) return pendingReads.get(path);
  const task = (async()=>{
    const response = await fetch(API + path, {credentials:'same-origin', ...options});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `조회 실패 (${response.status})`);
    if(path.split('?')[0]==='/policies')data.items=data.items.filter(p=>p.policy_id==='POL_2025_0907');
    return data;
  })();
  if(share)pendingReads.set(path,task);
  try{return await task;}finally{if(share && pendingReads.get(path)===task)pendingReads.delete(path);}
}

function query() {
  const params = new URLSearchParams();
  for (const [id, key] of [['as-of','as_of_date'],['region','region'],['policy','policy_id'],['search','q'],['source-filter','source_id'],['stage-filter','stage'],['mapping-filter','mapping_status']]) {
    if ($(id).value) params.set(key, $(id).value);
  }
  return params;
}
function table(rows, small = false) {
  if (!rows.length) return empty('선택한 조건의 사업 후보가 없습니다. 수집 원천과 기준일을 확인하세요.');
  return `<table><thead><tr><th>사업 / 지구</th><th>지역</th><th>계획호수</th><th>진행 단계</th><th>공정률</th>${small ? '' : '<th>원천 기준일</th>'}<th>정책 연결</th></tr></thead><tbody>${rows.map(row => `<tr><td><button class="project-name" data-project="${esc(row.id)}">${esc(row.name)}</button><small class="row-sub">${esc(sourceNames.get(row.source_id) || row.source_id)} · ${esc(row.program)}</small></td><td>${esc(row.region.replace('특별시','').replace('도',''))}<small class="row-sub">${esc(row.municipality)}</small></td><td class="numeric">${num(row.planned_units)}${row.planned_units == null ? '' : '호'}</td><td><span class="badge neutral">${esc(row.stage_label)}</span></td><td>${row.progress_pct == null ? '<span class="badge review" title="실제 공정률 원천 미입수 · 0%나 미착수 확정이 아님">미입수</span>' : `<div class="progress-inline"><span>${num(row.progress_pct)}%</span><progress max="100" value="${Number(row.progress_pct)}" aria-label="공정률"></progress></div>${row.progress_date?`<small class="row-sub">${esc(row.progress_date_precision==='MONTH'?row.progress_date.slice(0,7):row.progress_date)} 기록</small>`:''}`}</td>${small ? '' : `<td>${esc(baseText(row))}<small class="row-sub">${row.source_age_days == null ? '연간 계획 · 갱신일 미제공' : `${num(row.source_age_days)}일 경과`}</small></td>`}<td>${badge(row.mapping.status)}</td></tr>`).join('')}</tbody></table>`;
}
function renderOverview(overview, rows, roadmap) {
  const cards = [['수집 사업 후보',overview.project_count,'건','같은 사업이 원천별로 존재할 수 있음','▤'],['향후 목표 확보',roadmap.future_target_count,'건',`향후 ${roadmap.horizon}년 · 원천 예정과 관리자 목표`,'⑂'],['확대 API 데이터',overview.api_sample_count,'건','청약·인허가·주소 조회 · 정책 연결 검토 전','⌖'],['일정 미확보',roadmap.no_schedule_count,'건','사업별 연도 목표 확인 필요','◎']];
  $('metrics').innerHTML = cards.map(([title, value, unit, note, icon]) => `<article class="metric"><div class="metric-label">${title}<span class="metric-icon">${icon}</span></div><div class="metric-value">${num(value)}<small>${unit}</small></div><div class="metric-note">${note}</div></article>`).join('');
  $('policy-cards').innerHTML = state.policies.length ? state.policies.map(p => `<div class="policy-row"><div class="policy-date">${esc(p.announced_at.slice(0,4))}<strong>${esc(p.announced_at.slice(5).replace('-','.'))}</strong></div><div class="policy-info"><h3><a href="${esc(safeUrl(p.evidence_url))}" target="_blank" rel="noopener noreferrer">${esc(p.name)} ↗</a></h3><p>${esc(p.metric)}</p><span class="policy-target">${num(p.target_units)}호 <small>${esc(p.target_scope)} · 서울·경기 배정량과 구분</small></span></div><span class="badge review">유효상태 검토</span></div>`).join('') : empty('정책 원문을 수집 중입니다.');
  const maximum = Math.max(1, ...Object.values(overview.regions));
  $('region-summary').innerHTML = `<div class="region-block">${['서울특별시','경기도'].map(region => `<div class="region-line"><div><span>${region}</span><strong>${num(overview.regions[region] || 0)} <small>건</small></strong></div><progress value="${overview.regions[region] || 0}" max="${maximum}" aria-label="${region} 사업 후보 수"></progress></div>`).join('')}</div>`;
  $('program-summary').innerHTML = `<div class="programs"><p class="programs-title">프로그램별 후보 기록</p>${Object.entries(overview.programs).sort((a,b) => b[1]-a[1]).slice(0,5).map(([k,v]) => `<div class="program-line"><span>${esc(k)}</span><span>${num(v)}건</span></div>`).join('')}</div>`;
  $('recent-projects').innerHTML = table(rows.slice(0,5), true);
  $('collection-footnote').textContent = overview.first_collection_date ? `최초 수집 ${overview.first_collection_date} · 범위 기준선 검토 중` : '초기 데이터 수집 중';
  // Historical views never reconstruct information collected after that date.
  $('as-of').min = overview.first_collection_date || '';
}
function renderSourceVolumes(data) {
  const root=$('source-volume-summary');root.setAttribute('aria-busy','false');
  for(const node of root.querySelectorAll('[data-source-volume]')){
    const key=node.dataset.sourceVolume,unit=key==='linked_records'?'건':'개';
    node.title=data.definitions[key]+(key==='linked_records'?' · 오늘: '+data.definitions.today_linked_records:' · '+data.definitions.today);
    if(key!=='sources')node.querySelector('strong').innerHTML=num(data.current[key])+'<small>'+unit+'</small>';
    else {node.title='등록된 공식 수집 경로 · API, 파일 및 홈페이지 수집 포함';node.dataset.acquired=data.current[key];}
    node.querySelector('p b').textContent=num(data.today[key]);
  }
  $('source-volume-status').hidden=false;
  $('source-volume-status').textContent='집계 시각 '+timeText(data.generated_at)+(data.refreshing?' · 최신 집계 갱신 중':data.refresh_failed?' · 최신 집계 재시도 예정':'');
  $('source-volume-details').querySelector('summary').textContent='소스 유형별 자세히 보기 · '+data.as_of_date+' 기준';
  const cells=r=>'<td class="source-volume-number">'+num(r.source_count)+'</td><td class="source-volume-number">'+num(r.records)+'</td><td class="source-volume-number">'+num(r.columns)+'</td><td class="source-volume-number source-volume-emphasis">'+num(r.extracted_cells)+'</td><td class="source-volume-number source-volume-today">'+num(r.today_extracted_cells)+'</td><td class="source-volume-number">'+num(r.linked_records)+'</td>';
  const totals=data.types.reduce((v,r)=>{for(const k of ['source_count','records','columns','extracted_cells','today_extracted_cells','linked_records'])v[k]=(v[k]||0)+r[k];return v;},{});
  const breakdown=$('source-volume-breakdown'),opened=new Set([...breakdown.querySelectorAll('details[open][data-volume-type]')].map(n=>n.dataset.volumeType)),scroll=breakdown.scrollTop;
  const markup='<table><caption class="sr-only">소스 유형별 현재 수집·추출·연결 현황과 오늘 수집량</caption><thead><tr><th scope="col">소스 데이터 유형</th><th scope="col">출처 수</th><th scope="col">수집 행</th><th scope="col">컬럼 합계</th><th scope="col">추출 데이터<br>(행 × 컬럼)</th><th scope="col">오늘 수집량<br>(행 × 컬럼)</th><th scope="col">연결 데이터<br>(건)</th></tr></thead><tbody>'+data.types.map(r=>'<tr><th scope="row">'+esc(r.label)+'<span class="source-type-description">'+esc(r.description||'')+'</span>'+((r.sources||[]).length?'<details class="source-type-examples" data-volume-type="'+esc(r.label)+'"'+(opened.has(r.label)?' open':'')+'><summary>실제 수집 자료 '+num(r.sources.length)+'개 보기</summary><ul>'+r.sources.map(s=>'<li><a href="'+esc(safeUrl(s.url))+'" target="_blank" rel="noopener noreferrer">'+esc(s.name)+' ↗</a></li>').join('')+'</ul></details>':'<small>현재 수집된 자료 없음</small>')+'</th>'+cells(r)+'</tr>').join('')+'</tbody><tfoot><tr><th scope="row">합계</th>'+cells(totals)+'</tr></tfoot></table>';
  if(breakdown.innerHTML!==markup){breakdown.innerHTML=markup;breakdown.scrollTop=scroll;}
}
async function loadSourceVolumes(version) {
  $('source-volume-summary').setAttribute('aria-busy','true');
  try{
    const data=await request('/source-summary');
    if(version!==state.generation||state.view!=='sources')return;
    if(data.current)renderSourceVolumes(data);
    else {$('source-volume-status').hidden=false;$('source-volume-status').textContent='수집 통계를 집계하고 있습니다. 완료하면 자동으로 표시됩니다.';}
    if(data.refreshing||!data.current)setTimeout(()=>{if(version===state.generation&&state.view==='sources')loadSourceVolumes(version);},5000);
  }catch(_){
    if(version!==state.generation||state.view!=='sources')return;
    $('source-volume-summary').setAttribute('aria-busy','false');$('source-volume-status').hidden=false;
    $('source-volume-status').textContent='통계 조회를 재시도합니다. 기존 집계값은 유지합니다.';
    setTimeout(()=>{if(version===state.generation&&state.view==='sources')loadSourceVolumes(version);},15000);
  }
}

function renderSources(sources) {
  const category=s=>s.authority==='NONOFFICIAL'?'NONOFFICIAL_WEB':!s.virtual&&s.data_type==='API'?'API':'OFFICIAL_WEB';
  const labels={API:'API 수집',OFFICIAL_WEB:'공식 웹 수집',NONOFFICIAL_WEB:'비공식 웹 수집'},order={API:0,OFFICIAL_WEB:1,NONOFFICIAL_WEB:2};
  sources=sources.slice().sort((a,b)=>order[category(a)]-order[category(b)]);
  const registry=sources.filter(s=>!s.virtual),apiCount=registry.filter(s=>s.data_type==='API').length;
  document.querySelector('[data-source-volume="sources"] strong').innerHTML=num(registry.length)+'<small>개</small>';
  $('source-registry-count').textContent='API '+num(apiCount)+'개 · 파일·웹 '+num(registry.length-apiCount)+'개';
  $('source-channel-summary').innerHTML=Object.entries(labels).map(([key,label])=>{const group=sources.filter(s=>category(s)===key),errors=group.filter(s=>s.status==='FAILED'),excluded=group.filter(s=>s.id==='ih_supply'&&s.manual_only&&!s.record_count),paths=group.filter(s=>!s.virtual).length,docs=group.filter(s=>s.virtual).length;return '<section class="source-channel-stat"><h2>'+label+'</h2><strong>'+num(group.length)+'<small>개</small></strong><p>'+(key==='API'?'등록 API 경로':key==='OFFICIAL_WEB'?'등록 파일·웹 경로 '+num(paths)+'개 · 문서 출처 '+num(docs)+'곳':'확보 문서 출처 '+num(docs)+'곳')+'</p>'+(errors.length||excluded.length?'<p class="source-channel-error" data-collector-errors="'+key+'">'+(errors.length?'수집 오류 '+errors.length+'개':'')+(excluded.length?' · iH '+excluded.length+'개 자동 수집 제외':'')+'</p>':'')+'</section>';}).join('');
  $('source-channel-summary').title='수집 목록의 항목 수입니다. 공식 웹에는 등록 파일·웹 경로와 별도 확보 문서 출처를 함께 표시하며 같은 기관이 여러 항목에 포함될 수 있습니다.';
  const groupTitle=(s,i)=>i&&category(sources[i-1])===category(s)?'':'<h3 class="source-authority-heading" data-authority="'+esc(s.authority||'UNKNOWN')+'" data-source-category="'+category(s)+'">'+labels[category(s)]+' <small>'+num(sources.filter(r=>category(r)===category(s)).length)+'개 항목</small></h3>';
  const statusNames = {SUCCESS:'수집 정상', REGISTERED:'문서 확보', FAILED:'수집 실패', RUNNING:'수집 중', NOT_COLLECTED:'수집 대기', INTERRUPTED:'수집 중단', CONNECTOR_PENDING:'연결 준비'};
  $('sources-list').innerHTML = sources.map((s,i) => `${groupTitle(s,i)}<article class="source-card${s.status === 'FAILED' ? ' source-collection-failed' : ''}" data-source-id="${esc(s.id)}"><div class="source-title"><h3 title="${esc(s.name)}">${esc(s.name)}</h3><span class="badge ${['SUCCESS','REGISTERED'].includes(s.status) ? 'confirmed' : s.status === 'FAILED' ? 'failed' : 'neutral'}">${statusNames[s.status] || esc(s.status)}</span><div class="source-operation-tags">${(s.operations?.tags||[]).map(t=>`<span class="source-operation-tag ${esc(t.kind)}">${esc(t.label)}</span>`).join('')}${s.operations?`<button type="button" class="source-operation-info" data-source-operations="${esc(s.id)}">수집·전처리 방식 ⓘ</button>`:""}</div></div><p><span class="source-kind-tag">${esc(s.data_type_label||'웹 자료')}</span> ${esc(s.org)} · ${esc(s.operations?.mode||(s.virtual?'수집·검토한 문서 원천':'수집 방식 확인 필요'))}</p><div class="source-data"><div><span>${s.virtual?'문서 기록 갱신':'마지막 정상 수집'}</span><strong>${timeText(s.virtual?s.last_recorded_at:s.last_success)}</strong></div><div><span>${s.virtual?'확보 문서 기록':s.collection_mode === 'TEST_SAMPLE' ? '테스트 표본' : s.collection_mode === 'MAP_LAYER' ? '공동주택용지 지구' : '정상 레코드'}</span><strong>${num(s.record_count)}건</strong></div></div>${(s.stats.source_base_date || s.stats.dataset_version) ? `<p>원천 자료 기준일 ${esc(s.stats.source_base_date || s.stats.dataset_version)} · 현재 실적과 구분</p>` : ''}${s.description?`<p>${esc(s.description)}</p>`:''}${s.error ? `<p>${esc(s.error)}</p>` : ''}<a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">${s.authority==='OFFICIAL'?'공식 원천 확인':'출처 확인'} ↗</a>${s.snapshots.length ? `<details data-source-snapshots="${esc(s.id)}"><summary>근거 snapshot ${s.snapshots.length}개 · SHA-256</summary><div class="source-snapshot-body"></div></details>` : ''}</article>`).join('');
  for(const element of $('sources-list').querySelectorAll('[data-source-snapshots]'))element.addEventListener('toggle',()=>{
    if(!element.open||element.dataset.loaded)return;
    const source=sources.find(s=>s.id===element.dataset.sourceSnapshots);
    element.querySelector('.source-snapshot-body').innerHTML=source.snapshots.map(m=>`<p><a href="${esc(safeUrl(m.url))}" target="_blank" rel="noopener noreferrer">수집 원문 ↗</a> · ${num(m.bytes)} bytes${m.credentials_removed?' · 인증정보 제거':''}</p><div class="hash">${esc(m.sha256)}</div>`).join('');
    element.dataset.loaded='true';
  });
  sources.forEach((source,index)=>{if(source.collection_mode==='HISTORY')document.querySelectorAll('.source-card')[index].querySelector('p').innerHTML='<span class="source-kind-tag">'+esc(source.data_type_label||'공개 파일')+'</span> '+esc(source.org)+' · 정책 기원부터 과거 원천 누적 수집';});
  $('sources-list').querySelectorAll('[data-source-operations]').forEach(button=>button.addEventListener('click',()=>{
    const source=sources.find(s=>s.id===button.dataset.sourceOperations),o=source?.operations;
    if(!o)return;
    const dialog=document.createElement('dialog');dialog.className='source-operation-dialog';
    dialog.setAttribute('aria-label',source.name+' 수집·전처리 방식');
    dialog.innerHTML='<form method="dialog"><button class="button secondary">닫기</button></form><h2>'+esc(source.name)+'</h2><div class="source-operation-tags">'+o.tags.map(t=>'<span class="source-operation-tag '+esc(t.kind)+'">'+esc(t.label)+'</span>').join('')+'</div><dl>'+[
      ['수집 주기',o.frequency+' · '+o.schedule_note],['새 파일·추가 게시물 감지',o.discovery],['항목 추출·정리',o.parser],['추출 보완',o.pdf],['수집·전처리의 수동 작업',o.manual],['수정·중복 처리',o.changes]
    ].filter(([,text])=>text).map(([title,text])=>'<div><dt>'+esc(title)+'</dt><dd>'+esc(text)+'</dd></div>').join('')+'</dl><p>자동 수집 태그는 실행 설정을 의미합니다. 마지막 정상 수집 시각·오류 및 조회 범위와 함께 확인하세요.</p>';
    document.body.append(dialog);dialog.addEventListener('close',()=>{dialog.remove();button.focus();});dialog.showModal();
  }));
  SourcePreview.attach($('sources-list'),sources);
  renderCollectionStatus(sources);
}
function renderProjectDataStatus(r) {
  const d=r.data_status;
  if(!d)return '';
  const moveIn=`<dt>입주 시작</dt><dd>${esc(d.move_in_start||'미확보')}</dd>`;
  return `<div class="detail-section"><h3>빈 항목 상태</h3><p>${esc(d.phase)}. 실제 미착수 확정 근거는 ${d.not_started_verified?'있음':'없음'}.</p><dl><dt>계획호수</dt><dd>${esc(d.planned_units)}</dd><dt>실제 공정률</dt><dd>${esc(d.progress)}</dd>${moveIn}<dt>실제 준공일</dt><dd>${esc(d.completion_date)}</dd><dt>예정 일정</dt><dd>${esc(d.schedule)}</dd></dl></div>`;
}
async function load() {
  const version = ++state.generation;
  if(!['project-collection','data-integrity','area','annual-supply','manual','requirements','supply-conditions','projects'].includes(state.view)){
    try{await ensureCatalogue();}catch(error){$('loading').hidden=true;$('error').hidden=false;$('error').textContent=error.message;return;}
    if(version!==state.generation)return;
  }
  $('view-update-notice').hidden=true;
  const params = query();
  const qs = params.toString();
  const reportParams=new URLSearchParams(params);reportParams.set('policy_id','POL_2025_0907');
  const reportQs=reportParams.toString();
  if(state.historyQuery!==qs){state.historyPage=1;state.historyQuery=qs;}
  const historyParams=new URLSearchParams(params);historyParams.set('page',state.historyPage);
  if($('history-year').value)historyParams.set('history_year',$('history-year').value);
  $('error').hidden = true;
  $('loading').hidden = !$('content').hidden;
  try {
    if(state.view==='supply-conditions'){state.workspaceOnly=true;$('content').hidden=false;SupplyConditions.visible();return;}
    if(['project-collection','data-integrity','area','annual-supply','manual','requirements'].includes(state.view)){
      // These workspaces own their requests. Do not queue the other menus'
      // large projections behind their initial render.
      state.workspaceOnly=true;$('content').hidden=false;return;
    }
    if(state.view==='overview'){
      const dashboard=await request('/map/dashboard?'+qs+'&'+HousingMap.query()+'&compact=true');
      if(version!==state.generation)return;
      state.workspaceOnly=true;$('content').hidden=false;
      HousingMap.render({districts:dashboard.districts},dashboard,dashboard);
      return;
    }
    if(state.view==='sources'){
      loadSourceVolumes(version);SourceYears.invalidate();
      const sources=await request('/sources');if(version!==state.generation)return;
      state.sources=sources.items;state.workspaceOnly=true;
      renderSources(sources.items);CollectionSchema.load(sources.items);$('content').hidden=false;return;
    }
    if(['policy-progress','program-progress'].includes(state.view)){
      // Policy workspaces do not need the million-row source browser or the
      // separate supply map before their own overview/chart can be displayed.
      Policy907.prepare();
      const [monitor,mappings,viewVersion]=await Promise.all([
        request('/policy-monitor?'+reportQs),request('/mappings?'+reportQs+'&compact=true'),request('/view-version?view='+state.view)]);
      if(version!==state.generation)return;
      state.viewVersion=viewVersion.version;
      state.workspaceOnly=true;
      PolicyReport.setData(monitor,mappings);PolicyDashboard.render(monitor);
      $('content').hidden=false;PolicyGeo3D.dataChanged();
      return;
    }
    // Load only this menu. Source-wide counts and maps must not block editors.
    state.workspaceOnly=true;
    if(state.view==='tree'){
      const mappings=await request('/mapping-workbench');
      if(version!==state.generation)return;
      MappingWorkbench.render(mappings);
    }else if(state.view==='history'){
      const historyData=await request('/history?'+historyParams);
      if(version!==state.generation)return;HistoryPanel.render(historyData);
    }else if(state.view==='projects'){
      $('content').hidden=false;$('loading').hidden=true;
      const viewVersion=await request('/view-version?view=projects');
      if(version!==state.generation)return;
      state.viewVersion=viewVersion.version;
      await ProjectWorkspace.load();
      if(version!==state.generation)return;
    }
    $('content').hidden=false;
    if(policyViews.has(state.view)&&state.view!=='projects')PolicyGeo3D.dataChanged();
  } catch (error) {
    if (version !== state.generation) return;
    $('error').textContent = error.message + ' 잠시 후 다시 조회해 주세요.';
    $('error').hidden = false;
  } finally {if (version === state.generation) $('loading').hidden = true;}
}
const policyViews = new Set(['policy-progress','program-progress','projects','history']);
const supplyViews = new Set(['overview','supply-conditions','annual-supply','area']);
const sourceViews = new Set(['sources','project-collection','data-integrity']);
function toggleNavGroup(group,open) {
  const button=document.querySelector(`[data-nav-group="${group}"]`);
  const children=$(button.getAttribute('aria-controls'));
  button.setAttribute('aria-expanded',String(open));children.hidden=!open;
}
function setView(view,options={}) {
  if(['validation','samples','keys'].includes(view))view='sources';
  if (!labels[view]) return;
  const previous=state.view;
  if(previous!==view){++state.generation;state.viewVersion=null;$('view-update-notice').hidden=true;}
  state.view=view;
  for (const pane of document.querySelectorAll('.pane')) pane.hidden = pane.id !== 'pane-' + view && !(pane.id==='pane-policy-geo'&&policyViews.has(view)&&view!=='projects');
  const category=supplyViews.has(view)?'supply':policyViews.has(view)?'policy':view==='tree'||sourceViews.has(view)?'data':'manual';
  if(category==='supply')toggleNavGroup('supply',true);
  if(category==='policy')toggleNavGroup('policy',true);
  if(category==='data')toggleNavGroup('data',true);
  if(category==='manual')toggleNavGroup('manual',true);
  for(const nav of document.querySelectorAll('#home-main-nav .nav-item')){
    const active=nav.dataset.view===view || (category==='supply'&&view!=='supply-conditions'&&nav.dataset.view==='overview') ||
      (category==='policy'&&nav.dataset.view==='policy-progress'&&view==='history') ||
      (category==='data'&&nav.dataset.view==='sources'&&sourceViews.has(view)&&!['project-collection','data-integrity'].includes(view));
    nav.classList.toggle('active',active);
    if(active&&nav.dataset.view===view)nav.setAttribute('aria-current','page');else nav.removeAttribute('aria-current');
  }
  for(const button of document.querySelectorAll('#home-main-nav .nav-group-toggle'))button.classList.toggle('group-active',button.dataset.navGroup===category);
  $('supply-subnav').hidden=category!=='supply'||view==='supply-conditions';
  for(const button of document.querySelectorAll('.home-subnav [data-view]')){
    const active=button.dataset.view===view;button.classList.toggle('active',active);button.setAttribute('aria-current',active?'page':'false');
  }
  $('page-label').textContent=labels[view];ReportMD.syncView(view);
  document.body.classList.toggle('source-summary-view',view==='sources');$('source-volume-summary').hidden=view!=='sources';$('source-volume-details').hidden=view!=='sources';
  document.body.classList.toggle('home-map-view',view==='overview');
  document.body.classList.toggle('user-guide-view',view==='manual');
  document.body.classList.toggle('policy-geo-view',policyViews.has(view)&&view!=='projects');
  document.body.classList.toggle('project-workspace-view',view==='projects');
  if(previous==='projects'&&view!=='projects')ProjectWorkspace.hidden();
  document.body.classList.toggle('policy-summary-view',view==='policy-progress');
  document.body.classList.toggle('policy-compact-view',['policy-progress','program-progress'].includes(view));
  $('report-policy-picker').hidden=!['policy-progress','program-progress'].includes(view);
  $('report-program-picker').hidden=view!=='program-progress';
  $('policy-map-controls').hidden=!['policy-progress','program-progress'].includes(view);
  document.querySelector('.policy-geo-toolbar>div:first-child small').textContent=view==='policy-progress'?'POLICY REGIONAL VIEW':'POLICY GEO 3D';
  document.querySelector('.policy-geo-toolbar h2').textContent=view==='policy-progress'?'지역별 정책 공급 분포':'정책·프로그램·사업 지역 그래프';
  $('policy-geo-map').setAttribute('aria-label',view==='policy-progress'?'정책현황 시군구 공급 분포도':'정책현황 3D 지역 지도');
  if(view==='overview')HousingMap.visible();else if(previous==='overview')HousingMap.hidden();
  document.querySelector('.filterbar').hidden=['supply-conditions','area','annual-supply','policy-progress','program-progress','projects','history','manual','requirements','project-collection','data-integrity'].includes(view);
  document.querySelector('.page-heading').hidden=['supply-conditions','area','annual-supply','policy-progress','program-progress','projects','history','manual','requirements','project-collection','data-integrity'].includes(view);
  // These workspaces load their own data. A cancelled request from the
  // previous menu must not leave their shared content container hidden.
  if(['manual','requirements','project-collection','data-integrity','area','annual-supply'].includes(view)){
    state.workspaceOnly=true;$('content').hidden=false;$('loading').hidden=true;$('error').hidden=true;
  }
  if(view==='area')AreaDashboard.visible();
  if(view==='annual-supply')AnnualSupply.visible();
  if(view==='project-collection'&&(previous!==view||!options.fromHistory))ProjectCollection.visible({refresh:previous!==view});
  if(view==='data-integrity')DataIntegrity.visible();
  if(view==='requirements')RequirementsManual.visible();
  if(view==='manual')UserGuide.visible();
  $('policy-filter-label').hidden=false;
  if(policyViews.has(view)&&view!=='projects')PolicyGeo3D.visible(view);else PolicyGeo3D.hidden();
  if(!options.fromHistory){const next='#'+view;if(location.hash!==next)history[options.replace?'replaceState':'pushState'](null,'',next);}
  if(!options.deferLoad&&previous!==view&&!['manual','requirements','project-collection','data-integrity','area','annual-supply'].includes(view))load();
}
async function openDetail(id) {
  const generation = ++state.detailGeneration;
  const dialog = $('detail-dialog');
  $('detail-content').innerHTML = empty('사업 근거를 불러오는 중입니다.');
  if (!dialog.open) dialog.showModal();
  try {
    const r = await request('/projects/' + encodeURIComponent(id) + '?as_of_date=' + encodeURIComponent($('as-of').value));
    if (generation !== state.detailGeneration) return;
    const terms = [['지역',r.region + ' · ' + r.municipality],['원천',sourceNames.get(r.source_id)],['물량의 의미',r.unit_basis],['일정의 의미',r.schedule_basis],['시행기관',r.developer],['정책 연결',r.mapping.basis]];
    if(r.completion_plan_date){terms.push(['준공 계획일',r.completion_plan_date],['계획 분류','준공 예정으로 관리합니다. 분양·모집 공급계획 및 실제 준공·입주와 구분합니다.']);}
    if(r.mapping?.policy_id==='POL_2025_0907'&&r.start_actual_date&&r.start_actual_date<'2026-01-01'){terms.push(['9.7 목표 집계','2026년 이전 착공 사업으로 135만 호 신규 착공 목표 집계에서 제외됩니다. 사업별 준공 계획은 별도로 유지합니다.']);}
    const dates = [['자료 기준',baseText(r)],['승인',null],['착공',r.start_actual_date],['준공',null]];
    $('detail-content').innerHTML = `<h2 id="detail-title" class="detail-title">${esc(r.name)}</h2><p class="detail-sub">${esc(r.program)} · ${esc(r.stage_label)} · ${badge(r.mapping.status)}</p><div class="detail-grid"><div><span>계획호수</span><strong>${num(r.planned_units)}${r.planned_units == null ? '' : '호'}</strong></div><div><span>원천상 공정률</span><strong>${r.progress_pct == null ? '미확보' : num(r.progress_pct) + '%'}</strong></div><div><span>원천 기준일</span><strong>${esc(baseText(r))}</strong></div></div><div class="timeline">${dates.map(([label,d]) => `<div class="${d ? 'known' : ''}">${label}<strong>${esc(d || '실적 미확인')}</strong></div>`).join('')}</div>${r.progress_evidence_url?`<div class="detail-section"><h3>실제 공정률 근거</h3><p>${esc(r.progress_date_precision==='MONTH'?r.progress_date.slice(0,7):r.progress_date)} · ${esc(r.progress_date_basis)}</p><a href="${esc(safeUrl(r.progress_evidence_url))}" target="_blank" rel="noopener noreferrer">블록별 공정률 원본 ↗</a></div>`:''}${renderProjectDataStatus(r)}${ProjectCollection.constructionPlanHtml(r.construction_plan)}<div class="detail-section"><h3>사업·일정 근거</h3><dl>${terms.map(([k,v]) => `<dt>${esc(k)}</dt><dd>${esc(v || '미확보')}</dd>`).join('')}<dt>예정시점</dt><dd>${esc(r.schedule_month || '개별 일정 미확보')}</dd></dl><p><a href="${esc(safeUrl(r.evidence_url))}" target="_blank" rel="noopener noreferrer">공식 원문에서 확인 ↗</a></p></div>${r.warnings.length ? `<div class="detail-section"><h3>확인이 필요한 항목</h3><ul>${r.warnings.map(w => `<li>${esc(warningNames[w] || w)}</li>`).join('')}</ul></div>` : ''}${r.rows ? `<div class="detail-section"><h3>면적별 원천 공급계획</h3><table><thead><tr><th>면적</th><th>공급호수</th><th>공급예정월</th><th>입주예정월</th></tr></thead><tbody>${r.rows.map(x => `<tr><td>${esc(x.area)}㎡</td><td>${num(x.units)}호</td><td>${esc(x.supply_schedule?.label || x.supply_month || '일정 미확인')}</td><td>${esc(x.move_in_schedule?.label || x.move_in_month || '일정 미확인')}</td></tr>`).join('')}</tbody></table><p>총세대수는 면적 행마다 반복되므로 더하지 않습니다.</p></div>` : ''}<div class="detail-section"><h3>수집·변경 이력</h3>${r.history.map(h => `<details><summary>revision ${h.revision_no} · ${timeText(h.recorded_at)}</summary><p>원천 기준일 ${esc(baseText(h.values))} · 원본 snapshot ${h.snapshots.length}개</p>${revisionText(h.values)}<div class="hash">레코드 SHA-256 ${esc(h.payload_hash)}</div>${h.snapshots.map(s => `<p><a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">수집 근거 ↗</a></p><div class="hash">${esc(s.sha256)}</div>`).join('')}</details>`).join('')}</div>${state.admin ? `<div class="detail-section"><h3>정책–프로그램–사업 매칭</h3><p>정책–프로그램과 프로그램–사업을 각각 검토합니다.</p><button id="detail-mapping-open" class="button primary" type="button">이 사업의 연결 검토 열기</button></div>` : ''}`;
    const market=document.createElement('section');market.className='detail-section';market.id='detail-unsold';$('detail-content').append(market);UnsoldIndicators.mount(market,r);
    if (state.admin) $('detail-mapping-open').addEventListener('click',()=>{
      dialog.close();setView('tree');MappingWorkbench.focusProject(id);
    });
  } catch (error) {if (generation === state.detailGeneration) $('detail-content').innerHTML = empty(error.message);}
}
document.addEventListener('click', event => {
  const group=event.target.closest('[data-nav-group]');if(group){toggleNavGroup(group.dataset.navGroup,group.getAttribute('aria-expanded')!=='true');return;}
  const nav = event.target.closest('[data-view]'); if (nav) setView(nav.dataset.view);
  const row = event.target.closest('[data-project]'); if (row) openDetail(row.dataset.project);

});
$('close-detail').addEventListener('click', () => {$('detail-dialog').close(); ++state.detailGeneration;});
$('detail-dialog').addEventListener('click', e => {if (e.target === $('detail-dialog')) $('detail-dialog').close();});
for (const id of ['region','policy','as-of','source-filter','stage-filter','mapping-filter']) $(id).addEventListener('change', () => {state.page = 1; load();});
let debounce;
$('search').addEventListener('input', () => {clearTimeout(debounce); debounce = setTimeout(() => {state.page = 1; load();},250);});
$('reset').addEventListener('click', () => {for (const id of ['region','policy','search','source-filter','stage-filter','mapping-filter']) $(id).value = ''; $('as-of').value = $('as-of').max; state.page = 1;Roadmap.reset();HousingMap.reset(); load();});
$('prev').addEventListener('click', () => {if (state.page > 1) {state.page--; load();}});
$('next').addEventListener('click', () => {if (state.page * 25 < state.total) {state.page++; load();}});
function setupSidebar() {
  const toggle=$('sidebar-toggle');
  try {if(localStorage.getItem('home-sidebar-collapsed')==='true')document.body.classList.add('sidebar-collapsed');}catch(_){}
  const sync=()=>{const collapsed=document.body.classList.contains('sidebar-collapsed');const label=collapsed?'왼쪽 메뉴 펼치기':'왼쪽 메뉴 접기';toggle.setAttribute('aria-expanded',String(!collapsed));toggle.setAttribute('aria-label',label);toggle.title=label;toggle.querySelector('span').textContent=collapsed?'»':'☰';};
  toggle.addEventListener('click',()=>{const collapsed=document.body.classList.toggle('sidebar-collapsed');try{localStorage.setItem('home-sidebar-collapsed',String(collapsed));}catch(_){}sync();setTimeout(()=>{if(state.view==='overview')HousingMap.visible();if(policyViews.has(state.view))PolicyGeo3D.resize();},220);});
  sync();
}
let catalogueReady=null;
function ensureCatalogue(){
  if(catalogueReady)return catalogueReady;
  catalogueReady=Promise.all([request('/policies'),request('/sources?compact=true')]).then(([policies,sources])=>{
    state.policies=policies.items;state.sources=sources.items;
    $('policy').innerHTML=policies.items.map(p=>`<option value="${esc(p.policy_id)}">${esc(p.name)}</option>`).join('');
    $('policy').value='POL_2025_0907';
    $('source-filter').innerHTML='<option value="">원천 전체</option>'+sources.items.filter(s=>s.collection_mode!=='TEST_SAMPLE'&&s.type!=='POLICY_FOLLOWUP').map(s=>`<option value="${esc(s.id)}">${esc(s.name)}</option>`).join('');
    for(const source of sources.items)sourceNames.set(source.id,source.name);
  }).catch(error=>{catalogueReady=null;throw error;});
  return catalogueReady;
}
async function start() {
  setupSidebar();SourceYears.start();
  Roadmap.start();
  HousingMap.start();
  AreaDashboard.start();
  AnnualSupply.start();ReportMD.start();
  HistoryPanel.start();
  PolicyDashboard.start();MappingWorkbench.start();PolicySchematic.start();PolicyGeo3D.start();PolicyReport.start();Policy907.start();
  const day = new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul'}).format(new Date());
  $('as-of').value = day; $('as-of').max = day;
  try {
    // Static integrity documents do not wait for database-backed catalogues.
    const adminRequest=request('/admin/status');
    if(location.hash.slice(1)!=='data-integrity')await ensureCatalogue();
    const admin=await adminRequest;state.admin=admin.authenticated;
    if (state.admin) $('admin-link').textContent = '관리자로 로그인됨 ↗';
    setView(location.hash.slice(1) || 'policy-progress',{replace:true,deferLoad:true});
    await load();
  } catch (error) {$('loading').hidden = true; $('error').hidden = false; $('error').textContent = error.message;}
}
window.addEventListener('popstate',()=>setView(location.hash.slice(1)||'policy-progress',{fromHistory:true}));
window.addEventListener('hashchange',()=>setView(location.hash.slice(1)||'policy-progress',{fromHistory:true}));
const sourceStatusNames={SUCCESS:'수집 정상',FAILED:'수집 실패',RUNNING:'수집 중',NOT_COLLECTED:'수집 대기',INTERRUPTED:'수집 중단',CONNECTOR_PENDING:'연결 준비'};
function renderCollectionStatus(sources){
  for(const node of $('source-channel-summary').querySelectorAll('[data-collector-errors]')){
    const group=sources.filter(s=>(s.data_type==='API'?'API':'OFFICIAL_WEB')===node.dataset.collectorErrors),errors=group.filter(s=>s.status==='FAILED').length,excluded=group.some(s=>s.id==='ih_supply'&&s.manual_only&&!s.record_count);
    node.textContent=[errors?'수집 오류 '+errors+'개':'',excluded?'iH 자동 수집 제외':''].filter(Boolean).join(' · ');node.hidden=!node.textContent;
  }
}
function notifyViewUpdate(view){
  if(state.view!==view)return;
  const button=$('view-update-notice');button.hidden=false;button.dataset.view=view;
}
function updateSourceStatus(items){
  const updates=new Map(items.map(s=>[s.id,s]));
  // Compact reads must not replace the full metadata used by open dialogs and snapshots.
  state.sources=state.sources.map(source=>{
    const next=updates.get(source.id);if(!next)return source;
    const patch={};for(const key of ['status','last_success','record_count','error'])if(key in next)patch[key]=next[key];
    return {...source,...patch};
  });
  for(const card of $('sources-list').querySelectorAll('[data-source-id]')){
    const next=updates.get(card.dataset.sourceId);if(!next)continue;
    if('status' in next)card.classList.toggle('source-collection-failed',next.status==='FAILED');
    const badge=card.querySelector('.source-title>.badge');
    if(badge){badge.textContent=sourceStatusNames[next.status]||next.status;badge.className='badge '+(next.status==='SUCCESS'?'confirmed':next.status==='FAILED'?'failed':'neutral');}
    const values=card.querySelectorAll('.source-data strong');
    if(values[0]&&'last_success' in next)values[0].textContent=timeText(next.last_success);
    if(values[1]&&'record_count' in next)values[1].textContent=num(next.record_count)+'건';
  }
  renderCollectionStatus(state.sources);
}
let sourcePolling=false;
async function pollCollectionStatus(){
  if(state.view!=='sources'||sourcePolling||document.hidden||!$('loading').hidden)return;
  const view=state.view,generation=state.generation;sourcePolling=true;
  try{
    const previous=new Map(state.sources.map(s=>[s.id,s]));
    const result=await request('/sources?compact=true');
    if(state.view!==view||state.generation!==generation)return;
    const changed=result.items.some(s=>{const old=previous.get(s.id);return !old||old.last_success!==s.last_success||old.record_count!==s.record_count;});
    updateSourceStatus(result.items);
    if(changed)notifyViewUpdate(view);
  }catch(_){}finally{sourcePolling=false;}
}
$('view-update-notice').addEventListener('click',()=>{if($('view-update-notice').dataset.view===state.view)load();});
setInterval(pollCollectionStatus,10000);
let viewPolling=false;
setInterval(async()=>{
  const view=state.view;
  if(viewPolling||document.hidden||!$('loading').hidden||document.querySelector('dialog[open]')||!state.viewVersion||!['projects','policy-progress','program-progress'].includes(view))return;
  viewPolling=true;
  try{
    const observed=await request('/view-version?view='+view);
    if(view===state.view&&observed.version!==state.viewVersion)notifyViewUpdate(view);
  }catch(_){}finally{viewPolling=false;}
},20000);
start();
