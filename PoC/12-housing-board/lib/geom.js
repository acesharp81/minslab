/* 지오메트리 공용 함수(경계·필지·건물 API 가 같이 쓴다). 좌표는 WGS84 [경도, 위도], 소수 5자리(약 1 m).
   시험: tests/js/resolve.test.cjs · tests/js/permits.test.cjs */
'use strict';

const round5 = (n) => Math.round(n * 1e5) / 1e5;

/* 링을 소수 5자리로 줄이고 연속 중복점을 지운 뒤 max 점 이하로 솎는다. 닫힌 링으로 돌려주고, 점이 3개 미만이면 null */
function thinRing(ring, max = 600) {
  const pts = [];
  for (const p of ring) { const q = [round5(p[0]), round5(p[1])]; const last = pts[pts.length - 1]; if (!last || last[0] !== q[0] || last[1] !== q[1]) pts.push(q); }
  const open = pts.length > 1 && pts[0][0] === pts[pts.length - 1][0] && pts[0][1] === pts[pts.length - 1][1] ? pts.slice(0, -1) : pts;
  const kept = open.length <= max ? open : Array.from({ length: max }, (_, i) => open[Math.floor(i * open.length / max)]);
  return kept.length >= 3 ? [...kept, kept[0]] : null;
}
function thinGeometry(g, max = 600) {
  if (!g || !g.coordinates) return null;
  const polys = g.type === 'Polygon' ? [g.coordinates] : g.type === 'MultiPolygon' ? g.coordinates : [];
  const out = polys.map((rings) => rings.map((r) => thinRing(r, max)).filter(Boolean)).filter((rings) => rings.length);
  if (!out.length) return null;
  return out.length === 1 ? { type: 'Polygon', coordinates: out[0] } : { type: 'MultiPolygon', coordinates: out };
}
function bboxOf(g) {
  let x0 = 180, y0 = 90, x1 = -180, y1 = -90;
  const polys = g.type === 'Polygon' ? [g.coordinates] : g.coordinates;
  for (const rings of polys) for (const p of rings[0]) { x0 = Math.min(x0, p[0]); y0 = Math.min(y0, p[1]); x1 = Math.max(x1, p[0]); y1 = Math.max(y1, p[1]); }
  return [round5(x0), round5(y0), round5(x1), round5(y1)];
}
/* 링 면적(도², 부호 없음)으로 가장 큰 다각형의 바깥 링(구멍 제외)만 Polygon 으로. 필지가 MultiPolygon 일 때 대표 윤곽 */
function largestPolygon(g) {
  const polys = !g ? [] : g.type === 'Polygon' ? [g.coordinates] : g.type === 'MultiPolygon' ? g.coordinates : [];
  const area = (r) => { let s = 0; for (let i = 0; i < r.length - 1; i++) s += r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1]; return Math.abs(s / 2); };
  let best = null, ba = -1;
  for (const rings of polys) { if (rings && rings[0] && rings[0].length >= 4) { const a = area(rings[0]); if (a > ba) { ba = a; best = rings[0]; } } }
  return best ? { type: 'Polygon', coordinates: [best] } : null;
}

module.exports = { round5, thinRing, thinGeometry, bboxOf, largestPolygon };
