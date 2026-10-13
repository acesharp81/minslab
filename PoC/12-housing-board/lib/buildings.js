/* V-World 건물 레이어(LT_C_BLDGINFO) → 번들 buildings.json 과 같은 모양의 피처. 요청 시 조회(/api/v1/buildings)가 쓴다.
   tools/regiontools/buildings.py · geo.py 의 JS 이식이다. 규칙은 번들-어댑터-정의서 3.4:
   공식 높이 h>0 → eh=h(공식높이), 아니면 지상층수 f → eh=f×층고(층수환산), 둘 다 없으면 eh=3(정보없음). V-World 는 모르는 값을 "0"·""로 주므로 0은 모르는 값이다.
   번들은 지역 건물에서 높이÷층수 중앙값(층고)을 측정해 쓰지만, 요청 시 조회에는 지역 표본이 없어 계양 측정값(16,696동 중 높이·층수가 모두 있는 건물)을 기본값으로 쓴다 → 층수환산 높이는 근사.
   칸(cell): 0.01° 격자(약 0.9×1.1 km). 칸 번호 ix=floor(경도×100), iy=floor(위도×100). 건물은 중심점이 있는 칸에만 속한다(이웃 칸과 겹치지 않음).
   시험: tests/js/buildings.test.cjs (Python 구현에서 뽑은 기준값과 맞춤) */
'use strict';

const CELL_DEG = 0.01;
const KOREA = { lon: [124, 132], lat: [33, 39] };       // 칸 번호가 이 범위 밖이면 거절
const DEFAULT_FLOOR_M = 2.85;
const NO_INFO_M = 3.0;
const MIN_AREA_M2 = 10;                                  // 번들 빌드(min_building_m2)와 같은 값
const M_PER_DEG_LAT = 110540.0;
const M_PER_DEG_LON_EQ = 111320.0;

/* 계양 buildings.json meta.factor(2026-09-06 기준) */
const DEFAULT_FACTOR = {
  '공동주택_1-5': 3.1, '공동주택_6-10': 2.87, '공동주택_11-15': 2.82, '공동주택_16-20': 2.76, '공동주택_21+': 2.77,
  '단독주택': 3.7, '제1종근린생활시설': 4.0, '제2종근린생활시설': 3.97, '교육연구시설': 4.0, '노유자시설': 3.73, '종교시설': 4.15,
  '위험물저장및처리시설': 4.0, '동.식물 관련시설': 4.85, '자동차관련시설': 4.03, '숙박시설': 3.44, '공장': 4.05, '업무시설': 3.79, '창고시설': 4.6,
};

const USE_NAMES = {
  '01000': '단독주택', '02000': '공동주택', '03000': '제1종근린생활시설', '04000': '제2종근린생활시설',
  '05000': '문화및집회시설', '06000': '종교시설', '07000': '판매시설', '08000': '운수시설', '09000': '의료시설',
  '10000': '교육연구시설', '11000': '노유자시설', '12000': '수련시설', '13000': '운동시설', '14000': '업무시설',
  '15000': '숙박시설', '16000': '위락시설', '17000': '공장', '18000': '창고시설', '19000': '위험물저장및처리시설',
  '20000': '자동차관련시설', '21000': '동.식물 관련시설',
};

/* Python round() 와 같게: 소수 표현이 아니라 실제 이진 값 기준으로 반올림한다(예 4.05 → 4.0). Math.round 는 4.1 이 된다 */
const roundTo = (x, nd) => Number(x.toFixed(nd));

function toPosInt(v) {
  const n = Math.trunc(Number(String(v == null ? '' : v).trim()));
  return Number.isFinite(n) && n > 0 && String(v).trim() !== '' ? n : null;
}
function toPosFloat(v) {
  const s = String(v == null ? '' : v).trim();
  const x = s === '' ? NaN : Number(s);
  return Number.isFinite(x) && x > 0 ? x : null;
}
const useName = (code) => USE_NAMES[String(code == null ? '' : code).trim()] || null;

function floorBand(f) { return f <= 5 ? '1-5' : f <= 10 ? '6-10' : f <= 15 ? '11-15' : f <= 20 ? '16-20' : '21+'; }
function floorHeight(f, use, factor) {
  const fac = factor || {};
  if (use && use !== '공동주택' && use in fac) return fac[use];
  const v = fac[`공동주택_${floorBand(f)}`];
  return v === undefined ? DEFAULT_FLOOR_M : v;
}
function effectiveHeight(h, f, use, factor) {
  if (h && h > 0) return [roundTo(h, 2), '공식높이'];
  if (f && f > 0) return [roundTo(f * floorHeight(f, use, factor), 1), '층수환산'];
  return [NO_INFO_M, '정보없음'];
}
/* 높이/지상층수가 1.8~6.0 m 를 크게 벗어나면 1. 1층 건물은 판정하지 않는다 */
function mismatchFlag(h, f) {
  if (!h || !f || f < 2) return null;
  const r = h / f;
  return r < 1.8 || r > 6.0 ? 1 : null;
}

/* ---------- 지오메트리 ---------- */
const same = (a, b) => a[0] === b[0] && a[1] === b[1];
function openRing(ring) { const r = ring.slice(); if (r.length > 1 && same(r[0], r[r.length - 1])) r.pop(); return r; }
/* 소수 6자리로 반올림하고 연속 중복점을 지운다. 서로 다른 점이 3개 미만이면 null. closed 면 첫 점을 끝에 붙인다 */
function cleanRing(ring, nd = 6, closed = true) {
  let out = [];
  for (const p of ring || []) {
    const q = [roundTo(Number(p[0]), nd), roundTo(Number(p[1]), nd)];
    if (!out.length || !same(out[out.length - 1], q)) out.push(q);
  }
  out = openRing(out);
  if (new Set(out.map((p) => `${p[0]},${p[1]}`)).size < 3) return null;
  return closed ? out.concat([out[0].slice()]) : out;
}
const polygonsOf = (g) => (!g ? [] : g.type === 'Polygon' ? [g.coordinates || []] : g.type === 'MultiPolygon' ? (g.coordinates || []).slice() : []);
function cleanGeometry(geom) {
  const polys = [];
  for (const poly of polygonsOf(geom)) {
    const rings = poly.map((r) => cleanRing(r));
    if (!rings.length || rings[0] === null) continue;
    polys.push([rings[0]].concat(rings.slice(1).filter((r) => r !== null)));
  }
  if (!polys.length) return null;
  return geom.type === 'Polygon' ? { type: 'Polygon', coordinates: polys[0] } : { type: 'MultiPolygon', coordinates: polys };
}
function ringAreaM2(ring) {
  const r = openRing(ring);
  if (r.length < 3) return 0;
  const lat0 = r.reduce((a, p) => a + p[1], 0) / r.length;
  const ox = r[0][0], oy = r[0][1];   // 첫 점을 원점으로 옮겨 큰 수끼리 빼는 오차를 줄인다(Python 과 같은 방식)
  let s = 0;
  for (let i = 0; i < r.length; i++) { const x1 = r[i][0] - ox, y1 = r[i][1] - oy, x2 = r[(i + 1) % r.length][0] - ox, y2 = r[(i + 1) % r.length][1] - oy; s += x1 * y2 - x2 * y1; }
  return Math.abs(s / 2) * M_PER_DEG_LON_EQ * Math.cos(lat0 * (Math.PI / 180)) * M_PER_DEG_LAT;
}
function geometryAreaM2(geom) {
  let total = 0;
  for (const poly of polygonsOf(geom)) if (poly.length) total += ringAreaM2(poly[0]) - poly.slice(1).reduce((a, h) => a + ringAreaM2(h), 0);
  return Math.max(total, 0);
}
/* 건물 중심점(바깥 링 꼭짓점 평균). 칸 소속과 중복 판정에 쓴다 */
function centroidOf(geom) {
  const p = polygonsOf(geom)[0];
  const ring = p && p[0] && openRing(p[0]);
  if (!ring || !ring.length) return null;
  return [ring.reduce((a, q) => a + q[0], 0) / ring.length, ring.reduce((a, q) => a + q[1], 0) / ring.length];
}

/* ---------- 속성 ---------- */
function buildingProps(props, factor = DEFAULT_FACTOR) {
  const h = toPosFloat(props.height), f = toPosInt(props.grnd_flr), b = toPosInt(props.ugrnd_flr), u = useName(props.usability);
  const [eh, src] = effectiveHeight(h, f, u, factor);
  const out = { eh, src };
  if (h) out.h = roundTo(h, 2);
  if (f) out.f = f;
  if (b) out.b = b;
  if (u) out.u = u;
  const name = [String(props.bld_nm || '').trim(), String(props.dong_nm || '').trim()].filter(Boolean).join(' ');
  if (/[0-9A-Za-z가-힣]/.test(name)) out.n = name;   // 원천에 '.' 만 적힌 이름이 있어(팝업에 '. .') 글자·숫자가 없으면 이름 없음으로 본다. Python 번들 빌드와 다른 점
  const day = String(props.useapr_day || '').trim();
  if (day.length >= 4 && /^\d{4}/.test(day) && Number(day.slice(0, 4)) >= 1900 && Number(day.slice(0, 4)) <= 2100) out.a = Number(day.slice(0, 4));
  const x = mismatchFlag(h, f);
  if (x) out.x = x;
  return out;
}

/* V-World 피처 하나 → 번들 모양 피처. 너무 작거나(10 m² 미만) 지오메트리가 깨졌으면 null */
function convertFeature(feature, { factor = DEFAULT_FACTOR, minAreaM2 = MIN_AREA_M2 } = {}) {
  const g = feature && feature.geometry;
  if (!g || geometryAreaM2(g) < minAreaM2) return null;
  const geometry = cleanGeometry(g);
  if (!geometry) return null;
  return { type: 'Feature', properties: buildingProps(feature.properties || {}, factor), geometry };
}

/* ---------- 칸 ---------- */
const cellOf = (lon, lat) => [Math.floor(lon / CELL_DEG + 1e-9), Math.floor(lat / CELL_DEG + 1e-9)];
function cellBbox(ix, iy) { const r = (n) => Math.round(n * 1e6) / 1e6; return [r(ix * CELL_DEG), r(iy * CELL_DEG), r((ix + 1) * CELL_DEG), r((iy + 1) * CELL_DEG)]; }
function parseCell(text) {
  const m = /^(-?\d{1,5}),(-?\d{1,5})$/.exec(String(text == null ? '' : text).trim());
  if (!m) return null;
  const ix = Number(m[1]), iy = Number(m[2]);
  const [x0, y0, x1, y1] = cellBbox(ix, iy);
  if (x0 < KOREA.lon[0] || x1 > KOREA.lon[1] || y0 < KOREA.lat[0] || y1 > KOREA.lat[1]) return null;
  return [ix, iy];
}
/* 중심점이 칸 안(왼쪽·아래 포함, 오른쪽·위 제외)인가 */
function inCell(pt, ix, iy) { const [x0, y0, x1, y1] = cellBbox(ix, iy); return !!pt && pt[0] >= x0 && pt[0] < x1 && pt[1] >= y0 && pt[1] < y1; }

module.exports = {
  CELL_DEG, KOREA, DEFAULT_FACTOR, USE_NAMES, MIN_AREA_M2,
  toPosInt, toPosFloat, useName, floorBand, floorHeight, effectiveHeight, mismatchFlag,
  cleanRing, cleanGeometry, ringAreaM2, geometryAreaM2, centroidOf, buildingProps, convertFeature,
  cellOf, cellBbox, parseCell, inCell,
};
