CREATE TABLE transcript_utterance_summaries (
    id uuid PRIMARY KEY,
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id) ON DELETE CASCADE,
    source_speaker_label text NOT NULL,
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    summary text NOT NULL CHECK (length(btrim(summary)) BETWEEN 1 AND 300),
    provider text NOT NULL,
    model text NOT NULL,
    prompt_version text NOT NULL,
    original_char_count integer NOT NULL CHECK (original_char_count > 0),
    segment_count integer NOT NULL CHECK (segment_count > 0),
    usage_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (broadcast_id, content_hash, provider, model, prompt_version)
);

CREATE INDEX transcript_utterance_summaries_lookup_idx
    ON transcript_utterance_summaries (
        broadcast_id, provider, model, prompt_version, content_hash
    );
