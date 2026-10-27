"""Reversible wire-only evidence references; stored and validated IDs stay unchanged."""
from __future__ import annotations
from copy import deepcopy
from typing import Any


def transform(value: Any, evidence: dict[str, str], clusters: dict[str, str]) -> Any:
    if isinstance(value, list):
        return [transform(item, evidence, clusters) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        mapping = evidence if key == 'evidence_ids' else clusters if key == 'live_topic_cluster_ids' else None
        if mapping is not None and isinstance(item, list):
            result[key] = [mapping.get(ref, ref) for ref in item]
        else:
            result[key] = transform(item, evidence, clusters)
    return result


def encode(analyses: list[dict], live_clusters: list[dict], valid_ids: set[str]):
    evidence = {key: f'e{index}' for index, key in enumerate(sorted(valid_ids))}
    clusters = {str(item['id']): f'c{index}' for index, item in enumerate(live_clusters)}
    encoded_clusters = deepcopy(live_clusters)
    for item in encoded_clusters:
        item['id'] = clusters[str(item['id'])]
    return (transform(analyses, evidence, clusters), encoded_clusters,
            {value: key for key, value in evidence.items()},
            {value: key for key, value in clusters.items()})
