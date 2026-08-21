ALTER TABLE live_broadcasts
    ADD COLUMN official_status text NOT NULL DEFAULT 'PENDING'
        CHECK (official_status IN ('PENDING', 'CHECKING', 'NOT_PUBLISHED', 'PUBLISHED', 'AMBIGUOUS', 'FAILED')),
    ADD COLUMN official_last_checked_at timestamptz,
    ADD COLUMN official_check_attempts integer NOT NULL DEFAULT 0;

CREATE TABLE broadcast_official_publications (
    id uuid PRIMARY KEY,
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id),
    meeting_id uuid NOT NULL REFERENCES meetings(id),
    conference_id text NOT NULL,
    source_document_version_id uuid NOT NULL REFERENCES source_document_versions(id),
    official_url text,
    pdf_url text,
    matched_at timestamptz NOT NULL,
    match_method text NOT NULL,
    match_confidence numeric(4,3) NOT NULL,
    reconciliation_status text NOT NULL DEFAULT 'UNRESOLVED'
        CHECK (reconciliation_status IN ('MATCHED', 'UNRESOLVED', 'CONFLICT')),
    body_contract_status text NOT NULL DEFAULT 'LINK_ONLY'
        CHECK (body_contract_status IN ('LINK_ONLY', 'TEXT_EXTRACTED', 'UNSUPPORTED')),
    UNIQUE (broadcast_id, source_document_version_id, conference_id)
);

CREATE INDEX live_broadcasts_official_poll_idx
    ON live_broadcasts (official_status, ended_at)
    WHERE lifecycle_status = 'ENDED';
CREATE INDEX broadcast_official_publication_broadcast_idx
    ON broadcast_official_publications (broadcast_id, matched_at DESC);
