from __future__ import annotations

import unittest
from uuid import uuid4

from app.db.meeting_brief_repository import MeetingBriefRepository
from app.services.ontology_sources import select_current_ontology_brief


class OntologySourcesTests(unittest.TestCase):
    def test_report_catalog_excludes_isolated_sources_and_out_of_scope_committees(self):
        from unittest.mock import Mock
        connection = Mock()
        connection.execute.return_value.fetchall.return_value = []
        self.assertEqual(MeetingBriefRepository(connection).latest_all(), [])
        sql, parameters = connection.execute.call_args.args
        self.assertIn("broadcast.source_system NOT IN", sql)
        self.assertIn("'poc07.test'", sql)
        self.assertIn("broadcast.committee_name = ANY(%s)", sql)
        self.assertIn("본회의", parameters[0])
        self.assertIn("법제사법위원회", parameters[0])
        self.assertNotIn("국방위원회", parameters[0])

    def test_only_ready_integration_for_same_brief_and_current_document_is_official(self):
        brief_id, current_document, previous_document = uuid4(), uuid4(), uuid4()
        item = {"brief_id": brief_id, "brief": {"topics": [{"id": "draft"}]}}
        integration = {
            "status": "READY", "meeting_brief_id": brief_id,
            "official_document_id": current_document,
            "integrated_brief": {"topics": [{"id": "official"}]},
        }
        self.assertEqual(
            select_current_ontology_brief(item, integration, current_document)[1],
            "OFFICIAL_INTEGRATED",
        )
        for changes in (
            {"official_document_id": previous_document},
            {"meeting_brief_id": uuid4()},
            {"status": "PROCESSING"},
            {"usage_metadata": {"reuse_reason": "TEMPORARY_UPDATE_DEFERRED"}},
            {"usage_metadata": {"comparison_mode": "SOURCE_ONLY_TIMEOUT"}},
        ):
            selected, source = select_current_ontology_brief(
                item, {**integration, **changes}, current_document,
            )
            self.assertEqual((selected, source), (item["brief"], "PROVISIONAL"))
        self.assertEqual(
            select_current_ontology_brief(item, integration, None)[1],
            "PROVISIONAL",
        )


if __name__ == "__main__":
    unittest.main()
