"""지역 폴더 하나를 검증한다."""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from .model import RegionResult
from .readers import read_csv, read_geojson_table
from .rules_domain import DOMAIN_CHECKS, check_cross
from .rules_rows import check_primary_key, check_refs, check_rows
from .spec import Spec

ENCODING_HINT = "UTF-8이 아님. 엑셀에서 'CSV UTF-8(쉼표로 분리)'로 다시 저장하세요"


def load_tables(res: RegionResult, spec: Spec) -> None:
    """파일을 읽고 E001 E002 W001을 낸다."""
    for name, fs in spec.files.items():
        path = res.path / name
        if not path.exists():
            if fs.required_file:
                res.add("E001", name, None, "필수 파일이 없음")
                res.rejected = True
            continue
        try:
            if fs.kind == "geojson":
                table, res.features = read_geojson_table(path, name, res.slug)
            else:
                table = read_csv(path, name)
        except UnicodeDecodeError:  # ValueError의 하위 클래스이므로 먼저 잡는다
            res.add("E002", name, None, ENCODING_HINT)
            res.rejected_files.add(name)
            continue
        except (ValueError, csv.Error) as e:
            res.add("E002", name, None, f"파일을 읽을 수 없음: {e}")
            res.rejected_files.add(name)
            continue
        if fs.kind == "csv":
            dup = sorted({h for h in table.header if table.header.count(h) > 1})
            missing = [c for c in fs.required_columns if c not in table.header]
            if dup or missing:
                parts = []
                if dup:
                    parts.append(f"중복된 열: {', '.join(dup)}")
                if missing:
                    parts.append(f"필수 열이 없음: {', '.join(missing)}")
                res.add("E002", name, None, "; ".join(parts))
                res.rejected_files.add(name)
                continue
        for h in table.header:
            if h not in fs.column_names:
                res.add("W001", name, None, f"정의되지 않은 열: {h}")
        res.tables[name] = table
    if "regions.csv" not in res.tables:
        res.rejected = True


def check_regions_file(res: RegionResult) -> None:
    """E003: regions.csv는 정확히 1행이고 region_slug가 폴더 이름과 같아야 한다."""
    rows = res.tables["regions.csv"].rows
    if len(rows) != 1:
        res.add("E003", "regions.csv", None, f"regions.csv는 정확히 1행이어야 함 (현재 {len(rows)}행)")
        res.rejected = True
    elif rows[0].get("region_slug") != res.slug:
        res.add("E003", "regions.csv", None,
                f"region_slug={rows[0].get('region_slug')!r}가 폴더 이름 {res.slug!r}와 다름")
        res.rejected = True


def validate_region(path: Path | str, spec: Spec, today: date, slug: str | None = None) -> RegionResult:
    res = RegionResult(slug=slug or Path(path).name, path=Path(path))
    load_tables(res, spec)
    if not res.rejected:
        check_regions_file(res)
    if res.rejected:
        return res
    for name in spec.order:  # 참조 대상 파일이 항상 앞에 온다
        table = res.tables.get(name)
        if table is None:
            continue
        fs = spec.files[name]
        check_rows(res, spec, fs, table)
        check_primary_key(res, fs)
        check_refs(res, fs)
        domain = DOMAIN_CHECKS.get(name)
        if domain:
            domain(res, spec, today)
        res.valid_keys[name] = {tuple(r.get(c) for c in fs.primary_key) for r in res.active_rows(name)}
    check_cross(res, spec, today)
    return res
