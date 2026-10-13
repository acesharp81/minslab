/* api/bus.js — 버스 위치 중계. 네트워크 없이 가짜 fetch 로 시험한다. */
const test = require('node:test');
const assert = require('node:assert/strict');
const bus = require('../../handlers/bus.js');
const { createKeyPool, memoryStore } = require('../../lib/keys.js');
const { createCache } = require('../../lib/cache.js');

const KEY = 'fake+data/go==KEY';
const live = { city: 23, routes: ['R87', 'R584'] };
const item = (v, lon, lat, ord, nm) => ({ vehicleno: v, gpslong: lon, gpslati: lat, nodeord: ord, nodenm: nm, routenm: 87 });
const ok = (items) => ({ response: { header: { resultCode: '00' }, body: { items: items === '' ? '' : { item: items }, totalCount: 0 } } });
const resp = (json, status = 200) => ({ ok: status === 200, status, json: async () => json, text: async () => (typeof json === 'string' ? json : JSON.stringify(json)) });

function harness(over = {}) {
  const calls = [];
  const clock = { t: 1_000_000 };
  const fetchImpl = over.fetch || (async () => resp(ok([item('인천73아1091', '126.7', 37.5, 7, '가정류장')])));
  const env = over.env || { DATA_GO_KR_KEY: KEY };
  const now = () => clock.t;
  const pool = createKeyPool({ env, now, store: memoryStore() });
  const handler = bus.createHandler({
    fetch: async (url, opts) => { calls.push(url); return fetchImpl(url, opts); },
    env, now, pool, cache: createCache({ persist: false, now }),
    readLiveRoutes: over.readLiveRoutes || ((slug) => (slug === 'incheon-gyeyang' ? live : null)),
    sleep: async () => {},
  });
  const run = async (url, method = 'GET') => {
    const res = { headers: {}, statusCode: 0, body: '', setHeader(k, v) { this.headers[k.toLowerCase()] = v; }, end(b) { this.body = b; } };
    await handler({ method, url }, res);
    return { status: res.statusCode, headers: res.headers, json: res.body ? JSON.parse(res.body) : null };
  };
  return { run, calls, clock, pool };
}

test('ttl: 노선이 적어도 60초, 많아지면 하루 예산에 맞춰 늘어난다', () => {
  assert.equal(bus.ttlFor(0), 60);
  assert.equal(bus.ttlFor(4), 60);
  assert.equal(bus.ttlFor(7), 76);     // 7 × 86400 / 8000 = 75.6
  assert.equal(bus.ttlFor(10), 108);
  for (const n of [1, 4, 7, 20, 50]) assert.ok(n * 86400 / bus.ttlFor(n) <= bus.DAILY_BUDGET + n, `노선 ${n}개`);
});

test('normalize: 문자열 좌표를 읽고, 좌표가 없거나 범위 밖이거나 차량번호가 없는 행은 뺀다', () => {
  const out = bus.normalize('R87', ok([item('가1', '126.7123456789', '37.5', '7', '정류장'), item('가2', '', '', 3, 'x'), item('가3', 10, 37.5, 1, 'x'), { gpslong: 126.7, gpslati: 37.5 }, item('가5', 126.8, 37.6, 'x', '')]));
  assert.deepEqual(out.map((b) => b.v), ['가1', '가5']);
  assert.deepEqual(out[0], { r: 'R87', v: '가1', lon: 126.712346, lat: 37.5, ord: 7, stop: '정류장' });
  assert.equal(out[1].ord, null);
  assert.deepEqual(bus.normalize('R', ok('')), []);                                // 운행 차량이 없으면 items 가 빈 문자열
  assert.equal(bus.normalize('R', ok(item('단일', 126.7, 37.5, 1, 'a'))).length, 1);   // item 이 목록이 아닌 한 건일 때
});

test('성공: 노선마다 한 번씩만 부르고, 키는 URL 인코딩해서 보내며, CDN 캐시 시간을 ttl 로 준다', async () => {
  const h = harness();
  const r = await h.run('/api/bus?region=incheon-gyeyang');
  assert.equal(r.status, 200);
  assert.equal(h.calls.length, 2);
  for (const u of h.calls) {
    assert.ok(u.includes('serviceKey=fake%2Bdata%2Fgo%3D%3DKEY'), u);             // + / = 가 그대로면 승인된 키도 거절된다
    assert.ok(!u.includes(KEY));
    assert.ok(u.includes('cityCode=23'));
  }
  assert.ok(h.calls[0].includes('routeId=R87') && h.calls[1].includes('routeId=R584'));
  assert.equal(r.headers['cache-control'], 'public, s-maxage=60, stale-while-revalidate=60');
  assert.equal(r.json.ttl, 60);
  assert.equal(r.json.buses.length, 2);
  assert.equal(r.json.at, new Date(1_000_000).toISOString());
  assert.ok(!JSON.stringify(r.json).includes('KEY'));
});

test('로컬 캐시: ttl(60초) 안에 다시 오면 TAGO 를 다시 부르지 않고, 남은 시간만큼만 CDN 에 맡긴다', async () => {
  const h = harness();
  const first = await h.run('/api/bus?region=incheon-gyeyang');
  assert.equal(first.headers['cache-control'], 'public, s-maxage=60, stale-while-revalidate=60');
  h.clock.t += 29_000;
  const again = await h.run('/api/bus?region=incheon-gyeyang');
  assert.equal(h.calls.length, 2);
  assert.equal(again.headers['cache-control'], 'public, s-maxage=31, stale-while-revalidate=60');   // 이미 29초 묵었다
  assert.deepEqual(again.json, first.json);
  h.clock.t += 30_000;
  await h.run('/api/bus?region=incheon-gyeyang');
  assert.equal(h.calls.length, 2);                                                // 59초
  h.clock.t += 2_000;
  await h.run('/api/bus?region=incheon-gyeyang');
  assert.equal(h.calls.length, 4);                                                // 61초: 만료
});

test('요청이 노선을 정하지 못한다: 모르는 지역·추가 쿼리·형식 위반은 TAGO 를 부르지 않고 거절한다', async () => {
  const h = harness();
  for (const [url, status] of [['/api/bus', 400], ['/api/bus?region=incheon-gyeyang&x=1', 400], ['/api/bus?region=incheon-gyeyang&region=a', 400], ['/api/bus?routeId=R1', 400],
    ['/api/bus?region=../etc', 400], ['/api/bus?region=UPPER', 400], ['/api/bus?region=jeonnam-naju', 404]]) {
    const r = await h.run(url);
    assert.equal(r.status, status, url);
  }
  assert.equal(h.calls.length, 0);
});

test('GET·HEAD 외 방식은 405, 키가 없으면 503 이고 캐시하지 않는다', async () => {
  assert.equal((await harness().run('/api/bus?region=incheon-gyeyang', 'POST')).status, 405);
  const r = await harness({ env: {} }).run('/api/bus?region=incheon-gyeyang');
  assert.equal(r.status, 503);
  assert.equal(r.headers['cache-control'], 'no-store');
});

test('키가 이미 URL 인코딩된 채로 들어와도 한 번만 디코딩해서 보낸다', async () => {
  const h = harness({ env: { DATA_GO_KR_KEY: 'fake%2Bdata%2Fgo%3D%3DKEY' } });
  await h.run('/api/bus?region=incheon-gyeyang');
  assert.ok(h.calls[0].includes('serviceKey=fake%2Bdata%2Fgo%3D%3DKEY'), h.calls[0]);
});

test('한 노선이 실패해도 나머지는 돌려주고 failed 에 적는다. 전부 실패하면 502 를 짧게만 캐시한다', async () => {
  const partial = harness({ fetch: async (url) => (url.includes('R584') ? resp({}, 500) : resp(ok([item('가', 126.7, 37.5, 1, 'a')]))) });
  const r = await partial.run('/api/bus?region=incheon-gyeyang');
  assert.equal(r.status, 200);
  assert.deepEqual(r.json.failed, ['R584']);
  assert.equal(r.json.buses.length, 1);
  const none = harness({ fetch: async () => { throw new Error('boom serviceKey=' + KEY); } });
  const r2 = await none.run('/api/bus?region=incheon-gyeyang');
  assert.equal(r2.status, 502);
  assert.equal(r2.headers['cache-control'], 'public, s-maxage=15');
  assert.deepEqual(r2.json, { error: 'upstream' });                              // 원인 문구(키가 섞일 수 있음)는 밖으로 내보내지 않는다
});

test('TAGO 가 동시 접속 가득(99)이면 한 번 다시 시도한다. 다른 오류 코드는 다시 시도하지 않는다', async () => {
  let n = 0;
  const busyOnce = harness({ fetch: async () => (n++ === 0 ? resp({ response: { header: { resultCode: '99' } } }) : resp(ok([item('가', 126.7, 37.5, 1, 'a')]))) });
  const r = await busyOnce.run('/api/bus?region=incheon-gyeyang');
  assert.equal(r.status, 200);
  assert.ok(n >= 3);                                                             // 두 노선 중 하나가 재시도했다
  let m = 0;
  const denied = harness({ readLiveRoutes: () => ({ city: 23, routes: ['R1'] }), fetch: async () => { m++; return resp({ response: { header: { resultCode: '30' } } }); } });
  assert.equal((await denied.run('/api/bus?region=incheon-gyeyang')).status, 502);
  assert.equal(m, 1);
});

test('실제 번들: 계양 infra.json 의 live 노선과 도시코드를 읽는다', () => {
  const real = require('../../handlers/bus.js').createHandler;
  assert.equal(typeof real, 'function');
  const fs = require('node:fs');
  const infra = JSON.parse(fs.readFileSync(require('node:path').join(__dirname, '../../regions/incheon-gyeyang/infra.json'), 'utf8'));
  const liveIds = infra.busRoutes.filter((r) => r.live).map((r) => r.id);
  assert.ok(liveIds.length >= 1 && infra.busCityCode === 23);
  assert.ok(bus.ttlFor(liveIds.length) >= 60);
});

const KEYS3 = { DATA_GO_KR_KEY_BUS_1: 'k1+a/b=', DATA_GO_KR_KEY_BUS_2: 'k2+a/b=', DATA_GO_KR_KEY_BUS_3: 'k3+a/b=' };
const keyOf = (url) => decodeURIComponent(new URL(url).searchParams.get('serviceKey'));

test('키 풀: BUS 키가 여러 개면 호출을 나눠 쓰고(가장 적게 쓴 키 우선), ttl 은 키 수만큼 짧아진다', async () => {
  const many = { city: 23, routes: ['R1', 'R2', 'R3', 'R4', 'R5', 'R6'] };
  const h = harness({ env: KEYS3, readLiveRoutes: () => many });
  const r = await h.run('/api/bus?region=incheon-gyeyang');
  assert.equal(r.status, 200);
  const used = {};
  for (const u of h.calls) used[keyOf(u)] = (used[keyOf(u)] || 0) + 1;
  assert.deepEqual(Object.values(used).sort(), [2, 2, 2]);                       // 6번을 세 키가 2번씩
  assert.equal(r.json.ttl, 60);                                                   // 6 × 86400 / 24000 = 21.6 → 최소 60초
  assert.equal(bus.ttlFor(10, 1), 108); assert.equal(bus.ttlFor(10, 3), 60); assert.equal(bus.ttlFor(40, 2), 216); assert.equal(bus.ttlFor(5, 0), 60);
});

test('키 풀: 한도 오류(resultCode 22, XML 본문, HTTP 429)를 받은 키는 쉬게 하고 다음 키로 다시 부른다', async () => {
  const quotaXml = '<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg><returnAuthMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR</returnAuthMsg><returnReasonCode>22</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>';
  const modes = [['json22', () => resp({ response: { header: { resultCode: '22' } } })], ['xml', () => resp(quotaXml)], ['429', () => resp({}, 429)]];
  for (const [name, bad] of modes) {
    const h = harness({ env: { DATA_GO_KR_KEY_BUS_1: 'k1', DATA_GO_KR_KEY_BUS_2: 'k2' }, readLiveRoutes: () => ({ city: 23, routes: ['R1'] }), fetch: async (url) => (keyOf(url) === 'k1' ? bad() : resp(ok([item('가', 126.7, 37.5, 1, 'a')]))) });
    const r = await h.run('/api/bus?region=incheon-gyeyang');
    assert.equal(r.status, 200, name);
    assert.deepEqual(h.calls.map(keyOf), ['k1', 'k2'], name);
    assert.equal(h.pool.usage().keys.BUS_1.tago.exhausted, true, name);
    h.clock.t += 61_000;                                                          // 캐시가 만료돼도 k1 은 그날 쉰다
    await h.run('/api/bus?region=incheon-gyeyang');
    assert.deepEqual(h.calls.map(keyOf), ['k1', 'k2', 'k2'], name);
  }
});

test('키 풀: 모든 키가 한도에 닿으면 429 + Retry-After(한국시간 자정까지), 캐시하지 않는다', async () => {
  const h = harness({ env: { DATA_GO_KR_KEY_BUS_1: 'k1' }, readLiveRoutes: () => ({ city: 23, routes: ['R1'] }), fetch: async () => resp({ response: { header: { resultCode: '22' } } }) });
  const r = await h.run('/api/bus?region=incheon-gyeyang');
  assert.equal(r.status, 429);
  assert.equal(r.json.error, 'keys-exhausted'); assert.ok(r.json.retryAfterSec > 0 && r.json.retryAfterSec <= 86400);
  assert.equal(r.headers['retry-after'], String(r.json.retryAfterSec)); assert.equal(r.headers['cache-control'], 'no-store');
  const before = h.calls.length;
  await h.run('/api/bus?region=incheon-gyeyang');
  assert.equal(h.calls.length, before);                                          // 쉬는 키는 다시 부르지 않는다
});

test('키 풀: 응답·캐시·사용 현황 어디에도 키 값이 나오지 않는다', async () => {
  const h = harness({ env: KEYS3 });
  const r = await h.run('/api/bus?region=incheon-gyeyang');
  const all = JSON.stringify([r, h.pool.usage()]);
  for (const v of Object.values(KEYS3)) assert.ok(!all.includes(v));
  assert.ok(all.includes('BUS_1'));
});

test('실패 직후 15초는 원천을 다시 부르지 않는다(502 를 짧게 캐시)', async () => {
  const h = harness({ readLiveRoutes: () => ({ city: 23, routes: ['R1'] }), fetch: async () => { throw new Error('down'); } });
  assert.equal((await h.run('/api/bus?region=incheon-gyeyang')).status, 502);
  const n = h.calls.length;
  h.clock.t += 14_000;
  assert.equal((await h.run('/api/bus?region=incheon-gyeyang')).status, 502);
  assert.equal(h.calls.length, n);
  h.clock.t += 2_000;
  await h.run('/api/bus?region=incheon-gyeyang');
  assert.ok(h.calls.length > n);
});

test('비밀: 로컬 캐시 파일과 사용량 파일(.cache 에 해당)에도 키 값이 남지 않는다', async () => {
  const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
  const { fileStore } = require('../../lib/keys.js');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'busapi-secret-'));
  const env = { DATA_GO_KR_KEY_BUS_1: 'sEcRet+one/=', DATA_GO_KR_KEY_BUS_2: 'sEcRet+two/=' };
  const clock = { t: 5_000_000 }, now = () => clock.t;
  const handler = bus.createHandler({
    fetch: async () => resp(ok([item('가', 126.7, 37.5, 1, 'a')])), env, now, sleep: async () => {}, readLiveRoutes: () => live,
    pool: createKeyPool({ env, now, store: fileStore(path.join(dir, 'key-usage.json')) }), cache: createCache({ dir, now }),
  });
  const res = { headers: {}, setHeader() {}, end(b) { this.body = b; } };
  await handler({ method: 'GET', url: '/api/bus?region=incheon-gyeyang' }, res);
  const files = fs.readdirSync(dir);
  assert.ok(files.includes('key-usage.json') && files.length >= 2);
  for (const f of files) {
    const text = fs.readFileSync(path.join(dir, f), 'utf8');
    for (const v of Object.values(env)) for (const form of [v, encodeURIComponent(v)]) assert.ok(!text.includes(form), f);
  }
  assert.ok(!res.body.includes('sEcRet'));
  assert.ok(fs.readFileSync(path.join(dir, 'key-usage.json'), 'utf8').includes('BUS_'));   // 라벨만
  fs.rmSync(dir, { recursive: true, force: true });
});
