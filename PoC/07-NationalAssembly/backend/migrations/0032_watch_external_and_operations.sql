ALTER TABLE watch_rules
    ADD COLUMN kakao_enabled boolean NOT NULL DEFAULT false;

ALTER TABLE notification_outbox
    DROP CONSTRAINT notification_outbox_status_check;
ALTER TABLE notification_outbox
    ADD CONSTRAINT notification_outbox_status_check
        CHECK (status IN ('PENDING', 'SENDING', 'SENT', 'FAILED', 'CANCELED')),
    ADD COLUMN lease_owner text,
    ADD COLUMN lease_expires_at timestamptz;
CREATE INDEX notification_outbox_delivery_idx
    ON notification_outbox (channel, status, next_attempt_at, created_at);

CREATE TABLE watch_kakao_oauth_states (
    state_hash char(64) PRIMARY KEY,
    subscriber_id uuid NOT NULL REFERENCES watch_subscribers(id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE watch_kakao_accounts (
    id uuid PRIMARY KEY,
    subscriber_id uuid NOT NULL UNIQUE REFERENCES watch_subscribers(id) ON DELETE CASCADE,
    kakao_user_id text NOT NULL,
    access_token_ciphertext text NOT NULL,
    refresh_token_ciphertext text NOT NULL,
    access_token_expires_at timestamptz NOT NULL,
    refresh_token_expires_at timestamptz,
    scopes text[] NOT NULL DEFAULT '{}'::text[],
    status text NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'REAUTHORIZE', 'DISCONNECTED')),
    last_error text,
    connected_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX watch_kakao_accounts_status_idx
    ON watch_kakao_accounts (status, updated_at DESC);

CREATE TABLE watch_summary_versions (
    id uuid PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES watch_sessions(id) ON DELETE CASCADE,
    evidence_set_hash char(64) NOT NULL,
    status text NOT NULL CHECK (status IN (
        'PENDING', 'READY', 'FAILED', 'LIMIT_REACHED'
    )),
    summary text,
    claims jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidence_match_ids uuid[] NOT NULL DEFAULT '{}'::uuid[],
    provider text NOT NULL,
    model text NOT NULL,
    prompt_version text NOT NULL,
    input_tokens integer NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens integer NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    cost_usd numeric(12, 8) NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
    update_number integer NOT NULL CHECK (update_number > 0),
    last_error text,
    retry_after timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, evidence_set_hash)
);
CREATE INDEX watch_summary_versions_session_idx
    ON watch_summary_versions (session_id, created_at DESC);

CREATE TABLE watch_review_decisions (
    id uuid PRIMARY KEY,
    verification_id uuid NOT NULL
        REFERENCES watch_match_official_verifications(id) ON DELETE CASCADE,
    automatic_status text NOT NULL,
    decision text NOT NULL CHECK (decision IN ('APPROVE', 'CORRECT', 'DEFER')),
    note text NOT NULL DEFAULT '',
    reviewed_by text NOT NULL,
    reviewed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX watch_review_decisions_verification_idx
    ON watch_review_decisions (verification_id, reviewed_at DESC);

CREATE TABLE live_regression_audits (
    id uuid PRIMARY KEY,
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id) ON DELETE CASCADE,
    status text NOT NULL CHECK (status IN ('PASS', 'PENDING', 'REVIEW_REQUIRED')),
    checks jsonb NOT NULL,
    revision_count integer NOT NULL DEFAULT 0 CHECK (revision_count >= 0),
    final_count integer NOT NULL DEFAULT 0 CHECK (final_count >= 0),
    partial_count integer NOT NULL DEFAULT 0 CHECK (partial_count >= 0),
    reconnect_gap_count integer NOT NULL DEFAULT 0 CHECK (reconnect_gap_count >= 0),
    audited_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX live_regression_audits_broadcast_idx
    ON live_regression_audits (broadcast_id, audited_at DESC);
