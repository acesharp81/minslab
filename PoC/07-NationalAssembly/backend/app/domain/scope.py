from __future__ import annotations


TARGET_COMMITTEES: tuple[str, ...] = (
    "행정안전위원회",
    "예산결산특별위원회",
    "법제사법위원회",
)


def is_target_committee(committee_name: str | None) -> bool:
    return committee_name in TARGET_COMMITTEES
