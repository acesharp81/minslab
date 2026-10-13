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


Index('ix_home_revision_recorded', Revision.recorded_at.desc())
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

# Latest-change checks run for every cached read.
Index('ix_home_audit_recorded', Audit.recorded_at.desc())
Index('ix_home_batch_finished', Batch.finished_at.desc())
