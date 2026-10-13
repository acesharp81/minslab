'use strict';
/* api/v1/codes/search.js — 글자(이름·지번·도로명)와 코드를 지도가 열 수 있는 후보로. 네트워크 없이 가짜 fetch 로 시험한다. */
const test = require('node:test');
const assert = require('node:assert/strict');
const { createCache } = require('../../lib/cache.js');
const { createKeyPool, memoryStore } = require('../../lib/keys.js');
const api = require('../../handlers/v1/codes/search.js');

const row = (region_cd, locatadd_nm, locallow_nm) => ({ region_cd, sido_cd: region_cd.slice(0, 2), sgg_cd: region_cd.slice(2, 5), umd_cd: region_cd.slice(5, 8), ri_cd: region_cd.slice(8, 10), locatadd_nm, locallow_nm });
const ROWS = [
  row('4145000000', '경기도 하남시', '하남시'), row('4145011400', '경기도 하남시 감일동', '감일동'), row('4145010800', '경기도 하남시 덕풍동', '덕풍동'),
  row('1129013800', '서울특별시 성북구 장위동', '장위동'), row('4373035027', '충청북도 옥천군 청산면 장위리', '장위리'),
  row('4145010600', '경기도 하남시 신장동', '신장동'), row('4131010300', '경기도 구리시 교문동', '교문동'), row('5115010100', '강원특별자치도 강릉시 홍제동', '홍제동'),
  row('2824500000', '인천광역시 계양구', '계양구'), row('2824510900', '인천광역시 계양구 박촌동', '박촌동'), row('4111100000', '경기도 수원시 장안구', '장안구'), row('4111111500', '경기도 수원시 장안구 파장동', '파장동'),
];
const stanJson = (rows) => (rows.length ? { StanReginCd: [{ head: [{ totalCount: rows.length }, { numOfRows: '100', pageNo: '1', type: 'JSON' }, { RESULT: { resultCode: 'INFO-0', resultMsg: 'NOMAL SERVICE' } }] }, { row: rows }] } : { RESULT: { resultCode: 'INFO-3', resultMsg: 'NO DATA' } });
const ok = (json) => ({ ok: true, status: 200, json: async () => json, text: async () => JSON.stringify(json) });
const raw = (status, text) => ({ ok: status < 400, status, json: async () => JSON.parse(text), text: async () => text });
const isStan = (url) => new URL(url).pathname.endsWith('/getStanReginCdList');
const isVw = (url) => new URL(url).hostname === 'api.vworld.kr';
const isPlace = (url) => isVw(url) && new URL(url).pathname === '/req/search';
const isAddr = (url) => isVw(url) && new URL(url).pathname === '/req/address';
const COV = { '28245': { slug: 'incheon-gyeyang', name: '인천 계양구' } };

const vwOk = (point, text, st) => ({ response: { status: 'OK', result: { point: { x: String(point[0]), y: String(point[1]) } }, refined: { text, structure: st } } });
const VW_NONE = { response: { status: 'NOT_FOUND' } };
const PARCELS = { '장위동 68-37': vwOk([127.053020, 37.612292], '서울특별시 성북구 장위동 68-37', { level1: '서울특별시', level2: '성북구', level3: '', level4L: '장위동', level4LC: '1129013800100680037', level4A: '', level5: '68-37' }) };
const ROADS = { '경기도 하남시 감일로15번길 78': vwOk([127.145460, 37.509897], '경기도 하남시 감일로15번길 78 (감일동)', { level1: '경기도', level2: '하남시', level3: '감일동', level4L: '감일로15번길', level4LC: '', level4A: '감일동', level4AC: '4145058200', level5: '78' }) };

const poi = (title, category, parcel, road, x, y) => ({ title, category, address: { parcel, road }, point: { x: String(x), y: String(y) } });
const placeResp = (items) => ({ response: { status: items.length ? 'OK' : 'NOT_FOUND', result: { items } } });
const PLACES = {
  '하남시청': () => [poi('하남시청', '지방행정기관', '경기도 하남시 신장동 520대', '경기도 하남시 대청로 10', 127.2145, 37.5392), poi('하남시청(덕풍신장)역입구', '진출입시설', '경기도 하남시 신장동 423-10대', '', 127.2067, 37.5422),
    poi('하남시청', '지방행정기관', '경기도 하남시 신장동 520대', '경기도 하남시 대청로 10', 127.21451, 37.53921), poi('하남시청', '건물 > 업무시설', '', '경기도 하남시 신장동 대청로 10-0', 127.2146, 37.5398),
    poi('하남시청역', '철도시설 > 철도/지하철 > 지하철역', '경기도 하남시 덕풍동 406-17', '', 127.2065, 37.5419)],
  '시청': (bbox) => (bbox ? [poi('구리시청', '지방행정기관 > 시청', '경기도 구리시 교문동 390-1', '경기도 구리시 아차산로 439', 127.1296, 37.5944), poi('하남시청', '지방행정기관 > 시청', '경기도 하남시 신장동 520대', '경기도 하남시 대청로 10', 127.2145, 37.5392)]
    : [poi('강릉시청', '지방행정기관 > 시청', '강원특별자치도 강릉시 홍제동 1001', '강원특별자치도 강릉시 강릉대로 33', 128.8758, 37.7522), poi('하남시청', '지방행정기관 > 시청', '경기도 하남시 신장동 520대', '경기도 하남시 대청로 10', 127.2145, 37.5392)]),
  '덕풍초등학교': () => [poi('덕풍초등학교', '중앙행정기관 > 교육부 > 초등학교', '경기도 하남시 덕풍동 360-14', '경기도 하남시 덕풍공원로 20', 127.1975, 37.5407)],
  '산 위의 집': () => [poi('산 위의 집', '음식점', '경기도 하남시 덕풍동 산 3-1', '', 127.2, 37.55)],
};
function defaultFetch(url) {
  const u = new URL(url);
  if (isStan(url)) {
    const nm = u.searchParams.get('locatadd_nm');
    if (nm) return ok(stanJson(ROWS.filter((r) => r.locatadd_nm.includes(nm))));
    return ok(stanJson(ROWS.filter((r) => r.sido_cd === u.searchParams.get('sido_cd') && r.sgg_cd === u.searchParams.get('sgg_cd'))));
  }
  if (isVw(url) && u.pathname === '/req/search') { const f = PLACES[u.searchParams.get('query')]; return ok(f ? placeResp(f(u.searchParams.get('bbox'))) : VW_NONE); }
  if (isVw(url)) { const a = u.searchParams.get('address'); return ok((u.searchParams.get('type') === 'PARCEL' ? PARCELS : ROADS)[a] || VW_NONE); }
  throw new Error(`예상 밖 호출 ${url}`);
}
function harness(over = {}) {
  const calls = [], clock = { t: Date.parse('2026-10-05T03:00:00Z') };
  const env = over.env || { DATA_GO_KR_KEY_RESOLVE_1: 'STAN-KEY-1', VWORLD_KEY: 'VW-OPERATING', VWORLD_DEV_KEY: 'VW-DEV', VWORLD_DOMAIN: 'localhost' };
  const now = () => clock.t;
  const svc = api.createService({ env, now, sleep: async () => {}, readCoverage: () => COV, cache: createCache({ persist: false, now }), pool: createKeyPool({ env, now, store: memoryStore() }), fetch: async (url) => { calls.push(url); return (over.fetch || defaultFetch)(url, calls.length); } });
  const handler = svc.handler;
  const run = async (url, method = 'GET') => {
    const res = { headers: {}, statusCode: 0, body: '', setHeader(k, v) { this.headers[k.toLowerCase()] = v; }, end(b) { this.body = b; } };
    await handler({ method, url }, res);
    return { status: res.statusCode, headers: res.headers, json: res.body ? JSON.parse(res.body) : null, raw: res.body };
  };
  const get = (q, extra = '') => run(`/api/v1/codes/search?q=${encodeURIComponent(q)}${extra}`);
  return { run, get, calls, clock, pool: svc.pool };
}
const brief = (r) => r.json.items.map((i) => [i.kind, i.code, i.tier]);

test('이름 검색: 법정동을 찾고(번들 없음=req), 숫자가 없으니 V-World 는 부르지 않는다. 키는 응답에 없다', async () => {
  const h = harness();
  const r = await h.get('감일');
  assert.equal(r.status, 200);
  assert.deepEqual(brief(r), [['bjd', '4145011400', 'req']]);
  assert.deepEqual(r.json.items[0].parts, { sido: '경기도', sgg: '하남시', umd: '감일동' }); assert.equal(r.json.items[0].name, '경기도 하남시 감일동');
  assert.equal(r.json.meta.count, 1); assert.deepEqual(r.json.meta.sources, ['행정표준코드', 'V-World 장소']); assert.equal(r.json.meta.q, '감일'); assert.equal(r.json.meta.partial, undefined);
  assert.equal(r.headers['cache-control'], 'public, s-maxage=3600, stale-while-revalidate=3600');
  assert.equal(h.calls.filter(isAddr).length, 0); assert.deepEqual(h.calls.filter(isPlace).map((c) => new URL(c).searchParams.get('type')), ['place']);   // 숫자가 없으니 주소 API 는 안 부르고 장소 검색만 한 번
  const st = new URL(h.calls.find(isStan)); assert.equal(st.searchParams.get('locatadd_nm'), '감일'); assert.equal(st.searchParams.get('serviceKey'), 'STAN-KEY-1');
  assert.ok(!r.raw.includes('KEY') && !r.raw.includes('VW-'));
});

test('이름 검색: 번들이 있는 시군구는 bundle, 번들 없는 시군구는 edge(경계만), 법정동·시군구·리 순서와 구 이름 구성', async () => {
  const h = harness();
  const g = await h.get('계양구'); assert.deepEqual(brief(g), [['sgg', '28245', 'bundle'], ['bjd', '2824510900', 'bundle']]);
  assert.deepEqual(g.json.items[0].parts, { sido: '인천광역시', sgg: '계양구' });
  const s = await h.get('하남시'); assert.deepEqual(brief(s), [['sgg', '41450', 'edge'], ['bjd', '4145011400', 'req'], ['bjd', '4145010800', 'req'], ['bjd', '4145010600', 'req']]);
  const j = await h.get('장위'); assert.deepEqual(brief(j), [['bjd', '1129013800', 'req'], ['bjd', '4373035027', 'req']]);   // 동이 리보다 앞
  assert.deepEqual(j.json.items[1].parts, { sido: '충청북도', sgg: '옥천군', umd: '청산면', ri: '장위리' });
  const w = await h.get('파장동'); assert.deepEqual(w.json.items[0].parts, { sido: '경기도', sgg: '수원시 장안구', umd: '파장동' });
  assert.deepEqual((await h.get('경기도')).json.items.map((i) => i.kind).filter((k) => k === 'sido'), []);                                    // 시도 행은 후보가 아니다
});

test('이름 검색: 시를 빼고 쳐도(하남 감일동) 가장 긴 낱말로 찾아 모든 낱말이 든 것만 남긴다. 결과가 없으면 빈 목록(오류 아님)', async () => {
  const h = harness();
  const r = await h.get('하남 감일동');
  assert.deepEqual(brief(r), [['bjd', '4145011400', 'req']]);
  assert.deepEqual(h.calls.filter(isStan).map((c) => new URL(c).searchParams.get('locatadd_nm')), ['하남 감일동', '감일동']);                                 // 전체 → 가장 긴 낱말
  const none = await h.get('없는곳이름');
  assert.equal(none.status, 200); assert.deepEqual(none.json.items, []); assert.equal(none.json.meta.count, 0);
});

test('지번: 필지(PNU)가 먼저이고 점 좌표가 붙으며 법정동 후보가 뒤따른다. V-World 는 PARCEL 한 번', async () => {
  const h = harness();
  const r = await h.get('장위동 68-37');
  assert.deepEqual(brief(r), [['pnu', '1129013800100680037', 'req'], ['bjd', '1129013800', 'req']]);
  assert.deepEqual(r.json.items[0].point, [127.05302, 37.612292]); assert.deepEqual(r.json.items[0].parts, { sido: '서울특별시', sgg: '성북구', umd: '장위동', jibun: '68-37' });
  assert.deepEqual(r.json.meta.sources, ['V-World 주소', '행정표준코드', 'V-World 장소']);
  const vw = h.calls.filter(isAddr); assert.equal(vw.length, 1);
  const u = new URL(vw[0]); assert.equal(u.searchParams.get('type'), 'PARCEL'); assert.equal(u.searchParams.get('address'), '장위동 68-37'); assert.equal(u.searchParams.get('service'), 'address');
  assert.equal(u.searchParams.get('key'), 'VW-DEV'); assert.equal(u.searchParams.get('domain'), 'localhost');                                   // 로컬은 개발키
  assert.equal(new URL(h.calls.find(isStan)).searchParams.get('locatadd_nm'), '장위동');                                                      // 숫자 낱말(지번)은 이름 검색에서 뺀다
});

test('도로명: 지번이 없으면 ROAD 로, 법정동 이름으로 표준코드를 찾아 법정동 + 좌표로 연다(법정동 후보와 따로 나옴)', async () => {
  const h = harness();
  const r = await h.get('경기도 하남시 감일로15번길 78');
  assert.deepEqual(brief(r), [['bjd', '4145011400', 'req']]);
  assert.equal(r.json.items[0].road, true); assert.deepEqual(r.json.items[0].point, [127.14546, 37.509897]); assert.equal(r.json.items[0].parts.road, '감일로15번길 78'); assert.equal(r.json.items[0].name, '경기도 하남시 감일로15번길 78 (감일동)');
  assert.deepEqual(h.calls.filter(isAddr).map((c) => new URL(c).searchParams.get('type')), ['PARCEL', 'ROAD']);
  const both = await h.get('하남시 감일동 100');                                                                                                // 지번도 도로명도 못 찾으면 법정동만
  assert.deepEqual(brief(both), [['bjd', '4145011400', 'req']]); assert.equal(both.json.items[0].road, undefined);
});

test('코드: 시군구 5·법정동 8/10·PNU 19자리는 표준코드 표에서 이름을 확인해 후보로, 틀린 코드는 이유와 함께 빈 목록', async () => {
  const h = harness();
  const a = await h.get('41450'); assert.deepEqual(brief(a), [['sgg', '41450', 'edge']]); assert.equal(a.json.items[0].name, '경기도 하남시');
  const b = await h.get('4145011400'); assert.deepEqual(brief(b), [['bjd', '4145011400', 'req']]);
  const c = await h.get('41450114'); assert.deepEqual(brief(c), [['bjd', '4145011400', 'req']]);                                               // 8자리는 00 보충
  const d = await h.get('41450-1140-0'); assert.deepEqual(brief(d), [['bjd', '4145011400', 'req']]);                                           // 하이픈·공백 허용
  const e = await h.get('1129013800100680037'); assert.deepEqual(brief(e), [['pnu', '1129013800100680037', 'req']]); assert.equal(e.json.items[0].name, '서울특별시 성북구 장위동 68-37'); assert.equal(e.json.items[0].parts.jibun, '68-37');
  const bad = await h.get('12345'); assert.deepEqual(bad.json.items, []); assert.equal(bad.json.meta.reason, 'unknown-code');
  const len = await h.get('1234567'); assert.equal(len.json.meta.reason, 'bad-length');
  const sido = await h.get('41'); assert.equal(sido.json.meta.reason, 'unsupported-level');
  const pnu0 = await h.get('1129013800100000000'); assert.equal(pnu0.json.meta.reason, 'bad-pnu');
  assert.equal(h.calls.filter(isVw).length, 0);                                                                                                // 코드는 V-World 를 부르지 않는다
});

test('캐시: 같은 검색을 또 하면 원천 호출이 없다(표준코드·주소 24시간), 하루 뒤에는 다시', async () => {
  const h = harness();
  await h.get('장위동 68-37'); const n = h.calls.length; assert.ok(n >= 2);
  await h.get('장위동 68-37'); assert.equal(h.calls.length, n);
  h.clock.t += 24 * 3600 * 1000 + 1;
  await h.get('장위동 68-37'); assert.ok(h.calls.length > n);
});

test('거절: 쿼리 이름·개수·길이·limit·방식. limit 으로 후보를 줄인다', async () => {
  const h = harness();
  for (const [url, code, reason] of [['/api/v1/codes/search', 'invalid-query'], ['/api/v1/codes/search?q=감일동&x=1', 'invalid-query'], ['/api/v1/codes/search?q=가&q=나', 'invalid-query'],
    ['/api/v1/codes/search?q=%EA%B0%80', 'invalid-query', 'too-short'], [`/api/v1/codes/search?q=${'가'.repeat(61)}`, 'invalid-query', 'too-long'],
    ['/api/v1/codes/search?q=감일동&limit=0', 'invalid-query'], ['/api/v1/codes/search?q=감일동&limit=21', 'invalid-query'], ['/api/v1/codes/search?q=감일동&limit=a', 'invalid-query'], ['/api/v1/codes/search?q=감일동&limit=2&limit=3', 'invalid-query']]) {
    const r = await h.run(url); assert.equal(r.status, 400, url); assert.equal(r.json.code, code, url); assert.equal(r.json.type, `/problems/${code}`); if (reason) assert.equal(r.json.reason, reason, url);
  }
  assert.equal((await h.run('/api/v1/codes/search?q=감일동', 'POST')).status, 405); assert.equal(h.calls.length, 0);
  assert.equal((await h.get('하남시', '&limit=2')).json.items.length, 2);
  assert.equal((await h.get('  하남시   감일동  ')).json.meta.q, '하남시 감일동');                                                                // 공백 정리
});

test('한쪽만 실패하면 나머지 후보를 주고 partial 에 적는다(짧게만 캐시): V-World 오류·시간당 상한·표준코드 오류', async () => {
  const vwDown = harness({ fetch: (url) => (isVw(url) ? raw(500, '') : defaultFetch(url)) });
  const a = await vwDown.get('장위동 68-37');
  assert.equal(a.status, 200); assert.deepEqual(brief(a), [['bjd', '1129013800', 'req']]); assert.deepEqual(a.json.meta.partial, ['vworld']); assert.equal(a.headers['cache-control'], 'public, s-maxage=60');
  const tight = harness({ env: { DATA_GO_KR_KEY_RESOLVE_1: 'k', VWORLD_KEY: 'v', SEARCH_UPSTREAM_PER_HOUR: '1' } });
  const b = await tight.get('장위동 68-37');                                                                                                     // PARCEL 1회는 되고
  assert.equal(b.json.items[0].kind, 'pnu');
  const c = await tight.get('덕풍동 788');                                                                                                        // 다음 주소 호출은 상한
  assert.deepEqual(c.json.meta.partial, ['budget']); assert.deepEqual(brief(c), [['bjd', '4145010800', 'req']]);
  const stanDown = harness({ fetch: (url) => (isStan(url) ? raw(503, '') : defaultFetch(url)) });
  const d = await stanDown.get('장위동 68-37');
  assert.equal(d.status, 200); assert.deepEqual(brief(d), [['pnu', '1129013800100680037', 'req']]); assert.deepEqual(d.json.meta.partial, ['stan']);
  const noVw = harness({ env: { DATA_GO_KR_KEY_RESOLVE_1: 'k' } });
  const e = await noVw.get('장위동 68-37'); assert.deepEqual(e.json.meta.partial, ['vworld-key']); assert.deepEqual(brief(e), [['bjd', '1129013800', 'req']]);
});

test('둘 다 실패하면 502(no-store), 키가 없으면 503, 한도 오류는 키 풀이 429', async () => {
  const dead = harness({ fetch: () => raw(500, '') });
  const a = await dead.get('장위동 68-37'); assert.equal(a.status, 502); assert.equal(a.json.code, 'upstream'); assert.equal(a.headers['cache-control'], 'no-store');
  const stanOnlyDead = harness({ fetch: () => raw(503, '') });
  assert.equal((await stanOnlyDead.get('감일')).status, 502);
  assert.equal((await harness({ env: {} }).get('감일')).status, 503);
  const quota = harness({ env: { DATA_GO_KR_KEY_RESOLVE_1: 'K1', VWORLD_KEY: 'v' }, fetch: () => ok({ response: { header: { resultCode: '22' } } }) });
  const q = await quota.get('감일'); assert.equal(q.status, 429); assert.equal(q.json.code, 'keys-exhausted'); assert.ok(Number(q.headers['retry-after']) > 0);
});

test('rowParts: 시도·시군구(구 포함)·읍면동·리 이름 구성', () => {
  assert.deepEqual(api.rowParts(row('4145011400', '경기도 하남시 감일동')), { sido: '경기도', sgg: '하남시', umd: '감일동' });
  assert.deepEqual(api.rowParts(row('4111100000', '경기도 수원시 장안구')), { sido: '경기도', sgg: '수원시 장안구' });
  assert.deepEqual(api.rowParts(row('4373035027', '충청북도 옥천군 청산면 장위리')), { sido: '충청북도', sgg: '옥천군', umd: '청산면', ri: '장위리' });
});

test('장소 이름: 지번이 있는 장소만 필지(PNU)+좌표로, 분류가 좋은 것(행정기관·역)이 앞이고 입구는 뒤, 같은 이름·같은 자리는 하나, 법정동은 이름당 한 번만 찾는다', async () => {
  const h = harness();
  const r = await h.get('하남시청');
  assert.equal(r.status, 200);
  assert.deepEqual(r.json.items.map((i) => [i.kind, i.code, i.name]), [['pnu', '4145010600105200000', '하남시청'], ['pnu', '4145010800104060017', '하남시청역'], ['pnu', '4145010600104230010', '하남시청(덕풍신장)역입구']]);   // 같은 필지 중복·지번 없는 건물 기록은 빠짐, 입구는 맨 뒤
  const a = r.json.items[0];
  assert.deepEqual([a.place, a.tier, a.category, a.addr, a.point], [true, 'req', '지방행정기관', '경기도 하남시 대청로 10', [127.2145, 37.5392]]);
  assert.deepEqual(a.parts, { sido: '경기도', sgg: '하남시', umd: '신장동', jibun: '520', place: '하남시청' });
  assert.equal(r.json.items[1].parts.jibun, '406-17'); assert.equal(r.json.items[2].parts.jibun, '423-10');
  assert.deepEqual(r.json.meta.sources, ['행정표준코드', 'V-World 장소']);
  const names = h.calls.filter(isStan).map((c) => new URL(c).searchParams.get('locatadd_nm')); assert.deepEqual(names.sort(), ['경기도 하남시 덕풍동', '경기도 하남시 신장동', '하남시청']);   // 이름 검색 1 + 법정동 2(신장동은 한 번만)
  assert.deepEqual(h.calls.filter(isPlace).map((c) => [new URL(c).searchParams.get('query'), new URL(c).searchParams.get('bbox')]), [['하남시청', null]]);      // near 가 없으면 전국 한 번
  const san = await h.get('산 위의 집'); assert.equal(san.json.items[0].code, '4145010800200030001'); assert.equal(san.json.items[0].parts.jibun, '산3-1');   // '산 3-1' 은 대지구분 2
});

test('장소 이름: near(지금 보는 지도 가운데)가 있으면 둘레 상자 안을 따로 찾아 가까운 것을 앞에 둔다(시청 → 하남시청이 구리·강릉보다 앞). near 형식 거절', async () => {
  const h = harness();
  const r = await h.get('시청', '&near=127.17,37.55');
  assert.deepEqual(r.json.items.map((i) => i.name), ['하남시청', '구리시청', '강릉시청']);
  const bb = h.calls.filter(isPlace).map((c) => new URL(c).searchParams.get('bbox')).sort((a, b) => String(a).localeCompare(String(b)));
  assert.deepEqual(bb, ['126.89,37.33,127.45,37.77', null]);                                                                                   // 둘레 상자 호출 1 + 상자 없는 전국 호출 1
  const far = await harness().get('시청'); assert.deepEqual(far.json.items.map((i) => i.name), ['강릉시청', '하남시청']);                          // near 가 없으면 V-World 순서
  for (const bad of ['&near=abc', '&near=127.17', '&near=10,37', '&near=127.17,60', '&near=127.1,37.5&near=127.2,37.6']) { const x = await harness().get('시청', bad); assert.equal(x.status, 400, bad); assert.equal(x.json.code, 'invalid-query'); }
});

test('장소 검색 실패는 이름 후보를 막지 않는다(partial vworld), 표준코드 초당 한도(429 PER_SECOND)는 쉬었다 다시 부르고 키를 하루 쉬게 하지 않는다', async () => {
  const placeDown = harness({ fetch: (url) => (isPlace(url) ? raw(500, '') : defaultFetch(url)) });
  const a = await placeDown.get('감일'); assert.equal(a.status, 200); assert.deepEqual(brief(a), [['bjd', '4145011400', 'req']]); assert.deepEqual(a.json.meta.partial, ['vworld']); assert.equal(a.headers['cache-control'], 'public, s-maxage=60');
  const perSec = raw(429, JSON.stringify({ OpenAPI_ServiceResponse: { cmmMsgHeader: { errMsg: 'SERVICE ERROR', returnAuthMsg: 'LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR', returnReasonCode: '22' } } }));
  let n = 0; const flaky = harness({ fetch: (url) => (isStan(url) && n++ < 2 ? perSec : defaultFetch(url)) });
  const b = await flaky.get('감일'); assert.equal(b.status, 200); assert.deepEqual(brief(b), [['bjd', '4145011400', 'req']]);                         // 두 번 막혔다가 성공
  assert.equal(Object.values(flaky.pool.usage().keys)[0].stan.exhausted, false);
  const always = harness({ fetch: (url) => (isStan(url) ? perSec : defaultFetch(url)) });
  const c = await always.get('감일'); assert.equal(c.status, 502);                                                                                 // 계속 막히면 줄 것이 없어 502
  assert.equal(Object.values(always.pool.usage().keys)[0].stan.exhausted, false);                                                              // 초당 한도는 하루 소진이 아니다
  const daily = harness({ fetch: (url) => (isStan(url) ? raw(429, '') : defaultFetch(url)) });
  assert.equal((await daily.get('감일')).status, 429);                                                                                         // 본문 없는 429 는 하루 한도
});

test('장소 이름 순위: 같은 필지는 앞선 하나만(단지와 그 동들), 중앙행정기관(기상관측소·학교)은 지방행정기관보다 뒤, 세 글자 이상은 이름이 그 글자로 시작하는 것이 앞', async () => {
  const many = { '감일스윗시티': () => [poi('감일스윗시티10단지', '시설구역경계 > 아파트단지', '경기도 하남시 덕풍동 360-14', '', 127.16, 37.5), poi('감일스윗시티10단지/1001동', '건물 > 주거용공동주택', '경기도 하남시 덕풍동 360-14', '', 127.1601, 37.5001),
      poi('감일스윗시티12단지', '시설구역경계 > 아파트단지', '경기도 하남시 감일동 100', '', 127.162, 37.503)],
    '시청': () => [poi('시청', '중앙행정기관 > 기상청 > 기상관측소', '경기도 하남시 신장동 27', '', 127.2194, 37.5471), poi('경기도하남시청', '지방행정기관 > 시청', '경기도 하남시 신장동 520대', '', 127.2147, 37.5391)],
    '미사역': () => [poi('작심스터디카페미사역점', '기타도서관 > 독서실/스터디카페', '경기도 하남시 덕풍동 360-21', '', 127.19, 37.56), poi('미사역', '철도시설 > 철도/지하철 > 지하철역', '경기도 하남시 덕풍동 406-17', '', 127.1929, 37.5631)] };
  const h = harness({ fetch: (url) => { if (isPlace(url)) { const f = many[new URL(url).searchParams.get('query')]; if (f) return ok(placeResp(f())); } return defaultFetch(url); } });
  const a = await h.get('감일스윗시티'); assert.deepEqual(a.json.items.filter((i) => i.place).map((i) => i.name), ['감일스윗시티10단지', '감일스윗시티12단지']);                // 1001동은 같은 필지라 빠짐
  const b = await h.get('시청'); assert.deepEqual(b.json.items.map((i) => i.name), ['경기도하남시청', '시청']);                                                                          // 지방행정기관 > 기상관측소
  const c = await h.get('미사역', '&near=127.19,37.56'); assert.deepEqual(c.json.items.map((i) => i.name), ['미사역', '작심스터디카페미사역점']);                                       // 지하철역 먼저(둘 다 '미사역' 시작이 아니어도 분류가 앞)
});

test('장소 이름 순위: 지번 주소로 찾은 필지와 같은 필지의 장소는 빼고, 아파트 동(/601동) 단위 기록은 단지·다른 장소보다 뒤', async () => {
  const sameParcel = { '장위동 68-37': () => [poi('가로변안전비상벨', '공공시설', '서울특별시 성북구 장위동 68-37', '', 127.0531, 37.6123), poi('장위동 주민센터', '지방행정기관 > 주민센터', '서울특별시 성북구 장위동 98-1', '', 127.0544, 37.6124)],
    '감일아파트': () => [poi('감일아파트/101동', '건물 > 주거용공동주택', '경기도 하남시 감일동 7-1', '', 127.17, 37.5), poi('감일아파트', '시설구역경계 > 아파트단지', '경기도 하남시 감일동 8', '', 127.17, 37.51), poi('감일마트', '소매업', '경기도 하남시 감일동 9', '', 127.17, 37.52)] };
  const h = harness({ fetch: (url) => { if (isPlace(url)) { const f = sameParcel[new URL(url).searchParams.get('query')]; if (f) return ok(placeResp(f())); } return defaultFetch(url); } });
  const a = await h.get('장위동 68-37');
  assert.deepEqual(a.json.items.map((i) => [i.kind, i.name]), [['pnu', '서울특별시 성북구 장위동 68-37'], ['bjd', '서울특별시 성북구 장위동'], ['pnu', '장위동 주민센터']]);   // 같은 필지의 안전비상벨은 빠짐
  const b = await h.get('감일아파트');
  assert.deepEqual(b.json.items.filter((i) => i.place).map((i) => i.name), ['감일아파트', '감일아파트/101동', '감일마트']);                                  // 동 기록은 단지 뒤, 가게(소매업)는 맨 뒤
});

test('장소 이름 순위: 이름이 입력과 같은 것이 그 글자로 시작하는 것(하남시청역)보다 앞이고, near 가 더 가까워도 뒤집히지 않는다', async () => {
  const h = harness({ fetch: (url) => { if (isPlace(url) && new URL(url).searchParams.get('query') === '하남시청') return ok(placeResp([poi('하남시청역', '철도시설 > 철도/지하철 > 지하철역', '경기도 하남시 덕풍동 406-17', '', 127.2065, 37.5419), poi('하남시청', '지방행정기관', '경기도 하남시 신장동 520대', '경기도 하남시 대청로 10', 127.2145, 37.5392)])); return defaultFetch(url); } });
  const r = await h.get('하남시청', '&near=127.2,37.54'); assert.deepEqual(r.json.items.map((i) => i.name), ['하남시청', '하남시청역']);                 // 역이 더 가까워도 이름이 같은 시청이 먼저
});

test('이름 검색: 시에 구가 새로 생겨 낱말이 이어지지 않아도(화성시 오산동 → 화성시 동탄구 오산동) 동·읍·면 낱말로 찾아 나머지 낱말이 든 행만 남긴다(앞쪽 100행에 밀리지 않음)', async () => {
  const filler = Array.from({ length: 150 }, (_, i) => row(`4159${String(100000 + i).padStart(6, '0')}`.slice(0, 10), `경기도 화성시 만세구 가나${i}동`, `가나${i}동`));
  const rows = [...filler, row('4159310900', '경기도 화성시 동탄구 오산동', '오산동'), row('4137010100', '경기도 오산시 오산동', '오산동')];
  const h = harness({ fetch: (url) => { if (isStan(url)) { const nm = new URL(url).searchParams.get('locatadd_nm'); return ok(stanJson(rows.filter((r) => r.locatadd_nm.includes(nm)).slice(0, 100))); } return defaultFetch(url); } });
  const r = await h.get('화성시 오산동'); assert.deepEqual(r.json.items.map((i) => i.name), ['경기도 화성시 동탄구 오산동']);
  assert.deepEqual(h.calls.filter(isStan).map((c) => new URL(c).searchParams.get('locatadd_nm')), ['화성시 오산동', '오산동']);                          // 전체 → 동 낱말(화성시 전체 150행을 훑지 않음)
  const k = await harness().get('하남시 감일동 100'); assert.deepEqual(k.json.items.filter((i) => !i.place).map((i) => i.code), ['4145011400']);                // 지번 낱말은 이름 검색에서 빠진다
});
