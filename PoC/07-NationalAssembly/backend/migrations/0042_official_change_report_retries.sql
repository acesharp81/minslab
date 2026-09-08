ALTER TABLE meeting_official_change_reports
    ADD COLUMN attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    ADD COLUMN next_attempt_at timestamptz;

-- Existing one-off failures get one controlled retry after this migration.
UPDATE meeting_official_change_reports
SET attempt_count = 1, next_attempt_at = now()
WHERE status = 'FAILED';

DROP INDEX IF EXISTS meeting_official_change_reports_claim_idx;
CREATE INDEX meeting_official_change_reports_claim_idx
    ON meeting_official_change_reports (status, next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'PROCESSING', 'FAILED');
