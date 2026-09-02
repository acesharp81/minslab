"""Pure project-context assembly for AIWorks planning."""

from __future__ import annotations


def assemble(
    *,
    project_id: str,
    classification: str,
    intent_analysis: dict,
    document_context: dict,
    fact_snapshot: dict,
    markdown_context: list,
    source_ids: list[str],
    masked_fields: list[dict],
) -> dict:
    active_document_id = str(
        document_context.get("active_document_id")
        or document_context.get("document_id")
        or ""
    )
    return {
        "contractVersion": "context-assembly/1.0",
        "projectId": project_id,
        "classification": classification,
        "activeDocumentId": active_document_id or None,
        "intent": dict(intent_analysis or {}),
        "facts": dict(fact_snapshot or {}),
        "markdownDocuments": list(markdown_context or []),
        "projectSourceIds": list(dict.fromkeys(str(item) for item in source_ids if str(item))),
        "dataProtection": {
            "personalDataDetected": bool(masked_fields),
            "maskedFields": list(masked_fields or []),
        },
    }


def validate(contract: dict) -> list[str]:
    errors = []
    if contract.get("contractVersion") != "context-assembly/1.0":
        errors.append("contractVersion")
    if not str(contract.get("projectId") or ""):
        errors.append("projectId")
    if contract.get("classification") not in {"public", "internal", "confidential", "personal"}:
        errors.append("classification")
    if not isinstance(contract.get("markdownDocuments"), list):
        errors.append("markdownDocuments")
    if not isinstance(contract.get("projectSourceIds"), list):
        errors.append("projectSourceIds")
    return errors
