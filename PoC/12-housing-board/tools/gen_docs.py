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
