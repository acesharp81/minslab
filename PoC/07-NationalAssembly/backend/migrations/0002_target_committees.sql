ALTER TABLE schedule_entries
    ADD COLUMN is_target_committee boolean NOT NULL DEFAULT false;

UPDATE schedule_entries
SET is_target_committee = COALESCE(committee_name IN (
    '행정안전위원회',
    '예산결산특별위원회',
    '법제사법위원회'
), false);

CREATE INDEX schedule_entries_target_date_idx
    ON schedule_entries (is_target_committee, scheduled_date, start_time);
