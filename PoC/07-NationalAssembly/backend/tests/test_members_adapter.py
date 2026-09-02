from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from app.adapters.national_assembly.base import SourcePayload
from app.adapters.national_assembly.members import MemberAdapter, value_for_term


class MemberAdapterTests(unittest.TestCase):
    def test_member_contract_parses_without_network_and_aligns_term_values(self):
        body = {
            "ALLNAMEMBER": [
                {"head": [
                    {"list_total_count": 1},
                    {"RESULT": {"CODE": "INFO-000", "MESSAGE": "정상"}},
                ]},
                {"row": [{
                    "NAAS_CD": "MEMBER-1",
                    "NAAS_NM": "홍길동",
                    "PLPT_NM": "이전정당/현재정당",
                    "GTELT_ERACO": "제21대, 제22대",
                    "ELECD_DIV_NM": "지역구/비례대표",
                    "NTR_DIV": "여",
                    "DTY_NM": "위원",
                    "CMIT_NM": "행정안전위원회",
                }]},
            ],
        }
        payload = SourcePayload(
            source_key="members",
            content=json.dumps(body, ensure_ascii=False).encode(),
            content_type="application/json",
            retrieved_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
            source_url="https://example.invalid",
            http_status=200,
        )
        records, total = MemberAdapter().parse(payload)
        self.assertEqual(1, total)
        self.assertEqual("홍길동", records[0].name)
        self.assertEqual(
            "현재정당",
            value_for_term(records[0].parties, records[0].elected_terms, "제22대"),
        )
        self.assertEqual(
            "비례대표",
            value_for_term(
                records[0].election_types, records[0].elected_terms, "제22대",
            ),
        )


if __name__ == "__main__":
    unittest.main()
