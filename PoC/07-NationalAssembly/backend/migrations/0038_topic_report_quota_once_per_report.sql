-- Count a topic-report request once even when the worker retries it.

ALTER TABLE topic_reports
    ADD COLUMN quota_reserved_at timestamptz;

UPDATE topic_reports
SET quota_reserved_at = COALESCE(generated_at, updated_at)
WHERE status IN ('READY', 'FAILED');

UPDATE topic_report_daily_usage usage
SET request_count = (
        SELECT count(*)
        FROM topic_reports report
        WHERE report.subscriber_id = usage.subscriber_id
          AND timezone('UTC', report.quota_reserved_at)::date = usage.usage_date
    ),
    updated_at = now();
