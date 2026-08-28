CREATE TABLE llm_provider_daily_usage (
    provider text NOT NULL,
    usage_date date NOT NULL,
    request_count integer NOT NULL DEFAULT 0 CHECK (request_count >= 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, usage_date)
);
