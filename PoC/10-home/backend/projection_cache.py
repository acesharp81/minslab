"""Bounded response cache, checked against committed DB changes on every read."""
from collections import OrderedDict
from concurrent.futures import Future
from contextlib import nullcontext
import json
import zlib
from threading import RLock
from time import monotonic
from sqlalchemy import select, func, union_all
from .db import Revision, Mapping, ProgramMapping, Audit, Batch


def projection_version(service, revision_kinds=None, batch_sources=None, audit_actions=None, ignored_audit_actions=()):
    def scalar(value):
        return select(value).scalar_subquery()
    # Every source/goal edit appends an immutable revision. Mapping edits bump
    # revision_no and append Audit. Finished collections change source coverage.
    revisions = select(func.max(Revision.recorded_at))
    batches = select(func.max(Batch.finished_at))
    audits = select(func.max(Audit.recorded_at))
    if audit_actions is not None:
        audits = audits.where(Audit.action.in_(audit_actions))
    if ignored_audit_actions:
        audits = audits.where(Audit.action.not_in(ignored_audit_actions))
    if revision_kinds is not None:
        # MAX over a broad IN predicate can scan millions of raw revisions.
        # Each kind has an indexed (kind, recorded_at) maximum; combine those
        # small results without weakening synchronous change detection.
        if revision_kinds:
            latest = union_all(*(select(func.max(Revision.recorded_at).label('stamp'))
                .where(Revision.kind == kind) for kind in revision_kinds)).subquery()
            revisions = select(func.max(latest.c.stamp))
        else:
            revisions = revisions.where(Revision.kind.in_(()))
    if batch_sources is not None:
        batches = batches.where(Batch.source_id.in_(batch_sources))
    query = select(revisions.scalar_subquery(),
                   scalar(func.sum(Mapping.revision_no)), scalar(func.count(Mapping.id)),
                   scalar(func.sum(ProgramMapping.revision_no)), scalar(func.count(ProgramMapping.id)),
                   audits.scalar_subquery(), batches.scalar_subquery())
    with service.sessions() as session:
        return tuple(session.execute(query).one())


COLLECTION_REVISION_KINDS = (
    'mapping_decision',
    'project', 'policy', 'policy_event', 'policy_profile', 'policy_delivery_plan',
    'program_source', 'program_profile', 'program_alias', 'program_district_plan',
    'project_profile', 'project_report', 'project_location', 'block_location', 'project_parcel',
    'district', 'municipality', 'policy_district', 'policy_municipality',
    'goal', 'delivery_setting', 'execution_schedule', 'stage_evidence', 'evidence_bridge',
    'collection_link', 'collection_assessment', 'collection_research', 'collection_repair',
    'document_evidence', 'notice', 'permit', 'register_recap', 'lh_notice', 'lh_movein_plan',
    'lh_completion_plan', 'plan_notice', 'sh_project', 'gh_notice', 'gh_completion_evidence',
)


def collection_projection_version(service, include_batch_status=True):
    # Unlinked bulk general permits/registers/statistics do not change this
    # project matrix. Persisted link changes and officer audits still invalidate
    # synchronously; historical dates and query variants remain separate keys.
    from .project_collection import CATALOG
    sources = set().union(*CATALOG.values()) | {'official_document', 'officer', 'manual_delivery'}
    return projection_version(service, COLLECTION_REVISION_KINDS, sources if include_batch_status else (),
                              ignored_audit_actions=(
                                  'START_CANDIDATE_FOUND', 'INDEPENDENT_SNAPSHOT',
                                  'DATA_INTEGRITY_ROUND', 'DATA_INTEGRITY_ROUND_AMENDED',
                                  'DATA_INTEGRITY_ROUND_REPLACED',
                                  'AI_PUBLICATION_DISCOVERY', 'AI_PUBLICATION_ANALYSIS'))


RAW_BUILDING_KINDS=('permit','general_permit','register','register_recap','permit_dong','permit_parcel')
RAW_BUILDING_SOURCES=('building_hub','building_hub_incheon','building_general_permit',
    'building_register','building_register_recap','building_hub_details')


def requirements_projection_version(service):
    # The requirements page also reads administrative schedules/cases. Raw
    # building imports and score publication cannot change its indicators.
    kinds=COLLECTION_REVISION_KINDS+('execution_case','execution_scenario','execution_agency')
    return projection_version(service,kinds,batch_sources=(),audit_actions=())


def workspace_projection_version(service):
    """The picker depends on project/catalogue edits, not candidate/batch activity.

    Mapping table versions cover officer membership changes. Project/profile and
    catalogue revisions cover all fields returned by /project-workspace.
    """
    return projection_version(service, (
        'project', 'project_location', 'project_profile', 'project_report', 'execution_schedule',
        'policy', 'policy_event', 'policy_profile', 'program_source', 'program_profile', 'program_alias',
    ), batch_sources=(), audit_actions=())


def delivery_projection_version(service):
    """Raw building imports do not affect policy totals before persisted linking.

    Keep every other revision, officer review and source status in the version.
    A confirmed stage/evidence bridge always invalidates immediately.
    """
    def scalar(q):return q.scalar_subquery()
    query=select(
        scalar(select(func.max(Revision.recorded_at)).where(Revision.kind.not_in(RAW_BUILDING_KINDS+('ai_publication_analysis',)))),
        scalar(select(func.sum(Mapping.revision_no))),scalar(select(func.count(Mapping.id))),
        scalar(select(func.sum(ProgramMapping.revision_no))),scalar(select(func.count(ProgramMapping.id))),
        scalar(select(func.max(Audit.recorded_at)).where(Audit.action.not_in(('START_CANDIDATE_FOUND', 'AI_PUBLICATION_DISCOVERY', 'AI_PUBLICATION_ANALYSIS')))),
        scalar(select(func.max(Batch.finished_at)).where(Batch.source_id.not_in(RAW_BUILDING_SOURCES))))
    with service.sessions() as db:return tuple(db.execute(query).one())


def delivery_screen_projection_version(service):
    # Screen quantities depend on committed ledger/geometry/statistic rows and
    # mapping versions. Collection status and unrelated regional/price imports
    # cannot change them; the full diagnostics endpoint keeps its wider version.
    kinds=tuple(k for k in COLLECTION_REVISION_KINDS if k not in RAW_BUILDING_KINDS and k!='document_evidence')
    version=projection_version(service,kinds,batch_sources=(),audit_actions=())
    # Discovery-only documents do not enter this ledger until a persisted
    # bridge is created. Keep linked document changes synchronous, including
    # historical links, while an unrelated hourly notice no longer rebuilds it.
    links=select(Revision.payload['source_entity_id'].as_string()).where(Revision.kind=='evidence_bridge')
    # A correction can reclassify a previously used statistic, so retain all
    # statistic revisions in invalidation even though reads select one metric.
    statistics=select(func.max(Revision.recorded_at)).where(Revision.kind=='statistic')
    with service.sessions() as db:
        # Materialize IDs once: a JSON-expression semi-join can repeatedly
        # detoast large bridge payloads for every document in PostgreSQL.
        linked_ids=tuple({value for value in db.scalars(links) if value})
        documents=select(func.max(Revision.recorded_at)).where(Revision.kind=='document_evidence',Revision.entity_id.in_(linked_ids))
        return version+tuple(db.execute(select(documents.scalar_subquery(),statistics.scalar_subquery())).one())


class ProjectionCache:
    def __init__(self, version, max_entries=8, ttl=1800, max_bytes=32 * 1024 * 1024, build_guard=None):
        self.version = version
        self.max_entries = max_entries
        self.ttl = ttl
        self.max_bytes = max_bytes
        self.build_guard = build_guard
        self.entries = OrderedDict()
        self.inflight = {}
        self.lock = RLock()

    def get(self, key, build):
        # DB validation stays synchronous: officer edits must be visible on the
        # next request. A slow miss must not hold the lock over unrelated hits.
        version = self.version()
        flight_key = (key, version)
        with self.lock:
            item = self.entries.get(key)
            if item and item[0] == version and monotonic() - item[1] < self.ttl:
                self.entries.move_to_end(key)
                return (zlib.decompress(item[2]) if item[3] else item[2]), 'HIT'
            flight = self.inflight.get(flight_key)
            owner = flight is None
            if owner:
                flight = self.inflight[flight_key] = Future()
        if not owner:
            return flight.result(), 'COALESCED'
        try:
            # Cold menus can otherwise build several large Python graphs and
            # JSON strings at once. Hits/coalesced requests never acquire this gate.
            with self.build_guard if self.build_guard is not None else nullcontext():
                body = json.dumps(build(), ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
            # Retain compact bytes instead of repeated 20MB policy responses.
            # Clients receive exactly the same uncompressed JSON bytes.
            packed = zlib.compress(body, 1) if len(body) >= 256 * 1024 else body
            compressed = len(packed) < len(body)
            if not compressed:packed = body
            if self.version() == version:
                with self.lock:
                    self.entries[key] = (version, monotonic(), packed, compressed)
                    self.entries.move_to_end(key)
                    while len(self.entries) > self.max_entries or sum(len(v[2]) for v in self.entries.values()) > self.max_bytes:
                        self.entries.popitem(last=False)
            flight.set_result(body)
            return body, 'MISS'
        except BaseException as error:
            flight.set_exception(error)
            raise
        finally:
            with self.lock:
                self.inflight.pop(flight_key, None)
