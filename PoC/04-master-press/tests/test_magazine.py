from __future__ import annotations

import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from master_press.magazine import MagazinePublisher, edition_window
from master_press.service import MasterPressService
from master_press.storage import KST, Store, now_iso

class MagazineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "magazine.sqlite3")

    def tearDown(self): self.temp.cleanup()

    def test_publish_uses_completed_send_results_and_snapshots_cases(self):
        organization = self.store.save_organization({"name": "행정안전부"})
        case = self.store.save_case({"name": "AI 정책", "organization_id": organization["id"], "topic_description": "AI", "is_active": True})
        article, _ = self.store.upsert_article({"canonical_url": "https://example.com/magazine", "original_url": "https://example.com/magazine", "title": "AI 정책 확대", "publisher": "테스트일보", "published_at": "2026-07-30T09:30:00+09:00", "image_url": "https://example.com/photo.jpg"})
        analysis, _ = self.store.ensure_article_analysis(article, organization["id"])
        evaluation, _ = self.store.create_case_evaluation(analysis["id"], article["id"], case, True)
        with self.store.connect() as connection:
            connection.execute("UPDATE article_analyses SET status='completed',summary='요약',tone='긍정적',article_type='AI·디지털' WHERE id=?", (analysis["id"],))
            connection.execute("UPDATE case_evaluations SET status='completed',decision='send',final_score=91 WHERE id=?", (evaluation["id"],))
        edition = MagazinePublisher(self.store).publish(organization["id"], "2026-07-30", "lunch", "2026-07-30T08:00:00+09:00", "2026-07-30T12:00:00+09:00")
        self.assertEqual(edition["members"][0]["case_matches"][0]["id"], case["id"])
        self.assertEqual(edition["members"][0]["image_url"], "https://example.com/photo.jpg")
        self.assertEqual(edition_window("morning", datetime(2026, 7, 30, 7, tzinfo=KST))[1], "2026-07-29T07:00:00+09:00")
        self.assertEqual(edition_window("daily", datetime(2026, 7, 30, 7, tzinfo=KST))[1], "2026-07-29T07:00:00+09:00")
        self.assertEqual((edition["issue_count"], edition["article_count"]), (1, 1))

    def test_publish_refreshes_issue_group_for_the_edition_window(self):
        organization = self.store.save_organization({"name": "행정안전부"})
        case = self.store.save_case({"name": "AI 정책", "organization_id": organization["id"], "topic_description": "AI", "is_active": True})
        for index, publisher in enumerate(("가일보", "나일보")):
            article, _ = self.store.upsert_article({"canonical_url": f"https://example.com/ai-{index}", "original_url": f"https://example.com/ai-{index}", "title": f"정부 AI 정책 발표 {index + 1}", "snippet": "정부 AI 정책 발표 내용", "publisher": publisher, "published_at": "2026-07-30T09:30:00+09:00"})
            analysis, _ = self.store.ensure_article_analysis(article, organization["id"])
            evaluation, _ = self.store.create_case_evaluation(analysis["id"], article["id"], case, True)
            with self.store.connect() as connection:
                connection.execute("UPDATE article_analyses SET status='completed',summary=?,entities=?,topic_concepts=? WHERE id=?", ("정부 AI 정책 발표", '[\"AI 정책\"]', '[\"AI 정책\"]', analysis["id"]))
                connection.execute("UPDATE case_evaluations SET status='completed',decision='send',final_score=? WHERE id=?", (90 - index, evaluation["id"]))
        solo, _ = self.store.upsert_article({"canonical_url": "https://example.com/solo", "original_url": "https://example.com/solo", "title": "완전히 다른 단독 기사", "publisher": "다일보", "published_at": "2026-07-30T09:30:00+09:00"})
        solo_analysis, _ = self.store.ensure_article_analysis(solo, organization["id"])
        solo_evaluation, _ = self.store.create_case_evaluation(solo_analysis["id"], solo["id"], case, True)
        with self.store.connect() as connection:
            connection.execute("UPDATE article_analyses SET status='completed',summary='단독 기사' WHERE id=?", (solo_analysis["id"],))
            connection.execute("UPDATE case_evaluations SET status='completed',decision='send',final_score=99 WHERE id=?", (solo_evaluation["id"],))
        edition = MagazinePublisher(self.store).publish(organization["id"], "2026-07-30", "lunch", "2026-07-30T08:00:00+09:00", "2026-07-30T12:00:00+09:00")
        self.assertEqual((edition["issue_count"], edition["article_count"]), (2, 3))
        self.assertEqual(edition["members"][0]["issue_key"], edition["members"][1]["issue_key"])
        self.assertNotEqual(edition["members"][0]["article_id"], solo["id"])

    def test_editions_are_ordered_newest_first_within_each_date(self):
        organization = self.store.save_organization({"name": "행정안전부"})
        publisher = MagazinePublisher(self.store)
        for slot in ("evening", "lunch", "morning", "daily"):
            publisher.publish(organization["id"], "2026-07-30", slot, "2026-07-30T00:00:00+09:00", "2026-07-30T01:00:00+09:00")
        publisher.publish(organization["id"], "2026-07-29", "evening", "2026-07-29T00:00:00+09:00", "2026-07-29T01:00:00+09:00")

        editions = publisher.editions(organization["id"], include_legacy=True)

        self.assertEqual([item["edition_date"] for item in editions], ["2026-07-30"] * 4 + ["2026-07-29"])

    def test_recent_three_magazines_are_resent_in_chronological_order(self):
        organization = self.store.save_organization({"name": "행정안전부", "is_active": True})
        case = self.store.save_case({
            "name": "AI 정책", "organization_id": organization["id"],
            "topic_description": "AI", "is_active": True,
        })
        _invite, token = self.store.create_invite("테스트 수신자", 60)
        recipient = self.store.consume_invite(token, {
            "kakao_user_id": "magazine-test-user",
            "access_token_ciphertext": "access",
            "refresh_token_ciphertext": "refresh",
            "access_token_expires_at": now_iso(),
            "refresh_token_expires_at": now_iso(),
            "scopes": ["talk_message"],
        })
        request, _token = self.store.create_signup_request(
            "테스트 수신자", organization["id"], [case["id"]], recipient_id=recipient["id"],
            magazine_slots=["morning", "lunch", "evening"],
        )
        self.store.set_signup_request_subscriptions(
            request["id"], [case["id"]], magazine_slots=["morning", "lunch", "evening"],
        )
        publisher = MagazinePublisher(self.store)
        publisher.publish(organization["id"], "2026-07-30", "morning", "2026-07-29T07:00:00+09:00", "2026-07-30T07:00:00+09:00")
        publisher.publish(organization["id"], "2026-07-30", "lunch", "2026-07-30T07:00:00+09:00", "2026-07-30T12:00:00+09:00")
        publisher.publish(organization["id"], "2026-07-30", "evening", "2026-07-30T12:00:00+09:00", "2026-07-30T18:00:00+09:00")

        service = object.__new__(MasterPressService)
        service.store = self.store
        service.settings = SimpleNamespace(kakao_redirect_uri="https://example.com/callback")
        service.kakao = mock.MagicMock()
        service.kakao.send_to_me.return_value = (200, {})

        result = service.resend_recent_magazines(recipient["id"], 3)

        self.assertEqual(result["sent"], 3)
        self.assertEqual([item["edition_slot"] for item in result["items"]], ["morning", "lunch", "evening"])
        self.assertEqual(service.kakao.send_to_me.call_count, 3)
        for call in service.kakao.send_to_me.call_args_list:
            self.assertNotIn("CaseON", call.args[1])
            self.assertNotIn("CaseON", call.kwargs["title"])
            self.assertNotIn("CaseON", call.kwargs["description"])

    def test_daily_topics_use_repeated_snapshot_headline_phrases(self):
        topics = MagazinePublisher(self.store)._daily_topics([
            {"article_id": "one", "title": "극한 폭염 자택 온열질환자 증가", "original_url": "https://example.com/one", "score": 90, "image_url": ""},
            {"article_id": "two", "title": "극한 폭염 자택 온열질환자 주의", "original_url": "https://example.com/two", "score": 80, "image_url": ""},
            {"article_id": "three", "title": "별도 정책 기사", "original_url": "https://example.com/three", "score": 70, "image_url": ""},
        ])
        self.assertIn(topics[0]["label"], "극한 폭염 자택 온열질환자 증가")
        self.assertEqual(topics[0]["value"], 2)
        self.assertEqual(topics[0]["article_url"], "https://example.com/one")

    def test_publish_groups_highly_similar_embeddings_without_metadata(self):
        organization = self.store.save_organization({"name": "행정안전부"})
        case = self.store.save_case({"name": "AI 정책", "organization_id": organization["id"], "topic_description": "AI", "is_active": True})
        self.store.set_setting("magazine_similarity_threshold", "90")
        for index, vector in enumerate(([1.0, 0.0], [0.95, 0.312])):
            article, _ = self.store.upsert_article({"canonical_url": f"https://example.com/similar-{index}", "original_url": f"https://example.com/similar-{index}", "title": f"원주시 AI 공모전 기사 {index}", "publisher": "테스트일보", "published_at": "2026-07-30T09:30:00+09:00"})
            analysis, _ = self.store.ensure_article_analysis(article, organization["id"])
            evaluation, _ = self.store.create_case_evaluation(analysis["id"], article["id"], case, True)
            with self.store.connect() as connection:
                connection.execute("UPDATE article_analyses SET status='completed',summary=?,entities='[]',topic_concepts='[]' WHERE id=?", ("원주시 공공데이터 AI 공모전", analysis["id"]))
                connection.execute("UPDATE case_evaluations SET status='completed',decision='send',final_score=? WHERE id=?", (90 - index, evaluation["id"]))
            self.store.save_article_embedding(analysis["id"], "test", vector)
        solo, _ = self.store.upsert_article({"canonical_url": "https://example.com/other-ai", "original_url": "https://example.com/other-ai", "title": "화성시 AI 이번 도시 데이터 사업", "publisher": "테스트일보", "published_at": "2026-07-30T09:30:00+09:00"})
        solo_analysis, _ = self.store.ensure_article_analysis(solo, organization["id"])
        solo_evaluation, _ = self.store.create_case_evaluation(solo_analysis["id"], solo["id"], case, True)
        with self.store.connect() as connection:
            connection.execute("UPDATE article_analyses SET status='completed',summary='화성시 AI 이번 도시 데이터 사업',entities='[]',topic_concepts='[]' WHERE id=?", (solo_analysis["id"],))
            connection.execute("UPDATE case_evaluations SET status='completed',decision='send',final_score=88 WHERE id=?", (solo_evaluation["id"],))
        self.store.save_article_embedding(solo_analysis["id"], "test", [0.96, 0.28])
        edition = MagazinePublisher(self.store).publish(organization["id"], "2026-07-30", "lunch", "2026-07-30T08:00:00+09:00", "2026-07-30T12:00:00+09:00")
        self.assertEqual(edition["issue_count"], 2)
        self.assertEqual(edition["members"][0]["issue_key"], edition["members"][1]["issue_key"])
        self.assertNotEqual(edition["members"][0]["issue_key"], edition["members"][2]["issue_key"])
