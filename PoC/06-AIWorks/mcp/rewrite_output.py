"""Normalize selection-rewrite output without changing the user's requested content."""

from __future__ import annotations

import re


_LABEL = r"(?:수정된\s*문장|최종\s*(?:대체\s*)?문구|대체\s*문구|변경\s*문구|수정안)"
_EXPLANATION = r"(?:변경\s*사항(?:\s*설명)?|수정\s*이유|설명|해설)"


def clean(content: str) -> str:
    """Return only the replacement text when a model adds labels or explanation."""

    value = str(content or "").replace("\r\n", "\n").strip()
    value = re.sub(r"^```(?:\w+)?\s*|\s*```$", "", value, flags=re.IGNORECASE).strip()

    quoted = re.search(
        _LABEL + r"\s*\*{0,2}\s*[:：-]?\s*\*{0,2}\s*[\"“](.*?)[\"”]",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if quoted:
        value = quoted.group(1).strip()
    else:
        labelled = re.search(
            _LABEL + r"\s*\*{0,2}\s*[:：-]?\s*\*{0,2}\s*(.+)",
            value,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if labelled:
            value = re.split(
                r"\n\s*(?:#{1,6}\s*)?\*{0,2}" + _EXPLANATION,
                labelled.group(1),
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip()

    value = re.sub(r"^\*{1,2}|\*{1,2}$", "", value).strip()
    if len(value) >= 2 and value[0] in "\"'“‘" and value[-1] in "\"'”’":
        value = value[1:-1].strip()
    return value
