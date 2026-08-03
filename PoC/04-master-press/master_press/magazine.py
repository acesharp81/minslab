from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta

from .scoring import cosine_similarity
from .similarity import build_magazine_issue_groups
from .storage import KST, Store, now_iso

SLOT_LABELS = {"morning": "모닝 브리핑", "lunch": "커피탐 포스트", "evening": "퇴근 메이트", "daily": "DAILY"}
PUBLISHED_SLOTS = ("morning", "lunch", "evening")
SLOT_HOURS = {"morning": 7, "lunch": 12, "evening": 18, "daily": 7}


def edition_title(organization_name: str, slot: str) -> str:
    return f"{str(organization_name or '기관').strip()} CaseON {SLOT_LABELS.get(slot, slot.upper())}"

def edition_window(slot: str, reference: datetime | None = None) -> tuple[str, str, str]:
    current = (reference or datetime.now(KST)).astimezone(KST)
    end = current.replace(hour=SLOT_HOURS.get(slot, -1), minute=0, second=0, microsecond=0)
    if slot == "morning":
        start = end - timedelta(days=1)
    elif slot in {"lunch", "evening"}:
        start = end - timedelta(hours=5 if slot == "lunch" else 6)
    elif slot == "daily":
        start = end - timedelta(days=1)
    else:
        raise ValueError("매거진 회차는 morning, lunch, evening, daily 중 하나여야 합니다.")
    return end.date().isoformat(), start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")

class MagazinePublisher:
    def __init__(self, store: Store):
        self.store = store
        self.store.ensure_magazine_schema()
        self.deferred: list[dict] = []

    def window_readiness(self, organization_id: str, window_start: str, window_end: str, reference: datetime | None = None) -> dict:
        status = self.store.magazine_window_readiness(organization_id, window_start, window_end)
        try:
            grace_minutes = max(0, min(60, int(self.store.get_setting("magazine_completion_grace_minutes", "5") or 5)))
        except (TypeError, ValueError):
            grace_minutes = 5
        current = (reference or datetime.now(KST)).astimezone(KST)
        end = datetime.fromisoformat(str(window_end).replace("Z", "+00:00")).astimezone(KST)
        eligible_at = end + timedelta(minutes=grace_minutes)
        status.update({"grace_minutes": grace_minutes, "eligible_at": eligible_at.isoformat(timespec="seconds")})
        status["ready"] = bool(status.get("ready") and current >= eligible_at)
        if current < eligible_at:
            status["reason"] = "completion_grace"
        elif not status["ready"]:
            status["reason"] = "pipeline_pending"
        else:
            status["reason"] = "ready"
        return status

    def publish_for_slot(self, slot: str, reference: datetime | None = None, force: bool = False) -> list[dict]:
        edition_date, window_start, window_end = edition_window(slot, reference)
        current = (reference or datetime.now(KST)).astimezone(KST)
        editions: list[dict] = []
        self.deferred = []
        for organization in self.store.list_organizations(active_only=True):
            organization_id = str(organization["id"])
            if not force and self.store.magazine_edition_exists(organization_id, edition_date, slot):
                continue
            if not force:
                readiness = self.window_readiness(organization_id, window_start, window_end, current)
                if not readiness["ready"]:
                    self.deferred.append({"organization_id": organization_id, "slot": slot, **readiness})
                    continue
            editions.append(self.publish(organization_id, edition_date, slot, window_start, window_end, force))
        return editions

    def publish_due(self, reference: datetime | None = None) -> list[dict]:
        current = (reference or datetime.now(KST)).astimezone(KST)
        editions: list[dict] = []
        self.deferred = []
        for slot in PUBLISHED_SLOTS:
            hour = SLOT_HOURS[slot]
            if current.hour < hour:
                continue
            edition_date, window_start, window_end = edition_window(slot, current)
            for organization in self.store.list_organizations(active_only=True):
                if self.store.magazine_edition_exists(organization["id"], edition_date, slot):
                    continue
                readiness = self.window_readiness(organization["id"], window_start, window_end, current)
                if not readiness["ready"]:
                    self.deferred.append({"organization_id": organization["id"], "slot": slot, **readiness})
                    continue
                editions.append(self.publish(
                    organization["id"], edition_date, slot, window_start, window_end
                ))
        return editions

    def publish(self, organization_id: str, edition_date: str, slot: str, window_start: str, window_end: str, force: bool = False) -> dict:
        organization = self.store.get_organization(organization_id)
        if not organization: raise ValueError("기관을 찾지 못했습니다.")
        catalog = [{"id": item["id"], "name": item["name"]} for item in self.store.list_cases_for_organization(organization_id, active_only=True)]
        with self.store.connect() as connection:
            existing = connection.execute("SELECT id FROM magazine_editions WHERE organization_id=? AND edition_date=? AND edition_slot=?", (organization_id, edition_date, slot)).fetchone()
            if existing and not force: return self._edition_from_connection(connection, str(existing["id"])) or {}
            rows = connection.execute("""SELECT a.id article_id,a.title,a.original_url,a.publisher,a.image_url,a.published_at,a.first_seen_at,aa.summary,aa.tone,aa.article_type,ce.case_id,c.name case_name,ce.final_score,CASE WHEN COALESCE(sg.group_size,1)>1 AND COALESCE(sg.group_id,'')<>'' THEN sg.group_id ELSE 'article:'||a.id END issue_key FROM article_case_processing_flags acpf JOIN case_evaluations ce ON ce.id=acpf.evaluation_id JOIN articles a ON a.id=acpf.article_id JOIN article_analyses aa ON aa.id=acpf.analysis_id JOIN cases c ON c.id=ce.case_id LEFT JOIN article_similarity_groups sg ON sg.article_id=a.id WHERE c.organization_id=? AND ce.status='completed' AND ce.decision='send' AND COALESCE(a.published_at,a.first_seen_at)>=? AND COALESCE(a.published_at,a.first_seen_at)<? ORDER BY ce.final_score DESC,COALESCE(a.published_at,a.first_seen_at) DESC""", (organization_id, window_start, window_end)).fetchall()
            article_ids = [str(row["article_id"]) for row in rows]
            press_by_article: dict[str, list[dict]] = {}
            if article_ids:
                marks = ",".join("?" for _ in article_ids)
                press_rows = connection.execute(f"SELECT m.article_id,p.title,p.canonical_url,p.published_at,m.similarity_score FROM article_press_release_matches m JOIN press_releases p ON p.id=m.press_release_id WHERE m.article_id IN ({marks}) AND m.is_related=1 ORDER BY m.article_id,m.similarity_score DESC", article_ids).fetchall()
                for row in press_rows: press_by_article.setdefault(str(row["article_id"]), []).append({"title": row["title"], "url": row["canonical_url"], "published_at": row["published_at"], "similarity_score": round(float(row["similarity_score"] or 0), 1)})
            members: dict[str, dict] = {}
            for row in rows:
                article_id = str(row["article_id"])
                member = members.setdefault(article_id, {"article_id": article_id, "issue_key": "article:" + article_id, "title": row["title"], "summary": row["summary"], "publisher": row["publisher"], "image_url": row["image_url"] or "", "tone": row["tone"], "article_type": row["article_type"], "published_at": row["published_at"] or row["first_seen_at"], "original_url": row["original_url"], "case_matches": [], "related_press_releases": press_by_article.get(article_id, [])[:3], "score": 0.0})
                member["score"] = max(float(member["score"]), float(row["final_score"] or 0))
                member["case_matches"].append({"id": row["case_id"], "name": row["case_name"], "score": round(float(row["final_score"] or 0), 1)})
            items = self._finalize_issue_keys(list(members.values()), organization_id)
            # DAILY 화두는 같은 시간창에 실제 지면으로 확정된 유사기사 묶음에서
            # 만든다. 분석 엔터티가 비어 있는 과거 기사도 제목에는 남아 있으므로,
            # 빈 화두나 지면 밖 화두를 만들지 않는다.
            daily_topics = self._daily_topics(items) if slot in {"daily", "morning"} else []
            items = self._order_issue_items(items)
            generated, edition_id = now_iso(), str(existing["id"]) if existing else str(uuid.uuid4())
            values = (organization["name"], window_start, window_end, json.dumps(catalog, ensure_ascii=False), json.dumps(daily_topics, ensure_ascii=False), len({item["issue_key"] for item in items}), len(items), generated, generated)
            if existing:
                connection.execute("DELETE FROM magazine_issue_members WHERE edition_id=?", (edition_id,))
                connection.execute("UPDATE magazine_editions SET organization_name=?,window_start_at=?,window_end_at=?,case_catalog=?,daily_topics=?,issue_count=?,article_count=?,status='published',generated_at=?,updated_at=? WHERE id=?", (*values, edition_id))
            else:
                connection.execute("INSERT INTO magazine_editions(id,organization_id,organization_name,edition_date,edition_slot,window_start_at,window_end_at,case_catalog,daily_topics,issue_count,article_count,status,generated_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (edition_id, organization_id, organization["name"], edition_date, slot, window_start, window_end, json.dumps(catalog, ensure_ascii=False), json.dumps(daily_topics, ensure_ascii=False), len({item["issue_key"] for item in items}), len(items), "published", generated, generated))
            for rank, item in enumerate(items, 1): connection.execute("INSERT INTO magazine_issue_members(edition_id,article_id,issue_key,rank,title,summary,publisher,tone,article_type,published_at,original_url,image_url,case_matches,related_press_releases,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (edition_id, item["article_id"], item["issue_key"], rank, item["title"], item["summary"], item["publisher"], item["tone"], item["article_type"], item["published_at"], item["original_url"], item["image_url"], json.dumps(item["case_matches"], ensure_ascii=False), json.dumps(item["related_press_releases"], ensure_ascii=False), generated))
            return self._edition_from_connection(connection, edition_id) or {}

    @staticmethod
    def _json_list(value: object) -> list:
        if isinstance(value, list):
            return value
        try:
            decoded = json.loads(str(value or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        return decoded if isinstance(decoded, list) else []

    @staticmethod
    def _order_issue_items(items: list[dict]) -> list[dict]:
        """Order issues by article count, then unique linked press releases."""
        buckets: dict[str, list[dict]] = {}
        for item in items:
            key = str(item.get("issue_key") or "article:" + str(item.get("article_id") or ""))
            buckets.setdefault(key, []).append(item)

        def press_keys(members: list[dict]) -> set[str]:
            result: set[str] = set()
            for member in members:
                for release in member.get("related_press_releases") or []:
                    url = str(release.get("url") or "").strip()
                    title = str(release.get("title") or "").strip()
                    key = url or ("title:" + title if title else "")
                    if key:
                        result.add(key)
            return result

        ordered_buckets = sorted(
            buckets.values(),
            key=lambda members: (
                -len(members),
                -len(press_keys(members)),
                -max(float(member.get("score") or 0) for member in members),
                -max(bool(member.get("image_url")) for member in members),
                max(str(member.get("published_at") or "") for member in members),
                min(str(member.get("article_id") or "") for member in members),
            ),
        )
        ordered: list[dict] = []
        for members in ordered_buckets:
            members.sort(
                key=lambda item: (
                    -float(item.get("score") or 0),
                    -bool(item.get("image_url")),
                    -len(str(item.get("summary") or "")),
                    str(item.get("published_at") or ""),
                    str(item.get("article_id") or ""),
                )
            )
            ordered.extend(members)
        return ordered

    def _finalize_issue_keys(self, items: list[dict], organization_id: str) -> list[dict]:
        """Build high-precision issue keys inside the current edition scope."""
        for item in items:
            item["issue_key"] = "article:" + str(item.get("article_id") or "")
        article_ids = [str(item.get("article_id") or "") for item in items if item.get("article_id")]
        if len(article_ids) < 2:
            return items
        marks = ",".join("?" for _ in article_ids)
        with self.store.connect() as connection:
            rows = connection.execute(
                f"""SELECT aa.article_id,aa.entities,aa.topic_concepts,ae.vector
                       FROM article_processing_flags apf
                       JOIN article_analyses aa ON aa.id=apf.analysis_id
                       LEFT JOIN article_embeddings ae ON ae.article_analysis_id=aa.id AND ae.status='completed'
                      WHERE aa.article_id IN ({marks}) AND aa.organization_id=? AND aa.status='completed'""",
                (*article_ids, organization_id),
            ).fetchall()
        signals = {str(row["article_id"]): dict(row) for row in rows}
        snapshot_groups = self.store.article_similarity_groups(article_ids)
        try:
            threshold = float(self.store.get_setting("magazine_similarity_threshold", "90")) / 100.0
        except (TypeError, ValueError):
            threshold = 0.90
        group_inputs = []
        for item in items:
            article_id = str(item.get("article_id") or "")
            row = signals.get(article_id, {})
            group_inputs.append({
                "id": article_id,
                "title": item.get("title") or "",
                "summary": item.get("summary") or "",
                "published_at": item.get("published_at") or "",
                "score": item.get("score") or 0,
                "entities": self._json_list(row.get("entities")),
                "topic_concepts": self._json_list(row.get("topic_concepts")),
                "semantic_vector": self._json_list(row.get("vector")),
            })
        groups = build_magazine_issue_groups(
            group_inputs, threshold=threshold, snapshot_groups=snapshot_groups
        )
        for item in items:
            article_id = str(item.get("article_id") or "")
            group = groups.get(article_id, {})
            if group.get("group_id") and int(group.get("size") or 1) > 1:
                item["issue_key"] = "issue:" + str(group["group_id"])
        return items

    def _legacy_recalculate_issue_keys(self, items: list[dict], organization_id: str) -> list[dict]:
        """Assign issue keys with the same engine used by dashboard and neural graph."""
        for item in items:
            item["issue_key"] = "article:" + str(item.get("article_id") or "")
        article_ids = [str(item.get("article_id") or "") for item in items if item.get("article_id")]
        if len(article_ids) < 2:
            return items
        marks = ",".join("?" for _ in article_ids)
        with self.store.connect() as connection:
            rows = connection.execute(
                f"""SELECT a.id article_id,aa.entities,aa.topic_concepts,ae.vector
                       FROM articles a JOIN article_analyses aa ON aa.article_id=a.id
                       LEFT JOIN article_embeddings ae ON ae.article_analysis_id=aa.id AND ae.status='completed'
                      WHERE a.id IN ({marks}) AND aa.organization_id=? AND aa.status='completed'""",
                (*article_ids, organization_id),
            ).fetchall()
        signals = {str(row["article_id"]): dict(row) for row in rows}
        group_inputs = []
        for item in items:
            article_id = str(item.get("article_id") or "")
            row = signals.get(article_id, {})
            group_inputs.append({
                "id": article_id,
                "title": item.get("title") or "",
                "summary": item.get("summary") or "",
                "published_at": item.get("published_at") or "",
                "entities": self._json_list(row.get("entities")),
                "topic_concepts": self._json_list(row.get("topic_concepts")),
                "semantic_vector": self._json_list(row.get("vector")),
                "_group_text": " ".join((str(item.get("title") or ""), str(item.get("summary") or ""))),
            })
        try:
            threshold = float(self.store.get_setting("magazine_similarity_threshold", "90")) / 100.0
        except (TypeError, ValueError):
            threshold = 0.90
        groups = self.store._dashboard_article_groups(
            group_inputs, organization_id=organization_id, threshold_override=threshold
        )
        for item in items:
            article_id = str(item.get("article_id") or "")
            group = groups.get(article_id, {})
            if group.get("group_id") and int(group.get("size") or 1) > 1:
                item["issue_key"] = "issue:" + str(group["group_id"])
        return items

    def _legacy_finalize_issue_keys(self, items: list[dict], organization_id: str) -> list[dict]:
        """Group an edition with stored analysis signals and no new model calls.

        Candidate pairs need corroborating editorial evidence. Clusters are built
        around a directly connected leader, so weak A-B-C chains cannot collapse
        unrelated events. Groups of 30 or more receive a stricter cohesion pass.
        """
        for item in items:
            item["issue_key"] = "article:" + str(item.get("article_id") or "")
        by_id = {str(item.get("article_id") or ""): item for item in items if item.get("article_id")}
        article_ids = list(by_id)
        if len(article_ids) < 2:
            return items
        marks = ",".join("?" for _ in article_ids)
        with self.store.connect() as connection:
            rows = connection.execute(
                f"""SELECT a.id article_id,aa.entities,aa.topic_concepts,ae.vector
                       FROM articles a JOIN article_analyses aa ON aa.article_id=a.id
                       LEFT JOIN article_embeddings ae ON ae.article_analysis_id=aa.id AND ae.status='completed'
                      WHERE a.id IN ({marks}) AND aa.organization_id=? AND aa.status='completed'""",
                (*article_ids, organization_id),
            ).fetchall()

        generic = {
            "정부", "정책", "행정안전부", "행안부", "기사", "보도", "관련", "이번", "주요",
            "전국", "지원", "추진", "확대", "강화", "대응", "운영", "개최", "발표", "점검",
            "현장", "안전", "관리", "사업", "지역", "시설", "시스템", "계획", "업무", "기관",
            "관계", "대책", "위해", "통해", "대한", "위한", "있는", "한다",
            # These broad actors/topics recur across otherwise unrelated ministry
            # stories.  They are useful search terms, but unsafe issue anchors.
            "ai", "인공지능", "로봇", "디지털", "데이터", "공공데이터", "공공부문",
            "재난", "재난대응", "호우재난대응", "재난환경", "안전관리",
            "수사기관개혁사법제도", "윤호중", "장관", "휴가철", "여름", "폭염",
        }

        def expand_term(value: object) -> set[str]:
            clean = re.sub(r"[^가-힣a-z0-9]", "", str(value or "").casefold())
            if len(clean) < 2 or clean in generic:
                return set()
            result = {clean}
            if any(alias in clean for alias in ("제주특별자치도지사", "제주도지사", "제주지사")):
                result.add("제주지사")
            if "경찰차량" in clean or "경찰차" in clean:
                result.add("경찰차")
            if "전기차" in clean or "전기수소차" in clean:
                result.add("전기차")
            if "수소차" in clean or "전기수소차" in clean:
                result.add("수소차")
            without_policy = clean.removesuffix("정책")
            if len(without_policy) >= 2:
                result.add(without_policy)
            return result

        analysis = {str(row["article_id"]): dict(row) for row in rows}
        stored_entities = {
            article_id: set().union(*(expand_term(value) for value in self._json_list((analysis.get(article_id) or {}).get("entities"))))
            for article_id in article_ids
        }
        stored_concepts = {
            article_id: set().union(*(expand_term(value) for value in self._json_list((analysis.get(article_id) or {}).get("topic_concepts"))))
            for article_id in article_ids
        }
        known_entities = set().union(*stored_entities.values()) if stored_entities else set()
        known_concepts = set().union(*stored_concepts.values()) if stored_concepts else set()
        texts = {
            # Recover missing stored anchors from the headline only. Summary-wide
            # recovery can join separate stories that merely share a broad theme.
            article_id: re.sub(r"[^가-힣a-z0-9]", "", str(by_id[article_id].get("title") or "").casefold())
            for article_id in article_ids
        }
        entities = {
            article_id: stored_entities[article_id] | {term for term in known_entities if len(term) >= 2 and term in texts[article_id]}
            for article_id in article_ids
        }
        concepts = {
            article_id: stored_concepts[article_id] | {term for term in known_concepts if len(term) >= 2 and term in texts[article_id]}
            for article_id in article_ids
        }
        for article_id, text in texts.items():
            if "위성곤" in text:
                entities[article_id].add("위성곤")
                if "제주" in text:
                    entities[article_id].add("위성곤제주지사")
                    if any(term in text for term in ("지원", "협력", "국비", "기본사회", "선도")):
                        concepts[article_id].add("제주정부협력")
            if any(alias in text for alias in ("제주특별자치도지사", "제주도지사", "제주지사")):
                entities[article_id].add("제주지사")
            if "경찰차량" in text or "경찰차" in text:
                entities[article_id].add("경찰차")
                if "2035" in text and any(term in text for term in ("친환경", "전기", "수소", "전동화", "전환")):
                    concepts[article_id].update({"경찰차친환경전환", "2035경찰차전환"})
            if "전기차" in text or "전기수소차" in text:
                concepts[article_id].add("전기차")
            if "수소차" in text or "전기수소차" in text:
                concepts[article_id].add("수소차")

        title_phrases: dict[str, set[str]] = {}
        exact_titles: dict[str, str] = {}
        for article_id, item in by_id.items():
            title = str(item.get("title") or "")
            exact_titles[article_id] = re.sub(r"[\W\d_]+", "", title).casefold()
            tokens = [
                token.casefold() for token in re.findall(r"[가-힣A-Za-z0-9]{2,}", title)
                if token.casefold() not in generic
            ]
            phrases = set()
            for size in (3, 2):
                for index in range(len(tokens) - size + 1):
                    phrases.add(" ".join(tokens[index:index + size]))
            title_phrases[article_id] = phrases

        press = {
            article_id: {
                str(release.get("title") or ""): float(release.get("similarity_score") or 0)
                for release in by_id[article_id].get("related_press_releases") or []
                if float(release.get("similarity_score") or 0) >= 78
            }
            for article_id in article_ids
        }
        vectors = {
            article_id: self._json_list((analysis.get(article_id) or {}).get("vector"))
            for article_id in article_ids
        }

        pair_candidates: set[tuple[str, str]] = set()
        for features in (entities, concepts, title_phrases, {key: set(value) for key, value in press.items()}):
            inverted: dict[str, list[str]] = {}
            for article_id, values in features.items():
                for value in values:
                    inverted.setdefault(value, []).append(article_id)
            for members in inverted.values():
                for index, left_id in enumerate(members):
                    for right_id in members[index + 1:]:
                        pair_candidates.add(tuple(sorted((left_id, right_id))))
        exact_map: dict[str, list[str]] = {}
        for article_id, key in exact_titles.items():
            if len(key) >= 6:
                exact_map.setdefault(key, []).append(article_id)
        for members in exact_map.values():
            for index, left_id in enumerate(members):
                for right_id in members[index + 1:]:
                    pair_candidates.add(tuple(sorted((left_id, right_id))))

        related: dict[str, dict[str, float]] = {article_id: {} for article_id in article_ids}
        for left_id, right_id in pair_candidates:
            shared_entities = entities[left_id] & entities[right_id]
            shared_concepts = concepts[left_id] & concepts[right_id]
            shared_phrases = title_phrases[left_id] & title_phrases[right_id]
            shared_press = press[left_id].keys() & press[right_id].keys()
            press_strength = max((min(press[left_id][key], press[right_id][key]) for key in shared_press), default=0.0)
            semantic = cosine_similarity(vectors[left_id], vectors[right_id])
            exact = bool(exact_titles[left_id] and exact_titles[left_id] == exact_titles[right_id])
            is_related = bool(
                exact
                or (press_strength >= 78 and (semantic >= 0.70 or shared_entities or shared_concepts))
                or (bool({"제주정부협력", "경찰차친환경전환"} & shared_concepts) and semantic >= 0.65)
                or (shared_phrases and semantic >= 0.76)
                or (shared_entities and shared_concepts and len(shared_entities | shared_concepts) >= 3 and semantic >= 0.78)
                or (len(shared_concepts) >= 3 and semantic >= 0.82)
                or (len(shared_entities) >= 3 and semantic >= 0.84)
            )
            if not is_related:
                continue
            score = (
                (10.0 if exact else 0.0)
                + (6.0 + max(0.0, press_strength - 78.0) / 4.0 if press_strength else 0.0)
                + min(6.0, len(shared_entities) * 2.0)
                + min(6.0, len(shared_concepts) * 2.0)
                + min(5.0, len(shared_phrases) * 1.5)
                + max(0.0, semantic - 0.70) * 10.0
            )
            related[left_id][right_id] = score
            related[right_id][left_id] = score

        remaining = set(article_ids)
        groups: list[list[str]] = []
        while remaining:
            seed = max(remaining, key=lambda article_id: (sum(neighbor in remaining for neighbor in related[article_id]), float(by_id[article_id].get("score") or 0), article_id))
            candidates = {seed} | {neighbor for neighbor in related[seed] if neighbor in remaining}
            if len(candidates) < 2:
                remaining.remove(seed)
                continue
            ratio = 0.50 if len(candidates) >= 30 else 0.35
            changed = True
            while changed and len(candidates) >= 2:
                minimum = max(1, int((len(candidates) - 1) * ratio + 0.999))
                filtered = {
                    article_id for article_id in candidates
                    if article_id == seed or sum(neighbor in candidates for neighbor in related[article_id]) >= minimum
                }
                changed = filtered != candidates
                candidates = filtered
            if len(candidates) < 2:
                remaining.remove(seed)
                continue
            group = sorted(candidates)
            groups.append(group)
            remaining.difference_update(group)

        # A short or metadata-empty headline can miss the leader even when it is
        # directly related to many other members. Attach only such well-supported
        # orphans; this does not permit transitive A-B-C chaining.
        grouped_ids = {article_id for group in groups for article_id in group}
        for article_id in sorted(set(article_ids) - grouped_ids):
            best: tuple[int, int] | None = None
            for index, group in enumerate(groups):
                ratio = 0.50 if len(group) + 1 >= 30 else 0.35
                minimum = max(2, int(len(group) * ratio + 0.999))
                connections = sum(member in related[article_id] for member in group)
                if connections >= minimum and (best is None or connections > best[0]):
                    best = (connections, index)
            if best is not None:
                groups[best[1]].append(article_id)

        for group in groups:
            issue_key = "issue:" + group[0]
            for article_id in group:
                by_id[article_id]["issue_key"] = issue_key
        return items

    @staticmethod
    def _daily_topic_label(items: list[dict]) -> str:
        """Choose a readable shared headline phrase without another AI call."""
        stop = {
            "행정안전부", "행안부", "정부", "정책", "관련", "통해", "위해", "이번", "주요",
            "전국", "대응", "추진", "강화", "운영", "개최", "발표", "지원", "확대", "적극",
            "이용", "가동", "활용", "대책", "상황", "대상", "대한", "위한", "있는", "한다",
        }
        phrase_counts: dict[str, int] = {}
        word_counts: dict[str, int] = {}
        for item in items:
            tokens = [
                token for token in re.findall(r"[가-힣A-Za-z]{2,}", str(item.get("title") or ""))
                if token not in stop
            ]
            seen_phrases, seen_words = set(), set()
            for size in (3, 2):
                for index in range(len(tokens) - size + 1):
                    phrase = " ".join(tokens[index:index + size])
                    if phrase not in seen_phrases:
                        phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1
                        seen_phrases.add(phrase)
            for token in tokens:
                if token not in seen_words:
                    word_counts[token] = word_counts.get(token, 0) + 1
                    seen_words.add(token)
        minimum_phrase_count = max(2, (len(items) + 3) // 4)
        candidates = [phrase for phrase, count in phrase_counts.items() if count >= minimum_phrase_count]
        if candidates:
            return max(candidates, key=lambda value: (phrase_counts[value], len(value.split()), len(value), value))[:42]
        if word_counts:
            return max(word_counts, key=lambda value: (word_counts[value], len(value), value))[:42]
        return str(items[0].get("title") or "주요 보도")[:42] if items else "주요 보도"

    def _daily_topics(self, items: list[dict]) -> list[dict]:
        """Use only repeated, exact headline phrases from this DAILY snapshot."""
        stop = {
            "행정안전부", "행안부", "정부", "정책", "관련", "통해", "위해", "이번", "주요",
            "전국", "대응", "추진", "강화", "운영", "개최", "발표", "지원", "확대", "적극",
            "이용", "가동", "활용", "대책", "상황", "대상", "대한", "위한", "있는", "한다",
        }
        by_id = {str(item.get("article_id") or ""): item for item in items}
        phrase_articles: dict[str, set[str]] = {}
        for article_id, item in by_id.items():
            tokens = [
                token for token in re.findall(r"[가-힣A-Za-z]{2,}", str(item.get("title") or ""))
                if token not in stop
            ]
            seen = set()
            for size in (3, 2):
                for index in range(len(tokens) - size + 1):
                    phrase = " ".join(tokens[index:index + size])
                    if phrase not in seen:
                        phrase_articles.setdefault(phrase, set()).add(article_id)
                        seen.add(phrase)
        selected: list[dict] = []
        ranked_phrases = sorted(
            ((phrase, article_ids) for phrase, article_ids in phrase_articles.items() if len(article_ids) >= 2),
            key=lambda value: (-len(value[1]), -len(value[0].split()), -len(value[0]), value[0]),
        )
        for phrase, article_ids in ranked_phrases:
            # Keep only one spelling for substantially the same set of articles.
            if any(len(article_ids & picked["article_ids"]) / min(len(article_ids), len(picked["article_ids"])) >= 0.6 for picked in selected):
                continue
            # article_ids were created from this normalized title phrase above.
            source_items = [by_id[article_id] for article_id in article_ids]
            source = sorted(
                source_items,
                key=lambda item: (-float(item.get("score") or 0), -bool(item.get("image_url")), str(item.get("published_at") or "")),
            )[0]
            selected.append({
                "label": phrase[:42],
                "value": len(article_ids),
                "image_url": str(source.get("image_url") or ""),
                "article_title": str(source.get("title") or "")[:160],
                "article_url": str(source.get("original_url") or ""),
                "article_ids": article_ids,
            })
            if len(selected) >= 8:
                break
        return [{key: value for key, value in topic.items() if key != "article_ids"} for topic in selected]

    def editions(self, organization_id: str = "", limit: int = 90, include_legacy: bool = False) -> list[dict]:
        query, params = "SELECT * FROM magazine_editions", []
        where = []
        if organization_id:
            where.append("organization_id=?"); params.append(organization_id)
        if not include_legacy:
            # DAILY is retained in storage for audit, but replaced in the reader by morning.
            where.append("edition_slot<>'daily'")
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY edition_date DESC,CASE edition_slot WHEN 'daily' THEN 1 WHEN 'morning' THEN 2 WHEN 'lunch' THEN 3 WHEN 'evening' THEN 4 ELSE 0 END DESC LIMIT ?"
        # Three current editions per day; legacy DAILY snapshots remain queryable by ID.
        params.append(max(1, min(1_100, int(limit))))
        with self.store.connect() as connection: return [self._edition_meta(row) for row in connection.execute(query, params).fetchall()]

    def edition(self, edition_id: str) -> dict | None:
        with self.store.connect() as connection: return self._edition_from_connection(connection, edition_id)

    def _edition_meta(self, row) -> dict:
        item = dict(row); item["case_catalog"] = json.loads(item.pop("case_catalog") or "[]"); item["daily_topics"] = json.loads(item.pop("daily_topics", "[]") or "[]"); item["slot_label"] = SLOT_LABELS.get(item["edition_slot"], item["edition_slot"]); item["title"] = edition_title(item.get("organization_name") or "", item["edition_slot"]); return item

    def _edition_from_connection(self, connection, edition_id: str) -> dict | None:
        row = connection.execute("SELECT * FROM magazine_editions WHERE id=?", (edition_id,)).fetchone()
        if not row: return None
        item = self._edition_meta(row)
        members = [dict(member) for member in connection.execute("SELECT * FROM magazine_issue_members WHERE edition_id=? ORDER BY rank", (edition_id,)).fetchall()]
        for member in members:
            member["case_matches"] = json.loads(member.pop("case_matches") or "[]")
            member["related_press_releases"] = json.loads(member.pop("related_press_releases") or "[]")
        item["members"] = members
        return item
