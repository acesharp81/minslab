from __future__ import annotations

import hashlib
import html
import json
import math
import re
import time
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .storage import KST, Store, json_value, now_iso


MOIS_PRESS_RSS = "https://www.mois.go.kr/gpms/view/jsp/rss/rss.jsp?ctxCd=1012"
MATCHER_VERSION = "press-rag-v3"
TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]{2,}")
CONTACT_RE = re.compile(
    r"담당자\s*[:：]\s*(?P<department>[^\n()]{2,40}?)\s+(?P<name>[가-힣A-Za-z]{2,20})\s*\((?P<phone>0\d{1,2}-\d{3,4}-\d{4})\)"
)


PRESS_RELEASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS press_releases (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  source TEXT NOT NULL DEFAULT 'mois',
  external_id TEXT NOT NULL,
  canonical_url TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  department TEXT NOT NULL DEFAULT '',
  contact_name TEXT NOT NULL DEFAULT '',
  contact_phone TEXT NOT NULL DEFAULT '',
  published_at TEXT,
  summary TEXT NOT NULL DEFAULT '',
  markdown_path TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  document_fingerprint TEXT NOT NULL DEFAULT '',
  embedding_status TEXT NOT NULL DEFAULT 'pending',
  embedding_model TEXT NOT NULL DEFAULT '',
  last_error TEXT,
  supabase_synced_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_press_releases_org_published
  ON press_releases(organization_id,published_at DESC);
CREATE INDEX IF NOT EXISTS idx_press_releases_embedding
  ON press_releases(embedding_status,updated_at);

CREATE TABLE IF NOT EXISTS press_release_chunks (
  id TEXT PRIMARY KEY,
  press_release_id TEXT NOT NULL REFERENCES press_releases(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  embedding_model TEXT NOT NULL,
  dimensions INTEGER NOT NULL DEFAULT 0,
  vector TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(press_release_id,chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_press_release_chunks_release
  ON press_release_chunks(press_release_id,chunk_index);

CREATE TABLE IF NOT EXISTS press_release_match_jobs (
  article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  press_release_id TEXT NOT NULL REFERENCES press_releases(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending',
  queued_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  error TEXT,
  PRIMARY KEY(article_id,press_release_id)
);
CREATE INDEX IF NOT EXISTS idx_press_release_match_jobs_status
  ON press_release_match_jobs(status,queued_at);

CREATE TABLE IF NOT EXISTS article_press_release_matches (
  article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  press_release_id TEXT NOT NULL REFERENCES press_releases(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'completed',
  is_related INTEGER NOT NULL DEFAULT 0,
  semantic_score REAL NOT NULL DEFAULT 0,
  lexical_score REAL NOT NULL DEFAULT 0,
  similarity_score REAL NOT NULL DEFAULT 0,
  matcher_version TEXT NOT NULL,
  matched_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  supabase_synced_at TEXT,
  PRIMARY KEY(article_id,press_release_id)
);
CREATE INDEX IF NOT EXISTS idx_article_press_release_related
  ON article_press_release_matches(article_id,is_related,similarity_score DESC);
CREATE INDEX IF NOT EXISTS idx_press_release_articles_related
  ON article_press_release_matches(press_release_id,is_related,similarity_score DESC);
"""


class _TextExtractor(HTMLParser):
    BLOCKS = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "br"}

    def __init__(self, target_id: str | None = None):
        super().__init__(convert_charrefs=True)
        self.target_id = target_id
        self.depth = 0
        self.target_depth = 0
        self.parts: list[str] = []

    @property
    def active(self) -> bool:
        return self.target_id is None or self.target_depth > 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.depth += 1
        attributes = dict(attrs)
        if self.target_id and attributes.get("id") == self.target_id:
            self.target_depth = self.depth
        if self.active and tag.lower() in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.active and tag.lower() in self.BLOCKS:
            self.parts.append("\n")
        if self.target_depth == self.depth:
            self.target_depth = 0
        self.depth = max(0, self.depth - 1)

    def handle_data(self, data: str) -> None:
        if self.active and data.strip():
            self.parts.append(data)

    def text(self) -> str:
        value = html.unescape("".join(self.parts)).replace("\xa0", " ")
        lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
        return "\n\n".join(line for line in lines if line)


def html_to_markdown(value: str, target_id: str | None = None) -> str:
    parser = _TextExtractor(target_id)
    parser.feed(str(value or ""))
    return parser.text()


def parse_mois_date(value: str) -> str | None:
    match = re.search(r"(\d{1,2})\s+(\d{1,2})월\s+(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})", str(value or ""))
    if not match:
        return None
    day, month, year, hour, minute, second = map(int, match.groups())
    try:
        return datetime(year, month, day, hour, minute, second, tzinfo=KST).isoformat(timespec="seconds")
    except ValueError:
        return None


def extract_external_id(url: str) -> str:
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    return str((query.get("nttId") or [hashlib.sha256(url.encode()).hexdigest()[:20]])[0])[:80]


def document_fingerprint(title: str, body_or_markdown: str) -> str:
    body = str(body_or_markdown or "")
    body = re.sub(r"^---\s*.*?\s*---\s*", "", body, count=1, flags=re.S)
    body = re.sub(r"^#\s+[^\n]+\n+", "", body, count=1)
    body = CONTACT_RE.sub("", body)
    body = re.sub(r"(?m)^\s*[-*#>]+\s*", "", body)
    normalized = re.sub(r"\s+", " ", f"{title} {body}").casefold().strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def extractive_summary(text: str, limit: int = 360) -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    clean = CONTACT_RE.sub("", clean).strip()
    if len(clean) <= limit:
        return clean
    sentences = re.split(r"(?<=[.!?다요])\s+", clean)
    selected: list[str] = []
    for sentence in sentences:
        if not sentence:
            continue
        if selected and len(" ".join([*selected, sentence])) > limit:
            break
        selected.append(sentence)
        if len(selected) >= 3:
            break
    return (" ".join(selected) or clean[:limit]).strip()[:limit]


def chunk_markdown(markdown: str, size: int = 1200, overlap: int = 160) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", str(markdown or "")) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > size:
            if current:
                chunks.append(current)
                current = ""
            step = max(200, size - overlap)
            chunks.extend(paragraph[index:index + size] for index in range(0, len(paragraph), step))
            continue
        candidate = f"{current}\n\n{paragraph}".strip()
        if current and len(candidate) > size:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            current = f"{tail}\n\n{paragraph}".strip()
        else:
            current = candidate
    if current:
        chunks.append(current)
    return list(dict.fromkeys(chunk for chunk in chunks if len(chunk) >= 40))


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm <= 1e-12 or right_norm <= 1e-12:
        return 0.0
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)))


def lexical_similarity(left: str, right: str) -> float:
    left_terms, right_terms = set(TOKEN_RE.findall(str(left or "").casefold())), set(TOKEN_RE.findall(str(right or "").casefold()))
    stop = {"행정안전부", "행안부", "정부", "관련", "대한", "통해", "위해", "밝혔다"}
    left_terms -= stop
    right_terms -= stop
    if not left_terms or not right_terms:
        return 0.0
    overlap = left_terms & right_terms
    return min(1.0, len(overlap) / max(1, min(len(left_terms), len(right_terms))))


class PressReleaseManager:
    def __init__(self, settings, store: Store, ollama, mirror):
        self.settings = settings
        self.store = store
        self.ollama = ollama
        self.mirror = mirror
        self.markdown_root = Path(settings.data_dir) / "press_releases" / "mois"
        self.markdown_root.mkdir(parents=True, exist_ok=True)
        stale_before = (datetime.now(KST) - timedelta(minutes=15)).isoformat(timespec="seconds")
        with self.store.connect() as connection:
            connection.executescript(PRESS_RELEASE_SCHEMA)
            release_columns = {row[1] for row in connection.execute("PRAGMA table_info(press_releases)")}
            if "document_fingerprint" not in release_columns:
                connection.execute("ALTER TABLE press_releases ADD COLUMN document_fingerprint TEXT NOT NULL DEFAULT ''")
            if "supabase_synced_at" not in release_columns:
                connection.execute("ALTER TABLE press_releases ADD COLUMN supabase_synced_at TEXT")
            match_columns = {row[1] for row in connection.execute("PRAGMA table_info(article_press_release_matches)")}
            if "supabase_synced_at" not in match_columns:
                connection.execute("ALTER TABLE article_press_release_matches ADD COLUMN supabase_synced_at TEXT")
            connection.execute("DROP INDEX IF EXISTS idx_press_releases_org_fingerprint")
            rows = connection.execute("SELECT id,title,markdown_path FROM press_releases").fetchall()
            for row in rows:
                markdown_path = Path(str(row["markdown_path"] or ""))
                markdown = markdown_path.read_text(encoding="utf-8") if markdown_path.is_file() else ""
                connection.execute(
                    "UPDATE press_releases SET document_fingerprint=? WHERE id=?",
                    (document_fingerprint(row["title"], markdown), row["id"]),
                )
            duplicates = connection.execute(
                "SELECT organization_id,document_fingerprint FROM press_releases WHERE document_fingerprint<>'' GROUP BY organization_id,document_fingerprint HAVING COUNT(*)>1"
            ).fetchall()
            for duplicate in duplicates:
                records = connection.execute(
                    "SELECT id FROM press_releases WHERE organization_id=? AND document_fingerprint=? ORDER BY CAST(external_id AS INTEGER) DESC,id DESC",
                    (duplicate["organization_id"], duplicate["document_fingerprint"]),
                ).fetchall()
                for record in records[1:]:
                    connection.execute("DELETE FROM press_releases WHERE id=?", (record["id"],))
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_press_releases_org_fingerprint ON press_releases(organization_id,document_fingerprint) WHERE document_fingerprint<>''"
            )
            connection.execute(
                "UPDATE press_release_match_jobs SET status='pending',started_at=NULL WHERE status='processing' AND started_at<?",
                (stale_before,),
            )
            connection.execute(
                "UPDATE press_releases SET embedding_status='pending' WHERE embedding_status='processing' AND updated_at<?",
                (stale_before,),
            )

    def _mois_organization(self) -> dict | None:
        for organization in self.store.list_organizations(active_only=True):
            domains = " ".join(str(value) for value in organization.get("domains", []))
            if "행정안전부" in organization.get("name", "") or "mois.go.kr" in domains:
                return organization
        return None

    def _request_text(self, url: str) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": self.settings.user_agent, "Accept": "text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.5"})
        with urllib.request.urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
            return response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")

    def _existing_url(self, url: str) -> bool:
        with self.store.connect() as connection:
            return connection.execute("SELECT 1 FROM press_releases WHERE canonical_url=?", (url,)).fetchone() is not None

    def _detail(self, url: str, fallback_html: str) -> tuple[str, str, str, str]:
        detail_html = self._request_text(url)
        body = html_to_markdown(detail_html, "desc_pc") or html_to_markdown(fallback_html)
        contact = CONTACT_RE.search(body)
        department = contact.group("department").strip(" *") if contact else ""
        name = contact.group("name").strip() if contact else ""
        phone = contact.group("phone").strip() if contact else ""
        return body, department, name, phone

    def _markdown(self, item: dict) -> str:
        metadata = [
            "---", f'title: "{str(item["title"]).replace(chr(34), chr(39))}"',
            "organization: \"행정안전부\"", f'department: "{item.get("department", "")}"',
            f'contact_name: "{item.get("contact_name", "")}"', f'contact_phone: "{item.get("contact_phone", "")}"',
            f'published_at: "{item.get("published_at") or ""}"', f'source_url: "{item["canonical_url"]}"', "---", "",
            f'# {item["title"]}', "", str(item.get("body") or "").strip(), "",
        ]
        return "\n".join(metadata).strip() + "\n"

    def _save_release(self, organization_id: str, item: dict) -> tuple[dict, bool]:
        release_id = str(uuid.uuid5(uuid.NAMESPACE_URL, item["canonical_url"]))
        published = item.get("published_at") or now_iso()
        year = str(published)[:4] if str(published)[:4].isdigit() else "unknown"
        path = self.markdown_root / year / f'{item["external_id"]}.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        markdown = self._markdown(item)
        content_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        fingerprint = document_fingerprint(item["title"], item.get("body") or "")
        now = now_iso()
        with self.store.connect() as connection:
            existing = connection.execute("SELECT * FROM press_releases WHERE canonical_url=?", (item["canonical_url"],)).fetchone()
            duplicate = connection.execute(
                "SELECT * FROM press_releases WHERE organization_id=? AND document_fingerprint=?",
                (organization_id, fingerprint),
            ).fetchone()
            if duplicate and not existing:
                return dict(duplicate), False
            if existing and existing["content_hash"] == content_hash:
                return dict(existing), False
            path.write_text(markdown, encoding="utf-8")
            if existing:
                release_id = str(existing["id"])
                connection.execute(
                    """UPDATE press_releases SET title=?,department=?,contact_name=?,contact_phone=?,published_at=?,summary=?,markdown_path=?,content_hash=?,document_fingerprint=?,embedding_status='pending',last_error=NULL,supabase_synced_at=NULL,updated_at=? WHERE id=?""",
                    (item["title"], item.get("department", ""), item.get("contact_name", ""), item.get("contact_phone", ""), item.get("published_at"), item.get("summary", ""), str(path), content_hash, fingerprint, now, release_id),
                )
                connection.execute("DELETE FROM press_release_chunks WHERE press_release_id=?", (release_id,))
            else:
                connection.execute(
                    """INSERT INTO press_releases(id,organization_id,source,external_id,canonical_url,title,department,contact_name,contact_phone,published_at,summary,markdown_path,content_hash,document_fingerprint,created_at,updated_at)
                       VALUES(?,?,'mois',?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (release_id, organization_id, item["external_id"], item["canonical_url"], item["title"], item.get("department", ""), item.get("contact_name", ""), item.get("contact_phone", ""), item.get("published_at"), item.get("summary", ""), str(path), content_hash, fingerprint, now, now),
                )
            row = connection.execute("SELECT * FROM press_releases WHERE id=?", (release_id,)).fetchone()
        return dict(row), True

    def sync(self, force: bool = False) -> dict:
        organization = self._mois_organization()
        if not organization:
            return {"status": "skipped", "reason": "mois_organization_missing", "new": 0}
        now = datetime.now(KST)
        next_at = self.store.get_setting("press_release_next_sync_at", "")
        if not force and next_at and next_at > now.isoformat(timespec="seconds"):
            return {"status": "not_due", "new": 0, "next_sync_at": next_at}
        feed_url = str(getattr(self.settings, "press_release_rss_url", "") or MOIS_PRESS_RSS)
        created, checked, errors = 0, 0, []
        try:
            root = ET.fromstring(self._request_text(feed_url))
            for node in root.findall("./channel/item"):
                url = (node.findtext("link") or "").strip()
                if not url:
                    continue
                published_at = parse_mois_date(node.findtext("pubDate") or "")
                title = (node.findtext("title") or "").strip()
                if self._existing_url(url):
                    with self.store.connect() as connection:
                        connection.execute(
                            "UPDATE press_releases SET published_at=COALESCE(published_at,?),title=CASE WHEN title='' THEN ? ELSE title END,updated_at=updated_at WHERE canonical_url=?",
                            (published_at, title, url),
                        )
                    continue
                checked += 1
                try:
                    fallback_html = node.findtext("description") or ""
                    body, department, contact_name, contact_phone = self._detail(url, fallback_html)
                    department = department or (node.findtext("author") or "").strip()
                    item = {"external_id": extract_external_id(url), "canonical_url": url, "title": title,
                            "department": department, "contact_name": contact_name, "contact_phone": contact_phone,
                            "published_at": published_at, "body": body,
                            "summary": extractive_summary(body)}
                    _release, was_created = self._save_release(organization["id"], item)
                    created += int(was_created)
                    if created >= int(getattr(self.settings, "press_release_per_sync", 8)):
                        break
                    time.sleep(0.12)
                except Exception as error:
                    errors.append(f"{title[:60]}: {type(error).__name__}")
            next_sync = (now + timedelta(minutes=int(getattr(self.settings, "press_release_sync_minutes", 30)))).isoformat(timespec="seconds")
            self.store.set_setting("press_release_next_sync_at", next_sync)
            self.store.set_setting("press_release_last_sync_at", now_iso())
            self.store.set_setting("press_release_last_error", "\n".join(errors)[:2000])
            mirror_result = self.mirror_backfill(20)
            return {"status": "completed_with_errors" if errors else "completed", "checked": checked, "new": created,
                    "errors": errors, "next_sync_at": next_sync, "supabase": mirror_result}
        except Exception as error:
            self.store.set_setting("press_release_last_error", str(error)[:2000])
            self.store.set_setting("press_release_next_sync_at", (now + timedelta(minutes=5)).isoformat(timespec="seconds"))
            return {"status": "failed", "new": 0, "error": str(error)}

    def _release_markdown(self, release: dict) -> str:
        path = Path(str(release.get("markdown_path") or ""))
        try:
            path.resolve().relative_to(self.markdown_root.resolve())
        except (ValueError, OSError):
            return ""
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    def _next_pending_release(self) -> dict | None:
        with self.store.connect() as connection:
            row = connection.execute("SELECT * FROM press_releases WHERE embedding_status='pending' ORDER BY COALESCE(published_at,created_at) DESC LIMIT 1").fetchone()
            if row:
                changed = connection.execute(
                    "UPDATE press_releases SET embedding_status='processing',updated_at=? WHERE id=? AND embedding_status='pending'",
                    (now_iso(), row["id"]),
                ).rowcount
                if not changed:
                    return None
        return dict(row) if row else None

    def _queue_release_pairs(self, release_id: str) -> int:
        window = int(getattr(self.settings, "press_release_match_window_days", 45))
        now = now_iso()
        with self.store.connect() as connection:
            return connection.execute(
                """INSERT OR IGNORE INTO press_release_match_jobs(article_id,press_release_id,status,queued_at)
                   SELECT aa.article_id,pr.id,'pending',? FROM press_releases pr
                   JOIN article_processing_flags apf ON 1=1 JOIN article_analyses aa ON aa.id=apf.analysis_id
                   JOIN article_embeddings ae ON ae.article_analysis_id=aa.id AND ae.status='completed'
                   WHERE pr.id=? AND aa.organization_id=pr.organization_id
                     AND ABS(julianday(COALESCE((SELECT published_at FROM articles WHERE id=aa.article_id),aa.created_at))-julianday(COALESCE(pr.published_at,pr.created_at)))<=?""",
                (now, release_id, window),
            ).rowcount

    def queue_for_article(self, article_analysis_id: str) -> int:
        window = int(getattr(self.settings, "press_release_match_window_days", 45))
        now = now_iso()
        with self.store.connect() as connection:
            return connection.execute(
                """INSERT OR IGNORE INTO press_release_match_jobs(article_id,press_release_id,status,queued_at)
                   SELECT aa.article_id,pr.id,'pending',? FROM article_analyses aa
                   JOIN articles a ON a.id=aa.article_id JOIN press_releases pr ON pr.organization_id=aa.organization_id AND pr.embedding_status='completed'
                   WHERE aa.id=? AND ABS(julianday(COALESCE(a.published_at,a.first_seen_at))-julianday(COALESCE(pr.published_at,pr.created_at)))<=?""",
                (now, article_analysis_id, window),
            ).rowcount

    def _embed_release(self, release: dict) -> dict:
        markdown = self._release_markdown(release)
        chunks = chunk_markdown(markdown)
        if not chunks:
            raise ValueError("press_release_markdown_empty")
        model = str(self.settings.embedding_model)
        vectors = self.ollama.embeddings([f"search_document: {chunk}" for chunk in chunks])
        if len(vectors) != len(chunks) or not all(vectors):
            raise ValueError("press_release_embedding_empty")
        now = now_iso()
        chunk_rows = []
        with self.store.connect() as connection:
            connection.execute("DELETE FROM press_release_chunks WHERE press_release_id=?", (release["id"],))
            for index, (content, vector) in enumerate(zip(chunks, vectors)):
                chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'{release["id"]}:{index}:{hashlib.sha256(content.encode()).hexdigest()}'))
                row = {"id": chunk_id, "press_release_id": release["id"], "chunk_index": index, "content": content,
                       "content_hash": hashlib.sha256(content.encode()).hexdigest(), "embedding_model": model,
                       "dimensions": len(vector), "vector": vector, "created_at": now, "updated_at": now}
                connection.execute(
                    """INSERT INTO press_release_chunks(id,press_release_id,chunk_index,content,content_hash,embedding_model,dimensions,vector,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (chunk_id, release["id"], index, content, row["content_hash"], model, len(vector), json.dumps(vector), now, now),
                )
                chunk_rows.append(row)
            connection.execute("UPDATE press_releases SET embedding_status='completed',embedding_model=?,last_error=NULL,updated_at=? WHERE id=?", (model, now, release["id"]))
            completed = connection.execute("SELECT * FROM press_releases WHERE id=?", (release["id"],)).fetchone()
        release_ok = self.mirror.press_release(dict(completed), self._release_markdown(dict(completed)))
        chunks_ok = self.mirror.press_release_chunks(chunk_rows)
        if self.mirror.enabled:
            if release_ok and chunks_ok:
                with self.store.connect() as connection:
                    connection.execute("UPDATE press_releases SET supabase_synced_at=? WHERE id=?", (now_iso(), release["id"]))
            self.store.set_setting("press_release_supabase_status", "ready" if release_ok and chunks_ok else "schema_required")
            self.store.set_setting("press_release_supabase_error", str(self.mirror.last_error or "")[:1000])
        queued = self._queue_release_pairs(release["id"])
        return {"stage": "press_embedding", "press_release_id": release["id"], "chunks": len(chunks), "queued_matches": queued}

    def _next_match_job(self) -> dict | None:
        with self.store.connect() as connection:
            row = connection.execute("SELECT * FROM press_release_match_jobs WHERE status='pending' ORDER BY queued_at LIMIT 1").fetchone()
            if row:
                changed = connection.execute("UPDATE press_release_match_jobs SET status='processing',started_at=? WHERE article_id=? AND press_release_id=? AND status='pending'", (now_iso(), row["article_id"], row["press_release_id"])).rowcount
                if not changed:
                    return None
        return dict(row) if row else None

    def _process_match(self, job: dict) -> dict:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT a.id article_id,a.title article_title,a.snippet,a.body,ae.vector article_vector,
                          pr.*,GROUP_CONCAT(pc.vector,'\n') chunk_vectors
                   FROM articles a JOIN article_processing_flags apf ON apf.article_id=a.id
                   JOIN article_embeddings ae ON ae.article_analysis_id=apf.analysis_id
                   JOIN press_releases pr ON pr.id=? JOIN press_release_chunks pc ON pc.press_release_id=pr.id
                   WHERE a.id=? GROUP BY a.id,pr.id""",
                (job["press_release_id"], job["article_id"]),
            ).fetchone()
        if not row:
            raise ValueError("article_or_press_embedding_missing")
        item = dict(row)
        article_vector = json_value(item.get("article_vector"), [])
        vectors = [json_value(value, []) for value in str(item.get("chunk_vectors") or "").splitlines() if value]
        semantic = max([cosine_similarity(article_vector, vector) for vector in vectors] or [0.0])
        # Korean institutional documents share a high cosine baseline simply because they
        # mention the same ministry and administrative vocabulary. Remove that corpus-level
        # floor, then retain lexical evidence as an independent topic anchor.
        semantic_calibrated = max(0.0, min(1.0, (semantic - 0.68) / 0.22))
        lexical = lexical_similarity(
            f'{item.get("article_title", "")} {item.get("snippet", "")} {str(item.get("body") or "")[:3000]}',
            f'{item.get("title", "")} {item.get("summary", "")}',
        )
        similarity = max(0.0, min(100.0, (semantic_calibrated * 0.8 + lexical * 0.2) * 100.0))
        threshold = float(getattr(self.settings, "press_release_match_threshold", 62.0))
        topic_evidence = lexical >= 0.15
        related = similarity >= threshold and topic_evidence
        now = now_iso()
        with self.store.connect() as connection:
            connection.execute(
                """INSERT INTO article_press_release_matches(article_id,press_release_id,status,is_related,semantic_score,lexical_score,similarity_score,matcher_version,matched_at,created_at,updated_at)
                   VALUES(?,?,'completed',?,?,?,?,?,?,?,?)
                   ON CONFLICT(article_id,press_release_id) DO NOTHING""",
                (job["article_id"], job["press_release_id"], int(related), round(semantic * 100, 2), round(lexical * 100, 2), round(similarity, 2), MATCHER_VERSION, now, now, now),
            )
            connection.execute("UPDATE press_release_match_jobs SET status='completed',finished_at=?,error=NULL WHERE article_id=? AND press_release_id=?", (now, job["article_id"], job["press_release_id"]))
        if related:
            mirrored = self.mirror.press_release_match({"article_id": job["article_id"], "press_release_id": job["press_release_id"], "similarity_score": round(similarity, 2), "semantic_score": round(semantic * 100, 2), "lexical_score": round(lexical * 100, 2), "matcher_version": MATCHER_VERSION, "matched_at": now})
            if mirrored:
                with self.store.connect() as connection:
                    connection.execute(
                        "UPDATE article_press_release_matches SET supabase_synced_at=? WHERE article_id=? AND press_release_id=?",
                        (now_iso(), job["article_id"], job["press_release_id"]),
                    )
        return {"stage": "press_match", "article_id": job["article_id"], "press_release_id": job["press_release_id"], "related": related, "similarity_score": round(similarity, 2)}

    def process_next(self) -> dict | None:
        release = self._next_pending_release()
        if release:
            try:
                return self._embed_release(release)
            except Exception as error:
                with self.store.connect() as connection:
                    connection.execute("UPDATE press_releases SET embedding_status='failed',last_error=?,updated_at=? WHERE id=?", (str(error)[:1000], now_iso(), release["id"]))
                return {"stage": "press_embedding", "status": "failed", "press_release_id": release["id"], "error": str(error)}
        results, errors = [], []
        for _index in range(12):
            job = self._next_match_job()
            if not job:
                break
            try:
                results.append(self._process_match(job))
            except Exception as error:
                with self.store.connect() as connection:
                    connection.execute(
                        "UPDATE press_release_match_jobs SET status='failed',finished_at=?,error=? WHERE article_id=? AND press_release_id=?",
                        (now_iso(), str(error)[:1000], job["article_id"], job["press_release_id"]),
                    )
                errors.append(str(error))
        if not results and not errors:
            return None
        return {"stage": "press_match", "processed": len(results), "related": sum(bool(item.get("related")) for item in results),
                "failed": len(errors), "errors": errors[:3], "results": results}

    def list_releases(self, organization_id: str = "", limit: int = 50) -> list[dict]:
        where, params = "", []
        if organization_id:
            where, params = "WHERE pr.organization_id=?", [organization_id]
        with self.store.connect() as connection:
            rows = connection.execute(
                f"""SELECT pr.*,o.name organization_name,
                       COUNT(DISTINCT CASE WHEN m.is_related=1 THEN m.article_id END) related_article_count,
                       COUNT(DISTINCT CASE WHEN m.is_related=1 AND aa.tone='사실전달' THEN m.article_id END) factual_count,
                       COUNT(DISTINCT CASE WHEN m.is_related=1 AND aa.tone='부정적' THEN m.article_id END) negative_count,
                       COUNT(DISTINCT CASE WHEN m.is_related=1 AND aa.tone='긍정적' THEN m.article_id END) positive_count
                    FROM press_releases pr JOIN organizations o ON o.id=pr.organization_id
                    LEFT JOIN article_press_release_matches m ON m.press_release_id=pr.id
                    LEFT JOIN article_processing_flags apf ON apf.article_id=m.article_id
                    LEFT JOIN article_analyses aa ON aa.id=apf.analysis_id
                    {where} GROUP BY pr.id ORDER BY COALESCE(pr.published_at,pr.created_at) DESC LIMIT ?""",
                (*params, max(1, min(200, int(limit)))),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_release(self, release_id: str, include_markdown: bool = True) -> dict | None:
        with self.store.connect() as connection:
            row = connection.execute("SELECT pr.*,o.name organization_name FROM press_releases pr JOIN organizations o ON o.id=pr.organization_id WHERE pr.id=?", (release_id,)).fetchone()
            if not row:
                return None
            articles = connection.execute(
                """SELECT a.id,a.title,a.original_url,a.publisher,a.published_at,aa.summary,aa.tone,m.similarity_score
                   FROM article_press_release_matches m JOIN articles a ON a.id=m.article_id
                   JOIN article_processing_flags apf ON apf.article_id=a.id JOIN article_analyses aa ON aa.id=apf.analysis_id
                   WHERE m.press_release_id=? AND m.is_related=1 ORDER BY m.similarity_score DESC,COALESCE(a.published_at,a.first_seen_at) DESC""",
                (release_id,),
            ).fetchall()
        item = dict(row)
        item["related_articles"] = [dict(article) for article in articles]
        if include_markdown:
            item["markdown"] = self._release_markdown(item)
        return item

    def releases_for_article(self, article_id: str) -> list[dict]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """SELECT pr.id,pr.title,pr.department,pr.contact_name,pr.contact_phone,pr.published_at,pr.summary,pr.canonical_url,m.similarity_score
                   FROM article_press_release_matches m JOIN press_releases pr ON pr.id=m.press_release_id
                   WHERE m.article_id=? AND m.is_related=1 ORDER BY m.similarity_score DESC,COALESCE(pr.published_at,pr.created_at) DESC""",
                (article_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mirror_backfill(self, limit: int = 20) -> dict:
        if not self.mirror.enabled:
            return {"status": "disabled", "mirrored": 0}
        with self.store.connect() as connection:
            releases = connection.execute(
                "SELECT * FROM press_releases WHERE embedding_status='completed' AND supabase_synced_at IS NULL ORDER BY COALESCE(published_at,created_at) DESC LIMIT ?",
                (max(1, min(100, int(limit))),),
            ).fetchall()
        mirrored = 0
        for release_row in releases:
            release = dict(release_row)
            with self.store.connect() as connection:
                chunk_records = connection.execute(
                    "SELECT * FROM press_release_chunks WHERE press_release_id=? ORDER BY chunk_index",
                    (release["id"],),
                ).fetchall()
            chunks = []
            for row in chunk_records:
                item = dict(row)
                item["vector"] = json_value(item.get("vector"), [])
                chunks.append(item)
            if not chunks or not self.mirror.press_release(release, self._release_markdown(release)):
                break
            if not self.mirror.press_release_chunks(chunks):
                break
            with self.store.connect() as connection:
                connection.execute("UPDATE press_releases SET supabase_synced_at=? WHERE id=?", (now_iso(), release["id"]))
            mirrored += 1
        with self.store.connect() as connection:
            match_rows = connection.execute(
                """SELECT m.* FROM article_press_release_matches m
                   JOIN press_releases pr ON pr.id=m.press_release_id
                   WHERE m.is_related=1 AND m.supabase_synced_at IS NULL AND pr.supabase_synced_at IS NOT NULL
                   ORDER BY m.matched_at LIMIT 1000"""
            ).fetchall()
        match_items = [dict(row) for row in match_rows]
        matched = 0
        if match_items and self.mirror.press_release_matches(match_items):
            synced_at = now_iso()
            with self.store.connect() as connection:
                connection.executemany(
                    "UPDATE article_press_release_matches SET supabase_synced_at=? WHERE article_id=? AND press_release_id=?",
                    [(synced_at, item["article_id"], item["press_release_id"]) for item in match_items],
                )
            matched = len(match_items)
        with self.store.connect() as connection:
            pending_releases = int(connection.execute("SELECT COUNT(*) FROM press_releases WHERE embedding_status='completed' AND supabase_synced_at IS NULL").fetchone()[0])
            pending_matches = int(connection.execute("SELECT COUNT(*) FROM article_press_release_matches WHERE is_related=1 AND supabase_synced_at IS NULL").fetchone()[0])
        pending = pending_releases + pending_matches
        successful = mirrored == len(releases) and matched == len(match_items)
        status = "ready" if successful and pending == 0 else ("syncing" if successful else "schema_required")
        self.store.set_setting("press_release_supabase_status", status)
        self.store.set_setting("press_release_supabase_error", "" if status == "ready" else str(self.mirror.last_error or "")[:1000])
        return {"status": status, "mirrored": mirrored, "requested": len(releases), "matched": matched, "pending": pending}

    def status(self) -> dict:
        with self.store.connect() as connection:
            releases = connection.execute("SELECT embedding_status,COUNT(*) value FROM press_releases GROUP BY embedding_status").fetchall()
            jobs = connection.execute("SELECT status,COUNT(*) value FROM press_release_match_jobs GROUP BY status").fetchall()
            related = connection.execute("SELECT COUNT(*) value FROM article_press_release_matches WHERE is_related=1").fetchone()
            unsynced_releases = connection.execute("SELECT COUNT(*) value FROM press_releases WHERE embedding_status='completed' AND supabase_synced_at IS NULL").fetchone()
            unsynced_matches = connection.execute("SELECT COUNT(*) value FROM article_press_release_matches WHERE is_related=1 AND supabase_synced_at IS NULL").fetchone()
        supabase_pending = int(unsynced_releases["value"] or 0) + int(unsynced_matches["value"] or 0)
        return {"releases": {row["embedding_status"]: int(row["value"]) for row in releases},
                "match_jobs": {row["status"]: int(row["value"]) for row in jobs}, "related": int(related["value"] or 0),
                "last_sync_at": self.store.get_setting("press_release_last_sync_at", ""),
                "next_sync_at": self.store.get_setting("press_release_next_sync_at", ""),
                "last_error": self.store.get_setting("press_release_last_error", ""),
                "supabase_enabled": bool(self.mirror.enabled),
                "supabase_status": self.store.get_setting("press_release_supabase_status", "schema_required" if self.mirror.enabled else "disabled"),
                "supabase_pending": supabase_pending,
                "supabase_error": self.store.get_setting("press_release_supabase_error", "")}
