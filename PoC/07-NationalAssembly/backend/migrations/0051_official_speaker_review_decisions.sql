-- Human-reviewed exceptions are scoped to one draft, official source version,
-- point, and exact LIVE source text. A new version cannot inherit a correction.
CREATE TABLE official_speaker_review_decisions (
    id uuid PRIMARY KEY,
    broadcast_id uuid NOT NULL REFERENCES live_broadcasts(id),
    meeting_brief_id uuid NOT NULL REFERENCES meeting_briefs(id),
    official_document_id uuid NOT NULL REFERENCES official_transcript_documents(id),
    point_id text NOT NULL,
    source_text_hash char(64) NOT NULL,
    official_utterance_id uuid NOT NULL REFERENCES official_transcript_utterances(id),
    replacement_summary text,
    reviewed_by text NOT NULL,
    reason text NOT NULL,
    matcher_version text NOT NULL,
    status text NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'REVOKED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (meeting_brief_id, official_document_id, point_id, source_text_hash)
);

CREATE INDEX official_speaker_review_decisions_document_idx
    ON official_speaker_review_decisions (official_document_id, meeting_brief_id)
    WHERE status = 'ACTIVE';

-- Migrate the previously verified correction without guessing a reviewer.
-- The source hash and official version prevent it from moving to new text.
INSERT INTO official_speaker_review_decisions (
    id, broadcast_id, meeting_brief_id, official_document_id,
    point_id, source_text_hash, official_utterance_id,
    replacement_summary, reviewed_by, reason, matcher_version
)
SELECT 'be8786a8-14c4-4949-9360-f713b74c597e'::uuid,
       brief.broadcast_id, brief.id, document.id,
       'speaker-5-3',
       'c5b6d2139c0d27fe4a216cfd2e32990ed6ca6a21e1465c2ef9ada4c67f920e0f',
       utterance.id,
       '박형수는 증인 협의안을 자신이 먼저 제안했으나 당시 받아들여지지 않았다고 반박했다.',
       'legacy_review_import',
       '기존 원문 대조로 확인된 증인 협의안 발언 보정 이관',
       'REVIEWED_OFFICIAL_SOURCE_V2'
FROM meeting_briefs brief
JOIN official_transcript_documents document
  ON document.id = 'd3ec609c-d73a-4cfa-b992-6c1608c73df7'::uuid
JOIN official_transcript_utterances utterance
  ON utterance.id = 'c2d070a0-2721-4fb1-8ff8-00d44d34e13f'::uuid
 AND utterance.document_id = document.id
WHERE brief.id = 'a42b73d1-af02-44ab-9907-03ee773a5ca5'::uuid
  AND brief.broadcast_id = '205bacd6-10ed-46bc-b4d6-8be4293fcab1'::uuid
ON CONFLICT DO NOTHING;
