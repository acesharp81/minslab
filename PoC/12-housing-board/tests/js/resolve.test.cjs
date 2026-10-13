/* api/v1/resolve.js — 코드 해석 API. 네트워크 없이 가짜 fetch 로 시험한다. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const R = require('../../handlers/v1/resolve.js');

const ROW = (cd, nm, lvl) => ({ region_cd: cd, sido_cd: cd.slice(0, 2), sgg_cd: cd.slice(2, 5), umd_cd: cd.slice(5, 8), ri_cd: cd.slice(8, 10), locatadd_nm: nm, locallow_nm: nm.split(' ').pop(), locathigh_cd: '', adpt_de: '' });
const STAN_ROWS = [ROW('2824500000', '인천광역시 계양구'), ROW('2824510900', '인천광역시 계양구 박촌동'), ROW('2824511000', '인천광역시 계양구 동양동'), ROW('2824511100', '인천광역시 계양구 귤현동')];
const stanJson = (rows) => ({ StanReginCd: [{ head: [{ totalCount: rows.length }, { numOfRows: '1000', pageNo: '1', type: 'JSON' }, { RESULT: { resultCode: 'INFO-0', resultMsg: 'NOMAL SERVICE' } }] }, { row: rows }] });
const SQUARE = (x, y, d = 0.01) => ({ type: 'MultiPolygon', coordinates: [[[[x, y], [x + d, y], [x + d, y + d], [x, y + d], [x, y]]]] });
const vwJson = (feature) => ({ response: { status: feature ? 'OK' : 'NOT_FOUND', result: feature ? { featureCollection: { features: [feature] } } : undefined } });

function harness(over = {}) {
  const calls = [], dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rs-'));
  const env = over.env || { DATA_GO_KR_KEY_RESOLVE_1: 'SECRET-R1', VWORLD_KEY: 'VW-SECRET', VWORLD_DOMAIN: 'localhost' };
  const fakeFetch = async (url) => {
    calls.push(url);
    if (over.fetch) return over.fetch(url);
    const u = new URL(url);
    if (u.hostname === 'apis.data.go.kr') return { ok: true, status: 200, json: async () => (u.searchParams.get('sgg_cd') === '245' && u.searchParams.get('sido_cd') === '28' ? stanJson(STAN_ROWS) : { RESULT: { resultCode: 'INFO-3' } }) };
    const f = u.searchParams.get('attrFilter'), layer = u.searchParams.get('data');
    if (layer === 'LT_C_ADEMD_INFO') return { ok: true, status: 200, json: async () => vwJson({ properties: { emd_cd: '28245109' }, geometry: SQUARE(126.73, 37.53) }) };
    if (layer === 'LT_C_ADSIGG_INFO') return { ok: true, status: 200, json: async () => vwJson({ properties: { sig_cd: '28245' }, geometry: SQUARE(126.68, 37.52, 0.1) }) };
    if (layer === 'LP_PA_CBND_BUBUN') return { ok: true, status: 200, json: async () => (f.includes('2824511000104790000') ? vwJson({ properties: { pnu: '2824511000104790000', addr: '인천광역시 계양구 동양동 479', jibun: '479도' }, geometry: SQUARE(126.758, 37.55, 0.003) }) : vwJson(null)) };
    throw new Error('예상 밖 호출 ' + url);
  };
  const handler = R.createHandler({ fetch: fakeFetch, env, now: () => Date.parse('2026-10-05T03:00:00Z'), cacheDir: dir, readCoverage: over.readCoverage || (() => ({ 28245: { slug: 'incheon-gyeyang', name: '인천 계양구', updatedAt: '2026-10-03', visibility: 'public' } })) });
  const run = async (url, method = 'GET') => {
    const res = { headers: {}, statusCode: 0, body: '', setHeader(k, v) { this.headers[k.toLowerCase()] = v; }, end(b) { this.body = b; } };
    await handler({ method, url }, res);
    return { status: res.statusCode, headers: res.headers, json: res.body ? JSON.parse(res.body) : null, raw: res.body };
  };
  return { run, calls, dir, done: () => fs.rmSync(dir, { recursive: true, force: true }) };
}

test('법정동 10자리: 이름·수준·경계·bbox·커버리지, 표준코드 표는 시군구 한 번만 받아 캐시한다', async () => {
  const h = harness();
  const r = await h.run('/api/v1/resolve?code=2824510900');
  assert.equal(r.status, 200);
  assert.deepEqual([r.json.type, r.json.canonical, r.json.sgg, r.json.bjd, r.json.name, r.json.level], ['bjd', '2824510900', '28245', '2824510900', '인천광역시 계양구 박촌동', 'umd']);
  assert.deepEqual(r.json.bbox, [126.73, 37.53, 126.74, 37.54]);
  assert.deepEqual(r.json.center, [126.735, 37.535]);
  assert.equal(r.json.geometry.type, 'Polygon');
  assert.deepEqual(r.json.coverage, { tier: 'A', slug: 'incheon-gyeyang', name: '인천 계양구', updatedAt: '2026-10-03', visibility: 'public' });
  assert.equal(r.headers['cache-control'], 'public, s-maxage=300, stale-while-revalidate=300');
  const stanCalls = () => h.calls.filter((u) => u.includes('StanReginCd')).length;
  assert.equal(stanCalls(), 1);
  await h.run('/api/v1/resolve?bjd=2824511000');                              // 같은 시군구는 캐시
  assert.equal(stanCalls(), 1);
  assert.ok(!h.raw && !JSON.stringify(r.json).includes('SECRET'));
  h.done();
});

test('8자리 emd 는 00을 붙이고 알려 준다. 시군구는 geometry 를 기본 생략, geometry=1 이면 포함', async () => {
  const h = harness();
  const a = await h.run('/api/v1/resolve?code=28245109');
  assert.equal(a.json.canonical, '2824510900'); assert.deepEqual(a.json.warnings, ['padded-8-digit']);
  const s = await h.run('/api/v1/resolve?code=28245');
  assert.equal(s.json.type, 'sgg'); assert.equal(s.json.name, '인천광역시 계양구'); assert.equal(s.json.geometry, undefined); assert.ok(s.json.bbox);
  const g = await h.run('/api/v1/resolve?sgg=28245&geometry=1');
  assert.ok(g.json.geometry);
  h.done();
});

test('PNU: 지번·건축HUB 인자·필지 경계, 필지를 못 찾으면 법정동 경계로 후퇴하고 알린다', async () => {
  const h = harness();
  const r = await h.run('/api/v1/resolve?pnu=2824511000104790000');
  assert.equal(r.status, 200);
  assert.equal(r.json.type, 'pnu'); assert.equal(r.json.bjd, '2824511000');
  assert.equal(r.json.parcel.jibun, '479'); assert.equal(r.json.parcel.addr, '인천광역시 계양구 동양동 479');
  assert.deepEqual(r.json.parcel.hub, { sigunguCd: '28245', bjdongCd: '11000', platGbCd: '0', bun: '0479', ji: '0000' });
  assert.ok(r.json.parcel.geometry);
  const miss = await h.run('/api/v1/resolve?pnu=2824511000104800000');         // 필지 없음 → 법정동 경계
  assert.equal(miss.status, 200); assert.ok(miss.json.warnings.includes('parcel-not-found')); assert.ok(miss.json.bbox);
  assert.equal(miss.json.parcel.geometry, null);
  h.done();
});

test('오류: 형식·종류·시도·모르는 시군구·모르는 법정동(후보 포함)을 problem+json 으로', async () => {
  const h = harness();
  const bad = await h.run('/api/v1/resolve?code=abc');
  assert.equal(bad.status, 400); assert.equal(bad.json.code, 'invalid-code'); assert.match(bad.headers['content-type'], /application\/problem\+json/);
  assert.equal(bad.json.type, '/problems/invalid-code'); assert.equal(bad.json.title.length > 0, true); assert.equal(bad.json.status, 400);   // RFC 7807: type 은 상대 URI
  assert.equal((await h.run('/api/v1/resolve?bjd=28245')).json.reason, 'type-mismatch');
  assert.equal((await h.run('/api/v1/resolve?code=28')).status, 422);
  const noSgg = await h.run('/api/v1/resolve?code=28999'); assert.equal(noSgg.status, 404); assert.equal(noSgg.json.code, 'unknown-code');
  const noBjd = await h.run('/api/v1/resolve?code=2824519900'); assert.equal(noBjd.status, 404);
  assert.ok(noBjd.json.suggestions.length >= 3 && noBjd.json.suggestions[0].bjd);
  assert.equal((await h.run('/api/v1/resolve')).status, 400);
  assert.equal((await h.run('/api/v1/resolve?code=28245&code=28245')).status, 400);
  assert.equal((await h.run('/api/v1/resolve?code=28245&x=1')).status, 400);
  assert.equal((await h.run('/api/v1/resolve?code=28245', 'POST')).status, 405);
  h.done();
});

test('커버리지: 번들이 없는 시군구는 tier none', async () => {
  const h = harness({ readCoverage: () => ({}) });
  assert.deepEqual((await h.run('/api/v1/resolve?code=2824510900')).json.coverage, { tier: 'none' });
  h.done();
});

test('V-World 실패·키 없음이면 경계 없이 이름과 커버리지만(경고 포함)', async () => {
  const noKey = harness({ env: { DATA_GO_KR_KEY_RESOLVE_1: 'k' } });
  const a = await noKey.run('/api/v1/resolve?code=2824510900');
  assert.equal(a.status, 200); assert.ok(a.json.warnings.includes('geometry-not-configured')); assert.equal(a.json.bbox, undefined); assert.equal(a.json.name, '인천광역시 계양구 박촌동');
  noKey.done();
  const down = harness({ fetch: async (url) => { if (url.includes('vworld')) throw new Error('boom VW-SECRET'); return { ok: true, status: 200, json: async () => stanJson(STAN_ROWS) }; } });
  const b = await down.run('/api/v1/resolve?code=2824510900');
  assert.equal(b.status, 200); assert.ok(b.json.warnings.includes('geometry-unavailable'));
  assert.ok(!b.raw.includes('VW-SECRET'));
  down.done();
});

test('키: 용도 키가 없으면 503, 한도 오류로 모두 소진되면 429 와 Retry-After, 원천 오류는 502 로 원인을 숨긴다', async () => {
  const none = harness({ env: { VWORLD_KEY: 'v' } });
  assert.equal((await none.run('/api/v1/resolve?code=28245')).status, 503); none.done();
  const quota = harness({ fetch: async () => ({ ok: true, status: 200, json: async () => ({ response: { header: { resultCode: '22' } } }) }) });
  const q = await quota.run('/api/v1/resolve?code=28245');
  assert.equal(q.status, 429); assert.ok(Number(q.headers['retry-after']) > 0); assert.equal(q.json.code, 'keys-exhausted'); assert.equal(q.headers['cache-control'], 'no-store'); quota.done();
  const down = harness({ fetch: async () => { throw new Error('upstream SECRET-R1 down'); } });
  const d = await down.run('/api/v1/resolve?code=28245');
  assert.equal(d.status, 502); assert.ok(!d.raw.includes('SECRET-R1')); down.done();
});

test('지오메트리 단순화: 링을 600점 이하로 줄이고 닫으며 소수 5자리로 맞춘다', () => {
  const ring = Array.from({ length: 5000 }, (_, i) => [126 + Math.cos(i / 800) * 0.01234567, 37 + Math.sin(i / 800) * 0.01234567]);
  const g = R.thinGeometry({ type: 'Polygon', coordinates: [[...ring, ring[0]]] });
  assert.ok(g.coordinates[0].length <= 601);
  assert.deepEqual(g.coordinates[0][0], g.coordinates[0][g.coordinates[0].length - 1]);
  assert.ok(g.coordinates[0].every((p) => String(p[0]).split('.')[1].length <= 5));
  assert.equal(R.thinGeometry({ type: 'Polygon', coordinates: [[[0, 0], [1, 1]]] }), null);
  assert.deepEqual(R.bboxOf(SQUARE(126.7, 37.5)), [126.7, 37.5, 126.71, 37.51]);
});

test('readCoverage: 실제 regions/ 에서 계양·광산구·나주 시군구 코드를 읽는다', () => {
  const cov = R.readCoverage();
  assert.equal(cov['28245'].slug, 'incheon-gyeyang'); assert.equal(cov['12330'].slug, 'gwangju-gwangsan'); assert.equal(cov['12170'].slug, 'jeonnam-naju');
  assert.deepEqual(R.readCoverage('/nonexistent/path'), {});
});

test('readCoverage: 운영(production)에서는 미리보기(preview) 지역을 뺀다', () => {
  const fs = require('fs'), os = require('os'), path = require('path');
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'cov-'));
  fs.writeFileSync(path.join(root, 'index.json'), JSON.stringify({ regions: [{ slug: 'pub', name: '공개', visibility: 'public', updatedAt: '2026-10-01' }, { slug: 'pre', name: '미리보기', visibility: 'preview', updatedAt: '2026-10-02' }] }));
  for (const [slug, code] of [['pub', '11111'], ['pre', '22222']]) { fs.mkdirSync(path.join(root, slug)); fs.writeFileSync(path.join(root, slug, 'region.json'), JSON.stringify({ codes: [{ code, type: 'sigungu', name: slug }] })); }
  assert.deepEqual(Object.keys(R.readCoverage(root)).sort(), ['11111', '22222']);
  assert.deepEqual(Object.keys(R.readCoverage(root, true)), ['11111']);
  fs.rmSync(root, { recursive: true, force: true });
});

test('vworldCreds: Vercel 에서는 운영키(VWORLD_KEY), 로컬에서는 개발키(VWORLD_DEV_KEY)가 있으면 그것, domain 은 VWORLD_DOMAIN 우선', () => {
  const both = { VWORLD_KEY: 'op', VWORLD_DEV_KEY: 'dev', VWORLD_DOMAIN: 'localhost' };
  assert.deepEqual(R.vworldCreds(both), { key: 'dev', domain: 'localhost' });
  assert.deepEqual(R.vworldCreds({ ...both, VERCEL: '1', VWORLD_DOMAIN: 'housing-board.vercel.app' }), { key: 'op', domain: 'housing-board.vercel.app' });
  assert.deepEqual(R.vworldCreds({ VWORLD_KEY: 'op' }), { key: 'op', domain: 'localhost' });                       // 개발키가 없으면 VWORLD_KEY
  assert.deepEqual(R.vworldCreds({ VWORLD_KEY: 'op', VERCEL: '1', VERCEL_PROJECT_PRODUCTION_URL: 'x.vercel.app' }), { key: 'op', domain: 'x.vercel.app' });
  assert.equal(R.vworldCreds({}).key, undefined);
});

test('V-World 호출: 로컬이면 개발키와 domain 을 요청에 싣고(운영키는 안 씀), 키 값은 응답에 나오지 않는다', async () => {
  const h = harness({ env: { DATA_GO_KR_KEY_RESOLVE_1: 'dgk', VWORLD_KEY: 'OPERATING-KEY', VWORLD_DEV_KEY: 'DEVELOPMENT-KEY', VWORLD_DOMAIN: 'localhost' } });
  const r = await h.run('/api/v1/resolve?bjd=2824510900');
  assert.equal(r.status, 200);
  const vw = h.calls.filter((u) => u.includes('api.vworld.kr'));
  assert.ok(vw.length >= 1);
  for (const u of vw) { assert.ok(u.includes('key=DEVELOPMENT-KEY') && u.includes('domain=localhost'), u); assert.ok(!u.includes('OPERATING-KEY')); }
  assert.ok(!JSON.stringify(r).includes('DEVELOPMENT-KEY') && !JSON.stringify(r).includes('OPERATING-KEY'));
  h.done();
});

test('구가 있는 시(화성·수원 …)는 V-World 에 시 경계가 없고 구만 있어 앞 4자리가 같은 구 경계를 합쳐 시 경계로 연다(districts-merged). 구도 없으면 boundary-not-found', async () => {
  const rows = [ROW('4159000000', '경기도 화성시'), ROW('4159700000', '경기도 화성시 동탄구'), ROW('4159710700', '경기도 화성시 동탄구 중동'), ROW('4159100000', '경기도 화성시 만세구')];
  const feat = (cd, x) => ({ properties: { sig_cd: cd }, geometry: SQUARE(x, 37.2, 0.05) });
  const fetchFn = (children) => async (url) => {
    const u = new URL(url);
    if (u.hostname === 'apis.data.go.kr') { const sg = u.searchParams.get('sgg_cd'); return { ok: true, status: 200, json: async () => (u.searchParams.get('sido_cd') === '41' && sg === '590' ? stanJson(rows) : sg === '597' ? stanJson([rows[1], rows[2]]) : { RESULT: { resultCode: 'INFO-3' } }) }; }
    const f = u.searchParams.get('attrFilter');
    if (u.searchParams.get('data') === 'LT_C_ADSIGG_INFO') return { ok: true, status: 200, json: async () => (f === 'sig_cd:=:41590' ? vwJson(null) : f === 'sig_cd:like:4159' && children ? { response: { status: 'OK', result: { featureCollection: { features: [feat('41591', 126.9), feat('41597', 127.1)] } } } } : vwJson(null)) };
    if (u.searchParams.get('data') === 'LT_C_ADEMD_INFO') return { ok: true, status: 200, json: async () => vwJson({ properties: { emd_cd: '41597107' }, geometry: SQUARE(127.1, 37.2, 0.02) }) };
    throw new Error('예상 밖 호출 ' + url);
  };
  const h = harness({ fetch: fetchFn(true), readCoverage: () => ({}) });
  const r = await h.run('/api/v1/resolve?sgg=41590&geometry=1');
  assert.equal(r.status, 200); assert.deepEqual(r.json.warnings, ['districts-merged']); assert.equal(r.json.geometry.type, 'MultiPolygon'); assert.equal(r.json.geometry.coordinates.length, 2);
  assert.deepEqual(r.json.bbox, [126.9, 37.2, 127.15, 37.25]); assert.deepEqual(r.json.center, [127.025, 37.225]); assert.equal(r.json.coverage.tier, 'none');
  const calls = h.calls.filter((u) => u.includes('LT_C_ADSIGG_INFO')).map((u) => new URL(u).searchParams.get('attrFilter')); assert.deepEqual(calls, ['sig_cd:=:41590', 'sig_cd:like:4159']);
  await h.run('/api/v1/resolve?sgg=41590&geometry=1'); assert.equal(h.calls.filter((u) => u.includes('LT_C_ADSIGG_INFO')).length, 2);                    // 두 번째는 캐시
  const b = await h.run('/api/v1/resolve?bjd=4159710700'); assert.equal(b.status, 200); assert.equal(b.json.warnings, undefined);                           // 구 아래 법정동은 법정동 경계라 영향 없음
  const none = harness({ fetch: fetchFn(false), readCoverage: () => ({}) }); const n = await none.run('/api/v1/resolve?sgg=41590&geometry=1');
  assert.deepEqual(n.json.warnings, ['boundary-not-found']); assert.equal(n.json.geometry, undefined);
  h.done(); none.done();
});

test('neighbors: 같은 시군구의 읍면동(리 제외)을 법정동·필지는 자기 자신을 빼고, 시군구는 전체를 준다(최대 150)', async () => {
  const h = harness();
  const b = await h.run('/api/v1/resolve?bjd=2824510900');
  assert.deepEqual(b.json.neighbors, [{ bjd: '2824511000', name: '동양동' }, { bjd: '2824511100', name: '귤현동' }]);                                // 박촌동 자신은 빠짐, 시군구 행은 읍면동이 아님
  const s = await h.run('/api/v1/resolve?sgg=28245&geometry=0');
  assert.deepEqual(s.json.neighbors.map((x) => x.name), ['박촌동', '동양동', '귤현동']);
  const p = await h.run('/api/v1/resolve?pnu=2824511000104790000'); assert.deepEqual(p.json.neighbors.map((x) => x.bjd), ['2824510900', '2824511100']);
  const many = harness({ fetch: async (url) => { const u = new URL(url); if (u.hostname === 'apis.data.go.kr') return { ok: true, status: 200, json: async () => stanJson([ROW('2824500000', '인천광역시 계양구'), ...Array.from({ length: 200 }, (_, i) => ROW(`28245${String(101 + i).padStart(3, '0')}00`, `인천광역시 계양구 가${i}동`))]) }; return { ok: true, status: 200, json: async () => vwJson({ properties: {}, geometry: SQUARE(126.7, 37.5) }) }; } });
  assert.equal((await many.run('/api/v1/resolve?sgg=28245')).json.neighbors.length, 150);
  const none = harness({ fetch: async (url) => { const u = new URL(url); if (u.hostname === 'apis.data.go.kr') return { ok: true, status: 200, json: async () => stanJson([ROW('2824500000', '인천광역시 계양구')]) }; return { ok: true, status: 200, json: async () => vwJson({ properties: {}, geometry: SQUARE(126.7, 37.5) }) }; } });
  assert.equal((await none.run('/api/v1/resolve?sgg=28245')).json.neighbors, undefined);                                                         // 읍면동이 없으면 항목 자체가 없다
  h.done(); many.done(); none.done();
});
