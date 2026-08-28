from __future__ import annotations

from copy import deepcopy
from typing import Any


def attach_official_evidence_from_changes(
    brief: dict[str, Any], changes: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Restore official evidence IDs omitted by an older cached integration.

    Official ADD edits have always retained their source utterance IDs in the
    immutable change record.  Some early cached integrated briefs did not copy
    those IDs onto the newly-created topic/task.  Repair that projection at
    read time without another LLM request or a destructive data rewrite.
    """
    result = deepcopy(brief)
    collections = {
        "topic": result.get("topics") or [],
        "task": result.get("tasks") or [],
    }
    by_type_and_id = {
        (entity_type, str(entity.get("id") or "")): entity
        for entity_type, entities in collections.items()
        for entity in entities
        if entity.get("id")
    }
    for change in changes or []:
        entity_type = str(change.get("entity_type") or "")
        entity_id = str(change.get("entity_id") or "")
        target = by_type_and_id.get((entity_type, entity_id))
        if not target:
            continue
        official_ids = [
            str(value) for value in change.get("official_utterance_ids") or []
            if value
        ]
        if official_ids:
            target["official_evidence_ids"] = list(dict.fromkeys([
                *(target.get("official_evidence_ids") or []), *official_ids,
            ]))
    return result


def official_evidence_ids(
    brief: dict[str, Any], entity_type: str, entity_id: str,
) -> list[str]:
    if entity_type == "topic":
        entities = brief.get("topics", [])
    elif entity_type == "task":
        entities = brief.get("tasks", [])
    elif entity_type == "speaker":
        entities = [
            point for topic in brief.get("topics", [])
            for point in topic.get("speaker_points", [])
        ]
    else:
        return []
    for entity in entities:
        if str(entity.get("id") or "") == entity_id:
            return [
                str(value) for value in entity.get("official_evidence_ids", [])
                if value
            ]
    return []
