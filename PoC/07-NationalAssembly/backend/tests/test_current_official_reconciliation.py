from __future__ import annotations

import unittest
from uuid import uuid4
from unittest.mock import patch

from fastapi import HTTPException

from app.db.live_repository import LiveRepository


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, query, parameters):
        self.calls.append((query, parameters))
        return _Cursor(self.rows)


def _row(revision_id, official_id, name):
    return (
        revision_id, "MATCHED", "CURRENT_METHOD", 0.99, "자막",
        official_id, 1, name, "위원", "공식 발언", {}, "FINAL", "OFFICIAL",
    )


class CurrentOfficialReconciliationTests(unittest.TestCase):
    def test_current_document_and_revision_are_required(self):
        connection = _Connection([])
        repository = LiveRepository(connection)
        broadcast_id = uuid4()
        revision_id = uuid4()
        self.assertEqual(repository.broadcast_reconciliation_details(
            broadcast_id, official_document_id=None,
            revision_ids=[revision_id],
        ), {})
        self.assertEqual(repository.broadcast_reconciliation_details(
            broadcast_id, official_document_id=uuid4(),
            revision_ids=[],
        ), {})
        self.assertEqual(connection.calls, [])

    def test_official_utterance_api_uses_current_document(self):
        from app.main import ended_official_utterances

        broadcast_id, document_id = uuid4(), uuid4()
        page = {"items": [{"speaker_name": "박형수"}], "total": 1,
                "offset": 0, "next_offset": 1, "has_more": False}
        with patch("app.main.connect") as connect, patch(
            "app.main.LiveRepository"
        ) as repository_class:
            repository = repository_class.return_value
            repository.broadcast_official_context.return_value = {
                "official_document_id": document_id,
                "official_authority_status": "OFFICIAL",
                "publication_stage": "FINAL",
            }
            repository.official_utterance_page.return_value = page
            result = ended_official_utterances(broadcast_id, 0, 40, "박형수")
            repository.official_utterance_page.assert_called_once_with(
                document_id, offset=0, limit=40, query="박형수",
            )
            self.assertEqual(result["official_document_id"], document_id)
            self.assertEqual(result["items"], page["items"])
            self.assertTrue(connect.called)
        with self.assertRaises(HTTPException) as error:
            ended_official_utterances(broadcast_id, -1, 40, "")
        self.assertEqual(error.exception.status_code, 422)

    def test_part_match_query_is_current_document_scoped(self):
        broadcast_id, document_id, revision_id = uuid4(), uuid4(), uuid4()
        connection = _Connection([(
            revision_id, 1, "hash", "METHOD", 0.99,
            uuid4(), 2, "박형수", "위원", "원문", {}, "FINAL", "OFFICIAL",
        )])
        result = LiveRepository(connection).broadcast_part_reconciliation_details(
            broadcast_id, official_document_id=document_id,
            revision_ids=[revision_id],
        )
        self.assertEqual(result[revision_id][1]["official_speaker_name"], "박형수")
        query, params = connection.calls[0]
        self.assertIn("part_match.official_document_id = %s", query)
        self.assertIn("part_match.transcript_revision_id = ANY(%s)", query)
        self.assertEqual(params, (broadcast_id, [revision_id], document_id))
        self.assertEqual(LiveRepository(connection).broadcast_part_reconciliation_details(
            broadcast_id, official_document_id=None, revision_ids=[revision_id],
        ), {})
        self.assertEqual(len(connection.calls), 1)

    def test_current_document_query_hides_conflicting_names(self):
        broadcast_id, document_id = uuid4(), uuid4()
        matching_revision, conflicting_revision = uuid4(), uuid4()
        connection = _Connection([
            _row(matching_revision, uuid4(), "박형수"),
            _row(conflicting_revision, uuid4(), "서영교"),
            _row(conflicting_revision, uuid4(), "손인혁"),
        ])
        result = LiveRepository(connection).broadcast_reconciliation_details(
            broadcast_id,
            official_document_id=document_id,
            revision_ids=[matching_revision, conflicting_revision],
        )
        self.assertEqual(result[matching_revision]["official_speaker_name"], "박형수")
        self.assertEqual(result[conflicting_revision]["status"], "CONFLICT")
        self.assertIsNone(result[conflicting_revision]["official_speaker_name"])
        query, parameters = connection.calls[0]
        self.assertIn("utterance.document_id = %s", query)
        self.assertIn("revision.id = ANY(%s)", query)
        self.assertIn("reconciliation.reconciliation_status = 'MATCHED'", query)
        self.assertEqual(parameters, (
            broadcast_id, [matching_revision, conflicting_revision], document_id,
        ))


if __name__ == "__main__":
    unittest.main()
