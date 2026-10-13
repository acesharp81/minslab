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
