ALTER TABLE watch_rules
    ADD COLUMN cooldown_minutes integer NOT NULL DEFAULT 10
        CHECK (cooldown_minutes IN (10, 15, 30, 60)),
    ADD COLUMN digest_enabled boolean NOT NULL DEFAULT false,
    ADD COLUMN current_revision integer NOT NULL DEFAULT 1 CHECK (current_revision > 0),
    ADD COLUMN archived_at timestamptz;

ALTER TABLE watch_rules DROP CONSTRAINT watch_rules_notification_policy_check;
ALTER TABLE watch_rules ADD CONSTRAINT watch_rules_notification_policy_check
    CHECK (notification_policy IN (
        'FIRST_PER_MEETING', 'FIRST_PER_SPEAKER',
        'ONCE_PER_10_MINUTES', 'INTERVAL_15_MINUTES',
        'INTERVAL_30_MINUTES', 'INTERVAL_60_MINUTES', 'EVERY_MATCH'
    ));

CREATE TABLE watch_rule_revisions (
    id uuid PRIMARY KEY,
    rule_id uuid NOT NULL REFERENCES watch_rules(id) ON DELETE CASCADE,
    revision integer NOT NULL CHECK (revision > 0),
    effective_at timestamptz NOT NULL DEFAULT now(),
    configuration jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (rule_id, revision)
);

INSERT INTO watch_rule_revisions (id, rule_id, revision, effective_at, configuration)
SELECT gen_random_uuid(), id, 1, starts_at,
       jsonb_build_object(
           'name', name,
           'include_terms', include_terms,
           'exclude_terms', exclude_terms,
           'institution', institution,
           'committee_name', committee_name,
           'notification_policy', notification_policy,
           'cooldown_minutes', cooldown_minutes,
           'digest_enabled', digest_enabled,
           'enabled', enabled
       )
FROM watch_rules;

ALTER TABLE watch_notifications
    ALTER COLUMN detection_event_id DROP NOT NULL,
    ADD COLUMN notification_type text NOT NULL DEFAULT 'MATCH'
        CHECK (notification_type IN ('MATCH', 'DIGEST')),
    ADD COLUMN dedupe_key text;

UPDATE watch_notifications SET dedupe_key = 'match:' || id::text WHERE dedupe_key IS NULL;
ALTER TABLE watch_notifications ALTER COLUMN dedupe_key SET NOT NULL;
CREATE UNIQUE INDEX watch_notifications_dedupe_idx ON watch_notifications (dedupe_key);

CREATE TABLE watch_match_official_verifications (
    id uuid PRIMARY KEY,
    match_id uuid NOT NULL REFERENCES watch_matches(id) ON DELETE CASCADE,
    official_document_id uuid NOT NULL REFERENCES official_transcript_documents(id) ON DELETE CASCADE,
    official_utterance_id uuid REFERENCES official_transcript_utterances(id) ON DELETE SET NULL,
    status text NOT NULL CHECK (status IN (
        'PENDING_OFFICIAL', 'OFFICIAL_CONFIRMED', 'OFFICIAL_CORRECTED',
        'OFFICIAL_NOT_CONFIRMED', 'REVIEW_REQUIRED'
    )),
    verification_method text NOT NULL,
    verified_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (match_id, official_document_id)
);
CREATE INDEX watch_match_verification_status_idx
    ON watch_match_official_verifications (status, verified_at DESC);
