CREATE TABLE meeting_official_integrations (
    id uuid PRIMARY KEY,
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id),
    meeting_brief_id uuid NOT NULL REFERENCES meeting_briefs(id),
    official_document_id uuid NOT NULL REFERENCES official_transcript_documents(id),
    integration_version text NOT NULL,
    status text NOT NULL CHECK (status IN ('PROCESSING', 'READY', 'REVIEW_REQUIRED', 'FAILED')),
    integrated_brief jsonb NOT NULL DEFAULT '{}'::jsonb,
    changes jsonb NOT NULL DEFAULT '[]'::jsonb,
    speaker_stats jsonb NOT NULL DEFAULT '{}'::jsonb,
    usage_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    generated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (meeting_brief_id, official_document_id, integration_version)
);

CREATE INDEX meeting_official_integrations_broadcast_latest_idx
    ON meeting_official_integrations (broadcast_id, generated_at DESC);
