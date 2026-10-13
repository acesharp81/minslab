"""입력 파일 읽기: CSV, GeoJSON."""
from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

from .model import Row, Table

IGNORED_DIRS = {"__MACOSX", "quarantine", "validation_out"}


def read_csv(path: Path | str, name: str) -> Table:
    """UTF-8(BOM 허용) CSV를 읽는다. UTF-8이 아니면 UnicodeDecodeError를 낸다."""
    text = Path(path).read_bytes().decode("utf-8-sig")
    raw = list(csv.reader(io.StringIO(text, newline="")))
    header = [h.strip() for h in raw[0]] if raw else []
    while header and header[-1] == "":
        header.pop()  # 엑셀이 서식만 남은 오른쪽 열까지 내보낸 빈 열 이름
    rows: list[Row] = []
    for n, cells in enumerate(raw[1:], start=1):  # 행 번호 = 스프레드시트 위치(헤더 제외). 빈 행도 번호를 차지한다
        if not any(c.strip() for c in cells):
            continue  # 엑셀에서 내용만 지운 행, 끝의 빈 줄 등은 표에 넣지 않는다
        values = {h: (cells[i].strip() if i < len(cells) else "") for i, h in enumerate(header)}
        rows.append(Row(n, values))
    return Table(name, header, rows)


def read_geojson_table(path: Path | str, name: str, slug: str) -> tuple[Table, list[dict]]:
    """GeoJSON FeatureCollection을 표로 읽는다. 각 Feature의 properties가 한 행이 된다.

    행에는 region_slug 가 자동으로 들어간다(참조 검사용). 형식이 틀리면 ValueError.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise ValueError("FeatureCollection이 아님")
    features = [f if isinstance(f, dict) else {"type": "Feature", "properties": {}, "geometry": None}
                for f in data["features"]]  # 문자열·숫자 항목도 행(E101)으로 보고되도록 정규화
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
