from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest import mock
from uuid import uuid4

from app.main import policy_ontology


class PolicyOntologyApiTests(unittest.TestCase):
    def test_current_official_report_and_draft_are_counted_separately(self):
        official_broadcast, draft_broadcast = uuid4(), uuid4()
        official_brief, draft_brief, current_document = uuid4(), uuid4(), uuid4()
        items = [
            {"brief_id": official_brief, "broadcast_id": official_broadcast,
             "brief": {"topics": [{"id": "draft-one", "title": "검토 보류"}]}},
            {"brief_id": draft_brief, "broadcast_id": draft_broadcast,
             "brief": {"topics": [{"id": "housing", "title": "주택 공급 확대"}]}},
        ]
        integration = {
            "meeting_brief_id": official_brief,
            "official_document_id": current_document,
            "status": "READY",
            "integrated_brief": {"topics": [{"id": "energy", "title": "재생에너지 확대"}]},
        }

        @contextmanager
        def fake_connect(_url):
            yield object()

        with mock.patch("app.main.connect", fake_connect), \
             mock.patch("app.main.get_settings") as settings, \
             mock.patch("app.main.MeetingBriefRepository") as briefs, \
             mock.patch("app.main.LiveRepository") as live, \
             mock.patch("app.main.OfficialIntegrationRepository") as integrations:
            settings.return_value.database_url = "unused"
            briefs.return_value.latest_all.return_value = items
            live.return_value.broadcast_official_context.side_effect = [
                {"official_document_id": current_document}, None,
            ]
            integrations.return_value.latest_for_brief_document.return_value = integration
            response = policy_ontology()
        metrics = response["metrics"]
        self.assertEqual(response["source_status"], "CURRENT_OFFICIAL_WHEN_AVAILABLE")
        self.assertEqual(response["additional_llm_calls"], 0)
        self.assertEqual(metrics["report_count"], 2)
        self.assertEqual(metrics["official_report_count"], 1)
        self.assertEqual(metrics["provisional_report_count"], 1)
        self.assertEqual(metrics["ontology_topic_count"], 2)
        self.assertEqual(metrics["integrity_failure_count"], 0)
        integrations.return_value.latest_for_brief_document.assert_called_once_with(
            official_brief, current_document,
        )


if __name__ == "__main__":
    unittest.main()
