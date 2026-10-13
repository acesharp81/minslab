'use strict';
// 지도 로딩 화면(2026-10-10): 유리 카드 + 영역 다섯(지도 프로그램 · 지역 자료 · 배경 지도 · 건물·단지 · 지형)의 실시간 진행.
// 사용자 요청: "지도 로딩 화면을 현재 디자인에 맞춰서 좀 더 품질을 개선" → "로딩이 실시간이 아닌거 같은데 실시간으로 처리되는 영역별로 보여지도록".
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const html = read('index.html'), app = read('assets/js/app.js'), css = read('assets/css/app.css'), island = read('components/MapIsland.tsx');
const LV = require('../../assets/js/loadview.js');

test('마크업: 표지·제목(상태 알림)·경과 시간·영역 다섯 줄(이름 | 막대 | 값), 처음엔 지도 프로그램만 준비 중', () => {
  const m = /<div id="loading">([\s\S]*?)\n  <\/div>\n  <div id="fatal"/.exec(html);
  assert.ok(m, '#loading 블록');
  assert.match(m[1], /<svg class="ld-mark"[^>]*aria-hidden="true">/);
  assert.match(m[1], /<div class="ld-text" role="status"><b>공급 지도를 여는 중<\/b><span id="ldSub">지역 자료를 읽고 있습니다<\/span><\/div>/);
  assert.match(m[1], /<span class="ld-time" id="ldTime" aria-hidden="true"><\/span>/);
  assert.match(m[1], /<ol class="ld-rows" aria-hidden="true">/, '숫자가 계속 바뀌는 줄은 화면 읽기에 알리지 않는다');
  assert.deepEqual([...m[1].matchAll(/<li data-area="(\w+)" data-st="(\w+)"><span class="ld-name">([^<]+)<\/span><i class="ld-bar"><\/i><span class="ld-val">([^<]+)<\/span><\/li>/g)].map((x) => x.slice(1)),
    [['code', 'active', '지도 프로그램', '준비 중'], ['data', 'wait', '지역 자료', '대기'], ['base', 'wait', '배경 지도', '대기'], ['bld', 'wait', '건물·단지', '대기'], ['dem', 'wait', '지형', '대기']]);
  assert.deepEqual(LV.AREAS, ['code', 'data', 'base', 'bld', 'dem']);
});

test('영역 상태(순수): 대기 → 받는 중(셀 것이 없으면 하는 일, 있으면 n/m + 지금 받는 것, 막대 = 받은/요청) → 완료(✓ 끝난 시각, 제목에 개수·크기·실패)', () => {
  const a = LV.newArea();
  assert.deepEqual(LV.areaView('base', a), { st: 'wait', frac: 0, val: '대기', title: '' });
  a.t0 = 10;
  assert.equal(LV.areaView('bld', a).val, '건물 정리 중');
  assert.equal(LV.areaView('base', a).val, '타일 요청 중');
  ['t1', 't2', 't3', 't4'].forEach((k) => a.want.add(k)); a.got.add('t1');
  assert.deepEqual(LV.areaView('dem', a), { st: 'active', frac: 0.25, val: '1/4장', title: '' });
  a.now = '건물 받는 중';
  assert.equal(LV.areaView('data', a).val, '1/4개 · 건물 받는 중');
  a.got.add('t2'); a.got.add('t3'); a.got.add('t4'); a.bytes = 6012463; a.fail = 1; a.t1 = 2420;
  assert.deepEqual(LV.areaView('data', a), { st: 'done', frac: 1, val: '✓ 2.4초', title: '4개 · 5.7MB · 실패 1' });
  assert.equal(LV.sec(12345), '12초'); assert.equal(LV.fmtBytes(41598), '41KB'); assert.equal(LV.fmtBytes(512), '512B');
});

test('지역 자료로 세는 요청(nameOf): 번들 파일·코드 해석·인허가·기반시설만, 공고·버스·타일은 세지 않는다', () => {
  const cases = { 'regions/index.json': '지역 목록', '/regions/incheon-gyeyang/region.json': '지역 정보', 'regions/a/projects.json': '단지', 'regions/a/buildings.json': '건물', 'regions/a/context.json': '역·학교', 'regions/a/infra.json': '기반시설',
    'api/v1/resolve?sgg=28245&geometry=1': '코드 해석', 'api/v1/permits?bjd=4145010800': '인허가', 'api/v1/infra?bjd=4145010800': '기반시설', 'api/v1/notices?sgg=41450': null, 'api/bus?region=x': null, 'https://api.vworld.kr/req/wmts/1.0.0/k/white/15/1/2.png': null };
  for (const [u, want] of Object.entries(cases)) assert.equal(LV.nameOf(u), want, u);
});

test('알리는 쪽: 지도 섬·옛 로더가 스크립트 7개를, boot 동안 감싼 fetch 가 지역 자료를, app.js 가 소스별 타일(배경·건물·지형)을 알리고 첫 idle 에서 닫는다', () => {
  assert.match(island, /lv!?\.want\('code', s\)/); assert.match(island, /load\(s\)\.then\(step\(s\)\)/);
  assert.match(island, /const restore = lv \? lv\.trackFetch\(window\) : \(\) => \{\};\n        return w\.RegionLoader!\.boot\(window, document\)\.finally\(\(\) => \{ restore\(\); if \(lv\) lv\.finish\('data'\); \}\);/);
  assert.match(html, /<script src="assets\/js\/loadview\.js"><\/script>/);
  assert.match(html, /if \(lv\) restore = lv\.trackFetch\(window\); return window\.RegionLoader\.boot\(window, document\);/);
  assert.match(app, /LV\.watchMap\(map, \{ base: \['vworld', 'openmaptiles', 'ofm'\], bld: \['official', 'dongs', 'dong-shadow', 'blocks', 'other-blocks'\], dem: \['dem', 'dem-shade'\] \}\);/);
  assert.match(app, /firstIdle = false; if \(LV\) LV\.close\(\); else \$\('#loading'\)\.hidden = true;/);
  const lv = read('assets/js/loadview.js');
  for (const ev of ['sourcedataloading', 'sourcedata', 'sourcedataabort', 'error']) assert.match(lv, new RegExp(`${ev}: \\(e\\) =>`), ev);
  assert.match(lv, /const settled = \(id\) => A\[id\]\.want\.size > 0 && groups\[id\]\.every/, '타일을 하나도 세기 전에는 끝내지 않는다');
  assert.match(lv, /return \(\) => \{ win\.fetch = orig; \};/, 'fetch 는 지역 자료 구간이 끝나면 되돌린다');
});

test('스타일: 흐린 지도 위 유리 카드, 막대는 각지고 실제 비율(--p)로 채워짐, 걷힐 때 서서히, 움직임 줄이기면 멈춤', () => {
  const rule = (sel) => { const i = css.indexOf(sel + '{'); assert.ok(i >= 0, sel); return css.slice(i, css.indexOf('}', i)); };
  assert.match(rule('#loading'), /backdrop-filter:blur\(5px\)/);
  assert.match(rule('#loading'), /transition:opacity \.35s ease,display \.35s allow-discrete/);
  assert.match(rule('#loading[hidden]'), /display:none;opacity:0/);
  assert.match(rule('.ld-card'), /background:var\(--glass-card\)/);
  assert.doesNotMatch(rule('.ld-bar'), /border-radius/);
  assert.match(rule('.ld-bar::before'), /width:var\(--p,0%\)/);
  assert.match(css, /@media \(prefers-reduced-motion:reduce\)\{\n  #loading\{transition:none\}\n  \.ld-mark \.ld-wave,\.ld-rows li\[data-st="active"\] \.ld-bar::after\{animation:none\}/);
  assert.match(css, /@keyframes spin\{/, '주소 입력줄 조회 표시가 쓰는 회전');
  assert.doesNotMatch(css, /html\[data-map-shell\]:not\(\.dark\) #loading/, '라이트도 같은 토큰(--bg·--glass-card)으로');
});

test('지도 화면은 index.html 을 그릴 때 읽는다(개발 서버가 고친 마크업을 다시 켜지 않고 내보낸다)', () => {
  const page = read('app/(map)/map/page.tsx');
  assert.match(page, /function mapMarkup\(\) \{\n  const html = fs\.readFileSync/);
  assert.match(page, /export default function MapPage\(\) \{\n  const markup = mapMarkup\(\);/);
});

test('건물 그림자(official-shadow)는 첫 idle 뒤에 붙는다: 건물이 많은 지역(계양 16,724동)에서 그림자 도형 계산·두 번째 큰 GeoJSON 이 로딩을 늦추지 않게', () => {
  assert.match(app, /if \(map\.getZoom\(\) >= 14\.3\) \{ if \(firstIdle\) map\.once\('idle', addOfficialShadows\); else addOfficialShadows\(\); \}/);
  assert.match(app, /map\.on\('zoom', \(\) => \{ if \(!firstIdle && map\.getZoom\(\) >= 14\.3\) addOfficialShadows\(\); \}\);/);
  assert.ok(app.indexOf("map.on('style.load', setupCustom);") < app.indexOf('let firstIdle = true;'), 'setupCustom 은 style.load(비동기)에서만 돌아 뒤에 선언된 firstIdle 을 읽어도 된다');
});

test('글꼴은 display block: 대체 글꼴로 먼저 그렸다 바꾸면 상단 메뉴가 좌우로 오므라든다(메뉴 708→655px)', () => {
  const fonts = read('lib/shell/fonts.ts');
  assert.match(fonts, /display: 'block',/);
  assert.doesNotMatch(fonts, /display: 'swap'/);
});
