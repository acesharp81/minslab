-- Cross-device account sessions and user-triggered topic reports.

CREATE TABLE watch_web_sessions (
    id uuid PRIMARY KEY,
    subscriber_id uuid NOT NULL REFERENCES watch_subscribers(id) ON DELETE CASCADE,
    token_hash char(64) NOT NULL UNIQUE,
    user_agent_hash char(64),
    expires_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX watch_web_sessions_subscriber_idx
    ON watch_web_sessions (subscriber_id, expires_at DESC)
    WHERE revoked_at IS NULL;

CREATE INDEX watch_kakao_accounts_user_lookup_idx
    ON watch_kakao_accounts (kakao_user_id, updated_at DESC);

CREATE TABLE topic_reports (
    id uuid PRIMARY KEY,
    subscriber_id uuid NOT NULL REFERENCES watch_subscribers(id) ON DELETE CASCADE,
    ministry text NOT NULL CHECK (char_length(ministry) BETWEEN 1 AND 80),
    topic text NOT NULL CHECK (char_length(topic) BETWEEN 2 AND 160),
    period_start date NOT NULL,
    period_end date NOT NULL,
    institution text CHECK (
        institution IS NULL OR institution IN ('EXECUTIVE', 'LEGISLATURE')
    ),
    query_hash char(64) NOT NULL,
    evidence_set_hash char(64) NOT NULL,
    evidence jsonb NOT NULL,
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
    CHECK (period_end >= period_start),
    UNIQUE (
        subscriber_id, query_hash, evidence_set_hash,
        provider, model, prompt_version
    )
);
CREATE INDEX topic_reports_owner_idx
    ON topic_reports (subscriber_id, created_at DESC);
CREATE INDEX topic_reports_claim_idx
    ON topic_reports (status, created_at)
    WHERE status IN ('PENDING', 'PROCESSING');

CREATE TABLE topic_report_daily_usage (
    subscriber_id uuid NOT NULL REFERENCES watch_subscribers(id) ON DELETE CASCADE,
    usage_date date NOT NULL,
    request_count integer NOT NULL DEFAULT 0 CHECK (request_count >= 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (subscriber_id, usage_date)
);

CREATE TABLE topic_report_global_daily_usage (
    usage_date date PRIMARY KEY,
    request_count integer NOT NULL DEFAULT 0 CHECK (request_count >= 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);
