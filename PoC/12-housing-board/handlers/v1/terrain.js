/* 지형 타일 중계: AWS Terrain Tiles(terrarium PNG, 미국 동부 S3)를 우리 서버를 거쳐 받아 CDN 에 오래 캐시한다.
   지도는 처음 열 때 이 타일(한 화면 24~42장, 장당 약 100 KB)을 기다리느라 로딩이 가장 길었다(S3 응답 시작 ~0.7 s, 계획서 16절·지도 로딩 분석).
   한 번 받은 타일은 Vercel CDN(서울 icn1 가까운 엣지)에서 바로 나가고, 로컬 개발에서는 로컬 캐시(lib/cache.js)에서 나간다.

   GET /api/v1/terrain?z=<0..14>&x=<0..2^z-1>&y=<0..2^z-1>
   → 200 image/png  Cache-Control: public, max-age=86400, s-maxage=31536000, immutable (원자료는 2017년 이후 바뀌지 않는다)
   → problem+json: invalid-query 400 · out-of-range 400(한국 밖 타일) · method 405 · budget-exhausted 429 · not-found 404 · upstream 502

   - 열린 중계가 되지 않게 한국 범위(경도 124~132°, 위도 33~39.5°)에 걸치는 타일만, z 는 0~14(지도의 DEM maxzoom)만 받는다.
   - 인스턴스별 시간당 원천 호출 상한(TERRAIN_UPSTREAM_PER_HOUR, 기본 3000장)을 넘으면 429.
   - 로컬 캐시 24시간(PNG 를 base64 로). 원천 URL·오류 문구는 응답에 싣지 않는다.
   - 출처 표기('Terrain: AWS Terrain Tiles (SRTM·GMTED2010 © USGS, ETOPO1 © NOAA 등)')는 지도 출처(ⓘ)에 있다. AWS Open Data 의 공개 자료다.
   시험: tests/js/terrainapi.test.cjs */
'use strict';
const { createCache, defaultDir } = require('../../lib/cache.js');

const UPSTREAM = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium';
const MAX_Z = 14;
const KOREA = { w: 124, e: 132, s: 33, n: 39.5 };
const TTL_MS = 24 * 3600 * 1000;
const FETCH_TIMEOUT_MS = 10000;
const DEFAULT_BUDGET_PER_HOUR = 3000;
const OK_CACHE = 'public, max-age=86400, s-maxage=31536000, immutable';
const ALLOWED = new Set(['z', 'x', 'y']);

const lonOf = (x, z) => x / 2 ** z * 360 - 180;
const latOf = (y, z) => { const n = Math.PI - 2 * Math.PI * y / 2 ** z; return 180 / Math.PI * Math.atan(Math.sinh(n)); };
/* 타일(z,x,y)이 한국 범위와 겹치는가 */
function inKorea(z, x, y) {
  const w = lonOf(x, z), e = lonOf(x + 1, z), n = latOf(y, z), s = latOf(y + 1, z);
  return e > KOREA.w && w < KOREA.e && n > KOREA.s && s < KOREA.n;
}

function createHandler(overrides = {}) {
  const env = overrides.env || process.env;
  const now = overrides.now || (() => Date.now());
  const doFetch = overrides.fetch || ((...a) => fetch(...a));
  const cache = overrides.cache || createCache({ dir: overrides.cacheDir || defaultDir(env), now });
  const budgetMax = Number(env.TERRAIN_UPSTREAM_PER_HOUR) > 0 ? Math.floor(Number(env.TERRAIN_UPSTREAM_PER_HOUR)) : DEFAULT_BUDGET_PER_HOUR;
  const budget = { hour: -1, used: 0 };
  const spend = () => {
    const hour = Math.floor(now() / 3600000);
    if (budget.hour !== hour) { budget.hour = hour; budget.used = 0; }
    if (budget.used >= budgetMax) return false;
    budget.used += 1;
    return true;
  };
  const problem = (res, status, code, title, detail) => {
    res.statusCode = status;
    res.setHeader('Content-Type', 'application/problem+json; charset=utf-8');
    res.setHeader('Cache-Control', status === 404 ? 'public, s-maxage=86400' : status >= 500 || status === 429 ? 'no-store' : 'public, s-maxage=60');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.end(JSON.stringify({ type: `/problems/${code}`, title, status, code, detail }));
  };

  return async function terrain(req, res) {
    if (req.method !== 'GET' && req.method !== 'HEAD') { res.setHeader('Allow', 'GET, HEAD'); return problem(res, 405, 'method', '허용하지 않는 메서드', 'GET 만 받습니다'); }
    const q = new URL(req.url, 'http://x').searchParams;
    const extra = [...q.keys()].filter((k) => !ALLOWED.has(k));
    const [z, x, y] = ['z', 'x', 'y'].map((k) => (/^\d{1,6}$/.test(q.get(k) || '') ? Number(q.get(k)) : NaN));
    if (extra.length || ![z, x, y].every(Number.isInteger)) return problem(res, 400, 'invalid-query', '잘못된 요청', 'z·x·y 정수만 받습니다');
    if (z > MAX_Z || x >= 2 ** z || y >= 2 ** z || !inKorea(z, x, y)) return problem(res, 400, 'out-of-range', '범위 밖 타일', `한국 범위의 z 0~${MAX_Z} 타일만 중계합니다`);

    const key = `terrain:${z}/${x}/${y}`;
    let b64 = cache.get(key);
    if (b64 == null) {
      if (!spend()) return problem(res, 429, 'budget-exhausted', '잠시 뒤 다시', '원천 호출 상한을 넘었습니다');
      let r;
      try { r = await doFetch(`${UPSTREAM}/${z}/${x}/${y}.png`, { signal: AbortSignal.timeout(FETCH_TIMEOUT_MS) }); }
      catch (e) { return problem(res, 502, 'upstream', '원천 응답 없음', '지형 타일을 받지 못했습니다'); }
      if (r.status === 404 || r.status === 403) return problem(res, 404, 'not-found', '타일 없음', '이 위치의 지형 타일이 없습니다');
      if (!r.ok) return problem(res, 502, 'upstream', '원천 오류', '지형 타일을 받지 못했습니다');
      b64 = Buffer.from(await r.arrayBuffer()).toString('base64');
      cache.set(key, b64, TTL_MS);
    }
    res.statusCode = 200;
    res.setHeader('Content-Type', 'image/png');
    res.setHeader('Cache-Control', OK_CACHE);
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.end(Buffer.from(b64, 'base64'));
  };
}

module.exports = createHandler();
module.exports.createHandler = createHandler;
module.exports.inKorea = inKorea;
