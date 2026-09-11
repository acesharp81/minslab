ALTER TABLE live_broadcasts
    ADD COLUMN IF NOT EXISTS active_transcript_source text NOT NULL DEFAULT 'NONE',
    ADD COLUMN IF NOT EXISTS official_caption_state text NOT NULL DEFAULT 'UNAVAILABLE',
    ADD COLUMN IF NOT EXISTS official_caption_failure_started_at timestamptz,
    ADD COLUMN IF NOT EXISTS official_caption_recovery_started_at timestamptz,
    ADD COLUMN IF NOT EXISTS stt_fallback_status text NOT NULL DEFAULT 'IDLE',
    ADD COLUMN IF NOT EXISTS stt_fallback_started_at timestamptz,
    ADD COLUMN IF NOT EXISTS stt_capture_lease_owner text,
    ADD COLUMN IF NOT EXISTS stt_capture_lease_expires_at timestamptz;

UPDATE live_broadcasts SET
    active_transcript_source = CASE
        WHEN caption_websocket_url IS NOT NULL THEN 'OFFICIAL_CAPTION'
        WHEN media_stream_url IS NOT NULL THEN 'AI_STT'
        ELSE 'NONE' END,
    official_caption_state = CASE
        WHEN caption_websocket_url IS NOT NULL THEN 'ACTIVE'
        ELSE 'UNAVAILABLE' END,
    stt_fallback_status = CASE
        WHEN institution = 'EXECUTIVE' AND media_stream_url IS NOT NULL THEN 'AUDIO_READY'
        ELSE 'IDLE' END
WHERE active_transcript_source = 'NONE';

CREATE TABLE IF NOT EXISTS transcript_source_sessions (
    id uuid PRIMARY KEY,
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id) ON DELETE CASCADE,
    source_type text NOT NULL,
    transition text NOT NULL,
    reason text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS transcript_source_sessions_broadcast_idx
    ON transcript_source_sessions(broadcast_id, occurred_at);
