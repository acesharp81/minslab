'use strict';
/* api/v1/buildings.js — 칸 단위 건물 요청 시 조회. 네트워크 없이 가짜 fetch 로 시험한다. */
const test = require('node:test');
const assert = require('node:assert/strict');
const { createCache } = require('../../lib/cache.js');
const api = require('../../handlers/v1/buildings.js');

const SQ = (x, y, d = 0.0002) => ({ type: 'Polygon', coordinates: [[[x, y], [x + d, y], [x + d, y + d], [x, y + d], [x, y]]] });
const feat = (x, y, props = {}, d) => ({ type: 'Feature', properties: Object.assign({ bld_nm: '건물', usability: '02000', grnd_flr: '5', height: '13' }, props), geometry: SQ(x, y, d) });
const page = (features, total = 1, current = 1) => ({ response: { status: 'OK', page: { total: String(total), current: String(current) }, result: { featureCollection: { type: 'FeatureCollection', features } } } });
const ok = (json) => ({ ok: true, status: 200, json: async () => json });
const CELL = '12675,3755';                                   // 경도 126.75~126.76, 위도 37.55~37.56
const IN1 = feat(126.7510, 37.5510, { bld_nm: '안1' }), IN2 = feat(126.7550, 37.5550, { bld_nm: '안2' });
const OUT = feat(126.7599, 37.5510, { bld_nm: '이웃칸' }, 0.0004);   // 중심점이 오른쪽 이웃 칸(126.76 이상)
const TINY = feat(126.7530, 37.5530, { bld_nm: '작음' }, 0.00003);

function harness(over = {}) {
  const calls = [], clock = { t: Date.parse('2026-10-05T03:00:00Z') };
  const env = over.env || { VWORLD_KEY: 'OPERATING-KEY', VWORLD_DEV_KEY: 'DEVELOPMENT-KEY', VWORLD_DOMAIN: 'localhost' };
  const handler = api.createHandler({
    env, now: () => clock.t, cache: createCache({ persist: false, now: () => clock.t }),
    fetch: async (url, init) => { calls.push(url); if (over.onFetch) over.onFetch(url, init); return (over.fetch || (async () => ok(page([IN1, IN2, OUT, TINY]))))(url, calls.length); },
  });
  const run = async (url, method = 'GET') => {
    const res = { headers: {}, statusCode: 0, body: '', setHeader(k, v) { this.headers[k.toLowerCase()] = v; }, end(b) { this.body = b; } };
    await handler({ method, url }, res);
    return { status: res.statusCode, headers: res.headers, json: res.body ? JSON.parse(res.body) : null, raw: res.body };
  };
  return { run, calls, clock };
}

test('칸 하나: 번들 모양 피처, 칸 안 건물만(이웃 칸·10 m² 미만 제외), 호출 인자와 캐시 헤더', async () => {
  const h = harness();
  const r = await h.run(`/api/v1/buildings?cell=${CELL}`);
  assert.equal(r.status, 200);
  assert.equal(r.json.type, 'FeatureCollection'); assert.deepEqual(r.json.cell, [12675, 3755]); assert.deepEqual(r.json.bbox, [126.75, 37.55, 126.76, 37.56]);
  assert.deepEqual(r.json.features.map((f) => f.properties.n), ['안1', '안2']);
  assert.deepEqual(r.json.features[0].properties, { eh: 13, src: '공식높이', h: 13, f: 5, u: '공동주택', n: '안1' });
  assert.equal(r.json.meta.count, 2); assert.equal(r.json.meta.rawCount, 4); assert.equal(r.json.meta.tinyDropped, 1); assert.equal(r.json.meta.outsideCell, 1);
  assert.equal(r.json.meta.pages, 1); assert.equal(r.json.meta.truncated, false); assert.equal(r.json.meta.fetchedAt, '2026-10-05');
  assert.equal(r.headers['cache-control'], 'public, s-maxage=86400, stale-while-revalidate=86400');
  const u = new URL(h.calls[0]);
  assert.equal(u.hostname, 'api.vworld.kr'); assert.equal(u.searchParams.get('data'), 'LT_C_BLDGINFO'); assert.equal(u.searchParams.get('geomFilter'), 'BOX(126.75,37.55,126.76,37.56)');
  assert.equal(u.searchParams.get('size'), '1000'); assert.equal(u.searchParams.get('crs'), 'EPSG:4326');
});

test('키: 로컬은 개발키·localhost, Vercel 은 운영키·운영 도메인. 키 값은 응답에 없다', async () => {
  const local = harness(); const r = await local.run(`/api/v1/buildings?cell=${CELL}`);
  const lu = new URL(local.calls[0]); assert.equal(lu.searchParams.get('key'), 'DEVELOPMENT-KEY'); assert.equal(lu.searchParams.get('domain'), 'localhost');
  assert.ok(!r.raw.includes('KEY'));
  const prod = harness({ env: { VERCEL: '1', VWORLD_KEY: 'OPERATING-KEY', VWORLD_DEV_KEY: 'DEVELOPMENT-KEY', VWORLD_DOMAIN: 'housing-board.vercel.app' } });
  await prod.run(`/api/v1/buildings?cell=${CELL}`);
  const pu = new URL(prod.calls[0]); assert.equal(pu.searchParams.get('key'), 'OPERATING-KEY'); assert.equal(pu.searchParams.get('domain'), 'housing-board.vercel.app');
  assert.equal((await harness({ env: {} }).run(`/api/v1/buildings?cell=${CELL}`)).status, 503);
});

test('HOME의 서버 전용 키는 Referer로 인증하고 응답·공개 설정에는 노출하지 않는다', async () => {
  let request = null;
  const h = harness({ env: { VWORLD_KEY: 'SERVER-ONLY-KEY', VWORLD_REFERER_AUTH: '1' }, onFetch: (url, init) => { request = { url, init }; } });
  const r = await h.run(`/api/v1/buildings?cell=${CELL}`);
  assert.equal(r.status, 200);
  const url = new URL(request.url);
  assert.equal(url.searchParams.has('domain'), false);
  assert.equal(url.searchParams.get('version'), '2.0');
  assert.equal(request.init.headers.Referer, 'https://www.minslab.kr/poc/home/');
  assert.ok(!r.raw.includes('SERVER-ONLY-KEY'));
});

test('여러 쪽: 마지막 쪽까지 받고, 5쪽을 넘으면 truncated', async () => {
  const two = harness({ fetch: async (url, n) => ok(page([n === 1 ? IN1 : IN2], 2, n)) });
  const r = await two.run(`/api/v1/buildings?cell=${CELL}`);
  assert.equal(r.json.meta.pages, 2); assert.equal(r.json.features.length, 2); assert.equal(r.json.meta.truncated, false);
  assert.equal(new URL(two.calls[1]).searchParams.get('page'), '2');
  const many = harness({ fetch: async (url, n) => ok(page([feat(126.7510 + n * 0.0001, 37.5510, { bld_nm: `b${n}` })], 9, n)) });
  const t = await many.run(`/api/v1/buildings?cell=${CELL}`);
  assert.equal(many.calls.length, api.MAX_PAGES); assert.equal(t.json.meta.truncated, true); assert.equal(t.json.features.length, api.MAX_PAGES);
});

test('NOT_FOUND 는 빈 칸(200). 같은 칸은 캐시에서 주고 원천을 다시 부르지 않는다. 24시간 뒤 만료', async () => {
  const empty = harness({ fetch: async () => ok({ response: { status: 'NOT_FOUND' } }) });
  const e = await empty.run(`/api/v1/buildings?cell=${CELL}`);
  assert.equal(e.status, 200); assert.equal(e.json.features.length, 0);
  const h = harness();
  const a = await h.run(`/api/v1/buildings?cell=${CELL}`), b = await h.run(`/api/v1/buildings?cell=${CELL}`);
  assert.equal(h.calls.length, 1); assert.deepEqual(a.json.features, b.json.features);
  h.clock.t += 24 * 3600 * 1000 + 1;
  await h.run(`/api/v1/buildings?cell=${CELL}`);
  assert.equal(h.calls.length, 2);
});

test('거절: 모르는 쿼리·칸 형식·한국 밖·방식, 원천이 막히면 502 이고 원인 문구(키 포함)는 숨기며 캐시하지 않는다', async () => {
  const h = harness();
  for (const [url, status, code] of [['/api/v1/buildings', 400, 'invalid-query'], [`/api/v1/buildings?cell=${CELL}&x=1`, 400, 'invalid-query'], [`/api/v1/buildings?cell=${CELL}&cell=${CELL}`, 400, 'invalid-query'],
    ['/api/v1/buildings?cell=abc', 400, 'invalid-cell'], ['/api/v1/buildings?cell=1,2', 400, 'invalid-cell'], ['/api/v1/buildings?cell=99999,3755', 400, 'invalid-cell']]) {
    const r = await h.run(url); assert.equal(r.status, status, url); assert.equal(r.json.code, code, url);
    assert.match(r.headers['content-type'], /application\/problem\+json/); assert.equal(r.json.type, `/problems/${code}`);
  }
  assert.equal((await h.run(`/api/v1/buildings?cell=${CELL}`, 'POST')).status, 405);
  assert.equal(h.calls.length, 0);
  const bad = harness({ fetch: async () => { throw new Error('boom key=DEVELOPMENT-KEY'); } });
  const r = await bad.run(`/api/v1/buildings?cell=${CELL}`);
  assert.equal(r.status, 502); assert.equal(r.headers['cache-control'], 'no-store'); assert.ok(!r.raw.includes('DEVELOPMENT-KEY') && !r.raw.includes('boom'));
  await bad.run(`/api/v1/buildings?cell=${CELL}`); assert.equal(bad.calls.length, 2);                      // 실패는 저장하지 않음
  const denied = harness({ fetch: async () => ok({ response: { status: 'ERROR', error: { code: 'INCORRECT_KEY', text: 'x' } } }) });
  assert.equal((await denied.run(`/api/v1/buildings?cell=${CELL}`)).status, 502);
});

test('시간당 원천 호출 상한: 넘으면 429 + Retry-After, 다음 시간에 풀린다, 캐시된 칸은 예산을 쓰지 않는다', async () => {
  const h = harness({ env: { VWORLD_KEY: 'k', BUILDINGS_UPSTREAM_PER_HOUR: '2' } });
  assert.equal((await h.run('/api/v1/buildings?cell=12675,3755')).status, 200);
  assert.equal((await h.run('/api/v1/buildings?cell=12675,3756')).status, 200);
  assert.equal((await h.run('/api/v1/buildings?cell=12675,3755')).status, 200);                    // 캐시: 예산 안 씀
  const r = await h.run('/api/v1/buildings?cell=12676,3755');
  assert.equal(r.status, 429); assert.equal(r.json.code, 'budget-exhausted'); assert.equal(r.headers['cache-control'], 'no-store');
  assert.ok(Number(r.headers['retry-after']) > 0 && Number(r.headers['retry-after']) <= 3600);
  h.clock.t += 3600 * 1000;
  assert.equal((await h.run('/api/v1/buildings?cell=12676,3755')).status, 200);
});
