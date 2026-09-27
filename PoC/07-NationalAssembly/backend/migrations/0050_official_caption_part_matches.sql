-- A caption revision can contain multiple source-provided speaker pieces.
-- Keep each piece's official attribution separately from revision-wide history.
CREATE TABLE transcript_official_part_matches (
    official_document_id uuid NOT NULL REFERENCES official_transcript_documents(id),
    transcript_revision_id uuid NOT NULL REFERENCES transcript_segment_revisions(id),
    source_part_index integer NOT NULL CHECK (source_part_index >= 0),
    source_text_hash char(64) NOT NULL,
    official_utterance_id uuid NOT NULL REFERENCES official_transcript_utterances(id),
    match_method text NOT NULL,
    match_confidence numeric(4,3) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (official_document_id, transcript_revision_id, source_part_index)
);

CREATE INDEX transcript_official_part_matches_revision_idx
    ON transcript_official_part_matches (transcript_revision_id, official_document_id);
