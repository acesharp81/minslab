"""Read-only case fallback canary; never saves judgments or queues deliveries."""

from __future__ import annotations

import argparse
import json
import time

import master_press.scoring as scoring_module
from master_press.service import get_service


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batches", type=int, default=5)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--max-cases", type=int, default=10)
    parser.add_argument("--largest", action="store_true")
    parser.add_argument("--model", default="")
    args = parser.parse_args()
    service = get_service()
    model = str(args.model or service.selected_case_fallback_model()).strip()
    with service.store.connect() as connection:
        order_by = "case_count DESC,completed_at DESC" if args.largest else "completed_at DESC"
        groups = connection.execute(
            f"""SELECT ce.article_analysis_id,MAX(ce.completed_at) completed_at,COUNT(*) case_count
               FROM case_evaluations ce
               JOIN article_analyses aa ON aa.id=ce.article_analysis_id
               WHERE ce.status='completed' AND ce.model LIKE '%:free'
                 AND aa.status='completed'
               GROUP BY ce.article_analysis_id
               ORDER BY {order_by} LIMIT ? OFFSET ?""",
            (max(1, min(50, int(args.batches))), max(0, int(args.offset))),
        ).fetchall()
    summary = {"provider": "cloudflare", "model": model, "requested_batches": len(groups),
               "completed_batches": 0, "failed_batches": 0, "cases": 0,
               "results": 0, "decision_matches": 0, "duration_ms": 0,
               "decision_matrix": {}, "errors": [], "response_diagnostics": []}
    started_all = time.monotonic()
    for group in groups:
        analysis_id = str(group["article_analysis_id"])
        analysis = service.store.get_article_analysis(analysis_id)
        article = service.store.get_article(str((analysis or {}).get("article_id") or ""))
        if not analysis or not article:
            continue
        with service.store.connect() as connection:
            evaluations = connection.execute(
                """SELECT * FROM case_evaluations
                   WHERE article_analysis_id=? AND status='completed' AND model LIKE '%:free'
                   ORDER BY completed_at DESC LIMIT 10""",
                (analysis_id,),
            ).fetchall()
        prepared = []
        expected = {}
        for raw in evaluations:
            evaluation = service.store._decode_case_evaluation(raw) or {}
            case = service.store.get_case(str(evaluation.get("case_id") or ""))
            if not case or not case.get("is_active"):
                continue
            enriched, _organization = service.analysis_case(case)
            enriched["_semantic_raw"] = float(evaluation.get("semantic_raw") or 0)
            enriched["_semantic_score"] = float(evaluation.get("semantic_score") or 0)
            prepared.append(enriched)
            expected[str(enriched["id"])] = str(evaluation.get("decision") or "")
            if len(prepared) >= max(1, min(10, int(args.max_cases))):
                break
        if not prepared:
            continue
        started = time.monotonic()
        response_shape = {}
        original_parser = scoring_module.parse_llm_json

        def diagnostic_parser(raw: str) -> dict:
            value = str(raw or "")
            stripped = value.strip()
            response_shape.update({
                "chars": len(value),
                "empty": not bool(stripped),
                "starts_with_object": stripped.startswith("{"),
                "ends_with_object": stripped.endswith("}"),
                "open_braces": value.count("{"),
                "close_braces": value.count("}"),
                "has_results_key": '"results"' in value,
                "has_markdown_fence": "```" in value,
            })
            return original_parser(raw)

        scoring_module.parse_llm_json = diagnostic_parser
        try:
            results = service.scoring.evaluate_cases_with_common_provider(
                "cloudflare", prepared, article, analysis, model,
            )
            summary["completed_batches"] += 1
            summary["cases"] += len(prepared)
            summary["results"] += len(results)
            summary["duration_ms"] += round((time.monotonic() - started) * 1000)
            for case in prepared:
                expected_decision = expected[str(case["id"])]
                actual_decision = str((results.get(str(case["id"])) or {}).get("decision") or "missing")
                matrix_key = f"{expected_decision}->{actual_decision}"
                summary["decision_matrix"][matrix_key] = int(summary["decision_matrix"].get(matrix_key, 0)) + 1
                if actual_decision == expected_decision:
                    summary["decision_matches"] += 1
        except Exception as error:
            summary["failed_batches"] += 1
            summary["errors"].append(type(error).__name__)
        finally:
            scoring_module.parse_llm_json = original_parser
            if response_shape:
                summary["response_diagnostics"].append(response_shape)
    summary["wall_duration_ms"] = round((time.monotonic() - started_all) * 1000)
    summary["json_valid_rate"] = round(summary["completed_batches"] / max(1, summary["completed_batches"] + summary["failed_batches"]), 4)
    summary["decision_match_rate"] = round(summary["decision_matches"] / max(1, summary["cases"]), 4)
    summary["result_completeness"] = round(summary["results"] / max(1, summary["cases"]), 4)
    summary["average_batch_ms"] = round(summary["duration_ms"] / max(1, summary["completed_batches"]))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
