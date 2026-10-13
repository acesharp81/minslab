"""LH 공공주택 준공예정현황(공공데이터포털 15141761, CP949 CSV) → 블록 목록. 입출력은 read_blocks 뿐.

열: 사업지구명, 블록명, 위치(문자열), 공급유형, 세대수, 준공예정일. 위치는 코드가 아니라 문자열이라 첫 마디(시도 이름)로만 시도를 가른다.
광주·전남은 현재 행정구역(코드 12 전남광주)으로 합친다(molit.py 와 같은 결정). 파일 기준일은 2026-01-27(파일 이름)이라 8개월 묵었다.
"""
from __future__ import annotations

import csv

SIDO_BY_NAME = {
    "서울특별시": "11", "부산광역시": "26", "대구광역시": "27", "인천광역시": "28", "광주광역시": "12", "대전광역시": "30",
    "울산광역시": "31", "세종특별자치시": "36", "경기도": "41", "충청북도": "43", "충청남도": "44", "경상북도": "47",
    "경상남도": "48", "제주특별자치도": "50", "강원특별자치도": "51", "전북특별자치도": "52", "전라남도": "12",
}


def read_blocks(path) -> list[dict]:
    with open(path, encoding="cp949", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        first = r["위치"].split()[0]
        if first not in SIDO_BY_NAME:
            raise ValueError(f"알 수 없는 시도 이름: {r['위치']}")
        out.append({
            "district": r["사업지구명"].strip(), "block": r["블록명"].strip(), "location": " ".join(r["위치"].split()),
            "type": r["공급유형"].strip(), "units": int(r["세대수"]), "date": r["준공예정일"].strip(), "sido": SIDO_BY_NAME[first],
        })
    out.sort(key=lambda b: (b["date"], b["district"], b["block"]))
    return out


def build(blocks: list[dict], source_as_of: str) -> dict:
    return {
        "schema": "board-lh-completion/1",
        "source": {"provider": "한국토지주택공사", "dataset": "공공주택 준공예정현황", "id": "15141761"},
        "sourceAsOf": source_as_of,
        "count": len(blocks),
        "units": sum(b["units"] for b in blocks),
        "blocks": blocks,
    }
