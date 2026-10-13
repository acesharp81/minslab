#!/usr/bin/env python3
"""옛 계양 운영 데이터(data/gyeyang_*.js)를 지역 번들(regions/incheon-gyeyang/*.json)로 옮긴다. 한 번 쓰는 이전 도구.

  python3 tools/regiontools/migrate_legacy.py --src data --out regions/incheon-gyeyang --index regions/index.json

옛 값은 그대로 두고 번들 모양에 맞춘다. 윤곽 등급은 옛 outlineHow 로 판정한다(공식 블록이면 official).
출처는 옛 단지별 src 문구를 그대로 살려 단지마다 하나씩 둔다.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

SLUG = "incheon-gyeyang"
NAME = "인천 계양구"
ZONE_ID = "techno-valley"
BUNDLE_VERSION = "1.1.0"
STATUS_ORDER = ["계획", "분양중", "건설 단계", "준공 임박", "입주 단계"]
LEGACY_ORDER = ["A6", "A17", "A9", "A10", "A2", "A3"]   # 옛 app.js 의 ORDER(분양중 → 건설 단계 → 준공 임박)
VIEW = {"center": [126.7585, 37.5515], "zoom": 14.4, "pitch": 52, "bearing": 0}   # 옛 app.js 의 START
SPONSOR = {"name": "한국토지주택공사", "type": "public"}
PROGRESS_SOURCE = "lh-cwstt"


def read_legacy_js(path: Path | str, var: str):
    text = Path(path).read_text(encoding="utf-8")
    marker = f"window.{var}="
    at = text.find(marker)
    if at < 0:
        raise ValueError(f"{path}: window.{var}= 를 찾을 수 없음")
    body = text[at + len(marker):].rstrip()
    if body.endswith(";"):
        body = body[:-1]
    return json.loads(body)


def move_in(value):
    """옛 입주 표기 → 번들 moveIn. '2026.12' → '2026-12', '준공 예정 2028-09-30' → '2028-09-30', 없으면 None."""
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    m = re.fullmatch(r"(\d{4})\.(\d{2})", v)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.fullmatch(r"준공 예정\s*(\d{4}-\d{2}-\d{2})", v)
    if m:
        return m.group(1)
    return v


def _tier_of(how: str | None) -> str:
    return "official" if how and "V-World 공식" in how else "schematic"


def _project(b: dict) -> dict:
    label = b["id"]
    p = {
        "id": f"techno-{label}", "zoneId": ZONE_ID, "label": label, "name": f"인천계양 테크노밸리 {label} 블록",
        "sponsor": dict(SPONSOR), "sponsorClass": "public", "kind": b["kind"], "status": b["status"],
        "units": b.get("units"), "dongCount": b.get("dongCount"), "moveIn": move_in(b.get("moveIn")),
        "outline": {"tier": _tier_of(b.get("outlineHow")), "poly": b["poly"]},
        "sources": [f"notice-{label.lower()}"],
    }
    if b.get("outlineHow"):
        p["outline"]["how"] = b["outlineHow"]
    pr = b.get("progress")
    if pr:
        p["progress"] = {"rate": pr["rate"], "asOf": pr["asOf"], "history": pr.get("history", []), "source": PROGRESS_SOURCE}
        for k in ("start", "end"):
            if pr.get(k):
                p["progress"][k] = pr[k]
    dongs = [{"no": d["no"], "floorsAbove": d["floors"], "tier": "schematic", "poly": d["poly"]} for d in b.get("dongs") or []]
    if dongs:
        p["dongs"] = dongs
    if b.get("builder"):
        p["builder"] = b["builder"]
    if b.get("contractM") is not None:
        p["contractAmountM"] = b["contractM"]
    if b.get("note"):
        p["note"] = b["note"]
    return p


def convert(projects: dict, buildings: dict, context: dict) -> dict:
    """옛 세 전역 값 → {region, projects, buildings, context}. 입력은 바꾸지 않는다."""
    projects, buildings, context = copy.deepcopy(projects), copy.deepcopy(buildings), copy.deepcopy(context)
    blocks = projects.get("blocks", [])
    out_projects = [_project(b) for b in blocks]
    sources = [{"id": f"notice-{b['id'].lower()}", "label": b["src"], "publisher": "한국토지주택공사", "redistributable": "unknown"} for b in blocks if b.get("src")]
    sources.append({"id": PROGRESS_SOURCE, "label": "LH청약플러스 공사현황", "publisher": "한국토지주택공사", "redistributable": "unknown"})
    district = projects.get("district") or {}
    zone = {"id": ZONE_ID, "name": "인천계양 테크노밸리 지구", "type": "공공주택지구", "publicLand": True}
    if district.get("poly"):
        zone["poly"] = district["poly"]
    if district.get("source"):
        sources.append({"id": "osm-district", "label": district["source"], "license": "ODbL", "redistributable": "Y"})
    ids = {p["id"] for p in out_projects}
    region = {
        "schema_version": BUNDLE_VERSION, "slug": SLUG, "name": NAME, "title": "주택파동 · 인천 계양구",
        "description": "인천 계양 테크노밸리 공공주택 공급 현황을 V-World 공식 건물 위에 3차원으로 보여 주는 지도",
        "updatedAt": (projects.get("meta") or {}).get("asOf") or context.get("asOf"),
        "view": dict(VIEW), "codes": [{"code": "28245", "type": "sigungu", "name": "계양구"}],
        "zones": [zone], "sources": sources, "statusOrder": list(STATUS_ORDER),
        "projectOrder": [f"techno-{x}" for x in LEGACY_ORDER if f"techno-{x}" in ids],
    }
    buildings["schema_version"] = BUNDLE_VERSION
    return {
        "region": region,
        "projects": {"schema_version": BUNDLE_VERSION, "projects": out_projects, "otherBlocks": projects.get("otherBlocks", [])},
        "buildings": buildings, "context": context,
    }


def _dump(path: Path, obj, indent=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    kw = {"indent": indent} if indent else {"separators": (",", ":")}
    path.write_text(json.dumps(obj, ensure_ascii=False, **kw) + "\n", encoding="utf-8")


def add_to_index(path: Path | str, *, slug: str, name: str, updated_at: str, default: bool = False, visibility: str = "public") -> None:
    path = Path(path)
    idx = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"schema_version": BUNDLE_VERSION, "regions": []}
    entry = {"slug": slug, "name": name, "visibility": visibility, "updatedAt": updated_at, "schema_version": BUNDLE_VERSION}
    if default:
        entry = {"slug": slug, "name": name, "default": True, "visibility": visibility, "updatedAt": updated_at, "schema_version": BUNDLE_VERSION}
    regions = idx["regions"]
    for i, r in enumerate(regions):
        if r["slug"] == slug:
            regions[i] = entry
            break
    else:
        regions.append(entry)
    if default:
        for r in regions:
            if r["slug"] != slug:
                r.pop("default", None)
    _dump(path, idx, indent=2)


def migrate(src: Path | str, out: Path | str) -> dict:
    src, out = Path(src), Path(out)
    bundle = convert(
        read_legacy_js(src / "gyeyang_projects.js", "GY_PROJECTS"),
        read_legacy_js(src / "gyeyang_buildings.js", "GY_BUILDINGS"),
        read_legacy_js(src / "gyeyang_context.js", "GY_CONTEXT"),
    )
    for name in ("region", "projects", "buildings", "context"):
        _dump(out / f"{name}.json", bundle[name])
    return bundle


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", default="data", help="옛 data/ 폴더")
    ap.add_argument("--out", default=f"regions/{SLUG}", help="번들을 쓸 폴더")
    ap.add_argument("--index", help="지정하면 이 index.json 에 지역을 올린다(계양을 기본 지역으로)")
    a = ap.parse_args(argv)
    try:
        bundle = migrate(a.src, a.out)
        if a.index:
            add_to_index(a.index, slug=SLUG, name=NAME, updated_at=bundle["region"]["updatedAt"], default=True)
    except (OSError, ValueError, KeyError) as e:
        print(f"이전 실패: {e}", file=sys.stderr)
        return 1
    print(f"이전 완료: {len(bundle['projects']['projects'])}개 단지, 건물 {len(bundle['buildings']['features'])}동 → {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
