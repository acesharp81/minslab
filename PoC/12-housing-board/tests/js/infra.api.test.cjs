'use strict';
/* lib/infra.js · api/v1/infra.js — 요청 시 조회용 신설예정 학교·버스 정류장. 네트워크 없이 가짜 fetch 로 시험한다. */
const test = require('node:test');
const assert = require('node:assert/strict');
const { createCache } = require('../../lib/cache.js');
const { createKeyPool, memoryStore } = require('../../lib/keys.js');
const I = require('../../lib/infra.js');
const api = require('../../handlers/v1/infra.js');

/* ---------- lib/infra.js ---------- */
const row = (over) => Object.assign({ schlSeq: 51, schlNm: '(가칭)덕풍초', ditcNm: '초', openSchdYm: '202903', classCnt: '44', stdtCnt: '1113', realAddr: '경기도 하남시 덕풍동 1 일원', pointX: '37.5400', pointY: '127.2000' }, over);

test('scheduledSchools: 번들 infra.js 와 같은 모양(초·중·고·특수 학교급, 년월, 학급·학생, 좌표 pointX=위도), 가까운 것만, 개교 빠른 순', () => {
  const centers = [[127.2005, 37.5402]];
  const { schools, skipped } = I.scheduledSchools([
    row(), row({ schlSeq: 52, schlNm: '(가칭)가중', ditcNm: '중', openSchdYm: '202803', classCnt: '', stdtCnt: null }),
    row({ schlSeq: 53, schlNm: '멀리', pointX: '37.6', pointY: '127.3' }), row({ schlSeq: 54, ditcNm: '유치원' }), row({ schlSeq: 55, openSchdYm: '2029' }), row({ schlSeq: 56, pointX: '99', pointY: '999' }),
  ], centers);
  assert.deepEqual(skipped, { level: 1, ym: 1, point: 1 });
  assert.deepEqual(schools.map((s) => s.name), ['(가칭)가중', '(가칭)덕풍초']);
  assert.deepEqual(schools[1], { id: 'edu-51', name: '(가칭)덕풍초', level: '초등학교', status: '신설예정', openYm: '2029-03', classes: 44, students: 1113, address: '경기도 하남시 덕풍동 1 일원', lon: 127.2, lat: 37.54, sources: ['edu-newschool'] });
  assert.equal('classes' in schools[0], false); assert.equal('students' in schools[0], false);
  assert.deepEqual(I.scheduledSchools(null, centers).schools, []);
});

test('tagoStop·queryCenters·centerOf: 정류소 변환, 150 m 안 중심은 건너뜀, 폴리곤 중심', () => {
  assert.deepEqual(I.tagoStop({ nodeid: 'BSB1', nodenm: '해운대구청', nodeno: 12345, gpslati: '35.1631', gpslong: '129.1639' }), { id: 'BSB1', name: '해운대구청', lon: 129.1639, lat: 35.1631, no: '12345' });
  assert.equal('no' in I.tagoStop({ nodeid: 'X', nodenm: 'y', gpslati: 35, gpslong: 129 }), false);
  for (const bad of [{ nodenm: 'a', gpslati: 35, gpslong: 129 }, { nodeid: 'a', gpslati: 35, gpslong: 129 }, { nodeid: 'a', nodenm: 'b', gpslati: 1, gpslong: 1 }]) assert.equal(I.tagoStop(bad), null);
  const near = [127.2, 37.54], also = [127.2008, 37.5401], far = [127.205, 37.54];                              // also 는 약 70 m, far 는 약 440 m
  assert.deepEqual(I.queryCenters([near, also, far]), [near, far]);
  assert.equal(I.queryCenters(Array.from({ length: 100 }, (_, i) => [127 + i * 0.01, 37.5])).length, 40);
  assert.deepEqual(I.centerOf({ type: 'Polygon', coordinates: [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]] }), [1, 1]);
  assert.equal(I.centerOf(null), null); assert.equal(I.centerOf({ type: 'Point', coordinates: [1, 1] }), null);
  assert.ok(Math.abs(I.distM([127, 37.5], [127, 37.51]) - 1111.9) < 2);
});

/* ---------- api/v1/infra.js ---------- */
const BJD = '4145010800';
const rec = (over) => Object.assign({ sigunguCd: '41450', bjdongCd: '10800', bun: '0569', ji: '0000', platGbCd: '0', purpsCdNm: '공동주택', totHhldCnt: 100, bldNm: '덕풍아파트', mgmHsrgstPk: 1, apprvDay: '20240101', stcnsDay: '20240601', useInsptDay: '', mainBldCnt: 3, platPlc: '경기도 하남시 덕풍동 569번지' }, over);
const SQ = (x, y, d = 0.0003) => ({ type: 'Polygon', coordinates: [[[x, y], [x + d, y], [x + d, y + d], [x, y + d], [x, y]]] });
const ok = (json) => ({ ok: true, status: 200, json: async () => json, text: async () => JSON.stringify(json) });
const raw = (status, text) => ({ ok: status < 400, status, json: async () => JSON.parse(text), text: async () => text });
const hub = (items) => ({ response: { header: { resultCode: '00' }, body: { items: { item: items }, totalCount: items.length } } });
const tago = (items) => ({ response: { header: { resultCode: '00' }, body: { items: items.length ? { item: items } : '', totalCount: items.length } } });
const vw = (g) => ({ response: { status: 'OK', result: { featureCollection: { features: [{ geometry: g }] } } } });
const host = (url) => new URL(url).hostname;
const seoulNone = () => ok({ msgHeader: { headerCd: '4', headerMsg: '결과가 없습니다.', itemCount: 0 }, msgBody: { itemList: null } });
const seoulItems = (items) => ok({ msgHeader: { headerCd: '0', headerMsg: '정상적으로 처리되었습니다.', itemCount: items.length }, msgBody: { itemList: items } });

function defaultFetch(url, init) {
  const u = new URL(url);
  if (u.hostname === 'ws.bus.go.kr') return seoulNone();                                                                  // 서울시 정류소 API: 기본은 결과 없음
  if (u.hostname.startsWith('overpass')) return ok({ elements: [] });                                                   // OpenStreetMap 보조: 기본은 정류장 없음
  if (u.hostname === 'eduinfo.go.kr') return ok({ result: [row(), row({ schlSeq: 90, schlNm: '(가칭)먼곳', pointX: '36', pointY: '128' })] });
  if (u.hostname === 'api.vworld.kr') { const pnu = /pnu:=:(\d+)/.exec(u.searchParams.get('attrFilter'))[1]; return ok(vw(pnu.endsWith('05690000') ? SQ(127.2, 37.54) : SQ(127.206, 37.54))); }
  if (u.pathname.includes('HsPmsHubService')) return ok(hub([rec(), rec({ mgmHsrgstPk: 2, bun: '0570', bldNm: '다른단지', totHhldCnt: 50, stcnsDay: '' })]));
  if (u.pathname.includes('getCrdntPrxmtSttnList')) {
    const lon = Number(u.searchParams.get('gpsLong')), lat = Number(u.searchParams.get('gpsLati'));
    return ok(tago([{ nodeid: `S${Math.round(lon * 1000)}`, nodenm: `정류소${Math.round(lon * 1000)}`, nodeno: '123', gpslati: lat + 0.001, gpslong: lon + 0.001 }, { nodeid: 'FAR', nodenm: '먼정류소', gpslati: lat + 0.01, gpslong: lon + 0.01 }]));   // 약 140 m / 1.4 km
  }
  throw new Error('예상 밖 호출 ' + url);
}
function harness(over = {}) {
  const calls = [], clock = { t: Date.parse('2026-10-05T03:00:00Z') };
  const env = over.env || { DATA_GO_KR_KEY_RESOLVE_1: 'RES-KEY', DATA_GO_KR_KEY_BUS_1: 'BUS-KEY', VWORLD_KEY: 'VW-KEY', VWORLD_DOMAIN: 'localhost' };
  const now = () => clock.t;
  const handler = api.createHandler({
    env, now, sleep: async () => {}, cache: createCache({ persist: false, now }), pool: createKeyPool({ env, now, store: memoryStore() }),
    fetch: async (url, init) => { calls.push({ url, init }); return (over.fetch || defaultFetch)(url, init, calls.length); },
  });
  const run = async (url, method = 'GET') => {
    const res = { headers: {}, statusCode: 0, body: '', setHeader(k, v) { this.headers[k.toLowerCase()] = v; }, end(b) { this.body = b; } };
    await handler({ method, url }, res);
    return { status: res.statusCode, headers: res.headers, json: res.body ? JSON.parse(res.body) : null, raw: res.body };
  };
  return { run, calls, clock };
}

test('덕풍동: 인허가 단지 중심에서 가까운 신설예정 학교와 정류소를 번들 infra 모양으로(출처·기준일 포함, 먼 학교·먼 정류소 제외)', async () => {
  const h = harness();
  const r = await h.run(`/api/v1/infra?bjd=${BJD}`);
  assert.equal(r.status, 200); assert.equal(r.json.type, 'Infra'); assert.equal(r.json.bjd, BJD); assert.equal(r.json.asOf, '2026-10-05');
  assert.deepEqual(r.json.schools.map((s) => s.name), ['(가칭)덕풍초']); assert.equal(r.json.schools[0].openYm, '2029-03'); assert.equal(r.json.schools[0].level, '초등학교');
  assert.equal(r.json.stops.length, 2);                                                                            // 단지 2곳(중심 약 500 m 떨어짐)마다 1곳, 먼정류소 제외
  assert.deepEqual(Object.keys(r.json.stops[0]).sort(), ['id', 'lat', 'lon', 'name', 'no']);
  assert.deepEqual(r.json.sources.map((s) => s.id), ['edu-newschool', 'tago-bus']); assert.ok(r.json.sources.every((s) => s.redistributable && s.asOf === '2026-10-05'));
  const m = r.json.meta; assert.equal(m.centers, 2); assert.equal(m.schoolsNational, 2); assert.equal(m.schools, 1); assert.equal(m.stopCalls, 2); assert.equal(m.stops, 2);
  assert.equal(r.headers['cache-control'], 'public, s-maxage=86400, stale-while-revalidate=86400');
  const t = h.calls.map((c) => c.url).filter((u) => u.includes('getCrdntPrxmtSttnList')).map((u) => new URL(u));
  assert.equal(t[0].searchParams.get('serviceKey'), 'BUS-KEY'); assert.ok(Number(t[0].searchParams.get('gpsLati')) > 37.5);                              // 정류소는 BUS 용도 키
  const hubCall = h.calls.map((c) => c.url).find((u) => u.includes('HsPmsHubService')); assert.equal(new URL(hubCall).searchParams.get('serviceKey'), 'RES-KEY');   // 인허가는 RESOLVE 용도 키
  const edu = h.calls.find((c) => host(c.url) === 'eduinfo.go.kr'); assert.equal(edu.init.method, 'POST'); assert.match(edu.init.headers.Referer, /newSchMapPage/);
  assert.ok(!r.raw.includes('KEY'));
});

test('같은 법정동은 캐시에서(원천 호출 0), 24시간 뒤 만료. 인허가가 이미 캐시돼 있으면 건축HUB·필지를 다시 부르지 않는다', async () => {
  const h = harness();
  await h.run(`/api/v1/permits?bjd=${BJD}`.replace('/permits', '/infra'));
  const n = h.calls.length; await h.run(`/api/v1/infra?bjd=${BJD}`); assert.equal(h.calls.length, n);
  h.clock.t += 24 * 3600 * 1000 + 1; await h.run(`/api/v1/infra?bjd=${BJD}`); assert.ok(h.calls.length > n);
});

test('서울처럼 근접정류소가 0곳이면 meta.noBus, 학교는 그대로. 사업이 없으면 학교·정류소도 없고 외부 호출도 없다', async () => {
  const seoul = harness({ fetch: (url, init) => (new URL(url).pathname.includes('getCrdntPrxmtSttnList') ? ok(tago([])) : defaultFetch(url, init)) });
  const r = await seoul.run(`/api/v1/infra?bjd=${BJD}`);
  assert.equal(r.json.stops.length, 0); assert.equal(r.json.meta.noBus, true); assert.equal(r.json.schools.length, 1); assert.deepEqual(r.json.sources.map((s) => s.id), ['edu-newschool']);
  assert.equal(r.headers['cache-control'], 'public, s-maxage=86400, stale-while-revalidate=86400');
  const empty = harness({ fetch: (url, init) => (new URL(url).pathname.includes('HsPmsHubService') ? ok(hub([])) : defaultFetch(url, init)) });
  const e = await empty.run(`/api/v1/infra?bjd=${BJD}`);
  assert.deepEqual([e.json.schools, e.json.stops, e.json.meta.centers], [[], [], 0]);
  assert.equal(empty.calls.filter((c) => host(c.url) === 'eduinfo.go.kr' || c.url.includes('getCrdntPrxmtSttnList')).length, 0);
});

test('학교 또는 정류소 한쪽이 실패해도 나머지는 주고 짧게만 캐시한다. 인허가를 못 받으면 502, 키가 없으면 503', async () => {
  const noEdu = harness({ fetch: (url, init) => (host(url) === 'eduinfo.go.kr' ? raw(500, '') : defaultFetch(url, init)) });
  const a = await noEdu.run(`/api/v1/infra?bjd=${BJD}`);
  assert.equal(a.status, 200); assert.deepEqual(a.json.schools, []); assert.equal(a.json.meta.schoolsError, '신설예정 학교를 불러오지 못함'); assert.equal(a.json.stops.length, 2); assert.equal(a.headers['cache-control'], 'public, s-maxage=60');
  const noBus = harness({ fetch: (url, init) => (url.includes('getCrdntPrxmtSttnList') ? raw(500, '') : defaultFetch(url, init)) });
  const b = await noBus.run(`/api/v1/infra?bjd=${BJD}`);
  assert.equal(b.status, 200); assert.deepEqual(b.json.stops, []); assert.equal(b.json.meta.stopsError, '버스 정류소를 불러오지 못함'); assert.equal(b.json.schools.length, 1); assert.equal(b.json.meta.noBus, undefined);
  let firstLon = null;                                                                                                // 정류소 호출 둘 중 하나(첫 중심)만 계속 실패
  const partial = harness({ fetch: (url, init) => { if (!url.includes('getCrdntPrxmtSttnList')) return defaultFetch(url, init); const lon = new URL(url).searchParams.get('gpsLong'); if (firstLon === null) firstLon = lon; return lon === firstLon ? raw(500, '') : defaultFetch(url, init); } });
  const p = await partial.run(`/api/v1/infra?bjd=${BJD}`);
  assert.equal(p.status, 200); assert.equal(p.json.stops.length, 1); assert.equal(p.json.meta.stopsError, '정류소 조회 1곳을 불러오지 못해 일부만 보임'); assert.equal(p.headers['cache-control'], 'public, s-maxage=60');
  const noPermit = harness({ fetch: (url, init) => (url.includes('HsPmsHubService') ? raw(503, '') : defaultFetch(url, init)) });
  const c = await noPermit.run(`/api/v1/infra?bjd=${BJD}`); assert.equal(c.status, 502); assert.equal(c.headers['cache-control'], 'no-store');
  assert.equal((await harness({ env: {} }).run(`/api/v1/infra?bjd=${BJD}`)).status, 503);
  assert.equal((await harness({ env: { DATA_GO_KR_KEY: 'k' } }).run(`/api/v1/infra?bjd=${BJD}`)).status, 503);        // V-World 키 없음
});

test('정류소 한도 오류는 다음 BUS 키로, 시간당 상한을 넘으면 정류소만 비우고 알린다', async () => {
  const env = { DATA_GO_KR_KEY_RESOLVE_1: 'RES', DATA_GO_KR_KEY_BUS_1: 'B1', DATA_GO_KR_KEY_BUS_2: 'B2', VWORLD_KEY: 'v' };
  const q = harness({ env, fetch: (url, init) => { if (!url.includes('getCrdntPrxmtSttnList')) return defaultFetch(url, init); return new URL(url).searchParams.get('serviceKey') === 'B1' ? ok({ response: { header: { resultCode: '22' } } }) : defaultFetch(url, init); } });
  const r = await q.run(`/api/v1/infra?bjd=${BJD}`);
  assert.equal(r.status, 200); assert.equal(r.json.stops.length, 2); assert.ok(q.calls.some((c) => c.url.includes('serviceKey=B2')));
  const tight = harness({ env: { ...env, INFRA_UPSTREAM_PER_HOUR: '1' } });
  const t = await tight.run(`/api/v1/infra?bjd=${BJD}`);
  assert.equal(t.status, 200); assert.equal(t.json.stops.length, 1); assert.match(t.json.meta.stopsError, /시간당 정류소 조회 한도/); assert.equal(t.headers['cache-control'], 'public, s-maxage=60');
  const none = harness({ env: { DATA_GO_KR_KEY_RESOLVE_1: 'R', DATA_GO_KR_KEY_BUS_1: 'B1', VWORLD_KEY: 'v' }, fetch: (url, init) => (url.includes('getCrdntPrxmtSttnList') ? ok({ response: { header: { resultCode: '22' } } }) : defaultFetch(url, init)) });
  const n = await none.run(`/api/v1/infra?bjd=${BJD}`); assert.equal(n.status, 429); assert.equal(n.json.code, 'keys-exhausted');   // 정류소 키가 모두 소진
});

test('거절: 쿼리·법정동 형식·방식', async () => {
  const h = harness();
  for (const [url, status, code] of [['/api/v1/infra', 400, 'invalid-query'], [`/api/v1/infra?bjd=${BJD}&lat=1`, 400, 'invalid-query'], ['/api/v1/infra?lat=37&lon=127', 400, 'invalid-query'],
    ['/api/v1/infra?bjd=41450', 400, 'invalid-code'], ['/api/v1/infra?bjd=abc', 400, 'invalid-code']]) {
    const r = await h.run(url); assert.equal(r.status, status, url); assert.equal(r.json.code, code, url);
  }
  assert.equal((await h.run(`/api/v1/infra?bjd=${BJD}`, 'POST')).status, 405); assert.equal(h.calls.length, 0);
});

test('서울(시도 11)은 TAGO 를 부르지 않는다: 서울시 정류소도 OSM 도 0곳이면 noBus 로 알린다(학교는 그대로, 캐시도 정상)', async () => {
  const BJD11 = '1129013800';
  const h = harness({ fetch: (url, init) => {
    const u = new URL(url);
    if (u.pathname.includes('HsPmsHubService')) return ok(hub([rec({ sigunguCd: '11290', bjdongCd: '13800' })]));
    return defaultFetch(url, init);
  } });
  const r = await h.run(`/api/v1/infra?bjd=${BJD11}`);
  assert.equal(r.status, 200); assert.equal(r.json.meta.noBus, true); assert.equal(r.json.meta.stopCalls, 1); assert.deepEqual(r.json.stops, []);
  assert.equal(h.calls.filter((c) => c.url.includes('getCrdntPrxmtSttnList')).length, 0);
  assert.equal(h.calls.filter((c) => host(c.url) === 'ws.bus.go.kr').length, 1, '서울시 정류소 API 를 한 번 부른다');
  assert.equal(r.headers['cache-control'], 'public, s-maxage=86400, stale-while-revalidate=86400');
});

test('인허가를 CDN 에서 받는다(Vercel): 이 서버의 permits 공개 주소를 불러 건축HUB·V-World 를 다시 부르지 않고, 못 받으면 직접 만든다. 요청의 Host 헤더는 쓰지 않는다', async () => {
  const VERCEL = { DATA_GO_KR_KEY_RESOLVE_1: 'RES-KEY', DATA_GO_KR_KEY_BUS_1: 'BUS-KEY', VWORLD_KEY: 'VW-KEY', VERCEL: '1', VERCEL_ENV: 'production', VERCEL_PROJECT_PRODUCTION_URL: 'housing-board.example.app', VERCEL_URL: 'housing-board-abc.vercel.app' };
  const permitsBody = { type: 'FeatureCollection', bjd: BJD, features: [{ type: 'Feature', properties: { pnu: '4145010800105690000', name: 'a', label: 'a', status: '계획', units: 100, jibun: '569', records: 1 }, geometry: SQ(127.2, 37.54) }], meta: {} };
  const viaCdn = harness({ env: VERCEL, fetch: (url, init, n) => (host(url) === 'housing-board.example.app' ? ok(permitsBody) : defaultFetch(url, init, n)) });
  const a = await viaCdn.run(`/api/v1/infra?bjd=${BJD}`);
  assert.equal(a.status, 200); assert.equal(a.json.meta.centers, 1); assert.ok(a.json.stops.length > 0);
  const cdn = viaCdn.calls.filter((c) => host(c.url) === 'housing-board.example.app'); assert.equal(cdn.length, 1); assert.equal(cdn[0].url, `https://housing-board.example.app/api/v1/permits?bjd=${BJD}`);
  assert.equal(viaCdn.calls.filter((c) => c.url.includes('HsPmsHubService') || host(c.url) === 'api.vworld.kr').length, 0, '인허가를 다시 만들지 않는다');
  assert.ok(!/headers\.host|x-forwarded-host/i.test(require('node:fs').readFileSync(require('node:path').join(__dirname, '../../handlers/v1/infra.js'), 'utf8')), '요청의 Host 헤더를 주소에 쓰지 않는다');
  for (const down of [() => raw(500, ''), () => raw(401, '<html>보호됨</html>'), () => ok({ type: 'Other' }), () => ok({ ...permitsBody, bjd: '1111111111' })]) {
    const h = harness({ env: VERCEL, fetch: (url, init, n) => (host(url) === 'housing-board.example.app' ? down() : defaultFetch(url, init, n)) });
    const r = await h.run(`/api/v1/infra?bjd=${BJD}`); assert.equal(r.status, 200); assert.ok(r.json.meta.centers >= 1);                          // 못 받으면 직접 만들어 같은 결과
    assert.ok(h.calls.some((c) => c.url.includes('HsPmsHubService')), '직접 만든다');
  }
  const local = harness();                                                                                                                       // Vercel 이 아니면(로컬) 공개 주소를 부르지 않는다
  await local.run(`/api/v1/infra?bjd=${BJD}`); assert.ok(!local.calls.some((c) => /\/api\/v1\/permits/.test(c.url)));
  const preview = harness({ env: { ...VERCEL, VERCEL_ENV: 'preview' }, fetch: (url, init, n) => (host(url) === 'housing-board-abc.vercel.app' ? ok(permitsBody) : defaultFetch(url, init, n)) });
  await preview.run(`/api/v1/infra?bjd=${BJD}`); assert.equal(preview.calls.filter((c) => host(c.url) === 'housing-board-abc.vercel.app').length, 1);   // 미리보기는 배포 주소
});

const osmNode = (id, name, lon, lat, tags = {}) => ({ type: 'node', id, lon, lat, tags: { highway: 'bus_stop', ...(name ? { name } : {}), ...tags } });
const SEOUL_ENV = { DATA_GO_KR_KEY_RESOLVE_1: 'RES-KEY', DATA_GO_KR_KEY_BUS_1: 'BUS-KEY', VWORLD_KEY: 'VW-KEY' };
const seoulHub = (url, init, n, overpass) => {
  if (host(url).startsWith('overpass')) return overpass(url);
  if (url.includes('HsPmsHubService')) return ok(hub([rec({ sigunguCd: '11290', bjdongCd: '13800', platPlc: '서울특별시 성북구 장위동 569번지' })]));
  return defaultFetch(url, init, n);
};

test('OpenStreetMap 보조: 서울시 정류소가 0곳이면 Overpass 로 정류장을 받는다(이름 있는 것만, 반경 안만, 출처 osm-bus), TAGO 는 부르지 않는다. 인프라 응답은 24시간 캐시', async () => {
  const cx = 127.2, cy = 37.54;
  const elements = [osmNode(1, '장위동주민센터', cx + 0.001, cy + 0.001, { ref: '08123' }), osmNode(2, null, cx + 0.001, cy), osmNode(3, '먼정류장', cx + 0.02, cy + 0.02),
    osmNode(4, '플랫폼', cx, cy + 0.002, { highway: undefined, public_transport: 'platform', bus: 'yes' }), { type: 'way', id: 5, tags: { name: '길' } }, osmNode(1, '장위동주민센터', cx + 0.001, cy + 0.001)];
  const h = harness({ env: SEOUL_ENV, fetch: (url, init, n) => seoulHub(url, init, n, () => ok({ elements })) });
  const r = await h.run('/api/v1/infra?bjd=1129013800');
  assert.equal(r.status, 200); assert.equal(r.headers['cache-control'], 'public, s-maxage=86400, stale-while-revalidate=86400');
  assert.equal(r.json.meta.stopsSource, 'osm'); assert.equal(r.json.meta.noBus, undefined); assert.equal(r.json.meta.stopCalls, 1); assert.equal(r.json.meta.stops, 2);
  assert.deepEqual(r.json.stops.map((s) => s.name), ['장위동주민센터', '플랫폼']);                                                              // 이름 없음·멀리·way·중복은 뺌
  assert.deepEqual(r.json.stops.find((s) => s.name === '장위동주민센터'), { id: 'osm-1', name: '장위동주민센터', lon: 127.201, lat: 37.541, no: '08123' });
  assert.ok(r.json.sources.some((s) => s.id === 'osm-bus' && s.redistributable === 'Y' && /ODbL/.test(s.license))); assert.ok(!r.json.sources.some((s) => s.id === 'tago-bus'));
  assert.equal(h.calls.filter((c) => c.url.includes('getCrdntPrxmtSttnList')).length, 0);
  const ov = h.calls.filter((c) => host(c.url).startsWith('overpass')); assert.equal(ov.length, 2);                                               // 두 서버를 동시에
  assert.equal(ov[0].init.method, 'POST'); assert.match(ov[0].init.headers['User-Agent'], /housing-board/); assert.match(decodeURIComponent(ov[0].init.body), /bus_stop/);
  await h.run('/api/v1/infra?bjd=1129013800'); assert.equal(h.calls.filter((c) => host(c.url).startsWith('overpass')).length, 2);                // 같은 법정동은 캐시(공개 서버를 다시 부르지 않음)
});

test('OpenStreetMap 보조: 한 서버가 죽어도 다른 서버로, 둘 다 죽거나 모양이 다르면 정류장 없이(stopsError, 짧게만 캐시), TAGO 가 정류소를 주면 부르지 않는다', async () => {
  const mk = (overpass) => harness({ env: SEOUL_ENV, fetch: (url, init, n) => seoulHub(url, init, n, overpass) });
  const one = mk((url) => (host(url) === 'overpass-api.de' ? raw(504, '') : ok({ elements: [osmNode(7, '가까운정류장', 127.2005, 37.5405)] })));
  const a = await one.run('/api/v1/infra?bjd=1129013800'); assert.equal(a.json.meta.stopsSource, 'osm'); assert.equal(a.json.stops.length, 1); assert.equal(a.headers['cache-control'], 'public, s-maxage=86400, stale-while-revalidate=86400');
  const both = mk(() => raw(504, '')); const b = await both.run('/api/v1/infra?bjd=1129013800');
  assert.equal(b.status, 200); assert.equal(b.json.stops.length, 0); assert.equal(b.json.meta.stopsError, '버스 정류장(OpenStreetMap)을 불러오지 못함'); assert.equal(b.headers['cache-control'], 'public, s-maxage=60');
  const n0 = both.calls.filter((x) => host(x.url).startsWith('overpass')).length; assert.equal(n0, 2);
  await both.run('/api/v1/infra?bjd=1129013800'); assert.equal(both.calls.filter((x) => host(x.url).startsWith('overpass')).length, n0);   // 실패 뒤 2분은 공개 서버를 다시 두드리지 않는다
  both.clock.t += 2 * 60 * 1000 + 1; await both.run('/api/v1/infra?bjd=1129013800'); assert.equal(both.calls.filter((x) => host(x.url).startsWith('overpass')).length, n0 + 2);
  const bad = mk(() => ok({ nope: 1 })); assert.equal((await bad.run('/api/v1/infra?bjd=1129013800')).json.meta.stopsError, '버스 정류장(OpenStreetMap)을 불러오지 못함');
  const tagoCity = harness(); const c = await tagoCity.run(`/api/v1/infra?bjd=${BJD}`);                                                          // 하남: TAGO 가 정류소를 준다
  assert.equal(c.json.meta.stopsSource, 'tago'); assert.ok(c.json.stops.length > 0); assert.equal(tagoCity.calls.filter((x) => host(x.url).startsWith('overpass')).length, 0);
});

/* ---------- 서울시 정류소정보조회(lib/seoul.js) ---------- */
const seoulStn = (id, name, lon, lat, ars = '08123') => ({ stationId: String(id), stationNm: name, arsId: ars, gpsX: String(lon), gpsY: String(lat), dist: '10' });
const SEOUL_CALLS = (h) => h.calls.filter((c) => host(c.url) === 'ws.bus.go.kr');

test('서울시 정류소: 서울(시도 11)의 정류장을 서울시 API 로 받는다(http, tmX=경도 tmY=위도 radius 700, 반경 안만·중복·이상한 항목 제외, 출처 seoul-bus). TAGO·OSM 은 부르지 않고 24시간 캐시', async () => {
  const cx = 127.2, cy = 37.54;
  const items = [seoulStn(101, '장위동주민센터', cx + 0.001, cy + 0.001), seoulStn(102, '먼정류소', cx + 0.02, cy + 0.02), seoulStn(101, '장위동주민센터', cx + 0.001, cy + 0.001), seoulStn(103, '', cx, cy), seoulStn(104, '좌표없음', 'x', 'y'), seoulStn(105, '번호없음', cx, cy + 0.001, '0')];
  const h = harness({ env: SEOUL_ENV, fetch: (url, init, n) => (host(url) === 'ws.bus.go.kr' ? seoulItems(items) : seoulHub(url, init, n, () => { throw new Error('OSM 을 부르면 안 된다'); })) });
  const r = await h.run('/api/v1/infra?bjd=1129013800');
  assert.equal(r.status, 200); assert.equal(r.headers['cache-control'], 'public, s-maxage=86400, stale-while-revalidate=86400');
  assert.equal(r.json.meta.stopsSource, 'seoul'); assert.equal(r.json.meta.noBus, undefined); assert.equal(r.json.meta.stopCalls, 1); assert.equal(r.json.meta.stops, 2); assert.equal(r.json.meta.seoulError, undefined);
  assert.deepEqual(r.json.stops, [{ id: 'seoul-105', name: '번호없음', lon: 127.2, lat: 37.541 }, { id: 'seoul-101', name: '장위동주민센터', lon: 127.201, lat: 37.541, no: '08123' }].sort((a, b) => a.name.localeCompare(b.name, 'ko')));
  assert.deepEqual(r.json.sources.map((s) => s.id).sort(), ['edu-newschool', 'seoul-bus']); assert.equal(r.json.sources.find((s) => s.id === 'seoul-bus').publisher, '서울특별시');
  const c = SEOUL_CALLS(h)[0], u = new URL(c.url);
  assert.equal(u.protocol, 'http:', 'https 는 연결 시간 초과라 http'); assert.equal(u.pathname, '/api/rest/stationinfo/getStationByPos');
  assert.deepEqual([u.searchParams.get('tmX'), u.searchParams.get('tmY'), u.searchParams.get('radius'), u.searchParams.get('resultType')], ['127.200150', '37.540150', '700', 'json']);     // 단지 필지 윤곽의 중심(경도, 위도)
  assert.equal(u.searchParams.get('serviceKey'), 'BUS-KEY');
  assert.equal(h.calls.filter((x) => x.url.includes('getCrdntPrxmtSttnList') || host(x.url).startsWith('overpass')).length, 0);
  await h.run('/api/v1/infra?bjd=1129013800'); assert.equal(SEOUL_CALLS(h).length, 1);                                                          // 같은 법정동은 캐시
});

test('서울시 정류소: 중심은 300 m 간격으로 최대 12곳, 키 풀 서비스는 seoul, 한도 오류는 다음 키로·모두 소진이면 OSM 으로 물러나고 오늘은 서울시를 다시 부르지 않는다', async () => {
  const many = Array.from({ length: 30 }, (_, i) => rec({ mgmHsrgstPk: 100 + i, bun: String(600 + i).padStart(4, '0'), bldNm: `단지${i}`, sigunguCd: '11290', bjdongCd: '13800' }));
  const wide = (url, init, n) => {
    const u = new URL(url);
    if (u.pathname.includes('HsPmsHubService')) return ok(hub(many));
    if (u.hostname === 'api.vworld.kr') { const b = Number(/pnu:=:\d{11}\d(\d{4})/.exec(u.searchParams.get('attrFilter'))[1]); return ok(vw(SQ(127.2 + (b - 600) * 0.004, 37.54))); }   // 단지마다 약 350 m 떨어져 나란히
    return defaultFetch(url, init, n);
  };
  const h = harness({ env: SEOUL_ENV, fetch: (url, init, n) => (host(url) === 'ws.bus.go.kr' ? seoulItems([seoulStn(1, '가', 127.2, 37.54)]) : wide(url, init, n)) });
  const r = await h.run('/api/v1/infra?bjd=1129013800');
  assert.equal(r.status, 200); assert.equal(r.json.meta.centers, 30); assert.equal(r.json.meta.stopCalls, 12); assert.equal(SEOUL_CALLS(h).length, 12);

  const quota = '<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg><returnAuthMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR</returnAuthMsg><returnReasonCode>22</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>';
  const q = harness({ env: { ...SEOUL_ENV, DATA_GO_KR_KEY_BUS_2: 'BUS-KEY-2' }, fetch: (url, init, n) => {
    if (host(url) !== 'ws.bus.go.kr') return seoulHub(url, init, n, () => ok({ elements: [osmNode(9, '대체정류장', 127.2005, 37.5405)] }));
    return new URL(url).searchParams.get('serviceKey') === 'BUS-KEY' ? raw(200, quota) : seoulItems([seoulStn(7, '둘째키정류소', 127.2005, 37.5405)]);
  } });
  const a = await q.run('/api/v1/infra?bjd=1129013800'); assert.equal(a.json.meta.stopsSource, 'seoul'); assert.deepEqual(a.json.stops.map((s) => s.name), ['둘째키정류소']);
  assert.ok(SEOUL_CALLS(q).some((c) => new URL(c.url).searchParams.get('serviceKey') === 'BUS-KEY-2'));
  const dead = harness({ env: SEOUL_ENV, fetch: (url, init, n) => (host(url) === 'ws.bus.go.kr' ? raw(200, quota) : seoulHub(url, init, n, () => ok({ elements: [osmNode(9, '대체정류장', 127.2005, 37.5405)] }))) });
  const b = await dead.run('/api/v1/infra?bjd=1129013800');
  assert.equal(b.status, 200); assert.equal(b.json.meta.stopsSource, 'osm'); assert.equal(b.json.stops.length, 1); assert.equal(b.json.meta.seoulError, '서울시 정류소 조회 인증키 한도·설정 문제');
  assert.equal(b.headers['cache-control'], 'public, s-maxage=60', 'OSM 으로 물러났으면 짧게만 캐시');
  const n = SEOUL_CALLS(dead).length; dead.clock.t += 61 * 1000; await dead.run('/api/v1/infra?bjd=1129013800'); assert.equal(SEOUL_CALLS(dead).length, n, '키가 소진된 날은 서울시를 다시 부르지 않는다');
});

test('서울시 정류소: 실패(연결·5xx·모양 이상)는 OSM 으로 물러나고 짧게만 캐시, 일부만 실패하면 받은 것만 주고 알림, 시간당 상한(SEOUL_UPSTREAM_PER_HOUR)을 넘으면 부르지 않는다', async () => {
  const osm = () => ok({ elements: [osmNode(9, '대체정류장', 127.2005, 37.5405)] });
  for (const down of [() => { throw new Error('connect timeout'); }, () => raw(503, ''), () => raw(200, '<html>점검</html>'), () => ok({ msgHeader: { headerCd: '1', headerMsg: '시스템 에러' } })]) {
    const h = harness({ env: SEOUL_ENV, fetch: (url, init, n) => (host(url) === 'ws.bus.go.kr' ? down() : seoulHub(url, init, n, osm)) });
    const r = await h.run('/api/v1/infra?bjd=1129013800');
    assert.equal(r.status, 200); assert.equal(r.json.meta.stopsSource, 'osm'); assert.equal(r.json.meta.seoulError, '서울시 정류소를 불러오지 못함'); assert.equal(r.headers['cache-control'], 'public, s-maxage=60');
    assert.ok(!JSON.stringify(r.json).includes('BUS-KEY'), '키는 응답에 없다');
  }
  const two = [rec({ mgmHsrgstPk: 1, bun: '0569' }), rec({ mgmHsrgstPk: 2, bun: '0570', bldNm: '둘째' })].map((x) => ({ ...x, sigunguCd: '11290', bjdongCd: '13800' }));
  let calls = 0;
  const part = harness({ env: SEOUL_ENV, fetch: (url, init, n) => {
    const u = new URL(url);
    if (host(url) === 'ws.bus.go.kr') return ++calls === 1 ? seoulItems([seoulStn(1, '받은정류소', 127.2, 37.54)]) : raw(503, '');
    if (u.pathname.includes('HsPmsHubService')) return ok(hub(two));
    if (u.hostname === 'api.vworld.kr') { const pnu = /pnu:=:(\d+)/.exec(u.searchParams.get('attrFilter'))[1]; return ok(vw(SQ(pnu.endsWith('05690000') ? 127.2 : 127.206, 37.54))); }
    return defaultFetch(url, init, n);
  } });
  const p = await part.run('/api/v1/infra?bjd=1129013800');
  assert.equal(p.json.meta.stopCalls, 2); assert.equal(p.json.meta.stopsSource, 'seoul'); assert.deepEqual(p.json.stops.map((s) => s.name), ['받은정류소']);
  assert.equal(p.json.meta.seoulError, '서울시 정류소 조회 일부를 불러오지 못해 일부만 보임'); assert.equal(p.headers['cache-control'], 'public, s-maxage=60');

  const capped = harness({ env: { ...SEOUL_ENV, SEOUL_UPSTREAM_PER_HOUR: '1' }, fetch: (url, init, n) => (host(url) === 'ws.bus.go.kr' ? seoulItems([seoulStn(1, '가', 127.2, 37.54)]) : seoulHub(url, init, n, osm)) });
  const c = await capped.run('/api/v1/infra?bjd=1129013800');
  assert.equal(SEOUL_CALLS(capped).length, 1, '1건 상한 안에서 한 번'); assert.equal(c.json.meta.stopsSource, 'seoul');
  const capped2 = harness({ env: { ...SEOUL_ENV, SEOUL_UPSTREAM_PER_HOUR: '1' }, fetch: (url, init, n) => (host(url) === 'ws.bus.go.kr' ? seoulItems([seoulStn(1, '가', 127.2, 37.54)]) : seoulHub(url, init, n, osm)) });
  await capped2.run('/api/v1/infra?bjd=1129013800'); capped2.clock.t += 24 * 3600 * 1000 + 1;                                                   // 캐시가 만료된 다음 날에는 예산도 새로 시작
  const d = await capped2.run('/api/v1/infra?bjd=1129013800'); assert.equal(d.json.meta.stopsSource, 'seoul'); assert.equal(SEOUL_CALLS(capped2).length, 2);
});
