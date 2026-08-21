CREATE TABLE bill_official_documents (
    id uuid PRIMARY KEY,
    bill_id uuid NOT NULL REFERENCES bills(id),
    source_document_version_id uuid NOT NULL REFERENCES source_document_versions(id),
    document_kind text NOT NULL,
    document_index integer NOT NULL,
    title text,
    page_count integer,
    extracted_text text NOT NULL,
    parser_version text NOT NULL,
    authority_status text NOT NULL CHECK (authority_status IN ('PROVISIONAL', 'OFFICIAL')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (bill_id, source_document_version_id, document_index)
);

CREATE TABLE bill_official_document_sections (
    id uuid PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES bill_official_documents(id) ON DELETE CASCADE,
    section_kind text NOT NULL,
    heading text NOT NULL,
    source_span_id text NOT NULL,
    page_start integer,
    page_end integer,
    text text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, section_kind, source_span_id)
);

CREATE INDEX bill_official_documents_bill_idx
    ON bill_official_documents (bill_id, created_at DESC);
