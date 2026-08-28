CREATE TEMP TABLE runtime_demo_broadcasts ON COMMIT DROP AS
SELECT id
FROM live_broadcasts
WHERE source_system = 'poc07.demo';

CREATE TEMP TABLE runtime_demo_segments ON COMMIT DROP AS
SELECT id
FROM transcript_segments
WHERE broadcast_id IN (SELECT id FROM runtime_demo_broadcasts);

CREATE TEMP TABLE runtime_demo_revisions ON COMMIT DROP AS
SELECT id
FROM transcript_segment_revisions
WHERE segment_id IN (SELECT id FROM runtime_demo_segments);

CREATE TEMP TABLE runtime_demo_reviews ON COMMIT DROP AS
SELECT id
FROM broadcast_reviews
WHERE broadcast_id IN (SELECT id FROM runtime_demo_broadcasts);

CREATE TEMP TABLE runtime_demo_review_topics ON COMMIT DROP AS
SELECT id
FROM broadcast_review_topics
WHERE review_id IN (SELECT id FROM runtime_demo_reviews);

CREATE TEMP TABLE runtime_demo_publications ON COMMIT DROP AS
SELECT id
FROM broadcast_official_publications
WHERE broadcast_id IN (SELECT id FROM runtime_demo_broadcasts);

CREATE TEMP TABLE runtime_demo_official_documents ON COMMIT DROP AS
SELECT id
FROM official_transcript_documents
WHERE publication_id IN (SELECT id FROM runtime_demo_publications);

CREATE TEMP TABLE runtime_demo_official_utterances ON COMMIT DROP AS
SELECT id
FROM official_transcript_utterances
WHERE document_id IN (SELECT id FROM runtime_demo_official_documents);

DELETE FROM broadcast_review_evidence
WHERE review_topic_id IN (SELECT id FROM runtime_demo_review_topics)
   OR revision_id IN (SELECT id FROM runtime_demo_revisions);

DELETE FROM transcript_official_reconciliations
WHERE transcript_revision_id IN (SELECT id FROM runtime_demo_revisions)
   OR official_utterance_id IN (SELECT id FROM runtime_demo_official_utterances);

DELETE FROM broadcast_review_topics
WHERE id IN (SELECT id FROM runtime_demo_review_topics);

DELETE FROM broadcast_reviews
WHERE id IN (SELECT id FROM runtime_demo_reviews);

DELETE FROM official_utterance_agenda_links
WHERE utterance_id IN (SELECT id FROM runtime_demo_official_utterances);

DELETE FROM official_utterance_annotations
WHERE utterance_id IN (SELECT id FROM runtime_demo_official_utterances);

DELETE FROM official_transcript_utterances
WHERE id IN (SELECT id FROM runtime_demo_official_utterances);

DELETE FROM official_transcript_documents
WHERE id IN (SELECT id FROM runtime_demo_official_documents);

DELETE FROM broadcast_official_publications
WHERE id IN (SELECT id FROM runtime_demo_publications);

DELETE FROM meeting_brief_failures
WHERE broadcast_id IN (SELECT id FROM runtime_demo_broadcasts);
DELETE FROM meeting_brief_progress
WHERE broadcast_id IN (SELECT id FROM runtime_demo_broadcasts);
DELETE FROM meeting_briefs
WHERE broadcast_id IN (SELECT id FROM runtime_demo_broadcasts);
DELETE FROM transcript_speaker_overrides
WHERE broadcast_id IN (SELECT id FROM runtime_demo_broadcasts);
DELETE FROM transcript_utterance_summaries
WHERE broadcast_id IN (SELECT id FROM runtime_demo_broadcasts);
DELETE FROM transcript_utterance_summary_failures
WHERE broadcast_id IN (SELECT id FROM runtime_demo_broadcasts);

DELETE FROM transcript_segment_revisions
WHERE id IN (SELECT id FROM runtime_demo_revisions);
DELETE FROM transcript_segments
WHERE id IN (SELECT id FROM runtime_demo_segments);
DELETE FROM live_broadcast_source_versions
WHERE broadcast_id IN (SELECT id FROM runtime_demo_broadcasts);
DELETE FROM live_broadcasts
WHERE id IN (SELECT id FROM runtime_demo_broadcasts);

DELETE FROM source_document_versions
WHERE source_document_id IN (
    SELECT id FROM source_documents WHERE source_system = 'poc07.demo'
);

DELETE FROM source_documents
WHERE source_system = 'poc07.demo';
