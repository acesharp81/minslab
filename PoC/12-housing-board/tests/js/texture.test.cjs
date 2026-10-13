'use strict';
// 화면 텍스처 개선(계획서 14·16절, 2026-10-10): 추이 그래프 선 굵기(E2), 잠정치 빗금(E3), 글꼴 역할(E4), 지도 바닥 텍스처 묶음(E5), 지형 과장(E6).
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const board = read('components/board/Board.tsx'), lines = read('components/charts/MonthLines.tsx'), tw = read('app/tailwind.css'), css = read('assets/css/app.css'), app = read('assets/js/app.js');

test('E2 추이 그래프: 줄여 그려도(0.6~1배) 선·격자·현재선 굵기는 화면 px(non-scaling-stroke)', () => {
  const svg = /<svg id="trend"[\s\S]*?<\/svg>/.exec(board)[0];
  const strokes = [...svg.matchAll(/<(line|polyline)[^>]*>/g)].map((m) => m[0]);
  assert.equal(strokes.length, 6, '격자 3 · 지연·주의 선 2 · 현재선 1');
  for (const s of [...svg.matchAll(/<(?:line|polyline)\b[^>]*\/>/g)].map((m) => m[0])) assert.match(s, /vectorEffect="non-scaling-stroke"/, s.slice(0, 60));
});

test('E3 잠정치 빗금: 가로로 늘어나는 SVG 무늬 대신 그래프 뒤 HTML 띠(45°)', () => {
  assert.doesNotMatch(lines, /<pattern|hatch-prov/);
  assert.match(lines, /data-slot="chart-prov"[^>]*repeating-linear-gradient\(45deg,/);
  assert.match(lines, /left: `\$\{\(L \+ step \* prov\[0\]\) \/ W \* 100\}%`, width: `\$\{step \* prov\.length \/ W \* 100\}%`/);
  assert.match(lines, /<svg preserveAspectRatio="none" className="relative block/, '그래프(SVG)가 띠 위에 그려진다');
});

test('E4 글꼴 역할: 본문은 시스템 한글 글꼴, 로고·메뉴·제목·큰 숫자는 Do Hyeon(대시보드·지도 같은 규칙)', () => {
  assert.match(tw, /--font-sans: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;/);
  assert.match(tw, /--font-display: var\(--font-do-hyeon, 'Do Hyeon'\)/);
  assert.match(tw, /h1, h2, h3 \{\n    font-family: var\(--font-display\);/);
  for (const f of ['app/(dashboard)/layout.tsx', 'app/(map)/layout.tsx']) { const s = read(f); assert.match(s, /className=\{`font-sans \$\{doHyeon\.variable\}/, f); assert.doesNotMatch(s, /doHyeon\.className/, f); }
  assert.match(read('components/TopNav.tsx'), /<header className="[^"]*font-display/);
  assert.match(read('components/ui.tsx'), /<b className="font-display text-\[32px\]/);
  assert.match(read('components/StageLadder.tsx'), /<b className="font-display text-\[20px\]/);
  assert.match(read('components/board/styles.ts'), /export const disp = "font-display /);
  assert.match(css, /:root\{--font-body:'Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif;--font-disp:var\(--font-do-hyeon,'Do Hyeon'\)/);
  for (const r of [/body\{font-family:var\(--font-body\);/, /\.maplibregl-map\{font-family:var\(--font-body\)\}/, /\.maplibregl-popup-content\{font:13px\/1\.5 var\(--font-body\);/, /h1\{margin:0;font-family:var\(--font-disp\);/, /\.sum \.big\{font-family:var\(--font-disp\);/]) assert.match(css, r);
  assert.doesNotMatch(css.replace(/:root\{--font-body[^\n]*\n/, ''), /var\(--font-do-hyeon/, 'Do Hyeon 은 --font-disp 로만 쓴다');
});

test('E5 지도 바닥 텍스처: 2D 선 층은 첫 3D 층(sel-3d) 앞으로 모으고, dong-line 은 minzoom 대신 투명도 단계', () => {
  assert.match(app, /if \(map\.getLayer\('sel-3d'\)\) for \(const id of \['official-ao', 'infra-link-zone', 'infra-link-new', 'bus-route-line'\]\) if \(map\.getLayer\(id\)\) map\.moveLayer\(id, 'sel-3d'\);/);
  const dl = /add\(\{ id: 'dong-line'[^\n]*/.exec(app)[0].split('//')[0];   // 주석 앞 코드만
  assert.doesNotMatch(dl, /minzoom/); assert.match(dl, /'line-opacity': \['step', \['zoom'\], 0, 15\.6, 0\.75\]/);
});

test('E6 지형 과장 1(30m급 표고를 과장하면 평지 바닥 선·면이 휘고 움직일 때 튄다)', () => {
  assert.match(app, /map\.setTerrain\(\{ source: 'dem', exaggeration: 1 \}\);/);
});
