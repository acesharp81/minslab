from __future__ import annotations

import unittest
import uuid

from app.services.broadcast_review import build_broadcast_review


class BroadcastReviewTests(unittest.TestCase):
    def test_groups_final_quotes_and_keeps_revision_evidence(self):
        first = uuid.UUID("00000000-0000-4000-8000-000000000001")
        second = uuid.UUID("00000000-0000-4000-8000-000000000002")
        result = build_broadcast_review(
            {"committee_name": "법제사법위원회"},
            [
                {"revision_id": first, "cursor": 3, "text": "법률 지원을 점검합니다", "speaker_label": "위원"},
                {"revision_id": second, "cursor": 4, "text": "법무부의 법률구조 집행 상황을 상세히 확인합니다", "speaker_label": "위원장"},
            ],
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["topic"], "법무·사법")
        self.assertEqual(result[0]["major_quote"], "법무부의 법률구조 집행 상황을 상세히 확인합니다")
        self.assertEqual(result[0]["evidence_revision_ids"], [first, second])
        self.assertIn("법무부", result[0]["ministries"])
        self.assertIn("법제사법위원회", result[0]["committees"])

    def test_unknown_text_remains_provisional_other_topic(self):
        revision_id = uuid.UUID("00000000-0000-4000-8000-000000000003")
        result = build_broadcast_review(
            {"committee_name": "행정안전위원회"},
            [{"revision_id": revision_id, "cursor": 5, "text": "개의하겠습니다", "speaker_label": None}],
        )
        self.assertEqual(result[0]["topic"], "기타 정책")
        self.assertEqual(result[0]["ministries"], [])
        self.assertEqual(result[0]["committees"], ["행정안전위원회"])


if __name__ == "__main__":
    unittest.main()
