"""건물 레이어(V-World LT_C_BLDGINFO) → 번들 buildings.json 피처.

높이 규칙(번들-어댑터-정의서 3.4): 공식 높이 h>0 → eh=h(공식높이), 아니면 지상층수 f → eh=f×층고(층수환산),
둘 다 없으면 eh=3(정보없음). V-World는 모르는 값을 "0"·""로 주므로 0은 모르는 값으로 본다(정의서 9절 함정 7).
"""
from __future__ import annotations

import statistics

from . import geo

DEFAULT_FLOOR_M = 2.85   # 화면 기본 층고(meta.factor에 키가 없을 때)
NO_INFO_M = 3.0          # 높이·층수가 모두 없을 때의 평면 높이
FACTOR_MIN_SAMPLES = 30

# 건축물 주용도 코드 → 이름. 코드는 건축법 시행령 별표1의 번호×1000이다.
# 01·02·03·04·18·19·20은 건축HUB 응답의 코드·이름 쌍(purpsCd/mainPurpsCd)으로 확인했고,
# 나머지는 같은 번호 체계로 채웠다. 22번 이후와 Z로 시작하는 코드는 확인하지 못해 넣지 않는다(→ u 생략).
USE_NAMES = {
    "01000": "단독주택", "02000": "공동주택", "03000": "제1종근린생활시설", "04000": "제2종근린생활시설",
    "05000": "문화및집회시설", "06000": "종교시설", "07000": "판매시설", "08000": "운수시설", "09000": "의료시설",
    "10000": "교육연구시설", "11000": "노유자시설", "12000": "수련시설", "13000": "운동시설", "14000": "업무시설",
    "15000": "숙박시설", "16000": "위락시설", "17000": "공장", "18000": "창고시설", "19000": "위험물저장및처리시설",
    "20000": "자동차관련시설", "21000": "동.식물 관련시설",
}


def to_pos_int(v) -> int | None:
    try:
        n = int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def to_pos_float(v) -> float | None:
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return x if x > 0 else None


def floor_band(f: int) -> str:
    if f <= 5:
        return "1-5"
    if f <= 10:
        return "6-10"
    if f <= 15:
        return "11-15"
    if f <= 20:
        return "16-20"
    return "21+"


def floor_height(f: int, use: str | None = None, factor: dict | None = None) -> float:
    factor = factor or {}
    if use and use != "공동주택" and use in factor:
        return factor[use]
    return factor.get(f"공동주택_{floor_band(f)}", DEFAULT_FLOOR_M)


def effective_height(h: float | None, f: int | None, use: str | None = None, factor: dict | None = None):
    """(eh, src)."""
    if h and h > 0:
        return round(h, 2), "공식높이"
    if f and f > 0:
        return round(f * floor_height(f, use, factor), 1), "층수환산"
    return NO_INFO_M, "정보없음"


def mismatch_flag(h: float | None, f: int | None) -> int | None:
    """높이/지상층수가 1.8~6.0 m를 크게 벗어나면 1. 1층 건물(창고·공장의 높은 층고)은 판정하지 않는다."""
    if not h or not f or f < 2:
        return None
    r = h / f
    return 1 if (r < 1.8 or r > 6.0) else None


def compute_factor(rows: list[dict], min_samples: int = FACTOR_MIN_SAMPLES) -> dict:
    """같은 지역 건물의 높이÷지상층수 중앙값. 공동주택은 층수 구간별, 그 밖은 용도별. 표본 부족 키는 뺀다.

    rows: {"h": 높이, "f": 지상층수, "u": 용도 이름(없으면 None)}
    """
    groups: dict[str, list[float]] = {}
    for r in rows:
        h, f, u = r.get("h"), r.get("f"), r.get("u")
        if not h or not f or mismatch_flag(h, f):
            continue
        if u == "공동주택":
            key = f"공동주택_{floor_band(f)}"
        elif u:
            key = u
        else:
            continue
        groups.setdefault(key, []).append(h / f)
    return {k: round(statistics.median(v), 2) for k, v in sorted(groups.items()) if len(v) >= min_samples}


def use_name(code) -> str | None:
    return USE_NAMES.get(str(code or "").strip())


def raw_values(props: dict) -> dict:
    """V-World 속성에서 의미 있는 값만(0·빈 값은 None)."""
    return {
        "h": to_pos_float(props.get("height")),
        "f": to_pos_int(props.get("grnd_flr")),
        "b": to_pos_int(props.get("ugrnd_flr")),
        "u": use_name(props.get("usability")),
    }


def building_props(props: dict, factor: dict, d: str | None = None) -> dict:
    v = raw_values(props)
    h, f, u = v["h"], v["f"], v["u"]
    eh, src = effective_height(h, f, u, factor)
    out: dict = {"eh": eh, "src": src}
    if h:
        out["h"] = round(h, 2)
    if f:
        out["f"] = f
    if v["b"]:
        out["b"] = v["b"]
    if u:
        out["u"] = u
    name = " ".join(s for s in (str(props.get("bld_nm") or "").strip(), str(props.get("dong_nm") or "").strip()) if s)
    if name:
        out["n"] = name
    day = str(props.get("useapr_day") or "").strip()
    if len(day) >= 4 and day[:4].isdigit() and 1900 <= int(day[:4]) <= 2100:
        out["a"] = int(day[:4])
    if d:
        out["d"] = d
    x = mismatch_flag(h, f)
    if x:
        out["x"] = x
    return out


def clean_geometry(geom: dict) -> dict | None:
    """좌표 6자리, 닫힌 링(GeoJSON). 퇴화한 링은 버린다. 남는 것이 없으면 None."""
    polys = []
    for poly in geo.polygons_of(geom):
        rings = [geo.clean_ring(r, closed=True) for r in poly]
        if not rings or rings[0] is None:
            continue
        polys.append([rings[0]] + [r for r in rings[1:] if r is not None])
    if not polys:
        return None
    if geom.get("type") == "Polygon":
        return {"type": "Polygon", "coordinates": polys[0]}
    return {"type": "MultiPolygon", "coordinates": polys}


def building_feature(geom: dict, props: dict) -> dict | None:
    g = clean_geometry(geom)
    if g is None:
        return None
    return {"type": "Feature", "properties": props, "geometry": g}


def make_meta(basis: str, factor: dict, **extra) -> dict:
    meta = {"basis": basis}
    if factor:
        meta["factor"] = dict(factor)
    meta.update({k: v for k, v in extra.items() if v is not None})
    return meta
