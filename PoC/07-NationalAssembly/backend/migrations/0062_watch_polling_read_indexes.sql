-- Existing deployments can build these CONCURRENTLY before running migrations.
-- Cover polling reads without loading transcript text or scanning other broadcasts.
CREATE INDEX IF NOT EXISTS transcript_segments_broadcast_cover_idx
    ON transcript_segments (broadcast_id, id);
CREATE INDEX IF NOT EXISTS transcript_revisions_boundary_cover_idx
    ON transcript_segment_revisions (segment_id, received_at) INCLUDE (event_cursor);
