'use strict';
/* 인터페이스 계약 시험: schemas/api/openapi.json(서버·화면 사이의 계약)이 ① 문서로서 온전하고(경로·매개변수·응답·$ref) ② 운영에서 받은 실제 응답
   (tests/fixtures/api, scripts/capture-fixtures.js 로 갱신)을 통과시키며 ③ 핸들러가 문서에 적은 오류를 같은 모양으로 내고 ④ 문서의 매개변수가 핸들러가 받는 이름과 같은지 확인한다.
   스키마 검증기는 외부 패키지 없이 쓰는 최소 JSON Schema(type·enum·const·required·properties·additionalProperties·items·prefixItems·pattern·min/max·format date·oneOf·$ref)다. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createCache } = require('../../lib/cache.js');
const { createKeyPool, memoryStore } = require('../../lib/keys.js');

const ROOT = path.join(__dirname, '..', '..');
const DOC = JSON.parse(fs.readFileSync(path.join(ROOT, 'schemas/api/openapi.json'), 'utf8'));
const FIX = path.join(ROOT, 'tests/fixtures/api');
const fixture = (f) => JSON.parse(fs.readFileSync(path.join(FIX, f), 'utf8'));

/* ---------- 최소 JSON Schema 검증기: 오류 문구 배열을 돌려준다(통과하면 []) ---------- */
function validate(schema, value, at = '$', errs = []) {
  if (schema === true || schema === undefined) return errs;
  if (schema.$ref) {
    const name = /^#\/components\/schemas\/(.+)$/.exec(schema.$ref);
    if (!name || !DOC.components.schemas[name[1]]) { errs.push(`${at}: 풀 수 없는 $ref ${schema.$ref}`); return errs; }
    return validate(DOC.components.schemas[name[1]], value, at, errs);
  }
  if (schema.oneOf) {
    const ok = schema.oneOf.filter((s) => validate(s, value, at, []).length === 0).length;
    if (ok !== 1) errs.push(`${at}: oneOf 가 ${ok}개와 맞음(1개여야 함)`);
    return errs;
  }
  if ('const' in schema && value !== schema.const) errs.push(`${at}: ${JSON.stringify(schema.const)} 이어야 함(${JSON.stringify(value)})`);
  if (schema.enum && !schema.enum.includes(value)) errs.push(`${at}: ${JSON.stringify(value)} 는 ${schema.enum.join('|')} 중 하나여야 함`);
  const types = schema.type ? [].concat(schema.type) : null;
  const is = (t) => (t === 'null' ? value === null : t === 'array' ? Array.isArray(value) : t === 'object' ? value !== null && typeof value === 'object' && !Array.isArray(value)
    : t === 'integer' ? Number.isInteger(value) : t === 'number' ? typeof value === 'number' && Number.isFinite(value) : t === 'string' ? typeof value === 'string' : t === 'boolean' ? typeof value === 'boolean' : false);
  if (types && !types.some(is)) { errs.push(`${at}: 형식 ${types.join('|')} 이어야 함(${value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value})`); return errs; }
  if (typeof value === 'string') {
    if (schema.minLength != null && value.length < schema.minLength) errs.push(`${at}: 너무 짧음`);
    if (schema.maxLength != null && value.length > schema.maxLength) errs.push(`${at}: 너무 김`);
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) errs.push(`${at}: 패턴 ${schema.pattern} 에 안 맞음(${value.slice(0, 30)})`);
    if (schema.format === 'date' && !(/^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value)))) errs.push(`${at}: 날짜가 아님(${value})`);
    if (schema.format === 'date-time' && !(/^\d{4}-\d{2}-\d{2}T/.test(value) && !Number.isNaN(Date.parse(value)))) errs.push(`${at}: 날짜·시각이 아님(${value})`);
  }
  if (typeof value === 'number') {
    if (schema.minimum != null && value < schema.minimum) errs.push(`${at}: ${value} < ${schema.minimum}`);
    if (schema.maximum != null && value > schema.maximum) errs.push(`${at}: ${value} > ${schema.maximum}`);
  }
  if (Array.isArray(value)) {
    if (schema.minItems != null && value.length < schema.minItems) errs.push(`${at}: 항목이 ${schema.minItems}개 미만`);
    if (schema.maxItems != null && value.length > schema.maxItems) errs.push(`${at}: 항목이 ${schema.maxItems}개 초과`);
    if (schema.prefixItems) schema.prefixItems.forEach((s, i) => { if (i < value.length) validate(s, value[i], `${at}[${i}]`, errs); });
    if (schema.items) value.forEach((v, i) => validate(schema.items, v, `${at}[${i}]`, errs));
  }
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
    for (const k of schema.required || []) if (!(k in value)) errs.push(`${at}: 필수 항목 ${k} 가 없음`);
    const props = schema.properties || {};
    for (const [k, v] of Object.entries(value)) {
      if (props[k]) validate(props[k], v, `${at}.${k}`, errs);
      else if (schema.additionalProperties === false) errs.push(`${at}: 문서에 없는 항목 ${k}`);
      else if (schema.additionalProperties && typeof schema.additionalProperties === 'object') validate(schema.additionalProperties, v, `${at}.${k}`, errs);
    }
  }
  return errs;
}
const check = (schemaName, value) => validate({ $ref: `#/components/schemas/${schemaName}` }, value);
const must = (schemaName, value, label) => { const e = check(schemaName, value); assert.deepEqual(e.slice(0, 5), [], `${label || schemaName} 가 계약을 어김`); };

/* ---------- ① 문서 자체 ---------- */
test('OpenAPI 문서: 3.1, 경로마다 operationId(유일)·태그·매개변수·200 과 오류 응답, GET 만', () => {
  assert.equal(DOC.openapi, '3.1.0');
  const ids = new Set(), want = ['/api/v1/resolve', '/api/v1/codes/search', '/api/v1/notices', '/api/v1/buildings', '/api/v1/permits', '/api/v1/infra', '/api/v1/terrain', '/api/bus'];
  const TILE = '/api/v1/terrain';   // 지형 타일 중계: PNG 로 답하고 인증키를 쓰지 않아 503 이 없다(2026-10-10). 나머지 경로의 규칙은 그대로
  assert.deepEqual(Object.keys(DOC.paths).sort(), want.slice().sort());
  for (const [p, item] of Object.entries(DOC.paths)) {
    assert.deepEqual(Object.keys(item), ['get'], `${p} 는 GET 만`);
    const op = item.get;
    assert.ok(op.operationId && !ids.has(op.operationId), `${p} operationId`); ids.add(op.operationId);
    assert.ok(op.summary && op.description && op.tags && op.tags.length === 1, `${p} 설명·태그`);
    assert.ok(op.responses['200'] && op.responses['405'] && op.responses['502'] && (op.responses['503'] || p === TILE), `${p} 200·405·502·503 응답`);
    for (const prm of op.parameters) assert.ok(prm.name && prm.in === 'query' && prm.schema && prm.description, `${p} 매개변수 ${prm.name}`);
    const ct = Object.keys(op.responses['200'].content)[0]; assert.equal(ct, p === TILE ? 'image/png' : 'application/json');
    assert.ok(op.responses['200'].headers['Cache-Control'].description, `${p} 캐시 규칙 문서화`);
  }
  assert.equal(DOC.tags.length, 8);
});

test('OpenAPI 문서: 모든 $ref 가 풀리고, 모든 스키마의 required 가 properties 에 있으며, Problem 의 code 목록이 응답 문서와 맞는다', () => {
  const refs = [];
  (function walk(n) { if (Array.isArray(n)) n.forEach(walk); else if (n && typeof n === 'object') { if (typeof n.$ref === 'string') refs.push(n.$ref); Object.values(n).forEach(walk); } })(DOC);
  assert.ok(refs.length > 30);
  for (const r of refs) assert.ok(DOC.components.schemas[r.replace('#/components/schemas/', '')], `$ref ${r}`);
  for (const [name, s] of Object.entries(DOC.components.schemas)) {
    (function walk(n, at) { if (!n || typeof n !== 'object') return; if (Array.isArray(n)) return n.forEach((x, i) => walk(x, `${at}[${i}]`));
      if (n.required && n.properties) for (const k of n.required) assert.ok(k in n.properties, `${name}${at}: required ${k} 가 properties 에 없음`);
      for (const [k, v] of Object.entries(n)) walk(v, `${at}.${k}`); })(s, '');
  }
  const codes = DOC.components.schemas.Problem.properties.code.enum;
  for (const item of Object.values(DOC.paths)) for (const [status, r] of Object.entries(item.get.responses)) {
    if (status === '200' || !r.content || !r.content['application/problem+json']) continue;
    assert.ok(Number(status) >= 400, status);
  }
  for (const c of ['invalid-query', 'invalid-code', 'invalid-cell', 'unsupported-level', 'unknown-code', 'method', 'keys-exhausted', 'budget-exhausted', 'not-configured', 'upstream']) assert.ok(codes.includes(c), c);
});

/* ---------- ② 운영에서 받은 실제 응답 ---------- */
test('골든 픽스처(운영 응답): resolve 6종(시군구·법정동·필지·번들 지역·리·8자리)이 ResolveResponse 를 지킨다', () => {
  for (const f of ['resolve-sgg', 'resolve-bjd', 'resolve-pnu', 'resolve-bundle', 'resolve-ri', 'resolve-8digit', 'resolve-sgg-districts', 'resolve-project', 'resolve-project-bundle']) must('ResolveResponse', fixture(`${f}.json`), f);
  assert.deepEqual(fixture('resolve-sgg-districts.json').warnings, ['districts-merged']); assert.equal(fixture('resolve-sgg-districts.json').geometry.type, 'MultiPolygon');   // 구만 있는 시(화성)
  assert.ok(fixture('resolve-bjd.json').neighbors.length > 5 && fixture('resolve-bjd.json').neighbors.every((n) => n.bjd !== fixture('resolve-bjd.json').bjd));   // 이웃 법정동
  const rp = fixture('resolve-project.json'), rb = fixture('resolve-project-bundle.json');   // 사업 id 로 열기(2026-10-06 로컬 핸들러 + 레지스트리에서 받음: 레지스트리가 운영에 오르면 capture-fixtures 가 운영에서 받는다)
  assert.deepEqual([rp.type, /^PRJ-\d{5}-\d{4}$/.test(rp.canonical), rp.project.id === rp.canonical, rp.pnu === rp.project.pnus[0], rp.coverage.tier], ['project', true, true, true, 'none']);
  assert.deepEqual([rb.type, rb.coverage.tier, typeof rb.project.block, rb.pnu === rb.project.pnus[0]], ['project', 'A', 'string', true]);
  assert.equal(fixture('resolve-bundle.json').coverage.tier, 'A'); assert.equal(fixture('resolve-bjd.json').coverage.tier, 'none');
  assert.deepEqual(fixture('resolve-ri.json').warnings, ['ri-uses-umd-boundary']); assert.deepEqual(fixture('resolve-8digit.json').warnings, ['padded-8-digit']);
});

test('골든 픽스처: 검색·건물·인허가(건물대장 보강 포함)·기반시설(서울시·OSM 물러남·noBus 포함)·공고(LH 포함)·버스가 각 응답 스키마를 지킨다', () => {
  for (const f of ['search-name', 'search-jibun', 'search-place', 'search-code-bad']) must('SearchResponse', fixture(`${f}.json`), f);
  must('BuildingsResponse', fixture('buildings-cell.json'), 'buildings');
  for (const f of ['permits-deokpung', 'permits-gamil-ledger']) must('PermitsResponse', fixture(`${f}.json`), f);
  for (const f of ['infra-deokpung', 'infra-seoul', 'infra-seoul-osm', 'infra-seoul-nobus']) must('InfraResponse', fixture(`${f}.json`), f);
  must('BusResponse', fixture('bus-gyeyang.json'), 'bus');
  for (const f of ['notices-hanam', 'notices-asan', 'notices-none']) must('NoticesResponse', fixture(`${f}.json`), f);
  assert.ok(fixture('notices-hanam.json').items.length > 0 && fixture('notices-hanam.json').items.every((i) => /^https:\/\/(www\.myhome\.go\.kr|m\.myhome\.go\.kr|apply\.lh\.or\.kr)\//.test(i.url || 'https://www.myhome.go.kr/')));
  assert.equal(fixture('infra-seoul.json').meta.stopsSource, 'seoul'); assert.equal(fixture('infra-seoul.json').meta.noBus, undefined);   // TAGO 밖 서울은 서울시 정류소정보조회
  assert.ok(fixture('infra-seoul.json').stops.every((s) => /^seoul-/.test(s.id)) && fixture('infra-seoul.json').sources.some((s) => s.id === 'seoul-bus'));
  assert.equal(fixture('infra-seoul-osm.json').meta.stopsSource, 'osm');   // 서울시 조회가 안 될 때(또는 강릉 등 TAGO·서울 밖) OpenStreetMap 정류장
  const asan = fixture('notices-asan.json'); assert.ok(asan.items.some((i) => i.source === 'lh' && i.url.startsWith('https://apply.lh.or.kr/') && i.complex && i.units > 0), 'LH 공고는 공급정보로 단지명·세대수가 채워진다');
  assert.ok(asan.meta.lh > 0 && asan.meta.lhMatched >= 1 && asan.items.every((i) => i.source === 'lh' || i.source === 'myhome'));
  assert.equal(fixture('infra-seoul-nobus.json').meta.noBus, true); assert.ok(fixture('infra-seoul-nobus.json').meta.stopsError);   // OSM 도 못 받으면 noBus + stopsError
  assert.ok(fixture('permits-gamil-ledger.json').features.some((f) => f.properties.via === 'ledger') || fixture('permits-gamil-ledger.json').meta.ledger.used, '건물대장 보강 응답');
  assert.ok(fixture('search-place.json').items.some((i) => i.place === true), '장소 후보');
});

test('검증기 자체: 필수 항목 누락·형식·열거·패턴·문서에 없는 항목(Problem 외)·oneOf 를 잡아낸다(통과만 하는 시험이 아니다)', () => {
  const p = fixture('permits-deokpung.json');
  const mutate = (fn) => { const c = JSON.parse(JSON.stringify(p)); fn(c); return check('PermitsResponse', c); };
  assert.deepEqual(check('PermitsResponse', p), []);
  assert.ok(mutate((c) => delete c.meta.located).some((e) => /필수 항목 located/.test(e)));
  assert.ok(mutate((c) => { c.features[0].properties.status = '분양중'; }).some((e) => /계획\|건설 단계\|입주 단계/.test(e)));
  assert.ok(mutate((c) => { c.features[0].properties.pnu = '123'; }).some((e) => /패턴/.test(e)));
  assert.ok(mutate((c) => { c.features[0].properties.units = '30'; }).some((e) => /oneOf/.test(e)));
  assert.ok(mutate((c) => { c.features[0].properties.approvedAt = '2017-13-45'; }).some((e) => /oneOf|날짜/.test(e)));
  assert.ok(mutate((c) => { c.features[0].geometry.type = 'Point'; }).some((e) => /Polygon\|MultiPolygon/.test(e)));
  assert.ok(check('Problem', { type: '/problems/x', title: 't', status: 200, code: 'invalid-query', detail: 'd' }).length > 0);   // status 는 4xx·5xx
  assert.ok(check('SearchResponse', { items: [], meta: { q: 'a', count: 0, sources: ['모름'], asOf: '2026-10-05' } }).length > 0);
  assert.ok(check('Bbox', [1, 2, 3]).length > 0);
});

/* ---------- ③ 핸들러의 오류 응답 ---------- */
const clock = Date.parse('2026-10-05T03:00:00Z');
function harness(mod, over = {}) {
  const env = over.env || { DATA_GO_KR_KEY: 'K-TEST', VWORLD_KEY: 'VW-TEST', VWORLD_DOMAIN: 'localhost' }, now = () => clock;
  const calls = [];
  const handler = mod.createHandler({ env, now, sleep: async () => {}, cache: createCache({ persist: false, now }), pool: createKeyPool({ env, now, store: memoryStore() }), readCoverage: () => ({}), fetch: async (u) => { calls.push(String(u)); return (over.fetch || (() => { throw new Error('호출하면 안 됨'); }))(String(u)); } });
  return async (url, method = 'GET') => {
    const res = { headers: {}, statusCode: 0, body: '', setHeader(k, v) { this.headers[k.toLowerCase()] = v; }, end(b) { this.body = b; } };
    await handler({ method, url }, res);
    return { status: res.statusCode, headers: res.headers, json: res.body ? JSON.parse(res.body) : null, calls };
  };
}
const ok = (json) => ({ ok: true, status: 200, json: async () => json, text: async () => JSON.stringify(json) });
const raw = (status, text) => ({ ok: status < 400, status, json: async () => JSON.parse(text || 'null'), text: async () => text });
const API = { resolve: require('../../handlers/v1/resolve.js'), search: require('../../handlers/v1/codes/search.js'), notices: require('../../handlers/v1/notices.js'), buildings: require('../../handlers/v1/buildings.js'), permits: require('../../handlers/v1/permits.js'), infra: require('../../handlers/v1/infra.js'), bus: require('../../handlers/bus.js') };
const OPS = { resolve: '/api/v1/resolve', search: '/api/v1/codes/search', notices: '/api/v1/notices', buildings: '/api/v1/buildings', permits: '/api/v1/permits', infra: '/api/v1/infra' };
const documented = (path_, status) => Object.keys(DOC.paths[path_].get.responses).includes(String(status));

function expectProblem(r, path_, status, code, extra) {
  assert.equal(r.status, status, `${path_} ${code}`);
  assert.ok(documented(path_, status), `${path_} 가 ${status} 응답을 문서에 적지 않음`);
  must('Problem', r.json, `${path_} ${code}`);
  assert.equal(r.json.code, code); assert.equal(r.json.type, `/problems/${code}`); assert.equal(r.json.status, status);
  assert.match(r.headers['content-type'], /^application\/problem\+json/);
  assert.ok(!JSON.stringify(r.json).match(/K-TEST|VW-TEST/), '오류 응답에 키가 없다');
  if (extra) assert.deepEqual(Object.fromEntries(Object.entries(extra).map(([k]) => [k, r.json[k]])), extra);
}

test('오류 계약(공통): 모든 v1 경로가 POST 는 405(Allow), 모르는 쿼리는 400 invalid-query 를 Problem 모양으로 낸다', async () => {
  for (const [name, p] of Object.entries(OPS)) {
    const run = harness(API[name]);
    const post = await run(`${p}?bjd=4145010800`, 'POST'); expectProblem(post, p, 405, 'method'); assert.equal(post.headers.allow, 'GET, HEAD');
    const bad = await run(`${p}?zzz=1`); expectProblem(bad, p, 400, 'invalid-query');
  }
});

test('오류 계약: resolve(코드 형식·종류·시도 422·표에 없음 404+suggestions·키 없음 503), search(길이·near·키 없음 503), buildings(cell), permits·infra(법정동 형식)', async () => {
  const resolve = harness(API.resolve);
  expectProblem(await resolve('/api/v1/resolve?code=abc'), '/api/v1/resolve', 400, 'invalid-code', { reason: 'not-digits' });
  expectProblem(await resolve('/api/v1/resolve?bjd=41450'), '/api/v1/resolve', 400, 'invalid-code', { reason: 'type-mismatch' });
  expectProblem(await resolve('/api/v1/resolve?code=41450&sgg=41450'), '/api/v1/resolve', 400, 'invalid-query');
  expectProblem(await resolve('/api/v1/resolve?code=41'), '/api/v1/resolve', 422, 'unsupported-level');
  expectProblem(await harness(API.resolve, { env: {} })('/api/v1/resolve?bjd=4145011400'), '/api/v1/resolve', 503, 'not-configured');
  const none = harness(API.resolve, { fetch: () => ok({ RESULT: { resultCode: 'INFO-3' } }) });
  const nf = await none('/api/v1/resolve?bjd=4145011400'); expectProblem(nf, '/api/v1/resolve', 404, 'unknown-code', { sgg: '41450' });
  const quota = harness(API.resolve, { fetch: () => raw(429, '') }); const q429 = await quota('/api/v1/resolve?bjd=4145011400'); expectProblem(q429, '/api/v1/resolve', 429, 'keys-exhausted'); assert.ok(Number(q429.headers['retry-after']) > 0); assert.ok(q429.json.retryAfterSec > 0);
  const down = harness(API.resolve, { fetch: () => raw(503, '') }); expectProblem(await down('/api/v1/resolve?bjd=4145011400'), '/api/v1/resolve', 502, 'upstream');

  const search = harness(API.search);
  expectProblem(await search('/api/v1/codes/search?q=%EA%B0%80'), '/api/v1/codes/search', 400, 'invalid-query', { reason: 'too-short' });
  expectProblem(await search('/api/v1/codes/search?q=감일동&near=abc'), '/api/v1/codes/search', 400, 'invalid-query');
  expectProblem(await search('/api/v1/codes/search?q=감일동&limit=99'), '/api/v1/codes/search', 400, 'invalid-query');
  expectProblem(await harness(API.search, { env: {} })('/api/v1/codes/search?q=감일동'), '/api/v1/codes/search', 503, 'not-configured');

  const bld = harness(API.buildings);
  expectProblem(await bld('/api/v1/buildings?cell=1,2'), '/api/v1/buildings', 400, 'invalid-cell');
  expectProblem(await bld('/api/v1/buildings'), '/api/v1/buildings', 400, 'invalid-query');
  expectProblem(await harness(API.buildings, { env: {} })('/api/v1/buildings?cell=12721,3753'), '/api/v1/buildings', 503, 'not-configured');
  const one = harness(API.buildings, { env: { DATA_GO_KR_KEY: 'K-TEST', VWORLD_KEY: 'VW-TEST', BUILDINGS_UPSTREAM_PER_HOUR: '1' }, fetch: () => ok({ response: { status: 'NOT_FOUND' } }) });
  await one('/api/v1/buildings?cell=12721,3753'); const b429 = await one('/api/v1/buildings?cell=12722,3753'); expectProblem(b429, '/api/v1/buildings', 429, 'budget-exhausted'); assert.ok(Number(b429.headers['retry-after']) > 0);

  for (const bad of ['sgg=abc', 'sgg=4145011400']) expectProblem(await harness(API.notices)(`/api/v1/notices?${bad}`), '/api/v1/notices', 400, 'invalid-code');
  expectProblem(await harness(API.notices, { env: {} })('/api/v1/notices?sgg=41450'), '/api/v1/notices', 503, 'not-configured');
  expectProblem(await harness(API.notices)('/api/v1/notices'), '/api/v1/notices', 400, 'invalid-query');
  const nfn = harness(API.notices, { fetch: () => ok({ RESULT: { resultCode: 'INFO-3' } }) }); expectProblem(await nfn('/api/v1/notices?sgg=41450'), '/api/v1/notices', 404, 'unknown-code', { sgg: '41450' });
  for (const name of ['permits', 'infra']) {
    const p = OPS[name], run = harness(API[name]);
    expectProblem(await run(`${p}?bjd=abc`), p, 400, 'invalid-code');
    expectProblem(await run(`${p}?bjd=41450`), p, 400, 'invalid-code', { reason: 'type-mismatch' });
    expectProblem(await run(p), p, 400, 'invalid-query');
    expectProblem(await harness(API[name], { env: {} })(`${p}?bjd=4145010800`), p, 503, 'not-configured');
  }
});

test('오류 계약: /api/bus 는 옛 모양 {error} 를 BusError 로 문서화하고 그대로 낸다', async () => {
  const run = harness(API.bus);
  for (const [url, status, error, method] of [['/api/bus', 400, 'query'], ['/api/bus?region=Bad_Slug', 400, 'query'], ['/api/bus?region=nowhere', 404, 'no-live-routes'], ['/api/bus?region=incheon-gyeyang', 405, 'method', 'POST']]) {
    const r = await run(url, method || 'GET'); assert.equal(r.status, status, url); must('BusError', r.json, url); assert.equal(r.json.error, error); assert.ok(Object.keys(DOC.paths['/api/bus'].get.responses).includes(String(status)), `/api/bus ${status} 문서화`);
  }
  assert.equal(Object.keys(DOC.paths['/api/bus'].get.responses).filter((s) => s !== '200').every((s) => Object.keys(DOC.paths['/api/bus'].get.responses[s].content)[0] === 'application/json'), true);
});

/* ---------- ④ 문서의 매개변수 = 핸들러가 받는 이름 ---------- */
test('문서의 쿼리 매개변수 이름이 핸들러의 허용 목록(ALLOWED)과 같다(문서와 코드가 어긋나면 깨진다)', () => {
  const files = { '/api/v1/resolve': 'handlers/v1/resolve.js', '/api/v1/codes/search': 'handlers/v1/codes/search.js', '/api/v1/notices': 'handlers/v1/notices.js', '/api/v1/buildings': 'handlers/v1/buildings.js', '/api/v1/permits': 'handlers/v1/permits.js', '/api/v1/infra': 'handlers/v1/infra.js', '/api/v1/terrain': 'handlers/v1/terrain.js' };
  for (const [p, f] of Object.entries(files)) {
    const m = /const ALLOWED = new Set\(\[([^\]]*)\]\)/.exec(fs.readFileSync(path.join(ROOT, f), 'utf8'));
    assert.ok(m, `${f} 에 ALLOWED 가 있어야 한다`);
    const code = [...m[1].matchAll(/'([a-z]+)'/g)].map((x) => x[1]).sort();
    const doc = DOC.paths[p].get.parameters.map((x) => x.name).sort();
    assert.deepEqual(doc, code, `${p} 문서 매개변수와 코드 허용 목록`);
  }
  const bus = fs.readFileSync(path.join(ROOT, 'handlers/bus.js'), 'utf8');
  assert.match(bus, /keys\[0\] !== 'region'/); assert.deepEqual(DOC.paths['/api/bus'].get.parameters.map((x) => x.name), ['region']);
});

test('문서의 캐시 규칙이 코드와 같다: 200 의 Cache-Control 문구가 각 핸들러 소스의 s-maxage 값과 일치', () => {
  const src = (f) => fs.readFileSync(path.join(ROOT, f), 'utf8');
  const want = { '/api/v1/resolve': ['handlers/v1/resolve.js', 's-maxage=300'], '/api/v1/codes/search': ['handlers/v1/codes/search.js', 's-maxage=3600'], '/api/v1/notices': ['handlers/v1/notices.js', 's-maxage=3600'], '/api/v1/buildings': ['handlers/v1/buildings.js', 's-maxage=86400'], '/api/v1/permits': ['handlers/v1/permits.js', 's-maxage=86400'], '/api/v1/infra': ['handlers/v1/infra.js', 's-maxage=86400'], '/api/v1/terrain': ['handlers/v1/terrain.js', 's-maxage=31536000'] };
  for (const [p, [f, s]] of Object.entries(want)) {
    assert.ok(DOC.paths[p].get.responses['200'].headers['Cache-Control'].description.includes(s), `${p} 문서`);
    assert.ok(src(f).includes(s), `${p} 코드에 ${s}`);
  }
});

test('사람이 읽는 API 정의서(docs/data-interface/API-정의서.md)가 openapi.json·픽스처에서 만든 것과 같다(고쳤으면 node scripts/gen-api-docs.js)', () => {
  const { build, OUT } = require('../../scripts/gen-api-docs.js');
  const text = build();
  assert.equal(fs.readFileSync(OUT, 'utf8'), text, 'API-정의서.md 가 최신이 아님: node scripts/gen-api-docs.js');
  for (const op of Object.keys(DOC.paths)) assert.ok(text.includes(`\`GET ${op}\``), op);
  for (const n of Object.keys(DOC.components.schemas)) if (!['BuildingProperties', 'PermitProject', 'InfraSource', 'School', 'Stop', 'SearchItem', 'BusError'].includes(n)) assert.ok(text.includes(n), `정의서에 ${n}`);
  assert.doesNotMatch(text, /undefined|\[object Object\]/);
});
