ALTER TABLE live_broadcasts
    ADD COLUMN thumbnail_url text,
    ADD COLUMN review_status text NOT NULL DEFAULT 'PENDING'
        CHECK (review_status IN ('PENDING', 'READY', 'PROCESSING', 'COMPLETED', 'NO_CONTENT', 'RETRY_WAIT', 'FAILED')),
    ADD COLUMN review_lease_owner text,
    ADD COLUMN review_lease_expires_at timestamptz,
    ADD COLUMN review_attempts integer NOT NULL DEFAULT 0;

UPDATE live_broadcasts
SET review_status = 'READY'
WHERE lifecycle_status = 'ENDED';

CREATE TABLE broadcast_reviews (
    id uuid PRIMARY KEY,
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id),
    generator_version text NOT NULL,
    source_last_event_cursor bigint NOT NULL CHECK (source_last_event_cursor >= 0),
    authority_status text NOT NULL DEFAULT 'PROVISIONAL'
        CHECK (authority_status = 'PROVISIONAL'),
    reconciliation_status text NOT NULL DEFAULT 'UNRESOLVED'
        CHECK (reconciliation_status IN ('MATCHED', 'UNRESOLVED', 'CONFLICT')),
    classification_method text NOT NULL,
    generated_at timestamptz NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (broadcast_id, generator_version, source_last_event_cursor)
);

CREATE TABLE broadcast_review_topics (
    id uuid PRIMARY KEY,
    review_id uuid NOT NULL REFERENCES broadcast_reviews(id),
    topic text NOT NULL,
    major_quote text NOT NULL,
    speaker_label text,
    ministries text[] NOT NULL DEFAULT '{}',
    committees text[] NOT NULL DEFAULT '{}',
    segment_count integer NOT NULL CHECK (segment_count > 0),
    representative_revision_id uuid NOT NULL REFERENCES transcript_segment_revisions(id),
    sort_order integer NOT NULL CHECK (sort_order >= 0),
    UNIQUE (review_id, topic)
);

CREATE TABLE broadcast_review_evidence (
    review_topic_id uuid NOT NULL REFERENCES broadcast_review_topics(id),
    revision_id uuid NOT NULL REFERENCES transcript_segment_revisions(id),
    position integer NOT NULL CHECK (position >= 0),
    PRIMARY KEY (review_topic_id, revision_id)
);

CREATE INDEX live_broadcasts_review_claim_idx
    ON live_broadcasts (review_status, ended_at)
    WHERE lifecycle_status = 'ENDED';
CREATE INDEX broadcast_reviews_recent_idx
    ON broadcast_reviews (generated_at DESC);
