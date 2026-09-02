from __future__ import annotations


MINISTRY_ALIASES = {
    "재경부": "재정경제부",
    "과기정통부": "과학기술정보통신부",
    "과기통신부": "과학기술정보통신부",
    "행안부": "행정안전부",
    "국토부": "국토교통부",
    "국조실": "국무조정실",
    "산업부": "산업통상부",
    "복지부": "보건복지부",
    "행복청": "행정중심복합도시건설청",
    "중기부": "중소벤처기업부",
    "공정위": "공정거래위원회",
    "금융위": "금융위원회",
    "질병청": "질병관리청",
}


def canonical_ministry_name(value: object) -> str:
    name = " ".join(str(value or "").split())
    return MINISTRY_ALIASES.get(name, name)
