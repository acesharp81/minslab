ALTER TABLE live_broadcasts
    DROP CONSTRAINT IF EXISTS live_broadcasts_capture_status_check;
ALTER TABLE live_broadcasts
    ADD CONSTRAINT live_broadcasts_capture_status_check
    CHECK (capture_status IN (
        'UNAVAILABLE', 'READY', 'AUDIO_READY', 'CAPTURING',
        'POST_PROCESSING', 'RETRY_WAIT', 'COMPLETED', 'FAILED'
    ));
