from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from copy import deepcopy
from difflib import SequenceMatcher
from typing import Any

from .official_reconciliation import (
    compact_text,
    inline_diff,
    style_only_equivalent,
)

PRESENTATION_VERSION = "official-evidence-presentation/1.3"

_PARTICLE_FORMS = {
    "은", "는", "이", "가", "을", "를", "의", "에", "로", "으로",
    "와", "과", "도", "만", "께", "에서", "에게",
}
_BOUNDARY_FILLERS = {
    "예", "네", "아니요", "이상입니다", "감사합니다", "수고하셨습니다",
    "이상으로마치겠습니다", "질의를마치겠습니다", "답변감사합니다",
}
_GRAMMATICAL_FRAGMENTS = {
    "것입니다", "겁니다", "것이고", "것이며", "것인데", "것으로",
    "것입니다만",
}


def _has_semantic_text(value: object) -> bool:
    return bool(compact_text(value))


def _is_particle_only_change(before: object, after: object) -> bool:
    old = compact_text(before)
    new = compact_text(after)
    return bool(old and new and old in _PARTICLE_FORMS and new in _PARTICLE_FORMS)


def _is_non_substantive_boundary(value: object) -> bool:
    compact = compact_text(value)
    if not compact or compact in _BOUNDARY_FILLERS:
        return True
    if re.fullmatch(r"(?:예|네)?(?:감사합니다|수고하셨습니다|이상입니다)+", compact):
        return True
    # Caption turns often include the next speaker introduction. Preserve it
    # as matching context, but do not call it a wording change in this speech.
    return bool(re.fullmatch(
        r"[가-힣]{2,12}(?:위원|간사|의원)(?:입니다|이었습니다)?",
        compact,
    ))


def _has_equal_content(spans: list[dict[str, str]], start: int, step: int) -> bool:
    index = start
    while 0 <= index < len(spans):
        span = spans[index]
        if span.get("kind") == "equal" and _has_semantic_text(span.get("text")):
            return True
        index += step
    return False


def _meaningful_official_spans(
    before: str, after: str,
) -> tuple[list[dict[str, str]], list[str], int]:
    """Return after-oriented spans and keep LIVE-only text out of official copy."""
    raw = inline_diff(before, after)
    displayed: list[dict[str, str]] = []
    live_only: list[str] = []
    change_count = 0
    for index, source in enumerate(raw):
        span = dict(source)
        kind = str(span.get("kind") or "equal")
        text = str(span.get("text") or "")
        before_text = str(span.get("before") or "")
        at_edge = not _has_equal_content(raw, index - 1, -1) or not _has_equal_content(
            raw, index + 1, 1,
        )
        if kind == "deleted":
            following = raw[index + 1] if index + 1 < len(raw) else {}
            if (
                following.get("kind") == "changed"
                and str(following.get("before") or "") == text
            ):
                # One replacement is one change, not a deletion plus addition.
                continue
            cleaned = " ".join(text.split()).strip()
            compact_cleaned = compact_text(cleaned)
            if (
                not cleaned
                or compact_cleaned in _PARTICLE_FORMS
                or compact_cleaned in _GRAMMATICAL_FRAGMENTS
                or (at_edge and _is_non_substantive_boundary(cleaned))
            ):
                continue
            live_only.append(cleaned)
            change_count += 1
            continue
        if kind == "changed" and _is_particle_only_change(before_text, text):
            displayed.append({"kind": "equal", "text": text})
            continue
        if kind in {"added", "changed"}:
            if at_edge and _is_non_substantive_boundary(text):
                displayed.append({"kind": "equal", "text": text})
                continue
            change_count += 1
        displayed.append(span)
    if change_count == 0:
        return [{"kind": "equal", "text": after}], [], 0
    return displayed, live_only, change_count


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
            "live_only_fragments": [],
        }
    compact_before = compact_text(before)
    compact_after = compact_text(after)
    similarity = SequenceMatcher(
        None, compact_before, compact_after, autojunk=False,
    ).ratio()
    if style_only_equivalent(before, after):
        return {
            "spans": [{"kind": "equal", "text": after}],
            "change_count": 0,
            "comparison_status": "STYLE_ONLY",
            "similarity": round(similarity, 3),
            "live_only_fragments": [],
        }
    if similarity < 0.32:
        return {
            "spans": [{"kind": "equal", "text": after}],
            "change_count": 0,
            "comparison_status": "LOW_CONFIDENCE",
            "similarity": round(similarity, 3),
            "live_only_fragments": [],
        }
    spans, live_only, change_count = _meaningful_official_spans(before, after)
    return {
        "spans": spans,
        "change_count": change_count,
        "comparison_status": (
            "COMPARED" if change_count else "NON_SUBSTANTIVE"
        ),
        "similarity": round(similarity, 3),
        "live_only_fragments": live_only,
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
    seen_live_matches: set[tuple[str, str]] = set()
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
            revision_id = str(reconciliation.get("live_revision_id") or "")
            match_key = (official_id, revision_id or str(utterance.get("utterance_id") or ""))
            if match_key in seen_live_matches:
                continue
            seen_live_matches.add(match_key)
            local_text = str(reconciliation.get("live_text") or "").strip()
            live_by_official.setdefault(official_id, []).append({
                **utterance,
                "text": local_text or utterance.get("text"),
                "segment_count": 1 if local_text else utterance.get("segment_count"),
            })
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
            "live_only_fragments": comparison["live_only_fragments"],
            "presentation_version": PRESENTATION_VERSION,
        })
    return result
