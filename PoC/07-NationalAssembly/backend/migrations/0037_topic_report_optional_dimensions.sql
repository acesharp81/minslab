-- A report may be scoped by ministry, topic, or both.

ALTER TABLE topic_reports
    DROP CONSTRAINT IF EXISTS topic_reports_ministry_check,
    DROP CONSTRAINT IF EXISTS topic_reports_topic_check;

ALTER TABLE topic_reports
    ADD CONSTRAINT topic_reports_ministry_check
        CHECK (char_length(ministry) BETWEEN 0 AND 80),
    ADD CONSTRAINT topic_reports_topic_check
        CHECK (char_length(topic) = 0 OR char_length(topic) BETWEEN 2 AND 160),
    ADD CONSTRAINT topic_reports_scope_check
        CHECK (
            char_length(btrim(ministry)) >= 1
            OR char_length(btrim(topic)) >= 2
        );
