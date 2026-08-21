WITH ranked AS (
    SELECT id, row_number() OVER (
        PARTITION BY bill_id, semantic_hash ORDER BY created_at DESC, id DESC
    ) AS duplicate_rank
    FROM bill_official_documents
    WHERE semantic_hash IS NOT NULL
)
DELETE FROM bill_official_documents document
USING ranked
WHERE document.id = ranked.id AND ranked.duplicate_rank > 1;

CREATE UNIQUE INDEX bill_official_documents_semantic_unique
    ON bill_official_documents (bill_id, semantic_hash)
    WHERE semantic_hash IS NOT NULL;
