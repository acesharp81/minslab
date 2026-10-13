'use strict';
/* scripts/smoke.js 의 판정 함수: 경계 윤곽이 쓸 만한가, 칸 번호, 열림·경고 판정 */
const test = require('node:test');
const assert = require('node:assert/strict');
const S = require('../../scripts/smoke.js');

const SQ = [[127, 37], [127.1, 37], [127.1, 37.1], [127, 37.1], [127, 37]];

test('geometryOk: Polygon·MultiPolygon 에 점 4개 이상 링이 있어야 쓸 만하다', () => {
  assert.equal(S.geometryOk({ type: 'Polygon', coordinates: [SQ] }), true);
  assert.equal(S.geometryOk({ type: 'MultiPolygon', coordinates: [[SQ], [SQ]] }), true);
  for (const bad of [null, {}, { type: 'Point', coordinates: [1, 1] }, { type: 'Polygon', coordinates: [[[1, 1], [2, 2]]] }, { type: 'Polygon', coordinates: [[[1, 'a'], [2, 2], [3, 3], [1, 'a']]] }, { type: 'Polygon', coordinates: [] }]) assert.equal(S.geometryOk(bad), false);
});

test('cellOf: 0.01° 칸 번호(경도×100, 위도×100 의 내림)', () => {
  assert.equal(S.cellOf(127.2145, 37.5392), '12721,3753'); assert.equal(S.cellOf(128.001, 37.551), '12800,3755'); assert.equal(S.cellOf(126.99999, 35.0001), '12699,3500');   // 칸 경계 위(37.55×100=3754.99…)는 부동소수 오차라 시험하지 않는다
});

test('judge: 열림 = 검색·해석 성공 + 경계. 인허가 0건·서울 정류소 없음은 정상, 오류·느림·대장 한도는 경고', () => {
  const base = { search: { ok: true }, resolve: { ok: true, geometry: true, ms: 300 }, buildings: { ok: true, count: 10, ms: 900 }, permits: { ok: true, ms: 2000 }, infra: { ok: true, ms: 3000 } };
  assert.deepEqual(S.judge(base), { open: true, why: '', warn: [] });
  assert.equal(S.judge({ ...base, search: { ok: false, status: 200 } }).open, false); assert.match(S.judge({ ...base, search: { ok: false, status: 200 } }).why, /검색 실패/);
  assert.match(S.judge({ ...base, resolve: { ok: false, status: 404, code: 'unknown-code' } }).why, /해석 실패\(404 unknown-code\)/);
  assert.equal(S.judge({ ...base, resolve: { ok: true, geometry: false } }).why, '경계 없음');
  const w = S.judge({ ...base, buildings: { ok: true, count: 0, ms: 1 }, permits: { ok: true, ms: 25000, ledgerError: '한도', parcelErrors: 2 }, infra: { ok: true, ms: 15000, stopsError: 'x' } });
  assert.equal(w.open, true); for (const t of ['건물 0', '대장:한도', '필지 오류 2', '기반시설 일부 실패', '인허가 25초(느림)', '기반시설 15초(느림)']) assert.ok(w.warn.includes(t), t);
  assert.ok(S.judge({ ...base, permits: { ok: false, status: 429 } }).warn.includes('인허가 429'));
  assert.deepEqual(S.judge({ search: { ok: true }, resolve: { ok: true, geometry: true, ms: 100 } }), { open: true, why: '', warn: [] });                 // 번들 없는 시군구: 건물·인허가를 부르지 않았다
});

test('표본 파일: 지역 이름이 중복 없이 59곳 안팎이고 시도 17곳과 입력 방식(지번·도로명·장소·코드·시군구)을 담는다', () => {
  const list = require('../smoke/regions.json').regions.map((r) => r.q);
  assert.equal(new Set(list).size, list.length); assert.ok(list.length >= 50);
  for (const want of ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주']) assert.ok(list.some((q) => q.includes(want) || ({ 경기: /수원|화성|성남|김포|평택|양평|과천|남양주|하남/, 강원: /춘천|양양|강릉/, 충북: /청주|음성|옥천/, 충남: /천안|아산|예산/, 전북: /전주|군산|완주/, 전남: /순천|나주|무안|담양/, 경북: /포항|경산|울릉/, 경남: /창원|김해|진주/ }[want] || /$^/).test(q)), want);
  assert.ok(list.includes('4145011400') && list.includes('41450') && list.includes('하남시청') && list.some((q) => /\d+-\d+/.test(q)) && list.some((q) => /길/.test(q)));
});
