from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from difflib import SequenceMatcher
from typing import Any, Iterable

from .official_reconciliation import compact_text, inline_diff


PRESENTATION_VERSION = "official-evidence-presentation/1.0"


def official_material_hash(rows: Iterable[dict[str, Any]]) -> str:
    """Hash semantic official speech content without UUID or formatting churn."""
    packet = [
        {
            "sequence": int(row.get("sequence_number") or 0),
            "speaker": compact_text(row.get("speaker_name")),
            "role": compact_text(row.get("speaker_role")),
            "text": compact_text(row.get("text")),
        }
        for row in rows
        if compact_text(row.get("text"))
    ]
    encoded = json.dumps(
        packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def remap_official_references(
    payload: Any, identifier_map: dict[str, str],
) -> Any:
    """Copy cached integration JSON while moving official evidence IDs forward."""
    if isinstance(payload, dict):
        return {
            key: remap_official_references(value, identifier_map)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [
            remap_official_references(value, identifier_map) for value in payload
        ]
    if isinstance(payload, str):
        return identifier_map.get(payload, payload)
    return deepcopy(payload)


def official_utterance_diff(
    live_text: object, official_text: object,
) -> dict[str, Any]:
    """Return a readable official-first diff without punctuation-only noise."""
    before = " ".join(str(live_text or "").split())
    after = " ".join(str(official_text or "").split())
    if not before:
        return {
            "spans": [{"kind": "equal", "text": after}],
            "change_count": 0,
            "comparison_status": "OFFICIAL_ONLY",
            "similarity": 0.0,
        }
    compact_before = compact_text(before)
    compact_after = compact_text(after)
    similarity = SequenceMatcher(
        None, compact_before, compact_after, autojunk=False,
    ).ratio()
    if compact_before == compact_after:
        return {
            "spans": [{"kind": "equal", "text": after}],
            "change_count": 0,
            "comparison_status": "STYLE_ONLY",
            "similarity": 1.0,
        }
    if similarity < 0.32:
        return {
            "spans": [{"kind": "equal", "text": after}],
            "change_count": 0,
            "comparison_status": "LOW_CONFIDENCE",
            "similarity": round(similarity, 3),
        }
    spans: list[dict[str, str]] = []
    for span in inline_diff(before, after):
        kind = str(span.get("kind") or "equal")
        text = str(span.get("text") or "")
        if kind != "equal" and not compact_text(text):
            if kind in {"added", "changed"}:
                spans.append({"kind": "equal", "text": text})
            continue
        spans.append(dict(span))
    return {
        "spans": spans,
        "change_count": sum(
            span.get("kind") in {"added", "changed", "deleted"}
            for span in spans
        ),
        "comparison_status": "COMPARED",
        "similarity": round(similarity, 3),
    }


def build_official_evidence_presentations(
    live_utterances: Iterable[dict[str, Any]],
    official_utterances: Iterable[dict[str, Any]],
    preferred_official_ids: Iterable[object],
    *,
    publication_stage: str,
    authority_status: str,
) -> list[dict[str, Any]]:
    official_rows = [dict(row) for row in official_utterances]
    official_by_id = {
        str(row.get("utterance_id")): row
        for row in official_rows if row.get("utterance_id")
    }
    live_by_official: dict[str, list[dict[str, Any]]] = {}
    matched_ids: list[str] = []
    for source in live_utterances:
        utterance = dict(source)
        reconciliations = list(utterance.get("official_reconciliations") or [])
        single = utterance.get("official_reconciliation")
        if isinstance(single, dict):
            reconciliations.append(single)
        for reconciliation in reconciliations:
            if reconciliation.get("status") != "MATCHED":
                continue
            official_id = str(
                reconciliation.get("official_utterance_id") or ""
            )
            if not official_id or official_id not in official_by_id:
                continue
            live_by_official.setdefault(official_id, []).append(utterance)
            if official_id not in matched_ids:
                matched_ids.append(official_id)

    selected_ids: list[str] = []
    for value in preferred_official_ids:
        official_id = str(value or "")
        if official_id in official_by_id and official_id not in selected_ids:
            selected_ids.append(official_id)
    for official_id in matched_ids:
        if official_id not in selected_ids:
            selected_ids.append(official_id)
    selected_ids.sort(
        key=lambda value: int(
            official_by_id[value].get("sequence_number") or 0
        ),
    )

    result: list[dict[str, Any]] = []
    for official_id in selected_ids:
        official = official_by_id[official_id]
        live_rows = live_by_official.get(official_id, [])
        live_text = " ".join(
            str(row.get("text") or "").strip() for row in live_rows
            if str(row.get("text") or "").strip()
        )
        comparison = official_utterance_diff(live_text, official.get("text"))
        result.append({
            **official,
            "utterance_id": official_id,
            "speaker_label": official.get("speaker_name") or "공식 발언자",
            "text": str(official.get("text") or ""),
            "source": "OFFICIAL_TRANSCRIPT_UTTERANCE",
            "publication_stage": publication_stage,
            "authority_status": authority_status,
            "segment_count": sum(
                int(row.get("segment_count") or 1) for row in live_rows
            ),
            "live_utterance_count": len(live_rows),
            "live_text": live_text,
            "diff_spans": comparison["spans"],
            "change_count": comparison["change_count"],
            "comparison_status": comparison["comparison_status"],
            "match_similarity": comparison["similarity"],
            "presentation_version": PRESENTATION_VERSION,
        })
    return result
