import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def history_projection(job):
    """Small read model; neither observation inventories nor past results travel here."""
    rows=[]
    for run in job.get('runs',[]):
        options=run.get('options') or {}
        observation=run.get('observation') or {}
        reusable=options.get('mode')=='live' and run.get('scope')!='CROP' and (
            isinstance(observation.get('objects'),list) or any(
                r.get('status') not in ('ERROR','NOT_RUN','NOT_APPLICABLE') and r.get('observation')
                and r.get('model') not in (None,'none','mock-fixture') for r in run.get('results',[])))
        rows.append(dict(id=run.get('id'),created_at=run.get('created_at'),
                         vision_model=options.get('vision_model'),analysis_model=options.get('analysis_model'),
                         observation_model=run.get('observation_model'),options={'vision_model':options.get('vision_model')},
                         result_count=len(run.get('results',[])),review_count=len(run.get('reviews',[])),
                         object_count=len(observation.get('objects') or []),reusable_observation=bool(reusable)))
    summary={k:job.get(k) for k in ('id','metadata','created_at','state','demo')}
    summary['run_count']=len(rows)
    return summary,rows


class Store:
    def __init__(self, path):
        self.path = path
        with self.connect() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            BEGIN IMMEDIATE;
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, created TEXT NOT NULL, body TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS jobs_created_idx ON jobs(created DESC,id DESC);
            CREATE TABLE IF NOT EXISTS job_history(
                id TEXT PRIMARY KEY,created TEXT NOT NULL,state TEXT NOT NULL,summary TEXT NOT NULL,versions TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS job_history_created_idx ON job_history(created DESC,id DESC);
            CREATE INDEX IF NOT EXISTS job_history_state_idx ON job_history(state);
            CREATE TABLE IF NOT EXISTS job_history_dirty(id TEXT PRIMARY KEY);
            DROP TRIGGER IF EXISTS jobs_history_insert;
            DROP TRIGGER IF EXISTS jobs_history_update;
            CREATE TRIGGER jobs_history_insert AFTER INSERT ON jobs BEGIN
                INSERT INTO job_history_dirty SELECT NEW.id WHERE NOT EXISTS(SELECT 1 FROM job_history_dirty WHERE id=NEW.id);
            END;
            CREATE TRIGGER jobs_history_update AFTER UPDATE OF body,created ON jobs BEGIN
                INSERT INTO job_history_dirty SELECT NEW.id WHERE NOT EXISTS(SELECT 1 FROM job_history_dirty WHERE id=NEW.id);
            END;
            CREATE TRIGGER IF NOT EXISTS jobs_history_delete AFTER DELETE ON jobs BEGIN
                DELETE FROM job_history WHERE id=OLD.id;
                DELETE FROM job_history_dirty WHERE id=OLD.id;
            END;
            CREATE TABLE IF NOT EXISTS references_registry(id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS usage_events(id TEXT PRIMARY KEY, body TEXT NOT NULL, synced INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, role TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at TEXT, actor TEXT, action TEXT, target TEXT, body TEXT);
            COMMIT;
            ''')
            c.execute('INSERT OR IGNORE INTO job_history_dirty SELECT id FROM jobs WHERE id NOT IN (SELECT id FROM job_history)')
        self.refresh_history()
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
            self._save_history(c,job)
    @staticmethod
    def _save_history(c,job):
        summary,versions=history_projection(job)
        c.execute('''INSERT INTO job_history VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            created=excluded.created,state=excluded.state,summary=excluded.summary,versions=excluded.versions''',
            (job['id'],job['created_at'],job.get('state','READY'),json.dumps(summary,ensure_ascii=False),json.dumps(versions,ensure_ascii=False)))
        c.execute('DELETE FROM job_history_dirty WHERE id=?',(job['id'],))
    def refresh_history(self,jid=None):
        # Legacy scripts may write raw SQL. Triggers invalidate by ID only;
        # rebuilding is transactional, so a concurrent update cannot be lost.
        with self.connect() as c:
            where=' WHERE id=?' if jid else ''
            args=(jid,) if jid else ()
            if not c.execute('SELECT 1 FROM job_history_dirty'+where+' LIMIT 1',args).fetchone():return
            c.execute('BEGIN IMMEDIATE')
            query='SELECT j.body FROM jobs j JOIN job_history_dirty d ON d.id=j.id'+(' WHERE j.id=?' if jid else '')
            for row in c.execute(query,args):self._save_history(c,json.loads(row[0]))
    def summaries(self,limit=100,offset=0):
        self.refresh_history()
        with self.connect() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT summary FROM job_history ORDER BY created DESC,id DESC LIMIT ? OFFSET ?',
                                                       (max(1,min(100,limit)),max(0,offset)))]
    def versions(self,jid):
        self.refresh_history(jid)
        with self.connect() as c:row=c.execute('SELECT versions FROM job_history WHERE id=?',(jid,)).fetchone()
        return json.loads(row[0]) if row else None
    def exists(self,jid):
        with self.connect() as c:return bool(c.execute('SELECT 1 FROM jobs WHERE id=?',(jid,)).fetchone())
    def active_jobs(self):
        self.refresh_history()
        with self.connect() as c:
            return [json.loads(r[0]) for r in c.execute("SELECT j.body FROM job_history h JOIN jobs j ON j.id=h.id WHERE h.state IN ('RUNNING','QUEUED')")]
    def active_count(self):
        self.refresh_history()
        with self.connect() as c:return c.execute("SELECT count(*) FROM job_history WHERE state IN ('RUNNING','QUEUED')").fetchone()[0]
    def view(self,jid,run_id=None):
        self.refresh_history(jid)
        with self.connect() as c:
            if run_id:
                row=c.execute("""SELECT json_set(j.body,'$.runs',json_array(json(r.value)))
                    FROM jobs j,json_each(j.body,'$.runs') r WHERE j.id=? AND json_extract(r.value,'$.id')=? LIMIT 1""",(jid,run_id)).fetchone()
            else:
                row=c.execute("""SELECT CASE WHEN json_array_length(body,'$.runs')>0
                    THEN json_set(body,'$.runs',json_array(json_extract(body,'$.runs[#-1]')))
                    ELSE body END FROM jobs WHERE id=?""",(jid,)).fetchone()
        if not row:return None
        job=json.loads(row[0]);versions=self.versions(jid) or []
        job.update(run_count=len(versions),history_truncated=len(versions)>len(job.get('runs',[])))
        current=job.get('runs',[])
        job['previous_reusable_run']=next((r for r in reversed(versions) if r['reusable_observation'] and (not current or r['id']!=current[-1]['id'])),None)
        return job
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
