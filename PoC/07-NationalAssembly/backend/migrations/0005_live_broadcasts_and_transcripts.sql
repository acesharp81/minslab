CREATE TABLE live_broadcasts (
    id uuid PRIMARY KEY,
    meeting_id uuid REFERENCES meetings(id),
    institution text NOT NULL CHECK (institution IN ('EXECUTIVE', 'LEGISLATURE')),
    source_system text NOT NULL,
    external_id text NOT NULL,
    committee_name text,
    title text,
    lifecycle_status text NOT NULL CHECK (lifecycle_status IN ('SCHEDULED', 'LIVE', 'ENDED', 'CANCELED')),
    caption_source_status text NOT NULL,
    detected_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    ended_at timestamptz,
    latest_source_document_version_id uuid NOT NULL REFERENCES source_document_versions(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_system, external_id)
);

CREATE TABLE live_broadcast_source_versions (
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id),
    source_document_version_id uuid NOT NULL REFERENCES source_document_versions(id),
    observed_at timestamptz NOT NULL,
    PRIMARY KEY (broadcast_id, source_document_version_id)
);

CREATE TABLE transcript_segments (
    id uuid PRIMARY KEY,
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id),
    source_segment_id text NOT NULL,
    speaker_label text,
    start_offset_ms integer CHECK (start_offset_ms IS NULL OR start_offset_ms >= 0),
    end_offset_ms integer CHECK (end_offset_ms IS NULL OR end_offset_ms >= 0),
    current_text text NOT NULL DEFAULT '',
    is_final boolean NOT NULL DEFAULT false,
    authority_status text NOT NULL DEFAULT 'LIVE' CHECK (authority_status IN ('LIVE', 'PROVISIONAL', 'OFFICIAL')),
    first_received_at timestamptz NOT NULL,
    last_received_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (broadcast_id, source_segment_id)
);

CREATE TABLE transcript_segment_revisions (
    id uuid PRIMARY KEY,
    segment_id uuid NOT NULL REFERENCES transcript_segments(id),
    revision_number integer NOT NULL CHECK (revision_number > 0),
    content_hash char(64) NOT NULL,
    text text NOT NULL,
    speaker_label text,
    is_final boolean NOT NULL,
    received_at timestamptz NOT NULL,
    source_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (segment_id, revision_number),
    UNIQUE (segment_id, content_hash)
);

CREATE INDEX live_broadcasts_lifecycle_idx
    ON live_broadcasts (institution, lifecycle_status, last_seen_at DESC);
CREATE INDEX transcript_segments_broadcast_idx
    ON transcript_segments (broadcast_id, first_received_at, source_segment_id);
CREATE INDEX transcript_revisions_segment_idx
    ON transcript_segment_revisions (segment_id, revision_number);
