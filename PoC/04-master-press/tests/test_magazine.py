from __future__ import annotations

import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from master_press.magazine import MagazinePublisher, edition_window
from master_press.service import MasterPressService
from master_press.similarity import build_magazine_issue_groups
from master_press.storage import KST, Store, now_iso

class MagazineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "magazine.sqlite3")

    def test_magazine_edition_metrics_make_republish_changes_visible(self):
        metrics = MasterPressService.magazine_edition_metrics({
            "generated_at": "2026-08-03T21:53:07+09:00",
            "members": [
                {"article_id": "one", "issue_key": "issue:group"},
                {"article_id": "two", "issue_key": "issue:group"},
                {"article_id": "three", "issue_key": "article:three"},
            ],
        })
        self.assertEqual(metrics, {
            "issue_count": 2,
            "article_count": 3,
            "grouped_issue_count": 1,
            "grouped_article_count": 2,
            "generated_at": "2026-08-03T21:53:07+09:00",
        })

    def test_magazine_orders_by_article_count_then_unique_press_release_count(self):
        def item(article_id, issue_key, score, releases=()):
            return {
                "article_id": article_id, "issue_key": issue_key, "score": score,
                "published_at": "2026-08-04T06:00:00+09:00",
                "related_press_releases": [
                    {"title": title, "url": url} for title, url in releases
                ],
            }

        ordered = MagazinePublisher._order_issue_items([
            item("b1", "issue:b", 80, (("자료 1", "https://press/1"),)),
            item("a1", "issue:a", 70),
            item("c1", "issue:c", 75, (("자료 1", "https://press/1"), ("자료 2", "https://press/2"))),
            item("a2", "issue:a", 90),
            item("b2", "issue:b", 85, (("자료 1 중복", "https://press/1"),)),
            item("a3", "issue:a", 60),
            item("c2", "issue:c", 65, (("자료 3", "https://press/3"),)),
        ])

        self.assertEqual(
            [value["issue_key"] for value in ordered],
            ["issue:a", "issue:a", "issue:a", "issue:c", "issue:c", "issue:b", "issue:b"],
        )
        self.assertEqual([value["article_id"] for value in ordered[:3]], ["a2", "a1", "a3"])

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
        grouped_article_ids = []
        for index, publisher in enumerate(("가일보", "나일보")):
            article, _ = self.store.upsert_article({"canonical_url": f"https://example.com/ai-{index}", "original_url": f"https://example.com/ai-{index}", "title": f"정부 AI 정책 발표 {index + 1}", "snippet": "정부 AI 정책 발표 내용", "publisher": publisher, "published_at": "2026-07-30T09:30:00+09:00"})
            grouped_article_ids.append(article["id"])
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
        self.store.save_article_similarity_groups([
            {"id": article_id, "similar_group_id": grouped_article_ids[0], "similar_group_size": 2,
             "similar_group_basis": "hybrid", "similar_group_status": "finalized", "similar_group_score": 95}
            for article_id in grouped_article_ids
        ] + [{"id": solo["id"], "similar_group_size": 1}])
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

    def test_all_three_magazine_slots_queue_send_and_do_not_duplicate(self):
        organization = self.store.save_organization({"name": "행정안전부", "is_active": True})
        case = self.store.save_case({
            "name": "AI 정책", "organization_id": organization["id"],
            "topic_description": "AI", "is_active": True,
        })
        _invite, token = self.store.create_invite("세 회차 수신자", 60)
        recipient = self.store.consume_invite(token, {
            "kakao_user_id": "all-slot-user",
            "access_token_ciphertext": "access",
            "refresh_token_ciphertext": "refresh",
            "access_token_expires_at": now_iso(),
            "refresh_token_expires_at": now_iso(),
            "scopes": ["talk_message"],
        })
        request, _token = self.store.create_signup_request(
            "세 회차 수신자", organization["id"], [case["id"]], recipient_id=recipient["id"],
            magazine_slots=["morning", "lunch", "evening"],
        )
        self.store.set_signup_request_subscriptions(
            request["id"], [case["id"]], magazine_slots=["morning", "lunch", "evening"],
        )
        service = object.__new__(MasterPressService)
        service.store = self.store
        service.settings = SimpleNamespace(kakao_redirect_uri="https://example.com/callback")
        service.kakao = mock.MagicMock()
        service.kakao.send_to_me.return_value = (200, {})
        reference = datetime(2026, 7, 30, 18, 6, tzinfo=KST)

        first = [service.publish_magazine_slot(slot, reference=reference) for slot in ("morning", "lunch", "evening")]
        second = [service.publish_magazine_slot(slot, reference=reference) for slot in ("morning", "lunch", "evening")]

        self.assertEqual([item["queued"] for item in first], [1, 1, 1])
        self.assertEqual([item["delivery"]["sent"] for item in first], [1, 1, 1])
        self.assertEqual([item["queued"] for item in second], [0, 0, 0])
        self.assertEqual([item["delivery"]["sent"] for item in second], [0, 0, 0])
        self.assertEqual(service.kakao.send_to_me.call_count, 3)
        with self.store.connect() as connection:
            deliveries = connection.execute(
                """SELECT e.edition_slot,d.status,d.attempts FROM magazine_deliveries d
                   JOIN magazine_editions e ON e.id=d.edition_id ORDER BY e.window_end_at"""
            ).fetchall()
        self.assertEqual(
            [(row["edition_slot"], row["status"], row["attempts"]) for row in deliveries],
            [("morning", "sent", 1), ("lunch", "sent", 1), ("evening", "sent", 1)],
        )

    def test_scheduled_slot_path_also_waits_for_completion_grace(self):
        organization = self.store.save_organization({"name": "행정안전부", "is_active": True})
        service = object.__new__(MasterPressService)
        service.store = self.store
        service.settings = SimpleNamespace(kakao_redirect_uri="https://example.com/callback")
        service.kakao = mock.MagicMock()

        result = service.publish_magazine_slot("evening", reference=datetime(2026, 7, 30, 18, tzinfo=KST))

        self.assertEqual(result["published"], 0)
        self.assertEqual(result["queued"], 0)
        self.assertEqual(len(result["deferred"]), 1)
        self.assertEqual(result["deferred"][0]["organization_id"], organization["id"])
        self.assertEqual(result["deferred"][0]["reason"], "completion_grace")

    def test_due_magazine_waits_for_complete_article_bundle(self):
        organization = self.store.save_organization({"name": "행정안전부", "is_active": True})
        case = self.store.save_case({"name": "정책", "organization_id": organization["id"], "topic_description": "정책", "is_active": True})
        article, _ = self.store.upsert_article({
            "canonical_url": "https://example.com/wait", "original_url": "https://example.com/wait",
            "title": "처리 완료 대기 기사", "published_at": "2026-07-30T06:30:00+09:00",
        })
        analysis, _ = self.store.ensure_article_analysis(article, organization["id"])
        evaluation, _ = self.store.create_case_evaluation(analysis["id"], article["id"], case, True)
        publisher = MagazinePublisher(self.store)
        reference = datetime(2026, 7, 30, 7, 6, tzinfo=KST)
        self.assertEqual(publisher.publish_due(reference), [])
        self.assertEqual(publisher.deferred[0]["reason"], "pipeline_pending")
        self.assertGreater(publisher.deferred[0]["pending_common"], 0)

        with self.store.connect() as connection:
            connection.execute("UPDATE article_analyses SET status='completed',summary='완료' WHERE id=?", (analysis["id"],))
            connection.execute("UPDATE case_evaluations SET status='completed',decision='send',final_score=90 WHERE id=?", (evaluation["id"],))
        self.store.save_article_embedding(analysis["id"], "test", [1.0, 0.0])
        self.store.mark_article_cases_routed(analysis["id"])
        self.store.save_article_similarity_groups([{"id": article["id"], "similar_group_size": 1}])
        editions = publisher.publish_due(reference)
        self.assertEqual(len(editions), 1)
        self.assertEqual(editions[0]["article_count"], 1)

    def test_requeue_magazine_delivery_resets_sent_row(self):
        organization = self.store.save_organization({"name": "행정안전부", "is_active": True})
        case = self.store.save_case({"name": "정책", "organization_id": organization["id"], "topic_description": "정책", "is_active": True})
        _invite, token = self.store.create_invite("재발송 수신자", 60)
        recipient = self.store.consume_invite(token, {"kakao_user_id": "resend-user", "access_token_ciphertext": "a", "refresh_token_ciphertext": "r", "access_token_expires_at": now_iso(), "refresh_token_expires_at": now_iso(), "scopes": ["talk_message"]})
        request, _ = self.store.create_signup_request("재발송 수신자", organization["id"], [case["id"]], recipient_id=recipient["id"], magazine_slots=["morning"])
        self.store.set_signup_request_subscriptions(request["id"], [case["id"]], magazine_slots=["morning"])
        edition = MagazinePublisher(self.store).publish(organization["id"], "2026-07-30", "morning", "2026-07-29T07:00:00+09:00", "2026-07-30T07:00:00+09:00")
        self.assertEqual(self.store.queue_magazine_deliveries(edition), 1)
        with self.store.connect() as connection:
            delivery_id = connection.execute("SELECT id FROM magazine_deliveries WHERE edition_id=?", (edition["id"],)).fetchone()["id"]
        self.store.finish_magazine_delivery(delivery_id, True, 200)
        self.assertEqual(self.store.requeue_magazine_deliveries(edition), 1)
        with self.store.connect() as connection:
            row = connection.execute("SELECT status,attempts,sent_at FROM magazine_deliveries WHERE id=?", (delivery_id,)).fetchone()
        self.assertEqual((row["status"], row["attempts"], row["sent_at"]), ("pending", 0, None))

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
        reference = datetime.now(KST)
        published_at = (reference - timedelta(minutes=30)).isoformat(timespec="seconds")
        for index, vector in enumerate(([1.0, 0.0], [0.95, 0.312])):
            article, _ = self.store.upsert_article({"canonical_url": f"https://example.com/similar-{index}", "original_url": f"https://example.com/similar-{index}", "title": f"원주시 AI 공모전 기사 {index}", "publisher": "테스트일보", "published_at": published_at})
            analysis, _ = self.store.ensure_article_analysis(article, organization["id"])
            evaluation, _ = self.store.create_case_evaluation(analysis["id"], article["id"], case, True)
            with self.store.connect() as connection:
                connection.execute("UPDATE article_analyses SET status='completed',summary=?,entities='[]',topic_concepts='[]' WHERE id=?", ("원주시 공공데이터 AI 공모전", analysis["id"]))
                connection.execute("UPDATE case_evaluations SET status='completed',decision='send',final_score=? WHERE id=?", (90 - index, evaluation["id"]))
            self.store.save_article_embedding(analysis["id"], "test", vector)
        solo, _ = self.store.upsert_article({"canonical_url": "https://example.com/other-ai", "original_url": "https://example.com/other-ai", "title": "화성시 AI 이번 도시 데이터 사업", "publisher": "테스트일보", "published_at": published_at})
        solo_analysis, _ = self.store.ensure_article_analysis(solo, organization["id"])
        solo_evaluation, _ = self.store.create_case_evaluation(solo_analysis["id"], solo["id"], case, True)
        with self.store.connect() as connection:
            connection.execute("UPDATE article_analyses SET status='completed',summary='화성시 AI 이번 도시 데이터 사업',entities='[]',topic_concepts='[]' WHERE id=?", (solo_analysis["id"],))
            connection.execute("UPDATE case_evaluations SET status='completed',decision='send',final_score=88 WHERE id=?", (solo_evaluation["id"],))
        self.store.save_article_embedding(solo_analysis["id"], "test", [0.96, 0.28])
        self.store.rebuild_article_similarity_groups()
        edition = MagazinePublisher(self.store).publish(
            organization["id"], reference.date().isoformat(), "lunch",
            (reference - timedelta(hours=1)).isoformat(timespec="seconds"),
            (reference + timedelta(hours=1)).isoformat(timespec="seconds"),
        )
        self.assertEqual(edition["issue_count"], 2)
        self.assertEqual(edition["members"][0]["issue_key"], edition["members"][1]["issue_key"])
        self.assertNotEqual(edition["members"][0]["issue_key"], edition["members"][2]["issue_key"])

    def test_magazine_uses_shared_snapshot_as_evidence_not_authority(self):
        organization = self.store.save_organization({"name": "행정안전부"})
        items = [
            {"article_id": "one", "title": "햇빛소득마을 확대", "summary": "태양광", "published_at": "2026-08-03T10:00:00+09:00"},
            {"article_id": "two", "title": "총리 폭염 대응 긴급지시", "summary": "전국 폭염", "published_at": "2026-08-03T10:10:00+09:00"},
        ]
        groups = {article_id: {"group_id": "one", "size": 2, "score": 100} for article_id in ("one", "two")}
        with mock.patch.object(self.store, "article_similarity_groups", return_value=groups) as snapshot_reader:
            result = MagazinePublisher(self.store)._finalize_issue_keys(items, organization["id"])
        snapshot_reader.assert_called_once()
        self.assertNotEqual(result[0]["issue_key"], result[1]["issue_key"])

    def test_magazine_groups_miryang_field_visit_and_rejects_topic_only_articles(self):
        vector = [1.0, 0.05, 0.02]
        visit_titles = [
            "밀양시, 가뭄·폭염 대응 총력…행안부와 현장점검 실시",
            "박상웅 의원, 행안부 장관과 밀양 폭염·가뭄 대응 현장 점검",
            "윤호중 행안부·송미령 농식품부 장관, 잇따라 밀양 찾아 가뭄·폭염 점검",
            "윤호중 행정안전부 장관, 밀양 가뭄 현장 점검",
        ]
        articles = [
            {
                "id": f"visit-{index}", "title": title, "summary": title,
                "entities": ["밀양시", "윤호중"], "topic_concepts": ["폭염 대응"],
                "semantic_vector": vector,
            }
            for index, title in enumerate(visit_titles)
        ]
        articles.extend([
            {
                "id": "festival",
                "title": "'가뭄 극심' 밀양서 열리는 물놀이 페스티벌, 강행해도 될까요?",
                "summary": "밀양 가뭄과 물놀이 축제 논란", "entities": ["밀양시"],
                "topic_concepts": ["폭염 대응"], "semantic_vector": vector,
            },
            {
                "id": "order",
                "title": "한 총리, 폭염 대응 긴급지시",
                "summary": "전국 쉼터 냉방 상황을 점검하라고 지시했다",
                "entities": ["국무총리"], "topic_concepts": ["폭염 대응"],
                "semantic_vector": vector,
            },
        ])

        groups = build_magazine_issue_groups(articles, threshold=0.70)

        visit_group_ids = {groups[f"visit-{index}"]["group_id"] for index in range(len(visit_titles))}
        self.assertEqual(len(visit_group_ids), 1)
        self.assertEqual(groups["visit-0"]["size"], len(visit_titles))
        self.assertNotIn("festival", groups)
        self.assertNotIn("order", groups)
