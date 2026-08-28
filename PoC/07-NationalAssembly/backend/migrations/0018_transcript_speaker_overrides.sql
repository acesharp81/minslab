CREATE TABLE transcript_speaker_overrides (
    id uuid PRIMARY KEY,
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id) ON DELETE CASCADE,
    source_speaker_label text NOT NULL,
    display_name text NOT NULL CHECK (length(btrim(display_name)) BETWEEN 1 AND 80),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (broadcast_id, source_speaker_label)
);

CREATE INDEX transcript_speaker_overrides_broadcast_idx
    ON transcript_speaker_overrides (broadcast_id, source_speaker_label);
