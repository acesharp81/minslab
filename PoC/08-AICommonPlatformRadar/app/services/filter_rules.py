from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from ..config import get_settings


@dataclass(frozen=True)
class FilterResult:
    skip: bool
    reason: str
    score: int
    matched_include_keywords: list[str]
    matched_exclude_keywords: list[str]
    needs_sample_review: bool

    def as_dict(self) -> dict:
        return asdict(self)


def _matches(text: str, keywords: list[str]) -> list[str]:
    folded = text.casefold()
    return [keyword for keyword in keywords if keyword.casefold() in folded]


@lru_cache(maxsize=1)
def load_rules() -> tuple[dict, dict]:
    root = Path(__file__).resolve().parent.parent / "rules"
    include = yaml.safe_load((root / "include_keywords.yml").read_text(encoding="utf-8"))
    exclude = yaml.safe_load((root / "exclude_keywords.yml").read_text(encoding="utf-8"))
    return include, exclude


def evaluate_notice(
    *, title: str, agency: str = "", budget_amount: int | None = None,
    attachment_names: list[str] | None = None, text_excerpt: str = "",
) -> FilterResult:
    include, exclude = load_rules()
    attachment_text = " ".join(attachment_names or [])
    title_context = f"{title} {agency} {attachment_text}"
    include_title = _matches(title_context, include.get("title_keywords", []))
    include_body = _matches(text_excerpt[:20_000], include.get("body_keywords", []))
    excluded = _matches(title, exclude.get("title_keywords", []))
    included = list(dict.fromkeys(include_title + include_body))
    high_budget = (budget_amount or 0) >= get_settings().high_budget_review_won

    score = min(100, len(include_title) * 22 + len(include_body) * 12 + (15 if high_budget else 0))
    # 제목 제외어만으로 AI 근거까지 버리지는 않는다.
    skip = bool(excluded and not included and not high_budget)
    if included:
        reason = f"AI 후보 키워드 확인: {', '.join(included[:4])}"
    elif high_budget:
        reason = "고예산 정보화 용역 표본 검토"
    elif excluded:
        reason = f"명백한 제외 후보: {', '.join(excluded[:3])}"
    else:
        reason = "본문 또는 담당자 확인 필요"
    return FilterResult(skip, reason, score, included, excluded, high_budget and not included)

