"""파일별·교차 규칙: E106 E107 W101~W106 I201 I202."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from .model import RegionResult, Row
from .spec import Spec
from .values import parse_date, parse_event_date

PLANNABLE = {"construction_start", "completion_inspection", "move_in"}


# ---------- events.csv ----------
def check_events(res: RegionResult, spec: Spec, today: date) -> None:
    f = "events.csv"
    for row in res.active_rows(f):
        event_type, text = row.get("event_type"), row.get("event_date")
        planned = row.get("is_planned") == "Y"
        d = parse_event_date(text)
        if planned and event_type not in PLANNABLE:
            res.add("E103", f, row.n, f"event_type={event_type!r}는 예정(is_planned=Y)을 허용하지 않음")
        if len(text) == 7 and event_type != "move_in":
            res.add("E102", f, row.n, f"event_date={text!r}: YYYY-MM은 move_in 사건에서만 허용")
        if not planned and d and d > today:
            res.add("E106", f, row.n, f"실제 사건의 날짜가 검증일({today})보다 미래: {text}")
        if event_type == "progress":
            value = row.get("value")
            if value == "":
                res.add("E107", f, row.n, "progress에는 value(공정율 0~100)가 필요함")
            elif not 0 <= float(value) <= 100:  # 형식 검사를 통과한 행이라 숫자다
                res.add("E107", f, row.n, f"공정율 value={value}가 0~100 밖")


# ---------- dongs.csv ----------
def _stale(res: RegionResult, file: str, row: Row, today: date) -> None:
    d = parse_date(row.get("observed_at"))
    if d and (today - d).days > 365:
        res.add("W106", file, row.n, f"observed_at={row.get('observed_at')}: 검증일로부터 365일 넘게 지남")


def check_dongs(res: RegionResult, spec: Spec, today: date) -> None:
    f = "dongs.csv"
    for row in res.active_rows(f):
        above, height = row.get("floors_above"), row.get("height_m")
        floors = int(above) if above != "" else None
        h = float(height) if height != "" else None
        use = row.get("dong_use")
        if floors == 0 and h is not None and h >= 10:
            res.add("W103", f, row.n,
                    f"floors_above=0인데 height_m={h:g}m: 지상·지하 층수가 뒤바뀌었는지 확인")
        elif floors is not None and floors >= 3 and h is not None and (use == "" or "공동주택" in use):
            ratio = h / floors
            if not 2.4 <= ratio <= 4.5:
                res.add("W102", f, row.n,
                        f"높이/지상층수={ratio:.2f}m로 2.4~4.5m 밖 (height_m={h:g}, floors_above={floors})")
        _stale(res, f, row, today)


# ---------- projects.csv ----------
def check_projects(res: RegionResult, spec: Spec, today: date) -> None:
    f = "projects.csv"
    for row in res.active_rows(f):
        if row.get("sponsor_type") == "unknown":
            res.add("W105", f, row.n, "sponsor_type=unknown: 시행자를 확인할 때까지 지도에서 제외됨")
        _stale(res, f, row, today)


# ---------- geometry_overrides.geojson ----------
GEO = "geometry_overrides.geojson"


def _geometry_error(geometry) -> str | None:
    """geometry가 Polygon/MultiPolygon이고 링이 닫혀 있으며 좌표가 한국 범위 안인지 본다."""
    if not isinstance(geometry, dict):
        return "geometry가 없음"
    kind, coords = geometry.get("type"), geometry.get("coordinates")
    if kind == "Polygon":
        polygons = [coords]
    elif kind == "MultiPolygon":
        polygons = coords
    else:
        return f"Polygon 또는 MultiPolygon이 아님: {kind}"
    try:
        for polygon in polygons:
            for ring in polygon:
                if len(ring) < 4:
                    return "링의 점이 4개 미만"
                if list(ring[0]) != list(ring[-1]):
                    return "링이 닫히지 않음(첫 점과 끝 점이 다름)"
                for point in ring:
                    lon, lat = float(point[0]), float(point[1])
                    if not (124 <= lon <= 132 and 33 <= lat <= 39):
                        return f"좌표가 한국 범위(경도 124~132, 위도 33~39) 밖: {lon}, {lat}"
    except (TypeError, ValueError, IndexError):
        return "coordinates 구조가 올바르지 않음"
    return None


def check_geometry(res: RegionResult, spec: Spec, today: date) -> None:
    for row in res.active_rows(GEO):
        feature = res.features[row.n - 1]
        error = _geometry_error(feature.get("geometry") if isinstance(feature, dict) else None)
        if error:
            res.add("E108", GEO, row.n, error)


DOMAIN_CHECKS = {
    "events.csv": check_events,
    "dongs.csv": check_dongs,
    "projects.csv": check_projects,
    GEO: check_geometry,
}


# ---------- 교차 규칙 ----------
def _earliest(rows: list[Row]):
    dated = [(parse_event_date(r.get("event_date")), r) for r in rows]
    dated = [(d, r) for d, r in dated if d]
    return min(dated, key=lambda x: x[0]) if dated else None


def _order_warnings(res: RegionResult, events: dict[str, list[Row]]) -> None:
    f = "events.csv"
    for pid, rows in events.items():
        actual: dict[str, list[Row]] = defaultdict(list)
        for r in rows:
            if r.get("is_planned") != "Y":
                actual[r.get("event_type")].append(r)
        # 변경허가는 준공 뒤에도 생기므로 '가장 이른 날짜'끼리만 비교한다
        for before, after in (("permit_approved", "construction_start"),
                              ("construction_start", "completion_inspection")):
            a, b = _earliest(actual[before]), _earliest(actual[after])
            if a and b and a[0] > b[0]:
                msg = f"{pid}: {before}({a[0]})가 {after}({b[0]})보다 늦음"
                res.add("W101", f, a[1].n, msg)
                res.add("W101", f, b[1].n, msg)
        progress = sorted(((parse_event_date(r.get("event_date")), r) for r in actual["progress"]
                           if parse_event_date(r.get("event_date"))), key=lambda x: x[0])
        for (d0, r0), (d1, r1) in zip(progress, progress[1:]):
            if float(r1.get("value")) < float(r0.get("value")):
                res.add("W101", f, r1.n,
                        f"{pid}: 공정율이 줄어듦 ({d0} {r0.get('value')} → {d1} {r1.get('value')})")


def _units_warnings(res: RegionResult, projects: dict[str, Row], events: dict[str, list[Row]]) -> None:
    for pid, p in projects.items():
        units = p.get("units")
        if units == "":
            continue
        permits = [(parse_event_date(r.get("event_date")), r) for r in events.get(pid, [])
                   if r.get("event_type") == "permit_approved" and r.get("is_planned") != "Y" and r.get("value") != ""]
        permits = [(d, r) for d, r in permits if d]
        if not permits:
            continue
        d, r = max(permits, key=lambda x: x[0])
        value = float(r.get("value"))
        if value > 0 and abs(int(units) - value) / value > 0.2:
            res.add("W104", "projects.csv", p.n,
                    f"units={units}가 가장 최근 permit_approved({d})의 value={r.get('value')}와 20% 넘게 다름")


def resolve_on_public_land(spec: Spec, row: Row, zone_type: dict[tuple[str, str], str]) -> str:
    """on_public_land 가 Y/N이면 그대로, 비었으면 소속 지구 유형으로 계산한다."""
    value = row.get("on_public_land")
    if value in ("Y", "N"):
        return value
    zone_id = row.get("zone_id")
    if zone_id:
        return "Y" if zone_type.get((row.get("region_slug"), zone_id)) in spec.public_land_zone_types else "N"
    return "unknown"


def _scope(res: RegionResult, spec: Spec, projects: dict[str, Row], zone_type: dict) -> None:
    counts = {"public": 0, "private_on_public_land": 0, "out_of_scope": 0, "unknown": 0}
    for pid, p in projects.items():
        sponsor = p.get("sponsor_type")
        if sponsor in ("public", "joint"):
            counts["public"] += 1
        elif sponsor == "unknown":
            counts["unknown"] += 1
        elif resolve_on_public_land(spec, p, zone_type) == "Y":
            counts["private_on_public_land"] += 1
        else:
            counts["out_of_scope"] += 1
            res.add("I201", "projects.csv", p.n, f"{pid}: 공공 시행이 아니고 공공택지 위도 아님 → 지도에서 제외")
    res.scope = counts


def _summary(res: RegionResult) -> None:
    parts = [f"{name.rsplit('.', 1)[0]} {len(res.active_rows(name))}"
             for name in ("zones.csv", "projects.csv", "events.csv", "dongs.csv", "sources.csv")
             if name in res.tables]
    res.add("I202", "", None, "정상 행 수: " + ", ".join(parts))


def check_cross(res: RegionResult, spec: Spec, today: date) -> None:
    zone_type = {(r.get("region_slug"), r.get("zone_id")): r.get("zone_type") for r in res.active_rows("zones.csv")}
    projects = {r.get("project_id"): r for r in res.active_rows("projects.csv")}
    events: dict[str, list[Row]] = defaultdict(list)
    for r in res.active_rows("events.csv"):
        events[r.get("project_id")].append(r)
    _order_warnings(res, events)
    _units_warnings(res, projects, events)
    _scope(res, spec, projects, zone_type)
    _summary(res)
