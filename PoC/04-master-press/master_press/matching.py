from __future__ import annotations

import re


SPACE_RE = re.compile(r"\s+")
LATIN_TERM_RE = re.compile(r"^[a-z0-9][a-z0-9+._/-]*$", re.I)
BOILERPLATE_PATTERNS = (
    re.compile(r"(?:무단\s*전재|무단전재)[^.!?。！？\n]{0,160}(?:금지|금합니다)", re.I),
    re.compile(r"ai\s*(?:학습|training)[^.!?。！？\n]{0,100}(?:금지|불가|제한)", re.I),
    re.compile(r"저작권자[^.!?。！？\n]{0,160}(?:금지|금합니다|reserved)", re.I),
    re.compile(r"copyright\s*(?:©|\(c\))?[^.!?。！？\n]{0,160}", re.I),
)


def normalize(value: object) -> str:
    return SPACE_RE.sub(" ", str(value or "").casefold()).strip()


def strip_article_boilerplate(value: object) -> str:
    """Remove publisher/footer text that must never count as an article topic."""
    text = str(value or "")
    for pattern in BOILERPLATE_PATTERNS:
        text = pattern.sub(" ", text)
    return SPACE_RE.sub(" ", text).strip()


def term_in_text(term: object, text: object) -> bool:
    """Match short Latin terms as tokens so AI does not match e-mail/URL fragments."""
    needle = normalize(term)
    haystack = normalize(text)
    if not needle or not haystack:
        return False
    if LATIN_TERM_RE.fullmatch(needle):
        return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack, re.I) is not None
    return needle in haystack


def expanded_case_terms(case: dict, keys: tuple[str, ...] = ("required_terms", "include_terms")) -> dict[str, list[str]]:
    synonyms = case.get("synonym_terms") if isinstance(case.get("synonym_terms"), dict) else {}
    result: dict[str, list[str]] = {}
    for key in keys:
        for raw_term in case.get(key, []):
            term = str(raw_term or "").strip()
            if not term:
                continue
            variants = [term]
            synonym_values = synonyms.get(raw_term, synonyms.get(term, []))
            if isinstance(synonym_values, list):
                variants.extend(str(value).strip() for value in synonym_values if str(value).strip())
            result[term] = list(dict.fromkeys(variants))
    return result


def article_topic_fields(article: dict) -> tuple[str, str, str]:
    return (
        str(article.get("title") or ""),
        str(article.get("snippet") or ""),
        strip_article_boilerplate(article.get("body") or ""),
    )
