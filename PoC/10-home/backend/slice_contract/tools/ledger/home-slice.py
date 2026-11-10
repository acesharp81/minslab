#!/usr/bin/env python3
"""HOME 원천 데이터셋 슬라이스 — 만들기(make)·반영(apply).

슬라이스 = 우리 변환기·생성기가 실제로 읽는 HOME 원천(kind·작은 표)과 칸만 잘라 낸 JSON 묶음(패키지).
정의는 schemas/home-slices/slices.json, 명세는 docs/product/HOME-데이터셋-슬라이스-명세.md.

  make  --new <판> [--base <판> --since <시각>] --out <패키지> [--alembic-version V] [--api <폴더>]
        내부 판(home-dump.py 출력) 둘로 패키지를 만든다(시험·HOME 참고 구현). --base 없이 --new 만 주면 전체 슬라이스.
  sql   HOME DB 에서 내보내기 폴더를 만드는 psql 스크립트를 찍는다(slices.json 에서 만든다)
  seal  --export <폴더> --out <패키지> [--api <폴더>]
        HOME 이 SQL 로 뽑은 내보내기(export.json + rows/<이름>.jsonl, 실명 포함 — HOME 밖으로 내지 않는다)를 잘라·지워 패키지로 봉인한다.
  apply [--base <판>] --in <패키지> --out <새 판>
        기준 판 + 패키지 → 내부 형식 새 판(<이름>.jsonl.gz + manifest.json, home-source.js readHome 이 그대로 읽는다).
        전체 패키지(since 없음)는 --base 없이 쓴다(= 판을 슬라이스 칸으로 자르기).

직렬화·gzip·키 검사는 home-dump.py 의 dumps·encode_rows·key_scan 을 그대로 쓴다(같은 입력 → 바이트까지 같은 출력).
멈춤(종료 코드 2): sha256·행 수 불일치, 키 검사 걸림, 정의에 없는 슬라이스·칸, since > 기준 판 스냅샷(빈 구간), 반영 결과의 count·digest 불일치.
"""
import argparse, gzip, hashlib, importlib.util, json, os, re, sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPEC_FILE = os.path.join(ROOT, 'schemas', 'home-slices', 'slices.json')
FORMAT = 'home-slices/1'

_s = importlib.util.spec_from_file_location('home_dump', os.path.join(ROOT, 'tools', 'ledger', 'home-dump.py'))
HD = importlib.util.module_from_spec(_s)
_s.loader.exec_module(HD)
dumps, encode_rows, key_scan = HD.dumps, HD.encode_rows, HD.key_scan


class Stop(Exception):
    pass


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ---- 시각: PostgreSQL TimeZone=UTC 의 ::text 꼴('2026-10-22 13:32:48.919713+00')과 ISO 를 읽는다 ----
_TS = re.compile(r'^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}(?::?\d{2})?)$')


def parse_ts(s):
    m = _TS.match(str(s).strip())
    if not m:
        raise Stop('시각을 읽지 못했다: %r' % s)
    tz = m.group(4)
    if tz == 'Z':
        off = timedelta(0)
    else:
        h, mm = int(tz[1:3]), int(tz[3:].lstrip(':') or 0)
        off = timedelta(hours=h, minutes=mm) * (1 if tz[0] == '+' else -1)
    return datetime.fromisoformat('%sT%s.%s' % (m.group(1), m.group(2), (m.group(3) or '0').ljust(6, '0'))).replace(tzinfo=timezone(off))


def pg_text(dt):
    """UTC 의 PostgreSQL ::text 꼴(소수 초 끝의 0 은 뺀다)."""
    u = dt.astimezone(timezone.utc)
    frac = ('.%06d' % u.microsecond).rstrip('0').rstrip('.') if u.microsecond else ''
    return u.strftime('%Y-%m-%d %H:%M:%S') + frac + '+00'


def edition_of(dt):
    return dt.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


# ---- 정의 ----
def load_spec(path=SPEC_FILE):
    with open(path, encoding='utf-8') as f:
        spec = json.load(f)
    if spec.get('format') != FORMAT:
        raise Stop('slices.json 형식이 %s 가 아니다' % FORMAT)
    return spec


def compile_paths(paths):
    """'a.b[].c'·'a.*.v' 목록 → 나무. 잎(True) = 값 통째. '[]' = 배열 원소, '*' = 아무 키."""
    tree = {}
    for p in paths:
        toks = []
        for seg in p.split('.'):
            base = seg.rstrip('[]') if seg.endswith('[]') else seg
            toks.append(base)
            toks.extend(['[]'] * ((len(seg) - len(base)) // 2))
        node = tree
        for i, t in enumerate(toks):
            if i == len(toks) - 1:
                node[t] = True
            else:
                nxt = node.get(t)
                if nxt is True:
                    break
                node = node.setdefault(t, {})
    return tree


def cut(v, tree):
    if tree is True:
        return v
    if isinstance(v, list):
        sub = tree.get('[]')
        return v if sub is None else [cut(x, sub) for x in v]
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            sub = tree[k] if k in tree else tree.get('*')
            if sub is not None:
                out[k] = cut(x, sub)
        return out
    return v


class Slice:
    def __init__(self, d):
        self.name, self.mode, self.d = d['name'], d['mode'], d
        if self.mode == 'revision':
            self.tree = compile_paths(d['payload'])
        else:
            self.columns = d['columns']

    def cut_row(self, r):
        if self.mode == 'revision':
            out = {k: r[k] for k in ROW_FIELDS if k != 'payload'}
            out['payload'] = cut(r['payload'], self.tree)
            return out
        return {k: r.get(k) for k in self.columns}

    def check_row(self, r, where):
        """패키지 행이 정의 칸만 가졌는가(정의에 없는 칸이 오면 멈춘다)."""
        if self.mode == 'revision':
            if sorted(r) != sorted(ROW_FIELDS):
                raise Stop('%s: 행 칸이 정의와 다르다 %s' % (where, sorted(set(r) ^ set(ROW_FIELDS))))
            if r['kind'] != self.name:
                raise Stop('%s: kind 가 %r' % (where, r['kind']))
            if dumps(cut(r['payload'], self.tree)) != dumps(r['payload']):
                raise Stop('%s: 정의에 없는 payload 칸이 있다(entity %s)' % (where, r['entity_id']))
        elif sorted(r) != sorted(self.columns):
            raise Stop('%s: 열이 정의와 다르다 %s' % (where, sorted(set(r) ^ set(self.columns))))


# ---- 담당자 실명·입력 사유 지우기: home-source.js officerTerms·scrubText·scrubKinds 와 같은 규칙 ----
# 판 전체(현재 판 kind·작은 표·감사)에서 actor 값(이름)·reason/change_reason 값(사유)을 모아, 남기는 글 칸에서 ' · ' 조각째 빼고
# 남은 이름은 지운다. 슬라이스에는 actor·reason 칸이 없으므로 우리 쪽 readHome→scrubKinds 는 아무것도 하지 않게 되고, 같은 결과가 미리 만들어진다.
def collect_terms(rows_iter, names=None, reasons=None):
    names = set() if names is None else names
    reasons = set() if reasons is None else reasons

    def walk(o):
        if isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, dict):
            for k, v in o.items():
                if not isinstance(v, str):
                    walk(v)
                elif k == 'actor':
                    names.add(v.strip())
                elif k in ('reason', 'change_reason'):
                    reasons.add(v.strip())
    for r in rows_iter:
        walk(r)
    return names, reasons


def make_terms(names, reasons):
    names = sorted((n for n in names if n), key=lambda x: x.encode('utf-16-be'))
    return {'names': names, 'reasons': sorted(r for r in reasons if r)}


_COLON = re.compile(r'^\s*[:：]\s*')


def scrub_text(s, names, reasons):
    out = ' · '.join(seg for seg in s.split(' · ') if seg.strip() not in names and seg.strip() not in reasons)
    cut_ = False
    for n in names:
        if n in out:
            out = out.replace(n, '')
            cut_ = True
    if cut_:
        out = ' · '.join(x for x in (_COLON.sub('', seg) for seg in out.split(' · ')) if x.strip())
    return out


def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, list):
        for x in o:
            yield from strings(x)
    elif isinstance(o, dict):
        for x in o.values():
            yield from strings(x)


def term_hit(row, terms):
    """남기는 글에 이름·사유가 조각으로라도 있는가(값은 돌려주지 않는다)."""
    ts = [t for t in terms['names'] + terms['reasons'] if t]
    return any(t in s for s in strings(row) for t in ts)


def scrub(o, terms):
    if not terms['names'] and not terms['reasons']:
        return o
    names, reasons = terms['names'], set(terms['reasons'])

    def deep(v):
        if isinstance(v, str):
            return scrub_text(v, names, reasons)
        if isinstance(v, list):
            return [deep(x) for x in v]
        if isinstance(v, dict):
            return {k: deep(x) for k, x in v.items()}
        return v
    return deep(o)


ROW_FIELDS = ['entity_id', 'kind', 'source_id', 'revision_no', 'recorded_at', 'payload_hash', 'batch_id', 'payload']


def digest(pairs):
    return sha('\n'.join(pairs).encode('utf-8'))


def current_of(sl, rows):
    if sl.mode == 'revision':
        pairs = sorted('%s:%d' % (r['entity_id'], r['revision_no']) for r in rows)
    else:
        pairs = sorted(r['id'] for r in rows)
    return {'count': len(rows), 'digest': digest(pairs)}


def sort_rows(sl, rows):
    if sl.mode == 'revision':
        return sorted(rows, key=lambda r: (r['entity_id'], r['revision_no']))
    return sorted(rows, key=lambda r: r.get('id', ''))


def log_changed(sl, r, since):
    """쌓이는 표: since 뒤에 생기거나 바뀐 행(시각 칸 중 하나라도 since 뒤, 끝나지 않은 실행 포함)."""
    for c in sl.d['time_columns']:
        v = r.get(c)
        if v is None and sl.d.get('open_if_null') == c:
            return True
        if v is not None and parse_ts(v) > since:
            return True
    return False


# ---- 내부 판 ----
class Edition:
    def __init__(self, folder):
        self.dir = folder
        with open(os.path.join(folder, 'manifest.json'), encoding='utf-8') as f:
            self.manifest = json.load(f)
        self.snapshot = parse_ts(self.manifest['snapshot_at'])

    def terms(self):
        """판 전체(readHome 이 읽는 모든 파일)의 담당자 이름·사유."""
        names, reasons = set(), set()
        for fn in sorted(self.manifest['files']):
            collect_terms(self.rows(fn[:-9]), names, reasons)
        return make_terms(names, reasons)

    def rows(self, name, missing_ok=False):
        """missing_ok: 기준 판에 아직 없던 kind(예 mapping_decision 은 10-22 22:35 판부터)는 빈 것으로 본다 — 끝의 digest 검사가 지킨다."""
        fn = name + '.jsonl.gz'
        meta = self.manifest['files'].get(fn)
        if meta is None and missing_ok:
            return []
        if meta is None:
            raise Stop('%s 에 %s 가 없다' % (self.dir, fn))
        with open(os.path.join(self.dir, fn), 'rb') as f:
            blob = f.read()
        if meta.get('sha256') and sha(blob) != meta['sha256']:
            raise Stop('%s/%s 의 sha256 이 manifest 와 다르다' % (self.dir, fn))
        return [json.loads(l) for l in gzip.decompress(blob).decode('utf-8').split('\n') if l]


def write_json(path, obj, indent=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=indent) + '\n' if indent else dumps(obj) + '\n'
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return text.encode('utf-8')


def scan_or_stop(text, where):
    k = key_scan(text)
    if any(k.values()):
        raise Stop('키 검사 걸림: %s name_value=%d url_query_long_token=%d (값은 출력하지 않음)' % (where, k['name_value'], k['url_query_long_token']))


# ---- 내보내기(export) → 봉인(seal) ----
# 내보내기 = 자르기·지우기 전의 원천 행(HOME 안에만 둔다 — 실명 포함): export.json(since·until·current·removed·officer_terms 등) + rows/<이름>.jsonl.
# HOME 은 DB 에서 SQL 로(명세 문서 5절), 우리는 내부 판 둘에서(export_from_editions) 같은 것을 만든다. 봉인이 칸을 자르고 실명을 지워 패키지를 쓴다.
def export_from_editions(spec, new_dir, base_dir=None, since=None, alembic=None):
    new = Edition(new_dir)
    base = Edition(base_dir) if base_dir else None
    if base and since is None:
        raise Stop('--base 를 주면 --since 도 준다')
    since_dt = parse_ts(since) if since else None
    if base and since_dt > base.snapshot:
        raise Stop('since(%s) 가 기준 판 스냅샷(%s) 뒤다 — 빈 구간' % (pg_text(since_dt), pg_text(base.snapshot)))
    rows, current, removed = {}, {}, {}
    terms = new.terms()
    for d in spec['slices']:
        sl = Slice(d)
        all_rows = new.rows(sl.name, missing_ok=True)
        if sl.mode == 'revision':
            current[sl.name] = current_of(sl, all_rows)
            full = since_dt is None or d.get('resend') == 'all'
            rows[sl.name] = all_rows if full else [r for r in all_rows if parse_ts(r['recorded_at']) > since_dt]
            if not full:
                guard_terms(sl, all_rows, terms)
            if base:
                gone = sorted({r['entity_id'] for r in base.rows(sl.name, missing_ok=True)} - {r['entity_id'] for r in all_rows})
                if gone:
                    removed[sl.name] = gone
        elif sl.mode == 'log':
            current[sl.name] = current_of(sl, all_rows)
            rows[sl.name] = all_rows if since_dt is None else [r for r in all_rows if log_changed(sl, r, since_dt)]
        else:
            rows[sl.name] = all_rows
    return {'since': pg_text(since_dt) if since_dt else None, 'until': pg_text(new.snapshot), 'source_commit': new.manifest.get('source_commit'),
            'alembic_version': alembic or new.manifest.get('alembic_version'), 'dump_sha256': new.manifest.get('dump_sha256'),
            'current': current, 'removed': removed, 'officer_terms': terms, 'rows': rows}


def guard_terms(sl, rows, terms):
    """변경분만 보내는 kind 의 남기는 글에 이름·사유가 들어 있으면 멈춘다. 지우기 결과는 판 전체의 이름·사유 목록에 따라 달라서
    (사유가 다른 행에서 사라지면 같은 글이 다르게 지워진다) 이런 kind 는 slices.json 에서 resend: all(매번 현재 판 전체)로 둬야 한다."""
    n = sum(1 for r in rows if term_hit(sl.cut_row(r)['payload'], terms))
    if n:
        raise Stop('%s: 남기는 글에 담당자 이름·사유가 든 행 %d — slices.json 에서 이 kind 를 resend: all 로 바꾼다' % (sl.name, n))


def _jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]


def read_export(spec, folder):
    """SQL 내보내기 폴더(sql 하위 명령이 내는 SQL 의 출력) → 봉인 입력.
    meta.json · current.jsonl · removed.jsonl · terms.jsonl · rows/home_revision.jsonl(kind 섞임) · rows/<표>.jsonl"""
    with open(os.path.join(folder, 'meta.json'), encoding='utf-8') as f:
        meta = json.load(f)
    current = {r['kind']: {'count': r['count'], 'digest': r['digest']} for r in _jsonl(os.path.join(folder, 'current.jsonl'))}
    for d in spec['slices']:   # 현재 판이 0행인 kind 는 SQL 결과에 줄이 없다
        if d['mode'] != 'table':
            current.setdefault(d['name'], {'count': 0, 'digest': digest([])})
    removed = {}
    for r in _jsonl(os.path.join(folder, 'removed.jsonl')):
        removed.setdefault(r['kind'], []).append(r['entity_id'])
    names, reasons = set(), set()
    for r in _jsonl(os.path.join(folder, 'terms.jsonl')):
        (names if r['key'] == 'actor' else reasons).add(r['value'].strip())
    rows = {d['name']: [] for d in spec['slices'] if d['mode'] == 'revision'}
    for r in _jsonl(os.path.join(folder, 'rows', 'home_revision.jsonl')):
        if r['kind'] not in rows:
            raise Stop('정의에 없는 kind: %s' % r['kind'])
        rows[r['kind']].append(r)
    for d in spec['slices']:
        if d['mode'] != 'revision':
            rows[d['name']] = _jsonl(os.path.join(folder, 'rows', d['name'] + '.jsonl'))
    return {'since': pg_text(parse_ts(meta['since'])) if meta.get('since') else None, 'until': pg_text(parse_ts(meta['until'])),
            'source_commit': meta.get('source_commit'), 'alembic_version': meta.get('alembic_version'), 'dump_sha256': meta.get('dump_sha256'),
            'current': current, 'removed': {k: sorted(set(v)) for k, v in sorted(removed.items())}, 'officer_terms': make_terms(names, reasons), 'rows': rows}


# 내부 판에 뽑는 kind 전체(home-dump.py KINDS) — 담당자 이름·사유는 이 범위에서 모은다(우리 readHome 이 읽는 범위와 같게)
def sql(spec):
    """HOME DB 에서 내보내기 폴더를 만드는 psql 스크립트(한 READ ONLY REPEATABLE READ 트랜잭션)."""
    q = lambda xs: 'ARRAY[%s]' % ', '.join("'%s'" % x for x in xs)
    rev = [d['name'] for d in spec['slices'] if d['mode'] == 'revision']
    full = [d['name'] for d in spec['slices'] if d.get('resend') == 'all']
    col = lambda c: '%s::text AS %s' % (c, c) if c.endswith('_at') else c
    L = ["-- home-slice.py sql 이 slices.json 에서 만든 것. 사용: psql \"$HOME_DB_URL\" -v since='2026-10-22 00:00:00+09' -v commit=<HOME 소스 커밋> -f export.sql",
         "-- 결과: export/ 폴더(실명 포함 — HOME 밖으로 내지 않는다) → python3 tools/ledger/home-slice.py seal --export export --out <패키지>",
         "\\set ON_ERROR_STOP on", "\\pset format unaligned", "\\pset tuples_only on", "\\pset pager off", "\\! mkdir -p export/rows",
         "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;", "SET LOCAL TimeZone = 'UTC';",
         "\\o export/meta.json",
         "SELECT json_build_object('since', :'since'::timestamptz::text, 'until', now()::text, 'source_commit', :'commit', "
         "'alembic_version', (SELECT version_num FROM alembic_version LIMIT 1), 'dump_sha256', NULL);",
         "\\o export/rows/home_revision.jsonl",
         "SELECT json_build_object('entity_id', entity_id, 'kind', kind, 'source_id', source_id, 'revision_no', revision_no, 'recorded_at', recorded_at::text, "
         "'payload_hash', payload_hash, 'batch_id', batch_id, 'payload', payload) FROM home_revision",
         "  WHERE superseded_at IS NULL AND kind = ANY(%s)" % q(rev),
         "    AND (recorded_at > :'since'::timestamptz OR kind = ANY(%s))" % q(full),
         "  ORDER BY kind, entity_id COLLATE \"C\", revision_no;",
         "\\o export/current.jsonl",
         "SELECT json_build_object('kind', kind, 'count', count(*), 'digest', encode(sha256(convert_to(string_agg(entity_id || ':' || revision_no, E'\\n' ORDER BY entity_id COLLATE \"C\"), 'UTF8')), 'hex'))",
         "  FROM home_revision WHERE superseded_at IS NULL AND kind = ANY(%s) GROUP BY kind ORDER BY kind;" % q(rev),
         "\\o export/removed.jsonl",
         "SELECT json_build_object('kind', r.kind, 'entity_id', r.entity_id) FROM (SELECT DISTINCT kind, entity_id FROM home_revision",
         "  WHERE kind = ANY(%s) AND superseded_at > :'since'::timestamptz) r" % q(rev),
         "  WHERE NOT EXISTS (SELECT 1 FROM home_revision c WHERE c.kind = r.kind AND c.entity_id = r.entity_id AND c.superseded_at IS NULL)",
         "  ORDER BY r.kind, r.entity_id COLLATE \"C\";",
         "\\o export/terms.jsonl",
         "WITH docs AS (SELECT payload::jsonb AS d FROM home_revision WHERE superseded_at IS NULL AND kind = ANY(%s)" % q(HD.KINDS),
         "  UNION ALL SELECT before::jsonb FROM home_audit WHERE action LIKE '%\\_REVIEW' UNION ALL SELECT after::jsonb FROM home_audit WHERE action LIKE '%\\_REVIEW'",
         "  UNION ALL SELECT stats::jsonb FROM home_batch),",
         "  t AS (SELECT DISTINCT k.key, v #>> '{}' AS value FROM docs, (VALUES ('actor'), ('reason'), ('change_reason')) AS k(key),",
         "    LATERAL jsonb_path_query(d, ('lax $.**.' || k.key)::jsonpath) AS v WHERE jsonb_typeof(v) = 'string')",
         "SELECT json_build_object('key', key, 'value', value) FROM t ORDER BY key, value COLLATE \"C\";"]
    for d in spec['slices']:
        if d['mode'] == 'revision':
            continue
        where = ''
        if d['name'] == 'home_audit':
            where = " WHERE action LIKE '%\\_REVIEW' AND recorded_at > :'since'::timestamptz"
        elif d['mode'] == 'log':
            where = " WHERE started_at > :'since'::timestamptz OR finished_at > :'since'::timestamptz OR finished_at IS NULL"
        L += ["\\o export/rows/%s.jsonl" % d['name'],
              "SELECT row_to_json(t) FROM (SELECT %s FROM %s%s) t ORDER BY id COLLATE \"C\";" % (', '.join(col(c) for c in d['columns']), d['source'], where)]
    L += ["\\o", "COMMIT;"]
    return '\n'.join(L) + '\n'


def seal(spec, ex, out, api_dir=None):
    if os.path.exists(out) and os.listdir(out):
        raise Stop('%s 가 비어 있지 않다' % out)
    names = {d['name'] for d in spec['slices']}
    extra = sorted(set(ex['rows']) - names)
    if extra:
        raise Stop('정의에 없는 원천: %s' % ', '.join(extra))
    terms = make_terms(*collect_terms([], set(ex['officer_terms']['names']), set(ex['officer_terms']['reasons'])))
    files = {}
    for d in spec['slices']:
        sl = Slice(d)
        if sl.name not in ex['rows']:
            raise Stop('내보내기에 %s 가 없다' % sl.name)
        if ex['since'] is not None and sl.mode == 'revision' and d.get('resend') != 'all':
            guard_terms(sl, ex['rows'][sl.name], terms)
        body = [scrub(sl.cut_row(r), terms) for r in sort_rows(sl, ex['rows'][sl.name])]
        rel = 'slices/%s.json' % sl.name
        blob = write_json(os.path.join(out, rel), body)
        text = blob.decode('utf-8')
        scan_or_stop(text, rel)
        files[rel] = {'rows': len(body), 'sha256': sha(blob)}
    if api_dir:
        fetched = {}
        if os.path.exists(os.path.join(api_dir, 'fetched.json')):   # {'api/<이름>': 받은 시각} — 있으면 manifest 에 적는다
            with open(os.path.join(api_dir, 'fetched.json'), encoding='utf-8') as f:
                fetched = json.load(f)
        for group in ('api', 'golden', 'web'):
            if not os.path.isdir(os.path.join(api_dir, group)):
                continue   # 없는 묶음은 넣지 않는다(정답 대조 입력 golden·web 은 받는 날만)
            for e in spec[group]:
                if '{' in e['save']:
                    continue   # 프로그램마다 되풀이하는 요청은 있는 것만(아래)
                src = os.path.join(api_dir, group, e['save'])
                if not os.path.exists(src):
                    raise Stop('응답이 없다: %s' % src)
                copy_extra(src, out, '%s/%s' % (group, e['save']), files)
            for e in spec[group]:
                if '{' in e['save']:
                    pat = re.compile('^' + re.escape(e['save']).replace(r'\{program_id\}', r'PRG_[0-9a-f]+').replace(r'\{until_date\}', r'\d{4}-\d{2}-\d{2}') + '$')
                    for fn in sorted(os.listdir(os.path.join(api_dir, group))):
                        if pat.match(fn):
                            copy_extra(os.path.join(api_dir, group, fn), out, '%s/%s' % (group, fn), files)
        for rel in files:
            if rel in fetched:
                files[rel]['fetched_at'] = fetched[rel]
    manifest = {'format': FORMAT, 'since': ex['since'], 'until': ex['until'], 'source_commit': ex.get('source_commit'),
                'alembic_version': ex.get('alembic_version'), 'dump_sha256': ex.get('dump_sha256'),
                'files': files, 'current': ex['current'], 'removed': ex.get('removed', {})}
    write_json(os.path.join(out, 'manifest.json'), manifest, indent=2)
    return manifest


def copy_extra(src, out, rel, files):
    with open(src, 'rb') as f:
        blob = f.read()
    scan_or_stop(blob.decode('utf-8'), rel)
    os.makedirs(os.path.dirname(os.path.join(out, rel)), exist_ok=True)
    with open(os.path.join(out, rel), 'wb') as f:
        f.write(blob)
    files[rel] = {'rows': None, 'sha256': sha(blob)}


# ---- apply ----
def read_package(spec, pkg):
    with open(os.path.join(pkg, 'manifest.json'), 'rb') as f:
        mblob = f.read()
    pm = json.loads(mblob)
    if pm.get('format') != FORMAT:
        raise Stop('패키지 형식이 %s 가 아니다: %r' % (FORMAT, pm.get('format')))
    names = {d['name'] for d in spec['slices']}
    for rel in pm['files']:
        if rel.startswith('slices/') and rel[7:-5] not in names:
            raise Stop('정의에 없는 슬라이스: %s' % rel)
    for k in list(pm.get('current', {})) + list(pm.get('removed', {})):
        if k not in names:
            raise Stop('정의에 없는 kind: %s' % k)
    data = {}
    for rel, meta in sorted(pm['files'].items()):
        with open(os.path.join(pkg, rel), 'rb') as f:
            blob = f.read()
        if sha(blob) != meta['sha256']:
            raise Stop('%s 의 sha256 이 manifest 와 다르다' % rel)
        text = blob.decode('utf-8')
        scan_or_stop(text, rel)
        if rel.startswith('slices/'):
            rows = json.loads(text)
            if len(rows) != meta['rows']:
                raise Stop('%s 행 수가 manifest 와 다르다(%d != %d)' % (rel, len(rows), meta['rows']))
            data[rel[7:-5]] = rows
    for d in spec['slices']:
        if d['name'] not in data:
            raise Stop('패키지에 슬라이스가 없다: %s' % d['name'])
        if d['mode'] != 'table' and d['name'] not in pm.get('current', {}):
            raise Stop('manifest.current 에 %s 가 없다' % d['name'])
    return pm, mblob, data


def base_row(sl, r, terms):
    r = sl.cut_row(r)
    return scrub(r, terms) if terms else r


def apply(spec, pkg, out, base_dir=None):
    pm, mblob, data = read_package(spec, pkg)
    since = parse_ts(pm['since']) if pm.get('since') else None
    until = parse_ts(pm['until'])
    base = Edition(base_dir) if base_dir else None
    if since is not None and base is None:
        raise Stop('변경분 패키지(since %s)에는 --base 가 필요하다' % pm['since'])
    if base and since is not None:
        if since > base.snapshot:
            raise Stop('since(%s) 가 기준 판 스냅샷(%s) 뒤다 — 빈 구간' % (pm['since'], pg_text(base.snapshot)))
        if until < base.snapshot:
            raise Stop('패키지 until(%s) 이 기준 판(%s) 보다 앞이다' % (pm['until'], pg_text(base.snapshot)))
    use_base = base is not None and since is not None
    base_terms = base.terms() if use_base and 'slice_format' not in base.manifest else None   # 내부 판(home-dump.py)은 실명이 있다
    if os.path.exists(out) and os.listdir(out):
        raise Stop('%s 가 비어 있지 않다' % out)
    result = {}
    for d in spec['slices']:
        sl = Slice(d)
        for r in data[sl.name]:
            sl.check_row(r, 'slices/%s.json' % sl.name)
        if sl.mode == 'table' or not use_base:
            rows = data[sl.name]
        elif sl.mode == 'revision' and d.get('resend') == 'all':
            rows = data[sl.name]
        elif sl.mode == 'revision':
            cur = {r['entity_id']: base_row(sl, r, base_terms) for r in base.rows(sl.name, missing_ok=True)}
            for eid in pm.get('removed', {}).get(sl.name, []):
                cur.pop(eid, None)
            for r in data[sl.name]:
                old = cur.get(r['entity_id'])
                if old is None or r['revision_no'] >= old['revision_no']:
                    cur[r['entity_id']] = r
            rows = list(cur.values())
        else:
            cur = {r['id']: base_row(sl, r, base_terms) for r in base.rows(sl.name, missing_ok=True)}
            for r in data[sl.name]:
                cur[r['id']] = r
            rows = list(cur.values())
        rows = sort_rows(sl, rows)
        if sl.mode != 'table':
            got, want = current_of(sl, rows), pm['current'][sl.name]
            if got != want:
                raise Stop('%s: 반영 결과가 manifest.current 와 다르다(count %d/%d) — 패키지·기준 판을 확인' % (sl.name, got['count'], want['count']))
        result[sl.name] = rows
    os.makedirs(out, exist_ok=True)
    files, total = {}, {'name_value': 0, 'url_query_long_token': 0}
    for d in spec['slices']:
        rows = result[d['name']]
        for r in rows:
            for k, n in key_scan(dumps(r)).items():
                total[k] += n
        blob = encode_rows(rows)
        fn = d['name'] + '.jsonl.gz'
        with open(os.path.join(out, fn), 'wb') as f:
            f.write(blob)
        files[fn] = {'rows': len(rows), 'sha256': sha(blob), 'bytes': len(blob)}
    manifest = {
        'dump_sha256': pm.get('dump_sha256') or sha(mblob), 'snapshot_at': until.astimezone(timezone.utc).isoformat(),
        'source_commit': pm.get('source_commit'), 'alembic_version': pm.get('alembic_version'),
        'kinds': [d['name'] for d in spec['slices'] if d['mode'] == 'revision'], 'files': files,
        'key_check': {'name_value': total['name_value'], 'url_query_long_token': total['url_query_long_token'], 'ok': not any(total.values())},
        'slice_format': FORMAT}
    if not manifest['key_check']['ok']:
        raise Stop('키 검사 실패(값은 출력하지 않음)')
    with open(os.path.join(out, 'manifest.json'), 'w', encoding='utf-8') as f:
        f.write(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    # 어디서 왔는지(readHome 은 읽지 않는다 — manifest.files 밖)
    with open(os.path.join(out, 'slice-origin.json'), 'w', encoding='utf-8') as f:
        f.write(json.dumps({'package_manifest_sha256': sha(mblob), 'since': pm.get('since'), 'until': pm['until'],
                            'base': os.path.basename(os.path.normpath(base_dir)) if use_base else None}, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    return manifest


# ---- HOME API 응답 → raw/home-api/<기준일>/ 스냅샷(home-projects.js·home-sources.js 의 POC_FILES 규칙: 줄이기·담당자 칸 지우기·gzip) ----
API_JS = r"""
const [pkg, out, untilDate, specFile, root] = process.argv.slice(1);
const fs = require('fs'), path = require('path'), zlib = require('zlib'), crypto = require('crypto');
const HP = require(path.join(root, 'tools/ledger/home-projects.js')), HS = require(path.join(root, 'tools/ledger/home-sources.js'));
const spec = JSON.parse(fs.readFileSync(specFile, 'utf8')), pm = JSON.parse(fs.readFileSync(path.join(pkg, 'manifest.json'), 'utf8'));
const BASE = 'https://www.minslab.kr/poc/home/api/';
fs.mkdirSync(out, { recursive: true });
const entries = {};
for (const e of spec.api) {
  const rel = 'api/' + e.save, file = e.save + '.gz';
  if (!pm.files[rel]) throw new Error('패키지에 ' + rel + ' 가 없다');
  const raw = JSON.parse(fs.readFileSync(path.join(pkg, rel), 'utf8'));
  let body, rows;
  if (HP.POC_FILES[file]) { const [, keep, n] = HP.POC_FILES[file]; body = HP.scrub(keep(raw)); rows = n(body); }
  else if (HS.POC_FILES[file]) { const [, n] = HS.POC_FILES[file]; body = HS.scrub(raw); rows = n(body); }
  else { body = HS.scrub(raw); rows = body.data_gaps?.rows?.length ?? null; }   // sources-validation(옛 /validation — 연도 칸 행 수)
  const text = JSON.stringify(body);
  if (text.includes('사용자 입력 ·')) throw new Error(file + ': 담당자 입력 글이 남았다');
  const buf = zlib.gzipSync(text, { level: 9 });
  fs.writeFileSync(path.join(out, file), buf);
  entries[file] = { url: BASE + e.path + (e.query ? '?' + e.query.split('{until_date}').join(untilDate) : ''), fetched_at: pm.files[rel].fetched_at ?? null,
    sha256: crypto.createHash('sha256').update(buf).digest('hex'), rows, bytes: buf.length };
}
HS.writeManifest(out, Object.fromEntries(Object.entries(entries).sort(([a], [b]) => (a < b ? -1 : 1))));
console.log('API 스냅샷 ' + Object.keys(entries).length + '개: ' + out);
"""


def apply_api(spec_file, pkg, out_dir):
    import subprocess
    with open(os.path.join(pkg, 'manifest.json'), encoding='utf-8') as f:
        until = parse_ts(json.load(f)['until'])
    until_date = (until.astimezone(timezone(timedelta(hours=9)))).strftime('%Y-%m-%d')
    r = subprocess.run(['node', '-e', API_JS, pkg, out_dir, until_date, spec_file, ROOT], capture_output=True, text=True)
    if r.returncode != 0:
        raise Stop('API 스냅샷 만들기 실패: %s' % ' / '.join(l for l in r.stderr.splitlines() if 'Error' in l)[:300])
    print(r.stdout.strip())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    m = sub.add_parser('make')
    m.add_argument('--new', required=True)
    m.add_argument('--base')
    m.add_argument('--since')
    m.add_argument('--out', required=True)
    m.add_argument('--alembic-version')
    m.add_argument('--api', help='HOME API·정답 입력·프런트 JS 폴더(api/·golden/·web/ 아래 slices.json 의 save 이름)')
    se = sub.add_parser('seal')
    se.add_argument('--export', required=True, help='내보내기 폴더(export.json + rows/<이름>.jsonl)')
    se.add_argument('--out', required=True)
    se.add_argument('--api')
    a = sub.add_parser('apply')
    a.add_argument('--base')
    a.add_argument('--in', dest='pkg', required=True)
    a.add_argument('--out', required=True)
    a.add_argument('--api-out', help='패키지 api/ 를 raw/home-api/<until 한국 날짜>/ 스냅샷으로 옮길 폴더')
    sq = sub.add_parser('sql', help='HOME DB 내보내기 psql 스크립트를 찍는다')
    for p in (m, a, se, sq):
        p.add_argument('--spec', default=SPEC_FILE)
    o = ap.parse_args(argv)
    try:
        spec = load_spec(o.spec)
        if o.cmd == 'sql':
            sys.stdout.write(sql(spec))
            return 0
        if o.cmd in ('make', 'seal'):
            ex = export_from_editions(spec, o.new, base_dir=o.base, since=o.since, alembic=o.alembic_version) if o.cmd == 'make' else read_export(spec, o.export)
            man = seal(spec, ex, o.out, api_dir=o.api)
            print('패키지: %s (파일 %d, 행 %d, since %s, until %s)' % (o.out, len(man['files']), sum(v['rows'] or 0 for v in man['files'].values()), man['since'], man['until']))
        else:
            man = apply(spec, o.pkg, o.out, base_dir=o.base)
            if o.api_out:
                apply_api(o.spec, o.pkg, o.api_out)
            print('새 판: %s (스냅샷 %s, 판 이름 권장 %s, 파일 %d)' % (o.out, man['snapshot_at'], edition_of(parse_ts(man['snapshot_at'])), len(man['files'])))
    except Stop as e:
        print('멈춤: %s' % e, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
