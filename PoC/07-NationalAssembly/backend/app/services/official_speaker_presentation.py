from __future__ import annotations

from typing import Any, Iterable


def apply_official_speakers(
    segments: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Use the current official speaker as the presentation grouping key.

    The provisional label is retained only on the in-memory read model. Adjacent
    segments with the same official speaker merge naturally, while a caption
    block spanning multiple official speakers splits at its existing segment
    boundaries.
    """
    result: list[dict[str, Any]] = []
    for source in segments:
        item = dict(source)
        reconciliation = item.get("official_reconciliation")
        official_name = str(
            reconciliation.get("official_speaker_name") or ""
        ).strip() if isinstance(reconciliation, dict) else ""
        if reconciliation and reconciliation.get("status") == "MATCHED" and official_name:
            item["provisional_speaker_label"] = item.get("speaker_label")
            item["speaker_label"] = official_name
            item["source_speaker_label"] = f"official:{official_name}"
            item["speaker_official"] = True
        result.append(item)
    return result
