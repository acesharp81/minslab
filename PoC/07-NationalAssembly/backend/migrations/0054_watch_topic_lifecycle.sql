-- Delivery ledger survives notification pruning. No historical replay/backfill.
CREATE TABLE watch_topic_episodes (
    id uuid PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES watch_sessions(id) ON DELETE CASCADE,
    rule_revision integer NOT NULL,
    matched_term text NOT NULL,
    started_cursor bigint NOT NULL,
    started_at timestamptz NOT NULL,
    status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'WAITING', 'CLOSED', 'CANCELED')),
    boundary_id uuid,
    closed_at timestamptz,
    details jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE UNIQUE INDEX watch_topic_open_idx ON watch_topic_episodes(session_id, matched_term) WHERE status = 'OPEN';
ALTER TABLE watch_detection_events ADD COLUMN episode_id uuid REFERENCES watch_topic_episodes(id) ON DELETE SET NULL;
CREATE INDEX watch_detection_episode_idx ON watch_detection_events(episode_id);
CREATE TABLE watch_episode_detections (
    episode_id uuid NOT NULL REFERENCES watch_topic_episodes(id) ON DELETE CASCADE,
    event_id uuid NOT NULL REFERENCES watch_detection_events(id) ON DELETE CASCADE,
    PRIMARY KEY(episode_id,event_id)
);
ALTER TABLE watch_notifications DROP CONSTRAINT watch_notifications_subscriber_id_detection_event_id_key;
CREATE TABLE watch_meeting_boundaries (
    id uuid PRIMARY KEY,
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('RECESS', 'ENDED')),
    occurred_at timestamptz NOT NULL,
    cutoff_cursor bigint NOT NULL,
    evidence jsonb NOT NULL,
    UNIQUE(broadcast_id, kind, cutoff_cursor)
);
ALTER TABLE watch_topic_episodes ADD CONSTRAINT watch_episode_boundary_fk
    FOREIGN KEY (boundary_id) REFERENCES watch_meeting_boundaries(id);
CREATE TABLE watch_broadcast_signals (
    broadcast_id uuid PRIMARY KEY REFERENCES live_broadcasts(id) ON DELETE CASCADE,
    state text NOT NULL,
    observed_at timestamptz NOT NULL
);
CREATE TABLE watch_dispatches (
    id uuid PRIMARY KEY,
    sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    subscriber_id uuid NOT NULL REFERENCES watch_subscribers(id) ON DELETE CASCADE,
    session_id uuid NOT NULL REFERENCES watch_sessions(id) ON DELETE CASCADE,
    dedupe_key text NOT NULL UNIQUE,
    stage integer NOT NULL CHECK (stage BETWEEN 1 AND 3),
    details jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE watch_notifications ADD COLUMN dispatch_id uuid REFERENCES watch_dispatches(id) ON DELETE SET NULL;
ALTER TABLE watch_notifications DROP CONSTRAINT watch_notifications_notification_type_check;
ALTER TABLE watch_notifications ADD CONSTRAINT watch_notifications_notification_type_check
    CHECK (notification_type IN ('MATCH', 'TOPIC_COMPLETE', 'DIGEST'));
-- Retain legacy columns for compatibility with older workers during rolling deployment.
-- New code exposes no user-selectable frequency/digest options.
CREATE TABLE watch_lifecycle_rollout (singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), starts_at timestamptz NOT NULL);
INSERT INTO watch_lifecycle_rollout VALUES (true, now());
