from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from master_press.magazine import MagazinePublisher, edition_window
from master_press.storage import KST, Store

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
        self.assertEqual(edition_window("morning", datetime(2026, 7, 30, 8, tzinfo=KST))[1], "2026-07-29T18:00:00+09:00")
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

        editions = publisher.editions(organization["id"])

        self.assertEqual([item["edition_date"] for item in editions], ["2026-07-30"] * 4 + ["2026-07-29"])
