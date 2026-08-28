CREATE TABLE llm_provider_token_usage_events (
    provider text NOT NULL,
    request_id text NOT NULL,
    model text NOT NULL,
    usage_month date NOT NULL,
    input_tokens bigint NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens bigint NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    total_tokens bigint NOT NULL DEFAULT 0 CHECK (total_tokens >= 0),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, request_id)
);

INSERT INTO llm_provider_token_usage_events (
    provider, request_id, model, usage_month,
    input_tokens, output_tokens, total_tokens, recorded_at
)
SELECT DISTINCT ON (provider, usage_metadata->>'request_id')
       provider,
       usage_metadata->>'request_id',
       model,
       date_trunc('month', timezone('UTC', created_at))::date,
       COALESCE(NULLIF(usage_metadata->'usage'->>'prompt_tokens', '')::bigint, 0),
       COALESCE(NULLIF(usage_metadata->'usage'->>'completion_tokens', '')::bigint, 0),
       COALESCE(NULLIF(usage_metadata->'usage'->>'total_tokens', '')::bigint, 0),
       created_at
FROM transcript_utterance_summaries
WHERE provider = 'mistral'
  AND COALESCE(usage_metadata->>'request_id', '') <> ''
ORDER BY provider, usage_metadata->>'request_id', created_at
ON CONFLICT (provider, request_id) DO NOTHING;

INSERT INTO llm_provider_token_usage_events (
    provider, request_id, model, usage_month,
    input_tokens, output_tokens, total_tokens, recorded_at
)
SELECT DISTINCT ON (mb.provider, item->>'request_id')
       mb.provider,
       item->>'request_id',
       mb.model,
       date_trunc('month', timezone('UTC', mb.generated_at))::date,
       COALESCE(NULLIF(item->'usage'->>'prompt_tokens', '')::bigint, 0),
       COALESCE(NULLIF(item->'usage'->>'completion_tokens', '')::bigint, 0),
       COALESCE(NULLIF(item->'usage'->>'total_tokens', '')::bigint, 0),
       mb.generated_at
FROM meeting_briefs mb
CROSS JOIN LATERAL jsonb_array_elements(
    COALESCE(mb.usage_metadata->'requests', '[]'::jsonb)
) item
WHERE mb.provider = 'mistral'
  AND COALESCE(item->>'request_id', '') <> ''
ORDER BY mb.provider, item->>'request_id', mb.generated_at
ON CONFLICT (provider, request_id) DO NOTHING;

DELETE FROM llm_provider_monthly_token_usage;

INSERT INTO llm_provider_monthly_token_usage (
    provider, model, usage_month, request_count,
    input_tokens, output_tokens, total_tokens
)
SELECT provider, model, usage_month, count(*),
       sum(input_tokens), sum(output_tokens), sum(total_tokens)
FROM llm_provider_token_usage_events
GROUP BY provider, model, usage_month;
