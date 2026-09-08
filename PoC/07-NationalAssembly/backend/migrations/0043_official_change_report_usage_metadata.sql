UPDATE meeting_official_change_reports
SET usage_metadata = COALESCE(usage_metadata, '{}'::jsonb)
                     || '{"api_requests": 1}'::jsonb
WHERE status = 'READY'
  AND usage_metadata ? 'request_id'
  AND NOT usage_metadata ? 'api_requests';
