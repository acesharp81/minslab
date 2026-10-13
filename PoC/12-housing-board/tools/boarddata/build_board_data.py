#!/usr/bin/env python3
"""상황판 화면이 읽는 자료(data/board/*.json)를 data/raw·data/processed 의 원천에서 만든다.

  python3 tools/boarddata/build_board_data.py           # data/board/molit.json · lh-completion.json · sources.json 을 쓴다
  python3 tools/boarddata/build_board_data.py --check   # 쓰지 않고 저장소의 파일과 같은지만 본다(다르면 1)

항등식(시행주체 합=총계, 시도 합=전국, 인허가 월 흐름의 연합계=연간 실적)이 하나라도 어긋나면 쓰지 않고 멈춘다.
Vercel 빌드에는 data/raw·processed·tools 가 올라가지 않으므로 결과를 커밋한다. 시험: tests/test_boarddata.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from boarddata import catalog, lh, molit  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LH_FILE = "15141761_한국토지주택공사_공공주택 준공예정현황_20260127.csv"


def make(root: Path = ROOT) -> dict[str, dict]:
    p = root / "data" / "processed"
    permit, start, complete = (molit.read_csv(p / f) for f in ("molit_인허가_월별누계.csv", "molit_착공_월계.csv", "molit_준공_월계.csv"))
    sale, annual = molit.read_csv(p / "molit_분양_공동주택.csv"), molit.read_csv(p / "molit_인허가_지역별_연간.csv")
    data = molit.build(permit, start, complete, sale)
    bad = molit.verify(data, permit, annual)
    if bad:
        raise SystemExit("항등식이 어긋난다:\n  " + "\n  ".join(bad[:20]))
    blocks = lh.read_blocks(root / "data" / "raw" / "datagokr" / LH_FILE)
    return {"molit.json": data, "lh-completion.json": lh.build(blocks, "2026-01-27"), "sources.json": catalog.build(root)}


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="build_board_data")
    ap.add_argument("--check", action="store_true", help="쓰지 않고 저장소의 파일과 같은지만 본다")
    args = ap.parse_args(argv)
    out = ROOT / "data" / "board"
    made = {name: dump(obj) for name, obj in make().items()}
    if args.check:
        stale = [n for n, text in made.items() if not (out / n).exists() or (out / n).read_text(encoding="utf-8") != text]
        print("최신입니다" if not stale else "낡았습니다: " + ", ".join(stale))
        return 1 if stale else 0
    out.mkdir(parents=True, exist_ok=True)
    for name, text in made.items():
        (out / name).write_text(text, encoding="utf-8")
        print(f"쓴 파일 data/board/{name} ({len(text.encode('utf-8')) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
