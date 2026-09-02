ALTER TABLE watch_sessions
    ADD COLUMN report_summary_requested_at timestamptz;

CREATE INDEX watch_sessions_report_summary_request_idx
    ON watch_sessions (report_summary_requested_at DESC)
    WHERE report_summary_requested_at IS NOT NULL;
