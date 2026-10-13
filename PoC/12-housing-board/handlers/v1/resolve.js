/* 코드 해석 API: 표준코드(법정동·시군구·PNU)를 받아 지도가 열 영역을 알려 준다.

   GET /api/v1/resolve?code=<코드>        (또는 sgg= | bjd= | pnu= | project= 중 하나)   선택: geometry=0|1
   → 200 { type, canonical, input, sgg, bjd?, pnu?, project?, name, level, bbox, center, geometry?, parcel?, coverage, warnings?, source, asOf }
   → 4xx/5xx application/problem+json (RFC 7807): invalid-code 400 · unsupported-level 422 · unknown-code 404 · unknown-project 404 · keys-exhausted 429 · not-configured 503 · upstream 502

   사업 id(PRJ-{시군구5}-{일련4}, lib/projects.js)는 사업 레지스트리(registry/projects.json)에서 찾아 그 사업의 위치로 연다: 필지(pnus 첫째)가 있으면 필지, 없으면 법정동(bjdCodes 첫째),
   그것도 없으면 시군구. 응답은 그 위치의 응답과 같고 type 이 'project', canonical 이 사업 id 이며 project{ id, name?, units?, stageCode, stage, pnus, bjdCodes, block?, supersededFrom? }가 붙는다.
   - 위치가 필지가 아니면 warnings 에 'project-unlocated'(위치 미연결), 합병되어 폐기된 id 를 남은 사업으로 열었으면 'project-superseded'.
   - 번들 단지의 사업(refs 에 bundle)은 project.block 으로 그 단지를 연 채로 열린다. 발급되지 않은 id 는 404 unknown-project.

   처리 순서: 형식 판별(lib/codes.js) → 행정표준코드 API(StanReginCd)로 존재 확인(시군구 단위로 가져와 캐시) → V-World 경계·필지(속성 조회) → 커버리지(regions/ 번들 유무).
   - 인증키: lib/keys.js 의 RESOLVE 용도 풀(DATA_GO_KR_KEY_RESOLVE_<N>, 없으면 DATA_GO_KR_KEY). V-World 는 VWORLD_KEY(운영키)·VWORLD_DOMAIN(그 키에 등록한 서비스 URL,
     운영은 housing-board.vercel.app). Vercel 밖(로컬)에서는 VWORLD_DEV_KEY 가 있으면 그것을 쓰고 VWORLD_DOMAIN 은 localhost 로 둔다.
   - 캐시: lib/cache.js 로컬 캐시 24시간(표준코드 표·경계·필지). 키·원본 응답은 응답에 싣지 않는다.
   - PNU 필지를 못 찾으면 법정동 경계로 후퇴하고 warnings 에 알린다. V-World 가 실패하면 경계 없이 이름·커버리지만 준다.
   - 시군구 폴리곤은 크므로 geometry 는 기본 생략(geometry=1 이면 포함). 링은 최대 600점으로 줄인다.
   시험: tests/js/resolve.test.cjs */
'use strict';
const fs = require('fs');
const path = require('path');
const { createKeyPool, fileStore, memoryStore, KeyPoolError } = require('../../lib/keys.js');
const { createCache, defaultDir } = require('../../lib/cache.js');
const { createStan } = require('../../lib/stan.js');
const codes = require('../../lib/codes.js');
const { readCoverage } = require('../../lib/coverage.js');   // 시군구 코드 → 번들(코드 검색 API 와 공용)
const Projects = require('../../lib/projects.js');
const { readRegistry } = require('../../lib/registry.js');

const { VWORLD_URL, vworldCreds, redactVworld } = require('../../lib/vworld.js');


const TTL_MS = 24 * 3600 * 1000;
const FETCH_TIMEOUT_MS = 10000;
const MAX_RING_POINTS = 600;
const ALLOWED = new Set(['code', 'sgg', 'bjd', 'pnu', 'project', 'geometry']);
const MAX_NEIGHBORS = 150;

const LAYERS = {
  sgg: { layer: 'LT_C_ADSIGG_INFO', filter: (c) => `sig_cd:=:${c}`, source: 'V-World 시군구 경계(LT_C_ADSIGG_INFO)' },
  umd: { layer: 'LT_C_ADEMD_INFO', filter: (c) => `emd_cd:=:${c.slice(0, 8)}`, source: 'V-World 법정읍면동 경계(LT_C_ADEMD_INFO)' },
  pnu: { layer: 'LP_PA_CBND_BUBUN', filter: (c) => `pnu:=:${c}`, source: 'V-World 연속지적도(LP_PA_CBND_BUBUN)' },
};

/* 지오메트리 단순화·bbox 는 lib/geom.js(건물·인허가 API 와 공용) */
const { round5, thinGeometry: thinGeometryTo, bboxOf } = require('../../lib/geom.js');
const thinGeometry = (g) => thinGeometryTo(g, MAX_RING_POINTS);

/* 서버 로그용 한 줄: 오류 종류와 문구만 남기고, 인증키·도메인 값은 가린다(응답에는 싣지 않는다) */
function logFailure(where, e, env = process.env) {
  const cause = e && e.cause ? ` (cause ${String(e.cause.code || e.cause.name || '')} ${redactVworld(e.cause.message || '', env).slice(0, 120)})` : '';
  console.error(`resolve ${where}: ${(e && e.name) || 'Error'}: ${redactVworld((e && e.message) || e, env).slice(0, 200)}${cause}`);
}

/* ---------- 응답 ---------- */
function createHandler(overrides = {}) {
  const env = overrides.env || process.env;
  const now = overrides.now || (() => Date.now());
  const doFetch = overrides.fetch || ((...a) => fetch(...a));
  const dir = overrides.cacheDir || defaultDir(env);
  const cache = overrides.cache || createCache({ dir, now });
  const pool = overrides.pool || createKeyPool({ env, now, store: env.VERCEL ? memoryStore() : fileStore(path.join(dir, 'key-usage.json')) });
  const stan = createStan({ doFetch, pool, cache });
  const coverageOf = overrides.readCoverage || (() => readCoverage(undefined, env.VERCEL_ENV === 'production'));
  const registryIndex = overrides.registryIndex ? () => overrides.registryIndex : () => readRegistry(overrides.registryFile).index;

  const send = (res, status, body, cacheControl, type = 'application/json; charset=utf-8') => {
    res.statusCode = status;
    res.setHeader('Content-Type', type);
    res.setHeader('Cache-Control', cacheControl);
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.end(JSON.stringify(body));
  };
  const problem = (res, status, code, title, detail, extra, cc) => send(res, status, Object.assign({ type: `/problems/${code}`, title, status, code, detail }, extra), cc || (status >= 500 || status === 429 ? 'no-store' : 'public, s-maxage=60'), 'application/problem+json; charset=utf-8');

  async function getJson(url) {
    const r = await doFetch(url, { signal: AbortSignal.timeout(FETCH_TIMEOUT_MS), headers: { Accept: 'application/json' } });
    if (!r.ok) { const e = new Error(`HTTP ${r.status}`); e.status = r.status; throw e; }
    return r.json();
  }

  /* 시군구 안 표준코드 행 전부(24시간 캐시, lib/stan.js). 없으면 [] */
  const stanRows = (sido, sgg) => stan.rows(sido, sgg);

  /* V-World 속성 조회 → { geometry, props } | null. 실패는 던진다 */
  async function vworld(kind, code) {
    const { key, domain } = vworldCreds(env);
    if (!key) { const e = new Error('VWORLD_KEY 없음'); e.notConfigured = true; throw e; }
    const L = LAYERS[kind];
    return cache.wrap(`vw:${L.layer}:${code}`, TTL_MS, async () => {
      const q = new URLSearchParams({ service: 'data', request: 'GetFeature', data: L.layer, key, domain, format: 'json', size: '5', crs: 'EPSG:4326', attrFilter: L.filter(code) });
      const json = await getJson(`${VWORLD_URL}?${q}`);
      const st = json && json.response && json.response.status;
      if (st === 'NOT_FOUND') return { none: true };
      if (st !== 'OK') throw new Error(`V-World ${st || '응답 형식'}`);
      const f = ((json.response.result || {}).featureCollection || {}).features || [];
      if (!f.length) return { none: true };
      const geometry = thinGeometry(f[0].geometry);
      return geometry ? { geometry, props: { addr: f[0].properties && f[0].properties.addr, jibun: f[0].properties && f[0].properties.jibun } } : { none: true };
    });
  }

  /* 구가 있는 시(수원·청주·포항·창원·고양·용인·천안·전주·화성 …)는 V-World 시군구 경계에 '시' 코드가 없고 구만 있다(실측: 9개 시가 경계 없이 열림).
     시 코드의 앞 4자리가 같은 구들(수원 41111·41113·41115·41117)을 한 번에 받아 하나의 MultiPolygon 으로 합쳐 시 경계로 쓴다. 구도 없으면 { none:true } */
  async function vworldDistricts(sgg) {
    const { key, domain } = vworldCreds(env);
    if (!key) { const e = new Error('VWORLD_KEY 없음'); e.notConfigured = true; throw e; }
    const prefix = sgg.slice(0, 4);
    return cache.wrap(`vw:${LAYERS.sgg.layer}:like:${prefix}`, TTL_MS, async () => {
      const q = new URLSearchParams({ service: 'data', request: 'GetFeature', data: LAYERS.sgg.layer, key, domain, format: 'json', size: '20', crs: 'EPSG:4326', attrFilter: `sig_cd:like:${prefix}` });
      const json = await getJson(`${VWORLD_URL}?${q}`);
      const st = json && json.response && json.response.status;
      if (st === 'NOT_FOUND') return { none: true };
      if (st !== 'OK') throw new Error(`V-World ${st || '응답 형식'}`);
      const f = ((json.response.result || {}).featureCollection || {}).features || [];
      const polys = f.flatMap((x) => { const g = thinGeometry(x.geometry, Math.max(120, Math.floor(MAX_RING_POINTS / Math.max(1, f.length)))); return !g ? [] : g.type === 'Polygon' ? [g.coordinates] : g.coordinates; });
      return polys.length ? { geometry: polys.length === 1 ? { type: 'Polygon', coordinates: polys[0] } : { type: 'MultiPolygon', coordinates: polys } } : { none: true };
    });
  }

  return async function handler(req, res) {
    if (req.method !== 'GET' && req.method !== 'HEAD') { res.setHeader('Allow', 'GET, HEAD'); return problem(res, 405, 'method', '허용하지 않는 방식', 'GET 만 지원합니다'); }
    const params = new URL(req.url || '/', 'http://local').searchParams;
    const names = [...new Set(params.keys())];
    if (names.some((n) => !ALLOWED.has(n))) return problem(res, 400, 'invalid-query', '알 수 없는 매개변수', `허용: ${[...ALLOWED].join(', ')}`);
    const given = ['code', 'sgg', 'bjd', 'pnu', 'project'].filter((n) => params.has(n));
    if (given.length !== 1 || params.getAll(given[0]).length !== 1) return problem(res, 400, 'invalid-query', '코드는 하나만 넘겨야 합니다', 'code, sgg, bjd, pnu, project 중 하나를 한 번만 쓰세요', undefined, 'public, s-maxage=3600');
    const input = params.get(given[0]);
    const asked = codes.classify(input);
    if (!asked.ok) return problem(res, 400, 'invalid-code', '코드 형식이 맞지 않습니다', asked.detail, { reason: asked.reason }, 'public, s-maxage=3600');
    if (given[0] !== 'code' && given[0] !== asked.type) return problem(res, 400, 'invalid-code', '코드 종류가 다릅니다', `${given[0]}= 에 ${asked.type} 코드가 왔습니다`, { reason: 'type-mismatch' }, 'public, s-maxage=3600');
    if (asked.type === 'sido') return problem(res, 422, 'unsupported-level', '시도 단위는 지도 대상이 아닙니다', '시군구(5자리) 이하 코드를 쓰세요', undefined, 'public, s-maxage=3600');
    /* 사업 id: 레지스트리에서 사업의 위치를 찾아 그 위치(필지 → 법정동 → 시군구)의 코드로 아래 해석을 그대로 한다. 위치는 사업이 갖고 있어 요청이 정하지 못한다 */
    let c = asked, proj = null;
    if (asked.type === 'project') {
      const hit = Projects.lookup(registryIndex(), asked.project);
      if (!hit) return problem(res, 404, 'unknown-project', '발급되지 않은 사업 id 입니다', `${asked.canonical} 는 사업 레지스트리에 없습니다`, { project: asked.canonical }, 'public, s-maxage=60');
      proj = hit;
      const at = hit.project.pnus[0] || hit.project.bjdCodes[0] || hit.project.sgg;
      c = codes.classify(at);
      if (!c.ok || c.type === 'sido') return problem(res, 502, 'upstream', '사업 레지스트리의 위치가 맞지 않습니다', '관리자에게 알려 주세요');   // 검사를 통과한 레지스트리에서는 일어나지 않는다
    }

    const wantGeometry = params.has('geometry') ? params.get('geometry') !== '0' : c.type !== 'sgg';
    try {
      const rows = await stanRows(c.sido, c.sgg);
      const sggRow = codes.findRow(rows, `${c.sgg}00000`);
      if (!sggRow) return problem(res, 404, 'unknown-code', '표준코드 표에 없는 시군구입니다', `${c.sgg}는 행정표준코드(2026-10-05 이후 기준)에 없습니다. 개편으로 바뀐 코드일 수 있습니다`, { sgg: c.sgg });
      let row = sggRow, level = 'sgg';
      if (c.type !== 'sgg') {
        row = codes.findRow(rows, c.bjd);
        if (!row) {
          const umd = rows.filter((r) => codes.levelOf(r) === 'umd').slice(0, 8).map((r) => ({ bjd: r.region_cd, name: r.locatadd_nm }));
          return problem(res, 404, 'unknown-code', '표준코드 표에 없는 법정동입니다', `${c.bjd}는 ${sggRow.locatadd_nm}에 없습니다`, { sgg: c.sgg, suggestions: umd });
        }
        level = codes.levelOf(row);
      }

      const warnings = [], out = { type: c.type, canonical: c.canonical, input: c.input, sgg: c.sgg };
      if (proj) {                                                  // 사업으로 열었다: 위치의 응답에 사업 정보를 붙인다(type 은 project, canonical 은 사업 id)
        const pr = proj.project, bundle = (pr.refs || []).find((r) => r.system === 'bundle');
        out.type = 'project'; out.canonical = pr.id; out.input = asked.input;
        out.project = { id: pr.id, ...(pr.name ? { name: pr.name } : {}), ...(pr.units ? { units: pr.units } : {}), stageCode: pr.stageCode, stage: Projects.STAGES[pr.stageCode], pnus: pr.pnus, bjdCodes: pr.bjdCodes, ...(bundle ? { block: bundle.value } : {}), ...(proj.followed.length ? { supersededFrom: proj.followed[0] } : {}) };
        if (!pr.pnus.length) warnings.push('project-unlocated');
        if (proj.followed.length) warnings.push('project-superseded');
      }
      if (c.bjd) out.bjd = c.bjd;
      if (c.pnu) { out.pnu = c.pnu; const p = codes.parsePnu(c.pnu); out.parcel = { jibun: p.jibun, landType: p.landType === '1' ? '일반' : '산', hub: p.hub, geometry: null }; }
      out.name = row.locatadd_nm; out.level = level;
      /* 같은 시군구의 읍면동(리 제외): 시군구면 전체, 법정동·필지면 자기 자신을 뺀 나머지. 화면이 인허가 사업이 없는 곳에서 '이웃 법정동'을 고르게 한다 */
      const umds = rows.filter((r) => codes.levelOf(r) === 'umd' && r.region_cd !== c.bjd).slice(0, MAX_NEIGHBORS).map((r) => ({ bjd: r.region_cd, name: String(r.locallow_nm || r.locatadd_nm.split(' ').pop()) }));
      if (umds.length) out.neighbors = umds;
      if (c.padded) warnings.push('padded-8-digit');

      let frame = null;
      try {
        let hit = null;
        if (c.type === 'pnu') {
          hit = await vworld('pnu', c.pnu);
          if (hit.none) { warnings.push('parcel-not-found'); hit = null; } else { out.parcel.geometry = hit.geometry; if (hit.props && hit.props.addr) out.parcel.addr = hit.props.addr; frame = hit.geometry; }
        }
        if (!frame) {
          const kind = c.type === 'sgg' ? 'sgg' : 'umd';
          if (c.type !== 'sgg' && level === 'ri') warnings.push('ri-uses-umd-boundary');
          let b = await vworld(kind, c.type === 'sgg' ? c.sgg : c.bjd);
          if (b.none && kind === 'sgg') { const d = await vworldDistricts(c.sgg); if (!d.none) { b = d; warnings.push('districts-merged'); } }   // 구만 있는 시
          if (b.none) warnings.push('boundary-not-found'); else frame = b.geometry;
          if (frame && wantGeometry && c.type !== 'pnu') out.geometry = frame;
          else if (frame && c.type === 'pnu' && wantGeometry) out.geometry = frame;     // 후퇴: 필지가 없으면 법정동 경계
        }
        if (frame) { out.bbox = bboxOf(frame); out.center = [round5((out.bbox[0] + out.bbox[2]) / 2), round5((out.bbox[1] + out.bbox[3]) / 2)]; }
        if (c.type === 'pnu' && out.parcel.geometry && !wantGeometry) out.parcel.geometry = null;
      } catch (e) {
        if (e instanceof KeyPoolError) throw e;
        warnings.push(e.notConfigured ? 'geometry-not-configured' : 'geometry-unavailable');
        if (!e.notConfigured) logFailure('vworld', e);
      }

      const cov = coverageOf()[c.sgg];
      out.coverage = cov ? { tier: 'A', slug: cov.slug, name: cov.name, updatedAt: cov.updatedAt, visibility: cov.visibility } : { tier: 'none' };
      if (warnings.length) out.warnings = warnings;
      out.source = { code: '행정안전부 행정표준코드(법정동코드)', geometry: c.type === 'pnu' ? LAYERS.pnu.source : LAYERS[c.type === 'sgg' ? 'sgg' : 'umd'].source };
      out.asOf = new Date(now()).toISOString().slice(0, 10);
      return send(res, 200, out, 'public, s-maxage=300, stale-while-revalidate=300');
    } catch (e) {
      if (e instanceof KeyPoolError) {
        if (e.code === 'EXHAUSTED') { res.setHeader('Retry-After', String(e.retryAfterSec || 3600)); return problem(res, 429, 'keys-exhausted', '오늘 인증키 한도에 닿았습니다', e.message, { retryAfterSec: e.retryAfterSec }); }
        return problem(res, 503, 'not-configured', '인증키가 설정되어 있지 않습니다', e.message);
      }
      return problem(res, 502, 'upstream', '표준코드 서비스를 부르지 못했습니다', '잠시 뒤 다시 시도하세요');   // 원인 문구는 밖으로 내보내지 않는다(키가 섞일 수 있음)
    }
  };
}

module.exports = createHandler();
module.exports.createHandler = createHandler;
module.exports.readCoverage = readCoverage;
module.exports.vworldCreds = vworldCreds;
module.exports.thinGeometry = thinGeometry;
module.exports.bboxOf = bboxOf;
