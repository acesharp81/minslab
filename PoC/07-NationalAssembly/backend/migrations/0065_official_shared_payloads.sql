-- Every document/utterance/annotation ID and source locator stays intact.
-- Only repeated text/derived payload bytes are shared. Legacy names are read views.
CREATE TABLE official_text_payloads(text_key text PRIMARY KEY, text text NOT NULL);
ALTER TABLE official_transcript_utterances RENAME TO official_utterance_rows;
ALTER TABLE official_utterance_rows ADD COLUMN text_key text REFERENCES official_text_payloads(text_key),
 ALTER COLUMN text DROP NOT NULL;
ALTER TABLE official_utterance_rows ADD CONSTRAINT official_text_present CHECK(text IS NOT NULL OR text_key IS NOT NULL) NOT VALID;
CREATE VIEW official_transcript_utterances AS SELECT u.id,u.document_id,u.sequence_number,u.source_speaker_id,u.source_span_id,
 u.agenda_item_ref,u.speaker_name,u.speaker_role,COALESCE(u.text,p.text) AS text,u.text_hash,u.source_locator,u.created_at
 FROM official_utterance_rows u LEFT JOIN official_text_payloads p USING(text_key);
CREATE FUNCTION normalize_official_text() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE k text; BEGIN
 IF NEW.text IS NOT NULL THEN
 k=encode(sha256(convert_to(NEW.text,'UTF8')),'hex');
 INSERT INTO official_text_payloads VALUES(k,NEW.text) ON CONFLICT DO NOTHING;
 IF (SELECT text FROM official_text_payloads WHERE text_key=k) IS DISTINCT FROM NEW.text
 THEN RAISE EXCEPTION 'OFFICIAL_TEXT_HASH_COLLISION'; END IF;
 NEW.text_key=k;NEW.text=NULL;
 END IF;RETURN NEW;
END $$;
CREATE TRIGGER normalize_official_text BEFORE INSERT OR UPDATE OF text ON official_utterance_rows
 FOR EACH ROW EXECUTE FUNCTION normalize_official_text();

CREATE TABLE official_annotation_payloads(payload_key text PRIMARY KEY,evidence_keywords text[] NOT NULL,
 topic_links jsonb NOT NULL,ministry_links jsonb NOT NULL);
ALTER TABLE official_utterance_annotations RENAME TO official_annotation_rows;
ALTER TABLE official_annotation_rows ADD COLUMN payload_key text REFERENCES official_annotation_payloads(payload_key),
 ALTER COLUMN evidence_keywords DROP NOT NULL,ALTER COLUMN topic_links DROP NOT NULL,ALTER COLUMN ministry_links DROP NOT NULL;
ALTER TABLE official_annotation_rows ADD CONSTRAINT official_annotation_payload_present CHECK(
 (evidence_keywords IS NOT NULL AND topic_links IS NOT NULL AND ministry_links IS NOT NULL) OR payload_key IS NOT NULL) NOT VALID;
CREATE VIEW official_utterance_annotations AS SELECT a.id,a.utterance_id,a.generator_version,a.classification_method,
 a.topics,a.ministries,a.source_committee,a.authority_status,a.review_status,a.generated_at,a.evidence_text_hash,a.utterance_kind,
 COALESCE(a.evidence_keywords,p.evidence_keywords) AS evidence_keywords,COALESCE(a.topic_links,p.topic_links) AS topic_links,
 COALESCE(a.ministry_links,p.ministry_links) AS ministry_links
 FROM official_annotation_rows a LEFT JOIN official_annotation_payloads p USING(payload_key);
CREATE FUNCTION normalize_official_annotation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE k text; BEGIN
 IF NEW.evidence_keywords IS NOT NULL AND NEW.topic_links IS NOT NULL AND NEW.ministry_links IS NOT NULL THEN
 k=encode(sha256(convert_to(jsonb_build_array(NEW.evidence_keywords,NEW.topic_links,NEW.ministry_links)::text,'UTF8')),'hex');
 INSERT INTO official_annotation_payloads VALUES(k,NEW.evidence_keywords,NEW.topic_links,NEW.ministry_links) ON CONFLICT DO NOTHING;
 IF (SELECT jsonb_build_array(evidence_keywords,topic_links,ministry_links) FROM official_annotation_payloads WHERE payload_key=k)
 IS DISTINCT FROM jsonb_build_array(NEW.evidence_keywords,NEW.topic_links,NEW.ministry_links)
 THEN RAISE EXCEPTION 'OFFICIAL_ANNOTATION_HASH_COLLISION'; END IF;
 NEW.payload_key=k;NEW.evidence_keywords=NULL;NEW.topic_links=NULL;NEW.ministry_links=NULL;
 END IF;RETURN NEW;
END $$;
CREATE TRIGGER normalize_official_annotation BEFORE INSERT OR UPDATE OF evidence_keywords,topic_links,ministry_links
 ON official_annotation_rows FOR EACH ROW EXECUTE FUNCTION normalize_official_annotation();
CREATE TABLE storage_normalization_jobs(job text PRIMARY KEY,cursor_id uuid,completed_rows bigint NOT NULL DEFAULT 0,
 verified_rows bigint NOT NULL DEFAULT 0,status text NOT NULL DEFAULT 'PENDING',updated_at timestamptz NOT NULL DEFAULT now());
ALTER TABLE storage_normalization_jobs ADD COLUMN cursor_block bigint NOT NULL DEFAULT 0;
CREATE TABLE storage_normalization_batches(job text NOT NULL,block_start bigint NOT NULL,block_end bigint NOT NULL,
 row_count bigint NOT NULL,before_hash text,after_hash text,created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(job,block_start));
