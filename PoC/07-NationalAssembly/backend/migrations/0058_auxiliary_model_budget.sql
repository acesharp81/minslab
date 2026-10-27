-- PoC7-owned reservations survive worker restarts. Unknown usage stays charged.
CREATE TABLE IF NOT EXISTS auxiliary_model_calls (
    id uuid PRIMARY KEY,
    provider text NOT NULL CHECK (provider IN ('groq', 'gemini')),
    model text NOT NULL,
    usage_date date NOT NULL,
    reserved_tokens bigint NOT NULL CHECK (reserved_tokens > 0),
    charged_tokens bigint NOT NULL CHECK (charged_tokens >= 0),
    status text NOT NULL DEFAULT 'RESERVED',
    usage_metadata jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS auxiliary_model_calls_daily ON auxiliary_model_calls(provider, usage_date);
CREATE TABLE IF NOT EXISTS auxiliary_model_pacing (
    provider text PRIMARY KEY,
    next_request_at timestamptz NOT NULL DEFAULT now()
);
