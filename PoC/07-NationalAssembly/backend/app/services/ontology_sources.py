from __future__ import annotations

from typing import Any


def select_current_ontology_brief(
    item: dict[str, Any],
    integration: dict[str, Any] | None,
    current_document_id: Any,
) -> tuple[dict[str, Any], str]:
    """Use the same current-document authority guard as the report API."""
    provisional = item.get("brief") or {}
    if (
        current_document_id is not None
        and integration
        and integration.get("status") == "READY"
        and integration.get("meeting_brief_id") == item.get("brief_id")
        and integration.get("official_document_id") == current_document_id
        and (integration.get("usage_metadata") or {}).get("reuse_reason")
            != "TEMPORARY_UPDATE_DEFERRED"
        and (integration.get("usage_metadata") or {}).get("comparison_mode")
            != "SOURCE_ONLY_TIMEOUT"
        and isinstance(integration.get("integrated_brief"), dict)
    ):
        return integration["integrated_brief"], "OFFICIAL_INTEGRATED"
    return provisional, "PROVISIONAL"
