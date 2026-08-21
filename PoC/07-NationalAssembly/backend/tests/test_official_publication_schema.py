from __future__ import annotations

import unittest
from pathlib import Path


MIGRATION = Path(__file__).parents[1] / "migrations" / "0009_broadcast_official_publications.sql"
BODY_MIGRATION = Path(__file__).parents[1] / "migrations" / "0010_official_transcript_bodies.sql"
MEETING_BODY_MIGRATION = Path(__file__).parents[1] / "migrations" / "0011_meeting_official_transcripts.sql"
ANNOTATION_MIGRATION = Path(__file__).parents[1] / "migrations" / "0012_official_utterance_annotations.sql"
EXPLAINABLE_MIGRATION = Path(__file__).parents[1] / "migrations" / "0013_explainable_utterance_annotations.sql"
AGENDA_LINK_MIGRATION = Path(__file__).parents[1] / "migrations" / "0014_official_utterance_agenda_links.sql"


class OfficialPublicationSchemaTests(unittest.TestCase):
    def test_official_link_state_does_not_claim_text_reconciliation(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE broadcast_official_publications", sql)
        self.assertIn("body_contract_status", sql)
        self.assertIn("LINK_ONLY", sql)
        self.assertIn("reconciliation_status", sql)

    def test_official_body_keeps_source_spans_and_separate_reconciliation(self):
        sql = BODY_MIGRATION.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE official_transcript_documents", sql)
        self.assertIn("publication_stage", sql)
        self.assertIn("source_span_id", sql)
        self.assertIn("source_locator jsonb", sql)
        self.assertIn("CREATE TABLE transcript_official_reconciliations", sql)

    def test_official_body_can_exist_before_live_broadcast_link(self):
        sql = MEETING_BODY_MIGRATION.read_text(encoding="utf-8")
        self.assertIn("ADD COLUMN meeting_id", sql)
        self.assertIn("ALTER COLUMN publication_id DROP NOT NULL", sql)
        self.assertIn("official_transcript_documents_meeting_version_uidx", sql)

    def test_derived_labels_are_separate_provisional_annotations(self):
        sql = ANNOTATION_MIGRATION.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE official_utterance_annotations", sql)
        self.assertIn("authority_status = 'PROVISIONAL'", sql)
        self.assertIn("review_status", sql)
        self.assertIn("evidence_text_hash", sql)

    def test_v2_annotations_store_explainable_links_and_utterance_kind(self):
        sql = EXPLAINABLE_MIGRATION.read_text(encoding="utf-8")
        self.assertIn("utterance_kind", sql)
        self.assertIn("evidence_keywords", sql)
        self.assertIn("topic_links jsonb", sql)
        self.assertIn("ministry_links jsonb", sql)

    def test_utterance_agenda_link_requires_explicit_reconciliation(self):
        sql = AGENDA_LINK_MIGRATION.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE official_utterance_agenda_links", sql)
        self.assertIn("reconciliation_status", sql)
        self.assertIn("match_method", sql)
        self.assertIn("match_confidence", sql)


if __name__ == "__main__":
    unittest.main()
