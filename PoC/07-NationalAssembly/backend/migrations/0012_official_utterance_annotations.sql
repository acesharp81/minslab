CREATE TABLE official_utterance_annotations (
    id uuid PRIMARY KEY,
    utterance_id uuid NOT NULL REFERENCES official_transcript_utterances(id),
    generator_version text NOT NULL,
    classification_method text NOT NULL,
    topics text[] NOT NULL DEFAULT '{}',
    ministries text[] NOT NULL DEFAULT '{}',
    source_committee text,
    authority_status text NOT NULL DEFAULT 'PROVISIONAL'
        CHECK (authority_status = 'PROVISIONAL'),
    review_status text NOT NULL DEFAULT 'DRAFT'
        CHECK (review_status IN ('DRAFT', 'REVIEWED', 'APPROVED')),
    generated_at timestamptz NOT NULL,
    evidence_text_hash char(64) NOT NULL,
    UNIQUE (utterance_id, generator_version)
);

CREATE INDEX official_utterance_annotations_topics_gin
    ON official_utterance_annotations USING gin (topics);
CREATE INDEX official_utterance_annotations_ministries_gin
    ON official_utterance_annotations USING gin (ministries);
