from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from master_press.collectors import canonicalize_url, quick_candidate_match
from master_press.kakao import TokenCipher
from master_press.scoring import keyword_relevance
from master_press.service import MasterPressService, delivery_at, next_collection_at
from master_press.storage import KST, Store


def case_payload(index: int = 1) -> dict:
    return {
        "name": f"케이스 {index}",
        "topic_description": "인공지능 행정 서비스 정책",
        "include_terms": ["인공지능", "행정"],
        "required_terms": [],
        "exclude_terms": ["광고"],
        "urgent_terms": ["긴급"],
        "synonym_terms": {},
        "include_publishers": [],
        "exclude_publishers": [],
        "rss_urls": [],
        "collection_mode": "interval",
        "collection_interval_minutes": 10,
        "collection_times": [],
        "delivery_mode": "immediate",
        "delivery_times": [],
        "relevance_threshold": 75,
        "hold_threshold": 55,
        "keyword_weight": 0.3,
        "semantic_weight": 0.4,
        "llm_weight": 0.3,
        "max_articles_per_message": 2,
        "is_active": True,
    }


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "test.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def test_case_limit_and_versions(self):
        first = self.store.save_case(case_payload(1))
        self.assertEqual(first["version"], 1)
        updated = self.store.save_case({**case_payload(1), "name": "수정"}, first["id"])
        self.assertEqual(updated["version"], 2)
        self.assertEqual(updated["name"], "수정")
        for index in range(2, 6):
            self.store.save_case(case_payload(index))
        with self.assertRaisesRegex(ValueError, "최대 5개"):
            self.store.save_case(case_payload(6))

    def test_article_score_dashboard(self):
        case = self.store.save_case(case_payload())
        article, created = self.store.upsert_article({
            "canonical_url": "https://example.com/news/1",
            "original_url": "https://example.com/news/1",
            "title": "인공지능 행정 서비스 확대",
            "publisher": "example.com",
            "published_at": "2026-07-17T10:00:00+09:00",
            "snippet": "정부가 인공지능 행정 서비스를 확대한다.",
            "source_type": "test",
        })
        self.assertTrue(created)
        score = self.store.save_score(article["id"], case["id"], 1, {
            "keyword_score": 90, "semantic_score": 80, "llm_score": 85, "final_score": 84,
            "summary": "행정 서비스 확대 기사", "reasons": ["관련"], "matched_terms": ["인공지능"],
            "low_score_categories": [], "decision": "send",
        })
        self.assertEqual(score["decision"], "send")
        dashboard = self.store.dashboard(case["id"])
        self.assertEqual(dashboard["stats"]["total"], 1)
        self.assertEqual(dashboard["articles"][0]["title"], "인공지능 행정 서비스 확대")

    def test_invite_is_one_time(self):
        invite, token = self.store.create_invite("테스트", 60)
        self.assertEqual(self.store.valid_invite(token)["id"], invite["id"])
        self.assertIsNone(self.store.valid_invite("wrong-token"))

    def test_schedule_and_threshold_validation(self):
        invalid_time = {**case_payload(), "collection_mode": "times", "collection_times": ["25:99"]}
        with self.assertRaisesRegex(ValueError, "HH:MM"):
            self.store.save_case(invalid_time)
        reversed_thresholds = {**case_payload(), "relevance_threshold": 50, "hold_threshold": 70}
        with self.assertRaisesRegex(ValueError, "보류 기준"):
            self.store.save_case(reversed_thresholds)


class ScoringTests(unittest.TestCase):
    def test_keyword_score_and_exclusion(self):
        case = case_payload()
        article = {"title": "인공지능 행정 혁신", "snippet": "공공 서비스 개선", "body": "행정 업무에 인공지능을 적용한다."}
        result = keyword_relevance(case, article)
        self.assertGreater(result["score"], 80)
        self.assertIn("인공지능", result["matched_terms"])
        excluded = keyword_relevance(case, {**article, "body": article["body"] + " 광고"})
        self.assertLess(excluded["score"], result["score"])
        self.assertIn("excluded_term", excluded["categories"])

    def test_quick_candidate_filter(self):
        case = case_payload()
        self.assertTrue(quick_candidate_match(case, {"title": "인공지능 정책", "snippet": ""}))
        self.assertFalse(quick_candidate_match(case, {"title": "인공지능 광고", "snippet": ""}))

    def test_url_canonicalization(self):
        value = canonicalize_url("HTTPS://Example.COM/news/1/?utm_source=x&keep=1#section")
        self.assertEqual(value, "https://example.com/news/1?keep=1")


class SchedulingTests(unittest.TestCase):
    def test_interval_and_immediate(self):
        now = datetime(2026, 7, 17, 10, 0, tzinfo=KST)
        case = case_payload()
        self.assertEqual(next_collection_at(case, now), "2026-07-17T10:10:00+09:00")
        self.assertEqual(delivery_at(case, False, now), "2026-07-17T10:00:00+09:00")

    def test_fixed_delivery_rolls_forward(self):
        now = datetime(2026, 7, 17, 19, 0, tzinfo=KST)
        case = {**case_payload(), "delivery_mode": "times", "delivery_times": ["09:00", "18:00"]}
        self.assertEqual(delivery_at(case, False, now), "2026-07-18T09:00:00+09:00")
        self.assertEqual(delivery_at(case, True, now), "2026-07-17T19:00:00+09:00")


class SecurityTests(unittest.TestCase):
    def test_kakao_tokens_are_encrypted_at_rest(self):
        from cryptography.fernet import Fernet

        cipher = TokenCipher(Fernet.generate_key().decode("ascii"))
        plaintext = "sample-access-token"
        encrypted = cipher.encrypt(plaintext)
        self.assertNotEqual(encrypted, plaintext)
        self.assertNotIn(plaintext, encrypted)
        self.assertEqual(cipher.decrypt(encrypted), plaintext)


    def test_kakao_text_respects_200_character_limit(self):
        delivery = {
            "case_name": "매우 긴 케이스 이름" * 10,
            "final_score": 88,
            "title": "긴 뉴스 제목" * 30,
            "summary": "긴 기사 요약" * 50,
        }
        message = MasterPressService.message_text(delivery)
        self.assertLessEqual(len(message), 200)
        self.assertIn("관련도 88%", message)
        self.assertIn("긴 뉴스 제목", message)

    def test_article_link_uses_registered_homepage_origin(self):
        class Config:
            kakao_redirect_uri = "https://www.minslab.kr/poc/master-press/oauth/kakao/callback"

        service = MasterPressService.__new__(MasterPressService)
        service.settings = Config()

if __name__ == "__main__":
    unittest.main()
