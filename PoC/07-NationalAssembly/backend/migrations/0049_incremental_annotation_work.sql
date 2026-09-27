CREATE TABLE official_annotation_processing_state (
    document_id uuid NOT NULL REFERENCES official_transcript_documents(id),
    generator_version text NOT NULL,
    utterance_count integer NOT NULL DEFAULT 0,
    status text NOT NULL CHECK (status IN ('SUCCEEDED', 'RETRY_WAIT')),
    attempt_count integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz,
    last_error text,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, generator_version)
);

CREATE INDEX official_annotation_processing_retry_idx
    ON official_annotation_processing_state (generator_version, next_attempt_at)
    WHERE status = 'RETRY_WAIT';

-- The previous worker's global anti-join returned no historical backlog.
-- Seed settled documents and let recently created documents run once through
-- the new bounded document queue.
INSERT INTO official_annotation_processing_state (
    document_id, generator_version, utterance_count, status, completed_at
)
SELECT id, 'official-keyword-insight/2.0', utterance_count,
       'SUCCEEDED', now()
FROM official_transcript_documents
WHERE created_at < now() - interval '1 hour';
