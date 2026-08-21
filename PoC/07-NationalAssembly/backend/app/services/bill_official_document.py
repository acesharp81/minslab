from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


PARSER_VERSION = "likms-bill-pdf-sections/1.0"
SECTION_HEADINGS = {
    "PROPOSAL_REASON": re.compile(r"^\s*\d+\.\s*제안(?:설명)?(?:의)?\s*(?:이유|요지)\s*$"),
    "MAIN_CONTENT": re.compile(r"^\s*\d+\.\s*(?:주요\s*내용|전문위원\s*검토보고의\s*요지)\s*$"),
}
NEXT_HEADING = re.compile(r"^\s*\d+\.\s*\S.*$")


def extract_pdf_pages(path: Path) -> list[str]:
    completed = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        check=True, capture_output=True, text=True, timeout=30,
    )
    return [page.strip() for page in completed.stdout.split("\f") if page.strip()]


def extract_official_sections(pages: list[str]) -> list[dict[str, Any]]:
    lines: list[tuple[int, str]] = []
    for page_number, page in enumerate(pages, start=1):
        lines.extend((page_number, line.rstrip()) for line in page.splitlines())
    sections = []
    for section_kind, pattern in SECTION_HEADINGS.items():
        for index, (page_start, line) in enumerate(lines):
            if not pattern.match(line):
                continue
            content: list[str] = []
            page_end = page_start
            for candidate_page, candidate in lines[index + 1:]:
                if NEXT_HEADING.match(candidate):
                    break
                page_end = candidate_page
                stripped = candidate.strip()
                if stripped and not re.fullmatch(r"-?\s*\d+\s*-?", stripped):
                    content.append(stripped)
            text = re.sub(r"\s+", " ", " ".join(content)).strip()
            if text:
                sections.append({
                    "section_kind": section_kind,
                    "heading": line.strip(),
                    "source_span_id": f"pdf-page-{page_start}-{section_kind.lower()}",
                    "page_start": page_start,
                    "page_end": page_end,
                    "text": text,
                })
            break
    return sections
