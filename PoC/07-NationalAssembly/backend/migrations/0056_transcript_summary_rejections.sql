-- Append-only audit of generated responses rejected before publication.
CREATE TABLE transcript_summary_rejections (
    id uuid PRIMARY KEY,
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id) ON DELETE CASCADE,
    provider text NOT NULL,
    model text NOT NULL,
    prompt_version text NOT NULL,
    request_snapshot jsonb NOT NULL,
    response jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX transcript_summary_rejections_broadcast_idx
    ON transcript_summary_rejections(broadcast_id, created_at DESC);
