from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from .storage import KST, Store, now_iso

SLOT_LABELS = {"morning": "AM", "lunch": "NOON", "evening": "PM", "daily": "DAILY"}
SLOT_HOURS = {"morning": 8, "lunch": 12, "evening": 18, "daily": 7}


def edition_title(organization_name: str, slot: str) -> str:
    return f"{str(organization_name or '기관').strip()} CaseON {SLOT_LABELS.get(slot, slot.upper())}"

def edition_window(slot: str, reference: datetime | None = None) -> tuple[str, str, str]:
    current = (reference or datetime.now(KST)).astimezone(KST)
    end = current.replace(hour=SLOT_HOURS.get(slot, -1), minute=0, second=0, microsecond=0)
    if slot == "morning":
        start = end - timedelta(hours=14)
    elif slot in {"lunch", "evening"}:
        start = end - timedelta(hours=4 if slot == "lunch" else 6)
    elif slot == "daily":
        start = end - timedelta(days=1)
    else:
        raise ValueError("매거진 회차는 morning, lunch, evening, daily 중 하나여야 합니다.")
    return end.date().isoformat(), start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")

class MagazinePublisher:
    def __init__(self, store: Store):
        self.store = store
        self.store.ensure_magazine_schema()

    def publish_for_slot(self, slot: str, reference: datetime | None = None, force: bool = False) -> list[dict]:
        edition_date, window_start, window_end = edition_window(slot, reference)
        return [self.publish(item["id"], edition_date, slot, window_start, window_end, force) for item in self.store.list_organizations(active_only=True)]

    def publish_due(self, reference: datetime | None = None) -> list[dict]:
        current = (reference or datetime.now(KST)).astimezone(KST)
        editions: list[dict] = []
        for slot, hour in SLOT_HOURS.items():
            if current.hour < hour:
                continue
            edition_date, window_start, window_end = edition_window(slot, current)
            for organization in self.store.list_organizations(active_only=True):
                if self.store.magazine_edition_exists(organization["id"], edition_date, slot):
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
            issue_sizes = {key: sum(1 for item in items if item["issue_key"] == key) for key in {item["issue_key"] for item in items}}
            items.sort(key=lambda item: (-issue_sizes[item["issue_key"]], -float(item["score"]), -bool(item.get("image_url")), -len(str(item.get("summary") or "")), str(item["published_at"] or "")))
            generated, edition_id = now_iso(), str(existing["id"]) if existing else str(uuid.uuid4())
            values = (organization["name"], window_start, window_end, json.dumps(catalog, ensure_ascii=False), len({item["issue_key"] for item in items}), len(items), generated, generated)
            if existing:
                connection.execute("DELETE FROM magazine_issue_members WHERE edition_id=?", (edition_id,))
                connection.execute("UPDATE magazine_editions SET organization_name=?,window_start_at=?,window_end_at=?,case_catalog=?,issue_count=?,article_count=?,status='published',generated_at=?,updated_at=? WHERE id=?", (*values, edition_id))
            else:
                connection.execute("INSERT INTO magazine_editions(id,organization_id,organization_name,edition_date,edition_slot,window_start_at,window_end_at,case_catalog,issue_count,article_count,status,generated_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (edition_id, organization_id, organization["name"], edition_date, slot, window_start, window_end, json.dumps(catalog, ensure_ascii=False), len({item["issue_key"] for item in items}), len(items), "published", generated, generated))
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

    def _finalize_issue_keys(self, items: list[dict], organization_id: str) -> list[dict]:
        """Refresh editorial issue groups from exactly this edition's articles.

        The persisted group map is a useful fallback, but is intentionally built in a
        background task. Magazine publication needs one fresh, scoped pass so stale
        membership cannot turn the same issue into repeated lead cards.
        """
        for item in items:
            item["issue_key"] = "article:" + str(item.get("article_id") or "")
        article_ids = [str(item.get("article_id") or "") for item in items if item.get("article_id")]
        if len(article_ids) < 2:
            return items
        marks = ",".join("?" for _ in article_ids)
        with self.store.connect() as connection:
            rows = connection.execute(
                f"""SELECT a.id article_id,a.title,a.published_at,a.first_seen_at,aa.summary,
                            aa.entities,aa.topic_concepts,ae.vector article_vector
                       FROM articles a JOIN article_analyses aa ON aa.article_id=a.id
                       LEFT JOIN article_embeddings ae ON ae.article_analysis_id=aa.id AND ae.status='completed'
                      WHERE a.id IN ({marks}) AND aa.organization_id=? AND aa.status='completed'""",
                (*article_ids, organization_id),
            ).fetchall()
        candidates = []
        for row in rows:
            candidates.append({
                "id": str(row["article_id"]), "title": row["title"] or "", "summary": row["summary"] or "",
                "published_at": row["published_at"] or row["first_seen_at"] or "",
                "entities": self._json_list(row["entities"]), "topic_concepts": self._json_list(row["topic_concepts"]),
                "semantic_vector": self._json_list(row["article_vector"]),
            })
        parent = {str(item["article_id"]): str(item["article_id"]) for item in items}

        def find(value: str) -> str:
            while parent[value] != value:
                parent[value] = parent[parent[value]]
                value = parent[value]
            return value

        def union(left: str, right: str) -> None:
            left_root, right_root = find(left), find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        generic_terms = {"정부", "정책", "발표", "지원", "추진", "확대", "강화", "관련", "기사", "보도", "행정안전부", "행안부", "윤호중"}
        evidence = {
            # Broad auto-tags can connect unrelated daily articles transitively.
            str(item["id"]): {
                str(term).strip().casefold() for term in (item.get("entities") or [])
                if len(str(term).strip()) >= 3 and str(term).strip() not in generic_terms
            }
            for item in candidates
        }
        candidate_ids = [str(item["id"]) for item in candidates]
        for index, left_id in enumerate(candidate_ids):
            for right_id in candidate_ids[index + 1:]:
                if len(evidence.get(left_id, set()) & evidence.get(right_id, set())) >= 2:
                    union(left_id, right_id)
        headline_keys = {str(item["id"]): "".join(character for character in str(item.get("title") or "").casefold() if not character.isspace() and not character.isdigit()) for item in candidates}
        press_keys = {str(item["article_id"]): {str(press.get("title") or "").strip() for press in item.get("related_press_releases") or [] if float(press.get("similarity_score") or 0) >= 80} for item in items}
        item_ids = list(press_keys)
        for index, left_id in enumerate(item_ids):
            for right_id in item_ids[index + 1:]:
                if press_keys[left_id] & press_keys[right_id]:
                    union(left_id, right_id)
        for index, left_id in enumerate(candidate_ids):
            for right_id in candidate_ids[index + 1:]:
                if len(headline_keys.get(left_id, "")) >= 6 and headline_keys[left_id] == headline_keys.get(right_id, ""):
                    union(left_id, right_id)
        item_headlines = {str(item["article_id"]): "".join(character for character in str(item.get("title") or "").casefold() if not character.isspace() and not character.isdigit()) for item in items}
        item_ids = list(item_headlines)
        for index, left_id in enumerate(item_ids):
            for right_id in item_ids[index + 1:]:
                if len(item_headlines[left_id]) >= 6 and item_headlines[left_id] == item_headlines[right_id]:
                    union(left_id, right_id)
        components: dict[str, list[str]] = {}
        for article_id in parent:
            components.setdefault(find(article_id), []).append(article_id)
        issue_by_article = {
            article_id: "issue:" + min(members)
            for members in components.values() if len(members) > 1 for article_id in members
        }
        for item in items:
            if str(item["article_id"]) in issue_by_article:
                item["issue_key"] = issue_by_article[str(item["article_id"])]
        return items

    def editions(self, organization_id: str = "", limit: int = 90) -> list[dict]:
        query, params = "SELECT * FROM magazine_editions", []
        if organization_id: query, params = query + " WHERE organization_id=?", [organization_id]
        query += " ORDER BY edition_date DESC,CASE edition_slot WHEN 'daily' THEN 1 WHEN 'morning' THEN 2 WHEN 'lunch' THEN 3 WHEN 'evening' THEN 4 ELSE 0 END DESC LIMIT ?"
        # Four editions per day: keep roughly a year's worth of editions available.
        params.append(max(1, min(1_100, int(limit))))
        with self.store.connect() as connection: return [self._edition_meta(row) for row in connection.execute(query, params).fetchall()]

    def edition(self, edition_id: str) -> dict | None:
        with self.store.connect() as connection: return self._edition_from_connection(connection, edition_id)

    def _edition_meta(self, row) -> dict:
        item = dict(row); item["case_catalog"] = json.loads(item.pop("case_catalog") or "[]"); item["slot_label"] = SLOT_LABELS.get(item["edition_slot"], item["edition_slot"]); item["title"] = edition_title(item.get("organization_name") or "", item["edition_slot"]); return item

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
