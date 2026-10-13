'use strict';
/* api/v1/permits.js — 법정동 하나의 건축HUB 인허가를 번지 단위 사업 + 필지 경계로. 네트워크 없이 가짜 fetch 로 시험한다. */
const test = require('node:test');
const assert = require('node:assert/strict');
const { createCache } = require('../../lib/cache.js');
const { createKeyPool, memoryStore } = require('../../lib/keys.js');
const api = require('../../handlers/v1/permits.js');

const BJD = '4145010800';                                   // 하남시 덕풍동
const rec = (over) => Object.assign({ sigunguCd: '41450', bjdongCd: '10800', bun: '0569', ji: '0000', platGbCd: '0', purpsCdNm: '공동주택', totHhldCnt: 100, bldNm: '덕풍아파트', mgmHsrgstPk: 1, apprvDay: '20240101', stcnsDay: '20240601', useInsptDay: '', mainBldCnt: 3, platPlc: '경기도 하남시 덕풍동 569번지' }, over);
const hubJson = (items, total = items.length) => ({ response: { header: { resultCode: '00' }, body: { items: { item: items }, totalCount: total } } });
const SQ = (x, y, d = 0.0003) => ({ type: 'Polygon', coordinates: [[[x, y], [x + d, y], [x + d, y + d], [x, y + d], [x, y]]] });
const vw = (g) => ({ response: { status: g ? 'OK' : 'NOT_FOUND', result: g ? { featureCollection: { features: [{ geometry: g }] } } : undefined } });
const ok = (json) => ({ ok: true, status: 200, json: async () => json, text: async () => JSON.stringify(json) });
const raw = (status, text) => ({ ok: status < 400, status, json: async () => JSON.parse(text), text: async () => text });
const isHub = (url) => new URL(url).hostname === 'apis.data.go.kr';
const svc = (url) => new URL(url).pathname.split('/').pop();
const isBasis = (url) => isHub(url) && svc(url) === 'getHpBasisOulnInfo';                       // 대지위치·건물대장·표준코드 호출은 따로(기본은 빈 목록)

function defaultFetch(url) {
  const u = new URL(url);
  if (isBasis(url)) return ok(hubJson([rec(), rec({ mgmHsrgstPk: 2, bun: '0570', bldNm: '다른단지', totHhldCnt: 50, stcnsDay: '' }), rec({ mgmHsrgstPk: 3, purpsCdNm: '단독주택' })]));
  if (isHub(url)) return ok(hubJson([]));
  const pnu = /pnu:=:(\d+)/.exec(u.searchParams.get('attrFilter'))[1];
  return ok(vw(pnu.endsWith('05690000') ? SQ(127.2, 37.54) : SQ(127.201, 37.541)));
}
function harness(over = {}) {
  const calls = [], clock = { t: Date.parse('2026-10-05T03:00:00Z') };
  const env = over.env || { DATA_GO_KR_KEY_RESOLVE_1: 'HUB-KEY-1', VWORLD_KEY: 'VW-OPERATING', VWORLD_DEV_KEY: 'VW-DEV', VWORLD_DOMAIN: 'localhost' };
  const now = () => clock.t;
  const handler = api.createHandler({
    env, now, sleep: async () => {}, cache: createCache({ persist: false, now }), pool: createKeyPool({ env, now, store: memoryStore() }),
    fetch: async (url) => { calls.push(url); return (over.fetch || defaultFetch)(url, calls.length); },
  });
  const run = async (url, method = 'GET') => {
    const res = { headers: {}, statusCode: 0, body: '', setHeader(k, v) { this.headers[k.toLowerCase()] = v; }, end(b) { this.body = b; } };
    await handler({ method, url }, res);
    return { status: res.statusCode, headers: res.headers, json: res.body ? JSON.parse(res.body) : null, raw: res.body };
  };
  return { run, calls, clock };
}

test('덕풍동: 후보 2건을 번지 단위 사업으로, 필지 경계를 붙여 돌려준다(호출 인자·상태·캐시 헤더)', async () => {
  const h = harness();
  const r = await h.run(`/api/v1/permits?bjd=${BJD}`);
  assert.equal(r.status, 200); assert.equal(r.json.bjd, BJD); assert.equal(r.json.type, 'FeatureCollection');
  assert.deepEqual(r.json.features.map((f) => [f.properties.label, f.properties.status, f.properties.units, f.properties.pnu]),
    [['덕풍', '건설 단계', 100, '4145010800105690000'], ['다른단지', '계획', 50, '4145010800105700000']]);
  assert.equal(r.json.features[0].geometry.type, 'Polygon'); assert.deepEqual(r.json.features[0].geometry.coordinates[0][0], r.json.features[0].geometry.coordinates[0][4]);
  assert.deepEqual(r.json.features[0].properties.refs, ['1']);
  const m = r.json.meta; assert.equal(m.records, 3); assert.equal(m.candidates, 2); assert.equal(m.projects, 2); assert.equal(m.located, 2); assert.equal(m.unlocated, 0); assert.equal(m.truncated, false); assert.equal(m.parcelErrors, 0);
  assert.equal(m.fetchedAt, '2026-10-05'); assert.deepEqual(m.skipped, { notCandidate: 1, noPnu: 0 });
  assert.equal(r.headers['cache-control'], 'public, s-maxage=86400, stale-while-revalidate=86400');
  const hub = new URL(h.calls[0]);
  assert.equal(hub.pathname, '/1613000/HsPmsHubService/getHpBasisOulnInfo'); assert.equal(hub.searchParams.get('sigunguCd'), '41450'); assert.equal(hub.searchParams.get('bjdongCd'), '10800');
  assert.equal(hub.searchParams.get('serviceKey'), 'HUB-KEY-1'); assert.equal(hub.searchParams.get('numOfRows'), '100');
  const vwUrl = new URL(h.calls[1]); assert.equal(vwUrl.hostname, 'api.vworld.kr'); assert.equal(vwUrl.searchParams.get('data'), 'LP_PA_CBND_BUBUN');
  assert.equal(vwUrl.searchParams.get('key'), 'VW-DEV'); assert.equal(vwUrl.searchParams.get('domain'), 'localhost');             // 로컬은 개발키
  assert.ok(!r.raw.includes('KEY') && !r.raw.includes('VW-'));
});

test('8자리 법정동도 받고, 같은 법정동은 캐시에서 주며(원천 호출 0), 24시간 뒤 만료', async () => {
  const h = harness();
  const a = await h.run('/api/v1/permits?bjd=41450108'); assert.equal(a.json.bjd, BJD);
  const n = h.calls.length, b = await h.run(`/api/v1/permits?bjd=${BJD}`);
  assert.equal(h.calls.length, n); assert.deepEqual(b.json.features, a.json.features);
  h.clock.t += 24 * 3600 * 1000 + 1;
  await h.run(`/api/v1/permits?bjd=${BJD}`); assert.ok(h.calls.length > n);
});

test('여러 쪽: 총건수만큼 쪽을 이어 받는다', async () => {
  const h = harness({ fetch: (url) => { if (!isBasis(url)) return defaultFetch(url); const page = Number(new URL(url).searchParams.get('pageNo')); return ok(hubJson([rec({ mgmHsrgstPk: page, bun: String(500 + page).padStart(4, '0'), bldNm: `단지${page}` })], 150)); } });
  const r = await h.run(`/api/v1/permits?bjd=${BJD}`);
  assert.equal(r.json.meta.pages, 2); assert.equal(r.json.meta.records, 2); assert.equal(r.json.features.length, 2);
  assert.equal(new URL(h.calls[1]).searchParams.get('pageNo'), '2');
});

test('건축HUB 일시 오류(503·빈 본문·JSON 아님·resultCode 99)는 다시 시도하고, 계속 실패하면 502', async () => {
  let n = 0;
  const seq = [() => raw(503, ''), () => raw(200, ''), () => raw(200, '<html>'), () => ok({ response: { header: { resultCode: '99' } } })];
  const flaky = harness({ fetch: (url) => { if (!isBasis(url)) return defaultFetch(url); return n < seq.length ? seq[n++]() : ok(hubJson([rec()])); } });
  const r = await flaky.run(`/api/v1/permits?bjd=${BJD}`);
  assert.equal(r.status, 502);                                                                                     // 4번 시도가 모두 일시 오류
  const again = await flaky.run(`/api/v1/permits?bjd=${BJD}`);
  assert.equal(again.status, 200); assert.equal(again.json.features.length, 1);
  const dead = harness({ fetch: () => raw(503, '') });
  const d = await dead.run(`/api/v1/permits?bjd=${BJD}`);
  assert.equal(d.status, 502); assert.equal(d.headers['cache-control'], 'no-store'); assert.equal(d.json.code, 'upstream'); assert.equal(dead.calls.length, 4);
});

test('한도 오류(resultCode 22·XML·429)를 받은 키는 쉬고 다음 키로 이어서 부른다. 전부 소진이면 429', async () => {
  const quotaXml = '<OpenAPI_ServiceResponse><cmmMsgHeader><returnAuthMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR</returnAuthMsg><returnReasonCode>22</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>';
  for (const bad of [() => ok({ response: { header: { resultCode: '22' } } }), () => raw(200, quotaXml), () => raw(429, '')]) {
    const h = harness({ env: { DATA_GO_KR_KEY_RESOLVE_1: 'K1', DATA_GO_KEY_X: 'x', DATA_GO_KR_KEY_RESOLVE_2: 'K2', VWORLD_KEY: 'v' }, fetch: (url) => { if (!isBasis(url)) return defaultFetch(url); return new URL(url).searchParams.get('serviceKey') === 'K1' ? bad() : ok(hubJson([rec()])); } });
    const r = await h.run(`/api/v1/permits?bjd=${BJD}`);
    assert.equal(r.status, 200);
    assert.deepEqual(h.calls.filter(isBasis).map((c) => new URL(c).searchParams.get('serviceKey')), ['K1', 'K2']);
  }
  const none = harness({ env: { DATA_GO_KR_KEY_RESOLVE_1: 'K1', VWORLD_KEY: 'v' }, fetch: () => ok({ response: { header: { resultCode: '22' } } }) });
  const r = await none.run(`/api/v1/permits?bjd=${BJD}`);
  assert.equal(r.status, 429); assert.equal(r.json.code, 'keys-exhausted'); assert.ok(Number(r.headers['retry-after']) > 0); assert.equal(r.headers['cache-control'], 'no-store');
});

test('필지를 못 찾은 사업은 지도에서 빼고 이름만 알린다. 일시 오류로 못 받았으면 응답을 짧게만 두고 다음에 다시 받는다', async () => {
  const noParcel = (url) => /05700000/.test(new URL(url).searchParams.get('attrFilter') || '');
  const none = harness({ fetch: (url) => (!isHub(url) && noParcel(url) ? ok(vw(null)) : defaultFetch(url)) });
  const a = await none.run(`/api/v1/permits?bjd=${BJD}`);
  assert.equal(a.json.features.length, 1); assert.equal(a.json.meta.unlocated, 1); assert.deepEqual(a.json.meta.unlocatedNames, ['다른단지(570)']); assert.equal(a.json.meta.parcelErrors, 0);
  assert.deepEqual(a.json.meta.unlocatedList, [{ name: '다른단지', jibun: '570', status: '계획', units: 50, approvedAt: '2024-01-01', reason: '연속지적도에 없음(원인 미상)' }]);
  assert.equal(a.headers['cache-control'], 'public, s-maxage=86400, stale-while-revalidate=86400');                // 없는 필지는 정상 결과
  let fail = true;
  const flaky = harness({ fetch: (url) => (fail && !isHub(url) && noParcel(url) ? raw(500, '') : defaultFetch(url)) });
  const b = await flaky.run(`/api/v1/permits?bjd=${BJD}`);
  assert.equal(b.status, 200); assert.equal(b.json.features.length, 1); assert.equal(b.json.meta.parcelErrors, 1); assert.equal(b.headers['cache-control'], 'public, s-maxage=60');
  fail = false;
  const c = await flaky.run(`/api/v1/permits?bjd=${BJD}`);
  assert.equal(c.json.features.length, 2); assert.equal(c.json.meta.parcelErrors, 0);                              // 성공한 필지는 캐시, 실패했던 것만 다시
  const allFail = harness({ fetch: (url) => (isHub(url) ? defaultFetch(url) : raw(500, '')) });
  assert.equal((await allFail.run(`/api/v1/permits?bjd=${BJD}`)).status, 502);
});

test('사업이 많으면 120개까지만 필지를 붙이고 truncated, 세대수 큰 순으로 남긴다', async () => {
  const many = Array.from({ length: 130 }, (_, i) => rec({ mgmHsrgstPk: i + 1, bun: String(1000 + i).padStart(4, '0'), bldNm: `단지${i}`, totHhldCnt: 10 + i, stcnsDay: '' }));
  const h = harness({ fetch: (url) => (isBasis(url) ? ok(hubJson(many)) : isHub(url) ? ok(hubJson([])) : ok(vw(SQ(127.2, 37.54)))) });
  const r = await h.run(`/api/v1/permits?bjd=${BJD}`);
  assert.equal(r.json.meta.candidates, 130); assert.equal(r.json.meta.projects, api.MAX_PROJECTS); assert.equal(r.json.features.length, api.MAX_PROJECTS); assert.equal(r.json.meta.truncated, true);
  assert.equal(r.json.features[0].properties.units, 139);
});

test('거절: 쿼리·법정동 형식·방식·키 없음, 시간당 필지 호출 상한', async () => {
  const h = harness();
  for (const [url, status, code] of [['/api/v1/permits', 400, 'invalid-query'], [`/api/v1/permits?bjd=${BJD}&x=1`, 400, 'invalid-query'], [`/api/v1/permits?bjd=${BJD}&bjd=${BJD}`, 400, 'invalid-query'],
    ['/api/v1/permits?bjd=abc', 400, 'invalid-code'], ['/api/v1/permits?bjd=41450', 400, 'invalid-code'], ['/api/v1/permits?bjd=9999999999', 400, 'invalid-code']]) {
    const r = await h.run(url); assert.equal(r.status, status, url); assert.equal(r.json.code, code, url); assert.equal(r.json.type, `/problems/${code}`);
  }
  assert.equal((await h.run(`/api/v1/permits?bjd=${BJD}`, 'POST')).status, 405); assert.equal(h.calls.length, 0);
  assert.equal((await harness({ env: {} }).run(`/api/v1/permits?bjd=${BJD}`)).status, 503);
  assert.equal((await harness({ env: { DATA_GO_KR_KEY: 'k' } }).run(`/api/v1/permits?bjd=${BJD}`)).status, 503);         // V-World 키 없음
  const tight = harness({ env: { DATA_GO_KR_KEY_RESOLVE_1: 'k', VWORLD_KEY: 'v', PERMITS_UPSTREAM_PER_HOUR: '1' } });
  const r = await tight.run(`/api/v1/permits?bjd=${BJD}`);                                                          // 필지 2개 필요 → 1건 상한 초과
  assert.equal(r.status, 429); assert.equal(r.json.code, 'budget-exhausted'); assert.ok(Number(r.headers['retry-after']) > 0);
});

/* ── 건물대장 보강: 블록 단위 허가 위치·합필로 사라진 지번·준공 확인 ───────────────────────────────────────── */
const GB = '4145011400';                                    // 하남시 감일동(블록 허가가 몰린 곳)
const blkRec = (over) => Object.assign({ sigunguCd: '41450', bjdongCd: '11400', bun: '0000', ji: '0000', platGbCd: '2', purpsCdNm: '공동주택', totHhldCnt: 600, bldNm: 'LH아파트', block: 'A1BL', mgmHsrgstPk: 101, apprvDay: '20170101', stcnsDay: '20180101', useInsptDay: '', platPlc: '경기도 하남시 감일동 블록' }, over);
const ledRow = (over) => Object.assign({ sigunguCd: '41450', bjdongCd: '10300', bun: '0458', ji: '0000', platGbCd: '0', hhldCnt: 600, platArea: 30000, bldNm: '하남감일 호반써밋', useAprDay: '20201027', platPlc: '경기도 하남시 감이동 458번지', mainPurpsCdNm: '공동주택' }, over);
const platRow = (ref, area) => ({ mgmHsrgstPk: ref, bun: '0000', ji: '0000', platArea: area });
const umdRows = [{ region_cd: '4145011400', umd_cd: '114', ri_cd: '00' }, { region_cd: '4145010300', umd_cd: '103', ri_cd: '00' }, { region_cd: '4145000000', umd_cd: '000', ri_cd: '00' }, { region_cd: '4145011401', umd_cd: '114', ri_cd: '01' }];
const stanJson = (rows) => ({ StanReginCd: [{ head: [{ totalCount: rows.length }, { numOfRows: '1000', pageNo: '1', type: 'JSON' }, { RESULT: { resultCode: 'INFO-0', resultMsg: 'NOMAL SERVICE' } }] }, { row: rows }] });
/* 감일동 허가: 블록 A1BL(600세대, 대지 30,100㎡) + 일반 단지 하나. 대장은 이웃 감이동에 있다 */
function ledgerFetch(opts = {}) {
  const basis = opts.basis || [blkRec(), rec({ bjdongCd: '11400', bun: '0100', platPlc: '경기도 하남시 감일동 100번지', bldNm: '일반단지', totHhldCnt: 80, mgmHsrgstPk: 7, stcnsDay: '' })];
  const ledger = opts.ledger || { '10300': [ledRow()], '11400': [] };
  return (url) => {
    const u = new URL(url);
    if (u.hostname === 'api.vworld.kr') { const pnu = /pnu:=:(\d+)/.exec(u.searchParams.get('attrFilter'))[1]; return opts.parcel ? opts.parcel(pnu) : ok(vw(SQ(127.2 + (Number(pnu.slice(-8, -4)) % 90) * 0.001, 37.54))); }
    if (u.pathname.endsWith('/getStanReginCdList')) return ok(stanJson(umdRows));
    const s = svc(url);
    if (s === 'getHpBasisOulnInfo') return ok(hubJson(basis));
    if (s === 'getHpPlatPlcInfo') return ok(hubJson(opts.plat || [platRow(101, 30100)]));
    if (s === 'getBrRecapTitleInfo') { if (opts.ledgerStatus) return raw(opts.ledgerStatus, ''); return ok(hubJson(ledger[u.searchParams.get('bjdongCd')] || [])); }
    return ok(hubJson([]));
  };
}
const calls = (h, name) => h.calls.filter((c) => isHub(c) && svc(c) === name);

test('건물대장: 블록 단위 허가가 세대수+대지면적으로 대장의 지번에 맞아 지도에 오른다(이웃 법정동까지 찾음, 이름·준공일은 대장 기준)', async () => {
  const h = harness({ fetch: ledgerFetch() });
  const r = await h.run(`/api/v1/permits?bjd=${GB}`);
  assert.equal(r.status, 200);
  const f = r.json.features.find((x) => x.properties.via === 'ledger'); assert.ok(f);
  assert.equal(f.properties.pnu, '4145010300104580000'); assert.equal(f.properties.jibun, '458'); assert.equal(f.properties.block, 'A1BL');
  assert.equal(f.properties.name, '하남감일 호반써밋');                                    // 허가 이름이 'LH아파트'라 대장 이름
  assert.equal(f.properties.status, '입주 단계'); assert.equal(f.properties.completedAt, '2020-10-27'); assert.equal(f.properties.units, 600);
  assert.deepEqual(f.properties.ledger, { name: '하남감일 호반써밋', platPlc: '경기도 하남시 감이동 458번지', useAprDay: '2020-10-27', areaDiff: 0.33 });
  assert.equal(f.geometry.type, 'Polygon'); assert.ok(!('geometry' in f.properties));
  const m = r.json.meta; assert.equal(m.blockProjects, 0); assert.deepEqual(m.blockList, []); assert.equal(m.candidates, 2); assert.equal(m.located, 2);
  assert.deepEqual(m.ledger, { used: true, bjds: 2, rows: 1, blocksMatched: 1, blocksAmbiguous: 0, parcelsRecovered: 0, completions: 0 });
  assert.deepEqual(calls(h, 'getBrRecapTitleInfo').map((c) => new URL(c).searchParams.get('bjdongCd')).sort(), ['10300', '11400']);      // 시군구 안 법정동(리·시군구 행 제외)
  assert.equal(new URL(calls(h, 'getBrRecapTitleInfo')[0]).searchParams.get('sigunguCd'), '41450');
  assert.equal(r.headers['cache-control'], 'public, s-maxage=86400, stale-while-revalidate=86400');
  const n = h.calls.length; await h.run(`/api/v1/permits?bjd=${GB}`); assert.equal(h.calls.length, n);                                   // 결과 전체가 캐시
  assert.ok(!r.raw.includes('KEY'));
});

test('건물대장: 지번이 합필로 사라진 사업의 현재 지번을 찾고, 같은 지번 대장의 사용승인일이 허가 이후면 준공으로 올린다(허가 이전 대장은 무시)', async () => {
  const basis = [rec({ bjdongCd: '11400', bun: '0200', ji: '0000', mgmHsrgstPk: 21, bldNm: '옛지번단지', totHhldCnt: 300, stcnsDay: '20190101', apprvDay: '20180101' }),
    rec({ bjdongCd: '11400', bun: '0300', ji: '0000', mgmHsrgstPk: 22, bldNm: '준공단지', totHhldCnt: 120, stcnsDay: '20190101', apprvDay: '20180101' }),
    rec({ bjdongCd: '11400', bun: '0400', ji: '0000', mgmHsrgstPk: 23, bldNm: '옛건물만있는단지', totHhldCnt: 90, stcnsDay: '', apprvDay: '20240101' })];
  const ledger = { '11400': [ledRow({ bjdongCd: '11400', bun: '0300', hhldCnt: 120, platArea: 5000, useAprDay: '20211231', bldNm: '준공단지', platPlc: '경기도 하남시 감일동 300번지' }),
    ledRow({ bjdongCd: '11400', bun: '0400', hhldCnt: 40, platArea: 1000, useAprDay: '20100101', bldNm: '허가 전 건물', platPlc: '경기도 하남시 감일동 400번지' })],
  '10300': [ledRow({ bjdongCd: '10300', bun: '0999', hhldCnt: 300, platArea: 12000, useAprDay: '20230630', bldNm: '합필후단지', platPlc: '경기도 하남시 감이동 999번지 외 1필지' })] };
  const gone = '4145011400102000000';
  const h = harness({ fetch: ledgerFetch({ basis, ledger, plat: [platRow(21, 11900), platRow(22, 5000), platRow(23, 3000)], parcel: (pnu) => ok(pnu === gone ? vw(null) : vw(SQ(127.3, 37.55))) }) });
  const r = await h.run(`/api/v1/permits?bjd=${GB}`);
  const by = Object.fromEntries(r.json.features.map((x) => [x.properties.name, x.properties]));
  const moved = by['옛지번단지'];                                                          // 허가 이름은 그대로, 위치·지번만 대장 기준으로
  assert.equal(moved.pnu, '4145010300109990000'); assert.equal(moved.jibun, '999'); assert.equal(moved.hubJibun, '200'); assert.equal(moved.via, 'ledger');
  assert.equal(moved.address, '경기도 하남시 감이동 999번지 외 1필지'); assert.equal(moved.ledger.name, '합필후단지'); assert.equal(moved.ledger.areaDiff, 0.84);
  assert.equal(moved.status, '입주 단계'); assert.equal(moved.completedAt, '2023-06-30'); assert.equal(moved.overdue, null);
  assert.equal(by['준공단지'].status, '입주 단계'); assert.equal(by['준공단지'].completedAt, '2021-12-31'); assert.equal(by['준공단지'].statusBy, 'ledger'); assert.equal(by['준공단지'].plannedStart, null);
  assert.equal(by['옛건물만있는단지'].status, '계획'); assert.ok(!by['옛건물만있는단지'].statusBy);                // 사용승인일(2010)이 허가(2024)보다 앞서면 옛 건물
  const m = r.json.meta; assert.equal(m.unlocated, 0); assert.equal(m.ledger.parcelsRecovered, 1); assert.equal(m.ledger.completions, 1); assert.equal(m.located, 3);
  assert.equal(calls(h, 'getHpPlatPlcInfo').length, 1);
});

test('건물대장: 권한이 없거나(403) 한도·장애면 인허가 결과는 그대로 주고 사유만 남긴다(짧게만 캐시, 이웃 법정동은 부르지 않음)', async () => {
  for (const [status, why] of [[403, '건물대장 서비스 권한이 없음(활용신청 필요)'], [503, '건물대장을 불러오지 못함']]) {
    const h = harness({ fetch: ledgerFetch({ ledgerStatus: status }) });
    const r = await h.run(`/api/v1/permits?bjd=${GB}`);
    assert.equal(r.status, 200); assert.equal(r.json.features.length, 1); assert.equal(r.json.features[0].properties.name, '일반단지');
    assert.equal(r.json.meta.blockProjects, 1); assert.equal(r.json.meta.blockList[0].block, 'A1BL');                      // 블록은 그대로 목록으로
    assert.equal(r.json.meta.ledger.used, false); assert.equal(r.json.meta.ledger.error, why);
    assert.equal(r.headers['cache-control'], 'public, s-maxage=60');
    assert.equal(calls(h, 'getBrRecapTitleInfo').length, status === 403 ? 1 : 4);                                          // 403 은 한 번에 멈춤(503 은 다시 시도)
  }
});

test('건물대장: 같은 세대수·면적 후보가 둘이면 모호로 남기고, 이미 다른 사업이 쓰는 지번에는 붙이지 않는다', async () => {
  const twin = [ledRow({ bun: '0458', platArea: 30000 }), ledRow({ bun: '0459', platArea: 30010, bldNm: '쌍둥이' })];
  const a = await harness({ fetch: ledgerFetch({ ledger: { '10300': twin, '11400': [] } }) }).run(`/api/v1/permits?bjd=${GB}`);
  assert.equal(a.json.meta.blockProjects, 1); assert.equal(a.json.meta.ledger.blocksAmbiguous, 1); assert.equal(a.json.meta.ledger.blocksMatched, 0);
  assert.ok(!a.json.features.some((f) => f.properties.via === 'ledger'));
  const used = '4145011400101000000';                                                                                     // 일반단지(감일동 100번지)의 대장 행이 블록과 같은 세대수·면적
  const b = await harness({ fetch: ledgerFetch({ ledger: { '10300': [], '11400': [ledRow({ bjdongCd: '11400', bun: '0100', hhldCnt: 600, platArea: 30000 })] } }) }).run(`/api/v1/permits?bjd=${GB}`);
  assert.ok(b.json.features.some((f) => f.properties.pnu === used)); assert.equal(b.json.features.filter((f) => f.properties.pnu === used).length, 1);
  assert.equal(b.json.meta.blockProjects, 1);
});

test('건물대장: 보강이 필요 없으면(모두 위치 있고 준공) 대장·대지위치는 부르지 않는다', async () => {
  const done = [rec({ bjdongCd: '11400', bun: '0100', bldNm: '준공단지', totHhldCnt: 80, apprvDay: '20180101', stcnsDay: '20200101', useInsptDay: '20230101' })];
  const h = harness({ fetch: ledgerFetch({ basis: done }) });
  const r = await h.run(`/api/v1/permits?bjd=${GB}`);
  assert.equal(r.json.features[0].properties.status, '입주 단계'); assert.equal(calls(h, 'getBrRecapTitleInfo').length, 0); assert.equal(calls(h, 'getHpPlatPlcInfo').length, 0);
  assert.deepEqual(r.json.meta.ledger, { used: false, bjds: 0, rows: 0, blocksMatched: 0, blocksAmbiguous: 0, parcelsRecovered: 0, completions: 0 });
});

test('건물대장: 초당 호출 한도(429 …PER_SECOND…)는 일일 한도가 아니므로 쉬었다 다시 부르고, 계속이어도 키를 하루 쉬게 하지 않는다', async () => {
  const perSec = () => raw(429, JSON.stringify({ OpenAPI_ServiceResponse: { cmmMsgHeader: { errMsg: 'SERVICE ERROR', returnAuthMsg: 'LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR', returnReasonCode: '22' } } }));
  let hits = 0, mode = 'twice';
  const base = ledgerFetch();
  const h = harness({ fetch: (url) => { if (isHub(url) && svc(url) === 'getBrRecapTitleInfo') { hits++; if (mode === 'always' || (mode === 'twice' && hits <= 2)) return perSec(); } return base(url); } });
  const a = await h.run(`/api/v1/permits?bjd=${GB}`);
  assert.equal(a.status, 200); assert.equal(a.json.meta.ledger.error, undefined); assert.equal(a.json.meta.ledger.blocksMatched, 1);              // 두 번 막혔다가 다시 불러 성공
  mode = 'always'; hits = 0;
  const other = await h.run('/api/v1/permits?bjd=4145011500');                                                                                    // 다른 법정동(캐시 없음)
  assert.equal(other.status, 200); assert.equal(other.json.meta.ledger.used, false); assert.match(other.json.meta.ledger.error, /초당 호출 한도/);
  assert.equal(hits, 4); assert.equal(other.headers['cache-control'], 'public, s-maxage=60');
  mode = 'ok';
  const later = await h.run('/api/v1/permits?bjd=4145011600');                                                                                    // 키는 그대로 쓸 수 있다
  assert.equal(later.status, 200); assert.equal(later.json.meta.ledger.error, undefined);
  const daily = harness({ fetch: (url) => (isHub(url) && svc(url) === 'getBrRecapTitleInfo' ? raw(429, '') : base(url)) });
  const d = await daily.run(`/api/v1/permits?bjd=${GB}`);
  assert.equal(d.status, 200); assert.equal(d.json.meta.ledger.error, '인증키 한도·설정 문제로 건물대장을 건너뜀');                                    // 본문 없는 429 는 일일 한도로 본다
});
