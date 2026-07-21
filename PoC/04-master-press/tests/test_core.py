from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from master_press.collectors import canonicalize_url, organization_candidate_match, quick_candidate_match
from master_press.article_metadata import publisher_name, reporter_name
from master_press.kakao import TokenCipher
from master_press.press_releases import (
    PressReleaseManager, chunk_markdown, document_fingerprint, html_to_markdown,
    lexical_similarity, parse_mois_date, supported_topic_concepts,
)
from master_press.scoring import OllamaClient, OpenRouterClient, OpenRouterError, RelevanceEngine, keyword_relevance
from master_press.service import MasterPressService, case_candidate_gate, delivery_at, next_collection_at
from master_press.storage import KST, Store, centered_semantic_similarity, inferred_topic_concepts, kst_day_start_iso, now_iso, topic_noun_similarity


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
        "send_relevant_immediately": True,
        "relevance_threshold": 70,
        "hold_threshold": 55,
        "keyword_weight": 0,
        "semantic_weight": 0.25,
        "llm_weight": 0.75,
        "max_articles_per_message": 2,
        "is_active": True,
    }


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "test.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def test_pipeline_error_total_counts_api_failures_not_job_retries(self):
        article, _ = self.store.upsert_article({
            "canonical_url": "https://example.com/api-error",
            "original_url": "https://example.com/api-error",
            "title": "API 오류 집계 테스트",
            "publisher": "example.com",
            "source_type": "test",
        })
        analysis, _ = self.store.ensure_article_analysis(article)
        job_id = self.store.queue_article_analysis(analysis["id"])
        now = now_iso()
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE article_analysis_jobs SET status='completed',attempts=11,finished_at=?,error=NULL WHERE id=?",
                (now, job_id),
            )
            connection.execute(
                "INSERT INTO llm_api_calls(id,provider,stage,model,status,http_status,duration_ms,error,created_at) "
                "VALUES('failed-groq','groq','common','test-model','failed',522,100,'timeout',?)",
                (now,),
            )
        stats = self.store.pipeline_stats()
        self.assertEqual(stats["article_jobs"]["failed_current"], 0)
        self.assertEqual(stats["article_jobs"]["failed_total"], 1)

        reset_after_log = (datetime.now(KST) + timedelta(seconds=1)).isoformat(timespec="seconds")
        self.store.set_setting("pipeline_error_reset_at", reset_after_log)
        self.assertEqual(self.store.pipeline_stats()["article_jobs"]["failed_total"], 0)

    def test_topic_similarity_uses_shared_nouns_only(self):
        frequency = {"충북도": 2, "파크골프장": 2, "경찰": 1}
        related = topic_noun_similarity({"충북도", "파크골프장"}, {"충북도", "파크골프장", "사업"}, frequency, 3)
        unrelated = topic_noun_similarity({"충북도", "파크골프장"}, {"경찰", "수사"}, frequency, 3)
        self.assertGreater(related, 0.16)
        self.assertEqual(unrelated, 0.0)

    def test_abstract_topic_concepts_group_related_events(self):
        self.assertIn("호우·재난 대응", inferred_topic_concepts("집중호우로 중대본을 가동하고 주민 대피를 실시했다"))
        self.assertIn("수사기관 개혁·사법제도", inferred_topic_concepts("광주경찰청 장윤기 사건과 경찰개혁 수사권 논의"))

    def test_centered_semantic_similarity_removes_shared_context(self):
        centroid = [10.0, 10.0, 10.0]
        related = centered_semantic_similarity([11.0, 9.0, 10.0], [12.0, 8.0, 10.0], centroid)
        unrelated = centered_semantic_similarity([11.0, 9.0, 10.0], [9.0, 11.0, 10.0], centroid)
        self.assertGreater(related, 0.9)
        self.assertLess(unrelated, 0)

    def test_case_versions_and_scale(self):
        first = self.store.save_case(case_payload(1))
        self.assertEqual(first["version"], 1)
        updated = self.store.save_case({**case_payload(1), "name": "수정"}, first["id"])
        self.assertEqual(updated["version"], 2)
        self.assertEqual(updated["name"], "수정")
        for index in range(2, 7):
            self.store.save_case(case_payload(index))
        self.assertEqual(len(self.store.list_cases()), 6)

    def test_case_display_order_can_be_reordered_per_organization(self):
        organization = self.store.save_organization({"name": "행정안전부", "is_active": True})
        first = self.store.save_case({**case_payload(1), "name": "첫 번째", "organization_id": organization["id"]})
        second = self.store.save_case({**case_payload(2), "name": "두 번째", "organization_id": organization["id"]})
        third = self.store.save_case({**case_payload(3), "name": "세 번째", "organization_id": organization["id"]})

        self.assertEqual([item["name"] for item in self.store.list_cases_for_organization(organization["id"])], ["첫 번째", "두 번째", "세 번째"])
        reordered = self.store.reorder_cases(organization["id"], [third["id"], first["id"], second["id"]])
        self.assertEqual([item["name"] for item in reordered], ["세 번째", "첫 번째", "두 번째"])
        self.assertEqual([item["name"] for item in self.store.list_cases_for_organization(organization["id"])], ["세 번째", "첫 번째", "두 번째"])
        self.assertEqual([item["name"] for item in self.store.list_cases(active_only=True)], ["세 번째", "첫 번째", "두 번째"])
        self.assertLess(reordered[0]["sort_order"], reordered[1]["sort_order"])

        with self.assertRaisesRegex(ValueError, "전체 케이스"):
            self.store.reorder_cases(organization["id"], [first["id"], second["id"]])

    def test_article_case_processing_flag_blocks_new_case_versions(self):
        case = self.store.save_case(case_payload())
        article, _ = self.store.upsert_article({
            "canonical_url": "https://example.com/flagged", "original_url": "https://example.com/flagged",
            "title": "처리 플래그 기사", "publisher": "example.com", "snippet": "행정안전부 기사", "source_type": "test",
        })
        analysis, created_analysis = self.store.ensure_article_analysis(article)
        self.assertTrue(created_analysis)
        revised_article, _ = self.store.upsert_article({
            **article, "body": "나중에 확보된 전체 본문", "content_hash": "revised-content-hash",
        })
        repeated_analysis, created_revised = self.store.ensure_article_analysis(revised_article)
        self.assertFalse(created_revised)
        self.assertEqual(repeated_analysis["id"], analysis["id"])
        first, created = self.store.create_case_evaluation(analysis["id"], article["id"], case, False)
        self.assertTrue(created)
        updated = self.store.save_case({**case_payload(), "name": "수정된 케이스"}, case["id"])
        repeated, created_again = self.store.create_case_evaluation(analysis["id"], article["id"], updated, False)
        self.assertFalse(created_again)
        self.assertEqual(repeated["id"], first["id"])
        with self.store.connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) value FROM case_evaluations WHERE article_analysis_id=? AND case_id=?",
                (analysis["id"], case["id"]),
            ).fetchone()["value"]
            flag = connection.execute(
                "SELECT * FROM article_case_processing_flags WHERE article_id=? AND case_id=?",
                (article["id"], case["id"]),
            ).fetchone()
        self.assertEqual(count, 1)
        with self.store.connect() as connection:
            common_count = connection.execute(
                "SELECT COUNT(*) value FROM article_analyses WHERE article_id=?", (article["id"],)
            ).fetchone()["value"]
        self.assertEqual(common_count, 1)
        self.assertEqual(flag["case_evaluation_completed"], 1)
        self.assertEqual(flag["delivery_classified"], 1)

    def test_dashboard_collapses_legacy_duplicate_analysis_rows(self):
        case = self.store.save_case(case_payload())
        article, _ = self.store.upsert_article({
            "canonical_url": "https://example.com/legacy-duplicate", "original_url": "https://example.com/legacy-duplicate",
            "title": "중복 표시 방지 기사", "publisher": "example.com", "snippet": "중복", "source_type": "test",
        })
        analysis, _ = self.store.ensure_article_analysis(article)
        first, _ = self.store.create_case_evaluation(analysis["id"], article["id"], case, False)
        later = "2099-01-01T10:00:00+09:00"
        with self.store.connect() as connection:
            connection.execute(
                """INSERT INTO article_analyses(id,article_id,content_key,status,summary,article_type,tone,classification_tags,analyzed_at,created_at,updated_at)
                   VALUES(?,?,?,'completed','최신 요약','정책·행정','사실전달','[]',?,?,?)""",
                ("analysis-new", article["id"], "new-content", later, later, later),
            )
            connection.execute(
                """INSERT INTO case_evaluations(id,article_analysis_id,article_id,case_id,case_version,candidate_status,status,decision,completed_at,created_at,updated_at)
                   VALUES(?,?,?,?,?,'candidate','completed','low',?,?,?)""",
                ("evaluation-new", "analysis-new", article["id"], case["id"], case["version"] + 1, later, later, later),
            )
            self.store._sync_article_processing_flags(connection)
        dashboard = self.store.pipeline_dashboard(case_id=case["id"])
        self.assertEqual(len(dashboard["articles"]), 1)
        self.assertEqual(len(dashboard["articles"][0]["case_results"]), 1)
        self.assertEqual(dashboard["articles"][0]["analysis_id"], "analysis-new")
        self.assertEqual(dashboard["articles"][0]["case_results"][0]["evaluation_id"], "evaluation-new")
        self.assertNotEqual(first["id"], "evaluation-new")

    def test_kst_daily_counter_starts_at_midnight(self):
        start = kst_day_start_iso()
        self.assertTrue(start.endswith("T00:00:00+09:00"))
        usage = self.store.openrouter_usage_today()
        self.assertEqual(usage["period"], "KST day")
        self.assertEqual(usage["day_start"], start)

    def test_openrouter_daily_limit_counts_failed_api_calls_and_defers(self):
        settings = SimpleNamespace(openrouter_api_key="test-key", openrouter_daily_soft_limit=3)
        for index in range(3):
            self.store.record_llm_api_call(
                "openrouter", "case", "test-model", "failed", 10,
                http_status=429, error=f"rate-{index}",
            )
        usage = self.store.openrouter_usage_today(3)
        self.assertEqual(usage["attempts"], 3)
        self.assertEqual(usage["failed"], 3)
        self.assertEqual(usage["remaining"], 0)

        client = OpenRouterClient(settings, self.store)
        with self.assertRaises(OpenRouterError) as captured:
            client.request("/chat/completions", {"model": "test-model", "messages": []})
        self.assertEqual(str(captured.exception), "openrouter_daily_soft_limit")
        self.assertTrue(captured.exception.deferred)
        self.assertTrue(captured.exception.retry_after.endswith("T00:00:00+09:00"))

    def test_article_search_and_published_time_order(self):
        rows = [
            ("older", "이전 기사", "https://yna.co.kr/older", "2026-07-20T09:00:00+09:00", "홍길동"),
            ("newer", "최신 관광 기사", "https://newsis.com/newer", "2026-07-21T09:00:00+09:00", "김민지"),
        ]
        for key, title, url, published_at, reporter in rows:
            article, _ = self.store.upsert_article({
                "canonical_url": url, "original_url": url, "title": title,
                "publisher": url.split("/")[2], "published_at": published_at,
                "body": f"{reporter} 기자가 취재했다.", "source_type": "test",
            })
            analysis, _ = self.store.ensure_article_analysis(article)
            self.store.save_article_analysis(analysis["id"], {
                "summary": title, "publisher_name": publisher_name(article["publisher"], url),
                "reporter_name": reporter, "article_type": "정책·행정", "tone": "사실전달",
                "classification_tags": ["정책·행정", "사실전달"], "entities": [],
                "topic_concepts": [], "evidence": [], "analysis_report": {},
            }, "test-model")

        dashboard = self.store.pipeline_dashboard(limit=10)
        self.assertEqual([item["title"] for item in dashboard["articles"][:2]], ["최신 관광 기사", "이전 기사"])
        self.assertEqual(self.store.pipeline_dashboard(search="홍길동")["articles"][0]["title"], "이전 기사")
        self.assertEqual(self.store.pipeline_dashboard(search="뉴시스")["articles"][0]["title"], "최신 관광 기사")

    def test_press_release_searches_title_department_and_contact_name(self):
        organization = self.store.save_organization({"name": "행정안전부", "is_active": True})
        timestamp = now_iso()
        with self.store.connect() as connection:
            connection.execute(
                """INSERT INTO press_releases(
                       id,organization_id,external_id,canonical_url,title,department,contact_name,
                       markdown_path,content_hash,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "release-target", organization["id"], "1", "https://example.com/release/1",
                    "여름철 재난 대응 강화", "안전정책과", "김담당", "", "hash-1",
                    timestamp, timestamp,
                ),
            )
        manager = PressReleaseManager(
            SimpleNamespace(data_dir=Path(self.temp.name)), self.store, None, None
        )

        for search in ("재난 대응", "안전정책과", "김담당"):
            results = manager.list_releases(organization["id"], search=search)
            self.assertEqual([item["id"] for item in results], ["release-target"])
        self.assertEqual(manager.list_releases(organization["id"], search="없는 검색어"), [])

    def test_article_source_metadata_helpers(self):
        self.assertEqual(publisher_name("yna.co.kr", "https://www.yna.co.kr/view/1"), "연합뉴스")
        self.assertEqual(reporter_name("(서울=연합뉴스) 구정모 기자 = 정책 소식입니다."), "구정모")

    def test_organization_crud_and_case_link(self):
        organization = self.store.save_organization({
            "name": "행정안전부",
            "abbreviations": ["행안부"],
            "former_names": ["행자부"],
            "people": ["윤호중 장관"],
            "exclude_terms": ["동명이인"],
            "domains": ["mois.go.kr"],
            "rss_urls": [],
            "collection_mode": "interval",
            "collection_interval_minutes": 10,
            "collection_times": [],
            "max_search_queries": 8,
            "max_articles_per_run": 50,
            "is_active": True,
        })
        self.assertEqual(organization["abbreviations"], ["행안부"])
        case = self.store.save_case({**case_payload(), "organization_id": organization["id"]})
        self.assertEqual(case["organization_id"], organization["id"])
        self.assertEqual(len(self.store.list_cases_for_organization(organization["id"])), 1)
        with self.assertRaisesRegex(ValueError, "사용 기관"):
            self.store.save_case(case_payload(2))
        self.assertTrue(self.store.archive_organization(organization["id"]))
        self.assertEqual(self.store.list_organizations(), [])

    def test_llm_processing_stats(self):
        case = self.store.save_case(case_payload())
        article, _created = self.store.upsert_article({
            "canonical_url": "https://example.com/news/job",
            "original_url": "https://example.com/news/job",
            "title": "LLM 작업",
            "publisher": "example.com",
            "snippet": "작업 상태 테스트",
            "source_type": "test",
        })
        job_id = self.store.queue_llm_job(article["id"], case["id"], case["version"])
        self.assertEqual(self.store.llm_processing_stats()["pending"], 1)
        self.store.start_llm_job(job_id)
        self.assertEqual(self.store.llm_processing_stats()["processing"], 1)
        self.store.finish_llm_job(job_id, True, 1250)
        stats = self.store.llm_processing_stats()
        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["average_seconds"], 1.25)
        self.assertEqual(stats["total"], 1)


    def test_reset_case_evaluation_requeues_and_preserves_sent_history(self):
        organization = self.store.save_organization({"name": "행정안전부", "is_active": True})
        case = self.store.save_case({**case_payload(), "organization_id": organization["id"], "recipient_ids": []})
        article, _ = self.store.upsert_article({
            "original_url": "https://news.example/reset", "canonical_url": "https://news.example/reset",
            "title": "인공지능 행정 서비스", "publisher": "뉴스", "published_at": now_iso(),
            "snippet": "행정 인공지능 서비스 확대", "body": "인공지능 행정 서비스를 확대한다.",
        })
        analysis, _ = self.store.ensure_article_analysis(article, organization["id"])
        self.store.save_article_analysis(analysis["id"], {
            "summary": "행정 인공지능 서비스 확대", "article_type": "정책·행정", "tone": "사실전달",
            "classification_tags": ["정책·행정"], "entities": [], "topic_concepts": [], "evidence": [], "analysis_report": {},
        }, "common")
        evaluation, _ = self.store.create_case_evaluation(analysis["id"], article["id"], case, True, 0.7, 70)
        self.store.save_case_evaluation(evaluation["id"], {
            "keyword_score": 0, "semantic_raw": 0.7, "semantic_score": 70, "llm_score": 85, "final_score": 81.25,
            "evidence_status": "verified", "reasons": ["관련 있음"], "matched_terms": [], "low_score_categories": [],
            "analysis_report": {"old": True}, "decision": "send",
        }, "case-model")
        self.store.queue_case_evaluation(evaluation["id"] + "-missing")
        _invite, token = self.store.create_invite("테스트", 60)
        recipient = self.store.consume_invite(token, {
            "kakao_user_id": "kakao-reset", "access_token_ciphertext": "access", "refresh_token_ciphertext": "refresh",
            "access_token_expires_at": now_iso(), "refresh_token_expires_at": now_iso(),
        })
        self.store.queue_delivery(article["id"], case["id"], recipient["id"], now_iso())
        delivery = self.store.due_deliveries(1)[0]
        self.store.finish_delivery(delivery["id"], True, 200, "")

        reset, _ = self.store.reset_case_evaluation_for_requeue(analysis["id"], article["id"], case, True, 0.6, 60, "")
        self.assertEqual(reset["status"], "pending")
        self.assertEqual(reset["decision"], "pending")
        self.assertEqual(reset["analysis_report"], {})
        job_id = self.store.queue_case_evaluation(reset["id"], ready_at=now_iso())
        self.assertTrue(job_id)
        with self.store.connect() as connection:
            sent = connection.execute("SELECT COUNT(*) FROM deliveries WHERE article_id=? AND case_id=? AND status='sent'", (article["id"], case["id"])).fetchone()[0]
            pending = connection.execute("SELECT COUNT(*) FROM case_evaluation_jobs WHERE case_evaluation_id=? AND status='pending'", (reset["id"],)).fetchone()[0]
        self.assertEqual(sent, 1)
        self.assertEqual(pending, 1)

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
            "article_type": "정책·행정", "classification_tags": ["정책·행정", "AI·디지털"],
            "evidence_status": "verified", "low_score_categories": [], "decision": "send",
        })
        self.assertEqual(score["decision"], "send")
        dashboard = self.store.dashboard(case["id"])
        self.assertEqual(dashboard["stats"]["total"], 1)
        self.assertEqual(dashboard["articles"][0]["classification_tags"], ["정책·행정", "AI·디지털"])
        self.assertEqual(dashboard["articles"][0]["evidence_status"], "verified")
        self.assertEqual(dashboard["tags"][0], {"label": "AI·디지털", "value": 1})
        self.assertEqual(dashboard["articles"][0]["title"], "인공지능 행정 서비스 확대")

    def test_llm_job_queue_recovers_after_worker_session_changes(self):
        case = self.store.save_case(case_payload())
        first, _ = self.store.upsert_article({
            "canonical_url": "https://example.com/queue-1", "original_url": "https://example.com/queue-1",
            "title": "첫 번째 기사", "publisher": "example.com", "snippet": "첫 번째", "source_type": "test",
        })
        second, _ = self.store.upsert_article({
            "canonical_url": "https://example.com/queue-2", "original_url": "https://example.com/queue-2",
            "title": "두 번째 기사", "publisher": "example.com", "snippet": "두 번째", "source_type": "test",
        })
        self.assertEqual(self.store.activate_worker_session("worker-a"), 0)
        first_job = self.store.queue_llm_job(first["id"], case["id"], 1)
        second_job = self.store.queue_llm_job(second["id"], case["id"], 1)
        self.assertTrue(self.store.start_llm_job(first_job))
        self.assertEqual(self.store.next_llm_job()["id"], second_job)
        self.assertEqual(self.store.activate_worker_session("worker-b"), 1)
        self.assertEqual(self.store.next_llm_job()["id"], first_job)

    def test_failed_common_analysis_is_requeued_for_bounded_retry(self):
        article, _ = self.store.upsert_article({
            "canonical_url": "https://example.com/retry-common",
            "original_url": "https://example.com/retry-common",
            "title": "재시도 기사", "publisher": "example.com", "snippet": "재시도", "source_type": "test",
        })
        analysis, _ = self.store.ensure_article_analysis(article)
        job_id = self.store.queue_article_analysis(analysis["id"])
        self.assertTrue(self.store.start_article_analysis_job(job_id))
        self.store.finish_article_analysis_job(job_id, False, 10, "failed_generation")
        recovered = self.store.recover_incomplete_pipeline_jobs()
        self.assertEqual(recovered["common"], 1)
        self.assertEqual(self.store.next_article_analysis_job()["id"], job_id)

    def test_invite_is_one_time(self):
        invite, token = self.store.create_invite("테스트", 60)
        self.assertEqual(self.store.valid_invite(token)["id"], invite["id"])
        self.assertIsNone(self.store.valid_invite("wrong-token"))

    def test_signup_request_links_kakao_recipient_after_admin_approval(self):
        organization = self.store.save_organization({
            "name": "행정안전부", "abbreviations": ["행안부"], "former_names": [],
            "people": [], "exclude_terms": [], "domains": [], "rss_urls": [],
            "collection_mode": "interval", "collection_interval_minutes": 30, "collection_times": [],
            "max_search_queries": 8, "max_articles_per_run": 50, "is_active": True,
        })
        case = self.store.save_case({**case_payload(), "organization_id": organization["id"]})
        case2 = self.store.save_case({**case_payload(), "name": "정책 발표", "organization_id": organization["id"]})
        request, token = self.store.create_signup_request("김철수", organization["id"], [case["id"]])
        self.assertEqual(request["masked_name"], "김*수")
        self.assertEqual(request["status"], "requested")
        recipient = self.store.consume_invite(token, {
            "kakao_user_id": "kakao-1", "access_token_ciphertext": "access",
            "refresh_token_ciphertext": "refresh", "access_token_expires_at": now_iso(),
            "refresh_token_expires_at": now_iso(),
        })
        updated = self.store.mark_signup_request_kakao_registered(token, recipient["id"])
        self.assertEqual(updated["status"], "kakao_registered")
        approved = self.store.decide_signup_case(request["id"], case["id"], "approved")
        self.assertEqual(approved["status"], "approved")
        self.assertIn(recipient["id"], self.store.case_recipient_ids(case["id"]))
        changed = self.store.set_signup_request_subscriptions(request["id"], [case2["id"]])
        statuses = {item["case_id"]: item["status"] for item in changed["case_requests"]}
        self.assertEqual(statuses[case["id"]], "revoked")
        self.assertEqual(statuses[case2["id"]], "approved")
        self.assertNotIn(recipient["id"], self.store.case_recipient_ids(case["id"]))
        self.assertIn(recipient["id"], self.store.case_recipient_ids(case2["id"]))
        revoked = self.store.set_signup_request_subscriptions(request["id"], [], "전체 해지")
        self.assertEqual(revoked["status"], "revoked")
        self.assertNotIn(recipient["id"], self.store.case_recipient_ids(case2["id"]))
        public = self.store.list_signup_requests(include_private=False)[0]
        self.assertNotIn("applicant_name", public)
        self.assertEqual(public["masked_name"], "김*수")
        self.assertTrue(self.store.delete_recipient(recipient["id"]))
        self.assertEqual(self.store.list_signup_requests(include_private=True), [])

    def test_completed_signup_requests_expire_after_six_hours(self):
        organization = self.store.save_organization({"name": "행정안전부", "is_active": True})
        case = self.store.save_case({**case_payload(), "organization_id": organization["id"]})
        request, token = self.store.create_signup_request("김철수", organization["id"], [case["id"]])
        recipient = self.store.consume_invite(token, {
            "kakao_user_id": "kakao-cleanup", "access_token_ciphertext": "access",
            "refresh_token_ciphertext": "refresh", "access_token_expires_at": now_iso(),
            "refresh_token_expires_at": now_iso(),
        })
        self.store.mark_signup_request_kakao_registered(token, recipient["id"])
        self.store.decide_signup_case(request["id"], case["id"], "approved")
        old = (datetime.now(KST) - timedelta(hours=7)).isoformat(timespec="seconds")
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE signup_requests SET decided_at=?,updated_at=? WHERE id=?",
                (old, old, request["id"]),
            )
        self.assertEqual(self.store.list_signup_requests(include_private=True), [])
        with self.store.connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) count FROM signup_request_cases WHERE request_id=?",
                (request["id"],),
            ).fetchone()["count"]
        self.assertEqual(count, 0)

    def test_schedule_and_threshold_validation(self):
        invalid_time = {**case_payload(), "collection_mode": "times", "collection_times": ["25:99"]}
        with self.assertRaisesRegex(ValueError, "HH:MM"):
            self.store.save_case(invalid_time)
        reversed_thresholds = {**case_payload(), "relevance_threshold": 50, "hold_threshold": 70}
        with self.assertRaisesRegex(ValueError, "보류 기준"):
            self.store.save_case(reversed_thresholds)


class ScoringTests(unittest.TestCase):
    def test_openrouter_case_judgment_sends_only_minimized_public_evidence(self):
        settings = SimpleNamespace(openrouter_case_model="google/gemma-4-26b-a4b-it:free")
        client = OpenRouterClient(settings)
        captured = {}

        def fake_request(path, payload):
            captured["path"] = path
            captured["payload"] = payload
            return {
                "message": {"content": json.dumps({
                    "is_relevant": True, "score": 88, "required_topic_met": True,
                    "topic_evidence_ids": ["Q1"], "target_is_primary": True,
                    "target_evidence_ids": ["T1"], "stance_evidence_ids": ["S1"],
                    "reasons": ["직접 비판 근거 확인"], "exclusion_reason": "none",
                    "low_score_categories": [],
                }, ensure_ascii=False)},
                "_provider_meta": {"provider": "openrouter", "upstream_provider": "test"},
            }

        client.request = fake_request
        case = {
            **case_payload(),
            "name": "행안부 부정 기사",
            "topic_search_prompt": "ADMIN_PROMPT_SENTINEL 행정안전부를 비판하는 기사",
            "include_terms": ["인공지능"],
            "organization_terms": ["행정안전부", "행안부", "윤호중 장관"],
        }
        article = {
            "title": "행정안전부 대응 지연 비판",
            "snippet": "대응이 늦었다는 지적이다.",
            "body": "행정안전부 대응이 늦었다는 비판이 나왔다. RAW_BODY_SENTINEL 관련 없는 문장이다.",
        }
        common = {"summary": "인공지능 행정 대응 지연을 비판한 기사", "tone": "부정적"}
        result = client.judge_case(case, article, common)
        transmitted = json.dumps(captured["payload"]["messages"], ensure_ascii=False)

        self.assertEqual(captured["path"], "/api/chat")
        self.assertIn(article["title"], transmitted)
        self.assertIn("인공지능 행정 대응 지연을 비판한 기사", transmitted)
        self.assertIn("ADMIN_PROMPT_SENTINEL", transmitted)
        self.assertIn("인공지능", transmitted)
        self.assertNotIn("RAW_BODY_SENTINEL", transmitted)
        self.assertEqual(result["analysis_report"]["privacy_mode"], "public_evidence_and_case_requirements")
        self.assertFalse(result["analysis_report"]["input_content"]["body_transmitted"])
        self.assertTrue(result["analysis_report"]["input_content"]["user_case_prompt_transmitted"])

    def test_ollama_common_analysis_uses_cpu_15b_profile(self):
        settings = SimpleNamespace(llm_model="qwen2.5:1.5b")
        client = OllamaClient(settings)
        captured = {}

        def fake_request(path, payload):
            captured["path"] = path
            captured["payload"] = payload
            return {"message": {"content": json.dumps({
                "article_type": "AI·디지털",
                "classification_tags": ["AI·디지털", "사실전달", "추가 태그"],
                "tone": "사실전달",
                "summary": "요약" * 120,
                "publisher_name": "연합뉴스",
                "reporter_name": "구정모",
                "entities": ["인공지능", "디지털정부", "공통기반", "데이터센터", "행정서비스", "플랫폼", "추가명사"],
                "topic_concepts": ["디지털 행정", "공공 AI 전환", "제외 개념"],
                "evidence_ids": ["E1", "E2", "E3", "E4", "E5", "E6"],
            }, ensure_ascii=False)}}

        client.request = fake_request
        result = client.analyze_article_common({
            "title": "디지털정부 공통기반 전환",
            "publisher": "yna.co.kr",
            "original_url": "https://yna.co.kr/article/1",
            "body": "구정모 기자가 취재했다. " + ("인공지능과 디지털정부 공통기반, 데이터센터, 행정서비스, 플랫폼을 설명한다. " * 100),
        })

        self.assertEqual(captured["path"], "/api/chat")
        self.assertEqual(captured["payload"]["model"], "qwen2.5:1.5b")
        self.assertEqual(captured["payload"]["options"], {
            "temperature": 0.0, "num_predict": 180, "num_ctx": 3072, "num_thread": 4,
        })
        self.assertEqual(captured["payload"]["keep_alive"], "10m")
        self.assertLessEqual(result["analysis_report"]["input_content"]["input_length"], 2200)
        self.assertLessEqual(len(result["summary"]), 160)
        self.assertEqual(len(result["classification_tags"]), 2)
        self.assertEqual(len(result["entities"]), 6)
        self.assertEqual(len(result["topic_concepts"]), 2)
        self.assertEqual(result["publisher_name"], "연합뉴스")
        self.assertEqual(result["reporter_name"], "구정모")

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
        self.assertFalse(quick_candidate_match(case, {"title": "체육 경기 결과", "snippet": ""}))

    def test_ai_copyright_notice_is_not_a_case_candidate(self):
        case = {**case_payload(), "include_terms": ["AI", "인공지능", "공통기반"]}
        article = {
            "title": "경찰 인사 쇄신안 논란",
            "snippet": "행정안전부가 인사 개선안을 발표했다.",
            "body": "경찰 내부에서는 조직 연좌제라는 반발이 나왔다. 무단전재 배포금지, AI 학습 및 활용 금지",
        }
        self.assertFalse(quick_candidate_match(case, article))
        self.assertEqual(keyword_relevance(case, article)["matched_terms"], [])

    def test_case_candidate_gate_requires_mandatory_terms_before_llm(self):
        case = {**case_payload(), "include_terms": ["인공지능"], "required_terms": ["쿠팡"]}
        article = {"title": "행안부 인공지능 정책", "snippet": "AI 행정서비스 확대", "body": "행정안전부가 서비스를 발표했다."}
        ok, reason = case_candidate_gate(case, article, {"summary": "인공지능 정책", "tone": "사실전달"}, 95, 65)
        self.assertFalse(ok)
        self.assertEqual(reason, "required_terms_missing")

    def test_case_candidate_gate_does_not_use_low_semantic_as_include_bypass(self):
        case = {**case_payload(), "include_terms": ["인공지능"], "required_terms": []}
        article = {"title": "행안부 재난 대응", "snippet": "호우 피해 복구", "body": "행정안전부가 중대본 회의를 열었다."}
        low_ok, low_reason = case_candidate_gate(case, article, {"summary": "호우 대응", "tone": "사실전달"}, 70, 65)
        high_ok, high_reason = case_candidate_gate(case, article, {"summary": "호우 대응", "tone": "사실전달"}, 91, 65)
        self.assertFalse(low_ok)
        self.assertEqual(low_reason, "include_terms_missing")
        self.assertTrue(high_ok)
        self.assertEqual(high_reason, "keyword_or_semantic_candidate")

    def test_organization_candidate_filter(self):
        organization = {
            "name": "행정안전부", "abbreviations": ["행안부"], "former_names": ["행자부"],
            "people": ["윤호중 장관"], "exclude_terms": ["동명이인"], "domains": ["mois.go.kr"],
        }
        self.assertTrue(organization_candidate_match(organization, {"title": "행안부 재난 대응", "snippet": ""}))
        self.assertTrue(organization_candidate_match(organization, {"title": "정부 보도자료", "snippet": "", "original_url": "https://mois.go.kr/news/1"}))
        self.assertFalse(organization_candidate_match(organization, {"title": "행안부 동명이인 인터뷰", "snippet": ""}))


    def test_llm_topic_match_controls_delivery(self):
        class FakeOllama:
            def __init__(self, relevant: bool):
                self.relevant = relevant

            def embeddings(self, _values):
                return [[1.0, 0.0], [1.0, 0.0]]

            def classify_and_summarize(self, _case, _article):
                return {
                    "score": 92 if self.relevant else 25,
                    "is_relevant": self.relevant,
                    "article_type": "정책·행정",
                    "classification_tags": ["정책·행정", "AI·디지털"],
                    "summary": "기사 요약",
                    "reasons": ["주제 본문 비교"],
                    "categories": [],
                    "exclusion_reason": "none" if self.relevant else "simple_mention",
                }

        engine = RelevanceEngine(None)
        article = {"title": "인공지능 행정 혁신", "snippet": "정책 소개", "body": "정부가 행정 서비스에 인공지능을 적용한다."}
        engine.ollama = FakeOllama(True)
        relevant = engine.evaluate(case_payload(), article)
        self.assertEqual(relevant["decision"], "send")
        self.assertTrue(relevant["topic_relevant"])
        self.assertEqual(relevant["article_type"], "정책·행정")
        self.assertEqual(relevant["classification_tags"][0], "정책·행정")

        engine.ollama = FakeOllama(False)
        unrelated = engine.evaluate(case_payload(), article)
        self.assertEqual(unrelated["decision"], "low")
        self.assertFalse(unrelated["topic_relevant"])
        self.assertIn("llm_simple_mention", unrelated["low_score_categories"])

    def test_case_similarity_percentage_matches_threshold_score(self):
        class FakeCaseLlm:
            def judge_case(self, _case, _article, _common, _model):
                return {
                    "score": 82, "is_relevant": True, "required_topic_met": True,
                    "topic_evidence": ["인공지능 행정 혁신"], "target_is_primary": False,
                    "target_evidence": [], "stance_evidence": [], "reasons": ["직접 유사도"],
                    "categories": [], "analysis_report": {},
                }

        case = {
            **case_payload(), "relevance_threshold": 75, "organization_terms": [],
            "keyword_weight": 0.25, "semantic_weight": 0.25, "llm_weight": 0.5,
        }
        article = {"title": "인공지능 행정 혁신", "snippet": "행정 서비스", "body": "인공지능 행정 서비스를 확대한다."}
        engine = RelevanceEngine(None)
        engine.case_llm = FakeCaseLlm()
        result = engine.evaluate_case_with_common(case, article, {"tone": "사실전달", "id": "common-1"})
        self.assertEqual(result["llm_score"], 82)
        self.assertEqual(result["similarity_score"], 82)
        self.assertEqual(result["final_score"], 82)
        self.assertEqual(result["decision"], "send")
        self.assertNotEqual(result["analysis_report"]["components"]["candidate_blend_score"], result["similarity_score"])

    def test_required_ai_topic_blocks_high_institution_score(self):
        class FakeCaseLlm:
            def judge_case(self, _case, _article, _common, _model):
                return {
                    "score": 85, "is_relevant": True, "required_topic_met": False,
                    "topic_evidence": [], "target_is_primary": True,
                    "target_evidence": ["행정안전부가 경찰 인사 개선안을 발표했다."],
                    "stance_evidence": [], "reasons": ["기관은 직접 관련됨"],
                    "categories": [], "analysis_report": {},
                }

        case = {
            **case_payload(),
            "topic_search_prompt": "주제는 반드시 AI 및 인공지능 관련 기술이어야 한다.",
            "include_terms": ["AI", "인공지능", "공통기반"],
            "organization_terms": ["행정안전부", "행안부"],
            "relevance_threshold": 75,
        }
        article = {
            "title": "경찰 인사 쇄신안 논란", "snippet": "행정안전부가 경찰 인사 개선안을 발표했다.",
            "body": "경찰 내부 반발이 나왔다. 무단전재 배포금지, AI 학습 및 활용 금지",
        }
        engine = RelevanceEngine(None)
        engine.case_llm = FakeCaseLlm()
        result = engine.evaluate_case_with_common(case, article, {"summary": "경찰 인사 개선안 기사", "tone": "사실전달", "id": "common-1"})
        self.assertEqual(result["llm_score"], 85)
        self.assertEqual(result["final_score"], 85)
        self.assertEqual(result["decision"], "low")
        self.assertIn("required_topic_not_verified", result["low_score_categories"])

    def test_prompt_must_not_promote_include_terms_to_hard_gate(self):
        class FakeCaseLlm:
            def judge_case(self, _case, _article, _common, _model):
                return {
                    "score": 85, "is_relevant": True, "required_topic_met": True,
                    "topic_evidence": ["송경주 지방재정경제실장이 정책 의미를 설명했다."],
                    "target_is_primary": True,
                    "target_evidence": ["행안부 송경주 지방재정경제실장이 정책 의미를 설명했다."],
                    "stance_evidence": [], "reasons": ["행안부 실국장 발언"],
                    "categories": [], "analysis_report": {},
                }

        case = {
            **case_payload(),
            "topic_search_prompt": "행안부 실국장의 의미 있는 발언인지 판정한다. 반드시 현직 실국장이어야 한다.",
            "include_terms": ["인터뷰", "발언", "답변", "현장방문", "주재", "브리핑"],
            "required_terms": [], "organization_terms": ["행정안전부", "행안부"],
            "_semantic_raw": 0.879012, "_semantic_score": 95.3,
            "semantic_weight": 0.5, "llm_weight": 0.5, "relevance_threshold": 75,
        }
        article = {
            "title": "문체부·행안부, 지역관광정책 경진대회 신설",
            "snippet": "행정안전부와 문화체육관광부가 공동 사업을 추진한다.",
            "body": "행안부 송경주 지방재정경제실장이 정책 의미를 설명했다.",
        }
        engine = RelevanceEngine(None)
        engine.case_llm = FakeCaseLlm()
        result = engine.evaluate_case_with_common(
            case, article, {"summary": "행안부 실장의 정책 설명", "tone": "사실전달", "id": "common-1"}
        )

        self.assertEqual(result["final_score"], 90.2)
        self.assertEqual(result["decision"], "send")
        self.assertFalse(result["analysis_report"]["components"]["local_topic_gate"]["required"])
        self.assertNotIn("required_topic_not_verified", result["low_score_categories"])

    def test_raw_llm_score_is_preserved_when_evidence_is_unverified(self):
        class FakeOllama:
            def embeddings(self, _values):
                return [[1.0, 0.0], [1.0, 0.0]]

            def classify_and_summarize(self, _case, _article):
                return {
                    "score": 95, "is_relevant": True, "summary": "관련 기사",
                    "reasons": [], "categories": [], "exclusion_reason": "none",
                    "article_type": "정책·행정", "classification_tags": ["정책·행정"],
                    "tone": "사실전달", "target_is_primary": False,
                    "target_evidence": ["본문 인용"], "stance_evidence": ["본문 인용"],
                }

        case = {
            **case_payload(), "topic_search_prompt": "행정안전부를 직접 비판하는 부정 기사를 찾아줘",
            "organization_terms": ["행정안전부", "행안부"],
        }
        article = {"title": "행정안전부 정책 발표", "snippet": "정책 설명", "body": "행정안전부가 정책을 발표했다."}
        engine = RelevanceEngine(None)
        engine.ollama = FakeOllama()
        result = engine.evaluate(case, article)
        self.assertEqual(result["llm_score"], 95)
        self.assertGreater(result["final_score"], 35)
        self.assertEqual(result["decision"], "low")
        self.assertEqual(result["evidence_status"], "target_and_stance_unverified")

    def test_operational_factual_report_is_excluded_from_negative_monitoring(self):
        class FakeOllama:
            def embeddings(self, _values):
                return [[1.0, 0.0], [1.0, 0.0]]

            def classify_and_summarize(self, _case, _article):
                return {
                    "score": 95, "is_relevant": True, "summary": "재난 대응 현황 기사",
                    "reasons": ["행정안전부 재난 대응 언급"], "categories": [], "exclusion_reason": "none",
                    "article_type": "재난·안전", "classification_tags": ["재난·안전"],
                    "tone": "부정적", "target_is_primary": True,
                    "target_evidence": ["행정안전부는 호우특보에 따라 중대본 1단계를 가동했다."],
                    "stance_evidence": ["행정안전부는 호우특보에 따라 중대본 1단계를 가동했다."],
                }

        case = {
            **case_payload(), "topic_search_prompt": "행정안전부를 직접 비판하는 부정 기사를 찾아줘",
            "organization_terms": ["행정안전부", "행안부"],
        }
        article = {
            "title": "행정안전부, 호우특보에 중대본 1단계 가동",
            "snippet": "행정안전부가 비상근무와 현장 점검을 지시했다.",
            "body": "행정안전부는 호우특보에 따라 중대본 1단계를 가동했다. 비상근무와 현장 점검을 지시했다.",
        }
        engine = RelevanceEngine(None)
        engine.ollama = FakeOllama()
        result = engine.evaluate(case, article)
        self.assertEqual(result["llm_score"], 95)
        self.assertEqual(result["final_score"], 95)
        self.assertEqual(result["decision"], "low")
        self.assertEqual(result["tone"], "사실전달")
        self.assertIn("operational_factual_report", result["low_score_categories"])

    def test_direct_criticism_is_not_capped_as_operational_report(self):
        class FakeOllama:
            def embeddings(self, _values):
                return [[1.0, 0.0], [1.0, 0.0]]

            def classify_and_summarize(self, _case, _article):
                return {
                    "score": 95, "is_relevant": True, "summary": "직접 비판 기사",
                    "reasons": ["대응 지연 비판"], "categories": [], "exclusion_reason": "none",
                    "article_type": "재난·안전", "classification_tags": ["재난·안전"],
                    "tone": "부정적", "target_is_primary": True,
                    "target_evidence": ["행정안전부의 중대본 가동이 늦었다는 비판이 나왔다."],
                    "stance_evidence": ["행정안전부의 중대본 가동이 늦었다는 비판이 나왔다."],
                }

        case = {
            **case_payload(), "topic_search_prompt": "행정안전부를 직접 비판하는 부정 기사를 찾아줘",
            "organization_terms": ["행정안전부", "행안부"],
        }
        article = {
            "title": "행정안전부 중대본 가동 늑장 비판",
            "snippet": "대응 지연을 지적하는 목소리가 나왔다.",
            "body": "행정안전부의 중대본 가동이 늦었다는 비판이 나왔다.",
        }
        engine = RelevanceEngine(None)
        engine.ollama = FakeOllama()
        result = engine.evaluate(case, article)
        self.assertEqual(result["llm_score"], 95)
        self.assertNotIn("operational_factual_report", result["low_score_categories"])

    def test_url_canonicalization(self):
        value = canonicalize_url("HTTPS://Example.COM/news/1/?utm_source=x&keep=1#section")
        self.assertEqual(value, "https://example.com/news/1?keep=1")


class OrganizationPipelineTests(unittest.TestCase):
    def test_new_case_ignores_articles_collected_before_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "case-start.sqlite3")
            organization = store.save_organization({"name": "행정안전부", "is_active": True})
            article, _ = store.upsert_article({
                "canonical_url": "https://example.com/before-case",
                "original_url": "https://example.com/before-case",
                "title": "케이스 생성 전 수집 기사",
                "body": "행정안전부 인공지능 정책 기사",
            })
            with store.connect() as connection:
                connection.execute(
                    "UPDATE articles SET first_seen_at='2020-01-01T00:00:00+09:00' WHERE id=?",
                    (article["id"],),
                )
            article = store.get_article(article["id"])
            analysis, _ = store.ensure_article_analysis(article, organization["id"])
            case = store.save_case({**case_payload(), "organization_id": organization["id"]})

            service = MasterPressService.__new__(MasterPressService)
            service.store = store
            routed = service._route_article_analysis(analysis, article, organization["id"])

            self.assertEqual(routed["case_before_start"], 1)
            with store.connect() as connection:
                count = connection.execute(
                    "SELECT COUNT(*) value FROM case_evaluations WHERE article_id=? AND case_id=?",
                    (article["id"], case["id"]),
                ).fetchone()["value"]
            self.assertEqual(count, 0)

    def test_collect_once_and_distribute_to_linked_case(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "pipeline.sqlite3")
            organization = store.save_organization({
                "name": "행정안전부", "abbreviations": ["행안부"], "former_names": [],
                "people": [], "exclude_terms": [], "domains": [], "rss_urls": [],
                "collection_mode": "interval", "collection_interval_minutes": 10,
                "collection_times": [], "max_search_queries": 8, "max_articles_per_run": 50,
                "is_active": True,
            })
            case = store.save_case({**case_payload(), "organization_id": organization["id"]})

            class FakeCollector:
                def collect_organization(self, _organization):
                    return [{
                        "canonical_url": "https://example.com/org-news",
                        "original_url": "https://example.com/org-news",
                        "title": "행안부 인공지능 행정 확대",
                        "publisher": "example.com",
                        "snippet": "행정안전부가 인공지능 디지털정부 행정 서비스를 확대한다.",
                        "source_type": "test",
                    }]

                def fetch_body(self, _url):
                    return {"body": "행정안전부가 인공지능 디지털정부 행정 서비스를 확대한다."}

            class FakeScoring:
                class FakeOllama:
                    def embeddings(self, _texts):
                        return [[1.0, 0.0, 0.0]]
                ollama = FakeOllama()

                def analyze_article_common(self, _article, _model):
                    return {
                        "summary": "행정 서비스 확대", "article_type": "정책·행정", "tone": "사실전달",
                        "classification_tags": ["정책·행정", "AI·디지털", "사실전달"],
                        "entities": ["행정안전부", "인공지능", "디지털정부", "행정 서비스", "확대한다", "기사에 없음"], "evidence": [],
                        "analysis_report": {},
                    }

                def evaluate_cases_with_common(self, _cases, _article, _common, _model):
                    return {}

                def evaluate_case_with_common(self, _case, _article, _common, _model):
                    return {
                        "keyword_score": 90, "semantic_score": 85, "llm_score": 88, "final_score": 87,
                        "evidence_status": "verified", "reasons": ["관련"], "matched_terms": ["인공지능"],
                        "low_score_categories": [], "decision": "low", "urgent": False, "llm_error": "", "analysis_report": {},
                    }

            class FakePressReleases:
                def queue_for_article(self, _analysis_id):
                    return 0

            class FakeMirror:
                def article_score(self, _article, _score):
                    return True

                def organization(self, _organization):
                    return True

            service = MasterPressService.__new__(MasterPressService)
            service.store = store
            service.collector = FakeCollector()
            service.scoring = FakeScoring()
            service.mirror = FakeMirror()
            service.press_releases = FakePressReleases()
            result = service.run_organization(organization["id"])
            self.assertEqual(result["counts"]["collected"], 1)
            self.assertEqual(result["counts"]["analysis_queued"], 1)
            self.assertEqual(result["counts"]["scored"], 0)
            common = service.process_next_article_analysis()
            self.assertEqual(common["stage"], "article")
            embedded = service.process_next_embedding()
            self.assertTrue(embedded["embedded"])
            with store.connect() as connection:
                connection.execute("UPDATE case_evaluation_jobs SET retry_after='' WHERE status='pending'")
            processed = service.process_next_case_evaluation()
            self.assertEqual(processed["counts"]["scored"], 1)
            self.assertEqual(processed["counts"]["missing"], 0)
            insight_labels = {item["label"] for item in store.analysis_insights(organization_id=organization["id"])["words"]}
            self.assertIn("인공지능", insight_labels)
            self.assertIn("행정 서비스", insight_labels)
            self.assertNotIn("행정안전부", insight_labels)
            self.assertNotIn("확대한다", insight_labels)
            self.assertNotIn("기사에 없음", insight_labels)
            dashboard = store.pipeline_dashboard(organization_id=organization["id"])
            self.assertEqual(dashboard["stats"]["total"], 1)
            self.assertEqual(dashboard["pipeline"]["processed_articles"], 1)
            self.assertGreaterEqual(dashboard["pipeline"]["average_seconds"], 0)
            self.assertEqual(dashboard["articles"][0]["organization_name"] if "organization_name" in dashboard["articles"][0] else dashboard["articles"][0]["case_results"][0]["organization_name"], "행정안전부")
            self.assertEqual(dashboard["articles"][0]["case_results"][0]["decision"], "low")
            self.assertEqual(dashboard["categories"][0], {"label": "정책·행정", "article_count": 1, "sent_count": 0})
            self.assertEqual({item["label"] for item in dashboard["tags"]}, {"정책·행정", "사실전달"})

            with store.connect() as connection:
                connection.execute("UPDATE case_evaluations SET decision='send' WHERE article_id=? AND case_id=?", (dashboard["articles"][0]["id"], case["id"]))
                connection.execute(
                    "INSERT INTO recipients(id,label,status,created_at,updated_at) VALUES(?,?,?,?,?)",
                    ("recipient-1", "테스트 수신자", "connected", "2026-07-17T10:00:00+09:00", "2026-07-17T10:00:00+09:00"),
                )
            store.queue_delivery(dashboard["articles"][0]["id"], case["id"], "recipient-1", "2026-07-17T10:00:00+09:00")
            with store.connect() as connection:
                delivery_id = connection.execute("SELECT id FROM deliveries LIMIT 1").fetchone()["id"]
            store.finish_delivery(delivery_id, True, 200)
            dashboard = store.pipeline_dashboard(case_id=case["id"])
            self.assertEqual(dashboard["recent_sent"][0]["title"], "행안부 인공지능 행정 확대")
            keyword_suggestions = store.case_sent_keyword_suggestions(case["id"])
            self.assertEqual(keyword_suggestions["sent_articles"], 1)
            self.assertEqual([item["keyword"] for item in keyword_suggestions["keywords"]], ["디지털정부"])
            self.assertNotIn("인공지능", [item["keyword"] for item in keyword_suggestions["keywords"]])
            self.assertNotIn("행정", [item["keyword"] for item in keyword_suggestions["keywords"]])
            self.assertEqual(dashboard["recent_sent"][0]["case_name"], case["name"])



class PressReleaseTests(unittest.TestCase):
    def test_mois_html_date_and_markdown_chunks(self):
        source = '<div id="desc_pc"><p>행정안전부가 호우 대응 단계를 가동했다.</p><div>* 담당자: 자연재난대응과 홍길동(044-205-1234)</div></div>'
        markdown = html_to_markdown(source, "desc_pc")
        self.assertIn("호우 대응", markdown)
        self.assertIn("044-205-1234", markdown)
        self.assertEqual(parse_mois_date("일, 19 7월 2026 09:00:00 KST"), "2026-07-19T09:00:00+09:00")
        self.assertTrue(chunk_markdown(markdown, size=80, overlap=10))
        first = '---\nsource_url: "https://mois.go.kr/a"\n---\n\n# 같은 제목\n\n본문입니다.\n\n*담당자: 안전과 홍길동(044-205-1234)'
        second = '---\nsource_url: "https://mois.go.kr/b"\n---\n\n# 같은 제목\n\n본문입니다.\n\n* 담당자: 안전과 홍길동(044-205-1234)'
        self.assertEqual(document_fingerprint("같은 제목", first), document_fingerprint("같은 제목", second))

    def test_v4_lite_normalizes_korean_topics_without_single_mention_false_anchor(self):
        self.assertGreater(lexical_similarity("중부 장맛비 피해 신고", "호우지역 피해 대응"), 0)
        article = supported_topic_concepts("중부지방 호우 피해", "인명피해는 없는 것으로 확인됐다")
        release = supported_topic_concepts("중앙재난안전대책본부장 긴급 지시", "호우와 침수, 산사태 대응")
        self.assertIn("호우·풍수해", article & release)
        incidental = supported_topic_concepts("긴급 지시", "지난해 산불 지역의 추가 산사태를 점검했다")
        self.assertNotIn("산불·화재", incidental)

    def test_article_press_pair_is_matched_only_once(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "press.sqlite3")
            organization = store.save_organization({
                "name": "행정안전부", "abbreviations": ["행안부"], "former_names": [], "people": [],
                "exclude_terms": [], "domains": ["mois.go.kr"], "rss_urls": [],
                "collection_mode": "interval", "collection_interval_minutes": 30, "collection_times": [],
                "max_search_queries": 8, "max_articles_per_run": 50, "is_active": True,
            })
            article, _ = store.upsert_article({
                "canonical_url": "https://example.com/heavy-rain", "original_url": "https://example.com/heavy-rain",
                "title": "행안부 호우 대응", "publisher": "테스트", "published_at": now_iso(),
                "snippet": "호우 대응 단계를 가동했다.", "body": "행정안전부가 호우 대응 단계를 가동했다.",
                "source_type": "test",
            })
            analysis, _ = store.ensure_article_analysis(article, organization["id"])
            store.save_article_analysis(analysis["id"], {
                "summary": "호우 대응 단계 가동", "article_type": "재난·환경", "tone": "사실전달",
                "classification_tags": ["재난·환경"], "entities": ["호우"], "topic_concepts": ["호우·재난 대응"],
                "evidence": [], "analysis_report": {},
            }, "fake")
            store.save_article_embedding(analysis["id"], "fake-embed", [1.0, 0.0])
            release_id, now = "00000000-0000-4000-8000-000000000099", now_iso()
            md_path = Path(directory) / "press_releases" / "mois" / "2026" / "99.md"
            md_path.parent.mkdir(parents=True)
            md_path.write_text("# 호우 대응\n\n행정안전부가 호우 대응 단계를 가동했다.", encoding="utf-8")
            with store.connect() as connection:
                connection.execute(
                    "INSERT INTO press_releases(id,organization_id,source,external_id,canonical_url,title,department,published_at,summary,markdown_path,content_hash,embedding_status,embedding_model,created_at,updated_at) VALUES(?,?,'mois','99','https://mois.go.kr/99','호우 대응 단계 가동','자연재난대응과',?,'호우 대응 단계 가동',?,'hash','completed','fake-embed',?,?)",
                    (release_id, organization["id"], now, str(md_path), now, now),
                )
                connection.execute(
                    "INSERT INTO press_release_chunks(id,press_release_id,chunk_index,content,content_hash,embedding_model,dimensions,vector,created_at,updated_at) VALUES('chunk-99',?,0,'호우 대응 단계 가동','hash','fake-embed',2,'[1.0,0.0]',?,?)",
                    (release_id, now, now),
                )

            class FakeMirror:
                enabled = True
                last_error = ""
                match_batches = 0
                def press_release(self, _release, _markdown): return True
                def press_release_chunks(self, _chunks): return True
                def press_release_match(self, match): return self.press_release_matches([match])
                def press_release_matches(self, _matches):
                    self.match_batches += 1
                    return True

            manager = PressReleaseManager(SimpleNamespace(
                data_dir=Path(directory), user_agent="test", request_timeout_seconds=3,
                embedding_model="fake-embed", press_release_match_window_days=45,
                press_release_match_threshold=62,
            ), store, SimpleNamespace(), FakeMirror())
            self.assertEqual(manager.queue_for_article(analysis["id"]), 1)
            self.assertEqual(manager.queue_for_article(analysis["id"]), 0)
            result = manager.process_next()
            self.assertTrue(result["related"])
            self.assertIsNone(manager.process_next())
            with store.connect() as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM article_press_release_matches").fetchone()[0], 1)
                self.assertIsNotNone(connection.execute("SELECT supabase_synced_at FROM article_press_release_matches").fetchone()[0])
                connection.execute("UPDATE article_press_release_matches SET similarity_score=64,is_related=1,supabase_synced_at=NULL")
            store.set_setting("press_release_match_threshold", "65")
            self.assertEqual(manager.releases_for_article(article["id"]), [])
            self.assertEqual(manager.get_release(release_id)["related_articles"], [])
            self.assertEqual(manager.list_releases()[0]["related_article_count"], 0)
            self.assertEqual(store.pipeline_dashboard(limit=5)["articles"][0]["related_press_count"], 0)
            store.set_setting("press_release_match_threshold", "60")
            self.assertEqual(len(manager.releases_for_article(article["id"])), 1)
            self.assertEqual(manager.list_releases()[0]["related_article_count"], 1)
            self.assertEqual(store.pipeline_dashboard(limit=5)["articles"][0]["related_press_count"], 1)
            sync_result = manager.mirror_backfill()
            self.assertEqual(sync_result["status"], "ready")
            self.assertEqual(sync_result["pending"], 0)
            self.assertGreaterEqual(manager.mirror.match_batches, 2)


class SchedulingTests(unittest.TestCase):
    def test_interval_and_immediate(self):
        now = datetime(2026, 7, 17, 10, 0, tzinfo=KST)
        case = case_payload()
        self.assertEqual(next_collection_at(case, now), "2026-07-17T10:10:00+09:00")
        self.assertEqual(delivery_at(case, False, now), "2026-07-17T10:00:00+09:00")
        one_minute = {**case, "collection_interval_minutes": 1}
        self.assertEqual(next_collection_at(one_minute, now), "2026-07-17T10:01:00+09:00")

    def test_fixed_delivery_rolls_forward(self):
        now = datetime(2026, 7, 17, 19, 0, tzinfo=KST)
        case = {**case_payload(), "send_relevant_immediately": False, "delivery_mode": "times", "delivery_times": ["09:00", "18:00"]}
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
            "organization_tag": "행정안전부",
            "final_score": 88,
            "title": "긴 뉴스 제목" * 30,
            "article_type": "정책·행정",
            "classification_tags": ["정책·행정", "AI·디지털"],
            "summary": "긴 기사 요약" * 50,
        }
        message = MasterPressService.message_text(delivery)
        self.assertLessEqual(len(message), 200)
        self.assertIn("유사도 88.0%", message)
        self.assertTrue(message.startswith("[행정안전부] [정책·행정] [AI·디지털]\n"))
        self.assertIn("긴 뉴스 제목", message)

    def test_article_link_uses_registered_homepage_origin(self):
        class Config:
            kakao_redirect_uri = "https://www.minslab.kr/poc/master-press/oauth/kakao/callback"

        service = MasterPressService.__new__(MasterPressService)
        service.settings = Config()

if __name__ == "__main__":
    unittest.main()
