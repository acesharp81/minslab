from __future__ import annotations

from typing import Any, Iterable


def official_evidence_items(
    connection: Any, utterance_ids: Iterable[str], *, document_id: Any | None = None,
) -> list[dict[str, Any]]:
    ids = [str(value) for value in utterance_ids if value]
    if not ids:
        return []
    rows = connection.execute(
        """
        SELECT utterance.id, utterance.sequence_number,
               utterance.speaker_name, utterance.speaker_role,
               utterance.text, utterance.source_locator,
               document.publication_stage, document.authority_status
        FROM official_transcript_utterances utterance
        JOIN official_transcript_documents document
          ON document.id = utterance.document_id
        WHERE utterance.id = ANY(%s::uuid[])
          AND (%s::uuid IS NULL OR utterance.document_id = %s::uuid)
        ORDER BY utterance.sequence_number
        """,
        (ids, document_id, document_id),
    ).fetchall()
    columns = (
        "utterance_id", "official_sequence_number", "speaker_label",
        "speaker_role", "text", "source_locator", "publication_stage",
        "official_authority_status",
    )
    items = []
    for row in rows:
        item = dict(zip(columns, row, strict=True))
        item.update({
            "summary": "", "segment_count": 1, "is_final": True,
            "authority_status": item["official_authority_status"],
            "source": "OFFICIAL_TRANSCRIPT_UTTERANCE",
        })
        items.append(item)
    return items
