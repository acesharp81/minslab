"""HOME-owned database. Source revisions are immutable except supersession time."""
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Revision(Base):
    __tablename__ = "home_revision"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    entity_id: Mapped[str] = mapped_column(String(80), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    source_id: Mapped[str] = mapped_column(String(40), index=True)
    revision_no: Mapped[int] = mapped_column(Integer)
    previous_id: Mapped[str | None] = mapped_column(String(36))
    sample_base_date: Mapped[str | None] = mapped_column(String(10))
    sample_region: Mapped[str | None] = mapped_column(String(30))
    sample_name: Mapped[str | None] = mapped_column(Text)
    sample_source_date: Mapped[str | None] = mapped_column(String(10))
    sample_event_day: Mapped[str | None] = mapped_column(String(10))
    payload: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    batch_id: Mapped[str] = mapped_column(String(36))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index("ix_home_sample_order", Revision.kind, Revision.sample_region, Revision.sample_name, Revision.entity_id,
      postgresql_where=Revision.superseded_at.is_(None), sqlite_where=Revision.superseded_at.is_(None))
Index("ix_home_sample_dates", Revision.kind, Revision.sample_source_date, Revision.sample_event_day, Revision.sample_region,
      postgresql_where=Revision.superseded_at.is_(None), sqlite_where=Revision.superseded_at.is_(None))

Index("ix_home_sample_counts", Revision.kind, Revision.sample_source_date, Revision.sample_event_day, Revision.sample_region,
      postgresql_include=['recorded_at','sample_base_date'],
      postgresql_where=Revision.superseded_at.is_(None), sqlite_where=Revision.superseded_at.is_(None))

Index("uq_home_current", Revision.entity_id, unique=True,
      postgresql_where=Revision.superseded_at.is_(None), sqlite_where=Revision.superseded_at.is_(None))

# Per-source cumulative counts run after each incremental batch. Keep current
# source membership in one compact index instead of reading historical payloads.
Index("ix_home_current_source", Revision.source_id,
      postgresql_where=Revision.superseded_at.is_(None), sqlite_where=Revision.superseded_at.is_(None))

Index("ix_home_general_actual_start", Revision.payload['dates']['실제착공일 (realStcnsDay)'].as_string(),
      postgresql_where=(Revision.kind == 'general_permit') & Revision.superseded_at.is_(None),
      sqlite_where=(Revision.kind == 'general_permit') & Revision.superseded_at.is_(None))


class Batch(Base):
    __tablename__ = "home_batch"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(String(40), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="RUNNING")
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    manifest: Mapped[list] = mapped_column(JSON, default=list)


class Coverage(Base):
    """Verified query scope for one collection batch; never implies population coverage."""
    __tablename__ = "home_coverage"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    batch_id: Mapped[str] = mapped_column(String(36), index=True)
    source_id: Mapped[str] = mapped_column(String(40), index=True)
    endpoint: Mapped[str] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(30))
    area_code: Mapped[str | None] = mapped_column(String(20))
    source_period: Mapped[str | None] = mapped_column(String(30))
    expected_count: Mapped[int | None] = mapped_column(Integer)
    fetched_count: Mapped[int] = mapped_column(Integer)
    query_status: Mapped[str] = mapped_column(String(24))
    population_status: Mapped[str] = mapped_column(String(24), default="UNVERIFIED")
    scope_note: Mapped[str | None] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProjectIdentity(Base):
    """Stable candidate identity; official sameness requires review."""
    __tablename__ = "home_project"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    region: Mapped[str] = mapped_column(String(30))
    identity_status: Mapped[str] = mapped_column(String(24), default="REVIEW")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IdentityAlias(Base):
    __tablename__ = "home_identity_alias"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("home_project.id"), index=True)
    source_entity_id: Mapped[str] = mapped_column(String(80), unique=True)
    source_id: Mapped[str] = mapped_column(String(40))
    relation_status: Mapped[str] = mapped_column(String(24), default="REVIEW")
    match_rule: Mapped[str] = mapped_column(String(80))
    unit_comparison: Mapped[str | None] = mapped_column(String(24))
    basis: Mapped[str] = mapped_column(Text)
    evidence_revision_id: Mapped[str] = mapped_column(String(36))
    evidence_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectEvidence(Base):
    __tablename__ = "home_project_evidence"
    __table_args__ = (UniqueConstraint("project_id", "revision_id", name="uq_home_project_evidence_revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("home_project.id"), index=True)
    revision_id: Mapped[str] = mapped_column(String(36))
    evidence_role: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Plan(Base):
    __tablename__ = "home_plan"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    region: Mapped[str] = mapped_column(String(30))
    plan_type: Mapped[str] = mapped_column(String(40))
    legal_status: Mapped[str] = mapped_column(String(24), default="EVIDENCE_REVIEW")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PlanEvent(Base):
    __tablename__ = "home_plan_event"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    plan_id: Mapped[str] = mapped_column(String(32), ForeignKey("home_plan.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    notice_no: Mapped[str | None] = mapped_column(String(100))
    notice_date: Mapped[str | None] = mapped_column(String(10))
    evidence_url: Mapped[str] = mapped_column(Text)
    evidence_sha256: Mapped[str | None] = mapped_column(String(64))
    source_revision_id: Mapped[str | None] = mapped_column(String(36))
    verification_status: Mapped[str] = mapped_column(String(24), default="REVIEW")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PlanProjectLink(Base):
    __tablename__ = "home_plan_project_link"
    __table_args__ = (UniqueConstraint("plan_id", "project_id", name="uq_home_plan_project"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    plan_id: Mapped[str] = mapped_column(String(32), ForeignKey("home_plan.id"), index=True)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("home_project.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="REVIEW")
    basis: Mapped[str] = mapped_column(Text)
    evidence_url: Mapped[str] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Mapping(Base):
    __tablename__ = "home_mapping"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(String(80), unique=True)
    policy_id: Mapped[str] = mapped_column(String(80))  # legacy direct proposal / audit
    program_id: Mapped[str | None] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(24), default="REVIEW")
    revision_no: Mapped[int] = mapped_column(Integer, default=1)
    basis: Mapped[str] = mapped_column(Text)
    evidence_url: Mapped[str] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProgramMapping(Base):
    """A named programme cohort linked to one announced policy or left unassigned."""
    __tablename__ = "home_program_mapping"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    seed_policy_id: Mapped[str] = mapped_column(String(80))
    policy_id: Mapped[str] = mapped_column(String(80), default="UNASSIGNED")
    status: Mapped[str] = mapped_column(String(24), default="REVIEW")
    revision_no: Mapped[int] = mapped_column(Integer, default=1)
    basis: Mapped[str] = mapped_column(Text)
    evidence_url: Mapped[str] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Audit(Base):
    __tablename__ = "home_audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    entity_id: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(30))
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MetricSnapshot(Base):
    """Frozen inputs and results; new knowledge creates another snapshot."""
    __tablename__ = 'home_metric_snapshot'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    known_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    actor: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(Text)
    context: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    digest: Mapped[str] = mapped_column(String(64))


class IntegrityRound(Base):
    """Append-only scorecards retain the previous rubric and item comments."""
    __tablename__ = 'home_integrity_round'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, unique=True)
    parent_id: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    actor: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(Text)
    snapshot_id: Mapped[str | None] = mapped_column(String(80))
    score: Mapped[str] = mapped_column(String(20))
    result: Mapped[dict] = mapped_column(JSON)
    report_html: Mapped[str] = mapped_column(Text)
    digest: Mapped[str] = mapped_column(String(64))


class CollectionJob(Base):
    __tablename__ = 'home_collection_job'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(24), default='QUEUED', index=True)
    stage: Mapped[str] = mapped_column(String(24), default='COLLECT')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)


Index('uq_home_active_collection_job', CollectionJob.source_id, unique=True,
      postgresql_where=CollectionJob.status.in_(('QUEUED', 'RUNNING', 'RETRY')),
      sqlite_where=CollectionJob.status.in_(('QUEUED', 'RUNNING', 'RETRY')))


Index('ix_home_revision_recorded', Revision.recorded_at.desc())
Index('ix_home_revision_kind_recorded', Revision.kind, Revision.recorded_at.desc())
Index('ix_home_revision_entity_version', Revision.entity_id, Revision.revision_no.desc())
Index('ix_home_audit_entity_recorded', Audit.entity_id, Audit.recorded_at.desc())
Index('ix_home_batch_status_source_started', Batch.status, Batch.source_id, Batch.started_at.desc())


def engine_for(url=None):
    return create_engine(url or os.environ["POC10_DATABASE_URL"], pool_pre_ping=True)


def factory(engine):
    return sessionmaker(engine, expire_on_commit=False)


def entity_id(kind, source_id, key):
    return f"{kind[:3].upper()}_{hashlib.sha256(f'{source_id}:{key}'.encode()).hexdigest()[:24]}"


def upsert_revision(session, kind, source_id, key, payload, batch_id):
    eid = entity_id(kind, source_id, key)
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    old = session.scalar(select(Revision).where(Revision.entity_id == eid, Revision.superseded_at.is_(None)))
    if old and old.payload_hash == digest:
        return old, "unchanged"
    if old and kind == 'document_evidence' and source_id == 'lh_notice_detail':
        # Dynamic HTML changes raw hashes without changing extracted facts.
        # Keep the immutable evidence revision; each fetch remains in its batch
        # manifest/raw archive. Any other field change still creates a revision.
        ignored = {'original_file', 'original_sha256'}
        if ({k:v for k,v in old.payload.items() if k not in ignored} ==
                {k:v for k,v in payload.items() if k not in ignored}):
            return old, "unchanged"
    if old:
        old.superseded_at = now()
        session.flush()
    new = Revision(entity_id=eid, kind=kind, source_id=source_id, revision_no=old.revision_no + 1 if old else 1,
                   previous_id=old.id if old else None, payload=payload, payload_hash=digest, batch_id=batch_id,
                   sample_base_date=payload.get('base_date'),sample_region=payload.get('region'),sample_name=payload.get('name'),
                   sample_source_date=payload.get('source_date'),
                   sample_event_day=((payload.get('dates') or {}).get('원천 허가일 (apprvDay)') or payload.get('source_date')) if kind=='permit' else payload.get('source_date'))
    session.add(new)
    session.flush()
    return new, "changed" if old else "new"


def upsert_raw_revisions(session, source_id, records, batch_id, chunk_size=500):
    """Batch raw API revisions with the same hashes and history as single upserts.

    The caller owns the transaction. Duplicate keys retain sequential semantics;
    projects and records with per-row side effects must use upsert_revision.
    """
    allowed={'permit','general_permit','register','register_recap','permit_dong','permit_parcel'}
    if any(kind not in allowed for kind,_,_ in records):
        raise ValueError('원천 API 기록만 일괄 적재할 수 있습니다')
    keys=[entity_id(kind,source_id,key) for kind,key,_ in records]
    if len(keys)!=len(set(keys)):
        for kind,key,payload in records:
            yield upsert_revision(session,kind,source_id,key,payload,batch_id)
        return
    for offset in range(0,len(records),chunk_size):
        chunk=records[offset:offset+chunk_size];ids=keys[offset:offset+chunk_size]
        existing={r.entity_id:r for r in session.scalars(select(Revision).where(
            Revision.entity_id.in_(ids),Revision.superseded_at.is_(None)))}
        results=[];pending=[]
        for (kind,key,payload),eid in zip(chunk,ids):
            digest=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            old=existing.get(eid)
            if old and old.payload_hash==digest:
                results.append((old,'unchanged'));continue
            if old:old.superseded_at=now()
            row=Revision(entity_id=eid,kind=kind,source_id=source_id,revision_no=old.revision_no+1 if old else 1,
                previous_id=old.id if old else None,payload=payload,payload_hash=digest,batch_id=batch_id,
                sample_base_date=payload.get('base_date'),sample_region=payload.get('region'),sample_name=payload.get('name'),
                sample_source_date=payload.get('source_date'),
                sample_event_day=((payload.get('dates') or {}).get('원천 허가일 (apprvDay)') or payload.get('source_date')) if kind=='permit' else payload.get('source_date'))
            pending.append(row);results.append((row,'changed' if old else 'new'))
        # Retire previous versions before inserting their replacements, preserving
        # the unique current-version index. Both flushes remain in one transaction.
        session.flush()
        session.add_all(pending);session.flush()
        yield from results

# Latest-change checks run for every cached read.
Index('ix_home_audit_recorded', Audit.recorded_at.desc())
Index('ix_home_batch_finished', Batch.finished_at.desc())
