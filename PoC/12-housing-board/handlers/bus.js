/* 버스 위치 중계(Vercel 함수 · 로컬 scripts/dev.js). 브라우저가 data.go.kr 을 직접 부르지 않게 해 인증키를 숨기고, 호출 횟수를 서버에서 묶는다.
   화면은 사용자가 '버스 위치 조회'를 누를 때만 부른다(자동 갱신·실시간 검색 없음).

   GET /api/bus?region=<slug>
   → 200 { at: 'ISO 시각', ttl: 초, buses: [{ r: 노선id, v: 차량번호, lon, lat, ord: 정류소순서, stop: 정류소 이름 }], failed?: [노선id] }
   → 400 query · 404 no-live-routes · 405 method · 429 keys-exhausted(Retry-After) · 502 upstream · 503 not-configured

   어느 노선을 부르는지는 요청이 정하지 못한다. 배포된 regions/<slug>/infra.json 의 busRoutes 중 live 노선만 부른다(키를 쓰는 열린 중계가 되지 않게).
   호출 수: 응답을 로컬 캐시(lib/cache.js)와 CDN 이 ttl 초 동안 나눠 쓰므로 하루 호출은 (live 노선 수) × 86400 / ttl 회로 묶인다.
   ttl = max(60, ceil(노선 수 × 86400 / (DAILY_BUDGET × BUS 키 수))) — 개발계정 한도(하루 10,000건/키)에서 DAILY_BUDGET 만 쓰고, 키가 늘면 그만큼 ttl 이 줄어든다.
   쿼리에 region 말고 다른 값이 있으면 거절한다(값을 바꿔 가며 캐시를 비켜 가는 호출을 막는다).
   인증키: lib/keys.js 의 BUS 용도 풀(DATA_GO_KR_KEY_BUS_<N>, 없으면 DATA_GO_KR_KEY). 호출마다 가장 적게 쓴 키를 고르고, 한도(resultCode 22·HTTP 429)에 닿은 키는
   그날 건너뛴다. 키 값은 응답·로그·캐시에 남기지 않는다. 시험: tests/js/busapi.test.cjs */
'use strict';
const fs = require('fs');
const path = require('path');
const { createKeyPool, fileStore, memoryStore, isQuotaError, KeyPoolError } = require('../lib/keys.js');
const { createCache, defaultDir } = require('../lib/cache.js');

const ENDPOINT = 'https://apis.data.go.kr/1613000/BusLcInfoInqireService/getRouteAcctoBusLcList';
const DAILY_BUDGET = 8000;
const MIN_TTL_S = 60;
const FETCH_TIMEOUT_MS = 8000;
const REGION = /^[a-z0-9-]{1,40}$/;

const ttlFor = (routeCount, keyCount = 1) => Math.max(MIN_TTL_S, Math.ceil(routeCount * 86400 / (DAILY_BUDGET * Math.max(1, keyCount))));

/* 지역 번들에서 실시간으로 부를 노선 {city, routes:[id]} — 없으면 null */
function readLiveRoutes(slug) {
  try {
    const infra = JSON.parse(fs.readFileSync(/*turbopackIgnore: true*/ path.join(require('../lib/root.js').ROOT, 'regions', slug, 'infra.json'), 'utf8'));
    const routes = (infra.busRoutes || []).filter((r) => r && r.live && typeof r.id === 'string').map((r) => r.id);
    return infra.busCityCode && routes.length ? { city: Number(infra.busCityCode), routes } : null;
  } catch (e) {
    return null;
  }
}

const num = (v) => { const n = typeof v === 'string' && v.trim() === '' ? NaN : Number(v); return Number.isFinite(n) ? n : null; };
function itemsOf(json) {
  const items = json && json.response && json.response.body && json.response.body.items;
  const it = items && items.item !== undefined ? items.item : items;
  return Array.isArray(it) ? it : it && typeof it === 'object' ? [it] : [];
}
/* TAGO 한 노선 응답 → 버스 목록. 좌표가 없거나 이상한 차량은 뺀다(좌표는 문자열로 오는 행도 있다) */
function normalize(routeId, json) {
  const out = [];
  for (const b of itemsOf(json)) {
    const lon = num(b.gpslong), lat = num(b.gpslati);
    if (lon === null || lat === null || lon < 120 || lon > 135 || lat < 30 || lat > 45 || !b.vehicleno) continue;
    out.push({ r: routeId, v: String(b.vehicleno), lon: Math.round(lon * 1e6) / 1e6, lat: Math.round(lat * 1e6) / 1e6, ord: num(b.nodeord), stop: b.nodenm ? String(b.nodenm) : '' });
  }
  return out;
}

/* 한 노선 조회 한 번(키 하나). 한도 오류는 e.quota=true 로 던져 키 풀이 다음 키로 넘어가게 한다 */
async function fetchRoute(deps, key, city, routeId) {
  const q = new URLSearchParams({ serviceKey: key, cityCode: String(city), routeId, numOfRows: '200', pageNo: '1', _type: 'json' });
  for (let attempt = 0; attempt < 2; attempt++) {
    const res = await deps.fetch(`${ENDPOINT}?${q}`, { signal: AbortSignal.timeout(FETCH_TIMEOUT_MS), headers: { Accept: 'application/json' } });
    if (res.status === 429) { const e = new Error('HTTP 429'); e.quota = true; throw e; }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const text = await res.text();
    if (isQuotaError(text)) { const e = new Error('quota'); e.quota = true; throw e; }   // 한도를 넘으면 200 에 XML 오류 본문이 온다
    const json = JSON.parse(text);
    const code = String(json && json.response && json.response.header && json.response.header.resultCode);
    if (code === '00') return normalize(routeId, json);
    if (code === '22') { const e = new Error('quota'); e.quota = true; throw e; }
    if (code === '99' && attempt === 0) { await deps.sleep(400); continue; }   // TAGO 동시 접속이 가득 찬 일시 오류
    throw new Error(`result ${code}`);
  }
  throw new Error('retry exhausted');
}

function createHandler(overrides) {
  const deps = Object.assign({
    fetch: (...a) => fetch(...a), env: process.env, now: () => Date.now(), readLiveRoutes, sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
  }, overrides);
  const dir = defaultDir(deps.env);
  const cache = deps.cache || createCache({ dir, now: deps.now });
  const pool = deps.pool || createKeyPool({ env: deps.env, now: deps.now, store: deps.env.VERCEL ? memoryStore() : fileStore(path.join(dir, 'key-usage.json')) });

  const send = (res, status, body, cacheControl) => {
    res.statusCode = status;
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', cacheControl);
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.end(JSON.stringify(body));
  };
  const cc = (ttl, ageS) => `public, s-maxage=${Math.max(1, ttl - ageS)}, stale-while-revalidate=${ttl}`;

  return async function handler(req, res) {
    if (req.method !== 'GET' && req.method !== 'HEAD') { res.setHeader('Allow', 'GET, HEAD'); return send(res, 405, { error: 'method' }, 'no-store'); }
    const params = new URL(req.url || '/', 'http://local').searchParams;
    const keys = [...new Set(params.keys())];
    const slug = params.get('region') || '';
    if (keys.length !== 1 || keys[0] !== 'region' || params.getAll('region').length !== 1 || !REGION.test(slug)) return send(res, 400, { error: 'query' }, 'public, s-maxage=3600');
    const live = deps.readLiveRoutes(slug);
    if (!live) return send(res, 404, { error: 'no-live-routes' }, 'public, s-maxage=3600');
    if (!pool.hasKeys('BUS')) return send(res, 503, { error: 'not-configured' }, 'no-store');
    const ttl = ttlFor(live.routes.length, pool.count('BUS'));

    const hit = cache.get(`bus:${slug}`);
    if (hit) return send(res, 200, hit.body, cc(ttl, Math.floor((deps.now() - hit.at) / 1000)));

    if (cache.get(`bus-fail:${slug}`)) return send(res, 502, { error: 'upstream' }, 'public, s-maxage=15');   // 방금 실패했으면 15초는 원천을 다시 부르지 않는다

    const results = await Promise.allSettled(live.routes.map((id) => pool.run('BUS', 'tago', (key) => fetchRoute(deps, key, live.city, id))));
    const buses = [], failed = [];
    results.forEach((r, i) => { if (r.status === 'fulfilled') buses.push(...r.value); else failed.push(live.routes[i]); });
    if (failed.length === live.routes.length) {
      const poolErr = results.map((r) => r.reason).find((e) => e instanceof KeyPoolError);
      if (poolErr && poolErr.code === 'EXHAUSTED') { res.setHeader('Retry-After', String(poolErr.retryAfterSec || 3600)); return send(res, 429, { error: 'keys-exhausted', retryAfterSec: poolErr.retryAfterSec }, 'no-store'); }
      if (poolErr) return send(res, 503, { error: 'not-configured' }, 'no-store');
      cache.set(`bus-fail:${slug}`, true, 15000);
      return send(res, 502, { error: 'upstream' }, 'public, s-maxage=15');   // 원인 문구는 밖으로 내보내지 않는다(키가 섞일 수 있음)
    }
    const at = deps.now();
    const body = Object.assign({ at: new Date(at).toISOString(), ttl, buses }, failed.length ? { failed } : {});
    cache.set(`bus:${slug}`, { at, body }, ttl * 1000);
    return send(res, 200, body, cc(ttl, 0));
  };
}

module.exports = createHandler();
module.exports.createHandler = createHandler;
module.exports.ttlFor = ttlFor;
module.exports.normalize = normalize;
module.exports.DAILY_BUDGET = DAILY_BUDGET;
