CREATE TABLE meeting_briefs (
    id uuid PRIMARY KEY,
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id),
    transcript_hash text NOT NULL CHECK (length(transcript_hash) = 64),
    source_last_event_cursor bigint NOT NULL CHECK (source_last_event_cursor >= 0),
    provider text NOT NULL,
    model text NOT NULL,
    prompt_version text NOT NULL,
    authority_status text NOT NULL DEFAULT 'PROVISIONAL'
        CHECK (authority_status = 'PROVISIONAL'),
    review_status text NOT NULL DEFAULT 'DRAFT'
        CHECK (review_status IN ('DRAFT', 'REVIEWED', 'APPROVED')),
    brief jsonb NOT NULL,
    usage_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    generated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (broadcast_id, transcript_hash, provider, model, prompt_version)
);

CREATE INDEX meeting_briefs_broadcast_generated_idx
    ON meeting_briefs (broadcast_id, generated_at DESC);

CREATE TABLE meeting_brief_failures (
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id),
    transcript_hash text NOT NULL,
    provider text NOT NULL,
    model text NOT NULL,
    prompt_version text NOT NULL,
    attempts integer NOT NULL DEFAULT 1,
    last_error text NOT NULL,
    retry_after timestamptz NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (broadcast_id, transcript_hash, provider, model, prompt_version)
);
