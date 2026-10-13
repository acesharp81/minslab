"""입력 규격 명세(schemas/input.spec.json)를 읽는다. 검증기와 문서 생성기가 함께 쓴다."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SPEC_PATH = Path(__file__).resolve().parents[2] / "schemas" / "input.spec.json"
COLUMN_TYPES = {"text", "slug", "int", "number", "date", "date_or_month", "yn", "enum",
                "pnu_list", "url", "code", "lon", "lat"}


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    required: bool
    desc: str
    enum: str | None = None
    min: float | None = None
    max: float | None = None


@dataclass(frozen=True)
class Ref:
    columns: tuple[str, ...]
    to: str
    to_columns: tuple[str, ...]
    optional_column: str | None = None  # 이 열이 비어 있으면 참조를 검사하지 않는다


@dataclass(frozen=True)
class FileSpec:
    name: str
    kind: str  # "csv" | "geojson"
    required_file: bool
    description: str
    primary_key: tuple[str, ...]
    columns: tuple[Column, ...]
    refs: tuple[Ref, ...]

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    @property
    def required_columns(self) -> list[str]:
        return [c.name for c in self.columns if c.required]


@dataclass(frozen=True)
class Spec:
    schema_version: str
    enums: dict[str, tuple[str, ...]]
    public_land_zone_types: tuple[str, ...]
    files: dict[str, FileSpec]

    @property
    def order(self) -> list[str]:
        """검증 순서. 참조 대상 파일이 항상 앞에 온다."""
        return list(self.files)


def load_spec(path: Path | str = SPEC_PATH) -> Spec:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    enums = {k: tuple(v) for k, v in raw["enums"].items()}
    files: dict[str, FileSpec] = {}
    for name, f in raw["files"].items():
        columns = tuple(
            Column(name=c["name"], type=c["type"], required=c.get("required", False), desc=c["desc"],
                   enum=c.get("enum"), min=c.get("min"), max=c.get("max"))
            for c in f["columns"]
        )
        for c in columns:
            if c.type not in COLUMN_TYPES:
                raise ValueError(f"{name}.{c.name}: 알 수 없는 열 형식 {c.type}")
            if c.type == "enum" and c.enum not in enums:
                raise ValueError(f"{name}.{c.name}: 정의되지 않은 열거형 {c.enum}")
        refs = tuple(
            Ref(columns=tuple(r["columns"]), to=r["to"], to_columns=tuple(r["to_columns"]),
                optional_column=r.get("optional_column"))
            for r in f.get("refs", [])
        )
        files[name] = FileSpec(
            name=name, kind=f.get("kind", "csv"), required_file=f.get("required_file", False),
            description=f["description"], primary_key=tuple(f["primary_key"]), columns=columns, refs=refs,
        )
    return Spec(
        schema_version=raw["schema_version"], enums=enums,
        public_land_zone_types=tuple(raw["public_land_zone_types"]), files=files,
    )
