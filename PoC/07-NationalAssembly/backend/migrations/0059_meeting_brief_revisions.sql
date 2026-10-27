-- Preserve prior AI projections before automatic finalization/enrichment.
CREATE TABLE IF NOT EXISTS meeting_brief_revisions (
    id bigserial PRIMARY KEY,
    meeting_brief_id uuid NOT NULL REFERENCES meeting_briefs(id),
    brief jsonb NOT NULL,
    reason text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS meeting_brief_revisions_source ON meeting_brief_revisions(meeting_brief_id, id);
