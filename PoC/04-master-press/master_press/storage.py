from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


KST = timezone(timedelta(hours=9))


def now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def json_value(value, default):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def normalized_clock_values(values: Any) -> list[str]:
    result = []
    for value in values if isinstance(values, list) else []:
        parts = str(value).strip().split(":", 1)
        try:
            hour, minute = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            continue
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            result.append(f"{hour:02d}:{minute:02d}")
    return sorted(dict.fromkeys(result))


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  topic_description TEXT NOT NULL DEFAULT '',
  include_terms TEXT NOT NULL DEFAULT '[]',
  required_terms TEXT NOT NULL DEFAULT '[]',
  exclude_terms TEXT NOT NULL DEFAULT '[]',
  synonym_terms TEXT NOT NULL DEFAULT '{}',
  urgent_terms TEXT NOT NULL DEFAULT '[]',
  include_publishers TEXT NOT NULL DEFAULT '[]',
  exclude_publishers TEXT NOT NULL DEFAULT '[]',
  rss_urls TEXT NOT NULL DEFAULT '[]',
  collection_mode TEXT NOT NULL DEFAULT 'interval',
  collection_interval_minutes INTEGER NOT NULL DEFAULT 30,
  collection_times TEXT NOT NULL DEFAULT '[]',
  delivery_mode TEXT NOT NULL DEFAULT 'immediate',
  delivery_times TEXT NOT NULL DEFAULT '[]',
  relevance_threshold REAL NOT NULL DEFAULT 75,
  hold_threshold REAL NOT NULL DEFAULT 55,
  keyword_weight REAL NOT NULL DEFAULT 0.3,
  semantic_weight REAL NOT NULL DEFAULT 0.4,
  llm_weight REAL NOT NULL DEFAULT 0.3,
  max_articles_per_message INTEGER NOT NULL DEFAULT 2,
  is_active INTEGER NOT NULL DEFAULT 1,
  version INTEGER NOT NULL DEFAULT 1,
  next_collect_at TEXT,
  last_collected_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS cases_max_five
BEFORE INSERT ON cases
WHEN (SELECT COUNT(*) FROM cases) >= 5
BEGIN
  SELECT RAISE(ABORT, 'cases are limited to five');
END;

CREATE TABLE IF NOT EXISTS case_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  snapshot TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(case_id, version)
);

CREATE TABLE IF NOT EXISTS recipients (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  kakao_user_id TEXT UNIQUE,
  access_token_ciphertext TEXT,
  refresh_token_ciphertext TEXT,
  access_token_expires_at TEXT,
  refresh_token_expires_at TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS case_recipients (
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  recipient_id TEXT NOT NULL REFERENCES recipients(id) ON DELETE CASCADE,
  PRIMARY KEY(case_id, recipient_id)
);

CREATE TABLE IF NOT EXISTS recipient_invites (
  id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  label TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS articles (
  id TEXT PRIMARY KEY,
  canonical_url TEXT NOT NULL UNIQUE,
  original_url TEXT NOT NULL,
  title TEXT NOT NULL,
  publisher TEXT NOT NULL DEFAULT '',
  published_at TEXT,
  snippet TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL DEFAULT '',
  body_expires_at TEXT,
  content_hash TEXT,
  source_type TEXT NOT NULL DEFAULT 'naver',
  first_seen_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS article_scores (
  id TEXT PRIMARY KEY,
  article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  case_version INTEGER NOT NULL,
  keyword_score REAL NOT NULL,
  semantic_score REAL NOT NULL,
  llm_score REAL NOT NULL,
  final_score REAL NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  reasons TEXT NOT NULL DEFAULT '[]',
  matched_terms TEXT NOT NULL DEFAULT '[]',
  low_score_categories TEXT NOT NULL DEFAULT '[]',
  decision TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(article_id, case_id)
);

CREATE TABLE IF NOT EXISTS deliveries (
  id TEXT PRIMARY KEY,
  article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  recipient_id TEXT NOT NULL REFERENCES recipients(id) ON DELETE CASCADE,
  scheduled_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  response_code INTEGER,
  last_error TEXT,
  sent_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(article_id, case_id, recipient_id)
);

CREATE TABLE IF NOT EXISTS collection_runs (
  id TEXT PRIMARY KEY,
  case_id TEXT REFERENCES cases(id) ON DELETE SET NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  collected_count INTEGER NOT NULL DEFAULT 0,
  new_count INTEGER NOT NULL DEFAULT 0,
  scored_count INTEGER NOT NULL DEFAULT 0,
  queued_count INTEGER NOT NULL DEFAULT 0,
  error TEXT
);

CREATE TABLE IF NOT EXISTS improvement_reports (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  sample_count INTEGER NOT NULL,
  average_score REAL NOT NULL,
  categories TEXT NOT NULL,
  suggestions TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scores_case_created ON article_scores(case_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scores_final ON article_scores(final_score);
CREATE INDEX IF NOT EXISTS idx_deliveries_due ON deliveries(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);
"""


class Store:
    CASE_JSON_FIELDS = {
        "include_terms": [], "required_terms": [], "exclude_terms": [], "synonym_terms": {},
        "urgent_terms": [], "include_publishers": [], "exclude_publishers": [], "rss_urls": [],
        "collection_times": [], "delivery_times": [],
    }

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self.connect() as connection:
            connection.executescript(SCHEMA)
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    @classmethod
    def decode_case(cls, row: sqlite3.Row | dict) -> dict:
        item = dict(row)
        for field, default in cls.CASE_JSON_FIELDS.items():
            item[field] = json_value(item.get(field), default)
        item["is_active"] = bool(item.get("is_active"))
        return item

    def list_cases(self, active_only: bool = False) -> list[dict]:
        query = "SELECT * FROM cases"
        if active_only:
            query += " WHERE is_active=1"
        query += " ORDER BY created_at"
        with self.connect() as connection:
            return [self.decode_case(row) for row in connection.execute(query)]

    def get_case(self, case_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        return self.decode_case(row) if row else None

    def save_case(self, payload: dict, case_id: str | None = None) -> dict:
        now = now_iso()
        existing = self.get_case(case_id) if case_id else None
        if not existing and len(self.list_cases()) >= 5:
            raise ValueError("케이스는 최대 5개까지 만들 수 있습니다.")
        values: dict[str, Any] = {
            "name": str(payload.get("name") or (existing or {}).get("name") or "새 케이스").strip()[:80],
            "topic_description": str(payload.get("topic_description", (existing or {}).get("topic_description", ""))).strip()[:2000],
            "collection_mode": payload.get("collection_mode", (existing or {}).get("collection_mode", "interval")),
            "collection_interval_minutes": max(5, min(1440, int(payload.get("collection_interval_minutes", (existing or {}).get("collection_interval_minutes", 30))))),
            "delivery_mode": payload.get("delivery_mode", (existing or {}).get("delivery_mode", "immediate")),
            "relevance_threshold": max(0, min(100, float(payload.get("relevance_threshold", (existing or {}).get("relevance_threshold", 75))))),
            "hold_threshold": max(0, min(100, float(payload.get("hold_threshold", (existing or {}).get("hold_threshold", 55))))),
            "keyword_weight": max(0, float(payload.get("keyword_weight", (existing or {}).get("keyword_weight", 0.3)))),
            "semantic_weight": max(0, float(payload.get("semantic_weight", (existing or {}).get("semantic_weight", 0.4)))),
            "llm_weight": max(0, float(payload.get("llm_weight", (existing or {}).get("llm_weight", 0.3)))),
            "max_articles_per_message": max(1, min(5, int(payload.get("max_articles_per_message", (existing or {}).get("max_articles_per_message", 2))))),
            "is_active": 1 if payload.get("is_active", (existing or {}).get("is_active", True)) else 0,
        }
        if values["collection_mode"] not in {"interval", "times"}:
            raise ValueError("올바르지 않은 수집 방식입니다.")
        if values["delivery_mode"] not in {"immediate", "times"}:
            raise ValueError("올바르지 않은 발송 방식입니다.")
        for field, default in self.CASE_JSON_FIELDS.items():
            raw = payload.get(field, (existing or {}).get(field, default))
            values[field] = json.dumps(raw if isinstance(raw, type(default)) else default, ensure_ascii=False)

        collection_times = normalized_clock_values(json_value(values["collection_times"], []))
        delivery_times = normalized_clock_values(json_value(values["delivery_times"], []))
        values["collection_times"] = json.dumps(collection_times, ensure_ascii=False)
        values["delivery_times"] = json.dumps(delivery_times, ensure_ascii=False)
        if values["collection_mode"] == "times" and not collection_times:
            raise ValueError("지정 시각 수집에는 올바른 HH:MM 시각이 하나 이상 필요합니다.")
        if values["delivery_mode"] == "times" and not delivery_times:
            raise ValueError("지정 시각 발송에는 올바른 HH:MM 시각이 하나 이상 필요합니다.")
        if values["hold_threshold"] > values["relevance_threshold"]:
            raise ValueError("보류 기준은 전송 기준보다 높을 수 없습니다.")

        weight_total = values["keyword_weight"] + values["semantic_weight"] + values["llm_weight"]
        if weight_total <= 0:
            raise ValueError("관련도 가중치 합은 0보다 커야 합니다.")
        case_id = case_id or str(uuid.uuid4())
        version = int((existing or {}).get("version", 0)) + 1
        with self._lock, self.connect() as connection:
            if existing:
                assignments = ",".join(f"{key}=?" for key in values)
                connection.execute(
                    f"UPDATE cases SET {assignments},version=?,updated_at=? WHERE id=?",
                    (*values.values(), version, now, case_id),
                )
            else:
                columns = ["id", *values, "version", "created_at", "updated_at"]
                marks = ",".join("?" for _ in columns)
                connection.execute(
                    f"INSERT INTO cases ({','.join(columns)}) VALUES ({marks})",
                    (case_id, *values.values(), version, now, now),
                )
            row = connection.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
            snapshot = self.decode_case(row) if row else {"id": case_id, **values, "version": version}
            connection.execute(
                "INSERT OR REPLACE INTO case_versions(case_id,version,snapshot,created_at) VALUES(?,?,?,?)",
                (case_id, version, json.dumps(snapshot, ensure_ascii=False, default=str), now),
            )
        return self.get_case(case_id) or {}

    def delete_case(self, case_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM cases WHERE id=?", (case_id,))
            return cursor.rowcount > 0

    def set_case_recipients(self, case_id: str, recipient_ids: Iterable[str]) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM case_recipients WHERE case_id=?", (case_id,))
            connection.executemany(
                "INSERT INTO case_recipients(case_id,recipient_id) VALUES(?,?)",
                [(case_id, value) for value in dict.fromkeys(recipient_ids)],
            )

    def case_recipient_ids(self, case_id: str) -> list[str]:
        with self.connect() as connection:
            return [row[0] for row in connection.execute("SELECT recipient_id FROM case_recipients WHERE case_id=?", (case_id,))]

    def list_recipients(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id,label,kakao_user_id,access_token_expires_at,refresh_token_expires_at,status,last_error,created_at,updated_at FROM recipients ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_article(self, article_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
        return dict(row) if row else None

    def get_recipient(self, recipient_id: str, include_tokens: bool = False) -> dict | None:
        fields = "*" if include_tokens else "id,label,kakao_user_id,access_token_expires_at,refresh_token_expires_at,status,last_error,created_at,updated_at"
        with self.connect() as connection:
            row = connection.execute(f"SELECT {fields} FROM recipients WHERE id=?", (recipient_id,)).fetchone()
        return dict(row) if row else None

    def create_invite(self, label: str, ttl_minutes: int = 60) -> tuple[dict, str]:
        token = secrets.token_urlsafe(32)
        now = datetime.now(KST)
        record = {
            "id": str(uuid.uuid4()),
            "label": str(label or "카카오 수신자").strip()[:80],
            "expires_at": (now + timedelta(minutes=max(5, min(ttl_minutes, 1440)))).isoformat(timespec="seconds"),
            "created_at": now.isoformat(timespec="seconds"),
        }
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO recipient_invites(id,token_hash,label,expires_at,created_at) VALUES(?,?,?,?,?)",
                (record["id"], hashlib.sha256(token.encode()).hexdigest(), record["label"], record["expires_at"], record["created_at"]),
            )
        return record, token

    def valid_invite(self, token: str) -> dict | None:
        token_hash = hashlib.sha256(str(token).encode()).hexdigest()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM recipient_invites WHERE token_hash=? AND used_at IS NULL AND expires_at>?",
                (token_hash, now_iso()),
            ).fetchone()
        return dict(row) if row else None

    def consume_invite(self, token: str, token_data: dict) -> dict:
        invite = self.valid_invite(token)
        if not invite:
            raise ValueError("수신자 등록 링크가 만료되었거나 이미 사용되었습니다.")
        now = now_iso()
        recipient_id = str(uuid.uuid4())
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO recipients(
                   id,label,kakao_user_id,access_token_ciphertext,refresh_token_ciphertext,
                   access_token_expires_at,refresh_token_expires_at,status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(kakao_user_id) DO UPDATE SET
                   label=excluded.label,access_token_ciphertext=excluded.access_token_ciphertext,
                   refresh_token_ciphertext=excluded.refresh_token_ciphertext,
                   access_token_expires_at=excluded.access_token_expires_at,
                   refresh_token_expires_at=excluded.refresh_token_expires_at,status='active',updated_at=excluded.updated_at""",
                (
                    recipient_id, invite["label"], str(token_data["kakao_user_id"]),
                    token_data["access_token_ciphertext"], token_data["refresh_token_ciphertext"],
                    token_data["access_token_expires_at"], token_data["refresh_token_expires_at"],
                    "active", now, now,
                ),
            )
            connection.execute("UPDATE recipient_invites SET used_at=? WHERE id=?", (now, invite["id"]))
            row = connection.execute("SELECT id FROM recipients WHERE kakao_user_id=?", (str(token_data["kakao_user_id"]),)).fetchone()
        return self.get_recipient(row["id"]) or {}

    def update_recipient_tokens(self, recipient_id: str, values: dict) -> None:
        allowed = {"access_token_ciphertext", "refresh_token_ciphertext", "access_token_expires_at", "refresh_token_expires_at", "status", "last_error"}
        clean = {key: value for key, value in values.items() if key in allowed}
        if not clean:
            return
        with self.connect() as connection:
            assignments = ",".join(f"{key}=?" for key in clean)
            connection.execute(f"UPDATE recipients SET {assignments},updated_at=? WHERE id=?", (*clean.values(), now_iso(), recipient_id))

    def delete_recipient(self, recipient_id: str) -> bool:
        with self.connect() as connection:
            return connection.execute("DELETE FROM recipients WHERE id=?", (recipient_id,)).rowcount > 0

    def upsert_article(self, article: dict) -> tuple[dict, bool]:
        now = now_iso()
        with self.connect() as connection:
            existing = connection.execute("SELECT * FROM articles WHERE canonical_url=?", (article["canonical_url"],)).fetchone()
            if existing:
                connection.execute(
                    """UPDATE articles SET original_url=?,title=?,publisher=?,published_at=?,snippet=?,
                       body=CASE WHEN ?<>'' THEN ? ELSE body END,
                       body_expires_at=CASE WHEN ?<>'' THEN ? ELSE body_expires_at END,
                       content_hash=COALESCE(?,content_hash),updated_at=? WHERE id=?""",
                    (
                        article["original_url"], article["title"], article.get("publisher", ""), article.get("published_at"),
                        article.get("snippet", ""), article.get("body", ""), article.get("body", ""), article.get("body", ""),
                        article.get("body_expires_at"), article.get("content_hash"), now, existing["id"],
                    ),
                )
                article_id, created = existing["id"], False
            else:
                article_id, created = str(uuid.uuid4()), True
                connection.execute(
                    """INSERT INTO articles(id,canonical_url,original_url,title,publisher,published_at,snippet,body,
                       body_expires_at,content_hash,source_type,first_seen_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        article_id, article["canonical_url"], article["original_url"], article["title"], article.get("publisher", ""),
                        article.get("published_at"), article.get("snippet", ""), article.get("body", ""), article.get("body_expires_at"),
                        article.get("content_hash"), article.get("source_type", "naver"), now, now,
                    ),
                )
            row = connection.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
        return dict(row), created

    def score_exists(self, article_id: str, case_id: str) -> bool:
        with self.connect() as connection:
            return connection.execute("SELECT 1 FROM article_scores WHERE article_id=? AND case_id=?", (article_id, case_id)).fetchone() is not None

    def save_score(self, article_id: str, case_id: str, case_version: int, result: dict) -> dict:
        now = now_iso()
        score_id = str(uuid.uuid4())
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO article_scores(
                   id,article_id,case_id,case_version,keyword_score,semantic_score,llm_score,final_score,
                   summary,reasons,matched_terms,low_score_categories,decision,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(article_id,case_id) DO UPDATE SET
                   case_version=excluded.case_version,keyword_score=excluded.keyword_score,
                   semantic_score=excluded.semantic_score,llm_score=excluded.llm_score,
                   final_score=excluded.final_score,summary=excluded.summary,reasons=excluded.reasons,
                   matched_terms=excluded.matched_terms,low_score_categories=excluded.low_score_categories,
                   decision=excluded.decision,updated_at=excluded.updated_at""",
                (
                    score_id, article_id, case_id, case_version, result["keyword_score"], result["semantic_score"],
                    result["llm_score"], result["final_score"], result.get("summary", ""),
                    json.dumps(result.get("reasons", []), ensure_ascii=False),
                    json.dumps(result.get("matched_terms", []), ensure_ascii=False),
                    json.dumps(result.get("low_score_categories", []), ensure_ascii=False),
                    result["decision"], now, now,
                ),
            )
            row = connection.execute("SELECT * FROM article_scores WHERE article_id=? AND case_id=?", (article_id, case_id)).fetchone()
        return dict(row)

    def queue_delivery(self, article_id: str, case_id: str, recipient_id: str, scheduled_at: str) -> None:
        now = now_iso()
        with self.connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO deliveries(id,article_id,case_id,recipient_id,scheduled_at,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), article_id, case_id, recipient_id, scheduled_at, now, now),
            )

    def due_deliveries(self, limit: int = 20) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT d.*,a.title,a.original_url,a.publisher,a.published_at,s.summary,s.final_score,c.name AS case_name
                   FROM deliveries d JOIN articles a ON a.id=d.article_id
                   JOIN article_scores s ON s.article_id=d.article_id AND s.case_id=d.case_id
                   JOIN cases c ON c.id=d.case_id
                   WHERE d.status IN ('pending','retry') AND d.scheduled_at<=? AND d.attempts<3
                   ORDER BY d.scheduled_at LIMIT ?""",
                (now_iso(), limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def finish_delivery(self, delivery_id: str, ok: bool, response_code: int | None = None, error: str = "") -> None:
        now = now_iso()
        with self.connect() as connection:
            connection.execute(
                """UPDATE deliveries SET status=?,attempts=attempts+1,response_code=?,last_error=?,sent_at=?,updated_at=? WHERE id=?""",
                ("sent" if ok else "retry", response_code, error[:1000], now if ok else None, now, delivery_id),
            )

    def start_run(self, case_id: str) -> str:
        run_id = str(uuid.uuid4())
        with self.connect() as connection:
            connection.execute("INSERT INTO collection_runs(id,case_id,started_at,status) VALUES(?,?,?,'running')", (run_id, case_id, now_iso()))
        return run_id

    def finish_run(self, run_id: str, status: str, counts: dict | None = None, error: str = "") -> None:
        counts = counts or {}
        with self.connect() as connection:
            connection.execute(
                """UPDATE collection_runs SET finished_at=?,status=?,collected_count=?,new_count=?,scored_count=?,queued_count=?,error=? WHERE id=?""",
                (now_iso(), status, counts.get("collected", 0), counts.get("new", 0), counts.get("scored", 0), counts.get("queued", 0), error[:2000], run_id),
            )

    def set_case_schedule(self, case_id: str, next_collect_at: str, collected: bool = False) -> None:
        with self.connect() as connection:
            if collected:
                connection.execute("UPDATE cases SET next_collect_at=?,last_collected_at=?,updated_at=? WHERE id=?", (next_collect_at, now_iso(), now_iso(), case_id))
            else:
                connection.execute("UPDATE cases SET next_collect_at=?,updated_at=? WHERE id=?", (next_collect_at, now_iso(), case_id))

    def list_due_cases(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM cases WHERE is_active=1 AND (next_collect_at IS NULL OR next_collect_at<=?) ORDER BY next_collect_at", (now_iso(),)).fetchall()
        return [self.decode_case(row) for row in rows]

    def dashboard(self, case_id: str | None = None, limit: int = 100) -> dict:
        filters, params = "", []
        if case_id:
            filters, params = "WHERE s.case_id=?", [case_id]
        with self.connect() as connection:
            articles = connection.execute(
                f"""SELECT a.id,a.title,a.original_url,a.publisher,a.published_at,a.first_seen_at,
                    s.case_id,s.keyword_score,s.semantic_score,s.llm_score,s.final_score,s.summary,
                    s.reasons,s.low_score_categories,s.decision,c.name AS case_name
                    FROM article_scores s JOIN articles a ON a.id=s.article_id JOIN cases c ON c.id=s.case_id
                    {filters} ORDER BY s.created_at DESC LIMIT ?""",
                (*params, limit),
            ).fetchall()
            stats = connection.execute(
                f"""SELECT COUNT(*) total,
                    COALESCE(SUM(CASE WHEN decision='send' THEN 1 ELSE 0 END),0) sent_candidates,
                    COALESCE(SUM(CASE WHEN decision='hold' THEN 1 ELSE 0 END),0) held,
                    COALESCE(SUM(CASE WHEN decision='low' THEN 1 ELSE 0 END),0) low,
                    COALESCE(ROUND(AVG(final_score),1),0) average_score
                    FROM article_scores s {filters}""",
                params,
            ).fetchone()
            publishers = connection.execute(
                f"""SELECT a.publisher label,COUNT(*) value FROM article_scores s JOIN articles a ON a.id=s.article_id
                    {filters} GROUP BY a.publisher ORDER BY value DESC LIMIT 10""",
                params,
            ).fetchall()
            deliveries = connection.execute("SELECT status,COUNT(*) value FROM deliveries GROUP BY status").fetchall()
            recent_runs = connection.execute("SELECT * FROM collection_runs ORDER BY started_at DESC LIMIT 10").fetchall()
        decoded = []
        for row in articles:
            item = dict(row)
            item["reasons"] = json_value(item["reasons"], [])
            item["low_score_categories"] = json_value(item["low_score_categories"], [])
            decoded.append(item)
        return {
            "stats": dict(stats) if stats else {},
            "articles": decoded,
            "publishers": [dict(row) for row in publishers],
            "deliveries": [dict(row) for row in deliveries],
            "recent_runs": [dict(row) for row in recent_runs],
        }

    def low_score_analysis(self, case_id: str, days: int = 7) -> dict:
        since = (datetime.now(KST) - timedelta(days=days)).isoformat(timespec="seconds")
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT final_score,low_score_categories FROM article_scores WHERE case_id=? AND decision<>'send' AND created_at>=?",
                (case_id, since),
            ).fetchall()
        categories: dict[str, int] = {}
        for row in rows:
            for category in json_value(row["low_score_categories"], []):
                categories[category] = categories.get(category, 0) + 1
        average = sum(float(row["final_score"]) for row in rows) / len(rows) if rows else 0
        suggestions = []
        mapping = {
            "required_term_missing": "필수 키워드가 지나치게 제한적인지 확인하세요.",
            "excluded_term": "제외 키워드가 적절히 오탐을 제거하는지 사례를 검토하세요.",
            "title_only_match": "제목에만 등장하는 키워드의 본문 일치 조건을 강화하세요.",
            "low_semantic_similarity": "주제 설명에 구체적인 대상·행위·지역 표현을 추가하세요.",
            "body_unavailable": "본문 접근 제한 언론사는 검색 요약문 기준 별도 임계점을 고려하세요.",
        }
        for key, _count in sorted(categories.items(), key=lambda item: item[1], reverse=True)[:5]:
            if key in mapping:
                suggestions.append(mapping[key])
        return {"sample_count": len(rows), "average_score": round(average, 1), "categories": categories, "suggestions": suggestions}

    def cleanup(self, raw_days: int, metadata_days: int) -> dict:
        raw_cutoff = (datetime.now(KST) - timedelta(days=raw_days)).isoformat(timespec="seconds")
        metadata_cutoff = (datetime.now(KST) - timedelta(days=metadata_days)).isoformat(timespec="seconds")
        with self.connect() as connection:
            raw = connection.execute("UPDATE articles SET body='',body_expires_at=NULL WHERE body<>'' AND first_seen_at<?", (raw_cutoff,)).rowcount
            meta = connection.execute(
                "DELETE FROM articles WHERE first_seen_at<? AND id NOT IN (SELECT article_id FROM deliveries WHERE status IN ('pending','retry'))",
                (metadata_cutoff,),
            ).rowcount
            connection.execute("DELETE FROM recipient_invites WHERE expires_at<?", (now_iso(),))
        return {"cleared_bodies": raw, "deleted_articles": meta}
