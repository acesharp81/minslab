#!/usr/bin/env python3
"""기존 번들(regions/<slug>/buildings.json)에 철거 잔존 의심 표시(g=1)를 붙이거나 갱신한다. 번들을 다시 만들지 않는다.
신도시 지구 안에서 도로명주소 건물(V-World LT_C_SPBD)과 겹치지 않는 옛 건물이 대상이다(규칙: existence.py, dataset.md 2.6).

  .venv/bin/python tools/regiontools/flag_existence.py regions/<slug> [--dry-run]

region.json 의 zones[].poly 를 지구로 쓴다. 키는 build_region 과 같다(.env.local 의 V-World 키). 번들을 다시 만들면 build_region 이 같은 일을 한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from regiontools import api, bundle, existence, geo  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="flag_existence", description="기존 번들 건물에 철거 잔존 의심 표시(g)를 붙인다.")
    ap.add_argument("region_dir", help="regions/<slug>")
    ap.add_argument("--env", default=str(ROOT / ".env.local"), help="키 파일(기본 저장소의 .env.local)")
    ap.add_argument("--cache-dir", default=None, help="응답 캐시 폴더(저장소 밖)")
    ap.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않고 결과만 본다")
    args = ap.parse_args(argv)
    d = Path(args.region_dir)
    try:
        region = json.loads((d / "region.json").read_text(encoding="utf-8"))
        bdoc = json.loads((d / "buildings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"오류: 번들을 읽지 못함 — {e}")
        return 2
    polys = [z["poly"] for z in region.get("zones") or [] if z.get("poly")]
    if not polys:
        print("오류: region.json 에 zones[].poly 가 없어 지구를 알 수 없음")
        return 2
    try:
        keys = api.load_keys(args.env)
    except api.MissingKey as e:
        print(f"오류: {e}. 키가 있을 때만 동작합니다.")
        return 2
    client = api.Client(keys, cache_dir=args.cache_dir)
    pts = [p for ring in polys for p in ring]
    stats = existence.apply(client, bdoc["features"], polys, geo.bbox_of(pts), bdoc.setdefault("meta", {}))
    print(f"# {d.name}\n{existence.report(stats)}")
    if "skipped" in stats and not any("g" in f["properties"] for f in bdoc["features"]) and "existence" not in bdoc["meta"]:
        print("- 표시를 붙이지 않았으므로 파일은 그대로 둡니다." if not args.dry_run else "- (dry-run)")
        return 0 if "조회 실패" not in stats["skipped"] else 1
    if args.dry_run:
        print("- (dry-run) 파일을 쓰지 않음")
        return 0
    bundle.write_json(d / "buildings.json", bdoc)
    print(f"- 씀: {d / 'buildings.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
