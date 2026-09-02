ALTER TABLE watch_summary_versions
    DROP CONSTRAINT watch_summary_versions_session_id_evidence_set_hash_key;

ALTER TABLE watch_summary_versions
    ADD CONSTRAINT watch_summary_versions_identity_key
    UNIQUE (session_id, evidence_set_hash, provider, model, prompt_version);
