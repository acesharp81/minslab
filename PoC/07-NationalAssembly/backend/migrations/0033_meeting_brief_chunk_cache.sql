CREATE TABLE meeting_brief_chunk_cache (
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id) ON DELETE CASCADE,
    chunk_hash text NOT NULL,
    provider text NOT NULL,
    model text NOT NULL,
    prompt_version text NOT NULL,
    chunk_index integer NOT NULL,
    analysis jsonb NOT NULL,
    usage_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (broadcast_id, chunk_hash, provider, model, prompt_version)
);

CREATE INDEX meeting_brief_chunk_cache_created_idx
    ON meeting_brief_chunk_cache (created_at);
