-- Append-only semantic grouping; original transcript and summaries are untouched.
CREATE TABLE IF NOT EXISTS live_discussion_classifications (
    id uuid PRIMARY KEY,
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id),
    profile text NOT NULL,
    input_hash text NOT NULL,
    state jsonb NOT NULL,
    request_snapshot jsonb NOT NULL,
    response jsonb NOT NULL,
    provider text NOT NULL,
    model text NOT NULL,
    usage_metadata jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (broadcast_id, profile, input_hash)
);
CREATE INDEX IF NOT EXISTS live_discussion_classifications_latest
    ON live_discussion_classifications(broadcast_id, profile, created_at DESC);
