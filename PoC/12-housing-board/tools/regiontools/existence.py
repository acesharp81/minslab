"""신도시 지구 안에서 철거됐을 가능성이 있는 옛 건물에 g=1 을 붙인다(현존 확인: 도로명주소 건물 LT_C_SPBD).

배경(dataset.md 2.6): V-World 건물 레이어(LT_C_BLDGINFO)에는 신도시 조성 전 옛 건물이 대장 속성을 가진 채 남아 있어,
나주 혁신도시에서는 차로·횡단보도 위에 1990년대 승인 농축산 시설이 서 있는 것처럼 그려졌다. 도로명주소 건물 레이어는
현존하는 건물만 담아 이 구분이 된다(나주 혁신도시 표본: 2008년 이후 승인 건물 57/57동이 겹치고, 2008년 이전 승인 건물은 지구 안에서 18%만 겹침).

규칙: 건물 중심이 신도시 지구 안에 있고, 건물 면적의 min_cover(0.5) 이상이 도로명주소 건물과 겹치지 않으며,
사용승인이 recent_year(2015) 이전이거나 없으면 g=1.
- 지구 밖에는 쓰지 않는다: 구도심·농촌에서는 도로명주소가 없는 실제 건물(농가 부속 건물, 2008년 이전 공동주택 일부)도 겹치지 않는다(계양 구도심 19%).
- 사용승인이 2015년 이후인 건물은 도로명주소가 아직 없을 수 있어 건드리지 않는다.
- 도로명주소 건물을 받지 못했거나(0동), 최근 승인 건물(2008년 이후)의 겹침이 너무 낮으면(자료가 불완전하다는 뜻) 아무것도 붙이지 않는다.
시험: tests/test_regiontools_existence.py
"""
from __future__ import annotations

import math

from . import geo

LAYER = "LT_C_SPBD"
MIN_COVER = 0.5        # 건물 면적의 이 비율 이상이 도로명주소 건물과 겹치면 현존으로 본다
RECENT_YEAR = 2015     # 사용승인이 이 해 이후면 도로명주소가 아직 없을 수 있어 표시하지 않는다
SANITY_YEAR = 2008     # 이 해 이후 승인 건물은 지구 안에서도 현존한다고 보고 자료가 온전한지 가늠하는 표본으로 쓴다
SANITY_MIN_N = 10      # 표본이 이만큼 안 되면 가늠하지 않는다
SANITY_MIN_RATE = 0.6  # 표본의 겹침 비율이 이보다 낮으면 도로명주소 자료가 불완전하다고 보고 표시하지 않는다
CELL = 0.002           # 격자 색인 칸(도)
MAX_SAMPLES = 400      # 건물 하나에 찍는 점 수의 상한


def _bbox(geom: dict) -> tuple[float, float, float, float]:
    pts = list(geo.geometry_points(geom))
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


class Index:
    """도로명주소 건물을 격자로 색인한다(점이 어느 건물 안인지 빠르게 찾으려고)."""

    def __init__(self, geoms):
        self.items = []
        self.grid: dict = {}
        for g in geoms:
            if not g or not geo.polygons_of(g):
                continue
            b = _bbox(g)
            n = len(self.items)
            self.items.append((b, g))
            for i in range(math.floor(b[0] / CELL), math.floor(b[2] / CELL) + 1):
                for j in range(math.floor(b[1] / CELL), math.floor(b[3] / CELL) + 1):
                    self.grid.setdefault((i, j), []).append(n)

    def __len__(self) -> int:
        return len(self.items)

    def contains(self, pt) -> bool:
        x, y = pt
        for n in self.grid.get((math.floor(x / CELL), math.floor(y / CELL)), ()):
            b, g = self.items[n]
            if b[0] <= x <= b[2] and b[1] <= y <= b[3] and geo.point_in_geometry(pt, g):
                return True
        return False


def coverage(geom: dict, index: Index) -> float | None:
    """건물 안쪽에 격자로 찍은 점 가운데 도로명주소 건물 안에 든 비율. 점을 찍을 수 없으면 None."""
    x0, y0, x1, y1 = _bbox(geom)
    lat = (y0 + y1) / 2
    mx, my = 111320.0 * math.cos(math.radians(lat)), 110540.0
    step = max(1.0, math.sqrt(max((x1 - x0) * mx * (y1 - y0) * my, 1.0) / MAX_SAMPLES))   # m
    n = hit = 0
    x = x0
    while x <= x1:
        y = y0
        while y <= y1:
            if geo.point_in_geometry((x, y), geom):
                n += 1
                if index.contains((x, y)):
                    hit += 1
            y += step / my
        x += step / mx
    return hit / n if n else None


def annotate(features: list, spbd_geoms, zone_polys, *, min_cover: float = MIN_COVER, recent_year: int = RECENT_YEAR) -> dict:
    """features(번들 건물 피처)의 properties 에 g=1 을 붙이거나(이미 있던 g 는 먼저 지운다) 아무것도 붙이지 않고 이유를 돌려준다."""
    for f in features:
        f["properties"].pop("g", None)
    index = Index(spbd_geoms)
    stats = {"layer": LAYER, "spbd": len(index), "zoneBuildings": 0, "flagged": 0, "flaggedNoInfo": 0, "minCover": min_cover, "recentYear": recent_year}
    if not len(index):
        stats["skipped"] = "도로명주소 건물을 받지 못해 표시하지 않음"
        return stats
    inzone = []
    for f in features:
        c = geo.geometry_centroid(f["geometry"])
        if any(geo.point_in_ring(c, ring) for ring in zone_polys):
            cov = coverage(f["geometry"], index)
            if cov is not None:
                inzone.append((f, cov))
    stats["zoneBuildings"] = len(inzone)
    sample = [cov for f, cov in inzone if isinstance(f["properties"].get("a"), int) and f["properties"]["a"] >= SANITY_YEAR]
    stats["sanityN"] = len(sample)
    if len(sample) >= SANITY_MIN_N:
        rate = sum(1 for c in sample if c >= min_cover) / len(sample)
        stats["sanityRate"] = round(rate, 3)
        if rate < SANITY_MIN_RATE:
            stats["skipped"] = f"최근 승인 건물의 도로명주소 겹침이 {rate:.0%}로 낮아 자료가 불완전한 것으로 보고 표시하지 않음"
            return stats
    for f, cov in inzone:
        p = f["properties"]
        a = p.get("a")
        if cov < min_cover and not (isinstance(a, int) and a >= recent_year):
            p["g"] = 1
            stats["flagged"] += 1
            if p.get("src") == "정보없음":
                stats["flaggedNoInfo"] += 1
    return stats


TILE_DEG = 0.02   # V-World geomFilter 상자는 면적 10 km² 이내여야 한다(실측: 15.77 km² 는 INVALID_RANGE). 0.02° 칸은 약 4 km²


def tiles(bbox, step: float = TILE_DEG) -> list:
    """bbox(경도·위도 최소·최대)를 step 도 칸으로 나눈다."""
    x0, y0, x1, y1 = bbox
    out, x = [], x0
    while x < x1:
        y = y0
        while y < y1:
            out.append((round(x, 6), round(y, 6), round(min(x + step, x1), 6), round(min(y + step, y1), 6)))
            y += step
        x += step
    return out


def fetch_spbd(client, bbox) -> list:
    """bbox 안의 도로명주소 건물 지오메트리. 칸 경계에 걸친 건물이 두 번 오므로 건물관리번호로 한 번만 담는다."""
    out, seen = [], set()
    for t in tiles(bbox):
        for f in client.vworld_features(LAYER, bbox=t):
            key = (f.get("properties") or {}).get("bd_mgt_sn") or id(f)
            if key in seen or not f.get("geometry"):
                continue
            seen.add(key)
            out.append(f["geometry"])
    return out


def apply(client, features: list, zone_polys, zone_bbox, meta: dict | None = None) -> dict:
    """도로명주소 건물을 지구 범위(+약 200 m)로 받아 annotate 를 돌리고, 결과 요약을 meta.existence 에 남긴다.
    조회가 실패하면 아무것도 붙이지 않고 이유를 돌려준다(번들 만들기는 이어간다)."""
    from . import api

    bb = geo.expand_bbox(zone_bbox, 0.002)
    try:
        spbd = fetch_spbd(client, bb)
    except api.ApiError as e:
        for f in features:
            f["properties"].pop("g", None)
        stats = {"layer": LAYER, "skipped": f"도로명주소 건물 조회 실패({type(e).__name__})"}
    else:
        stats = annotate(features, spbd, zone_polys)
    if meta is not None:
        meta.pop("existence", None)
        if "skipped" not in stats:
            meta["existence"] = {"source": LAYER, "minCover": stats["minCover"], "recentYear": stats["recentYear"], "flagged": stats["flagged"]}
    return stats


def report(stats: dict) -> str:
    if "skipped" in stats:
        return f"- 현존 확인(도로명주소 건물): 표시 안 함 — {stats['skipped']}"
    return (f"- 현존 확인(도로명주소 건물 {stats['spbd']}동): 지구 안 건물 {stats['zoneBuildings']}동 중 {stats['flagged']}동 표시(g=1, 그중 정보없음 {stats['flaggedNoInfo']}동)"
            + (f", 최근 승인 건물 {stats['sanityN']}동의 겹침 {stats['sanityRate']:.0%}" if "sanityRate" in stats else ""))
