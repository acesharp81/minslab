'use strict';
/* 건물 요청 시 조회의 화면 연결(app.js·index.html·css): 정적 시험. 동작 자체는 lib/buildings.js·api/v1/buildings.js 시험과 브라우저 확인으로 본다 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', '..');
const read = (f) => fs.readFileSync(path.join(ROOT, f), 'utf8');
const app = read('assets/js/app.js'), html = read('index.html'), css = read('assets/css/app.css');

test('건물은 칸 단위로 /api/v1/buildings 에서 받고, 서버가 없으면(404·405·503) 더 부르지 않으며, 실패한 칸은 30초 뒤 다시 시도한다', () => {
  assert.match(app, /api\/v1\/buildings\?cell=\$\{key\}/);
  assert.match(app, /\[404, 405, 503\]\.includes\(res\.status\)/);
  assert.match(app, /DYN\.cells\.set\(key, Date\.now\(\) \+ 30000\)/);
  assert.match(app, /map\.on\('moveend', dynLoad\)/);
  assert.match(app, /minZ: 14\.6/); assert.match(app, /maxFeatures: 60000/); assert.match(app, /conc: 3/);
});

test('GY 를 자라는 배열로 둔다: 붙인 건물에 i 를 매기고 색·학교 강조·소스·그림자를 다시 반영하며, 번들 영역 안은 번들이 맡는다', () => {
  assert.match(app, /const HAS_GY = !!\(GY && GY\.features && \(GY\.features\.length \|\| GY\.dynamic\)\)/);
  assert.match(app, /function addBuildings\(feats\)[\s\S]*inBox\(featCenter\(f\.geometry\)\)[\s\S]*f\.properties\.i = i; GY\.features\.push\(f\)/);
  assert.match(app, /function flushBuildings\(\)[\s\S]*paintBuildings\(\)[\s\S]*FL\.annotate\(GY\.features\)[\s\S]*getSource\('official'\)[\s\S]*setData\(GY\)[\s\S]*officialShadowData\(\)/);
  assert.match(app, /function cellInBox\(ix, iy\)|const cellInBox = /);
  assert.match(app, /if \(DYN\.on && STATIC_N\)/);
});

test('요청 시 조회가 켜지면 학교·병원 강조 레이어를 미리 만들고, 꺼 두는 주소 ?dyn=0 을 따른다', () => {
  assert.match(app, /const HAS_FAC = DYN_ON \|\|/);
  assert.match(app, /get\('dyn'\) !== '0'/);
});

test('안내 띠: 확대 안내·불러오는 중·실패 문구가 #dynHint 에 뜨고 CSS 가 있다', () => {
  assert.match(html, /id="dynHint" role="status"/);
  assert.match(css, /\.dynhint\{/); assert.match(css, /\.dynhint\[hidden\]\{display:none\}/);
  assert.match(app, /지도를 확대\(\$\{DYN\.minZ\.toFixed\(1\)\} 이상\)하면 요청 시 불러옵니다/);
  assert.match(app, /건물 불러오는 중…/); assert.match(app, /일부 건물을 불러오지 못했습니다/);
});

test('기준일 문구: 요청 시 조회는 조회일을, 번들과 섞이면 둘 다 적는다', () => {
  assert.match(app, /\$\{BASIS_STATIC\}\(번들\) · 번들 밖은 \$\{TODAY\} 조회/);
  assert.match(app, /\$\{TODAY\} 조회\(요청 시\)/);
});

test('필지로 열면 그 필지의 인허가 단지를 연다: ?block= 이 없을 때 RES.block, 주석이 코드를 가리지 않는다', () => {
  const line = app.split('\n').find((l) => l.includes("const want = q.get('block')"));
  assert.ok(line);
  assert.match(line, /q\.get\('block'\) \|\| \(RES && RES\.block\)/);
  assert.match(line.split('//')[0], /focusBlock\(wb\.id, \{ toggle: false \}\)/);   // 호출이 주석보다 앞에 있다(한 줄 안의 // 가 호출을 지우는 실수 방지)
});
