"""Persistent automation queue and conservative spend reservations (no secrets)."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
from .ai_collection_progress import summarize

DEFAULTS = dict(enabled=False, profile='OPENAI', hour_kst=7, max_documents=20,
                daily_usd=2.0, monthly_usd=30.0, solar_total_usd=110.0,
                mini_tokens=9_000_000, large_tokens=900_000, search_enabled=True,
                queries=['수도권 주택 공급 착공 모집 공고', '서울 경기 인천 주택 정정 재모집'],
                seed_urls=[], sample_every=5, version=0)
ACTIVE = ('QUEUED', 'RUNNING', 'STOPPING')


class BudgetExceeded(Exception):
    pass


class Store:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / 'runtime' / 'ai-collection.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, status TEXT NOT NULL,
                created REAL NOT NULL, updated REAL NOT NULL, config TEXT NOT NULL,
                actor TEXT NOT NULL, schedule_day TEXT UNIQUE, error TEXT);
            CREATE UNIQUE INDEX IF NOT EXISTS one_active ON runs ((1))
                WHERE status IN ('QUEUED','RUNNING','STOPPING');
            CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, run_id TEXT,
                created REAL, kind TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, run_id TEXT, created REAL,
                provider TEXT, model TEXT, token_group TEXT, reserved_tokens INTEGER,
                reserved_usd REAL, input_tokens INTEGER, output_tokens INTEGER,
                cost_usd REAL, status TEXT);
            CREATE INDEX IF NOT EXISTS calls_created ON calls(created);
            CREATE INDEX IF NOT EXISTS events_run ON events(run_id,id);
            CREATE TABLE IF NOT EXISTS shared_settlements (event_id TEXT PRIMARY KEY, payload TEXT NOT NULL, synced INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS scans (document_id TEXT PRIMARY KEY, checked REAL);
            CREATE TABLE IF NOT EXISTS run_progress (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS worker (id INTEGER PRIMARY KEY, checked REAL);
            ''')
            db.execute('INSERT OR IGNORE INTO settings VALUES (1,?)', (json.dumps(DEFAULTS),))

    @contextmanager
    def db(self, write=False):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA journal_mode=WAL')
            if write: db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def settings(self):
        with self.db() as db:
            return {**DEFAULTS, **json.loads(db.execute('SELECT value FROM settings WHERE id=1').fetchone()[0])}

    def configure(self, config):
        with self.db(True) as db:
            old = json.loads(db.execute('SELECT value FROM settings WHERE id=1').fetchone()[0])
            if old['version'] != config['version']:
                raise ValueError('설정이 변경됐습니다. 새로고침 후 저장하세요')
            value = {**DEFAULTS, **config, 'version': old['version'] + 1}
            db.execute('UPDATE settings SET value=? WHERE id=1', (json.dumps(value),))
            db.execute('INSERT INTO events(run_id,created,kind,payload) VALUES (?,?,?,?)',
                       ('settings', time.time(), 'SETTINGS', json.dumps(value)))
        return value

    def enqueue(self, actor='관리자 실행', schedule_day=None, overrides=None):
        with self.db(True) as db:
            existing = db.execute("SELECT id FROM runs WHERE status IN ('QUEUED','RUNNING','STOPPING')").fetchone()
            if existing: return {'id': existing[0], 'already_running': True}
            if schedule_day and db.execute('SELECT id FROM runs WHERE schedule_day=?', (schedule_day,)).fetchone():
                return None
            config = db.execute('SELECT value FROM settings WHERE id=1').fetchone()[0]
            if overrides: config=json.dumps({**DEFAULTS,**json.loads(config),**overrides})
            rid = str(uuid.uuid4())
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)',
                       (rid, 'QUEUED', time.time(), time.time(), config, actor, schedule_day, None))
            return {'id': rid, 'already_running': False}

    def heartbeat(self):
        with self.db(True) as db:
            db.execute('INSERT OR REPLACE INTO worker VALUES (1,?)', (time.time(),))

    def claim(self):
        with self.db(True) as db:
            # Do not replay an uncertain/billed operation after process loss.
            db.execute("UPDATE runs SET status='INTERRUPTED',error='작업자 중단 · 완료 자료 보존, 다시 실행 가능' "
                       "WHERE status IN ('RUNNING','STOPPING') AND updated<?", (time.time()-300,))
            if db.execute("SELECT 1 FROM runs WHERE status IN ('RUNNING','STOPPING')").fetchone(): return None
            row = db.execute("SELECT * FROM runs WHERE status='QUEUED' ORDER BY created LIMIT 1").fetchone()
            if not row: return None
            db.execute("UPDATE runs SET status='RUNNING',updated=? WHERE id=?", (time.time(), row['id']))
            return {**dict(row), 'config': json.loads(row['config'])}

    def alive(self, rid):
        with self.db(True) as db:
            row = db.execute('SELECT status FROM runs WHERE id=?', (rid,)).fetchone()
            if not row or row[0] != 'RUNNING': return False
            db.execute('UPDATE runs SET updated=? WHERE id=?', (time.time(), rid))
            return True

    def stop(self, rid):
        with self.db(True) as db:
            db.execute("UPDATE runs SET status=CASE WHEN status='QUEUED' THEN 'CANCELLED' ELSE 'STOPPING' END, "
                       "updated=? WHERE id=? AND status IN ('QUEUED','RUNNING')", (time.time(), rid))
        return {'id': rid}

    def finish(self, rid, status, error=None):
        with self.db(True) as db:
            db.execute('UPDATE runs SET status=?,updated=?,error=? WHERE id=?', (status, time.time(), error, rid))

    def event(self, rid, kind, **payload):
        with self.db(True) as db:
            db.execute('INSERT INTO events(run_id,created,kind,payload) VALUES (?,?,?,?)',
                       (rid, time.time(), kind, json.dumps(payload, ensure_ascii=False)))

    def checkpoint(self, rid, **changes):
        with self.db(True) as db:
            row=db.execute('SELECT payload FROM run_progress WHERE run_id=?',(rid,)).fetchone()
            value=json.loads(row[0]) if row else {}
            if any(k in changes and changes[k]!=value.get(k) for k in ('stage','current','model')):
                value['phase_started']=time.time()
            value.update(changes,updated_at=time.time())
            db.execute('INSERT INTO run_progress VALUES (?,?) ON CONFLICT(run_id) DO UPDATE SET payload=excluded.payload',
                       (rid,json.dumps(value,ensure_ascii=False)))

    def confirmed_tokens(self, rid):
        with self.db() as db:
            return db.execute('SELECT COALESCE(SUM(input_tokens+output_tokens),0) FROM calls WHERE run_id=?',(rid,)).fetchone()[0]

    def scanned(self, document_id):
        with self.db(True) as db:
            db.execute('INSERT OR REPLACE INTO scans VALUES (?,?)',(document_id,time.time()))

    def scan_times(self):
        with self.db() as db:
            return {r[0]:r[1] for r in db.execute('SELECT document_id,checked FROM scans')}

    def reserve(self, rid, provider, model, group, tokens, cost, config):
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        with self.db(True) as db:
            def total(start, column, extra='', args=()):
                return db.execute(f'SELECT COALESCE(SUM({column}),0) FROM calls WHERE created>=? '+extra,
                                  (start.timestamp(), *args)).fetchone()[0]
            dollars = 'COALESCE(cost_usd,reserved_usd)'
            unlimited = provider == 'SOLAR' and os.environ.get('SHARED_SOLAR_UNLIMITED','false').lower() == 'true'
            cap_filter = "AND provider!='SOLAR'" if os.environ.get('SHARED_SOLAR_UNLIMITED','false').lower() == 'true' else ''
            if not unlimited and (total(today, dollars,cap_filter)+cost > config['daily_usd'] or total(today.replace(day=1), dollars,cap_filter)+cost > config['monthly_usd']):
                raise BudgetExceeded('일/월 비용 상한 도달 · 다음 실행 또는 예산 조정 필요')
            if provider == 'SOLAR':
                used = db.execute(f"SELECT COALESCE(SUM({dollars}),0) FROM calls WHERE provider='SOLAR'").fetchone()[0]
                if not unlimited and used+cost > config['solar_total_usd']: raise BudgetExceeded('Solar 누적 비용 상한 도달')
            elif group in ('mini','large'):
                used = total(today, 'COALESCE(input_tokens+output_tokens,reserved_tokens)', 'AND token_group=?', (group,))
                if used+tokens > config['mini_tokens' if group=='mini' else 'large_tokens']:
                    raise BudgetExceeded('모델 그룹 일일 토큰 상한 도달 · 한국시간 09시 갱신')
            cid = str(uuid.uuid4())
            db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                       (cid,rid,time.time(),provider,model,group,tokens,cost,None,None,None,'RESERVED'))
            return cid

    def settle(self, cid, input_tokens, output_tokens, cost):
        with self.db(True) as db:
            db.execute("UPDATE calls SET input_tokens=?,output_tokens=?,cost_usd=?,status='COMPLETED' WHERE id=?",
                       (input_tokens, output_tokens, cost, cid))

    def fail_call(self, cid):
        with self.db(True) as db:
            db.execute("UPDATE calls SET status='UNKNOWN_COST' WHERE id=?", (cid,))

    def status(self):
        with self.db() as db:
            runs = [dict(r) for r in db.execute('SELECT * FROM runs ORDER BY created DESC LIMIT 20')]
            for r in runs:
                r['config'] = json.loads(r['config'])
                r['events'] = [dict(kind=e['kind'], **json.loads(e['payload'])) for e in db.execute(
                    'SELECT kind,payload FROM events WHERE run_id=? ORDER BY id DESC LIMIT 100', (r['id'],))]
                r['cost_usd'] = db.execute('SELECT COALESCE(SUM(COALESCE(cost_usd,reserved_usd)),0) FROM calls WHERE run_id=?', (r['id'],)).fetchone()[0]
                progress=db.execute('SELECT payload FROM run_progress WHERE run_id=?',(r['id'],)).fetchone()
                calls=[dict(c) for c in db.execute('SELECT model,input_tokens,output_tokens,reserved_tokens,status FROM calls WHERE run_id=?',(r['id'],))]
                counts=dict(db.execute('SELECT kind,count(*) FROM events WHERE run_id=? GROUP BY kind',(r['id'],)).fetchall())
                r['progress']=summarize(r,json.loads(progress[0]) if progress else {},calls,counts)
            day = datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
            usage = [dict(r) for r in db.execute('SELECT provider,token_group,SUM(COALESCE(input_tokens+output_tokens,reserved_tokens)) AS tokens, '
                'SUM(COALESCE(cost_usd,reserved_usd)) AS cost_usd FROM calls WHERE created>=? GROUP BY provider,token_group', (day,))]
            health = db.execute('SELECT checked FROM worker WHERE id=1').fetchone()
        return dict(settings=self.settings(), runs=runs, usage=usage,
                    worker_online=bool(health and time.time()-health[0]<90),
                    usage_note='이 자동화의 사용량·공개 단가 추정치입니다. 조직 전체 무료 잔여량·실제 청구액은 제공사 Usage에서 확인하세요.')
