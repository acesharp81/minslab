/* 이동할 곳 검색 API: 사용자가 친 글자(법정동·시군구 이름, 지번·도로명 주소, 표준코드)를 지도가 열 수 있는 코드로 바꿔 후보로 돌려준다.
   화면의 "주소 이동" 입력줄(assets/js/goto.js)이 부른다. 후보를 고르면 화면이 ?pnu= | ?bjd= | ?sgg= 로 지도를 연다(/api/v1/resolve 가 해석).

   GET /api/v1/codes/search?q=<글자>&limit=<1~20, 기본 8>&near=<경도,위도>
   → 200 { items:[{ code, kind:'sgg'|'bjd'|'pnu', name, parts:{ sido, sgg, umd?, ri?, jibun?, road?, place? }, tier:'bundle'|'req'|'edge', point?:[경도,위도], road?, place?, category?, addr? }], meta:{ q, count, sources, partial?, reason?, detail?, asOf } }
   near 는 지금 보는 지도 가운데(선택): 장소 이름이 전국에 많을 때('시청') 가까운 것을 먼저 준다.
   → problem+json: invalid-query 400 · method 405 · keys-exhausted 429 · not-configured 503 · upstream 502

   처리:
   - 숫자만(공백·하이픈 허용)이면 코드로 본다: lib/codes.js 가 시군구 5 · 법정동 8/10 · PNU 19 자리를 판별하고 행정표준코드 표에 있는지 확인한다(없거나 자릿수가 틀리면 items [] + meta.reason).
   - 글자면 ① 행정표준코드 이름 부분 일치(locatadd_nm, 전국 최대 100행, 숫자 토큰은 지번으로 보고 뺌) → 법정동·시군구 ② V-World 장소(POI) 검색('하남시청'·'미사역'·'덕풍초등학교'): 지번 주소가 있는 장소만 PNU 로 열고(place:true, 좌표도 붙음),
     가까운 곳 먼저(near 가 있으면 ±0.25° 안을 따로 찾아 앞에 두고 전국 결과를 뒤에), 분류가 행정기관·학교·역·공원 같으면 앞, 입구·버스정류장·소매점은 뒤, 같은 이름·같은 자리는 하나로, 최대 5곳 ③ 숫자가 있으면 V-World 주소 API:
     지번(PARCEL)이 먼저이고 구조의 level4LC 가 필지(PNU)다(예 '장위동 68-37' → 1129013800100680037). 못 찾으면 도로명(ROAD): 법정동 이름으로 표준코드를 찾아 법정동 + 좌표로 연다.
   - tier: bundle = 번들이 있는 시군구(regions/), req = 번들이 없는 법정동·필지(경계·건물·인허가를 요청 시 조회), edge = 번들이 없는 시군구(경계만).
   - 한쪽(표준코드 또는 V-World)만 실패하면 나머지 후보를 주고 meta.partial 에 적는다(이때는 캐시하지 않음). 둘 다 실패하면 502.
   - 인증키: lib/keys.js 의 RESOLVE 용도 풀(서비스 stan), V-World 는 lib/vworld.js. 열린 중계가 되지 않게 인스턴스별 시간당 V-World 주소·장소 호출 상한(SEARCH_UPSTREAM_PER_HOUR, 기본 600).
     키·원천 URL·원천 오류 문구는 응답에 싣지 않는다. 표준코드·주소 조회는 각각 24시간 캐시, 응답은 CDN 1시간.
   시험: tests/js/codessearch.test.cjs */
'use strict';
const path = require('path');
const { createKeyPool, fileStore, memoryStore, KeyPoolError } = require('../../../lib/keys.js');
const { createCache, defaultDir } = require('../../../lib/cache.js');
const { VWORLD_ADDRESS_URL, VWORLD_SEARCH_URL, vworldCreds, redactVworld } = require('../../../lib/vworld.js');
const { createStan } = require('../../../lib/stan.js');
const { readCoverage } = require('../../../lib/coverage.js');
const codes = require('../../../lib/codes.js');

const MIN_Q = 2;
const MAX_Q = 60;
const DEFAULT_LIMIT = 8;
const MAX_LIMIT = 20;
const TTL_MS = 24 * 3600 * 1000;
const FETCH_TIMEOUT_MS = 10000;
const DEFAULT_BUDGET_PER_HOUR = 600;
const MAX_PLACES = 5;
const NEAR_LON = 0.28;                                  // near 둘레 상자(약 25 km). 가까운 장소를 따로 찾는다
const NEAR_LAT = 0.22;
const ALLOWED = new Set(['q', 'limit', 'near']);
const CAT_LOW = /진출입시설|버스|정류장|도로시설|소매업|도매업|제조업|음식점|은행|숙박|학원|주차장|서비스업/;   // 입구·정류장·가게는 뒤로
const CAT_HIGH = /지방행정기관|초등학교|중학교|고등학교|대학|지하철역|철도|공원|병원|구청|시청|군청|주민센터|행정복지센터|경찰서|소방서|우체국|문화시설|체육시설|관광/;   // '중앙행정기관'은 기상관측소·학교까지 들어 있어 쓰지 않는다
const catScore = (c, title) => (CAT_LOW.test(c) || /\/\d+동/.test(title || '') ? 2 : CAT_HIGH.test(c) ? 0 : 1);   // 아파트 '/601동' 같은 동 단위 기록도 뒤로
const JIBUN_TOKEN = /^(산)?\d+(-\d+)?$/;               // 지번 토큰(본번·부번, 산)
const LEVEL_RANK = { umd: 0, sgg: 1, ri: 2 };

const normalize = (s) => String(s == null ? '' : s).replace(/\s+/g, ' ').trim();

/* 표준코드 행 → 이름 구성(시도·시군구·읍면동·리). 시군구는 '수원시 장안구'처럼 두 낱말일 수 있다 */
function rowParts(row) {
  const t = String(row.locatadd_nm || '').split(' ').filter(Boolean), level = codes.levelOf(row), sido = t[0] || '';
  if (level === 'sgg') return { sido, sgg: t.slice(1).join(' ') };
  if (level === 'umd') return { sido, sgg: t.slice(1, -1).join(' '), umd: t[t.length - 1] };
  return { sido, sgg: t.slice(1, -2).join(' '), umd: t[t.length - 2], ri: t[t.length - 1] };
}

function createService(overrides = {}) {
  const env = overrides.env || process.env;
  const now = overrides.now || (() => Date.now());
  const doFetch = overrides.fetch || ((...a) => fetch(...a));
  const dir = overrides.cacheDir || defaultDir(env);
  const cache = overrides.cache || createCache({ dir, now });
  const pool = overrides.pool || createKeyPool({ env, now, store: env.VERCEL ? memoryStore() : fileStore(path.join(dir, 'key-usage.json')) });
  const sleep = overrides.sleep || ((ms) => new Promise((r) => setTimeout(r, ms)));
  const stan = createStan({ doFetch, pool, cache, sleep });
  const coverageOf = overrides.readCoverage || (() => readCoverage(undefined, env.VERCEL_ENV === 'production'));
  const budgetMax = Number(env.SEARCH_UPSTREAM_PER_HOUR) > 0 ? Math.floor(Number(env.SEARCH_UPSTREAM_PER_HOUR)) : DEFAULT_BUDGET_PER_HOUR;
  const budget = { hour: -1, used: 0 };
  const spend = (n) => {
    const hour = Math.floor(now() / 3600000);
    if (budget.hour !== hour) { budget.hour = hour; budget.used = 0; }
    if (budget.used + n > budgetMax) return false;
    budget.used += n;
    return true;
  };

  const send = (res, status, body, cacheControl, type = 'application/json; charset=utf-8') => {
    res.statusCode = status;
    res.setHeader('Content-Type', type);
    res.setHeader('Cache-Control', cacheControl);
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.end(JSON.stringify(body));
  };
  const problem = (res, status, code, title, detail, extra, cc) => send(res, status, Object.assign({ type: `/problems/${code}`, title, status, code, detail }, extra),
    cc || (status >= 500 || status === 429 ? 'no-store' : 'public, s-maxage=60'), 'application/problem+json; charset=utf-8');

  /* ---------- 후보 만들기 ---------- */
  const tierOf = (kind, sgg) => (coverageOf()[sgg] ? 'bundle' : kind === 'sgg' ? 'edge' : 'req');
  function rowItem(row, jibun) {
    const level = codes.levelOf(row);
    if (!LEVEL_RANK.hasOwnProperty(level)) return null;                                   // 시도는 지도 대상이 아니다
    const sgg = row.region_cd.slice(0, 5), parts = rowParts(row);
    if (jibun && level !== 'sgg') {                                                       // 코드로 친 PNU
      return { code: jibun.pnu, kind: 'pnu', name: `${row.locatadd_nm} ${jibun.jibun}`, parts: { ...parts, jibun: jibun.jibun }, tier: tierOf('pnu', sgg) };
    }
    const kind = level === 'sgg' ? 'sgg' : 'bjd';
    return { code: kind === 'sgg' ? sgg : row.region_cd, kind, name: row.locatadd_nm, parts, tier: tierOf(kind, sgg) };
  }

  /* 이름으로 표준코드 행 찾기. 지번 같은 숫자 토큰은 뺀다. 전체가 안 걸리면 가장 긴 낱말로 찾아 모든 낱말이 들어간 것만 남긴다('하남 감일동') */
  async function nameRows(q) {
    const tokens = q.split(' ').filter((t) => !JIBUN_TOKEN.test(t));
    if (!tokens.length || tokens.join('').length < MIN_Q) return [];
    let rows = await stan.search(tokens.join(' '));
    if (!rows.length && tokens.length > 1) {                                                // 구가 새로 생겨('화성시 동탄구 오산동') 낱말이 이어지지 않으면: 동·읍·면·리·가로 끝나는 낱말(가장 구별되는 것)로 찾아 나머지 낱말이 든 행만 남긴다
      const place = tokens.filter((t) => /[동읍면리가]$/.test(t)).sort((a, b) => b.length - a.length)[0];
      rows = await stan.search(place || tokens.slice().sort((a, b) => b.length - a.length)[0]);
    }
    const last = tokens[tokens.length - 1], whole = tokens.join(' ');
    const score = (r) => (r.locallow_nm === last || String(r.locatadd_nm).endsWith(whole) ? 0 : String(r.locallow_nm).includes(last) ? 1 : 2);
    return rows.filter((r) => tokens.every((t) => String(r.locatadd_nm).includes(t)) && LEVEL_RANK.hasOwnProperty(codes.levelOf(r)))
      .sort((a, b) => score(a) - score(b) || LEVEL_RANK[codes.levelOf(a)] - LEVEL_RANK[codes.levelOf(b)] || String(a.locatadd_nm).length - String(b.locatadd_nm).length);
  }

  /* V-World 주소 → 좌표·구조. 없으면 null, 일시 오류는 던진다(캐시 안 함). 24시간 캐시 */
  function geocode(type, q, creds) {
    return cache.wrap(`geo:${type}:${q}`, TTL_MS, async () => {
      if (!spend(1)) { const e = new Error('budget'); e.budget = true; throw e; }
      const qs = new URLSearchParams({ service: 'address', request: 'getcoord', version: '2.0', crs: 'epsg:4326', address: q, refine: 'true', simple: 'false', format: 'json', type, key: creds.key, domain: creds.domain });
      const r = await doFetch(`${VWORLD_ADDRESS_URL}?${qs}`, { signal: AbortSignal.timeout(FETCH_TIMEOUT_MS), headers: { Accept: 'application/json' } });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const res = (await r.json()).response, st = res && res.status;
      if (st === 'NOT_FOUND') return { none: true };
      if (st !== 'OK') throw new Error(`V-World ${(res && res.error && res.error.code) || st || '응답 형식'}`);
      const pt = res.result && res.result.point, ref = res.refined || {};
      const x = Number(pt && pt.x), y = Number(pt && pt.y);
      if (!Number.isFinite(x) || !Number.isFinite(y)) return { none: true };
      return { point: [Math.round(x * 1e6) / 1e6, Math.round(y * 1e6) / 1e6], text: String(ref.text || ''), st: ref.structure || {} };
    });
  }

  /* 숫자가 든 글자 → 지번(필지) 또는 도로명(법정동 + 좌표) 후보. 없으면 [] */
  async function addressItems(q, creds) {
    const parcel = await geocode('PARCEL', q, creds);
    if (!parcel.none) {
      const pnu = codes.clean(parcel.st.level4LC), c = pnu && codes.classify(pnu);
      if (c && c.ok && c.type === 'pnu') {
        const st = parcel.st;
        return [{ code: pnu, kind: 'pnu', name: parcel.text || q, parts: { sido: st.level1 || '', sgg: st.level2 || '', umd: st.level4L || '', jibun: st.level5 || '' }, tier: tierOf('pnu', c.sgg), point: parcel.point }];
      }
    }
    const road = await geocode('ROAD', q, creds);
    if (road.none || !road.st.level3) return [];
    const st = road.st, hit = (await nameRows(`${st.level1 || ''} ${st.level2 || ''} ${st.level3}`.trim())).find((r) => codes.levelOf(r) === 'umd');
    if (!hit) return [];
    return [{ code: hit.region_cd, kind: 'bjd', name: road.text || q, parts: { sido: st.level1 || '', sgg: st.level2 || '', umd: st.level3, road: `${st.level4L || ''} ${st.level5 || ''}`.trim() }, tier: tierOf('bjd', hit.region_cd.slice(0, 5)), point: road.point, road: true }];
  }

  /* V-World 장소(POI) 검색 → 원시 항목 목록(제목·분류·지번 주소·도로명·좌표). bbox 가 있으면 그 안에서만. 24시간 캐시, 일시 오류는 던진다 */
  function placeSearch(q, bbox, creds) {
    return cache.wrap(`place:${q}:${bbox ? bbox.join(',') : ''}`, TTL_MS, async () => {
      if (!spend(1)) { const e = new Error('budget'); e.budget = true; throw e; }
      const qs = new URLSearchParams({ service: 'search', request: 'search', version: '2.0', crs: 'EPSG:4326', size: '30', page: '1', query: q, type: 'place', format: 'json', errorformat: 'json', key: creds.key, domain: creds.domain });
      if (bbox) qs.set('bbox', bbox.join(','));
      const r = await doFetch(`${VWORLD_SEARCH_URL}?${qs}`, { signal: AbortSignal.timeout(FETCH_TIMEOUT_MS), headers: { Accept: 'application/json' } });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const res = (await r.json()).response, st = res && res.status;
      if (st === 'NOT_FOUND') return [];
      if (st !== 'OK') throw new Error(`V-World ${(res && res.error && res.error.code) || st || '응답 형식'}`);
      return ((res.result && res.result.items) || []).map((it) => ({
        title: normalize(it.title), category: normalize(it.category), parcel: normalize(it.address && it.address.parcel), road: normalize(it.address && it.address.road),
        point: [Number(it.point && it.point.x), Number(it.point && it.point.y)],
      })).filter((x) => x.title && x.point.every(Number.isFinite));
    });
  }
  /* '경기도 하남시 신장동 520대'·'경기도 하남시 감이동 291-18 잡' → { name:'경기도 하남시 신장동', san:false, bun:'520', ji:'0' }. 지번이 없으면 null */
  function splitParcel(s) {
    const t = normalize(s).split(' '), i = t.findIndex((x, k) => k >= 2 && (/^산?\d/.test(x) || (x === '산' && /^\d/.test(t[k + 1] || ''))));   // '520대'·'산3-1'·'산 3-1'
    if (i < 2) return null;
    const m = /^(산)?(\d+)(?:-(\d+))?/.exec(t[i] === '산' ? `산${t[i + 1]}` : t[i]);
    return m && m[2].length <= 4 && (m[3] || '').length <= 4 ? { name: t.slice(0, i).join(' '), san: !!m[1], bun: m[2], ji: m[3] || '0' } : null;
  }
  const distSq = (a, b) => ((a[0] - b[0]) * Math.cos(b[1] * Math.PI / 180)) ** 2 + (a[1] - b[1]) ** 2;
  /* 장소 이름 → 후보(필지 + 좌표). near 가 있으면 둘레 상자 안 결과를 따로 찾아 앞에 둔다. 지번 주소가 없거나 법정동을 못 찾는 장소는 뺀다 */
  async function placeItems(q, near, creds) {
    const bbox = near ? [near[0] - NEAR_LON, near[1] - NEAR_LAT, near[0] + NEAR_LON, near[1] + NEAR_LAT].map((v) => Math.round(v * 1e4) / 1e4) : null;
    const [close, all] = await Promise.all([bbox ? placeSearch(q, bbox, creds) : [], placeSearch(q, null, creds)]);
    const flat = q.replace(/\s/g, ''), prefix = (p) => { if (flat.length < 3) return 2; const t = p.title.replace(/\s/g, ''); return t === flat ? 0 : t.startsWith(flat) ? 1 : 2; };   // 세 글자 이상이면 이름이 그 글자와 같은 것 → 그 글자로 시작하는 것 순('하남시청' 이 '하남시청역' 보다 앞)
    const cand = [];
    [...close, ...all].forEach((p, order) => { if (splitParcel(p.parcel)) cand.push(Object.assign({ order }, p)); });
    cand.sort((a, b) => catScore(a.category, a.title) - catScore(b.category, b.title) || prefix(a) - prefix(b) || (near ? distSq(a.point, near) - distSq(b.point, near) : 0) || a.order - b.order);
    const seen = new Set(), top = [], rowOf = new Map();                                // 같은 필지의 장소(단지와 그 동들, 시청과 별칭)는 앞선 하나만
    for (const p of cand) { const sp = splitParcel(p.parcel), k = `${sp.name}|${sp.san}|${sp.bun}|${sp.ji}`; if (!seen.has(k)) { seen.add(k); top.push(p); if (top.length === 8) break; } }                                     // 법정동 이름은 겹치므로 한 번씩만(표준코드 API 는 초당 한도가 있다), 한 번에 둘까지만
    const names = [...new Set(top.map((p) => splitParcel(p.parcel).name))];
    for (let i = 0; i < names.length; i += 2) await Promise.all(names.slice(i, i + 2).map(async (n) => rowOf.set(n, (await stan.search(n)).find((r) => r.locatadd_nm === n && (codes.levelOf(r) === 'umd' || codes.levelOf(r) === 'ri')) || null)));
    const built = await Promise.all(top.map(async (p) => {
      const sp = splitParcel(p.parcel), row = rowOf.get(sp.name);
      if (!row) return null;
      const pnu = `${row.region_cd}${sp.san ? '2' : '1'}${sp.bun.padStart(4, '0')}${sp.ji.padStart(4, '0')}`, c = codes.classify(pnu);
      if (!c.ok || c.type !== 'pnu') return null;
      const jibun = `${sp.san ? '산' : ''}${Number(sp.bun)}${Number(sp.ji) ? `-${Number(sp.ji)}` : ''}`;
      return { code: pnu, kind: 'pnu', name: p.title, parts: { ...rowParts(row), jibun, place: p.title }, tier: tierOf('pnu', c.sgg), point: p.point.map((v) => Math.round(v * 1e6) / 1e6), place: true, category: p.category, addr: p.road || p.parcel };
    }));
    return built.filter(Boolean).slice(0, MAX_PLACES);
  }

  /* 숫자만 쓴 코드: 형식 판별 + 표준코드 표에서 이름 확인 */
  async function codeItems(digits) {
    const c = codes.classify(digits);
    if (!c.ok) return { items: [], reason: c.reason, detail: c.detail };
    if (c.type === 'sido') return { items: [], reason: 'unsupported-level', detail: '시도 단위는 지도로 열 수 없습니다. 시군구 이하를 입력하세요' };
    const rows = await stan.rows(c.sido, c.sgg);
    const want = c.type === 'sgg' ? `${c.sgg}00000` : c.bjd, row = codes.findRow(rows, want);
    if (!row) return { items: [], reason: 'unknown-code', detail: '행정표준코드 표에 없는 코드입니다' };
    if (c.type === 'pnu') { const p = codes.parsePnu(c.pnu); return { items: [rowItem(row, { pnu: c.pnu, jibun: p.jibun })].filter(Boolean) }; }
    return { items: [rowItem(row)].filter(Boolean) };
  }

  /* → { items, meta }, 한쪽만 실패하면 meta.partial. 둘 다 실패하면 던진다 */
  async function search(q, limit, near) {
    const meta = { q, sources: [], partial: [], asOf: new Date(now()).toISOString().slice(0, 10) };
    const digits = codes.clean(q);
    if (digits !== null) {
      const r = await codeItems(digits);
      meta.sources.push('행정표준코드');
      if (r.reason) { meta.reason = r.reason; meta.detail = r.detail; }
      return { items: r.items.slice(0, limit), meta };
    }
    const creds = vworldCreds(env), wantVw = !!creds.key, wantAddr = wantVw && /\d/.test(q);
    const [names, addr, places] = await Promise.allSettled([nameRows(q), wantAddr ? addressItems(q, creds) : Promise.resolve([]), wantVw ? placeItems(q, near, creds) : Promise.resolve([])]);
    const vwOk = [addr, places].filter((x) => x.status === 'fulfilled' && x.value.length).length > 0;
    const vwFail = [addr, places].find((x) => x.status === 'rejected');
    if (names.status === 'rejected' && !vwOk) throw (vwFail && vwFail.reason instanceof KeyPoolError && !(names.reason instanceof KeyPoolError) ? vwFail.reason : names.reason);   // 이름 검색이 실패했고 V-World 후보도 없으면 줄 것이 없다
    if (names.status === 'rejected') meta.partial.push('stan');
    if (vwFail) { if (vwFail.reason instanceof KeyPoolError) throw vwFail.reason; meta.partial.push(vwFail.reason && vwFail.reason.budget ? 'budget' : 'vworld'); }
    if (!wantVw) meta.partial.push('vworld-key');
    const items = [], seen = new Set();
    const add = (it) => { if (!it) return; if (it.place && items.some((x) => x.kind === 'pnu' && x.code === it.code && !x.place)) return; const k = `${it.kind}:${it.code}:${it.road ? 'road' : ''}:${it.place ? it.name : ''}`; if (!seen.has(k)) { seen.add(k); items.push(it); } };
    const placeList = places.status === 'fulfilled' ? places.value : [];
    if (addr.status === 'fulfilled') { for (const it of addr.value) add(it); if (addr.value.length || wantAddr) meta.sources.push('V-World 주소'); }
    if (names.status === 'fulfilled') { for (const r of names.value.slice(0, placeList.length ? 4 : limit)) add(rowItem(r)); meta.sources.push('행정표준코드'); }
    for (const it of placeList) add(it);
    if (places.status === 'fulfilled' && wantVw) meta.sources.push('V-World 장소');
    return { items: items.slice(0, limit), meta };
  }

  const handler = async function handler(req, res) {
    if (req.method !== 'GET' && req.method !== 'HEAD') { res.setHeader('Allow', 'GET, HEAD'); return problem(res, 405, 'method', '허용하지 않는 방식', 'GET 만 지원합니다'); }
    const params = new URL(req.url || '/', 'http://local').searchParams;
    const names = [...new Set(params.keys())];
    if (names.some((n) => !ALLOWED.has(n)) || !params.has('q') || params.getAll('q').length !== 1 || params.getAll('limit').length > 1) {
      return problem(res, 400, 'invalid-query', '쿼리가 맞지 않습니다', 'q=<글자> 하나와 선택 limit 만 받습니다', undefined, 'public, s-maxage=3600');
    }
    const q = normalize(params.get('q'));
    if (q.length < MIN_Q || q.length > MAX_Q) return problem(res, 400, 'invalid-query', '검색어 길이가 맞지 않습니다', `검색어는 ${MIN_Q}~${MAX_Q}자여야 합니다`, { reason: q.length < MIN_Q ? 'too-short' : 'too-long' }, 'public, s-maxage=3600');
    let limit = DEFAULT_LIMIT;
    if (params.has('limit')) {
      const n = Number(params.get('limit'));
      if (!Number.isInteger(n) || n < 1 || n > MAX_LIMIT) return problem(res, 400, 'invalid-query', 'limit 이 맞지 않습니다', `limit 은 1~${MAX_LIMIT} 정수입니다`, undefined, 'public, s-maxage=3600');
      limit = n;
    }
    let near = null;
    if (params.has('near')) {
      const m = /^(\d{2,3}(?:\.\d+)?),(\d{2}(?:\.\d+)?)$/.exec(params.get('near') || ''), lon = m && Number(m[1]), lat = m && Number(m[2]);
      if (!m || params.getAll('near').length > 1 || lon < 120 || lon > 135 || lat < 30 || lat > 45) return problem(res, 400, 'invalid-query', 'near 가 맞지 않습니다', 'near=<경도>,<위도>(한국 안)입니다', undefined, 'public, s-maxage=3600');
      near = [lon, lat];
    }
    if (!pool.hasKeys('RESOLVE')) return problem(res, 503, 'not-configured', '인증키가 설정되어 있지 않습니다', 'RESOLVE 용도 공공데이터포털 키가 필요합니다');
    try {
      const out = await search(q, limit, near);
      out.meta.count = out.items.length;
      if (!out.meta.partial.length) delete out.meta.partial;
      return send(res, 200, out, out.meta.partial ? 'public, s-maxage=60' : 'public, s-maxage=3600, stale-while-revalidate=3600');
    } catch (e) {
      if (e instanceof KeyPoolError) {
        if (e.code === 'EXHAUSTED') { res.setHeader('Retry-After', String(e.retryAfterSec || 3600)); return problem(res, 429, 'keys-exhausted', '오늘 인증키 한도에 닿았습니다', e.message, { retryAfterSec: e.retryAfterSec }); }
        return problem(res, 503, 'not-configured', '인증키가 설정되어 있지 않습니다', e.message);
      }
      console.error(`codes/search: ${(e && e.name) || 'Error'}: ${redactVworld((e && e.message) || e, env).slice(0, 200)}`);
      return problem(res, 502, 'upstream', '주소 검색 서비스를 부르지 못했습니다', '잠시 뒤 다시 시도하세요');   // 원인 문구는 밖으로 내보내지 않는다(키가 섞일 수 있음)
    }
  };
  return { handler, search, cache, pool };
}
const createHandler = (overrides) => createService(overrides).handler;

module.exports = createHandler();
module.exports.createHandler = createHandler;
module.exports.createService = createService;
module.exports.rowParts = rowParts;
