"""국토교통 통계누리 주택건설실적통계(data/processed/molit_*.csv) → 시도·시행주체별 월 계열. 입출력 없는 순수 함수와 항등식 검증.

원천의 모양(2026-10-09 직접 확인):
- 월별 표 3종(인허가·착공·준공)은 (기간, 구분, 부문, 시도, 호수) 행이다. 총계는 구분·부문이 모두 `총계`,
  시행주체 4분류는 지자체·LH·주택업체의 `소계`와 민간(구분 `민간부문`, 부문은 착공·준공이 `소계`, 인허가가 `민간부문`)이다.
  네 분류의 합은 총계와 같고, 시도 합은 전국과 같다(verify 가 모든 월에서 확인한다).
- 인허가 '월별누계'는 연초부터의 누계다(연내 감소 0건, 12월 값 = 연간 실적). 월 흐름은 차분이고 1월은 그 값 자체다.
  자료가 2021-09부터라 첫 달(2021-09)의 월 흐름은 알 수 없다(None).
- 광주·전남은 2026-07부터 `전남광주` 하나로 나온다(그 달부터 둘은 없다). 현재 행정구역(코드 12) 기준으로 잇기 위해
  그 이전 달은 광주+전남을 합산한다(사용자 결정 2026-10-09).
- 분양(공동주택) 표는 (기간, 구분1, 구분2, 순계_*, 누계_*)이고 순계가 월 값이다. 시행주체 구분은 없다.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

ACTORS = ("지자체", "LH", "주택업체", "민간")
NATION = "00"
# 행정표준코드 시도 2자리(2026-10-05 전국 표, lib/codes.js KNOWN_SIDO 와 같은 16개). 12 = 전남광주통합특별시(2026-07 통합)
SIDO = (
    ("11", "서울"), ("26", "부산"), ("27", "대구"), ("28", "인천"), ("30", "대전"), ("31", "울산"), ("36", "세종"), ("41", "경기"),
    ("43", "충북"), ("44", "충남"), ("47", "경북"), ("48", "경남"), ("50", "제주"), ("51", "강원"), ("52", "전북"), ("12", "전남광주"),
)
NAME_TO_CODE = {name: code for code, name in SIDO}
NAME_TO_CODE.update({"광주": "12", "전남": "12", "전국": NATION})
MERGED = {"12": {"광주", "전남"}}   # 이 코드는 (광주+전남) 또는 (전남광주) 중 한 쪽만 한 달에 나온다


def read_csv(path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def months_of(rows: list[dict], key: str = "기간") -> list[str]:
    return sorted({r[key] for r in rows})


def actor_of(gubun: str, bubun: str) -> str | None:
    """행 → 'total' | 시행주체 4분류 | None(그 밖의 세부 행: 부문별 국민임대·공공임대 등)."""
    if gubun == "총계" and bubun == "총계":
        return "total"
    if gubun in ("지자체", "LH", "주택업체") and bubun == "소계":
        return gubun
    if gubun == "민간부문" and bubun in ("소계", "민간부문"):
        return "민간"
    return None


def _collect(items):
    """items = (시도 이름, 라벨, 달, 값) → {code: {라벨: {달: 값}}}. 이름 집합이 규칙에 맞는지 검사한다."""
    acc = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    names = defaultdict(set)
    seen = set()
    for name, label, month, value in items:
        code = NAME_TO_CODE.get(name)
        if code is None:
            raise ValueError(f"알 수 없는 시도 이름: {name}")
        if (name, label, month) in seen:
            raise ValueError(f"같은 행이 두 번 있다: {name} {label} {month}")
        seen.add((name, label, month))
        acc[code][label][month] += value
        names[(code, label, month)].add(name)
    for (code, label, month), ns in names.items():
        ok = ns in ({"광주", "전남"}, {"전남광주"}) if code in MERGED else len(ns) == 1
        if not ok:
            raise ValueError(f"시도 {code} {label} {month} 의 이름 구성이 이상하다: {sorted(ns)}")
    return acc


def monthly_series(rows: list[dict], value_key: str) -> dict:
    """월별 표(인허가·착공·준공) → {code: {'total'|시행주체: {달: 호수}}}."""
    items = []
    for r in rows:
        label = actor_of(r["구분"], r["부문"])
        if label:
            items.append((r["시도"], label, r["기간"], int(r[value_key])))
    return _collect(items)


def sale_series(rows: list[dict], value_key: str = "순계_합계") -> dict:
    """분양(공동주택) 표 → {code: {'total': {달: 호수}}}. 합계 행은 전국, 시도 행(소계 제외)은 시도."""
    items = []
    for r in rows:
        if r["구분1"] == "합계":
            items.append(("전국", "total", r["기간"], int(r[value_key])))
        elif r["구분2"] != "소계":
            items.append((r["구분2"], "total", r["기간"], int(r[value_key])))
    return _collect(items)


def cumulative_to_flow(by_month: dict, months: list[str]) -> list:
    """연초 누계 → 월 흐름. 1월은 값 그대로, 그 밖의 달은 직전 달(같은 해)과의 차이, 직전 달이 자료에 없으면 None."""
    out, prev = [], None
    for m in months:
        cum = by_month.get(m)
        if cum is None:
            out.append(None)
        elif m.endswith("-01"):
            out.append(cum)
        elif prev is not None and prev[0][:4] == m[:4] and _next_month(prev[0]) == m and prev[1] is not None:
            out.append(cum - prev[1])
        else:
            out.append(None)
        prev = (m, cum)
    return out


def _next_month(m: str) -> str:
    y, mo = int(m[:4]), int(m[5:7])
    return f"{y + (mo == 12)}-{1 if mo == 12 else mo + 1:02d}"


def to_list(by_month: dict, months: list[str]) -> list:
    return [by_month.get(m) for m in months]


def provisional_months(rows: list[dict]) -> list[str]:
    return sorted({r["기간"] for r in rows if r.get("잠정치") == "Y"})


def build(permit_rows, start_rows, complete_rows, sale_rows) -> dict:
    """네 표 → data/board/molit.json 의 내용."""
    months = months_of(permit_rows)
    for name, rs in (("착공", start_rows), ("준공", complete_rows), ("분양", sale_rows)):
        if months_of(rs) != months:
            raise ValueError(f"{name} 표의 기간이 인허가 표와 다르다")
    prov = sorted(set(provisional_months(permit_rows)) | set(provisional_months(start_rows)) | set(provisional_months(complete_rows)))
    codes = [NATION] + [c for c, _ in SIDO]

    def flows(series, cumulative):
        out = {}
        for code in codes:
            s = series[code]
            conv = (lambda bm: cumulative_to_flow(bm, months)) if cumulative else (lambda bm: to_list(bm, months))
            out[code] = {"total": conv(s["total"]), "actors": {a: conv(s[a]) for a in ACTORS}}
        return out

    permit = monthly_series(permit_rows, "인허가실적_호")
    start = monthly_series(start_rows, "착공실적_호")
    complete = monthly_series(complete_rows, "준공실적_호")
    sale = sale_series(sale_rows)
    return {
        "schema": "board-molit/1",
        "months": months,
        "provisional": prov,
        "sido": [{"code": NATION, "name": "전국"}] + [{"code": c, "name": n} for c, n in SIDO],
        "actors": list(ACTORS),
        "metrics": {
            "permit": {"label": "인허가", "unit": "호", "basis": "통계누리 월별누계(연초 누계)의 차분", "series": flows(permit, True)},
            "start": {"label": "착공", "unit": "호", "basis": "통계누리 월계", "series": flows(start, False)},
            "complete": {"label": "준공", "unit": "호", "basis": "통계누리 월계", "series": flows(complete, False)},
            "sale": {"label": "분양(공동주택)", "unit": "호", "basis": "통계누리 분양실적 순계", "series": {c: {"total": to_list(sale[c]["total"], months)} for c in codes}},
        },
    }


def verify(data: dict, permit_rows, annual_rows) -> list[str]:
    """항등식. 어긋나면 사람이 읽을 문장 목록을 돌려준다(빈 목록이면 통과)."""
    bad = []
    months, codes = data["months"], [s["code"] for s in data["sido"]]
    n = len(months)
    for key in ("permit", "start", "complete"):
        ser = data["metrics"][key]["series"]
        for code in codes:
            for i in range(n):
                t = ser[code]["total"][i]
                a = [ser[code]["actors"][x][i] for x in ACTORS]
                if t is None:
                    if any(v is not None for v in a):
                        bad.append(f"{key} {code} {months[i]}: 총계는 없는데 시행주체는 있다")
                    continue
                if None in a:
                    bad.append(f"{key} {code} {months[i]}: 시행주체 값이 비었다")
                elif sum(a) != t:
                    bad.append(f"{key} {code} {months[i]}: 시행주체 합 {sum(a)} ≠ 총계 {t}")
                if t < 0:
                    bad.append(f"{key} {code} {months[i]}: 음수 {t}")
        for i in range(n):
            nat = ser[NATION]["total"][i]
            if nat is None:
                continue
            s = sum(ser[c]["total"][i] for c in codes if c != NATION)
            if s != nat:
                bad.append(f"{key} {months[i]}: 시도 합 {s} ≠ 전국 {nat}")
    sale = data["metrics"]["sale"]["series"]
    for i in range(n):
        s = sum(sale[c]["total"][i] for c in codes if c != NATION)
        if s != sale[NATION]["total"][i]:
            bad.append(f"sale {months[i]}: 시도 합 {s} ≠ 전국 {sale[NATION]['total'][i]}")
    # 인허가 월 흐름의 연합계(= 12월 누계)가 통계누리 지역별 연간 실적과 같다(전국·시도별). 연간 표는 시도 이름 그대로라 광주+전남이 코드 12로 합쳐진다.
    annual, annual_nat = defaultdict(int), {}
    for r in annual_rows:
        g, v = r["구분"], r["인허가_호"]
        if g in ("계획", "수도권") or v in ("", None):
            continue
        if g == "실적":
            annual_nat[r["연도"]] = int(v)
        else:
            annual[(r["연도"], NAME_TO_CODE[g])] += int(v)
    permit = data["metrics"]["permit"]["series"]
    for year in sorted({m[:4] for m in months}):
        if f"{year}-01" not in months or f"{year}-12" not in months:
            continue   # 1~12월이 모두 있는 해만(2021은 1~8월 흐름을 알 수 없고, 2026은 12월이 없다)
        idx = [i for i, m in enumerate(months) if m.startswith(year)]
        for code in codes:
            want = annual_nat.get(year) if code == NATION else annual.get((year, code))
            if want is None:
                continue
            got = sum(permit[code]["total"][i] for i in idx)
            if got != want:
                bad.append(f"인허가 {year} {code}: 월 흐름 합 {got} ≠ 연간 실적 {want}")
    return bad
