"""Provider-independent free-quota exhaustion and reset-time decisions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime


HOURLY_RECHECK_SECONDS = 60 * 60
MAX_TRUSTED_RESET_SECONDS = 7 * 24 * 60 * 60
TRUSTED_RETRY_SOURCES = {"error_body", "response_header", "resource_header"}

_EXHAUSTION_PATTERNS = (
    re.compile(r"free-models-per-day", re.I),
    re.compile(r"daily\s+free\s+allocation", re.I),
    re.compile(r"used\s+up.{0,80}\bfree\b", re.I | re.S),
    re.compile(r"\b(?:tokens?|requests?)[ _-]*per[ _-]*day\b", re.I),
    re.compile(r"(?:tokens?|requests?)perday", re.I),
    re.compile(r"\b(?:tpd|rpd)\b", re.I),
    re.compile(r"insufficient_quota", re.I),
    re.compile(r"free[_ -]?tier.{0,100}(?:quota|limit|requests?)", re.I | re.S),
)

_EXPLICIT_RETRY_PATTERNS = (
    re.compile(r"please\s+(?:try|retry)\s+again\s+in\s+([0-9.]+(?:ms|s|m|h|d)(?:[0-9.]+(?:ms|s|m|h|d))*)", re.I),
    re.compile(r"retry(?:ing)?\s+(?:in|after)\s+([0-9.]+(?:ms|s|m|h|d)(?:[0-9.]+(?:ms|s|m|h|d))*)", re.I),
    re.compile(r'"retryDelay"\s*:\s*"([^"]+)"', re.I),
)


@dataclass(frozen=True)
class QuotaLockDecision:
    confirmed_exhaustion: bool
    lock_until: str = ""
    lock_mode: str = ""
    confidence: str = ""
    reset_source: str = ""
    reason: str = ""


def duration_seconds(value: str) -> float:
    text = str(value or "").strip().lower()
    if not text:
        return 0.0
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    total = 0.0
    for amount, unit in re.findall(r"(\d+(?:\.\d+)?)(ms|s|m|h|d)", text):
        number = float(amount)
        if unit == "ms":
            total += number / 1000.0
        elif unit == "s":
            total += number
        elif unit == "m":
            total += number * 60
        elif unit == "h":
            total += number * 3600
        else:
            total += number * 86400
    return total


def _aware_now(reference: datetime | None = None) -> datetime:
    current = reference or datetime.now().astimezone()
    return current if current.tzinfo else current.replace(tzinfo=timezone.utc)


def _valid_future(value: str, reference: datetime) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except Exception:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=reference.tzinfo)
    seconds = (parsed - reference).total_seconds()
    return parsed if 1 <= seconds <= MAX_TRUSTED_RESET_SECONDS else None


def confirmed_free_quota_exhaustion(message: str, status: int = 0) -> bool:
    """Require explicit free/daily allocation evidence; a plain 429 is not enough."""
    text = str(message or "")
    if not any(pattern.search(text) for pattern in _EXHAUSTION_PATTERNS):
        return False
    lowered = text.casefold()
    exhaustion_words = ("exceed", "reached", "used up", "limit", "allocation", "insufficient", "quota")
    return any(word in lowered for word in exhaustion_words) or int(status or 0) in {402, 403, 429}


def _explicit_retry_seconds(message: str) -> float:
    for pattern in _EXPLICIT_RETRY_PATTERNS:
        match = pattern.search(str(message or ""))
        if match:
            seconds = duration_seconds(match.group(1))
            if 0 < seconds <= MAX_TRUSTED_RESET_SECONDS:
                return max(1.0, seconds)
    return 0.0


def quota_lock_decision(error: Exception, reference: datetime | None = None) -> QuotaLockDecision:
    """Choose an exact reset only when the exhaustion and reset signal are both strong."""
    now = _aware_now(reference)
    message = str(error or "")[:1000]
    status = int(getattr(error, "status", 0) or 0)
    if not confirmed_free_quota_exhaustion(message, status):
        return QuotaLockDecision(False)

    retry_seconds = _explicit_retry_seconds(message)
    if retry_seconds:
        until = now + timedelta(seconds=retry_seconds)
        return QuotaLockDecision(
            True, until.isoformat(timespec="seconds"), "exact_reset", "high", "error_body", message,
        )

    retry_source = str(getattr(error, "retry_source", "") or "")
    retry_at = _valid_future(str(getattr(error, "retry_after", "") or ""), now)
    if retry_at and retry_source in TRUSTED_RETRY_SOURCES:
        return QuotaLockDecision(
            True, retry_at.isoformat(timespec="seconds"), "exact_reset", "high", retry_source, message,
        )

    until = now + timedelta(seconds=HOURLY_RECHECK_SECONDS)
    return QuotaLockDecision(
        True, until.isoformat(timespec="seconds"), "hourly_recheck", "low", "hourly_recheck", message,
    )
