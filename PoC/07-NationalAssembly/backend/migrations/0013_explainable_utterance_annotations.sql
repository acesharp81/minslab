ALTER TABLE official_utterance_annotations
    ADD COLUMN utterance_kind text NOT NULL DEFAULT 'OTHER'
        CHECK (utterance_kind IN ('POLICY', 'PROCEDURAL', 'OTHER')),
    ADD COLUMN evidence_keywords text[] NOT NULL DEFAULT '{}',
    ADD COLUMN topic_links jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN ministry_links jsonb NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX official_utterance_annotations_kind_idx
    ON official_utterance_annotations (generator_version, utterance_kind);
