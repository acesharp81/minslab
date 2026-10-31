-- Preserve the JSON contract while separating body versions from progress.
CREATE TABLE meeting_brief_finalization_state (
 meeting_brief_id uuid PRIMARY KEY REFERENCES meeting_briefs(id), state jsonb NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE meeting_brief_finalization_events (
 id bigserial PRIMARY KEY, meeting_brief_id uuid NOT NULL REFERENCES meeting_briefs(id),
 state jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX meeting_brief_finalization_events_brief ON meeting_brief_finalization_events(meeting_brief_id,id);
INSERT INTO meeting_brief_finalization_state(meeting_brief_id,state)
 SELECT id,brief->'finalization' FROM meeting_briefs WHERE brief ? 'finalization';
CREATE FUNCTION meeting_brief_payload(source_id uuid, body jsonb) RETURNS jsonb
 LANGUAGE sql STABLE AS $$ SELECT body || COALESCE((SELECT jsonb_build_object('finalization',state)
 FROM meeting_brief_finalization_state WHERE meeting_brief_id=source_id),'{}'::jsonb) $$;
CREATE FUNCTION log_meeting_finalization() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' OR NEW.state IS DISTINCT FROM OLD.state THEN
 INSERT INTO meeting_brief_finalization_events(meeting_brief_id,state) VALUES(NEW.meeting_brief_id,NEW.state);
 END IF; RETURN NEW;
END $$;
CREATE TRIGGER meeting_finalization_log AFTER INSERT OR UPDATE ON meeting_brief_finalization_state
 FOR EACH ROW EXECUTE FUNCTION log_meeting_finalization();
-- New/legacy writers can still submit the original complete JSON.
CREATE FUNCTION split_meeting_finalization() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.brief ? 'finalization' THEN
 INSERT INTO meeting_brief_finalization_state(meeting_brief_id,state) VALUES(NEW.id,NEW.brief->'finalization')
 ON CONFLICT(meeting_brief_id) DO UPDATE SET state=EXCLUDED.state,updated_at=now()
 WHERE meeting_brief_finalization_state.state IS DISTINCT FROM EXCLUDED.state;
 END IF; RETURN NULL;
END $$;
-- AFTER INSERT keeps the state FK valid. Routine progress writes use the state table directly.
CREATE TRIGGER meeting_brief_initial_state AFTER INSERT ON meeting_briefs FOR EACH ROW EXECUTE FUNCTION split_meeting_finalization();

CREATE TABLE meeting_brief_revision_bodies(body_hash text PRIMARY KEY, body jsonb NOT NULL);
ALTER TABLE meeting_brief_revisions RENAME TO meeting_brief_revision_entries;
ALTER TABLE meeting_brief_revision_entries ADD COLUMN body_hash text, ADD COLUMN finalization jsonb,
 ADD COLUMN had_finalization boolean NOT NULL DEFAULT false;
INSERT INTO meeting_brief_revision_bodies SELECT DISTINCT encode(sha256(convert_to((brief-'finalization')::text,'UTF8')),'hex'),brief-'finalization' FROM meeting_brief_revision_entries;
UPDATE meeting_brief_revision_entries SET body_hash=encode(sha256(convert_to((brief-'finalization')::text,'UTF8')),'hex'),
 finalization=brief->'finalization',had_finalization=brief ? 'finalization';
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM meeting_brief_revision_entries e JOIN meeting_brief_revision_bodies b USING(body_hash)
 WHERE e.brief IS DISTINCT FROM b.body || CASE WHEN had_finalization THEN jsonb_build_object('finalization',finalization) ELSE '{}'::jsonb END)
 THEN RAISE EXCEPTION 'BRIEF_REVISION_ROUNDTRIP_MISMATCH'; END IF;
END $$;
ALTER TABLE meeting_brief_revision_entries ALTER COLUMN body_hash SET NOT NULL,
 ADD FOREIGN KEY(body_hash) REFERENCES meeting_brief_revision_bodies(body_hash), DROP COLUMN brief;
CREATE VIEW meeting_brief_revisions AS SELECT e.id,e.meeting_brief_id,
 b.body || CASE WHEN e.had_finalization THEN jsonb_build_object('finalization',e.finalization) ELSE '{}'::jsonb END AS brief,
 e.reason,e.created_at FROM meeting_brief_revision_entries e JOIN meeting_brief_revision_bodies b USING(body_hash);
CREATE FUNCTION store_meeting_brief_revision() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE k text; BEGIN
 k=encode(sha256(convert_to((NEW.brief-'finalization')::text,'UTF8')),'hex');
 INSERT INTO meeting_brief_revision_bodies VALUES(k,NEW.brief-'finalization') ON CONFLICT DO NOTHING;
 IF (SELECT body FROM meeting_brief_revision_bodies WHERE body_hash=k) IS DISTINCT FROM NEW.brief-'finalization'
 THEN RAISE EXCEPTION 'BRIEF_BODY_HASH_COLLISION'; END IF;
 INSERT INTO meeting_brief_revision_entries(meeting_brief_id,body_hash,finalization,had_finalization,reason,created_at)
 VALUES(NEW.meeting_brief_id,k,NEW.brief->'finalization',NEW.brief ? 'finalization',NEW.reason,COALESCE(NEW.created_at,now())) RETURNING id INTO NEW.id;
 RETURN NEW;
END $$;
CREATE TRIGGER store_meeting_brief_revision INSTEAD OF INSERT ON meeting_brief_revisions
 FOR EACH ROW EXECUTE FUNCTION store_meeting_brief_revision();
