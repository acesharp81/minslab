/* assets/js/bus.js — 버스 노선·위치의 순수 함수 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const B = require('../../assets/js/bus.js');

const close = (a, b, tol = 1e-6) => assert.ok(Math.abs(a - b) <= tol, `${a} ≉ ${b}`);
const cen = (b) => b.c;

test('노선 유형 색: 간선 하늘색, 지선 연두, 광역·급행·좌석 산호색 계열, 모르면 회청색(어두운 지도 위에서 보이는 밝은 색)', () => {
  assert.equal(B.routeColor('간선버스'), '#56B4E9');
  assert.equal(B.routeColor('지선버스'), '#5BD6A8');
  for (const t of ['광역버스', '급행버스', '좌석버스']) assert.equal(B.routeColor(t), '#FF8A65');
  assert.equal(B.routeColor('이상한버스'), '#9AA8D6');
  assert.equal(B.routeColor(undefined), '#9AA8D6');
});

test('방위: 북 0 · 동 90 · 남 180 · 서 270', () => {
  const o = [126.75, 37.55];
  close(B.bearing(o, [126.75, 37.56]), 0, 1e-6);
  close(B.bearing(o, [126.76, 37.55]), 90, 0.05);
  close(B.bearing(o, [126.75, 37.54]), 180, 1e-6);
  close(B.bearing(o, [126.74, 37.55]), 270, 0.05);
});

test('진행 방향: 마지막으로 지난 정류소 → 다음 정류소, 같은 좌표는 건너뛰고, 종점은 직전 구간, 모르면 null', () => {
  const path_ = [[126.75, 37.55], [126.75, 37.55], [126.76, 37.55], [126.76, 37.56]];
  close(B.headingOf(path_, 1), 90, 0.05);                  // 2번째 점이 같은 좌표라 건너뛴다
  close(B.headingOf(path_, 3), 0, 0.05);                   // 동쪽으로 간 뒤 북쪽
  close(B.headingOf(path_, 4), 0, 0.05);                   // 마지막 점은 직전 구간(북쪽)
  for (const [p, o] of [[null, 1], [[], 1], [path_, 0], [path_, 5], [path_, null], [[[126.7, 37.5]], 1], [[[126.7, 37.5], [126.7, 37.5]], 1]]) assert.equal(B.headingOf(p, o), null);
});

test('버스 바닥면: 닫힌 사각형이고 방향대로 길며, 방향을 모르면 정사각형에 가깝다', () => {
  const east = B.busRing(126.75, 37.55, 90), c = [126.75, 37.55];
  assert.equal(east.length, 5);
  assert.deepEqual(east[0], east[4]);
  close(B.distM(east[0], east[3]), B.BUS_LEN_M, 0.1);
  close(B.distM(east[0], east[1]), B.BUS_WID_M, 0.1);
  assert.ok(east.every((p) => Math.abs(p[1] - c[1]) < 0.0001));                       // 동쪽을 보면 위도 차이는 폭만큼만
  close(B.distM(B.busRing(126.75, 37.55, 90, 2)[0], B.busRing(126.75, 37.55, 90, 2)[3]), B.BUS_LEN_M * 2, 0.2);   // 크기 배율
  const unknown = B.busRing(126.75, 37.55, null);
  close(B.distM(unknown[0], unknown[1]), B.distM(unknown[1], unknown[2]), 0.2);
  const centre = [east.slice(0, 4).reduce((a, p) => a + p[0], 0) / 4, east.slice(0, 4).reduce((a, p) => a + p[1], 0) / 4];
  close(centre[0], 126.75, 1e-6); close(centre[1], 37.55, 1e-6);                      // 위치가 버스 중심
});

test('확대 단계별 크기: 17.5 이상은 실제 크기, 멀어질수록 커져 4배에서 멈춘다', () => {
  assert.equal(B.scaleFor(17.5), 1);
  assert.equal(B.scaleFor(19), 1);
  assert.equal(B.scaleFor(14), 4);
  assert.equal(B.scaleFor(10), 4);
  assert.equal(B.scaleFor(undefined), B.scaleFor(16));
  assert.ok(B.scaleFor(16) > 1.9 && B.scaleFor(16) < 2.2);
  let prev = Infinity;
  for (let z = 12; z <= 19; z += 0.5) { const s = B.scaleFor(z); assert.ok(s <= prev, z); prev = s; }
});

test('버스 모형: 부품이 제자리에 있고(앞·뒤·바퀴·지붕), 같은 높이의 면이 겹쳐 깜박이지 않는다', () => {
  const names = B.MODEL.map((m) => m[0]);
  for (const part of ['body', 'glass', 'cab', 'roof', 'sign', 'unit', 'bumper', 'wheel']) assert.ok(names.includes(part), part);
  assert.equal(names.filter((n) => n === 'wheel').length, 4);
  assert.equal(names.filter((n) => n === 'bumper').length, 2);
  for (const [n, a0, a1, b0, b1, z0, z1] of B.MODEL) {
    assert.ok(a0 < a1 && b0 < b1 && z0 < z1, n);
    assert.ok(a0 >= -6 && a1 <= 6 && b0 >= -1.4 && b1 <= 1.4 && z0 >= 0 && z1 <= 3.3, n);   // 실제 시내버스 크기 안
  }
  const m = Object.fromEntries(B.MODEL.map((r) => [r[0], r]));
  assert.equal(m.roof[5], m.glass[6]);                                                  // 지붕은 창 위에 얹힌다
  assert.equal(m.glass[6], m.cab[6]);                                                   // 앞 유리와 옆 창의 높이가 같다
  assert.ok(m.cab[1] >= m.glass[2]);                                                    // 앞 유리는 창띠 앞쪽
  assert.ok(m.unit[5] >= m.roof[6]);                                                    // 에어컨은 지붕 위
  for (let i = 0; i < B.MODEL.length; i++) for (let j = i + 1; j < B.MODEL.length; j++) {
    const [x, y] = [B.MODEL[i], B.MODEL[j]], overlapA = x[1] < y[2] && y[1] < x[2], overlapB = x[3] < y[4] && y[3] < x[4];
    if (overlapA && overlapB) assert.ok(Math.abs(x[6] - y[6]) > 1e-9, `${x[0]}·${y[0]} 윗면이 같은 높이로 겹침`);
  }
  assert.equal(B.MODEL_BLOB.length, 3);
});

test('3D 조각과 라벨: 방향을 알면 모형 12조각, 모르면 덩어리 3조각, 번호 라벨은 한 대에 하나', () => {
  const routes = [{ id: 'R87', no: '87', type: '간선버스', path: [[126.75, 37.55], [126.76, 37.55]] }];
  const f = B.features([{ v: 'a', r: 'R87', lon: 126.751, lat: 37.55, ord: 1 }, { v: 'b', r: 'RX', lon: 126.752, lat: 37.55, ord: 1 }], routes);
  assert.equal(f.solids.features.length, B.MODEL.length + B.MODEL_BLOB.length);
  assert.equal(f.labels.features.length, 2);
  const parts = (v) => f.solids.features.filter((x) => x.properties.v === v);
  assert.equal(parts('a').length, B.MODEL.length);
  assert.equal(parts('b').length, B.MODEL_BLOB.length);
  const body = parts('a').find((x) => x.properties.part === 'body'), sign = parts('a').find((x) => x.properties.part === 'sign'), glass = parts('a').find((x) => x.properties.part === 'glass');
  assert.equal(body.properties.c, '#56B4E9');                                           // 차체·앞 표지는 노선 색
  assert.equal(sign.properties.c, '#56B4E9');
  assert.equal(glass.properties.c, B.GLASS_COLOR);
  close(body.properties.base, 0.45); close(body.properties.h, 1.45);
  assert.ok(glass.properties.base >= body.properties.h - 1e-9);                         // 창띠는 차체 위에 얹힌다
  assert.equal(f.labels.features[0].properties.text, '87번');
  assert.equal(f.labels.features[1].properties.text, '버스');
  assert.deepEqual(f.labels.features[0].geometry.coordinates, [126.751, 37.55]);
  const big = B.features([{ v: 'a', r: 'R87', lon: 126.751, lat: 37.55, ord: 1 }], routes, 2).solids.features.find((x) => x.properties.part === 'body');
  close(big.properties.base, 0.9); close(big.properties.h, 2.9);                         // 크기 배율은 높이에도 곱한다
  assert.deepEqual(B.features([], routes).solids.features, []);
});

test('위치 섞기: 0이면 직전, 1이면 새 위치, 새로 나타난 차는 그대로, 방향은 짧은 쪽으로 돈다', () => {
  const prev = [{ v: 'a', lon: 126.0, lat: 37.0, hd: 350 }], next = [{ v: 'a', lon: 126.2, lat: 37.2, hd: 10 }, { v: 'n', lon: 1, lat: 2 }];
  assert.deepEqual(B.interpolate(prev, next, 0)[0], { v: 'a', lon: 126.0, lat: 37.0, hd: 350 });
  assert.deepEqual(B.interpolate(prev, next, 1)[0], { v: 'a', lon: 126.2, lat: 37.2, hd: 10 });
  const mid = B.interpolate(prev, next, 0.5)[0];
  close(mid.lon, 126.1); close(mid.lat, 37.1); close(mid.hd, 0, 1e-9);                 // 350° → 10° 는 0°를 지난다
  assert.deepEqual(B.interpolate(prev, next, 0.5)[1], next[1]);
  assert.deepEqual(B.interpolate(null, next, 0.5), next);
});

test('방향 붙이기: 경로가 우선, 없으면 5 m 넘게 움직인 쪽, 안 움직였으면 직전 방향을 이어 쓴다', () => {
  const routes = [{ id: 'R', path: [[126.75, 37.55], [126.76, 37.55]] }];
  const [a] = B.withHeading([{ v: 'a', r: 'R', lon: 126.751, lat: 37.55, ord: 1 }], routes, []);
  close(a.hd, 90, 0.05);
  const moved = B.withHeading([{ v: 'b', r: 'NO', lon: 126.7501, lat: 37.55, ord: 1 }], routes, [{ v: 'b', lon: 126.75, lat: 37.55 }])[0];
  close(moved.hd, 90, 0.5);
  const still = B.withHeading([{ v: 'c', r: 'NO', lon: 126.75, lat: 37.55, ord: 1 }], routes, [{ v: 'c', lon: 126.75, lat: 37.55, hd: 123 }])[0];
  assert.equal(still.hd, 123);
  assert.equal('hd' in B.withHeading([{ v: 'd', r: 'NO', lon: 1, lat: 1, ord: 1 }], routes, [])[0], false);
});

test('지나는 단지: 경로가 단지 중심에서 500 m 안이면 가까운 순으로, 경로가 없으면 빈 목록', () => {
  const route = { path: [[126.75, 37.55], [126.76, 37.55]] };            // 동서로 약 880 m
  const near = { id: 'A2', c: [126.755, 37.5518] }, far = { id: 'A9', c: [126.755, 37.58] }, mid = { id: 'A3', c: [126.755, 37.5504] };
  assert.deepEqual(B.passes(route, [far, mid, near], cen).map((x) => x.id), ['A3', 'A2']);   // A3 가 약 44 m, A2 가 약 200 m
  assert.deepEqual(B.passes({}, [near], cen), []);
  assert.deepEqual(B.passes({ path: [[1, 1]] }, [near], cen), []);
  assert.equal(B.nearestBlock([126.755, 37.5518], [far, near, mid], cen).id, 'A2');
});

test('응답 해석: 모양이 다르면 null, 이상한 버스는 거르고, ttl 은 60초 아래로 내려가지 않는다', () => {
  assert.equal(B.parse(null), null);
  assert.equal(B.parse({ buses: 'x' }), null);
  const p = B.parse({ at: '2026-10-05T00:00:00Z', ttl: 10, buses: [{ r: 'R', v: 'a', lon: 126.7, lat: 37.5 }, { r: 'R', v: 'b', lon: 'x', lat: 37.5 }, null], failed: ['R2'] });
  assert.equal(p.buses.length, 1);
  assert.equal(p.ttl, 60);
  assert.deepEqual(p.failed, ['R2']);
  assert.equal(B.parse({ buses: [], ttl: 120 }).ttl, 120);
});

test('호출 간격: 서버 ttl 이상, 실패하면 2배씩 늘어나 10분에서 멈춘다', () => {
  assert.equal(B.pollDelayMs(60, 0), 60000);
  assert.equal(B.pollDelayMs(10, 0), 60000);
  assert.equal(B.pollDelayMs(undefined, 0), 60000);
  assert.equal(B.pollDelayMs(60, 1), 120000);
  assert.equal(B.pollDelayMs(60, 2), 240000);
  assert.equal(B.pollDelayMs(60, 9), 600000);
  assert.equal(B.pollDelayMs(900, 3), 900000);                             // ttl 자체가 10분을 넘으면 그 값 아래로 줄이지 않는다
});

test('몇 분 전: 방금 · N분 전 · 1시간 넘게 지남', () => {
  const now = Date.parse('2026-10-05T01:00:00Z');
  assert.equal(B.ageText('2026-10-05T00:59:40Z', now), '방금');
  assert.equal(B.ageText('2026-10-05T00:57:00Z', now), '3분 전');
  assert.equal(B.ageText('2026-10-04T22:00:00Z', now), '1시간 넘게 지남');
  assert.equal(B.ageText('이상한값', now), '');
  assert.equal(B.fmtDist(450), '약 450 m');
  assert.equal(B.fmtDist(1530), '약 1.5 km');
});

test('팝업 내용: 노선·차량·현재 위치·가까운 단지·지나는 단지', () => {
  const route = { id: 'R87', no: '87', type: '간선버스', from: '기점', to: '종점', path: [[126.75, 37.55], [126.76, 37.55]] };
  const blocks = [{ id: 'A2', c: [126.755, 37.5518] }, { id: 'A9', c: [126.755, 37.58] }];
  const d = B.describe({ v: '인천73아1091', r: 'R87', lon: 126.755, lat: 37.55, ord: 7, stop: '독정역' }, route, blocks, cen, '2026-10-05T00:59:30Z', Date.parse('2026-10-05T01:00:00Z'));
  assert.equal(d.title, '87번 간선버스');
  assert.equal(d.plate, '인천73아1091');
  assert.equal(d.where, '독정역 · 7번째 정류소 부근');
  assert.equal(d.near.id, 'A2');
  assert.match(d.near.text, /^A2 단지에서 약 \d+ m$/);
  assert.deepEqual(d.passes, ['A2']);
  assert.equal(d.age, '방금');
  assert.equal(d.color, '#56B4E9');
  const bare = B.describe({ v: 'x', r: 'RX', lon: 1, lat: 1 }, undefined, [], cen);
  assert.equal(bare.title, '버스');
  assert.equal(bare.near, null);
  assert.equal(bare.where, '');
});

test('실제 번들: 실시간 노선마다 경로·방향을 구할 수 있고, 계양 단지 중 하나는 지난다', () => {
  const dir = path.join(__dirname, '../../regions/incheon-gyeyang');
  const infra = JSON.parse(fs.readFileSync(path.join(dir, 'infra.json'), 'utf8'));
  const projects = JSON.parse(fs.readFileSync(path.join(dir, 'projects.json'), 'utf8')).projects;
  const centroid = (p) => { const r = p.outline.poly; return [r.reduce((a, q) => a + q[0], 0) / r.length, r.reduce((a, q) => a + q[1], 0) / r.length]; };
  const live = infra.busRoutes.filter((r) => r.live);
  assert.ok(live.length >= 1);
  for (const r of live) {
    assert.ok(r.path.length >= 10, r.no);
    assert.ok(B.headingOf(r.path, 5) !== null, r.no);
    assert.ok(B.passes(r, projects, centroid).length >= 1, `${r.no}번이 지나는 단지`);
  }
  const stopRoutes = new Set(infra.stops.flatMap((s) => s.routes || []));
  for (const r of live) assert.ok(stopRoutes.has(r.id), `${r.no}번을 지나는 정류소`);
});

/* ---- 화면 연결(app.js·index.html): 지도 없이 소스 글자로 약속을 지키는지 본다 ---- */
const app = fs.readFileSync(path.join(__dirname, '../../assets/js/app.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, '../../index.html'), 'utf8');

test('bus.js 는 화면 스크립트보다 먼저 불러오고, 버스 옵션 체크박스가 점검 묶음 안에 있다', () => {
  assert.ok(html.indexOf("assets/js/bus.js") > 0 && html.indexOf("assets/js/bus.js") < html.indexOf("assets/js/app.js"));
  assert.match(html, /<fieldset id="fsInfra"[\s\S]*id="busChip"[\s\S]*<\/fieldset>/);
  assert.match(html, /id="lblBus" hidden/);                                          // 실시간 노선이 있는 지역에서만 켜진다
});

test('요청 시에만 조회: 버튼을 누를 때 한 번 부르고, 자동 반복·탭 감시·반복 타이머가 없으며, 서버 ttl 동안 다시 못 누르고, 중계가 없으면(404·405·503) 더 부르지 않는다', () => {
  assert.match(app, /async function busLoad\(\)/);
  assert.match(app, /fetch\(`api\/bus\?region=\$\{encodeURIComponent\(REG\.slug\)\}`\)/);
  assert.match(app, /\$\('#busLoad'\)\.addEventListener\('click', busLoad\)/);
  assert.match(html, /id="busLoad" class="opt" hidden/);
  assert.match(app, /BUS\.cooldownUntil = Date\.now\(\) \+ data\.ttl \* 1000/);
  assert.match(app, /btn\.disabled = BUS\.loading \|\| wait > 0/);
  assert.match(app, /\[404, 405, 503\]\.includes\(res\.status\)/);
  assert.doesNotMatch(app, /setInterval\([^)]*bus/i);                                // 고정 간격 반복 호출 없음
  assert.doesNotMatch(app, /BL\.pollDelayMs|busSchedule|busFetch|visibilitychange/);  // 예약 호출·탭 감시 없음
  assert.doesNotMatch(app, /busLoad\(\);?\s*\n\s*(applyBus|setBusData)/);            // 로드 시 자동 호출 없음
});

test('3D 층: 높이·바닥은 피처 값(차체·창띠), 색은 노선 유형, 라벨은 노선 번호이며 URL ?bus=0 으로 끈다', () => {
  assert.match(app, /id: 'bus-3d', type: 'fill-extrusion'[^\n]*'fill-extrusion-base': \['get', 'base'\][^\n]*'fill-extrusion-height': \['get', 'h'\]/);
  assert.match(app, /id: 'bus-label'[^\n]*'text-field': \['get', 'text'\]/);
  assert.match(app, /let busOn = q\.get\('bus'\) !== '0'/);
  assert.match(app, /set\('bus', HAS_BUS && !busOn \? '0' : ''\)/);
  assert.match(app, /const HAS_BUS = LIVE_ROUTES\.length > 0 && !!REG\.slug/);
});

test('클릭: 버스를 먼저 고르고(작아서 7px 여유), 정류소 팝업은 정류소 id 로 경유 노선을 찾는다', () => {
  assert.match(app, /const pickBus = \(\) =>[^\n]*r = 7/);
  assert.match(app, /const f = pickBus\(\) \|\|/);
  assert.match(app, /\(INFRA\.stops \|\| \[\]\)\.forEach\(\(s\) => stops\.push\(pt\(\{ name: s\.name, id: s\.id \|\| '' \}/);
  assert.match(app, /\(INFRA\.stops \|\| \[\]\)\.find\(\(s\) => s\.id === p\.id\)/);
});

test('함수가 없는 정적 서버(404)에서는 조용히 사라지지 않고, 이유와 해결 방법을 화면·콘솔에 남긴다', () => {
  assert.match(app, /BUS\.off = true; BUS\.loading = false; applyBus\(\); setLegend\(\);/);
  assert.match(app, /console\.warn\([^\n]*\.\/run-app\.sh/);
  assert.match(app, /BUS\.off \? '버스 선만' : '버스'/);                              // 하단 범례 요약 줄에 보인다
  assert.match(app, /lb\.textContent = BUS\.off \? '위치 서버 없음'/);                // 옵션 항목에도 보인다
  assert.match(app, /\$\{IS_LOCAL \? ' — 로컬은 node scripts\/dev\.js 로 여세요' : ''\}/);   // 운영 화면에는 개발 명령을 적지 않는다
  assert.match(html, /node scripts\/dev\.js/);
});

test('크기는 확대 단계에 맞추고(BusLib.scaleFor), 확대가 바뀌면 마지막 위치를 다시 그린다', () => {
  assert.match(app, /BL\.features\(list, LIVE_ROUTES, BL\.scaleFor\(map\.getZoom\(\)\)\)/);
  assert.match(app, /map\.on\('zoom', busRescale\)/);
  assert.match(app, /BUS\.shown = list/);
});

test('버스를 찾기 쉽게: 옵션의 \'가장 가까운 버스 보기\' 버튼과 주소 ?at= 시작 위치(값이 이상하면 무시)', () => {
  assert.match(html, /id="busGo" hidden/);
  assert.match(app, /\$\('#busGo'\)\.addEventListener\('click', busGo\)/);
  assert.match(app, /map\.flyTo\(\{ center: \[near\.lon, near\.lat\], zoom: 17\.4/);
  assert.match(app, /go\.hidden = !\(can && has\)/);
  assert.match(app, /\.\.\.atParam\(\) \};/);
  assert.match(app, /lon < 120 \|\| lon > 135 \|\| lat < 30 \|\| lat > 45 \|\| zoom < 0 \|\| zoom > 22\) return \{\};/);
});

test('run-app.sh: 실행 권한이 있고, Next.js 개발 서버(npm run dev, 127.0.0.1)를 열며, 포트 충돌·키 없음을 알려 준다', () => {
  const file = path.join(__dirname, '../../run-app.sh'), sh = fs.readFileSync(file, 'utf8');
  assert.ok(fs.statSync(file).mode & 0o100, '실행 권한(chmod +x)');
  assert.match(sh, /^#!\/usr\/bin\/env bash/);
  assert.match(sh, /exec npm run dev -- -p "\$PORT" -H 127\.0\.0\.1/);
  assert.match(sh, /lsof -nP -iTCP:"\$PORT" -sTCP:LISTEN/);
  assert.match(sh, /DATA_GO_KR_KEY/);
  assert.match(sh, /NO_OPEN/);
  const code = sh.split('\n').filter((l) => !l.trim().startsWith('#')).join('\n');   // 주석 설명 제외
  assert.doesNotMatch(code, /http\.server/);    // 정적 서버로 여는 줄은 없다
  assert.doesNotMatch(code, /scripts\/dev\.js/); // 옛 개발 서버는 더 이상 켜지 않는다
});

test('run-app.sh: 코드가 없으면 종합상황판(/), 있으면 그 코드의 지도(/map?…, 인자·START_CODE·region:<slug>)를 열고, 자릿수로 종류를 정하며, 키가 없으면 계양 번들로 연다', () => {
  const { spawnSync } = require('node:child_process'), os = require('node:os');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'runapp-'));
  fs.copyFileSync(path.join(__dirname, '../../run-app.sh'), path.join(dir, 'run-app.sh')); fs.chmodSync(path.join(dir, 'run-app.sh'), 0o755);
  const run = (args, env = {}) => spawnSync('bash', [path.join(dir, 'run-app.sh'), ...args], { env: { PATH: process.env.PATH, DRY_RUN: '1', ...env }, encoding: 'utf8', cwd: dir });
  const last = (r) => r.stdout.trim().split('\n').pop();
  fs.writeFileSync(path.join(dir, '.env.local'), 'DATA_GO_KR_KEY=dummy\n');
  assert.equal(last(run([])), 'http://127.0.0.1:8000/');                                                        // 코드가 없으면 종합상황판
  assert.equal(last(run(['8123'])), 'http://127.0.0.1:8123/');
  assert.equal(last(run(['8123', '28245'])), 'http://127.0.0.1:8123/map?sgg=28245');
  assert.equal(last(run(['8123', '4145011100'])), 'http://127.0.0.1:8123/map?bjd=4145011100');
  assert.equal(last(run(['8123', '41450111'])), 'http://127.0.0.1:8123/map?bjd=41450111');
  assert.equal(last(run(['8123', '1129013800100740307'])), 'http://127.0.0.1:8123/map?pnu=1129013800100740307');
  assert.equal(last(run(['8123', 'region:jeonnam-naju'])), 'http://127.0.0.1:8123/map?region=jeonnam-naju');
  assert.equal(last(run(['8123'], { START_CODE: '12330' })), 'http://127.0.0.1:8123/map?sgg=12330');
  assert.equal(last(run(['8123', '28245'], { START_CODE: '12330' })), 'http://127.0.0.1:8123/map?sgg=28245');     // 인자가 환경변수보다 우선
  for (const bad of ['12345678901', 'abc', '123']) { const r = run(['8123', bad]); assert.equal(r.status, 2, bad); assert.match(r.stderr, /코드/); }
  assert.equal(run(['abc']).status, 2);                                                                            // 포트 검사는 그대로
  // 코드 해석 키가 없으면 코드를 해석할 수 없으므로 계양 번들로 연다(번들 주소는 키가 없어도 그대로)
  fs.writeFileSync(path.join(dir, '.env.local'), 'VWORLD_KEY=x\n');
  const nokey = run(['8123', '41450']); assert.equal(last(nokey), 'http://127.0.0.1:8123/map?region=incheon-gyeyang'); assert.match(nokey.stderr, /해석할 수 없습니다/);
  assert.equal(last(run(['8123', 'region:jeonnam-naju'])), 'http://127.0.0.1:8123/map?region=jeonnam-naju');
  const home = run(['8123']); assert.equal(last(home), 'http://127.0.0.1:8123/'); assert.equal(home.stderr, '');   // 코드가 없으면 키가 없어도 경고 없이 종합상황판
  fs.writeFileSync(path.join(dir, '.env.local'), 'DATA_GO_KR_KEY_RESOLVE_1=k\n');
  assert.equal(last(run(['8123', '41450'])), 'http://127.0.0.1:8123/map?sgg=41450');                                // 용도별 키만 있어도 열린다
  fs.rmSync(dir, { recursive: true, force: true });
});
