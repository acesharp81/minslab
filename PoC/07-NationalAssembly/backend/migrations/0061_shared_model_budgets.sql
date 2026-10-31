-- Reservations for HTTP clients share the existing native PoC7 OpenAI ledgers.
CREATE TABLE shared_model_reservations (
    event_id TEXT PRIMARY KEY, project TEXT NOT NULL, model TEXT NOT NULL,
    budget_kind TEXT NOT NULL, period_key TEXT NOT NULL,
    reserved_tokens BIGINT NOT NULL DEFAULT 0, reserved_usd NUMERIC(18,8) NOT NULL DEFAULT 0,
    settled BOOLEAN NOT NULL DEFAULT FALSE, input_tokens BIGINT, output_tokens BIGINT,
    cost_usd NUMERIC(18,8), created_at TIMESTAMPTZ NOT NULL DEFAULT now(), settled_at TIMESTAMPTZ
);
CREATE TABLE shared_solar_grant_usage (
    grant_id TEXT PRIMARY KEY, spent_usd NUMERIC(18,8) NOT NULL DEFAULT 0,
    reserved_usd NUMERIC(18,8) NOT NULL DEFAULT 0, unknown_usd NUMERIC(18,8) NOT NULL DEFAULT 0,
    request_count BIGINT NOT NULL DEFAULT 0, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX shared_model_project_idx ON shared_model_reservations(project, created_at);
