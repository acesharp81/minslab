'use strict';
/* 사업 id 가 서버 API 에 닿는 곳: /api/v1/resolve?project=PRJ-… (사업의 위치로 열기) · /api/v1/permits 의 projectId. 네트워크 없이 가짜 fetch 로 시험한다. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createCache } = require('../../lib/cache.js');
const { createKeyPool, memoryStore } = require('../../lib/keys.js');
const P = require('../../lib/projects.js');
const resolveApi = require('../../handlers/v1/resolve.js');
const permitsApi = require('../../handlers/v1/permits.js');

const NOW = Date.parse('2026-10-06T03:00:00Z');
const ROW = (cd, nm) => ({ region_cd: cd, sido_cd: cd.slice(0, 2), sgg_cd: cd.slice(2, 5), umd_cd: cd.slice(5, 8), ri_cd: cd.slice(8, 10), locatadd_nm: nm, locallow_nm: nm.split(' ').pop(), locathigh_cd: '', adpt_de: '' });
const STAN = {
  '41450': [ROW('4145000000', '경기도 하남시'), ROW('4145010800', '경기도 하남시 덕풍동'), ROW('4145011400', '경기도 하남시 감일동')],
  '28245': [ROW('2824500000', '인천광역시 계양구'), ROW('2824510900', '인천광역시 계양구 박촌동')],
};
const stanJson = (rows) => ({ StanReginCd: [{ head: [{ totalCount: rows.length }, { RESULT: { resultCode: 'INFO-0' } }] }, { row: rows }] });
const SQ = (x, y, d = 0.003) => ({ type: 'Polygon', coordinates: [[[x, y], [x + d, y], [x + d, y + d], [x, y + d], [x, y]]] });
const vw = (g, props = {}) => ({ response: { status: g ? 'OK' : 'NOT_FOUND', result: g ? { featureCollection: { features: [{ properties: props, geometry: g }] } } : undefined } });
const ok = (json) => ({ ok: true, status: 200, json: async () => json, text: async () => JSON.stringify(json) });

/* ---- 레지스트리: 하남 덕풍동 사업(필지 연결), 위치 미연결 사업(법정동만), 합병되어 폐기된 id, 번들 단지(계양) ---- */
const PNU = '4145010800105690000';
const base = { stageCode: '04', source: P.HUB_SOURCE, asOf: '2026-10-06', issuedAt: '2026-10-06' };
const REG = {
  schema: P.SCHEMA, updatedAt: '2026-10-06', counters: { '41450': 3, '28245': 1 },
  projects: [
    { id: 'PRJ-28245-0001', sgg: '28245', bjdCodes: [], pnus: [], ...base, stageCode: '04', source: { provider: '주택파동 지도 번들', dataset: 'regions/incheon-gyeyang/projects.json' }, name: '인천계양 테크노밸리 A2 블록', units: 747, refs: [{ system: 'bundle', key: 'incheon-gyeyang', value: 'techno-A2' }] },
    { id: 'PRJ-41450-0001', sgg: '41450', bjdCodes: ['4145010800'], pnus: [PNU], ...base, name: '덕풍아파트', units: 100, refs: [{ system: 'hub-hs-basis', key: 'mgmHsrgstPk', value: '0000123', asOf: '2026-10-06' }, { system: 'hub-hs-basis', key: 'mgmHsrgstPk', value: '555' }] },
    { id: 'PRJ-41450-0002', sgg: '41450', bjdCodes: ['4145011400'], pnus: [], ...base, stageCode: '03', name: '블록 사업', refs: [{ system: 'hub-hs-basis', key: 'mgmHsrgstPk', value: '9001' }] },
    { id: 'PRJ-41450-0003', sgg: '41450', bjdCodes: ['4145010800'], pnus: [PNU], ...base, supersededBy: 'PRJ-41450-0001', refs: [{ system: 'hub-hs-basis', key: 'mgmHsrgstPk', value: '555' }] },
  ],
};
// 0003 은 합병되어 폐기됐으므로 참조를 0001 에 합쳐 둔 모양으로 맞춘다(같은 참조를 활성 사업 둘이 갖지 않게)
REG.projects[3].refs = [{ system: 'hub-hs-basis', key: 'mgmHsrgstPk', value: '777' }];
REG.projects[1].refs.push({ system: 'hub-hs-basis', key: 'mgmHsrgstPk', value: '777' });
const INDEX = P.indexRegistry(REG);

test('시험용 레지스트리는 일관성 검사를 통과한다', () => assert.deepEqual(P.validateRegistry(REG), []));

function resolveHarness(over = {}) {
  const calls = [], dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pj-'));
  const env = { DATA_GO_KR_KEY_RESOLVE_1: 'SECRET-R1', VWORLD_KEY: 'VW-SECRET', VWORLD_DOMAIN: 'localhost' };
  const fakeFetch = async (url) => {
    calls.push(url);
    const u = new URL(url);
    if (u.hostname === 'apis.data.go.kr') return ok(STAN[`${u.searchParams.get('sido_cd')}${u.searchParams.get('sgg_cd')}`] ? stanJson(STAN[`${u.searchParams.get('sido_cd')}${u.searchParams.get('sgg_cd')}`]) : { RESULT: { resultCode: 'INFO-3' } });
    const layer = u.searchParams.get('data'), f = u.searchParams.get('attrFilter') || '';
    if (layer === 'LT_C_ADEMD_INFO') return ok(vw(SQ(127.2, 37.54, 0.02)));
    if (layer === 'LT_C_ADSIGG_INFO') return ok(vw(SQ(127.1, 37.5, 0.2)));
    if (layer === 'LP_PA_CBND_BUBUN') return ok(f.includes(PNU) ? vw(SQ(127.2, 37.54), { addr: '경기도 하남시 덕풍동 569', jibun: '569대' }) : vw(null));
    throw new Error(`예상 밖 호출 ${url}`);
  };
  const handler = resolveApi.createHandler({ fetch: fakeFetch, env, now: () => NOW, cacheDir: dir, registryIndex: over.index || INDEX,
    readCoverage: () => ({ 28245: { slug: 'incheon-gyeyang', name: '인천 계양구', updatedAt: '2026-10-03', visibility: 'public' } }) });
  const run = async (url, method = 'GET') => {
    const res = { headers: {}, statusCode: 0, body: '', setHeader(k, v) { this.headers[k.toLowerCase()] = v; }, end(b) { this.body = b; } };
    await handler({ method, url }, res);
    return { status: res.statusCode, headers: res.headers, json: res.body ? JSON.parse(res.body) : null, raw: res.body };
  };
  return { run, calls, done: () => fs.rmSync(dir, { recursive: true, force: true }) };
}

test('resolve: 사업 id 를 필지로 연다(type project, canonical 은 사업 id, pnu·parcel·경계는 첫 필지, project 정보)', async () => {
  const h = resolveHarness();
  const r = await h.run('/api/v1/resolve?project=PRJ-41450-0001&geometry=1');
  assert.equal(r.status, 200);
  assert.deepEqual([r.json.type, r.json.canonical, r.json.input, r.json.sgg, r.json.bjd, r.json.pnu, r.json.name, r.json.level], ['project', 'PRJ-41450-0001', 'PRJ-41450-0001', '41450', '4145010800', PNU, '경기도 하남시 덕풍동', 'umd']);
  assert.deepEqual(r.json.project, { id: 'PRJ-41450-0001', name: '덕풍아파트', units: 100, stageCode: '04', stage: '건설', pnus: [PNU], bjdCodes: ['4145010800'] });
  assert.equal(r.json.parcel.addr, '경기도 하남시 덕풍동 569'); assert.equal(r.json.parcel.geometry.type, 'Polygon'); assert.ok(r.json.bbox && r.json.center);
  assert.equal(r.json.warnings, undefined); assert.deepEqual(r.json.coverage, { tier: 'none' });
  assert.equal(r.headers['cache-control'], 'public, s-maxage=300, stale-while-revalidate=300'); assert.ok(!r.raw.includes('SECRET'));
  const viaCode = await h.run('/api/v1/resolve?code=prj-41450-0001'); assert.equal(viaCode.status, 200); assert.equal(viaCode.json.canonical, 'PRJ-41450-0001'); assert.equal(viaCode.json.pnu, PNU);   // code= 도 자릿수가 아니라 접두로 판별(소문자 허용)
  h.done();
});

test('resolve: 위치(필지)가 없는 사업은 법정동 경계로 열고 project-unlocated, 번들 단지 사업은 coverage A 와 project.block, 시군구까지만 있어도 열린다', async () => {
  const h = resolveHarness();
  const b = await h.run('/api/v1/resolve?project=PRJ-41450-0002&geometry=1');
  assert.deepEqual([b.json.type, b.json.canonical, b.json.bjd, b.json.pnu, b.json.level, b.json.warnings], ['project', 'PRJ-41450-0002', '4145011400', undefined, 'umd', ['project-unlocated']]);
  assert.equal(b.json.project.stageCode, '03'); assert.equal(b.json.project.stage, '인허가'); assert.deepEqual(b.json.project.pnus, []); assert.equal(b.json.geometry.type, 'Polygon');
  const a = await h.run('/api/v1/resolve?project=PRJ-28245-0001&geometry=1');
  assert.equal(a.status, 200); assert.deepEqual([a.json.type, a.json.sgg, a.json.coverage.tier, a.json.coverage.slug, a.json.project.block, a.json.warnings], ['project', '28245', 'A', 'incheon-gyeyang', 'techno-A2', ['project-unlocated']]);
  assert.equal(a.json.bjd, undefined); assert.equal(a.json.name, '인천광역시 계양구'); assert.equal(a.json.geometry.type, 'Polygon', '시군구 경계(화면은 geometry=1)');
  h.done();
});

test('resolve: 합병되어 폐기된 id 는 남은 사업으로 열고 project-superseded 와 supersededFrom 을 알린다', async () => {
  const h = resolveHarness();
  const r = await h.run('/api/v1/resolve?project=PRJ-41450-0003&geometry=1');
  assert.equal(r.status, 200); assert.equal(r.json.canonical, 'PRJ-41450-0001'); assert.equal(r.json.input, 'PRJ-41450-0003'); assert.equal(r.json.project.supersededFrom, 'PRJ-41450-0003'); assert.deepEqual(r.json.warnings, ['project-superseded']);
  h.done();
});

test('resolve: 발급되지 않은 id 는 404 unknown-project, 형식·시도·종류 오류는 400, 레지스트리가 비어 있어도 다른 코드는 그대로', async () => {
  const h = resolveHarness();
  const nf = await h.run('/api/v1/resolve?project=PRJ-41450-0099'); assert.equal(nf.status, 404); assert.equal(nf.json.code, 'unknown-project'); assert.equal(nf.json.type, '/problems/unknown-project'); assert.equal(nf.json.project, 'PRJ-41450-0099');
  for (const [url, reason] of [['project=PRJ-4145-0001', 'bad-project'], ['project=PRJ-41450-0000', 'bad-project'], ['project=PRJ-99999-0001', 'unknown-sido'], ['project=PRJ-41450-0001x', 'bad-project']]) {
    const r = await h.run(`/api/v1/resolve?${url}`); assert.equal(r.status, 400, url); assert.equal(r.json.code, 'invalid-code'); assert.equal(r.json.reason, reason, url);
  }
  const mism = await h.run('/api/v1/resolve?pnu=PRJ-41450-0001'); assert.equal(mism.status, 400); assert.equal(mism.json.reason, 'type-mismatch');
  const two = await h.run('/api/v1/resolve?project=PRJ-41450-0001&code=41450'); assert.equal(two.status, 400); assert.equal(two.json.code, 'invalid-query');
  const empty = resolveHarness({ index: P.indexRegistry(P.emptyRegistry()) });
  assert.equal((await empty.run('/api/v1/resolve?project=PRJ-41450-0001')).status, 404);
  const plain = await empty.run('/api/v1/resolve?bjd=4145010800'); assert.equal(plain.status, 200); assert.equal(plain.json.type, 'bjd'); assert.equal(plain.json.project, undefined);
  h.done(); empty.done();
});

/* ---- permits: 사업 id 붙이기 ---- */
const rec = (over) => ({ sigunguCd: '41450', bjdongCd: '10800', bun: '0569', ji: '0000', platGbCd: '0', purpsCdNm: '공동주택', totHhldCnt: 100, bldNm: '덕풍아파트', mgmHsrgstPk: 555, apprvDay: '20240101', stcnsDay: '20240601', useInsptDay: '', mainBldCnt: 3, platPlc: '경기도 하남시 덕풍동 569번지', ...over });
const hubJson = (items) => ({ response: { header: { resultCode: '00' }, body: { items: { item: items }, totalCount: items.length } } });
function permitsHarness(over = {}) {
  const calls = [];
  const env = { DATA_GO_KR_KEY_RESOLVE_1: 'RES-KEY', VWORLD_KEY: 'VW-KEY', VWORLD_DOMAIN: 'localhost' };
  const svc = permitsApi.createService({ env, now: () => NOW, sleep: async () => {}, cache: createCache({ persist: false, now: () => NOW }), pool: createKeyPool({ env, now: () => NOW, store: memoryStore() }), registryIndex: over.index || INDEX,
    fetch: async (url) => {
      calls.push(url);
      const u = new URL(url);
      if (u.pathname.includes('getHpBasisOulnInfo')) return ok(hubJson([rec(), rec({ mgmHsrgstPk: 556, bun: '0570', bldNm: '다른단지', totHhldCnt: 50, stcnsDay: '' })]));
      if (u.pathname.includes('getHpPlatPlcInfo') || u.pathname.includes('getBrRecapTitleInfo')) return ok(hubJson([]));   // 대지위치·건물대장은 비어 있음(오류 없이 보강 끝 → 24시간 캐시)
      if (u.hostname === 'api.vworld.kr') return ok(vw(SQ(127.2, 37.54)));
      throw new Error(`예상 밖 호출 ${url}`);
    } });
  const run = async (url) => {
    const res = { headers: {}, statusCode: 0, body: '', setHeader(k, v) { this.headers[k.toLowerCase()] = v; }, end(b) { this.body = b; } };
    await svc.handler({ method: 'GET', url }, res);
    return { status: res.statusCode, json: res.body ? JSON.parse(res.body) : null };
  };
  return { run, svc, calls };
}

test('permits: 레지스트리에 발급된 사업에만 projectId(허가 관리번호가 같거나 PNU 가 같을 때). 캐시된 본문은 바뀌지 않아 레지스트리를 고치면 바로 반영된다', async () => {
  const h = permitsHarness();
  const r = await h.run('/api/v1/permits?bjd=4145010800');
  assert.equal(r.status, 200);
  const byName = Object.fromEntries(r.json.features.map((f) => [f.properties.name, f.properties]));
  assert.equal(byName['덕풍아파트'].projectId, 'PRJ-41450-0001'); assert.equal('projectId' in byName['다른단지'], false, '발급되지 않은 사업에는 없다');
  const cached = (await h.svc.getPermits('4145010800')).body; assert.equal(cached.features.every((f) => !('projectId' in f.properties)), true, '공유되는 캐시 본문에는 싣지 않는다');
  const n = h.calls.length;
  const second = permitsHarness({ index: P.indexRegistry(P.emptyRegistry()) }); const none = await second.run('/api/v1/permits?bjd=4145010800'); assert.equal(none.json.features.every((f) => !('projectId' in f.properties)), true);
  await h.run('/api/v1/permits?bjd=4145010800'); assert.equal(h.calls.length, n, '두 번째는 원천을 다시 부르지 않는다');
});

test('permits: 관리번호가 달라도 PNU 가 같으면 같은 사업 id (변경허가로 새 관리번호가 생긴 경우)', async () => {
  const h = permitsHarness({ index: P.indexRegistry({ ...REG, projects: REG.projects.filter((p) => p.id === 'PRJ-41450-0001').map((p) => ({ ...p, refs: [{ system: 'hub-hs-basis', key: 'mgmHsrgstPk', value: 'OLD-1' }] })) }) });
  const r = await h.run('/api/v1/permits?bjd=4145010800');
  assert.equal(r.json.features.find((f) => f.properties.name === '덕풍아파트').properties.projectId, 'PRJ-41450-0001');
});
