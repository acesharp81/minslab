// 기존 건물 중 기반시설(학교·병원·공공·복지): 분류 규칙, 이름표 점, 강조색과 지도 연결을 확인한다.
// 규칙은 실제 건물 자료(regions/*/buildings.json)의 이름·용도 목록을 보고 정했으므로, 실자료 회귀 검사도 함께 둔다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const FL = require('../../assets/js/facility.js');

const ROOT = path.join(__dirname, '..', '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const app = read('assets/js/app.js'), css = read('assets/css/app.css'), html = read('index.html');
const cls = (n, u) => FL.classify({ n, u });

test('이름 키워드가 먼저: 학교·유치원·어린이집은 교육, 병원은 의료, 구청·경찰·경로당은 공공·복지', () => {
  for (const n of ['효성초등학교', '경인교육대학교', '보람유치원', '예능어린이집', '인혜학교', '산포초등학교 관사']) assert.equal(cls(n, ''), 'edu', n);
  for (const n of ['효사랑병원', '성로요양병원', '하나여성병원', '성베드로한방병원']) assert.equal(cls(n, ''), 'med', n);
  for (const n of ['인천광역시 계양구청사', '계양경찰서', '산포파출소', '효성1동이촌경로당', '계양1동 주민센터', '작전2동 행정복지센터', '계양소방서', '효성체육문화센터']) assert.equal(cls(n, ''), 'pub', n);
  assert.equal(cls('열린병원', '제2종근린생활시설'), 'med');            // 용도가 달라도 이름이 병원이면 병원
  assert.equal(cls('계양경찰서', '업무시설'), 'pub');
});

test('상가·아파트·교회·농협 이름은 용도가 교육연구·의료·노유자여도 칠하지 않는다', () => {
  const bad = [['프리드빌딩', '교육연구시설'], ['현대아파트', '교육연구시설'], ['(주)엘지씨엔에스', '교육연구시설'], ['삼성프라자', '노유자시설'], ['키위타워', '노유자시설'],
    ['학마을 영남아파트', '노유자시설'], ['동양빌딩', '의료시설'], ['청운교회 교육연구시설', '교육연구시설'], ['계암교회 교육관', '노유자시설'], ['계양농협 경제사업장', '업무시설'], ['금천농협남부지소 양곡창고', '']];
  for (const [n, u] of bad) assert.equal(cls(n, u), null, `${n} / ${u}`);
  assert.equal(cls('동보아파트 유치원', '노유자시설'), 'edu');           // 단지 안 유치원처럼 강한 키워드는 믿는다
  assert.equal(cls('○○빌딩 의원', '제2종근린생활시설'), null);          // 건물 안 의원은 건물 전체를 칠하지 않는다
});

test('이름이 없거나 일반명(가동·16동·주건축물)이면 용도만 따른다: 교육연구→교육, 의료→의료, 공공·노유자→공공·복지', () => {
  assert.equal(cls('', '교육연구시설'), 'edu');
  assert.equal(cls('', '교육연구및복지시설'), 'edu');
  assert.equal(cls('C동', '의료시설'), 'med');
  assert.equal(cls('', '공공용시설'), 'pub');
  assert.equal(cls('', '노유자시설'), 'pub');
  assert.equal(cls('주건축물제1동', '노유자시설'), 'pub');
  assert.equal(cls('', '공동주택'), null);
  assert.equal(cls('', '제2종근린생활시설'), null);
  assert.equal(cls('', '업무시설'), null);                                // 업무시설은 이름 키워드가 있을 때만(오피스텔과 구청사가 섞여 있다)
  assert.equal(cls(undefined, undefined), null); assert.equal(FL.classify(null), null);
});

test('이름표 점: 같은 이름·같은 동은 가장 높은 한 동에만, 괄호·주건축물 꼬리는 덜어 낸다', () => {
  const sq = (x, y) => [[[x, y], [x + 0.0002, y], [x + 0.0002, y + 0.0002], [x, y + 0.0002], [x, y]]];
  const mk = (n, u, eh, x, d = '계산동') => ({ type: 'Feature', properties: { n, u, eh, d }, geometry: { type: 'Polygon', coordinates: sq(x, 37.5) } });
  const fs2 = [mk('경인교육대학교', '교육연구시설', 10, 126.70), mk('경인교육대학교', '교육연구시설', 30, 126.71), mk('경인교육대학교', '교육연구시설', 20, 126.72),
    mk('효사랑병원 주건축물2동', '의료시설', 12, 126.73), mk('인천계양초등학교(1동)', '교육연구시설', 9, 126.74), mk('삼성프라자', '노유자시설', 9, 126.75), mk('', '교육연구시설', 5, 126.76)];
  const r = FL.annotate(fs2);
  assert.deepEqual(r.count, { edu: 5, med: 1, pub: 0 });
  assert.deepEqual(fs2.map((f) => f.properties.fc || null), ['edu', 'edu', 'edu', 'med', 'edu', null, 'edu']);   // 건물마다 분류가 남는다(색·팝업용)
  const names = r.points.features.map((f) => f.properties.n).sort();
  assert.deepEqual(names, ['경인교육대학교', '인천계양초등학교', '효사랑병원']);   // 이름 없는 건물·상가는 이름표가 없다
  const gy = r.points.features.find((f) => f.properties.n === '경인교육대학교');
  assert.equal(gy.properties.eh, 30);                                      // 가장 높은 동
  assert.ok(Math.abs(gy.geometry.coordinates[0] - 126.7101) < 0.001);
  // 다른 동(d)의 같은 이름은 각각 붙는다
  const r2 = FL.annotate([mk('유치원', '', 5, 126.7, '효성동'), mk('유치원', '', 5, 126.8, '계산동')]);
  assert.equal(r2.points.features.length, 2);
  assert.deepEqual(FL.annotate([]).points.features, []);
});

test('실자료 회귀: 계양에서 교육·공공복지·의료가 칠해지되 전체의 5%를 넘지 않고, 이름표에 상가식 이름이 없다', () => {
  const d = JSON.parse(read('regions/incheon-gyeyang/buildings.json'));
  const r = FL.annotate(d.features);
  const total = r.count.edu + r.count.med + r.count.pub;
  assert.ok(r.count.edu >= 150 && r.count.med >= 15 && r.count.pub >= 100, JSON.stringify(r.count));
  assert.ok(total / d.features.length < 0.05, `비율 ${(total / d.features.length * 100).toFixed(1)}%`);
  const shop = r.points.features.map((f) => f.properties.n).filter((n) => /빌딩|오피스텔|프라자|타워|농협|교회/.test(n));
  assert.deepEqual(shop, []);
  assert.ok(r.points.features.length >= 100 && r.points.features.length <= r.count.edu + r.count.med + r.count.pub);
});

// ---- 지도 연결(app.js·css) ----
const hue = (h) => { const [r, g, b] = [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255), mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn; if (!d) return 0; const x = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4; return (x * 60 + 360) % 360; };
const hueGap = (a, b) => { const d = Math.abs(hue(a) - hue(b)); return Math.min(d, 360 - d); };
const lum = (h) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; const [r, g, b] = [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)); return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
const contrastOnNavy = (h) => (lum(h) + 0.05) / (lum('#0A1030') + 0.05);   // 지도 바탕(THEME.bg) 위 이름표 글자
const FAC = (() => { const m = /fac: \{ edu: \{ c: '(#\w{6})', t: '(#\w{6})' \}, med: \{ c: '(#\w{6})', t: '(#\w{6})' \}, pub: \{ c: '(#\w{6})', t: '(#\w{6})' \} \}/.exec(app); assert.ok(m, 'THEME.fac 를 찾을 수 없음'); return { edu: { c: m[1], t: m[2] }, med: { c: m[3], t: m[4] }, pub: { c: m[5], t: m[6] } }; })();

test('강조색은 상태색·점검 보라와 색상각이 18° 이상 떨어지고, 이름표 글자는 네이비 바탕에서 4.5:1 이상이다', () => {
  const status = [...(/const COLOR = \{([^}]*)\}/.exec(app)[1]).matchAll(/(\w+): '(#\w{6})'/g)].filter(([, k]) => k !== 'plan' && k !== 'priv').map((m) => [m[1], m[2]]);   // 회색 계열은 색상각이 뜻이 없다
  status.push(['edu(신설 학교)', '#B79CFF']);
  for (const [k, v] of Object.entries(FAC)) {
    for (const [n, c] of status) assert.ok(hueGap(v.c, c) >= 18, `${k} ${v.c} ↔ ${n} ${c}: ${hueGap(v.c, c).toFixed(0)}°`);
    assert.ok(contrastOnNavy(v.t) >= 4.5, `${k} 글자 ${v.t} ${contrastOnNavy(v.t).toFixed(1)}:1`);
  }
  const ks = Object.keys(FAC);
  for (let i = 0; i < ks.length; i++) for (let j = i + 1; j < ks.length; j++) assert.ok(hueGap(FAC[ks[i]].c, FAC[ks[j]].c) >= 40, `${ks[i]}↔${ks[j]}`);
});

test('건물 색은 강조색으로 덮이고, 흐리게(기본)에서도 기반시설은 지금처럼 3D 로 남는다', () => {
  assert.match(app, /fac = p\.fc && T\.fac\[p\.fc\]/);
  assert.match(app, /let c = fac \? hex2\(fac\.c\)/);
  assert.match(app, /FL\.annotate\(GY\.features\)/);
  assert.doesNotMatch(app, /dimK|p\.cd\b|p\.crd\b/);   // 옛 흐리게(반투명 3D)는 없다: 기반시설을 흐리게 하지 않는다
  assert.match(app, /const IS_FAC = \['has', 'fc'\]/);
});

test('이름표 층(fac-label)은 이름 있는 기반시설만, 확대 15.2부터, 큰 건물 먼저, 분류별 진한 글자색으로 그린다', () => {
  const m = /id: 'fac-label'[\s\S]*?\} \}\);/.exec(app);
  assert.ok(m, 'fac-label 층을 찾을 수 없음');
  assert.match(m[0], /source: 'fac-pts'/); assert.match(m[0], /minzoom: 15\.2/);
  assert.match(m[0], /'text-field': \['get', 'n'\]/); assert.match(m[0], /'symbol-sort-key': \['-', 0, \['get', 'eh'\]\]/);
  assert.match(m[0], /T\.fac\.edu\.t.*T\.fac\.med\.t.*T\.fac\.pub\.t/);
  assert.match(m[0], /'text-halo-width'/);
  assert.match(app, /src\('fac-pts', \{ type: 'geojson', data: FAC\.points \}\)/);
});

test('범례에 기존 학교·병원·공공시설 한 줄이 있고 견본 색이 CSS 와 THEME 에서 같다', () => {
  assert.match(app, /add\('<i class="sw fac-edu"><\/i><i class="sw fac-med"><\/i><i class="sw fac-pub"><\/i>', '기존 학교·병원·공공시설'/);
  for (const k of ['edu', 'med', 'pub']) assert.match(css, new RegExp(`\\.sw\\.fac-${k}\\{background:${FAC[k].c}\\}`, 'i'));
});

test('공식 건물 팝업 부제에 분류명이 붙고, 분류 모듈은 화면 스크립트보다 먼저 불러온다', () => {
  assert.match(app, /\[p\.d, p\.fc && FL\.NAMES\[p\.fc\]\]/);
  assert.match(html, /load\('assets\/js\/infra\.js'\), load\('assets\/js\/facility\.js'\)/);
  assert.ok(html.indexOf("facility.js") < html.indexOf("assets/js/app.js"));
});
