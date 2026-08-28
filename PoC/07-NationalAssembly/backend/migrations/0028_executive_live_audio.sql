ALTER TABLE live_broadcasts
    ADD COLUMN IF NOT EXISTS media_stream_url text;

ALTER TABLE live_broadcasts
    DROP CONSTRAINT IF EXISTS live_broadcasts_capture_status_check;
ALTER TABLE live_broadcasts
    ADD CONSTRAINT live_broadcasts_capture_status_check
    CHECK (capture_status IN (
        'UNAVAILABLE', 'READY', 'AUDIO_READY', 'CAPTURING',
        'RETRY_WAIT', 'COMPLETED', 'FAILED'
    ));

CREATE TABLE IF NOT EXISTS executive_audio_chunks (
    id uuid PRIMARY KEY,
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id) ON DELETE CASCADE,
    chunk_number integer NOT NULL CHECK (chunk_number >= 0),
    content_hash char(64) NOT NULL,
    raw_path text NOT NULL,
    captured_at timestamptz NOT NULL,
    duration_ms integer NOT NULL CHECK (duration_ms > 0),
    transcription_status text NOT NULL DEFAULT 'CAPTURED'
        CHECK (transcription_status IN ('CAPTURED', 'PROCESSING', 'TRANSCRIBED', 'FAILED')),
    provider text,
    model text,
    transcript_payload jsonb,
    usage_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    attempts integer NOT NULL DEFAULT 0,
    error_type text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (broadcast_id, chunk_number),
    UNIQUE (broadcast_id, content_hash)
);

CREATE INDEX IF NOT EXISTS executive_audio_chunks_pending_idx
    ON executive_audio_chunks (broadcast_id, transcription_status, chunk_number);

CREATE TABLE IF NOT EXISTS audio_usage_events (
    provider text NOT NULL,
    request_id text NOT NULL,
    model text NOT NULL,
    usage_month date NOT NULL,
    audio_seconds numeric(14,3) NOT NULL DEFAULT 0,
    cost_usd numeric(14,8) NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, request_id)
);

CREATE INDEX IF NOT EXISTS audio_usage_events_month_idx
    ON audio_usage_events (provider, usage_month);

CREATE TABLE IF NOT EXISTS executive_official_matches (
    broadcast_id uuid PRIMARY KEY REFERENCES live_broadcasts(id) ON DELETE CASCADE,
    official_briefing_id text NOT NULL,
    meeting_number integer,
    meeting_date date,
    match_method text NOT NULL
        CHECK (match_method IN ('MEETING_NUMBER_AND_DATE', 'UNIQUE_MEETING_NUMBER')),
    official_content_hash char(64),
    matched_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
