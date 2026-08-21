from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from app.adapters.national_assembly.base import SourcePayload
from app.ingestion.executive_briefings import (
    parse_detail, parse_list, parse_president_detail, parse_president_list,
)


class ExecutiveBriefingTests(unittest.TestCase):
    def test_parses_only_official_state_council_links(self):
        html = b"""
        <ul><li><a onclick="goView('/briefing/stateCouncilView.do?newsId=123','')">
        <strong>\xec\xa0\x9c35\xed\x9a\x8c \xea\xb5\xad\xeb\xac\xb4\xed\x9a\x8c\xec\x9d\x98 \xeb\xb8\x8c\xeb\xa6\xac\xed\x95\x91</strong></a>
        <span class="source"><span>2026.08.11</span></span></li></ul>
        """
        items = parse_list(html)
        self.assertEqual(items[0]["news_id"], "123")
        self.assertEqual(items[0]["published_date"], "2026.08.11")

    def test_extracts_explicit_agenda_and_ministry_evidence(self):
        body = """
        <div class="article_body"><div class="view_cont">
        <p>&lt;물가안정에 관한 법률 시행령 일부개정령안&gt;, 매점매석 단속 권한을 정비합니다.
        【소관 : 재정경제부 물가정책과 044-215-2831】</p>
        </div></div>
        """.encode()
        payload = SourcePayload(
            "executive_state_council_detail", body, "text/html",
            datetime.now(timezone.utc), "https://www.korea.kr/briefing/stateCouncilView.do?newsId=123", 200,
        )
        item = {"news_id": "123", "title": "제35회 국무회의 브리핑", "published_date": "2026.08.11", "source_url": payload.source_url}
        result = parse_detail(item, payload, "a" * 64)
        self.assertEqual(result["meeting_number"], 35)
        self.assertEqual(result["agendas"][0]["ministries"], ["재정경제부"])
        self.assertEqual(result["agendas"][0]["authority_status"], "OFFICIAL")

    def test_presidential_briefing_keeps_official_message_spans(self):
        listing = json.dumps({"data": {"list": [{
            "SUBJECT": "제35회 국무회의 관련 서면 브리핑",
            "WRITE_DATE": "2026.08.11", "BBS_CD": "sample",
        }]}}).encode()
        item = parse_president_list(listing)[0]
        html = """<div class="view_txt ck-content">
        <p>이 대통령은 국민 안전 대책을 빈틈없이 마련해 달라고 지시했습니다.</p>
        <p>일반적인 안건 설명입니다.</p></div>""".encode()
        payload = SourcePayload(
            "president_state_council_detail", html, "text/html",
            datetime.now(timezone.utc), item["source_url"], 200,
        )
        result = parse_president_detail(item, payload, "b" * 64)
        self.assertEqual(result["message_count"], 1)
        self.assertEqual(result["messages"][0]["source_span_id"], "president-paragraph-1")
        self.assertEqual(result["messages"][0]["authority_status"], "OFFICIAL")


if __name__ == "__main__":
    unittest.main()
