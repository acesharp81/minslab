ALTER TABLE bill_official_documents ADD COLUMN semantic_hash text;

UPDATE bill_official_documents
SET semantic_hash = md5(extracted_text)
WHERE semantic_hash IS NULL;

CREATE INDEX bill_official_documents_semantic_idx
    ON bill_official_documents (bill_id, semantic_hash);
