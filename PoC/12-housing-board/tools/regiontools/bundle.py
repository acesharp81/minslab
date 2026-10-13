"""번들 4개 파일(region·projects·buildings·context) 조립과 쓰기.

UTF-8(BOM 없음), ensure_ascii=False, 공백 없는 compact JSON, 좌표 소수 6자리. 모르는 값(None)은 키를 뺀다.
"""
from __future__ import annotations

import json
from pathlib import Path

from .status import STATUS_ORDER

SCHEMA_VERSION = "1.1.0"
ND = 6


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def round_coords(obj, nd: int = ND):
    """좌표 배열(중첩 리스트) 안의 실수를 nd자리로 반올림."""
    if isinstance(obj, (list, tuple)):
        return [round_coords(x, nd) for x in obj]
    if isinstance(obj, float):
        return round(obj, nd)
    return obj


def strip_none(obj):
    """dict에서 값이 None인 키를 재귀적으로 뺀다(리스트 안의 dict 포함)."""
    if isinstance(obj, dict):
        return {k: strip_none(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [strip_none(x) for x in obj]
    return obj


def region_doc(*, slug, name, title, description, center, zoom, codes, zones, sources, updated,
               pitch=None, bearing=0, project_order=None) -> dict:
    view = {"center": round_coords([float(center[0]), float(center[1])]), "zoom": zoom}
    if pitch is not None:
        view["pitch"] = pitch
    if bearing is not None:
        view["bearing"] = bearing
    zs = []
    for z in zones:
        z = dict(z)
        if z.get("poly") is not None:
            z["poly"] = round_coords(z["poly"])
        zs.append(z)
    doc = {
        "schema_version": SCHEMA_VERSION, "slug": slug, "name": name, "title": title,
        "description": description or None, "updatedAt": updated, "view": view,
        "codes": codes, "zones": zs, "sources": sources, "statusOrder": list(STATUS_ORDER),
        "projectOrder": project_order or None,
    }
    return strip_none(doc)


def _project(p: dict) -> dict:
    p = strip_none(p)
    if "outline" in p:
        p["outline"]["poly"] = round_coords(p["outline"]["poly"])
    for d in p.get("dongs", []):
        d["poly"] = round_coords(d["poly"])
    return p


def projects_doc(projects: list[dict], other_blocks: list) -> dict:
    doc = {"schema_version": SCHEMA_VERSION, "projects": [_project(p) for p in projects]}
    if other_blocks:
        doc["otherBlocks"] = round_coords(other_blocks)
    return doc


def buildings_doc(features: list[dict], meta: dict) -> dict:
    feats = []
    for f in features:
        g = dict(f["geometry"])
        g["coordinates"] = round_coords(g["coordinates"])
        feats.append({"type": "Feature", "properties": strip_none(f["properties"]), "geometry": g})
    return {"type": "FeatureCollection", "schema_version": SCHEMA_VERSION, "meta": meta, "features": feats}


def context_doc(stations: list[dict], schools: list[dict], as_of: str, source: str) -> dict:
    def places(xs):
        return [{"name": x["name"], "lon": round(float(x["lon"]), ND), "lat": round(float(x["lat"]), ND)} for x in xs]
    return {"schema_version": SCHEMA_VERSION, "stations": places(stations), "schools": places(schools),
            "asOf": as_of, "source": source}


def write_json(path: Path, obj) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(obj) + "\n", encoding="utf-8")
    return path


def write_bundle(out_dir, region: dict, projects: dict, buildings: dict, context: dict | None = None) -> list[Path]:
    """지역 폴더에 번들을 쓴다. context가 None이면 context.json은 쓰지 않는다(기존 파일은 건드리지 않음)."""
    out = Path(out_dir)
    written = [write_json(out / "region.json", region), write_json(out / "projects.json", projects),
               write_json(out / "buildings.json", buildings)]
    if context is not None:
        written.append(write_json(out / "context.json", context))
    return written
