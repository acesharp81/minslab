from __future__ import annotations

import re
from collections.abc import Iterable
from difflib import SequenceMatcher
from typing import Any

from .official_brief_integration import semantic_tokens
from .official_reconciliation import (
    MIN_INLINE_PATCH_SIMILARITY,
    style_only_equivalent,
)


def _style_only_update(target: dict[str, Any], edit: dict[str, Any]) -> bool:
    field = str(edit.get("field") or "")
    if field not in {"headline", "summary", "title"}:
        return False
    return style_only_equivalent(target.get(field), edit.get("new_text"))


def _rewrites_too_much(target: dict[str, Any], edit: dict[str, Any]) -> bool:
    field = str(edit.get("field") or "")
    if field not in {"headline", "summary", "title"}:
        return False
    before = re.sub(r"[^0-9A-Za-z가-힣]+", "", str(target.get(field) or "").casefold())
    after = re.sub(r"[^0-9A-Za-z가-힣]+", "", str(edit.get("new_text") or "").casefold())
    if min(len(before), len(after)) < 20:
        return False
    return (
        SequenceMatcher(None, before, after, autojunk=False).ratio()
        < MIN_INLINE_PATCH_SIMILARITY
    )


def _duplicates_existing_entity(
    brief: dict[str, Any], entity_type: str, edit: dict[str, Any],
) -> bool:
    if entity_type not in {"topic", "task"}:
        return False
    key = "topics" if entity_type == "topic" else "tasks"
    candidate = " ".join(str(edit.get("title") or edit.get("new_text") or "").split())
    candidate_compact = re.sub(r"[^0-9A-Za-z가-힣]+", "", candidate.casefold())
    if not candidate_compact:
        return True
    candidate_tokens = semantic_tokens(candidate)
    for existing in brief.get(key, []):
        title = " ".join(str(existing.get("title") or "").split())
        compact = re.sub(r"[^0-9A-Za-z가-힣]+", "", title.casefold())
        overlap = candidate_tokens & semantic_tokens(title)
        coverage = len(overlap) / max(1, min(len(candidate_tokens), len(semantic_tokens(title))))
        if candidate_compact == compact or (
            SequenceMatcher(None, candidate_compact, compact).ratio() >= 0.82
            and coverage >= 0.75
        ) or (len(overlap) >= 3 and coverage >= 0.8) or (
            len(overlap) >= 4 and coverage >= 0.6):
            return True
    return False


def _entity(
    brief: dict[str, Any], entity_type: str, entity_id: str,
) -> dict[str, Any] | None:
    if entity_type == "meeting":
        return brief
    key = "topics" if entity_type == "topic" else "tasks" if entity_type == "task" else ""
    for item in brief.get(key, []) if key else []:
        if str(item.get("id") or "") == entity_id:
            return item
    return None


def filter_supported_official_edits(
    payload: dict[str, Any], live_brief: dict[str, Any],
    official_rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    evidence_map = {
        str(row.get("utterance_id")): dict(row)
        for row in official_rows if row.get("utterance_id")
    }
    accepted = []
    candidates = payload.get("edits", []) if isinstance(payload.get("edits"), list) else []
    for raw in candidates:
        if not isinstance(raw, dict):
            continue
        edit = dict(raw)
        entity_type = str(edit.get("entity_type") or "")
        operation = str(edit.get("operation") or "")
        entity_id = str(edit.get("entity_id") or "")
        field = str(edit.get("field") or "")
        if entity_type not in {"meeting", "topic", "task"}:
            continue
        # Official absence is not evidence of deletion. Explicit contradiction
        # review can be added later, but automatic deletion is intentionally off.
        if operation == "DELETE":
            continue
        target = _entity(live_brief, entity_type, entity_id)
        if operation != "ADD" and target is None:
            continue
        if entity_type == "meeting" and operation != "UPDATE":
            continue
        if operation == "UPDATE" and target and _style_only_update(target, edit):
            continue
        if operation == "UPDATE" and target and _rewrites_too_much(target, edit):
            # Keep the verified official alternative for the comparison card,
            # but minimal_patch_text will preserve the provisional main copy.
            edit["presentation_status"] = "FULL_REWRITE_SUPPRESSED"
        if operation == "ADD" and _duplicates_existing_entity(live_brief, entity_type, edit):
            continue
        evidence_ids = [
            str(value) for value in edit.get("official_utterance_ids") or []
            if str(value) in evidence_map
        ]
        if not evidence_ids:
            continue
        evidence_rows = [evidence_map[value] for value in evidence_ids]
        if field == "ministries":
            before = set(target.get("ministries") or []) if target else set()
            after = {str(value) for value in edit.get("new_values") or [] if value}
            added = after - before
            supported = {
                str(value) for row in evidence_rows
                for value in row.get("ministries") or [] if value
            }
            if not added or not added.issubset(supported):
                continue
        else:
            changed_text = " ".join(str(value or "") for value in (
                edit.get("new_text"), edit.get("title"), edit.get("summary"),
            ))
            context_text = " ".join(str(value or "") for value in (
                (target or {}).get("title"), (target or {}).get("summary"),
                live_brief.get("headline") if entity_type == "meeting" else "",
            ))
            evidence_tokens = semantic_tokens(*(
                row.get("text") for row in evidence_rows
            ))
            shared = semantic_tokens(changed_text, context_text) & evidence_tokens
            if len(shared) < 2 and not any(len(token) >= 6 for token in shared):
                continue
            if target and entity_type != "meeting":
                context_shared = semantic_tokens(
                    target.get("title"), target.get("summary"),
                ) & evidence_tokens
                if len(context_shared) < 2 and not any(
                    len(token) >= 6 for token in context_shared
                ): continue
        edit["official_utterance_ids"] = evidence_ids
        accepted.append(edit)
    return accepted
