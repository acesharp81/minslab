"""Read models for the policy-status 3D thematic map.

These projections retain review and evidence semantics; they do not turn
recruitment notices into completed or occupied homes.
"""
from functools import lru_cache


def _polygons(geometry):
    if not geometry:
        return []
    kind = geometry.get("type")
    if kind == "Polygon":
        return [geometry.get("coordinates", [])]
    if kind == "MultiPolygon":
        return geometry.get("coordinates", [])
    if kind == "GeometryCollection":
        return [polygon for child in geometry.get("geometries", []) for polygon in _polygons(child)]
    return []


def _shape(geometry):
    polygons = _polygons(geometry)
    return {"type": "MultiPolygon", "coordinates": polygons} if polygons else None


def geometry_view(dashboard):
    """Return real admin/land shapes and explicitly classified block anchors."""
    municipalities = []
    regions = {"서울특별시": [], "인천광역시": [], "경기도": []}
    for row in dashboard["municipalities"]:
        shape = _shape(row.get("geometry"))
        if not shape:
            continue
        municipalities.append({"type": "Feature", "id": row["id"], "geometry": shape,
            "properties": {"id": row["id"], "name": row["name"], "region": row["region"],
                           "geometry_role": "OFFICIAL_ADMIN_BOUNDARY", "source_layer": row.get("source_layer"),
                           "base_date": row.get("base_date")}})
        if row["region"] in regions:
            regions[row["region"]].extend(shape["coordinates"])
    region_features = [{"type": "Feature", "id": region, "geometry": {"type": "MultiPolygon", "coordinates": polygons},
        "properties": {"id": region, "name": region, "geometry_role": "ADMIN_BOUNDARY_COMPOSITE",
                       "basis": "확보한 공식 시군구 경계의 결합 표시"}}
        for region, polygons in regions.items() if polygons]
    districts = []
    for row in dashboard["districts"]:
        shape = _shape(row.get("geometry"))
        if shape:
            districts.append({"type": "Feature", "id": row["id"], "geometry": shape,
                "properties": {"id": row["id"], "name": row["name"], "regions": row.get("regions", []),
                               "geometry_role": "OFFICIAL_HOUSING_LAND", "source_layer": row.get("source_layer"),
                               "base_date": row.get("base_date"), "link_status": row.get("link_status")}})
    blocks = [{"id": row["id"], "name": row["name"], "block": row["block"],
               "district_name": row["district_name"], "region": row["region"],
               "longitude": row.get("longitude"), "latitude": row.get("latitude"),
               "geometry_role": row.get("coordinate_basis"),
               "location_evidence_url": row.get("location_evidence_url")}
              for row in dashboard["blocks"]]
    return {"type": "PolicyGeoGeometry", "geometry_date": dashboard["knowledge_date"],
            "scope": ["서울특별시", "인천광역시", "경기도"], "out_of_scope": [],
            "regions": {"type": "FeatureCollection", "features": region_features},
            "municipalities": {"type": "FeatureCollection", "features": municipalities},
            "housing_lands": {"type": "FeatureCollection", "features": districts},
            "block_anchors": blocks,
            "geometry_note": "지구 도형은 LH 공동주택용지이며 법정 사업지구 경계가 아닙니다. 블록 점은 경계가 아닙니다."}


def _future(row):
    return [{"year": item["end_year"], "source_units": item.get("source_units"),
             "manual_units": item.get("manual_units"), "missing_events": item.get("units_missing_events", 0)}
            for item in row.get("future", [])]


def _quantity(row):
    progress = row.get("progress") or {}
    return {"target_units": row.get("target_units"), "project_count": row.get("project_count", 0),
            "target_missing_projects": row.get("target_missing_projects", 0),
            "current_notice_units": row.get("current_notice_units"),
            "current_notice_status": row.get("current_notice_status"),
            "actual_delivery_units": progress.get("actual_delivery_units"),
            "cumulative_goal_units": progress.get("cumulative_goal_units"),
            "early_count": progress.get("early_count", 0),
            "on_time_count": progress.get("on_time_count", 0),
            "late_count": progress.get("late_count", 0),
            "verification_count": progress.get("verification_count", 0),
            "future": _future(row)}


def _scoped(row):
    return {kind: {key: _quantity(value) for key, value in values.items()}
            for kind, values in row.get("group_quantities", {}).items() if kind in {"policy", "program"}}


def _source_events(item):
    """Original dated schedule evidence, with the year retained from annual buckets."""
    events = []
    for event in item.get("earlier_events", []):
        if event.get("origin") == "SOURCE":
            events.append({**event, "year": event.get("year") or int(event["month"][:4])})
    for annual in item.get("annual", []):
        for event in annual.get("events", []):
            if event.get("origin") == "SOURCE":
                events.append({**event, "year": event.get("year") or annual["year"]})
    return events


def _source_schedule(item):
    """Month-dated source milestones for exact as-of comparisons in the UI."""
    return [{"stage":event["stage"], "month":event["month"], "year":event["year"],
             "units":event.get("units"), "basis":event.get("basis"),
             "evidence_url":event.get("evidence_url")}
            for event in _source_events(item) if event.get("month")
            and event.get("stage") in {"SUPPLY", "CONSTRUCTION", "COMPLETION"}]


def _annual_series(group, item_lookup):
    """Known annual source schedules and linked notices, never actual move-ins."""
    years = {}
    for project_id in group.get("chart_schedule_ids", []):
        item = item_lookup.get(project_id)
        if not item:
            continue
        for event in _source_events(item):
            if event.get("units") is None:
                continue
            stage = event["stage"]
            slot = years.setdefault(event["year"], {})
            slot[stage] = slot.get(stage, 0) + event["units"]
    notices = set()
    for project_id in group.get("project_ids", []):
        notice = (item_lookup.get(project_id) or {}).get("notice_evidence")
        if not notice or not notice.get("source_date") or notice.get("units") is None or notice.get("id") in notices:
            continue
        notices.add(notice["id"])
        year = int(notice["source_date"][:4])
        slot = years.setdefault(year, {})
        slot["notice_units"] = slot.get("notice_units", 0) + notice["units"]
    return [{"year": year, **values} for year, values in sorted(years.items())]


def _program_link_groups(dashboard, item_lookup):
    """Keep reviewed program-link IDs distinct even when names are identical."""
    canonical_targets = {project_id for region in dashboard["groups"]["region"]
                         for project_id in region.get("chart_target_ids", [])}
    canonical_schedules = {project_id for region in dashboard["groups"]["region"]
                           for project_id in region.get("chart_schedule_ids", [])}
    grouped = {}
    for item in dashboard["items"]:
        mapping = item.get("mapping") or {}
        program_id = mapping.get("program_id")
        if not program_id:
            continue
        grouped.setdefault(program_id, []).append(item)
    results = []
    for program_id, members in sorted(grouped.items()):
        ids = [item["id"] for item in members]
        planned = [item["planned_units"] for item in members
                   if item["id"] in canonical_targets and item.get("planned_units") is not None]
        known_notices = {}
        for item in members:
            notice = item.get("notice_evidence") or {}
            if notice.get("id") and notice.get("units") is not None:
                known_notices[notice["id"]] = notice["units"]
        scheduled = [project_id for project_id in ids if project_id in canonical_schedules]
        annual = _annual_series({"project_ids": ids, "chart_schedule_ids": scheduled}, item_lookup)
        year = dashboard["analysis_year"]
        stage = dashboard["measure"]
        future = []
        for offset in range(1, 11):
            included = [point[stage] for point in annual
                        if year < point["year"] <= year + offset and point.get(stage) is not None]
            future.append({"year": year + offset, "source_units": sum(included) if included else None,
                           "manual_units": None, "missing_events": 0})
        policy_ids = {item.get("mapping", {}).get("policy_id") for item in members}
        policy_ids.discard(None)
        statuses = {item.get("mapping", {}).get("status") for item in members}
        name = (members[0].get("mapping") or {}).get("program_name") or members[0].get("program") or program_id
        results.append({"id": program_id, "name": name, "project_ids": ids,
                        "chart_target_ids": [project_id for project_id in ids if project_id in canonical_targets],
                        "chart_schedule_ids": scheduled, "annual_series": annual,
                        "policy_id": next(iter(policy_ids)) if len(policy_ids) == 1 else None,
                        "mapping_status": next(iter(statuses)) if len(statuses) == 1 else "REVIEW",
                        "target_units": sum(planned) if planned else None,
                        "project_count": len(ids), "target_missing_projects": sum(1 for item in members
                            if item["id"] in canonical_targets and item.get("planned_units") is None),
                        "current_notice_units": sum(known_notices.values()) if known_notices else None,
                        "current_notice_status": "REVIEW" if known_notices else "UNAVAILABLE",
                        "actual_delivery_units": None, "cumulative_goal_units": None,
                        "early_count": 0, "on_time_count": 0, "late_count": 0,
                        "verification_count": 0, "future": future})
    return results


def metrics_view(dashboard):
    """Compact, review-labelled values for the policy map's year controls."""
    item_lookup = {row["id"]: row for row in dashboard["items"]}
    return {"type": "PolicyGeoMetrics", "analysis_year": dashboard["analysis_year"],
            "knowledge_date": dashboard["knowledge_date"], "reference_date": dashboard["reference_date"],
            "start_year": dashboard["start_year"], "measure": dashboard["measure"],
            "measure_label": dashboard["measure_label"], "scope": ["서울특별시", "인천광역시", "경기도"],
            "groups": {**{kind: [dict(id=row["id"], name=row["name"], project_ids=row["project_ids"],
                                   by_scope=_scoped(row), annual_series=_annual_series(row, item_lookup),
                                   chart_target_ids=row.get("chart_target_ids", []),
                                   chart_schedule_ids=row.get("chart_schedule_ids", []), **_quantity(row)) for row in dashboard["groups"][kind]]
                       for kind in ("policy", "program", "region")},
                       "program_link": _program_link_groups(dashboard, item_lookup)},
            "municipalities": [dict(id=row["id"], name=row["name"], region=row["region"],
                                   longitude=row.get("longitude"), latitude=row.get("latitude"),
                                   project_ids=row["project_ids"], quantities=_quantity(row),
                                   by_scope=_scoped(row)) for row in dashboard["municipalities"]],
            "housing_lands": [dict(id=row["id"], name=row["name"], regions=row.get("regions", []),
                                   longitude=row.get("longitude"), latitude=row.get("latitude"),
                                   project_ids=row["project_ids"], quantities=row.get("quantities") and _quantity(row["quantities"]),
                                   by_scope=_scoped(row)) for row in dashboard["districts"]],
            "blocks": [dict(id=row["id"], name=row["name"], region=row["region"],
                            block=row["block"], district_name=row["district_name"],
                            longitude=row.get("longitude"), latitude=row.get("latitude"),
                            coordinate_basis=row.get("coordinate_basis"), project_ids=row["project_ids"],
                            quantities=_quantity(row), by_scope=_scoped(row)) for row in dashboard["blocks"]],
            "items": [{"id": row["id"], "name": row["name"], "region": row["region"],
                       "program": row.get("program"), "planned_units": row.get("planned_units"),
                       "current_notice_units": (row.get("notice_evidence") or {}).get("units"),
                       "notice_evidence_id": (row.get("notice_evidence") or {}).get("id"),
                       "notice_source_date": (row.get("notice_evidence") or {}).get("source_date"),
                       "annual_series": _annual_series({"chart_schedule_ids": [row["id"]], "project_ids": [row["id"]]}, item_lookup),
                       "schedule_events": _source_schedule(row),
                       "stage_label": row.get("stage_label"), "mapping": row.get("mapping"),
                       "move_in_start":row.get("move_in_start"),
                       "construction_progress":row.get("construction_progress"),
                       "evidence_url": row.get("evidence_url")}
                      for row in dashboard["items"]],
            "notice": dashboard["notice"]}


def schematic_view(dashboard):
    """Small official municipality outlines for the policy report only.

    Exterior rings are simplified for a diagram; the map is not a cadastral or
    street map. The full geometry endpoint remains available to other views.
    """
    def distance(point, start, end):
        x,y=point; ax,ay=start; bx,by=end
        dx,dy=bx-ax,by-ay
        if not dx and not dy:
            return (x-ax)**2+(y-ay)**2
        t=max(0,min(1,((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy)))
        return (x-ax-t*dx)**2+(y-ay-t*dy)**2

    def simplify(points,tolerance=.0025):
        if len(points)<5:
            return [[round(x,5),round(y,5)] for x,y in points]
        points=points[:-1] if points[0]==points[-1] else points
        def walk(first,last):
            if last-first<=1:return [first,last]
            middle=max(range(first+1,last),key=lambda i:distance(points[i],points[first],points[last]))
            if distance(points[middle],points[first],points[last])<=tolerance*tolerance:
                return [first,last]
            return walk(first,middle)[:-1]+walk(middle,last)
        kept=walk(0,len(points)-1)
        result=[[round(points[i][0],5),round(points[i][1],5)] for i in kept]
        if len(result)<3:return []
        result.append(result[0]);return result

    shapes=[]
    for row in dashboard["municipalities"]:
        polygons=_polygons(row.get("geometry"))
        outlines=[]
        for polygon in polygons:
            if not polygon or not polygon[0]:continue
            ring=simplify(polygon[0])
            if ring:outlines.append(ring)
        if outlines:
            shapes.append({"id":row["id"],"name":row["name"],"region":row["region"],
                           "rings":outlines,"longitude":row.get("longitude"),"latitude":row.get("latitude")})
    return {"type":"PolicySchematic","geometry_date":dashboard["knowledge_date"],
            "regions":["서울특별시","인천광역시","경기도"],"shapes":shapes,
            "note":"공식 시군구 경계를 화면용으로 단순화했습니다. 높이는 연결 사업계획 규모를 표현하며 실제 건물 높이가 아닙니다."}


@lru_cache(maxsize=12)
def _region_outline(engine, collection):
    """Geometry content is the cache key; a new boundary cannot reuse old output."""
    from sqlalchemy import text
    from pathlib import Path
    import os,json,hashlib,tempfile
    key=hashlib.sha256(('union-simplify-002-v1\n'+collection).encode()).hexdigest()
    folder=Path(os.environ.get('POC10_DATA_DIR',str(Path(__file__).resolve().parents[1]/'data')))/'runtime/region-outlines'
    cached=folder/(key+'.json')
    try:
        saved=json.loads(cached.read_text())
        shape=json.loads(saved['shape']);anchor=json.loads(saved['anchor'])
        if saved['key']==key and shape.get('type') in ('Polygon','MultiPolygon') and anchor.get('type')=='Point':
            return saved['shape'],saved['anchor']
    except (OSError,ValueError,KeyError,TypeError):pass
    with engine.connect() as conn:
        value = conn.execute(text("""WITH outline AS (
          SELECT ST_SimplifyPreserveTopology(ST_UnaryUnion(ST_CollectionExtract(
            ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(:value),4326)),3)),0.002) g)
          SELECT ST_AsGeoJSON(g) shape, ST_AsGeoJSON(ST_PointOnSurface(g)) anchor FROM outline"""),
          {'value': collection}).mappings().one()
    temporary=None
    try:
        folder.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w',dir=folder,delete=False) as output:
            temporary=output.name
            json.dump(dict(key=key,shape=value['shape'],anchor=value['anchor']),output)
        os.replace(temporary,cached);temporary=None
    except OSError:pass
    finally:
        if temporary:
            try:os.unlink(temporary)
            except OSError:pass
    return value['shape'], value['anchor']


def region_outlines(places, engine):
    """Dissolve official municipalities in PostGIS; preserve enclave holes."""
    if getattr(getattr(engine, 'dialect', None), 'name', None) != 'postgresql':
        return []
    import json
    result = []
    for region in ('서울특별시', '경기도', '인천광역시'):
        geoms = [p['geometry'] for p in places if p.get('region') == region and p.get('geometry')]
        if not geoms:
            continue
        # Database row order is not geography. A stable content key lets the
        # unchanged union survive restarts and unrelated source collections.
        geoms.sort(key=lambda g:json.dumps(g,sort_keys=True,separators=(',',':')))
        collection = json.dumps(dict(type='GeometryCollection', geometries=geoms),sort_keys=True,separators=(',',':'))
        shape, anchor = _region_outline(engine, collection)
        polygons = _polygons(json.loads(shape))
        point = json.loads(anchor)['coordinates']
        result.append(dict(id=region, name=region, region=region, aggregate=True,
            rings=[p[0] for p in polygons if p], holes=[p[1:] for p in polygons if p],
            longitude=point[0], latitude=point[1]))
    return result
