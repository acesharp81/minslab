from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
import re

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
    scope_status: str = "unclear"
    scope_reason: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _matches(text: str, keywords: list[str]) -> list[str]:
    folded = text.casefold()
    return [keyword for keyword in keywords if keyword.casefold() in folded]


_AI_SCOPE = re.compile(
    r"(?<![A-Za-z])AI(?![A-Za-z])|인공지능|생성형|챗봇|(?<![A-Za-z])LLM(?![A-Za-z])|"
    r"(?<![A-Za-z])RAG(?![A-Za-z])|머신러닝|딥러닝|지능형",
    re.IGNORECASE,
)
_PLANNING_SCOPE = re.compile(
    r"(?<![A-Za-z])(?:BPR|ISP|ISMP)(?![A-Za-z])|정보화\s*전략(?:계획)?|업무\s*프로세스\s*재설계",
    re.IGNORECASE,
)
_BUILD_NOUN = r"(?:정보\s*시스템|시스템|플랫폼|서비스|솔루션|소프트웨어|SW|정보화|데이터|챗봇|LLM|RAG|API|애플리케이션|앱|웹|기능)"
_BUILD_VERB = r"(?:구축|개발|구현|고도화|기능\s*개선|재구축|도입|전환|통합|연계\s*개발)"
_BUILD_SCOPE = re.compile(
    rf"(?:{_BUILD_NOUN}.{{0,35}}{_BUILD_VERB}|{_BUILD_VERB}.{{0,35}}{_BUILD_NOUN})",
    re.IGNORECASE | re.DOTALL,
)
_AUDIT_SERVICE = re.compile(
    r"(?:정보\s*시스템|시스템|정보화|소프트웨어|SW|IT)?\s*감리(?:\s*(?:용역|사업|업무|수행)|\s*$|\s*(?:및|·|/|\())",
    re.IGNORECASE,
)
_INDICATOR_SERVICE = re.compile(
    r"(?:성과\s*)?(?:지표|KPI).{0,20}(?:발굴|개발|도출|정립|수립)|(?:발굴|개발|도출).{0,20}(?:지표|KPI)",
    re.IGNORECASE,
)
_TRAINING_TERM = r"(?:연수|교육(?=\s|과정|프로그램|훈련|$)|훈련(?=\s|과정|프로그램|모델|$)|워크숍|세미나)"
_TRAINING_SERVICE = re.compile(
    rf"{_TRAINING_TERM}.{{0,25}}(?:운영|위탁|진행|지원|대행|용역)|"
    rf"(?:운영|위탁).{{0,25}}{_TRAINING_TERM}",
    re.IGNORECASE,
)
_MAINTENANCE_ONLY = re.compile(
    r"(?:정보\s*시스템|시스템|플랫폼|서비스|소프트웨어|SW).{0,25}(?:유지\s*관리|운영\s*지원|운영\s*및\s*유지\s*관리)",
    re.IGNORECASE,
)
_NON_BUILD_ADVISORY = re.compile(
    r"(?:컨설팅|자문|실태\s*조사|수요\s*조사|사례\s*조사|홍보|캠페인)(?:\s*용역|\s*사업|\s*$)",
    re.IGNORECASE,
)


def evaluate_service_scope(title: str, text_excerpt: str = "") -> tuple[str, str]:
    """Limit inspection to IT construction and construction-planning services."""
    title = title.strip()
    early_body = (text_excerpt or "")[:6_000]

    # The contract's primary deliverable controls. Generic references to the
    # system being audited or to a training "model" must not make it a build.
    if _AUDIT_SERVICE.search(title):
        return "non_target", "정보화 서비스 구축이 아니라 감리 수행이 주된 용역이므로 검사 비대상입니다."
    if _INDICATOR_SERVICE.search(title):
        return "non_target", "정보화 서비스 구축이 아니라 지표 발굴·개발이 주된 용역이므로 검사 비대상입니다."
    if _TRAINING_SERVICE.search(title):
        return "non_target", "정보화 서비스 구축이 아니라 연수·교육·훈련 운영이 주된 용역이므로 검사 비대상입니다."
    if _MAINTENANCE_ONLY.search(title) and not re.search(r"고도화|기능\s*개선|재구축|개발", title, re.IGNORECASE):
        return "non_target", "신규 구축·고도화가 아닌 기존 정보화 서비스 운영·유지관리 용역이므로 검사 비대상입니다."
    if _NON_BUILD_ADVISORY.search(title):
        return "non_target", "정보화 서비스 구축이 아니라 조사·자문·컨설팅이 주된 용역이므로 검사 비대상입니다."

    if _PLANNING_SCOPE.search(title):
        return "target", "정보화 서비스 구축을 위한 BPR·ISP·ISMP 기획 용역입니다."
    if _BUILD_SCOPE.search(title):
        return "target", "정보시스템·플랫폼·AI 서비스의 구축·개발·고도화가 사업 범위에 명시되어 있습니다."

    research = bool(re.search(r"연구(?:\s*용역)?|조사\s*연구", title, re.IGNORECASE))
    if research and (
        _PLANNING_SCOPE.search(early_body)
        or _BUILD_SCOPE.search(title)
        or re.search(r"정보화|정보\s*시스템|AI\s*서비스|인공지능\s*서비스", title, re.IGNORECASE)
        and re.search(r"구축\s*(?:방안|계획|전략|타당성)|도입\s*(?:방안|계획|전략|타당성)", title, re.IGNORECASE)
    ):
        return "target", "정보화 서비스 구축을 준비하기 위한 연구용역입니다."
    if research:
        return "non_target", "연구용역이지만 정보화 서비스 구축을 준비하는 연구 범위가 확인되지 않아 검사 비대상입니다."

    # A vague title can be rescued only by an early, strong build deliverable.
    # This is deliberately not applied to the explicit exclusions above.
    if _BUILD_SCOPE.search(early_body) or _PLANNING_SCOPE.search(early_body):
        return "target", "사업 목적·주요 과업에서 정보화 서비스 구축 또는 구축기획 범위를 확인했습니다."
    if _AI_SCOPE.search(title) and early_body.strip():
        return "non_target", "AI 관련 용역이지만 정보화 서비스 구축 또는 이를 위한 BPR·ISP·연구용역 범위가 확인되지 않아 검사 비대상입니다."
    return "unclear", "제목만으로 정보화 서비스 구축·구축기획 용역 여부가 명확하지 않습니다."


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
    scope_status, scope_reason = evaluate_service_scope(title, text_excerpt)

    score = min(100, len(include_title) * 22 + len(include_body) * 12 + (15 if high_budget else 0))
    # 제목 제외어만으로 AI 근거까지 버리지는 않는다.
    skip = scope_status == "non_target" or bool(excluded and not included and not high_budget)
    if scope_status == "non_target":
        score = 0
        high_budget = False
        reason = scope_reason
    elif included:
        reason = f"AI 후보 키워드 확인: {', '.join(included[:4])}"
    elif high_budget:
        reason = "고예산 정보화 용역 표본 검토"
    elif excluded:
        reason = f"명백한 제외 후보: {', '.join(excluded[:3])}"
    else:
        reason = "본문 또는 담당자 확인 필요"
    return FilterResult(
        skip, reason, score, included, excluded, high_budget and not included,
        scope_status, scope_reason,
    )
