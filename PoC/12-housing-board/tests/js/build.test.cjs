const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { pickRegions, build } = require('../../scripts/build.js');

const idx = (regions) => ({ schema_version: '1.1.0', regions });
const R = (slug, extra = {}) => ({ slug, name: slug, visibility: 'public', updatedAt: '2026-10-04', schema_version: '1.1.0', ...extra });

test('pickRegions: 개발 빌드는 미리보기 지역도 남긴다', () => {
  const out = pickRegions(idx([R('a', { default: true }), R('b', { visibility: 'preview' })]), false);
  assert.deepEqual(out.regions.map((r) => r.slug), ['a', 'b']);
});

test('pickRegions: 운영 빌드는 미리보기 지역을 뺀다', () => {
  const out = pickRegions(idx([R('a', { default: true }), R('b', { visibility: 'preview' }), R('c')]), true);
  assert.deepEqual(out.regions.map((r) => r.slug), ['a', 'c']);
});

test('pickRegions: 기본 지역이 미리보기라 빠지면 남은 첫 지역이 기본이 된다', () => {
  const out = pickRegions(idx([R('p', { default: true, visibility: 'preview' }), R('a'), R('c')]), true);
  assert.deepEqual(out.regions.map((r) => [r.slug, !!r.default]), [['a', true], ['c', false]]);
});

test('pickRegions: 원본 객체를 바꾸지 않는다', () => {
  const src = idx([R('p', { default: true, visibility: 'preview' }), R('a')]);
  const before = JSON.stringify(src);
  pickRegions(src, true);
  assert.equal(JSON.stringify(src), before);
});

function fixture(regions, { withConfig = false } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hb-build-'));
  const w = (p, c) => { fs.mkdirSync(path.dirname(path.join(root, p)), { recursive: true }); fs.writeFileSync(path.join(root, p), c); };
  w('index.html', '<html></html>');
  w('assets/js/app.js', '//app');
  w('assets/README.md', 'docs');
  w('regions/index.json', JSON.stringify(idx(regions)));
  for (const r of regions) { w(`regions/${r.slug}/region.json`, '{}'); w(`regions/${r.slug}/projects.json`, '{}'); }
  w('data/old.js', 'legacy');   // 옛 data/ 는 배포 산출물에 들어가면 안 된다
  w('tools/secret.py', 'x');
  if (withConfig) w('config.js', "window.VWORLD_KEY = 'local-key-value';\n");
  return root;
}
const silent = () => {};

test('build(운영): 미리보기 지역 폴더와 색인 항목이 산출물에 없다, 공개 지역은 복사된다', () => {
  const root = fixture([R('a', { default: true }), R('b', { visibility: 'preview' })]);
  build({ root, env: { VERCEL_ENV: 'production' }, log: silent });
  assert.ok(fs.existsSync(path.join(root, 'public/regions/a/region.json')));
  assert.ok(!fs.existsSync(path.join(root, 'public/regions/b')));
  const out = JSON.parse(fs.readFileSync(path.join(root, 'public/regions/index.json'), 'utf8'));
  assert.deepEqual(out.regions.map((r) => r.slug), ['a']);
});

test('build(미리보기 배포·로컬): 미리보기 지역도 들어간다', () => {
  const root = fixture([R('a', { default: true }), R('b', { visibility: 'preview' })]);
  build({ root, env: { VERCEL_ENV: 'preview' }, log: silent });
  assert.ok(fs.existsSync(path.join(root, 'public/regions/b/region.json')));
  build({ root, env: {}, log: silent });
  assert.ok(fs.existsSync(path.join(root, 'public/regions/b/region.json')));
});

test('build: 필요한 것만 복사한다(assets, regions) — index.html(지도 마크업 정본, Next.js 가 루트에서 읽음)·data·tools·*.md 는 제외', () => {
  const root = fixture([R('a', { default: true })]);
  build({ root, env: {}, log: silent });
  const has = (p) => fs.existsSync(path.join(root, 'public', p));
  assert.ok(!has('index.html')); assert.ok(has('assets/js/app.js')); assert.ok(has('config.js'));
  assert.ok(!has('data')); assert.ok(!has('tools')); assert.ok(!has('assets/README.md'));
});

test('build: 색인에 있는데 폴더가 없으면 실패한다(조용히 빈 지역을 올리지 않는다)', () => {
  const root = fixture([R('a', { default: true })]);
  fs.rmSync(path.join(root, 'regions/a'), { recursive: true });
  assert.throws(() => build({ root, env: {}, log: silent }), /regions\/a/);
});

test('build: 환경변수 VWORLD_KEY 로 config.js 를 만들고, 없으면 로컬 config.js, 그것도 없으면 빈 키', () => {
  let root = fixture([R('a', { default: true })], { withConfig: true });
  build({ root, env: { VWORLD_KEY: 'env-key-value', VWORLD_LAYER: 'Satellite' }, log: silent });
  let cfg = fs.readFileSync(path.join(root, 'public/config.js'), 'utf8');
  assert.match(cfg, /VWORLD_KEY = "env-key-value"/); assert.match(cfg, /VWORLD_LAYER = "Satellite"/); assert.doesNotMatch(cfg, /local-key-value/);
  build({ root, env: {}, log: silent });
  assert.match(fs.readFileSync(path.join(root, 'public/config.js'), 'utf8'), /local-key-value/);
  root = fixture([R('a', { default: true })]);
  build({ root, env: {}, log: silent });
  assert.equal(fs.readFileSync(path.join(root, 'public/config.js'), 'utf8'), "window.VWORLD_KEY = '';\n");
});

test('build: 로그에 키 값을 찍지 않는다', () => {
  const root = fixture([R('a', { default: true })]);
  const lines = [];
  build({ root, env: { VWORLD_KEY: 'super-secret-key' }, log: (l) => lines.push(l) });
  assert.ok(lines.length > 0);
  assert.ok(!lines.join('\n').includes('super-secret-key'));
});

test('build: 로컬 config.js 를 고치지 않는다', () => {
  const root = fixture([R('a', { default: true })], { withConfig: true });
  const before = fs.readFileSync(path.join(root, 'config.js'), 'utf8');
  build({ root, env: { VWORLD_KEY: 'x' }, log: silent });
  assert.equal(fs.readFileSync(path.join(root, 'config.js'), 'utf8'), before);
});


test('build: HOME 지도 자료가 있으면 9·7 검토 범위를 기본 지역으로 기록한다', () => {
  const root = fixture([R('a', { default: true })]);
  fs.mkdirSync(path.join(root, 'data/home10'), { recursive: true });
  fs.writeFileSync(path.join(root, 'data/home10/map.json'), '{"format":"poc12-home10-map/1"}');
  build({ root, env: {}, log: silent });
  const index = JSON.parse(fs.readFileSync(path.join(root, 'public/regions/index.json'), 'utf8'));
  assert.equal(index.homeDefault, 'home-907');
  assert.ok(fs.existsSync(path.join(root, 'public/home10/map.json')));
});
