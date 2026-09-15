from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TypeVar


T = TypeVar("T")

PARSER_PRIORITY = {
    "txt": 60,
    "docx": 50,
    "hwpx": 40,
    "hwp": 35,
    "pdf": 30,
    "xlsx": 25,
    "zip": 20,
}

_BUSINESS_KOREAN_TERMS = (
    "제안요청",
    "과업지시",
    "과업내용",
    "과업설명",
    "과업요청",
    "사업설명",
    "사업내용",
    "사업개요",
    "사업계획",
    "용역설명",
    "요구사항정의",
    "요구사항명세",
    "기술규격",
)
_NON_BUSINESS_DESCRIPTION_TERMS = ("사용설명서", "조작설명서", "제품설명서")
_ANCILLARY_LIST_TERMS = ("지정상품목록", "첨부목록", "제출서류목록")
_BUSINESS_ENGLISH_PATTERNS = (
    re.compile(r"(?:^|[^a-z])rfp(?:[^a-z]|$)"),
    re.compile(r"(?:^|[^a-z])tor(?:[^a-z]|$)"),
    re.compile(r"request\s+for\s+proposals?"),
    re.compile(r"terms?\s+of\s+reference"),
    re.compile(r"statements?\s+of\s+work"),
    re.compile(r"scopes?\s+of\s+work"),
)
_KNOWN_EXTENSION = re.compile(r"\.(?:txt|docx|hwpx|pdf|xlsx|zip|hwp)\s*;?\s*$", re.IGNORECASE)


def _clean_name(filename: str) -> str:
    return unicodedata.normalize("NFKC", Path(filename.replace("\\", "/")).name).strip(" .;")


def attachment_extension(filename: str) -> str:
    match = _KNOWN_EXTENSION.search(_clean_name(filename))
    return match.group(0).strip(" .;").lower() if match else ""


def is_opaque_attachment_name(filename: str) -> bool:
    cleaned = _clean_name(filename).casefold()
    stem = re.sub(r"[^0-9a-z가-힣]+", "", cleaned)
    return not attachment_extension(cleaned) and stem in {
        "attachment", "download", "downloadfile", "downloadfiledo", "file",
    }


def is_business_document(filename: str) -> bool:
    cleaned = _clean_name(filename).casefold()
    compact = re.sub(r"\s+", "", cleaned)
    if "첨부" in compact and any(term in compact for term in _ANCILLARY_LIST_TERMS):
        return False
    if any(term in compact for term in _BUSINESS_KOREAN_TERMS):
        return True
    if "설명서" in compact and not any(term in compact for term in _NON_BUSINESS_DESCRIPTION_TERMS):
        return True
    return any(pattern.search(cleaned) for pattern in _BUSINESS_ENGLISH_PATTERNS)


def business_document_key(filename: str) -> str:
    stem = _KNOWN_EXTENSION.sub("", _clean_name(filename)).casefold()
    stem = re.sub(r"^\s*(?:첨부\s*)?\d+\s*[.)_\]-]*\s*", "", stem)
    return re.sub(r"[^0-9a-z가-힣]+", "", stem)


def parser_priority(filename: str) -> int:
    return PARSER_PRIORITY.get(attachment_extension(filename), 0)


def select_preferred_documents(
    items: Iterable[T], *, name: Callable[[T], str]
) -> list[T]:
    """Keep relevant documents and one parser-preferred format per normalized title.

    Opaque G2B download names are retained until Content-Disposition reveals the
    actual filename. Their relevance is checked again after download.
    """
    materialized = list(items)
    chosen_indexes: dict[str, int] = {}
    opaque_indexes: set[int] = set()
    for index, item in enumerate(materialized):
        filename = name(item)
        if is_opaque_attachment_name(filename):
            opaque_indexes.add(index)
            continue
        if not is_business_document(filename):
            continue
        key = business_document_key(filename)
        current_index = chosen_indexes.get(key)
        if current_index is None or parser_priority(filename) > parser_priority(name(materialized[current_index])):
            chosen_indexes[key] = index
    selected_indexes = opaque_indexes | set(chosen_indexes.values())
    return [item for index, item in enumerate(materialized) if index in selected_indexes]
