"""On-demand, bounded exports implementing the supplied home-slices/1 contract.

Only the sealed package is persisted. The source DB is read in a repeatable-read
transaction; concurrent DB writes invalidate the API comparison bundle. No source
collection, model invocation, business mutation or remote upload is performed.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import copy
import fcntl
from functools import lru_cache
import hashlib
import hmac
import importlib.util
import json
import logging
import os
import re
import tempfile
import threading
import time
import uuid
import zipfile
from urllib.parse import parse_qsl, urlsplit

import httpx
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path(__file__).with_name('slice_contract')
_loader = importlib.util.spec_from_file_location('home_slice_contract', CONTRACT / 'tools/ledger/home-slice.py')
codec = importlib.util.module_from_spec(_loader)
_loader.loader.exec_module(codec)
SPEC = codec.load_spec()
TARGET = 'the-housing'
KST = timezone(timedelta(hours=9))
TTL = 86400
LOG = logging.getLogger(__name__)

# Public document identifiers observed in stored official/public source links.
# This is deliberately path+parameter scoped; an arbitrary ?token= is rejected.
PUBLIC_DOCUMENT_IDS = {
    ('youthpolicy.kr', '/post_file_download.cm', 'c'),
    ('council.bucheon.go.kr', '/assembly/ems/qna.do', 'key'),
    ('gonggam.korea.kr', '/newsContentView.es', 'news_id'),
    ('www.work.go.kr', '/framework/filedownload/keisDownload.do', 'realFileNm'),
    ('korean.visitkorea.or.kr', '/detail/ms_detail.do', 'cotid'),
    ('smc.sba.kr', '/Pages/BusinessApply/PostingDetail.aspx', 'mid'),
    ('ms.smc.seoul.kr', '/record/appendixDownload.do', 'key'),
    ('mas.smc.seoul.kr', '/record/appendixDownload.do', 'key'),
    ('cast.ydpc.go.kr', '/record/appendixDownload.do', 'key'),
    ('opengov.seoul.go.kr', '/og/com/download.php', 'uri'),
    ('soco.seoul.go.kr', '/coHouse/cmmn/file/fileDown.do', 'atchFileId'),
}


class ExportError(ValueError):
    pass


def write_spooled_json(path, body):
    # Avoid a second full-size serialized string/bytes allocation for large APIs.
    with path.open('w', encoding='utf-8') as stream:
        # API encoders allow a null dictionary key (e.g. unknown sample region).
        # Preserve that HTTP representation; sorting None beside strings fails.
        json.dump(body, stream, ensure_ascii=False, separators=(',', ':'))
        stream.write('\n')


def encode_public_document_links(path):
    """Keep exact decoded URLs while supporting the recipient's text-only scan.

    Their regex mistakes long public document IDs for API credentials. Validate
    BEFORE encoding, then use JSON's standard escaped slash for these responses.
    json.loads (and the receiver) restores every URL byte; no field is dropped.
    """
    value = path.read_text()
    if codec.HD.KV_RE.search(value):
        raise ExportError('전달 대조 자료에서 인증키 형태가 발견되어 중단했습니다. 값은 표시하지 않습니다.')
    public_matches = False
    for match in codec.HD.URLQ_RE.finditer(value):
        if not codec.HD._is_token(match.group(1)): continue
        url = urlsplit(match.group(0))
        parameters = parse_qsl(url.query)
        if not parameters or (url.hostname, url.path, parameters[-1][0]) not in PUBLIC_DOCUMENT_IDS:
            raise ExportError('전달 대조 자료에 확인되지 않은 긴 URL 토큰이 있어 중단했습니다. 값은 표시하지 않습니다.')
        public_matches = True
    if public_matches:
        path.write_text(value.replace('/', '\\/'))


def options():
    return {'targets': [{'id': TARGET, 'name': 'the-housing 상황판', 'format': codec.FORMAT,
                         'slices': len(SPEC['slices']), 'api': len(SPEC['api'])}],
            'default_since': '2026-10-22T00:00', 'timezone': 'Asia/Seoul'}


def parse_since(mode, value):
    if mode not in ('delta', 'full'):
        raise ExportError('추출 방식은 변경분 또는 전체를 선택하세요.')
    if mode == 'full':
        return None
    try:
        stamp = datetime.fromisoformat(value)
        stamp = stamp.replace(tzinfo=KST) if stamp.tzinfo is None else stamp
    except (ValueError, TypeError):
        raise ExportError('변경 기준일을 올바르게 입력하세요.') from None
    if stamp > datetime.now(timezone.utc) or stamp.year < 2000:
        raise ExportError('변경 기준일은 2000년 이후부터 현재까지 선택할 수 있습니다.')
    return stamp.astimezone(timezone.utc)


def public_json(value, terms, scrub_text=None):
    """Keep calculation fields; strip personal review metadata throughout API JSON."""
    reasons = set(terms['reasons'])
    scrub_text = scrub_text or (lambda s: codec.scrub_text(s, terms['names'], reasons))
    def walk(item):
        if isinstance(item, dict):
            if any(isinstance(v, str) and v.strip() and re.fullmatch(codec.HD.KEY_NAMES, str(k), re.IGNORECASE)
                   for k, v in item.items()):
                raise ExportError('대조 자료의 인증정보 필드가 비어 있지 않아 전달을 중단했습니다. 값은 표시하지 않습니다.')
            return {k: walk(v) for k, v in item.items()
                    if k not in {'actor', 'reason', 'change_reason', 'last_changes'}}
        if isinstance(item, list): return [walk(v) for v in item]
        if isinstance(item, str): return scrub_text(item)
        return item
    return walk(value)


def snapshot(service, since):
    """All rows/current digests/terms share one PostgreSQL snapshot.

    Unlike the supplied SQL/read_export prototype, log current digests describe
    ALL retained rows, not only this delta (or zero). Empty kinds remain explicit.
    """
    if service.engine.dialect.name != 'postgresql':
        raise ExportError('연계 데이터셋 생성에는 운영 PostgreSQL 연결이 필요합니다.')
    names, reasons = set(), set()
    rows, current, removed = {}, {}, {}
    with service.engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn:
        with conn.begin():
            conn.execute(text('SET TRANSACTION READ ONLY'))
            conn.execute(text("SET LOCAL TimeZone = 'UTC'"))
            conn.execute(text("SET LOCAL statement_timeout = '60s'"))
            until, token = conn.execute(text('SELECT now(), txid_current_snapshot()::text')).one()
            alembic = conn.execute(text('SELECT version_num FROM alembic_version LIMIT 1')).scalar()
            # The supplied privacy scope covers current payloads, review history and batch stats.
            # Keep JSON (not JSONB): archived OCR can legally contain escaped
            # U+0000, which PostgreSQL's JSONB conversion rejects. Prefilter keys
            # in SQL, then walk only matching documents with the supplied codec.
            terms_sql = """WITH docs AS (
                SELECT payload AS d FROM home_revision WHERE superseded_at IS NULL AND kind = ANY(:kinds)
                UNION ALL SELECT before FROM home_audit WHERE right(action,7) = '_REVIEW'
                UNION ALL SELECT after FROM home_audit WHERE right(action,7) = '_REVIEW'
                UNION ALL SELECT stats FROM home_batch)
                SELECT d FROM docs WHERE d::text ~ '"(actor|reason|change_reason)"[[:space:]]*:'"""
            for (value,) in conn.execution_options(yield_per=50).execute(text(terms_sql), {'kinds': codec.HD.KINDS}):
                codec.collect_terms([value], names, reasons)
            revision_kinds = [d['name'] for d in SPEC['slices'] if d['mode'] == 'revision']
            revisions = {kind: [] for kind in revision_kinds}
            cutters = {d['name']: codec.Slice(d) for d in SPEC['slices'] if d['mode'] == 'revision'}
            source = conn.execute(text('SELECT entity_id, kind, source_id, revision_no, recorded_at::text, payload_hash, batch_id, payload '
                'FROM home_revision WHERE superseded_at IS NULL AND kind=ANY(:kinds)'), {'kinds': revision_kinds})
            for r in source.mappings():
                # Drop large OCR/native payloads immediately; do not buffer the
                # complete source corpus just to retain a handful of fields.
                revisions[r['kind']].append(cutters[r['kind']].cut_row(dict(r)))
            for d in SPEC['slices']:
                name = d['name']
                sl = codec.Slice(d)
                if d['mode'] == 'revision':
                    all_rows = revisions[name]
                    current[name] = codec.current_of(sl, all_rows)
                else:
                    # All SQL identifiers come from the checked-in contract, never request input.
                    columns = ','.join(c + '::text AS ' + c if c.endswith('_at') else c for c in d['columns'])
                    where = " WHERE right(action,7) = '_REVIEW'" if name == 'home_audit' else ''
                    all_rows = [dict(r) for r in conn.execute(text(f'SELECT {columns} FROM {d["source"]}{where} ORDER BY id COLLATE "C"')).mappings()]
                    if d['mode'] == 'log':
                        current[name] = codec.current_of(sl, all_rows)
                rows[name] = all_rows
            # Determine privacy fallback before scanning historical deletions.
            privacy_fallback = False
            if since:
                terms = codec.make_terms(names, reasons)
                for d in SPEC['slices']:
                    if d['mode'] == 'revision' and d.get('resend') != 'all':
                        try: codec.guard_terms(codec.Slice(d), rows[d['name']], terms)
                        except codec.Stop:
                            privacy_fallback = True
                            break
                if not privacy_fallback:
                    incremental = [d['name'] for d in SPEC['slices'] if d['mode']=='revision' and d.get('resend') != 'all']
                    existing = {kind: {r['entity_id'] for r in revisions[kind]} for kind in incremental}
                    historical = conn.execute(text('SELECT DISTINCT kind,entity_id FROM home_revision '
                        'WHERE kind=ANY(:kinds) AND superseded_at>:since'), {'kinds': incremental, 'since': since})
                    for kind, eid in historical:
                        if eid not in existing[kind]: removed.setdefault(kind, []).append(eid)
                    removed = {kind: sorted(ids) for kind, ids in removed.items()}
    return {'since': codec.pg_text(since) if since else None, 'until': codec.pg_text(until),
            'source_commit': source_commit(), 'alembic_version': alembic, 'dump_sha256': None,
            'rows': rows, 'current': current, 'removed': removed,
            'officer_terms': codec.make_terms(names, reasons), '_privacy_fallback': privacy_fallback}, token


def source_commit():
    p = CONTRACT / 'source-commit.txt'
    return p.read_text().strip() if p.is_file() else None


def select_delta(ex, since):
    """A new privacy term can affect old rows. Fall back to a valid full package."""
    fallback = ex.get('_privacy_fallback', False)
    if since and not fallback:
        for d in SPEC['slices']:
            if d['mode'] == 'revision' and d.get('resend') != 'all':
                try:
                    codec.guard_terms(codec.Slice(d), ex['rows'][d['name']], ex['officer_terms'])
                except codec.Stop:
                    fallback = True
                    break
    if fallback:
        ex['since'] = None
        ex['removed'] = {}
        return True
    for d in SPEC['slices']:
        if since and d['mode'] == 'revision' and d.get('resend') != 'all':
            ex['rows'][d['name']] = [r for r in ex['rows'][d['name']] if codec.parse_ts(r['recorded_at']) > since]
        elif since and d['mode'] == 'log':
            ex['rows'][d['name']] = [r for r in ex['rows'][d['name']] if codec.log_changed(codec.Slice(d), r, since)]
    return False


def fetch_bundle(fetch, ex, golden, progress, spool=None):
    """Deduplicate requests and expand every active policy program from mappings."""
    day = codec.parse_ts(ex['until']).astimezone(KST).date().isoformat()
    cache, files, fetched = {}, {}, {}
    names, reasons = set(ex['officer_terms']['names']), set(ex['officer_terms']['reasons'])
    if spool:
        spool.mkdir(parents=True, exist_ok=True)
    def read(value):
        return json.loads(value.read_text()) if isinstance(value, Path) else value
    entries = [('api', e) for e in SPEC['api']]
    if golden:
        entries += [('golden', e) for e in SPEC['golden'] if not e.get('optional')]
    for group, entry in entries:
        if '{program_id}' in entry['save']:
            mappings = read(cache.get(('mappings', f'as_of_date={day}&compact=true')))
            if not isinstance(mappings, dict) or not isinstance(mappings.get('programs'), list):
                raise ExportError('정답 대조용 프로그램 목록을 확인하지 못했습니다.')
            programs = [p['id'] for p in mappings['programs'] if p.get('policy_id') == 'POL_2025_0907' and p.get('status') not in ('REJECTED', 'RELEASED')]
            if any(not re.fullmatch(r'PRG_[0-9a-f]+', p) for p in programs):
                raise ExportError('프로그램 ID 형식이 전달 규격과 다릅니다.')
        else:
            programs = [None]
        for program in programs:
            values = {'until_date': day, 'program_id': program}
            query, save = entry['query'].format(**values), entry['save'].format(**values)
            key = (entry['path'], query)
            if key not in cache:
                progress(f'화면 대조 자료 수집 · {entry["path"]}')
                body = fetch(*key)
                codec.collect_terms([body], names, reasons)
                if spool:
                    raw = spool / f'{len(cache)}.json'
                    write_spooled_json(raw, body)
                    cache[key] = raw
                    del body
                else:
                    cache[key] = body
            files[f'{group}/{save}'] = cache[key]
            fetched[f'{group}/{save}'] = datetime.now(timezone.utc).isoformat()
    # API responses can contain names absent from the historic dump privacy scope.
    terms = codec.make_terms(names, reasons)
    ex['officer_terms'] = terms
    reason_set = set(terms['reasons'])
    @lru_cache(maxsize=32768)
    def short_text(value):
        return codec.scrub_text(value, terms['names'], reason_set)
    def scrub_text(value):
        return short_text(value) if len(value) < 4096 else codec.scrub_text(value, terms['names'], reason_set)
    if spool:
        # Rewrite one unique response at a time. Repeated filenames share the
        # sanitized file until copied into the final package, not Python objects.
        for index, path in enumerate(cache.values(), 1):
            progress(f'대조 자료 개인정보 제거 · {index}/{len(cache)}')
            body = public_json(read(path), terms, scrub_text)
            write_spooled_json(path, body)
            del body
            encode_public_document_links(path)
        return files, fetched
    clean = {key: public_json(body, terms, scrub_text) for key, body in cache.items()}
    by_identity = {id(cache[key]): clean[key] for key in cache}
    return {rel: by_identity[id(body)] for rel, body in files.items()}, fetched


def legacy_response(service, path, query):
    """Removed UI routes, retained builders: reproduce the October wire shapes.

    These are private export adapters, not reintroduced public/admin endpoints.
    """
    if path == 'samples':
        from datetime import date
        params = dict(parse_qsl(query))
        return service.sample_page(as_of=date.fromisoformat(params['as_of_date']), page=1, page_size=100)
    if path == 'validation':
        from .coverage_audit import coverage_audit
        from datetime import date
        day = dict(parse_qsl(query)).get('as_of_date')
        rows = service.projects(as_of=date.fromisoformat(day) if day else None)
        sources = service.sources(compact=True)
        issues = [dict(project_id=r['id'], name=r['name'], source_id=r['source_id'], code=code)
                  for r in rows for code in r.get('warnings', [])]
        return dict(items=issues, total=len(issues), baseline_status='DRAFT', coverage=coverage_audit(sources),
                    coverage_details=service.coverage_details(), data_gaps=service.data_gaps(sources, rows),
                    notes=['자동 매칭·승인 대기 사업은 담당자 확정과 구분합니다. 연결 해제 사업은 정책 통계에서 제외합니다.',
                           '실제 착공·준공·입주 단계는 공고 또는 담당자 근거 확인 후 확정합니다.'])
    if path == 'connections':
        from .connection_audit import connection_audit
        return connection_audit(service.sources(compact=True))
    if path == 'api-requests':
        from .api_requests import board
        return board(service)
    raise ExportError('등록되지 않은 이전 API입니다.')


def build(service, folder, since, golden, progress, fetch=None):
    progress('원천 31종 · 같은 시점의 DB 자료 추출')
    ex, token = snapshot(service, since)
    started = time.monotonic()
    def local_fetch(path, query):
        if time.monotonic() - started > 1200:
            raise ExportError('생성 제한 시간 20분을 초과했습니다. 잠시 후 다시 시도하세요.')
        try:
            if path in {'validation', 'connections', 'api-requests', 'samples'}:
                return legacy_response(service, path, query)
            headers = {}
            if path == 'data-integrity':
                secret = os.environ.get('POC10_INTERNAL_SECRET', '')
                if not secret: raise ExportError('내부 인증 설정이 없어 정답 대조 자료를 생성할 수 없습니다.')
                stamp = str(int(time.time()))
                signature = hmac.new(secret.encode(), f'{stamp}:GET:/poc/home/api/data-integrity'.encode(), hashlib.sha256).hexdigest()
                headers['x-home-admin'] = stamp + ':' + signature
            # Constant loopback base and checked-in paths: no user URL/SSRF.
            response = httpx.get('http://127.0.0.1:8000/poc/home/api/' + path,
                                 params=dict(parse_qsl(query)), headers=headers, timeout=90, trust_env=False)
            response.raise_for_status()
            body = response.json()
            if path == 'source-summary':
                for _ in range(60):
                    if body.get('status') == 'READY' and not body.get('refreshing') and not body.get('refresh_failed'):
                        break
                    if body.get('refresh_failed'):
                        raise ExportError('출처 집계 갱신 실패로 대조 자료를 만들 수 없습니다. 출처와 수집현황을 확인하세요.')
                    time.sleep(1)
                    response = httpx.get('http://127.0.0.1:8000/poc/home/api/source-summary', timeout=30, trust_env=False)
                    response.raise_for_status()
                    body = response.json()
                else:
                    raise ExportError('출처 집계가 갱신 중입니다. 완료 후 다시 생성하세요.')
            return body
        except (httpx.HTTPError, ValueError):
            raise ExportError(f'화면 대조 자료 조회 실패: {path}. 다시 생성해 주세요.') from None
    with tempfile.TemporaryDirectory(prefix='.work-', dir=folder) as temporary:
        tmp = Path(temporary)
        files, fetched = fetch_bundle(fetch or local_fetch, ex, golden, progress, spool=tmp/'responses')
        with service.engine.connect() as conn:
            after = conn.execute(text('SELECT txid_current_snapshot()::text')).scalar()
        if after != token:
            raise ExportError('생성 중 DB 변경이 감지되어 시점이 다른 자료의 전달을 중단했습니다. 수집·검토 작업 종료 후 다시 생성하세요.')
        if datetime.now(KST).date() != codec.parse_ts(ex['until']).astimezone(KST).date():
            raise ExportError('생성 중 한국시간 기준 날짜가 바뀌었습니다. 같은 기준일의 자료를 위해 다시 생성하세요.')
        fallback = select_delta(ex, since)
        progress('담당자 정보 제거 · 전달 규격 및 파일 해시 검증')
        extra, package = tmp / 'extra', tmp / 'package'
        import shutil
        for rel, source in files.items():
            destination = extra / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        codec.write_json(str(extra / 'fetched.json'), fetched)
        for item in SPEC['web']:
            source = ROOT / 'web/assets' / Path(item['path']).name
            target = extra / 'web' / item['save']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        manifest = codec.seal(SPEC, ex, str(package), str(extra))
        codec.read_package(SPEC, str(package))
        for d in SPEC['slices']:
            for row in json.loads((package / 'slices' / (d['name'] + '.json')).read_text()):
                codec.Slice(d).check_row(row, d['name'])
        # Full packages can also be round-tripped with the recipient's own apply.
        if ex['since'] is None:
            codec.apply(SPEC, str(package), str(tmp / 'roundtrip'))
        output = folder / 'dataset.zip'
        with zipfile.ZipFile(output.with_suffix('.tmp'), 'w', zipfile.ZIP_DEFLATED, compresslevel=4) as archive:
            for path in sorted(package.rglob('*')):
                if path.is_file():
                    archive.write(path, path.relative_to(package).as_posix())
        output.with_suffix('.tmp').replace(output)
    return {'filename': f'home-slices-{codec.edition_of(codec.parse_ts(ex["until"]))}.zip',
            'since': ex['since'], 'until': ex['until'], 'full_fallback': fallback,
            'files': len(manifest['files']), 'rows': sum(v['rows'] or 0 for v in manifest['files'].values()),
            'bytes': output.stat().st_size, 'golden': golden}


class SliceJobs:
    """One export per service, no polling except an explicitly opened active job."""
    def __init__(self, service):
        self.service = service
        self.root = service.data_dir / 'runtime/dataset-slices'
        self.guard = threading.Lock()

    def _save(self, folder, state):
        temp = folder / 'state.tmp'
        temp.write_text(json.dumps(state, ensure_ascii=False))
        temp.replace(folder / 'state.json')

    def get(self, job_id):
        if not re.fullmatch(r'[0-9a-f]{32}', job_id):
            raise ExportError('잘못된 생성 작업 ID입니다.')
        folder = self.root / job_id
        if not (folder / 'state.json').is_file():
            raise ExportError('생성 자료가 없거나 보관 기간이 지났습니다. 다시 생성하세요.')
        state = json.loads((folder / 'state.json').read_text())
        if time.time() - state['created_epoch'] > TTL:
            raise ExportError('생성 자료의 24시간 보관 기간이 지났습니다. 다시 생성하세요.')
        if state['status'] == 'RUNNING':
            with (self.root / 'export.lock').open('a') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass
                else:
                    state.update(status='FAILED', message='서비스 재시작으로 생성이 중단됐습니다. 다시 생성하세요.')
                    import shutil
                    for work in folder.glob('.work-*'):
                        if work.is_dir(): shutil.rmtree(work)
                    self._save(folder, state)
        return state

    def start(self, target, mode, value, golden):
        if target != TARGET:
            raise ExportError('등록된 연계 시스템을 선택하세요.')
        since = parse_since(mode, value)
        params = {'target': target, 'mode': mode, 'since': codec.pg_text(since) if since else None, 'golden': golden}
        with self.guard:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            lock = (self.root / 'export.lock').open('a')
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock.close()
                active = self.root / 'active.json'
                if active.is_file():
                    state = self.get(json.loads(active.read_text())['id'])
                    if state['parameters'] == params:
                        return state
                raise ExportError('다른 데이터셋을 생성 중입니다. 완료 후 다시 시도하세요.') from None
            # Only sealed exports and small state files live here. Remove expired packages.
            import shutil
            for path in self.root.iterdir():
                if path.is_dir() and re.fullmatch(r'[0-9a-f]{32}', path.name) and time.time() - path.stat().st_mtime > TTL:
                    shutil.rmtree(path)
            active = self.root / 'active.json'
            folder = self.root / uuid.uuid4().hex
            folder.mkdir(mode=0o700)
            state = {'id': folder.name, 'status': 'RUNNING', 'message': '데이터셋 생성 준비',
                     'parameters': params, 'created_epoch': time.time()}
            self._save(folder, state)
            pending = self.root / 'active.tmp'
            pending.write_text(json.dumps({'id': folder.name}))
            pending.replace(active)
            def run():
                def progress(message):
                    state['message'] = message
                    self._save(folder, state)
                try:
                    result = build(self.service, folder, since, golden, progress)
                    state.update(status='COMPLETED', message='전달 데이터셋 생성·검증 완료', result=result)
                except (ExportError, codec.Stop) as error:
                    state.update(status='FAILED', message=str(error))
                except Exception as error:
                    LOG.warning('Dataset slice failed (%s)', type(error).__name__)
                    state.update(status='FAILED', message='데이터셋 생성 중 오류가 발생했습니다. 다시 시도하거나 관리자에게 확인해 주세요.')
                finally:
                    self._save(folder, state)
                    lock.close()
            threading.Thread(target=run, name='home-dataset-slice', daemon=True).start()
            return copy.deepcopy(state)
