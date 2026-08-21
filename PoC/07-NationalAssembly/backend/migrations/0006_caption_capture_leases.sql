ALTER TABLE live_broadcasts
    ADD COLUMN caption_websocket_url text,
    ADD COLUMN capture_status text NOT NULL DEFAULT 'UNAVAILABLE'
        CHECK (capture_status IN ('UNAVAILABLE', 'READY', 'CAPTURING', 'RETRY_WAIT', 'COMPLETED', 'FAILED')),
    ADD COLUMN capture_lease_owner text,
    ADD COLUMN capture_lease_expires_at timestamptz,
    ADD COLUMN reconnect_attempts integer NOT NULL DEFAULT 0,
    ADD COLUMN last_caption_received_at timestamptz;

ALTER TABLE transcript_segment_revisions
    ADD COLUMN source_document_version_id uuid REFERENCES source_document_versions(id);

CREATE INDEX live_broadcasts_capture_idx
    ON live_broadcasts (capture_status, capture_lease_expires_at)
    WHERE lifecycle_status = 'LIVE';
