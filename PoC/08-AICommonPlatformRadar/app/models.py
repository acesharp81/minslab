from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Notice(Base):
    __tablename__ = "notices"
    __table_args__ = (
        UniqueConstraint("source", "stage", "notice_no", name="uq_notice_source_stage_no"),
        Index("ix_notice_posted_grade", "posted_at", "stage"),
        Index("ix_notices_created_at", "created_at"),
        Index("ix_notices_updated_at", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(30), default="g2b")
    stage: Mapped[str] = mapped_column(String(30))
    notice_no: Mapped[str] = mapped_column(String(120))
    bid_no: Mapped[str | None] = mapped_column(String(120), nullable=True)
    agency_name: Mapped[str] = mapped_column(String(300), default="")
    agency_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(1000))
    budget_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_type: Mapped[str] = mapped_column(String(50), default="service")
    raw_payload_json: Mapped[str] = mapped_column(Text, default="{}")
    collect_status: Mapped[str] = mapped_column(String(30), default="collected")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    attachments: Mapped[list["Attachment"]] = relationship(back_populates="notice", cascade="all, delete-orphan")
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(back_populates="notice", cascade="all, delete-orphan")
    decision: Mapped["NoticeDecision | None"] = relationship(back_populates="notice", cascade="all, delete-orphan", uselist=False)
    action: Mapped["ActionItem | None"] = relationship(back_populates="notice", cascade="all, delete-orphan", uselist=False)


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        UniqueConstraint("notice_id", "source_url", name="uq_attachment_notice_url"),
        Index("ix_attachment_sha256", "sha256"),
        Index("ix_attachments_updated_at", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    notice_id: Mapped[int] = mapped_column(ForeignKey("notices.id", ondelete="CASCADE"), index=True)
    original_filename: Mapped[str] = mapped_column(String(1000), default="")
    stored_filename: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_ext: Mapped[str | None] = mapped_column(String(20), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_url: Mapped[str] = mapped_column(Text)
    download_status: Mapped[str] = mapped_column(String(30), default="pending")
    download_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_status: Mapped[str] = mapped_column(String(30), default="pending")
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    notice: Mapped[Notice] = relationship(back_populates="attachments")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        Index("ix_analysis_notice_type", "notice_id", "run_type"),
        Index(
            "ix_analysis_notice_type_status_id",
            "notice_id", "run_type", "status", "id",
        ),
        Index(
            "ix_analysis_type_status_notice_id",
            "run_type", "status", "notice_id", "id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    notice_id: Mapped[int] = mapped_column(ForeignKey("notices.id", ondelete="CASCADE"), index=True)
    run_type: Mapped[str] = mapped_column(String(30))
    model_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30))
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    notice: Mapped[Notice] = relationship(back_populates="analysis_runs")


class NoticeDecision(Base):
    __tablename__ = "notice_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    notice_id: Mapped[int] = mapped_column(ForeignKey("notices.id", ondelete="CASCADE"), unique=True, index=True)
    final_grade: Mapped[str] = mapped_column(String(1), default="D", index=True)
    ai_relevance: Mapped[str] = mapped_column(String(20), default="low")
    common_platform_fit: Mapped[str] = mapped_column(String(20), default="uncertain")
    usage_mentioned: Mapped[str] = mapped_column(String(20), default="unclear")
    priority_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    recommended_action: Mapped[str] = mapped_column(String(30), default="manual_review")
    summary: Mapped[str] = mapped_column(Text, default="자료를 추가 확인해야 합니다.")
    possible_functions_json: Mapped[str] = mapped_column(Text, default="[]")
    key_evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    check_questions_json: Mapped[str] = mapped_column(Text, default="[]")
    caveats_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    notice: Mapped[Notice] = relationship(back_populates="decision")


class ActionItem(Base):
    __tablename__ = "action_items"
    __table_args__ = (Index("ix_action_items_updated_at", "updated_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    notice_id: Mapped[int] = mapped_column(ForeignKey("notices.id", ondelete="CASCADE"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    agency_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    saving_estimate: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    security_effect_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    notice: Mapped[Notice] = relationship(back_populates="action")


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_kind: Mapped[str] = mapped_column(String(40), index=True)
    mode: Mapped[str] = mapped_column(String(30), default="mock")
    status: Mapped[str] = mapped_column(String(30), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stats_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_event_id", "event_type", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    actor: Mapped[str] = mapped_column(String(200), default="system")
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
