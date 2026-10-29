import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = path
        with self.connect() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, created TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS references_registry(id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS usage_events(id TEXT PRIMARY KEY, body TEXT NOT NULL, synced INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, role TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at TEXT, actor TEXT, action TEXT, target TEXT, body TEXT);
            ''')
    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=20)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()
    def save(self, job):
        with self.connect() as c:
            c.execute('INSERT INTO jobs VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',
                      (job['id'], job['created_at'], json.dumps(job, ensure_ascii=False)))
    def get(self, jid):
        with self.connect() as c:
            r = c.execute('SELECT body FROM jobs WHERE id=?', (jid,)).fetchone()
        return json.loads(r[0]) if r else None
    def jobs(self):
        with self.connect() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT body FROM jobs ORDER BY created DESC LIMIT 100')]
    def references(self):
        with self.connect() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT body FROM references_registry ORDER BY id')]
    def audit(self, actor, action, target, body):
        with self.connect() as c:
            c.execute('INSERT INTO audit(at,actor,action,target,body) VALUES(?,?,?,?,?)',
                      (now(), actor, action, target, json.dumps(body, ensure_ascii=False)))
