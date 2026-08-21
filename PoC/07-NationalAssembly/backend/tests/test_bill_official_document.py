from __future__ import annotations

import unittest

from app.services.bill_official_document import extract_official_sections


class BillOfficialDocumentTests(unittest.TestCase):
    def test_extracts_proposal_and_main_content_with_page_spans(self):
        pages = [
            "1. 심사경과\n발의 내용\n",
            "2. 제안설명의 요지\n국민의 참정권을 회복하려는 것임.\n",
            "계속되는 제안 설명\n3. 전문위원 검토보고의 요지\n특별검사를 임명하여 수사함.\n4. 대체토론의 요지\n없음",
        ]
        result = extract_official_sections(pages)
        self.assertEqual([item["section_kind"] for item in result], ["PROPOSAL_REASON", "MAIN_CONTENT"])
        self.assertEqual(result[0]["page_start"], 2)
        self.assertEqual(result[0]["page_end"], 3)
        self.assertIn("참정권", result[0]["text"])
        self.assertEqual(result[1]["source_span_id"], "pdf-page-3-main_content")

    def test_does_not_invent_missing_sections(self):
        self.assertEqual(extract_official_sections(["1. 심사경과\n자료 없음"]), [])


if __name__ == "__main__":
    unittest.main()
