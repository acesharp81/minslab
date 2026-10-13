/* 입주 전 기반시설 요청 시 조회 API: 번들이 없는 법정동에서도 인허가 단지 위에 "입주 전 점검"(교육·교통)이 나오도록,
   그 법정동 인허가 단지 가까이의 신설예정 학교와 버스 정류장을 번들 infra.json 의 schools·stops 와 같은 모양으로 돌려준다.

   GET /api/v1/infra?bjd=<법정동 10자리>        (8자리는 00 을 붙여 받는다)
   → 200 { type:'Infra', bjd, asOf, sources:[…], schools:[…], stops:[…], meta:{ centers, schoolsNational, schools, stopCalls, stops, stopsSource?, schoolsError?, stopsError?, seoulError?, noBus? } }
   → problem+json: invalid-query 400 · invalid-code 400 · method 405 · keys-exhausted 429 · budget-exhausted 429 · not-configured 503 · upstream 502 (인허가를 못 받았을 때)

   - 서버는 임의 좌표를 받지 않는다. 그 법정동의 인허가 결과(/api/v1/permits 와 같은 캐시·키 풀)에서 필지 중심을 꺼내 쓴다 → 열린 중계가 되지 않는다. 사업이 없으면 학교·정류장도 없다.
   - 신설예정 학교: 교육재정알리미 전국 목록(키 없음, 24시간 캐시)에서 단지 중심 2 km 안만. 정류장: TAGO 근접정류소(키 풀 BUS·서비스 tago)를 단지 중심마다 한 번(150 m 안은 건너뜀, 동시 10개), 400 m 안만. 서울(시도 11)은 TAGO 도시 목록에 없어 부르지 않고, 서울시 정류소정보조회(lib/seoul.js, 키 풀 BUS·서비스 seoul)를 단지 중심 주변으로 부르며(300 m 간격, 최대 12곳) 실패하면 OpenStreetMap 으로 물러난다(둘 다 안 되면 meta.noBus).
   - 학교·정류장 한쪽이 실패해도 나머지는 준다(meta.schoolsError·stopsError). 응답은 로컬 캐시 24시간 + CDN 24시간, 한쪽이라도 실패했으면 캐시하지 않는다.
   - 인스턴스별 시간당 TAGO 호출 상한(INFRA_UPSTREAM_PER_HOUR, 기본 600)을 넘으면 정류장만 비운다(meta.stopsError). 키·원천 URL·원인 문구는 응답에 싣지 않는다.
   시험: tests/js/infra.api.test.cjs */
'use strict';
const permits = require('./permits.js');
const { KeyPoolError } = require('../../lib/keys.js');
const { fetchPage } = require('../../lib/datagokr.js');
const codes = require('../../lib/codes.js');
const I = require('../../lib/infra.js');
const Seoul = require('../../lib/seoul.js');
const { vworldCreds } = require('../../lib/vworld.js');

const TAGO_NEAR_URL = 'https://apis.data.go.kr/1613000/BusSttnInfoInqireService/getCrdntPrxmtSttnList';
const EDU_URL = 'https://eduinfo.go.kr/portal/theme/newSchInfoDetail.do';
const EDU_REFERER = 'https://eduinfo.go.kr/portal/theme/newSchMapPage.do';
const TTL_MS = 24 * 3600 * 1000;
const DEFAULT_BUDGET_PER_HOUR = 600;
const DEFAULT_SEOUL_BUDGET_PER_HOUR = 120;   // 서울 개발계정은 하루 1,000건이라 인스턴스당 시간당 120건(8시간이면 960건)
const SEOUL_CONCURRENCY = 4;
const STOP_CONCURRENCY = 10;
const MAX_STOP_PAGES = 3;
const ALLOWED = new Set(['bjd']);
const CDN_TIMEOUT_MS = 20000;
const OVERPASS_URLS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter'];   // 공개 서버는 자주 느리거나 504 라 둘을 동시에 부르고 먼저 온 것을 쓴다
const OVERPASS_TIMEOUT_MS = 12000;
const OSM_TTL_MS = 24 * 3600 * 1000;                                                                               // 로컬 캐시 보관 상한(lib/cache.js)과 같다
const OSM_FAIL_TTL_MS = 2 * 60 * 1000;                                                                              // 둘 다 실패하면 2분은 다시 묻지 않는다(공개 서버를 두드리지 않고, 보는 사람마다 12초씩 기다리지 않게)
const OSM_MAX_BOX_DEG = 0.12;                                                                                      // 상자가 이보다 크면 부르지 않는다(공개 서버 부담·응답 크기)
const NO_TAGO_SIDO = new Set(['11']);   // 서울은 국토교통부 TAGO 도시 목록에 없다(실측: 근접정류소 0곳, cityCode=11 노선 0건). 호출 낭비를 줄이려고 건너뛴다

function createHandler(overrides = {}) {
  const svc = permits.createService(overrides);
  const { cache, pool, now, sleep, doFetch } = svc;
  const env = overrides.env || process.env;
  const budgetMax = Number(env.INFRA_UPSTREAM_PER_HOUR) > 0 ? Math.floor(Number(env.INFRA_UPSTREAM_PER_HOUR)) : DEFAULT_BUDGET_PER_HOUR;
  const budget = { hour: -1, used: 0 }, sbudget = { hour: -1, used: 0 };
  const seoulMax = Number(env.SEOUL_UPSTREAM_PER_HOUR) > 0 ? Math.floor(Number(env.SEOUL_UPSTREAM_PER_HOUR)) : DEFAULT_SEOUL_BUDGET_PER_HOUR;
  const spendOf = (b, max) => (n) => {
    const hour = Math.floor(now() / 3600000);
    if (b.hour !== hour) { b.hour = hour; b.used = 0; }
    if (b.used + n > max) return false;
    b.used += n;
    return true;
  };
  const spend = spendOf(budget, budgetMax), spendSeoul = spendOf(sbudget, seoulMax);
  const send = (res, status, body, cacheControl, type = 'application/json; charset=utf-8') => {
    res.statusCode = status;
    res.setHeader('Content-Type', type);
    res.setHeader('Cache-Control', cacheControl);
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.end(JSON.stringify(body));
  };
  const problem = (res, status, code, title, detail, extra, cc) => send(res, status, Object.assign({ type: `/problems/${code}`, title, status, code, detail }, extra),
    cc || (status >= 500 || status === 429 ? 'no-store' : 'public, s-maxage=60'), 'application/problem+json; charset=utf-8');

  /* 교육재정알리미 전국 신설예정학교(24시간 캐시). 일시 오류는 3번까지 다시 */
  function nationalSchools() {
    return cache.wrap('eduinfo:newschools', TTL_MS, async () => {
      const form = new URLSearchParams({ schlSeq: '', yymmdd: '', searchRg: '', searchOffc: '', searchWd: '' });
      let last = '응답 없음';
      for (let attempt = 0; attempt < 3; attempt++) {
        if (attempt) await sleep(400 * attempt);
        let r;
        try { r = await doFetch(EDU_URL, { method: 'POST', body: form.toString(), signal: AbortSignal.timeout(10000), headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-Requested-With': 'XMLHttpRequest', Referer: EDU_REFERER } }); } catch (e) { last = 'network'; continue; }
        if (!r.ok) { last = `HTTP ${r.status}`; continue; }
        let json; try { json = await r.json(); } catch (e) { last = 'JSON 아님'; continue; }
        if (json && Array.isArray(json.result)) return json.result;
        last = 'result 목록이 없음';
      }
      throw new Error(last);
    });
  }
  /* TAGO 근접정류소 한 중심(반경 약 500 m). 서울처럼 도시 목록에 없으면 빈 목록 */
  async function stopsNear(center) {
    const all = [];
    for (let page = 1; page <= MAX_STOP_PAGES; page++) {
      if (!spend(1)) { const e = new Error('budget'); e.budget = true; throw e; }
      const got = await pool.run('BUS', 'tago', (key) => fetchPage({ doFetch, sleep, url: TAGO_NEAR_URL,
        params: { serviceKey: key, gpsLati: center[1].toFixed(6), gpsLong: center[0].toFixed(6), numOfRows: '100', pageNo: String(page), _type: 'json' } }));
      all.push(...got.items);
      if (!got.items.length || page * 100 >= got.total) break;
    }
    return all;
  }
  /* 서울시 정류소정보조회: 단지 중심 주변(반경 700 m, 중심은 300 m 간격으로 최대 12곳)의 정류소. 24시간 캐시(일부만 받았으면 캐시하지 않음).
     모두 실패하면 첫 오류를 던진다(키 풀 오류 포함 — 부르는 쪽이 OSM 으로 물러난다). 일부만 실패하면 받은 것만 주고 partial 로 알린다 */
  async function seoulStops(bjd, centers) {
    const hit = cache.get(`seoul:stops:${bjd}`);
    if (hit) return { stops: hit, partial: false };
    const picked = I.queryCenters(centers, Seoul.SKIP_M, Seoul.MAX_CENTERS);
    if (!spendSeoul(picked.length)) { const e = new Error('budget'); e.budget = true; throw e; }
    const got = await mapLimit(picked, SEOUL_CONCURRENCY, (c) => pool.run('BUS', 'seoul', (key) => Seoul.fetchStations({ doFetch, sleep, key, center: c })));
    const okRuns = got.filter((g) => g.ok), failedRuns = got.filter((g) => g.err);
    if (picked.length && !okRuns.length) throw failedRuns[0].err;
    const byId = new Map();
    for (const g of okRuns) for (const it of g.ok) { const s = Seoul.seoulStop(it); if (s && !byId.has(s.id)) byId.set(s.id, s); }
    const stops = [...byId.values()], partial = failedRuns.length > 0;
    if (!partial) cache.set(`seoul:stops:${bjd}`, stops, TTL_MS);
    return { stops, partial };
  }
  /* TAGO 에 자료가 없는 지역(서울·강릉 등)의 보조: OpenStreetMap 정류장을 Overpass 로 한 번에 받는다. 이름 있는 정류장만, 24시간 캐시.
     실패는 던진다(캐시 안 함). 공개 서버라 느리거나 꺼질 수 있어 둘을 동시에 불러 먼저 온 것을 쓰고, 이 보조가 실패해도 지도는 정류장 없이 열린다 */
  async function osmStops(bjd, centers) {
    const box = I.bboxAround(centers);
    if (box[2] - box[0] > OSM_MAX_BOX_DEG || box[3] - box[1] > OSM_MAX_BOX_DEG) throw new Error('범위가 넓어 정류장을 받지 않음');
    if (cache.get(`osm:fail:${bjd}`)) throw new Error('최근에 실패해 잠시 건너뜀');
    return cache.wrap(`osm:stops:${bjd}`, OSM_TTL_MS, async () => {
      const [w, s, e, n] = box, ql = `[out:json][timeout:15];(node["highway"="bus_stop"](${s},${w},${n},${e});node["public_transport"="platform"]["bus"="yes"](${s},${w},${n},${e}););out body;`;
      const ask = (url) => doFetch(url, { method: 'POST', body: new URLSearchParams({ data: ql }).toString(), signal: AbortSignal.timeout(OVERPASS_TIMEOUT_MS), headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json', 'User-Agent': 'housing-board/1.0 (+https://housing-board.vercel.app)' } })
        .then(async (r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); const j = await r.json(); if (!j || !Array.isArray(j.elements)) throw new Error('elements 가 없음'); return j.elements; });
      const elements = await Promise.any(OVERPASS_URLS.map(ask));
      const byId = new Map();
      for (const el of elements) { const st = I.osmStop(el); if (st && !byId.has(st.id)) byId.set(st.id, st); }
      return [...byId.values()];
    }).catch((e) => { cache.set(`osm:fail:${bjd}`, 1, OSM_FAIL_TTL_MS); throw e; });
  }
  async function mapLimit(items, limit, fn) {
    const out = new Array(items.length); let next = 0;
    await Promise.all(Array.from({ length: Math.min(limit, items.length) }, async () => {
      while (next < items.length) { const i = next++; try { out[i] = { ok: await fn(items[i]) }; } catch (e) { out[i] = { err: e }; } }
    }));
    return out;
  }

  /* 인허가 결과: ① 이 인스턴스 캐시 ② 이 서버의 permits API 를 공개 주소로 불러 CDN 캐시에서 ③ 직접 만들기.
     Vercel 은 api 함수마다 따로 돌아 permits 함수와 infra 함수의 메모리 캐시가 다르다. 화면이 방금 permits 를 불렀어도 infra 가 인허가를 다시 만들어 한 법정동에 12~24초가 걸렸다(실측: 부산 우동 18초·대구 범어동 24초·대전 봉명동 17초).
     주소는 환경변수의 이 프로젝트 호스트만 쓰고 요청의 Host 헤더는 쓰지 않는다(다른 서버로 보내는 중계가 되지 않게). 못 받으면(보호된 미리보기 배포 등) 직접 만든다. */
  const selfHost = () => (env.VERCEL ? (env.VERCEL_ENV === 'production' ? env.VERCEL_PROJECT_PRODUCTION_URL : env.VERCEL_URL) : '') || '';
  async function permitsOf(bjd) {
    const local = cache.get(`permits:${bjd}`);
    if (local) return local;
    const host = selfHost();
    if (/^[a-z0-9.-]+$/i.test(host)) {
      try {
        const r = await doFetch(`https://${host}/api/v1/permits?bjd=${bjd}`, { signal: AbortSignal.timeout(CDN_TIMEOUT_MS), headers: { Accept: 'application/json' } });
        if (r.ok) { const b = await r.json(); if (b && b.type === 'FeatureCollection' && Array.isArray(b.features) && b.bjd === bjd) return b; }
      } catch (e) { /* 직접 만든다 */ }
    }
    return (await svc.getPermits(bjd)).body;
  }

  async function build(bjd, perm) {
    const centers = perm.features.map((f) => I.centerOf(f.geometry)).filter(Boolean);
    const meta = { centers: centers.length, schoolsNational: 0, schools: 0, stopCalls: 0, stops: 0 };
    let schools = [], stops = [], failed = false;
    if (centers.length) {
      try {
        const rows = await nationalSchools();
        meta.schoolsNational = rows.length;
        schools = I.scheduledSchools(rows, centers).schools;
      } catch (e) { failed = true; meta.schoolsError = '신설예정 학교를 불러오지 못함'; console.error(`infra ${bjd} schools: ${(e && e.message) || e}`); }
      const noTago = NO_TAGO_SIDO.has(bjd.slice(0, 2));
      const picked = noTago ? [] : I.queryCenters(centers);
      meta.stopCalls = picked.length;
      if (noTago) meta.noBus = true;
      const got = await mapLimit(picked, STOP_CONCURRENCY, stopsNear);
      const byId = new Map(); let ok = 0, budgetHit = false, errs = 0;
      for (const g of got) {
        if (g.err) { if (g.err.budget) budgetHit = true; else if (g.err instanceof KeyPoolError) throw g.err; else errs++; continue; }
        ok++;
        for (const it of g.ok) { const s = I.tagoStop(it); if (s && !byId.has(s.id) && I.nearAny([s.lon, s.lat], centers, I.STOP_SHOW_M)) byId.set(s.id, s); }
      }
      stops = [...byId.values()].sort((a, b) => a.name.localeCompare(b.name, 'ko'));
      if (budgetHit) { failed = true; meta.stopsError = '이 서버의 시간당 정류소 조회 한도에 닿아 일부만 불러옴'; }
      else if (picked.length && !ok) { failed = true; meta.stopsError = '버스 정류소를 불러오지 못함'; }
      else if (errs) { failed = true; meta.stopsError = `정류소 조회 ${errs}곳을 불러오지 못해 일부만 보임`; }   // 일부만 실패해도 조용히 넘기지 않고 캐시하지 않는다
      else if (picked.length && !stops.length) meta.noBus = true;   // 호출은 됐는데 반경 안에 정류소가 0곳: 서울처럼 TAGO 도시 목록에 없는 지역
      if (stops.length) meta.stopsSource = 'tago';
      else if (!meta.stopsError) {
        if (noTago) {                                                // 서울: 서울시 정류소정보조회를 먼저(실패해도 지도는 열리고 OSM 으로 물러난다)
          try {
            const sv = await seoulStops(bjd, centers);
            stops = sv.stops.filter((x) => I.nearAny([x.lon, x.lat], centers, I.STOP_SHOW_M)).sort((a, b) => a.name.localeCompare(b.name, 'ko'));
            meta.stopCalls = I.queryCenters(centers, Seoul.SKIP_M, Seoul.MAX_CENTERS).length;
            if (sv.partial) { failed = true; meta.seoulError = '서울시 정류소 조회 일부를 불러오지 못해 일부만 보임'; }
            if (stops.length) { meta.stopsSource = 'seoul'; delete meta.noBus; }
          } catch (e) {
            failed = true;
            meta.seoulError = e && e.budget ? '이 서버의 시간당 서울시 정류소 조회 한도에 닿음' : e instanceof KeyPoolError ? '서울시 정류소 조회 인증키 한도·설정 문제' : '서울시 정류소를 불러오지 못함';
            console.error(`infra ${bjd} seoul: ${(e && e.name) || 'Error'}: ${String((e && e.message) || e).slice(0, 120)}`);
          }
        }
        if (!stops.length) {                                         // TAGO·서울시에 자료가 없으면(또는 반경 안 0곳) OpenStreetMap 으로 보조
          try {
            const osm = await osmStops(bjd, centers);
            stops = osm.filter((x) => I.nearAny([x.lon, x.lat], centers, I.STOP_SHOW_M)).sort((a, b) => a.name.localeCompare(b.name, 'ko'));
            if (stops.length) { meta.stopsSource = 'osm'; delete meta.noBus; }
          } catch (e) { failed = true; meta.stopsError = '버스 정류장(OpenStreetMap)을 불러오지 못함'; console.error(`infra ${bjd} osm: ${(e && e.name) || 'Error'}: ${String((e && e.message) || e).slice(0, 120)}`); }
        }
      }
    }
    meta.schools = schools.length; meta.stops = stops.length;
    const used = new Set();
    if (schools.length) used.add('edu-newschool');
    if (stops.length) used.add(meta.stopsSource === 'osm' ? 'osm-bus' : meta.stopsSource === 'seoul' ? 'seoul-bus' : 'tago-bus');
    const asOf = new Date(now()).toISOString().slice(0, 10);
    return {
      body: { type: 'Infra', bjd, asOf, sources: [...used].map((id) => ({ ...I.SOURCE_DEFS[id], asOf })), schools, stops, meta },
      cacheable: !failed,
    };
  }

  return async function handler(req, res) {
    if (req.method !== 'GET' && req.method !== 'HEAD') { res.setHeader('Allow', 'GET, HEAD'); return problem(res, 405, 'method', '허용하지 않는 방식', 'GET 만 지원합니다'); }
    const params = new URL(req.url || '/', 'http://local').searchParams;
    const names = [...new Set(params.keys())];
    if (names.some((n) => !ALLOWED.has(n)) || !params.has('bjd') || params.getAll('bjd').length !== 1) return problem(res, 400, 'invalid-query', '쿼리가 맞지 않습니다', 'bjd=<법정동 10자리> 하나만 받습니다', undefined, 'public, s-maxage=3600');
    const c = codes.classify(params.get('bjd'));
    if (!c.ok || c.type !== 'bjd') return problem(res, 400, 'invalid-code', '법정동 코드가 맞지 않습니다', c.ok ? `${c.type} 코드가 왔습니다. 법정동(8 또는 10자리)만 받습니다` : c.detail, c.ok ? { reason: 'type-mismatch' } : { reason: c.reason }, 'public, s-maxage=3600');
    const bjd = c.bjd;
    if (!vworldCreds(env).key || !pool.hasKeys('RESOLVE')) return problem(res, 503, 'not-configured', '인증키가 설정되어 있지 않습니다', 'RESOLVE 용도 공공데이터포털 키와 V-World 키가 필요합니다');
    try {
      const hit = cache.get(`infra:${bjd}`);
      if (hit) return send(res, 200, hit, 'public, s-maxage=86400, stale-while-revalidate=86400');
      const perm = await permitsOf(bjd);
      const out = await build(bjd, perm);
      if (out.cacheable) cache.set(`infra:${bjd}`, out.body, TTL_MS);
      return send(res, 200, out.body, out.cacheable ? 'public, s-maxage=86400, stale-while-revalidate=86400' : 'public, s-maxage=60');
    } catch (e) {
      if (e instanceof KeyPoolError) {
        if (e.code === 'EXHAUSTED') { res.setHeader('Retry-After', String(e.retryAfterSec || 3600)); return problem(res, 429, 'keys-exhausted', '오늘 인증키 한도에 닿았습니다', e.message, { retryAfterSec: e.retryAfterSec }); }
        return problem(res, 503, 'not-configured', '인증키가 설정되어 있지 않습니다', e.message);
      }
      if (e && e.budget) {
        const wait = 3600 - (Math.floor(now() / 1000) % 3600);
        res.setHeader('Retry-After', String(wait));
        return problem(res, 429, 'budget-exhausted', '이 서버의 시간당 조회 한도에 닿았습니다', '잠시 뒤 다시 시도하세요', { retryAfterSec: wait });
      }
      console.error(`infra ${bjd}: ${(e && e.name) || 'Error'}: ${String((e && e.message) || e).slice(0, 200)}`);
      return problem(res, 502, 'upstream', '기반시설 서비스를 부르지 못했습니다', '잠시 뒤 다시 시도하세요');
    }
  };
}

module.exports = createHandler();
module.exports.createHandler = createHandler;
