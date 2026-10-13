'use strict';
const API = '/poc/home/api';
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
const num = v => v == null ? '미확보' : Number(v).toLocaleString('ko-KR');
const baseText = r => r.date_precision === 'YEAR' ? r.base_date.slice(0,4) + '년 연간 계획' : r.base_date;
const revisionText = r => `<p>계획호수 ${num(r.planned_units)}${r.planned_units == null ? '' : '호'} · ${esc(r.stage_label)} · 공정률 ${r.progress_pct == null ? '미확보' : num(r.progress_pct) + '%'}</p>`;
const sourceNames = new Map();
const warningNames = {POLICY_PLAN_NOT_ACTUAL:'정책 계획 · 실적 미확인',JOINT_QUANTITY_UNALLOCATED:'여러 지구 합계 · 개별 물량 미확보',AGENCY_PLAN_NOT_ACTUAL:'기관 계획 · 실적 미확인',MUNICIPALITY_UNVERIFIED:'시군구 연결 검토',MAPPING_REVIEW:'정책 귀속 검토 필요', STALE_SOURCE:'원천 기준일 30일 초과', PAST_PLAN_UNVERIFIED:'지난 예정일 · 실제 이행 미확인', UNITS_UNKNOWN:'개별 물량 미확보', TOTAL_CONFLICT:'총세대수 불일치', SUPPLY_EXCEEDS_TOTAL:'공급호수 > 총세대수', MISSING_IN_LATEST_SOURCE:'최신 원천에서 미발견', MULTI_SITE_CONTRACT:'복수 현장 계약 · 지역별 물량 확인', USE_INSPECTION_FIELD_REVIEW:'사용검사 필드 의미 검토 · 준공으로 확정하지 않음', ZERO_UNITS_REVIEW:'원천 세대수 0 · 용도·집계 기준 확인', ADDRESS_APPROXIMATE:'주소 일부를 정리해 검색 · 사업 경계 확인 필요', GEOCODE_NOT_FOUND:'주소 좌표 미발견'};
const labels = {overview:'공급현황','annual-supply':'연도별 공급 비교',area:'인구·가구·고용 분석','policy-progress':'정책별 추진현황','program-progress':'프로그램별 추진현황',history:'정책 흐름·과거 자료', projects:'사업별 추진현황', tree:'정책-프로그램-사업연결', validation:'데이터 검증', samples:'원천 검증 자료', sources:'출처와 수집현황', keys:'API 연결 안내','project-collection':'사업별 수집·연계',manual:'매뉴얼',requirements:'총리님 요구사항'};
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
const sampleKinds = {notice:'청약공고', permit:'인허가', location:'주소 좌표', register:'주거용 건축물대장', register_recap:'주거용 총괄표제부', lh_notice:'LH 분양·임대 공고', statistic:'지역 주택건설 통계', sh_plan:'SH 분양 공급계획', sh_project:'SH 재개발·재건축 사업', gh_notice:'GH 주택 공고', agency_stock:'SH·GH 관리·매입 재고', legal_dong:'공식 법정동 코드', lh_supply:'LH 과거 공공분양 공급현황', lh_movein_plan:'LH 연도별 입주계획', lh_stock:'LH 단지 준공·입주지정 일정',renewal_inventory:'국토부 정비사업 현황 후보',lh_completion_plan:'LH 블록별 준공예정',permit_dong:'건축HUB 동별 가구 구성',permit_parcel:'건축HUB 대지위치',plan_notice:'공식 계획 고시 원문'};
const sampleUnit = r => r.units == null ? '' : r.sample_kind === 'statistic' ? '호' : '세대';
const sampleQuantity = r => r.value_status === 'NOT_APPLICABLE' ? '해당 없음' : r.value_status === 'UNVERIFIED' ? '미확정' : num(r.units) + sampleUnit(r);
Object.assign(warningNames, {SH_PLAN_NOT_ACTUAL:'SH 계획 물량 · 공급 실적 미확인', SH_HISTORY_SNAPSHOT:'과거 공개본 · 다른 공개본과 물량 중복 합산 금지', SH_OLD_STATUS:'과거 기준일의 추진현황 · 현재 상태 확인 필요', SH_SCHEDULE_NOT_ACTUAL:'공급 예정월 · 실제 공급·지연 확인 필요', REGISTER_STOCK_NOT_SUPPLY:'건축물대장 기존 재고 · 신규 공급 실적과 구분', USE_APPROVAL_NOT_MOVE_IN:'건축물 사용승인일 · 주택법 사용검사·실입주와 구분', NOTICE_DETAIL_UNITS_REQUIRED:'공고 상세 세대수·정정·재공고 중복 확인 필요', REGIONAL_TOTAL_NOT_POLICY_ACTUAL:'시도 전체 통계 · 개별 정책 실적 합산 제외'});
const state = {view:'overview', page:1, total:0, samplePage:1, sampleTotal:0, identityPage:1, policies:[], sources:[], admin:false, generation:0, detailGeneration:0};
const empty = text => `<div class="empty">${esc(text)}</div>`;
const badge = status => `<span class="badge ${status === 'CONFIRMED' ? 'confirmed' : status === 'RELEASED' ? 'neutral' : 'review'}">${status === 'CONFIRMED' ? '담당자 확정' : status === 'RELEASED' ? '연결 해제' : '확인 필요'}</span>`;
function safeUrl(value) {try {const u = new URL(value); return u.protocol === 'https:' ? u.href : '#';} catch {return '#';}}
function timeText(value) {return value ? new Date(value).toLocaleString('ko-KR', {timeZone:'Asia/Seoul', dateStyle:'short', timeStyle:'short'}) : '미수집';}
// Share simultaneous identical reads; never reuse a response after an edit.
const pendingReads = new Map();
async function request(path, options = {}) {
  const share = (!options.method || options.method === 'GET') && !options.signal;
  if (share && pendingReads.has(path)) return pendingReads.get(path);
  const task = (async()=>{
    const response = await fetch(API + path, {credentials:'same-origin', ...options});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `조회 실패 (${response.status})`);
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
function sampleQuery() {
  const params = new URLSearchParams();
  for (const [id,key] of [['as-of','as_of_date'],['region','region'],['search','q'],['sample-kind','kind'],['sample-year','source_year']]) {
    if ($(id).value) params.set(key, $(id).value);
  }
  return params;
}
function coordinateText(row) {
  return row.resolution_status === 'OK' ? `${Number(row.longitude).toFixed(6)}, ${Number(row.latitude).toFixed(6)}` : '좌표 미발견';
}
function renderSamples(data) {
  const selectedYear=$('sample-year').value;
  const years=new Set(data.source_years||[]);
  if(selectedYear)years.add(Number(selectedYear));
  $('sample-year').innerHTML='<option value="">자료 연도 전체</option>'+[...years].sort((a,b)=>b-a).map(year=>`<option value="${year}">${year}년</option>`).join('');
  $('sample-year').value=selectedYear;
  state.sampleTotal=data.total;
  $('sample-page-info').textContent=`${state.samplePage} / ${Math.max(1,Math.ceil(data.total/100))}`;
  $('sample-prev').disabled=state.samplePage===1;
  $('sample-next').disabled=state.samplePage*100>=data.total;
  $('sample-total').textContent = `원천 자료 ${num(data.total)}건 · ` + Object.entries(data.counts).map(([kind,count]) => `${sampleKinds[kind]} ${num(count)}건`).join(' / ');
  $('sample-list').innerHTML = data.items.length ? `<table><thead><tr><th>표본 / 원천</th><th>지역 · 주소</th><th>원천 날짜</th><th>물량 / 좌표</th><th>수집일</th></tr></thead><tbody>${data.items.map(r => `<tr><td><button class="project-name" data-sample="${esc(r.id)}">${esc(r.name)}</button><small class="row-sub">${sampleKinds[r.sample_kind]} · ${esc(sourceNames.get(r.source_id) || r.source_id)}</small></td><td>${esc(r.region)}<small class="row-sub">${esc(r.address)}</small></td><td>${esc(r.source_date || '미제공')}<small class="row-sub">${esc(r.source_date_label)}</small></td><td>${r.sample_kind === 'location' ? esc(coordinateText(r)) : sampleQuantity(r)}<small class="row-sub">${esc(r.coordinate_basis || r.unit_basis)}</small></td><td>${esc(r.base_date)}<small class="row-sub">${r.in_latest_source===false?'최신 공개본 미발견':'정책 연결 검토 전'}</small></td></tr>`).join('')}</tbody></table>` : empty('해당 조건의 원천 자료가 없습니다. 지역·검색·기준일을 확인하세요.');
  $('sample-export').href = API + '/samples/export.csv?' + sampleQuery();
}
function table(rows, small = false) {
  if (!rows.length) return empty('선택한 조건의 사업 후보가 없습니다. 수집 원천과 기준일을 확인하세요.');
  return `<table><thead><tr><th>사업 / 지구</th><th>지역</th><th>계획호수</th><th>진행 단계</th><th>공정률</th>${small ? '' : '<th>원천 기준일</th>'}<th>정책 연결</th></tr></thead><tbody>${rows.map(row => `<tr><td><button class="project-name" data-project="${esc(row.id)}">${esc(row.name)}</button><small class="row-sub">${esc(sourceNames.get(row.source_id) || row.source_id)} · ${esc(row.program)}</small></td><td>${esc(row.region.replace('특별시','').replace('도',''))}<small class="row-sub">${esc(row.municipality)}</small></td><td class="numeric">${num(row.planned_units)}${row.planned_units == null ? '' : '호'}</td><td><span class="badge neutral">${esc(row.stage_label)}</span></td><td>${row.progress_pct == null ? '<span class="badge review" title="실제 공정률 원천 미입수 · 0%나 미착수 확정이 아님">미입수</span>' : `<div class="progress-inline"><span>${num(row.progress_pct)}%</span><progress max="100" value="${Number(row.progress_pct)}" aria-label="공정률"></progress></div>${row.progress_date?`<small class="row-sub">${esc(row.progress_date_precision==='MONTH'?row.progress_date.slice(0,7):row.progress_date)} 기록</small>`:''}`}</td>${small ? '' : `<td>${esc(baseText(row))}<small class="row-sub">${row.source_age_days == null ? '연간 계획 · 갱신일 미제공' : `${num(row.source_age_days)}일 경과`}</small></td>`}<td>${badge(row.mapping.status)}</td></tr>`).join('')}</tbody></table>`;
}
function renderOverview(overview, rows, roadmap) {
  const cards = [['수집 사업 후보',overview.project_count,'건','같은 사업이 원천별로 존재할 수 있음','▤'],['향후 목표 확보',roadmap.future_target_count,'건',`향후 ${roadmap.horizon}년 · 원천 예정과 관리자 목표`,'⑂'],['확대 API 데이터',overview.api_sample_count,'건','청약·인허가·주소 조회 · 정책 연결 검토 전','⌖'],['일정 미확보',roadmap.no_schedule_count,'건','사업별 연도 목표 확인 필요','◎']];
  $('metrics').innerHTML = cards.map(([title, value, unit, note, icon]) => `<article class="metric"><div class="metric-label">${title}<span class="metric-icon">${icon}</span></div><div class="metric-value">${num(value)}<small>${unit}</small></div><div class="metric-note">${note}</div></article>`).join('');
  $('nav-count').textContent = num(overview.project_count);
  $('policy-cards').innerHTML = state.policies.length ? state.policies.map(p => `<div class="policy-row"><div class="policy-date">${esc(p.announced_at.slice(0,4))}<strong>${esc(p.announced_at.slice(5).replace('-','.'))}</strong></div><div class="policy-info"><h3><a href="${esc(safeUrl(p.evidence_url))}" target="_blank" rel="noopener noreferrer">${esc(p.name)} ↗</a></h3><p>${esc(p.metric)}</p><span class="policy-target">${num(p.target_units)}호 <small>${esc(p.target_scope)} · 서울·경기 배정량과 구분</small></span></div><span class="badge review">유효상태 검토</span></div>`).join('') : empty('정책 원문을 수집 중입니다.');
  const maximum = Math.max(1, ...Object.values(overview.regions));
  $('region-summary').innerHTML = `<div class="region-block">${['서울특별시','경기도'].map(region => `<div class="region-line"><div><span>${region}</span><strong>${num(overview.regions[region] || 0)} <small>건</small></strong></div><progress value="${overview.regions[region] || 0}" max="${maximum}" aria-label="${region} 사업 후보 수"></progress></div>`).join('')}</div>`;
  $('program-summary').innerHTML = `<div class="programs"><p class="programs-title">프로그램별 후보 기록</p>${Object.entries(overview.programs).sort((a,b) => b[1]-a[1]).slice(0,5).map(([k,v]) => `<div class="program-line"><span>${esc(k)}</span><span>${num(v)}건</span></div>`).join('')}</div>`;
  $('recent-projects').innerHTML = table(rows.slice(0,5), true);
  $('collection-footnote').textContent = overview.first_collection_date ? `최초 수집 ${overview.first_collection_date} · 범위 기준선 검토 중` : '초기 데이터 수집 중';
  // Historical views never reconstruct information collected after that date.
  $('as-of').min = overview.first_collection_date || '';
}
function renderSources(sources) {
  const statusNames = {SUCCESS:'수집 정상', FAILED:'수집 실패', RUNNING:'수집 중', NOT_COLLECTED:'수집 대기', INTERRUPTED:'수집 중단', CONNECTOR_PENDING:'연결 준비'};
  $('sources-list').innerHTML = sources.map(s => `<article class="source-card"><div class="source-title"><h3>${esc(s.name)}</h3><span class="badge ${s.status === 'SUCCESS' ? 'confirmed' : s.status === 'FAILED' ? 'failed' : 'neutral'}">${statusNames[s.status] || esc(s.status)}</span></div><p>${esc(s.org)} · ${s.collection_mode==='PUBLIC_FILE' ? '공식 공개 파일 · 판본별 수집' : s.id==='gh_notice' ? '공식 웹 공고 목록 · 수동 수집' : s.collection_mode==='PILOT_DETAIL' ? '건축HUB API 상세 · 수동 수집' : s.collection_mode==='DERIVED_INVENTORY' ? '최신 API 공개본 사업 연결' : s.collection_mode === 'TEST_SAMPLE' ? 'API 테스트 표본 · 수동 수집' : s.collection_mode === 'MAP_LAYER' ? '공식 공간정보 · 수동 수집' : '키 없이 웹·파일 수집'}</p><div class="source-data"><div><span>마지막 정상 수집</span><strong>${timeText(s.last_success)}</strong></div><div><span>${s.collection_mode === 'TEST_SAMPLE' ? '테스트 표본' : s.collection_mode === 'MAP_LAYER' ? '공동주택용지 지구' : '정상 레코드'}</span><strong>${num(s.record_count)}건</strong></div></div>${(s.stats.source_base_date || s.stats.dataset_version) ? `<p>원천 자료 기준일 ${esc(s.stats.source_base_date || s.stats.dataset_version)} · 현재 실적과 구분</p>` : ''}${s.error ? `<p>${esc(s.error)}</p>` : ''}<a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">공식 원천 확인 ↗</a>${s.snapshots.length ? `<details data-source-snapshots="${esc(s.id)}"><summary>근거 snapshot ${s.snapshots.length}개 · SHA-256</summary><div class="source-snapshot-body"></div></details>` : ''}</article>`).join('');
  for(const element of $('sources-list').querySelectorAll('[data-source-snapshots]'))element.addEventListener('toggle',()=>{
    if(!element.open||element.dataset.loaded)return;
    const source=sources.find(s=>s.id===element.dataset.sourceSnapshots);
    element.querySelector('.source-snapshot-body').innerHTML=source.snapshots.map(m=>`<p><a href="${esc(safeUrl(m.url))}" target="_blank" rel="noopener noreferrer">수집 원문 ↗</a> · ${num(m.bytes)} bytes${m.credentials_removed?' · 인증정보 제거':''}</p><div class="hash">${esc(m.sha256)}</div>`).join('');
    element.dataset.loaded='true';
  });
  sources.forEach((source,index)=>{if(source.collection_mode==='HISTORY')document.querySelectorAll('.source-card')[index].querySelector('p').textContent=source.org+' · 정책 기원부터 과거 원천 누적 수집';});
  const running = sources.some(s => s.status === 'RUNNING');
  $('refresh').disabled = running;
  $('refresh').textContent = running ? '수집 중…' : '지금 수집 ↻';
  $('sample-refresh').disabled = running;
  $('sample-refresh').textContent = running ? '수집 중…' : '확대 표본 수집 ↻';
  const failed = sources.filter(s => s.status === 'FAILED');
  $('refresh-status').textContent = running ? '공식 원천을 수집하고 있습니다. 결과는 자동 갱신됩니다.' : failed.length ? `${failed.length}개 원천의 수집을 확인하세요. 마지막 정상 데이터는 유지됩니다.` : '';
}
function renderKeys(sources) {
  const purposes = {sh_supply_plan:'SH 분양계획의 최신·과거 공개본과 공급 예정월', sh_redevelopment:'SH 재개발·재건축 위치·계획 세대수·원천 추진현황', cheongyak:'정책 기원 연도부터 서울·경기 공고의 연도별 전체 조회 페이지 수집', building_hub:'서울·경기 6개 법정동의 과거 인허가 전체 조회 페이지 수집', vworld:'주소 좌표·공식 공동주택용지·배경지도 조회', building_register:'6개 법정동 전체 조회 페이지 중 주거용 건축물대장 · 사용승인일 검증', lh_notice:'2018년부터 서울·경기 LH 분양·임대 공고 전체 페이지', molit_statistics:'2018년부터 서울·경기 월별 분양승인·착공·준공과 연간 인허가 총계'};
  $('keys-list').innerHTML = sources.filter(s => s.key_env && s.show_key_card!==false).map(s => `<article class="key-card"><div><h3>${esc(s.name)} <span class="badge neutral">공식 API 연결</span></h3><p>${esc(purposes[s.id]||'공식 공간정보 조회')}</p><code>${esc(s.key_env)}</code><p>${s.key_configured ? `서버에 키 설정됨 · ${s.status === 'SUCCESS' ? num(s.record_count) + '건 수집 정상' : '수집 상태: ' + esc(s.status)}` : 'API 키 미설정 · HOME 서버 설정 확인 필요'}</p></div><a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">발급·활용신청 ↗</a></article>`).join('');
}
function renderTree(tree) {
  $('tree-list').innerHTML = tree.items.length ? tree.items.map(p => `<details class="tree-policy" open><summary>${esc(p.name)} <span class="badge neutral">${num(p.groups.reduce((n,g) => n + g.count,0))}건</span></summary>${p.groups.map(g => `<details class="tree-group" open><summary>${esc(g.name)} · ${num(g.count)}건</summary>${g.projects.map(r => `<div class="tree-project"><button class="project-name" data-project="${esc(r.id)}">${esc(r.name)}<small class="row-sub">${esc(r.region)} · ${esc(sourceNames.get(r.source_id) || r.source_id)}</small></button><div><span>${num(r.planned_units)}${r.planned_units == null ? '' : '호'}</span>${badge(r.mapping.status)}</div></div>`).join('')}</details>`).join('')}</details>`).join('') : empty('선택한 조건의 정책–프로그램–사업 연결이 없습니다.');
}
const availabilityNames = {ACQUIRED:'확보',NOT_ACQUIRED:'미입수',NO_SOURCE_RECORD:'원본에 행 없음',SOURCE_NOT_PUBLISHED:'원천에 미공표',NOT_STARTED:'수집 미시작',FAILED:'수집 실패',PARTIAL:'범위 일부'};
function renderDataGaps(data) {
  if (!data) return;
  const p=data.projects || {};
  $('data-gap-note').textContent=data.notice;
  const fields=[['계획호수',p.planned_units_acquired],['실제 공정률',p.progress_acquired],['착공일 근거',p.start_date_acquired],['개별 예정월',p.schedule_acquired],['입주 시작 예정월',p.move_in_start_acquired]];
  $('data-gap-projects').innerHTML='<h4>조회 사업 '+num(p.total)+'건의 근거 확보</h4><div class="data-gap-metrics">'+fields.map(([name,count])=>`<div><span>${esc(name)}</span><strong>${num(count)} / ${num(p.total)}</strong><progress max="${p.total||1}" value="${count||0}" aria-label="${esc(name)} 확보 수"></progress></div>`).join('')+'</div><p class="data-gap-explain">원천상 계획·지정 단계 '+num(p.planning_stage)+'건 · 실제 미착수 확인 '+num(p.not_started_verified)+'건. 계획 단계만으로 미착수를 확정하지 않습니다. 정책 연결 검토 '+num(p.mapping_review)+'건.</p>'+'<p class="data-gap-explain">입주는 시작일만 관리합니다. 현재 연결된 원천은 예정월 정밀도이며 실제 시작일 확인은 별도입니다.</p>';
  $('data-gap-scope').innerHTML='<h4>법정동별 API 조회 범위</h4><div class="data-gap-scopes">'+(data.scope||[]).map(r=>`<div><strong>${esc(r.label)}</strong><span>${r.completed==null?'수집 미시작':num(r.completed)+' / '+num(r.total)+'개 동'}</span><progress max="${r.total||1}" value="${r.completed||0}" aria-label="${esc(r.label)} 조회 범위"></progress><small>${r.remaining==null?'범위 미확인':'잔여 '+num(r.remaining)+'개 동'} · ${esc(availabilityNames[r.status]||r.status)} · <a href="${esc(safeUrl(r.source_url))}" target="_blank" rel="noopener noreferrer">원천</a></small></div>`).join('')+'</div>';
  const keys={ACQUIRED:'확보',NO_SOURCE_RECORD:'원본 행 없음',SOURCE_NOT_PUBLISHED:'원천 미공표',NOT_ACQUIRED:'미입수',NOT_STARTED:'미시작',FAILED:'실패'};
  $('data-gap-years').innerHTML='<h4>자료연도별 확보 현황</h4><p class="data-gap-explain">공고·입주예정·지역 통계·공정 이력은 서로 다른 지표입니다. 색은 저장된 원천 증거의 유무만 나타냅니다. '+Object.entries(keys).map(([key,label])=>`<span class="data-gap-legend ${key}">${label}</span>`).join('')+'</p><table class="data-gap-matrix"><thead><tr><th>자료 · 범위</th>'+data.years.map(y=>`<th>${y}${y===data.years.at(-1)?'<small>진행 연도</small>':''}</th>`).join('')+'<th>확인할 일</th></tr></thead><tbody>'+(data.rows||[]).map(r=>`<tr><td><strong>${esc(r.label)}</strong><small>${esc(r.region)} · <a href="${esc(safeUrl(r.source_url))}" target="_blank" rel="noopener noreferrer">원천 ↗</a>${r.collection_status==='FAILED'?' · 최근 수집 실패 / 이전 성공본 유지':''}</small></td>${r.cells.map(c=>`<td><span class="data-gap-cell ${esc(c.status)}" title="${esc(r.region+' '+c.year+'년 '+(keys[c.status]||c.status)+(c.count?' · '+c.count+'개 저장':' · 원천 발표 여부 별도 확인'))}" aria-label="${esc(r.label+' '+r.region+' '+c.year+'년 '+(keys[c.status]||c.status))}">${c.status==='ACQUIRED'?'●':c.status==='NO_SOURCE_RECORD'?'행 없음':c.status==='SOURCE_NOT_PUBLISHED'?'미공표':c.status==='NOT_STARTED'?'시작 전':c.status==='FAILED'?'실패':'미입수'}</span></td>`).join('')}<td class="data-gap-next">${esc(r.next_action)}</td></tr>`).join('')+'</tbody></table>';
  $('data-gap-forecast').innerHTML='<h4>장래가구 추계 · 시도 단위</h4><p class="data-gap-explain">실제 가구 수와 다른 전망치입니다. 시군구별 추계는 아직 미연계입니다.</p><table class="data-gap-matrix"><thead><tr><th>범위</th>'+data.forecast_years.map(y=>`<th>${y}</th>`).join('')+'</tr></thead><tbody>'+(data.forecast_rows||[]).map(r=>`<tr><td><strong>${esc(r.region)}</strong><small><a href="${esc(safeUrl(r.source_url))}" target="_blank" rel="noopener noreferrer">KOSIS 원천 ↗</a></small></td>${r.cells.map(c=>`<td><span class="data-gap-cell ${esc(c.status)}" title="${esc(r.region+' '+c.year+'년 '+(keys[c.status]||c.status))}">${c.status==='ACQUIRED'?'●':'미입수'}</span></td>`).join('')}</tr>`).join('')+'</tbody></table>';
  $('data-gap-unstarted').innerHTML='<h4>아직 수집기를 연결하지 않은 자료</h4><div class="data-gap-pending">'+(data.not_started||[]).map(r=>`<div><span class="data-gap-legend NOT_STARTED">미시작</span><strong>${esc(r.label)}</strong><small>${esc(r.scope)} · ${esc(r.next_action)} ${r.source_url?'<a href="'+esc(safeUrl(r.source_url))+'" target="_blank" rel="noopener noreferrer">원천 ↗</a>':''}</small></div>`).join('')+'</div>';
}
function renderProjectDataStatus(r) {
  const d=r.data_status;
  if(!d)return '';
  const moveIn=`<dt>입주 시작</dt><dd>${esc(d.move_in_start||'미확보')}</dd>`;
  return `<div class="detail-section"><h3>빈 항목 상태</h3><p>${esc(d.phase)}. 실제 미착수 확정 근거는 ${d.not_started_verified?'있음':'없음'}.</p><dl><dt>계획호수</dt><dd>${esc(d.planned_units)}</dd><dt>실제 공정률</dt><dd>${esc(d.progress)}</dd>${moveIn}<dt>실제 준공일</dt><dd>${esc(d.completion_date)}</dd><dt>예정 일정</dt><dd>${esc(d.schedule)}</dd></dl></div>`;
}
function renderValidation(data) {
  renderDataGaps(data.data_gaps);
  const coverage=data.coverage;
  if(coverage){
    $('coverage-note').textContent=coverage.notice;
    const labels={VERIFIED:'조건 내 전체 조회',PARTIAL:'일부 조회',UNVERIFIED:'전체성 미검증',NOT_COLLECTED:'미수집'};
    $('coverage-list').innerHTML='<table><thead><tr><th>원천 / 조회 검증</th><th>제공 → 조회 → 적재</th><th>실제 범위 · 자료 기간</th><th>아직 부족한 자료</th></tr></thead><tbody>'+coverage.items.map(r=>`<tr><td><a href="${esc(safeUrl(r.evidence_url))}" target="_blank" rel="noopener noreferrer">${esc(r.name)}</a><small class="row-sub">${esc(labels[r.query_status]||r.query_status)} · ${esc(r.collection_status)}</small></td><td>${r.provided_records==null?'미확인':num(r.provided_records)} → ${r.fetched_records==null?'미확인':num(r.fetched_records)} → ${num(r.collected_records)}<small class="row-sub">원천 레코드 · 사업 수와 구분</small></td><td>${esc(r.scope)}<small class="row-sub">${esc(r.source_period)}</small></td><td>${esc(r.gap)}</td></tr>`).join('')+'</tbody></table>';
  }
  const details=data.coverage_details||[];
  $('coverage-endpoint-list').innerHTML=details.length ? '<details><summary>실증된 세부 조회 범위 '+num(details.length)+'개 보기</summary><table><thead><tr><th>원천·조회 항목</th><th>지역·법정동</th><th>원천 기준일</th><th>제공 → 확보</th><th>판정</th></tr></thead><tbody>'+details.map(r=>`<tr><td>${esc(sourceNames.get(r.source_id)||r.source_id)}<small class="row-sub">${esc(r.endpoint)}</small></td><td>${esc(r.region)}${r.area_code ? '<small class="row-sub">'+esc(r.area_code)+'</small>':''}</td><td>${esc(r.source_period||'수집 시점 조회')}</td><td>${num(r.expected_count)} → ${num(r.fetched_count)}</td><td>${r.query_status==='COMPLETE_QUERY'?'조건 내 전체 페이지':'일부 페이지'}<small class="row-sub">서울·경기 사업 전수 아님</small></td></tr>`).join('')+'</tbody></table></details>' : '';
  $('validation-notes').innerHTML = `<span>ⓘ</span><div><strong>검증 기준</strong>${data.notes.map(n => `<p>${esc(n)}</p>`).join('')}</div>`;
  $('validation-list').innerHTML = data.items.length ? `<table><thead><tr><th>확인 항목</th><th>사업 후보</th><th>원천</th></tr></thead><tbody>${data.items.map(r => `<tr><td><span class="badge review">${esc(warningNames[r.code] || r.code)}</span></td><td><button class="project-name" data-project="${esc(r.project_id)}">${esc(r.name)}</button></td><td>${esc(sourceNames.get(r.source_id) || r.source_id)}</td></tr>`).join('')}</tbody></table>` : empty('해당 조건에서 추가 확인 항목이 없습니다.');
}
function renderIdentityPlans(identities, plans, queue, options) {
  state.identityQueue = queue.items || [];
  state.identityOptions = options.items || [];
  let html = '<p>실사업 정체성 후보 <strong>' + num(identities.total) + '건</strong> · LH 준공예정 단일 일치 검토 <strong>' +
    num(identities.forecast_review_count) + '건</strong> · 공식 계획 고시 파일럿 <strong>' + num(plans.total) +
    '건</strong></p><p class="row-sub">고시는 공급·준공 실적이 아닙니다. 최초 지정부터 전체 변경 이력과 계획–사업 연결은 별도 검증합니다.</p>';
  html += '<h4>공식 계획 고시</h4><table><thead><tr><th>계획</th><th>고시 사건</th><th>사업 연결</th></tr></thead><tbody>' +
    (plans.items || []).map(p => '<tr><td>' + esc(p.region) + ' · ' + esc(p.name) +
      '</td><td>' + (p.events || []).map(e => '<a href="' + esc(safeUrl(e.evidence_url)) +
      '" target="_blank" rel="noopener noreferrer">' + esc(e.notice_no || '고시번호 미확보') + ' · ' +
      esc(e.notice_date || '일정 미정') + ' ↗</a>').join('<br>') +
      '</td><td>' + (p.project_links || []).length + '건 · ' + ((p.project_links || []).length ? '검토 필요' : '미연계') +
      '</td></tr>').join('') + '</tbody></table>';
  html += '<h4>LH 준공예정 ↔ 사업 동일성 검토</h4><table><thead><tr><th>LH 일정</th><th>현재 사업 후보</th><th>검토</th></tr></thead><tbody>' +
    state.identityQueue.map(item => '<tr><td>' + esc(item.region) + ' · ' + esc(item.source_name) +
      '<small class="row-sub">준공예정 ' + num(item.source_units) + '호</small></td><td>' +
      esc(item.project_name) + (item.unit_comparison === 'DIFFERENT' ? '<small class="row-sub">계획 호수 차이</small>' : '') +
      '</td><td>' + badge(item.status) + (state.admin ? ' <button type="button" class="button secondary" data-identity-open="' +
      esc(item.id) + '">확인·조정</button>' : '') + '</td></tr>').join('') + '</tbody></table>';
  html += '<div class="pagination"><button type="button" class="button secondary" data-identity-page="prev"' +
    (state.identityPage <= 1 ? ' disabled' : '') + '>← 이전</button><span>' + state.identityPage + ' / ' +
    Math.max(1, Math.ceil(queue.total / queue.page_size)) + '</span><button type="button" class="button secondary" data-identity-page="next"' +
    (state.identityPage * queue.page_size >= queue.total ? ' disabled' : '') + '>다음 →</button></div><div id="identity-editor"></div>';
  $('identity-plan-list').innerHTML = html;
}
function openIdentityEditor(id) {
  if (!state.admin) return;
  const item = (state.identityQueue || []).find(row => row.id === id);
  if (!item) return;
  state.identitySelected = item;
  const options = (state.identityOptions || []).filter(row => row.region === item.region);
  const target = options.map(row => '<option value="' + esc(row.id) + '"' +
    (row.id === item.project_id ? ' selected' : '') + '>' + esc(row.name) + ' · ' + esc(row.id) + '</option>').join('');
  $('identity-editor').innerHTML = '<form id="identity-review-form" class="identity-review-form"><h4>' +
    esc(item.source_name) + ' · 정체성 연결 검토</h4><label>연결 사업 후보<select id="identity-target">' +
    target + '</select></label><label>검토 상태<select id="identity-status"><option value="CONFIRMED">담당자 확정</option>' +
    '<option value="REVIEW">확인 필요</option><option value="RELEASED">연결 해제</option></select></label>' +
    '<label>확인 근거<textarea id="identity-basis" rows="3" required></textarea></label>' +
    '<label>원문 URL<input id="identity-evidence" type="url" required></label>' +
    '<button type="submit" class="button primary">검토 결과 저장</button><span id="identity-save-status" role="status"></span></form>';
  $('identity-editor').scrollIntoView({behavior:'smooth', block:'nearest'});
  $('identity-status').value = item.status;
  $('identity-basis').value = item.basis || '';
  $('identity-evidence').value = item.evidence_url || '';
  $('identity-review-form').addEventListener('submit', async event => {
    event.preventDefault();
    $('identity-save-status').textContent = '저장 중…';
    try {
      await request('/admin/identities/' + encodeURIComponent(item.id), {method:'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({
          project_id:$('identity-target').value, expected_project_id:item.project_id,
          expected_status:item.status, status:$('identity-status').value,
          basis:$('identity-basis').value.trim(), evidence_url:$('identity-evidence').value.trim()})});
      await load();
    } catch (error) {
      if ($('identity-save-status')) $('identity-save-status').textContent = error.message;
    }
  });
}
async function load() {
  const version = ++state.generation;
  const params = query();
  const qs = params.toString();
  const reportParams=new URLSearchParams(params);reportParams.delete('policy_id');
  const reportQs=reportParams.toString();
  if(state.historyQuery!==qs){state.historyPage=1;state.historyQuery=qs;}
  const historyParams=new URLSearchParams(params);historyParams.set('page',state.historyPage);
  if($('history-year').value)historyParams.set('history_year',$('history-year').value);
  $('error').hidden = true;
  $('loading').hidden = !$('content').hidden;
  try {
    if(['project-collection','area','annual-supply','manual','requirements'].includes(state.view)){
      // These workspaces own their requests. Do not queue the other menus'
      // large projections behind their initial render.
      state.workspaceOnly=true;$('content').hidden=false;return;
    }
    if(state.view==='overview'){
      const dashboard=await request('/map/dashboard?'+qs+'&'+HousingMap.query()+'&compact=true');
      if(version!==state.generation)return;
      state.workspaceOnly=true;$('content').hidden=false;
      $('nav-count').textContent=num(dashboard.items.length);
      HousingMap.render({districts:dashboard.districts},dashboard,dashboard);
      return;
    }
    if(['sources','keys'].includes(state.view)){
      const sources=await request(state.view==='sources'?'/sources':'/sources?compact=true');if(version!==state.generation)return;
      state.sources=sources.items;state.workspaceOnly=true;
      if(state.view==='sources')renderSources(sources.items);else {renderKeys(sources.items);const connections=await request('/connections');if(version!==state.generation)return;ConnectionGuide.render(connections);ApiRequests.load();}$('content').hidden=false;return;
    }
    if(['policy-progress','program-progress'].includes(state.view)){
      // Policy workspaces do not need the million-row source browser or the
      // separate supply map before their own overview/chart can be displayed.
      const [monitor,mappings]=await Promise.all([
        request('/policy-monitor?'+reportQs),request('/mappings?'+reportQs)]);
      if(version!==state.generation)return;
      state.workspaceOnly=true;
      $('nav-count').textContent=num(mappings.items.filter(r=>r.mapping?.policy_id==='POL_2025_0907'&&r.mapping?.status!=='RELEASED').length);
      PolicyReport.setData(monitor,mappings);PolicyDashboard.render(monitor);
      $('content').hidden=false;PolicyGeo3D.dataChanged();
      return;
    }
    // Load only this menu. Source-wide counts and maps must not block editors.
    state.workspaceOnly=true;
    if(state.view==='tree'){
      const [tree,mappings]=await Promise.all([request('/tree?'+qs),request('/mappings?'+reportQs)]);
      if(version!==state.generation)return;
      renderTree(tree);MappingWorkbench.render(mappings);
    }else if(state.view==='validation'){
      const [validation,identities,plans,queue,options,connections]=await Promise.all([
        request('/validation?'+qs),request('/identities?page_size=1'),request('/plans'),
        request('/identity-reviews?page='+state.identityPage+'&page_size=20'),request('/identity-options'),request('/connections')]);
      if(version!==state.generation)return;
      renderValidation(validation);renderIdentityPlans(identities,plans,queue,options);ConnectionGuide.render(connections);
    }else if(state.view==='samples'){
      const samples=await request('/samples?'+sampleQuery()+'&page='+state.samplePage+'&page_size=100');
      if(version!==state.generation)return;renderSamples(samples);
    }else if(state.view==='history'){
      const historyData=await request('/history?'+historyParams);
      if(version!==state.generation)return;HistoryPanel.render(historyData);
    }else if(state.view==='projects'){
      const [projects,monitor,mappings]=await Promise.all([
        request(`/projects?${qs}&page=${state.page}&page_size=25`),request('/policy-monitor?'+reportQs),request('/mappings?'+reportQs)]);
      if(version!==state.generation)return;
      state.total=projects.total;PolicyReport.setData(monitor,mappings);
      $('project-list').innerHTML=table(projects.items);
      $('project-total').textContent=`사업 후보 기록 ${num(projects.total)}건`;
      $('page-info').textContent=`${state.page} / ${Math.max(1,Math.ceil(projects.total/25))}`;
      $('prev').disabled=state.page===1;$('next').disabled=state.page*25>=projects.total;
      $('export').href=API+'/export.csv?'+qs;
    }
    $('content').hidden=false;
    if(policyViews.has(state.view))PolicyGeo3D.dataChanged();
  } catch (error) {
    if (version !== state.generation) return;
    $('error').textContent = error.message + ' 잠시 후 다시 조회해 주세요.';
    $('error').hidden = false;
  } finally {if (version === state.generation) $('loading').hidden = true;}
}
const policyViews = new Set(['policy-progress','program-progress','projects','history']);
const supplyViews = new Set(['overview','annual-supply','area']);
const sourceViews = new Set(['sources','validation','samples','keys','project-collection']);
function toggleNavGroup(group,open) {
  const button=document.querySelector(`[data-nav-group="${group}"]`);
  const children=$(button.getAttribute('aria-controls'));
  button.setAttribute('aria-expanded',String(open));children.hidden=!open;
}
function setView(view,options={}) {
  if (!labels[view]) return;
  const previous=state.view;
  if(previous!==view)++state.generation;
  state.view=view;
  for (const pane of document.querySelectorAll('.pane')) pane.hidden = pane.id !== 'pane-' + view && !(pane.id==='pane-policy-geo'&&policyViews.has(view));
  const category=supplyViews.has(view)?'supply':policyViews.has(view)?'policy':view==='tree'||sourceViews.has(view)?'data':'manual';
  if(category==='policy')toggleNavGroup('policy',true);
  if(category==='data')toggleNavGroup('data',true);
  if(category==='manual')toggleNavGroup('manual',true);
  for(const nav of document.querySelectorAll('#home-main-nav .nav-item')){
    const active=nav.dataset.view===view || (category==='supply'&&nav.dataset.view==='overview') ||
      (category==='policy'&&nav.dataset.view==='policy-progress'&&view==='history') ||
      (category==='data'&&nav.dataset.view==='sources'&&sourceViews.has(view)&&view!=='project-collection');
    nav.classList.toggle('active',active);
    if(active&&nav.dataset.view===view)nav.setAttribute('aria-current','page');else nav.removeAttribute('aria-current');
  }
  for(const button of document.querySelectorAll('#home-main-nav .nav-group-toggle'))button.classList.toggle('group-active',button.dataset.navGroup===category);
  for(const id of ['supply-subnav','data-subnav'])$(id).hidden=id==='supply-subnav'?category!=='supply':(!sourceViews.has(view)||view==='project-collection');
  for(const button of document.querySelectorAll('.home-subnav [data-view]')){
    const active=button.dataset.view===view;button.classList.toggle('active',active);button.setAttribute('aria-current',active?'page':'false');
  }
  $('page-label').textContent=labels[view];
  document.body.classList.toggle('home-map-view',view==='overview');
  document.body.classList.toggle('policy-geo-view',policyViews.has(view));
  document.body.classList.toggle('policy-summary-view',view==='policy-progress');
  document.body.classList.toggle('policy-compact-view',['policy-progress','program-progress'].includes(view));
  $('report-policy-picker').hidden=!['policy-progress','program-progress'].includes(view);
  $('report-program-picker').hidden=view!=='program-progress';
  $('policy-map-controls').hidden=!['policy-progress','program-progress'].includes(view);
  document.querySelector('.policy-geo-toolbar>div:first-child small').textContent=view==='policy-progress'?'POLICY REGIONAL VIEW':'POLICY GEO 3D';
  document.querySelector('.policy-geo-toolbar h2').textContent=view==='policy-progress'?'지역별 정책 공급 분포':'정책·프로그램·사업 지역 그래프';
  $('policy-geo-map').setAttribute('aria-label',view==='policy-progress'?'정책현황 시군구 공급 분포도':'정책현황 3D 지역 지도');
  if(view==='overview')HousingMap.visible();else if(previous==='overview')HousingMap.hidden();
  document.querySelector('.filterbar').hidden=['area','annual-supply','policy-progress','program-progress','history','manual','requirements','project-collection'].includes(view);
  document.querySelector('.page-heading').hidden=['area','annual-supply','policy-progress','program-progress','projects','history','manual','requirements','project-collection'].includes(view);
  if(view==='area')AreaDashboard.visible();
  if(view==='annual-supply')AnnualSupply.visible();
  if(view==='project-collection'&&(previous!==view||!options.fromHistory))ProjectCollection.visible({refresh:previous!==view});
  if(view==='requirements')RequirementsManual.visible();
  $('policy-filter-label').hidden=view==='samples';
  $('search').placeholder=view==='samples'?'표본명, 주소, 원천 식별자 검색':'사업명, 지구명, 프로그램 검색';
  if(policyViews.has(view))PolicyGeo3D.visible(view);else PolicyGeo3D.hidden();
  if(!options.fromHistory){const next='#'+view;if(location.hash!==next)history[options.replace?'replaceState':'pushState'](null,'',next);}
  if(!options.deferLoad&&previous!==view&&!['manual','requirements','project-collection','area','annual-supply'].includes(view))load();
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
async function openSample(id) {
  const generation = ++state.detailGeneration;
  const dialog = $('detail-dialog');
  $('detail-content').innerHTML = empty('원천 근거를 불러오는 중입니다.');
  if (!dialog.open) dialog.showModal();
  try {
    const r = await request('/samples/' + encodeURIComponent(id) + '?as_of_date=' + encodeURIComponent($('as-of').value));
    if (generation !== state.detailGeneration) return;
    const terms = [['원천',sourceNames.get(r.source_id)],['원천 식별자',r.source_object_id],['주소',r.address],
      [r.source_date_label,r.source_date],['표본 수집일',r.base_date],['최초/변경 저장',timeText(r.recorded_at)],
      ['정책 연결','검토 전 · 공급 실적 합산 제외'],['물량의 의미',r.unit_basis],['입주예정월 (원천)',r.move_in_plan_month],
      ['좌표 검색 주소',r.query_address],['좌표의 의미',r.coordinate_basis],['좌표 결과',r.sample_kind === 'location' ? coordinateText(r) : null],
      ['통계 대상 기간',r.statistic_period],['통계 주기',r.statistic_frequency === 'MONTH' ? '월계' : r.statistic_frequency === 'YEAR' ? '연간' : null],
      ['지구',r.district_name || r.district],['블록',r.block],['준공 예정일 (실적 아님)',r.completion_plan_date],['원천값 상태',r.value_status],['최신 공개본 포함',r.in_latest_source == null ? null : (r.in_latest_source ? '예' : '아니오 · 과거 근거')],['연결 주택인허가 관리번호',r.parent_permit_native_id],['동별개요 관리번호',r.native_dong_id],['대표 필지',r.representative == null ? null : (r.representative ? '예' : '아니오')],['지번 구성',r.bun && r.ji ? `${r.plat_gb_cd || ''}-${r.bun}-${r.ji}` : null],...Object.entries(r.household_breakdown || {}).filter(([,v]) => v != null && v > 0).map(([k,v]) => ['동별 '+k,v]),['총세대수 (공고 공급호수와 구분)',r.total_units],['원천 설명',r.source_note],['자료 공개본 기준일',r.dataset_version],['최신 공개본 여부',r.is_latest_dataset == null ? null : (r.is_latest_dataset ? '최신 공개본' : '과거 공개본 · 중복 합산 금지')],['공급 예정월',r.schedule_month],['주택형',r.housing_type],['사업 유형',r.business_type],['사전청약 공급세대수',r.pre_subscription_units],['본청약 공급세대수',r.main_subscription_units],['임대 세대수 (전체의 일부)',r.rental_units],['원천 추진현황',r.source_stage],['통계 지표',r.statistic_metric],['건축물 주용도',r.main_purpose],['건축물 동',r.building_dong],
      ['대장 가구수 (세대수와 구분)',r.family_count],['대장 호수 (세대수와 구분)',r.unit_count],['LH 공고 유형',r.notice_type],['LH 공고 상태',r.notice_status],
      ...Object.entries(r.dates || {})].filter(([,value]) => value != null);
    $('detail-content').innerHTML = `<h2 id="detail-title" class="detail-title">${esc(r.name)}</h2><p class="detail-sub">${sampleKinds[r.sample_kind]} · ${esc(r.region)} · 정책 연결 검토 전</p><div class="detail-section"><h3>표본과 원천 근거</h3><dl>${terms.map(([key,value]) => `<dt>${esc(key)}</dt><dd>${esc(value)}</dd>`).join('')}</dl>${r.sample_kind !== 'location' ? `<p>원천 물량 ${sampleQuantity(r)}</p>` : ''}<p><a href="${esc(safeUrl(r.evidence_url))}" target="_blank" rel="noopener noreferrer">공식 원천 확인 ↗</a></p>${r.parent_sample_id ? `<button class="text-button" data-sample="${esc(r.parent_sample_id)}">주소 원천 표본 보기 ↗</button>` : ''}</div>${r.warnings.length ? `<div class="detail-section"><h3>확인이 필요한 항목</h3><ul>${r.warnings.map(w => `<li>${esc(warningNames[w] || w)}</li>`).join('')}</ul></div>` : ''}<div class="detail-section"><h3>수집·변경 이력</h3>${r.history.map(h => `<details><summary>revision ${h.revision_no} · ${timeText(h.recorded_at)}</summary><p>표본 수집일 ${esc(h.values.base_date)} · 인증정보 제거 후 저장한 API 응답</p><div class="hash">레코드 SHA-256 ${esc(h.payload_hash)}</div>${h.snapshots.map(s => `<p><a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">수집 요청 근거 ↗</a></p><div class="hash">응답 SHA-256 ${esc(s.sha256)}</div>`).join('')}</details>`).join('')}</div>`;
  } catch (error) {if (generation === state.detailGeneration) $('detail-content').innerHTML = empty(error.message);}
}
document.addEventListener('click', event => {
  const group=event.target.closest('[data-nav-group]');if(group){toggleNavGroup(group.dataset.navGroup,group.getAttribute('aria-expanded')!=='true');return;}
  const nav = event.target.closest('[data-view]'); if (nav) setView(nav.dataset.view);
  const row = event.target.closest('[data-project]'); if (row) openDetail(row.dataset.project);
  const sample = event.target.closest('[data-sample]'); if (sample) openSample(sample.dataset.sample);
  const identity = event.target.closest('[data-identity-open]'); if (identity) openIdentityEditor(identity.dataset.identityOpen);
  const identityPage = event.target.closest('[data-identity-page]');
  if (identityPage) {state.identityPage += identityPage.dataset.identityPage === 'next' ? 1 : -1; load();}
});
$('close-detail').addEventListener('click', () => {$('detail-dialog').close(); ++state.detailGeneration;});
$('detail-dialog').addEventListener('click', e => {if (e.target === $('detail-dialog')) $('detail-dialog').close();});
for (const id of ['region','policy','as-of','source-filter','stage-filter','mapping-filter','sample-kind','sample-year']) $(id).addEventListener('change', () => {state.page = 1; state.samplePage=1; load();});
let debounce;
$('search').addEventListener('input', () => {clearTimeout(debounce); debounce = setTimeout(() => {state.page = 1;state.samplePage=1; load();},250);});
$('reset').addEventListener('click', () => {for (const id of ['region','policy','search','source-filter','stage-filter','mapping-filter','sample-kind','sample-year']) $(id).value = ''; $('as-of').value = $('as-of').max; state.page = 1;state.samplePage=1;Roadmap.reset();HousingMap.reset(); load();});
$('prev').addEventListener('click', () => {if (state.page > 1) {state.page--; load();}});
$('next').addEventListener('click', () => {if (state.page * 25 < state.total) {state.page++; load();}});
$('sample-prev').addEventListener('click',()=>{if(state.samplePage>1){state.samplePage--;load();}});
$('sample-next').addEventListener('click',()=>{if(state.samplePage*100<state.sampleTotal){state.samplePage++;load();}});
$('refresh').addEventListener('click', async () => {
  $('refresh').disabled = true;
  try {await request('/admin/refresh', {method:'POST'}); $('refresh-status').textContent = '수집 요청을 접수했습니다. 결과는 자동 갱신됩니다.'; setTimeout(load,2000);} catch (error) {$('refresh-status').textContent = error.message; $('refresh').disabled = false;}
});
function setupSidebar() {
  const toggle=$('sidebar-toggle');
  try {if(localStorage.getItem('home-sidebar-collapsed')==='true')document.body.classList.add('sidebar-collapsed');}catch(_){}
  const sync=()=>{const collapsed=document.body.classList.contains('sidebar-collapsed');const label=collapsed?'왼쪽 메뉴 펼치기':'왼쪽 메뉴 접기';toggle.setAttribute('aria-expanded',String(!collapsed));toggle.setAttribute('aria-label',label);toggle.title=label;toggle.querySelector('span').textContent=collapsed?'»':'☰';};
  toggle.addEventListener('click',()=>{const collapsed=document.body.classList.toggle('sidebar-collapsed');try{localStorage.setItem('home-sidebar-collapsed',String(collapsed));}catch(_){}sync();setTimeout(()=>{if(state.view==='overview')HousingMap.visible();if(policyViews.has(state.view))PolicyGeo3D.resize();},220);});
  sync();
}
async function start() {
  setupSidebar();
  Roadmap.start();
  HousingMap.start();
  AreaDashboard.start();
  AnnualSupply.start();
  HistoryPanel.start();
  PolicyDashboard.start();MappingWorkbench.start();PolicySchematic.start();PolicyGeo3D.start();PolicyReport.start();Policy907.start();
  const day = new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul'}).format(new Date());
  $('as-of').value = day; $('as-of').max = day;
  try {
    const [policies,sources,admin] = await Promise.all([request('/policies'),request('/sources?compact=true'),request('/admin/status')]);
    state.policies = policies.items; state.sources = sources.items; state.admin = admin.authenticated;
    $('policy').innerHTML = '<option value="">정책 전체</option>' + policies.items.map(p => `<option value="${esc(p.policy_id)}">${esc(p.name)}</option>`).join('');
    $('policy').value = 'POL_2025_0907';
    $('source-filter').innerHTML = '<option value="">원천 전체</option>' + sources.items.filter(s => s.collection_mode !== 'TEST_SAMPLE' && s.type !== 'POLICY_FOLLOWUP').map(s => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join('');
    for (const source of sources.items) sourceNames.set(source.id,source.name);
    $('refresh').hidden = !state.admin;
    $('sample-refresh').hidden = !state.admin;
    if (state.admin) $('admin-link').textContent = '관리자로 로그인됨 ↗';
    setView(location.hash.slice(1) || 'overview',{replace:true,deferLoad:true});
    await load();
  } catch (error) {$('loading').hidden = true; $('error').hidden = false; $('error').textContent = error.message;}
}
window.addEventListener('popstate',()=>setView(location.hash.slice(1)||'overview',{fromHistory:true}));
window.addEventListener('hashchange',()=>setView(location.hash.slice(1)||'overview',{fromHistory:true}));
$('sample-refresh').addEventListener('click', async () => {
  $('sample-refresh').disabled = true;
  try {await request('/admin/refresh?mode=sample', {method:'POST'}); $('sample-refresh-status').textContent = '테스트 표본 수집을 요청했습니다. 결과는 자동 갱신됩니다.'; setTimeout(load,2000);} catch (error) {$('sample-refresh-status').textContent = error.message; $('sample-refresh').disabled = false;}
});
let sourcePolling=false;
setInterval(async()=>{
  if(sourcePolling||document.hidden||!$('loading').hidden||!state.sources.some(s=>s.status==='RUNNING'))return;
  sourcePolling=true;
  try{
    const signature=items=>JSON.stringify(items.map(s=>[s.id,s.status,s.last_success]));
    const previous=signature(state.sources),result=await request('/sources?compact=true');
    state.sources=result.items;
    if(previous!==signature(result.items))load();
  }catch(_){}finally{sourcePolling=false;}
},10000);
start();
