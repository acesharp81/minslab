CREATE TABLE transcript_utterance_summary_failures (
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id) ON DELETE CASCADE,
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    provider text NOT NULL,
    model text NOT NULL,
    prompt_version text NOT NULL,
    attempts integer NOT NULL DEFAULT 1 CHECK (attempts > 0),
    last_error text NOT NULL,
    retry_after timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (broadcast_id, content_hash, provider, model, prompt_version)
);

CREATE INDEX transcript_summary_failures_retry_idx
    ON transcript_utterance_summary_failures (provider, retry_after);
