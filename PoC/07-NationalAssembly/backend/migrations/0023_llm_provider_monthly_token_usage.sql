CREATE TABLE llm_provider_monthly_token_usage (
    provider text NOT NULL,
    model text NOT NULL,
    usage_month date NOT NULL,
    request_count integer NOT NULL DEFAULT 0 CHECK (request_count >= 0),
    input_tokens bigint NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens bigint NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    total_tokens bigint NOT NULL DEFAULT 0 CHECK (total_tokens >= 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, model, usage_month)
);
