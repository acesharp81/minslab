"""정의서 4절의 상태 계산 규칙. 이벤트 목록(단지 단위) → 5개 상태 중 하나.

이벤트: {"type", "date"(YYYY-MM-DD 또는 YYYY-MM), "planned"(예정이면 True), "value", "suspect"(의심이면 True)}
처음 맞는 규칙으로 정한다. suspect 이벤트는 쓰지 않는다. 기준일(today)은 계산하는 날.
  1. 입주 단계: 실제 completion_inspection 또는 move_in이 있다.
     또는 structure_observed가 있고 notice 또는 실제 permit_approved가 있으며 2·3에 해당하지 않는다.
  2. 준공 임박: 가장 최근 progress ≥ 90이고 move_in(예정 포함)이 기준일부터 3개월 안.
  3. 건설 단계: 실제 construction_start가 있거나 0보다 큰 progress가 있다.
  4. 분양중: notice가 있고 가장 최근 공고일이 기준일로부터 12개월 안.
  5. 계획: 그 밖.
준공 후에 찍힌 permit_approved(변경허가)는 무시한다 — 실제 준공이 있으면 1번에서 이미 끝나므로 결과에 영향이 없다.
"""
from __future__ import annotations

import calendar
from datetime import date

STATUS_ORDER = ["계획", "분양중", "건설 단계", "준공 임박", "입주 단계"]


def parse_day(s: str) -> date:
    s = str(s).strip()
    if len(s) == 8 and s.isdigit():
        return date(int(s[:4]), int(s[4:6]), int(s[6:]))
    parts = s.split("-")
    if len(parts) == 2:
        return date(int(parts[0]), int(parts[1]), 1)
    return date(int(parts[0]), int(parts[1]), int(parts[2]))


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _is_month(s: str) -> bool:
    return len(str(s).strip().split("-")) == 2


def flag_future(events: list[dict], today: date) -> list[dict]:
    """실제(예정 아님) 사건의 날짜가 기준일보다 미래면 suspect=True를 붙인 사본을 돌려준다(정의서 E106·함정 4)."""
    out = []
    for e in events:
        e2 = dict(e)
        if not e.get("planned") and e.get("date"):
            d = parse_day(e["date"])
            future = (d.year, d.month) > (today.year, today.month) if _is_month(e["date"]) else d > today
            if future:
                e2["suspect"] = True
        out.append(e2)
    return out


def _within_next_3_months(s: str, today: date) -> bool:
    d = parse_day(s)
    if _is_month(s):
        diff = (d.year * 12 + d.month) - (today.year * 12 + today.month)
        return 0 <= diff <= 3
    return today <= d <= add_months(today, 3)


def compute_status(events: list[dict], today: date) -> str:
    ev = [e for e in events if not e.get("suspect") and e.get("date")]

    def actual(e):
        return not e.get("planned") and parse_day(e["date"]) <= today

    def of(t):
        return [e for e in ev if e.get("type") == t]

    if any(actual(e) for e in of("completion_inspection") + of("move_in")):
        return "입주 단계"

    progress = sorted((e for e in of("progress") if e.get("value") is not None), key=lambda e: parse_day(e["date"]))
    latest = progress[-1]["value"] if progress else None
    if latest is not None and latest >= 90 and any(_within_next_3_months(e["date"], today) for e in of("move_in")):
        return "준공 임박"

    if any(actual(e) for e in of("construction_start")) or any((e.get("value") or 0) > 0 for e in progress):
        return "건설 단계"

    if of("structure_observed") and (of("notice") or any(actual(e) for e in of("permit_approved"))):
        return "입주 단계"

    notices = [parse_day(e["date"]) for e in of("notice")]
    if notices and add_months(today, -12) <= max(notices) <= today:
        return "분양중"

    return "계획"
