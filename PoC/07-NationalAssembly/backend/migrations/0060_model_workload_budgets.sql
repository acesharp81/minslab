-- Independent daily complimentary groups; legacy history remains untouched.
CREATE TABLE openai_group_daily_usage (
 budget_group text NOT NULL CHECK (budget_group IN ('mini','main')),
 usage_date date NOT NULL,
 request_count bigint NOT NULL DEFAULT 0,
 input_tokens bigint NOT NULL DEFAULT 0,
 output_tokens bigint NOT NULL DEFAULT 0,
 total_tokens bigint NOT NULL DEFAULT 0,
 unknown_tokens bigint NOT NULL DEFAULT 0,
 reserved_tokens bigint NOT NULL DEFAULT 0 CHECK (reserved_tokens >= 0),
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (budget_group, usage_date)
);
-- The pre-migration direct OpenAI route used gpt-5.4-mini exclusively.
INSERT INTO openai_group_daily_usage
 SELECT 'mini',usage_date,request_count,input_tokens,output_tokens,total_tokens,
        unknown_tokens+reserved_tokens,0,updated_at FROM openai_daily_token_usage;
CREATE TABLE openai_credit_grant_usage (
 grant_id text PRIMARY KEY,
 spent_usd numeric(18,8) NOT NULL DEFAULT 0,
 reserved_usd numeric(18,8) NOT NULL DEFAULT 0 CHECK (reserved_usd >= 0),
 unknown_usd numeric(18,8) NOT NULL DEFAULT 0,
 request_count bigint NOT NULL DEFAULT 0,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE model_provider_cooldowns (
 scope text PRIMARY KEY,
 blocked_until timestamptz NOT NULL,
 reason text NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT now()
);
