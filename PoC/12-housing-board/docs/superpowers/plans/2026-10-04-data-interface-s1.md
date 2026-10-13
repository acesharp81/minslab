# 데이터 인터페이스 정의서·스키마·검증기 (S1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 팀원이 넘길 입력 데이터(CSV·GeoJSON)의 규격을 정의서·명세 파일·템플릿·예시로 만들고, 제출물을 같은 규칙으로 검증해 오류를 되돌려 주는 검증기를 만든다.

**Architecture:** `schemas/input.spec.json` 하나가 입력 규격의 유일한 원천이다. 검증기(`tools/datacheck/` 패키지, 표준 라이브러리만 사용)와 문서 생성기(`tools/gen_docs.py`)가 모두 이 파일을 읽는다. 검증기는 지역 폴더 하나를 읽어 파일 수준 → 행 수준(형식·열거형·기본키·참조) → 파일별 규칙 → 교차 규칙 순으로 검사하고, error 행은 격리한다.

**Tech Stack:** Python 3.14 표준 라이브러리(`csv`, `json`, `zipfile`, `datetime`, `argparse`, `unittest`). 문서 PDF 생성에만 `markdown` 패키지(개발 전용, `.venv`)와 Chrome 헤드리스.

**Spec:** `docs/superpowers/specs/2026-10-04-data-interface-s1-design.md` (이 계획서보다 먼저 읽을 것. 규칙 ID·열 정의·상태 계산 규칙의 정본이다.)

## Global Constraints

- 검증기와 테스트는 **표준 라이브러리만** 쓴다. `markdown` 패키지는 `tools/build_docs_pdf.py`에서만 쓴다.
- 인코딩은 UTF-8(BOM 허용). CSV는 RFC 4180, 첫 줄은 영문 snake_case 헤더.
- 날짜는 `YYYY-MM-DD`. `move_in` 사건에 한해 `YYYY-MM`도 허용.
- 좌표는 WGS84(EPSG:4326), GeoJSON은 `[경도, 위도]`. 한국 범위는 경도 124~132, 위도 33~39.
- **미상은 빈 칸, 0은 실제 0.**
- 공공택지로 치는 `zone_type`은 `택지개발` `공공주택지구` `혁신도시` `신도시` 네 가지뿐이다.
- 상태는 `계획` `분양중` `건설 단계` `준공 임박` `입주 단계` 다섯 가지이고 입력 열로 받지 않는다(계산은 컴파일러 B의 몫이며 이 계획 범위 밖).
- 검증 규칙 ID: `E001 E002 E003 E101 E102 E103 E104 E105 E106 E107 E108 W001 W101 W102 W103 W104 W105 W106 I201 I202`. error는 행 격리, warn은 표시만, info는 목록만.
- 종료 코드: 0 = error 없음, 1 = error 있음(또는 `--strict`에서 warn 있음), 2 = 사용법·파일 열기 오류.
- 행 번호는 헤더를 뺀 데이터 행의 순번(스프레드시트에서는 번호 + 1행).
- 입력 규격의 필수 파일은 `regions.csv` `region_codes.csv` `sources.csv` `zones.csv` `projects.csv` `events.csv`, 선택 파일은 `dongs.csv` `geometry_overrides.geojson`.
- 커밋 메시지 끝에는 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` 줄을 붙인다(`git commit -m "<제목>" -m "<trailer>"`).
- 테스트 실행: 저장소 루트에서 `python3 -m unittest discover -s tests -v`. 한 파일만: `python3 -m unittest discover -s tests -p "test_files.py" -v`.
- 작업 트리에는 이 계획과 무관한 `.gitignore` 변경(`.vercel`, `.env*`)이 이미 있다. `.gitignore`는 Task 11에서만 건드리고 그때 함께 커밋한다. 다른 작업에서는 `git add`에 파일 경로를 하나씩 명시한다.

## Review Focus

스펙이 암시하지만 개별 테스트가 따로 겨냥하지 않으면 놓치기 쉬운 입력들이다. 각 줄의 테스트는 해당 코드를 만드는 작업에 들어 있다.

1. **윈도우 엑셀이 cp949로 저장한 CSV.** 기대: 깨진 글자를 읽으려 하지 말고 E002와 "UTF-8로 다시 저장" 안내를 낸다. (Task 2)
2. **엑셀이 만든 CSV의 잡음**: BOM, CRLF, 끝의 빈 줄, 쉼표가 든 따옴표 값. 기대: 정상 행 1개로 읽힌다. (Task 2)
3. **헤더만 있는 파일, 행이 0개인 필수 표.** 기대: 오류 없이 통과하고 요약 건수가 0으로 나온다. (Task 2, Task 4)
4. **macOS가 만든 ZIP**(`__MACOSX/`, `.DS_Store`, 최상위 폴더 하나)과 `../` 경로가 든 악성 ZIP. 기대: 잡음은 무시하고, 악성 경로는 푸는 것을 거부(종료 코드 2). (Task 6)
5. **한 제출에 지역이 둘이고 한 곳이 깨진 경우.** 기대: 깨진 지역만 거부되고 나머지는 정상 검증·리포트된다. (Task 6)

---

## File Structure

```
schemas/input.spec.json              입력 규격의 단일 원천 (Task 1)
schemas/bundle/*.schema.json         출력 번들 JSON Schema 5개 (Task 10)
tools/datacheck/__init__.py          패키지 표지 (Task 1)
tools/datacheck/spec.py              명세 로더: Spec, FileSpec, Column, Ref, load_spec (Task 1)
tools/datacheck/model.py             Issue, Row, Table, RegionResult (Task 2)
tools/datacheck/readers.py           CSV·GeoJSON·ZIP 읽기, 지역 폴더 찾기 (Task 2, Task 6)
tools/datacheck/values.py            값 형식 검사와 날짜 해석 (Task 3)
tools/datacheck/rules_rows.py        행 수준 규칙 E101~E105 (Task 3)
tools/datacheck/rules_domain.py      파일별·교차 규칙 E106 E107 E108 W101~W106 I201 I202 (Task 4, Task 5)
tools/datacheck/validate.py          지역 폴더 하나 검증: validate_region (Task 2~4)
tools/datacheck/report.py            JSON·Markdown 리포트, 격리 파일, 종료 코드 (Task 6)
tools/datacheck/cli.py               명령줄 진입점 main (Task 6)
tools/validate_input.py              얇은 실행 래퍼 (Task 6)
tools/gen_docs.py                    명세 → 필드표·CSV 템플릿 생성과 일치 검사 (Task 7)
tools/build_docs_pdf.py              정의서.md → PDF (Task 11)
tests/helpers.py                     정상 지역 폴더 만들기·수정 도구 (Task 1, Task 2)
tests/test_spec.py  test_files.py  test_rows.py  test_domain.py  test_geometry.py
tests/test_cli.py  test_gen_docs.py  test_examples.py  test_bundle_schemas.py  test_build_docs_pdf.py
docs/data-interface/정의서.md  정의서.pdf  README.md
docs/data-interface/templates/*       CSV 템플릿 7개 + geometry_overrides.geojson (Task 7)
docs/data-interface/examples/incheon-gyeyang/*   (Task 9)
docs/data-interface/examples/gwangju-gwangsan/*  (Task 9)
```

각 파일은 책임이 하나다. `rules_domain.py`는 규칙 함수만, `validate.py`는 순서 조립만, `report.py`는 출력만 맡는다.

---

### Task 1: 입력 규격 명세 파일과 로더

**Files:**
- Create: `schemas/input.spec.json`
- Create: `tools/datacheck/__init__.py`
- Create: `tools/datacheck/spec.py`
- Create: `tests/helpers.py`
- Test: `tests/test_spec.py`

**Interfaces:**
- Produces: `datacheck.spec.load_spec(path=SPEC_PATH) -> Spec`.
  `Spec(schema_version: str, enums: dict[str, tuple[str, ...]], public_land_zone_types: tuple[str, ...], files: dict[str, FileSpec])`, 속성 `order -> list[str]`(파일 검증 순서).
  `FileSpec(name, kind: "csv"|"geojson", required_file: bool, description, primary_key: tuple[str,...], columns: tuple[Column,...], refs: tuple[Ref,...])`, 속성 `column_names`, `required_columns`.
  `Column(name, type, required, desc, enum=None, min=None, max=None)`. 열 형식 `type`은 `text slug int number date date_or_month yn enum pnu_list url code lon lat` 중 하나.
  `Ref(columns: tuple[str,...], to: str, to_columns: tuple[str,...], optional_column: str|None)`.
- Produces(테스트 도구): `tests/helpers.py`의 `ROOT`, `TODAY = date(2026, 10, 4)`, `SPEC`. 이 모듈을 import하면 `tools/`가 `sys.path`에 들어간다.

- [ ] **Step 1: 실패하는 테스트와 최소 도구를 만든다**

`tests/helpers.py`:

```python
"""테스트 공용 도구. import하면 tools/ 가 sys.path 에 들어간다."""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from datacheck.spec import load_spec  # noqa: E402

TODAY = date(2026, 10, 4)
SPEC = load_spec()
```

`tests/test_spec.py`:

```python
import unittest

from helpers import SPEC

REQUIRED = ["regions.csv", "region_codes.csv", "sources.csv", "zones.csv", "projects.csv", "events.csv"]
OPTIONAL = ["dongs.csv", "geometry_overrides.geojson"]


class SpecTest(unittest.TestCase):
    def test_files_and_required_flags(self):
        self.assertEqual(SPEC.order, REQUIRED + OPTIONAL)
        self.assertEqual([n for n, f in SPEC.files.items() if f.required_file], REQUIRED)
        self.assertEqual(SPEC.files["geometry_overrides.geojson"].kind, "geojson")
        self.assertEqual(SPEC.files["projects.csv"].kind, "csv")

    def test_primary_keys_use_known_columns(self):
        for name, fs in SPEC.files.items():
            known = set(fs.column_names) | {"region_slug"}  # GeoJSON 행에는 region_slug가 자동으로 들어간다
            self.assertLessEqual(set(fs.primary_key), known, name)

    def test_refs_point_to_existing_files_and_primary_keys(self):
        for name, fs in SPEC.files.items():
            for ref in fs.refs:
                self.assertIn(ref.to, SPEC.files, f"{name} → {ref.to}")
                self.assertEqual(len(ref.columns), len(ref.to_columns))
                self.assertEqual(tuple(ref.to_columns), SPEC.files[ref.to].primary_key, f"{name} → {ref.to}")
                self.assertLessEqual(set(ref.columns), set(fs.column_names) | {"region_slug"})

    def test_ref_targets_come_first_in_order(self):
        order = SPEC.order
        for name, fs in SPEC.files.items():
            for ref in fs.refs:
                self.assertLess(order.index(ref.to), order.index(name), f"{name} → {ref.to}")

    def test_enums_and_public_land_types(self):
        self.assertEqual(SPEC.public_land_zone_types, ("택지개발", "공공주택지구", "혁신도시", "신도시"))
        self.assertLessEqual(set(SPEC.public_land_zone_types), set(SPEC.enums["zone_type"]))
        self.assertEqual(SPEC.enums["sponsor_type"], ("public", "private", "joint", "unknown"))
        self.assertEqual(
            SPEC.enums["event_type"],
            ("notice", "permit_approved", "construction_start", "progress",
             "completion_inspection", "move_in", "structure_observed"),
        )
        self.assertEqual(SPEC.enums["tier"], ("official", "building", "schematic"))

    def test_schema_version_is_semver(self):
        self.assertRegex(SPEC.schema_version, r"^\d+\.\d+\.\d+$")

    def test_required_columns_of_projects(self):
        self.assertEqual(
            SPEC.files["projects.csv"].required_columns,
            ["region_slug", "project_id", "project_name", "block_label", "sponsor_name",
             "sponsor_type", "project_kind", "source_id", "observed_at"],
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m unittest discover -s tests -p "test_spec.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'datacheck'`

- [ ] **Step 3: 명세 파일과 로더를 만든다**

`tools/datacheck/__init__.py`:

```python
"""입력 규격 검증기 패키지. 표준 라이브러리만 사용한다."""
```

`tools/datacheck/spec.py`:

```python
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
```

`schemas/input.spec.json`:

```json
{
  "schema_version": "1.0.0",
  "enums": {
    "code_type": ["sido", "sigungu", "bjdong"],
    "zone_type": ["택지개발", "공공주택지구", "혁신도시", "신도시", "도시개발", "산업단지", "기타"],
    "sponsor_type": ["public", "private", "joint", "unknown"],
    "project_kind": ["공공분양", "신혼희망타운", "통합공공임대", "행복주택", "국민임대", "영구임대", "공공임대", "민간분양", "민간임대", "공공지원민간임대", "기타"],
    "on_public_land": ["Y", "N", "unknown"],
    "event_type": ["notice", "permit_approved", "construction_start", "progress", "completion_inspection", "move_in", "structure_observed"],
    "redistributable": ["Y", "N", "unknown"],
    "tier": ["official", "building", "schematic"]
  },
  "public_land_zone_types": ["택지개발", "공공주택지구", "혁신도시", "신도시"],
  "files": {
    "regions.csv": {
      "required_file": true,
      "description": "지역(시군구) 1행. 폴더 이름과 region_slug가 같아야 한다.",
      "primary_key": ["region_slug"],
      "columns": [
        {"name": "region_slug", "type": "slug", "required": true, "desc": "지역 식별자. 폴더 이름과 같아야 함. 예: gwangju-gwangsan"},
        {"name": "region_name", "type": "text", "required": true, "desc": "화면에 표시할 이름. 예: 광주 광산구"},
        {"name": "sido_name", "type": "text", "desc": "예: 광주광역시"},
        {"name": "sigungu_name", "type": "text", "desc": "예: 광산구"},
        {"name": "center_lon", "type": "lon", "desc": "시작 지도 중심 경도. 비우면 지구 경계에서 계산"},
        {"name": "center_lat", "type": "lat", "desc": "시작 지도 중심 위도. 비우면 지구 경계에서 계산"},
        {"name": "default_zoom", "type": "number", "min": 8, "max": 18, "desc": "시작 확대 수준. 비우면 자동"},
        {"name": "note", "type": "text", "desc": "메모"}
      ]
    },
    "region_codes.csv": {
      "required_file": true,
      "description": "지역 코드와 유효기간. 행정구역이 바뀌어 코드가 달라진 경우를 기록한다.",
      "primary_key": ["region_slug", "code", "code_type"],
      "columns": [
        {"name": "region_slug", "type": "slug", "required": true, "desc": "지역 식별자"},
        {"name": "code", "type": "code", "required": true, "desc": "시도 2자리, 시군구 5자리, 법정동 8~10자리 숫자"},
        {"name": "code_type", "type": "enum", "enum": "code_type", "required": true, "desc": "코드 종류"},
        {"name": "code_name", "type": "text", "desc": "코드의 이름. 예: 광산구"},
        {"name": "valid_from", "type": "date", "desc": "유효 시작일. 비우면 처음부터"},
        {"name": "valid_to", "type": "date", "desc": "유효 종료일. 비우면 현재도 유효"},
        {"name": "note", "type": "text", "desc": "메모"}
      ],
      "refs": [
        {"columns": ["region_slug"], "to": "regions.csv", "to_columns": ["region_slug"]}
      ]
    },
    "sources.csv": {
      "required_file": true,
      "description": "출처. 다른 파일의 source_id가 여기를 가리킨다. redistributable이 Y가 아니면 운영 사이트에 노출하지 않는다.",
      "primary_key": ["source_id"],
      "columns": [
        {"name": "source_id", "type": "slug", "required": true, "desc": "출처 식별자. 예: myhome-notice"},
        {"name": "label", "type": "text", "required": true, "desc": "화면에 표시될 출처 이름"},
        {"name": "publisher", "type": "text", "desc": "제공기관"},
        {"name": "license", "type": "text", "desc": "이용조건 요약"},
        {"name": "url", "type": "url", "desc": "출처 주소"},
        {"name": "as_of", "type": "date", "desc": "자료 기준일"},
        {"name": "redistributable", "type": "enum", "enum": "redistributable", "required": true, "desc": "공개 사이트에 가공 결과를 실어도 되는지"},
        {"name": "usage_note", "type": "text", "desc": "이용 관련 메모"}
      ]
    },
    "zones.csv": {
      "required_file": true,
      "description": "지구(구역). 파일이 비어 있어도(헤더만) 된다. 지구에 속하지 않는 단지는 projects.zone_id를 비운다.",
      "primary_key": ["region_slug", "zone_id"],
      "columns": [
        {"name": "region_slug", "type": "slug", "required": true, "desc": "지역 식별자"},
        {"name": "zone_id", "type": "slug", "required": true, "desc": "지역 안에서 유일한 지구 식별자. 예: sunwoon2"},
        {"name": "zone_name", "type": "text", "required": true, "desc": "공식 지구명. 예: 광주선운2 공공주택지구"},
        {"name": "zone_type", "type": "enum", "enum": "zone_type", "required": true, "desc": "지구 유형. 앞의 네 유형이 공공택지"},
        {"name": "organizer", "type": "text", "desc": "조성 주체. 예: LH"},
        {"name": "source_id", "type": "slug", "required": true, "desc": "근거 출처"},
        {"name": "note", "type": "text", "desc": "메모"}
      ],
      "refs": [
        {"columns": ["region_slug"], "to": "regions.csv", "to_columns": ["region_slug"]},
        {"columns": ["source_id"], "to": "sources.csv", "to_columns": ["source_id"]}
      ]
    },
    "projects.csv": {
      "required_file": true,
      "description": "단지(블록) 1행. 시행자 유형은 시행자를 직접 말하는 자료(공고문·공사현황·공급기관명)로 정한다.",
      "primary_key": ["region_slug", "project_id"],
      "columns": [
        {"name": "region_slug", "type": "slug", "required": true, "desc": "지역 식별자"},
        {"name": "project_id", "type": "text", "required": true, "desc": "지역 안에서 유일하고 바뀌지 않는 단지 식별자. 권장 형식 <zone_id>-<블록>. 예: sunwoon2-A1"},
        {"name": "zone_id", "type": "slug", "desc": "소속 지구. 지구 밖 단지는 비움"},
        {"name": "project_name", "type": "text", "required": true, "desc": "공고·공사현황의 이름. 예: 광주선운2 A-1블록 신혼희망타운"},
        {"name": "block_label", "type": "text", "required": true, "desc": "지도에 짧게 보일 이름. 예: A-1"},
        {"name": "block_name_raw", "type": "text", "desc": "출처 원문 블록 이름. 예: A-1BL. 매칭에 쓰인다"},
        {"name": "sponsor_name", "type": "text", "required": true, "desc": "시행자 이름. 예: LH"},
        {"name": "sponsor_type", "type": "enum", "enum": "sponsor_type", "required": true, "desc": "시행자 유형. public 공공, private 민간, joint 민관 공동, unknown 미확인"},
        {"name": "project_kind", "type": "enum", "enum": "project_kind", "required": true, "desc": "사업 유형"},
        {"name": "on_public_land", "type": "enum", "enum": "on_public_land", "desc": "공공택지 위 여부. 비우면 지구 유형으로 계산"},
        {"name": "units", "type": "int", "min": 0, "desc": "총 세대수. 모르면 비움"},
        {"name": "dong_count", "type": "int", "min": 0, "desc": "주동 수"},
        {"name": "pnu_list", "type": "pnu_list", "desc": "필지 번호(PNU) 19자리 목록, 세미콜론(;)으로 구분. 윤곽·블록 매칭의 1순위 키"},
        {"name": "address", "type": "text", "desc": "주소"},
        {"name": "source_id", "type": "slug", "required": true, "desc": "이 행의 근거 출처"},
        {"name": "observed_at", "type": "date", "required": true, "desc": "수집한 날"},
        {"name": "verified", "type": "yn", "desc": "사람이 원문으로 확인했으면 Y"},
        {"name": "note", "type": "text", "desc": "메모"}
      ],
      "refs": [
        {"columns": ["region_slug"], "to": "regions.csv", "to_columns": ["region_slug"]},
        {"columns": ["region_slug", "zone_id"], "to": "zones.csv", "to_columns": ["region_slug", "zone_id"], "optional_column": "zone_id"},
        {"columns": ["source_id"], "to": "sources.csv", "to_columns": ["source_id"]}
      ]
    },
    "events.csv": {
      "required_file": true,
      "description": "단지의 사건. 추가만 하고 수정·삭제하지 않는다. 상태는 입력하지 않고 이 사건들에서 계산한다.",
      "primary_key": ["region_slug", "project_id", "event_type", "event_date", "source_ref"],
      "columns": [
        {"name": "region_slug", "type": "slug", "required": true, "desc": "지역 식별자"},
        {"name": "project_id", "type": "text", "required": true, "desc": "단지 식별자"},
        {"name": "event_type", "type": "enum", "enum": "event_type", "required": true, "desc": "사건 종류"},
        {"name": "event_date", "type": "date_or_month", "required": true, "desc": "사건이 일어난(또는 예정인) 날. move_in만 YYYY-MM 허용"},
        {"name": "is_planned", "type": "yn", "desc": "예정일이면 Y. 비우면 N. construction_start·completion_inspection·move_in만 예정 허용"},
        {"name": "value", "type": "number", "min": 0, "desc": "사건별 값. progress는 공정율(0~100) 필수, notice·permit_approved는 세대수, structure_observed는 관측된 동 수"},
        {"name": "source_id", "type": "slug", "required": true, "desc": "근거 출처"},
        {"name": "source_ref", "type": "text", "desc": "원자료 식별자. 예: 공고 ID, 허가 관리번호"},
        {"name": "note", "type": "text", "desc": "메모"}
      ],
      "refs": [
        {"columns": ["region_slug"], "to": "regions.csv", "to_columns": ["region_slug"]},
        {"columns": ["region_slug", "project_id"], "to": "projects.csv", "to_columns": ["region_slug", "project_id"]},
        {"columns": ["source_id"], "to": "sources.csv", "to_columns": ["source_id"]}
      ]
    },
    "dongs.csv": {
      "required_file": false,
      "description": "동(선택). 열 이름이 아니라 정의된 의미를 따른다: floors_above는 지상, floors_below는 지하 층수.",
      "primary_key": ["region_slug", "project_id", "dong_no"],
      "columns": [
        {"name": "region_slug", "type": "slug", "required": true, "desc": "지역 식별자"},
        {"name": "project_id", "type": "text", "required": true, "desc": "단지 식별자"},
        {"name": "dong_no", "type": "text", "required": true, "desc": "동 번호. 예: 601"},
        {"name": "floors_above", "type": "int", "min": 0, "max": 120, "desc": "지상 층수"},
        {"name": "floors_below", "type": "int", "min": 0, "max": 15, "desc": "지하 층수"},
        {"name": "height_m", "type": "number", "min": 0, "max": 700, "desc": "건물 높이(m)"},
        {"name": "units", "type": "int", "min": 0, "desc": "동의 세대수"},
        {"name": "dong_use", "type": "text", "desc": "동의 용도. 예: 공동주택, 상가"},
        {"name": "source_id", "type": "slug", "required": true, "desc": "근거 출처"},
        {"name": "observed_at", "type": "date", "required": true, "desc": "수집한 날"}
      ],
      "refs": [
        {"columns": ["region_slug"], "to": "regions.csv", "to_columns": ["region_slug"]},
        {"columns": ["region_slug", "project_id"], "to": "projects.csv", "to_columns": ["region_slug", "project_id"]},
        {"columns": ["source_id"], "to": "sources.csv", "to_columns": ["source_id"]}
      ]
    },
    "geometry_overrides.geojson": {
      "kind": "geojson",
      "required_file": false,
      "description": "손으로 그린 윤곽(선택). FeatureCollection이며 아래 열은 각 Feature의 properties이다. geometry는 Polygon 또는 MultiPolygon, 좌표는 WGS84 [경도, 위도].",
      "primary_key": ["region_slug", "project_id", "dong_no"],
      "columns": [
        {"name": "project_id", "type": "text", "required": true, "desc": "단지 식별자"},
        {"name": "dong_no", "type": "text", "desc": "동 번호. 비우면 블록 윤곽"},
        {"name": "tier", "type": "enum", "enum": "tier", "required": true, "desc": "윤곽 등급"},
        {"name": "basis", "type": "text", "required": true, "desc": "그린 근거. 예: LH 팸플릿 단지배치도"},
        {"name": "source_id", "type": "slug", "required": true, "desc": "근거 출처"},
        {"name": "observed_at", "type": "date", "required": true, "desc": "작성한 날"}
      ],
      "refs": [
        {"columns": ["region_slug", "project_id"], "to": "projects.csv", "to_columns": ["region_slug", "project_id"]},
        {"columns": ["source_id"], "to": "sources.csv", "to_columns": ["source_id"]}
      ]
    }
  }
}
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m unittest discover -s tests -p "test_spec.py" -v`
Expected: PASS — 7 tests OK

- [ ] **Step 5: 커밋**

```bash
git add schemas/input.spec.json tools/datacheck/__init__.py tools/datacheck/spec.py tests/helpers.py tests/test_spec.py
git commit -m "feat: 입력 규격 명세 파일과 로더" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 읽기와 파일 수준 검증 (E001 E002 E003 W001)

**Files:**
- Create: `tools/datacheck/model.py`
- Create: `tools/datacheck/readers.py`
- Create: `tools/datacheck/validate.py`
- Modify: `tests/helpers.py` (전체 교체)
- Test: `tests/test_files.py`

**Interfaces:**
- Consumes: Task 1의 `Spec`, `FileSpec`, `load_spec`.
- Produces:
  - `datacheck.model.Row(n: int, v: dict[str, str])` + `Row.get(col) -> str`(없으면 `""`).
  - `datacheck.model.Table(name, header: list[str], rows: list[Row])`.
  - `datacheck.model.Issue(rule, severity, region, file, row: int|None, message)` + `as_dict()`.
  - `datacheck.model.RegionResult(slug, path)`: 필드 `tables`, `issues`, `rejected`, `rejected_files`, `quarantined`, `valid_keys`, `scope`, `features`; 메서드 `add(rule, file, row, message) -> Issue`(규칙 ID 첫 글자 E/W/I로 심각도 결정, error이고 `row`가 있으면 그 행을 격리), `is_quarantined(file, n) -> bool`, `active_rows(file) -> list[Row]`.
  - `datacheck.readers.read_csv(path, name) -> Table`(UTF-8 BOM 허용, 아니면 `UnicodeDecodeError`), `read_geojson_table(path, name, slug) -> tuple[Table, list[dict]]`.
  - `datacheck.validate.validate_region(path, spec, today, slug=None) -> RegionResult`(이 작업에서는 파일 수준 검사만).
  - `tests/helpers.py`: `BASE_ROWS`, `write_csv(dirpath, name, rows)`, `raw_csv(header, rows) -> bytes`, `make_region(tmp, slug="test-region", edits=None, drop=(), raw=None) -> Path`, `rules_of(res) -> list[str]`.

- [ ] **Step 1: 테스트 도구를 확장하고 실패하는 테스트를 쓴다**

`tests/helpers.py` (전체 교체):

```python
"""테스트 공용 도구. import하면 tools/ 가 sys.path 에 들어간다."""
import copy
import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from datacheck.spec import load_spec  # noqa: E402

TODAY = date(2026, 10, 4)
SPEC = load_spec()

# 오류가 하나도 없는 최소 지역. 테스트는 이것을 복사해 한 곳만 바꾼다.
BASE_ROWS = {
    "regions.csv": [dict(region_slug="test-region", region_name="테스트구")],
    "region_codes.csv": [dict(region_slug="test-region", code="12330", code_type="sigungu", code_name="테스트구")],
    "sources.csv": [dict(source_id="src-a", label="출처 A", publisher="기관", license="CC BY",
                         url="https://example.org", as_of="2026-10-01", redistributable="Y")],
    "zones.csv": [dict(region_slug="test-region", zone_id="z1", zone_name="테스트 공공주택지구",
                       zone_type="공공주택지구", organizer="LH", source_id="src-a")],
    "projects.csv": [dict(region_slug="test-region", project_id="z1-A1", zone_id="z1",
                          project_name="테스트 A-1 블록", block_label="A-1", block_name_raw="A-1BL",
                          sponsor_name="LH", sponsor_type="public", project_kind="신혼희망타운",
                          units="828", dong_count="6", pnu_list="1233010600105190000",
                          address="테스트 주소", source_id="src-a", observed_at="2026-10-04", verified="Y")],
    "events.csv": [
        dict(region_slug="test-region", project_id="z1-A1", event_type="permit_approved",
             event_date="2022-03-11", value="828", source_id="src-a", source_ref="P1"),
        dict(region_slug="test-region", project_id="z1-A1", event_type="notice",
             event_date="2026-02-02", value="86", source_id="src-a", source_ref="N1"),
        dict(region_slug="test-region", project_id="z1-A1", event_type="structure_observed",
             event_date="2026-10-04", value="6", source_id="src-a"),
    ],
    "dongs.csv": [dict(region_slug="test-region", project_id="z1-A1", dong_no="101", floors_above="25",
                       floors_below="2", height_m="74", dong_use="공동주택", source_id="src-a",
                       observed_at="2026-10-04")],
}


def write_csv(dirpath, name, rows):
    """명세의 열 순서로 헤더를 쓰고, rows(dict 목록)를 UTF-8 BOM CSV로 쓴다."""
    cols = SPEC.files[name].column_names
    with open(Path(dirpath) / name, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])


def raw_csv(header, rows, encoding="utf-8"):
    """헤더와 행(문자열 목록)으로 원하는 인코딩의 CSV 바이트를 만든다."""
    lines = [",".join(header)] + [",".join(r) for r in rows]
    return ("\n".join(lines) + "\n").encode(encoding)


def make_region(tmp, slug="test-region", edits=None, drop=(), raw=None):
    """tmp/slug 폴더에 정상 지역을 만든다.

    edits: {파일명: 함수(rows)} — rows(dict 목록)를 제자리에서 고친다.
    drop:  만들지 않을 파일 이름들.
    raw:   {파일명: bytes} — 그 파일은 이 바이트를 그대로 쓴다.
    """
    rows = copy.deepcopy(BASE_ROWS)
    for name, fn in (edits or {}).items():
        fn(rows[name])
    d = Path(tmp) / slug
    d.mkdir(parents=True, exist_ok=True)
    for name, rs in rows.items():
        if name not in drop:
            write_csv(d, name, rs)
    for name, data in (raw or {}).items():
        (d / name).write_bytes(data)
    return d


def rules_of(res, severity=None):
    return [i.rule for i in res.issues if severity is None or i.severity == severity]
```

`tests/test_files.py`:

```python
import tempfile
import unittest
from pathlib import Path

from helpers import SPEC, TODAY, make_region, raw_csv, rules_of
from datacheck.readers import read_csv
from datacheck.validate import validate_region


def run(**kw):
    with tempfile.TemporaryDirectory() as tmp:
        return validate_region(make_region(tmp, **kw), SPEC, TODAY)


def problems(res):
    """error·warn 규칙 ID 목록 (info 제외)."""
    return [i.rule for i in res.issues if i.severity != "info"]


class FileLevel(unittest.TestCase):
    def test_base_region_has_no_problems(self):
        res = run()
        self.assertEqual(problems(res), [])  # info(요약)는 문제가 아니다
        self.assertFalse(res.rejected)
        self.assertEqual(sorted(res.tables), sorted(["regions.csv", "region_codes.csv", "sources.csv",
                                                     "zones.csv", "projects.csv", "events.csv", "dongs.csv"]))

    def test_e001_missing_required_file_rejects_region(self):
        res = run(drop=("events.csv",))
        self.assertIn("E001", rules_of(res))
        self.assertTrue(res.rejected)

    def test_optional_files_may_be_absent(self):
        res = run(drop=("dongs.csv",))
        self.assertEqual(problems(res), [])

    def test_e002_missing_required_column(self):
        res = run(raw={"events.csv": raw_csv(["region_slug", "project_id"], [["test-region", "z1-A1"]])})
        self.assertIn("E002", rules_of(res))
        self.assertIn("events.csv", res.rejected_files)
        self.assertNotIn("events.csv", res.tables)
        self.assertFalse(res.rejected)  # 파일만 거부, 지역은 계속 검사

    def test_e002_duplicate_header(self):
        header = SPEC.files["events.csv"].column_names + ["note"]
        res = run(raw={"events.csv": raw_csv(header, [])})
        [issue] = [i for i in res.issues if i.rule == "E002"]
        self.assertIn("중복", issue.message)

    def test_e002_cp949_file_gets_fix_hint(self):  # Review Focus 1
        cols = SPEC.files["sources.csv"].column_names
        row = ["src-a", "출처", "기관", "라이선스", "", "", "Y", ""]
        res = run(raw={"sources.csv": raw_csv(cols, [row], encoding="cp949")})
        [issue] = [i for i in res.issues if i.rule == "E002"]
        self.assertIn("UTF-8", issue.message)
        self.assertIn("다시 저장", issue.message)
        self.assertIn("sources.csv", res.rejected_files)

    def test_e003_region_slug_must_match_folder(self):
        res = run(slug="other-slug")
        self.assertIn("E003", rules_of(res))
        self.assertTrue(res.rejected)

    def test_e003_regions_csv_must_have_exactly_one_row(self):
        res = run(edits={"regions.csv": lambda rows: rows.append(dict(region_slug="test-region", region_name="둘째"))})
        self.assertIn("E003", rules_of(res))
        self.assertTrue(res.rejected)

    def test_w001_unknown_column_is_only_a_warning(self):
        header = SPEC.files["regions.csv"].column_names + ["memo"]
        row = ["test-region", "테스트구", "", "", "", "", "", "", "메모"]
        res = run(raw={"regions.csv": raw_csv(header, [row])})
        self.assertEqual(problems(res), ["W001"])
        self.assertIn("regions.csv", res.tables)

    def test_excel_noise_bom_crlf_blank_lines_quoted_comma(self):  # Review Focus 2
        text = "﻿region_slug,region_name\r\ntest-region,\"테스트, 구\"\r\n\r\n\r\n"
        res = run(raw={"regions.csv": text.encode("utf-8")})
        self.assertEqual(problems(res), [])
        [row] = res.tables["regions.csv"].rows
        self.assertEqual(row.get("region_name"), "테스트, 구")

    def test_header_only_tables_pass(self):  # Review Focus 3
        empty = lambda rows: rows.clear()
        res = run(edits={"zones.csv": empty, "dongs.csv": empty})
        self.assertEqual([i for i in res.issues if i.rule in ("E001", "E002")], [])
        self.assertEqual(res.tables["zones.csv"].rows, [])


class ReadCsv(unittest.TestCase):
    def test_rows_are_numbered_from_one_skipping_blank_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "t.csv"
            p.write_text("a,b\n1,2\n\n3,4\n", encoding="utf-8")
            t = read_csv(p, "t.csv")
        self.assertEqual([(r.n, r.get("a"), r.get("b")) for r in t.rows], [(1, "1", "2"), (2, "3", "4")])
        self.assertEqual(t.rows[0].get("missing"), "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m unittest discover -s tests -p "test_files.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'datacheck.readers'`

- [ ] **Step 3: 모델·읽기·파일 수준 검증을 구현한다**

`tools/datacheck/model.py`:

```python
"""검증 결과와 표 모델."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

SEVERITY = {"E": "error", "W": "warn", "I": "info"}


@dataclass(frozen=True)
class Issue:
    rule: str
    severity: str
    region: str
    file: str
    row: int | None  # 헤더를 뺀 데이터 행 순번(1부터). 파일·지역 수준 문제는 None
    message: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Row:
    n: int
    v: dict[str, str]

    def get(self, col: str) -> str:
        return self.v.get(col, "")


@dataclass
class Table:
    name: str
    header: list[str]
    rows: list[Row]


@dataclass
class RegionResult:
    slug: str
    path: Path
    tables: dict[str, Table] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    rejected: bool = False  # 지역 폴더 전체 거부 (E001, E003)
    rejected_files: set[str] = field(default_factory=set)  # 읽을 수 없어 거부된 파일 (E002)
    quarantined: dict[str, dict[int, list[Issue]]] = field(default_factory=dict)
    valid_keys: dict[str, set[tuple]] = field(default_factory=dict)
    scope: dict[str, int] = field(default_factory=dict)
    features: list[dict] = field(default_factory=list)  # geometry_overrides.geojson 원본 Feature 목록

    def add(self, rule: str, file: str, row: int | None, message: str) -> Issue:
        severity = SEVERITY[rule[0]]
        issue = Issue(rule, severity, self.slug, file, row, message)
        self.issues.append(issue)
        if severity == "error" and row is not None:
            self.quarantined.setdefault(file, {}).setdefault(row, []).append(issue)
        return issue

    def is_quarantined(self, file: str, n: int) -> bool:
        return n in self.quarantined.get(file, {})

    def active_rows(self, file: str) -> list[Row]:
        table = self.tables.get(file)
        if table is None:
            return []
        q = self.quarantined.get(file, {})
        return [r for r in table.rows if r.n not in q]
```

`tools/datacheck/readers.py`:

```python
"""입력 파일 읽기: CSV, GeoJSON."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from .model import Row, Table


def read_csv(path: Path | str, name: str) -> Table:
    """UTF-8(BOM 허용) CSV를 읽는다. UTF-8이 아니면 UnicodeDecodeError를 낸다."""
    text = Path(path).read_bytes().decode("utf-8-sig")
    raw = list(csv.reader(io.StringIO(text, newline="")))
    header = [h.strip() for h in raw[0]] if raw else []
    rows: list[Row] = []
    for cells in raw[1:]:
        if not any(c.strip() for c in cells):
            continue  # 끝의 빈 줄 등
        values = {h: (cells[i].strip() if i < len(cells) else "") for i, h in enumerate(header)}
        rows.append(Row(len(rows) + 1, values))
    return Table(name, header, rows)


def read_geojson_table(path: Path | str, name: str, slug: str) -> tuple[Table, list[dict]]:
    """GeoJSON FeatureCollection을 표로 읽는다. 각 Feature의 properties가 한 행이 된다.

    행에는 region_slug 가 자동으로 들어간다(참조 검사용). 형식이 틀리면 ValueError.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise ValueError("FeatureCollection이 아님")
    features = data["features"]
    rows: list[Row] = []
    keys: list[str] = []
    for i, feature in enumerate(features, start=1):
        props = feature.get("properties") if isinstance(feature, dict) else None
        props = props if isinstance(props, dict) else {}
        for k in props:
            if k not in keys:
                keys.append(k)
        values = {k: ("" if v is None else str(v)).strip() for k, v in props.items()}
        values["region_slug"] = slug
        rows.append(Row(i, values))
    return Table(name, keys, rows), features
```

`tools/datacheck/validate.py`:

```python
"""지역 폴더 하나를 검증한다."""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from .model import RegionResult
from .readers import read_csv, read_geojson_table
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
    return res
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m unittest discover -s tests -p "test_files.py" -v`
Expected: PASS — 12 tests OK. 실패하면 메시지를 읽고 `validate.py`·`readers.py`를 고친다(테스트를 고치지 않는다).

- [ ] **Step 5: 전체 테스트와 커밋**

Run: `python3 -m unittest discover -s tests`
Expected: `OK`

```bash
git add tools/datacheck/model.py tools/datacheck/readers.py tools/datacheck/validate.py tests/helpers.py tests/test_files.py
git commit -m "feat: CSV·GeoJSON 읽기와 파일 수준 검증(E001 E002 E003 W001)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 3: 행 수준 규칙 (E101 E102 E103 E104 E105)

**Files:**
- Create: `tools/datacheck/values.py`
- Create: `tools/datacheck/rules_rows.py`
- Modify: `tools/datacheck/validate.py` (`validate_region` 교체, import 추가)
- Test: `tests/test_rows.py`

**Interfaces:**
- Consumes: Task 1 `Spec/FileSpec/Column/Ref`, Task 2 `RegionResult/Row/Table`, `validate_region`.
- Produces:
  - `datacheck.values.parse_date(s) -> date|None`(엄격한 `YYYY-MM-DD`), `parse_month(s) -> date|None`(`YYYY-MM` → 그 달 1일), `parse_event_date(s) -> date|None`(둘 중 하나), `check_value(col: Column, value: str, enums: dict) -> tuple[str, str] | None`(문제 없으면 `None`, 있으면 `(규칙 ID, 설명)`, 열거형 위반만 `E103` 나머지는 `E102`).
  - `datacheck.rules_rows.check_rows(res, spec, fs, table)`, `check_primary_key(res, fs)`, `check_refs(res, fs)`. 모두 `res.add(...)`로 이슈를 쌓고 error 행을 격리한다.
  - `validate_region`은 파일마다 `check_rows → check_primary_key → check_refs`를 돌린 뒤 `res.valid_keys[파일] = {기본키 튜플}`(격리되지 않은 행만)을 채운다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_rows.py`:

```python
import tempfile
import unittest

from helpers import SPEC, TODAY, make_region, rules_of
from datacheck.validate import validate_region


def run(**kw):
    with tempfile.TemporaryDirectory() as tmp:
        return validate_region(make_region(tmp, **kw), SPEC, TODAY)


def issues(res, rule):
    return [i for i in res.issues if i.rule == rule]


def set_first(**kw):
    """rows[0]의 값을 바꾸는 edits 함수."""
    return lambda rows: rows[0].update(kw)


class RowRules(unittest.TestCase):
    def test_base_region_has_no_errors(self):
        self.assertEqual(rules_of(run(), "error"), [])

    def test_e101_required_value_missing_quarantines_the_row(self):
        res = run(edits={"projects.csv": set_first(project_name="")})
        [issue] = issues(res, "E101")
        self.assertEqual((issue.file, issue.row), ("projects.csv", 1))
        self.assertIn("project_name", issue.message)
        self.assertTrue(res.is_quarantined("projects.csv", 1))
        self.assertEqual(res.active_rows("projects.csv"), [])

    def test_e102_bad_formats(self):
        cases = [
            ("projects.csv", "pnu_list", "123"), ("projects.csv", "observed_at", "2026-13-40"),
            ("projects.csv", "units", "-5"), ("projects.csv", "source_id", "Bad ID"),
            ("dongs.csv", "floors_above", "abc"), ("dongs.csv", "floors_below", "99"),
            ("dongs.csv", "height_m", "1e3"), ("sources.csv", "url", "example.org"),
            ("region_codes.csv", "code", "123"), ("events.csv", "event_date", "2026/02/02"),
            ("events.csv", "value", "1_000"), ("regions.csv", "center_lon", "140"),
        ]
        for file, col, bad in cases:
            with self.subTest(file=file, col=col, bad=bad):
                res = run(edits={file: set_first(**{col: bad})})
                self.assertIn("E102", rules_of(res, "error"))

    def test_e103_value_not_in_enum(self):
        cases = [("projects.csv", "sponsor_type", "gov"), ("zones.csv", "zone_type", "공원"),
                 ("events.csv", "event_type", "started"), ("sources.csv", "redistributable", "maybe")]
        for file, col, bad in cases:
            with self.subTest(file=file, col=col, bad=bad):
                res = run(edits={file: set_first(**{col: bad})})
                self.assertIn("E103", rules_of(res, "error"))

    def test_e104_duplicate_primary_key_quarantines_the_later_row(self):
        res = run(edits={"projects.csv": lambda rows: rows.append(dict(rows[0]))})
        [issue] = issues(res, "E104")
        self.assertEqual((issue.file, issue.row), ("projects.csv", 2))
        self.assertFalse(res.is_quarantined("projects.csv", 1))

    def test_e104_duplicate_event(self):
        res = run(edits={"events.csv": lambda rows: rows.append(dict(rows[0]))})
        [issue] = issues(res, "E104")
        self.assertEqual((issue.file, issue.row), ("events.csv", 4))

    def test_e105_event_for_unknown_project(self):
        res = run(edits={"events.csv": set_first(project_id="nope")})
        [issue] = issues(res, "E105")
        self.assertEqual((issue.file, issue.row), ("events.csv", 1))

    def test_e105_unknown_zone_source_or_region(self):
        cases = [("projects.csv", "zone_id", "nozone"), ("events.csv", "source_id", "missing-src"),
                 ("zones.csv", "source_id", "missing-src"), ("projects.csv", "region_slug", "other")]
        for file, col, bad in cases:
            with self.subTest(file=file, col=col):
                res = run(edits={file: set_first(**{col: bad})})
                self.assertIn("E105", rules_of(res, "error"))

    def test_blank_zone_id_is_allowed(self):
        res = run(edits={"projects.csv": set_first(zone_id="")})
        self.assertEqual(rules_of(res, "error"), [])

    def test_reference_to_a_quarantined_parent_is_an_error(self):
        res = run(edits={"projects.csv": set_first(project_name="")})
        got = sorted((i.file, i.row) for i in issues(res, "E105"))
        self.assertEqual(got, [("dongs.csv", 1), ("events.csv", 1), ("events.csv", 2), ("events.csv", 3)])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m unittest discover -s tests -p "test_rows.py" -v`
Expected: FAIL — E101 등이 발생하지 않아 `ValueError: not enough values to unpack` 또는 `AssertionError`

- [ ] **Step 3: 값 검사와 행 규칙을 구현한다**

`tools/datacheck/values.py`:

```python
"""값 형식 검사와 날짜 해석."""
from __future__ import annotations

import re
from datetime import date

from .spec import Column

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
CODE = re.compile(r"^([0-9]{2}|[0-9]{5}|[0-9]{8,10})$")
PNU = re.compile(r"^[0-9]{19}$")
INT = re.compile(r"^-?[0-9]+$")
DECIMAL = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")


def parse_date(s: str) -> date | None:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", s):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def parse_month(s: str) -> date | None:
    """YYYY-MM 을 그 달 1일로 바꾼다."""
    m = re.fullmatch(r"([0-9]{4})-([0-9]{2})", s)
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), 1)
    except ValueError:
        return None


def parse_event_date(s: str) -> date | None:
    return parse_date(s) or parse_month(s)


def _bad(message: str) -> tuple[str, str]:
    return ("E102", message)


def _range(col: Column, n: float) -> tuple[str, str] | None:
    if col.min is not None and n < col.min:
        return _bad(f"{col.min:g} 이상이어야 함")
    if col.max is not None and n > col.max:
        return _bad(f"{col.max:g} 이하여야 함")
    return None


def check_value(col: Column, value: str, enums: dict[str, tuple[str, ...]]) -> tuple[str, str] | None:
    """빈 값이 아닌 value 가 열 형식에 맞는지 본다. 문제가 없으면 None, 있으면 (규칙 ID, 설명)."""
    t = col.type
    if t == "text":
        return None
    if t == "slug":
        return None if SLUG.match(value) else _bad("소문자 영문·숫자·하이픈으로 된 slug가 아님")
    if t == "int":
        return _range(col, int(value)) if INT.match(value) else _bad("정수가 아님")
    if t == "number":
        return _range(col, float(value)) if DECIMAL.match(value) else _bad("숫자가 아님")
    if t == "date":
        return None if parse_date(value) else _bad("YYYY-MM-DD 날짜가 아님")
    if t == "date_or_month":
        return None if parse_event_date(value) else _bad("YYYY-MM-DD 또는 YYYY-MM 형식이 아님")
    if t == "yn":
        return None if value in ("Y", "N") else _bad("Y 또는 N이 아님")
    if t == "enum":
        allowed = enums[col.enum]
        return None if value in allowed else ("E103", f"허용 값이 아님 (허용: {', '.join(allowed)})")
    if t == "pnu_list":
        bad = [p.strip() for p in value.split(";") if not PNU.match(p.strip())]
        return None if not bad else _bad(f"19자리 숫자가 아닌 PNU: {', '.join(bad)}")
    if t == "url":
        return None if value.startswith(("http://", "https://")) else _bad("http:// 또는 https:// 로 시작하는 주소가 아님")
    if t == "code":
        return None if CODE.match(value) else _bad("숫자 2·5·8~10자리가 아님")
    if t in ("lon", "lat"):
        lo, hi, label = (124, 132, "경도") if t == "lon" else (33, 39, "위도")
        if DECIMAL.match(value) and lo <= float(value) <= hi:
            return None
        return _bad(f"{label} {lo}~{hi} 범위의 숫자가 아님")
    raise ValueError(f"알 수 없는 열 형식: {t}")
```

`tools/datacheck/rules_rows.py`:

```python
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
```

`tools/datacheck/validate.py`에서 import 줄을 추가하고 `validate_region`을 아래로 **교체**한다.

import 추가(기존 `from .spec import Spec` 아래):

```python
from .rules_rows import check_primary_key, check_refs, check_rows
```

교체할 함수:

```python
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
        res.valid_keys[name] = {tuple(r.get(c) for c in fs.primary_key) for r in res.active_rows(name)}
    return res
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m unittest discover -s tests -p "test_rows.py" -v`
Expected: PASS — 10 tests OK

- [ ] **Step 5: 전체 테스트와 커밋**

Run: `python3 -m unittest discover -s tests`
Expected: `OK`

```bash
git add tools/datacheck/values.py tools/datacheck/rules_rows.py tools/datacheck/validate.py tests/test_rows.py
git commit -m "feat: 행 수준 검증(E101~E105)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 파일별·교차 규칙 (E106 E107 W101~W106 I201 I202)

**Files:**
- Create: `tools/datacheck/rules_domain.py`
- Modify: `tools/datacheck/validate.py` (`validate_region` 교체, import 추가)
- Test: `tests/test_domain.py`

**Interfaces:**
- Consumes: Task 3의 `res.add`, `res.active_rows`, `values.parse_date`, `values.parse_event_date`.
- Produces:
  - `datacheck.rules_domain.check_events(res, spec, today)`, `check_dongs(res, spec, today)`, `check_projects(res, spec, today)`, `check_cross(res, spec, today)`, `DOMAIN_CHECKS: dict[str, Callable]`(파일 이름 → 파일별 규칙 함수), `resolve_on_public_land(spec, row, zone_type) -> "Y"|"N"|"unknown"`.
  - `res.scope = {"public": int, "private_on_public_land": int, "out_of_scope": int, "unknown": int}` (`public`에는 `joint` 포함).
  - 항상 `I202`(info, 파일 `""`, 행 None)를 하나 낸다. 메시지는 `정상 행 수: zones N, projects N, events N, dongs N, sources N` 형식(없는 파일은 생략).

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_domain.py`:

```python
import tempfile
import unittest

from helpers import SPEC, TODAY, make_region, rules_of
from datacheck.validate import validate_region


def run(**kw):
    with tempfile.TemporaryDirectory() as tmp:
        return validate_region(make_region(tmp, **kw), SPEC, TODAY)


def issues(res, rule):
    return [i for i in res.issues if i.rule == rule]


def set_first(**kw):
    return lambda rows: rows[0].update(kw)


def ev(**kw):
    base = dict(region_slug="test-region", project_id="z1-A1", source_id="src-a")
    base.update(kw)
    return base


def add_events(*events):
    return lambda rows: rows.extend(events)


class EventRules(unittest.TestCase):
    def test_e106_actual_event_in_the_future(self):
        res = run(edits={"events.csv": add_events(ev(event_type="construction_start", event_date="2026-12-23"))})
        [i] = issues(res, "E106")
        self.assertEqual((i.file, i.row), ("events.csv", 4))

    def test_planned_future_event_is_fine(self):
        res = run(edits={"events.csv": add_events(
            ev(event_type="construction_start", event_date="2026-12-23", is_planned="Y"))})
        self.assertEqual(rules_of(res, "error"), [])

    def test_month_precision_is_only_for_move_in(self):
        ok = run(edits={"events.csv": add_events(ev(event_type="move_in", event_date="2029-06", is_planned="Y"))})
        self.assertEqual(rules_of(ok, "error"), [])
        bad = run(edits={"events.csv": add_events(ev(event_type="construction_start", event_date="2026-05"))})
        self.assertIn("E102", rules_of(bad, "error"))

    def test_actual_move_in_this_month_is_not_future(self):
        res = run(edits={"events.csv": add_events(ev(event_type="move_in", event_date="2026-10"))})
        self.assertEqual(rules_of(res, "error"), [])

    def test_e103_planned_not_allowed_for_notice(self):
        res = run(edits={"events.csv": add_events(ev(event_type="notice", event_date="2026-09-01", is_planned="Y"))})
        self.assertIn("E103", rules_of(res, "error"))

    def test_e107_progress_needs_value_between_0_and_100(self):
        for value, expect_error in (("", True), ("120", True), ("50", False)):
            with self.subTest(value=value):
                res = run(edits={"events.csv": add_events(
                    ev(event_type="progress", event_date="2026-09-21", value=value))})
                self.assertEqual("E107" in rules_of(res, "error"), expect_error)

    def test_w101_permit_after_construction_start_flags_both_events(self):
        res = run(edits={"events.csv": add_events(ev(event_type="construction_start", event_date="2021-01-01"))})
        self.assertEqual(sorted(i.row for i in issues(res, "W101")), [1, 4])
        self.assertEqual(rules_of(res, "error"), [])  # warn은 행을 격리하지 않는다

    def test_w101_construction_start_after_completion(self):
        res = run(edits={"events.csv": add_events(
            ev(event_type="construction_start", event_date="2026-06-01"),
            ev(event_type="completion_inspection", event_date="2026-01-20"))})
        self.assertEqual(sorted(i.row for i in issues(res, "W101")), [4, 5])

    def test_w101_progress_must_not_decrease(self):
        res = run(edits={"events.csv": add_events(
            ev(event_type="progress", event_date="2026-08-28", value="5"),
            ev(event_type="progress", event_date="2026-09-21", value="3"))})
        self.assertEqual([i.row for i in issues(res, "W101")], [5])

    def test_a_later_amendment_permit_after_completion_is_not_a_warning(self):
        res = run(edits={"events.csv": add_events(
            ev(event_type="completion_inspection", event_date="2023-01-01"),
            ev(event_type="permit_approved", event_date="2025-05-05", value="828", source_ref="P2"))})
        self.assertEqual(issues(res, "W101"), [])


class DongRules(unittest.TestCase):
    def test_base_dong_has_no_warning(self):
        res = run()
        self.assertEqual(rules_of(res, "warn"), [])

    def test_w102_height_per_floor_out_of_range(self):
        res = run(edits={"dongs.csv": set_first(floors_above="25", height_m="20")})
        self.assertEqual([i.rule for i in res.issues if i.rule.startswith("W10")], ["W102"])

    def test_w103_zero_floors_with_tall_height_suggests_swapped_fields(self):
        # 12층(36 m)짜리를 지상 0·지하 12로 뒤바꿔 적은 경우. floors_below 상한(15) 안이라 E102로 격리되지 않는다
        res = run(edits={"dongs.csv": set_first(floors_above="0", floors_below="12", height_m="36")})
        self.assertEqual([i.rule for i in res.issues if i.rule.startswith("W10")], ["W103"])

    def test_commercial_building_is_not_checked(self):
        res = run(edits={"dongs.csv": set_first(dong_use="상가", floors_above="5", height_m="100")})
        self.assertEqual(rules_of(res, "warn"), [])

    def test_dong_without_height_is_not_checked(self):
        res = run(edits={"dongs.csv": set_first(height_m="")})
        self.assertEqual(rules_of(res, "warn"), [])


class ProjectRules(unittest.TestCase):
    def test_base_has_no_units_warning_even_though_notice_value_differs(self):
        self.assertNotIn("W104", rules_of(run()))  # notice 86세대 ≠ units 828 이지만 비교 대상이 아니다

    def test_w104_units_differ_from_latest_permit(self):
        res = run(edits={"projects.csv": set_first(units="500")})
        [i] = issues(res, "W104")
        self.assertEqual((i.file, i.row), ("projects.csv", 1))

    def test_w105_unknown_sponsor(self):
        res = run(edits={"projects.csv": set_first(sponsor_type="unknown")})
        self.assertIn("W105", rules_of(res, "warn"))
        self.assertEqual(res.scope["unknown"], 1)
        self.assertNotIn("I201", rules_of(res))

    def test_w106_stale_observation(self):
        res = run(edits={"projects.csv": set_first(observed_at="2025-01-01"),
                         "dongs.csv": set_first(observed_at="2025-01-01")})
        self.assertEqual(sorted(i.file for i in issues(res, "W106")), ["dongs.csv", "projects.csv"])

    def test_scope_public_and_joint(self):
        res = run()
        self.assertEqual(res.scope, {"public": 1, "private_on_public_land": 0, "out_of_scope": 0, "unknown": 0})
        res = run(edits={"projects.csv": set_first(sponsor_type="joint")})
        self.assertEqual(res.scope["public"], 1)

    def test_private_on_public_land_zone_is_in_scope(self):
        res = run(edits={"projects.csv": set_first(sponsor_type="private", project_kind="민간분양")})
        self.assertEqual(res.scope["private_on_public_land"], 1)
        self.assertNotIn("I201", rules_of(res))

    def test_private_outside_public_land_is_out_of_scope(self):
        private = set_first(sponsor_type="private", project_kind="민간분양")
        cases = {
            "도시개발 지구": dict(edits={"projects.csv": private, "zones.csv": set_first(zone_type="도시개발")}),
            "지구 없음": dict(edits={"projects.csv": lambda r: r[0].update(
                sponsor_type="private", project_kind="민간분양", zone_id="")}),
            "on_public_land=N이 지구 유형보다 우선": dict(edits={"projects.csv": lambda r: r[0].update(
                sponsor_type="private", project_kind="민간분양", on_public_land="N")}),
        }
        for label, kw in cases.items():
            with self.subTest(label):
                res = run(**kw)
                self.assertEqual(res.scope["out_of_scope"], 1)
                self.assertEqual(len(issues(res, "I201")), 1)

    def test_on_public_land_y_overrides_zone_type(self):
        res = run(edits={"projects.csv": lambda r: r[0].update(
            sponsor_type="private", project_kind="민간분양", on_public_land="Y"),
            "zones.csv": set_first(zone_type="도시개발")})
        self.assertEqual(res.scope["private_on_public_land"], 1)

    def test_i202_summary_counts(self):
        [i] = issues(run(), "I202")
        self.assertIn("projects 1", i.message)
        self.assertIn("events 3", i.message)
        self.assertEqual((i.file, i.row), ("", None))

    def test_zero_row_tables_summarize_as_zero(self):  # Review Focus 3
        clear = lambda rows: rows.clear()
        res = run(edits={"projects.csv": clear, "events.csv": clear, "dongs.csv": clear})
        self.assertEqual(rules_of(res, "error"), [])
        [i] = issues(res, "I202")
        self.assertIn("projects 0", i.message)
        self.assertIn("events 0", i.message)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m unittest discover -s tests -p "test_domain.py" -v`
Expected: FAIL — E106·E107·W101·I202 등이 아직 발생하지 않아 여러 테스트가 `AssertionError` 또는 `ValueError: not enough values to unpack`으로 실패한다.

- [ ] **Step 3: 규칙을 구현한다**

`tools/datacheck/rules_domain.py`:

```python
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


DOMAIN_CHECKS = {
    "events.csv": check_events,
    "dongs.csv": check_dongs,
    "projects.csv": check_projects,
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
```

`tools/datacheck/validate.py`: import를 추가하고 `validate_region`을 교체한다.

import 추가:

```python
from .rules_domain import DOMAIN_CHECKS, check_cross
```

교체할 함수:

```python
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
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m unittest discover -s tests -p "test_domain.py" -v`
Expected: PASS — 25 tests OK. 실패하면 규칙 코드를 고친다(테스트를 고치지 않는다).

- [ ] **Step 5: 전체 테스트와 커밋**

Run: `python3 -m unittest discover -s tests`
Expected: `OK` (이전 작업의 테스트는 info를 제외하고 비교하므로 `I202`가 늘어도 깨지지 않는다)

```bash
git add tools/datacheck/rules_domain.py tools/datacheck/validate.py tests/test_domain.py
git commit -m "feat: 파일별·교차 검증(E106 E107 W101~W106 I201 I202)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 5: 손윤곽 GeoJSON 검증 (E108)

**Files:**
- Modify: `tools/datacheck/rules_domain.py` (함수 추가, `DOMAIN_CHECKS`에 항목 추가)
- Test: `tests/test_geometry.py`

**Interfaces:**
- Consumes: Task 2의 `read_geojson_table`이 만든 표(행 = Feature properties + 자동 `region_slug`)와 `res.features`, Task 3의 행 규칙(속성의 E101~E105는 이미 적용됨), Task 4의 `DOMAIN_CHECKS`.
- Produces: `datacheck.rules_domain.check_geometry(res, spec, today)`(격리되지 않은 Feature의 geometry를 검사해 E108), `GEO = "geometry_overrides.geojson"`.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_geometry.py`:

```python
import json
import tempfile
import unittest

from helpers import SPEC, TODAY, make_region, rules_of
from datacheck.validate import validate_region

GEO = "geometry_overrides.geojson"


def square(lon=126.78, lat=35.15, size=0.001):
    return [[lon, lat], [lon + size, lat], [lon + size, lat + size], [lon, lat + size], [lon, lat]]


def feature(ring=None, geometry=None, **props):
    p = dict(project_id="z1-A1", dong_no="", tier="schematic", basis="LH 팸플릿 단지배치도",
             source_id="src-a", observed_at="2026-10-04")
    p.update(props)
    return {"type": "Feature", "properties": p,
            "geometry": geometry or {"type": "Polygon", "coordinates": [ring or square()]}}


def run(features=None, raw=None):
    with tempfile.TemporaryDirectory() as tmp:
        d = make_region(tmp)
        if raw is not None:
            (d / GEO).write_bytes(raw)
        elif features is not None:
            (d / GEO).write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
        return validate_region(d, SPEC, TODAY)


class GeometryRules(unittest.TestCase):
    def test_valid_polygon_and_multipolygon(self):
        multi = {"type": "MultiPolygon", "coordinates": [[square()], [square(126.79)]]}
        res = run([feature(), feature(geometry=multi, dong_no="101")])
        self.assertEqual(rules_of(res, "error"), [])
        self.assertEqual(len(res.features), 2)

    def test_empty_feature_collection_is_fine(self):
        res = run([])
        self.assertEqual(rules_of(res, "error"), [])
        self.assertEqual(res.tables[GEO].rows, [])

    def test_e108_bad_geometry(self):
        p0, p1, p2 = square()[:3]
        cases = {
            "닫히지 않은 링": feature(ring=square()[:4]),
            "점 4개 미만": feature(ring=[p0, p1, p0]),
            "한국 범위 밖": feature(ring=square(lon=140.0)),
            "점 타입": feature(geometry={"type": "Point", "coordinates": [126.78, 35.15]}),
            "구조 이상": feature(geometry={"type": "Polygon", "coordinates": [[["x", "y"], p1, p2, ["x", "y"]]]}),
        }
        for label, f in cases.items():
            with self.subTest(label):
                res = run([f])
                self.assertIn("E108", rules_of(res, "error"))
                self.assertTrue(res.is_quarantined(GEO, 1))

    def test_bad_feature_is_quarantined_but_good_one_stays(self):
        res = run([feature(ring=square(lon=140.0)), feature(dong_no="102")])
        self.assertTrue(res.is_quarantined(GEO, 1))
        self.assertFalse(res.is_quarantined(GEO, 2))

    def test_property_errors_use_the_generic_rules(self):
        cases = [("E101", dict(basis="")), ("E103", dict(tier="exact")),
                 ("E105", dict(project_id="nope")), ("E102", dict(observed_at="2026-13-40"))]
        for rule, props in cases:
            with self.subTest(rule):
                self.assertIn(rule, rules_of(run([feature(**props)]), "error"))

    def test_e104_same_project_and_dong_twice(self):
        res = run([feature(), feature()])
        [issue] = [i for i in res.issues if i.rule == "E104"]
        self.assertEqual((issue.file, issue.row), (GEO, 2))

    def test_w001_unknown_property(self):
        res = run([feature(memo="메모")])
        self.assertIn("W001", rules_of(res, "warn"))

    def test_e002_when_file_is_not_valid_json_or_not_a_feature_collection(self):
        for label, raw in (("깨진 JSON", b"{not json"), ("다른 GeoJSON", b'{"type": "Feature"}')):
            with self.subTest(label):
                res = run(raw=raw)
                self.assertIn("E002", rules_of(res, "error"))
                self.assertIn(GEO, res.rejected_files)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m unittest discover -s tests -p "test_geometry.py" -v`
Expected: FAIL — `test_e108_bad_geometry` 등에서 `AssertionError: 'E108' not found` (나머지 일부는 이미 통과할 수 있다)

- [ ] **Step 3: 구현한다**

`tools/datacheck/rules_domain.py`에서 `DOMAIN_CHECKS` 정의 **바로 위**에 아래 함수들을 추가하고, `DOMAIN_CHECKS`를 교체한다.

추가:

```python
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
```

교체(`DOMAIN_CHECKS`):

```python
DOMAIN_CHECKS = {
    "events.csv": check_events,
    "dongs.csv": check_dongs,
    "projects.csv": check_projects,
    GEO: check_geometry,
}
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m unittest discover -s tests -p "test_geometry.py" -v`
Expected: PASS — 8 tests OK

- [ ] **Step 5: 전체 테스트와 커밋**

Run: `python3 -m unittest discover -s tests`
Expected: `OK`

```bash
git add tools/datacheck/rules_domain.py tests/test_geometry.py
git commit -m "feat: 손윤곽 GeoJSON 검증(E108)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 리포트·ZIP·명령줄 (`validate_input.py`)

**Files:**
- Modify: `tools/datacheck/readers.py` (`extract_zip`, `find_region_dirs` 추가, import 보강)
- Create: `tools/datacheck/report.py`
- Create: `tools/datacheck/cli.py`
- Create: `tools/validate_input.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 2~5의 `validate_region`, `RegionResult`(필드 `issues`, `quarantined`, `tables`, `features`, `scope`, `rejected`), `Spec`.
- Produces:
  - `datacheck.readers.extract_zip(zip_path, dest) -> Path`(dest 밖으로 나가는 경로가 있으면 아무것도 풀지 않고 `ValueError`), `datacheck.readers.find_region_dirs(base, file_names: set[str], fallback_slug=None) -> list[tuple[str, Path]]`(`(slug, 경로)` 목록. `base` 자체에 규격 파일이 있으면 `fallback_slug or base.name` 하나, 아니면 깊이 2까지 하위 폴더 탐색, `.`·`_`로 시작하는 폴더와 `__MACOSX` `quarantine` `validation_out` 무시).
  - `datacheck.report.build_report(results, spec, today, input_label) -> dict`, `render_markdown(report) -> str`, `write_report(report, results, out_dir)`(`validation_report.json`, `validation_report.md`, `quarantine/<slug>/<파일>` 작성, 기존 `quarantine/`는 지움), `exit_code(report, strict) -> int`.
  - `datacheck.cli.main(argv=None) -> int`. 옵션: `path`, `--out`(기본 `validation_out`), `--today YYYY-MM-DD`, `--strict`, `--spec`(숨김).
  - 보고서 JSON 구조: `{"schema_version", "validated_on", "input", "summary": {"error","warn","info","regions","regions_rejected"}, "regions": [{"slug","rejected","counts": {파일: {"rows","quarantined"}}, "scope": {...}}], "issues": [{"rule","severity","region","file","row","message"}]}`.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_cli.py`:

```python
import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from helpers import make_region
from datacheck.cli import main


def run_main(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(argv)
    return code, out.getvalue()


def cli(*args):
    """검증일을 2026-10-04로 고정해 main을 실행한다. (종료 코드, 출력)을 돌려준다."""
    return run_main([*map(str, args), "--today", "2026-10-04"])


def load(out_dir):
    return json.loads((Path(out_dir) / "validation_report.json").read_text(encoding="utf-8"))


def zip_region(zip_path, region_dir, prefix, extras=()):
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in sorted(Path(region_dir).iterdir()):
            zf.write(f, f"{prefix}{f.name}")
        for name, data in extras:
            zf.writestr(name, data)


def set_first(**kw):
    return lambda rows: rows[0].update(kw)


class CliTest(unittest.TestCase):
    def test_valid_folder_exits_0_and_writes_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            region, out = make_region(tmp), Path(tmp) / "out"
            code, text = cli(region, "--out", out)
            report = load(out)
            self.assertEqual(code, 0)
            self.assertEqual(report["summary"]["error"], 0)
            self.assertEqual([r["slug"] for r in report["regions"]], ["test-region"])
            self.assertFalse(report["regions"][0]["rejected"])
            self.assertEqual(report["regions"][0]["scope"]["public"], 1)
            md = (out / "validation_report.md").read_text(encoding="utf-8")
            self.assertIn("## test-region", md)
            self.assertIn("I202", md)
            self.assertIn("test-region", text)

    def test_error_exits_1_and_region_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            region, out = make_region(tmp, drop=("events.csv",)), Path(tmp) / "out"
            code, _ = cli(region, "--out", out)
            report = load(out)
            self.assertEqual(code, 1)
            self.assertTrue(report["regions"][0]["rejected"])
            self.assertIn("E001", [i["rule"] for i in report["issues"]])

    def test_strict_turns_warnings_into_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            region, out = make_region(tmp, edits={"projects.csv": set_first(units="500")}), Path(tmp) / "out"
            self.assertEqual(cli(region, "--out", out)[0], 0)
            self.assertIn("W104", [i["rule"] for i in load(out)["issues"]])
            self.assertEqual(cli(region, "--out", out, "--strict")[0], 1)

    def test_usage_errors_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty, afile = Path(tmp) / "empty", Path(tmp) / "a.txt"
            empty.mkdir()
            afile.write_text("x")
            self.assertEqual(cli(Path(tmp) / "nope")[0], 2)  # 경로 없음
            self.assertEqual(cli(empty)[0], 2)  # 지역 폴더를 찾지 못함
            self.assertEqual(cli(afile)[0], 2)  # .zip이 아닌 파일
            region = make_region(Path(tmp) / "r")
            code, text = run_main([str(region), "--today", "not-a-date"])
            self.assertEqual(code, 2)
            self.assertIn("--today", text)

    def test_quarantine_files_are_written_and_stale_ones_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            bad = make_region(Path(tmp) / "a", edits={"projects.csv": set_first(project_name="")})
            cli(bad, "--out", out)
            q = out / "quarantine" / "test-region" / "projects.csv"
            text = q.read_text(encoding="utf-8-sig")
            self.assertIn("_rule", text.splitlines()[0])
            self.assertIn("E101", text)
            good = make_region(Path(tmp) / "b")
            cli(good, "--out", out)
            self.assertFalse((out / "quarantine").exists())

    def test_quarantined_geojson_feature_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            region = make_region(tmp)
            bad = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [126.78, 35.15]},
                   "properties": {"project_id": "z1-A1", "tier": "schematic", "basis": "x",
                                  "source_id": "src-a", "observed_at": "2026-10-04"}}
            (region / "geometry_overrides.geojson").write_text(
                json.dumps({"type": "FeatureCollection", "features": [bad]}), encoding="utf-8")
            cli(region, "--out", out)
            data = json.loads((out / "quarantine" / "test-region" / "geometry_overrides.geojson").read_text(encoding="utf-8"))
            self.assertEqual(data["features"][0]["properties"]["_issues"][0]["rule"], "E108")

    def test_two_regions_one_broken_still_reports_the_other(self):  # Review Focus 5
        with tempfile.TemporaryDirectory() as tmp:
            parent, out = Path(tmp) / "input", Path(tmp) / "out"
            make_region(parent, slug="test-region")
            make_region(parent, slug="broken-region", drop=("events.csv",))
            code, _ = cli(parent, "--out", out)
            report = load(out)
            by_slug = {r["slug"]: r for r in report["regions"]}
            self.assertEqual(code, 1)
            self.assertFalse(by_slug["test-region"]["rejected"])
            self.assertTrue(by_slug["broken-region"]["rejected"])
            self.assertEqual(report["summary"]["regions"], 2)
            self.assertEqual(report["summary"]["regions_rejected"], 1)
            self.assertEqual(by_slug["test-region"]["scope"]["public"], 1)

    def test_zip_from_macos_with_noise_and_top_folder(self):  # Review Focus 4
        with tempfile.TemporaryDirectory() as tmp:
            region, out, zp = make_region(Path(tmp) / "src"), Path(tmp) / "out", Path(tmp) / "submit.zip"
            zip_region(zp, region, "input/test-region/",
                       extras=[("__MACOSX/input/test-region/._regions.csv", "junk"), ("input/.DS_Store", "junk")])
            code, _ = cli(zp, "--out", out)
            self.assertEqual(code, 0)
            self.assertEqual([r["slug"] for r in load(out)["regions"]], ["test-region"])

    def test_zip_with_files_at_root_uses_zip_name_as_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            region, out, zp = make_region(Path(tmp) / "src"), Path(tmp) / "out", Path(tmp) / "test-region.zip"
            zip_region(zp, region, "")
            code, _ = cli(zp, "--out", out)
            self.assertEqual(code, 0)
            self.assertEqual([r["slug"] for r in load(out)["regions"]], ["test-region"])

    def test_zip_slip_is_refused_with_exit_2(self):  # Review Focus 4
        with tempfile.TemporaryDirectory() as tmp:
            zp = Path(tmp) / "evil.zip"
            with zipfile.ZipFile(zp, "w") as zf:
                zf.writestr("../evil.txt", "x")
            code, text = cli(zp, "--out", Path(tmp) / "out")
            self.assertEqual(code, 2)
            self.assertIn("안전하지 않은", text)
            self.assertFalse((Path(tmp) / "evil.txt").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m unittest discover -s tests -p "test_cli.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'datacheck.cli'`

- [ ] **Step 3: 읽기 보강, 리포트, 명령줄을 구현한다**

`tools/datacheck/readers.py` 맨 위 import에 `os` 대신 아래를 맞춰 추가하고(`zipfile` 추가), 파일 끝에 함수 두 개를 추가한다.

import 블록을 이렇게 교체:

```python
import csv
import io
import json
import zipfile
from pathlib import Path

from .model import Row, Table

IGNORED_DIRS = {"__MACOSX", "quarantine", "validation_out"}
```

파일 끝에 추가:

```python
def extract_zip(zip_path: Path | str, dest: Path | str) -> Path:
    """ZIP을 dest에 푼다. dest 밖으로 나가는 경로가 하나라도 있으면 아무것도 풀지 않고 ValueError."""
    dest = Path(dest).resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            target = (dest / info.filename).resolve()
            if target != dest and dest not in target.parents:
                raise ValueError(f"안전하지 않은 경로가 들어 있음: {info.filename}")
        zf.extractall(dest)
    return dest


def find_region_dirs(base: Path | str, file_names: set[str], fallback_slug: str | None = None,
                     depth: int = 2) -> list[tuple[str, Path]]:
    """지역 폴더 (slug, 경로) 목록을 찾는다.

    base 자체에 규격 파일이 있으면 그 폴더가 지역이고 slug는 fallback_slug(없으면 폴더 이름)이다.
    아니면 하위 폴더를 depth 단계까지 찾는다. 숨김·`_` 시작·잡음 폴더는 무시한다.
    """
    base = Path(base)
    if any((base / name).exists() for name in file_names):
        return [(fallback_slug or base.name, base)]
    if depth == 0:
        return []
    found: list[tuple[str, Path]] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.name.startswith((".", "_")) or child.name in IGNORED_DIRS:
            continue
        found += find_region_dirs(child, file_names, None, depth - 1)
    return found
```

`tools/datacheck/report.py`:

```python
"""검증 결과를 JSON·Markdown 리포트와 격리 파일로 쓴다."""
from __future__ import annotations

import csv
import json
import shutil
from collections import Counter
from datetime import date
from pathlib import Path

from .model import RegionResult
from .spec import Spec

MAX_ISSUES_PER_REGION = 200
SEVERITY_RANK = {"error": 0, "warn": 1, "info": 2}


def build_report(results: list[RegionResult], spec: Spec, today: date, input_label: str) -> dict:
    issues = [i.as_dict() for r in results for i in r.issues]
    severity = Counter(i["severity"] for i in issues)
    regions = []
    for r in results:
        counts = {name: {"rows": len(t.rows), "quarantined": len(r.quarantined.get(name, {}))}
                  for name, t in r.tables.items()}
        regions.append({"slug": r.slug, "rejected": r.rejected, "counts": counts, "scope": r.scope})
    return {
        "schema_version": spec.schema_version,
        "validated_on": today.isoformat(),
        "input": input_label,
        "summary": {
            "error": severity["error"], "warn": severity["warn"], "info": severity["info"],
            "regions": len(results), "regions_rejected": sum(1 for r in results if r.rejected),
        },
        "regions": regions,
        "issues": issues,
    }


def render_markdown(report: dict) -> str:
    s = report["summary"]
    lines = [
        "# 입력 검증 리포트", "",
        f"- 검증일: {report['validated_on']}",
        f"- 입력: {report['input']}",
        f"- 규격 버전: {report['schema_version']}",
        f"- 결과: error {s['error']} · warn {s['warn']} · info {s['info']} "
        f"(지역 {s['regions']}개, 거부 {s['regions_rejected']}개)",
        "",
        "행 번호는 헤더를 뺀 데이터 행의 순번이다(스프레드시트에서는 번호 + 1행).", "",
    ]
    for reg in report["regions"]:
        lines += [f"## {reg['slug']} — {'거부' if reg['rejected'] else '검증 완료'}", ""]
        if reg["counts"]:
            lines += ["| 파일 | 행 | 격리 |", "|---|---|---|"]
            lines += [f"| {n} | {c['rows']} | {c['quarantined']} |" for n, c in reg["counts"].items()]
            lines.append("")
        if reg["scope"]:
            sc = reg["scope"]
            lines += [f"지도에 올라가는 단지: 공공 {sc['public']} · 공공택지 민간 {sc['private_on_public_land']} · "
                      f"범위 밖 {sc['out_of_scope']} · 시행자 미확인(제외) {sc['unknown']}", ""]
        issues = sorted((i for i in report["issues"] if i["region"] == reg["slug"]),
                        key=lambda i: (SEVERITY_RANK[i["severity"]], i["rule"], i["file"], i["row"] or 0))
        if issues:
            lines += ["| 규칙 | 심각도 | 파일 | 행 | 내용 |", "|---|---|---|---|---|"]
            for i in issues[:MAX_ISSUES_PER_REGION]:
                message = i["message"].replace("|", "\\|")
                lines.append(f"| {i['rule']} | {i['severity']} | {i['file']} | {i['row'] or ''} | {message} |")
            if len(issues) > MAX_ISSUES_PER_REGION:
                lines.append(f"\n(이하 {len(issues) - MAX_ISSUES_PER_REGION}건 생략 — validation_report.json 참고)")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _write_quarantine(results: list[RegionResult], root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)  # 이전 실행의 찌꺼기를 남기지 않는다
    for res in results:
        for name, by_row in res.quarantined.items():
            table = res.tables.get(name)
            if table is None:
                continue
            dest = root / res.slug
            dest.mkdir(parents=True, exist_ok=True)
            if name.endswith(".geojson"):
                features = []
                for n in sorted(by_row):
                    feature = dict(res.features[n - 1])
                    props = dict(feature.get("properties") or {})
                    props["_issues"] = [{"rule": i.rule, "message": i.message} for i in by_row[n]]
                    feature["properties"] = props
                    features.append(feature)
                (dest / name).write_text(
                    json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
            else:
                with open(dest / name, "w", encoding="utf-8-sig", newline="") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(table.header + ["_rule", "_message"])
                    for row in table.rows:
                        if row.n in by_row:
                            issues = by_row[row.n]
                            writer.writerow([row.get(h) for h in table.header]
                                            + [";".join(sorted({i.rule for i in issues})),
                                               " | ".join(i.message for i in issues)])


def write_report(report: dict, results: list[RegionResult], out_dir: Path | str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "validation_report.md").write_text(render_markdown(report), encoding="utf-8")
    _write_quarantine(results, out / "quarantine")


def exit_code(report: dict, strict: bool) -> int:
    s = report["summary"]
    return 1 if s["error"] or (strict and s["warn"]) else 0
```

`tools/datacheck/cli.py`:

```python
"""명령줄 진입점."""
from __future__ import annotations

import argparse
import tempfile
import zipfile
from datetime import date
from pathlib import Path

from .readers import extract_zip, find_region_dirs
from .report import build_report, exit_code, write_report
from .spec import SPEC_PATH, load_spec
from .validate import validate_region


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="validate_input", description="팀원이 제출한 입력(폴더 또는 ZIP)을 검증한다.")
    ap.add_argument("path", help="입력 폴더 또는 ZIP")
    ap.add_argument("--out", default="validation_out", help="리포트를 쓸 폴더 (기본: ./validation_out)")
    ap.add_argument("--today", help="검증일 YYYY-MM-DD (기본: 오늘)")
    ap.add_argument("--strict", action="store_true", help="warn이 있어도 종료 코드 1")
    ap.add_argument("--spec", default=str(SPEC_PATH), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        print(f"오류: --today 형식이 올바르지 않음: {args.today} (예: 2026-10-04)")
        return 2
    src = Path(args.path)
    if not src.exists():
        print(f"오류: 경로가 없음: {src}")
        return 2
    spec = load_spec(args.spec)

    with tempfile.TemporaryDirectory() as tmp:
        fallback = None
        base = src
        if src.is_file():
            if src.suffix.lower() != ".zip":
                print("오류: 폴더 또는 .zip 파일을 넘겨 주세요")
                return 2
            try:
                base = extract_zip(src, Path(tmp))
            except (ValueError, zipfile.BadZipFile) as e:
                print(f"오류: ZIP을 열 수 없음: {e}")
                return 2
            fallback = src.stem  # ZIP 최상위에 파일이 바로 있으면 ZIP 이름이 지역 이름
        regions = find_region_dirs(base, set(spec.files), fallback)
        if not regions:
            print("오류: 지역 폴더를 찾지 못함 (regions.csv 등이 든 폴더가 있어야 함)")
            return 2
        results = [validate_region(path, spec, today, slug=slug) for slug, path in regions]
        report = build_report(results, spec, today, str(src))
        write_report(report, results, Path(args.out))

    for reg in report["regions"]:
        print(f"{'거부' if reg['rejected'] else '완료'}  {reg['slug']}")
    s = report["summary"]
    print(f"error {s['error']} · warn {s['warn']} · info {s['info']}")
    print(f"리포트: {Path(args.out) / 'validation_report.md'}")
    return exit_code(report, args.strict)
```

`tools/validate_input.py`:

```python
#!/usr/bin/env python3
"""입력 규격 검증기. 사용법: docs/data-interface/정의서.md 11절.

  python3 tools/validate_input.py <폴더 또는 ZIP> [--out 리포트폴더] [--today YYYY-MM-DD] [--strict]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from datacheck.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m unittest discover -s tests -p "test_cli.py" -v`
Expected: PASS — 10 tests OK

직접 실행도 확인한다(검증기 파일을 하나 만들어 보는 대신 테스트가 쓰는 도구로 샘플 폴더를 만든다):

Run: `python3 -c "import sys; sys.path.insert(0,'tests'); import helpers, tempfile; print(helpers.make_region(tempfile.mkdtemp()))"`
Expected: 임시 지역 폴더 경로가 출력된다.
그 경로를 `<경로>`로 두고 Run: `python3 tools/validate_input.py <경로> --out "$(mktemp -d)" --today 2026-10-04; echo "exit=$?"`
Expected: `완료  test-region` / `error 0 · warn 0 · info 1` / `exit=0`

- [ ] **Step 5: 전체 테스트와 커밋**

Run: `python3 -m unittest discover -s tests`
Expected: `OK`

```bash
git add tools/datacheck/readers.py tools/datacheck/report.py tools/datacheck/cli.py tools/validate_input.py tests/test_cli.py
git commit -m "feat: 검증 리포트·ZIP 입력·명령줄(validate_input.py)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 7: 문서 생성기 (`gen_docs.py`)와 CSV 템플릿

**Files:**
- Create: `tools/gen_docs.py`
- Create: `docs/data-interface/정의서.md` (이 작업에서는 생성 구간 표지만 든 뼈대. Task 8에서 본문으로 교체)
- Create (생성물): `docs/data-interface/templates/{regions,region_codes,sources,zones,projects,events,dongs}.csv`, `docs/data-interface/templates/geometry_overrides.geojson`
- Test: `tests/test_gen_docs.py`

**Interfaces:**
- Consumes: Task 1의 `Spec`, `Column`, `load_spec`.
- Produces: `gen_docs.render_templates(spec) -> dict[str, str]`(파일 이름 → 내용. CSV는 BOM + 헤더 한 줄, GeoJSON은 빈 FeatureCollection), `render_field_tables(spec) -> str`, `render_enums(spec) -> str`, `inject(text, name, content) -> str`(`<!-- GENERATED:<name>:BEGIN -->`과 `END` 사이를 교체, 표지가 없으면 `ValueError`), `type_label(col) -> str`, `expected_files(spec, doc_text) -> dict[Path, str]`, `main(argv=None) -> int`(`--check`면 최신이 아닐 때 1). 상수 `DOC`, `TEMPLATES`.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_gen_docs.py`:

```python
import unittest

from helpers import SPEC
import gen_docs


class GenDocs(unittest.TestCase):
    def test_csv_templates_are_header_only_with_bom(self):
        templates = gen_docs.render_templates(SPEC)
        text = templates["projects.csv"]
        self.assertTrue(text.startswith("﻿region_slug,project_id,zone_id,project_name"))
        self.assertEqual(text.count("\n"), 1)
        self.assertEqual(sorted(templates), sorted(SPEC.files))

    def test_geojson_template_is_an_empty_feature_collection(self):
        text = gen_docs.render_templates(SPEC)["geometry_overrides.geojson"]
        self.assertIn('"type": "FeatureCollection"', text)
        self.assertIn('"features": []', text)

    def test_field_tables_list_every_file_and_column(self):
        md = gen_docs.render_field_tables(SPEC)
        for name, fs in SPEC.files.items():
            self.assertIn(f"#### {name}", md)
            for c in fs.columns:
                self.assertIn(f"| `{c.name}` |", md)
        self.assertIn("참조:", md)

    def test_required_columns_are_marked(self):
        md = gen_docs.render_field_tables(SPEC)
        self.assertIn("| `project_id` | ● |", md)
        self.assertIn("| `zone_id` |  |", md)

    def test_enum_table_lists_every_value(self):
        md = gen_docs.render_enums(SPEC)
        for name, values in SPEC.enums.items():
            self.assertIn(f"`{name}`", md)
            for v in values:
                self.assertIn(v, md)

    def test_type_label(self):
        floors = SPEC.files["dongs.csv"].columns[3]
        self.assertEqual(floors.name, "floors_above")
        self.assertEqual(gen_docs.type_label(floors), "정수 0~120")
        sponsor = [c for c in SPEC.files["projects.csv"].columns if c.name == "sponsor_type"][0]
        self.assertEqual(gen_docs.type_label(sponsor), "열거 (sponsor_type)")

    def test_inject_replaces_between_markers_and_is_idempotent(self):
        text = "머리\n<!-- GENERATED:x:BEGIN -->\n옛 내용\n<!-- GENERATED:x:END -->\n꼬리\n"
        once = gen_docs.inject(text, "x", "새 내용\n")
        self.assertEqual(once, "머리\n<!-- GENERATED:x:BEGIN -->\n새 내용\n<!-- GENERATED:x:END -->\n꼬리\n")
        self.assertEqual(gen_docs.inject(once, "x", "새 내용\n"), once)

    def test_inject_without_markers_raises(self):
        with self.assertRaises(ValueError):
            gen_docs.inject("표지 없음", "x", "내용\n")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m unittest discover -s tests -p "test_gen_docs.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gen_docs'`

- [ ] **Step 3: 생성기와 문서 뼈대를 만든다**

`tools/gen_docs.py`:

```python
#!/usr/bin/env python3
"""schemas/input.spec.json 에서 정의서의 필드표·코드표와 CSV 템플릿을 만든다.

  python3 tools/gen_docs.py          # 파일을 갱신한다
  python3 tools/gen_docs.py --check  # 커밋된 파일과 다르면 종료 코드 1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from datacheck.spec import Column, Spec, load_spec  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DOC_DIR = ROOT / "docs" / "data-interface"
DOC = DOC_DIR / "정의서.md"
TEMPLATES = DOC_DIR / "templates"
BEGIN = "<!-- GENERATED:{name}:BEGIN -->"
END = "<!-- GENERATED:{name}:END -->"

TYPE_LABEL = {
    "text": "문자", "slug": "slug(소문자·숫자·하이픈)", "int": "정수", "number": "숫자",
    "date": "날짜 YYYY-MM-DD", "date_or_month": "날짜 YYYY-MM-DD (move_in은 YYYY-MM 허용)",
    "yn": "Y/N", "pnu_list": "19자리 숫자 목록(;로 구분)", "url": "URL(http/https)",
    "code": "숫자 2·5·8~10자리", "lon": "경도 124~132", "lat": "위도 33~39",
}


def type_label(col: Column) -> str:
    if col.type == "enum":
        return f"열거 ({col.enum})"
    label = TYPE_LABEL[col.type]
    if col.min is not None or col.max is not None:
        lo = "" if col.min is None else f"{col.min:g}"
        hi = "" if col.max is None else f"{col.max:g}"
        label += f" {lo}~{hi}"
    return label


def render_templates(spec: Spec) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, fs in spec.files.items():
        if fs.kind == "geojson":
            out[name] = '{\n  "type": "FeatureCollection",\n  "features": []\n}\n'
        else:
            out[name] = "﻿" + ",".join(fs.column_names) + "\n"  # BOM: 엑셀에서 한글이 깨지지 않게
    return out


def render_field_tables(spec: Spec) -> str:
    lines: list[str] = []
    for name, fs in spec.files.items():
        lines += [f"#### {name} ({'필수 파일' if fs.required_file else '선택 파일'})", "", fs.description, "",
                  "| 열 | 필수 | 형식 | 설명 |", "|---|---|---|---|"]
        for c in fs.columns:
            lines.append(f"| `{c.name}` | {'●' if c.required else ''} | {type_label(c)} | {c.desc} |")
        lines += ["", "기본키: " + ", ".join(f"`{k}`" for k in fs.primary_key)]
        for r in fs.refs:
            cols = ", ".join(f"`{c}`" for c in r.columns)
            note = f" ({r.optional_column}가 비어 있으면 생략)" if r.optional_column else ""
            lines.append(f"참조: {cols} → {r.to}{note}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_enums(spec: Spec) -> str:
    lines = ["| 코드표 | 허용 값 |", "|---|---|"]
    for name, values in spec.enums.items():
        lines.append(f"| `{name}` | {', '.join(values)} |")
    lines += ["", "공공택지로 치는 `zone_type`: " + ", ".join(spec.public_land_zone_types)]
    return "\n".join(lines) + "\n"


def inject(text: str, name: str, content: str) -> str:
    begin, end = BEGIN.format(name=name), END.format(name=name)
    i = text.index(begin) + len(begin)  # 표지가 없으면 ValueError
    j = text.index(end)
    return text[:i] + "\n" + content + text[j:]


def expected_files(spec: Spec, doc_text: str) -> dict[Path, str]:
    files = {TEMPLATES / name: content for name, content in render_templates(spec).items()}
    text = inject(doc_text, "fields", render_field_tables(spec))
    files[DOC] = inject(text, "enums", render_enums(spec))
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="정의서 생성 구간과 CSV 템플릿을 명세에서 만든다.")
    ap.add_argument("--check", action="store_true", help="파일을 쓰지 않고 최신인지만 검사")
    args = ap.parse_args(argv)
    if not DOC.exists():
        print(f"오류: {DOC} 가 없음")
        return 2
    expected = expected_files(load_spec(), DOC.read_text(encoding="utf-8"))
    stale = [p for p, content in expected.items() if not p.exists() or p.read_text(encoding="utf-8") != content]
    if args.check:
        if stale:
            print("최신이 아님:\n  " + "\n  ".join(str(p.relative_to(ROOT)) for p in stale))
            print("python3 tools/gen_docs.py 를 실행해 갱신하세요")
            return 1
        print("정의서와 템플릿이 모두 최신입니다")
        return 0
    for path, content in expected.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print(f"{len(expected)}개 파일을 갱신했습니다 (바뀐 것 {len(stale)}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`docs/data-interface/정의서.md`(뼈대):

```markdown
# 주택파동 공급 지도 — 데이터 인터페이스 정의서

<!-- GENERATED:fields:BEGIN -->
<!-- GENERATED:fields:END -->

<!-- GENERATED:enums:BEGIN -->
<!-- GENERATED:enums:END -->
```

- [ ] **Step 4: 통과를 확인하고 템플릿을 생성한다**

Run: `python3 -m unittest discover -s tests -p "test_gen_docs.py" -v`
Expected: PASS — 8 tests OK

Run: `python3 tools/gen_docs.py && python3 tools/gen_docs.py --check`
Expected: `9개 파일을 갱신했습니다 (바뀐 것 9개)` 다음 `정의서와 템플릿이 모두 최신입니다`

Run: `ls docs/data-interface/templates`
Expected: `dongs.csv events.csv geometry_overrides.geojson projects.csv region_codes.csv regions.csv sources.csv zones.csv` (8개)

- [ ] **Step 5: 전체 테스트와 커밋**

Run: `python3 -m unittest discover -s tests`
Expected: `OK`

```bash
git add tools/gen_docs.py tests/test_gen_docs.py docs/data-interface/정의서.md docs/data-interface/templates
git commit -m "feat: 명세에서 정의서 필드표와 CSV 템플릿 생성" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: 정의서 본문과 팀원용 README

**Files:**
- Modify: `docs/data-interface/정의서.md` (전체 교체)
- Create: `docs/data-interface/README.md`
- Modify: `tests/test_gen_docs.py` (테스트 2개 추가)

**Interfaces:**
- Consumes: Task 7의 `gen_docs.inject`, `gen_docs.main`, `gen_docs.DOC`(생성 구간 표지 `fields`·`enums`).
- Produces: 완성된 정의서(0~11절 + 부록 A~C). 3.2절과 부록 B의 표는 생성 구간이다.

- [ ] **Step 1: 실패하는 테스트를 추가한다**

`tests/test_gen_docs.py`의 `if __name__ == "__main__":` 줄 위에 다음 클래스를 추가한다:

```python
class RepoDocs(unittest.TestCase):
    def test_repo_docs_and_templates_are_up_to_date(self):
        self.assertEqual(gen_docs.main(["--check"]), 0)

    def test_definition_has_all_sections_and_markers(self):
        text = gen_docs.DOC.read_text(encoding="utf-8")
        for heading in ["## 0. 개요·범위·용어", "## 1. 데이터 흐름과 책임", "## 2. 공통 규약", "## 3. 입력 표 정의",
                        "## 4. 이벤트와 상태 계산 규칙", "## 5. 시행자 유형과 공공택지 판정",
                        "## 6. 윤곽 등급과 화면 표기", "## 7. 출력 번들 스키마", "## 8. 검증 규칙과 격리 목록",
                        "## 9. 품질 함정 체크리스트", "## 10. 버전과 변경 절차", "## 11. 제출 방법",
                        "## 부록 A", "## 부록 B", "## 부록 C"]:
            self.assertIn(heading, text)
        for name in ("fields", "enums"):
            self.assertIn(f"<!-- GENERATED:{name}:BEGIN -->", text)

    def test_every_rule_id_appears_in_the_definition(self):
        text = gen_docs.DOC.read_text(encoding="utf-8")
        for rule in "E001 E002 E003 E101 E102 E103 E104 E105 E106 E107 E108 W001 W101 W102 W103 W104 W105 W106 I201 I202".split():
            self.assertIn(f"| {rule} |", text, rule)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m unittest discover -s tests -p "test_gen_docs.py" -v`
Expected: FAIL — `test_definition_has_all_sections_and_markers`, `test_every_rule_id_appears_in_the_definition` 실패 (뼈대에는 절 제목과 규칙표가 없다)

- [ ] **Step 3: 정의서 본문을 쓴다**

`docs/data-interface/정의서.md`를 아래 내용으로 **전체 교체**한다.

````markdown
# 주택파동 공급 지도 — 데이터 인터페이스 정의서

- 규격 버전: **1.0.0** (`schemas/input.spec.json`의 `schema_version`과 같다)
- 읽는 분: 지도에 들어갈 데이터를 수집·정리해서 넘기는 분
- 한 줄 요약: 지역마다 폴더 하나에 아래 CSV 표를 담아 ZIP으로 보내 주세요. 검증기가 오류를 찾아 리포트로 돌려드립니다. 보내기 전에 같은 검증기를 직접 돌려 볼 수 있습니다(11절).

## 0. 개요·범위·용어

### 0.1 무엇을 위한 문서인가

주택파동 공급 지도는 공공주택의 공급 현황(공고, 승인, 착공, 공정율, 준공, 입주)을 지도 위에 보여 줍니다. 이 문서는 **여러분이 넘겨줄 데이터의 모양**을 정합니다. 지도에 그릴 윤곽(폴리곤)이나 단지의 진행 상태는 여러분이 만들지 않습니다. 사실(단지 정보, 일어난 사건, 출처)만 표로 넘기면 나머지는 파이프라인이 계산합니다.

### 0.2 범위

지도에 올라가는 단지는 두 종류입니다.

1. 공공이 시행하는 주택(LH·SH·GH·지자체공사 등의 공공분양, 신혼희망타운, 공공임대, 행복주택 등)
2. **공공택지 위에서 민간이 짓는 주택**. 지도에서 회색 톤으로 구분해 보여 줍니다. 공공택지는 `택지개발`, `공공주택지구`, `혁신도시`, `신도시` 지구를 말하고 도시개발·산업단지는 포함하지 않습니다.

### 0.3 용어

| 용어 | 뜻 |
|---|---|
| 지역(region) | 시군구 하나. 예: 광주 광산구. 폴더 하나가 지역 하나 |
| 지구(zone) | 지역 안의 개발 구역. 예: 광주선운2 공공주택지구 |
| 단지(project) | 지구 안의 블록 하나에 짓는 주택 단지. 예: 선운2 A-1블록 |
| 동 | 단지 안의 건물 한 채 |
| 사건(event) | 단지에서 일어난 일(공고, 승인, 착공, 공정율, 사용검사, 입주). 날짜가 있다 |
| 시행자 | 사업을 시행하는 주체. 공고문·공사현황·공급기관명에 나온다 |
| 윤곽 등급 | 지도에 그린 윤곽의 정확도. 공식 / 실제 건물 / 근사 (6절) |
| 출처 | 값을 가져온 자료. `sources.csv`에 적고 다른 표가 `source_id`로 가리킨다 |
| 격리 | 오류가 있는 행을 지도 데이터에 넣지 않고 따로 돌려주는 것. 버리지 않는다 |

## 1. 데이터 흐름과 책임

```
여러분 ──(입력 규격: CSV·GeoJSON, 이 문서가 규범)──▶ 파이프라인 ──(출력 번들: JSON, 참고)──▶ 지도 화면
```

| 일 | 여러분 | 파이프라인 | 화면 |
|---|---|---|---|
| 단지·사건·동 사실을 모은다 | ● | | |
| 출처를 적는다(`source_id`, `observed_at`) | ● | | |
| 시행자 유형(`sponsor_type`)을 판단한다 | ● | | |
| 단지의 상태(계획~입주 단계)를 계산한다 | | ● | |
| 윤곽을 만든다(PNU·블록 이름 → 폴리곤) | | ● | |
| 공공택지 위인지 판정한다(`on_public_land`) | (알면 입력) | ● | |
| 입력을 검증하고 오류 행을 격리한다 | | ● (검증기) | |
| 지도를 그리고 필터를 제공한다 | | | ● |

**윤곽을 보낼 필요는 없습니다.** 손으로 그린 윤곽이 있을 때만 `geometry_overrides.geojson`으로 보냅니다. API 키도 필요 없습니다.

## 2. 공통 규약

| 항목 | 규칙 |
|---|---|
| 파일 | 지역마다 폴더 하나 `input/<region_slug>/`. 폴더 이름이 `region_slug`. 폴더 안 `regions.csv`는 **정확히 1행** |
| 인코딩 | **UTF-8**(BOM 허용). 엑셀에서는 "CSV UTF-8(쉼표로 분리)"로 저장. CSV는 RFC 4180, 첫 줄은 영문 snake_case 헤더 |
| 목록 값 | 한 칸에 여러 값은 세미콜론(`;`)으로 구분 |
| 날짜 | `YYYY-MM-DD`. `move_in` 사건만 `YYYY-MM`(월 단위)도 허용 |
| 좌표 | WGS84(EPSG:4326). GeoJSON은 `[경도, 위도]` 순서. 한국 범위는 경도 124~132, 위도 33~39 |
| 단위 | 면적 ㎡, 높이 m, 공정율 %(0~100, 소수 허용), 세대수·층수 정수 |
| 불리언 | `Y` / `N` |
| **미상과 0** | **모르는 값은 빈 칸, 0은 실제 0.** 건축HUB 같은 자료는 모르는 값을 0으로 주므로, 근거 없는 0은 빈 칸으로 바꿔서 넘긴다 |
| `region_slug` | 소문자 영문·숫자·하이픈. 권장 `<시도>-<시군구>`. 예 `incheon-gyeyang`, `jeonnam-naju`, `gwangju-gwangsan` |
| `zone_id` | 지역 안에서 유일한 slug. 예 `sunwoon2` |
| `project_id` | **지역 안에서 유일**하고 한 번 정하면 바꾸지 않는 문자열. 권장 `<zone_id>-<블록>`. 예 `sunwoon2-A1` |
| `block_label` | 지도에 짧게 보이는 이름. 예 `A-1`, `A6` (유일하지 않아도 됨) |
| 지역 코드 | 행에는 코드를 쓰지 않고 `region_slug`만 참조한다. 코드와 유효기간은 `region_codes.csv`에 둔다(전남·광주 통합으로 나주가 `46170`에서 `12170`으로 바뀐 사례 때문) |
| 행 번호 | 오류 리포트의 행 번호는 헤더를 뺀 데이터 행의 순번이다. 스프레드시트에서는 번호 + 1행 |

## 3. 입력 표 정의

### 3.1 파일 구성

```
input/<region_slug>/
  regions.csv           (필수) 지역 1행
  region_codes.csv      (필수) 지역 코드와 유효기간
  sources.csv           (필수) 출처
  zones.csv             (필수) 지구. 헤더만 있어도 됨
  projects.csv          (필수) 단지(블록)
  events.csv            (필수) 사건. 추가만 하고 수정·삭제하지 않음
  dongs.csv             (선택) 동
  geometry_overrides.geojson  (선택) 손으로 그린 윤곽
```

빈 템플릿은 `templates/`, 채워진 예는 `examples/`에 있습니다(부록 A).

### 3.2 필드표

아래 표는 `schemas/input.spec.json`에서 자동으로 만든 것입니다(`●`는 필수).

<!-- GENERATED:fields:BEGIN -->
<!-- GENERATED:fields:END -->

### 3.3 사건 종류

| `event_type` | 뜻 | `value` | 예정(`is_planned=Y`) 허용 |
|---|---|---|---|
| `notice` | 모집공고 | 공급 세대수(선택) | 아니오 |
| `permit_approved` | 사업(계획)승인 | 승인 세대수(선택) | 아니오 |
| `construction_start` | 착공 | | 예 |
| `progress` | 공정율 | **필수**, 0~100 | 아니오 |
| `completion_inspection` | 사용검사·사용승인 | | 예 |
| `move_in` | 입주 | | 예 (`YYYY-MM` 허용) |
| `structure_observed` | 건물이 실제로 관측됨 | 관측된 동 수(선택) | 아니오 |

같은 사건의 중복 판정 키는 `(region_slug, project_id, event_type, event_date, source_ref)`입니다. `source_ref`에 공고 ID·허가 관리번호처럼 원자료의 식별자를 적으면 같은 날 여러 건도 구분됩니다.

### 3.4 작성 요령

- **`projects.csv`**: 한 행이 블록 하나입니다. 같은 블록이 자료마다 다른 이름("A-1BL", "A-1블록", "A1")으로 나오면 `block_name_raw`에 원문을 적고 `block_label`은 하나로 통일합니다. 필지 번호(PNU)를 알면 `pnu_list`에 적어 주세요. 윤곽을 찾는 가장 정확한 열쇠입니다.
- **`events.csv`**: 상태 열은 없습니다. 일어난 일을 한 줄씩 적으면 됩니다. 예정일은 `is_planned=Y`로 표시합니다. 예: `move_in`, `2029-06`, `is_planned=Y`.
- **`dongs.csv`**: 동 번호와 층수·높이를 압니다. **열 이름이 아니라 아래 의미를 따릅니다.** `floors_above`는 지상, `floors_below`는 지하 층수입니다(9절 함정 1).
- **`sources.csv`**: `redistributable`은 그 자료의 가공 결과를 공개 사이트에 실어도 되는지입니다. 모르면 `unknown`. **`Y`가 아닌 출처의 데이터는 운영 사이트에 노출하지 않습니다.**

## 4. 이벤트와 상태 계산 규칙

여러분은 상태를 입력하지 않습니다. 파이프라인이 `suspect`(의심) 표시가 없는 이벤트만으로 아래 순서에 따라 **처음 맞는 규칙**으로 정합니다. 기준일은 계산하는 날입니다.

1. **입주 단계**: 실제(`is_planned=N`) `completion_inspection` 또는 `move_in`이 있다. 또는 `structure_observed`가 있고 `notice` 또는 실제 `permit_approved`가 있으며 아래 2·3에 해당하지 않는다.
2. **준공 임박**: 가장 최근 `progress` 값이 90 이상이고 `move_in`(예정 포함)이 기준일부터 3개월 안이다.
3. **건설 단계**: 실제 `construction_start`가 있거나 0보다 큰 `progress`가 있다.
4. **분양중**: 위에 해당하지 않고 `notice`가 있으며 가장 최근 공고일이 기준일로부터 12개월 안이다.
5. **계획**: 그 밖의 모든 단지(`permit_approved`만 있는 경우 포함).

변경허가 때문에 **준공 후에 찍힌 `permit_approved`는 상태 계산에서 무시**합니다. 계산 단위는 레코드가 아니라 단지입니다. 이 규칙을 바꿀 때는 정의서 버전을 올립니다.

## 5. 시행자 유형과 공공택지 판정

- **`sponsor_type`**은 시행자를 **직접 말하는 자료**(공고문, 공사현황, 마이홈의 공급기관명)로 정합니다. `public` 공공, `private` 민간, `joint` 민관 공동, `unknown` 미확인.
- 인허가 자료의 **세대 유형 호수**(공공임대·공공분양·민간분양 등)는 약한 증거입니다. 단독 근거로 쓰지 마세요. 인허가에서 "공공분양"으로 표기된 단지가 실제로는 민간 시행인 사례가 있습니다.
- **`on_public_land`**는 단지가 공공택지(`택지개발`·`공공주택지구`·`혁신도시`·`신도시` 지구) 위인지입니다. 비워 두면 단지의 `zone_id`가 가리키는 지구의 `zone_type`으로 파이프라인이 계산합니다. 알고 있으면 `Y`/`N`으로 적어 주세요(입력이 우선합니다).
- 지도에 올라가는 단지: `sponsor_type`이 `public` 또는 `joint`이거나, `private`이면서 공공택지 위인 단지. 공공도 아니고 공공택지 위도 아닌 민간 단지는 `I201`(범위 밖)로 목록에만 남고, `unknown`은 `W105`로 확인 목록에 올라 지도에서 제외됩니다.
- 지구 유형(`zone_type`)을 정하는 방법은 부록 C를 보세요.

## 6. 윤곽 등급과 화면 표기

| 등급 `tier` | 뜻 | 화면에 쓰는 문구 |
|---|---|---|
| `official` | 공식 블록·필지 윤곽 | "블록 윤곽은 공식 자료입니다" |
| `building` | 실제 건물 윤곽(준공 단지) | "동 윤곽은 실제 건물 자료입니다" |
| `schematic` | 근사·도식 배치 | "동 윤곽은 근사값(10~20 m)입니다" |

윤곽은 파이프라인이 PNU·블록 이름으로 찾아 등급과 함께 붙입니다. 손으로 그린 윤곽을 보낼 때는 `geometry_overrides.geojson`에 `tier`와 `basis`(그린 근거)를 적습니다.

## 7. 출력 번들 스키마 (참고)

이 절은 **참고**입니다. 여러분이 만들 파일이 아니라, 파이프라인이 입력으로 만들어 화면에 넘기는 파일의 모양입니다. 정본은 `schemas/bundle/*.schema.json`입니다.

| 파일 | 내용 |
|---|---|
| `regions/index.json` | 지역 목록. 각 지역의 `slug`, `name`, `visibility`(`public`/`preview`), `updatedAt`, `schema_version`, 기본 지역 표시. `dataBase`(데이터 기본 주소) |
| `regions/<slug>/region.json` | 지역 설정: 화면 제목, 시작 지도 위치(`view`), 지역 코드, 지구(`zones`, 공공택지 여부 포함), 출처(`sources`), 상태 순서 |
| `regions/<slug>/projects.json` | 단지 목록: `id`, `label`, `name`, `sponsor`, `sponsorClass`(`public`/`private_on_public_land`), `kind`, `status`, `units`, `progress`, `outline`(등급 포함), `dongs`, `events`, `flags` |
| `regions/<slug>/buildings.json` | 건물 윤곽 GeoJSON(높이 `eh`, 높이 출처 `src` 등) |
| `regions/<slug>/context.json` | 지하철역·학교 위치 |

## 8. 검증 규칙과 격리 목록

| ID | 심각도 | 규칙 | 처리 |
|---|---|---|---|
| E001 | error | 필수 파일 없음 (`regions` `region_codes` `zones` `projects` `events` `sources`) | 해당 지역 폴더 거부 |
| E002 | error | 헤더에 필수 열이 없거나 열 이름이 중복됨, UTF-8이 아님, 또는 GeoJSON을 읽을 수 없음 | 해당 파일 거부 |
| E003 | error | `regions.csv`가 1행이 아니거나 `region_slug`가 폴더 이름과 다름 | 해당 지역 폴더 거부 |
| E101 | error | 필수 값이 비어 있음 | 행 격리 |
| E102 | error | 형식 위반 (날짜, 숫자 범위, slug, PNU 19자리, URL, 좌표 범위) | 행 격리 |
| E103 | error | 열거형에 없는 값, 또는 허용되지 않는 조합(예정을 허용하지 않는 사건의 `is_planned=Y`) | 행 격리 |
| E104 | error | 기본키·중복 판정 키 중복 | 뒤의 행 격리 |
| E105 | error | 참조 무결성 위반 (`project_id`, `source_id`, `zone_id`, `region_slug`). 참조 대상이 격리된 경우도 포함 | 행 격리 |
| E106 | error | 실제 사건(`is_planned=N`)의 날짜가 검증일보다 미래 | 행 격리 |
| E107 | error | `progress`의 `value`가 없거나 0~100 밖 | 행 격리 |
| E108 | error | 오버라이드 지오메트리가 닫히지 않았거나 4점 미만이거나 좌표가 한국 범위 밖 | 피처 격리 |
| W001 | warn | 정의되지 않은 열 | 무시, 리포트에만 |
| W101 | warn | 날짜 순서 모순 (승인>착공, 착공>사용검사, `progress` 값 감소) | 이벤트에 `suspect` 표시 |
| W102 | warn | 높이/지상층수가 2.4~4.5 m 밖 (공동주택 동, 지상층수 3 이상) | 동에 `suspect_floors` 표시 |
| W103 | warn | `floors_above`가 0인데 `height_m`가 10 m 이상 (지상·지하 반전 의심) | 동에 `suspect_floors` 표시 |
| W104 | warn | `projects.units`가 가장 최근 `permit_approved`의 `value`와 20% 넘게 다름 (`notice`의 `value`는 부분 공급일 수 있어 비교하지 않음) | 리포트에만 |
| W105 | warn | `sponsor_type=unknown` | 지도에서 제외, 확인 목록 |
| W106 | warn | `observed_at`이 검증일로부터 365일 넘게 지남 | 리포트에만 |
| I201 | info | 범위 밖 단지(공공 시행도 아니고 공공택지 위도 아님) | 목록에만 남김 |
| I202 | info | 지역·지구·단지·사건·동 건수 요약 | 리포트에만 |

- **error 행은 번들로 들어가지 않습니다.** 버리지 않고 `quarantine/<region_slug>/<파일>`에 사유(`_rule`, `_message`) 열과 함께 돌려드립니다. 고쳐서 다시 보내 주세요.
- **warn 행은 번들에 들어가되** 위 표시를 답니다. 상태 계산은 `suspect` 이벤트를 쓰지 않습니다.
- 종료 코드: 0 = error 없음, 1 = error 있음, 2 = 사용법·파일 열기 오류. `--strict`면 warn도 1입니다.

## 9. 품질 함정 체크리스트

실제 자료를 조사하면서 만난 함정입니다. 보내기 전에 한 번씩 확인해 주세요.

| # | 함정 | 어떻게 나타나나 | 규칙 | 보내기 전에 확인할 것 |
|---|---|---|---|---|
| 1 | 층수 필드가 반대 | 건축HUB 동 개요에서 `ugrndFlrCnt`가 지상층수(높이 59.35 m = 20층), `grndFlrCnt`가 지하 | W102 W103 | 높이 ÷ 지상층수가 3 m 안팎인지. 열 이름이 아니라 의미(`floors_above` = 지상)로 적었는지 |
| 2 | 변경허가마다 레코드가 생김 | "사용검사일이 빈 레코드"로 진행 단지를 찾으면 약 46%가 오탐 | 4절 | 같은 블록의 레코드를 모두 모아 보고, 사건을 날짜별로 한 줄씩 적었는지 |
| 3 | 인허가는 지번이 아니라 블록 이름으로 이어짐 | LH 블록은 지번이 `0000-0000`이고 `block`·`bldNm`에 이름이 있음 | `block_name_raw` | 원문 블록 이름을 `block_name_raw`에 그대로 적었는지, PNU를 알면 `pnu_list`에 적었는지 |
| 4 | 날짜가 서로 맞지 않음 | 착공일이 사용검사일보다 뒤이고 미래 날짜인 레코드 | E106 W101 | 실제 사건에 미래 날짜가 없는지, 예정일은 `is_planned=Y`로 표시했는지 |
| 5 | "공공분양" 표기가 민간 단지에도 붙음 | 세대 유형 호수만 보고 공공으로 판단하면 틀림 | 5절 | 시행자를 직접 말하는 자료로 `sponsor_type`을 정했는지 |
| 6 | 지역 코드가 바뀜 | 전남·광주 통합으로 나주 시군구 코드가 `46170`에서 `12170`으로 | `region_codes.csv` | 코드를 `region_codes.csv`에 유효기간과 함께 적었는지 |
| 7 | 모르는 값이 0으로 옴 | 건축HUB가 모르는 세대수·층수를 0으로 줌 | 2절 | 근거 없는 0을 빈 칸으로 바꿨는지 |
| 8 | 준공 단지는 인허가에 동 정보가 비어 있음 | 선운2는 인허가에 동 개요·착공·사용검사가 비고 건물 자료에만 동이 있음 | `structure_observed` | 건물이 관측되면 `structure_observed` 사건과 관측 날짜를 적었는지 |

## 10. 버전과 변경 절차

- 정의서, `schemas/input.spec.json`, 출력 번들 스키마는 같은 `schema_version`(`주.부.패치`)을 씁니다.
- **부(minor)** 버전: 열 추가, 코드표 값 추가처럼 예전 제출물이 그대로 통과하는 변경.
- **주(major)** 버전: 열 삭제, 의미 변경, 필수 열 추가처럼 예전 제출물이 깨지는 변경. 지도 화면은 현재 주버전과 직전 주버전을 읽습니다.
- 변경이 필요하면 (1) 무엇이 왜 불편한지 설명하고 (2) 영향받는 파일과 열을 적어 (3) 규격 담당자에게 요청합니다. 승인되면 버전을 올리고 이 문서의 필드표를 다시 생성해 모두에게 알립니다.

## 11. 제출 방법

1. 지역마다 폴더 `input/<region_slug>/`를 만들고 3.1절의 파일을 CSV(UTF-8)로 담습니다. 빈 틀은 `templates/`에 있습니다.
2. 보내기 전에 직접 검증합니다(파이썬 3 필요, 설치할 것 없음): `python3 tools/validate_input.py input/ --out 검증결과`. 폴더 하나(`input/gwangju-gwangsan`)나 ZIP도 넘길 수 있습니다. 결과는 `검증결과/validation_report.md`에 있고, error가 있으면 `검증결과/quarantine/`에 문제 행이 사유와 함께 모입니다.
3. error가 0이 되면 `input/` 폴더를 ZIP으로 묶어 전달합니다.
4. 받는 쪽이 같은 명령을 다시 실행해 리포트를 회신합니다. error가 있는 행은 지도에 들어가지 않으니 고쳐서 다시 보내 주세요.

## 부록 A. 예시 세트

| 폴더 | 내용 |
|---|---|
| `examples/incheon-gyeyang/` | 인천 계양구. A6(분양중)·A9(건설 단계) 단지, 공정율 이력, 동별 층수 |
| `examples/gwangju-gwangsan/` | 광주 광산구. 선운2 A-1블록: 마이홈 공고 2건, 인허가 승인 2건(변경허가 중복 레코드 포함), 건물 관측, PNU |

예시의 `verified`는 모두 `N`입니다(사람이 원문과 다시 대조하지 않은 값이라는 뜻). 다음 명령으로 직접 검증해 볼 수 있습니다.

```
python3 tools/validate_input.py docs/data-interface/examples/gwangju-gwangsan --out 검증결과
```

## 부록 B. 코드표

<!-- GENERATED:enums:BEGIN -->
<!-- GENERATED:enums:END -->

## 부록 C. 지구 유형 판정 키워드

`zone_type`은 공식 지구명으로 정합니다. V-World 블록 레이어의 지구명(`zonename`)에서 확인한 사례입니다.

| 지구명에 들어 있는 말 | `zone_type` | 공공택지 | 실제 지구명 예 |
|---|---|---|---|
| 택지개발 | `택지개발` | 예 | 광주선운지구 택지개발사업 |
| 공공주택지구 | `공공주택지구` | 예 | 광주선운2 공공주택지구 |
| 혁신도시 | `혁신도시` | 예 | 광주 전남 공동혁신도시 개발사업 |
| 신도시 | `신도시` | 예 | (2기·3기 신도시 지구명) |
| 도시개발 | `도시개발` | 아니오 | 나주 남평지구 도시개발사업 |
| 산업단지 | `산업단지` | 아니오 | 광주 에너지밸리 일반산업단지 |
| 위에 없음 | `기타` | 아니오 | 광주송정역 KTX지역경제거점형 투자선도지구 |

맞는 말이 없으면 `기타`로 두고 `note`에 이유를 적어 주세요. 사람이 확인합니다.
````

`docs/data-interface/README.md`:

```markdown
# 데이터 인터페이스 패키지

지도에 들어갈 데이터를 정해진 표로 넘기기 위한 자료입니다.

| 무엇 | 어디 |
|---|---|
| 정의서 (먼저 읽으세요) | `정의서.pdf` (원본 `정의서.md`) |
| 빈 CSV 틀 | `templates/` |
| 채워진 예 | `examples/` |
| 검증기 | `tools/validate_input.py` (패키지 ZIP 안 또는 저장소) |

## 빠른 시작

1. `templates/`의 파일을 복사해 `input/<지역 slug>/` 폴더에 채웁니다. 엑셀에서는 "CSV UTF-8(쉼표로 분리)"로 저장하세요.
2. 검증합니다: `python3 tools/validate_input.py input/ --out 검증결과`
3. `검증결과/validation_report.md`를 보고 error를 고칩니다. 문제 행은 `검증결과/quarantine/`에 모입니다.
4. error가 0이면 `input/`을 ZIP으로 묶어 전달합니다.

자세한 규칙은 정의서 11절을 보세요.
```

- [ ] **Step 4: 생성 구간을 채우고 통과를 확인한다**

Run: `python3 tools/gen_docs.py && python3 tools/gen_docs.py --check`
Expected: `9개 파일을 갱신했습니다 (바뀐 것 1개)`(정의서만 바뀜) 다음 줄에 `정의서와 템플릿이 모두 최신입니다`

Run: `python3 -m unittest discover -s tests -p "test_gen_docs.py" -v`
Expected: PASS — 11 tests OK

Run: `grep -c "GENERATED" docs/data-interface/정의서.md`
Expected: `4`

- [ ] **Step 5: 전체 테스트와 커밋**

Run: `python3 -m unittest discover -s tests`
Expected: `OK`

```bash
git add docs/data-interface/정의서.md docs/data-interface/README.md tests/test_gen_docs.py
git commit -m "docs: 데이터 인터페이스 정의서 본문과 팀원용 README" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 9: 예시 입력 세트 2개

**Files:**
- Create: `docs/data-interface/examples/incheon-gyeyang/{regions,region_codes,sources,zones,projects,events,dongs}.csv`
- Create: `docs/data-interface/examples/gwangju-gwangsan/{regions,region_codes,sources,zones,projects,events}.csv`
- Test: `tests/test_examples.py`

**Interfaces:**
- Consumes: Task 1~6의 검증기(`validate_region`), Task 1의 `load_spec`(열 순서).
- Produces: 두 예시 폴더. 둘 다 `TODAY=2026-10-04` 기준으로 error 0, warn 0이어야 한다. 계양은 단지 2개(A6, A9)와 동 21개, 선운2는 단지 1개(A-1)와 인허가 승인 이벤트 2건(변경허가 중복 레코드)이다.

값은 모두 저장소 안 원자료나 조사 결과에서 **그대로 옮긴다**. 지어 쓰지 않는다. `verified`는 사람이 원문과 다시 대조하지 않았으므로 모두 `N`이다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_examples.py`:

```python
import unittest

from helpers import ROOT, SPEC, TODAY, rules_of
from datacheck.validate import validate_region

EXAMPLES = ROOT / "docs" / "data-interface" / "examples"


class Examples(unittest.TestCase):
    def test_both_examples_exist(self):
        names = sorted(p.name for p in EXAMPLES.iterdir() if p.is_dir())
        self.assertEqual(names, ["gwangju-gwangsan", "incheon-gyeyang"])

    def test_each_example_validates_without_errors_or_warnings(self):
        for d in sorted(p for p in EXAMPLES.iterdir() if p.is_dir()):
            with self.subTest(d.name):
                res = validate_region(d, SPEC, TODAY)
                self.assertFalse(res.rejected)
                self.assertEqual(rules_of(res, "error"), [])
                self.assertEqual(rules_of(res, "warn"), [])

    def test_example_content(self):
        g = validate_region(EXAMPLES / "incheon-gyeyang", SPEC, TODAY)
        s = validate_region(EXAMPLES / "gwangju-gwangsan", SPEC, TODAY)
        self.assertEqual(g.scope["public"], 2)
        self.assertEqual(s.scope["public"], 1)
        self.assertEqual(len(g.tables["dongs.csv"].rows), 12 + 9)
        a9_progress = [r for r in g.tables["events.csv"].rows
                       if r.get("project_id") == "techno-A9" and r.get("event_type") == "progress"]
        self.assertEqual(len(a9_progress), 7)
        permits = [r for r in s.tables["events.csv"].rows if r.get("event_type") == "permit_approved"]
        self.assertEqual(sorted(r.get("event_date") for r in permits), ["2022-03-04", "2022-03-11"])
        self.assertEqual(s.tables["projects.csv"].rows[0].get("pnu_list"), "1233010600105190000")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m unittest discover -s tests -p "test_examples.py" -v`
Expected: FAIL — `FileNotFoundError: ... examples` (폴더가 아직 없음)

- [ ] **Step 3: 예시 파일을 만든다**

임시 스크립트를 저장소 밖에 만든다(커밋하지 않는다). `MK="$(mktemp -d)"`로 폴더를 잡고 `$MK/make_examples.py`로 저장한 뒤 **저장소 루트에서** `python3 "$MK/make_examples.py"`로 실행한다.

```python
import csv
import sys
from pathlib import Path

ROOT = Path.cwd()  # 저장소 루트에서 실행한다
sys.path.insert(0, str(ROOT / "tools"))
from datacheck.spec import load_spec  # noqa: E402

SPEC = load_spec()
EX = ROOT / "docs" / "data-interface" / "examples"


def write(region, name, rows):
    d = EX / region
    d.mkdir(parents=True, exist_ok=True)
    cols = SPEC.files[name].column_names
    with open(d / name, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])


# ================= 인천 계양구 =================
G = "incheon-gyeyang"
cw = list(csv.DictReader(open(
    ROOT / "data/raw/lh/cwstt/lh_공사현황_인천계양_공정율_이력_20261003.csv", encoding="utf-8-sig")))

write(G, "regions.csv", [dict(region_slug=G, region_name="인천 계양구", sido_name="인천광역시", sigungu_name="계양구")])
write(G, "region_codes.csv", [
    dict(region_slug=G, code="28", code_type="sido", code_name="인천광역시"),
    dict(region_slug=G, code="28245", code_type="sigungu", code_name="계양구"),
])
write(G, "sources.csv", [
    dict(source_id="lh-cwstt", label="LH청약플러스 공사현황", publisher="한국토지주택공사",
         url="https://apply.lh.or.kr/lhapply/land/cwsttList.do", as_of="2026-10-03",
         redistributable="unknown", usage_note="robots.txt가 허용하는 화면. 이용조건 미확인"),
    dict(source_id="lh-notice", label="LH 입주자모집공고문", publisher="한국토지주택공사",
         redistributable="unknown", usage_note="공고문 PDF는 한 건씩 내려받음. 재배포 조건 미확인"),
    dict(source_id="lh-pamphlet", label="LH 팸플릿 동호배치도", publisher="한국토지주택공사",
         redistributable="unknown", usage_note="동별 최상층(필로티 1층 포함)"),
    dict(source_id="vworld-lhblpn", label="V-World 데이터 API LT_C_LHBLPN", publisher="국토교통부 V-World",
         as_of="2026-10-03", redistributable="unknown", usage_note="이용 조건 확인 필요"),
])
write(G, "zones.csv", [dict(region_slug=G, zone_id="techno-valley", zone_name="인천계양 테크노밸리 공공주택지구",
                            zone_type="공공주택지구", organizer="LH", source_id="vworld-lhblpn")])
write(G, "projects.csv", [
    dict(region_slug=G, project_id="techno-A6", zone_id="techno-valley", project_name="인천계양 A6블록 공공분양",
         block_label="A6", block_name_raw="A6", sponsor_name="LH", sponsor_type="public", project_kind="공공분양",
         units="663", dong_count="12", source_id="lh-notice", observed_at="2026-10-03", verified="N",
         note="시공사: (주)케이알산업, 우암건설"),
    dict(region_slug=G, project_id="techno-A9", zone_id="techno-valley", project_name="인천계양 A9블록 신혼희망타운",
         block_label="A9", block_name_raw="A9", sponsor_name="LH", sponsor_type="public", project_kind="신혼희망타운",
         units="317", dong_count="9", source_id="lh-notice", observed_at="2026-10-03", verified="N",
         note="시공사: 진흥기업(주)"),
])

events = []
for block, pid, notice_date, notice_ref, notice_note, units, move_in in (
    ("A6", "techno-A6", "2026-09-14", "LH_인천계양A6_입주자모집공고문_정정20260914.pdf", "입주자모집공고문(정정)", "663", "2029-06"),
    ("A9", "techno-A9", "2026-05-14", "LH_인천계양A9_입주자모집공고문_20260514.pdf", "입주자모집공고문", "317", "2029-02"),
):
    rows = sorted((r for r in cw if r["블록"] == block), key=lambda r: r["기준일"])
    ref = f'{rows[0]["지구코드"]}-{rows[0]["블록코드"]}'  # 공사현황의 지구코드-블록코드
    events.append(dict(region_slug=G, project_id=pid, event_type="notice", event_date=notice_date, value=units,
                       source_id="lh-notice", source_ref=notice_ref, note=notice_note))
    events.append(dict(region_slug=G, project_id=pid, event_type="construction_start", event_date=rows[0]["공사시작"],
                       source_id="lh-cwstt", source_ref=ref, note="공사현황의 공사시작일"))
    for r in rows:
        events.append(dict(region_slug=G, project_id=pid, event_type="progress", event_date=r["기준일"],
                           value=r["공정율_퍼센트"], source_id="lh-cwstt", source_ref=ref))
    events.append(dict(region_slug=G, project_id=pid, event_type="move_in", event_date=move_in, is_planned="Y",
                       source_id="lh-notice", source_ref=notice_ref, note="입주예정월"))
write(G, "events.csv", events)

A6 = {"601": 15, "602": 15, "603": 15, "604": 14, "605": 9, "606": 10, "607": 9, "608": 9, "609": 11, "610": 14, "611": 8, "612": 15}
A9 = {f"9{n:02d}": (14 if n == 5 else 15) for n in range(1, 10)}
dongs = [dict(region_slug=G, project_id=pid, dong_no=no, floors_above=str(fl), dong_use="공동주택",
              source_id="lh-pamphlet", observed_at="2026-10-03")
         for pid, floors in (("techno-A6", A6), ("techno-A9", A9)) for no, fl in floors.items()]
write(G, "dongs.csv", dongs)

# ================= 광주 광산구 (선운2 A-1) =================
S = "gwangju-gwangsan"
write(S, "regions.csv", [dict(region_slug=S, region_name="광주 광산구", sido_name="전남광주통합특별시", sigungu_name="광산구")])
write(S, "region_codes.csv", [
    dict(region_slug=S, code="12330", code_type="sigungu", code_name="광산구",
         note="전남·광주 통합 후 V-World 기준 코드. 유효 시작일은 확인하지 못함"),
    dict(region_slug=S, code="12330106", code_type="bjdong", code_name="운수동"),
    dict(region_slug=S, code="12330107", code_type="bjdong", code_name="선암동"),
    dict(region_slug=S, code="12330108", code_type="bjdong", code_name="소촌동"),
])
write(S, "sources.csv", [
    dict(source_id="myhome-notice", label="마이홈포털 공공주택 모집공고 조회 서비스", publisher="국토교통부",
         url="https://www.data.go.kr/data/15108420/openapi.do", as_of="2026-10-04", redistributable="unknown",
         usage_note="포털 약관과 이용허락 표기가 어긋난다는 메모가 있어 제공기관 확인 필요"),
    dict(source_id="hub-housing-permit", label="건축HUB 주택인허가정보 서비스", publisher="국토교통부",
         url="https://www.data.go.kr/data/15136560/openapi.do", as_of="2026-10-04", redistributable="unknown",
         usage_note="포털 약관과 이용허락 표기가 어긋난다는 메모가 있어 제공기관 확인 필요"),
    dict(source_id="vworld-bldginfo", label="V-World 데이터 API LT_C_BLDGINFO", publisher="국토교통부 V-World",
         as_of="2026-10-04", redistributable="unknown", usage_note="이용 조건 확인 필요"),
    dict(source_id="vworld-lhblpn", label="V-World 데이터 API LT_C_LHBLPN", publisher="국토교통부 V-World",
         as_of="2026-10-04", redistributable="unknown", usage_note="이용 조건 확인 필요"),
])
write(S, "zones.csv", [dict(region_slug=S, zone_id="sunwoon2", zone_name="광주선운2 공공주택지구",
                            zone_type="공공주택지구", source_id="vworld-lhblpn")])
write(S, "projects.csv", [dict(
    region_slug=S, project_id="sunwoon2-A1", zone_id="sunwoon2", project_name="광주선운2 A-1블록 신혼희망타운",
    block_label="A-1", block_name_raw="A-1BL", sponsor_name="LH", sponsor_type="public", project_kind="신혼희망타운",
    units="828", dong_count="6", pnu_list="1233010600105190000", address="전남광주통합특별시 광산구 선암1로 43",
    source_id="myhome-notice", observed_at="2026-10-04", verified="N",
    note="건축HUB에는 이 블록의 승인 레코드가 6동(2022-03-11)과 7동(2022-03-04) 두 개 있다")])
NOTICE_NAME = "공고명: 광주선운2 A-1,3블록 신혼희망타운 공공분양 선착순계약"
write(S, "events.csv", [
    dict(region_slug=S, project_id="sunwoon2-A1", event_type="notice", event_date="2026-02-02", value="86",
         source_id="myhome-notice", source_ref="0000061056", note=NOTICE_NAME + ". A-1블록 공급 86세대"),
    dict(region_slug=S, project_id="sunwoon2-A1", event_type="notice", event_date="2026-07-06", value="39",
         source_id="myhome-notice", source_ref="0000061131", note=NOTICE_NAME + ". A-1블록 공급 39세대"),
    dict(region_slug=S, project_id="sunwoon2-A1", event_type="permit_approved", event_date="2022-03-11", value="828",
         source_id="hub-housing-permit", source_ref="1064100004987", note="광주선운2지구 A-1BL 신혼희망타운 건설공사, 6동"),
    dict(region_slug=S, project_id="sunwoon2-A1", event_type="permit_approved", event_date="2022-03-04", value="828",
         source_id="hub-housing-permit", source_ref="1069100017752", note="같은 블록의 다른 허가 레코드, 7동"),
    dict(region_slug=S, project_id="sunwoon2-A1", event_type="structure_observed", event_date="2026-10-04", value="6",
         source_id="vworld-bldginfo", note="블록 안 5층 이상 건물 6동 관측(지상 25층)"),
])
print("예시 세트를 만들었습니다:", EX)
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m unittest discover -s tests -p "test_examples.py" -v`
Expected: PASS — 3 tests OK. `warn`이 나오면 리포트(`python3 tools/validate_input.py docs/data-interface/examples/<폴더> --out "$(mktemp -d)" --today 2026-10-04`의 `validation_report.md`)를 읽고 **예시 값이 아니라 원인**을 확인한다(예: 날짜가 검증일보다 미래인지). 값을 지어내서 맞추지 않는다.

Run: `python3 tools/validate_input.py docs/data-interface/examples/gwangju-gwangsan --out "$(mktemp -d)" --today 2026-10-04; echo "exit=$?"`
Expected: `완료  gwangju-gwangsan` / `error 0 · warn 0 · info 1` / `exit=0`

Run: `python3 tools/validate_input.py docs/data-interface/examples/incheon-gyeyang --out "$(mktemp -d)" --today 2026-10-04; echo "exit=$?"`
Expected: `완료  incheon-gyeyang` / `error 0 · warn 0 · info 1` / `exit=0`

- [ ] **Step 5: 전체 테스트와 커밋**

Run: `python3 -m unittest discover -s tests`
Expected: `OK`

```bash
git add docs/data-interface/examples tests/test_examples.py
git commit -m "docs: 예시 입력 세트(인천 계양, 광주 선운2 A-1)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 10: 출력 번들 JSON Schema

**Files:**
- Create: `schemas/bundle/index.schema.json`, `region.schema.json`, `projects.schema.json`, `buildings.schema.json`, `context.schema.json`
- Test: `tests/test_bundle_schemas.py`

**Interfaces:**
- Consumes: Task 1의 `SPEC.enums`(열거형과의 일치를 시험).
- Produces: 정의서 7절이 요약하는 출력 번들의 정본 스키마 5개. 번들을 만드는 컴파일러(B)와 지도 화면(S2)이 이 스키마를 따른다. 이 작업에서는 스키마 파일만 만들고 인스턴스 검증기는 만들지 않는다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_bundle_schemas.py`:

```python
import json
import unittest

from helpers import ROOT, SPEC

SCHEMAS = ROOT / "schemas" / "bundle"
NAMES = ["index", "region", "projects", "buildings", "context"]
STATUSES = ["계획", "분양중", "건설 단계", "준공 임박", "입주 단계"]


def load(name):
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))


class BundleSchemas(unittest.TestCase):
    def test_all_five_schemas_are_json_schema_documents(self):
        for name in NAMES:
            with self.subTest(name):
                s = load(name)
                self.assertEqual(s["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertTrue(s["title"].startswith("regions/"))
                self.assertEqual(s["type"], "object")
                self.assertIn("required", s)

    def test_refs_resolve_inside_each_schema(self):
        for name in NAMES:
            schema = load(name)

            def walk(node):
                if isinstance(node, dict):
                    ref = node.get("$ref")
                    if ref:
                        self.assertTrue(ref.startswith("#/$defs/"), ref)
                        self.assertIn(ref.split("/")[-1], schema["$defs"], f"{name}: {ref}")
                    for v in node.values():
                        walk(v)
                elif isinstance(node, list):
                    for v in node:
                        walk(v)

            walk(schema)

    def test_enums_match_the_input_spec(self):
        projects, region, index = load("projects"), load("region"), load("index")
        self.assertEqual(projects["$defs"]["status"]["enum"], STATUSES)
        self.assertEqual(tuple(projects["$defs"]["tier"]["enum"]), SPEC.enums["tier"])
        event_enum = projects["$defs"]["project"]["properties"]["events"]["items"]["properties"]["type"]["enum"]
        self.assertEqual(tuple(event_enum), SPEC.enums["event_type"])
        zone_enum = region["properties"]["zones"]["items"]["properties"]["type"]["enum"]
        self.assertEqual(tuple(zone_enum), SPEC.enums["zone_type"])
        self.assertEqual(region["properties"]["statusOrder"]["items"]["enum"], STATUSES)
        self.assertEqual(index["properties"]["regions"]["items"]["properties"]["visibility"]["enum"],
                         ["public", "preview"])

    def test_sponsor_class_and_flags(self):
        project = load("projects")["$defs"]["project"]["properties"]
        self.assertEqual(project["sponsorClass"]["enum"], ["public", "private_on_public_land"])
        self.assertEqual(project["flags"]["items"]["enum"], ["suspect_floors", "suspect_dates"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m unittest discover -s tests -p "test_bundle_schemas.py" -v`
Expected: FAIL — `FileNotFoundError: ... index.schema.json`

- [ ] **Step 3: 스키마 5개를 만든다**

`schemas/bundle/index.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "regions/index.json",
  "description": "지역 목록. 화면이 가장 먼저 읽는다.",
  "type": "object",
  "required": ["schema_version", "regions"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {"$ref": "#/$defs/semver"},
    "dataBase": {"type": "string", "description": "지역 데이터 폴더의 기본 주소. 기본값 'regions/'. 저장 위치가 바뀌어도 화면 코드는 바뀌지 않는다."},
    "regions": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["slug", "name", "visibility", "updatedAt", "schema_version"],
        "additionalProperties": false,
        "properties": {
          "slug": {"type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"},
          "name": {"type": "string"},
          "default": {"type": "boolean", "description": "?region= 이 없을 때 여는 지역"},
          "visibility": {"enum": ["public", "preview"], "description": "preview 지역은 운영 빌드에서 제외된다"},
          "updatedAt": {"type": "string", "format": "date"},
          "schema_version": {"$ref": "#/$defs/semver"}
        }
      }
    }
  },
  "$defs": {
    "semver": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$"}
  }
}
```

`schemas/bundle/region.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "regions/<slug>/region.json",
  "description": "지역 설정: 화면 제목, 시작 위치, 지역 코드, 지구, 출처, 상태 순서.",
  "type": "object",
  "required": ["schema_version", "slug", "name", "title", "updatedAt", "view", "codes", "zones", "sources", "statusOrder"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {"$ref": "#/$defs/semver"},
    "slug": {"type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"},
    "name": {"type": "string"},
    "title": {"type": "string", "description": "화면 제목"},
    "description": {"type": "string"},
    "updatedAt": {"type": "string", "format": "date"},
    "view": {
      "type": "object",
      "required": ["center", "zoom"],
      "additionalProperties": false,
      "properties": {
        "center": {"$ref": "#/$defs/lonlat"},
        "zoom": {"type": "number", "minimum": 8, "maximum": 18},
        "pitch": {"type": "number", "minimum": 0, "maximum": 85},
        "bearing": {"type": "number"}
      }
    },
    "codes": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["code", "type"],
        "additionalProperties": false,
        "properties": {
          "code": {"type": "string"},
          "type": {"enum": ["sido", "sigungu", "bjdong"]},
          "name": {"type": "string"},
          "validFrom": {"type": ["string", "null"], "format": "date"},
          "validTo": {"type": ["string", "null"], "format": "date"}
        }
      }
    },
    "zones": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "name", "type", "publicLand"],
        "additionalProperties": false,
        "properties": {
          "id": {"type": "string"},
          "name": {"type": "string"},
          "type": {"enum": ["택지개발", "공공주택지구", "혁신도시", "신도시", "도시개발", "산업단지", "기타"]},
          "publicLand": {"type": "boolean", "description": "공공택지(택지개발·공공주택지구·혁신도시·신도시)인지"},
          "poly": {"type": "array", "items": {"$ref": "#/$defs/lonlat"}}
        }
      }
    },
    "sources": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "label", "redistributable"],
        "additionalProperties": false,
        "properties": {
          "id": {"type": "string"},
          "label": {"type": "string"},
          "publisher": {"type": "string"},
          "license": {"type": "string"},
          "url": {"type": "string"},
          "asOf": {"type": ["string", "null"], "format": "date"},
          "redistributable": {"enum": ["Y", "N", "unknown"]}
        }
      }
    },
    "statusOrder": {
      "type": "array",
      "uniqueItems": true,
      "items": {"enum": ["계획", "분양중", "건설 단계", "준공 임박", "입주 단계"]}
    }
  },
  "$defs": {
    "semver": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$"},
    "lonlat": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2, "description": "[경도, 위도]"}
  }
}
```

`schemas/bundle/projects.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "regions/<slug>/projects.json",
  "description": "단지 목록. 상태·표시 클래스·윤곽 등급은 컴파일러가 입력 이벤트에서 계산해 채운다.",
  "type": "object",
  "required": ["schema_version", "projects"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {"$ref": "#/$defs/semver"},
    "projects": {"type": "array", "items": {"$ref": "#/$defs/project"}},
    "otherBlocks": {"type": "array", "items": {"$ref": "#/$defs/ring"}, "description": "이름을 모르는 주택 용지(공식 윤곽)"}
  },
  "$defs": {
    "semver": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$"},
    "lonlat": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
    "ring": {"type": "array", "items": {"$ref": "#/$defs/lonlat"}, "minItems": 3},
    "status": {"enum": ["계획", "분양중", "건설 단계", "준공 임박", "입주 단계"]},
    "tier": {"enum": ["official", "building", "schematic"]},
    "project": {
      "type": "object",
      "required": ["id", "label", "name", "sponsor", "sponsorClass", "kind", "status", "outline"],
      "properties": {
        "id": {"type": "string"},
        "zoneId": {"type": ["string", "null"]},
        "label": {"type": "string"},
        "name": {"type": "string"},
        "sponsor": {
          "type": "object",
          "required": ["name", "type"],
          "properties": {"name": {"type": "string"}, "type": {"enum": ["public", "private", "joint"]}}
        },
        "sponsorClass": {"enum": ["public", "private_on_public_land"]},
        "kind": {"type": "string"},
        "status": {"$ref": "#/$defs/status"},
        "units": {"type": ["integer", "null"], "minimum": 0},
        "dongCount": {"type": ["integer", "null"], "minimum": 0},
        "moveIn": {"type": ["string", "null"], "description": "입주(예정) 월 YYYY-MM 또는 날짜"},
        "progress": {
          "type": ["object", "null"],
          "required": ["rate", "asOf"],
          "properties": {
            "rate": {"type": "number", "minimum": 0, "maximum": 100},
            "asOf": {"type": "string"},
            "history": {
              "type": "array",
              "items": {"type": "array", "prefixItems": [{"type": "string"}, {"type": "number"}], "minItems": 2, "maxItems": 2}
            }
          }
        },
        "outline": {
          "type": "object",
          "required": ["tier", "poly"],
          "properties": {"tier": {"$ref": "#/$defs/tier"}, "poly": {"$ref": "#/$defs/ring"}, "how": {"type": "string"}}
        },
        "dongs": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["no", "tier", "poly"],
            "properties": {
              "no": {"type": "string"},
              "floorsAbove": {"type": ["integer", "null"]},
              "floorsBelow": {"type": ["integer", "null"]},
              "heightM": {"type": ["number", "null"]},
              "tier": {"$ref": "#/$defs/tier"},
              "poly": {"type": "array", "items": {"$ref": "#/$defs/ring"}}
            }
          }
        },
        "events": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["type", "date"],
            "properties": {
              "type": {"enum": ["notice", "permit_approved", "construction_start", "progress", "completion_inspection", "move_in", "structure_observed"]},
              "date": {"type": "string"},
              "planned": {"type": "boolean"},
              "value": {"type": ["number", "null"]},
              "source": {"type": "string"},
              "ref": {"type": ["string", "null"]},
              "suspect": {"type": "boolean"}
            }
          }
        },
        "flags": {"type": "array", "items": {"enum": ["suspect_floors", "suspect_dates"]}},
        "sources": {"type": "array", "items": {"type": "string"}}
      }
    }
  }
}
```

`schemas/bundle/buildings.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "regions/<slug>/buildings.json",
  "description": "건물 윤곽 GeoJSON. 높이 eh는 화면에 쓰는 높이(m), src는 그 높이의 출처.",
  "type": "object",
  "required": ["type", "features", "meta"],
  "properties": {
    "type": {"const": "FeatureCollection"},
    "meta": {
      "type": "object",
      "required": ["basis"],
      "properties": {"basis": {"type": "string", "description": "자료 기준일 YYYYMMDD"}},
      "additionalProperties": true
    },
    "features": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["type", "geometry", "properties"],
        "properties": {
          "type": {"const": "Feature"},
          "geometry": {
            "type": "object",
            "required": ["type", "coordinates"],
            "properties": {"type": {"enum": ["Polygon", "MultiPolygon"]}}
          },
          "properties": {
            "type": "object",
            "required": ["eh"],
            "properties": {
              "eh": {"type": "number", "minimum": 0},
              "src": {"enum": ["공식높이", "층수환산", "정보없음"]},
              "h": {"type": ["number", "null"]},
              "f": {"type": ["integer", "null"]},
              "b": {"type": ["integer", "null"]},
              "u": {"type": "string"},
              "n": {"type": "string"},
              "a": {"type": ["string", "integer", "null"]},
              "d": {"type": "string"},
              "x": {"type": ["integer", "null"]}
            }
          }
        }
      }
    }
  }
}
```

`schemas/bundle/context.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "regions/<slug>/context.json",
  "description": "주변 지하철역·학교 위치(OpenStreetMap).",
  "type": "object",
  "required": ["stations", "schools", "asOf", "source"],
  "properties": {
    "stations": {"type": "array", "items": {"$ref": "#/$defs/place"}},
    "schools": {"type": "array", "items": {"$ref": "#/$defs/place"}},
    "asOf": {"type": "string", "format": "date"},
    "source": {"type": "string"}
  },
  "$defs": {
    "place": {
      "type": "object",
      "required": ["name", "lon", "lat"],
      "properties": {"name": {"type": "string"}, "lon": {"type": "number"}, "lat": {"type": "number"}}
    }
  }
}
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m unittest discover -s tests -p "test_bundle_schemas.py" -v`
Expected: PASS — 4 tests OK

- [ ] **Step 5: 전체 테스트와 커밋**

Run: `python3 -m unittest discover -s tests`
Expected: `OK`

```bash
git add schemas/bundle tests/test_bundle_schemas.py
git commit -m "feat: 출력 번들 JSON Schema 5종" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 11: PDF 생성, 무시 규칙, 전달 패키지, 최종 검증

**Files:**
- Create: `tools/build_docs_pdf.py`
- Create: `docs/data-interface/정의서.pdf` (생성물)
- Modify: `.gitignore` (줄 추가)
- Test: `tests/test_build_docs_pdf.py`

**Interfaces:**
- Consumes: Task 8의 `docs/data-interface/정의서.md`.
- Produces: `build_docs_pdf.render_html(md_text, title) -> str`(markdown 패키지는 이 함수 안에서만 불러온다), `print_html_to_pdf(html_path, pdf_path, chrome=CHROME, timeout=120) -> None`(Chrome 헤드리스로 인쇄. **PDF가 완성되면 Chrome이 스스로 종료하지 않아도 직접 종료한다.** Chrome이 PDF 없이 끝나면 `RuntimeError`, 시간 안에 완성되지 않으면 `TimeoutError`), `build_pdf(md_path=MD, pdf_path=PDF, chrome=CHROME) -> None`, `main() -> int`. 상수 `MD`, `PDF`, `CHROME`. 팀원 전달 ZIP `dist/data-interface-package.zip`(저장소에는 올리지 않는다).
- 배경: Chrome 154는 `--print-to-pdf`로 PDF를 0.6초 만에 쓰고도 프로세스가 종료되지 않는다(플래그를 바꿔도 같음). 종료를 기다리면 시간 초과가 되므로 파일 완성(`%PDF`로 시작, 끝 1 KB 안에 `%%EOF`, 크기가 0.5초간 변하지 않음)을 기다린 뒤 종료시킨다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_build_docs_pdf.py`:

```python
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path

from helpers import ROOT  # noqa: F401  (tools/ 를 sys.path 에 넣는다)
import build_docs_pdf

try:
    import markdown  # noqa: F401
    HAVE_MARKDOWN = True
except ImportError:
    HAVE_MARKDOWN = False

PDF_PATH_ARG = 'out = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--print-to-pdf=")][0]\n'


def fake_chrome(tmp, body):
    """인자를 받아 body를 실행하는 가짜 Chrome 실행 파일을 만든다."""
    path = Path(tmp) / "fake-chrome"
    path.write_text(f"#!{sys.executable}\nimport sys, time\n{PDF_PATH_ARG}{body}", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def html_file(tmp):
    p = Path(tmp) / "a.html"
    p.write_text("<p>x</p>", encoding="utf-8")
    return p


class PrintHtmlToPdf(unittest.TestCase):
    def test_returns_once_the_pdf_is_complete_even_if_chrome_never_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            chrome = fake_chrome(tmp, 'open(out, "wb").write(b"%PDF-1.4\\nfake\\n%%EOF\\n")\ntime.sleep(600)\n')
            pdf = Path(tmp) / "out.pdf"
            started = time.monotonic()
            build_docs_pdf.print_html_to_pdf(html_file(tmp), pdf, chrome=chrome, timeout=30)
            self.assertLess(time.monotonic() - started, 15)
            self.assertTrue(pdf.read_bytes().startswith(b"%PDF"))

    def test_runtime_error_when_chrome_exits_without_a_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            chrome = fake_chrome(tmp, "sys.exit(3)\n")
            with self.assertRaises(RuntimeError):
                build_docs_pdf.print_html_to_pdf(html_file(tmp), Path(tmp) / "out.pdf", chrome=chrome, timeout=30)

    def test_timeout_when_nothing_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            chrome = fake_chrome(tmp, "time.sleep(600)\n")
            with self.assertRaises(TimeoutError):
                build_docs_pdf.print_html_to_pdf(html_file(tmp), Path(tmp) / "out.pdf", chrome=chrome, timeout=2)

    def test_an_old_pdf_is_not_mistaken_for_the_new_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "out.pdf"
            pdf.write_bytes(b"%PDF-1.4\nold\n%%EOF\n")
            chrome = fake_chrome(tmp, "sys.exit(0)\n")  # 아무것도 쓰지 않고 정상 종료
            with self.assertRaises(RuntimeError):
                build_docs_pdf.print_html_to_pdf(html_file(tmp), pdf, chrome=chrome, timeout=30)


@unittest.skipUnless(HAVE_MARKDOWN, "markdown 패키지가 필요함 (.venv/bin/python 으로 실행)")
class RenderHtml(unittest.TestCase):
    def test_render_html_keeps_tables_headings_and_language(self):
        html = build_docs_pdf.render_html("# 제목\n\n| a | b |\n|---|---|\n| 1 | 2 |\n", "정의서")
        self.assertIn("<table>", html)
        self.assertIn("<h1", html)
        self.assertIn('lang="ko"', html)
        self.assertIn("<title>정의서</title>", html)

    def test_the_real_definition_renders_all_tables(self):
        html = build_docs_pdf.render_html(build_docs_pdf.MD.read_text(encoding="utf-8"), "정의서")
        self.assertGreaterEqual(html.count("<table>"), 15)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 가상환경을 만들고 실패를 확인한다**

Run: `python3 -m venv .venv && .venv/bin/pip install --quiet markdown && .venv/bin/python -c "import markdown; print(markdown.__version__)"`
Expected: 버전 번호 출력 (예: `3.x`)


Run: `python3 -m unittest discover -s tests -p "test_build_docs_pdf.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'build_docs_pdf'` (모듈이 아직 없다)

- [ ] **Step 3: 생성 스크립트를 구현한다**

`tools/build_docs_pdf.py`:

```python
#!/usr/bin/env python3
"""정의서.md → HTML → PDF. 개발 전용: `markdown` 패키지와 Chrome이 필요하다.

  .venv/bin/python tools/build_docs_pdf.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / "docs" / "data-interface" / "정의서.md"
PDF = ROOT / "docs" / "data-interface" / "정의서.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@page { size: A4; margin: 18mm 16mm; }
body { font-family: 'Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif; font-size: 10.5pt; line-height: 1.55; color: #1a1a1a; }
h1 { font-size: 20pt; border-bottom: 2px solid #333; padding-bottom: 6px; }
h2 { font-size: 14.5pt; margin-top: 22px; border-bottom: 1px solid #bbb; padding-bottom: 3px; page-break-after: avoid; }
h3, h4 { page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9pt; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #bbb; padding: 3px 6px; vertical-align: top; text-align: left; }
th { background: #f0f0f0; }
code { font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 0.92em; background: #f4f4f4; padding: 0 3px; border-radius: 2px; }
pre { background: #f4f4f4; padding: 8px 10px; font-size: 9pt; line-height: 1.4; page-break-inside: avoid; white-space: pre-wrap; }
pre code { background: none; padding: 0; }
"""


def render_html(md_text: str, title: str) -> str:
    import markdown  # 개발 전용 의존성이라 필요할 때만 불러온다

    body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    return (f"<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\"><title>{title}</title>"
            f"<style>{CSS}</style></head><body>{body}</body></html>")


def _pdf_is_complete(path: Path) -> bool:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return False
    return data.startswith(b"%PDF") and b"%%EOF" in data[-1024:]


def print_html_to_pdf(html_path: Path | str, pdf_path: Path | str, chrome: str = CHROME, timeout: float = 120) -> None:
    """Chrome 헤드리스로 HTML을 PDF로 인쇄한다.

    Chrome 154는 PDF를 다 쓰고도 프로세스가 종료되지 않는다. 그래서 종료를 기다리지 않고
    PDF가 완성되면(끝에 %%EOF, 크기가 0.5초간 그대로) Chrome을 직접 종료한다.
    """
    pdf_path = Path(pdf_path)
    pdf_path.unlink(missing_ok=True)  # 예전 PDF를 새 것으로 착각하지 않게 먼저 지운다
    with tempfile.TemporaryDirectory() as profile:
        proc = subprocess.Popen(
            [chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
             f"--user-data-dir={profile}", f"--print-to-pdf={pdf_path}", Path(html_path).resolve().as_uri()],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + timeout
            last_size, steady = -1, 0
            while time.monotonic() < deadline:
                if _pdf_is_complete(pdf_path):
                    size = pdf_path.stat().st_size
                    steady = steady + 1 if size == last_size else 0
                    last_size = size
                    if steady >= 2:
                        return
                elif proc.poll() is not None:
                    raise RuntimeError(f"Chrome이 PDF를 만들지 않고 종료함 (종료 코드 {proc.returncode})")
                time.sleep(0.25)
            raise TimeoutError(f"{timeout:g}초 안에 PDF가 완성되지 않음")
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()


def build_pdf(md_path: Path = MD, pdf_path: Path = PDF, chrome: str = CHROME) -> None:
    html = render_html(Path(md_path).read_text(encoding="utf-8"), Path(md_path).stem)
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "doc.html"
        page.write_text(html, encoding="utf-8")
        print_html_to_pdf(page, pdf_path, chrome=chrome)


def main() -> int:
    if not Path(CHROME).exists():
        print(f"오류: Chrome을 찾지 못함: {CHROME}")
        return 2
    build_pdf()
    print(f"생성: {PDF}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 통과를 확인하고 PDF를 만든다**

Run: `python3 -m unittest discover -s tests -p "test_build_docs_pdf.py" -v`
Expected: PASS — 인쇄 테스트 4개 OK, 렌더 테스트 2개는 `skipped` (시스템 파이썬에는 markdown이 없다)

Run: `.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS — 전체 테스트 OK, skipped 0

Run: `.venv/bin/python tools/build_docs_pdf.py`
Expected: `생성: .../docs/data-interface/정의서.pdf`

Run: `head -c 5 docs/data-interface/정의서.pdf; echo; ls -l docs/data-interface/정의서.pdf`
Expected: `%PDF-` 와 수십 KB 이상의 파일 크기

그리고 PDF를 눈으로 확인한다: 파일 읽기 도구로 `docs/data-interface/정의서.pdf`의 1~2쪽과 8절이 있는 쪽을 읽어, 한글이 깨지지 않았고 표가 쪽 너비를 넘지 않는지 본다. 깨졌으면 `CSS`의 `table`·`font-size`를 고쳐 다시 만든다.

- [ ] **Step 5: `.gitignore`를 정리하고 커밋한다**

`.gitignore` 맨 아래에 다음을 추가한다(이미 있는 줄은 중복하지 않는다):

```
# 팀원 제출물·검증 결과·개발 환경·전달 패키지
input/
validation_out/
.venv/
dist/
```

Run: `git status --short`
Expected: `.gitignore`, `tools/build_docs_pdf.py`, `tests/test_build_docs_pdf.py`, `docs/data-interface/정의서.pdf`만 보인다(`.venv/`, `dist/`는 보이지 않는다)

```bash
git add .gitignore tools/build_docs_pdf.py tests/test_build_docs_pdf.py docs/data-interface/정의서.pdf
git commit -m "feat: 정의서 PDF 생성과 무시 규칙(input·.venv·dist)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: 팀원 전달 패키지를 만들고 혼자서도 돌아가는지 확인한다**

```bash
rm -rf dist && mkdir -p dist/data-interface-package/{docs,tools,schemas}
cp -R docs/data-interface dist/data-interface-package/docs/
cp tools/validate_input.py dist/data-interface-package/tools/
cp -R tools/datacheck dist/data-interface-package/tools/
cp schemas/input.spec.json dist/data-interface-package/schemas/
find dist -name "__pycache__" -type d -prune -exec rm -rf {} +
(cd dist && zip -rq data-interface-package.zip data-interface-package)
ls -l dist/data-interface-package.zip
```

Expected: ZIP 파일이 생긴다.

패키지만으로 검증기가 도는지 확인한다(저장소 밖 임시 폴더에 풀어서 실행):

```bash
T="$(mktemp -d)" && unzip -q dist/data-interface-package.zip -d "$T" && (cd "$T/data-interface-package" && python3 tools/validate_input.py docs/data-interface/examples/gwangju-gwangsan --out "$T/out" --today 2026-10-04; echo "exit=$?")
```

Expected: `완료  gwangju-gwangsan` / `error 0 · warn 0 · info 1` / `exit=0`

- [ ] **Step 7: 최종 검증**

아래를 모두 실행하고 결과를 확인한다. 하나라도 실패하면 완료가 아니다.

Run: `.venv/bin/python -m unittest discover -s tests`
Expected: `OK` (skipped 0)

Run: `python3 -m unittest discover -s tests`
Expected: `OK` (test_build_docs_pdf만 skipped)

Run: `python3 tools/gen_docs.py --check`
Expected: `정의서와 템플릿이 모두 최신입니다`

Run: `for d in docs/data-interface/examples/*/; do python3 tools/validate_input.py "$d" --out "$(mktemp -d)" --today 2026-10-04 >/dev/null; echo "$d exit=$?"; done`
Expected: 두 폴더 모두 `exit=0`

Run: `python3 -c "import pathlib,re; t=pathlib.Path('docs/superpowers/specs/2026-10-04-data-interface-s1-design.md').read_text(encoding='utf-8'); print(sorted(set(re.findall(r'\b[EWI][0-9]{3}\b', t))))"`
Expected: 규칙 ID 20개(`E001 E002 E003 E101 … I202`)가 출력된다. 정의서 8절과 같은 20개인지 비교한다.

Run: `git log --oneline | head -12`
Expected: Task 1~11의 커밋이 순서대로 보인다.

완료 기준(스펙 13절) 대조:
1. `정의서.md` 0~11절·부록 + `정의서.pdf` ✔ (Task 8, 11)
2. 필드표·템플릿 일치 검사 ✔ (`gen_docs.py --check`)
3. 모든 테스트 통과, 예시 2개 error 0 ✔
4. 규칙 ID마다 그 규칙을 일으키는 테스트가 있다 ✔ (Task 2~5의 테스트: E001~E003 W001 → test_files, E101~E105 → test_rows, E106 E107 W101~W106 I201 I202 → test_domain, E108 → test_geometry)
5. `docs/data-interface/` + 검증기를 그대로 전달할 수 있다 ✔ (`dist/data-interface-package.zip`)

최종 결과를 사용자에게 보고할 때는 위 명령의 실제 출력(통과 개수, 종료 코드)을 근거로 쓴다.
