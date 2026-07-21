from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from master_press.scoring import (
    OpenRouterClient,
    RelevanceEngine,
    calibrated_semantic_score,
    case_retrieval_text,
)
from master_press.storage import Store, now_iso


def case_data(index: int) -> dict:
    return {
        "name": f"AI 동향 {index}",
        "topic_search_prompt": "인공지능이 핵심 주제인 기사. 단순 언급은 제외한다.",
        "include_terms": ["인공지능"],
        "required_terms": [],
        "exclude_terms": ["광고"],
        "urgent_terms": [],
        "synonym_terms": {"인공지능": ["AI"]},
        "relevance_threshold": 69,
        "hold_threshold": 50,
        "keyword_weight": 0,
        "semantic_weight": 0.5,
        "llm_weight": 0.5,
        "is_active": True,
    }


class HybridScoreTests(unittest.TestCase):
    def test_case_retrieval_text_uses_positive_requirements_only(self):
        text = case_retrieval_text(case_data(1))
        self.assertIn("인공지능", text)
        self.assertNotIn("단순 언급은 제외", text)

    def test_calibration_spreads_dense_cosine_values(self):
        calibration = {"q10": 0.62, "q50": 0.72, "q90": 0.82}
        self.assertEqual(calibrated_semantic_score(0.62, calibration), 10.0)
        self.assertEqual(calibrated_semantic_score(0.72, calibration), 50.0)
        self.assertEqual(calibrated_semantic_score(0.82, calibration), 90.0)

    def test_final_score_is_vector_llm_hybrid_and_relevance_is_hard_gate(self):
        engine = RelevanceEngine.__new__(RelevanceEngine)
        case = {**case_data(1), "id": "case-1", "_semantic_raw": 0.71, "_semantic_score": 60.0}
        article = {
            "title": "정부 인공지능 행정서비스 확대",
            "snippet": "인공지능이 행정서비스의 핵심 정책으로 추진된다.",
            "body": "정부는 인공지능 행정서비스를 전 부처로 확대한다고 밝혔다.",
        }
        common = {"id": "analysis-1", "summary": article["snippet"], "tone": "사실전달"}
        judgment = {
            "score": 80.0,
            "is_relevant": True,
            "required_topic_met": True,
            "topic_evidence": [article["body"]],
            "target_is_primary": False,
            "target_evidence": [],
            "stance_evidence": [],
            "reasons": ["AI가 핵심 주제"],
            "categories": [],
            "analysis_report": {},
        }
        result = engine.evaluate_case_with_common(case, article, common, llm_result=judgment)
        self.assertEqual(result["final_score"], 70.0)
        self.assertEqual(result["decision"], "send")
        rejected = engine.evaluate_case_with_common(
            case, article, common, llm_result={**judgment, "is_relevant": False}
        )
        self.assertEqual(rejected["final_score"], 70.0)
        self.assertEqual(rejected["decision"], "low")


class BatchLeaseTests(unittest.TestCase):
    def test_jobs_for_one_article_are_leased_together_once(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "batch.sqlite3")
            organization = store.save_organization({"name": "행정안전부", "is_active": True})
            article, _ = store.upsert_article({
                "canonical_url": "https://example.com/ai",
                "original_url": "https://example.com/ai",
                "title": "행안부 인공지능 정책",
                "body": "행정안전부가 인공지능 정책을 발표했다.",
            })
            analysis, _ = store.ensure_article_analysis(article, organization["id"])
            for index in range(3):
                case = store.save_case({**case_data(index), "organization_id": organization["id"]})
                evaluation, created = store.create_case_evaluation(
                    analysis["id"], article["id"], case, True, 0.7 + index / 100, 60 + index
                )
                self.assertTrue(created)
                store.queue_case_evaluation(evaluation["id"], ready_at=now_iso())
                _duplicate, duplicate_created = store.create_case_evaluation(
                    analysis["id"], article["id"], case, True, 0.9, 99
                )
                self.assertFalse(duplicate_created)

            with store.connect() as connection:
                connection.execute("UPDATE articles SET first_seen_at=? WHERE id=?", (now_iso(), article["id"]))

            first = store.next_case_evaluation_batch(limit=2)
            second = store.next_case_evaluation_batch(limit=2)
            third = store.next_case_evaluation_batch(limit=2)
            self.assertEqual(len(first), 2)
            self.assertEqual(len(second), 1)
            self.assertEqual(third, [])
            self.assertEqual(len({item["article_analysis_id"] for item in first + second}), 1)
            self.assertEqual(first[0]["batch_size"], 2)


class OpenRouterBatchPromptTests(unittest.TestCase):
    def test_two_cases_use_one_request_and_keep_independent_scores(self):
        settings = SimpleNamespace(openrouter_case_model="test/free")
        client = OpenRouterClient(settings)
        captured = {"calls": 0}

        def fake_request(_path, payload):
            captured["calls"] += 1
            captured["payload"] = payload
            items = []
            for index in range(2):
                items.append({
                    "case_id": f"case-{index + 1}", "is_relevant": index == 0,
                    "score": 83.7 if index == 0 else 21.4, "required_topic_met": index == 0,
                    "target_is_primary": False, "tone_met": True,
                    "topic_evidence_ids": ["E1"] if index == 0 else [],
                    "target_evidence_ids": [], "stance_evidence_ids": [],
                    "reasons": ["독립 판정"], "exclusion_reason": "none",
                    "low_score_categories": [],
                })
            return {"message": {"content": json.dumps({"results": items}, ensure_ascii=False)}}

        client.request = fake_request
        cases = [{**case_data(1), "id": "case-1"}, {**case_data(2), "id": "case-2"}]
        article = {
            "id": "article-1", "title": "인공지능 행정 확대",
            "snippet": "인공지능 행정서비스가 확대된다.",
            "body": "인공지능 행정서비스가 핵심 정책으로 확대된다.",
        }
        results = client.judge_cases(cases, article, {"summary": article["snippet"], "tone": "사실전달"})
        self.assertEqual(captured["calls"], 1)
        self.assertEqual(set(results), {"case-1", "case-2"})
        self.assertEqual(results["case-1"]["score"], 83.7)
        self.assertEqual(results["case-2"]["score"], 21.4)
        self.assertEqual(results["case-1"]["analysis_report"]["batch_size"], 2)


if __name__ == "__main__":
    unittest.main()
