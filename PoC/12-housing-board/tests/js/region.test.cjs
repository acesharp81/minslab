'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const R = require('../../assets/js/region.js');

const RING = [[126.78, 35.15], [126.79, 35.15], [126.79, 35.16], [126.78, 35.16]];
const mkProject = (over = {}) => Object.assign({
  id: 'z1-A1', label: 'A-1', name: '테스트 A-1', sponsor: { name: 'LH', type: 'public' }, sponsorClass: 'public',
  kind: '공공분양', status: '분양중', units: 100, dongCount: 2,
  outline: { tier: 'official', poly: RING, how: 'V-World 공식 블록(LT_C_LHBLPN)' },
  dongs: [{ no: '101', tier: 'schematic', floorsAbove: 15, poly: [RING] }, { no: '102', tier: 'schematic', floorsAbove: 12, poly: [RING] }],
  sources: ['src-a', 'src-b'],
}, over);
const mkRegion = (over = {}) => Object.assign({
  schema_version: '1.1.0', slug: 'r1', name: '테스트구', title: '주택파동 · 테스트구', description: '설명', updatedAt: '2026-10-04',
  view: { center: [126.785, 35.155], zoom: 15, pitch: 52 }, codes: [],
  zones: [{ id: 'z1', name: '테스트 지구', type: '공공주택지구', publicLand: true, poly: RING }],
  sources: [{ id: 'src-a', label: '출처 A', redistributable: 'unknown' }, { id: 'src-b', label: '출처 B', redistributable: 'unknown' }, { id: 'lh-cwstt', label: 'LH 공사현황', redistributable: 'unknown' }],
  statusOrder: ['계획', '분양중', '건설 단계', '준공 임박', '입주 단계'],
}, over);
const mkRaw = (projects = [mkProject()], region = mkRegion(), extra = {}) => Object.assign({
  index: { schema_version: '1.1.0', regions: [{ slug: 'r1', name: '테스트구', default: true, visibility: 'public' }] },
  entry: { slug: 'r1', name: '테스트구', default: true, visibility: 'public' },
  region, projects: { schema_version: '1.1.0', projects }, buildings: { type: 'FeatureCollection', meta: { basis: '20261004' }, features: [] },
  context: { stations: [{ name: '역', lon: 126.78, lat: 35.15 }], schools: [], asOf: '2026-10-04', source: '© OpenStreetMap contributors (ODbL)' },
}, extra);

test('pickRegion: 기본 지역, ?region=, 모르는 slug, 빈 목록', () => {
  const index = { regions: [{ slug: 'a', name: 'A' }, { slug: 'b', name: 'B', default: true }] };
  assert.equal(R.pickRegion(index, '').region.slug, 'b');
  assert.equal(R.pickRegion(index, '?region=a').region.slug, 'a');
  const bad = R.pickRegion(index, '?region=zzz');
  assert.equal(bad.error, 'unknown'); assert.equal(bad.requested, 'zzz'); assert.equal(bad.regions.length, 2);
  assert.equal(R.pickRegion({ regions: [{ slug: 'x', name: 'X' }] }, '').region.slug, 'x');  // default 가 없으면 첫 지역
  assert.equal(R.pickRegion({ regions: [] }, '').error, 'empty');
});

test('moveInText: 입주 단계인데 날짜가 없으면 "입주 시기 미정"이 아니라 "입주 일자 미상"', () => {
  assert.equal(R.moveInText(null, undefined, '입주 단계'), '입주 일자 미상');
  assert.equal(R.moveInText('', null, '입주 단계'), '입주 일자 미상');
  assert.equal(R.moveInText('2026-09', null, '입주 단계'), '2026.09');
  assert.equal(R.moveInText(null, undefined, '건설 단계'), '입주 시기 미정');
});

test('adaptProject: 입주 단계 단지의 moveIn 문구에 상태가 반영된다', () => {
  const p = mkProject({ status: '입주 단계', moveIn: null, progress: null });
  assert.equal(R.adaptProject(p, mkRegion()).moveIn, '입주 일자 미상');
});

test('moveInText: 입주 월, 날짜, 종료일 대체, 미정', () => {
  assert.equal(R.moveInText('2029-06', null), '2029.06');
  assert.equal(R.moveInText('2028-09-30', null), '준공 예정 2028-09-30');
  assert.equal(R.moveInText(null, '2029-01-08'), '준공 예정 2029-01-08');
  assert.equal(R.moveInText(undefined, undefined), '입주 시기 미정');
  assert.equal(R.moveInText('', undefined), '입주 시기 미정');
});

test('adaptProject: 필드 매핑과 id=label, pid 보존', () => {
  const p = mkProject({ moveIn: '2029-06', builder: '시공사', contractAmountM: 1234.5, note: '메모', progress: { rate: 3.5, asOf: '2026-10-01', start: '2026-01-01', end: '2029-03-22', source: 'lh-cwstt' } });
  const b = R.adaptProject(p, mkRegion());
  assert.equal(b.id, 'A-1'); assert.equal(b.pid, 'z1-A1'); assert.equal(b.label, 'A-1');
  assert.equal(b.kind, '공공분양'); assert.equal(b.status, '분양중'); assert.equal(b.units, 100); assert.equal(b.unitsKnown, true);
  assert.equal(b.moveIn, '2029.06'); assert.equal(b.builder, '시공사'); assert.equal(b.contractM, 1234.5); assert.equal(b.note, '메모');
  assert.deepEqual(b.poly, RING); assert.equal(b.priv, false);
  assert.deepEqual(b.progress, { rate: 3.5, asOf: '2026-10-01', history: [], start: '2026-01-01', end: '2029-03-22', source: 'lh-cwstt' });
  assert.deepEqual(b.dongs.map((d) => [d.no, d.floors]), [['101', 15], ['102', 12]]);
  assert.equal(b.dongs[0].poly[0].length, 4);
  assert.equal(b.src, '출처 A · 출처 B');
  assert.equal(b.outlineHow, '블록 윤곽은 공식 자료 (V-World 공식 블록(LT_C_LHBLPN))');
});

test('adaptProject: 민간 단지, units 없음, progress 없음, dongs 없음', () => {
  const b = R.adaptProject(mkProject({ sponsorClass: 'private_on_public_land', units: null, dongs: undefined, dongCount: undefined, sources: undefined }), mkRegion());
  assert.equal(b.priv, true); assert.equal(b.units, 0); assert.equal(b.unitsKnown, false);
  assert.equal(b.progress, undefined); assert.equal(b.dongs, undefined); assert.equal(b.dongCount, 0); assert.equal(b.src, '');
  assert.equal(b.moveIn, '입주 시기 미정');
});

test('동: 층수·높이 모두 없으면 3D에서 뺀다, 높이만 있으면 층수를 추정, heightM 우선', () => {
  const dongs = [
    { no: '1', tier: 'building', poly: [RING] },
    { no: '2', tier: 'building', heightM: 57, poly: [RING] },
    { no: '3', tier: 'building', floorsAbove: 20, heightM: 59.35, poly: [RING] },
    { no: '4', tier: 'building', floorsAbove: 0, poly: [RING] },
  ];
  const b = R.adaptProject(mkProject({ dongs, dongCount: 4 }), mkRegion());
  assert.deepEqual(b.dongs.map((d) => d.no), ['2', '3']);
  assert.equal(b.dongs[0].floors, 20); assert.equal(b.dongs[0].h, 57);
  assert.equal(b.dongs[1].floors, 20); assert.equal(b.dongs[1].h, 59.35);
});

test('같은 label 이 둘이면 내부 id 를 구분한다', () => {
  const r = R.adaptBundle(mkRaw([mkProject({ id: 'a-A1' }), mkProject({ id: 'b-A1' }), mkProject({ id: 'c-B2', label: 'B-2' })]));
  const ids = r.blocks.map((b) => b.id);
  assert.equal(new Set(ids).size, 3);
  assert.deepEqual(r.blocks.map((b) => b.pid).sort(), ['a-A1', 'b-A1', 'c-B2']);
  assert.ok(ids.includes('B-2'));
});

test('같은 label 의 구분 접미사(·2)는 파일 순서가 아니라 화면에 보이는 순서를 따른다', () => {
  const r = R.adaptBundle(mkRaw([mkProject({ id: 'small', units: 10 }), mkProject({ id: 'big', units: 500 })]));   // 파일에는 작은 단지가 먼저
  assert.deepEqual(r.blocks.map((b) => [b.pid, b.id]), [['big', 'A-1'], ['small', 'A-1·2']]);
});

test('문구: 역·학교 문장은 마침표로 끝난다', () => {
  const r = R.adaptBundle(mkRaw());
  assert.match(r.texts.footerHtml, /역·학교는 OpenStreetMap입니다\.(<|$)/);
});

test('orderProjects: projectOrder, 상태 순서, 세대수, label', () => {
  const ps = [
    mkProject({ id: 'p1', label: 'P1', status: '계획', units: 900 }),
    mkProject({ id: 'p2', label: 'P2', status: '입주 단계', units: 100 }),
    mkProject({ id: 'p3', label: 'P3', status: '분양중', units: 100 }),
    mkProject({ id: 'p4', label: 'P4', status: '분양중', units: 300 }),
    mkProject({ id: 'p5', label: 'P5', status: '분양중', units: 300 }),
    mkProject({ id: 'p6', label: 'P6', status: '건설 단계', units: null }),
  ];
  const byDefault = R.adaptBundle(mkRaw(ps)).blocks.map((b) => b.pid);
  assert.deepEqual(byDefault, ['p4', 'p5', 'p3', 'p6', 'p2', 'p1']);
  const pinned = R.adaptBundle(mkRaw(ps, mkRegion({ projectOrder: ['p2', 'p1', 'ghost'] }))).blocks.map((b) => b.pid);
  assert.deepEqual(pinned.slice(0, 2), ['p2', 'p1']);
  assert.deepEqual(pinned.slice(2), ['p4', 'p5', 'p3', 'p6']);
});

test('resolveBlock: label, pid, 모르는 값', () => {
  const r = R.adaptBundle(mkRaw());
  assert.equal(r.resolveBlock('A-1').pid, 'z1-A1');
  assert.equal(r.resolveBlock('z1-A1').id, 'A-1');
  assert.equal(r.resolveBlock('nope'), null);
  assert.equal(r.resolveBlock(null), null);
});

test('전역 설정 모양: GY_PROJECTS, 지구, 건물, 맥락', () => {
  const r = R.adaptBundle(mkRaw([mkProject()], mkRegion(), { projects: { schema_version: '1.1.0', projects: [mkProject()], otherBlocks: [RING] } }));
  assert.equal(r.GY_PROJECTS.blocks.length, 1);
  assert.equal(r.GY_PROJECTS.district.poly, RING); assert.equal(r.GY_PROJECTS.district.name, '테스트 지구');
  assert.equal(r.GY_PROJECTS.districts.length, 1);
  assert.deepEqual(r.GY_PROJECTS.otherBlocks, [RING]);
  assert.equal(r.GY_BUILDINGS.meta.basis, '20261004');
  assert.equal(r.GY_CONTEXT.stations.length, 1);
  assert.deepEqual(r.view, { center: [126.785, 35.155], zoom: 15, pitch: 52 });
  assert.deepEqual(r.statusOrder, ['계획', '분양중', '건설 단계', '준공 임박', '입주 단계']);
});

test('지구에 poly 가 없으면 district 는 null, context 가 없으면 GY_CONTEXT 는 null', () => {
  const r = R.adaptBundle(mkRaw([mkProject()], mkRegion({ zones: [{ id: 'z', name: 'Z', type: '기타', publicLand: false }] }), { context: null }));
  assert.equal(r.GY_PROJECTS.district, null); assert.deepEqual(r.GY_PROJECTS.districts, []);
  assert.equal(r.GY_CONTEXT, null);
});

const INFRA_DOC = { schema_version: '1.2.0', asOf: '2026-10-04', sources: [{ id: 'i', label: '출처', redistributable: 'unknown' }], schools: [], stops: [] };

test('기반시설(infra.json): 있으면 GY_INFRA 와 푸터 문장, 없으면 null 이고 문장도 없다', () => {
  const withInfra = R.adaptBundle(mkRaw([mkProject()], mkRegion(), { infra: INFRA_DOC }));
  assert.equal(withInfra.GY_INFRA, INFRA_DOC);
  assert.match(withInfra.texts.footerHtml, /기반시설 점검 자료는 2026-10-04 기준 공개 자료입니다\.(<|$)/);
  const without = R.adaptBundle(mkRaw());
  assert.equal(without.GY_INFRA, null);
  assert.ok(!without.texts.footerHtml.includes('기반시설'));
  assert.equal(R.adaptBundle(mkRaw([mkProject()], mkRegion(), { infra: null })).GY_INFRA, null);
});

test('기반시설 문장은 다른 문장 뒤에 오고 한 번만 나온다', () => {
  const t = R.adaptBundle(mkRaw([mkProject()], mkRegion(), { infra: INFRA_DOC })).texts.footerHtml;
  assert.match(t, /역·학교는 OpenStreetMap입니다\. 기반시설 점검 자료는/);
  assert.equal(t.split('기반시설 점검 자료는').length, 2);
});

test('빈 지역(단지 0개)도 어댑터가 통과한다', () => {
  const r = R.adaptBundle(mkRaw([]));
  assert.deepEqual(r.blocks, []); assert.equal(r.hasPrivate, false);
  assert.equal(r.GY_PROJECTS.blocks.length, 0);
  assert.ok(r.texts.footerHtml.includes('V-World'));
});

test('hasPrivate', () => {
  assert.equal(R.adaptBundle(mkRaw([mkProject(), mkProject({ id: 'x', label: 'X', sponsorClass: 'private_on_public_land' })])).hasPrivate, true);
});

test('문구: 탭 제목, 소제목, 푸터(윤곽·공정율·역학교)', () => {
  const p1 = mkProject({ progress: { rate: 1, asOf: '2026-10-01', source: 'lh-cwstt' } });
  const p2 = mkProject({ id: 'p2', label: 'B', outline: { tier: 'official', poly: RING }, dongs: [{ no: '1', tier: 'building', floorsAbove: 5, poly: [RING] }] });
  const t = R.adaptBundle(mkRaw([p1, p2])).texts;
  assert.equal(t.documentTitle, '주택파동 공급 지도 (테스트구)');
  assert.equal(t.eyebrow, '주택파동 · 테스트구'); assert.equal(t.description, '설명');
  assert.match(t.footerHtml, /블록 윤곽은 공식 자료, 동 윤곽은 실제 건물 자료, 동 윤곽은 근사값\(10~20 m\)입니다\./);
  assert.match(t.footerHtml, /공정율은 LH 공사현황 기준입니다\./);
  assert.match(t.footerHtml, /역·학교는 OpenStreetMap입니다/);
  assert.match(t.footerHtml, /<span id="basis">-<\/span> 기준/);
});

test('문구: 공정율 출처·맥락이 없으면 그 문장이 없다, HTML 이스케이프', () => {
  const t = R.adaptBundle(mkRaw([mkProject()], mkRegion({ name: 'A&B<구>', title: 'T<b>' }), { context: null })).texts;
  assert.ok(!t.footerHtml.includes('공정율은')); assert.ok(!t.footerHtml.includes('역·학교'));
  assert.equal(t.documentTitle, '주택파동 공급 지도 (A&B<구>)');  // 제목은 텍스트라 이스케이프하지 않는다
  assert.equal(R.escapeHtml('<a href="x">&</a>'), '&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;');
});

test('1.0.0 번들(새 필드 없음)도 읽힌다', () => {
  const r = R.adaptBundle(mkRaw());
  const b = r.blocks[0];
  assert.equal(b.builder, undefined); assert.equal(b.contractM, undefined); assert.equal(b.note, undefined); assert.equal(b.progress, undefined);
});

test('selectorModel / regionUrl', () => {
  const index = { regions: [{ slug: 'a', name: 'A' }, { slug: 'b', name: 'B' }] };
  assert.deepEqual(R.selectorModel(index, 'b'), { visible: true, options: [{ value: 'a', label: 'A', selected: false }, { value: 'b', label: 'B', selected: true }] });
  assert.equal(R.selectorModel({ regions: [{ slug: 'a', name: 'A' }] }, 'a').visible, false);
  assert.equal(R.regionUrl('https://x.test/?block=A6&mode=time&region=a', 'b'), 'https://x.test/?mode=time&region=b');
});

function fakeFetch(files) {
  const calls = [];
  const f = async (url) => { calls.push(url); if (url in files) return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(files[url])) }; return { ok: false, status: 404, json: async () => { throw new Error('404'); } }; };
  f.calls = calls; return f;
}
const filesFor = (base = 'regions/') => ({
  'regions/index.json': { schema_version: '1.1.0', dataBase: base, regions: [{ slug: 'r1', name: '테스트구', default: true, visibility: 'public' }, { slug: 'r2', name: '둘째', visibility: 'public' }] },
  [`${base}r1/region.json`]: mkRegion(), [`${base}r1/projects.json`]: { schema_version: '1.1.0', projects: [mkProject()] },
  [`${base}r1/buildings.json`]: { type: 'FeatureCollection', meta: { basis: '20261004' }, features: [] },
  [`${base}r1/context.json`]: mkRaw().context,
});

test('loadRegion: 정상, context 404 는 무시', async () => {
  const files = filesFor(); delete files['regions/r1/context.json'];
  const out = await R.loadRegion({ fetch: fakeFetch(files), search: '' });
  assert.equal(out.ok, true); assert.equal(out.slug, 'r1'); assert.equal(out.GY_CONTEXT, null); assert.equal(out.blocks.length, 1);
  assert.equal(out.regions.length, 2);
});

test('loadRegion: infra.json 이 있으면 읽고, 404 면 null 로 둔다(지역은 그대로 열린다)', async () => {
  const files = filesFor(); files['regions/r1/infra.json'] = INFRA_DOC;
  const f = fakeFetch(files);
  const withInfra = await R.loadRegion({ fetch: f, search: '' });
  assert.equal(withInfra.ok, true); assert.deepEqual(withInfra.GY_INFRA, INFRA_DOC); assert.ok(f.calls.includes('regions/r1/infra.json'));
  const without = await R.loadRegion({ fetch: fakeFetch(filesFor()), search: '' });
  assert.equal(without.ok, true); assert.equal(without.GY_INFRA, null); assert.equal(without.blocks.length, 1);
});

test('loadRegion: infra.json 이 깨져 있으면(404 가 아닌 오류) URL 을 담은 예외', async () => {
  const files = filesFor(); files['regions/r1/infra.json'] = INFRA_DOC;
  const f = async (url) => (url === 'regions/r1/infra.json' ? { ok: false, status: 500, json: async () => ({}) } : fakeFetch(files)(url));
  await assert.rejects(() => R.loadRegion({ fetch: f, search: '' }), /regions\/r1\/infra\.json: HTTP 500/);
});

test('boot: 전역 GY_INFRA 를 채운다(없으면 null)', async () => {
  const doc = { title: '', querySelector: () => null, getElementById: () => null };
  const mk = (files) => ({ location: { search: '', href: 'http://x.test/' }, fetch: (u) => fakeFetch(files)(u) });
  const files = filesFor(); files['regions/r1/infra.json'] = INFRA_DOC;
  const w1 = mk(files); const r1 = await R.boot(w1, doc);
  assert.equal(r1.ok, true); assert.deepEqual(w1.GY_INFRA, INFRA_DOC); assert.equal(w1.REGION.slug, 'r1');
  const w2 = mk(filesFor()); await R.boot(w2, doc);
  assert.equal(w2.GY_INFRA, null);
});

test('loadRegion: dataBase 로 지역 폴더 주소를 바꾼다', async () => {
  const files = filesFor('https://cdn.test/data/');
  const f = fakeFetch(files);
  const out = await R.loadRegion({ fetch: f, search: '' });
  assert.equal(out.ok, true);
  assert.ok(f.calls.includes('https://cdn.test/data/r1/projects.json')); assert.ok(f.calls[0] === 'regions/index.json');
});

test('loadRegion: 모르는 지역은 오류 객체, 필수 파일 실패는 URL 을 담은 예외', async () => {
  const bad = await R.loadRegion({ fetch: fakeFetch(filesFor()), search: '?region=zzz' });
  assert.equal(bad.ok, false); assert.equal(bad.error, 'unknown'); assert.equal(bad.regions.length, 2);
  const files = filesFor(); delete files['regions/r1/buildings.json'];
  await assert.rejects(() => R.loadRegion({ fetch: fakeFetch(files), search: '' }), /regions\/r1\/buildings\.json/);
  await assert.rejects(() => R.loadRegion({ fetch: fakeFetch({}), search: '' }), /regions\/index\.json/);
});

/* ---------- 표준코드로 열기 ---------- */
test('codeQuery: 우선순위 project > pnu > bjd > sgg > code, 코드가 ?region= 보다 우선, 코드가 없으면 null', () => {
  assert.deepEqual(R.codeQuery('?project=PRJ-41450-0001&pnu=2824510900100010000&bjd=2824510900'), { name: 'project', value: 'PRJ-41450-0001' });   // 사업 id 가 가장 구체적이다
  assert.deepEqual(R.codeQuery('?code=28245&at=1,2,3'), { name: 'code', value: '28245' });
  assert.deepEqual(R.codeQuery('?pnu=2824510900100010000'), { name: 'pnu', value: '2824510900100010000' });
  assert.deepEqual(R.codeQuery('?code=1&sgg=28245&bjd=2824510900&pnu=2824510900100010000'), { name: 'pnu', value: '2824510900100010000' });
  assert.deepEqual(R.codeQuery('?code=1&sgg=28245'), { name: 'sgg', value: '28245' });
  assert.deepEqual(R.codeQuery('?region=r1&code=28245'), { name: 'code', value: '28245' });
  assert.equal(R.codeQuery('?region=r1'), null);
  assert.equal(R.codeQuery(''), null); assert.equal(R.codeQuery('?mode=floors'), null);
});

test('withRegion·regionUrl: 코드 매개변수를 지우고 지역으로 바꾼다, 나머지는 보존', () => {
  const s = R.withRegion('?code=28245&mode=progress&pnu=1', 'r1');
  const p = new URLSearchParams(s);
  assert.equal(p.get('region'), 'r1'); assert.equal(p.get('mode'), 'progress'); assert.equal(p.has('code'), false); assert.equal(p.has('pnu'), false);
  const u = new URL(R.regionUrl('https://x.test/?bjd=2824510900&block=A&at=1,2,3', 'r2'));
  assert.equal(u.searchParams.get('region'), 'r2'); assert.equal(u.searchParams.has('bjd'), false); assert.equal(u.searchParams.has('block'), false); assert.equal(u.searchParams.get('at'), '1,2,3');
});

test('resolvedStart·resolvedShape: 시군구는 지역 기본 시점(null), 법정동은 15.4, 필지는 17.6, 필지를 못 찾으면 법정동 경계', () => {
  const sq = { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] };
  const A = { tier: 'A' }, NONE = { tier: 'none' };
  assert.equal(R.resolvedStart({ type: 'sgg', center: [126.7, 37.5], coverage: A, bbox: [126.68, 37.52, 126.79, 37.59] }), null);   // 번들 있는 시군구는 지역 기본 시점
  assert.equal(R.resolvedShape({ type: 'sgg', geometry: sq, coverage: A }), null);
  assert.deepEqual(R.resolvedStart({ type: 'sgg', center: [127.02, 37.6], coverage: NONE, bbox: [126.99, 37.57, 127.05, 37.62] }), { center: [127.02, 37.6], zoom: 12.8 });   // 번들 없는 시군구는 경계가 한눈에
  assert.equal(R.resolvedShape({ type: 'sgg', geometry: sq, coverage: NONE }), sq);
  assert.equal(R.resolvedStart({ type: 'sgg', center: [127, 37.6], coverage: NONE }), null);                                       // 경계가 없으면 지역 기본 시점도 없음
  assert.deepEqual(R.resolvedStart({ type: 'bjd', center: [126.7, 37.5] }), { center: [126.7, 37.5], zoom: 15.4 });
  assert.equal(R.resolvedShape({ type: 'bjd', geometry: sq }), sq);
  const pnu = { type: 'pnu', center: [126.7, 37.5], parcel: { geometry: sq }, geometry: { type: 'Polygon', coordinates: [[[5, 5], [6, 5], [6, 6], [5, 5]]] } };
  assert.equal(R.resolvedStart(pnu).zoom, 17.6); assert.equal(R.resolvedShape(pnu), sq);
  const fallback = { type: 'pnu', center: [126.7, 37.5], parcel: { geometry: null }, geometry: sq };
  assert.equal(R.resolvedStart(fallback).zoom, 15.4); assert.equal(R.resolvedShape(fallback), sq);
  assert.equal(R.resolvedStart({ type: 'bjd' }), null); assert.equal(R.resolvedStart({ type: 'bjd', center: ['a', 1] }), null);
  assert.equal(R.resolvedShape(null), null);
});

function bootWith(search, resolveRes, files = filesFor()) {
  const els = {};
  const el = (id) => (els[id] = els[id] || { hidden: true, innerHTML: '', textContent: '', addEventListener() {}, setAttribute() {} });
  const doc = { title: '', querySelector: () => null, getElementById: el };
  const base = fakeFetch(files);
  const win = { location: { search, href: `http://x.test/${search}` }, fetch: async (u) => (String(u).startsWith('api/v1/resolve') ? resolveRes(u) : base(u)) };
  return { win, doc, els };
}
const json = (status, body) => ({ ok: status < 400, status, json: async () => body });

test('boot: ?code= 가 번들이 있는 시군구면 그 지역을 열고 시작 위치·경계를 RESOLVED 에 싣는다', async () => {
  const urls = [];
  const sq = { type: 'Polygon', coordinates: [[[126.7, 37.5], [126.8, 37.5], [126.8, 37.6], [126.7, 37.5]]] };
  const { win, doc } = bootWith('?bjd=2824510900&mode=progress', (u) => { urls.push(u); return json(200, { type: 'bjd', level: 'umd', name: '인천광역시 계양구 박촌동', center: [126.75, 37.55], geometry: sq, coverage: { tier: 'A', slug: 'r1' } }); });
  const r = await R.boot(win, doc);
  assert.equal(r.ok, true); assert.equal(win.REGION.slug, 'r1');
  assert.deepEqual(urls, ['api/v1/resolve?bjd=2824510900&geometry=1']);
  assert.deepEqual(win.RESOLVED.start, { center: [126.75, 37.55], zoom: 15.4 }); assert.equal(win.RESOLVED.shape, sq); assert.equal(win.RESOLVED.name, '인천광역시 계양구 박촌동');
});

test('boot: ?region= 과 코드가 함께 오면 코드가 가리키는 지역이 우선한다', async () => {
  const { win, doc } = bootWith('?region=zzz&sgg=28245', () => json(200, { type: 'sgg', level: 'sgg', name: '계양구', center: [126.7, 37.5], coverage: { tier: 'A', slug: 'r1' } }));
  const r = await R.boot(win, doc);
  assert.equal(r.ok, true); assert.equal(win.REGION.slug, 'r1'); assert.equal(win.RESOLVED.start, null);   // 시군구는 지역 기본 시점
});

test('boot: ?region= 만 있으면 해석 API 를 부르지 않고 RESOLVED 는 null', async () => {
  let called = 0;
  const { win, doc } = bootWith('?region=r1', () => { called++; return json(200, {}); });
  const r = await R.boot(win, doc);
  assert.equal(r.ok, true); assert.equal(called, 0); assert.equal(win.RESOLVED, null);
});

test('boot: 번들이 없는 시군구(tier none)도 지도를 연다: 빈 번들 + 건물 요청 시 조회, 경계만 강조, 선택기에 번들 없음 표시', async () => {
  const sq = { type: 'Polygon', coordinates: [[[126.99, 37.57], [127.05, 37.57], [127.05, 37.62], [126.99, 37.57]]] };
  const { win, doc, els } = bootWith('?code=11290', () => json(200, { type: 'sgg', level: 'sgg', name: '서울특별시 성북구', center: [127.02, 37.6], bbox: [126.99, 37.57, 127.05, 37.62], geometry: sq, coverage: { tier: 'none' } }));
  const r = await R.boot(win, doc);
  assert.equal(r.ok, true);                                                                                          // index.html 은 ok 일 때만 앱 스크립트를 읽는다
  assert.equal(r.slug, ''); assert.equal(win.REGION.name, '서울특별시 성북구'); assert.equal(win.GY_BUILDINGS.dynamic, true); assert.equal(win.GY_BUILDINGS.features.length, 0);
  assert.equal(win.GY_PROJECTS.blocks.length, 0); assert.equal(win.GY_INFRA, null);
  assert.deepEqual(win.RESOLVED.start, { center: [127.02, 37.6], zoom: 12.8 }); assert.equal(win.RESOLVED.shape, sq); assert.equal(win.RESOLVED.tier, 'none');
  assert.equal(els.pvBanner.hidden, false); assert.match(els.pvBanner.innerHTML, /지역 번들이 없어 경계와 건물\(요청 시 조회\)만/);
  assert.equal(els.fatal, undefined);
  assert.match(els.regionSel.innerHTML, /서울특별시 성북구 \(번들 없음\)/); assert.match(els.regionSel.innerHTML, /value="r1"/);
  const off = bootWith('?code=11290&dyn=0', () => json(200, { type: 'sgg', level: 'sgg', name: '서울특별시 성북구', center: [127.02, 37.6], bbox: [126.99, 37.57, 127.05, 37.62], coverage: { tier: 'none' } }));
  await R.boot(off.win, off.doc); assert.equal(off.win.GY_BUILDINGS.dynamic, false);                                   // 건물 없이 경계만
});

test('boot: 해석 실패(400·404·429·502·연결 불가)는 문구와 이스케이프된 detail 을 보인다', async () => {
  const cases = [
    [() => json(400, { code: 'invalid-code', detail: '자릿수 7는 지원하지 않습니다' }), /코드 형식이 맞지 않습니다/, 'invalid-code'],
    [() => json(404, { code: 'unknown-code', detail: '<b>x</b>' }), /표준코드 표에 없는 코드/, 'unknown-code'],
    [() => json(429, { code: 'keys-exhausted' }), /한도에 닿았습니다/, 'keys-exhausted'],
    [() => json(502, { code: 'upstream' }), /부르지 못했습니다/, 'upstream'],
    [() => json(404, null), /쓸 수 없습니다/, 'unavailable'],
    [() => { throw new Error('offline'); }, /연결하지 못했습니다/, 'network'],
  ];
  for (const [res, re, code] of cases) {
    const { win, doc, els } = bootWith('?code=123', res);
    const r = await R.boot(win, doc);
    assert.equal(r.ok, false); assert.equal(r.code, code); assert.match(els.fatal.innerHTML, re);
    assert.doesNotMatch(els.fatal.innerHTML, /<b>/);
  }
});

test('noticeText·mountBanner: 후퇴한 경고는 한 줄 안내로, 미리보기 문구와 합친다, 안내할 것이 없으면 숨김', () => {
  assert.equal(R.noticeText(['parcel-not-found']), '요청한 필지를 찾지 못해 법정동 경계로 열었습니다');
  assert.equal(R.noticeText(['padded-8-digit']), '');
  assert.equal(R.noticeText(['geometry-unavailable', 'boundary-not-found']), '경계를 불러오지 못해 지역 기본 위치로 열었습니다 · 경계를 찾지 못해 지역 기본 위치로 열었습니다');
  assert.equal(R.noticeText(undefined), '');
  const el = { hidden: true, innerHTML: '' }; const doc = { getElementById: () => el };
  R.mountBanner(doc, { visibility: 'public' }, ''); assert.equal(el.hidden, true);
  R.mountBanner(doc, { visibility: 'public' }, '안내'); assert.equal(el.hidden, false); assert.equal(el.innerHTML, '<span class="pv-s">안내</span>');
  R.mountBanner(doc, { visibility: 'preview' }, '안내'); assert.equal(el.innerHTML, '<details class="pv-d"><summary class="pv-s">미리보기 · 안내</summary><p class="pv-f">미리보기 — 공개 전 자료입니다 · 안내</p></details>');
  R.mountBanner(doc, { visibility: 'preview' }); assert.equal(el.innerHTML, '<details class="pv-d"><summary class="pv-s">미리보기</summary><p class="pv-f">미리보기 — 공개 전 자료입니다</p></details>');
  R.mountBanner(doc, { visibility: 'public' }, '<b>x</b>'); assert.equal(el.innerHTML, '<span class="pv-s">&lt;b&gt;x&lt;/b&gt;</span>', '글자는 이스케이프');
});

test('안내 띠(2026-10-10 피드백): 한 줄 요약만 보이고 누르면 전체 문장을 편다 — bannerBrief 는 경우마다 짧게 줄인다', () => {
  const el = { hidden: true, innerHTML: '' }; const doc = { getElementById: () => el };
  const full = '지역 번들이 없어 경계·건물(요청 시 조회)·건축HUB 인허가 사업 13곳만 보여 줍니다(건축물대장으로 위치를 찾은 3곳 포함, 필지를 못 찾은 3곳 제외)';
  R.mountBanner(doc, { visibility: 'public' }, full, '번들 없는 지역 · 인허가 사업 13곳 (대장으로 찾음 3 · 제외 3)');
  assert.equal(el.innerHTML, `<details class="pv-d"><summary class="pv-s">번들 없는 지역 · 인허가 사업 13곳 (대장으로 찾음 3 · 제외 3)</summary><p class="pv-f">${full}</p></details>`);
  const B = (permits, warnings, slug = null) => R.bannerBrief({ slug, permits }, warnings);
  assert.equal(B({ count: 13, fetched: true, ledger: { blocksMatched: 2, parcelsRecovered: 1 }, unlocated: 3 }), '번들 없는 지역 · 인허가 사업 13곳 (대장으로 찾음 3 · 제외 3)');
  assert.equal(B({ count: 4, fetched: true, ledger: { blocksMatched: 2, parcelsRecovered: 0 } }), '번들 없는 지역 · 인허가 사업 4곳 (대장으로 찾음 2)');
  assert.equal(B({ count: 2, fetched: true, unlocated: 2 }), '번들 없는 지역 · 인허가 사업 2곳 (제외 2)');
  assert.equal(B({ count: 6, fetched: true }), '번들 없는 지역 · 인허가 사업 6곳');
  assert.equal(B({ count: 0, fetched: true, blocks: 13 }), '번들 없는 지역 · 블록 단위 인허가 13곳은 지도에 못 그림');
  assert.equal(B({ count: 0, fetched: true, records: 0 }), '번들 없는 지역 · 이 법정동 인허가 사업 없음');
  assert.equal(B(null), '번들 없는 지역 · 경계·건물만');
  assert.equal(B(null, ['parcel-not-found'], 'r1'), '요청한 필지를 찾지 못해 법정동 경계로 열었습니다', '번들 지역의 경고는 짧아서 그대로');
  assert.equal(B({ count: 6, fetched: true }, ['parcel-not-found']), '위치 안내 1건 · 번들 없는 지역 · 인허가 사업 6곳');
  assert.equal(B(null, [], 'r1'), '');
});

test('boot: 필지를 못 찾아 법정동으로 후퇴하면 배너로 알린다', async () => {
  const sq = { type: 'Polygon', coordinates: [[[126.7, 37.5], [126.8, 37.5], [126.8, 37.6], [126.7, 37.5]]] };
  const { win, doc, els } = bootWith('?pnu=2824510900100010000', () => json(200, { type: 'pnu', level: 'umd', name: '박촌동', center: [126.75, 37.55], geometry: sq, parcel: { geometry: null }, warnings: ['parcel-not-found'], coverage: { tier: 'A', slug: 'r1' } }));
  const r = await R.boot(win, doc);
  assert.equal(r.ok, true);
  assert.equal(els.pvBanner.hidden, false); assert.match(els.pvBanner.innerHTML, /필지를 찾지 못해 법정동 경계로/);
  assert.equal(win.RESOLVED.start.zoom, 15.4); assert.deepEqual(win.RESOLVED.warnings, ['parcel-not-found']);
});

test('zoomForBbox·dynParam: 가로 폭에 맞는 확대 단계(11~16), ?dyn 값', () => {
  assert.equal(Math.round(R.zoomForBbox([126.68, 37.52, 126.79, 37.59]) * 10) / 10, 11.9);
  assert.equal(R.zoomForBbox([126.7, 37.5, 126.7001, 37.5001]), 16);                       // 아주 작으면 16 에서 멈춤
  assert.equal(R.zoomForBbox([120, 30, 130, 40]), 11);                                       // 아주 크면 지도 최소 확대 11
  assert.equal(R.zoomForBbox(null), null); assert.equal(R.zoomForBbox([1, 2, 'a', 4]), null);
  assert.equal(R.dynParam('?dyn=0'), 'off'); assert.equal(R.dynParam('?dyn=1&a=2'), 'on'); assert.equal(R.dynParam('?dyn=x'), null); assert.equal(R.dynParam(''), null);
});

test('boot: 번들이 있는 지역도 코드로 열면 번들 밖 건물을 요청 시 조회한다(?dyn=0 이면 끔), ?region= 만이면 그대로', async () => {
  const resp = () => json(200, { type: 'sgg', level: 'sgg', name: '계양구', center: [126.7, 37.5], coverage: { tier: 'A', slug: 'r1' } });
  const a = bootWith('?sgg=28245', resp); await R.boot(a.win, a.doc); assert.equal(a.win.GY_BUILDINGS.dynamic, true);
  const b = bootWith('?sgg=28245&dyn=0', resp); await R.boot(b.win, b.doc); assert.equal(b.win.GY_BUILDINGS.dynamic, undefined);
  const c = bootWith('?region=r1', () => json(200, {})); await R.boot(c.win, c.doc); assert.equal(c.win.GY_BUILDINGS.dynamic, undefined);
  const d = bootWith('?region=r1&dyn=1', () => json(200, {})); await R.boot(d.win, d.doc); assert.equal(d.win.GY_BUILDINGS.dynamic, true);
});

/* ---------- 번들 없는 지역의 건축HUB 인허가 사업 ---------- */
const PERMIT_FC = {
  type: 'FeatureCollection', bjd: '4145010800',
  features: [
    { type: 'Feature', properties: { pnu: '4145010800105690000', jibun: '569', name: '덕풍아파트 신축공사', label: '덕풍', units: 120, status: '건설 단계', mainBldCnt: 3, approvedAt: '2025-06-01', startedAt: '2025-09-01', completedAt: null, plannedCompletion: '2028-12-31', address: '경기도 하남시 덕풍동 569번지', refs: ['1', '2'], records: 2 },
      geometry: { type: 'Polygon', coordinates: [[[127.2, 37.54], [127.2003, 37.54], [127.2003, 37.5403], [127.2, 37.5403], [127.2, 37.54]]] } },
    { type: 'Feature', properties: { pnu: '4145010800100010002', jibun: '1-2', name: '옛단지', label: '옛단지', units: 50, status: '입주 단계', mainBldCnt: null, approvedAt: '2018-01-01', startedAt: '2018-06-01', completedAt: '2020-06-01', plannedCompletion: null, address: null, refs: [], records: 1 },
      geometry: { type: 'Polygon', coordinates: [[[127.201, 37.541], [127.2013, 37.541], [127.2013, 37.5413], [127.201, 37.541]]] } },
    { type: 'Feature', properties: { pnu: '4145010800100020000', name: '링 없음', label: 'x', status: '계획' }, geometry: null },
  ],
  meta: { records: 453, unlocated: 2, truncated: false },
};

test('permitsToProjects: 인허가 사업을 번들 단지 모양으로(윤곽=필지, 상태·세대수·입주 시기·출처·메모), 윤곽 없는 것은 뺀다', () => {
  const ps = R.permitsToProjects(PERMIT_FC);
  assert.equal(ps.length, 2);
  const [a, b] = ps;
  assert.equal(a.id, 'hub-4145010800105690000'); assert.equal(a.label, '덕풍'); assert.equal(a.name, '덕풍아파트 신축공사'); assert.equal(a.status, '건설 단계'); assert.equal(a.units, 120); assert.equal(a.dongCount, 3);
  assert.equal(a.kind, '인허가 사업'); assert.equal(a.sponsorClass, 'unknown'); assert.equal(a.outline.tier, 'official'); assert.equal(a.outline.poly.length, 4);                // 닫는 점을 뺀 링
  assert.equal(a.moveIn, '2028-12-31'); assert.deepEqual(a.sources, ['hub-housing-permit', 'vworld-cadastre']);
  assert.match(a.note, /경기도 하남시 덕풍동 569번지 · 허가 기록 2건 · 사업승인 2025-06-01 · 착공 2025-09-01 · 시행자·분양 정보는 없음/);
  assert.equal(b.moveIn, '2020-06'); assert.equal(b.dongCount, 0); assert.doesNotMatch(b.note, /null/);
  assert.deepEqual(R.permitsToProjects(null), []); assert.deepEqual(R.permitsToProjects({ features: [] }), []);
});

test('emptyBundle + 인허가: 단지로 들어가 어댑터가 쓰는 모양(상태 순서·세대수·출처 문구·민간 아님)이 된다', () => {
  const b = R.emptyBundle({ name: '경기도 하남시 덕풍동', center: [127.2, 37.54], bbox: [127.19, 37.53, 127.22, 37.55] }, { regions: [] }, PERMIT_FC);
  assert.equal(b.ok, true); assert.equal(b.slug, ''); assert.equal(b.blocks.length, 2);
  assert.deepEqual(b.blocks.map((x) => [x.id, x.status, x.units, x.priv]), [['덕풍', '건설 단계', 120, false], ['옛단지', '입주 단계', 50, false]]);
  assert.equal(b.blocks[0].src, '건축HUB 주택인허가정보(번지 단위 집계) · V-World 연속지적도(필지 경계)'); assert.equal(b.blocks[0].moveIn, '준공 예정 2028-12-31'); assert.equal(b.blocks[1].moveIn, '2020.06');
  assert.equal(b.resolveBlock('hub-4145010800105690000'), b.blocks[0]); assert.deepEqual(b.permits, { fetched: true, count: 2, unlocated: 2, truncated: false, records: 453, candidates: 0, blocks: 0, ledger: null });
  assert.equal(b.hasPrivate, false);
  const none = R.emptyBundle({ name: 'x', center: [127, 37] }, null, null); assert.equal(none.blocks.length, 0); assert.deepEqual(none.permits, { fetched: false, count: 0, unlocated: 0, truncated: false, records: 0, candidates: 0, blocks: 0, ledger: null });
});

function bootWithPermits(search, resolveBody, permitsRes) {
  const els = {}, el = (id) => (els[id] = els[id] || { hidden: true, innerHTML: '', textContent: '', addEventListener() {}, setAttribute() {} });
  const doc = { title: '', querySelector: () => null, getElementById: el };
  const urls = [], base = fakeFetch(filesFor());
  const win = { location: { search, href: `http://x.test/${search}` }, fetch: async (u) => { urls.push(String(u)); if (String(u).startsWith('api/v1/resolve')) return json(200, resolveBody); if (String(u).startsWith('api/v1/permits')) return permitsRes(u); return base(u); } };
  return { win, doc, els, urls };
}
const RESOLVED_BJD = { type: 'bjd', level: 'umd', name: '경기도 하남시 덕풍동', bjd: '4145010800', center: [127.2, 37.54], bbox: [127.19, 37.53, 127.22, 37.55], coverage: { tier: 'none' } };

test('boot: 번들 없는 법정동은 인허가 사업을 단지로 열고, 안내 띠에 곳수를 알린다', async () => {
  const { win, doc, els, urls } = bootWithPermits('?bjd=4145010800', RESOLVED_BJD, () => json(200, PERMIT_FC));
  const r = await R.boot(win, doc);
  assert.equal(r.ok, true); assert.deepEqual(urls.filter((u) => u.startsWith('api/v1/permits')), ['api/v1/permits?bjd=4145010800']);
  assert.equal(win.GY_PROJECTS.blocks.length, 2); assert.equal(win.RESOLVED.block, null);
  assert.match(els.pvBanner.innerHTML, /건축HUB 인허가 사업 2곳만 보여 줍니다\(필지를 못 찾은 2곳 제외\)/);
  assert.match(els.pvBanner.innerHTML, /<summary class="pv-s">번들 없는 지역 · 인허가 사업 2곳 \(제외 2\)<\/summary>/, '띠에는 요약, 펼치면 전체');
});

test('boot: 필지로 열었는데 그 필지가 인허가 사업이면 그 단지를 열도록 RESOLVED.block 에 싣는다', async () => {
  const pnuBody = { ...RESOLVED_BJD, type: 'pnu', pnu: '4145010800105690000', parcel: { geometry: PERMIT_FC.features[0].geometry } };
  const { win, doc } = bootWithPermits('?pnu=4145010800105690000', pnuBody, () => json(200, PERMIT_FC));
  await R.boot(win, doc);
  assert.equal(win.RESOLVED.block, 'hub-4145010800105690000');
  const other = bootWithPermits('?pnu=4145010800199990000', { ...pnuBody, pnu: '4145010800199990000' }, () => json(200, PERMIT_FC));
  await R.boot(other.win, other.doc); assert.equal(other.win.RESOLVED.block, null);
});

test('boot: 인허가 조회가 실패(429·502·연결 불가)하거나 ?permits=0 이거나 시군구 단위면 단지 없이 열린다(조회도 안 함)', async () => {
  for (const res of [() => json(429, { code: 'keys-exhausted' }), () => json(502, { code: 'upstream' }), () => { throw new Error('offline'); }, () => json(200, { type: 'x' })]) {
    const { win, doc, els } = bootWithPermits('?bjd=4145010800', RESOLVED_BJD, res);
    const r = await R.boot(win, doc);
    assert.equal(r.ok, true); assert.equal(win.GY_PROJECTS.blocks.length, 0); assert.match(els.pvBanner.innerHTML, /지역 번들이 없어 경계와 건물\(요청 시 조회\)만/);
  }
  const off = bootWithPermits('?bjd=4145010800&permits=0', RESOLVED_BJD, () => json(200, PERMIT_FC)); await R.boot(off.win, off.doc);
  assert.equal(off.urls.filter((u) => u.startsWith('api/v1/permits')).length, 0); assert.equal(off.win.GY_PROJECTS.blocks.length, 0);
  const sgg = bootWithPermits('?sgg=41450', { type: 'sgg', level: 'sgg', name: '경기도 하남시', center: [127.2, 37.5], coverage: { tier: 'none' } }, () => json(200, PERMIT_FC)); await R.boot(sgg.win, sgg.doc);
  assert.equal(sgg.urls.filter((u) => u.startsWith('api/v1/permits')).length, 0);
  const tierA = bootWithPermits('?bjd=2824510900', { type: 'bjd', level: 'umd', name: '박촌동', bjd: '2824510900', center: [126.75, 37.55], coverage: { tier: 'A', slug: 'r1' } }, () => json(200, PERMIT_FC)); await R.boot(tierA.win, tierA.doc);
  assert.equal(tierA.urls.filter((u) => u.startsWith('api/v1/permits')).length, 0);                                  // 번들이 있으면 번들의 단지를 쓴다
});

test('인허가 사업 메모: 예정일이 지났는데 기록이 없으면 사실만 적고(지연 판정 아님), 예정일이 아직이면 예정으로, 기록이 아예 없으면 그렇게', () => {
  const f = (props) => ({ type: 'Feature', properties: Object.assign({ pnu: '4145010800105690000', name: 'x', label: 'x', units: 10, status: '계획', records: 1, address: null }, props), geometry: PERMIT_FC.features[0].geometry });
  const note = (props) => R.permitsToProjects({ features: [f(props)] })[0].note;
  assert.match(note({ plannedStart: '2025-12-31', overdue: { kind: '착공', plannedAt: '2025-12-31', months: 9 } }), /착공 예정일 2025-12-31이 9개월 지났으나 착공 기록이 없음/);
  assert.doesNotMatch(note({ plannedStart: '2025-12-31', overdue: { kind: '착공', plannedAt: '2025-12-31', months: 9 } }), /착공 예정 2025/);
  assert.match(note({ overdue: { kind: '준공', plannedAt: '2019-11', months: 80 }, status: '건설 단계' }), /준공 예정일 2019-11이 80개월 지났으나 준공 기록이 없음/);
  assert.match(note({ overdue: { kind: '착공', plannedAt: '2026-10-01', months: 0 } }), /얼마 지났으나/);
  assert.match(note({ plannedStart: '2027-03-01' }), /착공 예정 2027-03-01/); assert.doesNotMatch(note({ plannedStart: '2027-03-01' }), /기록이 없음/);
  assert.match(note({}), /착공 기록 없음/);                                                                          // 예정일도 없는 계획(오래된 조합 허가 등)
  assert.doesNotMatch(note({ status: '입주 단계', completedAt: '2020-06-01' }), /기록 없음|지났으나/);
});

test('emptyBundle: 필지를 못 찾은 사업은 자료 안내(푸터)에 이름·추정 원인으로 알린다. 후보가 0이면 안내 띠에 이웃 법정동 가능성을 말한다', async () => {
  const fc = { ...PERMIT_FC, meta: { records: 442, candidates: 3, unlocated: 3, unlocatedList: [
    { name: '래미안 포레카운티', jibun: '144-24', status: '입주 단계', reason: '준공 뒤 합필·분할로 지번이 없어졌을 수 있음' },
    { name: '위례 A3-3a BL', jibun: '1-1', status: '계획', reason: '택지개발지구 등 지적이 아직 나뉘지 않은 곳일 수 있음' },
    { name: '다른 곳', jibun: '9', status: '입주 단계', reason: '준공 뒤 합필·분할로 지번이 없어졌을 수 있음' }] } };
  const b = R.emptyBundle({ name: '서울 장위동', center: [127, 37.6] }, null, fc);
  assert.match(b.texts.footerHtml, /필지를 못 찾아 지도에 없는 3곳: 래미안 포레카운티\(144-24\), 위례 A3-3a BL\(1-1\), 다른 곳\(9\)\. 원인 추정: 준공 뒤 합필·분할로 지번이 없어졌을 수 있음 \/ 택지개발지구 등 지적이 아직 나뉘지 않은 곳일 수 있음\./);
  assert.doesNotMatch(R.emptyBundle({ name: 'x', center: [127, 37] }, null, PERMIT_FC.features.length ? { ...PERMIT_FC, meta: { records: 1, unlocated: 0 } } : null).texts.footerHtml, /못 찾아/);
  const zero = bootWithPermits('?bjd=4145011100', { ...RESOLVED_BJD, bjd: '4145011100', name: '경기도 하남시 미사동' }, () => json(200, { type: 'FeatureCollection', features: [], meta: { records: 0, candidates: 0, unlocated: 0 } }));
  await R.boot(zero.win, zero.doc);
  assert.match(zero.els.pvBanner.innerHTML, /건축HUB 주택인허가에 이 법정동의 공동주택 사업이 없습니다\(기록 0건\) — 이웃 법정동에 있을 수 있습니다/);
  const fail = bootWithPermits('?bjd=4145011100', { ...RESOLVED_BJD, bjd: '4145011100' }, () => json(502, {}));
  await R.boot(fail.win, fail.doc);
  assert.doesNotMatch(fail.els.pvBanner.innerHTML, /이웃 법정동/);                                                    // 조회 실패는 '없음'이 아니다
});

test('공공주택지구 블록 단위 허가: 자료 안내에 이름·블록·세대수로 알리고, 후보가 그것뿐이면 안내 띠가 "블록 단위라 못 그림"이라고 말한다', async () => {
  const meta = { records: 32, candidates: 0, unlocated: 0, blockProjects: 13, blockList: [
    { name: 'LH아파트', block: 'B1BL', units: 684 }, { name: '하남감일A5BL 아파트', block: 'A5블록', units: 617 }, { name: '감일 B-4BL', block: 'B-4BL', units: 595 }] };
  const fc = { type: 'FeatureCollection', features: [], meta };
  const b = R.emptyBundle({ name: '경기도 하남시 감일동', center: [127.17, 37.55] }, null, fc);
  assert.match(b.texts.footerHtml, /공공주택지구 블록 단위 허가 13곳은 필지 번호가 없어\(블록 번호만 있음\) 위치를 정할 수 없어 지도에 없습니다: LH아파트\(B1BL\) 684세대, 하남감일A5BL 아파트\(A5블록\) 617세대, 감일 B-4BL 595세대 외\./);   // 이름에 블록이 이미 있으면 괄호를 또 붙이지 않는다
  assert.equal(b.permits.blocks, 13);
  const zero = bootWithPermits('?bjd=4145011400', { ...RESOLVED_BJD, bjd: '4145011400', name: '경기도 하남시 감일동' }, () => json(200, fc));
  await R.boot(zero.win, zero.doc);
  assert.match(zero.els.pvBanner.innerHTML, /이 법정동의 건축HUB 인허가는 공공주택지구 블록 단위 13곳뿐이라 필지 번호가 없어 지도에 그릴 수 없습니다/);
  assert.doesNotMatch(zero.els.pvBanner.innerHTML, /이웃 법정동/);
});

test('건물대장 보강: 위치·준공 근거를 메모에 적고(블록·합필·사용승인), 출처에 건물대장을 더하며, 못 맞춘 블록·보강 실패는 자료 안내에 알린다', async () => {
  const sq = (x) => ({ type: 'Polygon', coordinates: [[[x, 37.55], [x + 0.0003, 37.55], [x + 0.0003, 37.5503], [x, 37.55]]] });
  const ledgerMeta = { used: true, bjds: 2, rows: 40, blocksMatched: 1, blocksAmbiguous: 1, parcelsRecovered: 1, completions: 1 };
  const fc = { type: 'FeatureCollection', features: [
    { type: 'Feature', geometry: sq(127.17), properties: { pnu: '4145010300104580000', jibun: '458', name: '하남감일 호반써밋', label: '호반써밋', units: 600, status: '입주 단계', approvedAt: '2017-01-01', completedAt: '2020-10-27', address: '경기도 하남시 감이동 458번지', records: 3, block: 'A1BL', via: 'ledger', ledger: { name: '하남감일 호반써밋', platPlc: '경기도 하남시 감이동 458번지', useAprDay: '2020-10-27', areaDiff: 0.33 } } },
    { type: 'Feature', geometry: sq(127.18), properties: { pnu: '4145010300109990000', jibun: '999', name: '옛지번단지', label: '옛지번단지', units: 300, status: '입주 단계', approvedAt: '2018-01-01', completedAt: '2023-06-30', address: '경기도 하남시 감이동 999번지', records: 1, via: 'ledger', hubJibun: '200', ledger: { name: '합필후단지', platPlc: '경기도 하남시 감이동 999번지', useAprDay: '2023-06-30', areaDiff: 0.84 } } },
    { type: 'Feature', geometry: sq(127.19), properties: { pnu: '4145011400103000000', jibun: '300', name: '준공단지', label: '준공단지', units: 120, status: '입주 단계', approvedAt: '2018-01-01', completedAt: '2021-12-31', address: '경기도 하남시 감일동 300번지', records: 1, statusBy: 'ledger' } },
    { type: 'Feature', geometry: sq(127.2), properties: { pnu: '4145011400100100000', jibun: '100', name: '허가만', label: '허가만', units: 80, status: '계획', approvedAt: '2024-01-01', address: '경기도 하남시 감일동 100번지', records: 1 } }],
  meta: { records: 40, candidates: 5, unlocated: 0, blockProjects: 1, blockList: [{ name: '감일 B-4BL', block: 'B-4BL', units: 595 }], ledger: ledgerMeta } };
  const [a, moved, done, plain] = R.permitsToProjects(fc);
  assert.deepEqual(a.sources, ['hub-housing-permit', 'hub-bldrgst', 'vworld-cadastre']);
  assert.match(a.note, /경기도 하남시 감이동 458번지 · 건물대장 기준 위치\(허가는 블록 단위 A1BL\): 세대수 일치, 대지면적 오차 0\.33% · 허가 기록 3건 · 사업승인 2017-01-01 · 사용승인\(건물대장\) 2020-10-27/);
  assert.match(moved.note, /건물대장 기준 위치\(허가 지번 200은 합필·분할로 지금은 없음\): 세대수 일치, 대지면적 오차 0\.84%/); assert.equal(moved.outline.how, '건물대장이 가리키는 대지 필지(연속지적도)');
  const byName = R.permitsToProjects({ features: [{ type: 'Feature', geometry: sq(127.21), properties: { pnu: '1129013600102280000', jibun: '228', name: '꿈의숲 푸르지오', label: '꿈의숲', units: 714, status: '입주 단계', completedAt: '2010-04-29', address: '서울특별시 성북구 하월곡동 228번지', records: 1, via: 'ledger', hubJibun: '산2-11', ledger: { name: '꿈의숲 푸르지오', useAprDay: '2010-04-29', areaDiff: null, by: 'name' } } }] })[0];
  assert.match(byName.note, /건물대장 기준 위치\(허가 지번 산2-11은 합필·분할로 지금은 없음\): 세대수·단지명 일치\(허가에 대지면적 기록이 없음\)/);
  assert.deepEqual(done.sources, ['hub-housing-permit', 'hub-bldrgst', 'vworld-cadastre']); assert.match(done.note, /사용승인\(건물대장\) 2021-12-31/); assert.doesNotMatch(done.note, /건물대장 기준 위치/);
  assert.deepEqual(plain.sources, ['hub-housing-permit', 'vworld-cadastre']); assert.doesNotMatch(plain.note, /건물대장/);
  const b = R.emptyBundle({ name: '경기도 하남시 감일동', center: [127.17, 37.55] }, null, fc);
  assert.match(b.texts.footerHtml, /건축물대장으로 보강: 블록 단위 허가 1곳의 위치, 합필·분할로 사라진 지번 1곳의 현재 지번, 사용승인으로 준공 확인 1곳\./);
  assert.match(b.texts.footerHtml, /공공주택지구 블록 단위 허가 1곳은 필지 번호가 없어\(블록 번호만 있음\) 건축물대장과 세대수·대지면적을 맞춰 보았지만 지번을 정하지 못해 지도에 없습니다: 감일 B-4BL 595세대\./);
  const src = (id) => b.blocks.find((x) => x.id === id).src;
  assert.match(src('호반써밋'), /건축HUB 건축물대장정보/); assert.doesNotMatch(src('허가만'), /건축물대장/);
  assert.deepEqual(b.permits.ledger, ledgerMeta);
  const bad = R.emptyBundle({ name: 'x', center: [127, 37] }, null, { ...fc, meta: { ...fc.meta, ledger: { used: false, error: '건물대장 서비스 권한이 없음(활용신청 필요)' } } });
  assert.match(bad.texts.footerHtml, /건축물대장 보강이 완전하지 않습니다: 건물대장 서비스 권한이 없음\(활용신청 필요\)\./);
  const only = { type: 'FeatureCollection', features: [], meta: { records: 3, candidates: 0, blockProjects: 2, blockList: [], ledger: { used: true, bjds: 2, rows: 5, blocksMatched: 0, blocksAmbiguous: 2, parcelsRecovered: 0, completions: 0 } } };
  const zero = bootWithPermits('?bjd=4145011400', { ...RESOLVED_BJD, bjd: '4145011400', name: '경기도 하남시 감일동' }, () => json(200, only));
  await R.boot(zero.win, zero.doc);
  assert.match(zero.els.pvBanner.innerHTML, /블록 단위 2곳뿐이라 필지 번호가 없어 건축물대장과 맞춰 보아도 지번을 정하지 못해 지도에 그릴 수 없습니다/);
  const ok = bootWithPermits('?bjd=4145011400', { ...RESOLVED_BJD, bjd: '4145011400', name: '경기도 하남시 감일동' }, () => json(200, fc));
  await R.boot(ok.win, ok.doc);
  assert.match(ok.els.pvBanner.innerHTML, /건축HUB 인허가 사업 4곳만 보여 줍니다\(건축물대장으로 위치를 찾은 2곳 포함\)/);
});

test('기반시설이 제때 안 오면(15초 제한·오류) 지도는 열고 자료 안내에 이유를 적는다. 받았거나 요청하지 않았으면 적지 않는다', async () => {
  const late = R.emptyBundle({ name: '부산 우동', center: [129.16, 35.16] }, null, PERMIT_FC, null, { infraFailed: true });
  assert.match(late.texts.footerHtml, /기반시설\(신설예정 학교·정류장\)을 제때 불러오지 못해 입주 전 점검 없이 열었습니다\. 잠시 뒤 다시 열면 나올 수 있습니다\./);
  assert.doesNotMatch(R.emptyBundle({ name: 'x', center: [127, 37] }, null, PERMIT_FC, null).texts.footerHtml, /제때 불러오지 못해/);
  assert.doesNotMatch(R.emptyBundle({ name: 'x', center: [127, 37] }, null, PERMIT_FC, null, { infraFailed: false }).texts.footerHtml, /제때 불러오지 못해/);
  const slow = bootWithPermits('?bjd=4145010800', RESOLVED_BJD, () => json(200, PERMIT_FC));                                                      // 기반시설 요청은 기본 가짜 fetch 가 404
  await R.boot(slow.win, slow.doc);
  assert.ok(slow.urls.some((u) => u.startsWith('api/v1/infra?bjd=4145010800')));
  assert.match(slow.win.REGION.texts.footerHtml, /제때 불러오지 못해/);
  const none = bootWithPermits('?bjd=4145010800&infra=0', RESOLVED_BJD, () => json(200, PERMIT_FC)); await R.boot(none.win, none.doc);
  assert.ok(!none.urls.some((u) => u.startsWith('api/v1/infra'))); assert.doesNotMatch(none.win.REGION.texts.footerHtml, /제때 불러오지 못해/);   // ?infra=0 이면 부르지도 않고 안내도 없다
  const emptyPermits = bootWithPermits('?bjd=4145011100', RESOLVED_BJD, () => json(200, { type: 'FeatureCollection', features: [], meta: { records: 0, candidates: 0 } })); await R.boot(emptyPermits.win, emptyPermits.doc);
  assert.ok(!emptyPermits.urls.some((u) => u.startsWith('api/v1/infra')));                                                                        // 인허가 단지가 없으면 점검할 대상이 없다
});

test('정류장이 OpenStreetMap 에서 왔으면 자료 안내에 그 사실과 누락 가능성을 적는다(TAGO 는 안 적음)', () => {
  const infra = (meta) => ({ type: 'Infra', bjd: '1129013800', asOf: '2026-10-05', sources: [], schools: [], stops: [{ id: 'osm-1', name: '정류장', lon: 127.05, lat: 37.61 }], meta });
  const osm = R.emptyBundle({ name: '서울 장위동', center: [127.05, 37.61] }, null, PERMIT_FC, infra({ stopsSource: 'osm', stops: 1 }));
  assert.match(osm.texts.footerHtml, /국토교통부 TAGO에 이 지역 자료가 없어 OpenStreetMap 기준으로 보여 드립니다\(누락이 있을 수 있습니다\)\./);
  assert.doesNotMatch(R.emptyBundle({ name: 'x', center: [127, 37] }, null, PERMIT_FC, infra({ stopsSource: 'tago', stops: 1 })).texts.footerHtml, /OpenStreetMap 기준/);
});

test('빈 번들: resolve 의 neighbors 를 nearby 로 싣는다(10자리 코드·이름이 있는 것만, 150개까지). 화면은 인허가 사업이 없을 때 그 법정동으로 가는 링크를 보인다', () => {
  const nb = [{ bjd: '4145011100', name: '미사동' }, { bjd: 'x', name: '나쁨' }, { bjd: '4145010900', name: '' }, { bjd: '4145010900', name: '망월동' }, null];
  const b = R.emptyBundle({ name: '경기도 하남시 감일동', center: [127.17, 37.55], neighbors: nb }, null, null);
  assert.deepEqual(b.nearby, [{ bjd: '4145011100', name: '미사동' }, { bjd: '4145010900', name: '망월동' }]);
  assert.deepEqual(R.emptyBundle({ name: 'x', center: [127, 37] }, null, null).nearby, []);
  assert.equal(R.emptyBundle({ name: 'x', center: [127, 37], neighbors: Array.from({ length: 200 }, (_, i) => ({ bjd: String(4145010000 + i), name: `동${i}` })) }, null, null).nearby.length, 150);
  const app = require('node:fs').readFileSync(require('node:path').join(__dirname, '../../assets/js/app.js'), 'utf8');
  assert.match(app, /REG\.nearby/); assert.match(app, /window\.RegionLoader\.codeUrl\(location\.href, 'bjd', x\.bjd\)/); assert.match(app, /같은 시군구의 다른 법정동 \$\{near\.length\}곳/);
  assert.match(require('node:fs').readFileSync(require('node:path').join(__dirname, '../../assets/css/app.css'), 'utf8'), /\.list \.nearby a\{/);
});

test('noticeRows: 공고를 화면 줄로(기관·유형·세대수, 접수 기간 또는 공고일, 단지·주소, 링크는 https 마이홈·LH 만, pnu 는 19자리만). 빈 제목은 뺀다', () => {
  const fx = JSON.parse(require('node:fs').readFileSync(require('node:path').join(__dirname, '../fixtures/api/notices-hanam.json'), 'utf8'));
  const rows = R.noticeRows(fx); assert.equal(rows.length, fx.items.length); assert.ok(rows[0].title && rows[0].meta && /^접수 \d\d\.\d\d(~\d\d\.\d\d)?$/.test(rows[0].period));
  const n = { id: 'rental-1', kind: 'rental', title: '신혼희망타운 모집', agency: 'LH', supplyType: '행복주택', housingType: '아파트', units: 20, complex: '하남감일A7BL', address: '경기도 하남시 감일순환로 40', pnu: '4145011500104680000', announcedAt: '2026-10-01', applyFrom: '2026-10-12', applyTo: '2026-10-14', url: 'https://www.myhome.go.kr/hws/x' };
  assert.deepEqual(R.noticeRows({ items: [n] })[0], { id: 'rental-1', title: '신혼희망타운 모집', meta: 'LH · 임대(행복주택) · 아파트 · 20세대', period: '접수 10.12~10.14', place: '하남감일A7BL · 경기도 하남시 감일순환로 40', url: 'https://www.myhome.go.kr/hws/x', pnu: '4145011500104680000', fromLh: false });
  assert.equal(R.noticeRows({ items: [{ ...n, source: 'lh' }] })[0].fromLh, true); assert.equal(R.noticeRows({ items: [{ ...n, source: 'myhome' }] })[0].fromLh, false);
  assert.equal(R.noticeRows({ items: [{ ...n, applyFrom: '2026-10-12', applyTo: '2026-10-12' }] })[0].period, '접수 10.12');
  assert.equal(R.noticeRows({ items: [{ ...n, applyFrom: null, applyTo: null }] })[0].period, '공고 2026.10.01'); assert.equal(R.noticeRows({ items: [{ ...n, applyFrom: null, applyTo: null, announcedAt: null }] })[0].period, '');
  for (const bad of ['http://www.myhome.go.kr/x', 'https://evil.example/', 'javascript:alert(1)']) assert.equal(R.noticeRows({ items: [{ ...n, url: bad }] })[0].url, '', bad);
  assert.equal(R.noticeRows({ items: [{ ...n, pnu: '123' }] })[0].pnu, ''); assert.deepEqual(R.noticeRows({ items: [{ ...n, title: '' }, null] }), []); assert.deepEqual(R.noticeRows(null), []);
});

test('fetchNotices: Notices 응답만 받고 오류·네트워크 실패는 null(지도를 막지 않는다). 화면은 번들 없는 지역에서만 늦게 채운다', async () => {
  const w1 = { urls: [], fetch: async (u) => { w1.urls.push(u); return { ok: true, json: async () => ({ type: 'Notices', items: [], name: 'x' }) }; } };
  assert.deepEqual(await R.fetchNotices(w1, '41450'), { type: 'Notices', items: [], name: 'x' }); assert.deepEqual(w1.urls, ['api/v1/notices?sgg=41450']);
  assert.equal(await R.fetchNotices({ fetch: async () => ({ ok: false, status: 502 }) }, '41450'), null); assert.equal(await R.fetchNotices({ fetch: async () => { throw new Error('x'); } }, '41450'), null);
  assert.equal(await R.fetchNotices({ fetch: async () => ({ ok: true, json: async () => ({ type: 'Other' }) }) }, '41450'), null); assert.equal(await R.fetchNotices({ fetch: async () => ({ ok: true, json: async () => ({ type: 'Notices', items: 'x' }) }) }, '41450'), null);
  const app = require('node:fs').readFileSync(require('node:path').join(__dirname, '../../assets/js/app.js'), 'utf8'), html = require('node:fs').readFileSync(require('node:path').join(__dirname, '../../index.html'), 'utf8');
  assert.match(app, /if \(REG\.slug \|\| !RES \|\| !RES\.sgg/); assert.match(app, /noticeRows\(data\)/); assert.match(app, /rel=\"noopener noreferrer\"/); assert.match(html, /id="secNotice"[^>]*hidden/);
  const r = bootWithPermits('?bjd=4145010800', { ...RESOLVED_BJD, sgg: '41450' }, () => json(200, PERMIT_FC)); await R.boot(r.win, r.doc);
  assert.deepEqual([r.win.RESOLVED.sgg, r.win.RESOLVED.bjd], ['41450', '4145010800']);                                                        // 화면이 해석 결과의 시군구·법정동을 알아 공고를 부른다
});

test('사업 id 로 열기: resolveUrl 은 project= 를 그대로 보내고, 필지가 연결된 사업은 필지처럼(17.6·필지 경계), 위치가 없으면 법정동·시군구처럼 연다', () => {
  assert.equal(R.resolveUrl(R.codeQuery('?project=PRJ-41450-0001&mode=progress')), 'api/v1/resolve?project=PRJ-41450-0001&geometry=1');
  const sq = { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] }, pg = { type: 'Polygon', coordinates: [[[0, 0], [0.1, 0], [0.1, 0.1], [0, 0]]] };
  const base = { type: 'project', center: [127.2, 37.54], coverage: { tier: 'none' } };
  assert.deepEqual(R.resolvedStart({ ...base, bjd: '4145010800', pnu: '4145010800105690000', parcel: { geometry: pg }, geometry: sq }), { center: [127.2, 37.54], zoom: 17.6 });
  assert.equal(R.resolvedShape({ ...base, bjd: '4145010800', pnu: '4145010800105690000', parcel: { geometry: pg }, geometry: sq }), pg);
  assert.deepEqual(R.resolvedStart({ ...base, bjd: '4145011400', geometry: sq }), { center: [127.2, 37.54], zoom: 15.4 }); assert.equal(R.resolvedShape({ ...base, bjd: '4145011400', geometry: sq }), sq);   // 위치 미연결: 법정동 경계
  assert.equal(R.resolvedStart({ ...base, coverage: { tier: 'A' } }), null, '번들이 있는 시군구까지만 열린 사업은 지역 기본 시점'); assert.equal(R.resolvedShape({ ...base, coverage: { tier: 'A' }, geometry: sq }), null);
  assert.ok(R.noticeText(['project-unlocated', 'project-superseded']).includes('위치(필지)가 아직 연결되지 않아')); assert.ok(R.noticeText(['project-superseded']).includes('합병되어 폐기된 사업 id'));
});

test('boot: 사업 id(?project=)로 번들이 있는 지역을 열면 그 단지를 연다(project.block), 번들이 없으면 필지의 인허가 단지를 연다', async () => {
  const urls = [], pg = { type: 'Polygon', coordinates: [[[126.75, 37.55], [126.76, 37.55], [126.76, 37.56], [126.75, 37.55]]] };
  const { win, doc } = bootWith('?project=PRJ-28245-0001&mode=progress', (u) => { urls.push(u); return json(200, { type: 'project', canonical: 'PRJ-28245-0001', level: 'umd', name: '인천광역시 계양구 박촌동', pnu: '2824510900101840001', bjd: '2824510900', center: [126.755, 37.555], parcel: { geometry: pg }, geometry: pg,
    project: { id: 'PRJ-28245-0001', stageCode: '05', stage: '공급', pnus: ['2824510900101840001'], bjdCodes: ['2824510900'], block: 'z1-A1' }, coverage: { tier: 'A', slug: 'r1' } }); });
  const r = await R.boot(win, doc);
  assert.equal(r.ok, true); assert.deepEqual(urls, ['api/v1/resolve?project=PRJ-28245-0001&geometry=1']); assert.equal(win.REGION.slug, 'r1');
  assert.deepEqual([win.RESOLVED.type, win.RESOLVED.parcel, win.RESOLVED.projectId], ['project', true, 'PRJ-28245-0001']); assert.deepEqual(win.RESOLVED.start, { center: [126.755, 37.555], zoom: 17.6 });
  assert.equal(win.RESOLVED.block, 'z1-A1', '번들 단지(pid z1-A1)를 연 채로 시작한다');
  const none = bootWith('?project=PRJ-28245-0001', () => json(200, { type: 'project', canonical: 'PRJ-28245-0001', level: 'sgg', name: '인천광역시 계양구', center: [126.7, 37.5], project: { id: 'PRJ-28245-0001', stageCode: '05', stage: '공급', pnus: [], bjdCodes: [], block: '없는-단지' }, warnings: ['project-unlocated'], coverage: { tier: 'A', slug: 'r1' } }));
  await R.boot(none.win, none.doc); assert.equal(none.win.RESOLVED.block, null, '번들에 없는 단지 id 면 단지를 열지 않고 지역만 연다'); assert.equal(none.win.RESOLVED.start, null);
});

test('permitsToProjects: 사업 id(projectId)가 있으면 단지에 싣는다(형식이 맞을 때만)', () => {
  const ring = [[127.2, 37.54], [127.201, 37.54], [127.201, 37.541], [127.2, 37.541], [127.2, 37.54]];
  const fc = (props) => ({ features: [{ properties: { pnu: '4145010800105690000', name: '덕풍', label: '덕풍', status: '계획', units: 10, records: 1, ...props }, geometry: { type: 'Polygon', coordinates: [ring] } }] });
  assert.equal(R.permitsToProjects(fc({ projectId: 'PRJ-41450-0001' }))[0].projectId, 'PRJ-41450-0001');
  for (const bad of [undefined, null, '', 'PRJ-1-1', 'x']) assert.equal(R.permitsToProjects(fc({ projectId: bad }))[0].projectId, null, String(bad));
});
