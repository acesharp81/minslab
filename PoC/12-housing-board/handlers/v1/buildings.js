/* 건물 요청 시 조회 API: 번들이 없는 곳(등급 B·C)에서도 기존 건물 3D 를 그리기 위해, 0.01° 칸(약 0.9×1.1 km) 하나의 건물을 V-World 에서 받아
   번들 buildings.json 과 같은 속성으로 돌려준다. 화면(app.js)이 지도에 보이는 칸만 이 API 로 불러 건물 목록에 붙인다.

   GET /api/v1/buildings?cell=<ix>,<iy>        ix=floor(경도×100), iy=floor(위도×100). 예: 128.00,37.55 근처 → cell=12800,3755
   → 200 { type:'FeatureCollection', cell, bbox, features:[{properties:{eh,src,h?,f?,b?,u?,n?,a?,x?}, geometry}], meta:{ source, fetchedAt, count, rawCount, tinyDropped, pages, truncated, heights } }
   → problem+json: invalid-query 400 · invalid-cell 400 · method 405 · budget-exhausted 429 · not-configured 503 · upstream 502

   - 건물은 중심점이 있는 칸에만 속한다(이웃 칸과 겹치지 않음). 변환 규칙은 lib/buildings.js(번들 빌드와 같음)이고 층수환산 높이는 계양 측정값 기반 근사다.
   - 칸당 V-World 를 최대 5쪽(1,000동씩) 부르고 넘으면 truncated:true. 응답은 로컬 캐시 24시간 + CDN 24시간(s-maxage).
   - 키를 쓰는 열린 중계가 되지 않게: 칸 번호는 한국 범위의 정수만 받고, 인스턴스별 시간당 원천 호출 상한(BUILDINGS_UPSTREAM_PER_HOUR, 기본 1200쪽)을 넘으면 429.
   - 키: VWORLD_KEY(운영)·VWORLD_DEV_KEY(로컬)·VWORLD_DOMAIN → lib/vworld.js. 키·원천 URL·원천 오류 문구는 응답에 싣지 않는다(서버 로그에는 가려서 남김).
   시험: tests/js/buildingsapi.test.cjs */
'use strict';
const { createCache, defaultDir } = require('../../lib/cache.js');
const { VWORLD_URL, vworldCreds, redactVworld } = require('../../lib/vworld.js');
const Bld = require('../../lib/buildings.js');

const LAYER = 'LT_C_BLDGINFO';
const PAGE_SIZE = 1000;
const MAX_PAGES = 5;
const TTL_MS = 24 * 3600 * 1000;
const FETCH_TIMEOUT_MS = 10000;
const DEFAULT_BUDGET_PER_HOUR = 1200;
const ALLOWED = new Set(['cell']);

function createHandler(overrides = {}) {
  const env = overrides.env || process.env;
  const now = overrides.now || (() => Date.now());
  const doFetch = overrides.fetch || ((...a) => fetch(...a));
  const cache = overrides.cache || createCache({ dir: overrides.cacheDir || defaultDir(env), now });
  const budgetMax = Number(env.BUILDINGS_UPSTREAM_PER_HOUR) > 0 ? Math.floor(Number(env.BUILDINGS_UPSTREAM_PER_HOUR)) : DEFAULT_BUDGET_PER_HOUR;
  const budget = { hour: -1, used: 0 };                       // 인스턴스 메모리의 시간당 원천 호출 수

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

  async function getPage(ix, iy, page, creds) {
    const [x0, y0, x1, y1] = Bld.cellBbox(ix, iy);
    const params = { service: 'data', request: 'GetFeature', data: LAYER, key: creds.key, domain: creds.domain, format: 'json', size: String(PAGE_SIZE), page: String(page), crs: 'EPSG:4326', geomFilter: `BOX(${x0},${y0},${x1},${y1})` };
    // HOME에서 사용 중인 같은 도메인 VWorld 키는 Referer로 인증한다. 키는 브라우저에 보내지 않는다.
    if (env.VWORLD_REFERER_AUTH === '1') { delete params.domain; params.version = '2.0'; }
    const q = new URLSearchParams(params);
    const headers = { Accept: 'application/json' };
    if (env.VWORLD_REFERER_AUTH === '1') headers.Referer = 'https://www.minslab.kr/poc/home/';
    const r = await doFetch(`${VWORLD_URL}?${q}`, { signal: AbortSignal.timeout(FETCH_TIMEOUT_MS), headers });
    if (!r.ok) { const e = new Error(`HTTP ${r.status}`); e.status = r.status; throw e; }
    const json = await r.json();
    const res = json && json.response, st = res && res.status;
    if (st === 'NOT_FOUND') return { features: [], total: 1 };
    if (st !== 'OK') throw new Error(`V-World ${(res && res.error && res.error.code) || st || '응답 형식'}`);
    const fc = ((res.result || {}).featureCollection || {}).features || [];
    return { features: fc, total: Number((res.page || {}).total) || 1 };
  }

  /* 칸 하나: V-World 쪽을 받아 변환·칸 소속 거르기. 원천 호출 수만큼 예산을 쓴다 */
  async function loadCell(ix, iy, creds) {
    const out = [], stat = { rawCount: 0, tinyDropped: 0, outsideCell: 0, pages: 0, truncated: false };
    for (let page = 1; page <= MAX_PAGES; page++) {
      if (!spend(1)) { const e = new Error('budget'); e.budget = true; throw e; }
      const got = await getPage(ix, iy, page, creds);
      stat.pages++; stat.rawCount += got.features.length;
      for (const f of got.features) {
        const feat = Bld.convertFeature(f);
        if (!feat) { stat.tinyDropped++; continue; }
        if (!Bld.inCell(Bld.centroidOf(feat.geometry), ix, iy)) { stat.outsideCell++; continue; }
        out.push(feat);
      }
      if (page >= got.total || !got.features.length) return { features: out, stat };
    }
    stat.truncated = true;
    return { features: out, stat };
  }

  return async function handler(req, res) {
    if (req.method !== 'GET' && req.method !== 'HEAD') { res.setHeader('Allow', 'GET, HEAD'); return problem(res, 405, 'method', '허용하지 않는 방식', 'GET 만 지원합니다'); }
    const params = new URL(req.url || '/', 'http://local').searchParams;
    const names = [...new Set(params.keys())];
    if (names.some((n) => !ALLOWED.has(n)) || !params.has('cell') || params.getAll('cell').length !== 1) return problem(res, 400, 'invalid-query', '쿼리가 맞지 않습니다', 'cell=<ix>,<iy> 하나만 받습니다', undefined, 'public, s-maxage=3600');
    const cell = Bld.parseCell(params.get('cell'));
    if (!cell) return problem(res, 400, 'invalid-cell', '칸 번호가 맞지 않습니다', '한국 범위(경도 124~132, 위도 33~39)의 정수 칸 번호만 받습니다', undefined, 'public, s-maxage=3600');
    const [ix, iy] = cell;
    const creds = vworldCreds(env);
    if (!creds.key) return problem(res, 503, 'not-configured', 'V-World 키가 설정되어 있지 않습니다', 'VWORLD_KEY 가 없습니다');
    try {
      let hit = true;
      const data = await cache.wrap(`bld:${ix},${iy}`, TTL_MS, async () => { hit = false; return loadCell(ix, iy, creds); });
      const body = {
        type: 'FeatureCollection', cell: [ix, iy], bbox: Bld.cellBbox(ix, iy), features: data.features,
        meta: Object.assign({ source: 'V-World GIS건물통합정보(LT_C_BLDGINFO)', fetchedAt: new Date(now()).toISOString().slice(0, 10), count: data.features.length, heights: '층수환산 높이는 계양 측정 층고 기반 근사' }, data.stat),
      };
      return send(res, 200, body, 'public, s-maxage=86400, stale-while-revalidate=86400');
    } catch (e) {
      if (e && e.budget) {
        const wait = 3600 - (Math.floor(now() / 1000) % 3600);
        res.setHeader('Retry-After', String(wait));
        return problem(res, 429, 'budget-exhausted', '이 서버의 시간당 건물 조회 한도에 닿았습니다', '잠시 뒤 다시 시도하세요', { retryAfterSec: wait });
      }
      console.error(`buildings cell ${ix},${iy}: ${(e && e.name) || 'Error'}: ${redactVworld((e && e.message) || e, env).slice(0, 200)}`);
      return problem(res, 502, 'upstream', '건물 서비스를 부르지 못했습니다', '잠시 뒤 다시 시도하세요');   // 원인 문구는 밖으로 내보내지 않는다
    }
  };
}

module.exports = createHandler();
module.exports.createHandler = createHandler;
module.exports.MAX_PAGES = MAX_PAGES;
