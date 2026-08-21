"""Canonical report document model between LLM content and presentation MCPs."""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy


MANIFEST = {
    "id": "document.report-structure",
    "name": "보고서 구조화 MCP",
    "version": "0.1.0",
    "runtime": "local",
    "description": "LLM Markdown을 의미 블록으로 파싱하고 글머리표·문체를 정규화하여 양식과 내용을 분리합니다.",
    "inputs": {"markdown": {"type": "string"}, "styleProfile": {"type": "string"}, "facts": {"type": "object"}},
    "outputs": {"reportDocument": {"type": "object"}, "markdown": {"type": "string"}},
    "permissions": [],
}


STYLE_PROFILES = {
    "standard": {
        "id": "standard",
        "name": "표준 보고서",
        "listMarker": "-",
        "sentenceStyle": "preserve",
    },
    "central-government-outline": {
        "id": "central-government-outline",
        "name": "중앙부처 개조식",
        "listMarker": "-",
        "sentenceStyle": "nominal-outline",
    },
}


_MARKER = re.compile(r"^(?P<indent>\s*)(?:(?:[-*+•·○ㅇ□▪◦])\s*)+")
_ORDERED = re.compile(r"^(?P<indent>\s*)\d+[.)]\s+")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$")
_FACT_TOKEN = re.compile(r"\{\{fact:([A-Za-z0-9_.-]+)\}\}")
_SECTION_PREFIX = re.compile(
    r"^(?:(?:[IVXLCDM]+|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ]+)|\d{1,2})[.)]\s+",
    re.IGNORECASE,
)
_TITLE_PREFIX = re.compile(r"^(?:I|Ⅰ|1)[.)]\s+", re.IGNORECASE)


def select_profile(intent: str = "", requested: str = "") -> dict:
    if requested in STYLE_PROFILES:
        return deepcopy(STYLE_PROFILES[requested])
    normalized = " ".join(str(intent or "").lower().split())
    if any(term in normalized for term in ("중앙부처", "개조식", "항목식")):
        return deepcopy(STYLE_PROFILES["central-government-outline"])
    return deepcopy(STYLE_PROFILES["standard"])


def _fact_display(fact: dict) -> str:
    value = fact.get("value")
    if isinstance(value, bool):
        rendered = "예" if value else "아니오"
    elif isinstance(value, (int, float)):
        rendered = f"{value:,}"
    else:
        rendered = str(value if value is not None else "")
    unit = str(fact.get("unit") or "").strip()
    return rendered + ((" " if unit and unit[0].isalnum() else "") + unit if unit else "")


def bind_facts(markdown: str, facts: dict) -> tuple[str, list[str]]:
    used: list[str] = []

    def replace(match: re.Match) -> str:
        key = match.group(1)
        fact = facts.get(key)
        if not isinstance(fact, dict):
            return "[확인 필요: " + key + "]"
        used.append(key)
        return _fact_display(fact)

    return _FACT_TOKEN.sub(replace, str(markdown or "")), list(dict.fromkeys(used))


def _outline_sentence(text: str) -> str:
    value = str(text or "").strip()
    replacements = (
        (r"필요합니다\.?$", "필요함."),
        (r"확인됩니다\.?$", "확인됨."),
        (r"예상됩니다\.?$", "예상됨."),
        (r"추진합니다\.?$", "추진함."),
        (r"검토합니다\.?$", "검토함."),
        (r"관리합니다\.?$", "관리함."),
        (r"있습니다\.?$", "있음."),
        (r"없습니다\.?$", "없음."),
        (r"됩니다\.?$", "됨."),
        (r"합니다\.?$", "함."),
        (r"입니다\.?$", "임."),
    )
    for pattern, replacement in replacements:
        updated = re.sub(pattern, replacement, value)
        if updated != value:
            return updated
    return value


def _clean_list_text(text: str, profile: dict) -> str:
    value = str(text or "").strip()
    while True:
        updated = _MARKER.sub("", value).strip()
        updated = _ORDERED.sub("", updated).strip()
        if updated == value:
            break
        value = updated
    if profile.get("sentenceStyle") == "nominal-outline":
        value = _outline_sentence(value)
    return value


def _block_id(index: int, kind: str, text: str) -> str:
    digest = hashlib.sha256((kind + "\0" + text).encode("utf-8")).hexdigest()[:10]
    return f"block-{index:03d}-{digest}"


def _roman_number(value: int) -> str:
    number = max(1, int(value))
    parts = []
    for unit, label in (
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ):
        while number >= unit:
            parts.append(label)
            number -= unit
    return "".join(parts)


def _canonical_title(value: str) -> str:
    """Keep outline numbering out of the document title contract."""
    return _TITLE_PREFIX.sub("", str(value or "").strip()).strip()


def _central_section_heading(value: str, index: int) -> str:
    """Give top-level body sections one renderer-independent outline."""
    text = _SECTION_PREFIX.sub("", str(value or "").strip()).strip()
    return f"{_roman_number(index)}. {text}" if text else _roman_number(index) + "."


def parse(markdown: str, *, title: str = "", style_profile: str = "standard", facts: dict | None = None) -> dict:
    profile = select_profile(requested=style_profile)
    bound, used_facts = bind_facts(markdown, facts or {})
    lines = bound.replace("\r\n", "\n").split("\n")
    blocks: list[dict] = []
    table_lines: list[str] = []

    def append(kind: str, text: str, **extra) -> None:
        value = str(text or "").strip()
        if not value:
            return
        if kind == "list_item":
            value = _clean_list_text(value, profile)
        elif profile.get("sentenceStyle") == "nominal-outline" and kind == "paragraph":
            value = _outline_sentence(value)
        if not value:
            return
        blocks.append({"id": _block_id(len(blocks) + 1, kind, value), "type": kind, "text": value, **extra})

    def flush_table() -> None:
        nonlocal table_lines
        if not table_lines:
            return
        rows = []
        for raw in table_lines:
            if _TABLE_SEPARATOR.match(raw):
                continue
            cells = [cell.strip() for cell in raw.strip().strip("|").split("|")]
            if cells:
                rows.append(cells)
        if rows:
            text = "\n".join(" | ".join(row) for row in rows)
            blocks.append({"id": _block_id(len(blocks) + 1, "table", text), "type": "table", "rows": rows})
        table_lines = []

    # ``title`` is a caller fallback (often derived from the user's request),
    # not authoritative document content. The first Markdown H1 is the title
    # produced by the report model and must win when it exists.
    fallback_title = _canonical_title(title)
    inferred_title = ""
    top_level_heading_index = 0
    for raw in lines:
        line = raw.rstrip()
        if "|" in line and (line.strip().startswith("|") or line.strip().endswith("|")):
            table_lines.append(line)
            continue
        flush_table()
        stripped = line.strip()
        if not stripped:
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            level = len(heading.group(1))
            value = heading.group(2).strip()
            if level == 1 and not inferred_title:
                inferred_title = _canonical_title(value)
                continue
            elif level == 1 and _canonical_title(value) in {inferred_title, fallback_title}:
                continue
            else:
                if level == 2 and profile.get("id") == "central-government-outline":
                    top_level_heading_index += 1
                    value = _central_section_heading(value, top_level_heading_index)
                append("heading", value, level=max(2, level))
            continue
        list_match = _MARKER.match(line) or _ORDERED.match(line)
        if list_match:
            indent = len(list_match.groupdict().get("indent") or "")
            append("list_item", line[list_match.end():], level=max(1, indent // 2 + 1))
            continue
        if stripped.startswith("※"):
            append("note", stripped.removeprefix("※").strip())
        else:
            append("paragraph", stripped)
    flush_table()
    document = {
        "contractVersion": "1.0",
        "title": inferred_title or fallback_title or "AIWorks 파생 보고서",
        "styleProfile": profile,
        "blocks": blocks,
        "factRefs": used_facts,
        "source": {"format": "markdown", "content": str(markdown or "")},
    }
    document["normalizedMarkdown"] = compile_markdown(document)
    document["validation"] = validate(document)
    return document


def compile_markdown(document: dict) -> str:
    lines = ["# " + str(document.get("title") or "AIWorks 파생 보고서").strip(), ""]
    for block in document.get("blocks") or []:
        kind = block.get("type")
        if kind == "heading":
            lines.extend(["#" * max(2, min(6, int(block.get("level") or 2))) + " " + str(block.get("text") or "").strip(), ""])
        elif kind == "list_item":
            level = max(1, min(4, int(block.get("level") or 1)))
            lines.append("  " * (level - 1) + "- " + _clean_list_text(block.get("text") or "", document.get("styleProfile") or {}))
        elif kind == "table":
            rows = block.get("rows") or []
            if rows:
                width = max(len(row) for row in rows)
                normalized = [list(row) + [""] * (width - len(row)) for row in rows]
                lines.append("| " + " | ".join(normalized[0]) + " |")
                lines.append("| " + " | ".join(["---"] * width) + " |")
                lines.extend("| " + " | ".join(row) + " |" for row in normalized[1:])
                lines.append("")
        elif kind == "note":
            lines.extend(["※ " + str(block.get("text") or "").strip(), ""])
        else:
            lines.extend([str(block.get("text") or "").strip(), ""])
    return "\n".join(lines).strip()


def validate(document: dict) -> dict:
    errors = []
    blocks = document.get("blocks") or []
    if not str(document.get("title") or "").strip():
        errors.append("title.required")
    if not blocks:
        errors.append("blocks.required")
    for block in blocks:
        if block.get("type") == "list_item" and _MARKER.match(str(block.get("text") or "")):
            errors.append("list-marker.embedded:" + str(block.get("id") or ""))
    return {"passed": not errors, "errors": errors, "blocks": len(blocks)}
