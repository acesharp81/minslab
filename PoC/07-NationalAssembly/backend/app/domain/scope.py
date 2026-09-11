from __future__ import annotations


TARGET_COMMITTEES: tuple[str, ...] = (
    "행정안전위원회",
    "예산결산특별위원회",
    "법제사법위원회",
)

NATIONAL_ASSEMBLY_BODIES: tuple[str, ...] = ("본회의",)

NATIONAL_SESSION_KEYWORDS: tuple[str, ...] = (
    "정기국회", "정기회", "국정감사", "국감",
)


def is_target_committee(committee_name: str | None) -> bool:
    return committee_name in TARGET_COMMITTEES


def is_live_transcript_scope(committee_name: str | None) -> bool:
    return is_target_committee(committee_name) or committee_name in NATIONAL_ASSEMBLY_BODIES


def is_monitored_assembly_meeting(
    committee_name: str | None, *descriptions: str | None,
) -> bool:
    del descriptions
    return is_live_transcript_scope(committee_name)
