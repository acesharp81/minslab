ALTER TABLE live_broadcasts
    ADD COLUMN source_last_event_cursor bigint NOT NULL DEFAULT 0
    CHECK (source_last_event_cursor >= 0);

UPDATE live_broadcasts broadcast
SET source_last_event_cursor = latest.event_cursor
FROM (
    SELECT segment.broadcast_id, COALESCE(MAX(revision.event_cursor), 0) AS event_cursor
    FROM transcript_segments segment
    JOIN transcript_segment_revisions revision ON revision.segment_id = segment.id
    GROUP BY segment.broadcast_id
) latest
WHERE latest.broadcast_id = broadcast.id;

CREATE INDEX live_broadcasts_ended_detected_idx
    ON live_broadcasts (detected_at DESC, id DESC)
    WHERE lifecycle_status = 'ENDED';
