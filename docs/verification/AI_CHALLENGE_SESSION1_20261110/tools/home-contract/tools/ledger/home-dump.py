#!/usr/bin/env python3
"""HOME PoC PostgreSQL 덤프(pg_dump custom)에서 원장 변환에 필요한 자료만 뽑는다.

DB 서버·Docker 없이 `pg_restore -a -t <표> -f -` 의 COPY 텍스트만 파싱한다(덤프 안의 것은 실행하지 않는다).
같은 덤프는 바이트까지 같은 결과를 낸다(정렬·직렬화·gzip 헤더 고정).

사용: python3 tools/ledger/home-dump.py --dump <폴더> [--out <폴더>]
환경변수 PG_RESTORE 로 pg_restore 경로를 바꾼다.
"""
from urllib.parse import unquote
import argparse, gzip, hashlib, io, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_PG_RESTORE = '/opt/homebrew/opt/libpq/bin/pg_restore'

KINDS = ['policy', 'policy_delivery_plan', 'policy_event', 'project', 'project_report', 'stage_evidence',
         'sequence_review', 'lh_completion_plan', 'lh_notice', 'notice', 'gh_notice', 'statistic', 'area_stat',
         'unsold', 'district', 'block_location', 'project_location', 'plan_notice', 'collection_link',
         'municipality', 'policy_municipality',
         # 9·7 정책 단계별 목표·확인(tools/ledger/policy-progress.js, HOME policy_delivery.build_delivery)이 더 읽는 것
         'evidence_bridge', 'lh_movein_plan', 'document_evidence', 'delivery_setting', 'execution_schedule',
         # 담당자 입력 오버레이(계획물량·단계 측정값 — 2026-10-14 판부터). 원본 gz 는 커밋하지 않는다(실명·사유 포함)
         'project_profile',
         # 사업후보 연결 결정(2026-10-22 22:35 판부터 — home_mapping 행은 그대로 두고 해제 등 결정만 따로 쌓는다. HOME /mappings 의 상태가 이것을 따른다)
         'mapping_decision']
SMALL_TABLES = ['home_project', 'home_identity_alias', 'home_project_evidence', 'home_mapping',
                'home_program_mapping', 'home_plan', 'home_plan_event', 'home_plan_project_link', 'home_coverage']
BATCH_COLS = ['id', 'source_id', 'status', 'started_at', 'finished_at']
STATS_MAX_CHARS = 2000
JSON_COLS = {'payload', 'stats', 'before', 'after', 'manifest'}

# ---- COPY 텍스트 ----
_ESC = {b'b': b'\b', b'f': b'\f', b'n': b'\n', b'r': b'\r', b't': b'\t', b'v': b'\v'}
_ESC_RE = re.compile(rb'\\(x[0-9a-fA-F]{1,2}|[0-7]{1,3}|.)', re.S)


def _rep(m):
    g = m.group(1)
    if g[:1] == b'x' and len(g) > 1:
        return bytes([int(g[1:], 16)])
    if g[:1] in b'01234567':
        return bytes([int(g, 8) & 0xFF])
    return _ESC.get(g, g)


def unescape_field(b):
    """COPY 필드 하나(바이트) -> str, \\N 은 None."""
    if b == b'\\N':
        return None
    if b'\\' in b:
        b = _ESC_RE.sub(_rep, b)
    return b.decode('utf-8')


_COPY_RE = re.compile(rb'^COPY ([\w."]+) \((.*)\) FROM stdin;$')


def parse_copy(lines):
    """바이트 줄 이터레이터 -> (표 이름, 열 이름 목록, 행(dict) 이터레이터)를 표마다 낸다."""
    table = cols = None
    for raw in lines:
        line = raw.rstrip(b'\n')
        if table is None:
            m = _COPY_RE.match(line)
            if m:
                table = m.group(1).decode().replace('"', '')
                cols = [c.strip().strip('"') for c in m.group(2).decode().split(',')]
            continue
        if line == b'\\.':
            table = None
            continue
        fields = line.split(b'\t')
        if len(fields) != len(cols):
            raise ValueError('열 수 불일치: %s (%d != %d)' % (table, len(fields), len(cols)))
        yield table, cols, [unescape_field(f) for f in fields]


def to_record(cols, vals):
    rec = {}
    for c, v in zip(cols, vals):
        rec[c] = json.loads(v) if (c in JSON_COLS and v is not None) else v
    return rec


# ---- 결정적 직렬화 ----
def dumps(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def gz_bytes(data):
    buf = io.BytesIO()
    with gzip.GzipFile(filename='', mode='wb', fileobj=buf, compresslevel=9, mtime=0) as g:
        g.write(data)
    return buf.getvalue()


def encode_rows(rows):
    return gz_bytes(''.join(dumps(r) + '\n' for r in rows).encode('utf-8'))


# ---- 키 검사(값은 출력하지 않고 건수만) ----
KEY_NAMES = r'(?:service_?key|api_?key|auth_?key|crtfc_?key|confm_?key|cert_?key|access_?token|secret|passwd|password)'
KV_RE = re.compile(r'(?i)' + KEY_NAMES + r'(?:=|%3d)[^&\s"\\]+')
URLQ_RE = re.compile(r'(?i)https?://[^\s"\\]*[?&][^\s"\\]*?=([A-Za-z0-9%+/_\-]{32,})')
HANGUL_RE = re.compile(r'[\uac00-\ud7a3]')
# 퍼센트 인코딩을 풀면 '/YYYYMMDD/<이름>/…' 인 공개 파일 경로(토지이음 FileDownload.do 의 file=). 날짜 폴더로 시작해야만 빼서
# '/'·'+'·'=' 가 섞인 base64 키(%2F…%3D)는 그대로 잡힌다
FILE_PATH_RE = re.compile(r'^/(?:19|20)\d{6}(?:/[A-Za-z0-9_.\-]{1,64})+$')


def _is_token(v):
    # 퍼센트 인코딩된 한글(사업지구명 등)은 키가 아니다. UTF-8 로 못 읽는 퍼센트 글(EUC-KR 지구명 — 토지이음 고시 주소의 zonenm)도 키가 아니다
    if '%' not in v:
        return True
    d = unquote(v)
    return not (HANGUL_RE.search(d) or '\ufffd' in d or FILE_PATH_RE.match(d))


def key_scan(text):
    return {'name_value': len(KV_RE.findall(text)),
            'url_query_long_token': sum(1 for m in URLQ_RE.finditer(text) if _is_token(m.group(1)))}


# ---- 덤프 읽기 ----
def pg_restore_lines(pg, dump, table):
    p = subprocess.Popen([pg, '-a', '-n', 'public', '-t', table, '-f', '-', dump],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    yield from p.stdout
    err = p.stderr.read().decode('utf-8', 'replace')
    if p.wait() != 0:
        raise RuntimeError('pg_restore 실패(%s): %s' % (table, err[:300]))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_sums(folder):
    sums = {}
    with open(os.path.join(folder, 'SHA256SUMS.txt'), encoding='utf-8') as f:
        for ln in f:
            parts = ln.split()
            if len(parts) == 2:
                sums[parts[1].lstrip('*')] = parts[0]
    got = sha256_file(os.path.join(folder, 'home.dump'))
    if sums.get('home.dump') != got:
        sys.exit('덤프 sha256 이 SHA256SUMS.txt 와 다르다 — 중단')
    return got


def extract(pg, dump):
    """-> {파일 이름(확장자 제외): 행 목록}"""
    out = {}
    kinds = set(KINDS)
    rows = {k: [] for k in KINDS}
    for _t, cols, vals in parse_copy(pg_restore_lines(pg, dump, 'home_revision')):
        r = dict(zip(cols, vals))
        if r['superseded_at'] is not None or r['kind'] not in kinds:
            continue
        rows[r['kind']].append({
            'entity_id': r['entity_id'], 'kind': r['kind'], 'source_id': r['source_id'],
            'revision_no': int(r['revision_no']), 'recorded_at': r['recorded_at'],
            'payload_hash': r['payload_hash'], 'batch_id': r['batch_id'], 'payload': json.loads(r['payload'])})
    for k in KINDS:
        out[k] = sorted(rows[k], key=lambda x: (x['entity_id'], x['revision_no']))
    for t in SMALL_TABLES:
        recs = [to_record(c, v) for _t, c, v in parse_copy(pg_restore_lines(pg, dump, t))]
        out[t] = sorted(recs, key=lambda x: x.get('id', ''))
    batches = []
    for _t, c, v in parse_copy(pg_restore_lines(pg, dump, 'home_batch')):
        r = to_record(c, v)
        b = {k: r[k] for k in BATCH_COLS}
        if len(dumps(r['stats'])) <= STATS_MAX_CHARS:
            b['stats'] = r['stats']
        batches.append(b)
    out['home_batch'] = sorted(batches, key=lambda x: x['id'])
    audits = []
    for _t, c, v in parse_copy(pg_restore_lines(pg, dump, 'home_audit')):
        r = to_record(c, v)
        if r['action'].endswith('_REVIEW'):
            audits.append(r)
    out['home_audit'] = sorted(audits, key=lambda x: x['id'])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dump', required=True)
    ap.add_argument('--out')
    a = ap.parse_args()
    pg = os.environ.get('PG_RESTORE', DEFAULT_PG_RESTORE)
    dump_sha = verify_sums(a.dump)
    with open(os.path.join(a.dump, 'manifest.json'), encoding='utf-8') as f:
        dm = json.load(f)
    snap = dm['snapshot_at']
    stamp = re.sub(r'\D', '', snap)[:14]
    stamp = stamp[:8] + 'T' + stamp[8:] + 'Z'
    out = a.out or os.path.join(ROOT, 'schemas', 'ledger-2026-10', 'raw', 'home', stamp)
    os.makedirs(out, exist_ok=True)

    data = extract(pg, os.path.join(a.dump, 'home.dump'))
    files, total = {}, {'name_value': 0, 'url_query_long_token': 0}
    for name in KINDS + SMALL_TABLES + ['home_batch', 'home_audit']:
        rows = data[name]
        for r in rows:  # 파일에 쓸 직렬화 그대로 검사
            for k, n in key_scan(dumps(r)).items():
                total[k] += n
        blob = encode_rows(rows)
        fn = name + '.jsonl.gz'
        with open(os.path.join(out, fn), 'wb') as f:
            f.write(blob)
        files[fn] = {'rows': len(rows), 'sha256': hashlib.sha256(blob).hexdigest(), 'bytes': len(blob)}
    manifest = {
        'dump_sha256': dump_sha, 'snapshot_at': snap, 'source_commit': dm.get('source_commit'),
        'kinds': KINDS, 'files': files,
        'key_check': {'name_value': total['name_value'], 'url_query_long_token': total['url_query_long_token'],
                      'ok': not any(total.values())}}
    with open(os.path.join(out, 'manifest.json'), 'w', encoding='utf-8') as f:
        f.write(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    print('출력: %s (%d 파일, 행 %d)' % (out, len(files), sum(v['rows'] for v in files.values())))
    if not manifest['key_check']['ok']:
        sys.exit('키 검사 실패: name_value=%d url_query_long_token=%d (값은 출력하지 않음)'
                 % (total['name_value'], total['url_query_long_token']))


if __name__ == '__main__':
    main()
