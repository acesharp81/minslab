// 기존 건물 흐리게(기본 켬): 학교·병원·공공시설만 3D 로 두고 나머지 건물은 채우지 않은 점선 윤곽만 그린다(확대 15 이상, 그보다 멀리서는 그리지 않는다).
// 끄면(주소 dim=0) 모든 건물이 3D 로 채워진다. 화면의 실제 모양은 ?selftest 로 열어 확인하고, 여기서는 층·필터 규칙을 확인한다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..');
const app = fs.readFileSync(path.join(ROOT, 'assets/js/app.js'), 'utf8');
const css = fs.readFileSync(path.join(ROOT, 'assets/css/app.css'), 'utf8');
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');

test('기본은 흐리게 켬이고, 주소 dim=0 으로 끈다. 옵션 창이 아니라 위 도구 줄의 누름 단추(건물 흐리게)다(2026-10-10 사용자 요청)', () => {
  assert.match(app, /let dimExisting = q\.get\('dim'\) !== '0';/);
  assert.match(app, /set\('dim', dimExisting \? '' : '0'\)/);
  assert.match(html, /<div class="tools" role="toolbar" aria-label="시점과 옵션">[\s\S]*?<button type="button" id="dimBtn" aria-pressed="true" title="기존 건물 흐리게:[^"]*">건물 흐리게<\/button>[\s\S]*?<\/div>\s*<\/div>\s*<div class="optpanel"/);
  assert.doesNotMatch(html, /dimChip/, '옵션 창에는 없다');
  assert.match(app, /\$\('#dimBtn'\)\.setAttribute\('aria-pressed', String\(dimExisting\)\)/);
  assert.match(app, /\$\('#dimBtn'\)\.addEventListener\('click', \(\) => \{ dimExisting = !dimExisting; syncChips\(\); applyDim\(\); syncUrl\(openId\(\)\);/);
  assert.doesNotMatch(app, /dimExisting \? 1 : 0|dimExisting = true;/, '옵션 개수·옵션 되돌리기에는 넣지 않는다');
});

test('점선 윤곽 층: 선(점선)이고 면이 아니며, 시설이 아닌 건물만, 확대 15 이상에서만 그린다', () => {
  const m = /add\(\{ id: 'official-outline'[^\n]*\n/.exec(app);
  assert.ok(m, 'official-outline 층을 찾을 수 없음');
  assert.match(m[0], /type: 'line'/); assert.match(m[0], /source: 'official'/); assert.match(m[0], /minzoom: 15/);
  assert.match(m[0], /filter: NOT_FAC/); assert.match(m[0], /'line-dasharray': \[2, 2\]/);
  assert.doesNotMatch(m[0], /fill-color|fill-opacity|fill-pattern/);        // 채우지 않는다
  assert.match(m[0], /visibility: 'none'/);                                  // 흐리게가 켜졌을 때만 applyOfficial 이 보인다
});

test('클릭 판: 보이지 않는 면(official-hit, 투명도 0)이 윤곽의 클릭을 받는다', () => {
  const m = /add\(\{ id: 'official-hit'[^\n]*\n/.exec(app);
  assert.ok(m, 'official-hit 층을 찾을 수 없음');
  assert.match(m[0], /type: 'fill'/); assert.match(m[0], /'fill-opacity': 0/); assert.match(m[0], /filter: NOT_FAC/); assert.match(m[0], /minzoom: 15/);
});

test('범례: 흐리게 켬이면 점선 견본과 설명, 끄면 높이 램프 견본', () => {
  assert.match(app, /if \(dimNow\) add\('<i class="sw outline"><\/i>', '기존 건물'/);
  assert.match(app, /else add\('<i class="sw ramp"><\/i>', '기존 건물'/);
  assert.match(css, /\.sw\.outline\{border:1\.5px dashed var\(--mute\);background:transparent\}/);
});

/* applyOfficial 을 가짜 지도에 돌려 층마다 어떤 필터가 걸리는지 확인한다 */
function run(dim, selId) {
  const src = /function applyOfficial\(\) \{[\s\S]*?\n\}\n/.exec(app);
  assert.ok(src, 'applyOfficial 을 찾을 수 없음');
  const LAYERS = ['official-3d', 'official-roof', 'official-far', 'official-flat', 'official-flat-line', 'official-ao', 'official-shadow', 'official-outline', 'official-hit'];
  const filters = {}, visible = {};
  const map = { getLayer: (id) => (LAYERS.includes(id) ? { id } : undefined), setFilter: (id, f) => { filters[id] = f; } };
  const vis = (id, on) => { visible[id] = on; };
  const KNOWN_H = ['!=', ['get', 'src'], '정보없음'], NO_INFO = ['==', ['get', 'src'], '정보없음'], IS_FAC = ['has', 'fc'], NOT_FAC = ['!', ['has', 'fc']];
  new Function('map', 'vis', 'KNOWN_H', 'NO_INFO', 'IS_FAC', 'NOT_FAC', 'dimExisting', 'selId', `${src[0]}; applyOfficial();`)(map, vis, KNOWN_H, NO_INFO, IS_FAC, NOT_FAC, dim, selId);
  return { filters, visible };
}
const has = (f, needle) => JSON.stringify(f).includes(JSON.stringify(needle));

test('흐리게 켬: 3D·평면·접지 음영·그림자는 시설 건물만, 윤곽과 클릭 판은 시설이 아닌 건물만 보인다', () => {
  const { filters: F, visible: V } = run(true, null);
  for (const id of ['official-3d', 'official-roof', 'official-far', 'official-flat', 'official-flat-line', 'official-ao']) assert.ok(has(F[id], ['has', 'fc']), `${id} 는 시설 건물만`);
  assert.deepEqual(F['official-shadow'], ['!=', ['get', 'fc'], '']);
  for (const id of ['official-outline', 'official-hit']) { assert.deepEqual(F[id], ['!', ['has', 'fc']]); assert.equal(V[id], true, `${id} 보임`); }
});

test('흐리게 끔: 모든 건물이 3D(시설 거름 없음)이고 윤곽·클릭 판은 숨는다', () => {
  const { filters: F, visible: V } = run(false, null);
  for (const id of ['official-3d', 'official-roof', 'official-far', 'official-flat', 'official-flat-line', 'official-ao']) assert.ok(!has(F[id], ['has', 'fc']), `${id} 에 시설 거름이 없어야 한다`);
  assert.equal(F['official-shadow'], null);
  for (const id of ['official-outline', 'official-hit']) assert.equal(V[id], false, `${id} 숨김`);
});

test('고른 건물은 두 모드 모두에서 3D·윤곽·클릭 판에서 빠진다(sel-3d 가 따로 그린다)', () => {
  for (const dim of [true, false]) {
    const { filters: F } = run(dim, 7);
    const ids = dim ? ['official-3d', 'official-roof', 'official-far', 'official-outline', 'official-hit'] : ['official-3d', 'official-roof', 'official-far'];
    for (const id of ids) assert.ok(has(F[id], ['!=', ['get', 'i'], 7]), `${id} dim=${dim}`);
  }
});
