CREATE TABLE meeting_external_ids (
    id uuid PRIMARY KEY,
    meeting_id uuid NOT NULL REFERENCES meetings(id),
    source_system text NOT NULL,
    id_type text NOT NULL,
    external_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_system, id_type, external_id)
);

CREATE TABLE committee_minute_entries (
    id uuid PRIMARY KEY,
    meeting_id uuid NOT NULL REFERENCES meetings(id),
    source_document_version_id uuid NOT NULL REFERENCES source_document_versions(id),
    source_record_key char(64) NOT NULL,
    conference_id text NOT NULL,
    conference_number text,
    subject_name text,
    minutes_url text,
    pdf_url text,
    pdf_file_id text,
    vod_url text,
    department_code text,
    authority_status text NOT NULL CHECK (authority_status IN ('LIVE', 'PROVISIONAL', 'OFFICIAL')),
    official_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_document_version_id, source_record_key)
);

CREATE TABLE bills (
    id uuid PRIMARY KEY,
    bill_id text NOT NULL UNIQUE,
    bill_name text NOT NULL,
    official_url text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agenda_items (
    id uuid PRIMARY KEY,
    meeting_id uuid NOT NULL REFERENCES meetings(id),
    bill_id uuid REFERENCES bills(id),
    source_document_version_id uuid NOT NULL REFERENCES source_document_versions(id),
    source_record_key char(64) NOT NULL,
    conference_id text NOT NULL,
    assembly_term text,
    session_text text,
    meeting_order_text text,
    agenda_name text NOT NULL,
    official_url text,
    authority_status text NOT NULL CHECK (authority_status IN ('LIVE', 'PROVISIONAL', 'OFFICIAL')),
    official_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_document_version_id, source_record_key)
);

CREATE INDEX committee_minute_entries_meeting_idx ON committee_minute_entries (meeting_id);
CREATE INDEX agenda_items_meeting_idx ON agenda_items (meeting_id);
