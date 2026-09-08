-- Durable queue for reconciling provisional LIVE briefs with official minutes.
-- One broken or completed meeting must not block newer pending meetings.
CREATE TABLE meeting_official_integration_jobs (
    id uuid PRIMARY KEY,
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id) ON DELETE CASCADE,
    meeting_brief_id uuid NOT NULL REFERENCES meeting_briefs(id) ON DELETE CASCADE,
    official_document_id uuid NOT NULL REFERENCES official_transcript_documents(id) ON DELETE CASCADE,
    integration_version text NOT NULL,
    status text NOT NULL DEFAULT 'PENDING' CHECK (
        status IN ('PENDING', 'PROCESSING', 'RETRY_WAIT', 'READY', 'FAILED')
    ),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_error text,
    next_attempt_at timestamptz,
    lease_owner text,
    lease_expires_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (meeting_brief_id, official_document_id, integration_version)
);

CREATE INDEX meeting_official_integration_jobs_claim_idx
    ON meeting_official_integration_jobs (status, next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'PROCESSING', 'RETRY_WAIT');

CREATE INDEX meeting_official_integration_jobs_broadcast_idx
    ON meeting_official_integration_jobs (broadcast_id, updated_at DESC);

-- A meeting body can be collected before the LIVE broadcast is matched to its
-- official publication. Attach those preserved versions as soon as the exact
-- meeting/conference identity is available.
UPDATE official_transcript_documents document
SET publication_id = (
    SELECT publication.id AS publication_id
    FROM broadcast_official_publications publication
    WHERE publication.meeting_id = document.meeting_id
      AND publication.conference_id = document.conference_id
    ORDER BY publication.matched_at DESC, publication.id DESC
    LIMIT 1
)
WHERE document.publication_id IS NULL
  AND EXISTS (
      SELECT 1
      FROM broadcast_official_publications publication
      WHERE publication.meeting_id = document.meeting_id
        AND publication.conference_id = document.conference_id
  );

UPDATE broadcast_official_publications publication
SET body_contract_status = 'TEXT_EXTRACTED'
WHERE EXISTS (
    SELECT 1
    FROM official_transcript_documents document
    WHERE document.publication_id = publication.id
      AND document.extraction_status = 'EXTRACTED'
);
