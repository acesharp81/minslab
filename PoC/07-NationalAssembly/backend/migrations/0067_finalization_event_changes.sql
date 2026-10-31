-- Polling still refreshes the latest checked time for fair queue scheduling.
-- Retain history only when work status/counters/errors actually change.
CREATE OR REPLACE FUNCTION log_meeting_finalization() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' OR (NEW.state-'updated_at') IS DISTINCT FROM (OLD.state-'updated_at') THEN
 INSERT INTO meeting_brief_finalization_events(meeting_brief_id,state) VALUES(NEW.meeting_brief_id,NEW.state);
 END IF; RETURN NEW;
END $$;
