ALTER TABLE official_transcript_documents
    ADD COLUMN meeting_id uuid REFERENCES meetings(id);

UPDATE official_transcript_documents document
SET meeting_id = publication.meeting_id
FROM broadcast_official_publications publication
WHERE publication.id = document.publication_id;

ALTER TABLE official_transcript_documents
    ALTER COLUMN meeting_id SET NOT NULL,
    ALTER COLUMN publication_id DROP NOT NULL;

CREATE UNIQUE INDEX official_transcript_documents_meeting_version_uidx
    ON official_transcript_documents (meeting_id, source_document_version_id);
CREATE INDEX official_transcript_documents_meeting_latest_idx
    ON official_transcript_documents (meeting_id, retrieved_at DESC);
