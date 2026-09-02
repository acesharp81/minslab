CREATE TABLE watch_subscribers (
    id uuid PRIMARY KEY,
    token_hash char(64) NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE watch_rules (
    id uuid PRIMARY KEY,
    subscriber_id uuid NOT NULL REFERENCES watch_subscribers(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 80),
    include_terms text[] NOT NULL CHECK (cardinality(include_terms) BETWEEN 1 AND 10),
    exclude_terms text[] NOT NULL DEFAULT '{}'::text[],
    institution text CHECK (institution IS NULL OR institution IN ('EXECUTIVE', 'LEGISLATURE')),
    committee_name text,
    notification_policy text NOT NULL DEFAULT 'FIRST_PER_MEETING'
        CHECK (notification_policy IN ('FIRST_PER_MEETING', 'ONCE_PER_10_MINUTES', 'EVERY_MATCH')),
    enabled boolean NOT NULL DEFAULT true,
    starts_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX watch_rules_active_idx ON watch_rules (enabled, starts_at);

CREATE TABLE watch_detection_events (
    id uuid PRIMARY KEY,
    subscriber_id uuid NOT NULL REFERENCES watch_subscribers(id) ON DELETE CASCADE,
    rule_id uuid NOT NULL REFERENCES watch_rules(id) ON DELETE CASCADE,
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id) ON DELETE CASCADE,
    segment_id uuid NOT NULL REFERENCES transcript_segments(id) ON DELETE CASCADE,
    revision_id uuid NOT NULL REFERENCES transcript_segment_revisions(id) ON DELETE CASCADE,
    matched_term text NOT NULL,
    excerpt text NOT NULL,
    speaker_label text,
    detected_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (rule_id, revision_id)
);
CREATE INDEX watch_detection_subscriber_idx
    ON watch_detection_events (subscriber_id, detected_at DESC);

CREATE TABLE watch_sessions (
    id uuid PRIMARY KEY,
    subscriber_id uuid NOT NULL REFERENCES watch_subscribers(id) ON DELETE CASCADE,
    rule_id uuid NOT NULL REFERENCES watch_rules(id) ON DELETE CASCADE,
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id) ON DELETE CASCADE,
    title text NOT NULL,
    status text NOT NULL DEFAULT 'LIVE' CHECK (status IN ('LIVE', 'ENDED')),
    first_matched_at timestamptz NOT NULL,
    last_matched_at timestamptz NOT NULL,
    match_count integer NOT NULL DEFAULT 0 CHECK (match_count >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (rule_id, broadcast_id)
);

CREATE TABLE watch_matches (
    id uuid PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES watch_sessions(id) ON DELETE CASCADE,
    detection_event_id uuid NOT NULL REFERENCES watch_detection_events(id) ON DELETE CASCADE,
    segment_id uuid NOT NULL REFERENCES transcript_segments(id) ON DELETE CASCADE,
    revision_id uuid NOT NULL REFERENCES transcript_segment_revisions(id) ON DELETE CASCADE,
    speaker_label text,
    excerpt text NOT NULL,
    matched_term text NOT NULL,
    matched_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, revision_id)
);
CREATE INDEX watch_matches_session_idx ON watch_matches (session_id, matched_at);

CREATE TABLE watch_notifications (
    id uuid PRIMARY KEY,
    subscriber_id uuid NOT NULL REFERENCES watch_subscribers(id) ON DELETE CASCADE,
    detection_event_id uuid NOT NULL REFERENCES watch_detection_events(id) ON DELETE CASCADE,
    session_id uuid NOT NULL REFERENCES watch_sessions(id) ON DELETE CASCADE,
    title text NOT NULL,
    body text NOT NULL,
    is_test boolean NOT NULL DEFAULT false,
    read_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (subscriber_id, detection_event_id)
);
CREATE INDEX watch_notifications_unread_idx
    ON watch_notifications (subscriber_id, read_at, created_at DESC);

CREATE TABLE notification_outbox (
    id uuid PRIMARY KEY,
    subscriber_id uuid NOT NULL REFERENCES watch_subscribers(id) ON DELETE CASCADE,
    notification_id uuid NOT NULL REFERENCES watch_notifications(id) ON DELETE CASCADE,
    channel text NOT NULL CHECK (channel IN ('IN_APP', 'KAKAO')),
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'SENT', 'FAILED')),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    sent_at timestamptz,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (notification_id, channel)
);

CREATE TABLE watch_test_broadcasts (
    id uuid PRIMARY KEY,
    subscriber_id uuid NOT NULL REFERENCES watch_subscribers(id) ON DELETE CASCADE,
    broadcast_id uuid NOT NULL UNIQUE REFERENCES live_broadcasts(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'QUEUED' CHECK (status IN ('QUEUED', 'LIVE', 'COMPLETED', 'FAILED')),
    current_step integer NOT NULL DEFAULT 0 CHECK (current_step >= 0),
    total_steps integer NOT NULL CHECK (total_steps > 0),
    next_emit_at timestamptz NOT NULL,
    script jsonb NOT NULL,
    started_at timestamptz,
    ended_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX watch_test_due_idx ON watch_test_broadcasts (status, next_emit_at);

CREATE TABLE watch_worker_state (
    worker_name text PRIMARY KEY,
    event_cursor bigint NOT NULL DEFAULT 0 CHECK (event_cursor >= 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO watch_worker_state (worker_name, event_cursor)
VALUES ('watch-alerts', COALESCE((SELECT MAX(event_cursor) FROM transcript_segment_revisions), 0))
ON CONFLICT (worker_name) DO NOTHING;
