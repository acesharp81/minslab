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
