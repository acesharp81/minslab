-- Derived AI structure; immutable source briefs and official integrations stay intact.
CREATE TABLE meeting_topic_structures (
    id uuid PRIMARY KEY,
    meeting_brief_id uuid NOT NULL REFERENCES meeting_briefs(id),
    source_hash text NOT NULL,
    version text NOT NULL,
    status text NOT NULL CHECK (status IN ('PROCESSING','READY','FAILED')),
    source_snapshot jsonb NOT NULL,
    result jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(meeting_brief_id, source_hash, version)
);
CREATE TABLE meeting_topic_structure_batches (
    id uuid PRIMARY KEY,
    structure_id uuid NOT NULL REFERENCES meeting_topic_structures(id),
    batch_index integer NOT NULL,
    attempt integer NOT NULL,
    status text NOT NULL CHECK (status IN ('READY','FAILED')),
    request_snapshot jsonb NOT NULL,
    response jsonb NOT NULL DEFAULT '{}'::jsonb,
    usage_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(structure_id, batch_index, attempt)
);
