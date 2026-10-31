-- The UNIQUE (document_id, sequence_number) constraint already provides the
-- identical btree order. No foreign key or constraint uses this nonunique copy.
-- On the live large table this is applied with DROP INDEX CONCURRENTLY first;
-- normal migration runs then safely record the version with this no-op.
DROP INDEX IF EXISTS official_transcript_utterances_document_idx;
