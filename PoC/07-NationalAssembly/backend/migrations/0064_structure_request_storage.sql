-- One immutable request body; every attempt and its response remain distinct.
CREATE TABLE meeting_structure_requests(request_hash text PRIMARY KEY, request_snapshot jsonb NOT NULL);
ALTER TABLE meeting_topic_structure_batches RENAME TO meeting_topic_structure_attempts;
ALTER TABLE meeting_topic_structure_attempts ADD COLUMN request_hash text;
INSERT INTO meeting_structure_requests
 SELECT DISTINCT encode(sha256(convert_to(request_snapshot::text,'UTF8')),'hex'),request_snapshot FROM meeting_topic_structure_attempts;
UPDATE meeting_topic_structure_attempts SET request_hash=encode(sha256(convert_to(request_snapshot::text,'UTF8')),'hex');
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM meeting_topic_structure_attempts a JOIN meeting_structure_requests r USING(request_hash)
 WHERE a.request_snapshot IS DISTINCT FROM r.request_snapshot) THEN RAISE EXCEPTION 'REQUEST_ROUNDTRIP_MISMATCH'; END IF;
END $$;
ALTER TABLE meeting_topic_structure_attempts ALTER COLUMN request_hash SET NOT NULL,
 ADD FOREIGN KEY(request_hash) REFERENCES meeting_structure_requests(request_hash),DROP COLUMN request_snapshot;
CREATE VIEW meeting_topic_structure_batches AS SELECT a.id,a.structure_id,a.batch_index,a.attempt,a.status,
 r.request_snapshot,a.response,a.usage_metadata,a.error_code,a.created_at
 FROM meeting_topic_structure_attempts a JOIN meeting_structure_requests r USING(request_hash);
CREATE FUNCTION store_structure_attempt() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE k text; BEGIN
 k=encode(sha256(convert_to(NEW.request_snapshot::text,'UTF8')),'hex');
 INSERT INTO meeting_structure_requests VALUES(k,NEW.request_snapshot) ON CONFLICT DO NOTHING;
 IF (SELECT request_snapshot FROM meeting_structure_requests WHERE request_hash=k) IS DISTINCT FROM NEW.request_snapshot
 THEN RAISE EXCEPTION 'REQUEST_HASH_COLLISION'; END IF;
 INSERT INTO meeting_topic_structure_attempts(id,structure_id,batch_index,attempt,status,request_hash,response,usage_metadata,error_code,created_at)
 VALUES(NEW.id,NEW.structure_id,NEW.batch_index,NEW.attempt,NEW.status,k,COALESCE(NEW.response,'{}'),COALESCE(NEW.usage_metadata,'{}'),NEW.error_code,COALESCE(NEW.created_at,now()));
 RETURN NEW;
END $$;
CREATE TRIGGER store_structure_attempt INSTEAD OF INSERT ON meeting_topic_structure_batches
 FOR EACH ROW EXECUTE FUNCTION store_structure_attempt();
