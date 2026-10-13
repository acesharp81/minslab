"""'데이터 원본' 화면의 원천 카탈로그(스펙 9.3, 기획서 4.2). 건수는 파일에서 세고, 원천 기준일은 파일 이름의 날짜에서 읽는다.
모르는 값은 채우지 않고 None 으로 둔다(화면이 '확인하지 못함'을 보인다). 받은 시각(collectedAt)은 원본 파일의 저장 시각을
2026-10-09 에 확인해 고정한 값이다(복제본마다 달라지는 파일 수정 시각을 읽지 않는다: 결과가 결정적이어야 한다).
스펙 9.3 에 더한 필드: group(기관 묶음), usedBy(이 원천을 읽는 화면 경로. usedCount 의 '사용' 정의는 기획서 Q8 미결이라 건수 대신 화면 목록을 둔다).
query 는 API 원천이면 { sgg, ... }, 파일 원천이면 { file }.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from . import molit

KST = "+09:00"
MOLIT_FILES = [   # (id, 통계표 번호, 처리된 파일, 제목, 기간 끝(sourceAsOf), 설명)
    ("molit-permit-monthly", "1946", "molit_인허가_월별누계.csv", "주택건설 인허가실적(부문별, 월별 누계)", "2026-08-31",
     "시도·시행주체별 인허가 호수. 값은 연초부터의 누계라 화면은 차분(월 흐름)을 보인다. 2026-01~08은 잠정치."),
    ("molit-start-monthly", "5386", "molit_착공_월계.csv", "주택건설 착공실적(월계)", "2026-08-31", "시도·시행주체별 착공 호수. 2026-01~08은 잠정치."),
    ("molit-complete-monthly", "5372", "molit_준공_월계.csv", "주택건설 준공실적(월계)", "2026-08-31", "시도·시행주체별 준공 호수. 2026-01~08은 잠정치."),
    ("molit-sale-apt", "5557", "molit_분양_공동주택.csv", "주택건설 분양실적(공동주택)", "2026-08-31", "시도별 분양(순계) 호수. 시행주체 구분이 없다."),
    ("molit-permit-annual", "666", "molit_인허가_지역별_연간.csv", "지역별 주택건설 인허가실적(연간)", "2025-12-31", "연간 인허가 실적(2021~2025). `계획` 칸은 모든 해가 비어 있어 계획 대비 실적은 만들 수 없다."),
]
MOLIT_RAW = {"1946": "molit_1946_인허가_부문별_월별누계.csv", "5386": "molit_5386_착공_월계.csv", "5372": "molit_5372_준공_월계.csv",
             "5557": "molit_5557_분양_공동주택.csv", "666": "molit_666_인허가_지역별_연간.csv"}
MOLIT_COLLECTED = {"1946": "2026-10-03T18:38:26", "5386": "2026-10-03T18:37:58", "5372": "2026-10-03T18:38:06", "5557": "2026-10-03T18:38:15", "666": "2026-10-03T18:38:56"}

# 공공데이터포털 파일데이터(data/raw/datagokr). 이용허락은 data/README.md 1절 표.
DATAGOKR = {   # 번호: (이용허락, 받은 시각, 쓰는 화면, 설명)
    "15141761": ("제한 없음", "2026-10-02T17:10:24", ["/", "/month", "/agency"], "공공주택 준공 예정 블록의 세대수와 준공예정일. 향후 준공 예정과 LH 기관 화면이 읽는다. 파일 기준일이 8개월 묵었다."),
    "15043330": ("제한 없음", "2026-10-02T17:11:09", [], "행복주택 공급계획. 공급 시기가 2022~2025뿐이라 향후 예정으로 쓸 수 없다."),
    "15080989": ("제한 없음", "2026-10-02T17:11:10", [], "전국 LH 아파트 단지 정보(입주 단계). 아직 상황판 화면에서 쓰지 않는다."),
    "15066029": ("제한 없음", "2026-10-02T17:10:38", [], "SH 행복주택(리츠 포함) 공급계획. 아직 쓰지 않는다."),
    "15045310": ("제한 없음", "2026-10-02T17:10:39", [], "SH 국민임대주택 공급계획. 아직 쓰지 않는다."),
    "15045311": ("제한 없음", "2026-10-02T17:10:41", [], "SH 장기전세주택 공급계획. 아직 쓰지 않는다."),
    "15008820": ("제한 없음", "2026-10-02T17:10:42", [], "SH 주택분양 정보. 아직 쓰지 않는다."),
    "15124798": ("제한 없음", "2026-10-02T17:11:12", [], "SH 공공재개발·공공재건축 사업 현황(2023-11 기준). 아직 쓰지 않는다."),
    "3045249": ("제한 없음", "2026-10-02T17:11:13", [], "SH 공사계약 정보(건설 단계). 아직 쓰지 않는다."),
    "15061908": ("공공저작물 출처표시·변경금지(제3유형)", "2026-10-02T17:11:40", [], "군 특별공급 주택 공고 상세 현황. 과거 청약 공고 이력이지 사업 진행이 아니라 쓰지 않는다."),
}


def _count_csv(path: Path) -> int:
    for enc in ("utf-8-sig", "cp949"):
        try:
            with open(path, encoding=enc, newline="") as f:
                return sum(1 for _ in csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise ValueError(f"읽지 못함: {path}")


def _split_name(stem: str):
    """`번호_기관_제목_YYYYMMDD` · `번호_기관_제목`(날짜 없음) · `번호_기관 제목_YYYYMMDD`(기관과 제목이 한 마디) → (번호, 기관, 제목, 날짜|None)."""
    parts = stem.split("_")
    as_of = None
    if re.fullmatch(r"\d{8}", parts[-1]):
        y = parts.pop()
        as_of = f"{y[:4]}-{y[4:6]}-{y[6:]}"
    if not parts[0].isdigit() or len(parts) < 2:
        raise ValueError(f"파일 이름을 읽지 못함: {stem}")
    if len(parts) == 2:
        provider, _, title = parts[1].partition(" ")
    else:
        provider, title = parts[1], "_".join(parts[2:])
    if not title:
        raise ValueError(f"제목을 찾지 못함: {stem}")
    return parts[0], provider, title, as_of


def build(root: Path) -> dict:
    root = Path(root)
    items = []
    base = root / "data"
    for sid, no, fname, title, as_of, desc in MOLIT_FILES:
        n = len(molit.read_csv(base / "processed" / fname))
        items.append({
            "id": sid, "group": "국토교통부", "provider": "국토교통부(통계누리)", "dataset": f"주택건설실적통계 {no} {title}",
            "query": {"file": MOLIT_RAW[no]}, "collectedAt": MOLIT_COLLECTED[no] + KST, "sourceAsOf": as_of, "count": n,
            "description": desc, "license": None,
            "usedBy": ["/", "/area", "/month", "/agency"] if sid != "molit-permit-annual" else [],
        })
    for path in sorted((base / "raw" / "datagokr").glob("*.csv")):
        num, provider, title, as_of = _split_name(path.stem)
        if num not in DATAGOKR:
            raise ValueError(f"카탈로그에 없는 원천 파일: {path.name}")
        lic, collected, used, desc = DATAGOKR[num]
        items.append({
            "id": f"datagokr-{num}", "group": "서울주택도시공사" if provider.startswith("서울주택도시") else provider,   # 파일 이름이 개발공사·공사로 갈리지만 같은 기관(SH)이다
            "provider": "국방부(국군복지단)" if provider == "국방부" else f"{provider}(공공데이터포털)",
            "dataset": f"{num} {title}", "query": {"file": path.name}, "collectedAt": collected + KST, "sourceAsOf": as_of,
            "count": _count_csv(path), "description": desc, "license": lic, "usedBy": used,
        })
    reg = json.loads((root / "registry" / "projects.json").read_text(encoding="utf-8"))
    hub = [p for p in reg["projects"] if any(r["system"] == "hub-hs-basis" for r in p["refs"])]
    items.append({
        "id": "hub-hs-basis", "group": "국토교통부", "provider": "국토교통부(공공데이터포털)", "dataset": "건축HUB 주택인허가정보 서비스(기본개요)",
        "query": {"sgg": sorted({p["sgg"] for p in hub})}, "collectedAt": max(r["asOf"] for p in hub for r in p["refs"] if r["system"] == "hub-hs-basis"),
        "sourceAsOf": None, "count": sum(1 for p in reg["projects"] for r in p["refs"] if r["system"] == "hub-hs-basis"),
        "description": f"사업 id 레지스트리가 연결한 인허가 기록(관리번호) 수. 사업 {len(hub)}건. 레코드의 원천 기준일(crtnDay)은 아직 모으지 않았다.",
        "license": None, "usedBy": ["/projects", "/project"],
    })
    index = json.loads((root / "regions" / "index.json").read_text(encoding="utf-8"))
    for r in index["regions"]:
        region = json.loads((root / "regions" / r["slug"] / "region.json").read_text(encoding="utf-8"))
        n = sum(1 for p in reg["projects"] if p["source"]["dataset"] == f"regions/{r['slug']}/projects.json")
        items.append({
            "id": f"bundle-{r['slug']}", "group": "주택파동 지도 번들", "provider": "주택파동 지도 번들", "dataset": f"regions/{r['slug']}/projects.json",
            "query": {"file": f"regions/{r['slug']}/projects.json"}, "collectedAt": None, "sourceAsOf": region["updatedAt"], "count": n,
            "description": f"{region['name']} 지역 번들의 단지(사업 레지스트리에 연결된 수). 출처는 번들의 region.json sources 에 있다.",
            "license": None, "usedBy": ["/projects", "/project", "/map"],
        })
    return {"schema": "board-sources/1", "items": items}
