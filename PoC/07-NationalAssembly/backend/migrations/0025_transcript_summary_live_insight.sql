ALTER TABLE transcript_utterance_summaries
    ADD COLUMN live_insight jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE transcript_utterance_summaries
    ADD CONSTRAINT transcript_summary_live_insight_object_check
    CHECK (jsonb_typeof(live_insight) = 'object');
