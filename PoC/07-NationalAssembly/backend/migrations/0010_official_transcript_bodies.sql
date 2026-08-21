CREATE TABLE official_transcript_documents (
    id uuid PRIMARY KEY,
    publication_id uuid NOT NULL REFERENCES broadcast_official_publications(id),
    source_document_version_id uuid NOT NULL REFERENCES source_document_versions(id),
    conference_id text NOT NULL,
    publication_stage text NOT NULL CHECK (publication_stage IN ('TEMPORARY', 'FINAL', 'UNKNOWN')),
    authority_status text NOT NULL CHECK (authority_status IN ('PROVISIONAL', 'OFFICIAL')),
    extraction_status text NOT NULL CHECK (extraction_status IN ('EXTRACTED', 'UNSUPPORTED', 'FAILED')),
    status_text text,
    title text,
    utterance_count integer NOT NULL CHECK (utterance_count >= 0),
    parser_version text NOT NULL,
    retrieved_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (publication_id, source_document_version_id)
);

CREATE TABLE official_transcript_utterances (
    id uuid PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES official_transcript_documents(id),
    sequence_number integer NOT NULL CHECK (sequence_number > 0),
    source_speaker_id text NOT NULL,
    source_span_id text NOT NULL,
    agenda_item_ref text,
    speaker_name text,
    speaker_role text,
    text text NOT NULL,
    text_hash char(64) NOT NULL,
    source_locator jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, source_span_id),
    UNIQUE (document_id, sequence_number)
);

CREATE TABLE transcript_official_reconciliations (
    id uuid PRIMARY KEY,
    transcript_revision_id uuid NOT NULL REFERENCES transcript_segment_revisions(id),
    official_utterance_id uuid REFERENCES official_transcript_utterances(id),
    reconciliation_status text NOT NULL CHECK (reconciliation_status IN ('MATCHED', 'UNRESOLVED', 'CONFLICT')),
    match_method text NOT NULL,
    match_confidence numeric(4,3),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (transcript_revision_id, official_utterance_id, match_method)
);

CREATE INDEX official_transcript_documents_publication_idx
    ON official_transcript_documents (publication_id, retrieved_at DESC);
CREATE INDEX official_transcript_utterances_document_idx
    ON official_transcript_utterances (document_id, sequence_number);
CREATE INDEX transcript_official_reconciliation_revision_idx
    ON transcript_official_reconciliations (transcript_revision_id, created_at DESC);
