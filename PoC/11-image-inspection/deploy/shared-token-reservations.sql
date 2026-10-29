-- PoC7 owns openai_group_daily_usage. Only add the PoC11 idempotency journal.
CREATE TABLE IF NOT EXISTS poc11_token_reservations (
    event_id text PRIMARY KEY,
    usage_date date NOT NULL,
    reserved_tokens bigint NOT NULL CHECK (reserved_tokens >= 0),
    settled boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Existing reservations belong to main. Keep the group on the durable journal.
ALTER TABLE poc11_token_reservations ADD COLUMN IF NOT EXISTS budget_group text NOT NULL DEFAULT 'main' CHECK (budget_group IN ('main','mini'));
