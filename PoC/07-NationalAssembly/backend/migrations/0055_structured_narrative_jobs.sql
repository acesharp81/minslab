-- Only explicitly requested repairs are queued; no historical report backfill.
CREATE TABLE structured_narrative_jobs (
    broadcast_id uuid PRIMARY KEY REFERENCES live_broadcasts(id),
    status text NOT NULL DEFAULT 'PENDING',
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    last_result jsonb NOT NULL DEFAULT '{}'::jsonb,
    run_count integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX structured_narrative_jobs_due ON structured_narrative_jobs(next_attempt_at)
    WHERE status IN ('PENDING', 'WAITING_DAILY_LIMIT', 'RETRY_WAIT');
