"""Preserve classified LIVE issues omitted by the bounded final synthesis.

This is an opt-in provisional read model. No report, utterance, model mapping,
source authority, or task is written or invented by this transformation.
"""
from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

RECOVERY_VERSION = "live-topic-coverage/1.0"
SUPPLEMENTARY_STATUS = "SUPPLEMENTARY_EVIDENCE"
_MAPPED = {
    "DIRECT_EVIDENCE", "SYNTHESIS_ASSIGNED", "DETERMINISTIC_FALLBACK",
    "SEMANTIC_ASSIGNED", SUPPLEMENTARY_STATUS,
}


def recover_live_topic_coverage(
    brief: dict[str, Any],
    classify: Callable[[dict[str, Any]], dict[str, Any] | None],
) -> dict[str, Any]:
    result = deepcopy(brief)
    topics = result.get("topics") or []
    lineage = result.get("live_topic_lineage") or {}
    clusters = lineage.get("clusters") or []
    if not topics or not clusters:
        return result
    topic_ids = [str(topic.get("id")) for topic in topics]
    # An unresolved ID collision cannot safely receive additional references.
    if len(topic_ids) != len(set(topic_ids)):
        return result
    prior = result.get("live_topic_coverage") or {}
    original_unmapped = prior.get("original_unmapped_cluster_count", sum(
        cluster.get("mapping_status") == "UNMAPPED" for cluster in clusters
    ))
    original_singletons = prior.get("original_single_utterance_unmapped_count", sum(
        cluster.get("mapping_status") == "UNMAPPED"
        and int(cluster.get("utterance_count") or 0) == 1 for cluster in clusters
    ))
    used_ids = set(topic_ids)
    for cluster in clusters:
        # Ambiguous candidates and existing accepted links stay as reviewed.
        if cluster.get("mapping_status") != "UNMAPPED" or cluster.get("final_topic_ids"):
            continue
        title = str(cluster.get("title") or "").strip()
        evidence = list(dict.fromkeys(str(value) for value in cluster.get("utterance_ids") or [] if value))
        cluster_id = str(cluster.get("id") or "")
        if not title or not evidence or not cluster_id:
            continue
        match = classify({"title": title})
        if not match or match.get("key") == "assembly-procedure":
            continue
        # Do not turn short generic terms such as '기소' into coverage claims.
        if len(str(match.get("matched_keyword") or "")) < 3:
            continue
        topic_id = f"live-issue-{cluster_id}"
        if topic_id in used_ids:
            continue
        requests = [str(value).strip() for value in cluster.get("tasks") or [] if str(value).strip()]
        summary = "실시간 분석에서 보존한 쟁점입니다. "
        summary += " / ".join(requests) if requests else title
        topics.append({
            "id": topic_id,
            "title": title,
            "summary": summary,
            "summary_source": "PRESERVED_LIVE_TOPIC",
            "authority_status": "PROVISIONAL",
            "speaker_points": [],
            "evidence_ids": evidence,
            "official_evidence_ids": [],
            "live_topic_cluster_ids": [cluster_id],
            "coverage_origin": "LIVE_TOPIC_SUPPLEMENT",
            "classification_evidence": {
                "target_key": match["key"],
                "matched_keyword": match["matched_keyword"],
                "matched_field": "title",
            },
        })
        used_ids.add(topic_id)
        cluster["mapping_status"] = SUPPLEMENTARY_STATUS
        cluster["final_topic_ids"] = [topic_id]
        cluster["match_basis"] = "PRESERVED_CLUSTER_EVIDENCE"
        cluster["match_score"] = 1.0
    recovered = [str(c["id"]) for c in clusters if c.get("mapping_status") == SUPPLEMENTARY_STATUS]
    mapped = sum(c.get("mapping_status") in _MAPPED for c in clusters)
    unmapped = sum(c.get("mapping_status") == "UNMAPPED" for c in clusters)
    ambiguous = len(clusters) - mapped - unmapped
    lineage.update(
        mapped_cluster_count=mapped, unmapped_cluster_count=unmapped,
        ambiguous_cluster_count=ambiguous, supplementary_cluster_count=len(recovered),
        coverage_status="COMPLETE" if not unmapped and not ambiguous else "PARTIAL",
    )
    result["live_topic_lineage"] = lineage
    result["live_topic_coverage"] = {
        "version": RECOVERY_VERSION,
        "method": "CLASSIFIED_LIVE_EVIDENCE_SUPPLEMENT",
        "core_topic_count": sum(t.get("coverage_origin") != "LIVE_TOPIC_SUPPLEMENT" for t in topics),
        "supplementary_topic_count": len(recovered),
        "recovered_cluster_ids": recovered,
        "original_unmapped_cluster_count": original_unmapped,
        "original_single_utterance_unmapped_count": original_singletons,
        "additional_llm_calls": 0,
    }
    result["topics"] = topics
    return result
