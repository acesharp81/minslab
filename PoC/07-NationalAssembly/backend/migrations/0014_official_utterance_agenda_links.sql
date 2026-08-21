CREATE TABLE official_utterance_agenda_links (
    id uuid PRIMARY KEY,
    utterance_id uuid NOT NULL REFERENCES official_transcript_utterances(id),
    agenda_item_id uuid NOT NULL REFERENCES agenda_items(id),
    reconciliation_status text NOT NULL
        CHECK (reconciliation_status IN ('MATCHED', 'UNRESOLVED', 'CONFLICT')),
    match_method text NOT NULL,
    match_confidence numeric(4,3) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (utterance_id, agenda_item_id, match_method)
);

CREATE INDEX official_utterance_agenda_links_utterance_idx
    ON official_utterance_agenda_links (utterance_id);
CREATE INDEX official_utterance_agenda_links_agenda_idx
    ON official_utterance_agenda_links (agenda_item_id);
