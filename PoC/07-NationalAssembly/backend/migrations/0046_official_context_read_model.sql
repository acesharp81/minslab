ALTER TABLE live_broadcasts
    ADD COLUMN final_segment_count integer NOT NULL DEFAULT 0
        CHECK (final_segment_count >= 0),
    ADD COLUMN matched_segment_count integer NOT NULL DEFAULT 0
        CHECK (matched_segment_count >= 0),
    ADD COLUMN official_context_stats_updated_at timestamptz;

WITH final_counts AS MATERIALIZED (
    SELECT segment.broadcast_id, COUNT(*)::integer AS count
    FROM transcript_segments segment
    WHERE segment.is_final
    GROUP BY segment.broadcast_id
), matched_counts AS MATERIALIZED (
    SELECT segment.broadcast_id,
           COUNT(DISTINCT reconciliation.transcript_revision_id)::integer AS count
    FROM transcript_official_reconciliations reconciliation
    JOIN transcript_segment_revisions revision
      ON revision.id = reconciliation.transcript_revision_id
    JOIN transcript_segments segment ON segment.id = revision.segment_id
    WHERE reconciliation.reconciliation_status = 'MATCHED'
    GROUP BY segment.broadcast_id
), initial_counts AS (
    SELECT broadcast.id,
           COALESCE(finals.count, 0) AS final_segment_count,
           COALESCE(matches.count, 0) AS matched_segment_count
    FROM live_broadcasts broadcast
    LEFT JOIN final_counts finals ON finals.broadcast_id = broadcast.id
    LEFT JOIN matched_counts matches ON matches.broadcast_id = broadcast.id
)
UPDATE live_broadcasts broadcast
SET final_segment_count = counts.final_segment_count,
    matched_segment_count = counts.matched_segment_count,
    official_context_stats_updated_at = now()
FROM initial_counts counts
WHERE counts.id = broadcast.id;

CREATE OR REPLACE FUNCTION maintain_broadcast_final_segment_count()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP IN ('DELETE', 'UPDATE')
       AND OLD.is_final
       AND (
            TG_OP = 'DELETE'
            OR NOT NEW.is_final
            OR NEW.broadcast_id <> OLD.broadcast_id
       ) THEN
        UPDATE live_broadcasts
        SET final_segment_count = GREATEST(final_segment_count - 1, 0),
            official_context_stats_updated_at = now()
        WHERE id = OLD.broadcast_id;
    END IF;

    IF TG_OP IN ('INSERT', 'UPDATE')
       AND NEW.is_final
       AND (
            TG_OP = 'INSERT'
            OR NOT OLD.is_final
            OR NEW.broadcast_id <> OLD.broadcast_id
       ) THEN
        UPDATE live_broadcasts
        SET final_segment_count = final_segment_count + 1,
            official_context_stats_updated_at = now()
        WHERE id = NEW.broadcast_id;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER transcript_segments_final_count_trigger
AFTER INSERT OR DELETE OR UPDATE OF broadcast_id, is_final
ON transcript_segments
FOR EACH ROW
EXECUTE FUNCTION maintain_broadcast_final_segment_count();
