ALTER TABLE transcript_segment_revisions
    ADD COLUMN event_cursor bigint GENERATED ALWAYS AS IDENTITY;

CREATE UNIQUE INDEX transcript_revisions_event_cursor_idx
    ON transcript_segment_revisions (event_cursor);
