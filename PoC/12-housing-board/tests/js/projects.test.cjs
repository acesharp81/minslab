'use strict';
/* lib/projects.js — 사업 id 형식·6단계 매핑·레코드 만들기·발급(같은 입력 → 같은 id, 변경허가로 refs 가 늘어도 같은 사업, 합병)·조회. 네트워크·파일 없음. */
const test = require('node:test');
const assert = require('node:assert/strict');
const P = require('../../lib/projects.js');

const NOW = Date.parse('2026-10-06T03:00:00Z');
const hub = (over) => ({ pnu: '4145010800105690000', name: '덕풍아파트', units: 100, status: '건설 단계', approvedAt: '2024-01-01', refs: ['11111'], latestRef: '11111', ...over });
const cand = (over, bjd = '4145010800') => P.fromPermit(hub(over), { bjd, asOf: '2026-10-06' });

test('id: 형식 PRJ-{시군구5}-{일련4}, 만들기·읽기·범위', () => {
  assert.equal(P.formatId('28245', 3), 'PRJ-28245-0003'); assert.equal(P.formatId('41450', 9999), 'PRJ-41450-9999');
  assert.deepEqual(P.parseId('PRJ-28245-0003'), { sgg: '28245', serial: 3 }); assert.deepEqual(P.parseId(' PRJ-41450-0120 '), { sgg: '41450', serial: 120 });
  for (const bad of ['PRJ-2824-0003', 'PRJ-28245-003', 'prj-28245-0003', 'PRJ-28245-00003', '28245', '', null, 'PRJ-28245-0003x']) assert.equal(P.parseId(bad), null, String(bad));
  assert.throws(() => P.formatId('28245', 0)); assert.throws(() => P.formatId('28245', 10000)); assert.throws(() => P.formatId('2824', 1)); assert.throws(() => P.formatId('28245', 1.5));
  assert.ok(P.ID_RE.test('PRJ-28245-0003'));
});

test('stageOf: 9.2 제안 매핑(계획은 사업승인이 있으면 03, 없으면 02)', () => {
  assert.equal(P.stageOf('입주 단계'), '06'); assert.equal(P.stageOf('분양중'), '05'); assert.equal(P.stageOf('건설 단계'), '04'); assert.equal(P.stageOf('준공 임박'), '04');
  assert.equal(P.stageOf('계획', { approvedAt: '2024-01-01' }), '03'); assert.equal(P.stageOf('계획', {}), '02'); assert.equal(P.stageOf('계획'), '02'); assert.equal(P.stageOf('모르는 상태'), '02');
  for (const code of Object.keys(P.STAGES)) assert.match(code, /^0[1-6]$/);
});

test('fromPermit: 건축HUB 사업 → 사업 레코드(번지 하나, 관리번호는 문자열 참조, 앞 0·자릿수 보존)', () => {
  const c = P.fromPermit(hub({ refs: ['0000123', '12345678901234567890123'], latestRef: '0000123' }), { bjd: '4145010800', asOf: '2026-10-06' });
  assert.deepEqual({ ...c, approvedAt: undefined }, { sgg: '41450', bjdCodes: ['4145010800'], pnus: ['4145010800105690000'], stageCode: '04', source: P.HUB_SOURCE, asOf: '2026-10-06', approvedAt: undefined,
    refs: [{ system: 'hub-hs-basis', key: 'mgmHsrgstPk', value: '0000123', asOf: '2026-10-06' }, { system: 'hub-hs-basis', key: 'mgmHsrgstPk', value: '12345678901234567890123', asOf: '2026-10-06' }], name: '덕풍아파트', units: 100 });
  assert.equal(c.refs.every((r) => typeof r.value === 'string'), true); assert.equal(c.approvedAt, '2024-01-01');
  const block = P.fromPermit(hub({ pnu: null, refs: [], latestRef: '77' }), { bjd: '4145011400', asOf: '2026-10-06' });                       // 블록 단위 허가: 위치(PNU)가 없고 latestRef 만
  assert.deepEqual([block.pnus, block.bjdCodes, block.refs.map((r) => r.value)], [[], ['4145011400'], ['77']]);
  const moved = P.fromPermit(hub({ pnu: '4145011400103160002', refs: [], latestRef: '88' }), { bjd: '4145010800', asOf: '2026-10-06' });                    // 건물대장으로 찾은 필지가 다른 법정동에 있다
  assert.deepEqual([moved.bjdCodes, moved.pnus], [['4145010800', '4145011400'], ['4145011400103160002']]);
  assert.deepEqual(P.validateRegistry(P.issue(P.emptyRegistry(), [moved], { now: NOW }).registry), [], '필지의 법정동이 bjdCodes 에 있어 일관성 검사를 통과한다');
  assert.equal(P.fromPermit(hub({ refs: [], latestRef: null }), { bjd: '4145010800', asOf: 'x' }), null, '관리번호가 없으면 신원을 못 잡는다');
  assert.equal(P.fromPermit(hub({ pnu: null }), { bjd: null, asOf: 'x' }), null, '법정동도 PNU 도 없으면 못 만든다');
  assert.equal(P.fromPermit(null, { bjd: '4145010800' }), null);
  assert.equal('units' in P.fromPermit(hub({ units: null }), { bjd: '4145010800', asOf: 'x' }), false); assert.equal('name' in P.fromPermit(hub({ name: ' ' }), { bjd: '4145010800', asOf: 'x' }), false);
});

test('fromBundleProject: 번들 단지 → 사업 레코드(시군구는 region.codes, 참조는 bundle/<slug>/<단지 id>)', () => {
  const region = { slug: 'incheon-gyeyang', codes: [{ code: '28245', type: 'sigungu', name: '계양구' }] };
  const c = P.fromBundleProject({ id: 'techno-A2', name: '인천계양 테크노밸리 A2 블록', status: '준공 임박', units: 747 }, region, { asOf: '2026-10-06' });
  assert.deepEqual(c, { sgg: '28245', bjdCodes: [], pnus: [], stageCode: '04', asOf: '2026-10-06', source: { provider: '주택파동 지도 번들', dataset: 'regions/incheon-gyeyang/projects.json' },
    refs: [{ system: 'bundle', key: 'incheon-gyeyang', value: 'techno-A2', asOf: '2026-10-06' }], name: '인천계양 테크노밸리 A2 블록', units: 747 });
  assert.equal(P.fromBundleProject({ id: 'x' }, { slug: 's', codes: [] }, { asOf: 'x' }), null); assert.equal(P.fromBundleProject({}, region, { asOf: 'x' }), null);
});

test('issue: 시군구별로 0001 부터, 사업승인일 순(같은 입력 → 같은 번호), 입력은 바꾸지 않는다', () => {
  const a = cand({ pnu: '4145010800105690000', refs: ['1'], latestRef: '1', approvedAt: '2024-05-01', name: '나중' });
  const b = cand({ pnu: '4145010800105700000', refs: ['2'], latestRef: '2', approvedAt: '2023-01-01', name: '먼저' });
  const seoul = P.fromPermit(hub({ pnu: '1129013800103160002', refs: ['9'], latestRef: '9' }), { bjd: '1129013800', asOf: '2026-10-06' });
  const empty = P.emptyRegistry(); const frozen = JSON.stringify(empty);
  const r = P.issue(empty, [a, seoul, b], { now: NOW });
  assert.equal(JSON.stringify(empty), frozen);
  assert.deepEqual(r.issued, ['PRJ-41450-0001', 'PRJ-41450-0002', 'PRJ-11290-0001'].sort((x, y) => (r.issued.indexOf(x) - r.issued.indexOf(y))));
  const names = Object.fromEntries(r.registry.projects.map((p) => [p.id, p.name]));
  assert.equal(names['PRJ-41450-0001'], '먼저'); assert.equal(names['PRJ-41450-0002'], '나중'); assert.equal(r.registry.projects.find((p) => p.sgg === '11290').id, 'PRJ-11290-0001');
  assert.deepEqual(r.registry.counters, { '41450': 2, '11290': 1 }); assert.equal(r.registry.updatedAt, '2026-10-06'); assert.deepEqual(r.registry.projects.map((p) => p.id), [...r.registry.projects.map((p) => p.id)].sort());
  assert.equal(r.registry.projects.every((p) => p.issuedAt === '2026-10-06' && !('approvedAt' in p)), true);
  assert.deepEqual(P.validateRegistry(r.registry), []);
  const again = P.issue(empty, [b, seoul, a], { now: NOW });                                                                                   // 입력 순서가 달라도 같은 번호
  assert.deepEqual(again.registry.projects.map((p) => [p.id, p.name]), r.registry.projects.map((p) => [p.id, p.name]));
});

test('issue: 같은 사업을 다시 만나면 같은 id — 단계·세대수는 새로, 변경허가로 관리번호가 늘어도 참조가 겹치면 같은 사업', () => {
  const r1 = P.issue(P.emptyRegistry(), [cand({ refs: ['1'], latestRef: '1', status: '계획', units: 90 })], { now: NOW });
  assert.equal(r1.registry.projects[0].stageCode, '03');
  const r2 = P.issue(r1.registry, [cand({ refs: ['1', '5'], latestRef: '5', status: '건설 단계', units: 100 })], { now: NOW + 86400000 });
  assert.deepEqual([r2.issued, r2.updated], [[], ['PRJ-41450-0001']]); assert.equal(r2.registry.projects.length, 1);
  const p = r2.registry.projects[0];
  assert.deepEqual([p.id, p.stageCode, p.units, p.issuedAt, p.refs.map((x) => x.value)], ['PRJ-41450-0001', '04', 100, '2026-10-06', ['1', '5']]);
  const r3 = P.issue(r2.registry, [cand({ refs: ['5'], latestRef: '5' })], { now: NOW });                                                     // 나중에는 새 관리번호 하나만 와도 이어진다
  assert.deepEqual([r3.issued, r3.registry.projects.length], [[], 1]);
  const moved = P.issue(r3.registry, [cand({ pnu: '4145010800105690001', refs: ['5'], latestRef: '5' })], { now: NOW });                       // 지번이 바뀌어도(합필) 위치는 쌓인다
  assert.deepEqual(moved.registry.projects[0].pnus, ['4145010800105690000', '4145010800105690001']);
  const noPos = P.issue(r3.registry, [{ ...cand({ refs: ['5'], latestRef: '5' }), pnus: [] }], { now: NOW }); assert.deepEqual(noPos.registry.projects[0].pnus, ['4145010800105690000'], '후보에 위치가 없어도 기존 위치를 지우지 않는다');
});

test('issue: 후보가 두 사업과 참조를 공유하면 합병 — 일련이 작은 쪽이 남고 나머지는 supersededBy, 번호는 다시 쓰지 않는다', () => {
  let reg = P.issue(P.emptyRegistry(), [cand({ pnu: '4145010800105690000', refs: ['1'], latestRef: '1', approvedAt: '2023-01-01' }), cand({ pnu: '4145010800105700000', refs: ['2'], latestRef: '2', approvedAt: '2024-01-01' })], { now: NOW }).registry;
  assert.deepEqual(reg.projects.map((p) => p.id), ['PRJ-41450-0001', 'PRJ-41450-0002']);
  const m = P.issue(reg, [cand({ pnu: '4145010800105690000', refs: ['1', '2'], latestRef: '2' })], { now: NOW });
  assert.deepEqual(m.merged, [{ from: 'PRJ-41450-0002', into: 'PRJ-41450-0001' }]); assert.deepEqual(P.validateRegistry(m.registry), []);
  const idx = P.indexRegistry(m.registry);
  assert.deepEqual([P.lookup(idx, 'PRJ-41450-0002').project.id, P.lookup(idx, 'PRJ-41450-0002').followed], ['PRJ-41450-0001', ['PRJ-41450-0002']]);
  assert.deepEqual(P.lookup(idx, 'PRJ-41450-0001').followed, []); assert.equal(P.lookup(idx, 'PRJ-41450-0099'), null); assert.equal(P.lookup(idx, 'x'), null);
  const next = P.issue(m.registry, [cand({ pnu: '4145010800105800000', refs: ['3'], latestRef: '3' })], { now: NOW });                           // 합병으로 비운 0002 를 다시 쓰지 않는다
  assert.deepEqual(next.issued, ['PRJ-41450-0003']);
  const counterOnly = { ...P.emptyRegistry(), counters: { '41450': 7 } };                                                                       // 삭제된 번호도 counters 로 기억한다
  assert.deepEqual(P.issue(counterOnly, [cand({})], { now: NOW }).issued, ['PRJ-41450-0008']);
});

test('issue: 신원을 못 잡는 후보(참조·시군구 없음)는 건너뛰고 이유를 알린다. 9999 를 넘으면 오류', () => {
  const r = P.issue(P.emptyRegistry(), [{ sgg: '41450', refs: [], name: '이름만' }, { refs: [{ system: 'a', key: 'b', value: 'c' }], name: '시군구없음' }, null, cand({})], { now: NOW });
  assert.equal(r.issued.length, 1); assert.equal(r.skipped.length, 2); assert.ok(r.skipped.some((x) => /이름만/.test(x)) && r.skipped.some((x) => /시군구없음/.test(x)));
  assert.throws(() => P.issue({ ...P.emptyRegistry(), counters: { '41450': 9999 } }, [cand({})], { now: NOW }), /9999/);
});

test('projectIdFor·indexRegistry: 관리번호(참조)가 우선, 없으면 PNU. 폐기된 사업의 참조·위치는 남은 사업으로', () => {
  const reg = P.issue(P.emptyRegistry(), [cand({ refs: ['1', '5'], latestRef: '5' })], { now: NOW }).registry, idx = P.indexRegistry(reg);
  assert.equal(P.projectIdFor(idx, { refs: ['5'], pnu: '9999999999999999999' }), 'PRJ-41450-0001');
  assert.equal(P.projectIdFor(idx, { refs: [], latestRef: '1' }), 'PRJ-41450-0001');
  assert.equal(P.projectIdFor(idx, { refs: ['999'], pnu: '4145010800105690000' }), 'PRJ-41450-0001', '참조가 안 맞아도 PNU 로');
  assert.equal(P.projectIdFor(idx, { refs: ['999'], pnu: '4145010800105999999' }), null); assert.equal(P.projectIdFor(idx, null), null); assert.equal(P.projectIdFor(idx, {}), null);
  assert.equal(P.projectIdFor(P.indexRegistry(P.emptyRegistry()), { refs: ['1'] }), null);
});

test('validateRegistry: 깨진 레지스트리를 걸러낸다(중복 id·참조 겹침·counters 부족·위치 법정동 불일치·값 형식)', () => {
  const good = P.issue(P.emptyRegistry(), [cand({ refs: ['1'], latestRef: '1' }), cand({ pnu: '4145010800105700000', refs: ['2'], latestRef: '2' })], { now: NOW }).registry;
  assert.deepEqual(P.validateRegistry(good), []);
  const clone = () => JSON.parse(JSON.stringify(good));
  const t = (mut, re) => { const r = clone(); mut(r); const e = P.validateRegistry(r); assert.ok(e.some((x) => re.test(x)), `${re}: ${e.join(' | ')}`); };
  t((r) => { r.projects[1].id = r.projects[0].id; }, /중복/); t((r) => { r.projects[0].id = 'PRJ-1-1'; }, /형식/);
  t((r) => { r.projects[1].refs = r.projects[0].refs; }, /겹침/); t((r) => { r.counters['41450'] = 1; }, /counters/); t((r) => { delete r.counters; }, /counters/);
  t((r) => { r.projects[0].pnus = ['1129013800103160002']; }, /법정동이 bjdCodes 에 없음/); t((r) => { r.projects[0].pnus = ['123']; }, /19자리/);
  t((r) => { r.projects[0].refs[0].value = 123; }, /문자열/); t((r) => { r.projects[0].refs = []; }, /refs/); t((r) => { r.projects[0].stageCode = '07'; }, /stageCode/);
  t((r) => { r.projects[0].asOf = '2026/10/06'; }, /asOf/); t((r) => { r.projects[0].source = {}; }, /source/); t((r) => { r.projects[0].issuedAt = null; }, /issuedAt/);
  t((r) => { r.projects[0].supersededBy = 'PRJ-41450-0099'; }, /가리키는 사업이 없음/); t((r) => { r.projects[0].supersededBy = r.projects[1].id; r.projects[1].supersededBy = r.projects[0].id; }, /돌고 있음/);
  assert.deepEqual(P.validateRegistry({ schema: 'x' }), ['schema 가 project-registry/1 이어야 함']); assert.ok(P.validateRegistry(null).length); assert.ok(P.validateRegistry({ schema: P.SCHEMA }).length);
});
