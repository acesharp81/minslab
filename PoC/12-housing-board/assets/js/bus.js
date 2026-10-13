/* 버스 노선·위치(infra.json busRoutes + /api/bus 응답)의 순수 함수. DOM·지도는 만지지 않는다(node --test 로 시험: tests/js/bus.test.cjs).
   자료 모양의 정본: schemas/bundle/infra.schema.json(busRoutes) · api/bus.js(위치 응답)
   원칙: 위치는 국토교통부 TAGO 가 알려 준 값을 그대로 보이고(실시간이 아니라 몇 십 초 전 값일 수 있다), 방향·경유 단지는 노선 경로(정류소를 이은 선)로 어림한 값이다.
   버스는 여러 개의 입체 조각(차체·창·지붕·앞 표지·범퍼·바퀴·에어컨)을 맞춰 만든 모형이다(MODEL). 지도 엔진의 fill-extrusion 만 쓰므로 추가 라이브러리·모델 파일이 없다.
   멀리서는 눈에 띄도록 키우고(scaleFor) 확대 17.5 부터는 실제 크기로 그린다. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.BusLib = api;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const BUS_LEN_M = 11, BUS_WID_M = 2.5;                  // 시내버스 실제 크기(길이·폭, m). 높이는 약 3.2 m
  const GLASS_COLOR = '#2B3A4A', CAB_COLOR = '#161E28', ROOF_COLOR = '#E9EEF3', UNIT_COLOR = '#C5CDD6', BUMPER_COLOR = '#3A3F47', TIRE_COLOR = '#16181C';
  /* 버스 모형: [부품, 앞뒤 범위(앞이 +) a0·a1, 좌우 범위(오른쪽이 +) b0·b1, 높이 범위 z0·z1, 색('route' 는 노선 색)] — 단위 m, 같은 높이의 면이 겹치지 않게 나눴다 */
  const MODEL = [
    ['wheel', 3.5, 4.3, 1.0, 1.3, 0, 0.95, TIRE_COLOR], ['wheel', 3.5, 4.3, -1.3, -1.0, 0, 0.95, TIRE_COLOR],
    ['wheel', -3.6, -2.8, 1.0, 1.3, 0, 0.95, TIRE_COLOR], ['wheel', -3.6, -2.8, -1.3, -1.0, 0, 0.95, TIRE_COLOR],
    ['bumper', 5.5, 5.72, -1.1, 1.1, 0.45, 0.95, BUMPER_COLOR], ['bumper', -5.72, -5.5, -1.1, 1.1, 0.45, 0.95, BUMPER_COLOR],
    ['body', -5.5, 5.5, -1.25, 1.25, 0.45, 1.45, 'route'],
    ['glass', -5.3, 4.2, -1.2, 1.2, 1.45, 2.55, GLASS_COLOR], ['cab', 4.2, 5.3, -1.2, 1.2, 1.45, 2.55, CAB_COLOR],
    ['roof', -5.2, 4.2, -1.1, 1.1, 2.55, 2.8, ROOF_COLOR], ['sign', 4.2, 5.2, -1.1, 1.1, 2.55, 2.8, 'route'],
    ['unit', -3.4, -1.0, -0.8, 0.8, 2.8, 3.2, UNIT_COLOR],
  ];
  /* 진행 방향을 모를 때: 방향이 없는 작은 덩어리(차체+창+지붕)로 그린다 */
  const MODEL_BLOB = [['body', -2.1, 2.1, -2.1, 2.1, 0.45, 1.45, 'route'], ['glass', -2.0, 2.0, -2.0, 2.0, 1.45, 2.55, GLASS_COLOR], ['roof', -1.9, 1.9, -1.9, 1.9, 2.55, 2.8, ROOF_COLOR]];
  const SCALE_FULL_ZOOM = 17.5, SCALE_MAX = 4;             // 이 확대부터 실제 크기, 멀어질수록 키운다(최대 4배)
  const PASS_M = 500;                                     // 노선 경로가 단지 중심에서 이 거리 안이면 '지나는 단지'(빌드가 실시간 노선을 고르는 기준 BUS_LIVE_M 과 같다)
  const MIN_POLL_S = 60, MAX_BACKOFF_S = 600;
  const TYPE_COLORS = [['간선', '#56B4E9'], ['지선', '#5BD6A8'], ['광역', '#FF8A65'], ['급행', '#FF8A65'], ['좌석', '#FF8A65'], ['순환', '#E6C34D'], ['마을', '#E6C34D']];
  const OTHER_COLOR = '#9AA8D6';

  const finite = (v) => typeof v === 'number' && Number.isFinite(v);
  const routeColor = (type) => { const t = String(type || ''); const hit = TYPE_COLORS.find(([k]) => t.includes(k)); return hit ? hit[1] : OTHER_COLOR; };
  const rad = (d) => d * Math.PI / 180;
  const kx = (lat) => 111320 * Math.cos(rad(lat)), KY = 110540;

  function distM(a, b) {
    const R = 6371008.8, dl = rad(b[1] - a[1]), dn = rad(b[0] - a[0]);
    const h = Math.sin(dl / 2) ** 2 + Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(dn / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }
  /* 두 점 사이 방위(북 0°, 시계 방향, 0~360) */
  function bearing(a, b) {
    const dx = (b[0] - a[0]) * kx((a[1] + b[1]) / 2), dy = (b[1] - a[1]) * KY;
    return (Math.atan2(dx, dy) * 180 / Math.PI + 360) % 360;
  }
  /* 점 p 에서 선분 ab 까지 거리(m) */
  function segDistM(p, a, b) {
    const k = kx(p[1]), ax = (a[0] - p[0]) * k, ay = (a[1] - p[1]) * KY, bx = (b[0] - p[0]) * k, by = (b[1] - p[1]) * KY;
    const dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy;
    const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, -(ax * dx + ay * dy) / len2));
    return Math.hypot(ax + dx * t, ay + dy * t);
  }
  const pathDistM = (p, path) => { let m = Infinity; for (let i = 0; i + 1 < path.length; i++) m = Math.min(m, segDistM(p, path[i], path[i + 1])); return m; };

  /* 응답(JSON) → { at, ttl, buses, failed } — 모양이 다르면 null */
  function parse(json) {
    if (!json || typeof json !== 'object' || !Array.isArray(json.buses)) return null;
    const buses = json.buses.filter((b) => b && typeof b.v === 'string' && typeof b.r === 'string' && finite(b.lon) && finite(b.lat));
    return { at: typeof json.at === 'string' ? json.at : null, ttl: finite(json.ttl) ? Math.max(MIN_POLL_S, json.ttl) : MIN_POLL_S, buses, failed: Array.isArray(json.failed) ? json.failed : [] };
  }

  /* 진행 방향(방위, 도): 버스가 마지막으로 지난 정류소(ord) → 다음 정류소. 같은 좌표(기점 미정차 등)는 건너뛴다. 모르면 null */
  function headingOf(path, ord) {
    if (!Array.isArray(path) || !finite(ord) || ord < 1 || ord > path.length) return null;
    const here = path[ord - 1];
    for (let i = ord; i < Math.min(path.length, ord + 4); i++) if (path[i][0] !== here[0] || path[i][1] !== here[1]) return bearing(here, path[i]);
    for (let i = ord - 2; i >= Math.max(0, ord - 5); i--) if (path[i][0] !== here[0] || path[i][1] !== here[1]) return bearing(path[i], here);   // 종점 근처는 직전 구간
    return null;
  }

  /* 확대 단계에 따른 크기 배율: 17.5 이상은 1(실제 크기), 멀어질수록 커져 최대 4배. 소수 둘째 자리까지만(자주 다시 그리지 않게) */
  const scaleFor = (zoom) => { const z = finite(zoom) ? zoom : 16; return Math.round(Math.min(SCALE_MAX, Math.max(1, 2 ** ((SCALE_FULL_ZOOM - z) * 0.7))) * 20) / 20; };

  /* 버스 중심(lon, lat)에서 앞 a0~a1 m, 오른쪽 b0~b1 m 범위의 직사각형(닫힌 링, 방향 heading 도). s 는 크기 배율 */
  function boxRing(lon, lat, heading, s, a0, a1, b0, b1) {
    const h = rad(finite(heading) ? heading : 0), fx = Math.sin(h), fy = Math.cos(h), rx = Math.cos(h), ry = -Math.sin(h), k = kx(lat);   // 앞쪽·오른쪽 단위 벡터(동·북)
    const pt = (a, b) => [Math.round((lon + (fx * a + rx * b) * s / k) * 1e7) / 1e7, Math.round((lat + (fy * a + ry * b) * s / KY) * 1e7) / 1e7];
    const ring = [pt(a1, b0), pt(a1, b1), pt(a0, b1), pt(a0, b0)];
    return [...ring, ring[0]];
  }
  /* 버스 바닥면 전체(직사각형). 방향을 모르면 정사각형에 가깝게 그린다 */
  function busRing(lon, lat, heading, scale) {
    const s = scale || 1, known = finite(heading), hl = known ? BUS_LEN_M / 2 : BUS_WID_M * 0.8 * 1.6, hw = known ? BUS_WID_M / 2 : BUS_WID_M * 0.8 * 1.6;
    return boxRing(lon, lat, known ? heading : 0, s, -hl, hl, -hw, hw);
  }
  /* 버스 한 대의 모형 조각들 → [{ part, ring, base, h, c }] */
  function busParts(lon, lat, heading, routeColor_, scale) {
    const s = scale || 1;
    return (finite(heading) ? MODEL : MODEL_BLOB).map(([part, a0, a1, b0, b1, z0, z1, color]) =>
      ({ part, ring: boxRing(lon, lat, heading, s, a0, a1, b0, b1), base: z0 * s, h: z1 * s, c: color === 'route' ? routeColor_ : color }));
  }

  /* 버스 목록 → 3D 조각들(solids)과 번호 라벨 점(labels). routes 는 busRoutes 목록, scale 은 크기 배율(scaleFor) */
  function features(buses, routes, scale) {
    const byId = new Map((routes || []).map((r) => [r.id, r])), s = scale || 1;
    const solids = [], labels = [];
    for (const b of buses) {
      const r = byId.get(b.r) || {}, color = routeColor(r.type), hd = finite(b.hd) ? b.hd : headingOf(r.path, b.ord), props = { v: b.v, r: b.r, no: r.no || '' };
      for (const q of busParts(b.lon, b.lat, hd, color, s)) solids.push({ type: 'Feature', properties: { ...props, part: q.part, c: q.c, base: q.base, h: q.h }, geometry: { type: 'Polygon', coordinates: [q.ring] } });
      labels.push({ type: 'Feature', properties: { ...props, c: color, text: r.no ? `${r.no}번` : '버스' }, geometry: { type: 'Point', coordinates: [b.lon, b.lat] } });
    }
    return { solids: { type: 'FeatureCollection', features: solids }, labels: { type: 'FeatureCollection', features: labels } };
  }

  /* 직전 위치 → 새 위치를 t(0~1)만큼 섞는다. 차량번호로 짝짓고, 새로 나타난 차는 새 위치 그대로. 방향은 짧은 쪽으로 돈다 */
  function interpolate(prev, next, t) {
    const old = new Map((prev || []).map((b) => [b.v, b])), k = Math.max(0, Math.min(1, t));
    return next.map((b) => {
      const p = old.get(b.v);
      if (!p) return b;
      const out = { ...b, lon: p.lon + (b.lon - p.lon) * k, lat: p.lat + (b.lat - p.lat) * k };
      if (finite(p.hd) && finite(b.hd)) { const d = ((b.hd - p.hd + 540) % 360) - 180; out.hd = (p.hd + d * k + 360) % 360; }
      return out;
    });
  }

  /* 새 응답의 버스에 방향(hd)을 붙인다: 경로에서 구하고, 없으면 직전 위치에서 움직인 쪽(5 m 넘게 움직였을 때) */
  function withHeading(buses, routes, prev) {
    const byId = new Map((routes || []).map((r) => [r.id, r])), old = new Map((prev || []).map((b) => [b.v, b]));
    return buses.map((b) => {
      let hd = headingOf((byId.get(b.r) || {}).path, b.ord);
      const p = old.get(b.v);
      if (hd === null && p && distM([p.lon, p.lat], [b.lon, b.lat]) > 5) hd = bearing([p.lon, p.lat], [b.lon, b.lat]);
      if (hd === null && p && finite(p.hd)) hd = p.hd;
      return hd === null ? b : { ...b, hd };
    });
  }

  /* 노선이 지나는 단지: 경로(정류소를 이은 선)가 단지 중심에서 radiusM 안인 단지, 가까운 순 → [{ id, d }] */
  function passes(route, blocks, centroidOf, radiusM) {
    if (!route || !Array.isArray(route.path) || route.path.length < 2) return [];
    const lim = radiusM || PASS_M;
    return blocks.map((b) => ({ id: b.id, d: pathDistM(centroidOf(b), route.path) })).filter((x) => x.d <= lim).sort((a, b) => a.d - b.d);
  }
  function nearestBlock(pt, blocks, centroidOf) {
    let best = null;
    for (const b of blocks) { const d = distM(pt, centroidOf(b)); if (!best || d < best.d) best = { id: b.id, d }; }
    return best;
  }

  const fmtDist = (d) => (d < 1000 ? `약 ${Math.max(10, Math.round(d / 10) * 10)} m` : `약 ${(d / 1000).toFixed(1)} km`);
  function ageText(at, now) {
    const t = Date.parse(at || ''); if (!Number.isFinite(t)) return '';
    const s = Math.max(0, Math.round(((now == null ? Date.now() : now) - t) / 1000));
    return s < 45 ? '방금' : s < 3600 ? `${Math.round(s / 60)}분 전` : '1시간 넘게 지남';
  }
  /* 다음 호출까지 기다릴 시간(ms): 서버가 알려 준 ttl 이상, 실패하면 2배씩(최대 10분) */
  function pollDelayMs(ttl, failures) {
    const base = Math.max(MIN_POLL_S, finite(ttl) ? ttl : MIN_POLL_S), n = Math.max(0, failures || 0);
    return Math.min(base * 2 ** n, Math.max(base, MAX_BACKOFF_S)) * 1000;
  }
  /* 버스 한 대의 팝업 내용 */
  function describe(bus, route, blocks, centroidOf, at, now) {
    const r = route || {}, near = nearestBlock([bus.lon, bus.lat], blocks, centroidOf), pass = passes(r, blocks, centroidOf);
    return {
      title: r.no ? `${r.no}번 ${r.type || '버스'}` : '버스', plate: bus.v, color: routeColor(r.type), from: r.from || '', to: r.to || '',
      where: bus.stop ? `${bus.stop}${finite(bus.ord) ? ` · ${bus.ord}번째 정류소` : ''} 부근` : '',
      near: near ? { id: near.id, d: near.d, text: `${near.id} 단지에서 ${fmtDist(near.d)}` } : null,
      passes: pass.map((x) => x.id), age: ageText(at, now),
    };
  }

  return { routeColor, distM, bearing, segDistM, pathDistM, parse, headingOf, scaleFor, boxRing, busRing, busParts, features, interpolate, withHeading, passes, nearestBlock, fmtDist, ageText, pollDelayMs, describe,
    BUS_LEN_M, BUS_WID_M, MODEL, MODEL_BLOB, GLASS_COLOR, SCALE_FULL_ZOOM, SCALE_MAX, PASS_M, MIN_POLL_S, TYPE_COLORS };
});
