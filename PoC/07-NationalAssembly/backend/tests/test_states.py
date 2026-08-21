from __future__ import annotations

import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.domain.states import AuthorityStatus, LifecycleStatus, ReconciliationStatus


class StateModelTests(unittest.TestCase):
    def test_lifecycle_and_authority_are_independent(self):
        self.assertEqual(LifecycleStatus.LIVE.value, "LIVE")
        self.assertEqual(AuthorityStatus.LIVE.value, "LIVE")
        self.assertNotEqual(set(LifecycleStatus), set(AuthorityStatus))

    def test_authority_status_has_only_evidence_states(self):
        self.assertEqual(
            [item.value for item in AuthorityStatus],
            ["LIVE", "PROVISIONAL", "OFFICIAL"],
        )

    def test_uncertain_reconciliation_is_preserved(self):
        self.assertIn(ReconciliationStatus.UNRESOLVED, ReconciliationStatus)
        self.assertIn(ReconciliationStatus.CONFLICT, ReconciliationStatus)


if __name__ == "__main__":
    unittest.main()
