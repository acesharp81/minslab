/* 지역 번들 로더와 어댑터.
   regions/<slug>/*.json(번들)을 화면 코드(app.js)가 쓰는 전역 모양(GY_BUILDINGS · GY_PROJECTS · GY_CONTEXT · GY_INFRA)으로 바꾼다.
   순수 함수는 node --test 로 시험한다(tests/js/region.test.cjs). DOM 은 applyTexts · mount* · boot 에서만 만진다.
   필드 정의와 변환 규칙의 정본: docs/data-interface/번들-어댑터-정의서.md */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.RegionLoader = api;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const STATUS_RANK = ['분양중', '건설 단계', '준공 임박', '입주 단계', '계획'];
  const OUTLINE_TEXT = { official: '블록 윤곽은 공식 자료', building: '동 윤곽은 실제 건물 자료', schematic: '동 윤곽은 근사값(10~20 m)' };
  const TIER_ORDER = ['official', 'building', 'schematic'];
  const CODE_PARAMS = ['project', 'pnu', 'bjd', 'sgg', 'code'];   // 우선순위 순서(사업 id 가 가장 구체적이다)
  const FLOOR_HEIGHT = 2.85;   // 층고를 모를 때(화면의 기본 환산과 같은 값)

  const escapeHtml = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const finite = (v) => typeof v === 'number' && Number.isFinite(v);

  /* ---------- 지역 고르기 ---------- */
  function pickRegion(index, search) {
    const regions = (index && index.regions) || [];
    if (!regions.length) return { error: 'empty', regions };
    const want = new URLSearchParams(search || '').get('region');
    if (want) {
      const r = regions.find((x) => x.slug === want);
      return r ? { region: r } : { error: 'unknown', requested: want, regions };
    }
    return { region: regions.find((x) => x.default) || regions[0] };
  }
  function selectorModel(index, slug) {
    const regions = (index && index.regions) || [];
    return { visible: regions.length >= 2, options: regions.map((r) => ({ value: r.slug, label: r.name, selected: r.slug === slug })) };
  }
  function regionUrl(href, slug) {
    const u = new URL(href);
    u.searchParams.delete('block');
    u.searchParams.delete('homeProject');
    for (const n of CODE_PARAMS) u.searchParams.delete(n);   // 지역을 고르면 코드 진입은 끝난다
    u.searchParams.set('region', slug);
    return u.toString();
  }

  /* ---------- 표준코드로 열기 (?project= | ?pnu= | ?bjd= | ?sgg= | ?code=) ----------
     코드가 있으면 코드가 우선이다(둘 이상이면 project > pnu > bjd > sgg > code 중 앞선 하나). ?region= 만 있으면 옛 방식 그대로.
     코드는 /api/v1/resolve 가 해석하고, 번들이 있는 시군구(등급 A)만 지도를 연다. 스펙: docs/product/상황판-스펙.md 2.1 */
  function codeQuery(search) {
    const p = new URLSearchParams(search || '');
    for (const n of CODE_PARAMS) if (p.has(n)) return { name: n, value: p.get(n) };
    return null;
  }
  const resolveUrl = (cq, base) => `${base || 'api/v1/resolve'}?${new URLSearchParams({ [cq.name]: cq.value, geometry: '1' })}`;   // 경계도 함께 받는다(번들 없는 지역은 경계가 지도의 전부)
  /* 주소 이동 입력줄이 고른 곳으로 지도를 여는 주소: 코드 매개변수를 이 하나로 바꾸고 region·block·at 은 지운다(보던 상태 mode·panel 등은 남김).
     at 은 도로명 주소처럼 좌표가 있을 때만 '경도,위도,확대' 로 붙인다 */
  function codeUrl(href, name, value, at) {
    const u = new URL(href);
    for (const n of CODE_PARAMS) u.searchParams.delete(n);
    for (const n of ['region', 'block', 'at']) u.searchParams.delete(n);
    u.searchParams.set(name, value);
    if (at) u.searchParams.set('at', at);
    return u.toString();
  }
  /* 코드 입력을 지역 번들 주소(?region=slug)로 바꾼다. 코드 매개변수는 지우고 나머지(at·mode 등)는 그대로 둔다 */
  function withRegion(search, slug) {
    const p = new URLSearchParams(search || '');
    for (const n of CODE_PARAMS) p.delete(n);
    p.set('region', slug);
    return `?${p}`;
  }
  /* bbox 가 화면(가로 px)에 들어가는 확대 단계(타일 512 px 기준). 지도 앱의 minZoom 11 아래로는 내려가지 않는다 */
  function zoomForBbox(bbox, px = 700) {
    if (!Array.isArray(bbox) || bbox.length !== 4 || !bbox.every(finite)) return null;
    const lon = Math.max(bbox[2] - bbox[0], 1e-4);
    return Math.max(11, Math.min(16, Math.log2((px * 360) / (512 * lon)) - 0.2));
  }
  /* 해석 결과 → 지도 시작 위치. 번들이 있는 시군구는 지역 기본 시점이라 null. 법정동은 한눈에, 필지는 가까이,
     번들이 없는 시군구는 경계가 한눈에 보이게 */
  function resolvedStart(r) {
    if (!r || !Array.isArray(r.center) || r.center.length !== 2 || !r.center.every(finite)) return null;
    const none = !r.coverage || r.coverage.tier !== 'A';
    if (r.type === 'sgg' || (r.type === 'project' && !r.bjd && !r.pnu)) { const z = none ? zoomForBbox(r.bbox) : null; return z == null ? null : { center: r.center, zoom: Math.round(z * 10) / 10 }; }
    const parcel = (r.type === 'pnu' || r.type === 'project') && r.parcel && r.parcel.geometry;   // 사업 id 로 열었어도 필지가 연결돼 있으면 필지로
    return { center: r.center, zoom: parcel ? 17.6 : 15.4 };
  }
  /* 강조해서 그릴 경계: 필지가 있으면 필지, 없으면 법정동 경계(필지를 못 찾아 후퇴한 경우 포함).
     시군구는 번들이 있으면 그리지 않고(지구 경계가 있음) 번들이 없으면 시군구 경계가 화면의 전부다 */
  function resolvedShape(r) {
    if (!r) return null;
    if ((r.type === 'sgg' || (r.type === 'project' && !r.bjd && !r.pnu)) && r.coverage && r.coverage.tier === 'A') return null;   // 번들이 있는 시군구(사업이 위치 없이 시군구까지만 열린 경우 포함)는 지구 경계가 있어 그리지 않는다
    const g = ((r.type === 'pnu' || r.type === 'project') && r.parcel && r.parcel.geometry) || r.geometry;
    return g && g.type && g.coordinates ? g : null;
  }
  /* 건축HUB 인허가 사업(/api/v1/permits 의 features)을 번들 단지(projects.json 의 한 항목) 모양으로. 시행자·분양 정보가 없어 sponsorClass 는 'unknown' 이고
     상태는 인허가로 아는 3가지(계획·건설 단계·입주 단계)뿐이다. 윤곽은 필지(연속지적도), 동(3D)은 없다 */
  const HUB_SOURCES = [
    { id: 'hub-housing-permit', label: '건축HUB 주택인허가정보(번지 단위 집계)' },
    { id: 'vworld-cadastre', label: 'V-World 연속지적도(필지 경계)' },
  ];
  const LEDGER_SOURCE = { id: 'hub-bldrgst', label: '건축HUB 건축물대장정보(총괄표제부: 블록·합필 위치, 사용승인일)' };
  function permitsToProjects(fc) {
    const out = [];
    for (const f of (fc && fc.features) || []) {
      const p = f.properties || {}, ring = f.geometry && f.geometry.type === 'Polygon' ? f.geometry.coordinates[0] : null;
      if (!p.pnu || !ring || ring.length < 4) continue;
      const open = ring.slice(0, ring.length - 1);
      const byLedger = !!(p.via === 'ledger' || p.statusBy === 'ledger'), ledgerDone = !!(p.completedAt && (p.statusBy === 'ledger' || (p.ledger && p.ledger.useAprDay === p.completedAt)));
      const dates = [p.approvedAt ? `사업승인 ${p.approvedAt}` : '', p.startedAt ? `착공 ${p.startedAt}` : '', p.completedAt ? `${ledgerDone ? '사용승인(건물대장)' : '사용검사'} ${p.completedAt}` : ''].filter(Boolean).join(' · ');
      /* 건물대장으로 위치를 정했으면 근거를 적는다: 블록 단위 허가(필지 번호 없음)는 세대수·대지면적이 맞는 대장 지번, 합필·분할은 현재 지번 */
      const where = p.via === 'ledger' ? `건물대장 기준 위치${p.block ? `(허가는 블록 단위 ${p.block})` : p.hubJibun ? `(허가 지번 ${p.hubJibun}은 합필·분할로 지금은 없음)` : ''}: ${p.ledger && p.ledger.by === 'name' ? '세대수·단지명 일치(허가에 대지면적 기록이 없음)' : `세대수 일치, 대지면적 오차 ${p.ledger && finite(p.ledger.areaDiff) ? `${p.ledger.areaDiff}%` : '2% 이내'}`}` : '';
      /* 예정일이 지났는데 착공·사용검사 기록이 원천에 없으면 사실만 적는다(지연이라고 판정하지 않음) */
      const late = p.overdue ? `${p.overdue.kind} 예정일 ${p.overdue.plannedAt}이 ${p.overdue.months >= 1 ? `${p.overdue.months}개월` : '얼마'} 지났으나 ${p.overdue.kind} 기록이 없음` : (p.status === '계획' && !p.plannedStart ? '착공 기록 없음' : '');
      out.push({
        id: `hub-${p.pnu}`, projectId: /^PRJ-\d{5}-\d{4}$/.test(p.projectId || '') ? p.projectId : null, zoneId: 'hub', label: p.label || p.name, name: p.name, sponsor: { type: 'unknown', name: '' }, sponsorClass: 'unknown',
        kind: '인허가 사업', status: p.status, units: finite(p.units) ? p.units : null, dongCount: finite(p.mainBldCnt) ? p.mainBldCnt : 0,
        moveIn: p.status === '입주 단계' ? (p.completedAt ? p.completedAt.slice(0, 7) : null) : (p.plannedCompletion || null),
        outline: { tier: 'official', poly: open, how: p.via === 'ledger' ? '건물대장이 가리키는 대지 필지(연속지적도)' : '건축HUB 인허가의 대지 필지(연속지적도)' }, dongs: null, events: [], sources: byLedger ? ['hub-housing-permit', 'hub-bldrgst', 'vworld-cadastre'] : ['hub-housing-permit', 'vworld-cadastre'],
        note: [p.address, where, `허가 기록 ${p.records}건`, dates, p.status === '계획' && p.plannedStart && !p.overdue ? `착공 예정 ${p.plannedStart}` : '', late, '시행자·분양 정보는 없음'].filter(Boolean).join(' · '),
      });
    }
    return out;
  }
  /* 번들이 없는 지역(등급 B·C)을 여는 빈 번들. 건물은 화면이 요청 시 칸 단위로 불러 붙이므로(GY_BUILDINGS.dynamic) 처음엔 비어 있고,
     법정동·필지로 열었으면 그 법정동의 건축HUB 인허가 사업(permits)이 단지로 들어간다 */
  function emptyBundle(resolved, index, permits, infra, opts) {
    const name = resolved.name || '번들 없는 지역';
    const z = zoomForBbox(resolved.bbox) || 12;
    const projects = permitsToProjects(permits);
    const m0 = (permits && permits.meta) || {};
    const lost = (m0.unlocatedList || []).slice(0, 8);
    const blk = (m0.blockList || []).slice(0, 6);
    const lg = m0.ledger || {};
    const ledgerNote = [lg.blocksMatched || lg.parcelsRecovered || lg.completions ? `건축물대장으로 보강: 블록 단위 허가 ${lg.blocksMatched || 0}곳의 위치, 합필·분할로 사라진 지번 ${lg.parcelsRecovered || 0}곳의 현재 지번, 사용승인으로 준공 확인 ${lg.completions || 0}곳.` : '', lg.error ? `건축물대장 보강이 완전하지 않습니다: ${lg.error}.` : ''].filter(Boolean);
    const blockNote = m0.blockProjects ? [`공공주택지구 블록 단위 허가 ${m0.blockProjects}곳은 필지 번호가 없어(블록 번호만 있음) ${lg.used ? '건축물대장과 세대수·대지면적을 맞춰 보았지만 지번을 정하지 못해' : '위치를 정할 수 없어'} 지도에 없습니다: ${blk.map((x) => `${x.name}${x.block && !x.name.includes(x.block) ? `(${x.block})` : ''} ${x.units ? `${x.units}세대` : ''}`.trim()).join(', ')}${m0.blockProjects > blk.length ? ' 외' : ''}.`] : [];
    const im = (infra && infra.type === 'Infra' && infra.meta) || {};
    const infraNotes = [im.stopsSource === 'osm' ? `버스 정류장: 국토교통부 TAGO${im.seoulError ? '·서울시' : ''}에 이 지역 자료가 없어 OpenStreetMap 기준으로 보여 드립니다(누락이 있을 수 있습니다).` : '', im.stopsSource === 'seoul' ? '버스 정류소: 서울특별시 정류소정보조회 기준입니다(국토교통부 TAGO에는 서울 자료가 없습니다).' : '', im.seoulError ? `서울시 정류소: ${im.seoulError}.` : '', im.noBus ? '버스 정류소: 국토교통부 TAGO에 이 지역(서울 등)의 정류소 자료가 없어 교통 점검은 "자료 없음"입니다.' : '', im.schoolsError ? '신설예정 학교를 불러오지 못했습니다.' : '', im.stopsError ? `${im.stopsError}.` : ''].filter(Boolean);
    const infraLate = opts && opts.infraFailed ? ['기반시설(신설예정 학교·정류장)을 제때 불러오지 못해 입주 전 점검 없이 열었습니다. 잠시 뒤 다시 열면 나올 수 있습니다.'] : [];
    const notes = (lost.length ? [`건축HUB 인허가 사업 후보 중 필지를 못 찾아 지도에 없는 ${m0.unlocated}곳: ${lost.map((x) => `${x.name}(${x.jibun})`).join(', ')}${m0.unlocated > lost.length ? ' 외' : ''}. 원인 추정: ${[...new Set(lost.map((x) => x.reason))].join(' / ')}.`] : []).concat(blockNote, ledgerNote, infraNotes, infraLate);
    const region = {
      slug: '', name, notes, title: `${name} (번들 없음)`, description: `${name}의 경계와 건물을 보여 줍니다. 공급 사업은 건축HUB 인허가 기록에서 요청 시 조회한 것만 있습니다.`,
      view: { center: resolved.center || [127.0, 37.5], zoom: Math.round(z * 10) / 10, pitch: 50, bearing: 0 }, sources: projects.length ? (projects.some((x) => x.sources.includes('hub-bldrgst')) ? [HUB_SOURCES[0], LEDGER_SOURCE, HUB_SOURCES[1]] : HUB_SOURCES) : [], zones: [],
    };
    const buildings = { type: 'FeatureCollection', meta: { basis: '', factor: {} }, features: [], dynamic: true };
    const b = Object.assign({ ok: true }, adaptBundle({ index: index || { regions: [] }, entry: { visibility: 'public' }, region, projects: { projects, otherBlocks: [] }, buildings, context: null, infra: hasInfra(infra) && projects.length ? infraOf(infra) : null }));
    b.nearby = (Array.isArray(resolved.neighbors) ? resolved.neighbors : []).filter((x) => x && /^\d{10}$/.test(String(x.bjd)) && x.name).map((x) => ({ bjd: String(x.bjd), name: String(x.name) })).slice(0, 150);   // 같은 시군구의 다른 법정동(빈 지역에서 고르게)
    const m = (permits && permits.meta) || {};
    b.permits = { fetched: !!(permits && permits.type === 'FeatureCollection'), count: projects.length, unlocated: m.unlocated || 0, truncated: !!m.truncated, records: m.records || 0, candidates: m.candidates || 0, blocks: m.blockProjects || 0, ledger: m.ledger || null };
    return b;
  }
  /* /api/v1/infra 응답 → 번들 infra.json 모양(schema_version·asOf·sources·schools·stops). 학교나 정류소가 하나도 없으면 쓰지 않는다 */
  const hasInfra = (d) => !!(d && d.type === 'Infra' && ((d.schools || []).length || (d.stops || []).length));
  const infraOf = (d) => ({ schema_version: '1.3.0', asOf: d.asOf, sources: d.sources || [], schools: d.schools || [], stops: d.stops || [] });
  /* 기반시설(신설예정 학교·정류장) 요청: 시간이 걸릴 수 있어 15초까지만 기다리고, 실패해도 지도는 열린다(null) */
  async function fetchInfra(win, bjd) {
    try {
      const res = await Promise.race([win.fetch(`api/v1/infra?bjd=${encodeURIComponent(bjd)}`), new Promise((_, no) => setTimeout(() => no(new Error('timeout')), 15000))]);
      if (!res.ok) return null;
      const d = await res.json();
      return d && d.type === 'Infra' ? d : null;
    } catch (e) { return null; }
  }
  /* 공공 모집 공고(마이홈) 요청: 사이드바를 늦게 채우므로 지도를 막지 않는다. 실패하면 null(구역을 숨김) */
  async function fetchNotices(win, sgg) {
    try {
      const res = await win.fetch(`api/v1/notices?sgg=${encodeURIComponent(sgg)}`);
      if (!res.ok) return null;
      const d = await res.json();
      return d && d.type === 'Notices' && Array.isArray(d.items) ? d : null;
    } catch (e) { return null; }
  }
  /* 공고 → 화면 줄(순수 함수): 제목 · 기관·유형·세대수 · 접수 기간 · 단지·주소 · 공고 링크(https 마이홈·LH 만) · 필지로 이동(pnu) */
  const md = (iso) => (/^\d{4}-\d{2}-\d{2}$/.test(iso || '') ? `${iso.slice(5, 7)}.${iso.slice(8, 10)}` : '');
  function noticeRows(data) {
    const kind = { rental: '임대', sale: '분양' };
    return ((data && data.items) || []).filter((n) => n && n.title).map((n) => {
      const from = md(n.applyFrom), to = md(n.applyTo);
      return {
        id: String(n.id || ''), title: String(n.title),
        meta: [n.agency, `${kind[n.kind] || ''}${n.supplyType ? `(${n.supplyType})` : ''}`.trim(), n.housingType, n.units ? `${n.units}세대` : ''].filter(Boolean).join(' · '),
        period: from && to ? `접수 ${from === to ? from : `${from}~${to}`}` : n.announcedAt ? `공고 ${n.announcedAt.replace(/-/g, '.')}` : '',
        place: [n.complex, n.address].filter(Boolean).join(' · '),
        url: /^https:\/\/(www\.myhome\.go\.kr|m\.myhome\.go\.kr|apply\.lh\.or\.kr)\//.test(n.url || '') ? n.url : '', pnu: /^\d{19}$/.test(n.pnu || '') ? n.pnu : '', fromLh: n.source === 'lh',
      };
    });
  }
  /* 건축HUB 인허가 요청: 실패해도 지도는 열린다(null) */
  async function fetchPermits(win, bjd) {
    try {
      const res = await win.fetch(`api/v1/permits?bjd=${encodeURIComponent(bjd)}`);
      if (!res.ok) return null;
      const d = await res.json();
      return d && d.type === 'FeatureCollection' && Array.isArray(d.features) ? d : null;
    } catch (e) { return null; }
  }
  /* 주소 ?permits=0 이면 번들 없는 지역에서 건축HUB 인허가 사업을 조회하지 않는다 */
  const permitsOff = (search) => new URLSearchParams(search || '').get('permits') === '0';
  /* 주소 ?dyn=0|1: 0 이면 건물을 요청 시 조회하지 않고, 1 이면 번들이 있는 지역에서도 번들 밖 건물을 요청 시 조회한다 */
  function dynParam(search) {
    const v = new URLSearchParams(search || '').get('dyn');
    return v === '0' ? 'off' : v === '1' ? 'on' : null;
  }

  /* 해석 경고(warnings) → 지도 위 한 줄 안내. 요청한 것과 다른 범위로 열렸을 때 조용히 넘기지 않는다(스펙 1.4) */
  const NOTICE_TEXT = {
    'parcel-not-found': '요청한 필지를 찾지 못해 법정동 경계로 열었습니다',
    'ri-uses-umd-boundary': '리(里) 경계는 없어 읍면동 경계로 표시합니다',
    'boundary-not-found': '경계를 찾지 못해 지역 기본 위치로 열었습니다',
    'geometry-unavailable': '경계를 불러오지 못해 지역 기본 위치로 열었습니다',
    'geometry-not-configured': '경계를 불러오지 못해 지역 기본 위치로 열었습니다',
    'project-unlocated': '이 사업의 위치(필지)가 아직 연결되지 않아 법정동 또는 시군구 경계로 열었습니다',
    'project-superseded': '합병되어 폐기된 사업 id 라서 남은 사업으로 열었습니다',
  };
  function noticeText(warnings) {
    return [...new Set((warnings || []).map((w) => NOTICE_TEXT[w]).filter(Boolean))].join(' · ');
  }
  const PROBLEM_TEXT = {
    'invalid-code': '코드 형식이 맞지 않습니다', 'unknown-code': '표준코드 표에 없는 코드입니다', 'unknown-project': '발급되지 않은 사업 id 입니다', 'unsupported-level': '시도 단위는 열 수 없습니다',
    'keys-exhausted': '오늘 코드 해석 한도에 닿았습니다. 잠시 뒤 다시 시도하세요', 'not-configured': '코드 해석 서비스가 설정되어 있지 않습니다', upstream: '코드 해석 서비스를 부르지 못했습니다',
  };
  /* /api/v1/resolve 호출 → { ok:true, data } | { ok:false, code, message } */
  async function resolveCode(f, cq, base) {
    let res;
    try { res = await f(resolveUrl(cq, base)); } catch (e) { return { ok: false, code: 'network', message: '코드 해석 서비스에 연결하지 못했습니다' }; }
    let body = null;
    try { body = await res.json(); } catch (e) { /* 본문 없음 */ }
    if (res.ok && body && body.coverage) return { ok: true, data: body };
    const code = (body && body.code) || (res.status === 404 || res.status === 405 ? 'unavailable' : 'upstream');
    return { ok: false, code, message: PROBLEM_TEXT[code] || '코드 해석 서비스를 쓸 수 없습니다', detail: body && body.detail ? String(body.detail) : '' };
  }

  /* ---------- 단지 변환 ---------- */
  function moveInText(moveIn, progressEnd, status) {
    const v = moveIn == null ? '' : String(moveIn).trim();
    if (/^\d{4}-\d{2}$/.test(v)) return v.replace('-', '.');
    if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return `준공 예정 ${v}`;
    if (v) return v;
    if (status === '입주 단계') return '입주 일자 미상';   // 이미 입주한 단지에 '시기 미정'은 어색하다
    return progressEnd ? `준공 예정 ${progressEnd}` : '입주 시기 미정';
  }
  function outlineText(outline) {
    const base = OUTLINE_TEXT[outline.tier] || '';
    return outline.how ? `${base} (${outline.how})` : base;
  }
  function sourcesText(p, region) {
    const label = {};
    (region.sources || []).forEach((s) => { label[s.id] = s.label; });
    return (p.sources || []).map((id) => label[id] || id).join(' · ');
  }
  function adaptDongs(dongs) {
    const out = [];
    for (const d of dongs) {
      const above = finite(d.floorsAbove) && d.floorsAbove > 0 ? d.floorsAbove : null;
      const hasH = finite(d.heightM) && d.heightM > 0;
      if (above == null && !hasH) continue;   // 층수도 높이도 모르는 동은 3D 로 그리지 않는다
      out.push({ no: String(d.no), floors: above != null ? above : Math.max(1, Math.round(d.heightM / FLOOR_HEIGHT)), h: hasH ? d.heightM : undefined, tier: d.tier, poly: d.poly });
    }
    return out;
  }
  function adaptProject(p, region) {
    const dongs = Array.isArray(p.dongs) ? adaptDongs(p.dongs) : undefined;
    const pr = p.progress || null;
    const b = {
      id: p.label, pid: p.id, projectId: p.projectId || null, label: p.label, name: p.name, kind: p.kind, status: p.status,
      units: finite(p.units) ? p.units : 0, unitsKnown: finite(p.units),
      dongCount: finite(p.dongCount) ? p.dongCount : (dongs ? dongs.length : 0),
      moveIn: moveInText(p.moveIn, pr && pr.end, p.status),
      poly: p.outline.poly, outlineTier: p.outline.tier,
      sponsorClass: p.sponsorClass, priv: p.sponsorClass === 'private_on_public_land',
      src: sourcesText(p, region), outlineHow: outlineText(p.outline),
    };
    if (pr) {
      b.progress = { rate: pr.rate, asOf: pr.asOf, history: pr.history || [] };
      if (pr.start) b.progress.start = pr.start;
      if (pr.end) b.progress.end = pr.end;
      if (pr.source) b.progress.source = pr.source;
    }
    if (dongs) b.dongs = dongs;
    if (p.builder) b.builder = p.builder;
    if (finite(p.contractAmountM)) b.contractM = p.contractAmountM;
    if (p.note) b.note = p.note;
    if (p.candidateIds) {
      b.candidateIds = p.candidateIds; b.candidateNames = p.candidateNames;
      b.homeModelKind = p.homeModelKind; b.homeLocationMode = p.homeLocationMode;
      b.outlineHow = p.outline.how;
      b.primaryCandidateId = p.primaryCandidateId;
    }
    return b;
  }
  function uniqueIds(blocks) {
    const seen = new Map();
    blocks.forEach((b) => {
      const n = (seen.get(b.label) || 0) + 1;
      seen.set(b.label, n);
      if (n > 1) b.id = `${b.label}·${n}`;
    });
  }
  function orderBlocks(blocks, pinned) {
    const pos = new Map((pinned || []).map((id, i) => [id, i]));
    const rank = (b) => { const i = STATUS_RANK.indexOf(b.status); return i < 0 ? STATUS_RANK.length : i; };
    return blocks.slice().sort((a, c) => {
      const pa = pos.has(a.pid) ? pos.get(a.pid) : Infinity, pc = pos.has(c.pid) ? pos.get(c.pid) : Infinity;
      if (pa !== pc) return pa < pc ? -1 : 1;
      return (rank(a) - rank(c)) || (c.units - a.units) || String(a.label).localeCompare(String(c.label), 'ko');
    });
  }

  /* ---------- 문구 ---------- */
  function buildTexts(region, blocks, context, infra) {
    const tiers = new Set();
    blocks.forEach((b) => { tiers.add(b.outlineTier); (b.dongs || []).forEach((d) => tiers.add(d.tier)); });
    const phrases = TIER_ORDER.filter((t) => tiers.has(t)).map((t) => OUTLINE_TEXT[t]);
    const tierSentence = phrases.length ? `${phrases.join(', ')}입니다.` : '';
    const label = {};
    (region.sources || []).forEach((s) => { label[s.id] = s.label; });
    const progressLabels = [...new Set(blocks.filter((b) => b.progress && b.progress.source).map((b) => label[b.progress.source]).filter(Boolean))];
    const progressSentence = progressLabels.length ? `공정율은 ${progressLabels.join(', ')} 기준입니다.` : '';
    const ctxSentence = context ? `역·학교는 ${/OpenStreetMap/.test(context.source || '') ? 'OpenStreetMap' : (context.source || '출처 미상')}입니다.` : '';
    const infraSentence = infra && infra.asOf ? `기반시설 점검 자료는 ${infra.asOf} 기준 공개 자료입니다.` : '';
    const parts = [tierSentence, progressSentence, ctxSentence, infraSentence, ...(region.notes || [])].filter(Boolean).join(' ');
    return {
      documentTitle: `주택파동 공급 지도 (${region.name})`,
      eyebrow: region.title,
      description: region.description || '',
      footerHtml: `건물 © 국토교통부 GIS건물통합정보 (V-World)<br><span id="basis">-</span> 기준${parts ? `<details class="fnote"><summary>자료 안내</summary>${escapeHtml(parts)}</details>` : ''}`,   // 윤곽·공정율·출처 설명은 길어서 접어 둔다
    };
  }

  /* ---------- 번들 전체 변환 ---------- */
  function adaptBundle(raw) {
    const { index, entry, region, projects, buildings, context, infra } = raw;
    let blocks = (projects.projects || []).map((p) => adaptProject(p, region));
    blocks = orderBlocks(blocks, region.projectOrder);
    uniqueIds(blocks);   // 구분 접미사(·2)는 화면에 보이는 순서를 따른다
    const districts = (region.zones || []).filter((z) => Array.isArray(z.poly) && z.poly.length >= 3).map((z) => ({ name: z.name, poly: z.poly }));
    const byKey = new Map();
    blocks.forEach((b) => { byKey.set(b.id, b); byKey.set(b.pid, b); });
    return {
      slug: region.slug, name: region.name, title: region.title, description: region.description || '',
      visibility: (entry && entry.visibility) || 'public', view: region.view, statusOrder: region.statusOrder,
      sources: region.sources || [], zones: region.zones || [], districts,
      blocks, otherBlocks: projects.otherBlocks || [], hasPrivate: blocks.some((b) => b.priv),
      GY_BUILDINGS: buildings,
      GY_PROJECTS: { blocks, district: districts[0] || null, districts, otherBlocks: projects.otherBlocks || [], meta: {} },
      GY_CONTEXT: context || null,
      GY_INFRA: infra || null,
      texts: buildTexts(region, blocks, context || null, infra || null),
      regions: (index && index.regions) || [],
      resolveBlock: (param) => (param ? byKey.get(String(param)) || null : null),
    };
  }

  /* PoC 10 후보를 원래 단지·동 렌더러의 입력으로 변환한다. 위치 연결·공식 형상·가상 모형의
     근거는 별도 속성으로 보존하고, 위치 미확보 모형은 배경지도 없는 장면에서만 연다. */
  const HOME_REGIONS = [
    { slug: 'home-907', name: '9·7 전체 후보', policyId: 'POL_2025_0907', view: { center: [127.15, 37.45], zoom: 8.4, pitch: 52, bearing: 0 } },
    { slug: 'home-907-seoul', name: '9·7 서울', policyId: 'POL_2025_0907', region: '서울특별시', view: { center: [127.03, 37.56], zoom: 10.2, pitch: 52, bearing: 0 } },
    { slug: 'home-907-gyeonggi', name: '9·7 경기', policyId: 'POL_2025_0907', region: '경기도', view: { center: [127.15, 37.45], zoom: 8.7, pitch: 52, bearing: 0 } },
  ];
  function homeScope(data, slug) {
    const choice = HOME_REGIONS.find((x) => x.slug === slug);
    if (!choice || !data || data.format !== 'poc12-home10-map/1' || !Array.isArray(data.projects)) throw new Error('HOME 지도 자료 형식이 맞지 않습니다');
    const selected = (region) => !choice.region || region === choice.region;
    const projects = data.projects.filter((p) => selected(p.region) && (!choice.policyId || p.policyId === choice.policyId));
    const counts = new Map();
    const key = (region, name) => `${region}|${String(name || '').replace(/[시군구]$/, '')}`;
    projects.forEach((p) => { if (p.municipality) counts.set(key(p.region, p.municipality), (counts.get(key(p.region, p.municipality)) || 0) + 1); });
    const fc = (features) => ({ type: 'FeatureCollection', features });
    return {
      projects,
      regions: fc(data.regions.features.filter((f) => selected(f.properties.name))),
      municipalities: fc(data.municipalities.features.filter((f) => selected(f.properties.region)).map((f) => ({ ...f, properties: { ...f.properties, candidateCount: counts.get(key(f.properties.region, f.properties.name)) || 0 } }))),
      lands: fc(data.housingLands.features.filter((f) => !choice.region || (f.properties.regions || []).includes(choice.region))),
    };
  }
  function homeBundle(data, index, slug, scene = null, selected = null) {
    const choice = HOME_REGIONS.find((x) => x.slug === slug), home = homeScope(data, slug);
    const ids = new Set(home.projects.map((p) => p.id));
    const sites = (scene?.sites || []).filter((site) => site.candidateIds.some((id) => ids.has(id)));
    const previews = (scene?.previews || []).filter((site) => site.candidateIds.some((id) => ids.has(id)));
    const preview = previews.find((site) => site.candidateIds.includes(selected)) || (!sites.length ? previews[0] : null);
    const models = preview ? [preview] : sites;
    const showcase = models.find((site) => site.candidateIds.includes(selected))
      || models.find((site) => site.homeModelKind === 'OBSERVED_BUILDINGS') || models[0];
    home.sites = sites; home.previewModels = previews; home.isSchematicPreview = !!preview;
    home.previewProjectId = preview?.primaryCandidateId || null;
    home.sceneSummary = scene?.summary || null;
    const region = {
      slug, name: choice.name, title: `${choice.name} · PoC 10 사업후보`,
      description: 'PoC 10 사업후보와 위치 근거를 원래 3D 공급 지도에서 조회합니다. 정책 연결은 검토 상태입니다.',
      view: showcase ? { center: showcase.center, zoom: 15.8, pitch: 58, bearing: -10 } : choice.view, zones: [],
      sources: [{ id: 'home10', label: 'PoC 10 9·7 관련 사업후보 원천' }, { id: 'vworld-buildings', label: 'V-World GIS건물통합정보 · 공간 연결 검토' }, { id: 'illustration', label: '계획 규모에 따른 가상 모형 · 실제 설계 아님' }],
      notes: ['후보 위치는 LH 블록 라벨점 연결 검토입니다. 공식 건물 형상과 가상 아파트 모형을 구분하며 가상 모형의 동수·층수·배치는 실제 설계가 아닙니다.'],
    };
    const allRegions = { ...index, regions: HOME_REGIONS.map(({ slug: hs, name, region: area }) => {
      const candidates = data.projects.filter((p) => p.policyId === 'POL_2025_0907' && (!area || p.region === area));
      const points = new Set(candidates.filter((p) => p.locationRole === 'LH_PUBLIC_BLOCK_LABEL_POINT' && p.locationJoinStatus === 'NAME_MATCH_REVIEW'
        && Number.isFinite(p.longitude) && Number.isFinite(p.latitude)).map((p) => p.locationAnchorId || `${p.longitude},${p.latitude}`));
      return { slug: hs, name: `${name.replace(' 후보', '')} ${candidates.length}건 · 위치 ${points.size}곳`, visibility: 'public' };
    }) };
    const buildings = { type: 'FeatureCollection', meta: scene?.buildings?.meta || { basis: '', factor: {} },
      features: preview ? [] : (scene?.buildings?.features || []).filter((f) => !choice.region || f.properties.homeRegion === choice.region), dynamic: !preview };
    const r = adaptBundle({ index: allRegions, entry: { visibility: 'public' }, region, projects: { projects: models, otherBlocks: [] }, buildings, context: null, infra: null });
    r.texts.footerHtml = `PoC 10 HOME · 건물 © 국토교통부 GIS건물통합정보 (V-World)<br><span id="basis">-</span> 기준<details class="fnote"><summary>자료 안내</summary>${escapeHtml(region.notes.join(' '))}</details>`;
    r.home = home;
    return { ok: true, ...r };
  }

  /* ---------- 불러오기 ---------- */
  async function loadRegion(opts) {
    const f = opts.fetch, base = opts.base || 'regions/';
    const getJson = async (url, optional) => {
      let res;
      try { res = await f(url); } catch (e) { throw new Error(`${url}: ${e.message}`); }
      if (!res.ok) {
        if (optional && res.status === 404) return null;
        throw new Error(`${url}: HTTP ${res.status}`);
      }
      try { return await res.json(); } catch (e) { throw new Error(`${url}: JSON을 읽을 수 없음 (${e.message})`); }
    };
    const index = await getJson(base + 'index.json');
    const params = new URLSearchParams(opts.search || '');
    const homeSlug = params.get('region') || (!params.toString() ? index.homeDefault : null);
    if (index.policyOnly) {
      const [data, scene] = await Promise.all([getJson('home10/map.json'), getJson('home10/scene.json', true)]);
      return homeBundle(data, index, HOME_REGIONS.some((x) => x.slug === homeSlug) ? homeSlug : 'home-907', scene, params.get('homeProject'));
    }
    if (HOME_REGIONS.some((x) => x.slug === homeSlug)) return homeBundle(await getJson('home10/map.json'), index, homeSlug);
    const pick = pickRegion(index, opts.search);
    if (pick.error) return { ok: false, error: pick.error, requested: pick.requested, regions: pick.regions, index };
    const dir = String(index.dataBase || base).replace(/\/?$/, '/') + pick.region.slug + '/';
    const region = await getJson(dir + 'region.json');
    const [projects, buildings, context, infra] = await Promise.all([getJson(dir + 'projects.json'), getJson(dir + 'buildings.json'), getJson(dir + 'context.json', true), getJson(dir + 'infra.json', true)]);
    return Object.assign({ ok: true }, adaptBundle({ index, entry: pick.region, region, projects, buildings, context, infra }));
  }

  /* ---------- 화면 반영(브라우저 전용) ---------- */
  function applyTexts(doc, r) {
    doc.title = r.texts.documentTitle;
    const meta = doc.querySelector('meta[name="description"]');
    if (meta && r.texts.description) meta.setAttribute('content', r.texts.description);
    const eb = doc.querySelector('.eyebrow');
    if (eb) eb.textContent = r.texts.eyebrow;
    const foot = doc.querySelector('.foot');
    if (foot) foot.innerHTML = r.texts.footerHtml;
  }
  function mountSelector(doc, r, win) {
    const box = doc.getElementById('regionBox'), sel = doc.getElementById('regionSel');
    if (!box || !sel) return;
    const m = selectorModel({ regions: r.regions }, r.slug);
    if (!m.visible) return;
    const none = !r.slug ? `<option value="" selected disabled hidden>${escapeHtml(r.name)} (번들 없음)</option>` : '';   // 번들 없는 지역은 목록에 없으므로 현재 값을 따로 보인다
    const homeChoices = r.regions.filter((o) => HOME_REGIONS.some((home) => home.slug === o.slug)).map((o) => ({ value: o.slug, label: o.name, selected: o.slug === r.slug }));
    const options = [...homeChoices, ...m.options.filter((o) => !homeChoices.some((h) => h.value === o.value))];
    if (r.home) box.dataset.policyOnly = 'true';
    sel.innerHTML = none + options.map((o) => `<option value="${escapeHtml(o.value)}"${o.selected ? ' selected' : ''}>${escapeHtml(o.label)}</option>`).join('');
    sel.addEventListener('change', () => { win.location.assign(regionUrl(win.location.href, sel.value)); });
    box.hidden = false;
  }
  /* 안내 띠: 한 줄 요약(brief)만 보이고 누르면 전체 문장을 편다(2026-10-10 피드백, 주소 입력줄 아래 반투명 띠 — goto.js 가 옮긴다).
     요약이 없거나 전체와 같으면 전체 한 줄 */
  function mountBanner(doc, r, notice, brief) {
    const el = doc.getElementById('pvBanner');
    const pre = r.visibility === 'preview';
    const text = [pre ? '미리보기 — 공개 전 자료입니다' : '', notice || ''].filter(Boolean).join(' · ');
    if (!el || !text) return;
    const short = [pre ? '미리보기' : '', brief || notice || ''].filter(Boolean).join(' · ');
    el.innerHTML = short === text ? `<span class="pv-s">${escapeHtml(text)}</span>`
      : `<details class="pv-d"><summary class="pv-s">${escapeHtml(short)}</summary><p class="pv-f">${escapeHtml(text)}</p></details>`;
    el.hidden = false;
  }
  /* 안내 띠의 한 줄 요약: 번들 없는 지역은 무엇을 보여 주는지만 짧게(전체 문장은 mountResolved 의 baseNote). 번들 지역의 경고는 짧아서 그대로 */
  function bannerBrief(r, warnings) {
    const pm = r.permits, warn = noticeText(warnings);
    if (r.slug) return warn;
    const found = pm && pm.ledger ? pm.ledger.blocksMatched + pm.ledger.parcelsRecovered : 0;
    const extra = [found ? `대장으로 찾음 ${found}` : '', pm && pm.unlocated ? `제외 ${pm.unlocated}` : ''].filter(Boolean).join(' · ');
    const base = pm && pm.count ? `번들 없는 지역 · 인허가 사업 ${pm.count}곳${extra ? ` (${extra})` : ''}`
      : pm && pm.fetched && pm.blocks ? `번들 없는 지역 · 블록 단위 인허가 ${pm.blocks}곳은 지도에 못 그림`
      : pm && pm.fetched ? '번들 없는 지역 · 이 법정동 인허가 사업 없음'
      : '번들 없는 지역 · 경계·건물만';
    return [warn ? `위치 안내 ${warn.split(' · ').length}건` : '', base].filter(Boolean).join(' · ');
  }
  function showFatal(doc, html) {
    const f = doc.getElementById('fatal'), l = doc.getElementById('loading');
    if (l) l.hidden = true;
    if (f) { f.innerHTML = html; f.hidden = false; }
  }
  /* 코드 해석이 안 될 때 보여 줄 지역 목록 링크(index 를 못 읽으면 빈 문자열) */
  async function regionLinks(win) {
    try {
      const idx = await (await win.fetch('regions/index.json')).json();
      const items = (idx.regions || []).map((x) => `<li><a href="?region=${encodeURIComponent(x.slug)}">${escapeHtml(x.name)}</a></li>`).join('');
      return items ? `<ul>${items}</ul>` : '';
    } catch (e) { return ''; }
  }
  /* 불러와 전역에 올리고 문구·지역 선택기·배너를 반영한다. 실패하면 안내 화면을 보이고 {ok:false} 를 돌려 준다. */
  async function boot(win, doc) {
    let r, search = win.location.search, resolved = null;
    const cq = codeQuery(search);
    if (cq) {
      const rr = await resolveCode((u) => win.fetch(u), cq);
      if (!rr.ok) {
        showFatal(doc, `<p>${escapeHtml(rr.message)}</p>${rr.detail ? `<p><code>${escapeHtml(rr.detail)}</code></p>` : ''}${await regionLinks(win)}`);
        return { ok: false, error: 'code', code: rr.code };
      }
      resolved = rr.data;
      if (resolved.coverage.tier !== 'A') {
        /* 번들이 없는 지역(등급 B·C): 경계와 요청 시 조회한 건물만 보이는 빈 번들로 연다. ?dyn=0 이면 건물도 없이 경계만 */
        const idx = await getIndex(win);
        const permits = resolved.bjd && !permitsOff(search) ? await fetchPermits(win, resolved.bjd) : null;
        const wantInfra = !!(permits && permits.features && permits.features.length) && new URLSearchParams(search).get('infra') !== '0';   // 인허가 단지가 있어야 점검할 대상이 있다
        const infra = wantInfra ? await fetchInfra(win, resolved.bjd) : null;   // 서버가 인허가를 CDN 에서 이어 받으므로 인허가 다음에
        r = emptyBundle(resolved, idx, permits, infra, { infraFailed: wantInfra && !infra });
        if (dynParam(search) === 'off') r.GY_BUILDINGS.dynamic = false;
        mountResolved(win, doc, r, resolved);
        return r;
      }
      search = withRegion(search, resolved.coverage.slug);
    }
    try {
      r = await loadRegion({ fetch: (u) => win.fetch(u), search });
    } catch (e) {
      showFatal(doc, `<p>지역 자료를 불러오지 못했습니다.</p><p><code>${escapeHtml(e.message)}</code></p>`);
      return { ok: false, error: 'load', message: e.message };
    }
    if (!r.ok) {
      const links = (r.regions || []).map((x) => `<li><a href="?region=${encodeURIComponent(x.slug)}">${escapeHtml(x.name)}</a></li>`).join('');
      showFatal(doc, `<p>${r.error === 'unknown' ? `‘${escapeHtml(r.requested)}’ 지역을 찾을 수 없습니다.` : '볼 수 있는 지역이 없습니다.'}</p>${links ? `<ul>${links}</ul>` : ''}`);
      return r;
    }
    /* 번들이 있는 지역: 코드로 열었거나 ?dyn=1 이면 번들 밖 건물도 요청 시 조회한다(번들은 지구 주변만 담은 지역이 있음) */
    const dyn = dynParam(search);
    if (r.GY_BUILDINGS && dyn !== 'off' && (dyn === 'on' || resolved)) r.GY_BUILDINGS.dynamic = true;
    mountResolved(win, doc, r, resolved);
    return r;
  }
  /* 전역에 올리고 문구·지역 선택기·배너를 반영 */
  function mountResolved(win, doc, r, resolved) {
    win.GY_BUILDINGS = r.GY_BUILDINGS; win.GY_PROJECTS = r.GY_PROJECTS; win.GY_CONTEXT = r.GY_CONTEXT; win.GY_INFRA = r.GY_INFRA; win.REGION = r;
    const hit = resolved && ((resolved.pnu && r.blocks.find((b) => b.pid === `hub-${resolved.pnu}`))   // 필지로 열었는데 그 필지가 인허가 사업이면 그 단지를 연다
      || (resolved.project && resolved.project.block && r.blocks.find((b) => b.pid === resolved.project.block)));   // 사업 id 가 번들 단지의 것이면 그 단지를 연다
    win.RESOLVED = resolved ? { sgg: resolved.sgg, bjd: resolved.bjd || null, start: resolvedStart(resolved), shape: resolvedShape(resolved), name: resolved.name, level: resolved.level, type: resolved.type, parcel: !!(resolved.parcel && resolved.parcel.geometry), projectId: resolved.project ? resolved.project.id : null, tier: resolved.coverage.tier, warnings: resolved.warnings || [], block: hit ? hit.pid : null } : null;
    const pm = r.permits;
    const baseNote = r.slug ? '' : pm && pm.count ? `지역 번들이 없어 경계·건물(요청 시 조회)·건축HUB 인허가 사업 ${pm.count}곳만 보여 줍니다${pm.ledger && (pm.ledger.blocksMatched + pm.ledger.parcelsRecovered) ? `(건축물대장으로 위치를 찾은 ${pm.ledger.blocksMatched + pm.ledger.parcelsRecovered}곳 포함${pm.unlocated ? `, 필지를 못 찾은 ${pm.unlocated}곳 제외` : ''})` : pm.unlocated ? `(필지를 못 찾은 ${pm.unlocated}곳 제외)` : ''}`
      : pm && pm.fetched && pm.blocks ? `지역 번들이 없어 경계와 건물(요청 시 조회)만 보여 줍니다. 이 법정동의 건축HUB 인허가는 공공주택지구 블록 단위 ${pm.blocks}곳뿐이라 필지 번호가 없어 ${pm.ledger && pm.ledger.used ? '건축물대장과 맞춰 보아도 지번을 정하지 못해 ' : ''}지도에 그릴 수 없습니다`
      : pm && pm.fetched ? `지역 번들이 없어 경계와 건물(요청 시 조회)만 보여 줍니다. 건축HUB 주택인허가에 이 법정동의 공동주택 사업이 없습니다(기록 ${pm.records}건) — 이웃 법정동에 있을 수 있습니다`
      : '지역 번들이 없어 경계와 건물(요청 시 조회)만 보여 줍니다';
    const notes = [resolved ? noticeText(resolved.warnings) : '', baseNote].filter(Boolean).join(' · ');
    applyTexts(doc, r); mountSelector(doc, r, win); mountBanner(doc, r, notes, bannerBrief(r, resolved ? resolved.warnings : []));
  }
  async function getIndex(win) {
    try { return await (await win.fetch('regions/index.json')).json(); } catch (e) { return { regions: [] }; }
  }

  return { STATUS_RANK, escapeHtml, pickRegion, selectorModel, regionUrl, codeQuery, resolveUrl, withRegion, codeUrl, resolvedStart, resolvedShape, resolveCode, noticeText, zoomForBbox, emptyBundle, dynParam, permitsToProjects, fetchPermits, fetchInfra, fetchNotices, noticeRows, moveInText, outlineText, adaptDongs, adaptProject, orderBlocks, buildTexts, adaptBundle, homeScope, homeBundle, loadRegion, applyTexts, mountSelector, mountBanner, bannerBrief, boot };
});
