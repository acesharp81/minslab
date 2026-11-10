"""Immutable source/revision store; mutable pointers change in SQLite transactions."""
import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def uid():
    return uuid.uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else dump(value).encode()).hexdigest()


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "raw").mkdir(exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS cases (
              id TEXT PRIMARY KEY, title TEXT, predecessor TEXT, successor TEXT,
              created TEXT, current TEXT, confirmed TEXT, accepted TEXT);
            CREATE TABLE IF NOT EXISTS demo_sequences (kind TEXT PRIMARY KEY, number INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS case_members (case_id TEXT PRIMARY KEY REFERENCES cases(id), predecessor_id TEXT, successor_id TEXT);
            CREATE TABLE IF NOT EXISTS documents (
              id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id), path TEXT,
              sha TEXT, format TEXT, created TEXT, UNIQUE(case_id,path,sha));
            CREATE TABLE IF NOT EXISTS inherited_documents (doc_id TEXT PRIMARY KEY REFERENCES documents(id), case_id TEXT, source_doc_id TEXT);
            CREATE TABLE IF NOT EXISTS parses (
              id TEXT PRIMARY KEY, doc_id TEXT REFERENCES documents(id), parser TEXT,
              status TEXT, warnings TEXT, created TEXT, UNIQUE(doc_id,parser));
            CREATE TABLE IF NOT EXISTS blocks (
              id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id), parse_id TEXT REFERENCES parses(id),
              doc_id TEXT REFERENCES documents(id), ordinal INTEGER, location TEXT,
              kind TEXT, text TEXT, sha TEXT);
            CREATE TABLE IF NOT EXISTS revisions (
              id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id), parent TEXT,
              hash TEXT, payload TEXT, created TEXT, actor TEXT, reason TEXT);
            CREATE TABLE IF NOT EXISTS confirmations (
              revision TEXT PRIMARY KEY REFERENCES revisions(id), case_id TEXT, hash TEXT,
              created TEXT, warnings TEXT);
            CREATE TABLE IF NOT EXISTS handover_deliveries (
              id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id),
              revision_id TEXT REFERENCES revisions(id), revision_hash TEXT,
              sender_id TEXT, recipient_id TEXT, message TEXT, sent_at TEXT,
              UNIQUE(case_id,revision_id));
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id), input_hash TEXT,
              status TEXT, stage TEXT, progress INTEGER, attempts INTEGER, error TEXT,
              created TEXT, updated TEXT, result TEXT, config TEXT,
              UNIQUE(case_id,input_hash));
            CREATE TABLE IF NOT EXISTS discovery (
              job_id TEXT, doc_id TEXT, payload TEXT, PRIMARY KEY(job_id,doc_id));
            CREATE TABLE IF NOT EXISTS audit (
              id TEXT PRIMARY KEY, case_id TEXT, action TEXT, detail TEXT, created TEXT);
            CREATE INDEX IF NOT EXISTS blocks_case ON blocks(case_id);
            """)

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.root / "handover.sqlite", timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def rows(self, sql, args=()):
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.rows(sql, args)
        return rows[0] if rows else None

    def audit(self, db, case_id, action, detail):
        db.execute("INSERT INTO audit VALUES (?,?,?,?,?)", (uid(), case_id, action, dump(detail), now()))

    def revision(self, db, case_id, payload, parent, reason, actor="PREDECESSOR"):
        revision = uid()
        snapshot_hash = digest(payload)
        db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?,?,?)",
                   (revision, case_id, parent, snapshot_hash, dump(payload), now(), actor, reason))
        db.execute("UPDATE cases SET current=? WHERE id=?", (revision, case_id))
        self.audit(db, case_id, "REVISION", {"revision": revision, "parent": parent, "reason": reason})
        return revision
