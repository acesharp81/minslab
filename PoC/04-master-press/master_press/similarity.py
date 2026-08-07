from __future__ import annotations

import math
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Callable, Iterable
from .terminology import EVENT_CONCEPT_PREFIX, inferred_editorial_events

SIMILARITY_GROUPING_VERSION = "common-hybrid-v9-explicit-title-events-48h"


def raw_semantic_similarity(left: list[float], right: list[float]) -> float:
    """Return ordinary cosine similarity without corpus centering."""
    if not left or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm <= 1e-12 or right_norm <= 1e-12:
        return 0.0
    return round(sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm), 4)


def _normalized_title(value: object) -> str:
    return re.sub(r"[\W\d_]+", "", str(value or "")).casefold()


_MAGAZINE_GENERIC_TERMS = {
    "기사", "보도", "관련", "정부", "정책", "기관", "장관", "의원", "시장", "도지사",
    "행정안전부", "행안부", "농림축산식품부", "농식품부", "한국농어촌공사", "공사",
    "대응", "대책", "현장", "점검", "현장점검", "합동점검", "실시", "총력", "추진",
    "확대", "강화", "지원", "검토", "발표", "운영", "개최", "이번", "주요", "전국",
    "대한", "위한", "통해", "나선", "잇따라", "추가", "적극", "상황", "관련해",
}

_MAGAZINE_ACTION_RULES = {
    "field": ("현장점검", "합동점검", "점검", "현장", "방문", "찾아", "찾은", "찾다", "시찰", "살펴"),
    "meeting": ("회의", "간담회", "협의회", "토론회", "상황점검"),
    "order": ("긴급지시", "지시", "특별지시"),
    "festival": ("축제", "페스티벌", "공연", "물놀이행사"),
    "award": ("수상", "표창", "선정", "시상식", "우수기관"),
    "accident": ("사망", "부상", "사고", "화재", "붕괴", "실종"),
    "investigation": ("수사", "압수수색", "기소", "송치", "감사착수"),
    "election": ("선거", "출마", "후보", "공천"),
}

_MAGAZINE_EXCLUSIVE_ACTIONS = {"festival", "award", "accident", "investigation", "election"}


def _magazine_compact(value: object) -> str:
    return re.sub(r"[^가-힣a-z0-9]", "", str(value or "").casefold())


def _magazine_term_variants(value: object) -> set[str]:
    clean = _magazine_compact(value)
    if len(clean) < 2:
        return set()
    result = {clean}
    for suffix in (
        "으로", "에서", "에게", "까지", "부터", "관련", "대응", "대책", "정책", "사업",
        "실시", "추진", "확대", "강화", "발표", "점검", "방문", "지원", "검토",
        "와", "과", "은", "는", "이", "가", "을", "를", "의", "서",
    ):
        if clean.endswith(suffix) and len(clean) - len(suffix) >= 2:
            result.add(clean[:-len(suffix)])
    return {term for term in result if len(term) >= 2 and term not in _MAGAZINE_GENERIC_TERMS}


def _magazine_text_terms(value: object) -> set[str]:
    result: set[str] = set()
    for token in re.findall(r"[가-힣A-Za-z0-9]{2,}", str(value or "")):
        result.update(_magazine_term_variants(token))
    return result


def _magazine_location_terms(value: object) -> set[str]:
    text = str(value or "")
    result: set[str] = set()
    pattern = r"([가-힣]{2,}?)(?:특별자치도|특별자치시|광역시|특별시|시|군|구|도)(?=$|[\s,·'\"()\[\]….-])"
    for match in re.finditer(pattern, text):
        base = _magazine_compact(match.group(1))
        if len(base) >= 2 and base not in {"행정안전", "농림축산식품", "자치단체", "광역", "기초"}:
            result.add(base)
    return result


def _magazine_action_terms(title: object) -> set[str]:
    compact = _magazine_compact(title)
    return {
        action for action, terms in _MAGAZINE_ACTION_RULES.items()
        if any(_magazine_compact(term) in compact for term in terms)
    }


def _magazine_action_conflict(left: set[str], right: set[str]) -> bool:
    for action in _MAGAZINE_EXCLUSIVE_ACTIONS:
        if (action in left) != (action in right):
            return True
    return False


def _magazine_ngram_similarity(left: str, right: str, size: int = 3) -> float:
    if not left or not right:
        return 0.0
    if len(left) < size or len(right) < size:
        return 1.0 if left == right else 0.0
    left_values = {left[index:index + size] for index in range(len(left) - size + 1)}
    right_values = {right[index:index + size] for index in range(len(right) - size + 1)}
    return len(left_values & right_values) / max(1, len(left_values | right_values))


def build_magazine_issue_groups(
    articles: list[dict],
    *,
    threshold: float,
    snapshot_groups: dict[str, dict] | None = None,
) -> dict[str, dict]:
    """Build high-precision issue groups inside one magazine edition.

    The rolling similarity snapshot is useful duplicate evidence, but it is not
    allowed to join articles on a broad concept alone. Magazine issues require
    corroborating headline context such as the same place, subject and action.
    The configured magazine threshold is applied to ordinary cosine similarity,
    matching the label shown in the admin UI.
    """
    if len(articles) < 2:
        return {}
    threshold = max(0.70, min(0.99, float(threshold)))
    snapshot_groups = snapshot_groups or {}
    order = {
        str(article.get("id") or ""): index
        for index, article in enumerate(articles) if article.get("id")
    }
    article_by_id = {
        str(article.get("id") or ""): article for article in articles if article.get("id")
    }
    article_ids = list(order)

    known_locations: set[str] = set()
    known_entities: set[str] = set()
    for article in articles:
        values = article.get("entities") if isinstance(article.get("entities"), list) else []
        for value in values:
            known_locations.update(_magazine_location_terms(value))
            clean = _magazine_compact(value)
            if 2 <= len(clean) <= 40 and clean not in _MAGAZINE_GENERIC_TERMS:
                known_entities.add(clean)
        known_locations.update(_magazine_location_terms(article.get("title")))

    profiles: dict[str, dict] = {}
    for article_id, article in article_by_id.items():
        title = str(article.get("title") or "")
        summary = str(article.get("summary") or "")
        compact_title = _normalized_title(title)
        entities = article.get("entities") if isinstance(article.get("entities"), list) else []
        explicit_locations = _magazine_location_terms(title)
        for value in entities:
            explicit_locations.update(_magazine_location_terms(value))
        locations = explicit_locations | {
            value for value in known_locations if value in compact_title
        }
        grounded_entities = {
            value for value in known_entities
            if value in compact_title
            and value not in locations
            and value not in _MAGAZINE_GENERIC_TERMS
        }
        stored_concepts = (
            article.get("topic_concepts")
            if isinstance(article.get("topic_concepts"), list) else []
        )
        concepts: set[str] = set()
        for value in stored_concepts:
            variants = _magazine_term_variants(value)
            concepts.update(variants or {_magazine_compact(value)})
        title_terms = _magazine_text_terms(title)
        context_terms = title_terms | _magazine_text_terms(summary)
        for location in locations:
            title_terms = {term for term in title_terms if location not in term}
            context_terms = {term for term in context_terms if location not in term}
        title_terms.difference_update(grounded_entities)
        vector = (
            article.get("semantic_vector")
            if isinstance(article.get("semantic_vector"), list) else []
        )
        profiles[article_id] = {
            "title": compact_title,
            "title_terms": title_terms,
            "context_terms": context_terms,
            "locations": locations,
            "entities": grounded_entities,
            "concepts": {value for value in concepts if value},
            "actions": _magazine_action_terms(title),
            "vector": [float(value) for value in vector if isinstance(value, (int, float))],
        }

    related: dict[str, dict[str, float]] = {article_id: {} for article_id in article_ids}
    for left_index, left_id in enumerate(article_ids):
        left = profiles[left_id]
        for right_id in article_ids[left_index + 1:]:
            right = profiles[right_id]
            if _magazine_action_conflict(left["actions"], right["actions"]):
                continue
            shared_locations = left["locations"] & right["locations"]
            shared_entities = left["entities"] & right["entities"]
            shared_concepts = left["concepts"] & right["concepts"]
            shared_title_terms = left["title_terms"] & right["title_terms"]
            shared_context_terms = left["context_terms"] & right["context_terms"]
            shared_actions = left["actions"] & right["actions"]
            semantic = raw_semantic_similarity(left["vector"], right["vector"])
            has_semantic = bool(
                left["vector"] and right["vector"]
                and len(left["vector"]) == len(right["vector"])
            )
            exact = bool(
                len(left["title"]) >= 6 and left["title"] == right["title"]
            )
            sequence = (
                SequenceMatcher(None, left["title"], right["title"]).ratio()
                if left["title"] and right["title"] else 0.0
            )
            ngram = _magazine_ngram_similarity(left["title"], right["title"])
            left_group = snapshot_groups.get(left_id, {})
            right_group = snapshot_groups.get(right_id, {})
            same_snapshot = bool(
                left_group.get("group_id")
                and left_group.get("group_id") == right_group.get("group_id")
                and int(left_group.get("size") or 1) > 1
                and int(right_group.get("size") or 1) > 1
            )
            semantic_ok = semantic >= threshold if has_semantic else False
            lexical_strong = bool(
                exact or sequence >= 0.78 or ngram >= 0.56
                or (len(shared_title_terms) >= 3 and sequence >= 0.52)
            )
            event_context = bool(
                shared_locations and shared_actions
                and (shared_concepts or shared_title_terms or len(shared_context_terms) >= 2)
            )
            entity_context = bool(
                len(shared_entities) >= 2
                and (shared_concepts or len(shared_title_terms) >= 2)
            )
            snapshot_context = bool(
                same_snapshot and (
                    shared_locations or sequence >= 0.52
                    or (
                        shared_entities
                        and (shared_concepts or len(shared_context_terms) >= 2)
                    )
                )
            )
            is_related = bool(
                exact
                or (lexical_strong and (semantic_ok or not has_semantic))
                or (
                    event_context
                    and (
                        semantic_ok or sequence >= 0.46
                        or len(shared_title_terms) >= 2
                    )
                )
                or (entity_context and semantic >= max(0.78, threshold))
                or (snapshot_context and (semantic_ok or lexical_strong))
            )
            if not is_related:
                continue
            score = (
                (1.0 if exact else 0.0)
                + sequence * 0.28 + ngram * 0.18 + semantic * 0.24
                + min(0.12, len(shared_locations) * 0.08)
                + min(0.10, len(shared_entities) * 0.035)
                + min(0.10, len(shared_concepts) * 0.06)
                + min(0.08, len(shared_title_terms) * 0.02)
                + (0.06 if shared_actions else 0.0)
                + (0.04 if same_snapshot else 0.0)
            )
            related[left_id][right_id] = score
            related[right_id][left_id] = score

    # Pair admission above is deliberately strict. Once two articles have passed
    # those checks, preserve transitive publisher variants of the same event
    # instead of splitting them according to whichever headline became a leader.
    parent = {article_id: article_id for article_id in article_ids}

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left_id, neighbors in related.items():
        for right_id in neighbors:
            union(left_id, right_id)
    components: dict[str, list[str]] = {}
    for article_id in article_ids:
        components.setdefault(find(article_id), []).append(article_id)
    groups: list[list[str]] = []
    for component_members in components.values():
        if len(component_members) < 2:
            continue
        if len(component_members) <= 18:
            groups.append(sorted(component_members, key=lambda article_id: order[article_id]))
            continue
        # Large topical components are susceptible to one bridging headline.
        # Require dense direct support inside each published issue.
        remaining = set(component_members)
        while remaining:
            seed = max(
                remaining,
                key=lambda article_id: (
                    sum(neighbor in remaining for neighbor in related[article_id]),
                    float(article_by_id[article_id].get("score") or 0),
                    -order[article_id],
                ),
            )
            candidates = {seed} | {
                neighbor for neighbor in related[seed] if neighbor in remaining
            }
            if len(candidates) < 2:
                remaining.remove(seed)
                continue
            ratio = 0.50 if len(candidates) >= 30 else 0.35
            changed = True
            while changed and len(candidates) >= 2:
                minimum = max(1, math.ceil((len(candidates) - 1) * ratio))
                filtered = {
                    article_id for article_id in candidates
                    if sum(neighbor in candidates for neighbor in related[article_id]) >= minimum
                }
                changed = filtered != candidates
                candidates = filtered
            if len(candidates) < 2:
                remaining.remove(seed)
                continue
            group = sorted(candidates, key=lambda article_id: order[article_id])
            groups.append(group)
            remaining.difference_update(group)

    result: dict[str, dict] = {}
    for members in groups:
        representative = members[0]
        for member in members:
            best = max(
                related[member].get(other, 0.0)
                for other in members if other != member
            )
            result[member] = {
                "group_id": representative,
                "size": len(members),
                "basis": "magazine_event_context",
                "status": "finalized",
                "score": round(best * 100, 1),
            }
    return result


def build_article_similarity_groups(
    articles: list[dict],
    *,
    threshold: float,
    identity_terms: Iterable[str],
    stopwords: set[str],
    noun_extractor: Callable[[object, str, set[str], list[str]], list[str]],
    concept_inferer: Callable[[str], list[str]],
    noun_similarity_fn: Callable[[set[str], set[str], dict[str, int], int], float],
    centered_similarity_fn: Callable[[list[float], list[float], list[float]], float],
) -> dict[str, dict]:
    """Build bounded, explainable article groups for every product surface.

    Centered cosine remains the ranking signal that suppresses a shared institution
    background. A high raw cosine can only restore an edge when an exact headline,
    verified topic, or shared concept corroborates it. This keeps recurring case
    topics together without allowing generic embedding similarity to form a giant
    component.
    """
    if len(articles) < 2:
        return {}
    threshold = max(0.0, min(1.0, float(threshold)))
    identities = [str(value).strip() for value in identity_terms if str(value).strip()]
    stop = set(stopwords)
    stop.update(identities)
    topics_by_id: dict[str, set[str]] = {}
    concepts_by_id: dict[str, set[str]] = {}
    vectors_by_id: dict[str, list[float]] = {}
    published_days: dict[str, object] = {}
    exact_titles: dict[str, str] = {}
    order = {str(article.get("id")): index for index, article in enumerate(articles) if article.get("id")}

    for article in articles:
        article_id = str(article.get("id") or "")
        if not article_id:
            continue
        try:
            published_days[article_id] = datetime.fromisoformat(
                str(article.get("published_at") or article.get("first_seen_at") or "").replace("Z", "+00:00")
            ).date()
        except (TypeError, ValueError):
            pass
        text = str(article.get("_group_text") or " ".join((str(article.get("title") or ""), str(article.get("summary") or ""))))
        entities = article.get("entities") if isinstance(article.get("entities"), list) else []
        topics_by_id[article_id] = set(noun_extractor(entities, text, stop, identities))
        stored = [str(value).strip()[:60] for value in article.get("topic_concepts", []) if str(value).strip()] if isinstance(article.get("topic_concepts"), list) else []
        concept_source = " ".join((str(article.get("title") or ""), str(article.get("summary") or "")))
        compact_source = re.sub(r"\s+", "", concept_source).casefold()
        grounded_stored = []
        for value in stored:
            compact_value = re.sub(r"\s+", "", value).casefold()
            parts = [part.casefold() for part in re.findall(r"[가-힣A-Za-z0-9]{2,}", value)]
            if compact_value in compact_source or any(len(part) >= 3 and part not in {"관련", "대응", "정책", "지원", "추진", "확대", "강화"} and part in compact_source for part in parts):
                grounded_stored.append(value)
        # Inferred concepts augment stored labels. Previously they were only used
        # when the model returned no concepts, hiding stable families such as 폭염,
        # 햇빛소득마을, 적극행정 and 수사기관 개혁.
        inferred = [value for value in concept_inferer(concept_source) if not str(value).startswith(EVENT_CONCEPT_PREFIX)]
        # A precise event must be explicit in the headline. Summary mentions are
        # useful semantic context, but cannot promote a general story into an event.
        concepts_by_id[article_id] = set(dict.fromkeys([*grounded_stored, *inferred, *inferred_editorial_events(article.get("title"))]))
        vector = article.get("semantic_vector") if isinstance(article.get("semantic_vector"), list) else []
        if vector and all(isinstance(value, (int, float)) for value in vector):
            vectors_by_id[article_id] = [float(value) for value in vector]
        exact_titles[article_id] = _normalized_title(article.get("title"))

    ids = list(order)
    node_count = len(ids)
    topic_frequency: dict[str, int] = {}
    concept_frequency: dict[str, int] = {}
    for terms in topics_by_id.values():
        for term in terms:
            topic_frequency[term] = topic_frequency.get(term, 0) + 1
    for concepts in concepts_by_id.values():
        for concept in concepts:
            concept_frequency[concept] = concept_frequency.get(concept, 0) + 1

    dimensions = {len(vector) for vector in vectors_by_id.values()}
    semantic_vectors = vectors_by_id if len(dimensions) == 1 and len(vectors_by_id) >= 2 else {}
    centroid: list[float] = []
    if semantic_vectors:
        length = next(iter(dimensions))
        centroid = [sum(vector[index] for vector in semantic_vectors.values()) / len(semantic_vectors) for index in range(length)]

    semantic_min = threshold
    raw_min = max(0.86, threshold)
    concept_semantic_min = max(0.48, semantic_min - 0.08)
    direct_noun_min = 0.42 if node_count >= 35 else 0.36
    fallback_noun_min = 0.58 if node_count >= 35 else 0.50
    distinctive_limit = max(2, math.ceil(node_count * 0.35))
    candidate_edges: list[dict] = []

    # Every accepted edge below must share a concept, at least two verified
    # topics, or an exact normalized title. Build only those candidate pairs;
    # comparing every article with every other article made a time-window
    # snapshot prohibitively expensive as daily volume increased.
    candidate_pairs: set[tuple[str, str]] = set()
    topic_pair_hits: dict[tuple[str, str], int] = {}
    concept_members: dict[str, list[str]] = {}
    topic_members: dict[str, list[str]] = {}
    title_members: dict[str, list[str]] = {}
    for article_id in ids:
        for concept in concepts_by_id.get(article_id, set()):
            concept_members.setdefault(concept, []).append(article_id)
        for topic in topics_by_id.get(article_id, set()):
            topic_members.setdefault(topic, []).append(article_id)
        title = exact_titles.get(article_id, "")
        if len(title) >= 6:
            title_members.setdefault(title, []).append(article_id)
    for members in concept_members.values():
        for left_index, left_id in enumerate(members):
            for right_id in members[left_index + 1:]:
                candidate_pairs.add(tuple(sorted((left_id, right_id))))
    for members in topic_members.values():
        for left_index, left_id in enumerate(members):
            for right_id in members[left_index + 1:]:
                key = tuple(sorted((left_id, right_id)))
                topic_pair_hits[key] = topic_pair_hits.get(key, 0) + 1
    candidate_pairs.update(key for key, hits in topic_pair_hits.items() if hits >= 2)
    for members in title_members.values():
        for left_index, left_id in enumerate(members):
            for right_id in members[left_index + 1:]:
                candidate_pairs.add(tuple(sorted((left_id, right_id))))

    for left_id, right_id in sorted(candidate_pairs, key=lambda pair: (order.get(pair[0], 999999), order.get(pair[1], 999999))):
            left_topics = topics_by_id.get(left_id, set())
            right_topics = topics_by_id.get(right_id, set())
            shared_topics = left_topics & right_topics
            shared_concepts = concepts_by_id.get(left_id, set()) & concepts_by_id.get(right_id, set())
            left_events = {value for value in concepts_by_id.get(left_id, set()) if value.startswith(EVENT_CONCEPT_PREFIX)}
            right_events = {value for value in concepts_by_id.get(right_id, set()) if value.startswith(EVENT_CONCEPT_PREFIX)}
            if (left_events or right_events) and not (left_events & right_events):
                continue
            shared_events = left_events & right_events
            distinctive_topics = {term for term in shared_topics if topic_frequency.get(term, node_count) <= distinctive_limit}
            distinctive_concepts = {term for term in shared_concepts if concept_frequency.get(term, node_count) <= distinctive_limit}
            noun_similarity = noun_similarity_fn(left_topics, right_topics, topic_frequency, max(1, node_count))
            centered = raw = 0.0
            has_semantic = bool(centroid and left_id in semantic_vectors and right_id in semantic_vectors)
            if has_semantic:
                centered = centered_similarity_fn(semantic_vectors[left_id], semantic_vectors[right_id], centroid)
                raw = raw_semantic_similarity(semantic_vectors[left_id], semantic_vectors[right_id])
            exact = bool(len(exact_titles.get(left_id, "")) >= 6 and exact_titles[left_id] == exact_titles.get(right_id, ""))
            exact_only_evidence = exact and not (shared_topics or shared_concepts)
            raw_supported = has_semantic and raw >= raw_min and bool(
                distinctive_concepts or len(distinctive_topics) >= 2 or exact_only_evidence
            )
            left_day, right_day = published_days.get(left_id), published_days.get(right_id)
            event_supported = bool(shared_events) and (not left_day or not right_day or abs((left_day - right_day).days) <= 2)
            if left_day and right_day and abs((left_day - right_day).days) > 14 and max(centered, raw if raw_supported else 0.0) < 0.88:
                continue
            # Embeddings alone are not an editorial fact. Require a shared topic or
            # concept so institution-wide background similarity cannot join events.
            semantic_strong = has_semantic and centered >= semantic_min and bool(shared_concepts or len(shared_topics) >= 2)
            concept_supported = bool(shared_concepts) and (
                (has_semantic and centered >= concept_semantic_min) or noun_similarity >= direct_noun_min or raw_supported
            )
            direct_supported = len(shared_topics) >= 2 and (
                (has_semantic and centered >= max(0.34, semantic_min - 0.18) and noun_similarity >= 0.22)
                or (not has_semantic and noun_similarity >= fallback_noun_min)
                or noun_similarity >= max(0.50, direct_noun_min + 0.10)
                or raw_supported
            )
            if not (event_supported or exact or semantic_strong or concept_supported or direct_supported):
                continue
            if semantic_strong and not (shared_topics or shared_concepts):
                basis = "semantic"
            elif has_semantic:
                basis = "hybrid"
            else:
                basis = "keyword"
            raw_signal = max(0.0, min(1.0, (raw - 0.80) / 0.20)) if raw_supported else 0.0
            weight = max(noun_similarity, 0.98 if event_supported else 0.0, 1.0 if exact_only_evidence else 0.0, 0.62 if concept_supported else 0.0, centered if has_semantic else 0.0, raw_signal)
            candidate_edges.append({
                "source": left_id, "target": right_id, "weight": round(weight, 4), "basis": basis,
                "status": "finalized" if has_semantic or event_supported else "temporary",
                "noun_similarity": round(noun_similarity, 4), "semantic_similarity": round(centered, 4),
                "raw_semantic_similarity": round(raw, 4),
                "shared_topics": sorted(shared_topics, key=lambda term: (-len(term), term))[:5],
                "shared_concepts": sorted(shared_concepts)[:6],
                "shared_events": sorted(shared_events),
                "rank_score": round(max(0.0, centered) + raw_signal * 0.35 + noun_similarity * 0.25 + (0.08 if concept_supported else 0.0) + (0.2 if exact_only_evidence else 0.0), 4),
                "relation_level": "direct_topic" if event_supported else ("abstract_topic" if semantic_strong or concept_supported else "direct_topic"),
            })

    if not candidate_edges:
        return {}
    edge_lookup = {tuple(sorted((edge["source"], edge["target"]))): edge for edge in candidate_edges}
    selected_keys = {key for key, edge in edge_lookup.items() if edge["relation_level"] == "direct_topic" or edge["weight"] >= 0.99}
    concept_groups: dict[str, set[str]] = {}
    for article_id, concepts in concepts_by_id.items():
        for concept in concepts:
            concept_groups.setdefault(concept, set()).add(article_id)
    for members in concept_groups.values():
        if len(members) < 2:
            continue
        candidates = []
        for article_id in sorted(members):
            scores = [edge_lookup[key]["rank_score"] for other_id in members if other_id != article_id if (key := tuple(sorted((article_id, other_id)))) in edge_lookup]
            candidates.append((sum(scores) / max(1, len(scores)), article_id))
        hub_id = max(candidates, key=lambda item: (item[0], -order.get(item[1], 999999)))[1]
        for article_id in members:
            key = tuple(sorted((hub_id, article_id)))
            if article_id != hub_id and key in edge_lookup:
                selected_keys.add(key)
    semantic_only = [edge for edge in candidate_edges if not edge["shared_concepts"] and edge["relation_level"] == "abstract_topic" and edge["semantic_similarity"] >= semantic_min]
    for article_id in ids:
        neighbors = sorted((edge for edge in semantic_only if article_id in (edge["source"], edge["target"])), key=lambda edge: (-edge["rank_score"], edge["source"], edge["target"]))[:1]
        selected_keys.update(tuple(sorted((edge["source"], edge["target"]))) for edge in neighbors)

    parent = {article_id: article_id for article_id in ids}
    component_size = {article_id: 1 for article_id in ids}
    degree: dict[str, int] = {}
    group_edges: list[dict] = []

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return
        if component_size[left_root] < component_size[right_root]:
            left_root, right_root = right_root, left_root
        parent[right_root] = left_root
        component_size[left_root] += component_size[right_root]

    max_component = 14 if node_count >= 45 else (12 if node_count >= 25 else 10)
    degree_limit = 2 if node_count >= 25 else 3
    edge_limit = min(70, max(16, int(node_count * 1.15)))
    general_edge_count = 0
    proposed = sorted((edge_lookup[key] for key in selected_keys), key=lambda edge: (-bool(edge.get("shared_events")), -edge["weight"], -edge.get("raw_semantic_similarity", 0), -edge.get("semantic_similarity", 0), -edge.get("noun_similarity", 0), order.get(edge["source"], 999999), order.get(edge["target"], 999999)))
    for edge in proposed:
        source, target = edge["source"], edge["target"]
        duplicate = float(edge.get("weight") or 0) >= 0.94 and max(float(edge.get("semantic_similarity") or 0), float(edge.get("raw_semantic_similarity") or 0)) >= 0.70
        same_event = bool(edge.get("shared_events"))
        if not same_event and general_edge_count >= edge_limit:
            break
        current_degree_limit = max(node_count, degree_limit) if same_event else degree_limit + (1 if duplicate else 0)
        if degree.get(source, 0) >= current_degree_limit or degree.get(target, 0) >= current_degree_limit:
            continue
        source_root, target_root = find(source), find(target)
        if source_root == target_root:
            continue
        merged_size = component_size[source_root] if source_root == target_root else component_size[source_root] + component_size[target_root]
        current_max_component = min(120, node_count) if same_event else max_component
        if source_root != target_root and merged_size > current_max_component:
            continue
        group_edges.append(edge)
        degree[source] = degree.get(source, 0) + 1
        degree[target] = degree.get(target, 0) + 1
        union(source, target)
        general_edge_count += 0 if same_event else 1

    components: dict[str, list[str]] = {}
    for article_id in ids:
        components.setdefault(find(article_id), []).append(article_id)

    # A degree cap can leave one small shard beside a coherent bundle. Perform one
    # conservative component-level pass, requiring both semantics and shared
    # editorial evidence. This retains the former anti-chain behavior.
    attachment_max_component = min(18, max_component + 4)

    def component_profile(members: list[str]) -> dict[str, object]:
        topics: set[str] = set()
        concepts: set[str] = set()
        vectors: list[list[float]] = []
        dates = []
        for member in members:
            topics.update(topics_by_id.get(member, set()))
            concepts.update(concepts_by_id.get(member, set()))
            if member in semantic_vectors:
                vectors.append(semantic_vectors[member])
            if member in published_days:
                dates.append(published_days[member])
        vector: list[float] = []
        if vectors and len(vectors) == len(members) and len({len(value) for value in vectors}) == 1:
            vector = [sum(value[index] for value in vectors) / len(vectors) for index in range(len(vectors[0]))]
        return {"members": members, "topics": topics, "concepts": concepts, "vector": vector, "dates": dates}

    profiles = [(root, component_profile(members)) for root, members in components.items()]
    profile_by_root = dict(profiles)
    component_pairs: set[tuple[str, str]] = set()
    component_topic_hits: dict[tuple[str, str], int] = {}
    component_concepts: dict[str, list[str]] = {}
    component_topics: dict[str, list[str]] = {}
    for root, profile in profiles:
        for concept in profile["concepts"]:
            component_concepts.setdefault(str(concept), []).append(root)
        for topic in profile["topics"]:
            component_topics.setdefault(str(topic), []).append(root)
    for roots in component_concepts.values():
        for left_index, left_root in enumerate(roots):
            for right_root in roots[left_index + 1:]:
                component_pairs.add(tuple(sorted((left_root, right_root))))
    for roots in component_topics.values():
        for left_index, left_root in enumerate(roots):
            for right_root in roots[left_index + 1:]:
                key = tuple(sorted((left_root, right_root)))
                component_topic_hits[key] = component_topic_hits.get(key, 0) + 1
    component_pairs.update(key for key, hits in component_topic_hits.items() if hits >= 2)
    attachment_candidates: list[dict] = []
    attachment_semantic_min = max(0.72, semantic_min + 0.08)
    for left_root, right_root in sorted(component_pairs):
            left_profile = profile_by_root[left_root]
            left_members = left_profile["members"]
            right_profile = profile_by_root[right_root]
            right_members = right_profile["members"]
            if min(len(left_members), len(right_members)) > 3 or len(left_members) + len(right_members) > attachment_max_component:
                continue
            left_vector, right_vector = left_profile["vector"], right_profile["vector"]
            if not centroid or not left_vector or not right_vector:
                continue
            centered = centered_similarity_fn(left_vector, right_vector, centroid)
            raw = raw_semantic_similarity(left_vector, right_vector)
            shared_topics = left_profile["topics"] & right_profile["topics"]
            shared_concepts = left_profile["concepts"] & right_profile["concepts"]
            left_events = {value for value in left_profile["concepts"] if str(value).startswith(EVENT_CONCEPT_PREFIX)}
            right_events = {value for value in right_profile["concepts"] if str(value).startswith(EVENT_CONCEPT_PREFIX)}
            if (left_events or right_events) and not (left_events & right_events):
                continue
            distinctive_topic_count = sum(topic_frequency.get(term, node_count) <= distinctive_limit for term in shared_topics)
            distinctive = distinctive_topic_count >= 2 or any(concept_frequency.get(term, node_count) <= distinctive_limit for term in shared_concepts)
            raw_supported = raw >= raw_min and distinctive
            if centered < attachment_semantic_min and not raw_supported:
                continue
            noun_similarity = noun_similarity_fn(left_profile["topics"], right_profile["topics"], topic_frequency, max(1, node_count))
            if not (shared_concepts or len(shared_topics) >= 2):
                continue
            left_dates, right_dates = left_profile["dates"], right_profile["dates"]
            semantic_for_date = max(centered, raw if raw_supported else 0.0)
            if left_dates and right_dates and min(abs((left_day - right_day).days) for left_day in left_dates for right_day in right_dates) > 14 and semantic_for_date < 0.90:
                continue
            if len(left_members) <= len(right_members):
                small_root, large_root = left_root, right_root
            else:
                small_root, large_root = right_root, left_root
            raw_signal = max(0.0, min(1.0, (raw - 0.80) / 0.20)) if raw_supported else 0.0
            attachment_candidates.append({
                "source": min(left_members, key=lambda article_id: order.get(article_id, 999999)),
                "target": min(right_members, key=lambda article_id: order.get(article_id, 999999)),
                "small_root": small_root, "large_root": large_root,
                "weight": round(max(centered, raw_signal, noun_similarity), 4),
                "basis": "hybrid", "status": "finalized",
                "noun_similarity": round(noun_similarity, 4), "semantic_similarity": round(centered, 4),
                "raw_semantic_similarity": round(raw, 4),
                "shared_topics": sorted(shared_topics, key=lambda term: (-len(term), term))[:5],
                "shared_concepts": sorted(shared_concepts)[:6],
            })
    attached_roots: set[str] = set()
    for edge in sorted(attachment_candidates, key=lambda item: (-item["weight"], -item["semantic_similarity"], -item["noun_similarity"], order.get(item["source"], 999999), order.get(item["target"], 999999))):
        if edge["small_root"] in attached_roots or edge["large_root"] in attached_roots:
            continue
        source_root, target_root = find(edge["source"]), find(edge["target"])
        if source_root == target_root or component_size[source_root] + component_size[target_root] > attachment_max_component:
            continue
        group_edges.append(edge)
        union(edge["source"], edge["target"])
        attached_roots.update((edge["small_root"], edge["large_root"]))
    components = {}
    for article_id in ids:
        components.setdefault(find(article_id), []).append(article_id)

    result: dict[str, dict] = {}
    edges_by_node: dict[str, list[dict]] = {}
    for edge in group_edges:
        edges_by_node.setdefault(edge["source"], []).append(edge)
        edges_by_node.setdefault(edge["target"], []).append(edge)
    for members in components.values():
        if len(members) < 2:
            continue
        representative = min(members, key=lambda article_id: order.get(article_id, 999999))
        member_edges = [edge for edge in group_edges if edge["source"] in members and edge["target"] in members]
        best = max(member_edges, key=lambda edge: (edge["weight"], edge.get("raw_semantic_similarity", 0), edge.get("semantic_similarity", 0), edge.get("noun_similarity", 0))) if member_edges else {}
        basis_order = {"semantic": 3, "hybrid": 2, "keyword": 1}
        basis = max((edge.get("basis", "keyword") for edge in member_edges), key=lambda value: basis_order.get(value, 0), default="keyword")
        finalized = bool(member_edges) and all(edge.get("status") == "finalized" for edge in member_edges) and all(member in semantic_vectors for member in members)
        for member in members:
            nearest = max(edges_by_node.get(member, []), key=lambda edge: edge["weight"], default=best)
            evidence = nearest or best
            semantic_score = max(float(evidence.get("semantic_similarity") or 0), float(evidence.get("raw_semantic_similarity") or 0))
            result[member] = {
                "group_id": representative, "size": len(members), "basis": basis,
                "status": "finalized" if finalized else "temporary",
                "score": round(float(evidence.get("weight") or 0) * 100, 1),
                "semantic_score": round(semantic_score * 100, 1),
                "noun_score": round(float(evidence.get("noun_similarity") or 0) * 100, 1),
                "topics": evidence.get("shared_topics", []), "concepts": evidence.get("shared_concepts", []),
            }
    return result
