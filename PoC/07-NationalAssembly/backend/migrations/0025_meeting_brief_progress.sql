CREATE TABLE meeting_brief_progress (
    broadcast_id uuid PRIMARY KEY REFERENCES live_broadcasts(id),
    transcript_hash text NOT NULL CHECK (length(transcript_hash) = 64),
    provider text NOT NULL,
    model text NOT NULL,
    prompt_version text NOT NULL,
    status text NOT NULL CHECK (status IN ('PROCESSING', 'DEFERRED', 'FAILED', 'COMPLETED')),
    phase text NOT NULL,
    total_utterances integer NOT NULL CHECK (total_utterances >= 0),
    processed_utterances integer NOT NULL CHECK (
        processed_utterances >= 0 AND processed_utterances <= total_utterances
    ),
    total_chunks integer NOT NULL DEFAULT 0 CHECK (total_chunks >= 0),
    completed_chunks integer NOT NULL DEFAULT 0 CHECK (
        completed_chunks >= 0 AND completed_chunks <= total_chunks
    ),
    started_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX meeting_brief_progress_status_idx
    ON meeting_brief_progress (status, updated_at DESC);
