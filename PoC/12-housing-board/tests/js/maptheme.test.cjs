'use strict';
// 지도 화면 배색·표시 개선(docs/product/화면-배색-개선-계획.md 3단계)을 정적으로 고정한다.
// 색은 대시보드 토큰(app/tailwind.css)과 한 곳에서 맞추고, 숨긴 구역·무늬 해상도·모바일 머리 줄 같은 표시 결함이 되살아나지 않게 한다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const css = read('assets/css/app.css'), app = read('assets/js/app.js'), tw = read('app/tailwind.css');
const twLight = tw.slice(tw.indexOf('\n:root {'), tw.indexOf('\n}\n', tw.indexOf('\n:root {')));
const twVar = (n) => { const m = new RegExp(`--${n}:\\s*(#[0-9A-Fa-f]{6})`).exec(twLight); assert.ok(m, `--${n}`); return m[1].toUpperCase(); };

test('Next 지도의 강조색은 대시보드 주색이고, 6단계 색은 대시보드 토큰(--st-*-ink)을 가리킨다', () => {
  const shell = /html\[data-map-shell\]\{([^}]*)\}/.exec(css);
  assert.ok(shell, 'html[data-map-shell] 공통 규칙');
  assert.match(shell[1], /--acc:var\(--primary\)/);
  assert.match(shell[1], /--acc-ink:var\(--primary-foreground\)/);
  for (const k of ['sale', 'build', 'soon', 'move', 'plan', 'priv']) assert.match(shell[1], new RegExp(`--${k}:var\\(--st-${k}-ink\\)`), k);
  const light = /html\[data-map-shell\]:not\(\.dark\)\{([^}]*)\}/.exec(css)[1];
  assert.doesNotMatch(light, /--(acc|sale|build|soon|move|plan|priv):/, '라이트 덮어쓰기에 단계색·강조색을 따로 두지 않는다');
  assert.match(light, new RegExp(`--warn:${twVar('warn')}`, 'i'), '라이트 지도 주의색 = 대시보드 --warn');
});

test('지도 스크립트는 지도 셸에서 단계색을 CSS 토큰으로 읽고(독립 지도는 다크 대체값), 라이트 3D 동 색의 높은 층 끝은 차트 면 색(--st-*)이다', () => {
  assert.match(app, /getPropertyValue\(`--st-\$\{k\}-ink`\)/);
  assert.match(app, /if \(SHELL\) applyStageInk\(\);/);
  assert.doesNotMatch(app, /LIGHT_COLOR/, '라이트 단계색 사본을 따로 두지 않는다');
  const tone = /const LIGHT_THEME = \{[\s\S]*?tone: \{([^}]*)\}/.exec(app)[1];
  for (const [k, st] of [['sale', 'sale'], ['build', 'build'], ['soon', 'soon'], ['move', 'move'], ['plan', 'plan'], ['priv', 'priv']]) {
    const m = new RegExp(`${k}: \\['#[0-9A-Fa-f]{6}', '(#[0-9A-Fa-f]{6})'\\]`).exec(tone);
    assert.ok(m, `tone.${k}`); assert.equal(m[1].toUpperCase(), twVar(`st-${st}`), `tone.${k} 높은 층 끝 = --st-${st}`);
  }
});

test("라이트 배경은 V-World 백지도('white'): 장소 글자가 그림에 박히지 않아 기울여도 번지지 않고 벡터 지명과 겹치지 않는다", () => {
  assert.match(app, /const LIGHT_THEME = \{[\s\S]*?vw: 'white', ofm: 'liberty', raster: \{ 'raster-saturation': -0\.35, 'raster-contrast': -0\.05 \}/, '백지도의 공원 무늬는 채도로 누르고, 대비는 조금만 낮춘다(−0.12 는 뭉개져 보였다: 같은 화면 가장자리 선명도 15.71→16.43, 2026-10-10 계획서 14절 T4)');
  assert.match(app, /\{ id: 'vworld', type: 'raster', source: 'vworld', paint: TH\(\)\.raster \|\| \{\} \}/);
  /* 줄 끝 주석이 같은 줄의 라이트 글자·테두리 색을 삼키면 지도 글자가 다크 값(밝은 글자·남색 테두리)으로 그려진다(2026-10-09 실제로 겪음) */
  const line = app.split('\n').find((l) => l.startsWith("  vw: 'white'"));
  assert.ok(line && !line.includes('//'), '라이트 테마 첫 줄에 주석이 없어야 한다');
  for (const kv of ["text: '#172B4D'", "halo: '#FFFFFF'", "sub: '#526176'"]) assert.ok(line.includes(kv), kv);
});

test('블록 무늬는 24px 그림을 배율 2 로 올려 12px 주기로 반복하고, 멀리서는 옅어진다(기울인 지도의 무아레 방지)', () => {
  assert.match(app, /function patternImage\(kind\) \{\n  const s = 24,/);
  for (const n of ['hatch', 'dots', 'cross']) assert.match(app, new RegExp(`map\\.addImage\\('${n}', patternImage\\('${n}'\\), \\{ pixelRatio: 2 \\}\\)`));
  for (const n of ['hatch', 'dots', 'cross']) assert.match(app, new RegExp(`'fill-pattern': '${n}', 'fill-opacity': PAT_OP`));
});

test('숨긴 패널 구역과 그 레일 점은 실제로 숨는다(.sec 의 display:flex 가 hidden 을 덮지 않게)', () => {
  assert.match(css, /\.sec\[hidden\],\.prail button\[hidden\]\{display:none\}/);
  assert.match(app, /\$\('#prail \[data-sec="h-next"\]'\)\.hidden = !rows\.length;/);
  assert.match(app, /\$\('#prail \[data-sec="h-tl"\]'\)\.hidden = !items\.length;/);
});

test('패널 그림(합계 막대·입주 타임라인·기반시설 타임라인)은 고정 다크 색 대신 테마 변수를 쓴다', () => {
  for (const bad of ['fill="#9AA8D6"', 'stroke="#3A4C8C"', "'#0A1030' : INK", 'fill="#FFD66E"', '#7BA7FF 0 4px,#0A1030']) assert.ok(!app.includes(bad), bad);
  assert.match(app, /const INK = \{ move: 'var\(--mute\)', edu: 'var\(--edu\)', transit: 'var\(--ink\)' \}/);
});

test('떠 있는 상자의 그림자는 테마 변수다: 다크는 짙게, 라이트는 남색으로 옅게', () => {
  assert.doesNotMatch(css.replace(/:root\{[^}]*\}/, ''), /box-shadow:0 10px 26px rgba\(0,0,0,\.42\)/);
  for (const v of ['--hud-shadow', '--tag-shadow', '--sheet-shadow', '--stuck-shadow']) {
    assert.match(css, new RegExp(`${v}:0 [^;]*rgba\\(0,0,0,`), `${v} 다크 값`);
    assert.match(/html\[data-map-shell\]:not\(\.dark\)\{([^}]*)\}/.exec(css)[1], new RegExp(`${v}:0 [^;]*rgba\\(15,23,42,`), `${v} 라이트 값`);
  }
});

test('축척·출처 컨트롤은 라이브러리 기본 흰 상자 대신 지도 유리와 같은 바탕·글자를 쓴다', () => {
  assert.match(css, /\.maplibregl-ctrl\.maplibregl-ctrl-scale\{background:var\(--glass-sum\);border-color:var\(--ink2\);color:var\(--ink\)/);
  assert.match(css, /\.maplibregl-ctrl\.maplibregl-ctrl-attrib\{background:var\(--glass-sum\)/);
});

test('900px 이하에서 지도 머리 줄과 지도는 상단 메뉴 바 높이만큼 내려온다(첫 줄이 메뉴 바에 가려 누를 수 없던 문제)', () => {
  const m = /@media \(max-width:900px\)\{\n  \.shell-map\{--nav-h:49px\}\n  \.shell-map \.mhead\{top:var\(--nav-h\)\}\n  \.shell-map \.mapwrap\{top:calc\(var\(--nav-h\) \+ var\(--mh\)\)\}\n\}/.exec(css);
  assert.ok(m, '.shell-map 모바일 머리 줄 내림 규칙');
  assert.match(read('components/TopNav.tsx'), /mobile:h-12/, '메뉴 바 높이(48px + 아래 선 1px)와 --nav-h 가 맞아야 한다');
});
