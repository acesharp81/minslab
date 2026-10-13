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
