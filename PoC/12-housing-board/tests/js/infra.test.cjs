'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const I = require('../../assets/js/infra.js');

/* 계양 테크노밸리 근처 좌표로 만든 작은 자료. 블록 A2·A6 는 입주 시기만 다르다. */
const sq = (lon, lat, d = 0.0004) => [[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d]];
const block = (pid, moveIn, lon = 126.757, lat = 37.5545) => ({ id: pid.replace('techno-', ''), pid, moveIn, poly: sq(lon, lat) });
const A2 = block('techno-A2', '2026.12');
const INFRA = {
  schema_version: '1.2.0', asOf: '2026-10-04',
  sources: [{ id: 'tago-bus', label: '국토교통부 TAGO 버스정류소·노선정보', asOf: '2026-10-05', redistributable: 'Y' }],
  schools: [
    { id: 'new-1', name: '(가칭)계양1초', level: '초등학교', status: '신설예정', openYm: '2029-03', classes: 44, students: 1113, lon: 126.7573, lat: 37.5552, sources: ['x'] },
    { id: 'new-far', name: '(가칭)먼초', level: '초등학교', status: '신설예정', openYm: '2027-03', lon: 126.80, lat: 37.60, sources: ['x'] },
    { id: 'site-1', name: '중학교 부지', level: '중학교', status: '부지만', lon: 126.7555, lat: 37.5476, sources: ['x'] },
    { id: 'site-2', name: '유치원 부지', level: '유치원', status: '부지만', lon: 126.7563, lat: 37.5549, sources: ['x'] },
  ],
  zones: [{ id: 'z-d', name: '인천당산초통학구역', school: '인천당산초등학교', schoolLon: 126.7593, schoolLat: 37.5586, poly: sq(126.76, 37.556, 0.01), asOf: '2026-09-20', sources: ['x'] }],
  attendance: [{ projectId: 'techno-A2', zoneId: 'z-d' }],
  stops: [{ name: '당산초아래', lon: 126.7572, lat: 37.5546 }, { name: '먼 정류장', lon: 126.80, lat: 37.60 }],
  sites: [{ id: 'e1', category: '전기', name: '전기공급설비', poly: sq(126.7607, 37.5419, 0.0003), sources: ['x'] }, { id: 'r1', category: '교통', name: '차고지', poly: sq(126.7659, 37.5668), sources: ['x'] }],
};
const CTX = { stations: [{ name: '박촌역', lon: 126.74489, lat: 37.55366 }, { name: '귤현역', lon: 126.74266, lat: 37.56635 }] };

test('moveInYm: 입주 월, 준공 예정일, 날짜 없음', () => {
  assert.equal(I.moveInYm('2026.12'), '2026-12');
  assert.equal(I.moveInYm('2029.06'), '2029-06');
  assert.equal(I.moveInYm('준공 예정 2028-09-30'), '2028-09');
  assert.equal(I.moveInYm('입주 시기 미정'), null);
  assert.equal(I.moveInYm('입주 일자 미상'), null);
  assert.equal(I.moveInYm('2026.13'), null);
  assert.equal(I.moveInYm(null), null);
  assert.equal(I.moveInYm(undefined), null);
});

test('monthsBetween / fmtYm / fmtDate', () => {
  assert.equal(I.monthsBetween('2026-12', '2029-03'), 27);
  assert.equal(I.monthsBetween('2029-03', '2026-12'), -27);
  assert.equal(I.monthsBetween('2026-12', '2026-12'), 0);
  assert.equal(I.monthsBetween(null, '2026-12'), null);
  assert.equal(I.fmtYm('2029-03'), '2029.03');
  assert.equal(I.fmtYm('2029'), '');
  assert.equal(I.fmtYm(undefined), '');
  assert.equal(I.fmtDate('2025-10-31'), '2025.10.31');
});

test('fmtDist: app.js distTxt 와 같은 문구', () => {
  assert.equal(I.fmtDist(118), '약 120 m');
  assert.equal(I.fmtDist(994), '약 990 m');
  assert.equal(I.fmtDist(1000), '약 1.0 km');
  assert.equal(I.fmtDist(1234), '약 1.2 km');
});

test('distM·centroid: 위도 0.001도는 약 111 m', () => {
  const d = I.distM([126.75, 37.55], [126.75, 37.551]);
  assert.ok(d > 110 && d < 112, String(d));
  assert.deepEqual(I.centroid([[0, 0], [2, 0], [2, 2], [0, 2]]), [1, 1]);
});

test('compareOpen: 늦음 / 같은 시기 / 앞섬 / 시기 미정 / 준공 예정 단지', () => {
  const late = I.compareOpen('2029-03', A2);
  assert.deepEqual([late.n, late.level, late.text], [27, 'warn', '입주(2026.12)보다 27개월 늦음']);
  assert.deepEqual(I.compareOpen('2026-12', A2).text, '입주와 같은 시기');
  const early = I.compareOpen('2026-03', A2);
  assert.deepEqual([early.n, early.level, early.text], [-9, 'info', '입주(2026.12)보다 9개월 앞섬']);
  assert.equal(I.compareOpen('2029-03', block('p', '입주 시기 미정')).text, '입주 시기 미정');
  const rental = I.compareOpen('2029-03', block('p', '준공 예정 2028-09-30'));
  assert.equal(rental.text, '준공(2028.09)보다 6개월 늦음'); assert.equal(rental.level, 'warn');
  assert.equal(I.compareOpen('2028-09', block('p', '준공 예정 2028-09-30')).text, '준공과 같은 시기');
  assert.equal(I.compareOpen('2027-03', A2).level, 'info');   // 3개월 늦음은 주의가 아님
  assert.equal(I.compareOpen('2027-06', A2).level, 'warn');   // 6개월부터 주의
});

test('projectChecks 교육: 통학구역·신설예정 학교(주의)·일정 미공시 부지', () => {
  const r = I.projectChecks(A2, INFRA, CTX);
  const [zone, news, sites] = r.edu;
  assert.equal(zone.level, 'info'); assert.equal(zone.label, '통학구역');
  assert.match(zone.text, /^인천당산초등학교 통학구역 · 직선 약 \d+ m$/);
  assert.equal(zone.detail, '2026.09.20 기준 초등 통학구역. 신설 학교가 문을 열면 조정될 수 있음');
  assert.equal(news.level, 'warn');
  assert.match(news.text, /^\(가칭\)계양1초 2029\.03 개교 예정 · 약 \d+ m \(44학급·1,113명 계획\)$/);
  assert.equal(news.detail, '입주(2026.12)보다 27개월 늦음');
  assert.equal(sites.level, 'info'); assert.equal(sites.text, '개교 일정이 공시되지 않은 학교 부지 1곳 (600 m 안)');   // 유치원 부지만 600 m 안, 중학교 부지는 밖
});

test('projectChecks 교육: 입주 시기를 모르면 주의 대신 참고, 통학구역 자료가 없으면 줄이 없다', () => {
  const r = I.projectChecks(block('techno-A9', '입주 시기 미정'), INFRA, CTX);
  assert.equal(r.edu.some((x) => x.label === '통학구역'), false);
  const n = r.edu.find((x) => x.label === '신설 학교');
  assert.equal(n.level, 'info'); assert.equal(n.detail, '입주 시기 미정');
});

test('projectChecks 교육: 특수학교가 조금 더 가까워도 일반 학교를 먼저 보여 준다(일반 학교가 1.2 km 밖이면 특수학교)', () => {
  const special = { id: 'sp', name: '(가칭)계양학교', level: '특수학교', status: '신설예정', openYm: '2029-03', lon: 126.7571, lat: 37.5547, sources: ['x'] };
  const withSpecial = Object.assign({}, INFRA, { schools: [special, ...INFRA.schools] });
  const n = I.projectChecks(A2, withSpecial, CTX).edu.find((x) => x.label === '신설 학교');
  assert.match(n.text, /^\(가칭\)계양1초 /);
  const onlySpecial = Object.assign({}, INFRA, { schools: [special] });
  assert.match(I.projectChecks(A2, onlySpecial, CTX).edu.find((x) => x.label === '신설 학교').text, /^\(가칭\)계양학교 /);
  const farRegular = Object.assign({}, INFRA, { schools: [special, INFRA.schools[1]] });   // new-far 는 1.2 km 밖
  assert.match(I.projectChecks(A2, farRegular, CTX).edu.find((x) => x.label === '신설 학교').text, /^\(가칭\)계양학교 /);
});

test('projectChecks 교육: 1.2 km 안에 신설예정이 없으면 자료 없음 줄', () => {
  const far = block('techno-X', '2027.01', 126.70, 37.50);
  const n = I.projectChecks(far, INFRA, CTX).edu.find((x) => x.label === '신설 학교');
  assert.deepEqual([n.level, n.text], ['none', '1.2 km 안에 개교 예정 학교 공시 없음']);
});

test('projectChecks 교육: 일정 미공시 부지가 없으면 그 줄을 만들지 않는다', () => {
  const noSites = Object.assign({}, INFRA, { schools: INFRA.schools.filter((s) => s.status !== '부지만') });
  assert.equal(I.projectChecks(A2, noSites, CTX).edu.some((x) => x.label === '학교 부지'), false);
});

test('projectChecks 교통: 300 m 안 정류장, 가까운 역, 기준일', () => {
  const r = I.projectChecks(A2, INFRA, CTX);
  const [bus, st] = r.transit;
  assert.equal(bus.level, 'info'); assert.match(bus.text, /^정류장 1곳 · 가장 가까운 당산초아래 약 \d+ m$/);
  assert.equal(bus.detail, '국토교통부 TAGO 버스정류소 정보 2026.10.05 기준 — 입주 때 새로 생기는 정류장은 아직 반영되지 않았을 수 있음');
  assert.equal(st.label, '가까운 역'); assert.match(st.text, /^박촌역 약 [\d.]+ (m|km)$/);
});

test('projectChecks 교통: 300 m 안에 정류장이 없으면 주의, 정류장 자료 자체가 없으면 말하지 않는다', () => {
  const lonely = block('techno-Y', '2026.12', 126.70, 37.50);
  const bus = I.projectChecks(lonely, INFRA, null).transit;
  assert.deepEqual([bus[0].level, bus[0].text], ['warn', '300 m 안 정류장 없음']);
  assert.equal(bus.length, 1);                                            // context 가 없으면 역 줄도 없다
  const none = I.projectChecks(lonely, Object.assign({}, INFRA, { stops: [] }), CTX).transit;
  assert.equal(none.some((x) => x.label === '버스정류장'), false);
  assert.equal(none.some((x) => x.label === '가까운 역'), true);
});

test('projectChecks 교통: 정류장이 없어도 입주가 1년 넘게 남았으면 주의가 아니라 참고(아직 안 생긴 것이 당연)', () => {
  const far = (moveIn) => I.projectChecks(block('techno-Y', moveIn, 126.70, 37.50), INFRA, null).transit[0];
  assert.equal(far('2026.12').level, 'warn');            // 기준일(2026-10)에서 2개월
  assert.equal(far('2027.10').level, 'warn');            // 정확히 12개월
  assert.equal(far('2027.11').level, 'info');            // 13개월
  assert.equal(far('2029.06').level, 'info');
  assert.equal(far('2029.06').text, '300 m 안 정류장 없음');
  assert.equal(far('입주 시기 미정').level, 'info');     // 시기를 모르면 주의로 올리지 않는다
  assert.equal(far('준공 예정 2026-12-30').level, 'warn');
});

test('projectChecks 전기: 가장 가까운 전기공급설비 부지(다른 종류 시설은 세지 않음), 없으면 자료 없음', () => {
  const p = I.projectChecks(A2, INFRA, CTX).power;
  assert.equal(p.length, 1); assert.equal(p[0].level, 'info');
  assert.match(p[0].text, /^전기공급설비 부지 약 [\d.]+ (m|km) \(지구 안 1곳\)$/);
  assert.equal(p[0].detail, '수전 가능 여부는 한전 협의 사항이라 공개 자료가 없음');
  const none = I.projectChecks(A2, Object.assign({}, INFRA, { sites: [] }), CTX).power;
  assert.deepEqual([none[0].level, none[0].text], ['none', '전기공급설비 부지 자료 없음']);
});

test('projectChecks: 공통 설명(통학구역·정류장·전기)만 generic, 단지마다 다른 비교 문구는 아니다', () => {
  const r = I.projectChecks(A2, INFRA, CTX);
  const gen = [...r.edu, ...r.transit, ...r.power].filter((x) => x.generic).map((x) => x.label).sort();
  assert.deepEqual(gen, ['버스정류장', '전기 시설', '통학구역']);
  assert.equal(r.edu.find((x) => x.label === '신설 학교').generic, undefined);
});

test('projectChecks: 단지·자료가 없거나 위치가 없으면 빈 결과, 건립 현황 표기를 쓰지 않는다', () => {
  assert.deepEqual(I.projectChecks(null, INFRA, CTX), { edu: [], transit: [], power: [] });
  assert.deepEqual(I.projectChecks({ pid: 'x', poly: [] }, INFRA, CTX), { edu: [], transit: [], power: [] });
  assert.deepEqual(I.projectChecks(A2, null, CTX), { edu: [], transit: [], power: [] });
  const all = JSON.stringify(I.projectChecks(A2, INFRA, CTX));
  assert.ok(!/집행|미집행/.test(all));
});

test('sortSchools: 신설예정(개교 이른 순) 다음에 부지만, 원본은 바뀌지 않는다', () => {
  const before = JSON.stringify(INFRA.schools);
  const out = I.sortSchools(INFRA.schools).map((s) => s.id);
  assert.deepEqual(out, ['new-far', 'new-1', 'site-2', 'site-1']);   // 부지만은 이름(가나다) 순
  assert.equal(JSON.stringify(INFRA.schools), before);
  assert.deepEqual(I.sortSchools(undefined), []);
});

test('permitStatus: 사용승인 > 공사 중 > 허가', () => {
  assert.equal(I.permitStatus({ permitDate: '2025-01-01', startDate: '2025-02-01', approvalDate: '2026-01-01' }), '사용승인');
  assert.equal(I.permitStatus({ permitDate: '2025-01-01', startDate: '2025-02-01', approvalDate: null }), '공사 중');
  assert.equal(I.permitStatus({ permitDate: '2025-01-01', startDate: null }), '허가');
});

test('nearestBlock·scaleText', () => {
  const b = I.nearestBlock([A2, block('techno-A6', '2029.06', 126.77, 37.56)], [126.7573, 37.5552]);
  assert.equal(b.block.pid, 'techno-A2'); assert.ok(b.d < 150);
  assert.equal(I.nearestBlock([], [0, 0]), null);
  assert.equal(I.scaleText({ classes: 44, students: 1113 }), '44학급·1,113명');
  assert.equal(I.scaleText({ classes: 44 }), '44학급');
  assert.equal(I.scaleText({}), '');
});

/* ---------- 시각화용 순수 함수: 이름 줄이기, 격차 문구, 종류별 신호, 요약, 연결선, 타임라인 ---------- */
test('shortName: (가칭) 접두와 공백을 뗀다', () => {
  assert.equal(I.shortName('(가칭)계양1초'), '계양1초');
  assert.equal(I.shortName('  (가칭) 계양학교 '), '계양학교');
  assert.equal(I.shortName('인천당산초등학교'), '인천당산초등학교');
  assert.equal(I.shortName(undefined), '');
});

test('gapText: 개교가 입주보다 늦음·같음·앞섬·미정을 짧게', () => {
  assert.equal(I.gapText({ n: 27 }, '입주'), '입주 후 27개월 뒤 개교');
  assert.equal(I.gapText({ n: 0 }, '입주'), '입주와 같은 시기 개교');
  assert.equal(I.gapText({ n: 0 }, '준공'), '준공과 같은 시기 개교');
  assert.equal(I.gapText({ n: -9 }, '입주'), '입주 9개월 전 개교');
  assert.equal(I.gapText({ n: null }, '입주'), '입주 시기 미정');
});

test('categoryLevels: 종류마다 줄 가운데 가장 높은 단계(주의 > 참고 > 자료 없음), 줄이 없으면 null', () => {
  const c = I.categoryLevels({ edu: [{ level: 'info' }, { level: 'warn' }], transit: [{ level: 'none' }], power: [] });
  assert.deepEqual(c, { edu: 'warn', transit: 'none', power: null });
  assert.deepEqual(I.categoryLevels({ edu: [{ level: 'info' }, { level: 'none' }], transit: [{ level: 'info' }], power: [{ level: 'none' }] }),
    { edu: 'info', transit: 'info', power: 'none' });
  assert.deepEqual(I.categoryLevels(null), { edu: null, transit: null, power: null });
});

const A6 = block('techno-A6', '2029.06', 126.7565, 37.5477);
test('summarize: 단지×종류 칸을 세어 한 줄 요약을 만든다', () => {
  const s = I.summarize([A2, A6], INFRA, CTX);
  assert.equal(s.blocks.length, 2);
  assert.deepEqual(s.blocks[0].levels, { edu: 'warn', transit: 'info', power: 'info' });   // A2: 27개월 늦은 학교
  assert.equal(s.blocks[0].warn, 1);
  assert.equal(s.warn, s.blocks.reduce((a, b) => a + b.warn, 0));
  assert.deepEqual(s.byCat.edu, { warn: 1, info: s.byCat.edu.info, none: s.byCat.edu.none });
  assert.match(s.headline, /^주의 \d+건 \(교육 1/);
});

test('summarize: 주의가 없으면 그렇게 말하고, 자료가 없으면 빈 요약', () => {
  const calm = I.summarize([A6], Object.assign({}, INFRA, { schools: [] , zones: [], attendance: []}), CTX);
  assert.equal(calm.warn, 0); assert.equal(calm.headline, '주의할 항목 없음');
  const none = I.summarize([A2], null, CTX);
  assert.deepEqual([none.warn, none.blocks.length, none.headline], [0, 0, '']);
});

test('connectors: 단지마다 가까운 신설 학교로 가는 선(격차 라벨)과 배정 통학구역 학교로 가는 선', () => {
  const cs = I.connectors([A2, A6], INFRA, CTX);
  const a2new = cs.find((c) => c.pid === 'techno-A2' && c.kind === 'new');
  assert.equal(a2new.schoolId, 'new-1'); assert.equal(a2new.level, 'warn');
  assert.deepEqual(a2new.to, [126.7573, 37.5552]); assert.deepEqual(a2new.from, I.centroid(A2.poly));
  assert.match(a2new.label, /^계양1초 약 \d+ m\n입주 후 27개월 뒤 개교$/);
  const a2zone = cs.find((c) => c.pid === 'techno-A2' && c.kind === 'zone');
  assert.deepEqual(a2zone.to, [126.7593, 37.5586]); assert.equal(a2zone.level, 'info');
  assert.match(a2zone.label, /^인천당산초등학교\n통학구역 약 \d+ m$/);
  assert.equal(cs.some((c) => c.pid === 'techno-A6' && c.kind === 'zone'), false);       // 통학구역 배정이 없는 단지
});

test('connectors: 가까운 신설 학교가 없는 단지·자료 없음은 선이 없다', () => {
  const lonely = block('techno-Y', '2026.12', 126.70, 37.50);
  assert.deepEqual(I.connectors([lonely], INFRA, null), []);
  assert.deepEqual(I.connectors([A2], null, CTX), []);
});

const MEASURES = [
  { id: 'm1', category: '교통', title: '7701번 시내버스 신설', short: '7701번', when: '2026-10', status: '예정', sources: ['x'] },
  { id: 'm2', category: '교통', title: '서울 강남권 M버스 신규 노선 신청', short: 'M버스', when: '2026-11', status: '검토', sources: ['x'] },
  { id: 'm3', category: '교육', title: '계양1·2유치원(공립단설) 신설', short: '계양1·2유치원', when: '2029-09', status: '예정', sources: ['x'] },
  { id: 'm4', category: '교통', title: '셔틀버스 협의', status: '검토', sources: ['x'] },
  { id: 'm5', category: '교통', title: '장기 과제', when: '2030', status: '미정', sources: ['x'] },
];
const TL_INFRA = Object.assign({}, INFRA, { measures: MEASURES, schools: [
  { id: 'a', name: '(가칭)계양1초', level: '초등학교', status: '신설예정', openYm: '2029-03', lon: 126.7573, lat: 37.5552, sources: ['x'] },
  { id: 'b', name: '(가칭)계양학교', level: '특수학교', status: '신설예정', openYm: '2029-03', lon: 126.7515, lat: 37.5548, sources: ['x'] },
  { id: 'c', name: '(가칭)계양3초', level: '초등학교', status: '신설예정', openYm: '2029-09', lon: 126.7564, lat: 37.5476, sources: ['x'] },
  { id: 'd', name: '중학교 부지', level: '중학교', status: '부지만', lon: 126.7555, lat: 37.5476, sources: ['x'] },
] });

test('timeline: 입주·교육·교통 줄, 같은 달은 한 점에 이름을 쌓고, 달이 없는 대책은 뺀다', () => {
  const t = I.timeline([A2, A6, block('techno-A10', '준공 예정 2028-09-30')], TL_INFRA);
  assert.deepEqual(t.lanes.map((l) => l.key), ['move', 'edu', 'transit']);
  assert.deepEqual(t.lanes[0].items.map((i) => [i.ym, i.names]), [['2026-12', ['A2']], ['2028-09', ['A10']], ['2029-06', ['A6']]]);
  assert.deepEqual(t.lanes[1].items.map((i) => [i.ym, i.names]), [['2029-03', ['계양1초', '계양학교']], ['2029-09', ['계양3초', '계양1·2유치원']]]);
  assert.deepEqual(t.lanes[2].items.map((i) => [i.ym, i.names, i.hollow]), [['2026-10', ['7701번'], false], ['2026-11', ['M버스'], true]]);   // 검토는 속이 빈 점
  assert.equal(t.from, '2026-10');          // 자료 기준일의 달부터
  assert.ok(t.to >= '2029-09');
});

test('timeline: 학교 없는 기간(첫 입주 → 가장 이른 일반 학교 개교)', () => {
  const t = I.timeline([A2, A6], TL_INFRA);
  assert.deepEqual(t.gap, { from: '2026-12', to: '2029-03', months: 27, school: '계양1초' });
  const early = I.timeline([block('techno-Z', '2029.06')], TL_INFRA);
  assert.equal(early.gap, null);            // 개교가 입주보다 먼저면 공백 없음
  assert.equal(I.timeline([A2], Object.assign({}, TL_INFRA, { schools: [] })).gap, null);
});

test('timeline: 자료가 없으면 null', () => {
  assert.equal(I.timeline([A2], null), null);
  assert.equal(I.timeline([], TL_INFRA).lanes[0].items.length, 0);
});

/* ---------- 지도 안 단지 라벨(지면 라벨)에 들어가는 요약 ---------- */
test('shortDist: 라벨용 짧은 거리(약 없이)', () => {
  assert.equal(I.shortDist(118), '120 m');
  assert.equal(I.shortDist(994), '990 m');
  assert.equal(I.shortDist(1000), '1.0 km');
  assert.equal(I.shortDist(1234), '1.2 km');
});

test('stationLine: 가까운 역과 직선거리, 역 자료가 없으면 빈 글자', () => {
  assert.match(I.stationLine(A2, CTX), /^박촌역 [\d.]+ (m|km)$/);
  assert.equal(I.stationLine(A2, null), '');
  assert.equal(I.stationLine(A2, { stations: [] }), '');
  assert.equal(I.stationLine(null, CTX), '');
});

test('signalText: 기본은 주의만, all 이면 있는 종류 모두(기호+글자)', () => {
  const lv = { edu: 'warn', transit: 'info', power: null };
  assert.equal(I.signalText(lv), '▲교육');
  assert.equal(I.signalText(lv, true), '▲교육 ●교통');
  assert.equal(I.signalText({ edu: 'info', transit: 'none', power: 'info' }), '');
  assert.equal(I.signalText({ edu: 'info', transit: 'none', power: 'info' }, true), '●교육 ○교통 ●전기');
  assert.equal(I.signalText(null, true), '');
});

test('groundInfo: 역, 정류장 수, 신호 요약을 한 번에', () => {
  const g = I.groundInfo(A2, INFRA, CTX);
  assert.match(g.station, /^박촌역 [\d.]+ (m|km)$/);
  assert.equal(g.stops, 1);                                   // 300 m 안 정류장(당산초아래)
  assert.equal(g.warn, '▲교육');
  assert.equal(g.all, '▲교육 ●교통 ●전기');
  assert.equal(g.rest, '●교통 ●전기');                        // 주의를 뺀 나머지(기반시설 보기에서 보통 글자색으로 이어 붙임)
  const none = I.groundInfo(A2, null, CTX);
  assert.deepEqual([none.stops, none.warn, none.rest, none.all], [null, '', '', '']);
  assert.match(none.station, /역 [\d.]+ (m|km)$/);                    // 점검 자료가 없는 지역도 역은 나온다
});

/* ---------- 지면 라벨 위치: 카메라에 가까운 쪽 가장자리 바깥 ---------- */
test('frontPoint: 카메라가 보는 반대편(가까운 쪽) 가장자리 바깥의 지면 점', () => {
  const poly = sq(126.75, 37.55, 0.0005);                    // 중심 (126.75, 37.55), 한 변 약 90 m
  const south = I.frontPoint(poly, 0);                       // 북쪽을 보면 남쪽이 가깝다
  assert.ok(south[1] < 37.55 - 0.0005, `남쪽 가장자리 아래여야 함 ${south}`);
  assert.ok(Math.abs(south[0] - 126.75) < 0.0001);
  const north = I.frontPoint(poly, 180);                     // 남쪽을 보면 북쪽이 가깝다
  assert.ok(north[1] > 37.55 + 0.0005 && Math.abs(north[0] - 126.75) < 0.0001);
  const west = I.frontPoint(poly, 90);                       // 동쪽을 보면 서쪽이 가깝다
  assert.ok(west[0] < 126.75 - 0.0005 && Math.abs(west[1] - 37.55) < 0.0001);
  const east = I.frontPoint(poly, 270);
  assert.ok(east[0] > 126.75 + 0.0005 && Math.abs(east[1] - 37.55) < 0.0001);
});

test('frontPoint: 바깥으로 띄우는 거리를 따르고, 빈 도형은 null', () => {
  const poly = sq(126.75, 37.55, 0.0005);
  const near = I.frontPoint(poly, 0, 2), far = I.frontPoint(poly, 0, 30);
  assert.ok(far[1] < near[1]);
  assert.equal(I.frontPoint([], 0), null);
  assert.equal(I.frontPoint(null, 0), null);
});
