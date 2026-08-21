CREATE TABLE bill_versions (
    id uuid PRIMARY KEY,
    bill_id uuid NOT NULL REFERENCES bills(id),
    source_document_version_id uuid NOT NULL REFERENCES source_document_versions(id),
    source_record_key char(64) NOT NULL,
    assembly_term text NOT NULL,
    bill_number text,
    bill_kind text,
    bill_name text NOT NULL,
    proposer_kind text,
    proposer_name text,
    proposal_date date,
    committee_name text,
    committee_process_date date,
    committee_result text,
    plenary_resolution_date date,
    plenary_result text,
    pass_classification text,
    process_stage_code text,
    official_url text,
    authority_status text NOT NULL CHECK (authority_status IN ('LIVE', 'PROVISIONAL', 'OFFICIAL')),
    official_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (bill_id, source_document_version_id, source_record_key)
);

CREATE INDEX bill_versions_bill_idx ON bill_versions (bill_id, created_at DESC);
CREATE INDEX bill_versions_committee_stage_idx ON bill_versions (committee_name, process_stage_code);
CREATE INDEX bill_versions_name_lower_idx ON bill_versions (lower(bill_name));
