CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE source_documents (
    id uuid PRIMARY KEY,
    source_system text NOT NULL,
    source_type text NOT NULL,
    external_id text NOT NULL,
    canonical_url text,
    first_seen_at timestamptz NOT NULL,
    UNIQUE (source_system, source_type, external_id)
);

CREATE TABLE source_document_versions (
    id uuid PRIMARY KEY,
    source_document_id uuid NOT NULL REFERENCES source_documents(id),
    content_hash char(64) NOT NULL,
    source_url text NOT NULL,
    raw_path text NOT NULL,
    retrieved_at timestamptz NOT NULL,
    published_at timestamptz,
    parser_version text NOT NULL,
    content_type text NOT NULL,
    authority_status text NOT NULL CHECK (authority_status IN ('LIVE', 'PROVISIONAL', 'OFFICIAL')),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (source_document_id, content_hash)
);

CREATE TABLE meetings (
    id uuid PRIMARY KEY,
    meeting_uid uuid NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE meeting_sources (
    id uuid PRIMARY KEY,
    meeting_id uuid NOT NULL REFERENCES meetings(id),
    source_document_version_id uuid NOT NULL REFERENCES source_document_versions(id),
    source_record_key char(64) NOT NULL,
    reconciliation_status text NOT NULL CHECK (reconciliation_status IN ('MATCHED', 'UNRESOLVED', 'CONFLICT')),
    match_method text NOT NULL,
    match_confidence numeric(4,3),
    UNIQUE (source_document_version_id, source_record_key)
);

CREATE TABLE meeting_versions (
    id uuid PRIMARY KEY,
    meeting_id uuid NOT NULL REFERENCES meetings(id),
    source_document_version_id uuid NOT NULL REFERENCES source_document_versions(id),
    source_record_key char(64) NOT NULL,
    lifecycle_status text NOT NULL CHECK (lifecycle_status IN ('SCHEDULED', 'LIVE', 'ENDED', 'CANCELED')),
    authority_status text NOT NULL CHECK (authority_status IN ('LIVE', 'PROVISIONAL', 'OFFICIAL')),
    title text,
    meeting_type text,
    committee_name text,
    scheduled_date date NOT NULL,
    start_time time,
    end_time time,
    time_text text,
    session_text text,
    meeting_order_text text,
    place text,
    official_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (meeting_id, source_document_version_id, source_record_key)
);

CREATE TABLE schedule_entries (
    id uuid PRIMARY KEY,
    source_document_version_id uuid NOT NULL REFERENCES source_document_versions(id),
    source_record_key char(64) NOT NULL,
    meeting_id uuid REFERENCES meetings(id),
    schedule_kind text,
    title text,
    scheduled_date date NOT NULL,
    start_time time,
    end_time time,
    time_text text,
    meeting_type text,
    committee_name text,
    session_text text,
    meeting_order_text text,
    host_name text,
    place text,
    authority_status text NOT NULL CHECK (authority_status IN ('LIVE', 'PROVISIONAL', 'OFFICIAL')),
    reconciliation_status text NOT NULL CHECK (reconciliation_status IN ('MATCHED', 'UNRESOLVED', 'CONFLICT')),
    official_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_document_version_id, source_record_key)
);

CREATE INDEX schedule_entries_date_idx ON schedule_entries (scheduled_date, start_time);
CREATE INDEX meeting_versions_date_idx ON meeting_versions (scheduled_date, start_time);
