CREATE TABLE meeting_official_change_reports (
    id uuid PRIMARY KEY,
    integration_id uuid NOT NULL REFERENCES meeting_official_integrations(id) ON DELETE CASCADE,
    input_hash char(64) NOT NULL,
    input_snapshot jsonb NOT NULL,
    status text NOT NULL DEFAULT 'PENDING' CHECK (
        status IN ('PENDING', 'PROCESSING', 'READY', 'FAILED', 'LIMIT_REACHED')
    ),
    provider text NOT NULL,
    model text NOT NULL,
    prompt_version text NOT NULL,
    report jsonb NOT NULL DEFAULT '{}'::jsonb,
    usage_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    last_error text,
    lease_owner text,
    lease_expires_at timestamptz,
    generated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (integration_id, provider, model, prompt_version)
);

CREATE INDEX meeting_official_change_reports_claim_idx
    ON meeting_official_change_reports (status, created_at)
    WHERE status IN ('PENDING', 'PROCESSING');

CREATE TABLE official_change_report_daily_usage (
    usage_date date PRIMARY KEY,
    request_count integer NOT NULL DEFAULT 0 CHECK (request_count >= 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);
