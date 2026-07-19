from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from master_press.collectors import canonicalize_url, organization_candidate_match, quick_candidate_match
from master_press.kakao import TokenCipher
from master_press.press_releases import PressReleaseManager, chunk_markdown, document_fingerprint, html_to_markdown, parse_mois_date
from master_press.scoring import OpenRouterClient, RelevanceEngine, keyword_relevance
from master_press.service import MasterPressService, delivery_at, next_collection_at
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
    def test_openrouter_case_judgment_sends_only_minimized_public_evidence(self):
        settings = SimpleNamespace(openrouter_case_model="google/gemma-4-26b-a4b-it:free")
        client = OpenRouterClient(settings)
        captured = {}

        def fake_request(path, payload):
            captured["path"] = path
            captured["payload"] = payload
            return {
                "message": {"content": json.dumps({
                    "is_relevant": True, "score": 88, "target_is_primary": True,
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
            "include_terms": ["SECRET_KEYWORD_SENTINEL"],
            "organization_terms": ["행정안전부", "행안부", "윤호중 장관"],
        }
        article = {
            "title": "행정안전부 대응 지연 비판",
            "snippet": "대응이 늦었다는 지적이다.",
            "body": "행정안전부 대응이 늦었다는 비판이 나왔다. RAW_BODY_SENTINEL 관련 없는 문장이다.",
        }
        common = {"summary": "행정안전부 대응 지연을 비판한 기사", "tone": "부정적"}
        result = client.judge_case(case, article, common)
        transmitted = json.dumps(captured["payload"]["messages"], ensure_ascii=False)

        self.assertEqual(captured["path"], "/api/chat")
        self.assertIn(article["title"], transmitted)
        self.assertIn("행정안전부 대응 지연을 비판한 기사", transmitted)
        self.assertNotIn("ADMIN_PROMPT_SENTINEL", transmitted)
        self.assertNotIn("SECRET_KEYWORD_SENTINEL", transmitted)
        self.assertNotIn("RAW_BODY_SENTINEL", transmitted)
        self.assertEqual(result["analysis_report"]["privacy_mode"], "public_evidence_only")
        self.assertFalse(result["analysis_report"]["input_content"]["body_transmitted"])
        self.assertFalse(result["analysis_report"]["input_content"]["user_case_prompt_transmitted"])

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
        self.assertTrue(quick_candidate_match(case, {"title": "인공지능 광고", "snippet": ""}))
        self.assertFalse(quick_candidate_match(case, {"title": "체육 경기 결과", "snippet": ""}))

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
                    "score": 82, "is_relevant": False, "target_is_primary": False,
                    "target_evidence": [], "stance_evidence": [], "reasons": ["직접 유사도"],
                    "categories": [], "analysis_report": {},
                }

        case = {**case_payload(), "relevance_threshold": 75, "organization_terms": []}
        article = {"title": "인공지능 행정 혁신", "snippet": "행정 서비스", "body": "인공지능 행정 서비스를 확대한다."}
        engine = RelevanceEngine(None)
        engine.case_llm = FakeCaseLlm()
        result = engine.evaluate_case_with_common(case, article, {"tone": "사실전달", "id": "common-1"})
        self.assertEqual(result["llm_score"], 82)
        self.assertEqual(result["similarity_score"], 82)
        self.assertEqual(result["final_score"], 82)
        self.assertEqual(result["decision"], "send")
        self.assertNotEqual(result["analysis_report"]["components"]["candidate_blend_score"], result["similarity_score"])

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
        self.assertLessEqual(result["llm_score"], 49)
        self.assertLessEqual(result["final_score"], 49)
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
                        "snippet": "행정안전부가 인공지능 행정 서비스를 확대한다.",
                        "source_type": "test",
                    }]

                def fetch_body(self, _url):
                    return {"body": "행정안전부가 인공지능 행정 서비스를 확대한다."}

            class FakeScoring:
                def analyze_article_common(self, _article, _model):
                    return {
                        "summary": "행정 서비스 확대", "article_type": "정책·행정", "tone": "사실전달",
                        "classification_tags": ["정책·행정", "AI·디지털", "사실전달"],
                        "entities": ["행정안전부", "인공지능", "행정 서비스", "확대한다", "기사에 없음"], "evidence": [],
                        "analysis_report": {},
                    }

                def evaluate_case_with_common(self, _case, _article, _common, _model):
                    return {
                        "keyword_score": 90, "semantic_score": 85, "llm_score": 88, "final_score": 87,
                        "evidence_status": "verified", "reasons": ["관련"], "matched_terms": ["인공지능"],
                        "low_score_categories": [], "decision": "low", "urgent": False, "llm_error": "", "analysis_report": {},
                    }

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
            result = service.run_organization(organization["id"])
            self.assertEqual(result["counts"]["collected"], 1)
            self.assertEqual(result["counts"]["analysis_queued"], 1)
            self.assertEqual(result["counts"]["scored"], 0)
            common = service.process_next_article_analysis()
            self.assertEqual(common["stage"], "article")
            processed = service.process_next_case_evaluation()
            self.assertEqual(processed["counts"]["scored"], 1)
            insight_labels = {item["label"] for item in store.analysis_insights(organization_id=organization["id"])["words"]}
            self.assertIn("인공지능", insight_labels)
            self.assertIn("행정 서비스", insight_labels)
            self.assertNotIn("행정안전부", insight_labels)
            self.assertNotIn("확대한다", insight_labels)
            self.assertNotIn("기사에 없음", insight_labels)
            dashboard = store.pipeline_dashboard(organization_id=organization["id"])
            self.assertEqual(dashboard["stats"]["total"], 1)
            self.assertEqual(dashboard["articles"][0]["organization_name"] if "organization_name" in dashboard["articles"][0] else dashboard["articles"][0]["case_results"][0]["organization_name"], "행정안전부")
            self.assertEqual(dashboard["articles"][0]["case_results"][0]["decision"], "low")
            self.assertEqual(dashboard["categories"][0], {"label": "정책·행정", "article_count": 1, "sent_count": 0})
            self.assertEqual({item["label"] for item in dashboard["tags"]}, {"정책·행정", "사실전달"})

            with store.connect() as connection:
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
                connection.execute("UPDATE article_press_release_matches SET supabase_synced_at=NULL")
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
        self.assertIn("유사도 88%", message)
        self.assertTrue(message.startswith("[행정안전부] [정책·행정] [AI·디지털]\n"))
        self.assertIn("긴 뉴스 제목", message)

    def test_article_link_uses_registered_homepage_origin(self):
        class Config:
            kakao_redirect_uri = "https://www.minslab.kr/poc/master-press/oauth/kakao/callback"

        service = MasterPressService.__new__(MasterPressService)
        service.settings = Config()

if __name__ == "__main__":
    unittest.main()
