CREATE TABLE bill_official_document_fetches (
    bill_id uuid NOT NULL REFERENCES bills(id),
    bill_version_id uuid NOT NULL REFERENCES bill_versions(id),
    pdf_url text NOT NULL,
    parser_version text NOT NULL,
    status text NOT NULL CHECK (status IN ('SUCCEEDED', 'RETRY_WAIT')),
    attempt_count integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz,
    last_error text,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (bill_id, bill_version_id, pdf_url, parser_version)
);

CREATE INDEX bill_official_document_fetches_retry_idx
    ON bill_official_document_fetches (next_attempt_at)
    WHERE status = 'RETRY_WAIT';

CREATE TABLE official_agenda_reconciliation_state (
    document_id uuid PRIMARY KEY REFERENCES official_transcript_documents(id),
    agenda_count integer NOT NULL DEFAULT 0,
    last_sequence integer NOT NULL DEFAULT 0,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- The previous worker already reconciled the historical corpus on every
-- cycle. Seed only settled documents and agendas; recently changed records
-- will receive one bounded reconciliation from the new worker.
INSERT INTO official_agenda_reconciliation_state (
    document_id, agenda_count, last_sequence, completed_at
)
SELECT document.id, count(agenda.id)::integer, document.utterance_count, now()
FROM official_transcript_documents document
LEFT JOIN agenda_items agenda ON agenda.meeting_id = document.meeting_id
WHERE document.created_at < now() - interval '1 hour'
  AND NOT EXISTS (
      SELECT 1 FROM agenda_items recent
      WHERE recent.meeting_id = document.meeting_id
        AND recent.created_at >= now() - interval '1 hour'
  )
GROUP BY document.id;
