-- Completed topic reports are public read models retained for 30 days, at most 50.

CREATE INDEX topic_reports_public_ready_idx
    ON topic_reports (generated_at DESC, id DESC)
    WHERE status = 'READY';

WITH retained AS (
    SELECT id
    FROM topic_reports
    WHERE status = 'READY'
      AND generated_at >= now() - interval '30 days'
    ORDER BY generated_at DESC, id DESC
    LIMIT 50
)
DELETE FROM topic_reports report
WHERE (
        report.status = 'READY'
        AND NOT EXISTS (
            SELECT 1 FROM retained WHERE retained.id = report.id
        )
      )
   OR (
        report.status <> 'READY'
        AND report.updated_at < now() - interval '30 days'
      );
