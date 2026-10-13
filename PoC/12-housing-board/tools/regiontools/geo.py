"""좌표 계산용 순수 함수. 좌표는 WGS84 [경도, 위도]. 표준 라이브러리만 쓴다.

면적은 작은 영역(블록·건물)용 근사다: 링 평균 위도에서 경도 1°=111,320·cos(위도) m, 위도 1°=110,540 m.
"""
from __future__ import annotations

import math
from typing import Iterable, Iterator, Sequence

M_PER_DEG_LAT = 110540.0
M_PER_DEG_LON_EQ = 111320.0


def round_pt(pt: Sequence[float], nd: int = 6) -> list[float]:
    return [round(float(pt[0]), nd), round(float(pt[1]), nd)]


def _same(a, b) -> bool:
    return a[0] == b[0] and a[1] == b[1]


def open_ring(ring: Sequence[Sequence[float]]) -> list:
    """닫는 점(첫 점과 같은 마지막 점)을 뺀 링."""
    ring = list(ring)
    if len(ring) > 1 and _same(ring[0], ring[-1]):
        ring = ring[:-1]
    return ring


def clean_ring(ring: Sequence[Sequence[float]], nd: int = 6, closed: bool = False) -> list | None:
    """소수 nd자리로 반올림하고 연속 중복점을 지운다. 서로 다른 점이 3개 미만이면 None.

    closed=False면 닫는 점 없이(번들의 poly), True면 첫 점을 끝에 붙여(GeoJSON) 돌려준다.
    """
    out: list[list[float]] = []
    for p in ring:
        q = round_pt(p, nd)
        if not out or not _same(out[-1], q):
            out.append(q)
    out = open_ring(out)
    if len({(p[0], p[1]) for p in out}) < 3:
        return None
    return out + [list(out[0])] if closed else out


def point_in_ring(pt: Sequence[float], ring: Sequence[Sequence[float]]) -> bool:
    """반직선 교차법. 열린 링·닫힌 링 모두 된다."""
    x, y = pt[0], pt[1]
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > y) != (y2 > y):
            xc = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < xc:
                inside = not inside
    return inside


def point_in_polygon(pt: Sequence[float], rings: Sequence[Sequence[Sequence[float]]]) -> bool:
    """rings[0]은 바깥 링, 나머지는 구멍."""
    if not rings or not point_in_ring(pt, rings[0]):
        return False
    return not any(point_in_ring(pt, h) for h in rings[1:])


def polygons_of(geom: dict) -> list:
    """Polygon/MultiPolygon을 다각형(링 목록) 목록으로."""
    if not geom:
        return []
    t, c = geom.get("type"), geom.get("coordinates") or []
    if t == "Polygon":
        return [c]
    if t == "MultiPolygon":
        return list(c)
    return []


def point_in_geometry(pt: Sequence[float], geom: dict) -> bool:
    return any(point_in_polygon(pt, poly) for poly in polygons_of(geom))


def outer_rings(geom: dict) -> list:
    return [poly[0] for poly in polygons_of(geom) if poly]


def geometry_points(geom: dict) -> Iterator[list]:
    for poly in polygons_of(geom):
        for ring in poly:
            for p in ring:
                yield p


def _local(ring: Sequence[Sequence[float]]):
    """첫 점을 원점으로 옮긴 좌표와 원점. 경위도 절대값(126°, 35°)으로 신발끈 공식을 쓰면
    상쇄 오차로 건물 크기 링의 중심이 수십~수백 m 틀어지므로 반드시 옮겨서 계산한다."""
    ring = open_ring(ring)
    if not ring:
        return [], (0.0, 0.0)
    ox, oy = float(ring[0][0]), float(ring[0][1])
    return [(float(p[0]) - ox, float(p[1]) - oy) for p in ring], (ox, oy)


def _signed_area_deg(ring: Sequence[Sequence[float]]) -> float:
    pts, _ = _local(ring)
    n = len(pts)
    s = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def ring_area_m2(ring: Sequence[Sequence[float]]) -> float:
    ring = open_ring(ring)
    if len(ring) < 3:
        return 0.0
    lat0 = sum(p[1] for p in ring) / len(ring)
    kx = M_PER_DEG_LON_EQ * math.cos(math.radians(lat0))
    return abs(_signed_area_deg(ring)) * kx * M_PER_DEG_LAT


def geometry_area_m2(geom: dict) -> float:
    total = 0.0
    for poly in polygons_of(geom):
        if not poly:
            continue
        total += ring_area_m2(poly[0]) - sum(ring_area_m2(h) for h in poly[1:])
    return max(total, 0.0)


def ring_centroid(ring: Sequence[Sequence[float]]) -> tuple[float, float]:
    """넓이 가중 중심. 넓이가 0이면 점들의 평균."""
    pts, (ox, oy) = _local(ring)
    n = len(pts)
    if n == 0:
        raise ValueError("빈 링")
    a = _signed_area_deg(ring)
    if abs(a) < 1e-20:
        return (ox + sum(p[0] for p in pts) / n, oy + sum(p[1] for p in pts) / n)
    cx = cy = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    return (ox + cx / (6 * a), oy + cy / (6 * a))


def geometry_centroid(geom: dict) -> tuple[float, float]:
    """바깥 링 중심들을 넓이로 가중 평균."""
    rings = outer_rings(geom)
    if not rings:
        raise ValueError("다각형이 없음")
    ws = [abs(_signed_area_deg(r)) for r in rings]
    cs = [ring_centroid(r) for r in rings]
    tot = sum(ws)
    if tot <= 0:
        return cs[0]
    return (sum(c[0] * w for c, w in zip(cs, ws)) / tot, sum(c[1] * w for c, w in zip(cs, ws)) / tot)


def convex_hull(points: Iterable[Sequence[float]]) -> list[list[float]]:
    """모노톤 체인. 반시계 방향의 열린 링(가장 왼쪽 아래 점부터)."""
    pts = sorted({(float(p[0]), float(p[1])) for p in points})
    if len(pts) <= 2:
        return [list(p) for p in pts]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return [list(p) for p in lower[:-1] + upper[:-1]]


def simplify_ring(ring: Sequence[Sequence[float]], max_points: int = 100) -> list:
    """비스발링감-와이엇: 이웃과 만드는 삼각형 넓이가 가장 작은 점부터 지워 max_points 이하로 줄인다.

    남는 점은 모두 원래 점이다. 이미 작으면 그대로 돌려준다.
    """
    pts = [list(p) for p in open_ring(ring)]
    if len(pts) <= max_points:
        return pts
    max_points = max(max_points, 3)

    def tri(a, b, c):
        return abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]))

    while len(pts) > max_points:
        n = len(pts)
        i = min(range(n), key=lambda k: tri(pts[k - 1], pts[k], pts[(k + 1) % n]))
        del pts[i]
    return pts


def bbox_of(points: Iterable[Sequence[float]]) -> tuple:
    xs, ys = [], []
    for p in points:
        xs.append(p[0])
        ys.append(p[1])
    if not xs:
        raise ValueError("점이 없음")
    return (min(xs), min(ys), max(xs), max(ys))


def expand_bbox(b: Sequence[float], d: float) -> tuple:
    return (b[0] - d, b[1] - d, b[2] + d, b[3] + d)


def bbox_center(b: Sequence[float]) -> tuple:
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)
