#!/usr/bin/env python3
"""지역 번들을 schemas/bundle/*.schema.json 으로 검증한다. 개발 전용: jsonschema 가 필요하다(.venv/bin/python).

  .venv/bin/python tools/regiontools/check_bundle.py regions           # index.json 과 모든 지역
  .venv/bin/python tools/regiontools/check_bundle.py regions/<slug>    # 지역 하나

JSON Schema 가 못 잡는 교차 규칙도 본다: 출처 id 존재, 단지 id 중복, projectOrder 참조, 기본 지역 하나, 폴더·slug 일치.
종료 코드: 0 = 오류 없음, 1 = 오류 있음, 2 = 사용법·경로 오류
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas" / "bundle"
REGION_FILES = {"region.json": "region", "projects.json": "projects", "buildings.json": "buildings", "context.json": "context",
                "infra.json": "infra"}
OPTIONAL_FILES = {"context.json", "infra.json"}
INFRA_SOURCE_LISTS = ("schools", "zones", "sites", "permits", "measures")   # 출처 id(sources)를 가진 목록
INFRA_ID_LISTS = ("schools", "zones", "sites", "permits", "measures")       # id 가 목록 안에서 하나뿐이어야 하는 목록


def _schema_errors(label: str, data, name: str) -> list[str]:
    from jsonschema import Draft202012Validator

    schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
    errors = []
    for e in sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path]):
        where = "/".join(str(p) for p in e.absolute_path) or "(최상위)"
        errors.append(f"{label}: {where}: {e.message[:200]}")
    return errors


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _semantic(region: dict, projects: dict) -> list[str]:
    errors = []
    source_ids = {s.get("id") for s in region.get("sources", []) if isinstance(s, dict)}
    seen: dict = {}
    for i, p in enumerate(projects.get("projects", [])):
        if not isinstance(p, dict):
            continue
        pid = p.get("id")
        if pid in seen:
            errors.append(f"projects.json: 단지 id 중복: {pid!r} (#{seen[pid]}, #{i})")
        else:
            seen[pid] = i
        for sid in p.get("sources") or []:
            if sid not in source_ids:
                errors.append(f"projects.json: 단지 {pid!r}의 출처 id {sid!r}가 region.json의 sources에 없음")
        progress = p.get("progress")
        if isinstance(progress, dict) and progress.get("source") and progress["source"] not in source_ids:
            errors.append(f"projects.json: 단지 {pid!r}의 progress.source {progress['source']!r}가 region.json의 sources에 없음")
    for pid in region.get("projectOrder") or []:
        if pid not in seen:
            errors.append(f"region.json: projectOrder의 {pid!r}가 projects.json에 없음")
    return errors


def _semantic_infra(infra: dict, projects: dict | None) -> list[str]:
    errors = []
    source_ids = {s.get("id") for s in infra.get("sources", []) if isinstance(s, dict)}
    for name in INFRA_ID_LISTS:
        seen: dict = {}
        for i, item in enumerate(infra.get(name, [])):
            if not isinstance(item, dict):
                continue
            iid = item.get("id")
            if iid in seen:
                errors.append(f"infra.json: {name} id 중복: {iid!r} (#{seen[iid]}, #{i})")
            else:
                seen[iid] = i
            if name in INFRA_SOURCE_LISTS:
                for sid in item.get("sources") or []:
                    if sid not in source_ids:
                        errors.append(f"infra.json: {name} {iid!r}의 출처 id {sid!r}가 infra.json의 sources에 없음")
    for sch in infra.get("schools", []):
        if not isinstance(sch, dict):
            continue
        if sch.get("status") == "신설예정" and not sch.get("openYm"):
            errors.append(f"infra.json: schools {sch.get('id')!r}는 신설예정인데 openYm(개교 예정 년월)이 없음")
        if sch.get("status") == "부지만" and sch.get("openYm"):
            errors.append(f"infra.json: schools {sch.get('id')!r}는 부지만인데 openYm이 있음(개교 일정이 공시됐다면 신설예정)")
    zone_ids = {z.get("id") for z in infra.get("zones", []) if isinstance(z, dict)}
    project_ids = {p.get("id") for p in (projects or {}).get("projects", []) if isinstance(p, dict)}
    for a in infra.get("attendance", []):
        if not isinstance(a, dict):
            continue
        if projects is not None and a.get("projectId") not in project_ids:
            errors.append(f"infra.json: attendance의 단지 id {a.get('projectId')!r}가 projects.json에 없음")
        if a.get("zoneId") not in zone_ids:
            errors.append(f"infra.json: attendance의 zoneId {a.get('zoneId')!r}가 zones에 없음")
    routes = [r for r in infra.get("busRoutes", []) if isinstance(r, dict)]
    route_ids: dict = {}
    for i, r in enumerate(routes):
        rid = r.get("id")
        if rid in route_ids:
            errors.append(f"infra.json: busRoutes id 중복: {rid!r} (#{route_ids[rid]}, #{i})")
        else:
            route_ids[rid] = i
        if r.get("live") and not r.get("path"):
            errors.append(f"infra.json: busRoutes {rid!r}는 live(실시간 위치를 부르는 노선)인데 path(경로)가 없음")
        if r.get("path") and not r.get("live"):
            errors.append(f"infra.json: busRoutes {rid!r}는 live가 아닌데 path가 있음(경로는 live 노선에만 싣는다)")
    if any(r.get("live") for r in routes) and not infra.get("busCityCode"):
        errors.append("infra.json: 실시간 노선(live)이 있는데 busCityCode(TAGO 도시코드)가 없음")
    stop_seen: dict = {}
    for i, s in enumerate(infra.get("stops", [])):
        if not isinstance(s, dict):
            continue
        sid = s.get("id")
        if sid is not None:
            if sid in stop_seen:
                errors.append(f"infra.json: stops id 중복: {sid!r} (#{stop_seen[sid]}, #{i})")
            else:
                stop_seen[sid] = i
        for rid in s.get("routes") or []:
            if rid not in route_ids:
                errors.append(f"infra.json: stops {sid or s.get('name')!r}의 노선 id {rid!r}가 busRoutes에 없음")
    return errors


def check_region_dir(path: Path | str) -> list[str]:
    path = Path(path)
    errors: list[str] = []
    data: dict = {}
    for fname, schema in REGION_FILES.items():
        f = path / fname
        if not f.exists():
            if fname not in OPTIONAL_FILES:
                errors.append(f"{path.name}/{fname}: 파일이 없음")
            continue
        try:
            data[fname] = _read_json(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            errors.append(f"{path.name}/{fname}: JSON을 읽을 수 없음: {e}")
            continue
        errors += _schema_errors(f"{path.name}/{fname}", data[fname], schema)
    region, projects = data.get("region.json"), data.get("projects.json")
    if isinstance(region, dict) and region.get("slug") != path.name:
        errors.append(f"region.json: slug {region.get('slug')!r}가 폴더 이름 {path.name!r}와 다름")
    if isinstance(region, dict) and isinstance(projects, dict):
        errors += _semantic(region, projects)
    infra = data.get("infra.json")
    if isinstance(infra, dict):
        errors += _semantic_infra(infra, projects if isinstance(projects, dict) else None)
    return errors


def check_index(path: Path | str) -> list[str]:
    path = Path(path)
    try:
        data = _read_json(path)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return [f"index.json: JSON을 읽을 수 없음: {e}"]
    errors = _schema_errors("index.json", data, "index")
    regions = [r for r in (data.get("regions", []) if isinstance(data, dict) else []) if isinstance(r, dict)]
    defaults = [r.get("slug") for r in regions if r.get("default")]
    if len(defaults) != 1:
        errors.append(f"index.json: default: true 인 지역이 정확히 하나여야 함 (현재 {len(defaults)}개: {defaults})")
    slugs = [r.get("slug") for r in regions]
    for slug in sorted({s for s in slugs if slugs.count(s) > 1}):
        errors.append(f"index.json: 지역 slug 중복: {slug!r}")
    for slug in slugs:
        if not (path.parent / str(slug) / "region.json").exists():
            errors.append(f"index.json: 지역 {slug!r}의 폴더(region.json)가 없음")
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="check_bundle", description="지역 번들을 스키마로 검증한다.")
    ap.add_argument("path", help="regions 폴더 또는 지역 폴더 하나")
    args = ap.parse_args(argv)
    p = Path(args.path)
    if not p.exists():
        print(f"오류: 경로가 없음: {p}")
        return 2
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        print("오류: jsonschema 가 필요함 — .venv/bin/python 으로 실행하세요")
        return 2
    errors: list[str] = []
    if (p / "index.json").exists():
        errors += check_index(p / "index.json")
        for d in sorted(x for x in p.iterdir() if x.is_dir() and (x / "region.json").exists()):
            errors += check_region_dir(d)
    elif (p / "region.json").exists():
        errors += check_region_dir(p)
    else:
        print("오류: index.json 도 region.json 도 없음")
        return 2
    for e in errors:
        print("오류:", e)
    print(f"검증 {'통과' if not errors else '실패'}: 오류 {len(errors)}건")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
