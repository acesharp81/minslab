'use strict';
/* registry/projects.json(저장소에 올라가는 사업 레지스트리)이 일관되고, lib/registry.js 가 없거나 깨진 파일에도 서버를 막지 않는지 확인한다. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const P = require('../../lib/projects.js');
const { readRegistry, writeRegistry, DEFAULT_FILE } = require('../../lib/registry.js');

const ROOT = path.join(__dirname, '..', '..');
const REAL = JSON.parse(fs.readFileSync(DEFAULT_FILE, 'utf8'));

test('저장소의 registry/projects.json 은 일관성 검사를 통과한다(id 형식·중복 없음·참조 유일·counters·위치 법정동)', () => {
  assert.deepEqual(P.validateRegistry(REAL), []);
});

test('참조 값은 숫자 변환 흔적이 없다(22자리 관리번호가 부동소수 표기 1e+21 이 되면 서로 다른 사업이 한 사업이 된다)', () => {
  for (const p of REAL.projects) for (const r of p.refs) {
    assert.equal(typeof r.value, 'string', `${p.id} ${r.value}`);
    assert.doesNotMatch(r.value, /[eE][+-]?\d|\./, `${p.id}: 부동소수 표기 ${r.value}`);
    if (r.system === 'hub-hs-basis') assert.match(r.value, /^\d{1,22}$/, `${p.id}: 관리번호 형식 ${r.value}`);
  }
  const long = REAL.projects.flatMap((p) => p.refs).filter((r) => r.value.length > 15);
  assert.equal(new Set(long.map((r) => r.value)).size, long.length, '22자리 관리번호가 서로 다르게 보관된다');
});

test('번들 단지는 모두 사업 id 를 받았고 위치(필지·법정동)가 연결돼 있다(--link-pnu)', () => {
  const index = P.indexRegistry(REAL), regions = JSON.parse(fs.readFileSync(path.join(ROOT, 'regions', 'index.json'), 'utf8')).regions;
  assert.ok(regions.length >= 3);
  for (const r of regions) {
    const dir = path.join(ROOT, 'regions', r.slug), region = JSON.parse(fs.readFileSync(path.join(dir, 'region.json'), 'utf8')), projects = JSON.parse(fs.readFileSync(path.join(dir, 'projects.json'), 'utf8')).projects;
    for (const bp of projects) {
      const hit = index.byRef.get(P.refKey({ system: 'bundle', key: r.slug, value: bp.id }));
      assert.ok(hit, `${r.slug}/${bp.id} 에 사업 id 가 없음 — node scripts/issue-projects.js --region ${r.slug} --link-pnu`);
      const sgg = region.codes.find((c) => c.type === 'sigungu').code;
      assert.equal(hit.sgg, sgg); assert.equal(hit.pnus.length, 1, `${hit.id}: 필지가 연결되지 않음`); assert.equal(hit.pnus[0].slice(0, 5), sgg.length === 5 ? hit.pnus[0].slice(0, 5) : sgg);
      assert.equal(hit.name, bp.name);
    }
  }
});

test('readRegistry: 파일이 없으면 빈 레지스트리, 깨졌으면 빈 레지스트리 + invalid(서버는 막히지 않는다), 고치면 바로 다시 읽는다', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rg-')), file = path.join(dir, 'projects.json'), err = console.error; const logged = [];
  console.error = (m) => logged.push(String(m));
  try {
    const none = readRegistry(file); assert.equal(none.missing, true); assert.equal(none.index.byId.size, 0); assert.deepEqual(none.registry.projects, []);
    fs.writeFileSync(file, '{ 깨진 json'); const bad = readRegistry(file); assert.ok(bad.invalid && bad.invalid.length); assert.equal(bad.index.byId.size, 0); assert.equal(logged.length, 1); assert.match(logged[0], /빈 레지스트리로 동작/);
    readRegistry(file); assert.equal(logged.length, 1, '같은 파일 상태에서는 다시 읽지도 다시 로그를 남기지도 않는다');
    const broken = { ...REAL, projects: [REAL.projects[0], { ...REAL.projects[0] }] }; fs.writeFileSync(file, JSON.stringify(broken)); fs.utimesSync(file, new Date(), new Date(Date.now() + 5000));
    const dup = readRegistry(file); assert.ok(dup.invalid.some((e) => /중복/.test(e))); assert.equal(dup.index.byId.size, 0, '일관성 검사를 통과하지 못하면 쓰지 않는다');
    writeRegistry(REAL, file); fs.utimesSync(file, new Date(), new Date(Date.now() + 10000));
    const good = readRegistry(file); assert.equal(good.invalid, undefined); assert.equal(good.index.byId.size, REAL.projects.length);
    assert.equal(fs.readFileSync(file, 'utf8').endsWith('}\n'), true, '끝에 줄바꿈');
  } finally { console.error = err; fs.rmSync(dir, { recursive: true, force: true }); }
});

test('기본 경로는 저장소의 registry/projects.json 이고 next.config.ts 가 resolve·permits 함수에 이 파일을 포함시킨다', () => {
  assert.equal(path.relative(ROOT, DEFAULT_FILE), path.join('registry', 'projects.json'));
  const inc = require('../../next.config.ts').default.outputFileTracingIncludes;
  assert.ok(inc['/api/v1/resolve'].includes('./registry/projects.json')); assert.ok(inc['/api/v1/permits'].includes('./registry/projects.json'));
  assert.ok(!('/api/v1/notices' in inc), '공고 함수는 레지스트리를 쓰지 않는다');
});

