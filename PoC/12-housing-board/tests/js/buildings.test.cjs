'use strict';
/* lib/buildings.js — Python(tools/regiontools/buildings.py·geo.py)과 같은 결과를 내는지, 칸 계산이 맞는지 */
const test = require('node:test');
const assert = require('node:assert/strict');
const B = require('../../lib/buildings.js');

/* 아래 기준값은 Python 구현(계양 층고 측정값 factor)에서 뽑았다 */
const PY_CASES = [[{"bld_nm": "금강힐", "dong_nm": "", "usability": "02000", "grnd_flr": "5", "ugrnd_flr": "0", "height": "13", "useapr_day": "20011116"}, {"eh": 13.0, "src": "공식높이", "h": 13.0, "f": 5, "u": "공동주택", "n": "금강힐", "a": 2001}], [{"bld_nm": "우남푸르미아", "dong_nm": "101동", "usability": "02000", "grnd_flr": "15", "ugrnd_flr": "2", "height": "0", "useapr_day": "20060301"}, {"eh": 42.3, "src": "층수환산", "f": 15, "b": 2, "u": "공동주택", "n": "우남푸르미아 101동", "a": 2006}], [{"bld_nm": "", "dong_nm": "", "usability": "17000", "grnd_flr": "1", "ugrnd_flr": "0", "height": "", "useapr_day": ""}, {"eh": 4.0, "src": "층수환산", "f": 1, "u": "공장"}], [{"bld_nm": "가", "dong_nm": "", "usability": "09999", "grnd_flr": "", "ugrnd_flr": "", "height": "", "useapr_day": "abc"}, {"eh": 3.0, "src": "정보없음", "n": "가"}], [{"bld_nm": "교회", "dong_nm": "", "usability": "06000", "grnd_flr": "3", "ugrnd_flr": "1", "height": "30", "useapr_day": "19991231"}, {"eh": 30.0, "src": "공식높이", "h": 30.0, "f": 3, "b": 1, "u": "종교시설", "n": "교회", "a": 1999, "x": 1}], [{"bld_nm": "창고", "dong_nm": "B동", "usability": "18000", "grnd_flr": "2", "ugrnd_flr": "0", "height": "4.567", "useapr_day": "21010101"}, {"eh": 4.57, "src": "공식높이", "h": 4.57, "f": 2, "u": "창고시설", "n": "창고 B동"}], [{"bld_nm": "주택", "dong_nm": "", "usability": "02000", "grnd_flr": "22", "ugrnd_flr": "0", "height": "", "useapr_day": "20200101"}, {"eh": 60.9, "src": "층수환산", "f": 22, "u": "공동주택", "n": "주택", "a": 2020}]];
const PY_EXTRA = {"area_small": 24.40614436322613, "area_ring": 96.84511015406677, "clean_dup": [[126.7, 37.5], [126.7001, 37.5], [126.7001, 37.5001], [126.7, 37.5001], [126.7, 37.5]], "clean_bad": null, "mismatch": [1, null, 1, null], "eff": [[3.0, "정보없음"], [12.1, "층수환산"], [12.35, "공식높이"], [60.9, "층수환산"]]};

test('buildingProps: Python building_props 와 같은 속성(높이 규칙·용도·이름·사용승인 연도)', () => {
  for (const [input, expected] of PY_CASES) assert.deepEqual(B.buildingProps(input), expected, JSON.stringify(input));
});

test('높이 규칙: 공식 높이 → 층수환산 → 정보없음, 불일치 표시', () => {
  const fac = B.DEFAULT_FACTOR;
  assert.deepEqual(B.effectiveHeight(0, 0, null, fac), PY_EXTRA.eff[0]);
  assert.deepEqual(B.effectiveHeight(null, 3, '공장', fac), PY_EXTRA.eff[1]);
  assert.deepEqual(B.effectiveHeight(12.345, 4, null, fac), PY_EXTRA.eff[2]);
  assert.deepEqual(B.effectiveHeight(null, 22, '공동주택', fac), PY_EXTRA.eff[3]);
  assert.deepEqual([B.mismatchFlag(30, 3), B.mismatchFlag(4, 1), B.mismatchFlag(3, 2), B.mismatchFlag(13, 5)], PY_EXTRA.mismatch);
  assert.equal(B.floorHeight(7, null, {}), 2.85);                                       // 층고 표가 없으면 화면 기본값
});

test('지오메트리: 면적(근사), 링 정리(6자리·중복점·닫기), 퇴화 링 거절', () => {
  const ring = [[126.7000004, 37.5000004], [126.7001, 37.5000004], [126.7001, 37.5001], [126.7000004, 37.5001], [126.7000004, 37.5000004]];
  assert.ok(Math.abs(B.ringAreaM2(ring) - PY_EXTRA.area_ring) < 1e-9);
  const small = { type: 'Polygon', coordinates: [[[126.7, 37.5], [126.70005, 37.5], [126.70005, 37.50005], [126.7, 37.50005], [126.7, 37.5]]] };
  assert.ok(Math.abs(B.geometryAreaM2(small) - PY_EXTRA.area_small) < 1e-9);
  assert.deepEqual(B.cleanRing([[126.7, 37.5], [126.7, 37.5], [126.7001, 37.5], [126.7001, 37.5001], [126.7, 37.5001], [126.7, 37.5]]), PY_EXTRA.clean_dup);
  assert.equal(B.cleanRing([[1, 1], [1, 1], [2, 2]]), null);
});

const SQ = (x, y, d = 0.0002) => ({ type: 'Polygon', coordinates: [[[x, y], [x + d, y], [x + d, y + d], [x, y + d], [x, y]]] });

test('convertFeature: 번들 피처 모양, 10 m² 미만·깨진 지오메트리는 버림, MultiPolygon 유지', () => {
  const f = B.convertFeature({ type: 'Feature', properties: { bld_nm: '금강힐', usability: '02000', grnd_flr: '5', height: '13', useapr_day: '20011116' }, geometry: SQ(126.75, 37.55) });
  assert.equal(f.type, 'Feature'); assert.deepEqual(f.properties, { eh: 13, src: '공식높이', h: 13, f: 5, u: '공동주택', n: '금강힐', a: 2001 });
  assert.equal(f.geometry.type, 'Polygon'); assert.deepEqual(f.geometry.coordinates[0][0], f.geometry.coordinates[0][4]);
  assert.equal(B.convertFeature({ properties: {}, geometry: SQ(126.75, 37.55, 0.00003) }), null);           // 약 2.6×3.3 m = 8.7 m²
  assert.equal(B.convertFeature({ properties: {}, geometry: null }), null);
  assert.equal(B.convertFeature({ properties: {}, geometry: { type: 'Point', coordinates: [1, 2] } }), null);
  const m = B.convertFeature({ properties: {}, geometry: { type: 'MultiPolygon', coordinates: [SQ(126.75, 37.55).coordinates, SQ(126.76, 37.55).coordinates] } });
  assert.equal(m.geometry.type, 'MultiPolygon'); assert.equal(m.geometry.coordinates.length, 2);
});

test('칸: 번호·범위·반열린 소속, 한국 밖과 이상한 형식은 거절', () => {
  assert.deepEqual(B.cellOf(126.7516, 37.5508), [12675, 3755]);
  assert.deepEqual(B.cellBbox(12675, 3755), [126.75, 37.55, 126.76, 37.56]);
  assert.deepEqual(B.parseCell('12675,3755'), [12675, 3755]);
  for (const bad of ['', 'a,b', '12675', '12675,3755,1', '1,2', '99999,3755', '12675,99999', '12675, 3755 x', null, undefined]) assert.equal(B.parseCell(bad), null, String(bad));
  assert.deepEqual(B.parseCell(' 12675,3755 '), [12675, 3755]);
  assert.ok(B.inCell([126.75, 37.55], 12675, 3755));            // 왼쪽·아래 경계는 포함
  assert.ok(!B.inCell([126.76, 37.55], 12675, 3755));           // 오른쪽 경계는 이웃 칸
  assert.ok(!B.inCell([126.755, 37.56], 12675, 3755));          // 위쪽 경계는 이웃 칸
  assert.ok(!B.inCell(null, 12675, 3755));
  const c = B.centroidOf(SQ(126.7551, 37.5551));
  assert.ok(B.inCell(c, 12675, 3755));
});

test('이름: 글자·숫자가 없는 이름(".", ". .")은 이름 없음, 건물명+동 이름은 이어 붙임', () => {
  assert.equal(B.buildingProps({ bld_nm: '.', dong_nm: '.', height: '10' }).n, undefined);
  assert.equal(B.buildingProps({ bld_nm: ' ', dong_nm: '', height: '10' }).n, undefined);
  assert.equal(B.buildingProps({ bld_nm: '펠리스타운', dong_nm: '104동', height: '10' }).n, '펠리스타운 104동');
  assert.equal(B.buildingProps({ bld_nm: '', dong_nm: '3동', height: '10' }).n, '3동');
});
