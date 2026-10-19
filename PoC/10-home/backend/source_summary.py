"""Read-only collection volume: current rows × table columns, never revision count."""
from collections import Counter, defaultdict
from datetime import datetime, time, timezone
import json
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

from sqlalchemy import String, bindparam, func, select, text
from sqlalchemy.exc import DataError

from .db import Batch, IdentityAlias, Revision
from .sources import SOURCES

KST = ZoneInfo('Asia/Seoul')
TYPES = (
    ('API', '기관 시스템 직접 연계 (API)'), ('PRESS', '정부·공공기관 보도자료'), ('NEWS', '언론사 뉴스 기사'),
    ('NOTICE', '분양·임대 입주자 모집공고'), ('STATISTICS', '주택·인구·가격 공식 통계'), ('FILE', '기관 공개 데이터 파일'),
    ('GIS', '지도 경계·위치·행정구역 자료'), ('DOCUMENT', '사업계획·고시·추진현황 문서'), ('WEB', '기관 홈페이지 게시자료'),
)
LABELS = dict(TYPES)
DESCRIPTIONS = {
    'API': '기관이 제공하는 데이터 조회 기능에 연결해 인허가·주택·지역 정보를 가져옵니다.',
    'PRESS': '정부와 공공기관이 발표한 정책 내용·공급 목표·후속 계획을 수집합니다.',
    'NEWS': '언론사가 보도한 주택 정책과 사업 관련 기사를 수집하는 유형입니다.',
    'NOTICE': '분양·임대 모집공고에서 공급 호수·주택형·모집 일정·입주 예정일을 가져옵니다.',
    'STATISTICS': '기관이 공표한 주택 공급량·멸실량·가격지수 등의 통계 수치를 가져옵니다.',
    'FILE': '기관이 공개한 파일에서 사업 목록·공급계획·건설 실적 등을 읽어옵니다.',
    'GIS': '지도에 표시할 행정구역 코드·지구 경계·블록 위치를 가져옵니다.',
    'DOCUMENT': '사업계획·변경 고시·추진현황 문서에서 사업별 물량과 일정을 확인합니다.',
    'WEB': '기관 홈페이지의 사업·주택 현황 등 게시 내용에서 필요한 항목을 가져옵니다.',
}
INACTIVE = {'RELEASED', 'REJECTED', 'UNMATCHED', 'INVALID'}


def category(source):
    """One primary category per source; API delivery is also shown separately."""
    explicit = source.get('data_type')
    if explicit in LABELS:
        return explicit
    kind, mode = source.get('type'), source.get('collection_mode')
    if kind == 'NEWS' or mode == 'NEWS':
        return 'NEWS'
    if kind == 'NOTICE':
        return 'NOTICE'
    if kind == 'POLICY' or source['id'] in {'policy_history', 'policy_907_plan'}:
        return 'PRESS'
    if source.get('key_env'):
        return 'API'
    if kind == 'GIS':
        return 'GIS'
    if kind in {'STATISTIC', 'MARKET_REFERENCE'}:
        return 'STATISTICS'
    if mode in {'PUBLIC_FILE', 'AGENCY_PLAN_FILE', 'HISTORY'}:
        return 'FILE'
    if mode in {'PUBLIC_DOCUMENT', 'LEGAL_PLAN_PILOT', 'POLICY_DELIVERY'}:
        return 'DOCUMENT'
    return 'WEB'


def source_metadata(source):
    key = category(source)
    access = 'API' if source.get('key_env') else '파일' if source.get('collection_mode') in {
        'PUBLIC_FILE', 'AGENCY_PLAN_FILE', 'HISTORY', 'LEGAL_PLAN_PILOT', 'RAW_REPLAY'} else '웹'
    return dict(data_type=key, data_type_label=LABELS[key], access_method=access)


def _linked_ids(db, source_ids):
    """Selected references only: candidate lists and repeated stage links do not add rows."""
    projects = set(db.scalars(select(Revision.entity_id).where(
        Revision.kind == 'project', Revision.source_id.in_(source_ids),
        Revision.superseded_at.is_(None))))
    linked = set(projects)
    records = db.execute(select(Revision.kind, Revision.payload).where(
        Revision.kind.in_(('stage_evidence', 'collection_link', 'evidence_bridge',
                           'project_location', 'block_location', 'document_evidence')),
        Revision.superseded_at.is_(None)))
    for kind, row in records:
        if row.get('status') in INACTIVE or row.get('project_id') not in projects:
            continue
        if kind == 'stage_evidence':
            linked.add((row.get('selected') or {}).get('source_entity_id'))
        elif kind == 'collection_link':
            linked.update(r.get('source_entity_id') for r in row.get('links', []))
        elif kind == 'evidence_bridge':
            linked.add(row.get('source_entity_id'))
    # Direct, stored business references (e.g. the registered project-location source).
    direct = db.execute(select(Revision.entity_id, Revision.payload).where(
        Revision.kind.in_(('project_location', 'block_location', 'document_evidence')),
        Revision.source_id.in_(source_ids), Revision.superseded_at.is_(None)))
    linked.update(eid for eid, row in direct if row.get('project_id') in projects
                  and row.get('status') not in INACTIVE)
    linked.update(db.scalars(select(IdentityAlias.source_entity_id).where(
        IdentityAlias.relation_status.notin_(INACTIVE))))
    linked.discard(None)
    return linked


def _postgres_profiles(db, source_ids, start, instant, linked_ids, cache_path):
    # Immutable revision counts/timestamps validate the per-source schema cache.
    # A new small price batch or an officer edit must not reparse a million registers.
    try:
        stored = json.loads(cache_path.read_text())
        if not isinstance(stored, dict):
            stored = {}
    except (OSError, ValueError):
        stored = {}
    legacy = stored.get('format') != 2
    raw = stored if legacy else stored.get('groups', {})
    saved = {key: value for key, value in raw.items() if isinstance(value, dict)
             and isinstance(value.get('columns'), int) and value['columns'] >= 0
             and isinstance(value.get('version'), list) and len(value['version']) == 2
             and isinstance(value['version'][0], int)}
    # Validate current group counts/maxima using the covering index. A DISTINCT
    # source scan across all revisions since the oldest cache stamp becomes a
    # historical multi-million-row scan after a large backfill.
    changed = set(source_ids)
    if changed:
        versions = db.execute(select(Revision.source_id, Revision.kind, func.count(),
                                     func.max(Revision.recorded_at)).where(
            Revision.superseded_at.is_(None), Revision.source_id.in_(changed)).group_by(
                Revision.source_id, Revision.kind)).all()
        stamps = {f'{sid}|{kind}': [rows, stamp.isoformat()] for sid, kind, rows, stamp in versions}
        reparse = {sid for sid, kind, _, _ in versions
                   if saved.get(f'{sid}|{kind}', {}).get('version') != stamps[f'{sid}|{kind}']}
        columns = {}
        if reparse:
            for sid in sorted(reparse):
                try:
                    # Isolate a malformed Unicode scalar in one document source.
                    # PostgreSQL json_object_keys can reject \u0000 in a value
                    # even though JSON storage and Python's decoder preserve it.
                    with db.begin_nested():
                        fields = db.execute(text("""
                            SELECT kind, count(*) FROM (
                                SELECT DISTINCT kind, json_object_keys(payload::json) AS field
                                FROM home_revision WHERE superseded_at IS NULL AND source_id=:sid
                            ) AS fields GROUP BY kind
                            """), {'sid': sid}).all()
                    columns.update({(sid, kind): count for kind, count in fields})
                except DataError as error:
                    if getattr(error.orig, 'sqlstate', None) != '22P05':
                        raise
                    # Count keys in bounded batches; never rewrite original text
                    # or its evidence hash just to render a statistic.
                    schemas = defaultdict(set)
                    rows = db.execute(select(Revision.kind, Revision.payload).where(
                        Revision.superseded_at.is_(None), Revision.source_id == sid))
                    for kind, payload in rows.yield_per(500):
                        schemas[kind].update(payload)
                    columns.update({(sid, kind): len(keys) for kind, keys in schemas.items()})
        saved = {key: value for key, value in saved.items()
                 if key.split('|', 1)[0] not in changed or key in stamps}
        for sid, kind, _, _ in versions:
            key = f'{sid}|{kind}'
            saved[key] = dict(version=stamps[key], columns=columns.get((sid, kind),
                              saved.get(key, {}).get('columns', 0)))
    saved = {key: value for key, value in saved.items() if key.split('|', 1)[0] in source_ids}
    if changed or legacy:
        temp_name = None
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', dir=cache_path.parent, delete=False) as output:
                temp_name = output.name
                json.dump(dict(format=2, sources=sorted(source_ids), groups=saved), output)
            os.replace(temp_name, cache_path)
            temp_name = None
        except OSError:
            pass  # A disposable cache must not make a read-only statistic unavailable.
        finally:
            if temp_name:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
    profiles = [(key.split('|', 1)[0], key.split('|', 1)[1], value['version'][0], value['columns'])
                for key, value in saved.items()]
    today_cte = """
        WITH collected AS (
            SELECT DISTINCT b.source_id,
                json_array_elements_text(CASE
                    WHEN json_typeof(b.stats::json->'entity_ids') = 'array'
                    THEN b.stats::json->'entity_ids' ELSE '[]'::json END) AS entity_id
            FROM home_batch b WHERE b.status = 'SUCCESS' AND b.source_id IN :sources
                AND b.finished_at >= :start AND b.finished_at <= :instant
        )
        SELECT r.source_id, r.kind, count(*),
               count(*) FILTER(WHERE r.entity_id IN :linked)
        FROM home_revision r JOIN collected c USING(source_id, entity_id)
        WHERE r.superseded_at IS NULL GROUP BY r.source_id, r.kind
    """
    query = text(today_cte).bindparams(bindparam('sources', expanding=True, type_=String()),
                                     bindparam('linked', expanding=True, type_=String()))
    # The JSON batch arrays contain millions of IDs after a backfill. PostgreSQL
    # underestimates the set-returning function and otherwise chooses millions
    # of random index probes. Join the deduplicated set in bulk instead.
    db.execute(text('SET LOCAL enable_nestloop=off'))
    db.execute(text("SET LOCAL work_mem='32MB'"))
    recent = db.execute(query, dict(sources=source_ids, start=start, instant=instant,
                                    linked=sorted(linked_ids))).all()
    db.execute(text('SET LOCAL enable_nestloop=on'))
    return profiles, {(sid, kind): (rows, links) for sid, kind, rows, links in recent}


def _sqlite_profiles(db, source_ids, start, instant, linked_ids):
    collected = set()
    for sid, stats in db.execute(select(Batch.source_id, Batch.stats).where(
            Batch.status == 'SUCCESS', Batch.source_id.in_(source_ids),
            Batch.finished_at >= start, Batch.finished_at <= instant)):
        collected.update((sid, eid) for eid in stats.get('entity_ids', []))
    counts, schemas, recent = Counter(), defaultdict(set), defaultdict(lambda: [0, 0])
    records = db.execute(select(Revision.entity_id, Revision.source_id, Revision.kind,
                                Revision.payload).where(Revision.superseded_at.is_(None),
                                                        Revision.source_id.in_(source_ids)))
    for eid, sid, kind, payload in records.yield_per(1000):
        key = (sid, kind)
        counts[key] += 1
        schemas[key].update(payload)
        if (sid, eid) in collected:
            recent[key][0] += 1
            recent[key][1] += int(eid in linked_ids)
    return [(sid, kind, rows, len(schemas[sid, kind])) for (sid, kind), rows in counts.items()], recent


def build(service, instant=None, sources=None):
    sources = SOURCES if sources is None else sources
    registry = {s['id']: s for s in sources}
    instant = instant or datetime.now(timezone.utc)
    instant = instant.replace(tzinfo=timezone.utc) if instant.tzinfo is None else instant
    day = instant.astimezone(KST).date()
    start = datetime.combine(day, time.min, KST).astimezone(timezone.utc)
    with service.sessions() as db:
        if service.engine.dialect.name == 'postgresql':
            db.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
            db.execute(text('SET TRANSACTION READ ONLY'))
        linked_ids = _linked_ids(db, tuple(registry))
        if service.engine.dialect.name == 'postgresql':
            groups, recent = _postgres_profiles(db, tuple(registry), start, instant, linked_ids,
                Path(service.data_dir) / 'runtime' / 'source-summary-schemas.json')
        else:
            groups, recent = _sqlite_profiles(db, tuple(registry), start, instant, linked_ids)
        linked = Counter()
        for offset in range(0, len(linked_ids), 500):
            subset = sorted(linked_ids)[offset:offset + 500]
            for sid, kind in db.execute(select(Revision.source_id, Revision.kind).where(
                    Revision.entity_id.in_(subset), Revision.source_id.in_(tuple(registry)),
                    Revision.superseded_at.is_(None))):
                linked[sid, kind] += 1
    buckets = {key: dict(id=key, label=label, source_ids=set(), today_source_ids=set(),
                         records=0, columns=0, extracted_cells=0, linked_records=0,
                         today_records=0, today_extracted_cells=0, today_linked_records=0,
                         access_methods=set()) for key, label in TYPES}
    details = []
    for sid, kind, rows, columns in groups:
        today_rows, today_links = recent.get((sid, kind), (0, 0))
        item = dict(source_id=sid, kind=kind, rows=rows, columns=columns,
                    extracted_cells=rows * columns, linked_records=linked[sid, kind],
                    today_rows=today_rows, today_extracted_cells=today_rows * columns,
                    today_linked_records=today_links, **source_metadata(registry[sid]))
        details.append(item)
        bucket = buckets[item['data_type']]
        bucket['source_ids'].add(sid)
        if today_rows:
            bucket['today_source_ids'].add(sid)
        bucket['access_methods'].add(item['access_method'])
        for field, value in dict(records=rows, columns=columns,
                                 extracted_cells=item['extracted_cells'],
                                 linked_records=item['linked_records'], today_records=today_rows,
                                 today_extracted_cells=item['today_extracted_cells'],
                                 today_linked_records=today_links).items():
            bucket[field] += value
    types = []
    for item in buckets.values():
        types.append(dict(item, description=DESCRIPTIONS[item['id']],
                          sources=[dict(id=sid, name=registry[sid].get('name', sid),
                                        url=registry[sid].get('url', '')) for sid in sorted(item['source_ids'])],
                          source_count=len(item['source_ids']),
                          today_source_count=len(item['today_source_ids']),
                          source_ids=sorted(item['source_ids']),
                          today_source_ids=sorted(item['today_source_ids']),
                          access_methods=sorted(item['access_methods'])))
    return dict(as_of_date=day.isoformat(), timezone='Asia/Seoul',
                generated_at=instant.astimezone(KST).isoformat(),
                current=dict(sources=sum(t['source_count'] for t in types),
                             extracted_cells=sum(t['extracted_cells'] for t in types),
                             linked_records=sum(t['linked_records'] for t in types)),
                today=dict(sources=sum(t['today_source_count'] for t in types),
                           extracted_cells=sum(t['today_extracted_cells'] for t in types),
                           linked_records=sum(t['today_linked_records'] for t in types)),
                types=types, groups=details,
                definitions=dict(
                    sources='현재 저장된 데이터가 있는 등록 출처 수',
                    extracted_cells='출처·레코드 유형별 최신 행 수 × 고유 컬럼 수의 합계. 빈칸 포함, 중첩 값은 1컬럼',
                    linked_records='사업 데이터로 정리되거나 사업 근거로 연결된 고유 원천 레코드 수. 후보 목록·해제 링크 제외',
                    today='한국시간 오늘 성공 수집한 고유 레코드 기준. 재수집 포함, 같은 날 반복 수집 중복 제외',
                    today_linked_records='오늘 수집된 데이터 중 현재 사업에 연결된 고유 원천 레코드 수',
                    types='모집공고·보도자료 등 성격을 먼저 분류하고 나머지 API 연계 여부를 구분. 각 출처는 1유형만 집계'))
