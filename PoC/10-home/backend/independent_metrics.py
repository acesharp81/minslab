"""Event-based metrics and immutable knowledge-time snapshots.

External briefing values and official aggregate statistics never supply events.
Missing event dates, scope conflicts and inferred quantities remain explicit.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json

from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from .db import Audit, MetricSnapshot, Revision, now
from .service import HomeService, as_utc, KST
from .evidence_bridge import by_project, facts, match_key
from .subject_identity import taxonomy

VERSION = 'independent-events-v5-verified-notice-partitions'
EVENTS = {
    'BUSINESS': 'BUSINESS_STARTED', 'APPROVAL': 'APPROVAL_GRANTED',
    'CONSTRUCTION': 'CONSTRUCTION_STARTED', 'SUPPLY': 'RECRUITMENT_PUBLISHED',
    'COMPLETION': 'COMPLETION_VERIFIED', 'MOVE_IN': 'MOVE_IN_STARTED',
}
ORIGIN_CLASSES = ('PRIMARY_OPERATION', 'PRIMARY_NOTICE', 'OFFICIAL_STAT', 'EXTERNAL_BENCHMARK', 'ANALYST_DERIVED')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def source_role(source_id, kind=None):
    if kind == 'statistic' or source_id in ('molit_statistics', 'national_statistics', 'incheon_statistics'):
        return 'OFFICIAL_STAT'
    if kind in ('official_observation', 'external_benchmark'):
        return 'EXTERNAL_BENCHMARK'
    if kind in ('project_profile','delivery_setting') or source_id in ('officer','project_information','project_profile'):
        return 'ANALYST_DERIVED'
    return 'PRIMARY_NOTICE' if any(s in source_id for s in ('notice', 'document', 'cleanup')) else 'PRIMARY_OPERATION'


def notice_classification(row):
    """Use the offering's tenure, including rental with future sale conversion."""
    result = taxonomy(row)
    text = str(row.get('tenure') or row.get('name') or '')
    rental = any(t in text for t in ('임대', '행복주택', '분양전환'))
    sale = '공공분양' in text or ('분양' in text and not rental)
    result['supply_mode'] = 'UNKNOWN' if rental and sale else 'RENT' if rental else 'SALE' if sale else result['supply_mode']
    return result


def notice_round(row):
    # Earlier stored parser editions predate notice_round. Never treat their
    # residual or waiting-list notices as new supply just because it is absent.
    title = row.get('notice_title') or row.get('name') or ''
    if row.get('notice_status') == 'CANCELLED' or '취소공고' in title:
        return 'CANCELLED'
    if '예비입주자' in title:
        return 'WAITLIST'
    if any(t in title for t in ('추가', '잔여', '재공고')):
        return 'ADDITIONAL'
    return row.get('notice_round') or 'MAIN'


def validate_event(event):
    reasons = []
    if event['evidence_origin'] not in ('PRIMARY_OPERATION', 'PRIMARY_NOTICE'):
        reasons.append('NOT_PRIMARY_EVENT')
    try:
        date.fromisoformat(event.get('event_date') or '')
    except ValueError:
        reasons.append('EVENT_DATE_UNCONFIRMED')
    if event.get('date_basis')=='OBSERVED_BY' and not event.get('occurrence_period_within_query'):
        reasons.append('OBSERVATION_IS_NOT_NEW_EVENT_DATE')
    quantity = event.get('quantity')
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
        reasons.append('QUANTITY_UNCONFIRMED')
    if not event.get('source_revision_id') or not event.get('evidence_url'):
        reasons.append('EVIDENCE_MISSING')
    if event.get('inferred'):
        reasons.append('INFERRED_EVENT')
    if event.get('notice_round', 'MAIN') != 'MAIN':
        reasons.append('REISSUE_NOT_NET_NEW')
    if event.get('event_type') == 'CONSTRUCTION_STARTED' and not event['taxonomy']['construction_applicable']:
        reasons.append('NOT_APPLICABLE')
    return reasons


def partition_notices(events):
    """Sum disjoint tenures only with a checked original's complete breakdown.

    Different names or quantities alone do not prove disjointness. Corrections
    and duplicate project representations contribute once within each tenure.
    """
    proofs=[]
    for event in events:
        proof=event.get('notice_scope_proof') or {}
        parts=proof.get('breakdown');total=proof.get('total_units')
        if (isinstance(parts,dict) and len(parts)>1 and isinstance(total,int) and not isinstance(total,bool)
                and all(isinstance(v,int) and not isinstance(v,bool) and v>0 for v in parts.values())
                and sum(parts.values())==total and proof.get('source_revision_id')):
            proofs.append(proof)
    if not proofs or len({digest(p['breakdown']) for p in proofs})!=1:return None
    proof=proofs[-1];parts=proof['breakdown'];groups=defaultdict(list)
    for event in events:
        tenure=event.get('notice_tenure')
        if tenure not in parts or event['quantity']!=parts[tenure]:return None
        groups[tenure].append(event)
    if set(groups)!=set(parts):return None
    result=[]
    for tenure,pool in sorted(groups.items()):
        chosen=max(pool,key=lambda e:(e['review_status']=='CONFIRMED',e.get('collected_at') or '',e['event_date'],e['event_id']))
        result.append(dict(chosen,quantity_scope='PART',source_total_units=proof['total_units'],scope_label=tenure,
            disjointness_proof=proof,supporting_event_ids=sorted(e['event_id'] for e in pool)))
    return result


def build(service, known_at, region=None, period_start=None, period_end=None):
    if known_at.tzinfo is None:
        raise ValueError('인지 기준시각의 시간대가 필요합니다')
    day = known_at.astimezone(KST).date()
    end = period_end or day.isoformat()
    start = period_start or f'{day.year}-01-01'
    if date.fromisoformat(start) > date.fromisoformat(end) or end > day.isoformat():
        raise ValueError('실적 기간은 인지 기준일까지의 유효한 기간이어야 합니다')
    projects = service.rows('project', day)
    bridges = by_project(service, day)
    stage_rows=service.rows('stage_evidence', day)
    stage_links = defaultdict(list)
    for link in stage_rows:
        if link.get('status') in ('REVIEW', 'CONFIRMED') and link.get('selected'):
            stage_links[link['project_id']].append(link)
    profiles = {r['project_id']: r for r in service.rows('project_profile', day)}
    pinned_cache = {}

    def pinned(entity_id, revision_no):
        key = entity_id, revision_no
        if key not in pinned_cache:
            with service.sessions() as db:
                query = select(Revision).where(Revision.entity_id == entity_id, Revision.recorded_at < known_at)
                if revision_no is not None:
                    query = query.where(Revision.revision_no == revision_no)
                r = db.scalar(query.order_by(Revision.revision_no.desc()))
                pinned_cache[key] = dict(source_revision_id=r.id, source_payload_hash=r.payload_hash,
                                         recorded_at=as_utc(r.recorded_at).isoformat(), source_id=r.source_id,
                                         source_taxonomy=notice_classification(dict(r.payload, source_id=r.source_id)),
                                         source_notice_round=notice_round(r.payload) if r.source_id=='lh_notice_detail' else None,
                                         checked_notice_tenure=r.payload.get('tenure') if r.source_id=='lh_notice_detail' and r.payload.get('verification_status')=='SOURCE_CONTENT_CHECKED' and not r.payload.get('multi_complex') else None,
                                         notice_scope_proof=dict(breakdown=r.payload.get('complex_scope_breakdown'),
                                             total_units=r.payload.get('complex_total_units'),source_revision_id=r.id,
                                             source_payload_hash=r.payload_hash,evidence_url=r.payload.get('evidence_url'))
                                             if r.source_id=='lh_notice_detail' and r.payload.get('verification_status')=='SOURCE_CONTENT_CHECKED' and not r.payload.get('multi_complex') else None) if r else {}
        return pinned_cache[key]

    candidates = []
    for project in projects:
        if region and project['region'] != region:
            continue
        if project.get('mapping', {}).get('status') in ('RELEASED', 'REJECTED'):
            continue
        physical = match_key(project)
        physical_id = digest(list(physical) if physical else ['SOURCE_ANCHOR', project['id']])[:24]
        classification = taxonomy(project)

        def add(fact, source, relation='SOURCE_ANCHOR', review='REVIEW'):
            if fact.get('kind') != 'ACTUAL' or not fact.get('date') or not start <= fact['date'] <= end:
                return
            stage = fact.get('stage')
            if stage == 'CONSTRUCTION' and fact.get('pct') is not None and not fact.get('milestone'):
                event_type = 'CONSTRUCTION_PROGRESS_OBSERVED'
            elif fact.get('milestone') == 'COMPLETION':
                event_type = EVENTS['COMPLETION']
            elif fact.get('milestone') == 'AMENDED_APPROVAL':
                event_type = 'APPROVAL_AMENDED'
            else:
                event_type = EVENTS.get(stage)
            if not event_type:
                return
            quantity = fact.get('units', fact.get('scope_units'))
            # A date plus a project capacity does not attest the actual event
            # quantity. Retain the event as unresolved until scope is explicit.
            meta = pinned(source['source_entity_id'], source.get('source_revision_no')) if source.get('source_entity_id') else source if source.get('source_revision_id') else pinned(source.get('id'), source.get('source_revision_no'))
            event_classification = dict(classification)
            classification_evidence = None
            date_basis=fact.get('date_basis','EVENT')
            occurrence_start=fact.get('event_period_start')
            period_within=bool(date_basis=='OBSERVED_BY' and occurrence_start
                and start<=occurrence_start<=fact['date']<=end)
            if event_type == 'RECRUITMENT_PUBLISHED':
                # Classify the offering, not whichever project representation
                # survives deduplication (a construction row may omit tenure).
                source_classification = meta.get('source_taxonomy') or notice_classification(source)
                if source_classification['supply_mode'] != 'UNKNOWN':
                    event_classification['supply_mode'] = source_classification['supply_mode']
                    classification_evidence = dict(field='supply_mode', basis='모집 사건 원문 분류',
                        source_revision_id=meta.get('source_revision_id'),
                        value=source_classification['supply_mode'])
            value = dict(project_id=project['id'], name=project['name'], physical_scope_id=physical_id,
                         region=project['region'], policy_id=project.get('mapping', {}).get('policy_id'),
                         policy_status=project.get('mapping', {}).get('status'), taxonomy=event_classification,
                         classification_evidence=classification_evidence,
                         notice_tenure=meta.get('checked_notice_tenure') if event_type=='RECRUITMENT_PUBLISHED' else None,
                         notice_scope_proof=meta.get('notice_scope_proof') if event_type=='RECRUITMENT_PUBLISHED' else None,
                         event_type=event_type, event_date=fact['date'], quantity=quantity, unit='HOUSING_UNIT',
                         date_basis=date_basis,observed_on=fact.get('observed_on'),
                         source_event_date=fact.get('source_event_date') if date_basis!='EVENT' else fact['date'],
                         occurrence_period_start=occurrence_start,occurrence_period_end=fact['date'] if occurrence_start else None,
                         occurrence_period_within_query=period_within,
                         quantity_scope='PART' if fact.get('scope_partial') or fact.get('source_total_units') else 'WHOLE',
                         source_total_units=fact.get('source_total_units'), scope_label=fact.get('scope_label'),
                         source_entity_id=source.get('source_entity_id') or source.get('id'),
                         source_revision_id=meta.get('source_revision_id'), source_payload_hash=meta.get('source_payload_hash'),
                         source_id=meta.get('source_id') or source.get('source_id'),
                         collected_at=meta.get('recorded_at'), published_at=source.get('source_date'),
                         event_date_precision='DAY' if date_basis=='EVENT' else 'PERIOD' if period_within else 'OBSERVATION',
                         publication_time_precision='DAY' if source.get('source_date') else 'UNKNOWN',
                         evidence_url=source.get('evidence_url'), evidence_origin=source.get('evidence_origin') or source_role(meta.get('source_id') or source.get('source_id') or ''),
                         basis=fact.get('basis'), relation=relation, review_status=review,
                         inferred=bool(fact.get('inferred')), notice_round=(meta.get('source_notice_round') if event_type=='RECRUITMENT_PUBLISHED' else None)
                             or fact.get('notice_round') or source.get('source_notice_round') or 'MAIN')
            value['validation_reasons'] = validate_event(value)
            value['measurement_status'] = 'OBSERVED' if not value['validation_reasons'] else 'UNRESOLVED'
            value['event_id'] = 'EVT_' + digest({k: value[k] for k in ('physical_scope_id', 'event_type', 'event_date', 'quantity', 'source_revision_id')})[:24]
            candidates.append(value)

        for f in facts(project, day):
            add(f, project)
        for bridge in bridges.get(project['id'], []):
            if bridge.get('status') not in ('REVIEW', 'CONFIRMED'):
                continue
            for f in bridge.get('facts', []):
                add(f, bridge, bridge.get('relation_type'), bridge['status'])
        for link in stage_links.get(project['id'], []):
            picked = link['selected']
            if picked.get('method') in ('PREREQUISITE', 'STAGE_INFERENCE'):
                continue
            add(dict(kind='ACTUAL', stage=link['stage'], date=picked.get('event_date'), units=picked.get('units'),
                     milestone=picked.get('event_type'), scope_partial=picked.get('scope_partial', False),
                     source_total_units=picked.get('source_units'), scope_label=picked.get('scope_label'),
                     inferred=picked.get('inferred'), basis=picked.get('basis')), picked, 'STAGE_LINK', link['status'])
        # Officer event measurements remain distinct from estimated plan defaults.
        for stage, measurement in profiles.get(project['id'], {}).get('progress', {}).items():
            if measurement.get('inferred') or not measurement.get('event_date') or any(p.get('rule') == 'PROJECT_CAPACITY_ASSUMPTION' for p in measurement.get('field_provenance', {}).values()):
                continue
            add(dict(kind='ACTUAL', stage=stage, date=measurement['event_date'], units=measurement.get('units'),
                     basis=measurement.get('reason')), dict(profiles[project['id']], evidence_url=measurement.get('evidence_url') or project.get('evidence_url'),evidence_origin='ANALYST_DERIVED'),
                'OFFICER_MEASUREMENT', 'CONFIRMED')

    unique = {e['event_id']: e for e in candidates}
    grouped = defaultdict(list)
    excluded = []
    for event in unique.values():
        if event['validation_reasons']:
            excluded.append(event)
        elif event['event_type'] != 'CONSTRUCTION_PROGRESS_OBSERVED':
            grouped[(event['physical_scope_id'], event['event_type'])].append(event)
    selected, conflicts, resolved_partitions = [], [], []
    for key, events in grouped.items():
        partition=partition_notices(events) if key[1]=='RECRUITMENT_PUBLISHED' else None
        if partition:
            selected.extend(partition)
            resolved_partitions.append(dict(physical_scope_id=key[0],event_type=key[1],
                reason='OFFICIAL_DISJOINT_TENURE_BREAKDOWN',total_units=sum(e['quantity'] for e in partition),
                breakdown={e['notice_tenure']:e['quantity'] for e in partition},
                proof=partition[0]['disjointness_proof'],event_ids=[e['event_id'] for e in partition]))
            continue
        # Prefer an explicitly whole scope. Otherwise report a known partial
        # scope once; disjointness is not guessed from different source rows.
        whole = [e for e in events if e['quantity_scope'] == 'WHOLE']
        pool = whole or events
        quantities = {e['quantity'] for e in pool}
        dates = {e['event_date'] for e in pool}
        if len(quantities) > 1 or (key[1] == 'CONSTRUCTION_STARTED' and len({d[:4] for d in dates}) > 1):
            conflicts.append(dict(physical_scope_id=key[0], event_type=key[1], reason='SCOPE_OR_EVENT_CONFLICT',
                                  event_ids=[e['event_id'] for e in events], quantities=sorted(quantities)))
            continue
        chosen = max(pool, key=lambda e: (e['review_status'] == 'CONFIRMED', e['event_date'], e['event_id']))
        selected.append(dict(chosen, supporting_event_ids=sorted(e['event_id'] for e in events)))
    metrics = []
    for event_type in sorted(set(EVENTS.values()) | {'APPROVAL_AMENDED', 'OCCUPIED_UNITS', 'CONTRACT_SIGNED'}):
        events = [e for e in selected if e['event_type'] == event_type]
        metrics.append(dict(metric_code=event_type, metric_origin='INDEPENDENT_EVENT_AGGREGATE',
                            period_start=start, period_end=end, region=region or '등록된 수도권 사업',
                            value=sum(e['quantity'] for e in events) if events else None, unit='HOUSING_UNIT',
                            event_ids=[e['event_id'] for e in events], scope_status='PARTIAL_REGISTERED_POPULATION',
                            publishable=False, not_publishable_reasons=['POPULATION_NOT_VERIFIED'],
                            missing_reason=None if events else 'NO_VERIFIED_EVENT_FOR_SCOPE'))
    inputs=[]
    for kind,rows in [('project',projects),('evidence_bridge',[b for group in bridges.values() for b in group]),
                      ('stage_evidence',stage_rows),('project_profile',list(profiles.values()))]:
        for row in rows:
            inputs.append(dict(kind=kind,entity_id=row['id'],revision_no=row['revision_no'],
                               revision_id=row.get('source_revision_id'),payload_hash=row.get('source_payload_hash'),
                               mapping=row.get('mapping'),status=row.get('status')))
    return dict(version=VERSION, known_at=known_at.isoformat(), period_start=start, period_end=end,input_manifest=inputs,
                metric_origin='INDEPENDENT_EVENT_AGGREGATE', project_records=len(projects),
                population_status='UNVERIFIED', metrics=metrics, events=list(unique.values()),
                selected_events=selected, exclusions=excluded, conflicts=conflicts,resolved_scope_partitions=resolved_partitions,
                counts=dict(candidate_events=len(unique), selected_events=len(selected), exclusions=len(excluded), conflicts=len(conflicts),
                            verified_scope_partitions=len(resolved_partitions)),
                note='등록 사업의 직접 사건 집계. 기관 총량통계·외부 발표 수치·모델 추정을 포함하지 않으며 수도권 전수 실적으로 표시하지 않습니다.')


def freeze(service, actor, reason, known_at=None, **filters):
    if not actor.strip() or not reason.strip():
        raise ValueError('담당자와 사유가 필요합니다')
    known_at = known_at or now()
    if known_at.tzinfo is None or known_at > now():
        raise ValueError('인지 기준시각은 시간대가 있는 현재 이하 시각이어야 합니다')
    with service.engine.connect() as connection:
        if service.engine.dialect.name == 'postgresql':
            connection = connection.execution_options(isolation_level='REPEATABLE READ')
        with connection.begin():
            if service.engine.dialect.name == 'postgresql':
                connection.execute(text('SET TRANSACTION READ ONLY'))
            scoped = HomeService(service.engine, service.data_dir, known_at=known_at)
            scoped.sessions = sessionmaker(bind=connection, expire_on_commit=False, join_transaction_mode='create_savepoint')
            result = build(scoped, known_at, **filters)
    from pathlib import Path
    code_root=Path(__file__).resolve().parent
    code_hashes={name:hashlib.sha256((code_root/name).read_bytes()).hexdigest()
                 for name in ('independent_metrics.py','evidence_bridge.py','subject_identity.py','service.py','collectors.py')}
    context = dict(filters=filters, known_at=known_at.isoformat(), algorithm_version=VERSION,algorithm_sha256=code_hashes,
                   source_roles=ORIGIN_CLASSES, benchmark_allowed=False,
                   independence_status='PROSPECTIVE_FREEZE', approval_scope='HOME_INTERNAL_VALIDATION')
    checksum = digest(dict(context=context, result=result))
    identity = 'SNP_' + checksum[:32]
    from .snapshot_content import store_content
    with service.sessions.begin() as db:
        existing = db.get(MetricSnapshot, identity)
        if existing is None:
            db.add(MetricSnapshot(id=identity, known_at=known_at, actor=actor, reason=reason,
                                  context=context, result=store_content(db,context,result), digest=checksum))
            db.add(Audit(entity_id=identity, action='INDEPENDENT_SNAPSHOT', before={},
                         after=dict(actor=actor, reason=reason, digest=checksum, context=context, counts=result['counts'])))
    return dict(id=identity, digest=checksum, context=context, result=result)


def get_snapshot(service, identity):
    with service.sessions() as db:
        row = db.get(MetricSnapshot, identity)
        if row is None:
            raise ValueError('산출 기준본이 없습니다')
        from .snapshot_content import restore_content
        result=restore_content(db,row.context,row.result)
        expected = digest(dict(context=row.context, result=result))
        if expected != row.digest:
            raise ValueError('산출 기준본 무결성 확인 실패')
        return dict(id=row.id, known_at=as_utc(row.known_at).isoformat(), actor=row.actor, reason=row.reason,
                    digest=row.digest, context=row.context, result=result)
