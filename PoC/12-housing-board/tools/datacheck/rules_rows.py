"""행 수준 규칙: E101 필수값, E102 형식, E103 열거형, E104 기본키 중복, E105 참조."""
from __future__ import annotations

from .model import RegionResult, Table
from .spec import FileSpec, Spec
from .values import check_value


def check_rows(res: RegionResult, spec: Spec, fs: FileSpec, table: Table) -> None:
    for row in table.rows:
        for col in fs.columns:
            value = row.get(col.name)
            if value == "":
                if col.required:
                    res.add("E101", fs.name, row.n, f"필수 값이 비어 있음: {col.name}")
                continue
            problem = check_value(col, value, spec.enums)
            if problem:
                res.add(problem[0], fs.name, row.n, f"{col.name}={value!r}: {problem[1]}")


def check_primary_key(res: RegionResult, fs: FileSpec) -> None:
    first_seen: dict[tuple, int] = {}
    for row in res.active_rows(fs.name):  # 이미 다른 오류로 격리된 행은 건너뛴다
        key = tuple(row.get(c) for c in fs.primary_key)
        if key in first_seen:
            res.add("E104", fs.name, row.n,
                    f"기본키 중복: {dict(zip(fs.primary_key, key))} (첫 행 {first_seen[key]})")
        else:
            first_seen[key] = row.n


def check_refs(res: RegionResult, fs: FileSpec) -> None:
    for ref in fs.refs:
        if ref.to in res.rejected_files or ref.to not in res.tables:
            continue  # 참조 대상 파일이 없거나 거부됨: 연쇄 오류를 만들지 않는다
        valid = res.valid_keys.get(ref.to, set())
        for row in res.active_rows(fs.name):
            if ref.optional_column and row.get(ref.optional_column) == "":
                continue
            key = tuple(row.get(c) for c in ref.columns)
            if key not in valid:
                res.add("E105", fs.name, row.n,
                        f"참조 대상이 없거나 격리됨: {dict(zip(ref.columns, key))} → {ref.to}")
