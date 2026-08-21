"""AIWorks server boundary: plans, approvals, executions, audit, and HWPX intake."""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import io
import importlib.util
import json
import os
import re
import secrets
import selectors
import shutil
import sqlite3
import struct
import subprocess
import tempfile
import threading
import time
import uuid
import wave
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree
from urllib import error as url_error
from urllib import request as url_request


ROOT = Path(__file__).resolve().parent
DEFAULT_DB_PATH = ROOT / "data" / "aiworks.sqlite3"
DB_PATH = Path(os.getenv("AIWORKS_DB_PATH", str(DEFAULT_DB_PATH))).expanduser()
ENABLE_DEMO_SEED = os.getenv("AIWORKS_ENABLE_DEMO_SEED", "0").strip().lower() in {"1", "true", "yes", "on"}
TOKEN_TTL_SECONDS = max(60, min(3600, int(os.getenv("AIWORKS_APPROVAL_TTL_SECONDS", "600"))))
MAX_HWPX_BYTES = max(1_000_000, min(30_000_000, int(os.getenv("AIWORKS_MAX_HWPX_BYTES", "10000000"))))
MAX_UNCOMPRESSED_BYTES = 50_000_000
MAX_ASSET_BYTES = max(1_000_000, min(10_000_000, int(os.getenv("AIWORKS_MAX_ASSET_BYTES", "10000000"))))
_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


def _load_mcp_module(name: str, filename: str):
    path = ROOT / "mcp" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{filename} MCP를 불러오지 못했습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


INTENT_ANALYSIS_MCP = _load_mcp_module("aiworks_intent_analysis_mcp", "intent_analysis.py")
MODEL_MANAGEMENT_MCP = _load_mcp_module("aiworks_model_management_mcp", "model_management.py")
WORKSPACE_ORCHESTRATION_MCP = _load_mcp_module("aiworks_workspace_orchestration_mcp", "workspace_orchestration.py")
REWRITE_OUTPUT_MCP = _load_mcp_module("aiworks_rewrite_output_mcp", "rewrite_output.py")
REPORT_HWPX_MCP = _load_mcp_module("aiworks_report_hwpx_mcp", "report_hwpx.py")
REPORT_DOCUMENT_MCP = _load_mcp_module("aiworks_report_document_mcp", "report_document.py")
TEMPLATE_REPORT_STYLE_MCP = _load_mcp_module("aiworks_template_report_style_mcp", "template_report_style.py")
MOIS_REPORT_TEMPLATE_MCP = _load_mcp_module("aiworks_mois_report_template_mcp", "template_mois_report.py")
RHWP_AUTOMATION_MCP = _load_mcp_module("aiworks_rhwp_automation_mcp", "rhwp_automation.py")


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _secret() -> bytes:
    configured = os.getenv("AIWORKS_APPROVAL_SECRET", "").strip()
    if configured:
        return configured.encode("utf-8")
    fallback = f"aiworks-poc:{DB_PATH.resolve()}:{os.uname().nodename}"
    return hashlib.sha256(fallback.encode("utf-8")).digest()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        with _connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS plans (
                    id TEXT PRIMARY KEY,
                    intent TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    status TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    external_transfer INTEGER NOT NULL DEFAULT 0,
                    masked_fields_json TEXT NOT NULL,
                    required_permissions_json TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    document_context_json TEXT NOT NULL,
                    routing_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    nonce TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL REFERENCES plans(id),
                    actor TEXT NOT NULL,
                    permissions_json TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    consumed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS executions (
                    id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL REFERENCES plans(id),
                    status TEXT NOT NULL,
                    idempotency_key TEXT,
                    input_hash TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    queued_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    UNIQUE(plan_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    id TEXT PRIMARY KEY,
                    execution_id TEXT NOT NULL UNIQUE REFERENCES executions(id),
                    plan_id TEXT NOT NULL REFERENCES plans(id),
                    project_id TEXT,
                    status TEXT NOT NULL,
                    current_step_key TEXT,
                    input_json TEXT NOT NULL,
                    output_json TEXT NOT NULL,
                    checkpoint_json TEXT NOT NULL,
                    resumed_from_run_id TEXT,
                    resume_step_key TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS workflow_step_runs (
                    id TEXT PRIMARY KEY,
                    workflow_run_id TEXT NOT NULL REFERENCES workflow_runs(id),
                    step_key TEXT NOT NULL,
                    label TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    input_json TEXT NOT NULL,
                    output_json TEXT NOT NULL,
                    checkpoint_json TEXT NOT NULL,
                    error TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    UNIQUE(workflow_run_id, step_key, attempt)
                );
                CREATE INDEX IF NOT EXISTS workflow_step_runs_run_idx
                    ON workflow_step_runs(workflow_run_id, attempt, step_key);

                CREATE TABLE IF NOT EXISTS workflow_run_executions (
                    workflow_run_id TEXT NOT NULL REFERENCES workflow_runs(id),
                    execution_id TEXT NOT NULL UNIQUE REFERENCES executions(id),
                    plan_id TEXT NOT NULL REFERENCES plans(id),
                    attempt INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(workflow_run_id, attempt)
                );
                CREATE INDEX IF NOT EXISTS workflow_run_executions_run_idx
                    ON workflow_run_executions(workflow_run_id, attempt);

                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT,
                    plan_id TEXT,
                    actor TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS document_versions (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    artifact_sha256 TEXT NOT NULL,
                    patch_json TEXT NOT NULL,
                    execution_id TEXT,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspace_documents (
                    id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    name TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_members (
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    actor TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    invited_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(project_id, actor)
                );
                CREATE TABLE IF NOT EXISTS project_policies (
                    project_id TEXT PRIMARY KEY REFERENCES projects(id),
                    policy_json TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    updated_by TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS permission_grants (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    actor TEXT NOT NULL,
                    package_id TEXT NOT NULL,
                    version_range TEXT NOT NULL,
                    scopes_json TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    status TEXT NOT NULL,
                    granted_by TEXT NOT NULL,
                    expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_recipes (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    visibility TEXT NOT NULL,
                    status TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_recipe_versions (
                    id TEXT PRIMARY KEY,
                    recipe_id TEXT NOT NULL REFERENCES workflow_recipes(id),
                    version TEXT NOT NULL,
                    definition_json TEXT NOT NULL,
                    changelog TEXT,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(recipe_id, version)
                );
                CREATE TABLE IF NOT EXISTS workflow_recipe_installations (
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    recipe_id TEXT NOT NULL REFERENCES workflow_recipes(id),
                    version_id TEXT NOT NULL REFERENCES workflow_recipe_versions(id),
                    status TEXT NOT NULL,
                    installed_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(project_id, recipe_id)
                );
                CREATE TABLE IF NOT EXISTS project_workspace_states (
                    project_id TEXT PRIMARY KEY REFERENCES projects(id),
                    active_document_id TEXT,
                    active_tab TEXT NOT NULL,
                    active_view TEXT NOT NULL,
                    chat_json TEXT NOT NULL,
                    last_answer TEXT,
                    updated_by TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_facts (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    fact_key TEXT NOT NULL,
                    label TEXT NOT NULL,
                    value_type TEXT NOT NULL,
                    unit TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_id, fact_key)
                );
                CREATE TABLE IF NOT EXISTS project_fact_values (
                    id TEXT PRIMARY KEY,
                    fact_id TEXT NOT NULL REFERENCES project_facts(id),
                    value_json TEXT NOT NULL,
                    effective_date TEXT,
                    status TEXT NOT NULL,
                    source_document_id TEXT,
                    source_locator TEXT,
                    source_excerpt TEXT,
                    confidence REAL NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS report_fact_snapshots (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    plan_id TEXT,
                    execution_id TEXT,
                    artifact_filename TEXT NOT NULL,
                    facts_json TEXT NOT NULL,
                    report_document_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_markdown_documents (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    title TEXT NOT NULL,
                    current_revision INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_markdown_versions (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES project_markdown_documents(id),
                    revision INTEGER NOT NULL,
                    markdown TEXT NOT NULL,
                    markdown_sha256 TEXT NOT NULL,
                    source_format TEXT NOT NULL,
                    source_filename TEXT,
                    source_artifact_sha256 TEXT,
                    source_session_id TEXT,
                    fact_snapshot_json TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(document_id, revision)
                );
                CREATE TABLE IF NOT EXISTS project_document_artifacts (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES project_markdown_documents(id),
                    format TEXT NOT NULL,
                    variant_key TEXT NOT NULL,
                    source_version_id TEXT REFERENCES project_markdown_versions(id),
                    source_revision INTEGER,
                    source_markdown_sha256 TEXT,
                    status TEXT NOT NULL,
                    filename TEXT,
                    media_type TEXT,
                    content_blob BLOB,
                    artifact_sha256 TEXT,
                    template_id TEXT,
                    renderer TEXT,
                    instruction TEXT,
                    render_map_json TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(document_id, format, variant_key)
                );
                CREATE TABLE IF NOT EXISTS project_document_sync_events (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    document_id TEXT NOT NULL REFERENCES project_markdown_documents(id),
                    artifact_id TEXT,
                    event_type TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_version_id TEXT,
                    target_version_id TEXT,
                    detail_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_document_conflicts (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    document_id TEXT NOT NULL REFERENCES project_markdown_documents(id),
                    artifact_id TEXT REFERENCES project_document_artifacts(id),
                    conflict_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    base_version_id TEXT,
                    current_version_id TEXT,
                    source_json TEXT NOT NULL,
                    target_json TEXT NOT NULL,
                    render_map_json TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    resolution_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );
                CREATE INDEX IF NOT EXISTS project_document_conflicts_open_idx
                    ON project_document_conflicts(document_id, status, created_at);

                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    artifact_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_version_id TEXT,
                    source_type TEXT,
                    source_id TEXT,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_id, source_type, source_id)
                );
                CREATE TABLE IF NOT EXISTS artifact_versions (
                    id TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL REFERENCES artifacts(id),
                    version INTEGER NOT NULL,
                    media_type TEXT NOT NULL,
                    filename TEXT,
                    content_blob BLOB,
                    content_json TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    workflow_run_id TEXT,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(artifact_id, version),
                    UNIQUE(artifact_id, content_sha256)
                );
                CREATE TABLE IF NOT EXISTS artifact_relations (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    source_version_id TEXT NOT NULL REFERENCES artifact_versions(id),
                    target_version_id TEXT NOT NULL REFERENCES artifact_versions(id),
                    relation TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(source_version_id, target_version_id, relation)
                );
                CREATE TABLE IF NOT EXISTS artifact_evidence (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    artifact_id TEXT NOT NULL REFERENCES artifacts(id),
                    artifact_version_id TEXT REFERENCES artifact_versions(id),
                    source_artifact_id TEXT REFERENCES artifacts(id),
                    source_version_id TEXT REFERENCES artifact_versions(id),
                    locator TEXT NOT NULL,
                    excerpt TEXT NOT NULL,
                    excerpt_sha256 TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mcp_packages (
                    package_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    bundle_sha256 TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    publisher TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    PRIMARY KEY(package_id, version)
                );
                CREATE TABLE IF NOT EXISTS mcp_installations (
                    package_id TEXT PRIMARY KEY,
                    pinned_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    installed_by TEXT NOT NULL,
                    installed_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mcp_install_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    package_id TEXT NOT NULL,
                    from_version TEXT,
                    to_version TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mcp_configurations (
                    package_id TEXT PRIMARY KEY,
                    values_json TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    updated_by TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_nodes (
                    id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_sources (
                    id TEXT PRIMARY KEY,
                    node_id TEXT NOT NULL REFERENCES knowledge_nodes(id),
                    document_id TEXT NOT NULL,
                    locator TEXT NOT NULL,
                    excerpt TEXT NOT NULL,
                    effective_date TEXT,
                    confidence REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_edges (
                    id TEXT PRIMARY KEY,
                    source_node_id TEXT NOT NULL REFERENCES knowledge_nodes(id),
                    target_node_id TEXT NOT NULL REFERENCES knowledge_nodes(id),
                    relation TEXT NOT NULL,
                    weight REAL NOT NULL,
                    evidence_source_id TEXT REFERENCES knowledge_sources(id),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS acceptance_runs (
                    id TEXT PRIMARY KEY,
                    scenario TEXT NOT NULL,
                    status TEXT NOT NULL,
                    checks_json TEXT NOT NULL,
                    artifacts_json TEXT NOT NULL,
                    error TEXT,
                    actor TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mcp_drafts (
                    id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    status TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    validation_json TEXT NOT NULL,
                    published_package_id TEXT,
                    published_version TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mcp_draft_references (
                    id TEXT PRIMARY KEY,
                    draft_id TEXT NOT NULL REFERENCES mcp_drafts(id),
                    filename TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    content_blob BLOB NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mcp_package_files (
                    package_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    reference_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    content_blob BLOB NOT NULL,
                    PRIMARY KEY(package_id, version, reference_id),
                    FOREIGN KEY(package_id, version) REFERENCES mcp_packages(package_id, version)
                );
                CREATE TABLE IF NOT EXISTS mcp_capabilities (
                    package_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    capability_id TEXT NOT NULL,
                    mcp_type TEXT NOT NULL,
                    execution_adapter TEXT NOT NULL,
                    search_text TEXT NOT NULL,
                    trigger_examples_json TEXT NOT NULL,
                    indexed_at TEXT NOT NULL,
                    PRIMARY KEY(package_id, version, capability_id),
                    FOREIGN KEY(package_id, version) REFERENCES mcp_packages(package_id, version)
                );
                CREATE TABLE IF NOT EXISTS mcp_reference_chunks (
                    package_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    reference_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    page_number INTEGER,
                    content TEXT NOT NULL,
                    search_text TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    PRIMARY KEY(package_id, version, reference_id, chunk_index),
                    FOREIGN KEY(package_id, version) REFERENCES mcp_packages(package_id, version)
                );
                CREATE TABLE IF NOT EXISTS mcp_evaluations (
                    package_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    quality REAL NOT NULL,
                    success_rate REAL NOT NULL,
                    latency_ms REAL NOT NULL,
                    cost_per_run REAL NOT NULL,
                    sample_count INTEGER NOT NULL,
                    notes TEXT,
                    updated_by TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(package_id, version),
                    FOREIGN KEY(package_id, version) REFERENCES mcp_packages(package_id, version)
                );
                CREATE TABLE IF NOT EXISTS native_document_sessions (
                    id TEXT PRIMARY KEY,
                    actor TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    format TEXT NOT NULL,
                    adapter_id TEXT NOT NULL,
                    runtime TEXT NOT NULL,
                    status TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    intent_json TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    artifact_blob BLOB NOT NULL,
                    artifact_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(id DESC);
                CREATE INDEX IF NOT EXISTS idx_execution_plan ON executions(plan_id, queued_at DESC);
                CREATE INDEX IF NOT EXISTS idx_document_version ON document_versions(document_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_workspace_document_owner ON workspace_documents(owner, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_project_fact_project ON project_facts(project_id, fact_key);
                CREATE INDEX IF NOT EXISTS idx_project_member_actor ON project_members(actor, status, project_id);
                CREATE INDEX IF NOT EXISTS idx_permission_grant_project ON permission_grants(project_id, actor, status);
                CREATE INDEX IF NOT EXISTS idx_project_fact_value_fact ON project_fact_values(fact_id, effective_date DESC, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_recipe_visibility ON workflow_recipes(status, visibility, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_recipe_version_recipe ON workflow_recipe_versions(recipe_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_recipe_install_project ON workflow_recipe_installations(project_id, status);
                CREATE INDEX IF NOT EXISTS idx_report_fact_snapshot_project ON report_fact_snapshots(project_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_project_markdown_project ON project_markdown_documents(project_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_project_markdown_version ON project_markdown_versions(document_id, revision DESC);
                CREATE INDEX IF NOT EXISTS idx_artifact_project ON artifacts(project_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_artifact_version_artifact ON artifact_versions(artifact_id, version DESC);
                CREATE INDEX IF NOT EXISTS idx_artifact_relation_project ON artifact_relations(project_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_artifact_evidence_project ON artifact_evidence(project_id, artifact_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_project_artifact_document ON project_document_artifacts(document_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_project_sync_document ON project_document_sync_events(document_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_mcp_history ON mcp_install_history(package_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_mcp_configuration_updated ON mcp_configurations(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_knowledge_source_node ON knowledge_sources(node_id);
                CREATE INDEX IF NOT EXISTS idx_knowledge_edge_source ON knowledge_edges(source_node_id);
                CREATE INDEX IF NOT EXISTS idx_acceptance_completed ON acceptance_runs(completed_at DESC);
                CREATE INDEX IF NOT EXISTS idx_mcp_draft_owner ON mcp_drafts(owner, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_mcp_draft_reference ON mcp_draft_references(draft_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_mcp_capability_search ON mcp_capabilities(capability_id, mcp_type);
                CREATE INDEX IF NOT EXISTS idx_mcp_reference_chunk_package ON mcp_reference_chunks(package_id, version);
                CREATE INDEX IF NOT EXISTS idx_native_document_session_actor ON native_document_sessions(actor, updated_at DESC);
                """
            )
            plan_columns = {row["name"] for row in db.execute("PRAGMA table_info(plans)")}
            if "routing_json" not in plan_columns:
                db.execute("ALTER TABLE plans ADD COLUMN routing_json TEXT NOT NULL DEFAULT '{}'")
            workflow_run_columns = {row["name"] for row in db.execute("PRAGMA table_info(workflow_runs)")}
            if "resumed_from_run_id" not in workflow_run_columns:
                db.execute("ALTER TABLE workflow_runs ADD COLUMN resumed_from_run_id TEXT")
            if "resume_step_key" not in workflow_run_columns:
                db.execute("ALTER TABLE workflow_runs ADD COLUMN resume_step_key TEXT")
            document_version_columns = {row["name"] for row in db.execute("PRAGMA table_info(document_versions)")}
            if "content_blob" not in document_version_columns:
                db.execute("ALTER TABLE document_versions ADD COLUMN content_blob BLOB")
            native_session_columns = {row["name"] for row in db.execute("PRAGMA table_info(native_document_sessions)")}
            if "project_id" not in native_session_columns:
                db.execute("ALTER TABLE native_document_sessions ADD COLUMN project_id TEXT")
            if "markdown_document_id" not in native_session_columns:
                db.execute("ALTER TABLE native_document_sessions ADD COLUMN markdown_document_id TEXT")
            if "project_artifact_id" not in native_session_columns:
                db.execute("ALTER TABLE native_document_sessions ADD COLUMN project_artifact_id TEXT")
            if "markdown_base_revision" not in native_session_columns:
                db.execute("ALTER TABLE native_document_sessions ADD COLUMN markdown_base_revision INTEGER")
            _seed_mcp_store(db)
            for package_row in db.execute("SELECT manifest_json FROM mcp_packages").fetchall():
                _index_package_capabilities(db, _load_json(package_row["manifest_json"], {}))
            if ENABLE_DEMO_SEED:
                _seed_knowledge(db)
            _seed_default_project_facts(db)
            now = utc_now()
            db.execute(
                """
                INSERT OR IGNORE INTO project_members(project_id,actor,role,status,invited_by,created_at,updated_at)
                SELECT id,owner,'owner','active',owner,?,? FROM projects
                """,
                (now, now),
            )
        _SCHEMA_READY = True


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _load_json(value, fallback):
    try:
        return json.loads(value) if value else fallback
    except (TypeError, json.JSONDecodeError):
        return fallback


def _audit(
    db: sqlite3.Connection,
    actor: str,
    event_type: str,
    detail: dict,
    *,
    plan_id: str | None = None,
    execution_id: str | None = None,
) -> None:
    db.execute(
        "INSERT INTO audit_events(execution_id, plan_id, actor, event_type, detail_json, created_at) VALUES(?,?,?,?,?,?)",
        (execution_id, plan_id, actor, event_type, _json(detail), utc_now()),
    )


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign_claims(claims: dict) -> str:
    payload = _b64encode(_json(claims).encode("utf-8"))
    signature = _b64encode(hmac.new(_secret(), payload.encode("ascii"), hashlib.sha256).digest())
    return payload + "." + signature


def _verify_token(token: str) -> dict:
    try:
        payload, signature = str(token or "").split(".", 1)
        expected = _b64encode(hmac.new(_secret(), payload.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ApiError("승인 토큰 서명이 올바르지 않습니다.", 403)
        claims = json.loads(_b64decode(payload).decode("utf-8"))
    except ApiError:
        raise
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ApiError("승인 토큰 형식이 올바르지 않습니다.", 403) from error
    if int(claims.get("exp", 0)) < int(time.time()):
        raise ApiError("승인 토큰이 만료되었습니다. 다시 승인해 주세요.", 403)
    return claims


def _actor(payload: dict) -> str:
    value = str(payload.get("actor") or "workspace-user").strip()
    return value[:80] or "workspace-user"


STORE_KEY_ID = "aiworks-org-store-v1"
STORE_SIGNATURE_ALGORITHM = "HMAC-SHA256"
STORE_PERMISSION_SCOPES = {
    "document.read",
    "document.write",
    "common-data.read",
    "common-data.write",
    "network.send",
    "model.invoke",
}

MCP_BUILDER_TYPES = {
    "template": {
        "label": "양식 MCP",
        "capabilities": ["document.template.apply", "artifact.transform"],
        "referenceRoles": ["template-source", "sample-input", "guide"],
    },
    "process": {
        "label": "처리 MCP",
        "capabilities": ["workflow.execute", "artifact.process"],
        "referenceRoles": ["guide", "sample-input", "sample-output"],
    },
    "data": {
        "label": "데이터 MCP",
        "capabilities": ["data.query", "data.normalize"],
        "referenceRoles": ["data-source", "data-schema", "guide", "sample-output"],
    },
    "tool": {
        "label": "일반 도구 MCP",
        "capabilities": ["tool.invoke"],
        "referenceRoles": ["guide", "sample-input", "sample-output"],
    },
    "external": {
        "label": "외부 MCP 연결",
        "capabilities": ["external.tool.invoke"],
        "referenceRoles": ["guide", "sample-input", "sample-output"],
    },
}

PROTECTED_STORE_PUBLISHERS = {"AIWorks Core", "업무자동화팀", "공개 MCP", "Knowledge Lab", "Security Lab"}

KORDOC_PROFILE_ID = "kordoc@4.7.3"
EXTERNAL_MCP_SERVER_PROFILES = {
    KORDOC_PROFILE_ID: {
        "id": KORDOC_PROFILE_ID,
        "name": "KODAK (kordoc)",
        "transport": "stdio",
        "package": "kordoc",
        "version": "4.7.3",
        "binary": ROOT / "vendor" / "kordoc-runtime" / "node_modules" / ".bin" / "kordoc",
        "args": ["mcp"],
        "offline": True,
        "allowedTools": {
            "generate_document": "markdown-output-hwpx",
        },
        "capabilities": ["document.hwpx.finalize"],
        "homepage": "https://github.com/chrisryugj/kordoc",
    },
}


def _external_profile_status(profile_id: str) -> dict:
    profile = EXTERNAL_MCP_SERVER_PROFILES.get(profile_id)
    if not profile:
        return {"id": profile_id, "available": False, "reason": "profile-not-approved"}
    binary = Path(profile["binary"])
    node = next((str(path) for path in (Path("/usr/bin/node"), Path("/usr/local/bin/node"), Path("/usr/bin/nodejs")) if path.is_file()), None) or shutil.which("node") or shutil.which("nodejs")
    available = binary.is_file() and bool(node)
    return {
        "id": profile_id,
        "name": profile["name"],
        "transport": profile["transport"],
        "version": profile["version"],
        "available": available,
        "binary": str(binary),
        "node": node,
        "offline": bool(profile.get("offline")),
        "reason": "ready" if available else ("node-not-installed" if not node else "profile-runtime-not-installed"),
    }


def _store_secret() -> bytes:
    configured = os.getenv("AIWORKS_STORE_SIGNING_SECRET", "").strip()
    if configured:
        return configured.encode("utf-8")
    return hmac.new(_secret(), b"aiworks-org-store-v1", hashlib.sha256).digest()


def _package_manifest(
    package_id: str,
    name: str,
    version: str,
    runtime: str,
    description: str,
    permissions: list[tuple[str, str]],
    *,
    dependencies: list[str] | None = None,
    supports: list[str] | None = None,
) -> dict:
    return {
        "id": package_id,
        "name": name,
        "version": version,
        "runtime": runtime,
        "description": description,
        "inputs": {"request": {"type": "object"}},
        "outputs": {"result": {"type": "object"}},
        "permissions": [
            {"scope": scope, "reason": reason, "required": True}
            for scope, reason in permissions
        ],
        "supports": supports or [],
        "dependencies": dependencies or [],
        "visibility": "organization",
        "sourceIncluded": False,
    }


def _kordoc_adapter_manifest() -> dict:
    manifest = _package_manifest(
        "integration.kordoc",
        "KODAK 한글 문서 변환",
        "1.0.0",
        "local",
        "공개 kordoc MCP를 로컬 stdio로 실행하여 보고서 Markdown을 정부 보고서 서식의 HWPX로 생성합니다.",
        [("document.read", "현재 보고서 내용을 로컬 변환 입력으로 읽기"), ("document.write", "생성된 HWPX를 새 문서 revision으로 저장")],
        dependencies=["document.hwpx@1.2.0"],
        supports=[".hwpx", ".md"],
    )
    manifest.update(
        {
            "mcpType": "external",
            "capabilities": ["document.hwpx.finalize"],
            "builderGuide": {
                "version": "1.0",
                "instructions": "보고서의 제목과 본문을 Markdown으로 정규화한 뒤 kordoc generate_document 도구로 정부 보고서 HWPX를 생성합니다.",
                "cautions": ["KORDOC_OFFLINE=1로 실행합니다.", "작업별 임시 디렉터리 밖의 파일은 접근시키지 않습니다.", "생성 결과가 유효한 HWPX가 아니면 기존 보고서를 유지합니다."],
                "procedure": ["로컬 kordoc 런타임과 tools/list를 확인한다.", "현재 보고서를 Markdown으로 정규화한다.", "generate_document를 보고서 프리셋으로 실행한다.", "생성 HWPX 무결성을 확인하고 RHWP에서 연다."],
                "triggerExamples": ["이 보고서를 제대로 서식이 적용된 한글 문서로 만들어줘", "KODAK으로 HWPX를 변환해줘"],
                "dataSource": "공개 kordoc 4.7.3 · 로컬 stdio · 오프라인 제한",
                "useModel": False,
                "referenceRoles": MCP_BUILDER_TYPES["external"]["referenceRoles"],
            },
            "executionAdapter": {"kind": "external-mcp", "version": "1.0", "entrypoint": "external.tools.call", "arbitraryCode": False},
            "externalMcp": {
                "contractVersion": "2025-03-26",
                "transport": "stdio",
                "serverProfile": KORDOC_PROFILE_ID,
                "toolName": "generate_document",
                "invocationAdapter": "markdown-output-hwpx",
                "preset": "보고서",
                "documentTransfer": False,
            },
        }
    )
    return manifest


def _store_catalog() -> list[tuple[dict, str]]:
    catalog = [
        (INTENT_ANALYSIS_MCP.MANIFEST, "AIWorks Core"),
        (_package_manifest("document.hwpx", "HWPX 문서 어댑터", "1.2.0", "local", "HWPX 문단을 안전하게 읽고 변경합니다.", [("document.read", "문서 구조 분석"), ("document.write", "승인된 patch 적용")], supports=[".hwpx"]), "AIWorks Core"),
        (RHWP_AUTOMATION_MCP.MANIFEST, "AIWorks Core"),
        (_package_manifest("common-data.registry", "공통데이터 레지스트리", "1.1.0", "local", "기준일·출처·신뢰도를 포함한 업무 값을 관리합니다.", [("common-data.read", "현재 값 조회"), ("common-data.write", "승인된 값 저장")]), "AIWorks Core"),
        (_package_manifest("citation.linker", "출처·인용 연결기", "0.9.4", "local", "생성 문장과 근거 문서 위치를 연결합니다.", [("document.read", "원문 위치 연결")]), "Knowledge Lab"),
        (_package_manifest("privacy.mask", "개인정보 마스킹", "1.4.1", "local", "외부 실행 전 개인정보를 탐지하고 마스킹합니다.", [("document.read", "개인정보 탐지")]), "Security Lab"),
        (_package_manifest("document.rewrite", "공문체 변경기", "1.0.0", "hybrid", "선택 문장을 공문체 변경안으로 생성합니다.", [("document.read", "선택 문장 읽기"), ("model.invoke", "문체 변경 모델 호출"), ("network.send", "승인된 선택 문장 전송")]), "AIWorks Core"),
        (_kordoc_adapter_manifest(), "공개 MCP"),
    ]
    if ENABLE_DEMO_SEED:
        catalog.extend([
            (_package_manifest("budget.form", "예산요청서 양식", "1.0.2", "local", "예산요청서 구조와 필수 항목을 검증합니다.", [("common-data.read", "예산 기준값 확인"), ("document.write", "예산 변경안 생성")]), "업무자동화팀"),
            (_package_manifest("budget.form", "예산요청서 양식", "1.0.3", "local", "예산요청서 구조와 필수 항목을 검증하고 초안을 생성합니다.", [("common-data.read", "예산 기준값 확인"), ("document.write", "예산 변경안 생성")]), "업무자동화팀"),
            (_package_manifest("budget.form", "예산요청서 양식", "1.0.4", "local", "예산요청서 초안 생성과 금액 형식 검증을 강화합니다.", [("common-data.read", "예산 기준값 확인"), ("document.write", "예산 변경안 생성")]), "업무자동화팀"),
            (_package_manifest("sw-cost", "SW 대가산정", "2.0.0", "hybrid", "SW사업 대가 기준으로 산출 근거를 계산합니다.", [("common-data.read", "대가 기준 조회"), ("network.send", "공개 기준 갱신")]), "공개 MCP"),
            (_package_manifest("sw-cost", "SW 대가산정", "2.1.0", "hybrid", "최신 SW사업 대가 기준과 검증 규칙을 적용합니다.", [("common-data.read", "대가 기준 조회"), ("network.send", "공개 기준 갱신")]), "공개 MCP"),
        ])
    return catalog


def _bundle_sha256(manifest: dict) -> str:
    descriptor = b"AIWORKS-MCP-BUNDLE-V1\0" + _json(manifest).encode("utf-8")
    return hashlib.sha256(descriptor).hexdigest()


def _package_signature(package_id: str, version: str, bundle_sha256: str) -> str:
    signed = _json(
        {"bundleSha256": bundle_sha256, "keyId": STORE_KEY_ID, "packageId": package_id, "version": version}
    ).encode("utf-8")
    return _b64encode(hmac.new(_store_secret(), signed, hashlib.sha256).digest())


def _seed_mcp_store(db: sqlite3.Connection) -> None:
    published_at = "2026-08-11T00:00:00.000Z"
    for manifest, publisher in _store_catalog():
        digest = _bundle_sha256(manifest)
        signature = _package_signature(manifest["id"], manifest["version"], digest)
        db.execute(
            """
            INSERT OR IGNORE INTO mcp_packages(
                package_id, version, manifest_json, bundle_sha256,
                signature, publisher, published_at
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (manifest["id"], manifest["version"], _json(manifest), digest, signature, publisher, published_at),
        )
    if db.execute("SELECT COUNT(*) AS count FROM mcp_installations").fetchone()["count"] == 0:
        now = utc_now()
        bootstrap_packages = [("document.hwpx", "1.2.0"), ("common-data.registry", "1.1.0")]
        if ENABLE_DEMO_SEED:
            bootstrap_packages.append(("budget.form", "1.0.3"))
        for package_id, version in bootstrap_packages:
            db.execute(
                "INSERT INTO mcp_installations(package_id,pinned_version,status,installed_by,installed_at,updated_at) VALUES(?,?,?,?,?,?)",
                (package_id, version, "active", "system-bootstrap", now, now),
            )
            db.execute(
                "INSERT INTO mcp_install_history(package_id,from_version,to_version,action,actor,created_at) VALUES(?,?,?,?,?,?)",
                (package_id, None, version, "bootstrap", "system-bootstrap", now),
            )
    if not db.execute("SELECT 1 FROM mcp_installations WHERE package_id='document.rhwp'").fetchone():
        now = utc_now()
        db.execute(
            "INSERT INTO mcp_installations(package_id,pinned_version,status,installed_by,installed_at,updated_at) VALUES(?,?,?,?,?,?)",
            ("document.rhwp", "1.0.0", "active", "system-bootstrap", now, now),
        )
        db.execute(
            "INSERT INTO mcp_install_history(package_id,from_version,to_version,action,actor,created_at) VALUES(?,?,?,?,?,?)",
            ("document.rhwp", None, "1.0.0", "bootstrap", "system-bootstrap", now),
        )
    if not db.execute("SELECT 1 FROM mcp_installations WHERE package_id='integration.kordoc'").fetchone():
        now = utc_now()
        db.execute(
            "INSERT INTO mcp_installations(package_id,pinned_version,status,installed_by,installed_at,updated_at) VALUES(?,?,?,?,?,?)",
            ("integration.kordoc", "1.0.0", "active", "system-bootstrap", now, now),
        )
        db.execute(
            "INSERT INTO mcp_install_history(package_id,from_version,to_version,action,actor,created_at) VALUES(?,?,?,?,?,?)",
            ("integration.kordoc", None, "1.0.0", "bootstrap", "system-bootstrap", now),
        )
    if not db.execute("SELECT 1 FROM mcp_installations WHERE package_id='core.intent-analysis'").fetchone():
        now = utc_now()
        db.execute(
            "INSERT INTO mcp_installations(package_id,pinned_version,status,installed_by,installed_at,updated_at) VALUES(?,?,?,?,?,?)",
            ("core.intent-analysis", "0.1.0", "active", "system-bootstrap", now, now),
        )
        db.execute(
            "INSERT INTO mcp_install_history(package_id,from_version,to_version,action,actor,created_at) VALUES(?,?,?,?,?,?)",
            ("core.intent-analysis", None, "0.1.0", "bootstrap", "system-bootstrap", now),
        )


def _configuration_contract(manifest: dict) -> dict | None:
    contract = manifest.get("configuration")
    if contract is None:
        return None
    if not isinstance(contract, dict) or not isinstance(contract.get("properties"), dict):
        raise ApiError("MCP 환경설정 Schema가 올바르지 않습니다.")
    properties = contract["properties"]
    if not properties or len(properties) > 30:
        raise ApiError("MCP 환경설정 항목은 1개 이상 30개 이하여야 합니다.")
    required = contract.get("required") or []
    if not isinstance(required, list) or not set(required).issubset(properties):
        raise ApiError("MCP 필수 환경설정 항목이 Schema와 일치하지 않습니다.")
    for key, field in properties.items():
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{1,79}", str(key)) or not isinstance(field, dict):
            raise ApiError("MCP 환경설정 키가 올바르지 않습니다.")
        if field.get("type") not in {"string", "boolean", "integer", "number"}:
            raise ApiError("지원하지 않는 MCP 환경설정 타입입니다.")
        if not str(field.get("title") or "").strip():
            raise ApiError("MCP 환경설정에는 표시 이름이 필요합니다.")
        choices = field.get("enum")
        if choices is not None and (not isinstance(choices, list) or not choices or len(choices) > 50):
            raise ApiError("MCP 환경설정 선택값이 올바르지 않습니다.")
    return contract


def _normalize_configuration_values(contract: dict, values: dict) -> dict:
    if not isinstance(values, dict):
        raise ApiError("MCP 환경설정 값은 객체여야 합니다.")
    properties = contract["properties"]
    unknown = sorted(set(values) - set(properties))
    if unknown:
        raise ApiError("Manifest에 없는 환경설정 항목입니다: " + ", ".join(unknown))
    normalized = {}
    for key, field in properties.items():
        value = values[key] if key in values else field.get("default")
        if value is None:
            if key in (contract.get("required") or []):
                raise ApiError("필수 MCP 환경설정 값이 필요합니다: " + key)
            continue
        field_type = field["type"]
        valid = (
            (field_type == "string" and isinstance(value, str))
            or (field_type == "boolean" and isinstance(value, bool))
            or (field_type == "integer" and isinstance(value, int) and not isinstance(value, bool))
            or (field_type == "number" and isinstance(value, (int, float)) and not isinstance(value, bool))
        )
        if not valid:
            raise ApiError("MCP 환경설정 값의 타입이 올바르지 않습니다: " + key)
        if isinstance(value, str) and len(value) > int(field.get("maxLength") or 5_000):
            raise ApiError("MCP 환경설정 문자열이 너무 깁니다: " + key)
        if field.get("enum") is not None and value not in field["enum"]:
            raise ApiError("허용되지 않은 MCP 환경설정 값입니다: " + key)
        if field_type in {"integer", "number"}:
            if field.get("minimum") is not None and value < field["minimum"]:
                raise ApiError("MCP 환경설정 최솟값보다 작습니다: " + key)
            if field.get("maximum") is not None and value > field["maximum"]:
                raise ApiError("MCP 환경설정 최댓값보다 큽니다: " + key)
        normalized[key] = value
    return normalized


def _runtime_mcp_configuration(package_id: str, fallback_manifest: dict | None = None) -> dict:
    manifest = fallback_manifest or {}
    stored = {}
    with _connect() as db:
        installation = db.execute("SELECT pinned_version FROM mcp_installations WHERE package_id=? AND status='active'", (package_id,)).fetchone()
        if installation:
            package = db.execute("SELECT manifest_json FROM mcp_packages WHERE package_id=? AND version=?", (package_id, installation["pinned_version"])).fetchone()
            if package:
                manifest = _load_json(package["manifest_json"], manifest)
        row = db.execute("SELECT values_json FROM mcp_configurations WHERE package_id=?", (package_id,)).fetchone()
        if row:
            stored = _load_json(row["values_json"], {})
    contract = _configuration_contract(manifest)
    return _normalize_configuration_values(contract, stored) if contract else {}


def _validate_manifest(manifest: dict, package_id: str, version: str) -> None:
    if manifest.get("id") != package_id or manifest.get("version") != version:
        raise ApiError("패키지와 Manifest 식별자가 일치하지 않습니다.", 409)
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ApiError("MCP 버전은 정확한 SemVer로 고정해야 합니다.")
    if manifest.get("runtime") not in {"local", "remote", "hybrid"}:
        raise ApiError("지원하지 않는 MCP 런타임입니다.")
    if not isinstance(manifest.get("inputs"), dict) or not isinstance(manifest.get("outputs"), dict):
        raise ApiError("MCP 입출력 Schema가 필요합니다.")
    permissions = manifest.get("permissions")
    if not isinstance(permissions, list):
        raise ApiError("MCP 권한 선언이 필요합니다.")
    for permission in permissions:
        if not isinstance(permission, dict) or permission.get("scope") not in STORE_PERMISSION_SCOPES:
            raise ApiError("MCP에 허용되지 않은 권한 범위가 포함되어 있습니다.", 403)
    contract = _configuration_contract(manifest)
    if contract:
        _normalize_configuration_values(contract, {})


def _verified_package(row: sqlite3.Row) -> dict:
    manifest = _load_json(row["manifest_json"], {})
    _validate_manifest(manifest, row["package_id"], row["version"])
    findings = []
    for dependency in manifest.get("dependencies", []):
        if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*@\d+\.\d+\.\d+", str(dependency)):
            findings.append({"severity": "high", "code": "dependency.not-pinned", "dependency": dependency})
    if findings:
        raise ApiError("고정되지 않은 MCP 의존성이 포함되어 설치를 차단했습니다.", 409)
    calculated_digest = _bundle_sha256(manifest)
    expected_signature = _package_signature(row["package_id"], row["version"], row["bundle_sha256"])
    if not hmac.compare_digest(calculated_digest, row["bundle_sha256"]):
        raise ApiError("MCP 패키지 해시 검증에 실패했습니다.", 409)
    if not hmac.compare_digest(expected_signature, row["signature"]):
        raise ApiError("MCP 패키지 서명 검증에 실패했습니다.", 403)
    included_files = []
    with _connect() as db:
        file_rows = db.execute(
            "SELECT * FROM mcp_package_files WHERE package_id=? AND version=? ORDER BY reference_id",
            (row["package_id"], row["version"]),
        ).fetchall()
    expected_references = manifest.get("references") or []
    if manifest.get("sourceIncluded"):
        expected_by_id = {item["id"]: item for item in expected_references}
        if set(expected_by_id) != {item["reference_id"] for item in file_rows}:
            raise ApiError("MCP 패키지의 포함 문서 목록이 Manifest와 일치하지 않습니다.", 409)
        for item in file_rows:
            calculated = hashlib.sha256(item["content_blob"]).hexdigest()
            expected = expected_by_id[item["reference_id"]]
            if calculated != item["sha256"] or calculated != expected.get("sha256"):
                raise ApiError("MCP 패키지 포함 문서 무결성 검증에 실패했습니다.", 409)
            included_files.append({"id": item["reference_id"], "filename": item["filename"], "bytes": item["bytes"], "sha256": item["sha256"]})
    elif file_rows:
        raise ApiError("원본 미포함 패키지에 문서 파일이 들어 있습니다.", 409)
    return {
        "packageId": row["package_id"],
        "version": row["version"],
        "publisher": row["publisher"],
        "manifest": manifest,
        "bundleSha256": row["bundle_sha256"],
        "signature": {
            "algorithm": STORE_SIGNATURE_ALGORITHM,
            "keyId": STORE_KEY_ID,
            "value": row["signature"],
            "verified": True,
        },
        "validation": {
            "passed": True,
            "vulnerabilities": 0,
            "checks": ["manifest-contract", "permission-allowlist", "dependency-version-pin", "bundle-sha256", "publisher-signature"],
        },
        "includedFiles": included_files,
        "publishedAt": row["published_at"],
    }


def _get_package(db: sqlite3.Connection, package_id: str, version: str) -> dict:
    row = db.execute(
        "SELECT * FROM mcp_packages WHERE package_id=? AND version=?", (package_id, version)
    ).fetchone()
    if not row:
        raise ApiError("요청한 MCP 패키지 버전을 찾을 수 없습니다.", 404)
    return _verified_package(row)


def list_store_packages() -> dict:
    ensure_schema()
    with _connect() as db:
        rows = db.execute("SELECT * FROM mcp_packages ORDER BY package_id, version DESC").fetchall()
        installations = {
            row["package_id"]: dict(row)
            for row in db.execute("SELECT * FROM mcp_installations WHERE status='active'").fetchall()
        }
        history = db.execute(
            "SELECT package_id, from_version, to_version FROM mcp_install_history ORDER BY id DESC"
        ).fetchall()
        configurations = {
            row["package_id"]: dict(row)
            for row in db.execute("SELECT package_id,revision,updated_at FROM mcp_configurations").fetchall()
        }
    rollback_versions = {}
    for row in history:
        current = installations.get(row["package_id"], {}).get("pinned_version")
        if row["package_id"] not in rollback_versions and row["from_version"] and row["from_version"] != current:
            rollback_versions[row["package_id"]] = row["from_version"]
    grouped = {}
    quarantined = []
    for row in rows:
        try:
            package = _verified_package(row)
        except ApiError as error:
            quarantined.append({"packageId": row["package_id"], "version": row["version"], "error": str(error)})
            continue
        item = grouped.setdefault(
            package["packageId"],
            {
                "packageId": package["packageId"],
                "name": package["manifest"]["name"],
                "description": package["manifest"].get("description", ""),
                "publisher": package["publisher"],
                "runtime": package["manifest"]["runtime"],
                "permissions": [item["scope"] for item in package["manifest"]["permissions"]],
                "configuration": package["manifest"].get("configuration"),
                "configurable": bool(package["manifest"].get("configuration")),
                "editable": True,
                "deletable": package["publisher"] not in PROTECTED_STORE_PUBLISHERS,
                "versions": [],
            },
        )
        item["versions"].append(
            {"version": package["version"], "bundleSha256": package["bundleSha256"], "signatureVerified": True, "validationPassed": package["validation"]["passed"], "vulnerabilities": package["validation"]["vulnerabilities"]}
        )
    for package_id, item in grouped.items():
        installation = installations.get(package_id)
        item["installedVersion"] = installation["pinned_version"] if installation else None
        item["rollbackVersion"] = rollback_versions.get(package_id)
        item["configurationRevision"] = configurations.get(package_id, {}).get("revision", 0)
        item["configurationUpdatedAt"] = configurations.get(package_id, {}).get("updated_at")
    return {
        "items": list(grouped.values()),
        "signature": {"algorithm": STORE_SIGNATURE_ALGORITHM, "keyId": STORE_KEY_ID},
        "installedCount": len(installations),
        "quarantined": quarantined,
    }


def _installed_configuration_package(db: sqlite3.Connection, package_id: str) -> tuple[dict, dict]:
    installation = db.execute(
        "SELECT * FROM mcp_installations WHERE package_id=? AND status='active'", (package_id,)
    ).fetchone()
    if not installation:
        raise ApiError("환경설정할 MCP를 먼저 설치해 주세요.", 409)
    package_row = db.execute(
        "SELECT * FROM mcp_packages WHERE package_id=? AND version=?",
        (package_id, installation["pinned_version"]),
    ).fetchone()
    if not package_row:
        raise ApiError("설치된 MCP 패키지를 찾을 수 없습니다.", 404)
    package = _verified_package(package_row)
    contract = _configuration_contract(package["manifest"])
    if not contract:
        raise ApiError("이 MCP는 환경설정 항목을 선언하지 않았습니다.", 404)
    return package, contract


def get_mcp_configuration(payload: dict) -> dict:
    ensure_schema()
    package_id = str(payload.get("package_id") or "").strip()
    if not package_id:
        raise ApiError("환경설정할 MCP가 필요합니다.")
    with _connect() as db:
        package, contract = _installed_configuration_package(db, package_id)
        row = db.execute("SELECT * FROM mcp_configurations WHERE package_id=?", (package_id,)).fetchone()
    stored = _load_json(row["values_json"], {}) if row else {}
    return {
        "packageId": package_id,
        "packageRef": package_id + "@" + package["version"],
        "name": package["manifest"]["name"],
        "schema": contract,
        "values": _normalize_configuration_values(contract, stored),
        "revision": row["revision"] if row else 0,
        "updatedAt": row["updated_at"] if row else None,
    }


def save_mcp_configuration(payload: dict) -> dict:
    ensure_schema()
    package_id = str(payload.get("package_id") or "").strip()
    actor = _actor(payload)
    with _connect() as db:
        package, contract = _installed_configuration_package(db, package_id)
        values = _normalize_configuration_values(contract, payload.get("values"))
        existing = db.execute("SELECT * FROM mcp_configurations WHERE package_id=?", (package_id,)).fetchone()
        expected_revision = int(payload.get("base_revision") or 0)
        current_revision = existing["revision"] if existing else 0
        if expected_revision != current_revision:
            raise ApiError("다른 작업에서 MCP 환경설정이 변경되었습니다. 다시 열어 주세요.", 409)
        revision = current_revision + 1
        now = utc_now()
        db.execute(
            """
            INSERT INTO mcp_configurations(package_id,values_json,revision,updated_by,updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(package_id) DO UPDATE SET
              values_json=excluded.values_json, revision=excluded.revision,
              updated_by=excluded.updated_by, updated_at=excluded.updated_at
            """,
            (package_id, _json(values), revision, actor, now),
        )
        _audit(db, actor, "mcp.configuration_updated", {"package_id": package_id, "version": package["version"], "revision": revision, "keys": sorted(values)})
    return {
        "packageId": package_id,
        "packageRef": package_id + "@" + package["version"],
        "name": package["manifest"]["name"],
        "values": values,
        "revision": revision,
        "updatedAt": now,
    }


def _approved_package_permissions(payload: dict, manifest: dict) -> list[str]:
    approved = payload.get("approved_permissions")
    if not isinstance(approved, list):
        raise ApiError("설치 권한 승인이 필요합니다.", 403)
    approved_set = {str(item) for item in approved}
    required = {item["scope"] for item in manifest["permissions"] if item.get("required", True)}
    if not required.issubset(approved_set):
        raise ApiError("MCP가 요구하는 모든 권한을 승인해야 합니다.", 403)
    return sorted(required)


def install_mcp_package(payload: dict) -> dict:
    ensure_schema()
    package_id = str(payload.get("package_id") or "").strip()
    version = str(payload.get("version") or "").strip()
    if not package_id or not version:
        raise ApiError("설치할 MCP와 정확한 버전이 필요합니다.")
    if payload.get("acknowledge_signature") is not True:
        raise ApiError("게시자 서명 확인이 필요합니다.", 403)
    actor = _actor(payload)
    with _connect() as db:
        package = _get_package(db, package_id, version)
        approved = _approved_package_permissions(payload, package["manifest"])
        current = db.execute(
            "SELECT * FROM mcp_installations WHERE package_id=? AND status='active'", (package_id,)
        ).fetchone()
        previous_version = current["pinned_version"] if current else None
        if previous_version == version:
            return {"installation": dict(current), "package": package, "idempotent": True}
        now = utc_now()
        if current:
            db.execute(
                "UPDATE mcp_installations SET pinned_version=?,installed_by=?,updated_at=? WHERE package_id=?",
                (version, actor, now, package_id),
            )
        else:
            db.execute(
                "INSERT INTO mcp_installations(package_id,pinned_version,status,installed_by,installed_at,updated_at) VALUES(?,?,?,?,?,?)",
                (package_id, version, "active", actor, now, now),
            )
        action = "install" if not previous_version else ("upgrade" if tuple(map(int, version.split("."))) > tuple(map(int, previous_version.split("."))) else "downgrade")
        db.execute(
            "INSERT INTO mcp_install_history(package_id,from_version,to_version,action,actor,created_at) VALUES(?,?,?,?,?,?)",
            (package_id, previous_version, version, action, actor, now),
        )
        _audit(db, actor, "mcp.package_installed", {"package_id": package_id, "from_version": previous_version, "pinned_version": version, "bundle_sha256": package["bundleSha256"], "signature_verified": True, "approved_permissions": approved})
    return {"installation": {"package_id": package_id, "pinned_version": version, "status": "active", "installed_by": actor, "updated_at": now}, "package": package, "idempotent": False}


def rollback_mcp_package(payload: dict) -> dict:
    ensure_schema()
    package_id = str(payload.get("package_id") or "").strip()
    if not package_id:
        raise ApiError("롤백할 MCP가 필요합니다.")
    if payload.get("acknowledge_signature") is not True:
        raise ApiError("롤백 대상 패키지의 서명 확인이 필요합니다.", 403)
    actor = _actor(payload)
    with _connect() as db:
        current = db.execute(
            "SELECT * FROM mcp_installations WHERE package_id=? AND status='active'", (package_id,)
        ).fetchone()
        if not current:
            raise ApiError("설치된 MCP를 찾을 수 없습니다.", 404)
        candidates = db.execute(
            "SELECT from_version FROM mcp_install_history WHERE package_id=? AND from_version IS NOT NULL ORDER BY id DESC",
            (package_id,),
        ).fetchall()
        target_version = next((row["from_version"] for row in candidates if row["from_version"] != current["pinned_version"]), None)
        if not target_version:
            raise ApiError("롤백 가능한 이전 버전이 없습니다.", 409)
        package = _get_package(db, package_id, target_version)
        approved = _approved_package_permissions(payload, package["manifest"])
        now = utc_now()
        db.execute(
            "UPDATE mcp_installations SET pinned_version=?,installed_by=?,updated_at=? WHERE package_id=?",
            (target_version, actor, now, package_id),
        )
        db.execute(
            "INSERT INTO mcp_install_history(package_id,from_version,to_version,action,actor,created_at) VALUES(?,?,?,?,?,?)",
            (package_id, current["pinned_version"], target_version, "rollback", actor, now),
        )
        _audit(db, actor, "mcp.package_rolled_back", {"package_id": package_id, "from_version": current["pinned_version"], "pinned_version": target_version, "bundle_sha256": package["bundleSha256"], "signature_verified": True, "approved_permissions": approved})
    return {"installation": {"package_id": package_id, "pinned_version": target_version, "status": "active", "installed_by": actor, "updated_at": now}, "package": package}



def _next_package_patch_version(db: sqlite3.Connection, package_id: str, version: str) -> str:
    major, minor, patch = (int(item) for item in version.split("."))
    while db.execute("SELECT 1 FROM mcp_packages WHERE package_id=? AND version=?", (package_id, f"{major}.{minor}.{patch + 1}")).fetchone():
        patch += 1
    return f"{major}.{minor}.{patch + 1}"


def fork_mcp_package(payload: dict) -> dict:
    """Create an editable next-version draft without mutating the signed package."""
    ensure_schema()
    package_id = str(payload.get("package_id") or "").strip()
    version = str(payload.get("version") or "").strip()
    if not package_id or not version:
        raise ApiError("수정할 MCP와 정확한 버전이 필요합니다.")
    actor = _actor(payload)
    with _connect() as db:
        package = _get_package(db, package_id, version)
        manifest = json.loads(json.dumps(package["manifest"], ensure_ascii=False))
        new_version = _next_package_patch_version(db, package_id, version)
        manifest["version"] = new_version
        manifest["mcpType"] = str(manifest.get("mcpType") or "tool")
        type_contract = MCP_BUILDER_TYPES.get(manifest["mcpType"], MCP_BUILDER_TYPES["tool"])
        manifest["capabilities"] = list(manifest.get("capabilities") or type_contract["capabilities"])
        old_guide = manifest.get("builderGuide") or {}
        manifest["builderGuide"] = {
            "version": "1.1",
            "instructions": str(old_guide.get("instructions") or manifest.get("description") or "설치된 MCP의 기능을 유지하며 필요한 항목을 수정합니다."),
            "cautions": list(old_guide.get("cautions") or []),
            "procedure": list(old_guide.get("procedure") or ["입력값을 검증한다.", "기존 기능을 실행하고 결과를 확인한다."]),
            "triggerExamples": list(old_guide.get("triggerExamples") or []),
            "dataSource": str(old_guide.get("dataSource") or ""),
            "useModel": bool(old_guide.get("useModel")),
            "referenceRoles": type_contract["referenceRoles"],
            "templateSchema": old_guide.get("templateSchema") if manifest["mcpType"] == "template" else None,
            "templateProfile": old_guide.get("templateProfile") if manifest["mcpType"] == "template" else None,
            "authoringVersion": old_guide.get("authoringVersion") if manifest["mcpType"] == "template" else None,
        }
        manifest["executionAdapter"] = manifest.get("executionAdapter") or {"kind": "prompt", "version": "1.0", "entrypoint": "builder.guide", "arbitraryCode": False}
        manifest["derivedFrom"] = package_id + "@" + version
        draft_id = "draft_" + uuid.uuid4().hex
        now = utc_now()
        file_rows = db.execute("SELECT * FROM mcp_package_files WHERE package_id=? AND version=? ORDER BY reference_id", (package_id, version)).fetchall()
        source_contracts = {item.get("id"): item for item in manifest.get("references") or [] if isinstance(item, dict)}
        reference_map = {item["reference_id"]: "ref_" + uuid.uuid4().hex for item in file_rows}
        manifest["references"] = [{**source_contracts.get(item["reference_id"], {}), "id": reference_map[item["reference_id"]], "filename": item["filename"], "mediaType": item["media_type"], "bytes": item["bytes"], "sha256": item["sha256"]} for item in file_rows]
        manifest["sourceIncluded"] = bool(file_rows)
        db.execute("INSERT INTO mcp_drafts(id,owner,status,manifest_json,validation_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (draft_id, actor, "draft", _json(manifest), _json({"passed": False, "tests": []}), now, now))
        for item in file_rows:
            role = source_contracts.get(item["reference_id"], {}).get("role", "guide")
            summary = _inspect_builder_reference(item["filename"], bytes(item["content_blob"]))[1]
            summary["builderRole"] = role
            db.execute("INSERT INTO mcp_draft_references(id,draft_id,filename,media_type,bytes,sha256,summary_json,content_blob,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (reference_map[item["reference_id"]], draft_id, item["filename"], item["media_type"], item["bytes"], item["sha256"], _json(summary), item["content_blob"], now))
        _audit(db, actor, "mcp.package_forked_for_edit", {"package_id": package_id, "from_version": version, "draft_id": draft_id, "next_version": new_version})
        row = db.execute("SELECT * FROM mcp_drafts WHERE id=?", (draft_id,)).fetchone()
    return {"draft": _draft_row_result(row), "sourcePackage": package_id + "@" + version}


def delete_mcp_package(payload: dict) -> dict:
    ensure_schema()
    package_id = str(payload.get("package_id") or "").strip()
    version = str(payload.get("version") or "").strip()
    package_ref = package_id + "@" + version
    if payload.get("confirm_package_ref") != package_ref:
        raise ApiError("삭제할 MCP의 ID와 버전을 다시 확인해야 합니다.", 403)
    actor = _actor(payload)
    with _connect() as db:
        row = db.execute("SELECT * FROM mcp_packages WHERE package_id=? AND version=?", (package_id, version)).fetchone()
        if not row:
            raise ApiError("삭제할 MCP 버전을 찾을 수 없습니다.", 404)
        manifest = _load_json(row["manifest_json"], {})
        if row["publisher"] in PROTECTED_STORE_PUBLISHERS:
            raise ApiError("플랫폼 기본 MCP는 삭제할 수 없습니다. 수정 기능으로 파생 버전을 만드세요.", 403)
        installation = db.execute("SELECT * FROM mcp_installations WHERE package_id=?", (package_id,)).fetchone()
        installed_target = bool(installation and installation["pinned_version"] == version)
        if installed_target:
            db.execute("DELETE FROM mcp_installations WHERE package_id=?", (package_id,))
        db.execute("DELETE FROM mcp_reference_chunks WHERE package_id=? AND version=?", (package_id, version))
        db.execute("DELETE FROM mcp_capabilities WHERE package_id=? AND version=?", (package_id, version))
        db.execute("DELETE FROM mcp_package_files WHERE package_id=? AND version=?", (package_id, version))
        db.execute("DELETE FROM mcp_packages WHERE package_id=? AND version=?", (package_id, version))
        db.execute("UPDATE mcp_drafts SET status='validated',published_package_id=NULL,published_version=NULL,updated_at=? WHERE published_package_id=? AND published_version=?", (utc_now(), package_id, version))
        _audit(db, actor, "mcp.package_deleted", {"package_id": package_id, "version": version, "installation_removed": installed_target})
    return {"deleted": True, "packageRef": package_ref, "draftRetained": True}


def _index_package_capabilities(db: sqlite3.Connection, manifest: dict) -> None:
    package_id = str(manifest.get("id") or "")
    version = str(manifest.get("version") or "")
    capabilities = manifest.get("capabilities") or []
    guide = manifest.get("builderGuide") if isinstance(manifest.get("builderGuide"), dict) else {}
    if not package_id or not version or not capabilities or not guide:
        return
    adapter = manifest.get("executionAdapter") if isinstance(manifest.get("executionAdapter"), dict) else {}
    execution_adapter = str(adapter.get("kind") or "prompt")
    trigger_examples = [str(item)[:500] for item in guide.get("triggerExamples") or [] if str(item).strip()]
    search_text = "\n".join(
        [
            str(manifest.get("name") or ""),
            str(manifest.get("description") or ""),
            str(guide.get("instructions") or ""),
            *trigger_examples,
        ]
    )[:20_000]
    db.execute("DELETE FROM mcp_capabilities WHERE package_id=? AND version=?", (package_id, version))
    for capability_id in capabilities:
        db.execute(
            """
            INSERT INTO mcp_capabilities(
                package_id,version,capability_id,mcp_type,execution_adapter,
                search_text,trigger_examples_json,indexed_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                package_id,
                version,
                str(capability_id),
                str(manifest.get("mcpType") or "tool"),
                execution_adapter,
                search_text,
                _json(trigger_examples),
                utc_now(),
            ),
        )


def _normalized_intent(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", " ", str(value or "").lower()).strip()


def _intent_tokens(value: str) -> set[str]:
    ignored = {"해줘", "해주세요", "바꿔줘", "작성해줘", "만들어줘", "대한", "관련", "사용", "이걸", "이것"}
    return {
        token
        for token in _normalized_intent(value).split()
        if len(token) >= 2 and token not in ignored
    }


def _capability_match_score(intent: str, manifest: dict) -> tuple[int, list[str]]:
    query = _normalized_intent(intent)
    query_tokens = _intent_tokens(intent)
    guide = manifest.get("builderGuide") or {}
    score = 0
    matched_by = []
    for example in guide.get("triggerExamples") or []:
        trigger = _normalized_intent(example)
        if not trigger:
            continue
        if query == trigger:
            score = max(score, 140)
            matched_by.append("trigger-exact")
        elif trigger in query or query in trigger:
            score = max(score, 105)
            matched_by.append("trigger-phrase")
        else:
            trigger_tokens = _intent_tokens(trigger)
            overlap = len(query_tokens & trigger_tokens)
            if overlap:
                score = max(score, round(80 * overlap / max(1, len(trigger_tokens))))
                matched_by.append("trigger-token")
    name = _normalized_intent(str(manifest.get("name") or "").replace("MCP", ""))
    if name and name in query:
        score = max(score, 90)
        matched_by.append("name-phrase")
    name_tokens = _intent_tokens(name)
    if name_tokens:
        overlap = len(query_tokens & name_tokens)
        score = max(score, round(65 * overlap / len(name_tokens)))
        if overlap:
            matched_by.append("name-token")
    search_tokens = _intent_tokens(
        str(manifest.get("description") or "") + " " + str(guide.get("instructions") or "")
    )
    overlap = len(query_tokens & search_tokens)
    if overlap:
        score = max(score, min(55, overlap * 18))
        matched_by.append("guide-token")
    if manifest.get("mcpType") == "data":
        data_signals = {"조회", "검색", "현황", "수치", "통계", "금액", "기준", "근거", "자료", "얼마", "예산"}
        generic_terms = {"데이터", "자료", "조회", "검색", "현황", "기준", "관련", "등록", "조직", "우리부"}
        guide_text = " ".join(
            [
                str(manifest.get("name") or ""),
                str(manifest.get("description") or ""),
                str(guide.get("dataSource") or ""),
                *[str(item) for item in guide.get("triggerExamples") or []],
            ]
        )
        topic_overlap = (query_tokens - generic_terms) & (_intent_tokens(guide_text) - generic_terms)
        if any(signal in query for signal in data_signals) and topic_overlap:
            score = max(score, min(104, 84 + len(topic_overlap) * 5))
            matched_by.extend(["data-intent", "data-topic"])
    if manifest.get("mcpType") == "template":
        template_signals = ("양식", "서식", "형식", "포맷")
        template_text = _normalized_intent(
            " ".join(
                [
                    str(manifest.get("name") or ""),
                    str(manifest.get("description") or ""),
                    str(guide.get("instructions") or ""),
                    *[str(item) for item in guide.get("triggerExamples") or []],
                ]
            )
        )
        agency_match = (
            any(term in query for term in ("행안부", "행정안전부"))
            and any(term in template_text for term in ("행안부", "행정안전부"))
        )
        if any(signal in query for signal in template_signals) and agency_match:
            score = max(score, 112)
            matched_by.extend(["template-intent", "template-agency"])
    return score, sorted(set(matched_by))


def list_capability_registry() -> dict:
    ensure_schema()
    with _connect() as db:
        rows = db.execute(
            """
            SELECT p.*,c.capability_id,c.mcp_type,c.execution_adapter,c.indexed_at
              FROM mcp_capabilities c
              JOIN mcp_installations i
                ON i.package_id=c.package_id AND i.pinned_version=c.version AND i.status='active'
              JOIN mcp_packages p ON p.package_id=c.package_id AND p.version=c.version
             ORDER BY c.package_id,c.capability_id
            """
        ).fetchall()
    items = []
    for row in rows:
        package = _verified_package(row)
        manifest = package["manifest"]
        items.append(
            {
                "capabilityId": row["capability_id"],
                "packageId": row["package_id"],
                "version": row["version"],
                "packageRef": row["package_id"] + "@" + row["version"],
                "name": manifest.get("name", row["package_id"]),
                "description": manifest.get("description", ""),
                "mcpType": row["mcp_type"],
                "executionAdapter": row["execution_adapter"],
                "permissions": [item["scope"] for item in manifest.get("permissions") or []],
                "triggerExamples": (manifest.get("builderGuide") or {}).get("triggerExamples") or [],
                "indexedAt": row["indexed_at"],
            }
        )
    return {"items": items, "count": len(items), "installedPackages": len({item["packageRef"] for item in items})}


def resolve_capabilities(payload: dict) -> dict:
    intent = str(payload.get("intent") or "").strip()
    if not intent:
        raise ApiError("Capability를 찾을 업무 요청이 필요합니다.")
    registry = list_capability_registry()
    candidates = []
    seen_packages = set()
    excluded = []
    project_id = str(payload.get("project_id") or "").strip()
    resolver_policy = copy.deepcopy(_DEFAULT_PROJECT_POLICY["resolver"])
    if project_id:
        project_id = _safe_project_id(project_id)
        with _connect() as policy_db:
            resolver_policy.update((_project_policy_result(policy_db, project_id).get("policy") or {}).get("resolver") or {})
    allowed_permissions = {
        str(item) for item in (payload.get("allowed_permissions") or [])
        if str(item).strip()
    }
    required_input_types = {str(item) for item in (payload.get("input_artifact_types") or []) if str(item).strip()}
    required_output_type = str(payload.get("output_artifact_type") or "").strip()

    with _connect() as db:
        for entry in registry["items"]:
            package_ref = entry["packageRef"]
            if package_ref in seen_packages:
                continue
            row = db.execute(
                "SELECT * FROM mcp_packages WHERE package_id=? AND version=?",
                (entry["packageId"], entry["version"]),
            ).fetchone()
            package = _verified_package(row)
            manifest = package["manifest"]
            permissions = {str(item.get("scope") or "") for item in manifest.get("permissions") or []}
            if allowed_permissions and not permissions.issubset(allowed_permissions):
                excluded.append({
                    "packageRef": package_ref,
                    "reason": "permission-scope",
                    "requiredPermissions": sorted(permissions - allowed_permissions),
                })
                continue
            io_contract = manifest.get("ioContract") if isinstance(manifest.get("ioContract"), dict) else {}
            declared_inputs = {str(item) for item in io_contract.get("inputArtifactTypes") or []}
            declared_outputs = {str(item) for item in io_contract.get("outputArtifactTypes") or []}
            if required_input_types and declared_inputs and not (required_input_types & declared_inputs):
                excluded.append({"packageRef": package_ref, "reason": "input-artifact-incompatible"})
                continue
            if required_output_type and declared_outputs and required_output_type not in declared_outputs:
                excluded.append({"packageRef": package_ref, "reason": "output-artifact-incompatible"})
                continue

            score, matched_by = _capability_match_score(intent, manifest)
            if manifest.get("mcpType") == "data" and score < 80:
                query = _normalized_intent(intent)
                query_tokens = _rag_query_tokens(intent)
                data_signals = (
                    "조회", "검색", "확인", "찾아", "알려", "현황", "수치", "통계",
                    "금액", "기준", "근거", "자료", "얼마", "예산", "지적", "비교",
                )
                generic_route_tokens = {
                    "확인", "확인해줘", "찾아줘", "알려줘", "조회", "검색", "현황",
                    "주요", "사항", "지적사항", "지적사항을", "관련", "자료", "데이터",
                }
                chunk_rows = db.execute(
                    "SELECT filename,search_text FROM mcp_reference_chunks WHERE package_id=? AND version=?",
                    (entry["packageId"], entry["version"]),
                ).fetchall()
                topic_tokens = query_tokens - generic_route_tokens
                best_topic_overlap = set()
                for item in chunk_rows:
                    chunk_text = str(item["filename"]) + " " + str(item["search_text"])
                    overlap = {token for token in topic_tokens if token in chunk_text}
                    if len(overlap) > len(best_topic_overlap):
                        best_topic_overlap = overlap
                if any(signal in query for signal in data_signals) and best_topic_overlap:
                    score = min(104, 82 + len(best_topic_overlap) * 5)
                    matched_by = sorted(set([*matched_by, "data-intent", "rag-content-topic"]))
            if score < 80:
                continue
            evaluation_row = db.execute(
                "SELECT * FROM mcp_evaluations WHERE package_id=? AND version=?",
                (entry["packageId"], entry["version"]),
            ).fetchone()
            quality = float(evaluation_row["quality"]) if evaluation_row else 0.75
            success_rate = float(evaluation_row["success_rate"]) if evaluation_row else 0.90
            latency_ms = float(evaluation_row["latency_ms"]) if evaluation_row else 1_000.0
            cost_per_run = float(evaluation_row["cost_per_run"]) if evaluation_row else 0.0
            preferred = set(resolver_policy.get("preferredPackages") or [])
            components = {
                "intent": min(1.0, score / 140.0),
                "quality": max(0.0, min(1.0, quality * 0.7 + success_rate * 0.3)),
                "cost": 1.0 / (1.0 + max(0.0, cost_per_run)),
                "latency": 1.0 / (1.0 + max(0.0, latency_ms) / 1_500.0),
                "preference": 1.0 if package_ref in preferred or entry["packageId"] in preferred else 0.5,
            }
            weights = {
                "intent": float(resolver_policy.get("intentWeight", 0.45)),
                "quality": float(resolver_policy.get("qualityWeight", 0.30)),
                "cost": float(resolver_policy.get("costWeight", 0.10)),
                "latency": float(resolver_policy.get("latencyWeight", 0.10)),
                "preference": float(resolver_policy.get("preferenceWeight", 0.05)),
            }
            weight_total = sum(weights.values()) or 1.0
            rank_score = round(100 * sum(components[key] * weights[key] for key in weights) / weight_total, 3)

            seen_packages.add(package_ref)
            candidates.append(
                {
                    **entry,
                    "score": score,
                    "matchedBy": matched_by,
                    "capabilities": list(manifest.get("capabilities") or []),
                    "rankScore": rank_score,
                    "ranking": {
                        "components": {key: round(value, 4) for key, value in components.items()},
                        "weights": weights,
                    },
                    "evaluation": {
                        "quality": quality, "successRate": success_rate, "latencyMs": latency_ms,
                        "costPerRun": cost_per_run, "sampleCount": int(evaluation_row["sample_count"]) if evaluation_row else 0,
                    },
                    "guideVersion": (manifest.get("builderGuide") or {}).get("version", "1.0"),
                    "signatureVerified": True,
                }
            )
    candidates.sort(key=lambda item: (-item["rankScore"], -item["score"], item["packageRef"]))
    limit = max(1, min(10, int(payload.get("limit") or 3)))
    return {
        "intent": intent,
        "projectId": project_id or None,
        "items": candidates[:limit],
        "excluded": excluded,
        "resolved": bool(candidates),
        "threshold": 80,
        "rankingPolicy": resolver_policy,
    }




def save_mcp_evaluation(payload: dict) -> dict:
    ensure_schema()
    package_id = str(payload.get("package_id") or "").strip()
    version = str(payload.get("version") or "").strip()
    if not package_id or not version:
        raise ApiError("평가할 MCP package_id와 version이 필요합니다.")
    try:
        quality = float(payload.get("quality"))
        success_rate = float(payload.get("success_rate"))
        latency_ms = float(payload.get("latency_ms"))
        cost_per_run = float(payload.get("cost_per_run"))
        sample_count = int(payload.get("sample_count"))
    except (TypeError, ValueError) as error:
        raise ApiError("MCP 평가 지표가 올바르지 않습니다.") from error
    if not (0 <= quality <= 1 and 0 <= success_rate <= 1):
        raise ApiError("품질과 성공률은 0~1 범위여야 합니다.")
    if latency_ms < 0 or cost_per_run < 0 or sample_count < 0:
        raise ApiError("지연시간·비용·표본 수는 음수일 수 없습니다.")
    actor = _actor(payload)
    now = utc_now()
    with _connect() as db:
        if not db.execute(
            "SELECT 1 FROM mcp_packages WHERE package_id=? AND version=?",
            (package_id, version),
        ).fetchone():
            raise ApiError("평가할 MCP 패키지를 찾을 수 없습니다.", 404)
        db.execute(
            """
            INSERT INTO mcp_evaluations(
                package_id,version,quality,success_rate,latency_ms,cost_per_run,
                sample_count,notes,updated_by,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(package_id,version) DO UPDATE SET
                quality=excluded.quality,success_rate=excluded.success_rate,
                latency_ms=excluded.latency_ms,cost_per_run=excluded.cost_per_run,
                sample_count=excluded.sample_count,notes=excluded.notes,
                updated_by=excluded.updated_by,updated_at=excluded.updated_at
            """,
            (
                package_id, version, quality, success_rate, latency_ms, cost_per_run,
                sample_count, str(payload.get("notes") or "")[:2_000] or None, actor, now,
            ),
        )
        _audit(db, actor, "mcp.evaluation_saved", {
            "package_id": package_id, "version": version, "quality": quality,
            "success_rate": success_rate, "latency_ms": latency_ms,
            "cost_per_run": cost_per_run, "sample_count": sample_count,
        })
    return {
        "packageId": package_id, "version": version, "quality": quality,
        "successRate": success_rate, "latencyMs": latency_ms,
        "costPerRun": cost_per_run, "sampleCount": sample_count,
        "updatedBy": actor, "updatedAt": now,
    }

def _reference_row_result(row: sqlite3.Row) -> dict:
    summary = _load_json(row["summary_json"], {})
    return {
        "id": row["id"],
        "filename": row["filename"],
        "mediaType": row["media_type"],
        "bytes": row["bytes"],
        "sha256": row["sha256"],
        "role": summary.get("builderRole", "guide"),
        "summary": summary,
        "createdAt": row["created_at"],
    }


def _draft_row_result(row: sqlite3.Row) -> dict:
    with _connect() as reference_db:
        references = reference_db.execute(
            "SELECT * FROM mcp_draft_references WHERE draft_id=? ORDER BY created_at",
            (row["id"],),
        ).fetchall()
    return {
        "id": row["id"],
        "owner": row["owner"],
        "status": row["status"],
        "manifest": _load_json(row["manifest_json"], {}),
        "validation": _load_json(row["validation_json"], {"passed": False, "tests": []}),
        "references": [_reference_row_result(item) for item in references],
        "publishedPackageId": row["published_package_id"],
        "publishedVersion": row["published_version"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _pdf_text_extractor_path() -> str:
    configured = str(os.getenv("AIWORKS_PDFTOTEXT_PATH") or "").strip()
    candidates = [configured] if configured else []
    candidates.extend(["/usr/bin/pdftotext", "/usr/local/bin/pdftotext"])
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise ApiError(
        "PDF 텍스트 추출기를 실행할 수 없습니다. AIWORKS_PDFTOTEXT_PATH 또는 /usr/bin/pdftotext를 확인해 주세요.",
        503,
    )


def _pdf_text_extractor_status() -> dict:
    try:
        executable = _pdf_text_extractor_path()
        completed = subprocess.run(
            [executable, "-v"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3,
            check=False,
        )
        version_text = (completed.stderr or completed.stdout).decode("utf-8", errors="replace").splitlines()
        return {
            "available": completed.returncode == 0,
            "executable": executable,
            "version": version_text[0][:160] if version_text else "unknown",
        }
    except (ApiError, OSError, subprocess.TimeoutExpired) as error:
        return {"available": False, "executable": None, "version": None, "error": str(error)}


def _extract_pdf_pages(data: bytes) -> list[tuple[int, str]]:
    executable = _pdf_text_extractor_path()
    try:
        completed = subprocess.run(
            [executable, "-layout", "-enc", "UTF-8", "-", "-"],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except FileNotFoundError as error:
        raise ApiError(f"PDF 텍스트 추출기를 실행하지 못했습니다: {executable}", 503) from error
    except subprocess.TimeoutExpired as error:
        raise ApiError("PDF 텍스트 추출 시간이 초과되었습니다.", 408) from error
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()[:300]
        raise ApiError("PDF 텍스트를 추출하지 못했습니다." + (" " + detail if detail else ""), 415)
    text = completed.stdout.decode("utf-8", errors="replace")
    pages = []
    for page_number, page in enumerate(text.split("\f"), start=1):
        normalized = re.sub(r"[ \t]+", " ", page.replace("\r", "")).strip()
        if normalized:
            pages.append((page_number, normalized))
    return pages


def _reference_text_pages(filename: str, media_type: str, data: bytes) -> list[tuple[int | None, str]]:
    extension = Path(filename).suffix.lower()
    if extension == ".pdf" or media_type == "application/pdf":
        return _extract_pdf_pages(data)
    if extension == ".hwpx" or media_type == "application/hwp+zip":
        parsed = parse_hwpx(data, filename)
        text = "\n".join(item["text"] for item in parsed.get("paragraphs") or [] if item.get("text"))
        return [(None, text)] if text.strip() else []
    if extension == ".docx" or "wordprocessingml" in media_type:
        return _extract_docx_parts(data)
    if extension == ".xlsx" or "spreadsheetml" in media_type:
        return _extract_xlsx_parts(data)
    if extension in {".md", ".txt"} or media_type in {"text/markdown", "text/plain"}:
        return [(None, data.decode("utf-8", errors="strict"))]
    return []


def _chunk_reference_text(
    reference_id: str,
    filename: str,
    sha256: str,
    pages: list[tuple[int | None, str]],
    *,
    chunk_size: int = 1_200,
    overlap: int = 180,
) -> list[dict]:
    chunks = []
    for page_number, page_text in pages:
        text = re.sub(r"\n{3,}", "\n\n", str(page_text or "")).strip()
        start = 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            if end < len(text):
                boundary = max(text.rfind("\n", start + chunk_size // 2, end), text.rfind(" ", start + chunk_size // 2, end))
                if boundary > start:
                    end = boundary
            content = text[start:end].strip()
            if content:
                chunks.append(
                    {
                        "referenceId": reference_id,
                        "chunkIndex": len(chunks),
                        "filename": filename,
                        "pageNumber": page_number,
                        "content": content,
                        "searchText": _normalized_intent(content),
                        "sha256": sha256,
                    }
                )
            if end >= len(text):
                break
            start = max(start + 1, end - overlap)
    return chunks


def _reference_rag_chunks(reference_id: str, filename: str, media_type: str, sha256: str, data: bytes) -> list[dict]:
    return _chunk_reference_text(reference_id, filename, sha256, _reference_text_pages(filename, media_type, data))


def _rag_query_tokens(value: str) -> set[str]:
    ignored = {
        "대해", "대한", "관련", "정리", "정리해줘", "확인", "확인해줘", "찾아줘",
        "알려줘", "보여줘", "해줘", "해주세요", "연도별", "연도별로", "주요",
    }
    aliases = {"행안부": "행정안전부", "과기부": "과학기술정보통신부"}
    suffixes = ("으로부터", "에서부터", "으로", "에서", "에게", "부터", "까지", "처럼", "별로", "에", "을", "를", "이", "가", "은", "는", "와", "과", "로", "의")
    tokens = set()
    for raw_token in _normalized_intent(value).split():
        if raw_token in ignored:
            continue
        candidates = {raw_token}
        if raw_token.endswith("관련") and len(raw_token) > 2:
            candidates.add(raw_token[:-2])
        for suffix in suffixes:
            if raw_token.endswith(suffix) and len(raw_token) - len(suffix) >= 2:
                candidates.add(raw_token[:-len(suffix)])
                break
        for token in candidates:
            if (len(token) >= 2 or token.isdigit()) and token not in ignored:
                tokens.add(token)
                short_year = re.fullmatch(r"(\d{2})년", token)
                if short_year:
                    tokens.add("20" + short_year.group(1) + "년")
                    tokens.add("20" + short_year.group(1))
                if token in aliases:
                    tokens.add(aliases[token])
    return tokens


def _rag_query_phrases(value: str) -> set[str]:
    ignored = {
        "대해", "대한", "관련", "정리", "정리해줘", "확인", "확인해줘", "찾아줘",
        "알려줘", "보여줘", "해줘", "해주세요", "연도별", "연도별로", "주요",
    }
    aliases = {"행안부": "행정안전부", "과기부": "과학기술정보통신부"}
    suffixes = ("으로", "에서", "에게", "부터", "까지", "처럼", "별로", "에", "을", "를", "이", "가", "은", "는", "와", "과", "로", "의")
    normalized = []
    for raw_token in _normalized_intent(value).split():
        if raw_token in ignored:
            normalized.append("")
            continue
        token = raw_token[:-2] if raw_token.endswith("관련") and len(raw_token) > 2 else raw_token
        for suffix in suffixes:
            if token.endswith(suffix) and len(token) - len(suffix) >= 2:
                token = token[:-len(suffix)]
                break
        normalized.append(aliases.get(token, token))
    return {
        normalized[index] + " " + normalized[index + 1]
        for index in range(len(normalized) - 1)
        if normalized[index] and normalized[index + 1]
    }


def _search_rag_chunks(chunks: list[dict], query: str, *, limit: int = 5) -> list[dict]:
    normalized_query = _normalized_intent(query)
    query_tokens = _rag_query_tokens(query)
    query_phrases = _rag_query_phrases(query)
    if not normalized_query or not query_tokens:
        raise ApiError("검색할 질문을 두 글자 이상 입력해 주세요.")
    generic_phrase_tokens = {
        "행안부", "행정안전부", "예산", "지적사항", "보고서", "양식", "서식",
        "형식", "포맷", "대안", "확인하고", "포함해서", "작성해줘", "이에",
    }
    specific_phrases = {
        phrase
        for phrase in query_phrases
        if len(phrase.split()) >= 2
        and all(token not in generic_phrase_tokens and not re.fullmatch(r"\d{2,4}년?", token) for token in phrase.split())
    }
    matched_specific_phrases = {
        phrase
        for phrase in specific_phrases
        if any(phrase in str(item.get("searchText") or _normalized_intent(item.get("content") or "")) for item in chunks)
    }
    ranked = []
    for item in chunks:
        search_text = str(item.get("searchText") or _normalized_intent(item.get("content") or ""))
        filename_text = _normalized_intent(item.get("filename") or "")
        token_hits = sum(1 for token in query_tokens if token in search_text)
        title_hits = sum(1 for token in query_tokens if token in filename_text)
        phrase_hit = normalized_query in search_text
        phrase_hits = sum(1 for phrase in query_phrases if phrase in search_text)
        if not token_hits and not title_hits and not phrase_hit:
            continue
        density = sum(min(3, search_text.count(token)) for token in query_tokens)
        score = (120 if phrase_hit else 0) + phrase_hits * 90 + token_hits * 28 + title_hits * 12 + density * 3
        ranked.append({**item, "score": score, "matchedTopicPhrase": any(phrase in search_text for phrase in matched_specific_phrases)})
    if matched_specific_phrases:
        ranked = [item for item in ranked if item["matchedTopicPhrase"]]
    ranked.sort(key=lambda item: (-item["score"], item.get("filename", ""), item.get("chunkIndex", 0)))
    return [
        {key: value for key, value in item.items() if key != "matchedTopicPhrase"}
        for item in ranked[: max(1, min(8, int(limit)))]
    ]


def _rag_hit_result(item: dict, rank: int) -> dict:
    page_number = item.get("pageNumber")
    locator = item.get("filename", "자료") + (f" · {page_number}쪽" if page_number else "")
    return {
        "rank": rank,
        "referenceId": item.get("referenceId"),
        "filename": item.get("filename"),
        "pageNumber": page_number,
        "locator": locator,
        "excerpt": str(item.get("content") or "")[:1_500],
        "score": int(item.get("score") or 0),
        "sha256": item.get("sha256"),
    }


def _rag_extract_answer(query: str, hits: list[dict]) -> str:
    if not hits:
        return "등록된 자료에서 질문과 일치하는 근거를 찾지 못했습니다. 질문의 기관명·연도·항목을 더 구체적으로 입력해 주세요."
    return _rag_evidence_report(query, hits, include_title=False)


def _rag_sentence_units(value: str) -> list[str]:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    parts = re.split(r"(?<=[.!?])\s+|\s+[□■○●※▶▷]+\s*", text)
    units = []
    for part in parts:
        normalized = re.sub(r"\s+", " ", part).strip(" -·•")
        if len(normalized) < 12:
            continue
        if len(normalized) > 420:
            subparts = re.split(r"\s*[;；]\s*|\s+(?=\([가-힣0-9]+\))", normalized)
            units.extend(item.strip() for item in subparts if len(item.strip()) >= 12)
        else:
            units.append(normalized)
    return units[:80]


def _rag_clip(value: str, anchors: tuple[str, ...] = (), limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    anchor = next((term for term in anchors if term and term in text), "")
    position = text.find(anchor) if anchor else 0
    start = max(0, position - 110)
    end = min(len(text), start + limit)
    if start:
        boundary = text.find(" ", start, min(end, start + 40))
        start = boundary + 1 if boundary >= 0 else start
    if end < len(text):
        boundary = text.rfind(" ", max(start, end - 40), end)
        end = boundary if boundary > start else end
    return ("… " if start else "") + text[start:end].strip() + (" …" if end < len(text) else "")


def _rag_relevant_units(query: str, hit: dict, limit: int = 2) -> list[str]:
    query_tokens = _rag_query_tokens(query)
    issue_terms = (
        "지적", "문제", "우려", "미흡", "부족", "지연", "중복", "불용", "과다",
        "부적절", "곤란", "필요", "개선", "낮", "감소", "실효성", "비효율", "위험",
    )
    ranked = []
    for index, unit in enumerate(_rag_sentence_units(hit.get("content") or "")):
        token_hits = sum(1 for token in query_tokens if token in unit)
        issue_hits = sum(1 for term in issue_terms if term in unit)
        years = len(re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", unit))
        numeric = 1 if re.search(r"\d[\d,.]*\s*(?:원|억원|백만원|%|건|명|개)", unit) else 0
        score = token_hits * 5 + issue_hits * 7 + years * 3 + numeric * 2
        if score:
            ranked.append((score, -index, unit))
    ranked.sort(reverse=True)
    if not ranked:
        fallback = _rag_sentence_units(hit.get("content") or "")
        return [_rag_clip(item, tuple(sorted(query_tokens, key=len, reverse=True))) for item in fallback[:limit]]
    anchors = issue_terms + tuple(sorted(query_tokens, key=len, reverse=True))
    return [_rag_clip(item[2], anchors) for item in ranked[:limit]]


def _rag_evidence_report(query: str, hits: list[dict], *, include_title: bool = True) -> str:
    if not hits:
        return "등록된 자료에서 질문과 일치하는 근거를 찾지 못했습니다."
    selected = []
    seen = set()
    for rank, hit in enumerate(hits[:5], start=1):
        for unit in _rag_relevant_units(query, hit, limit=2):
            key = re.sub(r"\W+", "", unit)[:160]
            if not key or key in seen:
                continue
            seen.add(key)
            selected.append({"rank": rank, "text": unit})

    current_year = datetime.now(timezone.utc).year
    evidence_scope = " ".join(
        [query, *[str(hit.get("filename") or "") + " " + str(hit.get("content") or "") for hit in hits[:5]]]
    )
    full_years = set(re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", evidence_scope))
    short_years = {"20" + year for year in re.findall(r"(?<!\d)(\d{2})\s*년", query)}
    years = sorted(year for year in full_years | short_years if 2000 <= int(year) <= current_year + 2)
    lines = []
    if include_title:
        lines.extend(["# 데이터 MCP 근거 검토보고서", ""])
    lines.extend(["## 요청 및 검토 범위", query.strip(), ""])
    if years:
        lines.append("## 연도별 확인 결과")
        for year in years:
            year_items = []
            for rank, hit in enumerate(hits[:5], start=1):
                matching_units = [
                    unit for unit in _rag_sentence_units(hit.get("content") or "") if year in unit
                ]
                for unit in matching_units[:2]:
                    anchors = (
                        "지적", "문제", "우려", "미흡", "지연", "중복", "불용", "개선",
                        year,
                    )
                    clipped = _rag_clip(unit, anchors)
                    if year not in clipped:
                        clipped = year + "년 관련 근거: " + clipped
                    year_items.append({"rank": rank, "text": clipped})
                if not matching_units and year in str(hit.get("filename") or ""):
                    related = _rag_relevant_units(query, hit, limit=1)
                    if related:
                        year_items.append({
                            "rank": rank,
                            "text": year + "년 자료명 기준 · " + related[0],
                        })
            lines.append("### " + year + "년")
            if year_items:
                for item in year_items[:3]:
                    lines.append(f"- {item['text']} [{item['rank']}]")
            else:
                lines.append("- 등록 자료에서 해당 연도의 직접 근거를 찾지 못했습니다.")
        lines.append("")
    else:
        lines.append("## 핵심 확인 결과")
        for item in selected[:6]:
            lines.append(f"- {item['text']} [{item['rank']}]")
        lines.append("")

    signal_rules = [
        (("중복", "유사"), "유사·중복 사업 여부와 투자 범위를 교차 점검할 필요가 있습니다."),
        (("지연", "일정"), "사업 일정과 예산 집행 가능성의 정합성을 점검할 필요가 있습니다."),
        (("계획", "사전"), "선행 계획과 예산 편성 시점의 적정성을 확인할 필요가 있습니다."),
        (("불용", "집행률", "미집행"), "집행 실적과 향후 집행계획의 실현 가능성을 확인할 필요가 있습니다."),
        (("효과", "성과", "실효성"), "성과지표가 사업 목적과 직접 연결되는지 검토할 필요가 있습니다."),
    ]
    evidence_text = " ".join(item["text"] for item in selected)
    review_points = []
    for terms, message in signal_rules:
        if any(term in evidence_text for term in terms):
            related = next((item for item in selected if any(term in item["text"] for term in terms)), selected[0])
            review_points.append(f"- {message} [{related['rank']}]")
    lines.append("## 근거 기반 검토 포인트")
    lines.extend(review_points[:5] or ["- 현재 검색 근거만으로 추가 시사점을 확정하기 어렵습니다. 관련 원문 범위를 넓혀 확인해 주세요."])
    lines.extend(["", "## 출처"])
    for rank, hit in enumerate(hits[:5], start=1):
        page = f" · {hit.get('pageNumber')}쪽" if hit.get("pageNumber") else ""
        lines.append(f"- [{rank}] {hit.get('filename') or '등록 자료'}{page}")
    lines.extend(["", "※ 이 초안은 외부 전송 없이 등록 자료의 검색 근거를 재구성한 결과입니다. 최종 제출 전 원문과 수치를 확인하세요."])
    return "\n".join(lines).strip()


def _build_structured_report_artifact(
    title: str,
    content: str,
    intent: str,
    *,
    fact_snapshot: dict | None = None,
    generated_by: list[str] | None = None,
) -> dict:
    snapshot = fact_snapshot if isinstance(fact_snapshot, dict) else {}
    template = TEMPLATE_REPORT_STYLE_MCP.select(intent)
    report_document = REPORT_DOCUMENT_MCP.parse(
        content,
        title=title,
        style_profile=template["styleProfile"],
        facts=snapshot.get("facts") or {},
    )
    report_document = TEMPLATE_REPORT_STYLE_MCP.apply(report_document, template, snapshot)
    validation = REPORT_DOCUMENT_MCP.validate(report_document)
    report_document["validation"] = validation
    if not validation.get("passed"):
        raise ApiError("보고서 구조 검증에 실패했습니다: " + ", ".join(validation.get("errors") or []), 422)
    normalized = REPORT_DOCUMENT_MCP.compile_markdown(report_document)
    report_document["normalizedMarkdown"] = normalized
    quality_review = _review_report_against_request(intent, normalized, [])
    resolved_title = str(report_document.get("title") or title or "AIWorks 파생 보고서").strip()
    report_hwpx = REPORT_HWPX_MCP.build(resolved_title, normalized, template.get("rendererProfile") or "standard")
    safe_name = re.sub(r'[\\/:*?"<>|]+', "_", resolved_title).strip(" .")[:80] or "AIWorks_파생_보고서"
    generated = list(generated_by or [])
    generated.extend(["document.report-structure@0.1.0", "document.quality-harness@0.1.0", "template.report-style@0.1.0", "document.report-hwpx@0.1.0"])
    return {
        "title": resolved_title,
        "content": normalized,
        "sourceOfTruth": {"format": "markdown", "persistence": "project-version", "status": "pending-workflow-persist"},
        "sourceMarkdown": str(content or ""),
        "reportDocument": report_document,
        "qualityReview": quality_review,
        "template": template,
        "factSnapshot": report_document.get("factSnapshot") or {},
        "filename": safe_name + ".hwpx",
        "format": "hwpx",
        "mediaType": "application/hwp+zip",
        "contentBase64": base64.b64encode(report_hwpx).decode("ascii"),
        "editorMcp": "document.rhwp@1.0.0",
        "generatedBy": list(dict.fromkeys(item for item in generated if item)),
    }


def _rag_report_artifact(query: str, hits: list[dict], package_ref: str = "", synthesized_content: str = "", fact_snapshot: dict | None = None) -> dict:
    # The model's H1 is authoritative. If it omits H1, keep a neutral title
    # instead of copying the full imperative request and appending "보고서".
    title = "데이터 MCP 근거 분석 보고서"
    content = str(synthesized_content or "").strip() or _rag_evidence_report(query, hits, include_title=False)
    return _build_structured_report_artifact(
        title,
        content,
        query,
        fact_snapshot=fact_snapshot,
        generated_by=[package_ref],
    )



_TEMPLATE_PLACEHOLDERS = (
    "{{title}}", "{{content}}", "{{body}}", "{{date}}", "{{source_filename}}",
    "{{department}}", "{{author}}", "{{document_number}}", "{{approval_line}}",
)
_TEMPLATE_INSTRUCTION_PATTERN = re.compile(r"(작성\s*(?:요령|방법|안내)|입력(?:하세요|란)|기재(?:하세요|란)|※\s*작성|삭제\s*후\s*작성)")
_TEMPLATE_EXAMPLE_PATTERN = re.compile(r"(?:^|[\[<(（])\s*(?:예시|작성\s*예|sample)(?:[\]>）):：]|$)", re.IGNORECASE)
_TEMPLATE_SAMPLE_TITLE_PATTERN = re.compile(r"^(?:보고서\s*)?제목$|^제목\s*(?:입력|작성)$")
_TEMPLATE_SAMPLE_BODY_PATTERN = re.compile(r"(?:대제목|소제목|핵심\s*내용|세부내용|설명\s*내용|참조내용)")
_TEMPLATE_SAMPLE_CLEAR_PATTERN = re.compile(r"^(?:<표제목>|\(단위\s*:.*\)|항목\d+|내용\d+)$")


def _xml_local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def _hwpx_paragraph_nodes(xml_data: bytes) -> tuple[ElementTree.Element, list[tuple[ElementTree.Element, str]]]:
    root = ElementTree.fromstring(xml_data)
    paragraphs = []
    for node in root.iter():
        if _xml_local_name(node.tag) != "p":
            continue
        text = "".join(str(item.text or "") for item in node.iter() if _xml_local_name(item.tag) == "t").strip()
        paragraphs.append((node, text))
    return root, paragraphs


def _analyze_hwpx_template(data: bytes) -> dict:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise ApiError("양식 원본이 유효한 HWPX가 아닙니다.", 415) from error
    texts = []
    blank_count = 0
    table_count = 0
    with archive:
        for info in archive.infolist():
            if not re.fullmatch(r"Contents/section\d+\.xml", info.filename, flags=re.IGNORECASE):
                continue
            root, paragraphs = _hwpx_paragraph_nodes(archive.read(info.filename))
            texts.extend(text for _, text in paragraphs if text)
            blank_count += sum(1 for _, text in paragraphs if not text)
            table_count += sum(1 for node in root.iter() if _xml_local_name(node.tag) in {"tbl", "table"})
    joined = "\n".join(texts)
    placeholders = [token for token in _TEMPLATE_PLACEHOLDERS if token in joined]
    instruction_count = sum(1 for text in texts if _TEMPLATE_INSTRUCTION_PATTERN.search(text))
    example_count = sum(1 for text in texts if _TEMPLATE_EXAMPLE_PATTERN.search(text))
    body_candidates = sum(1 for text in texts if len(text) >= 20 and not _TEMPLATE_INSTRUCTION_PATTERN.search(text))
    placeholder_slots = {token[2:-2] for token in placeholders}
    required_slots_ready = "title" in placeholder_slots and bool({"content", "body"} & placeholder_slots)
    if required_slots_ready:
        mode, confidence = "explicit-placeholders", 0.98
        notice = "명시된 제목·본문 필드에 현재 보고서 내용을 대응합니다."
    elif placeholders:
        mode, confidence = "partial-placeholders", 0.58
        missing = "제목" if "title" not in placeholder_slots else "본문"
        notice = f"{missing} 슬롯이 없습니다. 일반 HWPX 변환 또는 RHWP 확인이 필요합니다."
    elif instruction_count or example_count:
        mode, confidence = "guided-fields", min(0.9, 0.62 + instruction_count * 0.06 + example_count * 0.05)
        notice = "작성요령·예시 문구를 입력 필드로 해석하고 고정 서식은 유지합니다."
    else:
        mode, confidence = "sample-structure", (0.72 if body_candidates >= 2 else 0.48)
        notice = "완성본의 제목·본문 스타일을 구조 템플릿으로 사용합니다."
    return {
        "mode": mode,
        "confidence": round(confidence, 2),
        "placeholders": placeholders,
        "instructionParagraphs": instruction_count,
        "exampleParagraphs": example_count,
        "blankParagraphs": blank_count,
        "bodyCandidates": body_candidates,
        "tables": table_count,
        "notice": notice,
        "reviewRequired": (not required_slots_ready) if placeholders else confidence < 0.6,
    }


def _hwpx_template_schema(data: bytes) -> dict:
    """Return the explicit authoring contract embedded in a HWPX template."""
    occurrences = []
    table_count = 0
    table_schemas = []
    structural_markers = {"heading": 0, "main": 0, "sub": 0, "note": 0}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            if not re.fullmatch(r"Contents/section\d+\.xml", info.filename, flags=re.IGNORECASE):
                continue
            root, paragraphs = _hwpx_paragraph_nodes(archive.read(info.filename))
            tables = [node for node in root.iter() if _xml_local_name(node.tag) in {"tbl", "table"}]
            table_count += len(tables)
            for table_index, table in enumerate(tables):
                rows = [node for node in table.iter() if _xml_local_name(node.tag) == "tr"]
                cells = [node for node in table.iter() if _xml_local_name(node.tag) in {"tc", "cell"}]
                merged_cells = 0
                for cell in cells:
                    span = next((item for item in cell.iter() if _xml_local_name(item.tag) == "cellSpan"), None)
                    attributes = span.attrib if span is not None else cell.attrib
                    try:
                        row_span = int(attributes.get("rowSpan") or 1)
                        col_span = int(attributes.get("colSpan") or 1)
                    except (TypeError, ValueError):
                        row_span, col_span = 1, 1
                    if row_span > 1 or col_span > 1:
                        merged_cells += 1
                table_text = _hwpx_node_text(table)
                approval_like = bool(re.search(r"(결재|담당|검토|협조|과장|국장|실장|승인)", table_text))
                table_schemas.append({
                    "locator": f"{info.filename}#table{table_index}",
                    "section": info.filename,
                    "tableIndex": table_index,
                    "rows": len(rows),
                    "cells": len(cells),
                    "mergedCells": merged_cells,
                    "approvalLike": approval_like,
                    "preview": re.sub(r"\s+", " ", table_text).strip()[:180],
                })
            for index, (_node, text) in enumerate(paragraphs):
                if re.match(r"^\s*□", text):
                    structural_markers["heading"] += 1
                elif re.match(r"^\s*[○ㅇ]", text):
                    structural_markers["main"] += 1
                elif re.match(r"^\s*[-·]", text):
                    structural_markers["sub"] += 1
                elif re.match(r"^\s*[※*]", text):
                    structural_markers["note"] += 1
                for token in _TEMPLATE_PLACEHOLDERS:
                    if token in text:
                        occurrences.append({"slot": token[2:-2], "token": token, "section": info.filename, "paragraphIndex": index})
    slots = {item["slot"] for item in occurrences}
    body_slot = "content" if "content" in slots else ("body" if "body" in slots else "")
    required = {"title": "title" in slots, "body": bool(body_slot), "bodySlot": body_slot or None}
    repeaters = {
        "sections": bool(body_slot),
        "lists": bool(structural_markers["main"] or structural_markers["sub"] or structural_markers["note"]),
        "tables": bool(table_count),
    }
    return {
        "contractVersion": "1.1",
        "slots": occurrences,
        "required": required,
        "repeaters": repeaters,
        "structuralMarkers": structural_markers,
        "templateTables": table_count,
        "metadataSlots": [item for item in occurrences if item["slot"] in {"date", "source_filename", "department", "author", "document_number"}],
        "tables": table_schemas,
        "approvalBlocks": [item for item in table_schemas if item["approvalLike"]],
        "mergedTables": [item for item in table_schemas if item["mergedCells"] > 0],
        "migration": {"from": "1.0", "to": "1.1", "automatic": True},
        "structuralBindingReady": bool(required["title"] and required["body"] and repeaters["sections"]),
    }


def _build_template_authoring_sample(template: bytes, filename: str) -> tuple[bytes, dict]:
    """Create an explicit, RHWP-editable starter from an attached report form."""
    profile = _analyze_hwpx_template(template)
    if profile["mode"] == "explicit-placeholders":
        schema = _hwpx_template_schema(template)
        return template, {
            "source": filename,
            "generated": False,
            "analysis": profile,
            "schema": schema,
            "inference": {"title": "explicit-placeholder", "body": "explicit-placeholder", "prototypes": [], "ready": bool(schema.get("structuralBindingReady"))},
        }
    try:
        source_archive = zipfile.ZipFile(io.BytesIO(template))
    except zipfile.BadZipFile as error:
        raise ApiError("첨부된 양식 원본이 유효한 HWPX가 아닙니다.", 415) from error
    section_payloads = {}
    title_targets = []
    body_targets = []
    blank_targets = []
    section_models = []
    leaf_records = []
    record_order = 0
    with source_archive:
        infos = source_archive.infolist()
        for info in infos:
            if not re.fullmatch(r"Contents/section\d+\.xml", info.filename, flags=re.IGNORECASE):
                continue
            original = source_archive.read(info.filename)
            root, paragraphs = _hwpx_paragraph_nodes(original)
            section_models.append((info.filename, original, root, paragraphs))
            for node, text_value in paragraphs:
                is_leaf = not any(item is not node and _xml_local_name(item.tag) == "p" for item in node.iter())
                if not is_leaf:
                    continue
                parents = {child: parent for parent in root.iter() for child in parent}
                cursor = node
                inside_table = False
                while cursor in parents:
                    cursor = parents[cursor]
                    if _xml_local_name(cursor.tag) in {"tbl", "table"}:
                        inside_table = True
                        break
                leaf_records.append({
                    "node": node, "text": text_value, "order": record_order,
                    "section": info.filename, "insideTable": inside_table,
                })
                record_order += 1
                if _TEMPLATE_SAMPLE_TITLE_PATTERN.search(text_value):
                    title_targets.append(node)
                elif _TEMPLATE_SAMPLE_BODY_PATTERN.search(text_value) or _TEMPLATE_INSTRUCTION_PATTERN.search(text_value) or _TEMPLATE_EXAMPLE_PATTERN.search(text_value):
                    body_targets.append(node)
                elif not text_value:
                    blank_targets.append(node)
        title_strategy = "explicit-label"
        body_strategy = "explicit-guide"
        if not title_targets:
            def title_score(record: dict) -> int:
                text_value = str(record.get("text") or "").strip()
                if not text_value or _TEMPLATE_INSTRUCTION_PATTERN.search(text_value) or _TEMPLATE_EXAMPLE_PATTERN.search(text_value):
                    return -1000
                if re.match(r"^(?:작성일|시행일|담당부서|담당자|수신|참조|붙임|문서번호)\s*[:：]", text_value):
                    return -1000
                score = max(0, 30 - int(record.get("order") or 0))
                if re.search(r"(?:보고서|계획서|요구서|검토서|결과서|현황|개선방안|추진계획)$", text_value):
                    score += 60
                if 4 <= len(text_value) <= 100:
                    score += 15
                if "|" in text_value or re.match(r"^[□○ㅇ※\-*·]", text_value):
                    score -= 80
                return score
            title_record = max(leaf_records, key=title_score, default=None)
            if not title_record or title_score(title_record) < 0:
                raise ApiError("일반 HWPX에서 제목 후보를 찾지 못했습니다. 제목 문구가 있는 보고서를 첨부하거나 RHWP 시작 양식을 사용해 주세요.", 409)
            title_targets = [title_record["node"]]
            title_strategy = "heuristic-report-title"
        title_records = [item for item in leaf_records if item["node"] in title_targets]
        title_record = next((item for item in reversed(title_records) if not item.get("insideTable")), None)
        if title_record is None:
            title_record = title_records[-1] if title_records else None
        title_node = title_record["node"] if title_record else title_targets[-1]
        title_record = next((item for item in leaf_records if item["node"] is title_node), None)
        body_targets = [node for node in body_targets if node is not title_node]
        if not body_targets:
            title_order = int((title_record or {}).get("order", -1))
            body_records = [
                item for item in leaf_records
                if int(item.get("order") or 0) > title_order
                and not item.get("insideTable")
                and str(item.get("text") or "").strip()
                and not re.match(r"^(?:작성일|시행일|담당부서|담당자|수신|참조|붙임|문서번호)\s*[:：]", str(item.get("text") or "").strip())
            ]
            preferred = next((item for item in body_records if re.match(r"^[□○ㅇ※\-*·]", str(item.get("text") or "").strip())), None)
            selected_body = preferred or next((item for item in body_records if len(str(item.get("text") or "").strip()) >= 8), None)
            if selected_body:
                body_targets = [selected_body["node"]]
                body_strategy = "heuristic-first-content"
            else:
                body_targets = [
                    item["node"] for item in leaf_records
                    if int(item.get("order") or 0) > title_order
                    and not item.get("insideTable")
                    and not str(item.get("text") or "").strip()
                ][:1]
                body_strategy = "heuristic-blank-field"
        if not body_targets:
            raise ApiError("일반 HWPX에서 본문 시작 위치를 찾지 못했습니다. 본문 예시나 빈 입력 문단을 하나 이상 포함해 주세요.", 409)
        for duplicate_title in title_targets:
            if duplicate_title is not title_node:
                _set_hwpx_paragraph_text(duplicate_title, "")
        _set_hwpx_paragraph_text(title_node, "{{title}}")
        _set_hwpx_paragraph_text(body_targets[0], "{{content}}")
        prototype_labels = []
        if title_strategy.startswith("heuristic") or body_strategy.startswith("heuristic"):
            body_record = next((item for item in leaf_records if item["node"] is body_targets[0]), None)
            body_order = int((body_record or {}).get("order", -1))
            body_section = str((body_record or {}).get("section") or "")
            remaining = [
                item for item in leaf_records
                if int(item.get("order") or 0) > body_order
                and str(item.get("section") or "") == body_section
                and not item.get("insideTable")
                and str(item.get("text") or "").strip()
                and not re.match(r"^(?:작성일|시행일|담당부서|담당자|수신|참조|붙임|문서번호)\s*[:：]", str(item.get("text") or "").strip())
            ]
            marker_specs = (
                (r"^\s*[○ㅇ]", "○ 소제목", "main"),
                (r"^\s*[-·]", "- 세부내용", "sub"),
                (r"^\s*[※*]", "※ 참조내용", "note"),
            )
            used_nodes = {body_targets[0]}
            for pattern, label, role in marker_specs:
                record = next((item for item in remaining if item["node"] not in used_nodes and re.match(pattern, str(item.get("text") or ""))), None)
                if record:
                    _set_hwpx_paragraph_text(record["node"], label)
                    used_nodes.add(record["node"])
                    prototype_labels.append(role)
            if remaining:
                boundary = remaining[-1]
                if boundary["node"] not in used_nodes:
                    _set_hwpx_paragraph_text(boundary["node"], "※ 참조내용")
                    used_nodes.add(boundary["node"])
                    prototype_labels.append("body-boundary")
            title_order = int((title_record or {}).get("order", -1))
            protected_nodes = {title_node, body_targets[0], *used_nodes}
            for record in leaf_records:
                text_value = str(record.get("text") or "").strip()
                if record.get("insideTable") or record["node"] in protected_nodes:
                    continue
                if int(record.get("order") or 0) <= title_order:
                    protected_nodes.add(record["node"])
                    continue
                if re.match(r"^(?:작성일|원본\s*파일)\s*[:：]", text_value):
                    protected_nodes.add(record["node"])
                    continue
                _set_hwpx_paragraph_text(record["node"], "")
            table_prototype_used = False
            for section_filename, _original, root, _paragraphs in section_models:
                for table in (item for item in root.iter() if _xml_local_name(item.tag) in {"tbl", "table"}):
                    table_paragraphs = [
                        item for item in table.iter()
                        if _xml_local_name(item.tag) == "p"
                        and not any(child is not item and _xml_local_name(child.tag) == "p" for child in item.iter())
                    ]
                    contains_title = any(item is title_node for item in table_paragraphs)
                    use_as_prototype = section_filename == body_section and not table_prototype_used and not contains_title
                    if not use_as_prototype:
                        for paragraph in table_paragraphs:
                            if paragraph is not title_node:
                                _set_hwpx_paragraph_text(paragraph, "")
                        continue
                    rows = [item for item in table.iter() if _xml_local_name(item.tag) == "tr"]
                    for row_index, row in enumerate(rows):
                        cells = [item for item in list(row) if _xml_local_name(item.tag) in {"tc", "cell"}]
                        for column_index, cell in enumerate(cells):
                            cell_paragraphs = [
                                item for item in cell.iter()
                                if _xml_local_name(item.tag) == "p"
                                and not any(child is not item and _xml_local_name(child.tag) == "p" for child in item.iter())
                            ]
                            for paragraph_index, paragraph in enumerate(cell_paragraphs):
                                label = (("항목" if row_index == 0 else "내용") + str(column_index + 1)) if paragraph_index == 0 else ""
                                _set_hwpx_paragraph_text(paragraph, label)
                                protected_nodes.add(paragraph)
                    if rows:
                        table_prototype_used = True
                        prototype_labels.append("table")
            for _section_filename, _original, root, _paragraphs in section_models:
                parents = {child: parent for parent in root.iter() for child in parent}
                for text_node in (item for item in root.iter() if _xml_local_name(item.tag) == "t"):
                    if re.fullmatch(r"(?:다각형|사각형|그림|개체)입니다\.?", str(text_node.text or "").strip()):
                        text_node.text = ""
                    cursor = text_node
                    paragraph = None
                    while cursor in parents:
                        cursor = parents[cursor]
                        if _xml_local_name(cursor.tag) == "p":
                            paragraph = cursor
                            break
                    if paragraph is not None and paragraph not in protected_nodes:
                        text_node.text = ""
        for section_filename, original, root, paragraphs in section_models:
            for node, text_value in paragraphs:
                if "작성일" in text_value and "{{date}}" not in text_value:
                    _set_hwpx_paragraph_text(node, re.sub(r"작성일\s*[:：]?\s*.*", "작성일: {{date}}", text_value))
                elif "원본 파일" in text_value and "{{source_filename}}" not in text_value:
                    _set_hwpx_paragraph_text(node, re.sub(r"원본\s*파일\s*[:：]?\s*.*", "원본 파일: {{source_filename}}", text_value))
            section_payloads[section_filename] = _serialize_hwpx_xml(original, root)
        output = io.BytesIO()
        preview = "{{title}}\n{{content}}\n작성일: {{date}}\n원본 파일: {{source_filename}}".encode("utf-8")
        with zipfile.ZipFile(output, "w") as target:
            for info in infos:
                data = section_payloads.get(info.filename, source_archive.read(info.filename))
                if info.filename == "Preview/PrvText.txt":
                    data = preview
                target.writestr(info, data)
    result = output.getvalue()
    analyzed = _analyze_hwpx_template(result)
    schema = _hwpx_template_schema(result)
    return result, {
        "source": filename,
        "generated": True,
        "analysis": analyzed,
        "schema": schema,
        "inference": {
            "title": title_strategy, "body": body_strategy,
            "prototypes": list(dict.fromkeys(prototype_labels)), "ready": bool(schema.get("structuralBindingReady")),
        },
    }



def _safe_office_archive(data: bytes) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise ApiError("Office Open XML 파일이 유효한 ZIP 패키지가 아닙니다.", 415) from error
    infos = archive.infolist()
    if sum(max(0, int(item.file_size)) for item in infos) > MAX_UNCOMPRESSED_BYTES:
        archive.close()
        raise ApiError("압축 해제된 Office 문서가 50MB를 넘습니다.", 413)
    if any(item.filename.startswith("/") or ".." in Path(item.filename).parts for item in infos):
        archive.close()
        raise ApiError("Office 문서에 안전하지 않은 내부 경로가 있습니다.", 415)
    return archive


def _extract_docx_parts(data: bytes) -> list[tuple[int | None, str]]:
    archive = _safe_office_archive(data)
    with archive:
        if "word/document.xml" not in archive.namelist():
            raise ApiError("DOCX 본문 XML을 찾을 수 없습니다.", 415)
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    paragraphs = []
    for node in root.iter():
        if _xml_local_name(node.tag) != "p":
            continue
        text = "".join(str(item.text or "") for item in node.iter() if _xml_local_name(item.tag) == "t").strip()
        if text:
            paragraphs.append(text)
    text = "\n".join(paragraphs)
    return [(None, text)] if text else []


def _extract_xlsx_parts(data: bytes) -> list[tuple[int | None, str]]:
    archive = _safe_office_archive(data)
    parts = []
    with archive:
        names = set(archive.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [
                "".join(str(item.text or "") for item in node.iter() if _xml_local_name(item.tag) == "t")
                for node in root.iter() if _xml_local_name(node.tag) == "si"
            ]
        sheet_names = sorted(
            name for name in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
        )
        for sheet_index, name in enumerate(sheet_names, 1):
            root = ElementTree.fromstring(archive.read(name))
            rows = []
            for row in (item for item in root.iter() if _xml_local_name(item.tag) == "row"):
                values = []
                for cell in (item for item in row if _xml_local_name(item.tag) == "c"):
                    cell_type = str(cell.attrib.get("t") or "")
                    value_node = next((item for item in cell.iter() if _xml_local_name(item.tag) == "v"), None)
                    inline_text = "".join(str(item.text or "") for item in cell.iter() if _xml_local_name(item.tag) == "t")
                    value = inline_text if cell_type == "inlineStr" else str(value_node.text or "") if value_node is not None else ""
                    if cell_type == "s" and value.isdigit() and int(value) < len(shared):
                        value = shared[int(value)]
                    values.append(value)
                if any(value.strip() for value in values):
                    rows.append("\t".join(values))
            if rows:
                parts.append((sheet_index, "\n".join(rows)))
    return parts

def _inspect_builder_reference(filename: str, data: bytes) -> tuple[str, dict]:
    extension = Path(filename).suffix.lower()
    if extension == ".hwpx":
        parsed = parse_hwpx(data, filename)
        extracted_text = "\n".join(item["text"] for item in parsed["paragraphs"] if item.get("text"))
        chunks = _chunk_reference_text("inspection", filename, hashlib.sha256(data).hexdigest(), [(None, extracted_text)])
        template_profile = _analyze_hwpx_template(data)
        return "application/hwp+zip", {
            "kind": "hwpx",
            "paragraphs": parsed["stats"]["paragraphs"],
            "commonDataCandidates": len(parsed["commonDataCandidates"]),
            "characters": len(extracted_text),
            "chunks": len(chunks),
            "ragReady": bool(chunks),
            "templateProfile": template_profile,
            "templateSchema": _hwpx_template_schema(data),
            "excerpt": extracted_text[:2_000] or "검색 가능한 텍스트 없음 · 스캔 PDF는 OCR 후 등록해 주세요.",
        }
    if extension == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise ApiError("확장자와 PDF 파일 내용이 일치하지 않습니다.")
        if b"/Encrypt" in data:
            raise ApiError("암호화된 PDF는 기준 문서로 등록할 수 없습니다.", 415)
        pages = _extract_pdf_pages(data)
        chunks = _chunk_reference_text("inspection", filename, hashlib.sha256(data).hexdigest(), pages)
        extracted_text = "\n".join(text for _, text in pages)
        return "application/pdf", {
            "kind": "pdf",
            "pagesDetected": len(re.findall(rb"/Type\s*/Page\b", data)),
            "pagesWithText": len(pages),
            "characters": len(extracted_text),
            "chunks": len(chunks),
            "ragReady": bool(chunks),
            "excerpt": extracted_text[:2_000],
        }
    if extension in {".docx", ".xlsx"}:
        parts = _extract_docx_parts(data) if extension == ".docx" else _extract_xlsx_parts(data)
        extracted_text = "\n\n".join(text for _index, text in parts)
        chunks = _chunk_reference_text("inspection", filename, hashlib.sha256(data).hexdigest(), parts)
        return (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if extension == ".docx"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            {
                "kind": extension[1:],
                "sections": len(parts),
                "characters": len(extracted_text),
                "chunks": len(chunks),
                "ragReady": bool(chunks),
                "excerpt": extracted_text[:2_000],
                "externalTransfer": False,
            },
        )

    if extension in {".md", ".txt"}:
        if b"\x00" in data:
            raise ApiError("텍스트 기준 문서에 바이너리 데이터가 포함되어 있습니다.")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ApiError("텍스트 기준 문서는 UTF-8이어야 합니다.") from error
        chunks = _chunk_reference_text("inspection", filename, hashlib.sha256(data).hexdigest(), [(None, text)])
        return ("text/markdown" if extension == ".md" else "text/plain"), {
            "kind": "text",
            "lines": len(text.splitlines()),
            "characters": len(text),
            "chunks": len(chunks),
            "ragReady": bool(chunks),
            "excerpt": text[:2_000],
        }
    raise ApiError("기준 문서는 HWPX, PDF, DOCX, XLSX, Markdown 또는 TXT만 지원합니다.", 415)


def add_mcp_draft_reference(draft_id: str, payload: dict) -> dict:
    ensure_schema()
    filename = str(payload.get("filename") or "").strip()
    if not filename or Path(filename).name != filename or filename in {".", ".."}:
        raise ApiError("안전한 기준 문서 파일 이름이 필요합니다.")
    encoded = str(payload.get("content_base64") or "")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as error:
        raise ApiError("content_base64가 올바르지 않습니다.") from error
    if not data:
        raise ApiError("기준 문서 내용이 비어 있습니다.")
    if len(data) > MAX_ASSET_BYTES:
        raise ApiError(f"기준 문서는 파일당 {MAX_ASSET_BYTES:,}바이트를 넘을 수 없습니다.", 413)
    media_type, summary = _inspect_builder_reference(filename, data)
    digest = hashlib.sha256(data).hexdigest()
    actor = _actor(payload)
    with _connect() as db:
        draft = db.execute("SELECT * FROM mcp_drafts WHERE id=?", (draft_id,)).fetchone()
        if not draft:
            raise ApiError("MCP draft를 찾을 수 없습니다.", 404)
        if draft["status"] == "published":
            raise ApiError("게시된 draft에는 기준 문서를 추가할 수 없습니다.", 409)
        manifest = _load_json(draft["manifest_json"], {})
        mcp_type = str(manifest.get("mcpType") or "tool")
        type_contract = MCP_BUILDER_TYPES.get(mcp_type, MCP_BUILDER_TYPES["tool"])
        role = str(payload.get("role") or "").strip()
        if not role:
            role = "template-source" if mcp_type == "template" and Path(filename).suffix.lower() == ".hwpx" else type_contract["referenceRoles"][0]
        if role not in type_contract["referenceRoles"]:
            raise ApiError(f"{type_contract['label']}에서 지원하지 않는 첨부 역할입니다: {role}")
        if role == "template-source" and Path(filename).suffix.lower() != ".hwpx":
            raise ApiError("양식 원본은 HWPX 파일 하나만 등록할 수 있습니다.", 415)
        summary = {**summary, "builderRole": role}
        superseded_reference_ids = []
        if role == "template-source":
            superseded_reference_ids = [
                item["id"] for item in db.execute(
                    "SELECT * FROM mcp_draft_references WHERE draft_id=?",
                    (draft_id,),
                ).fetchall()
                if _load_json(item["summary_json"], {}).get("builderRole") == "template-source"
            ]
            if superseded_reference_ids:
                db.executemany("DELETE FROM mcp_draft_references WHERE id=?", [(item,) for item in superseded_reference_ids])

        existing = db.execute(
            "SELECT * FROM mcp_draft_references WHERE draft_id=? AND sha256=?",
            (draft_id, digest),
        ).fetchone()
        if existing:
            return {"draft": _draft_row_result(draft), "reference": _reference_row_result(existing), "idempotent": True}
        reference_id = "ref_" + uuid.uuid4().hex
        now = utc_now()
        db.execute(
            "INSERT INTO mcp_draft_references(id,draft_id,filename,media_type,bytes,sha256,summary_json,content_blob,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (reference_id, draft_id, filename, media_type, len(data), digest, _json(summary), data, now),
        )
        manifest["references"] = [
            {
                "id": item["id"],
                "filename": item["filename"],
                "mediaType": item["media_type"],
                "bytes": item["bytes"],
                "sha256": item["sha256"],
                "role": _load_json(item["summary_json"], {}).get("builderRole", "guide"),
            }
            for item in db.execute(
                "SELECT * FROM mcp_draft_references WHERE draft_id=? ORDER BY created_at",
                (draft_id,),
            ).fetchall()
        ]
        validation = {"passed": False, "tests": []}
        db.execute(
            "UPDATE mcp_drafts SET status='draft',manifest_json=?,validation_json=?,updated_at=? WHERE id=?",
            (_json(manifest), _json(validation), now, draft_id),
        )
        _audit(db, actor, "mcp.reference_added", {"draft_id": draft_id, "reference_id": reference_id, "filename": filename, "bytes": len(data), "sha256": digest, "external_transfer": False})
        updated = db.execute("SELECT * FROM mcp_drafts WHERE id=?", (draft_id,)).fetchone()
        reference = db.execute("SELECT * FROM mcp_draft_references WHERE id=?", (reference_id,)).fetchone()
    return {"draft": _draft_row_result(updated), "reference": _reference_row_result(reference), "idempotent": False}

def delete_mcp_draft_reference(draft_id: str, reference_id: str, payload: dict) -> dict:
    ensure_schema()
    actor = _actor(payload)
    with _connect() as db:
        draft = db.execute("SELECT * FROM mcp_drafts WHERE id=?", (draft_id,)).fetchone()
        reference = db.execute("SELECT * FROM mcp_draft_references WHERE id=? AND draft_id=?", (reference_id, draft_id)).fetchone()
        if not draft:
            raise ApiError("MCP draft를 찾을 수 없습니다.", 404)
        if draft["status"] == "published":
            raise ApiError("게시된 draft의 첨부는 삭제할 수 없습니다. 스토어에서 수정 초안을 만드세요.", 409)
        if not reference:
            raise ApiError("삭제할 첨부 파일을 찾을 수 없습니다.", 404)
        summary = _load_json(reference["summary_json"], {})
        role = str(summary.get("builderRole") or "guide")
        filename = str(reference["filename"])
        db.execute("DELETE FROM mcp_draft_references WHERE id=?", (reference_id,))
        remaining = db.execute(
            "SELECT * FROM mcp_draft_references WHERE draft_id=? ORDER BY created_at",
            (draft_id,),
        ).fetchall()
        manifest = _load_json(draft["manifest_json"], {})
        manifest["references"] = [
            {
                "id": item["id"],
                "filename": item["filename"],
                "mediaType": item["media_type"],
                "bytes": item["bytes"],
                "sha256": item["sha256"],
                "role": _load_json(item["summary_json"], {}).get("builderRole", "guide"),
            }
            for item in remaining
        ]
        if role == "template-source":
            guide = manifest.get("builderGuide") if isinstance(manifest.get("builderGuide"), dict) else {}
            remaining_templates = [
                item for item in remaining
                if _load_json(item["summary_json"], {}).get("builderRole") == "template-source"
            ]
            if remaining_templates:
                active_summary = _load_json(remaining_templates[-1]["summary_json"], {})
                guide["templateProfile"] = active_summary.get("templateProfile") or {}
                guide["templateSchema"] = active_summary.get("templateSchema") or {}
            else:
                guide.pop("templateProfile", None)
                guide.pop("templateSchema", None)
            manifest["builderGuide"] = guide
        validation = {"passed": False, "tests": []}
        now = utc_now()
        db.execute(
            "UPDATE mcp_drafts SET status='draft',manifest_json=?,validation_json=?,updated_at=? WHERE id=?",
            (_json(manifest), _json(validation), now, draft_id),
        )
        _audit(db, actor, "mcp.reference_deleted", {"draft_id": draft_id, "reference_id": reference_id, "filename": filename, "role": role, "external_transfer": False})
        updated = db.execute("SELECT * FROM mcp_drafts WHERE id=?", (draft_id,)).fetchone()
    return {"draft": _draft_row_result(updated), "deleted": {"id": reference_id, "filename": filename, "role": role}}

def _draft_rag_chunks(db: sqlite3.Connection, draft_id: str) -> list[dict]:
    rows = db.execute(
        "SELECT * FROM mcp_draft_references WHERE draft_id=? ORDER BY created_at",
        (draft_id,),
    ).fetchall()
    chunks = []
    for row in rows:
        summary = _load_json(row["summary_json"], {})
        if summary.get("builderRole") != "data-source":
            continue
        chunks.extend(
            _reference_rag_chunks(
                row["id"], row["filename"], row["media_type"], row["sha256"], bytes(row["content_blob"])
            )
        )
    return chunks


def query_mcp_draft_rag(draft_id: str, payload: dict) -> dict:
    ensure_schema()
    query = str(payload.get("query") or payload.get("intent") or "").strip()
    limit = max(1, min(8, int(payload.get("limit") or 5)))
    with _connect() as db:
        draft = db.execute("SELECT * FROM mcp_drafts WHERE id=?", (draft_id,)).fetchone()
        if not draft:
            raise ApiError("MCP draft를 찾을 수 없습니다.", 404)
        manifest = _load_json(draft["manifest_json"], {})
        if manifest.get("mcpType") != "data":
            raise ApiError("RAG 검색 테스트는 데이터 MCP에서 사용할 수 있습니다.", 409)
        chunks = _draft_rag_chunks(db, draft_id)
        hits = _search_rag_chunks(chunks, query, limit=limit)
        _audit(
            db,
            _actor(payload),
            "mcp.draft_rag_queried",
            {"draft_id": draft_id, "query": query[:500], "chunks": len(chunks), "hits": len(hits), "external_transfer": False},
        )
    result = {
        "draftId": draft_id,
        "query": query,
        "answer": _rag_extract_answer(query, hits),
        "hits": [_rag_hit_result(item, index) for index, item in enumerate(hits, start=1)],
        "index": {"chunks": len(chunks), "references": len({item["referenceId"] for item in chunks})},
        "mode": "local-evidence-preview",
    }
    if payload.get("report") is True:
        result.update({
            "responseType": "report-artifact",
            "artifact": _rag_report_artifact(query, hits),
            "loadedMcps": ["builder.data-rag", "document.report-hwpx@0.1.0", "document.rhwp@1.0.0"],
        })
    return result


def _index_package_rag(db: sqlite3.Connection, manifest: dict) -> int:
    package_id = str(manifest.get("id") or "")
    version = str(manifest.get("version") or "")
    db.execute("DELETE FROM mcp_reference_chunks WHERE package_id=? AND version=?", (package_id, version))
    if manifest.get("mcpType") != "data":
        return 0
    references = {
        item.get("id"): item
        for item in manifest.get("references") or []
        if isinstance(item, dict) and item.get("role") == "data-source"
    }
    indexed = 0
    for row in db.execute(
        "SELECT * FROM mcp_package_files WHERE package_id=? AND version=? ORDER BY reference_id",
        (package_id, version),
    ).fetchall():
        if row["reference_id"] not in references:
            continue
        chunks = _reference_rag_chunks(
            row["reference_id"], row["filename"], row["media_type"], row["sha256"], bytes(row["content_blob"])
        )
        for item in chunks:
            db.execute(
                """
                INSERT INTO mcp_reference_chunks(
                    package_id,version,reference_id,chunk_index,filename,page_number,
                    content,search_text,sha256
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    package_id,
                    version,
                    item["referenceId"],
                    item["chunkIndex"],
                    item["filename"],
                    item["pageNumber"],
                    item["content"],
                    item["searchText"],
                    item["sha256"],
                ),
            )
            indexed += 1
    return indexed


def _package_rag_chunks(package_id: str, version: str) -> list[dict]:
    with _connect() as db:
        rows = db.execute(
            "SELECT * FROM mcp_reference_chunks WHERE package_id=? AND version=? ORDER BY reference_id,chunk_index",
            (package_id, version),
        ).fetchall()
    return [
        {
            "referenceId": row["reference_id"],
            "chunkIndex": row["chunk_index"],
            "filename": row["filename"],
            "pageNumber": row["page_number"],
            "content": row["content"],
            "searchText": row["search_text"],
            "sha256": row["sha256"],
        }
        for row in rows
    ]


def _builder_package_id(name: str, requested: str = "") -> str:
    if requested:
        package_id = requested.strip().lower()
    else:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        # Korean names commonly end in the English label "MCP". Treating that
        # lone token as a meaningful slug made every such package ``org.mcp``.
        if not slug or slug == "mcp":
            slug = "mcp-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:10]
        package_id = "org." + slug
    if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", package_id):
        raise ApiError("MCP ID는 영문 소문자, 숫자, 점과 하이픈만 사용할 수 있습니다.")
    return package_id


def _resolve_builder_package_identity(db: sqlite3.Connection, manifest: dict) -> dict | None:
    """Move a draft away from an ID already owned by a different MCP.

    Older builder versions allowed generic IDs such as ``org.mcp`` to be
    reused. Package identity spans every version, so comparing only the exact
    version at publish time produces a confusing "already published" error.
    """
    package_id = str(manifest.get("id") or "").strip()
    rows = db.execute(
        "SELECT version,manifest_json FROM mcp_packages WHERE package_id=? ORDER BY version DESC",
        (package_id,),
    ).fetchall()
    if not rows:
        return None
    derived_from = str(manifest.get("derivedFrom") or "")
    if derived_from.startswith(package_id + "@"):
        return None
    existing_names = sorted(
        {
            str(_load_json(row["manifest_json"], {}).get("name") or package_id)
            for row in rows
        }
    )
    draft_name = str(manifest.get("name") or package_id).strip()
    if draft_name in existing_names:
        return None

    base = _builder_package_id(draft_name, "")
    candidate = base
    suffix = 2
    while db.execute("SELECT 1 FROM mcp_packages WHERE package_id=?", (candidate,)).fetchone():
        candidate = f"{base}-{suffix}"
        suffix += 1
    manifest["id"] = candidate
    return {
        "previousPackageId": package_id,
        "packageId": candidate,
        "reason": "package-id-owned-by-different-mcp",
        "existingNames": existing_names,
    }


def _builder_lines(value, *, limit: int = 20) -> list[str]:
    if isinstance(value, list):
        candidates = [str(item) for item in value]
    else:
        candidates = str(value or "").replace("\r\n", "\n").split("\n")
    return [
        re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", item).strip()[:500]
        for item in candidates
        if item.strip()
    ][:limit]


def list_mcp_builder_types() -> dict:
    return {
        "items": [
            {
                "id": type_id,
                "label": contract["label"],
                "capabilities": contract["capabilities"],
                "referenceRoles": contract["referenceRoles"],
            }
            for type_id, contract in MCP_BUILDER_TYPES.items()
        ]
    }


def builder_template_starter() -> dict:
    artifact = REPORT_HWPX_MCP.build(
        "{{title}}",
        "{{content}}\n\n작성일: {{date}}\n원본 파일: {{source_filename}}",
    )
    return {
        "filename": "AIWorks_양식MCP_시작양식.hwpx",
        "mediaType": "application/hwp+zip",
        "contentBase64": base64.b64encode(artifact).decode("ascii"),
        "placeholders": ["{{title}}", "{{content}}", "{{body}}", "{{date}}", "{{source_filename}}"],
        "notice": "한글에서 서식과 고정 문구를 편집하되 플레이스홀더 문자열은 유지한 뒤 양식 원본으로 등록하세요.",
    }




def _template_draft_source(draft_id: str) -> tuple[sqlite3.Row, sqlite3.Row | None]:
    with _connect() as db:
        draft = db.execute("SELECT * FROM mcp_drafts WHERE id=?", (draft_id,)).fetchone()
        if not draft:
            raise ApiError("MCP draft를 찾을 수 없습니다.", 404)
        manifest = _load_json(draft["manifest_json"], {})
        if manifest.get("mcpType") != "template":
            raise ApiError("양식 제작 세션은 양식 MCP 초안에서만 사용할 수 있습니다.", 409)
        if draft["status"] == "published":
            raise ApiError("게시된 MCP는 스토어의 수정 기능으로 새 버전 초안을 만든 뒤 편집해 주세요.", 409)
        references = db.execute(
            "SELECT * FROM mcp_draft_references WHERE draft_id=? ORDER BY created_at DESC",
            (draft_id,),
        ).fetchall()
        sources = [
            item for item in references
            if _load_json(item["summary_json"], {}).get("builderRole") == "template-source"
            and str(item["filename"]).lower().endswith(".hwpx")
        ]
        if len(sources) > 1:
            raise ApiError(f"양식 기준 HWPX가 {len(sources)}개입니다. 첨부 목록에서 하나만 남긴 뒤 변환해 주세요.", 409)
        source = sources[0] if sources else None

    return draft, source


def build_mcp_template_sample(draft_id: str) -> dict:
    draft, source = _template_draft_source(draft_id)
    if source:
        artifact, authoring = _build_template_authoring_sample(
            bytes(source["content_blob"]), str(source["filename"])
        )
        stem = Path(str(source["filename"])).stem
        filename = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", stem)[:80] + "_양식등록.hwpx"
        reference_id = source["id"]
    else:
        starter = builder_template_starter()
        artifact = base64.b64decode(starter["contentBase64"], validate=True)
        authoring = {
            "source": starter["filename"],
            "generated": True,
            "analysis": _analyze_hwpx_template(artifact),

            "schema": _hwpx_template_schema(artifact),
        }
        filename = starter["filename"]
        reference_id = None
    return {
        "draftId": draft_id,
        "referenceId": reference_id,
        "filename": filename,
        "mediaType": "application/hwp+zip",
        "contentBase64": base64.b64encode(artifact).decode("ascii"),
        "authoring": authoring,
        "notice": "RHWP에서 고정 문구와 서식을 수정하되 {{title}}과 {{content}}는 유지한 뒤 ‘수정 완료·초안 반영’을 누르세요.",
    }


def evaluate_mcp_template_quality(draft_id: str) -> dict:
    """Render and parse a draft template without changing the draft."""
    sample = build_mcp_template_sample(draft_id)
    artifact = base64.b64decode(sample["contentBase64"], validate=True)
    quality = _evaluate_hwpx_template_quality(artifact, sample["filename"])
    return {
        "draftId": draft_id,
        "referenceId": sample.get("referenceId"),
        "filename": sample["filename"],
        "quality": quality,
        "notice": "테스트 ReportDocument를 실제 양식에 렌더링하고 다시 파싱한 결과입니다.",
    }



def _template_mapping_candidates(data: bytes) -> dict:
    """Expose stable paragraph locators for the visual TemplateSchema corrector."""
    candidates = []
    current_slots = {}
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise ApiError("양식 원본이 유효한 HWPX가 아닙니다.", 415) from error
    with archive:
        for info in archive.infolist():
            if not re.fullmatch(r"Contents/section\d+\.xml", info.filename, flags=re.IGNORECASE):
                continue
            root, paragraphs = _hwpx_paragraph_nodes(archive.read(info.filename))
            tables = [item for item in root.iter() if _xml_local_name(item.tag) in {"tbl", "table"}]
            parents = {child: parent for parent in root.iter() for child in parent}
            for index, (node, text_value) in enumerate(paragraphs):
                if any(item is not node and _xml_local_name(item.tag) == "p" for item in node.iter()):
                    continue
                cursor = node
                inside_table = False
                table_locator = ""
                table_merged = False
                approval_like = False
                while cursor in parents:
                    cursor = parents[cursor]
                    if _xml_local_name(cursor.tag) in {"tbl", "table"}:
                        inside_table = True
                        table_locator = f"{info.filename}#table{tables.index(cursor)}"
                        for cell in (item for item in cursor.iter() if _xml_local_name(item.tag) in {"tc", "cell"}):
                            span = next((item for item in cell.iter() if _xml_local_name(item.tag) == "cellSpan"), None)
                            attributes = span.attrib if span is not None else cell.attrib
                            try:
                                row_span = int(attributes.get("rowSpan") or 1)
                                col_span = int(attributes.get("colSpan") or 1)
                            except (TypeError, ValueError):
                                row_span, col_span = 1, 1
                            table_merged = table_merged or row_span > 1 or col_span > 1
                        approval_like = bool(re.search(r"(결재|담당|검토|협조|과장|국장|실장|승인)", _hwpx_node_text(cursor)))
                        break
                locator = f"{info.filename}#p{index}"
                slots = [token[2:-2] for token in _TEMPLATE_PLACEHOLDERS if token in text_value]
                for slot in slots:
                    current_slots[slot] = locator
                candidates.append({
                    "locator": locator,
                    "section": info.filename,
                    "paragraphIndex": index,
                    "text": text_value,
                    "preview": text_value[:140] or "(빈 문단)",
                    "insideTable": inside_table,
                    "tableLocator": table_locator or None,
                    "tableMerged": table_merged,
                    "approvalLike": approval_like,
                    "paraStyleId": str(node.attrib.get("paraPrIDRef") or ""),
                    "slots": slots,
                })
    if not candidates:
        raise ApiError("양식에서 보정 가능한 문단을 찾지 못했습니다.", 409)
    return {"candidates": candidates[:500], "currentSlots": current_slots, "total": len(candidates)}


def get_mcp_template_mapping(draft_id: str) -> dict:
    _draft, source = _template_draft_source(draft_id)
    if source is None:
        raise ApiError("먼저 HWPX를 양식 원본 역할로 첨부해 주세요.", 409)
    artifact = bytes(source["content_blob"])
    return {
        "draftId": draft_id,
        "referenceId": source["id"],
        "filename": source["filename"],
        "mapping": _template_mapping_candidates(artifact),
        "schema": _hwpx_template_schema(artifact),
        "profile": _analyze_hwpx_template(artifact),
        "notice": "제목과 본문은 서로 다른 문단으로 지정하세요. 목록 원형은 비워 두면 현재 양식에서 자동 감지합니다.",
    }



def apply_mcp_template_mapping(draft_id: str, payload: dict) -> dict:
    """Apply user-selected paragraph slots, then reuse the normal commit/quality gate."""
    _draft, source = _template_draft_source(draft_id)
    if source is None:
        raise ApiError("먼저 HWPX를 양식 원본 역할로 첨부해 주세요.", 409)
    title_locator = str(payload.get("title_locator") or "").strip()
    body_locator = str(payload.get("body_locator") or "").strip()
    if not title_locator or not body_locator:
        raise ApiError("제목 슬롯과 본문 슬롯을 모두 선택해 주세요.")
    if title_locator == body_locator:
        raise ApiError("제목 슬롯과 본문 슬롯은 서로 다른 문단이어야 합니다.")
    prototype_values = {
        str(payload.get("main_locator") or "").strip(): "○ 소제목",
        str(payload.get("sub_locator") or "").strip(): "- 세부내용",
        str(payload.get("note_locator") or "").strip(): "※ 참조내용",
    }
    prototype_values.pop("", None)
    metadata_values = {
        str(payload.get("department_locator") or "").strip(): "{{department}}",
        str(payload.get("author_locator") or "").strip(): "{{author}}",
        str(payload.get("document_number_locator") or "").strip(): "{{document_number}}",
        str(payload.get("approval_locator") or "").strip(): "{{approval_line}}",
    }
    metadata_values.pop("", None)
    selected_pairs = [(title_locator, "{{title}}"), (body_locator, "{{content}}"), *prototype_values.items(), *metadata_values.items()]
    selected_locators = [locator for locator, _value in selected_pairs]
    if len(selected_locators) != len(set(selected_locators)):
        raise ApiError("하나의 문단에 둘 이상의 TemplateSchema 역할을 지정할 수 없습니다.")
    selected = dict(selected_pairs)
    artifact = bytes(source["content_blob"])
    available = {item["locator"] for item in _template_mapping_candidates(artifact)["candidates"]}
    missing = sorted(locator for locator in selected if locator not in available)
    if missing:
        raise ApiError("선택한 문단 위치가 현재 양식과 일치하지 않습니다: " + ", ".join(missing[:3]), 409)
    if title_locator in prototype_values or body_locator in prototype_values:
        raise ApiError("제목·본문 문단은 목록 서식 원형으로 동시에 지정할 수 없습니다.")
    source_archive = zipfile.ZipFile(io.BytesIO(artifact))
    output = io.BytesIO()
    with source_archive:
        infos = source_archive.infolist()
        with zipfile.ZipFile(output, "w") as target:
            for info in infos:
                data = source_archive.read(info.filename)
                if re.fullmatch(r"Contents/section\d+\.xml", info.filename, flags=re.IGNORECASE):
                    root, paragraphs = _hwpx_paragraph_nodes(data)
                    for text_node in (item for item in root.iter() if _xml_local_name(item.tag) == "t" and item.text):
                        for token in ("{{title}}", "{{content}}", "{{body}}"):
                            text_node.text = text_node.text.replace(token, "")
                    for index, (node, _text_value) in enumerate(paragraphs):
                        locator = f"{info.filename}#p{index}"
                        if locator in selected:
                            _set_hwpx_paragraph_text(node, selected[locator])
                    data = _serialize_hwpx_xml(data, root)
                target.writestr(info, data)
    corrected = output.getvalue()
    session = open_native_document_session({
        "filename": str(source["filename"]),
        "content_base64": base64.b64encode(corrected).decode("ascii"),
        "intent": "TemplateSchema 시각 보정 결과 반영",
        "session_purpose": "template-authoring",
        "builder_draft_id": draft_id,
        "builder_reference_id": source["id"],
        "confirmed": True,
        "actor": _actor(payload),
    })
    committed = commit_mcp_template_authoring(
        draft_id, {"session_id": session["id"], "actor": _actor(payload)}
    )
    with _connect() as db:
        _audit(db, _actor(payload), "mcp.template_mapping_corrected", {
            "draft_id": draft_id,
            "reference_id": source["id"],
            "title_locator": title_locator,
            "body_locator": body_locator,
            "prototype_locators": sorted(prototype_values),
            "metadata_locators": {value[2:-2]: locator for locator, value in metadata_values.items()},
            "quality": (committed.get("authoring") or {}).get("quality") or {},
        })
    return {
        **committed,
        "mapping": get_mcp_template_mapping(draft_id)["mapping"],
        "notice": "선택한 슬롯을 반영하고 실제 ReportDocument 렌더링·재파싱 검증을 통과했습니다.",
    }


def convert_mcp_template_source(draft_id: str, payload: dict) -> dict:
    """Convert an ordinary HWPX into the draft's active template source."""
    _draft, source = _template_draft_source(draft_id)
    if source is None:
        raise ApiError("먼저 일반 HWPX를 양식 원본 역할로 첨부해 주세요.", 409)
    sample = build_mcp_template_sample(draft_id)
    session = open_native_document_session(
        {
            "filename": sample["filename"],
            "content_base64": sample["contentBase64"],
            "intent": "일반 HWPX를 양식 MCP 등록용 HWPX로 자동 변환",
            "session_purpose": "template-authoring",
            "builder_draft_id": draft_id,
            "builder_reference_id": sample["referenceId"] or "",
            "confirmed": True,
            "actor": _actor(payload),
        }
    )
    committed = commit_mcp_template_authoring(
        draft_id,
        {"session_id": session["id"], "actor": _actor(payload)},
    )
    conversion = {
        "sourceFilename": str(source["filename"]),
        "sourceSha256": str(source["sha256"]),
        "outputFilename": sample["filename"],
        "generated": bool(sample["authoring"].get("generated")),
        "analysis": sample["authoring"].get("analysis") or {},
        "schema": sample["authoring"].get("schema") or {},
        "inference": sample["authoring"].get("inference") or {},
        "externalTransfer": False,
    }
    with _connect() as db:
        _audit(
            db,
            _actor(payload),
            "mcp.template_source_converted",
            {
                "draft_id": draft_id,
                "source_filename": conversion["sourceFilename"],
                "source_sha256": conversion["sourceSha256"],
                "output_filename": conversion["outputFilename"],
                "generated": conversion["generated"],
                "structural_binding_ready": bool(conversion["schema"].get("structuralBindingReady")),
                "external_transfer": False,
            },
        )
    return {
        **committed,
        "filename": sample["filename"],
        "mediaType": sample["mediaType"],
        "contentBase64": sample["contentBase64"],
        "conversion": conversion,
        "notice": "변환본을 현재 초안의 유일한 양식 원본으로 반영했습니다. 다운로드하거나 RHWP에서 확인·수정한 뒤 검증하세요.",
    }


def open_mcp_template_authoring_session(draft_id: str, payload: dict) -> dict:
    sample = build_mcp_template_sample(draft_id)
    session = open_native_document_session(
        {
            "filename": sample["filename"],
            "content_base64": sample["contentBase64"],
            "intent": "양식 MCP 등록용 HWPX를 RHWP에서 편집",
            "session_purpose": "template-authoring",
            "builder_draft_id": draft_id,
            "builder_reference_id": sample["referenceId"] or "",
            "confirmed": True,
            "actor": _actor(payload),
        }
    )
    session["templateAuthoring"] = {
        "draftId": draft_id,
        "referenceId": sample["referenceId"],
        "notice": sample["notice"],
        "analysis": sample["authoring"]["analysis"],
        "schema": sample["authoring"]["schema"],
        "inference": sample["authoring"].get("inference") or {},
    }
    return session


def commit_mcp_template_authoring(draft_id: str, payload: dict) -> dict:
    session_id = str(payload.get("session_id") or "").strip()
    if not re.fullmatch(r"docsession_[a-f0-9]+", session_id):
        raise ApiError("양식 수정 세션 ID가 올바르지 않습니다.")
    with _connect() as db:
        draft = db.execute("SELECT * FROM mcp_drafts WHERE id=?", (draft_id,)).fetchone()
        session = db.execute("SELECT * FROM native_document_sessions WHERE id=?", (session_id,)).fetchone()
        if not draft:
            raise ApiError("MCP draft를 찾을 수 없습니다.", 404)
        if not session:
            raise ApiError("양식 수정 세션을 찾을 수 없습니다.", 404)
        manifest = _load_json(draft["manifest_json"], {})
        analysis = _load_json(session["intent_json"], {})
        if manifest.get("mcpType") != "template":
            raise ApiError("양식 MCP 초안이 아닙니다.", 409)
        if draft["status"] == "published":
            raise ApiError("게시된 MCP에는 수정본을 반영할 수 없습니다.", 409)
        if analysis.get("sessionPurpose") != "template-authoring" or analysis.get("builderDraftId") != draft_id:
            raise ApiError("이 RHWP 세션은 현재 양식 MCP 초안의 수정 세션이 아닙니다.", 409)
        artifact = bytes(session["artifact_blob"])
        filename = str(session["filename"])
        if not filename.lower().endswith(".hwpx"):
            raise ApiError("양식 등록용 수정본은 HWPX여야 합니다.", 415)
        media_type, summary = _inspect_builder_reference(filename, artifact)
        profile = summary.get("templateProfile") or {}
        schema = summary.get("templateSchema") or {}
        required = schema.get("required") if isinstance(schema, dict) else {}
        if profile.get("reviewRequired") or not required.get("title") or not required.get("body"):
            raise ApiError("양식 수정본에 {{title}}과 {{content}} 또는 {{body}} 슬롯이 모두 필요합니다.", 409)
        template_quality = _evaluate_hwpx_template_quality(artifact, filename)
        if not template_quality.get("passed"):
            failures = [item["detail"] for item in template_quality.get("checks") or [] if not item.get("passed")]
            raise ApiError("양식 실렌더링 검증에 실패했습니다: " + "; ".join(failures[:3]), 409)
        summary = {
            **summary,
            "builderRole": "template-source",
            "authoringSessionId": session_id,
            "templateQuality": template_quality,
        }
        digest = hashlib.sha256(artifact).hexdigest()
        reference_id = str(analysis.get("builderReferenceId") or "")
        reference = db.execute(
            "SELECT * FROM mcp_draft_references WHERE id=? AND draft_id=?",
            (reference_id, draft_id),
        ).fetchone() if reference_id else None
        previous_sha = str(reference["sha256"]) if reference else None
        now = utc_now()
        if reference:
            db.execute(
                "UPDATE mcp_draft_references SET filename=?,media_type=?,bytes=?,sha256=?,summary_json=?,content_blob=?,created_at=? WHERE id=?",
                (filename, media_type, len(artifact), digest, _json(summary), artifact, now, reference_id),
            )
        else:
            reference_id = "ref_" + uuid.uuid4().hex
            db.execute(
                "INSERT INTO mcp_draft_references(id,draft_id,filename,media_type,bytes,sha256,summary_json,content_blob,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (reference_id, draft_id, filename, media_type, len(artifact), digest, _json(summary), artifact, now),
            )
        superseded_reference_ids = [
            item["id"] for item in db.execute(
                "SELECT * FROM mcp_draft_references WHERE draft_id=? AND id<>?",
                (draft_id, reference_id),
            ).fetchall()
            if _load_json(item["summary_json"], {}).get("builderRole") == "template-source"
        ]
        if superseded_reference_ids:
            db.executemany("DELETE FROM mcp_draft_references WHERE id=?", [(item,) for item in superseded_reference_ids])
        guide = manifest.get("builderGuide") if isinstance(manifest.get("builderGuide"), dict) else {}
        guide["templateSchema"] = schema
        guide["templateProfile"] = profile
        guide["templateQuality"] = template_quality
        guide["authoringVersion"] = "1.0"
        manifest["builderGuide"] = guide
        manifest["references"] = [
            {
                "id": item["id"],
                "filename": item["filename"],
                "mediaType": item["media_type"],
                "bytes": item["bytes"],
                "sha256": item["sha256"],
                "role": _load_json(item["summary_json"], {}).get("builderRole", "guide"),
            }
            for item in db.execute(
                "SELECT * FROM mcp_draft_references WHERE draft_id=? ORDER BY created_at",
                (draft_id,),
            ).fetchall()
        ]
        validation = {"passed": False, "tests": []}
        db.execute(
            "UPDATE mcp_drafts SET status='draft',manifest_json=?,validation_json=?,updated_at=? WHERE id=?",
            (_json(manifest), _json(validation), now, draft_id),
        )
        _audit(
            db,
            _actor(payload),
            "mcp.template_authoring_committed",
            {
                "draft_id": draft_id,
                "reference_id": reference_id,
                "session_id": session_id,
                "previous_sha256": previous_sha,
                "sha256": digest,
                "superseded_reference_ids": superseded_reference_ids,
                "slots": [item.get("slot") for item in schema.get("slots") or []],
                "template_quality": template_quality.get("metrics") or {},
                "external_transfer": False,
            },
        )
        updated = db.execute("SELECT * FROM mcp_drafts WHERE id=?", (draft_id,)).fetchone()
        updated_reference = db.execute("SELECT * FROM mcp_draft_references WHERE id=?", (reference_id,)).fetchone()
    return {
        "draft": _draft_row_result(updated),
        "reference": _reference_row_result(updated_reference),
        "authoring": {"sessionId": session_id, "schema": schema, "analysis": profile, "quality": template_quality},
    }

def create_mcp_draft(payload: dict) -> dict:
    ensure_schema()
    name = str(payload.get("name") or "").strip()
    description = str(payload.get("description") or "").strip()
    if len(name) < 2 or len(name) > 120:
        raise ApiError("MCP 이름은 2자 이상 120자 이하여야 합니다.")
    if len(description) < 10 or len(description) > 4_000:
        raise ApiError("MCP 업무 설명은 10자 이상 4,000자 이하여야 합니다.")
    version = str(payload.get("version") or "0.1.0").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ApiError("MCP 버전은 정확한 SemVer여야 합니다.")
    visibility = str(payload.get("visibility") or "private")
    if visibility not in {"private", "organization", "public"}:
        raise ApiError("지원하지 않는 공개 범위입니다.")
    source_included = payload.get("source_included", False)
    if not isinstance(source_included, bool):
        raise ApiError("source_included는 boolean이어야 합니다.")
    allow_external = payload.get("allow_external", False)
    if not isinstance(allow_external, bool):
        raise ApiError("allow_external은 boolean이어야 합니다.")
    mcp_type = str(payload.get("mcp_type") or "tool").strip().lower()
    if mcp_type not in MCP_BUILDER_TYPES:
        raise ApiError("MCP 유형은 template, process, data, tool, external 중 하나여야 합니다.")
    type_contract = MCP_BUILDER_TYPES[mcp_type]
    external_transport = str(payload.get("external_transport") or "streamable-http").strip().lower()
    if mcp_type == "external" and external_transport not in {"streamable-http", "stdio"}:
        raise ApiError("외부 MCP 전송 방식은 streamable-http 또는 stdio여야 합니다.")
    instructions = str(payload.get("instructions") or description).strip()
    if len(instructions) < 10 or len(instructions) > 8_000:
        raise ApiError("실행 지침은 10자 이상 8,000자 이하여야 합니다.")
    cautions = _builder_lines(payload.get("cautions"))
    procedure = _builder_lines(payload.get("procedure")) or [description[:500]]
    trigger_examples = _builder_lines(payload.get("trigger_examples"), limit=10)
    data_source = str(payload.get("data_source") or "").strip()[:500]
    use_model = payload.get("use_model")
    if use_model is None:
        use_model = any(term in description.lower() for term in ("요약", "분석", "생성", "검증", "제안", "변경"))
    if not isinstance(use_model, bool):
        raise ApiError("use_model은 boolean이어야 합니다.")
    package_id = _builder_package_id(name, str(payload.get("package_id") or ""))
    lowered = description.lower()
    permissions = []

    def permission(scope: str, reason: str) -> None:
        if not any(item[0] == scope for item in permissions):
            permissions.append((scope, reason))

    document_work = mcp_type == "template" or any(term in lowered for term in ("문서", "예산", "양식", "hwpx", "pdf"))
    if document_work:
        permission("document.read", "입력 문서와 선택 영역 분석")
    if mcp_type == "template" or any(term in lowered for term in ("생성", "작성", "수정", "변경", "제안", "초안")):
        permission("document.write", "사용자 승인 후 변경안 생성")
    common_data = mcp_type == "data" or any(term in lowered for term in ("공통데이터", "기준값", "현재 값", "예산", "대가"))
    if common_data:
        permission("common-data.read", "업무 기준값과 출처 조회")
    if use_model:
        permission("model.invoke", "구조화된 업무 결과 생성")
    if mcp_type == "external":
        allow_external = external_transport == "streamable-http"
        permission("document.read", "현재 보고서 산출물을 연결 도구 입력으로 읽기")
        permission("document.write", "외부 MCP가 반환한 산출물을 새 revision으로 저장")
    if allow_external:
        permission("network.send", "사용자가 승인한 최소 데이터의 외부 전송")
    dependencies = []
    supports = []
    if document_work:
        dependencies.append("document.hwpx@1.2.0")
        supports.extend([".hwpx", ".pdf"])
    if common_data:
        dependencies.append("common-data.registry@1.1.0")
    manifest = _package_manifest(package_id, name, version, "hybrid" if allow_external else "local", description, permissions, dependencies=dependencies, supports=supports)
    io_contracts = {
        "template": (
            {"sourceArtifact": {"type": "object"}, "requestContext": {"type": "object"}},
            {"formattedArtifact": {"type": "object"}, "applicationGuide": {"type": "object"}},
        ),
        "process": (
            {"request": {"type": "object"}, "context": {"type": "object"}},
            {"result": {"type": "object"}, "checkpoints": {"type": "array"}},
        ),
        "data": (
            {"query": {"type": "string"}, "filters": {"type": "object"}, "asOf": {"type": "string"}},
            {"records": {"type": "array"}, "sources": {"type": "array"}},
        ),
        "tool": (
            {"request": {"type": "object"}},
            {"result": {"type": "object"}},
        ),
        "external": (
            {"request": {"type": "object"}, "artifact": {"type": "object"}},
            {"result": {"type": "object"}, "artifact": {"type": "object"}},
        ),
    }
    manifest["inputs"], manifest["outputs"] = io_contracts[mcp_type]
    manifest["mcpType"] = mcp_type
    manifest["capabilities"] = type_contract["capabilities"]
    manifest["builderGuide"] = {
        "version": "1.0",
        "instructions": instructions,
        "cautions": cautions,
        "procedure": procedure,
        "triggerExamples": trigger_examples,
        "dataSource": data_source,
        "useModel": use_model,
        "referenceRoles": type_contract["referenceRoles"],
    }
    if mcp_type == "data":
        manifest["retrieval"] = {
            "kind": "local-rag",
            "chunkSize": 1_200,
            "chunkOverlap": 180,
            "topK": 5,
            "citationRequired": True,
        }
    if mcp_type == "external":
        tool_name = str(payload.get("external_tool_name") or "").strip()
        capability_id = str(payload.get("external_capability") or "external.tool.invoke").strip().lower()
        if not re.fullmatch(r"[A-Za-z0-9_.:/-]{2,160}", tool_name):
            raise ApiError("외부 MCP에서 호출할 도구 이름이 필요합니다.")
        if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", capability_id):
            raise ApiError("외부 MCP Capability ID가 올바르지 않습니다.")
        manifest["capabilities"] = [capability_id]
        connector = {
            "contractVersion": "2025-03-26",
            "transport": external_transport,
            "toolName": tool_name,
            "documentTransfer": external_transport == "streamable-http",
        }
        if external_transport == "stdio":
            profile_id = str(payload.get("external_server_profile") or KORDOC_PROFILE_ID).strip()
            profile = EXTERNAL_MCP_SERVER_PROFILES.get(profile_id)
            if not profile:
                raise ApiError("승인되지 않은 로컬 MCP 서버 프로필입니다.", 403)
            adapter = profile["allowedTools"].get(tool_name)
            if not adapter:
                raise ApiError("이 서버 프로필에서 허용되지 않은 도구입니다.", 403)
            connector.update({"serverProfile": profile_id, "invocationAdapter": adapter})
            if tool_name == "generate_document":
                connector["preset"] = str(payload.get("external_preset") or "보고서").strip()[:40]
        else:
            endpoint_env = str(payload.get("external_endpoint_env") or "AIWORKS_EXTERNAL_MCP_URL").strip().upper()
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,80}", endpoint_env):
                raise ApiError("외부 MCP URL 환경변수 이름이 올바르지 않습니다.")
            connector.update(
                {
                    "endpointEnv": endpoint_env,
                    "inputMap": {
                        "filename": str(payload.get("external_input_filename") or "filename").strip(),
                        "contentBase64": str(payload.get("external_input_content") or "contentBase64").strip(),
                        "instruction": str(payload.get("external_input_instruction") or "instruction").strip(),
                    },
                    "outputContentPath": str(payload.get("external_output_content") or "contentBase64").strip(),
                    "outputFilenamePath": str(payload.get("external_output_filename") or "filename").strip(),
                }
            )
        manifest["externalMcp"] = connector
    manifest["executionAdapter"] = {
        "kind": "retrieval" if mcp_type == "data" else ("external-mcp" if mcp_type == "external" else ("composite" if mcp_type in {"template", "process"} else "prompt")),
        "version": "1.0",
        "entrypoint": "builder.rag" if mcp_type == "data" else ("external.tools.call" if mcp_type == "external" else "builder.guide"),
        "arbitraryCode": False,
    }
    manifest["visibility"] = visibility
    manifest["sourceIncluded"] = source_included
    draft_id = "draft_" + uuid.uuid4().hex
    now = utc_now()
    validation = {"passed": False, "tests": []}
    owner = _actor(payload)
    with _connect() as db:
        identity_adjustment = _resolve_builder_package_identity(db, manifest)
        if identity_adjustment:
            package_id = manifest["id"]
        db.execute("INSERT INTO mcp_drafts(id,owner,status,manifest_json,validation_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (draft_id, owner, "draft", _json(manifest), _json(validation), now, now))
        _audit(db, owner, "mcp.draft_created", {"draft_id": draft_id, "package_id": package_id, "visibility": visibility, "source_included": source_included})
        if identity_adjustment:
            _audit(db, owner, "mcp.package_id_reassigned", {"draft_id": draft_id, **identity_adjustment})
        row = db.execute("SELECT * FROM mcp_drafts WHERE id=?", (draft_id,)).fetchone()
    result = _draft_row_result(row)
    if identity_adjustment:
        result["identityAdjustment"] = identity_adjustment
    return result


def list_mcp_drafts() -> dict:
    ensure_schema()
    with _connect() as db:
        rows = db.execute("SELECT * FROM mcp_drafts ORDER BY updated_at DESC LIMIT 100").fetchall()
    return {"items": [_draft_row_result(row) for row in rows]}


def get_mcp_draft(draft_id: str) -> dict:
    ensure_schema()
    with _connect() as db:
        row = db.execute("SELECT * FROM mcp_drafts WHERE id=?", (draft_id,)).fetchone()
    if not row:
        raise ApiError("MCP draft를 찾을 수 없습니다.", 404)
    return _draft_row_result(row)


def validate_mcp_draft(draft_id: str, payload: dict) -> dict:
    ensure_schema()
    tests = []

    def test(test_id: str, passed: bool, detail: str) -> None:
        tests.append({"id": test_id, "passed": bool(passed), "detail": detail})

    with _connect() as db:
        row = db.execute("SELECT * FROM mcp_drafts WHERE id=?", (draft_id,)).fetchone()
        if not row:
            raise ApiError("MCP draft를 찾을 수 없습니다.", 404)
        if row["status"] == "published":
            raise ApiError("게시된 draft는 다시 검증할 수 없습니다.", 409)
        manifest = _load_json(row["manifest_json"], {})
        try:
            _validate_manifest(manifest, manifest.get("id", ""), manifest.get("version", ""))
            test("manifest.contract", True, "Manifest 필수 필드와 SemVer 유효")
        except ApiError as error:
            test("manifest.contract", False, str(error))
        dependencies = manifest.get("dependencies") or []
        pinned = all(re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*@\d+\.\d+\.\d+", str(item)) for item in dependencies)
        test("dependencies.pinned", pinned, f"고정 의존성 {len(dependencies)}개")
        scopes = [item.get("scope") for item in manifest.get("permissions") or [] if isinstance(item, dict)]
        test("permissions.allowlist", all(scope in STORE_PERMISSION_SCOPES for scope in scopes), f"최소권한 {len(scopes)}개")
        network_declared = "network.send" in scopes
        boundary_valid = (manifest.get("runtime") == "local" and not network_declared) or (manifest.get("runtime") in {"remote", "hybrid"} and network_declared)
        test("network.boundary", boundary_valid, "외부 전송 권한과 런타임 일치" if boundary_valid else "외부 전송 선언 불일치")
        test("io.schema", bool(manifest.get("inputs")) and bool(manifest.get("outputs")), "입출력 Schema 존재")
        reference_rows = db.execute(
            "SELECT * FROM mcp_draft_references WHERE draft_id=? ORDER BY created_at",
            (draft_id,),
        ).fetchall()
        reference_valid = all(
            hashlib.sha256(item["content_blob"]).hexdigest() == item["sha256"]
            for item in reference_rows
        )
        manifest_reference_hashes = {
            item.get("sha256") for item in manifest.get("references") or []
            if isinstance(item, dict)
        }
        stored_reference_hashes = {item["sha256"] for item in reference_rows}
        reference_valid = reference_valid and manifest_reference_hashes == stored_reference_hashes
        test("references.integrity", reference_valid, f"로컬 기준 문서 {len(reference_rows)}개 SHA-256 확인")
        mcp_type = str(manifest.get("mcpType") or "tool")
        guide = manifest.get("builderGuide") if isinstance(manifest.get("builderGuide"), dict) else {}
        roles = {
            _load_json(item["summary_json"], {}).get("builderRole", "guide")
            for item in reference_rows
        }
        type_valid = mcp_type in MCP_BUILDER_TYPES and len(str(guide.get("instructions") or "")) >= 10
        type_detail = f"{MCP_BUILDER_TYPES.get(mcp_type, MCP_BUILDER_TYPES['tool'])['label']} 실행 가이드 확인"
        if mcp_type == "template":
            template_sources = [
                item for item in reference_rows
                if _load_json(item["summary_json"], {}).get("builderRole") == "template-source"
            ]
            template_summary = _load_json(template_sources[-1]["summary_json"], {}) if len(template_sources) == 1 else {}
            template_profile = template_summary.get("templateProfile") or {}
            template_schema = template_summary.get("templateSchema") or {}
            template_required = template_schema.get("required") if isinstance(template_schema, dict) else {}
            template_quality = (
                _evaluate_hwpx_template_quality(bytes(template_sources[0]["content_blob"]), str(template_sources[0]["filename"]))
                if len(template_sources) == 1 else {"passed": False, "checks": [], "metrics": {}}
            )
            structure_valid = (
                len(template_sources) == 1
                and template_profile.get("reviewRequired") is False
                and template_required.get("title") is True
                and template_required.get("body") is True
                and template_schema.get("structuralBindingReady") is True
                and template_quality.get("passed") is True
            )
            structure_detail = (
                "제목·본문 슬롯과 반복 본문 구조 확인 · 양식용 HWPX 등록 완료"
                if structure_valid
                else "일반 HWPX를 양식용으로 변환한 뒤 RHWP에서 {{title}}과 {{content}} 또는 {{body}} 슬롯을 확인해 주세요."
            )
            test("template.structure", structure_valid, structure_detail)
            quality_metrics = template_quality.get("metrics") or {}
            test(
                "template.render-quality",
                template_quality.get("passed") is True,
                "실렌더링·재파싱 통과 · 본문 블록 {blocks}개 · 표 {tables}개 · 매핑률 {coverage:.0%}".format(
                    blocks=quality_metrics.get("renderedBlocks", 0),
                    tables=quality_metrics.get("renderedTables", 0),
                    coverage=float(quality_metrics.get("mappingCoverage") or 0),
                ) if template_quality.get("passed") else
                "테스트 문서를 양식에 렌더링한 결과가 구조 계약을 충족하지 못했습니다.",
            )
            type_valid = type_valid and structure_valid and manifest.get("sourceIncluded") is True
            type_detail = "양식 원본, 구조 슬롯, 반복 본문, 파일 포함, 변환 지침 확인" if type_valid else structure_detail
        elif mcp_type == "process":
            type_valid = type_valid and len(guide.get("procedure") or []) >= 2
            type_detail = "처리 순서 2단계 이상 확인"
        elif mcp_type == "data":
            rag_chunks = sum(
                int(_load_json(item["summary_json"], {}).get("chunks") or 0)
                for item in reference_rows
                if _load_json(item["summary_json"], {}).get("builderRole") == "data-source"
            )
            type_valid = (
                type_valid
                and bool(str(guide.get("dataSource") or "").strip())
                and "data-source" in roles
                and manifest.get("sourceIncluded") is True
                and rag_chunks > 0
            )
            if type_valid:
                type_detail = f"데이터 원본 포함 · 검색 청크 {rag_chunks}개 · 출처 인용 계약 확인"
            elif "data-source" not in roles:
                type_detail = "검색 데이터 원본이 없습니다. PDF를 첨부한 초안을 선택해 다시 검증하세요."
            elif manifest.get("sourceIncluded") is not True:
                type_detail = "데이터 MCP는 게시 패키지에 검색 원본을 포함해야 합니다."
            elif rag_chunks < 1:
                type_detail = "검색 가능한 텍스트 청크가 없습니다. 스캔 PDF는 OCR 후 다시 첨부하세요."
            else:
                type_detail = "데이터 출처와 조회 지침을 입력해 주세요."
        elif mcp_type == "external":
            connector = manifest.get("externalMcp") if isinstance(manifest.get("externalMcp"), dict) else {}
            transport = str(connector.get("transport") or "")
            tool_name = str(connector.get("toolName") or "")
            if transport == "stdio":
                profile_id = str(connector.get("serverProfile") or "")
                profile = EXTERNAL_MCP_SERVER_PROFILES.get(profile_id)
                status = _external_profile_status(profile_id)
                type_valid = (
                    type_valid
                    and bool(profile)
                    and profile["allowedTools"].get(tool_name) == connector.get("invocationAdapter")
                    and "network.send" not in scopes
                    and manifest.get("runtime") == "local"
                    and connector.get("documentTransfer") is False
                )
                type_detail = f"로컬 stdio · {profile_id} · 도구 {tool_name} · " + ("실행 준비됨" if status["available"] else "계약 통과, 런타임 설치 필요")
            else:
                endpoint_env = str(connector.get("endpointEnv") or "")
                type_valid = (
                    type_valid
                    and transport == "streamable-http"
                    and bool(re.fullmatch(r"[A-Z][A-Z0-9_]{2,80}", endpoint_env))
                    and bool(re.fullmatch(r"[A-Za-z0-9_.:/-]{2,160}", tool_name))
                    and "network.send" in scopes
                )
                configured = bool(os.getenv(endpoint_env, "").strip()) if endpoint_env else False
                type_detail = f"Streamable HTTP · 도구 {tool_name} · {endpoint_env} " + ("연결 주소 설정됨" if configured else "환경변수 설정 후 연결 테스트 필요")
        test("builder.type-guide", type_valid, type_detail)
        passed = all(item["passed"] for item in tests)
        validation = {"passed": passed, "tests": tests}
        status = "validated" if passed else "rejected"
        now = utc_now()
        db.execute("UPDATE mcp_drafts SET status=?,validation_json=?,updated_at=? WHERE id=?", (status, _json(validation), now, draft_id))
        _audit(db, _actor(payload), "mcp.draft_validated" if passed else "mcp.draft_rejected", {"draft_id": draft_id, "tests": tests})
        updated = db.execute("SELECT * FROM mcp_drafts WHERE id=?", (draft_id,)).fetchone()
    return _draft_row_result(updated)


def publish_mcp_draft(draft_id: str, payload: dict) -> dict:
    ensure_schema()
    actor = _actor(payload)
    with _connect() as db:
        row = db.execute("SELECT * FROM mcp_drafts WHERE id=?", (draft_id,)).fetchone()
        if not row:
            raise ApiError("MCP draft를 찾을 수 없습니다.", 404)
        if row["status"] != "validated":
            raise ApiError("샌드박스 검증을 통과한 draft만 게시할 수 있습니다.", 409)
        manifest = _load_json(row["manifest_json"], {})
        if payload.get("confirm_visibility") != manifest.get("visibility"):
            raise ApiError("MCP 공개 범위를 명시적으로 다시 확인해야 합니다.", 403)
        confirmed_source = payload.get("confirm_source_included")
        if not isinstance(confirmed_source, bool) or confirmed_source != manifest.get("sourceIncluded"):
            raise ApiError("원본 문서·소스 포함 여부를 명시적으로 다시 확인해야 합니다.", 403)
        identity_adjustment = _resolve_builder_package_identity(db, manifest)
        if identity_adjustment:
            db.execute(
                "UPDATE mcp_drafts SET manifest_json=?,updated_at=? WHERE id=?",
                (_json(manifest), utc_now(), draft_id),
            )
            _audit(db, actor, "mcp.package_id_reassigned", {"draft_id": draft_id, **identity_adjustment})
        package_id, version = manifest["id"], manifest["version"]
        existing = db.execute(
            "SELECT manifest_json FROM mcp_packages WHERE package_id=? AND version=?",
            (package_id, version),
        ).fetchone()
        if existing:
            existing_name = str(_load_json(existing["manifest_json"], {}).get("name") or package_id)
            raise ApiError(
                f"{package_id}@{version}은(는) 스토어의 ‘{existing_name}’에서 이미 사용 중입니다. "
                "스토어의 수정 기능으로 다음 버전을 만들거나 패키지 ID를 변경해 주세요.",
                409,
            )
        digest = _bundle_sha256(manifest)
        signature = _package_signature(package_id, version, digest)
        now = utc_now()
        db.execute("INSERT INTO mcp_packages(package_id,version,manifest_json,bundle_sha256,signature,publisher,published_at) VALUES(?,?,?,?,?,?,?)", (package_id, version, _json(manifest), digest, signature, actor, now))
        _index_package_capabilities(db, manifest)
        if manifest.get("sourceIncluded"):
            db.execute(
                """
                INSERT INTO mcp_package_files(package_id,version,reference_id,filename,media_type,bytes,sha256,content_blob)
                SELECT ?,?,id,filename,media_type,bytes,sha256,content_blob
                  FROM mcp_draft_references
                 WHERE draft_id=?
                """,
                (package_id, version, draft_id),
            )
        indexed_chunks = _index_package_rag(db, manifest)
        if manifest.get("mcpType") == "data" and indexed_chunks < 1:
            raise ApiError("데이터 MCP 게시 중 검색 인덱스를 만들지 못했습니다.", 409)
        db.execute("UPDATE mcp_drafts SET status='published',published_package_id=?,published_version=?,updated_at=? WHERE id=?", (package_id, version, now, draft_id))
        _audit(db, actor, "mcp.draft_published", {"draft_id": draft_id, "package_id": package_id, "version": version, "visibility": manifest["visibility"], "source_included": manifest["sourceIncluded"], "rag_chunks": indexed_chunks, "bundle_sha256": digest, "signature_verified": True})
        package_row = db.execute("SELECT * FROM mcp_packages WHERE package_id=? AND version=?", (package_id, version)).fetchone()
        updated = db.execute("SELECT * FROM mcp_drafts WHERE id=?", (draft_id,)).fetchone()
    result = {"draft": _draft_row_result(updated), "package": _verified_package(package_row)}
    if identity_adjustment:
        result["identityAdjustment"] = identity_adjustment
    return result


KNOWLEDGE_CLASSIFICATION_RANK = {"public": 0, "internal": 1, "confidential": 2, "personal": 3}
DEFAULT_PROJECT_ID = "project-default"


def _seed_knowledge(db: sqlite3.Connection) -> None:
    if db.execute("SELECT COUNT(*) AS count FROM knowledge_nodes").fetchone()["count"]:
        return
    sample = json.loads((ROOT / "sample-data" / "budget-request.json").read_text(encoding="utf-8"))
    now = utc_now()
    document_titles = {
        sample["document"]["id"]: sample["document"]["name"],
        "sw-cost-guide-2025": "SW사업 대가산정 가이드 2025",
        "sw-cost-guide-2026": "SW사업 대가산정 가이드 2026",
    }
    for document_id, title in document_titles.items():
        db.execute(
            "INSERT INTO knowledge_nodes(id,node_type,title,content,classification,metadata_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            ("document:" + document_id, "document", title, title, "internal", "{}", now, now),
        )
    for record in sample["commonData"]:
        versions = sorted(record["versions"], key=lambda item: item["effectiveDate"])
        current = versions[-1]
        node_id = "data:" + record["id"]
        content = f'{record["label"]}: {current["value"]}' + (f' {record.get("unit")}' if record.get("unit") else "")
        db.execute(
            "INSERT INTO knowledge_nodes(id,node_type,title,content,classification,metadata_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (node_id, "common-data", record["label"], content, "internal", _json(record), now, now),
        )
        for index, version in enumerate(versions, 1):
            source = version["source"]
            source_id = f"source:{record['id']}:{index}"
            db.execute(
                "INSERT INTO knowledge_sources(id,node_id,document_id,locator,excerpt,effective_date,confidence) VALUES(?,?,?,?,?,?,?)",
                (source_id, node_id, source["documentId"], source["locator"], source.get("excerpt", content), version["effectiveDate"], float(version["confidence"])),
            )
            target_id = "document:" + source["documentId"]
            if db.execute("SELECT 1 FROM knowledge_nodes WHERE id=?", (target_id,)).fetchone():
                db.execute(
                    "INSERT INTO knowledge_edges(id,source_node_id,target_node_id,relation,weight,evidence_source_id,created_at) VALUES(?,?,?,?,?,?,?)",
                    (f"edge:{record['id']}:{index}", node_id, target_id, "sourced_from", float(version["confidence"]), source_id, now),
                )
    note_id = "note:budget-cost-assumption"
    db.execute(
        "INSERT INTO knowledge_nodes(id,node_type,title,content,classification,metadata_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
        (note_id, "note", "예산 산정 기준 메모", "2026년 SW 기술자 월평균임금을 적용해 개발비 산출 근거를 갱신한다.", "internal", _json({"tags": ["예산", "SW대가", "갱신"]}), now, now),
    )
    db.execute(
        "INSERT INTO knowledge_sources(id,node_id,document_id,locator,excerpt,effective_date,confidence) VALUES(?,?,?,?,?,?,?)",
        ("source:note:budget-cost-assumption", note_id, "sw-cost-guide-2026", "표 2 > 중급기술자", "중급기술자 월평균임금 8,560,000원", "2026-01-01", 0.97),
    )
    db.execute(
        "INSERT INTO knowledge_edges(id,source_node_id,target_node_id,relation,weight,evidence_source_id,created_at) VALUES(?,?,?,?,?,?,?)",
        ("edge:note:uses-cost", note_id, "data:cost.engineer.monthly", "uses", 0.97, "source:note:budget-cost-assumption", now),
    )


def _seed_default_project_facts(db: sqlite3.Connection) -> None:
    now = utc_now()
    db.execute(
        "INSERT OR IGNORE INTO projects(id,name,owner,classification,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
        (DEFAULT_PROJECT_ID, "AIWorks 기본 프로젝트", "workspace-user", "internal", "active", now, now),
    )
    if not ENABLE_DEMO_SEED:
        return
    if db.execute("SELECT 1 FROM project_facts WHERE project_id=? LIMIT 1", (DEFAULT_PROJECT_ID,)).fetchone():
        return
    sample = json.loads((ROOT / "sample-data" / "budget-request.json").read_text(encoding="utf-8"))
    for record in sample.get("commonData") or []:
        fact_id = "fact_" + hashlib.sha256((DEFAULT_PROJECT_ID + "\0" + record["id"]).encode("utf-8")).hexdigest()[:24]
        db.execute(
            "INSERT INTO project_facts(id,project_id,fact_key,label,value_type,unit,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (fact_id, DEFAULT_PROJECT_ID, record["id"], record["label"], record.get("valueType") or "string", record.get("unit"), "confirmed", now, now),
        )
        for version in record.get("versions") or []:
            source = version.get("source") or {}
            value_id = "factvalue_" + hashlib.sha256((fact_id + "\0" + str(version.get("effectiveDate")) + "\0" + _json(version.get("value"))).encode("utf-8")).hexdigest()[:24]
            db.execute(
                "INSERT INTO project_fact_values(id,fact_id,value_json,effective_date,status,source_document_id,source_locator,source_excerpt,confidence,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (value_id, fact_id, _json(version.get("value")), version.get("effectiveDate"), "confirmed", source.get("documentId"), source.get("locator"), source.get("excerpt"), float(version.get("confidence") or 0), "system-bootstrap", now),
            )


def _safe_project_id(value: object) -> str:
    project_id = str(value or DEFAULT_PROJECT_ID).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,99}", project_id):
        raise ApiError("프로젝트 ID가 올바르지 않습니다.")
    return project_id


def list_projects() -> dict:
    """Return projects with enough state to render the mandatory workspace picker."""
    ensure_schema()
    with _connect() as db:
        rows = db.execute(
            """
            SELECT p.*,
                   (SELECT COUNT(*) FROM project_markdown_documents d
                     WHERE d.project_id=p.id AND d.status='active') AS document_count,
                   (SELECT COUNT(*) FROM project_facts f
                     WHERE f.project_id=p.id AND f.status='confirmed') AS fact_count,
                   (SELECT COUNT(*) FROM project_document_artifacts a
                     JOIN project_markdown_documents d ON d.id=a.document_id
                    WHERE d.project_id=p.id AND d.status='active') AS artifact_count,
                   COALESCE(
                     (SELECT MAX(d.updated_at) FROM project_markdown_documents d
                       WHERE d.project_id=p.id AND d.status='active'),
                     p.updated_at
                   ) AS last_activity_at
              FROM projects p
             WHERE p.status='active'
             ORDER BY last_activity_at DESC, p.created_at DESC
            """
        ).fetchall()
    return {
        "items": [
            {
                "id": row["id"],
                "name": row["name"],
                "owner": row["owner"],
                "classification": row["classification"],
                "status": row["status"],
                "documentCount": row["document_count"],
                "factCount": row["fact_count"],
                "artifactCount": row["artifact_count"],
                "createdAt": row["created_at"],
                "updatedAt": row["last_activity_at"],
            }
            for row in rows
        ]
    }


def create_project(payload: dict) -> dict:
    ensure_schema()
    name = re.sub(r"\s+", " ", str(payload.get("name") or "").strip())
    if len(name) < 2 or len(name) > 120:
        raise ApiError("프로젝트 이름은 2~120자로 입력해 주세요.")
    requested_id = str(payload.get("id") or "").strip()
    project_id = _safe_project_id(requested_id) if requested_id else "project-" + uuid.uuid4().hex[:12]
    classification = str(payload.get("classification") or "internal").strip()
    if classification not in {"public", "internal", "confidential"}:
        raise ApiError("프로젝트 보안 등급이 올바르지 않습니다.")
    actor = _actor(payload)
    now = utc_now()
    with _connect() as db:
        if db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
            raise ApiError("이미 사용 중인 프로젝트 ID입니다.", 409)
        db.execute(
            "INSERT INTO projects(id,name,owner,classification,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (project_id, name, actor, classification, "active", now, now),
        )
        db.execute(
            "INSERT INTO project_members(project_id,actor,role,status,invited_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (project_id, actor, "owner", "active", actor, now, now),
        )
        _audit(db, actor, "project.created", {"project_id": project_id, "name": name, "classification": classification})
    return {
        "id": project_id,
        "name": name,
        "owner": actor,
        "classification": classification,
        "status": "active",
        "documentCount": 0,
        "factCount": 0,
        "artifactCount": 0,
        "createdAt": now,
        "updatedAt": now,
    }


_PROJECT_BACKUP_COLUMNS = {
    "project_policies": ("project_id", "policy_json", "revision", "updated_by", "updated_at"),
    "project_workspace_states": ("project_id", "active_document_id", "active_tab", "active_view", "chat_json", "last_answer", "updated_by", "updated_at"),
    "project_markdown_documents": ("id", "project_id", "title", "current_revision", "status", "created_at", "updated_at"),
    "project_markdown_versions": ("id", "document_id", "revision", "markdown", "markdown_sha256", "source_format", "source_filename", "source_artifact_sha256", "source_session_id", "fact_snapshot_json", "created_by", "created_at"),
    "project_document_artifacts": ("id", "document_id", "format", "variant_key", "source_version_id", "source_revision", "source_markdown_sha256", "status", "filename", "media_type", "content_blob", "artifact_sha256", "template_id", "renderer", "instruction", "render_map_json", "error", "created_at", "updated_at"),
    "project_facts": ("id", "project_id", "fact_key", "label", "value_type", "unit", "status", "created_at", "updated_at"),
    "project_fact_values": ("id", "fact_id", "value_json", "effective_date", "status", "source_document_id", "source_locator", "source_excerpt", "confidence", "created_by", "created_at"),
    "artifacts": ("id", "project_id", "artifact_type", "title", "status", "current_version_id", "source_type", "source_id", "created_by", "created_at", "updated_at"),
    "artifact_versions": ("id", "artifact_id", "version", "media_type", "filename", "content_blob", "content_json", "content_sha256", "metadata_json", "workflow_run_id", "created_by", "created_at"),
    "artifact_relations": ("id", "project_id", "source_version_id", "target_version_id", "relation", "metadata_json", "created_by", "created_at"),
    "artifact_evidence": ("id", "project_id", "artifact_id", "artifact_version_id", "source_artifact_id", "source_version_id", "locator", "excerpt", "excerpt_sha256", "confidence", "metadata_json", "created_by", "created_at"),
}


def _backup_value(value):
    if isinstance(value, bytes):
        return {"$base64": base64.b64encode(value).decode("ascii")}
    return value


def _backup_rows(rows) -> list[dict]:
    return [{key: _backup_value(value) for key, value in dict(row).items()} for row in rows]


def _restore_backup_value(value):
    if isinstance(value, dict) and set(value) == {"$base64"}:
        try:
            return base64.b64decode(str(value["$base64"]), validate=True)
        except (ValueError, TypeError) as error:
            raise ApiError("백업의 바이너리 데이터가 올바르지 않습니다.") from error
    return value


def _insert_backup_row(db: sqlite3.Connection, table: str, source: dict, overrides: dict | None = None) -> None:
    allowed = _PROJECT_BACKUP_COLUMNS[table]
    values = {key: _restore_backup_value(source.get(key)) for key in allowed}
    values.update(overrides or {})
    columns = list(allowed)
    db.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})", tuple(values[key] for key in columns))


def export_project_backup(project_id: str, payload: dict | None = None) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    actor = _actor(payload or {})
    with _connect() as db:
        _require_project_role(db, project_id, actor, {"owner", "admin", "editor", "viewer"})
        project = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        data = {
            "projectPolicy": _backup_rows(db.execute("SELECT * FROM project_policies WHERE project_id=?", (project_id,)).fetchall()),
            "workspaceState": _backup_rows(db.execute("SELECT * FROM project_workspace_states WHERE project_id=?", (project_id,)).fetchall()),
            "markdownDocuments": _backup_rows(db.execute("SELECT * FROM project_markdown_documents WHERE project_id=?", (project_id,)).fetchall()),
            "markdownVersions": _backup_rows(db.execute("SELECT v.* FROM project_markdown_versions v JOIN project_markdown_documents d ON d.id=v.document_id WHERE d.project_id=?", (project_id,)).fetchall()),
            "documentArtifacts": _backup_rows(db.execute("SELECT a.* FROM project_document_artifacts a JOIN project_markdown_documents d ON d.id=a.document_id WHERE d.project_id=?", (project_id,)).fetchall()),
            "facts": _backup_rows(db.execute("SELECT * FROM project_facts WHERE project_id=?", (project_id,)).fetchall()),
            "factValues": _backup_rows(db.execute("SELECT v.* FROM project_fact_values v JOIN project_facts f ON f.id=v.fact_id WHERE f.project_id=?", (project_id,)).fetchall()),
            "artifacts": _backup_rows(db.execute("SELECT * FROM artifacts WHERE project_id=?", (project_id,)).fetchall()),
            "artifactVersions": _backup_rows(db.execute("SELECT v.* FROM artifact_versions v JOIN artifacts a ON a.id=v.artifact_id WHERE a.project_id=?", (project_id,)).fetchall()),
            "artifactRelations": _backup_rows(db.execute("SELECT * FROM artifact_relations WHERE project_id=?", (project_id,)).fetchall()),
            "artifactEvidence": _backup_rows(db.execute("SELECT * FROM artifact_evidence WHERE project_id=?", (project_id,)).fetchall()),
        }
    bundle = {
        "format": "aiworks-project-backup", "schemaVersion": "1.0", "exportedAt": utc_now(),
        "project": {"id": project["id"], "name": project["name"], "classification": project["classification"], "status": project["status"]},
        "data": data,
    }
    encoded = _json(bundle).encode("utf-8")
    if len(encoded) > MAX_UNCOMPRESSED_BYTES:
        raise ApiError("프로젝트 백업은 50MB를 넘을 수 없습니다.", 413)
    bundle["integrity"] = {"algorithm": "SHA-256", "sha256": hashlib.sha256(encoded).hexdigest()}
    bundle["filename"] = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", str(project["name"]))[:80] + ".aiworks.json"
    bundle["counts"] = {key: len(value) for key, value in data.items()}
    return bundle


def import_project_backup(payload: dict) -> dict:
    ensure_schema()
    actor = _actor(payload)
    bundle = payload.get("bundle")
    if bundle is None and payload.get("content_base64"):
        try:
            raw = base64.b64decode(str(payload["content_base64"]), validate=True)
            if len(raw) > MAX_UNCOMPRESSED_BYTES:
                raise ApiError("프로젝트 백업은 50MB를 넘을 수 없습니다.", 413)
            bundle = json.loads(raw.decode("utf-8"))
        except ApiError:
            raise
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
            raise ApiError("프로젝트 백업 JSON이 올바르지 않습니다.") from error
    if not isinstance(bundle, dict) or bundle.get("format") != "aiworks-project-backup" or bundle.get("schemaVersion") != "1.0":
        raise ApiError("지원하지 않는 AIWorks 프로젝트 백업입니다.")
    integrity = bundle.get("integrity") if isinstance(bundle.get("integrity"), dict) else {}
    unsigned = {key: value for key, value in bundle.items() if key not in {"integrity", "filename", "counts"}}
    expected = hashlib.sha256(_json(unsigned).encode("utf-8")).hexdigest()
    if not hmac.compare_digest(str(integrity.get("sha256") or ""), expected):
        raise ApiError("프로젝트 백업 무결성 검증에 실패했습니다.", 409)
    source_project = bundle.get("project") if isinstance(bundle.get("project"), dict) else {}
    data = bundle.get("data") if isinstance(bundle.get("data"), dict) else {}
    name = re.sub(r"\s+", " ", str(payload.get("name") or (str(source_project.get("name") or "복원 프로젝트") + " 복원")).strip())
    if len(name) < 2 or len(name) > 120:
        raise ApiError("복원 프로젝트 이름은 2~120자로 입력해 주세요.")
    classification = str(source_project.get("classification") or "internal")
    if classification not in {"public", "internal", "confidential"}:
        classification = "internal"
    project_id = "project-" + uuid.uuid4().hex[:12]
    now = utc_now()
    doc_map = {str(row.get("id")): "mdoc_" + uuid.uuid4().hex for row in (data.get("markdownDocuments") or []) if isinstance(row, dict)}
    mdver_map = {str(row.get("id")): "mdver_" + uuid.uuid4().hex for row in (data.get("markdownVersions") or []) if isinstance(row, dict)}
    docart_map = {str(row.get("id")): "artifact_" + uuid.uuid4().hex for row in (data.get("documentArtifacts") or []) if isinstance(row, dict)}
    fact_map = {str(row.get("id")): "fact_" + uuid.uuid4().hex for row in (data.get("facts") or []) if isinstance(row, dict)}
    gart_map = {str(row.get("id")): "gart_" + uuid.uuid4().hex for row in (data.get("artifacts") or []) if isinstance(row, dict)}
    gver_map = {str(row.get("id")): "gartver_" + uuid.uuid4().hex for row in (data.get("artifactVersions") or []) if isinstance(row, dict)}
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO projects(id,name,owner,classification,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (project_id, name, actor, classification, "active", now, now))
        db.execute("INSERT INTO project_members(project_id,actor,role,status,invited_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (project_id, actor, "owner", "active", actor, now, now))
        for row in data.get("markdownDocuments") or []:
            _insert_backup_row(db, "project_markdown_documents", row, {"id": doc_map[str(row.get("id"))], "project_id": project_id})
        for row in data.get("markdownVersions") or []:
            document_id = doc_map.get(str(row.get("document_id")))
            if document_id:
                _insert_backup_row(db, "project_markdown_versions", row, {"id": mdver_map[str(row.get("id"))], "document_id": document_id, "source_session_id": None})
        for row in data.get("documentArtifacts") or []:
            document_id = doc_map.get(str(row.get("document_id")))
            if document_id:
                _insert_backup_row(db, "project_document_artifacts", row, {"id": docart_map[str(row.get("id"))], "document_id": document_id, "source_version_id": mdver_map.get(str(row.get("source_version_id")))})
        for row in data.get("facts") or []:
            _insert_backup_row(db, "project_facts", row, {"id": fact_map[str(row.get("id"))], "project_id": project_id})
        for row in data.get("factValues") or []:
            fact_id = fact_map.get(str(row.get("fact_id")))
            if fact_id:
                _insert_backup_row(db, "project_fact_values", row, {"id": "factvalue_" + uuid.uuid4().hex, "fact_id": fact_id, "source_document_id": doc_map.get(str(row.get("source_document_id")))})
        for row in data.get("artifacts") or []:
            source_id = str(row.get("source_id") or "")
            if row.get("source_type") == "project-document-artifact":
                source_id = docart_map.get(source_id, source_id)
            _insert_backup_row(db, "artifacts", row, {"id": gart_map[str(row.get("id"))], "project_id": project_id, "current_version_id": None, "source_id": source_id})
        for row in data.get("artifactVersions") or []:
            artifact_id = gart_map.get(str(row.get("artifact_id")))
            if artifact_id:
                _insert_backup_row(db, "artifact_versions", row, {"id": gver_map[str(row.get("id"))], "artifact_id": artifact_id, "workflow_run_id": None})
        for row in data.get("artifacts") or []:
            new_artifact_id = gart_map[str(row.get("id"))]
            db.execute("UPDATE artifacts SET current_version_id=? WHERE id=?", (gver_map.get(str(row.get("current_version_id"))), new_artifact_id))
        for row in data.get("artifactRelations") or []:
            source_id, target_id = gver_map.get(str(row.get("source_version_id"))), gver_map.get(str(row.get("target_version_id")))
            if source_id and target_id:
                _insert_backup_row(db, "artifact_relations", row, {"id": "gartrel_" + uuid.uuid4().hex, "project_id": project_id, "source_version_id": source_id, "target_version_id": target_id})
        for row in data.get("artifactEvidence") or []:
            artifact_id = gart_map.get(str(row.get("artifact_id")))
            if artifact_id:
                _insert_backup_row(db, "artifact_evidence", row, {"id": "evidence_" + uuid.uuid4().hex, "project_id": project_id, "artifact_id": artifact_id, "artifact_version_id": gver_map.get(str(row.get("artifact_version_id"))), "source_artifact_id": gart_map.get(str(row.get("source_artifact_id"))), "source_version_id": gver_map.get(str(row.get("source_version_id")))})
        policy_rows = data.get("projectPolicy") or []
        if policy_rows:
            _insert_backup_row(db, "project_policies", policy_rows[0], {"project_id": project_id, "updated_by": actor, "updated_at": now})
        workspace_rows = data.get("workspaceState") or []
        if workspace_rows:
            _insert_backup_row(db, "project_workspace_states", workspace_rows[0], {"project_id": project_id, "active_document_id": doc_map.get(str(workspace_rows[0].get("active_document_id"))), "updated_by": actor, "updated_at": now})
        _audit(db, actor, "project.backup_imported", {"project_id": project_id, "source_project_id": source_project.get("id"), "integrity_sha256": expected, "counts": {key: len(value) for key, value in data.items() if isinstance(value, list)}})
    return {"project": {"id": project_id, "name": name, "owner": actor, "classification": classification, "status": "active", "createdAt": now, "updatedAt": now}, "sourceProjectId": source_project.get("id"), "integritySha256": expected, "counts": {key: len(value) for key, value in data.items() if isinstance(value, list)}}


_PROJECT_ROLES = {"viewer", "editor", "admin", "owner"}
_DEFAULT_PROJECT_POLICY = {
    "autoApprovalScopes": ["document.read", "data.read"],
    "finalConfirmationActions": ["submit", "publish", "send", "delete"],
    "resolver": {
        "intentWeight": 0.45,
        "qualityWeight": 0.30,
        "costWeight": 0.10,
        "latencyWeight": 0.10,
        "preferenceWeight": 0.05,
        "preferredPackages": [],
    },
}


def _project_role(db: sqlite3.Connection, project_id: str, actor: str) -> str | None:
    project = db.execute("SELECT owner,status FROM projects WHERE id=?", (project_id,)).fetchone()
    if not project:
        raise ApiError("프로젝트를 찾을 수 없습니다.", 404)
    if str(project["owner"]) == actor:
        return "owner"
    member = db.execute(
        "SELECT role FROM project_members WHERE project_id=? AND actor=? AND status='active'",
        (project_id, actor),
    ).fetchone()
    return str(member["role"]) if member else None


def _require_project_role(
    db: sqlite3.Connection,
    project_id: str,
    actor: str,
    allowed: set[str],
) -> str:
    role = _project_role(db, project_id, actor)
    if role not in allowed:
        raise ApiError("이 프로젝트 작업을 수행할 권한이 없습니다.", 403)
    return str(role)


def _project_policy_result(db: sqlite3.Connection, project_id: str) -> dict:
    row = db.execute("SELECT * FROM project_policies WHERE project_id=?", (project_id,)).fetchone()
    if not row:
        return {
            "projectId": project_id,
            "policy": copy.deepcopy(_DEFAULT_PROJECT_POLICY),
            "revision": 0,
            "updatedBy": None,
            "updatedAt": None,
        }
    return {
        "projectId": project_id,
        "policy": _load_json(row["policy_json"], copy.deepcopy(_DEFAULT_PROJECT_POLICY)),
        "revision": int(row["revision"]),
        "updatedBy": row["updated_by"],
        "updatedAt": row["updated_at"],
    }


def get_project_governance(project_id: str, payload: dict | None = None) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    actor = _actor(payload or {})
    with _connect() as db:
        project = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not project:
            raise ApiError("프로젝트를 찾을 수 없습니다.", 404)
        role = _project_role(db, project_id, actor)
        if role is None:
            raise ApiError("이 프로젝트를 조회할 권한이 없습니다.", 403)
        members = db.execute(
            "SELECT * FROM project_members WHERE project_id=? ORDER BY CASE role WHEN 'owner' THEN 1 WHEN 'admin' THEN 2 WHEN 'editor' THEN 3 ELSE 4 END,actor",
            (project_id,),
        ).fetchall()
        grants = db.execute(
            "SELECT * FROM permission_grants WHERE project_id=? ORDER BY updated_at DESC",
            (project_id,),
        ).fetchall()
        policy = _project_policy_result(db, project_id)
    return {
        "project": {
            "id": project["id"], "name": project["name"], "owner": project["owner"],
            "classification": project["classification"], "status": project["status"],
            "createdAt": project["created_at"], "updatedAt": project["updated_at"],
        },
        "currentActor": actor,
        "currentRole": role,
        "members": [
            {
                "actor": row["actor"], "role": row["role"], "status": row["status"],
                "invitedBy": row["invited_by"], "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
            }
            for row in members
        ],
        "policy": policy,
        "grants": [
            {
                "id": row["id"], "actor": row["actor"], "packageId": row["package_id"],
                "versionRange": row["version_range"], "scopes": _load_json(row["scopes_json"], []),
                "classification": row["classification"], "status": row["status"],
                "grantedBy": row["granted_by"], "expiresAt": row["expires_at"],
                "createdAt": row["created_at"], "updatedAt": row["updated_at"],
            }
            for row in grants
        ],
    }


def save_project_member(project_id: str, payload: dict) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    actor = _actor(payload)
    member_actor = str(payload.get("member_actor") or "").strip()
    role = str(payload.get("role") or "viewer").strip()
    status = str(payload.get("status") or "active").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._@-]{1,119}", member_actor):
        raise ApiError("프로젝트 구성원 식별자가 올바르지 않습니다.")
    if role not in _PROJECT_ROLES - {"owner"}:
        raise ApiError("구성원 역할은 viewer, editor, admin 중 하나여야 합니다.")
    if status not in {"active", "revoked"}:
        raise ApiError("구성원 상태가 올바르지 않습니다.")
    now = utc_now()
    with _connect() as db:
        _require_project_role(db, project_id, actor, {"owner", "admin"})
        project = db.execute("SELECT owner FROM projects WHERE id=?", (project_id,)).fetchone()
        if member_actor == project["owner"]:
            raise ApiError("프로젝트 소유자의 역할은 변경하거나 해제할 수 없습니다.", 409)
        db.execute(
            """
            INSERT INTO project_members(project_id,actor,role,status,invited_by,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(project_id,actor) DO UPDATE SET
                role=excluded.role,status=excluded.status,invited_by=excluded.invited_by,updated_at=excluded.updated_at
            """,
            (project_id, member_actor, role, status, actor, now, now),
        )
        _audit(db, actor, "project.member_changed", {
            "project_id": project_id, "member_actor": member_actor, "role": role, "status": status,
        })
    return get_project_governance(project_id, {"actor": actor})


def save_project_policy(project_id: str, payload: dict) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    actor = _actor(payload)
    policy = payload.get("policy")
    if not isinstance(policy, dict):
        raise ApiError("프로젝트 정책은 객체여야 합니다.")
    auto_scopes = policy.get("autoApprovalScopes") or []
    final_actions = policy.get("finalConfirmationActions") or []
    resolver = policy.get("resolver") or {}
    if not isinstance(auto_scopes, list) or not isinstance(final_actions, list) or not isinstance(resolver, dict):
        raise ApiError("프로젝트 정책 형식이 올바르지 않습니다.")
    safe_scopes = sorted({
        str(scope) for scope in auto_scopes
        if re.fullmatch(r"[a-z][a-z0-9_.-]{2,80}", str(scope))
    })
    if len(safe_scopes) != len(auto_scopes):
        raise ApiError("자동 승인 권한 범위에 올바르지 않은 값이 있습니다.")
    weights = {}
    for key, default in _DEFAULT_PROJECT_POLICY["resolver"].items():
        if key == "preferredPackages":
            values = resolver.get(key, default)
            if not isinstance(values, list) or len(values) > 30:
                raise ApiError("선호 MCP 목록이 올바르지 않습니다.")
            weights[key] = [str(item)[:160] for item in values if str(item).strip()]
        else:
            value = float(resolver.get(key, default))
            if value < 0 or value > 1:
                raise ApiError("Resolver 가중치는 0~1 범위여야 합니다.")
            weights[key] = value
    if sum(float(weights[key]) for key in weights if key != "preferredPackages") <= 0:
        raise ApiError("Resolver 가중치 합은 0보다 커야 합니다.")
    normalized = {
        "autoApprovalScopes": safe_scopes,
        "finalConfirmationActions": sorted({str(item)[:80] for item in final_actions if str(item).strip()}),
        "resolver": weights,
    }
    now = utc_now()
    with _connect() as db:
        _require_project_role(db, project_id, actor, {"owner", "admin"})
        current = db.execute("SELECT revision FROM project_policies WHERE project_id=?", (project_id,)).fetchone()
        revision = int(current["revision"]) + 1 if current else 1
        expected = payload.get("expected_revision")
        if expected is not None and int(expected) != (int(current["revision"]) if current else 0):
            raise ApiError("프로젝트 정책 revision이 변경되었습니다. 다시 불러와 주세요.", 409)
        db.execute(
            """
            INSERT INTO project_policies(project_id,policy_json,revision,updated_by,updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(project_id) DO UPDATE SET
                policy_json=excluded.policy_json,revision=excluded.revision,
                updated_by=excluded.updated_by,updated_at=excluded.updated_at
            """,
            (project_id, _json(normalized), revision, actor, now),
        )
        _audit(db, actor, "project.policy_saved", {"project_id": project_id, "revision": revision})
    return get_project_governance(project_id, {"actor": actor})


def save_permission_grant(project_id: str, payload: dict) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    actor = _actor(payload)
    grant_id = str(payload.get("id") or "").strip() or "grant_" + uuid.uuid4().hex
    package_id = str(payload.get("package_id") or "").strip()
    member_actor = str(payload.get("member_actor") or actor).strip()
    version_range = str(payload.get("version_range") or "*").strip()[:80]
    scopes = payload.get("scopes") or []
    classification = str(payload.get("classification") or "internal")
    status = str(payload.get("status") or "active")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,159}", package_id):
        raise ApiError("Grant 대상 MCP 패키지 ID가 올바르지 않습니다.")
    if not isinstance(scopes, list) or not scopes:
        raise ApiError("Grant 권한 범위가 한 개 이상 필요합니다.")
    normalized_scopes = sorted({str(scope) for scope in scopes if re.fullmatch(r"[a-z][a-z0-9_.-]{2,80}", str(scope))})
    if len(normalized_scopes) != len(scopes):
        raise ApiError("Grant 권한 범위에 올바르지 않은 값이 있습니다.")
    if classification not in {"public", "internal", "confidential"} or status not in {"active", "revoked"}:
        raise ApiError("Grant 정책 값이 올바르지 않습니다.")
    now = utc_now()
    with _connect() as db:
        _require_project_role(db, project_id, actor, {"owner", "admin"})
        if not db.execute("SELECT 1 FROM project_members WHERE project_id=? AND actor=? AND status='active'", (project_id, member_actor)).fetchone():
            raise ApiError("Grant 대상 사용자가 프로젝트 구성원이 아닙니다.", 409)
        db.execute(
            """
            INSERT INTO permission_grants(
                id,project_id,actor,package_id,version_range,scopes_json,classification,
                status,granted_by,expires_at,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                version_range=excluded.version_range,scopes_json=excluded.scopes_json,
                classification=excluded.classification,status=excluded.status,
                granted_by=excluded.granted_by,expires_at=excluded.expires_at,updated_at=excluded.updated_at
            """,
            (
                grant_id, project_id, member_actor, package_id, version_range,
                _json(normalized_scopes), classification, status, actor,
                str(payload.get("expires_at") or "").strip() or None, now, now,
            ),
        )
        _audit(db, actor, "project.permission_grant_changed", {
            "project_id": project_id, "grant_id": grant_id, "member_actor": member_actor,
            "package_id": package_id, "scopes": normalized_scopes, "status": status,
        })
    return get_project_governance(project_id, {"actor": actor})


def change_project_status(project_id: str, payload: dict) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    actor = _actor(payload)
    action = str(payload.get("action") or "").strip()
    if action not in {"archive", "restore"}:
        raise ApiError("프로젝트 상태 작업은 archive 또는 restore여야 합니다.")
    status = "archived" if action == "archive" else "active"
    with _connect() as db:
        _require_project_role(db, project_id, actor, {"owner"})
        now = utc_now()
        db.execute("UPDATE projects SET status=?,updated_at=? WHERE id=?", (status, now, project_id))
        _audit(db, actor, "project." + action, {"project_id": project_id})
        project = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    return {
        "id": project["id"], "name": project["name"], "owner": project["owner"],
        "classification": project["classification"], "status": project["status"],
        "updatedAt": project["updated_at"],
    }


def list_archived_projects(payload: dict | None = None) -> dict:
    ensure_schema()
    actor = _actor(payload or {})
    with _connect() as db:
        rows = db.execute(
            """
            SELECT p.* FROM projects p
             WHERE p.status='archived'
               AND (p.owner=? OR EXISTS(
                    SELECT 1 FROM project_members m
                     WHERE m.project_id=p.id AND m.actor=? AND m.status='active'
               ))
             ORDER BY p.updated_at DESC
            """,
            (actor, actor),
        ).fetchall()
    return {"items": [
        {
            "id": row["id"], "name": row["name"], "owner": row["owner"],
            "classification": row["classification"], "status": row["status"],
            "createdAt": row["created_at"], "updatedAt": row["updated_at"],
        }
        for row in rows
    ]}



def _normalize_recipe_definition(value: object) -> dict:
    if not isinstance(value, dict):
        raise ApiError("Recipe 정의는 객체여야 합니다.")
    steps = value.get("steps")
    if not isinstance(steps, list) or not steps or len(steps) > 30:
        raise ApiError("Recipe에는 1~30개의 단계가 필요합니다.")
    normalized_steps = []
    seen = set()
    for index, item in enumerate(steps, 1):
        if not isinstance(item, dict):
            raise ApiError("Recipe 단계 형식이 올바르지 않습니다.")
        step_id = str(item.get("id") or f"step-{index}").strip()
        capability = str(item.get("capability") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,79}", step_id) or step_id in seen:
            raise ApiError("Recipe 단계 ID가 올바르지 않거나 중복되었습니다.")
        if not re.fullmatch(r"[a-z][a-z0-9._-]{2,119}", capability):
            raise ApiError("Recipe 단계 Capability가 올바르지 않습니다.")
        seen.add(step_id)
        permissions = item.get("permissions") or []
        if not isinstance(permissions, list) or any(not re.fullmatch(r"[a-z][a-z0-9._-]{2,80}", str(scope)) for scope in permissions):
            raise ApiError("Recipe 단계 권한 범위가 올바르지 않습니다.")
        normalized_steps.append({
            "id": step_id,
            "name": str(item.get("name") or step_id)[:120],
            "capability": capability,
            "permissions": sorted({str(scope) for scope in permissions}),
            "input": item.get("input") if isinstance(item.get("input"), dict) else {},
            "outputArtifactType": str(item.get("outputArtifactType") or "")[:120] or None,
            "requiresConfirmation": bool(item.get("requiresConfirmation")),
        })
    security = value.get("security") if isinstance(value.get("security"), dict) else {}
    return {
        "contractVersion": "1.0",
        "description": str(value.get("description") or "")[:2_000],
        "tags": sorted({str(item).strip().lower()[:40] for item in (value.get("tags") or []) if str(item).strip()})[:20],
        "inputArtifactTypes": [str(item)[:120] for item in (value.get("inputArtifactTypes") or []) if str(item).strip()][:30],
        "outputArtifactTypes": [str(item)[:120] for item in (value.get("outputArtifactTypes") or []) if str(item).strip()][:30],
        "estimatedCost": max(0.0, min(1_000_000.0, float(value.get("estimatedCost") or 0))),
        "estimatedLatencyMs": max(0, min(86_400_000, int(value.get("estimatedLatencyMs") or 0))),
        "license": str(value.get("license") or "UNSPECIFIED")[:120],
        "provenance": str(value.get("provenance") or "user-authored")[:500],
        "security": {
            "status": str(security.get("status") or "unreviewed")[:40],
            "blocked": bool(security.get("blocked")),
            "advisories": [str(item)[:300] for item in (security.get("advisories") or [])][:20],
        },
        "steps": normalized_steps,
    }


def _recipe_preview(definition: dict) -> dict:
    steps = definition.get("steps") or []
    permissions = sorted({scope for step in steps for scope in (step.get("permissions") or [])})
    capabilities = sorted({str(step.get("capability") or "") for step in steps if step.get("capability")})
    security = definition.get("security") if isinstance(definition.get("security"), dict) else {}
    risk_flags = []
    if security.get("blocked") or security.get("status") in {"vulnerable", "blocked"}:
        risk_flags.append("security-blocked")
    if "network.send" in permissions:
        risk_flags.append("external-transfer")
    return {
        "tags": list(definition.get("tags") or []),
        "permissions": permissions,
        "capabilities": capabilities,
        "inputArtifactTypes": list(definition.get("inputArtifactTypes") or []),
        "outputArtifactTypes": list(definition.get("outputArtifactTypes") or []),
        "estimatedCost": float(definition.get("estimatedCost") or 0),
        "estimatedLatencyMs": int(definition.get("estimatedLatencyMs") or 0),
        "license": str(definition.get("license") or "UNSPECIFIED"),
        "provenance": str(definition.get("provenance") or "user-authored"),
        "requiresConfirmation": any(bool(step.get("requiresConfirmation")) for step in steps),
        "security": security,
        "riskFlags": risk_flags,
    }


def _recipe_result(db: sqlite3.Connection, recipe: sqlite3.Row, *, project_id: str = "") -> dict:
    versions = db.execute(
        "SELECT * FROM workflow_recipe_versions WHERE recipe_id=? ORDER BY created_at DESC",
        (recipe["id"],),
    ).fetchall()
    latest_definition = _load_json(versions[0]["definition_json"], {}) if versions else {}
    installed = None
    if project_id:
        installed = db.execute(
            "SELECT * FROM workflow_recipe_installations WHERE project_id=? AND recipe_id=?",
            (project_id, recipe["id"]),
        ).fetchone()
    return {
        "id": recipe["id"], "name": recipe["name"], "description": recipe["description"],
        "visibility": recipe["visibility"], "status": recipe["status"], "owner": recipe["owner"],
        "createdAt": recipe["created_at"], "updatedAt": recipe["updated_at"],
        "preview": _recipe_preview(latest_definition),
        "versions": [{
            "id": item["id"], "version": item["version"],
            "definition": _load_json(item["definition_json"], {}),
            "changelog": item["changelog"], "createdBy": item["created_by"],
            "createdAt": item["created_at"],
        } for item in versions],
        "installed": {
            "versionId": installed["version_id"], "status": installed["status"],
            "installedBy": installed["installed_by"], "updatedAt": installed["updated_at"],
        } if installed else None,
    }


def list_workflow_recipes(payload: dict | None = None) -> dict:
    ensure_schema()
    payload = payload or {}
    actor = _actor(payload)
    project_id = str(payload.get("project_id") or "").strip()
    if project_id:
        project_id = _safe_project_id(project_id)
    query = str(payload.get("q") or "").strip().lower()[:200]
    raw_tags = payload.get("tags") or []
    if isinstance(raw_tags, str):
        raw_tags = [item.strip() for item in raw_tags.split(",")]
    tags = {str(item).lower() for item in raw_tags if str(item).strip()}
    max_cost = payload.get("max_cost")
    required_permission = str(payload.get("required_permission") or "").strip()
    with _connect() as db:
        rows = db.execute(
            "SELECT * FROM workflow_recipes WHERE status!='deleted' AND (visibility!='private' OR owner=?) ORDER BY updated_at DESC",
            (actor,),
        ).fetchall()
        items = [_recipe_result(db, row, project_id=project_id) for row in rows]
    if query:
        items = [item for item in items if query in (item["id"] + " " + item["name"] + " " + item["description"] + " " + " ".join(item["preview"]["tags"])).lower()]
    if tags:
        items = [item for item in items if tags.issubset(set(item["preview"]["tags"]))]
    if max_cost not in (None, ""):
        try:
            cost_limit = max(0.0, float(max_cost))
        except (TypeError, ValueError) as error:
            raise ApiError("Recipe 최대 비용은 숫자여야 합니다.") from error
        items = [item for item in items if item["preview"]["estimatedCost"] <= cost_limit]
    if required_permission:
        items = [item for item in items if required_permission in item["preview"]["permissions"]]
    return {"items": items, "count": len(items), "projectId": project_id or None, "query": {"q": query, "tags": sorted(tags), "maxCost": max_cost, "requiredPermission": required_permission}}


def save_workflow_recipe(payload: dict) -> dict:
    ensure_schema()
    actor = _actor(payload)
    recipe_id = str(payload.get("id") or "").strip() or "recipe-" + uuid.uuid4().hex[:12]
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,119}", recipe_id):
        raise ApiError("Recipe ID가 올바르지 않습니다.")
    name = re.sub(r"\s+", " ", str(payload.get("name") or "").strip())
    description = str(payload.get("description") or "").strip()
    version = str(payload.get("version") or "0.1.0").strip()
    visibility = str(payload.get("visibility") or "private").strip()
    if len(name) < 2 or len(name) > 120 or not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version):
        raise ApiError("Recipe 이름 또는 SemVer가 올바르지 않습니다.")
    if visibility not in {"private", "organization", "public"}:
        raise ApiError("Recipe 공개 범위가 올바르지 않습니다.")
    definition = _normalize_recipe_definition(payload.get("definition"))
    now = utc_now()
    with _connect() as db:
        row = db.execute("SELECT * FROM workflow_recipes WHERE id=?", (recipe_id,)).fetchone()
        if row and row["owner"] != actor:
            raise ApiError("다른 사용자의 Recipe를 수정할 수 없습니다.", 403)
        if row and row["status"] == "deprecated" and payload.get("restore") is not True:
            raise ApiError("폐기된 Recipe는 restore 확인 후 새 버전을 만들 수 있습니다.", 409)
        if db.execute("SELECT 1 FROM workflow_recipe_versions WHERE recipe_id=? AND version=?", (recipe_id, version)).fetchone():
            raise ApiError("동일한 Recipe 버전이 이미 있습니다.", 409)
        if row:
            db.execute(
                "UPDATE workflow_recipes SET name=?,description=?,visibility=?,status='published',updated_at=? WHERE id=?",
                (name, description, visibility, now, recipe_id),
            )
        else:
            db.execute(
                "INSERT INTO workflow_recipes(id,name,description,visibility,status,owner,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (recipe_id, name, description, visibility, "published", actor, now, now),
            )
        version_id = "recipever_" + uuid.uuid4().hex
        db.execute(
            "INSERT INTO workflow_recipe_versions(id,recipe_id,version,definition_json,changelog,created_by,created_at) VALUES(?,?,?,?,?,?,?)",
            (version_id, recipe_id, version, _json(definition), str(payload.get("changelog") or "")[:1_000] or None, actor, now),
        )
        _audit(db, actor, "recipe.version_published", {"recipe_id": recipe_id, "version": version, "visibility": visibility})
        recipe = db.execute("SELECT * FROM workflow_recipes WHERE id=?", (recipe_id,)).fetchone()
        return _recipe_result(db, recipe)


def fork_workflow_recipe(recipe_id: str, payload: dict) -> dict:
    ensure_schema()
    actor = _actor(payload)
    with _connect() as db:
        source = db.execute("SELECT * FROM workflow_recipes WHERE id=? AND status='published'", (recipe_id,)).fetchone()
        if not source or (source["visibility"] == "private" and source["owner"] != actor):
            raise ApiError("포크할 Recipe를 찾을 수 없습니다.", 404)
        version = db.execute(
            "SELECT * FROM workflow_recipe_versions WHERE recipe_id=? ORDER BY created_at DESC LIMIT 1",
            (recipe_id,),
        ).fetchone()
    target_id = str(payload.get("id") or "").strip() or recipe_id + "-fork-" + uuid.uuid4().hex[:6]
    return save_workflow_recipe({
        "id": target_id, "name": str(payload.get("name") or source["name"] + " 사본"),
        "description": str(payload.get("description") or source["description"]),
        "version": str(payload.get("version") or "0.1.0"),
        "visibility": str(payload.get("visibility") or "private"),
        "definition": _load_json(version["definition_json"], {}),
        "changelog": "Forked from " + recipe_id + "@" + version["version"],
        "actor": actor,
    })


def install_workflow_recipe(project_id: str, recipe_id: str, payload: dict) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    actor = _actor(payload)
    requested_version = str(payload.get("version") or "").strip()
    now = utc_now()
    with _connect() as db:
        _require_project_role(db, project_id, actor, {"owner", "admin"})
        recipe = db.execute("SELECT * FROM workflow_recipes WHERE id=? AND status='published'", (recipe_id,)).fetchone()
        if not recipe or (recipe["visibility"] == "private" and recipe["owner"] != actor):
            raise ApiError("설치할 Recipe를 찾을 수 없습니다.", 404)
        if requested_version:
            version = db.execute(
                "SELECT * FROM workflow_recipe_versions WHERE recipe_id=? AND version=?",
                (recipe_id, requested_version),
            ).fetchone()
        else:
            version = db.execute(
                "SELECT * FROM workflow_recipe_versions WHERE recipe_id=? ORDER BY created_at DESC LIMIT 1",
                (recipe_id,),
            ).fetchone()
        if not version:
            raise ApiError("설치할 Recipe 버전을 찾을 수 없습니다.", 404)
        definition = _load_json(version["definition_json"], {})
        preview = _recipe_preview(definition)
        if "security-blocked" in preview["riskFlags"]:
            raise ApiError("보안 취약점으로 차단된 Recipe 버전은 설치할 수 없습니다.", 409)
        if preview["riskFlags"] and payload.get("acknowledge_risks") is not True:
            raise ApiError("Recipe의 외부 전송·확인 위험을 미리보고 승인해 주세요.", 403)
        db.execute(
            """INSERT INTO workflow_recipe_installations(project_id,recipe_id,version_id,status,installed_by,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(project_id,recipe_id) DO UPDATE SET version_id=excluded.version_id,status='active',installed_by=excluded.installed_by,updated_at=excluded.updated_at""",
            (project_id, recipe_id, version["id"], "active", actor, now, now),
        )
        _audit(db, actor, "recipe.installed", {"project_id": project_id, "recipe_id": recipe_id, "version": version["version"]})
        recipe = db.execute("SELECT * FROM workflow_recipes WHERE id=?", (recipe_id,)).fetchone()
        return _recipe_result(db, recipe, project_id=project_id)


def deprecate_workflow_recipe(recipe_id: str, payload: dict) -> dict:
    ensure_schema()
    actor = _actor(payload)
    with _connect() as db:
        recipe = db.execute("SELECT * FROM workflow_recipes WHERE id=?", (recipe_id,)).fetchone()
        if not recipe:
            raise ApiError("Recipe를 찾을 수 없습니다.", 404)
        if recipe["owner"] != actor:
            raise ApiError("Recipe 소유자만 폐기할 수 있습니다.", 403)
        now = utc_now()
        db.execute("UPDATE workflow_recipes SET status='deprecated',updated_at=? WHERE id=?", (now, recipe_id))
        db.execute("UPDATE workflow_recipe_installations SET status='deprecated',updated_at=? WHERE recipe_id=?", (now, recipe_id))
        _audit(db, actor, "recipe.deprecated", {"recipe_id": recipe_id})
        recipe = db.execute("SELECT * FROM workflow_recipes WHERE id=?", (recipe_id,)).fetchone()
        return _recipe_result(db, recipe)


def _project_workspace_state(db: sqlite3.Connection, project_id: str) -> dict:
    row = db.execute("SELECT * FROM project_workspace_states WHERE project_id=?", (project_id,)).fetchone()
    if not row:
        return {
            "projectId": project_id,
            "activeDocumentId": None,
            "activeTab": "markdown",
            "activeView": "editor",
            "chat": [],
            "lastAnswer": "",
            "updatedAt": None,
        }
    chat = _load_json(row["chat_json"], [])
    if not isinstance(chat, list):
        chat = []
    return {
        "projectId": project_id,
        "activeDocumentId": row["active_document_id"],
        "activeTab": row["active_tab"],
        "activeView": row["active_view"],
        "chat": chat[-100:],
        "lastAnswer": row["last_answer"] or "",
        "updatedAt": row["updated_at"],
    }


def save_project_workspace_state(project_id: str, payload: dict) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    document_id = str(payload.get("active_document_id") or "").strip()
    active_tab = str(payload.get("active_tab") or "markdown").strip()
    active_view = str(payload.get("active_view") or "editor").strip()
    if active_tab not in {"markdown", "metadata", "history"} and not re.fullmatch(r"artifact:[a-z0-9._-]+", active_tab):
        raise ApiError("마지막 작업 탭이 올바르지 않습니다.")
    if active_view not in {"editor", "data", "builder", "store", "audit", "settings"}:
        raise ApiError("마지막 작업 화면이 올바르지 않습니다.")
    raw_chat = payload.get("chat") or []
    if not isinstance(raw_chat, list):
        raise ApiError("프로젝트 대화 상태는 배열이어야 합니다.")
    chat = []
    for item in raw_chat[-100:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        text = str(item.get("text") or "").strip()
        if role not in {"user", "assistant", "system"} or not text:
            continue
        chat.append({"role": role, "text": text[:12_000], "kind": str(item.get("kind") or "message")[:40]})
    now = utc_now()
    actor = _actor(payload)
    with _connect() as db:
        if not db.execute("SELECT 1 FROM projects WHERE id=? AND status='active'", (project_id,)).fetchone():
            raise ApiError("프로젝트를 찾을 수 없습니다.", 404)
        if document_id and not db.execute("SELECT 1 FROM project_markdown_documents WHERE id=? AND project_id=? AND status='active'", (document_id, project_id)).fetchone():
            document_id = ""
            active_tab = "markdown"
        db.execute(
            """
            INSERT INTO project_workspace_states(project_id,active_document_id,active_tab,active_view,chat_json,last_answer,updated_by,updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(project_id) DO UPDATE SET
                active_document_id=excluded.active_document_id,
                active_tab=excluded.active_tab,
                active_view=excluded.active_view,
                chat_json=excluded.chat_json,
                last_answer=excluded.last_answer,
                updated_by=excluded.updated_by,
                updated_at=excluded.updated_at
            """,
            (project_id, document_id or None, active_tab, active_view, _json(chat), str(payload.get("last_answer") or "")[:20_000] or None, actor, now),
        )
        _audit(db, actor, "project.workspace_state_saved", {"project_id": project_id, "document_id": document_id or None, "tab": active_tab, "view": active_view, "chat_messages": len(chat)})
        state = _project_workspace_state(db, project_id)
    return state


def get_project_workspace(project_id: str) -> dict:
    """Load canonical Markdown, metadata and every derived file in one request."""
    ensure_schema()
    project_id = _safe_project_id(project_id)
    with _connect() as db:
        project = db.execute("SELECT * FROM projects WHERE id=? AND status='active'", (project_id,)).fetchone()
        if not project:
            raise ApiError("프로젝트를 찾을 수 없습니다.", 404)
        documents = []
        for row in db.execute(
            "SELECT id FROM project_markdown_documents WHERE project_id=? AND status='active' ORDER BY updated_at DESC",
            (project_id,),
        ).fetchall():
            document = _project_markdown_result(db, row["id"], include_versions=False)
            document["artifacts"] = [
                _project_artifact_result(item)
                for item in db.execute(
                    "SELECT * FROM project_document_artifacts WHERE document_id=? ORDER BY updated_at DESC",
                    (row["id"],),
                ).fetchall()
            ]
            document["excerpt"] = re.sub(r"\s+", " ", document.pop("markdown"))[:300]
            documents.append(document)
        snapshot = _project_fact_snapshot(db, project_id)
        candidate_count = db.execute(
            "SELECT COUNT(*) AS count FROM project_fact_values v JOIN project_facts f ON f.id=v.fact_id WHERE f.project_id=? AND v.status='candidate'",
            (project_id,),
        ).fetchone()["count"]
        workspace_state = _project_workspace_state(db, project_id)
    return {
        "project": dict(project),
        "documents": documents,
        "metadata": snapshot,
        "workspaceState": workspace_state,
        "summary": {
            "documentCount": len(documents),
            "factCount": len(snapshot.get("facts") or {}),
            "candidateCount": candidate_count,
            "artifactCount": sum(len(item.get("artifacts") or []) for item in documents),
        },
    }


def _ensure_project(db: sqlite3.Connection, project_id: str, actor: str = "workspace-user") -> None:
    if db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
        return
    now = utc_now()
    db.execute(
        "INSERT INTO projects(id,name,owner,classification,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
        (project_id, "AIWorks 프로젝트", actor, "internal", "active", now, now),
    )


def _project_fact_snapshot(db: sqlite3.Connection, project_id: str, as_of: str = "") -> dict:
    facts = {}
    rows = db.execute("SELECT * FROM project_facts WHERE project_id=? AND status='confirmed' ORDER BY fact_key", (project_id,)).fetchall()
    for row in rows:
        values = db.execute(
            "SELECT * FROM project_fact_values WHERE fact_id=? AND status='confirmed' AND (?='' OR effective_date IS NULL OR effective_date<=?) ORDER BY COALESCE(effective_date,'') DESC,created_at DESC",
            (row["id"], as_of, as_of),
        ).fetchall()
        if not values:
            continue
        selected = values[0]
        facts[row["fact_key"]] = {
            "factId": row["id"],
            "valueId": selected["id"],
            "label": row["label"],
            "value": _load_json(selected["value_json"], None),
            "valueType": row["value_type"],
            "unit": row["unit"],
            "effectiveDate": selected["effective_date"],
            "confidence": selected["confidence"],
            "source": {"documentId": selected["source_document_id"], "locator": selected["source_locator"], "excerpt": selected["source_excerpt"]},
        }
    return {"projectId": project_id, "asOf": as_of or None, "facts": facts, "valueIds": [item["valueId"] for item in facts.values()]}


def list_project_facts(project_id: str) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    with _connect() as db:
        project = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not project:
            raise ApiError("프로젝트를 찾을 수 없습니다.", 404)
        snapshot = _project_fact_snapshot(db, project_id)
        candidates = []
        for row in db.execute(
            "SELECT f.fact_key,f.label,f.value_type,f.unit,v.* FROM project_facts f JOIN project_fact_values v ON v.fact_id=f.id WHERE f.project_id=? AND v.status='candidate' ORDER BY v.created_at DESC",
            (project_id,),
        ).fetchall():
            value = _load_json(row["value_json"], None)
            previous = db.execute(
                "SELECT * FROM project_fact_values WHERE fact_id=? AND status='confirmed' ORDER BY COALESCE(effective_date,'') DESC,created_at DESC LIMIT 1",
                (row["fact_id"],),
            ).fetchone()
            conflict = None
            if previous:
                previous_value = _load_json(previous["value_json"], None)
                if previous_value == value:
                    conflict_type, suggested = "duplicate", "rejected"
                elif row["effective_date"] and (not previous["effective_date"] or str(row["effective_date"]) > str(previous["effective_date"])):
                    conflict_type, suggested = "time-change", "time-change"
                else:
                    conflict_type, suggested = "correction-review", "correction"
                conflict = {
                    "type": conflict_type, "suggestedResolution": suggested,
                    "current": {"valueId": previous["id"], "value": previous_value, "effectiveDate": previous["effective_date"], "source": {"documentId": previous["source_document_id"], "locator": previous["source_locator"], "excerpt": previous["source_excerpt"]}},
                }
            candidates.append({
                "valueId": row["id"], "key": row["fact_key"], "label": row["label"], "value": value,
                "valueType": row["value_type"], "unit": row["unit"], "effectiveDate": row["effective_date"],
                "confidence": row["confidence"], "source": {"documentId": row["source_document_id"], "locator": row["source_locator"], "excerpt": row["source_excerpt"]},
                "conflict": conflict,
            })
    return {"project": dict(project), "snapshot": snapshot, "candidates": candidates}


def save_project_fact(project_id: str, payload: dict) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    fact_key = str(payload.get("key") or "").strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{1,99}", fact_key):
        raise ApiError("Fact 키가 올바르지 않습니다.")
    status = str(payload.get("status") or "candidate")
    if status not in {"candidate", "confirmed", "rejected"}:
        raise ApiError("지원하지 않는 Fact 상태입니다.")
    try:
        confidence = float(payload.get("confidence", 1.0))
    except (TypeError, ValueError) as error:
        raise ApiError("Fact 신뢰도는 숫자여야 합니다.") from error
    if not 0 <= confidence <= 1:
        raise ApiError("Fact 신뢰도는 0과 1 사이여야 합니다.")
    actor = _actor(payload)
    now = utc_now()
    with _connect() as db:
        _ensure_project(db, project_id, actor)
        row = db.execute("SELECT * FROM project_facts WHERE project_id=? AND fact_key=?", (project_id, fact_key)).fetchone()
        fact_id = row["id"] if row else "fact_" + uuid.uuid4().hex
        if not row:
            db.execute(
                "INSERT INTO project_facts(id,project_id,fact_key,label,value_type,unit,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (fact_id, project_id, fact_key, str(payload.get("label") or fact_key)[:200], str(payload.get("value_type") or "string"), str(payload.get("unit") or "") or None, "confirmed" if status == "confirmed" else "candidate", now, now),
            )
        elif status == "confirmed":
            db.execute("UPDATE project_facts SET status='confirmed',updated_at=? WHERE id=?", (now, fact_id))
        source = payload.get("source") or {}
        value_id = "factvalue_" + uuid.uuid4().hex
        db.execute(
            "INSERT INTO project_fact_values(id,fact_id,value_json,effective_date,status,source_document_id,source_locator,source_excerpt,confidence,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (value_id, fact_id, _json(payload.get("value")), payload.get("effective_date"), status, source.get("documentId"), source.get("locator"), source.get("excerpt"), confidence, actor, now),
        )
        _audit(db, actor, "project.fact_saved", {"project_id": project_id, "fact_key": fact_key, "value_id": value_id, "status": status})
        snapshot = _project_fact_snapshot(db, project_id)
    return {"projectId": project_id, "factId": fact_id, "valueId": value_id, "status": status, "snapshot": snapshot}


def decide_project_fact_candidate(project_id: str, value_id: str, payload: dict) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    decision = str(payload.get("decision") or "")
    if decision not in {"confirmed", "rejected"}:
        raise ApiError("후보 결정은 confirmed 또는 rejected여야 합니다.")
    resolution = str(payload.get("resolution") or ("rejected" if decision == "rejected" else "confirm"))
    if resolution not in {"confirm", "correction", "time-change", "rejected"}:
        raise ApiError("메타정보 해결 방식이 올바르지 않습니다.")
    actor = _actor(payload)
    now = utc_now()
    with _connect() as db:
        row = db.execute(
            "SELECT v.*,f.id AS project_fact_id,f.fact_key FROM project_fact_values v JOIN project_facts f ON f.id=v.fact_id WHERE v.id=? AND f.project_id=?",
            (value_id, project_id),
        ).fetchone()
        if not row:
            raise ApiError("프로젝트 메타정보 후보를 찾을 수 없습니다.", 404)
        if row["status"] != "candidate":
            raise ApiError("이미 결정된 메타정보 후보입니다.", 409)
        if decision == "confirmed" and resolution == "time-change" and not row["effective_date"]:
            raise ApiError("시간 변화로 확정하려면 후보의 기준일이 필요합니다.", 409)
        if decision == "confirmed" and resolution == "correction":
            db.execute("UPDATE project_fact_values SET status='superseded' WHERE fact_id=? AND status='confirmed' AND id<>?", (row["project_fact_id"], value_id))
        db.execute("UPDATE project_fact_values SET status=? WHERE id=?", (decision, value_id))
        if decision == "confirmed":
            db.execute("UPDATE project_facts SET status='confirmed',updated_at=? WHERE id=?", (now, row["project_fact_id"]))
        _audit(db, actor, "project.fact_candidate_decided", {"project_id": project_id, "fact_key": row["fact_key"], "value_id": value_id, "decision": decision, "resolution": resolution, "reason": str(payload.get("reason") or "")[:500]})
        snapshot = _project_fact_snapshot(db, project_id)
    return {"projectId": project_id, "valueId": value_id, "decision": decision, "resolution": resolution, "snapshot": snapshot}



def decide_project_fact_candidates_bulk(project_id: str, payload: dict) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    decision = str(payload.get("decision") or "")
    if decision not in {"confirmed", "rejected"}:
        raise ApiError("후보 결정은 confirmed 또는 rejected여야 합니다.")
    value_ids = list(dict.fromkeys(str(item) for item in payload.get("value_ids") or [] if str(item)))
    if not value_ids:
        raise ApiError("일괄 결정할 메타정보 후보를 선택해 주세요.")
    if len(value_ids) > 200:
        raise ApiError("한 번에 최대 200개 후보를 결정할 수 있습니다.", 413)
    placeholders = ",".join("?" for _ in value_ids)
    actor, now = _actor(payload), utc_now()
    with _connect() as db:
        rows = db.execute(
            f"SELECT v.id,v.status,f.id AS project_fact_id,f.fact_key FROM project_fact_values v JOIN project_facts f ON f.id=v.fact_id WHERE f.project_id=? AND v.id IN ({placeholders})",
            (project_id, *value_ids),
        ).fetchall()
        if len(rows) != len(value_ids):
            raise ApiError("선택한 후보 중 현재 프로젝트에 없는 항목이 있습니다.", 404)
        decided = [row for row in rows if row["status"] == "candidate"]
        if len(decided) != len(rows):
            raise ApiError("선택한 후보 중 이미 결정된 항목이 있습니다.", 409)
        db.executemany("UPDATE project_fact_values SET status=? WHERE id=?", [(decision, row["id"]) for row in decided])
        if decision == "confirmed":
            db.executemany("UPDATE project_facts SET status='confirmed',updated_at=? WHERE id=?", [(now, row["project_fact_id"]) for row in decided])
        _audit(db, actor, "project.fact_candidates_bulk_decided", {
            "project_id": project_id, "value_ids": value_ids, "decision": decision,
            "reason": str(payload.get("reason") or "")[:500], "count": len(decided),
        })
        snapshot = _project_fact_snapshot(db, project_id)
    return {"projectId": project_id, "valueIds": value_ids, "decision": decision, "count": len(value_ids), "snapshot": snapshot}


def _record_report_fact_snapshot(db: sqlite3.Connection, project_id: str, plan_id: str, execution_id: str, result: dict) -> None:
    artifact = result.get("artifact") if isinstance(result, dict) else None
    if not isinstance(artifact, dict) or not isinstance(artifact.get("reportDocument"), dict):
        return
    _ensure_project(db, project_id)
    report_document = artifact["reportDocument"]
    fact_snapshot = artifact.get("factSnapshot") or report_document.get("factSnapshot") or {}
    db.execute(
        "INSERT INTO report_fact_snapshots(id,project_id,plan_id,execution_id,artifact_filename,facts_json,report_document_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (
            "reportsnapshot_" + uuid.uuid4().hex,
            project_id,
            plan_id,
            execution_id,
            str(artifact.get("filename") or "AIWorks_보고서.hwpx"),
            _json(fact_snapshot),
            _json(report_document),
            utc_now(),
        ),
    )


def _persist_result_markdown(
    db: sqlite3.Connection,
    project_id: str,
    plan_id: str,
    execution_id: str,
    input_context: dict,
    result: dict,
) -> dict | None:
    artifact = result.get("artifact") if isinstance(result, dict) else None
    if not isinstance(artifact, dict):
        return None
    report_document = artifact.get("reportDocument")
    markdown = str((report_document or {}).get("normalizedMarkdown") or artifact.get("content") or "").strip()
    if not markdown:
        return None
    document_id = str((artifact.get("markdownDocument") or {}).get("id") or "")
    if not document_id and artifact.get("applyMode") == "replace-current-session":
        session_id = str(input_context.get("document_id") or "")
        session = db.execute("SELECT markdown_document_id FROM native_document_sessions WHERE id=?", (session_id,)).fetchone()
        document_id = str(session["markdown_document_id"] or "") if session else ""
    if not document_id:
        current_document_id = str(input_context.get("current_markdown_document_id") or "")
        follow_up = any(
            term in str(input_context.get("intent") or "")
            for term in ("이 내용", "이 문서", "현재 문서", "기존 문서", "수정", "다듬", "바꿔", "변경", "반영", "양식으로", "서식으로", "이어서")
        )
        if current_document_id and follow_up:
            document_id = current_document_id
    artifact_sha256 = ""
    if artifact.get("contentBase64"):
        try:
            artifact_sha256 = hashlib.sha256(base64.b64decode(str(artifact["contentBase64"]), validate=True)).hexdigest()
        except (ValueError, TypeError):
            artifact_sha256 = ""
    record = _save_project_markdown_version(
        db,
        project_id,
        markdown,
        title=str(artifact.get("title") or "AIWorks 프로젝트 문서"),
        document_id=document_id,
        expected_revision=(input_context.get("current_markdown_revision") if document_id == str(input_context.get("current_markdown_document_id") or "") else None),
        source_format="llm-markdown",
        source_filename=str(artifact.get("filename") or ""),
        source_artifact_sha256=artifact_sha256,
        source_session_id=str(input_context.get("document_id") or ""),
        actor="workflow-runtime",
    )
    artifact["markdownDocument"] = {
        "id": record["id"],
        "versionId": record["versionId"],
        "revision": record["revision"],
        "markdownSha256": record["markdownSha256"],
        "projectId": project_id,
        "sourceOfTruth": True,
    }
    artifact["sourceOfTruth"] = {"format": "markdown", "persistence": "project-version", "status": "persisted", "documentId": record["id"], "versionId": record["versionId"]}
    artifact["derivedOutput"] = {
        "format": artifact.get("format") or "hwpx",
        "renderer": ((artifact.get("externalFormatter") or {}).get("packageRef") or (artifact.get("derivedOutput") or {}).get("renderer") or "document.report-hwpx@0.1.0"),
        "derivedFromMarkdownVersion": record["versionId"],
    }
    if (artifact.get("format") or "hwpx") == "hwpx" and artifact.get("contentBase64"):
        try:
            derived_bytes = base64.b64decode(str(artifact["contentBase64"]), validate=True)
            parsed_derived = parse_hwpx(derived_bytes, str(artifact.get("filename") or "AIWorks_보고서.hwpx"))
            project_artifact = _upsert_project_artifact(
                db, record, target_format="hwpx", status="synced", data=derived_bytes,
                filename=str(artifact.get("filename") or ""), media_type=str(artifact.get("mediaType") or "application/hwp+zip"),
                template_id=str((artifact.get("template") or {}).get("id") or ""), renderer=artifact["derivedOutput"]["renderer"],
                instruction=str((artifact.get("template") or {}).get("name") or "보고서 양식 적용"),
                render_map=_build_hwpx_render_map(artifact.get("reportDocument") or {}, parsed_derived), origin="workflow",
            )
            artifact["projectArtifact"] = project_artifact
        except (ApiError, ValueError, TypeError):
            pass
    _audit(db, "workflow-runtime", "project.markdown_rendered", {"project_id": project_id, "document_id": record["id"], "version_id": record["versionId"], "plan_id": plan_id, "execution_id": execution_id, "output_format": artifact.get("format") or "hwpx"}, plan_id=plan_id, execution_id=execution_id)
    return record


def _markdown_title(markdown: str, fallback: str = "AIWorks 프로젝트 문서") -> str:
    match = re.search(r"(?m)^#\s+(.+?)\s*$", str(markdown or ""))
    return (match.group(1).strip() if match else str(fallback or "").strip())[:200] or "AIWorks 프로젝트 문서"


def _record_document_sync_event(
    db: sqlite3.Connection,
    project_id: str,
    document_id: str,
    event_type: str,
    *,
    origin: str,
    status: str,
    artifact_id: str = "",
    source_version_id: str = "",
    target_version_id: str = "",
    detail: dict | None = None,
) -> str:
    event_id = "sync_" + uuid.uuid4().hex
    db.execute(
        "INSERT INTO project_document_sync_events(id,project_id,document_id,artifact_id,event_type,origin,status,source_version_id,target_version_id,detail_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (event_id, project_id, document_id, artifact_id or None, event_type, origin, status, source_version_id or None, target_version_id or None, _json(detail or {}), utc_now()),
    )
    return event_id


def _mark_project_artifacts_stale(db: sqlite3.Connection, project_id: str, document_id: str, version_id: str, revision: int) -> None:
    rows = db.execute("SELECT id,status FROM project_document_artifacts WHERE document_id=?", (document_id,)).fetchall()
    if not rows:
        return
    now = utc_now()
    db.execute("UPDATE project_document_artifacts SET status='stale',error=NULL,updated_at=? WHERE document_id=?", (now, document_id))
    for row in rows:
        _record_document_sync_event(
            db, project_id, document_id, "artifact.stale", origin="markdown", status="stale",
            artifact_id=row["id"], source_version_id=version_id,
            detail={"markdownRevision": revision, "previousStatus": row["status"]},
        )


def _project_artifact_result(row: sqlite3.Row, *, include_content: bool = False) -> dict:
    result = {
        "id": row["id"], "documentId": row["document_id"], "format": row["format"], "variantKey": row["variant_key"],
        "sourceVersionId": row["source_version_id"], "sourceRevision": row["source_revision"], "sourceMarkdownSha256": row["source_markdown_sha256"],
        "status": row["status"], "filename": row["filename"], "mediaType": row["media_type"], "artifactSha256": row["artifact_sha256"],
        "templateId": row["template_id"], "renderer": row["renderer"], "instruction": row["instruction"], "renderMap": _load_json(row["render_map_json"], {}),
        "error": row["error"], "createdAt": row["created_at"], "updatedAt": row["updated_at"],
    }
    if include_content and row["content_blob"] is not None:
        result["contentBase64"] = base64.b64encode(bytes(row["content_blob"])).decode("ascii")
    return result


_ARTIFACT_RELATIONS = {
    "derived_from", "references", "summarizes", "transforms",
    "validates", "supersedes", "conflicts_with",
}
_ACYCLIC_ARTIFACT_RELATIONS = {
    "derived_from", "summarizes", "transforms", "supersedes",
}


def _artifact_version_result(row: sqlite3.Row, *, include_content: bool = False) -> dict:
    result = {
        "id": row["id"], "artifactId": row["artifact_id"], "version": int(row["version"]),
        "mediaType": row["media_type"], "filename": row["filename"],
        "contentSha256": row["content_sha256"], "metadata": _load_json(row["metadata_json"], {}),
        "workflowRunId": row["workflow_run_id"], "createdBy": row["created_by"],
        "createdAt": row["created_at"],
    }
    content_json = _load_json(row["content_json"], {})
    if content_json:
        result["content"] = content_json
    if include_content and row["content_blob"] is not None:
        result["contentBase64"] = base64.b64encode(bytes(row["content_blob"])).decode("ascii")
    return result


def _artifact_result(
    db: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    include_versions: bool = True,
    include_content: bool = False,
) -> dict:
    result = {
        "id": row["id"], "projectId": row["project_id"],
        "artifactType": row["artifact_type"], "title": row["title"],
        "status": row["status"], "currentVersionId": row["current_version_id"],
        "source": {"type": row["source_type"], "id": row["source_id"]},
        "createdBy": row["created_by"], "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
    if include_versions:
        versions = db.execute(
            "SELECT * FROM artifact_versions WHERE artifact_id=? ORDER BY version DESC",
            (row["id"],),
        ).fetchall()
        result["versions"] = [
            _artifact_version_result(item, include_content=include_content and item["id"] == row["current_version_id"])
            for item in versions
        ]
    return result


def _sync_generic_artifact_version(
    db: sqlite3.Connection,
    project_id: str,
    *,
    artifact_type: str,
    title: str,
    source_type: str,
    source_id: str,
    media_type: str,
    filename: str = "",
    content_blob: bytes | None = None,
    content_json=None,
    metadata: dict | None = None,
    actor: str = "system",
    workflow_run_id: str = "",
) -> tuple[dict, dict]:
    project_id = _safe_project_id(project_id)
    if not db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
        raise ApiError("Artifact를 저장할 프로젝트를 찾을 수 없습니다.", 404)
    normalized_json = content_json if isinstance(content_json, (dict, list)) else (
        {"text": str(content_json)} if content_json not in (None, "") else {}
    )
    blob = bytes(content_blob) if content_blob is not None else None
    digest_source = blob if blob is not None else _json(normalized_json).encode("utf-8")
    digest = hashlib.sha256(digest_source).hexdigest()
    now = utc_now()
    row = db.execute(
        "SELECT * FROM artifacts WHERE project_id=? AND source_type=? AND source_id=?",
        (project_id, source_type, source_id),
    ).fetchone()
    if row:
        artifact_id = row["id"]
        existing = db.execute(
            "SELECT * FROM artifact_versions WHERE artifact_id=? AND content_sha256=?",
            (artifact_id, digest),
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE artifacts SET title=?,status='active',current_version_id=?,updated_at=? WHERE id=?",
                (title[:240], existing["id"], now, artifact_id),
            )
            updated = db.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
            return _artifact_result(db, updated), _artifact_version_result(existing)
        latest = db.execute(
            "SELECT COALESCE(MAX(version),0) AS version FROM artifact_versions WHERE artifact_id=?",
            (artifact_id,),
        ).fetchone()
        version_number = int(latest["version"]) + 1
    else:
        artifact_id = "gart_" + uuid.uuid4().hex
        version_number = 1
        db.execute(
            """
            INSERT INTO artifacts(
                id,project_id,artifact_type,title,status,current_version_id,
                source_type,source_id,created_by,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                artifact_id, project_id, artifact_type[:80], title[:240], "active", None,
                source_type[:80], source_id[:200], actor, now, now,
            ),
        )
    version_id = "gartver_" + uuid.uuid4().hex
    db.execute(
        """
        INSERT INTO artifact_versions(
            id,artifact_id,version,media_type,filename,content_blob,content_json,
            content_sha256,metadata_json,workflow_run_id,created_by,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            version_id, artifact_id, version_number, media_type[:160],
            filename[:240] or None, blob, _json(normalized_json), digest,
            _json(metadata or {}), workflow_run_id or None, actor, now,
        ),
    )
    db.execute(
        "UPDATE artifacts SET title=?,artifact_type=?,status='active',current_version_id=?,updated_at=? WHERE id=?",
        (title[:240], artifact_type[:80], version_id, now, artifact_id),
    )
    artifact = db.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
    version = db.execute("SELECT * FROM artifact_versions WHERE id=?", (version_id,)).fetchone()
    return _artifact_result(db, artifact), _artifact_version_result(version)


def _artifact_relation_would_cycle(
    db: sqlite3.Connection,
    project_id: str,
    source_version_id: str,
    target_version_id: str,
) -> bool:
    adjacency: dict[str, set[str]] = {}
    rows = db.execute(
        "SELECT source_version_id,target_version_id FROM artifact_relations WHERE project_id=? AND relation IN ('derived_from','summarizes','transforms','supersedes')",
        (project_id,),
    ).fetchall()
    for row in rows:
        adjacency.setdefault(str(row["source_version_id"]), set()).add(str(row["target_version_id"]))
    stack = [target_version_id]
    visited = set()
    while stack:
        current = stack.pop()
        if current == source_version_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        stack.extend(adjacency.get(current, ()))
    return False


def _create_artifact_relation(
    db: sqlite3.Connection,
    project_id: str,
    source_version_id: str,
    target_version_id: str,
    relation: str,
    *,
    actor: str,
    metadata: dict | None = None,
) -> dict:
    if relation not in _ARTIFACT_RELATIONS:
        raise ApiError("지원하지 않는 Artifact 관계입니다.")
    if source_version_id == target_version_id:
        raise ApiError("같은 Artifact Version을 자기 자신과 연결할 수 없습니다.", 409)
    rows = db.execute(
        """
        SELECT v.id,a.project_id FROM artifact_versions v
        JOIN artifacts a ON a.id=v.artifact_id
        WHERE v.id IN (?,?)
        """,
        (source_version_id, target_version_id),
    ).fetchall()
    if len(rows) != 2 or {str(row["project_id"]) for row in rows} != {project_id}:
        raise ApiError("같은 프로젝트의 Artifact Version만 연결할 수 있습니다.", 403)
    if relation in _ACYCLIC_ARTIFACT_RELATIONS and _artifact_relation_would_cycle(
        db, project_id, source_version_id, target_version_id
    ):
        raise ApiError("Artifact 계보에 순환 관계를 만들 수 없습니다.", 409)
    relation_id = "gartrel_" + uuid.uuid4().hex
    now = utc_now()
    db.execute(
        """
        INSERT OR IGNORE INTO artifact_relations(
            id,project_id,source_version_id,target_version_id,relation,
            metadata_json,created_by,created_at
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            relation_id, project_id, source_version_id, target_version_id,
            relation, _json(metadata or {}), actor, now,
        ),
    )
    row = db.execute(
        "SELECT * FROM artifact_relations WHERE source_version_id=? AND target_version_id=? AND relation=?",
        (source_version_id, target_version_id, relation),
    ).fetchone()
    return {
        "id": row["id"], "projectId": row["project_id"],
        "sourceVersionId": row["source_version_id"], "targetVersionId": row["target_version_id"],
        "relation": row["relation"], "metadata": _load_json(row["metadata_json"], {}),
        "createdBy": row["created_by"], "createdAt": row["created_at"],
    }


def list_project_artifacts(project_id: str) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    with _connect() as db:
        if not db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
            raise ApiError("프로젝트를 찾을 수 없습니다.", 404)
        rows = db.execute(
            "SELECT * FROM artifacts WHERE project_id=? AND status!='deleted' ORDER BY updated_at DESC",
            (project_id,),
        ).fetchall()
        relations = db.execute(
            "SELECT * FROM artifact_relations WHERE project_id=? ORDER BY created_at",
            (project_id,),
        ).fetchall()
        evidence = db.execute(
            "SELECT * FROM artifact_evidence WHERE project_id=? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
        items = [_artifact_result(db, row, include_versions=True) for row in rows]
    return {
        "items": items,
        "count": len(items),
        "relations": [
            {
                "id": row["id"], "sourceVersionId": row["source_version_id"],
                "targetVersionId": row["target_version_id"], "relation": row["relation"],
                "metadata": _load_json(row["metadata_json"], {}),
                "createdBy": row["created_by"], "createdAt": row["created_at"],
            }
            for row in relations
        ],
        "evidence": [_artifact_evidence_result(row) for row in evidence],
    }


def create_project_artifact(project_id: str, payload: dict) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    actor = _actor(payload)
    artifact_type = str(payload.get("artifact_type") or "file").strip()
    title = re.sub(r"\s+", " ", str(payload.get("title") or "").strip())
    media_type = str(payload.get("media_type") or "application/octet-stream").strip()
    if not re.fullmatch(r"[a-z][a-z0-9._-]{1,79}", artifact_type) or not title:
        raise ApiError("Artifact 유형과 제목이 필요합니다.")
    content_blob = None
    if payload.get("content_base64"):
        try:
            content_blob = base64.b64decode(str(payload["content_base64"]), validate=True)
        except (ValueError, TypeError) as error:
            raise ApiError("Artifact content_base64가 올바르지 않습니다.") from error
        if len(content_blob) > MAX_UNCOMPRESSED_BYTES:
            raise ApiError("Artifact는 50MB를 넘을 수 없습니다.", 413)
    content_json = payload.get("content")
    if content_blob is None and content_json in (None, "", {}, []):
        raise ApiError("Artifact 내용이 필요합니다.")
    source_id = str(payload.get("source_id") or "manual:" + uuid.uuid4().hex)
    with _connect() as db:
        _ensure_project(db, project_id, actor)
        artifact, version = _sync_generic_artifact_version(
            db, project_id, artifact_type=artifact_type, title=title,
            source_type=str(payload.get("source_type") or "manual"),
            source_id=source_id, media_type=media_type,
            filename=str(payload.get("filename") or ""),
            content_blob=content_blob, content_json=content_json,
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            actor=actor, workflow_run_id=str(payload.get("workflow_run_id") or ""),
        )
        _audit(db, actor, "artifact.created", {
            "project_id": project_id, "artifact_id": artifact["id"],
            "version_id": version["id"], "artifact_type": artifact_type,
        })
    return {"artifact": artifact, "version": version}


def append_project_artifact_version(project_id: str, artifact_id: str, payload: dict) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    actor = _actor(payload)
    with _connect() as db:
        artifact_row = db.execute(
            "SELECT * FROM artifacts WHERE id=? AND project_id=? AND status!='deleted'",
            (artifact_id, project_id),
        ).fetchone()
        if not artifact_row:
            raise ApiError("Artifact를 찾을 수 없습니다.", 404)
        current = db.execute(
            "SELECT version FROM artifact_versions WHERE id=?",
            (artifact_row["current_version_id"],),
        ).fetchone()
        expected = payload.get("expected_version")
        if expected is not None and int(expected) != int(current["version"]):
            raise ApiError("Artifact Version이 변경되었습니다. 다시 불러와 주세요.", 409)
        content_blob = None
        if payload.get("content_base64"):
            try:
                content_blob = base64.b64decode(str(payload["content_base64"]), validate=True)
            except (ValueError, TypeError) as error:
                raise ApiError("Artifact content_base64가 올바르지 않습니다.") from error
        content_json = payload.get("content")
        if content_blob is None and content_json in (None, "", {}, []):
            raise ApiError("새 Artifact Version 내용이 필요합니다.")
        artifact, version = _sync_generic_artifact_version(
            db, project_id, artifact_type=artifact_row["artifact_type"],
            title=str(payload.get("title") or artifact_row["title"]),
            source_type=artifact_row["source_type"], source_id=artifact_row["source_id"],
            media_type=str(payload.get("media_type") or "application/octet-stream"),
            filename=str(payload.get("filename") or ""),
            content_blob=content_blob, content_json=content_json,
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            actor=actor, workflow_run_id=str(payload.get("workflow_run_id") or ""),
        )
        _audit(db, actor, "artifact.version_created", {
            "project_id": project_id, "artifact_id": artifact_id, "version_id": version["id"],
        })
    return {"artifact": artifact, "version": version}


def get_project_artifact(project_id: str, artifact_id: str, *, include_content: bool = False) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    with _connect() as db:
        row = db.execute(
            "SELECT * FROM artifacts WHERE id=? AND project_id=? AND status!='deleted'",
            (artifact_id, project_id),
        ).fetchone()
        if not row:
            raise ApiError("Artifact를 찾을 수 없습니다.", 404)
        return _artifact_result(db, row, include_versions=True, include_content=include_content)


def create_project_artifact_relation(project_id: str, payload: dict) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    actor = _actor(payload)
    with _connect() as db:
        relation = _create_artifact_relation(
            db, project_id,
            str(payload.get("source_version_id") or ""),
            str(payload.get("target_version_id") or ""),
            str(payload.get("relation") or ""),
            actor=actor,
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        )
        _audit(db, actor, "artifact.relation_created", relation)
    return relation



def _artifact_evidence_result(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "projectId": row["project_id"],
        "artifactId": row["artifact_id"], "artifactVersionId": row["artifact_version_id"],
        "sourceArtifactId": row["source_artifact_id"], "sourceVersionId": row["source_version_id"],
        "locator": row["locator"], "excerpt": row["excerpt"],
        "excerptSha256": row["excerpt_sha256"], "confidence": float(row["confidence"]),
        "metadata": _load_json(row["metadata_json"], {}),
        "createdBy": row["created_by"], "createdAt": row["created_at"],
    }


def list_project_artifact_evidence(project_id: str, payload: dict | None = None) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    payload = payload or {}
    actor = _actor(payload)
    artifact_id = str(payload.get("artifact_id") or "").strip()
    with _connect() as db:
        _ensure_project(db, project_id, actor)
        if artifact_id:
            rows = db.execute("SELECT * FROM artifact_evidence WHERE project_id=? AND artifact_id=? ORDER BY created_at DESC", (project_id, artifact_id)).fetchall()
        else:
            rows = db.execute("SELECT * FROM artifact_evidence WHERE project_id=? ORDER BY created_at DESC", (project_id,)).fetchall()
    return {"items": [_artifact_evidence_result(row) for row in rows], "count": len(rows), "projectId": project_id}


def create_project_artifact_evidence(project_id: str, payload: dict) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    actor = _actor(payload)
    artifact_id = str(payload.get("artifact_id") or "").strip()
    artifact_version_id = str(payload.get("artifact_version_id") or "").strip()
    source_artifact_id = str(payload.get("source_artifact_id") or "").strip() or None
    source_version_id = str(payload.get("source_version_id") or "").strip() or None
    locator = str(payload.get("locator") or "").strip()[:1_000]
    excerpt = str(payload.get("excerpt") or "").strip()[:20_000]
    if not artifact_id or not locator or not excerpt:
        raise ApiError("Artifact, 근거 위치와 발췌문이 필요합니다.")
    try:
        confidence = float(payload.get("confidence", 1.0))
    except (TypeError, ValueError) as error:
        raise ApiError("근거 신뢰도는 0~1 숫자여야 합니다.") from error
    if confidence < 0 or confidence > 1:
        raise ApiError("근거 신뢰도는 0~1 범위여야 합니다.")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    with _connect() as db:
        _require_project_role(db, project_id, actor, {"owner", "admin", "editor"})
        artifact = db.execute("SELECT * FROM artifacts WHERE id=? AND project_id=? AND status!='deleted'", (artifact_id, project_id)).fetchone()
        if not artifact:
            raise ApiError("근거를 연결할 Artifact를 찾을 수 없습니다.", 404)
        artifact_version_id = artifact_version_id or str(artifact["current_version_id"] or "")
        target_version = db.execute("SELECT 1 FROM artifact_versions WHERE id=? AND artifact_id=?", (artifact_version_id, artifact_id)).fetchone()
        if not target_version:
            raise ApiError("근거를 연결할 Artifact Version을 찾을 수 없습니다.", 404)
        if source_version_id:
            source = db.execute("SELECT v.artifact_id FROM artifact_versions v JOIN artifacts a ON a.id=v.artifact_id WHERE v.id=? AND a.project_id=?", (source_version_id, project_id)).fetchone()
            if not source:
                raise ApiError("근거 원본 Version을 찾을 수 없습니다.", 404)
            inferred_source_artifact_id = str(source["artifact_id"])
            if source_artifact_id and source_artifact_id != inferred_source_artifact_id:
                raise ApiError("근거 원본 Artifact와 Version이 일치하지 않습니다.", 409)
            source_artifact_id = inferred_source_artifact_id
        elif source_artifact_id and not db.execute("SELECT 1 FROM artifacts WHERE id=? AND project_id=?", (source_artifact_id, project_id)).fetchone():
            raise ApiError("근거 원본 Artifact를 찾을 수 없습니다.", 404)
        evidence_id = "evidence_" + uuid.uuid4().hex
        now = utc_now()
        digest = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
        db.execute("INSERT INTO artifact_evidence(id,project_id,artifact_id,artifact_version_id,source_artifact_id,source_version_id,locator,excerpt,excerpt_sha256,confidence,metadata_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (evidence_id, project_id, artifact_id, artifact_version_id, source_artifact_id, source_version_id, locator, excerpt, digest, confidence, _json(metadata), actor, now))
        _audit(db, actor, "artifact.evidence_created", {"project_id": project_id, "artifact_id": artifact_id, "artifact_version_id": artifact_version_id, "evidence_id": evidence_id, "excerpt_sha256": digest})
        row = db.execute("SELECT * FROM artifact_evidence WHERE id=?", (evidence_id,)).fetchone()
    return _artifact_evidence_result(row)


def _upsert_project_artifact(
    db: sqlite3.Connection,
    document: dict,
    *,
    target_format: str,
    status: str,
    data: bytes | None = None,
    filename: str = "",
    media_type: str = "",
    template_id: str = "",
    renderer: str = "",
    instruction: str = "",
    render_map: dict | None = None,
    error: str = "",
    variant_key: str = "default",
    origin: str = "renderer",
) -> dict:
    row = db.execute("SELECT * FROM project_document_artifacts WHERE document_id=? AND format=? AND variant_key=?", (document["id"], target_format, variant_key)).fetchone()
    artifact_id = row["id"] if row else "artifact_" + uuid.uuid4().hex
    now = utc_now()
    blob = data if data is not None else (bytes(row["content_blob"]) if row and row["content_blob"] is not None else None)
    digest = hashlib.sha256(blob).hexdigest() if blob is not None else (row["artifact_sha256"] if row else None)
    values = (
        document["versionId"], document["revision"], document["markdownSha256"], status,
        filename or (row["filename"] if row else None), media_type or (row["media_type"] if row else None), blob, digest,
        template_id or (row["template_id"] if row else None), renderer or (row["renderer"] if row else None),
        instruction or (row["instruction"] if row else None), _json(render_map if render_map is not None else (_load_json(row["render_map_json"], {}) if row else {})),
        error or None, now,
    )
    if row:
        db.execute("UPDATE project_document_artifacts SET source_version_id=?,source_revision=?,source_markdown_sha256=?,status=?,filename=?,media_type=?,content_blob=?,artifact_sha256=?,template_id=?,renderer=?,instruction=?,render_map_json=?,error=?,updated_at=? WHERE id=?", (*values, artifact_id))
    else:
        db.execute("INSERT INTO project_document_artifacts(id,document_id,format,variant_key,source_version_id,source_revision,source_markdown_sha256,status,filename,media_type,content_blob,artifact_sha256,template_id,renderer,instruction,render_map_json,error,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (artifact_id, document["id"], target_format, variant_key, *values[:-1], now, now))
    if blob is not None and status != "failed":
        generic_artifact, generic_version = _sync_generic_artifact_version(
            db,
            document["projectId"],
            artifact_type="document." + target_format,
            title=filename or document.get("title") or (target_format.upper() + " 파생 문서"),
            source_type="project-document-artifact",
            source_id=artifact_id,
            media_type=media_type or "application/octet-stream",
            filename=filename,
            content_blob=blob,
            metadata={
                "legacyArtifactId": artifact_id,
                "sourceMarkdownVersionId": document["versionId"],
                "sourceMarkdownSha256": document["markdownSha256"],
                "templateId": template_id,
                "renderer": renderer,
                "status": status,
            },
            actor=origin,
        )
        markdown_artifact = db.execute(
            "SELECT current_version_id FROM artifacts WHERE project_id=? AND source_type='markdown-document' AND source_id=?",
            (document["projectId"], document["id"]),
        ).fetchone()
        if markdown_artifact and markdown_artifact["current_version_id"]:
            _create_artifact_relation(
                db, document["projectId"], generic_version["id"], markdown_artifact["current_version_id"],
                "derived_from", actor=origin, metadata={"legacyArtifactId": artifact_id},
            )

    _record_document_sync_event(
        db, document["projectId"], document["id"], "artifact." + status, origin=origin, status=status,
        artifact_id=artifact_id, source_version_id=document["versionId"], detail={"format": target_format, "revision": document["revision"], "error": error or None},
    )
    return _project_artifact_result(db.execute("SELECT * FROM project_document_artifacts WHERE id=?", (artifact_id,)).fetchone())


def _semantic_text(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"^(?:(?:[-*+•·○ㅇ□▪◦])\s*)+", "", text).strip()
    text = re.sub(r"^\d+[.)]\s+", "", text).strip()
    return text


def _build_hwpx_render_map(report_document: dict, parsed: dict) -> dict:
    paragraph_items = list(parsed.get("paragraphs") or [])
    used: set[str] = set()
    entries = []
    canonical_document = REPORT_DOCUMENT_MCP.parse(
        str((report_document.get("source") or {}).get("content") or ""),
        title=str(report_document.get("title") or ""), style_profile="standard",
    )
    canonical_blocks = canonical_document.get("blocks") or []

    def match(value: str) -> str:
        expected = _semantic_text(value)
        for item in paragraph_items:
            paragraph_id = str(item.get("id") or "")
            if paragraph_id in used or _semantic_text(item.get("text") or "") != expected:
                continue
            used.add(paragraph_id)
            return paragraph_id
        return ""

    for block_index, block in enumerate(report_document.get("blocks") or []):
        canonical_block = canonical_blocks[block_index] if block_index < len(canonical_blocks) else {}
        if block.get("type") == "table":
            for row_index, row in enumerate(block.get("rows") or []):
                for column_index, value in enumerate(row):
                    paragraph_id = match(str(value or ""))
                    if paragraph_id:
                        canonical_rows = canonical_block.get("rows") or []
                        canonical_value = canonical_rows[row_index][column_index] if row_index < len(canonical_rows) and column_index < len(canonical_rows[row_index]) else str(value or "")
                        entries.append({"paragraphId": paragraph_id, "blockId": block.get("id"), "blockType": "table", "blockIndex": block_index, "cellRow": row_index, "cellColumn": column_index, "sourceText": str(value or ""), "canonicalText": str(canonical_value or "")})
        else:
            value = str(block.get("text") or "")
            paragraph_id = match(value)
            if paragraph_id:
                entries.append({"paragraphId": paragraph_id, "blockId": block.get("id"), "blockType": block.get("type"), "blockIndex": block_index, "sourceText": value, "canonicalText": str(canonical_block.get("text") or value)})
    return {
        "contractVersion": "1.1",
        "strategy": "semantic-paragraph-cell",
        "entries": entries,
        "mapped": len(entries),
        "paragraphs": len(paragraph_items),
        "blockCount": len(report_document.get("blocks") or []),
    }


def _render_map_value(report_document: dict, mapping: dict) -> str:
    blocks = report_document.get("blocks") or []
    block_index = int(mapping.get("blockIndex", -1))
    if block_index < 0 or block_index >= len(blocks):
        raise ApiError("기존 HWPX 양식과 현재 Markdown의 문서 구조가 달라 전체 렌더링이 필요합니다.", 409)
    block = blocks[block_index]
    if str(block.get("type") or "") != str(mapping.get("blockType") or ""):
        raise ApiError("기존 HWPX 양식과 현재 Markdown의 블록 형식이 달라 전체 렌더링이 필요합니다.", 409)
    if block.get("type") != "table":
        return str(block.get("text") or "")
    row_index = int(mapping.get("cellRow", -1))
    column_index = int(mapping.get("cellColumn", -1))
    rows = block.get("rows") or []
    if row_index < 0 or row_index >= len(rows) or column_index < 0 or column_index >= len(rows[row_index]):
        raise ApiError("기존 HWPX 표와 현재 Markdown 표의 크기가 달라 전체 렌더링이 필요합니다.", 409)
    return str(rows[row_index][column_index] or "")


def _refresh_hwpx_layout_in_place(data: bytes, render_map: dict, report_document: dict) -> tuple[bytes, dict]:
    """Refresh mapped text while retaining every HWPX layout/style resource."""
    entries = list(render_map.get("entries") or [])
    if not entries:
        raise ApiError("기존 HWPX에 Markdown 연결 정보가 없어 전체 렌더링이 필요합니다.", 409)
    old_block_count = int(render_map.get("blockCount") or (max(int(item.get("blockIndex", -1)) for item in entries) + 1))
    new_blocks = list(report_document.get("blocks") or [])
    new_block_count = len(new_blocks)
    retained_entries = [item for item in entries if int(item.get("blockIndex", -1)) < new_block_count]
    removed_entries = [item for item in entries if int(item.get("blockIndex", -1)) >= new_block_count]
    for mapping in retained_entries:
        block_index = int(mapping.get("blockIndex", -1))
        if block_index < 0 or str(new_blocks[block_index].get("type") or "") != str(mapping.get("blockType") or ""):
            raise ApiError("Markdown 중간 구조가 변경되어 기존 HWPX 양식을 안전하게 부분 갱신할 수 없습니다.", 409)
    added_blocks = new_blocks[old_block_count:] if new_block_count > old_block_count else []
    if any(block.get("type") == "table" for block in added_blocks) or any(item.get("blockType") == "table" for item in removed_entries):
        raise ApiError("추가·삭제된 표는 기존 HWPX 양식의 표 구조와 자동 병합할 수 없습니다.", 409)
    replacements: dict[str, tuple[str, str]] = {}
    for mapping in retained_entries:
        target = str(mapping.get("paragraphId") or "")
        if not re.fullmatch(r"Contents/section\d+\.xml#p[1-9]\d*", target, re.IGNORECASE):
            raise ApiError("기존 HWPX의 Markdown 연결 위치가 올바르지 않습니다.", 409)
        value = _render_map_value(report_document, mapping)
        replacements[target] = (value, _semantic_text(value))
    try:
        source_archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise ApiError("기존 파생 문서가 유효한 HWPX가 아닙니다.", 409) from error
    section_payloads: dict[str, bytes] = {}
    with source_archive:
        infos = source_archive.infolist()
        by_section: dict[str, list[tuple[int, str, str]]] = {}
        for target, (value, canonical) in replacements.items():
            section_name, paragraph_token = target.split("#", 1)
            by_section.setdefault(section_name.lower(), []).append((int(paragraph_token[1:]), value, canonical))
        names = {info.filename.lower(): info.filename for info in infos}
        section_models: dict[str, tuple[str, bytes, ElementTree.Element, list[tuple[ElementTree.Element, str]]]] = {}
        required_sections = set(by_section)
        required_sections.update(str(item.get("paragraphId") or "").split("#", 1)[0].lower() for item in removed_entries)
        if added_blocks:
            anchor = max(retained_entries, key=lambda item: int(item.get("blockIndex", -1)), default=None)
            if not anchor:
                raise ApiError("새 문단을 삽입할 기존 HWPX 본문 기준점이 없습니다.", 409)
            required_sections.add(str(anchor.get("paragraphId") or "").split("#", 1)[0].lower())
        for section_key in required_sections:
            section_name = names.get(section_key)
            if not section_name:
                raise ApiError("기존 HWPX에서 연결된 본문 구역을 찾지 못했습니다.", 409)
            original = source_archive.read(section_name)
            root, nodes = _hwpx_paragraph_nodes(original)
            section_models[section_key] = (section_name, original, root, nodes)
        for section_key, items in by_section.items():
            section_name, original, root, nodes = section_models[section_key]
            for paragraph_index, value, canonical in items:
                if paragraph_index > len(nodes):
                    raise ApiError("기존 HWPX에서 연결된 문단을 찾지 못했습니다.", 409)
                node, before = nodes[paragraph_index - 1]
                target_key = section_key + "#p" + str(paragraph_index)
                mapping = next(item for item in entries if str(item.get("paragraphId") or "").lower() == target_key.lower())
                expected = {_semantic_text(mapping.get("sourceText") or ""), _semantic_text(mapping.get("canonicalText") or "")}
                expected.discard("")
                if expected and _semantic_text(before) not in expected:
                    raise ApiError("HWPX 내용이 MD 연결 정보와 달라 먼저 HWPX 변경을 MD에 반영해야 합니다.", 409)
                marker = re.match(r"^((?:(?:[-*+•·○ㅇ□▪◦])\s*)+)", before)
                replacement = (marker.group(1) + canonical) if marker and canonical else value
                _set_hwpx_paragraph_text(node, replacement)
        for mapping in sorted(removed_entries, key=lambda item: int(str(item.get("paragraphId") or "").rsplit("#p", 1)[-1]), reverse=True):
            target = str(mapping.get("paragraphId") or "")
            section_key, paragraph_token = target.split("#", 1)
            section_name, original, root, nodes = section_models[section_key.lower()]
            paragraph_index = int(paragraph_token[1:])
            if paragraph_index > len(nodes):
                raise ApiError("삭제할 기존 HWPX 문단을 찾지 못했습니다.", 409)
            node = nodes[paragraph_index - 1][0]
            parent = next((candidate for candidate in root.iter() if node in list(candidate)), None)
            if parent is None:
                raise ApiError("기존 HWPX 문단의 상위 구조를 찾지 못했습니다.", 409)
            parent.remove(node)
        if added_blocks:
            anchor_mapping = max(retained_entries, key=lambda item: int(item.get("blockIndex", -1)))
            anchor_target = str(anchor_mapping.get("paragraphId") or "")
            anchor_section, anchor_token = anchor_target.split("#", 1)
            section_name, original, root, nodes = section_models[anchor_section.lower()]
            anchor_node = nodes[int(anchor_token[1:]) - 1][0]
            parent = next((candidate for candidate in root.iter() if anchor_node in list(candidate)), None)
            if parent is None:
                raise ApiError("새 문단을 삽입할 HWPX 본문 구조를 찾지 못했습니다.", 409)
            insert_at = list(parent).index(anchor_node) + 1
            for offset, block in enumerate(added_blocks):
                prototype_mapping = next(
                    (item for item in reversed(retained_entries) if item.get("blockType") == block.get("type")),
                    anchor_mapping,
                )
                prototype_target = str(prototype_mapping.get("paragraphId") or "")
                prototype_section, prototype_token = prototype_target.split("#", 1)
                prototype_nodes = section_models[prototype_section.lower()][3]
                prototype = prototype_nodes[int(prototype_token[1:]) - 1][0]
                appended = copy.deepcopy(prototype)
                _set_hwpx_paragraph_text(appended, str(block.get("text") or ""))
                parent.insert(insert_at + offset, appended)
        for section_name, original, root, _nodes in section_models.values():
            section_payloads[section_name] = _serialize_hwpx_xml(original, root)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as target_archive:
            for info in infos:
                target_archive.writestr(info, section_payloads.get(info.filename, source_archive.read(info.filename)))
    refreshed = output.getvalue()
    refreshed_map = _build_hwpx_render_map(report_document, parse_hwpx(refreshed, "layout-preserved.hwpx"))
    refreshed_map["renderMode"] = "layout-preserving-structure-refresh" if old_block_count != new_block_count else "layout-preserving-text-refresh"
    return refreshed, refreshed_map


def _semantic_patch_markdown(markdown: str, mapping: dict, before: str, after: str) -> str:
    before_clean, after_clean = _semantic_text(before), _semantic_text(after)
    expected_values = {before_clean, _semantic_text(mapping.get("canonicalText") or "")}
    expected_values.discard("")
    if not before_clean:
        raise ApiError("HWPX 변경 원문이 비어 있어 Markdown에 반영할 수 없습니다.", 409)
    lines = str(markdown or "").splitlines()
    if mapping.get("blockType") == "table" and mapping.get("cellRow") is not None:
        table_rows = [index for index, line in enumerate(lines) if line.strip().startswith("|") and line.strip().endswith("|") and not re.fullmatch(r"\|?(?:\s*:?-{3,}:?\s*\|)+", line.strip())]
        row_index = int(mapping.get("cellRow") or 0)
        if row_index < len(table_rows):
            line_index = table_rows[row_index]
            cells = [cell.strip() for cell in lines[line_index].strip().strip("|").split("|")]
            column_index = int(mapping.get("cellColumn") or 0)
            if column_index < len(cells) and _semantic_text(cells[column_index]) in expected_values:
                cells[column_index] = after_clean
                lines[line_index] = "| " + " | ".join(cells) + " |"
                return "\n".join(lines).strip()
    for index, line in enumerate(lines):
        stripped = line.strip()
        prefix_match = re.match(r"^(\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|※\s*))(.+)$", line)
        value = prefix_match.group(2) if prefix_match else stripped
        if _semantic_text(value) not in expected_values:
            continue
        prefix = prefix_match.group(1) if prefix_match else line[: len(line) - len(line.lstrip())]
        lines[index] = prefix + after_clean
        return "\n".join(lines).strip()
    raise ApiError("HWPX 변경 위치가 현재 Markdown revision과 일치하지 않습니다. MD 탭에서 충돌을 확인해 주세요.", 409)


def _semantic_patch_from_hwpx_artifacts(markdown: str, render_map: dict, before_parsed: dict, after_parsed: dict) -> tuple[str, list[dict]]:
    before_items = {str(item.get("id") or ""): str(item.get("text") or "") for item in before_parsed.get("paragraphs") or []}
    after_items = {str(item.get("id") or ""): str(item.get("text") or "") for item in after_parsed.get("paragraphs") or []}
    entries = {str(item.get("paragraphId") or ""): item for item in render_map.get("entries") or []}
    changed = []
    updated = markdown
    for paragraph_id, mapping in entries.items():
        if paragraph_id not in before_items or paragraph_id not in after_items:
            continue
        before, after = before_items[paragraph_id], after_items[paragraph_id]
        if before == after:
            continue
        updated = _semantic_patch_markdown(updated, mapping, before, after)
        changed.append({"paragraphId": paragraph_id, "blockId": mapping.get("blockId"), "before": before, "after": after})
    unrecognized = [
        paragraph_id for paragraph_id in set(before_items) & set(after_items)
        if paragraph_id not in entries and before_items[paragraph_id] != after_items[paragraph_id]
        and _semantic_text(before_items[paragraph_id]) != _semantic_text(after_items[paragraph_id])
    ]
    if unrecognized:
        raise ApiError("HWPX에서 Markdown과 연결되지 않은 구조 변경이 발견되었습니다. MD 탭에서 병합해 주세요.", 409)
    return updated, changed


def _markdown_fact_candidates(markdown: str) -> list[dict]:
    text = str(markdown or "")
    patterns = (
        ("project.name", "사업명", r"(?:^|\n)\s*(?:[-*]\s*)?(?:\*\*)?사업명(?:\*\*)?\s*[:：]\s*([^\n|]{2,120})"),
        ("project.period", "사업기간", r"(?:^|\n)\s*(?:[-*]\s*)?(?:\*\*)?사업기간(?:\*\*)?\s*[:：]\s*([^\n|]{4,120})"),
        ("budget.total", "총사업비", r"(?:^|\n)\s*(?:[-*]\s*)?(?:\*\*)?총사업비(?:\*\*)?\s*[:：]\s*([0-9,.]+\s*(?:백만원|억원|원))"),
    )
    items = []
    for key, label, pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            items.append({"key": key, "label": label, "value": match.group(1).strip().strip("* ")})
    known_labels = {item["label"] for item in items}
    known_keys = {"사업명": "project.name", "사업기간": "project.period", "총사업비": "budget.total"}
    for match in re.finditer(r"(?m)^\s*(?:[-*+]\s*)?(?:\*\*)?([^\n|:#]{2,40}?)(?:\*\*)?\s*[:：]\s*([^\n|]{1,300})\s*$", text):
        label = re.sub(r"\s+", " ", match.group(1)).strip()
        value = match.group(2).strip().strip("* ")
        if label in known_labels or not value or value in {"확인 필요", "없음"}:
            continue
        key = known_keys.get(label) or "meta." + hashlib.sha256(label.encode("utf-8")).hexdigest()[:16]
        items.append({"key": key, "label": label, "value": value})
        known_labels.add(label)
    for line in text.splitlines():
        if not (line.strip().startswith("|") and line.strip().endswith("|")):
            continue
        cells = [cell.strip().strip("* ") for cell in line.strip().strip("|").split("|")]
        if len(cells) != 2 or not cells[0] or not cells[1] or cells[0] in known_labels or re.fullmatch(r":?-{3,}:?", cells[0]):
            continue
        label, value = cells
        if value not in {"값", "내용", "확인 필요", "없음"} and len(label) <= 40 and len(value) <= 300:
            items.append({"key": known_keys.get(label) or "meta." + hashlib.sha256(label.encode("utf-8")).hexdigest()[:16], "label": label, "value": value})
            known_labels.add(label)
    return items[:100]


def _save_markdown_fact_candidates(db: sqlite3.Connection, project_id: str, document_id: str, version_id: str, markdown: str, actor: str) -> None:
    now = utc_now()
    for item in _markdown_fact_candidates(markdown):
        row = db.execute("SELECT * FROM project_facts WHERE project_id=? AND fact_key=?", (project_id, item["key"])).fetchone()
        fact_id = row["id"] if row else "fact_" + uuid.uuid4().hex
        if not row:
            db.execute(
                "INSERT INTO project_facts(id,project_id,fact_key,label,value_type,unit,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (fact_id, project_id, item["key"], item["label"], "string", None, "candidate", now, now),
            )
        value_json = _json(item["value"])
        if row and row["status"] == "confirmed" and db.execute("SELECT 1 FROM project_fact_values WHERE fact_id=? AND status='confirmed' AND value_json=?", (fact_id, value_json)).fetchone():
            continue
        duplicate = db.execute(
            "SELECT 1 FROM project_fact_values WHERE fact_id=? AND value_json=? AND source_document_id=? AND source_locator=?",
            (fact_id, value_json, document_id, version_id),
        ).fetchone()
        if duplicate:
            continue
        db.execute(
            "INSERT INTO project_fact_values(id,fact_id,value_json,effective_date,status,source_document_id,source_locator,source_excerpt,confidence,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            ("factvalue_" + uuid.uuid4().hex, fact_id, value_json, None, "candidate", document_id, version_id, item["label"] + ": " + item["value"], 0.85, actor, now),
        )


def _save_project_markdown_version(
    db: sqlite3.Connection,
    project_id: str,
    markdown: str,
    *,
    title: str = "",
    document_id: str = "",
    expected_revision: int | None = None,
    source_format: str = "markdown",
    source_filename: str = "",
    source_artifact_sha256: str = "",
    source_session_id: str = "",
    actor: str = "workspace-user",
) -> dict:
    project_id = _safe_project_id(project_id)
    content = str(markdown or "").replace("\r\n", "\n").strip()
    if not content:
        raise ApiError("프로젝트 Markdown 내용이 비어 있습니다.")
    if len(content.encode("utf-8")) > 5_000_000:
        raise ApiError("프로젝트 Markdown은 5MB를 넘을 수 없습니다.", 413)
    _ensure_project(db, project_id, actor)
    row = db.execute("SELECT * FROM project_markdown_documents WHERE id=?", (document_id,)).fetchone() if document_id else None
    if row and row["project_id"] != project_id:
        raise ApiError("다른 프로젝트의 Markdown 문서를 갱신할 수 없습니다.", 403)
    if document_id and not row:
        raise ApiError("프로젝트 Markdown 문서를 찾을 수 없습니다.", 404)
    if row and expected_revision is not None and int(expected_revision) != int(row["current_revision"]):
        raise ApiError("Markdown 문서 revision이 변경되었습니다. 다시 불러와 주세요.", 409)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if row:
        current = db.execute("SELECT * FROM project_markdown_versions WHERE document_id=? AND revision=?", (row["id"], row["current_revision"])).fetchone()
        if current and current["markdown_sha256"] == digest:
            return _project_markdown_result(db, row["id"])
        revision = int(row["current_revision"]) + 1
        document_id = row["id"]
    else:
        document_id = "mdoc_" + uuid.uuid4().hex
        revision = 1
    version_id = "mdver_" + uuid.uuid4().hex
    now = utc_now()
    resolved_title = _markdown_title(content, title or (row["title"] if row else "AIWorks 프로젝트 문서"))
    snapshot = _project_fact_snapshot(db, project_id)
    if not row:
        db.execute(
            "INSERT INTO project_markdown_documents(id,project_id,title,current_revision,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (document_id, project_id, resolved_title, revision, "active", now, now),
        )
    else:
        db.execute("UPDATE project_markdown_documents SET title=?,current_revision=?,updated_at=? WHERE id=?", (resolved_title, revision, now, document_id))
    db.execute(
        "INSERT INTO project_markdown_versions(id,document_id,revision,markdown,markdown_sha256,source_format,source_filename,source_artifact_sha256,source_session_id,fact_snapshot_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (version_id, document_id, revision, content, digest, source_format, source_filename or None, source_artifact_sha256 or None, source_session_id or None, _json(snapshot), actor, now),
    )
    previous_generic = db.execute(
        "SELECT current_version_id FROM artifacts WHERE project_id=? AND source_type='markdown-document' AND source_id=?",
        (project_id, document_id),
    ).fetchone()
    generic_artifact, generic_version = _sync_generic_artifact_version(
        db,
        project_id,
        artifact_type="document.markdown",
        title=resolved_title,
        source_type="markdown-document",
        source_id=document_id,
        media_type="text/markdown",
        filename=(source_filename or resolved_title + ".md"),
        content_json={"markdown": content},
        metadata={
            "legacyDocumentId": document_id,
            "legacyVersionId": version_id,
            "revision": revision,
            "sourceFormat": source_format,
            "factValueIds": snapshot.get("valueIds") or [],
        },
        actor=actor,
    )
    if previous_generic and previous_generic["current_version_id"] and previous_generic["current_version_id"] != generic_version["id"]:
        _create_artifact_relation(
            db, project_id, generic_version["id"], previous_generic["current_version_id"],
            "supersedes", actor=actor, metadata={"legacyDocumentId": document_id},
        )

    _mark_project_artifacts_stale(db, project_id, document_id, version_id, revision)
    _save_markdown_fact_candidates(db, project_id, document_id, version_id, content, actor)
    _record_document_sync_event(
        db, project_id, document_id, "markdown.saved", origin=source_format, status="saved",
        source_version_id=version_id, detail={"revision": revision, "markdownSha256": digest, "actor": actor},
    )
    _audit(db, actor, "project.markdown_saved", {"project_id": project_id, "document_id": document_id, "version_id": version_id, "revision": revision, "source_format": source_format, "markdown_sha256": digest})
    return _project_markdown_result(db, document_id)


def _project_markdown_result(db: sqlite3.Connection, document_id: str, include_versions: bool = True) -> dict:
    document = db.execute("SELECT * FROM project_markdown_documents WHERE id=?", (document_id,)).fetchone()
    if not document:
        raise ApiError("프로젝트 Markdown 문서를 찾을 수 없습니다.", 404)
    current = db.execute("SELECT * FROM project_markdown_versions WHERE document_id=? AND revision=?", (document_id, document["current_revision"])).fetchone()
    result = {
        "id": document["id"], "projectId": document["project_id"], "title": document["title"], "status": document["status"],
        "revision": document["current_revision"], "markdown": current["markdown"], "markdownSha256": current["markdown_sha256"],
        "versionId": current["id"], "source": {"format": current["source_format"], "filename": current["source_filename"], "artifactSha256": current["source_artifact_sha256"], "sessionId": current["source_session_id"]},
        "factSnapshot": _load_json(current["fact_snapshot_json"], {}), "createdAt": document["created_at"], "updatedAt": document["updated_at"],
    }
    if include_versions:
        result["versions"] = [
            {"id": item["id"], "revision": item["revision"], "markdownSha256": item["markdown_sha256"], "sourceFormat": item["source_format"], "sourceFilename": item["source_filename"], "createdBy": item["created_by"], "createdAt": item["created_at"]}
            for item in db.execute("SELECT * FROM project_markdown_versions WHERE document_id=? ORDER BY revision DESC", (document_id,)).fetchall()
        ]
    return result


def list_project_markdown_documents(project_id: str) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    with _connect() as db:
        if not db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
            raise ApiError("프로젝트를 찾을 수 없습니다.", 404)
        items = []
        for row in db.execute("SELECT id FROM project_markdown_documents WHERE project_id=? AND status='active' ORDER BY updated_at DESC", (project_id,)).fetchall():
            item = _project_markdown_result(db, row["id"], include_versions=False)
            item["excerpt"] = re.sub(r"\s+", " ", item.pop("markdown"))[:300]
            items.append(item)
    by_digest = {}
    for item in reversed(items):
        by_digest.setdefault(item["markdownSha256"], []).append(item)
    duplicate_count = 0
    for group in by_digest.values():
        if len(group) < 2:
            continue
        canonical = group[0]["id"]
        for item in group[1:]:
            item["duplicateOf"] = canonical
            duplicate_count += 1
    return {"projectId": project_id, "items": items, "duplicateCount": duplicate_count}


def set_project_markdown_documents_status(project_id: str, payload: dict) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    action = str(payload.get("action") or "archive")
    if action not in {"archive", "restore"}:
        raise ApiError("문서 상태 작업은 archive 또는 restore여야 합니다.")
    document_ids = list(dict.fromkeys(str(item) for item in payload.get("document_ids") or [] if str(item)))
    if not document_ids or len(document_ids) > 100:
        raise ApiError("상태를 변경할 Markdown 문서를 1~100개 선택해 주세요.")
    placeholders = ",".join("?" for _ in document_ids)
    target_status = "archived" if action == "archive" else "active"
    expected_status = "active" if action == "archive" else "archived"
    actor, now = _actor(payload), utc_now()
    with _connect() as db:
        rows = db.execute(
            f"SELECT id,status FROM project_markdown_documents WHERE project_id=? AND id IN ({placeholders})",
            (project_id, *document_ids),
        ).fetchall()
        if len(rows) != len(document_ids):
            raise ApiError("선택한 Markdown 문서 중 현재 프로젝트에 없는 항목이 있습니다.", 404)
        if any(row["status"] != expected_status for row in rows):
            raise ApiError("선택한 Markdown 문서의 현재 상태가 작업과 맞지 않습니다.", 409)
        if action == "archive":
            active_count = int(db.execute("SELECT COUNT(*) FROM project_markdown_documents WHERE project_id=? AND status='active'", (project_id,)).fetchone()[0])
            if active_count <= len(document_ids):
                raise ApiError("프로젝트에는 활성 Markdown 문서를 하나 이상 남겨야 합니다.", 409)
        db.executemany(
            "UPDATE project_markdown_documents SET status=?,updated_at=? WHERE id=?",
            [(target_status, now, document_id) for document_id in document_ids],
        )
        workspace = db.execute("SELECT * FROM project_workspace_states WHERE project_id=?", (project_id,)).fetchone()
        if workspace and workspace["active_document_id"] in document_ids:
            replacement = str(payload.get("canonical_document_id") or "")
            if not replacement or not db.execute("SELECT 1 FROM project_markdown_documents WHERE id=? AND project_id=? AND status='active'", (replacement, project_id)).fetchone():
                candidate = db.execute("SELECT id FROM project_markdown_documents WHERE project_id=? AND status='active' ORDER BY updated_at DESC LIMIT 1", (project_id,)).fetchone()
                replacement = candidate["id"] if candidate else None
            db.execute("UPDATE project_workspace_states SET active_document_id=?,updated_by=?,updated_at=? WHERE project_id=?", (replacement, actor, now, project_id))
        _audit(db, actor, "project.markdown_documents_status_changed", {
            "project_id": project_id, "document_ids": document_ids, "action": action,
            "canonical_document_id": str(payload.get("canonical_document_id") or ""),
        })
    result = list_project_markdown_documents(project_id)
    result["changed"] = document_ids
    result["action"] = action
    return result


def get_project_markdown_document(project_id: str, document_id: str) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    with _connect() as db:
        result = _project_markdown_result(db, document_id)
    if result["projectId"] != project_id:
        raise ApiError("프로젝트 Markdown 문서를 찾을 수 없습니다.", 404)
    return result


def save_project_markdown_document(project_id: str, payload: dict) -> dict:
    ensure_schema()
    with _connect() as db:
        record = _save_project_markdown_version(
            db, project_id, str(payload.get("markdown") or ""), title=str(payload.get("title") or ""),
            document_id=str(payload.get("document_id") or ""), expected_revision=payload.get("base_revision"),
            source_format=str(payload.get("source_format") or "markdown"), source_filename=str(payload.get("source_filename") or ""), actor=_actor(payload),
        )
    if payload.get("auto_render") is True:
        try:
            rendered = render_project_markdown_document(project_id, record["id"], {"format": "hwpx", "instruction": str(payload.get("instruction") or "행안부 보고서 양식으로 바꿔줘"), "actor": _actor(payload)})
            record["sync"] = {"status": "synced", "artifact": rendered.get("projectArtifact") or (rendered.get("artifact") or {}).get("projectArtifact")}
        except ApiError as error:
            record["sync"] = {"status": "failed", "error": str(error)}
    return record



def _project_artifact_relation_graph(db: sqlite3.Connection, project_id: str, document_id: str) -> dict:
    nodes, edges = [], []
    versions = db.execute(
        "SELECT v.*,d.title FROM project_markdown_versions v JOIN project_markdown_documents d ON d.id=v.document_id WHERE d.project_id=? AND d.id=? ORDER BY v.revision",
        (project_id, document_id),
    ).fetchall()
    for item in versions:
        nodes.append({"id": item["id"], "type": "markdown-version", "label": f"{item['title']} · MD r{item['revision']}", "sha256": item["markdown_sha256"], "createdAt": item["created_at"]})
    for previous, current in zip(versions, versions[1:]):
        edges.append({"source": current["id"], "target": previous["id"], "relation": "supersedes", "evidence": "revision"})
    artifacts = db.execute("SELECT * FROM project_document_artifacts WHERE document_id=? ORDER BY created_at", (document_id,)).fetchall()
    for item in artifacts:
        nodes.append({"id": item["id"], "type": "artifact", "label": str(item["filename"] or item["format"]).strip(), "format": item["format"], "status": item["status"], "sha256": item["artifact_sha256"], "createdAt": item["created_at"]})
        if item["source_version_id"]:
            edges.append({"source": item["id"], "target": item["source_version_id"], "relation": "derived_from", "evidence": str(item["renderer"] or "")})
        if item["template_id"]:
            template_node_id = "template:" + str(item["template_id"])
            if not any(node["id"] == template_node_id for node in nodes):
                nodes.append({"id": template_node_id, "type": "template", "label": str(item["template_id"])})
            edges.append({"source": item["id"], "target": template_node_id, "relation": "formatted_by", "evidence": str(item["instruction"] or "")})
    conflicts = db.execute("SELECT * FROM project_document_conflicts WHERE document_id=? ORDER BY created_at", (document_id,)).fetchall()
    for item in conflicts:
        nodes.append({"id": item["id"], "type": "conflict", "label": item["conflict_type"], "status": item["status"], "createdAt": item["created_at"]})
        if item["artifact_id"]:
            edges.append({"source": item["id"], "target": item["artifact_id"], "relation": "compares", "evidence": "HWPX"})
        if item["current_version_id"]:
            edges.append({"source": item["id"], "target": item["current_version_id"], "relation": "compares", "evidence": "Markdown"})
    events = db.execute("SELECT * FROM project_document_sync_events WHERE document_id=? ORDER BY created_at", (document_id,)).fetchall()
    known = {node["id"] for node in nodes}
    for item in events:
        if item["source_version_id"] in known and item["target_version_id"] in known and item["source_version_id"] != item["target_version_id"]:
            edges.append({"source": item["target_version_id"], "target": item["source_version_id"], "relation": "transforms", "evidence": item["event_type"]})
    unique_edges = []
    seen = set()
    for edge in edges:
        key = (edge["source"], edge["target"], edge["relation"])
        if key not in seen:
            unique_edges.append(edge)
            seen.add(key)
    return {"contractVersion": "1.0", "nodes": nodes, "edges": unique_edges}


def get_project_document_workbench(project_id: str, document_id: str) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    with _connect() as db:
        document = _project_markdown_result(db, document_id)
        if document["projectId"] != project_id:
            raise ApiError("프로젝트 Markdown 문서를 찾을 수 없습니다.", 404)
        project = db.execute("SELECT id,name,classification,status FROM projects WHERE id=?", (project_id,)).fetchone()
        artifacts = [_project_artifact_result(row) for row in db.execute("SELECT * FROM project_document_artifacts WHERE document_id=? ORDER BY format,variant_key", (document_id,)).fetchall()]
        events = [
            {"id": row["id"], "artifactId": row["artifact_id"], "eventType": row["event_type"], "origin": row["origin"], "status": row["status"], "sourceVersionId": row["source_version_id"], "targetVersionId": row["target_version_id"], "detail": _load_json(row["detail_json"], {}), "createdAt": row["created_at"]}
            for row in db.execute("SELECT * FROM project_document_sync_events WHERE document_id=? ORDER BY created_at DESC LIMIT 50", (document_id,)).fetchall()
        ]
        conflicts = [
            _document_conflict_result(row)
            for row in db.execute("SELECT * FROM project_document_conflicts WHERE document_id=? ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, created_at DESC LIMIT 50", (document_id,)).fetchall()
        ]
        relation_graph = _project_artifact_relation_graph(db, project_id, document_id)
        evidence = [
            _artifact_evidence_result(row)
            for row in db.execute(
                "SELECT e.* FROM artifact_evidence e JOIN artifacts a ON a.id=e.artifact_id WHERE e.project_id=? AND ((a.source_type='markdown-document' AND a.source_id=?) OR (a.source_type='project-document-artifact' AND a.source_id IN (SELECT id FROM project_document_artifacts WHERE document_id=?))) ORDER BY e.created_at DESC",
                (project_id, document_id, document_id),
            ).fetchall()
        ]
        fact_counts = db.execute("SELECT status,COUNT(*) AS count FROM project_facts WHERE project_id=? GROUP BY status", (project_id,)).fetchall()
    if not any(item["format"] == "hwpx" for item in artifacts):
        artifacts.append({"id": None, "documentId": document_id, "format": "hwpx", "variantKey": "default", "sourceVersionId": None, "sourceRevision": None, "sourceMarkdownSha256": None, "status": "missing", "filename": None, "mediaType": "application/hwp+zip", "artifactSha256": None, "templateId": None, "renderer": None, "instruction": "행안부 보고서 양식으로 바꿔줘", "renderMap": {}, "error": None, "createdAt": None, "updatedAt": None})
    return {
        "project": dict(project) if project else {"id": project_id, "name": project_id, "classification": "internal", "status": "active"},
        "document": document,
        "evidence": evidence,
        "tabs": ["markdown", *[item["format"] for item in artifacts], "metadata", "history"],
        "artifacts": artifacts,
        "factCounts": {row["status"]: row["count"] for row in fact_counts},
        "conflicts": conflicts,
        "relationGraph": relation_graph,
        "events": events,
    }


def get_project_document_artifact(project_id: str, document_id: str, artifact_id: str) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    with _connect() as db:
        row = db.execute("SELECT a.*,d.project_id FROM project_document_artifacts a JOIN project_markdown_documents d ON d.id=a.document_id WHERE a.id=? AND a.document_id=?", (artifact_id, document_id)).fetchone()
    if not row or row["project_id"] != project_id:
        raise ApiError("프로젝트 파생 문서를 찾을 수 없습니다.", 404)
    return _project_artifact_result(row, include_content=True)



def _document_conflict_result(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "projectId": row["project_id"], "documentId": row["document_id"],
        "artifactId": row["artifact_id"], "conflictType": row["conflict_type"], "status": row["status"],
        "baseVersionId": row["base_version_id"], "currentVersionId": row["current_version_id"],
        "source": _load_json(row["source_json"], {}), "target": _load_json(row["target_json"], {}),
        "renderMap": _load_json(row["render_map_json"], {}), "detail": _load_json(row["detail_json"], {}),
        "resolution": _load_json(row["resolution_json"], {}), "createdAt": row["created_at"], "resolvedAt": row["resolved_at"],
    }


def _record_project_document_conflict(
    db: sqlite3.Connection,
    project_id: str,
    document_id: str,
    artifact_id: str,
    conflict_type: str,
    *,
    base_version_id: str,
    current_version_id: str,
    source: dict,
    target: dict,
    render_map: dict,
    detail: dict,
) -> dict:
    now = utc_now()
    existing = db.execute(
        "SELECT * FROM project_document_conflicts WHERE document_id=? AND artifact_id=? AND conflict_type=? AND status='open' ORDER BY created_at DESC LIMIT 1",
        (document_id, artifact_id, conflict_type),
    ).fetchone()
    if existing:
        db.execute(
            "UPDATE project_document_conflicts SET current_version_id=?,source_json=?,target_json=?,render_map_json=?,detail_json=? WHERE id=?",
            (current_version_id, _json(source), _json(target), _json(render_map), _json(detail), existing["id"]),
        )
        row = db.execute("SELECT * FROM project_document_conflicts WHERE id=?", (existing["id"],)).fetchone()
    else:
        conflict_id = "conflict_" + uuid.uuid4().hex
        db.execute(
            "INSERT INTO project_document_conflicts(id,project_id,document_id,artifact_id,conflict_type,status,base_version_id,current_version_id,source_json,target_json,render_map_json,detail_json,resolution_json,created_at) VALUES(?,?,?,?,?,'open',?,?,?,?,?,?,?,?)",
            (conflict_id, project_id, document_id, artifact_id, conflict_type, base_version_id, current_version_id, _json(source), _json(target), _json(render_map), _json(detail), "{}", now),
        )
        row = db.execute("SELECT * FROM project_document_conflicts WHERE id=?", (conflict_id,)).fetchone()
    return _document_conflict_result(row)


def promote_project_artifact_to_markdown(project_id: str, document_id: str, artifact_id: str, payload: dict) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    with _connect() as db:
        row = db.execute(
            "SELECT a.*,d.project_id FROM project_document_artifacts a JOIN project_markdown_documents d ON d.id=a.document_id WHERE a.id=? AND a.document_id=?",
            (artifact_id, document_id),
        ).fetchone()
        if not row or row["project_id"] != project_id:
            raise ApiError("프로젝트 파생 문서를 찾을 수 없습니다.", 404)
        if row["format"] != "hwpx" or row["content_blob"] is None:
            raise ApiError("HWPX 파생 문서만 MD로 반영할 수 있습니다.", 415)
        render_map = _load_json(row["render_map_json"], {})
        pending = render_map.get("pendingPromotion")
        if not isinstance(pending, dict) or not str(pending.get("markdown") or "").strip():
            raise ApiError("MD로 반영할 HWPX 변경이 없습니다.", 409)
        current = _project_markdown_result(db, document_id)
        if pending.get("baseVersionId") != current["versionId"] or int(pending.get("baseRevision") or 0) != int(current["revision"]):
            conflict = _record_project_document_conflict(
                db,
                project_id,
                document_id,
                artifact_id,
                "concurrent-md-hwpx-edit",
                base_version_id=str(pending.get("baseVersionId") or ""),
                current_version_id=current["versionId"],
                source={
                    "kind": "hwpx-pending-markdown",
                    "markdownSha256": hashlib.sha256(str(pending.get("markdown") or "").encode("utf-8")).hexdigest(),
                    "excerpt": str(pending.get("markdown") or "")[:1_200],
                    "changes": list(pending.get("changes") or [])[:50],
                },
                target={
                    "kind": "current-markdown",
                    "revision": current["revision"],
                    "markdownSha256": current["markdownSha256"],
                    "excerpt": current["markdown"][:1_200],
                },
                render_map=render_map,
                detail={"message": "HWPX 편집 이후 MD 원본도 변경되었습니다.", "availableResolutions": ["keep-markdown", "use-hwpx"]},
            )
            _record_document_sync_event(
                db, project_id, document_id, "sync.conflict-detected", origin="sync-engine", status="conflict",
                artifact_id=artifact_id, source_version_id=str(pending.get("baseVersionId") or ""), target_version_id=current["versionId"],
                detail={"conflictId": conflict["id"], "conflictType": conflict["conflictType"]},
            )
            _audit(db, _actor(payload), "project.document_conflict_detected", {"conflict_id": conflict["id"], "project_id": project_id, "document_id": document_id, "artifact_id": artifact_id})
            db.commit()
            raise ApiError("MD와 HWPX가 각각 변경되어 자동 반영을 중단했습니다. 변경 이력에서 충돌을 해결해 주세요. [" + conflict["id"] + "]", 409)

        markdown_record = _save_project_markdown_version(
            db,
            project_id,
            str(pending["markdown"]),
            title=str(pending.get("title") or current["title"]),
            document_id=document_id,
            expected_revision=current["revision"],
            source_format=str(pending.get("sourceFormat") or "hwpx-semantic-edit"),
            source_filename=str(row["filename"] or "document.hwpx"),
            source_artifact_sha256=str(row["artifact_sha256"] or ""),
            source_session_id=str(pending.get("sessionId") or ""),
            actor=_actor(payload),
        )
        changes = list(pending.get("changes") or [])
        conversion = pending.get("conversion") or {}
        render_map.pop("pendingPromotion", None)
        if conversion.get("fullDocumentReimport"):
            reverse_document = REPORT_DOCUMENT_MCP.parse(markdown_record["markdown"], title=markdown_record["title"], style_profile="standard")
            render_map = _build_hwpx_render_map(reverse_document, parse_hwpx(bytes(row["content_blob"]), str(row["filename"] or "document.hwpx")))
            render_map["renderMode"] = "hwpx-full-document-reimport"
        else:
            changed_by_paragraph = {item["paragraphId"]: item["after"] for item in changes if item.get("paragraphId")}
            for entry in render_map.get("entries") or []:
                if entry.get("paragraphId") in changed_by_paragraph:
                    entry["sourceText"] = _semantic_text(changed_by_paragraph[entry["paragraphId"]])
                    entry["canonicalText"] = _semantic_text(changed_by_paragraph[entry["paragraphId"]])
        synced = _upsert_project_artifact(
            db, markdown_record, target_format="hwpx", status="synced", data=bytes(row["content_blob"]),
            filename=str(row["filename"] or ""), media_type=str(row["media_type"] or "application/hwp+zip"),
            template_id=str(row["template_id"] or ""), renderer=str(row["renderer"] or "document.rhwp@1.0.0"),
            instruction=str(row["instruction"] or ""), render_map=render_map, origin="hwpx-explicit-promotion",
        )
        db.execute(
            "UPDATE native_document_sessions SET markdown_base_revision=?,updated_at=? WHERE project_artifact_id=? AND markdown_document_id=?",
            (markdown_record["revision"], utc_now(), artifact_id, document_id),
        )
        _record_document_sync_event(
            db, project_id, document_id, "hwpx.promoted-to-markdown", origin="user-explicit", status="synced",
            artifact_id=artifact_id, source_version_id=str(row["source_version_id"] or ""), target_version_id=markdown_record["versionId"],
            detail={"changes": changes, "conversion": conversion, "explicit": True},
        )
        _audit(db, _actor(payload), "project.hwpx_promoted_to_markdown", {"project_id": project_id, "document_id": document_id, "artifact_id": artifact_id, "version_id": markdown_record["versionId"], "revision": markdown_record["revision"]})
    return {"document": markdown_record, "artifact": synced, "changes": changes, "conversion": conversion}



def resolve_project_document_conflict(project_id: str, document_id: str, conflict_id: str, payload: dict) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    resolution = str(payload.get("resolution") or "").strip()
    if resolution not in {"keep-markdown", "use-hwpx"}:
        raise ApiError("충돌 해결 방식은 keep-markdown 또는 use-hwpx여야 합니다.")
    with _connect() as db:
        conflict_row = db.execute(
            "SELECT * FROM project_document_conflicts WHERE id=? AND project_id=? AND document_id=?",
            (conflict_id, project_id, document_id),
        ).fetchone()
        if not conflict_row:
            raise ApiError("문서 충돌을 찾을 수 없습니다.", 404)
        if conflict_row["status"] != "open":
            raise ApiError("이미 해결된 문서 충돌입니다.", 409)
        artifact_row = db.execute(
            "SELECT * FROM project_document_artifacts WHERE id=? AND document_id=?",
            (conflict_row["artifact_id"], document_id),
        ).fetchone()
        if not artifact_row or artifact_row["content_blob"] is None:
            raise ApiError("충돌한 HWPX 파생 문서를 찾을 수 없습니다.", 404)
        current = _project_markdown_result(db, document_id)
        render_map = _load_json(artifact_row["render_map_json"], {})
        pending = render_map.get("pendingPromotion")
        if not isinstance(pending, dict) or not str(pending.get("markdown") or "").strip():
            raise ApiError("충돌 해결에 사용할 HWPX 변경 초안이 없습니다.", 409)
        now = utc_now()
        if resolution == "use-hwpx":
            markdown_record = _save_project_markdown_version(
                db, project_id, str(pending["markdown"]),
                title=str(pending.get("title") or current["title"]), document_id=document_id,
                expected_revision=current["revision"], source_format="hwpx-conflict-resolution",
                source_filename=str(artifact_row["filename"] or "document.hwpx"),
                source_artifact_sha256=str(artifact_row["artifact_sha256"] or ""),
                source_session_id=str(pending.get("sessionId") or ""), actor=_actor(payload),
            )
            reverse_document = REPORT_DOCUMENT_MCP.parse(markdown_record["markdown"], title=markdown_record["title"], style_profile="standard")
            render_map = _build_hwpx_render_map(
                reverse_document,
                parse_hwpx(bytes(artifact_row["content_blob"]), str(artifact_row["filename"] or "document.hwpx")),
            )
            render_map["renderMode"] = "conflict-resolution-use-hwpx"
            artifact = _upsert_project_artifact(
                db, markdown_record, target_format="hwpx", status="synced", data=bytes(artifact_row["content_blob"]),
                filename=str(artifact_row["filename"] or ""), media_type=str(artifact_row["media_type"] or "application/hwp+zip"),
                template_id=str(artifact_row["template_id"] or ""), renderer=str(artifact_row["renderer"] or "document.rhwp@1.0.0"),
                instruction=str(artifact_row["instruction"] or ""), render_map=render_map, origin="conflict-resolution",
            )
            document = markdown_record
        else:
            render_map.pop("pendingPromotion", None)
            artifact = _upsert_project_artifact(
                db, current, target_format="hwpx", status="stale", data=bytes(artifact_row["content_blob"]),
                filename=str(artifact_row["filename"] or ""), media_type=str(artifact_row["media_type"] or "application/hwp+zip"),
                template_id=str(artifact_row["template_id"] or ""), renderer=str(artifact_row["renderer"] or "document.rhwp@1.0.0"),
                instruction=str(artifact_row["instruction"] or ""), render_map=render_map, origin="conflict-resolution",
            )
            document = current
        resolution_record = {"choice": resolution, "actor": _actor(payload), "resolvedAt": now, "resultRevision": document["revision"]}
        db.execute(
            "UPDATE project_document_conflicts SET status='resolved',resolution_json=?,resolved_at=? WHERE id=?",
            (_json(resolution_record), now, conflict_id),
        )
        _record_document_sync_event(
            db, project_id, document_id, "sync.conflict-resolved", origin="user-explicit", status="resolved",
            artifact_id=artifact["id"], source_version_id=conflict_row["base_version_id"], target_version_id=document["versionId"],
            detail={"conflictId": conflict_id, "resolution": resolution},
        )
        _audit(db, _actor(payload), "project.document_conflict_resolved", {"conflict_id": conflict_id, "resolution": resolution, "project_id": project_id, "document_id": document_id})
        resolved = db.execute("SELECT * FROM project_document_conflicts WHERE id=?", (conflict_id,)).fetchone()
    return {"conflict": _document_conflict_result(resolved), "document": document, "artifact": artifact}


def _project_markdown_context(db: sqlite3.Connection, project_id: str, limit: int = 6) -> list[dict]:
    items = []
    for row in db.execute("SELECT id,title,current_revision FROM project_markdown_documents WHERE project_id=? AND status='active' ORDER BY updated_at DESC LIMIT ?", (project_id, max(1, min(20, int(limit))))).fetchall():
        version = db.execute("SELECT id,markdown,markdown_sha256 FROM project_markdown_versions WHERE document_id=? AND revision=?", (row["id"], row["current_revision"])).fetchone()
        items.append({"documentId": row["id"], "versionId": version["id"], "revision": row["current_revision"], "title": row["title"], "markdownSha256": version["markdown_sha256"], "markdown": version["markdown"][:12_000]})
    return items


def project_document_format_adapters() -> dict:
    ensure_schema()
    adapters = [
        {"format": "md", "capability": "document.markdown.export", "mcp": "document.markdown@1.0.0", "status": "ready", "sourceOfTruth": True},
        {"format": "hwpx", "capability": "document.hwpx.render", "mcp": "template.report-style@0.1.0 + integration.kordoc@1.0.0", "status": "ready", "sourceOfTruth": False},
        {"format": "docx", "capability": "document.docx.extract", "mcp": "document.docx@0.1.0", "status": "ready", "sourceOfTruth": False, "direction": "input"},
        {"format": "xlsx", "capability": "document.xlsx.extract", "mcp": "document.xlsx@0.1.0", "status": "ready", "sourceOfTruth": False, "direction": "input"},
    ]
    with _connect() as db:
        rows = db.execute(
            "SELECT c.capability_id,c.package_id,c.version FROM mcp_capabilities c JOIN mcp_installations i ON i.package_id=c.package_id AND i.pinned_version=c.version WHERE i.status='active' AND c.capability_id LIKE 'document.format.convert.%' ORDER BY c.capability_id"
        ).fetchall()
    adapters.extend({"format": row["capability_id"].rsplit(".", 1)[-1], "capability": row["capability_id"], "mcp": row["package_id"] + "@" + row["version"], "status": "installed", "sourceOfTruth": False} for row in rows)
    return {"sourceFormat": "md", "adapters": adapters}


def render_project_markdown_document(project_id: str, document_id: str, payload: dict) -> dict:
    ensure_schema()
    project_id = _safe_project_id(project_id)
    target_format = str(payload.get("format") or "hwpx").lower().lstrip(".")
    with _connect() as db:
        document = _project_markdown_result(db, document_id)
        if document["projectId"] != project_id:
            raise ApiError("프로젝트 Markdown 문서를 찾을 수 없습니다.", 404)
        fact_snapshot = _project_fact_snapshot(db, project_id, str(payload.get("as_of") or ""))
        existing_artifact = db.execute(
            "SELECT * FROM project_document_artifacts WHERE document_id=? AND format='hwpx' AND variant_key='default'",
            (document_id,),
        ).fetchone()
    if existing_artifact and existing_artifact["status"] == "diverged" and payload.get("force") is not True:
        raise ApiError("HWPX에 아직 MD로 반영하지 않은 변경이 있습니다. 먼저 HWPX → MD 반영을 실행하거나 명시적으로 덮어쓰기를 확인해 주세요.", 409)
    if target_format in {"md", "markdown"}:
        data = document["markdown"].encode("utf-8")
        return {
            "sourceDocument": {"id": document["id"], "versionId": document["versionId"], "revision": document["revision"], "markdownSha256": document["markdownSha256"]},
            "artifact": {"title": document["title"], "filename": re.sub(r'[\\/:*?"<>|]+', "_", document["title"])[:80] + ".md", "format": "md", "mediaType": "text/markdown", "content": document["markdown"], "contentBase64": base64.b64encode(data).decode("ascii"), "derived": False},
        }
    if target_format != "hwpx":
        adapters = project_document_format_adapters()
        installed = next((item for item in adapters["adapters"] if item["format"] == target_format and item["status"] == "installed"), None)
        if installed:
            raise ApiError(installed["mcp"] + " 형식 어댑터의 실행 계약 연결이 필요합니다.", 501)
        raise ApiError("'" + target_format + "' 출력 형식 MCP가 없습니다. document.format.convert." + target_format + " Capability를 제공하는 MCP를 설치해 주세요.", 409)
    instruction = str(payload.get("instruction") or (existing_artifact["instruction"] if existing_artifact else "") or "표준 보고서 양식으로 변환")
    preserve_layout = payload.get("preserve_layout") is not False and existing_artifact is not None and existing_artifact["content_blob"] is not None
    with _connect() as db:
        _upsert_project_artifact(db, document, target_format="hwpx", status="rendering", instruction=instruction, origin="markdown")
    try:
        artifact = _build_structured_report_artifact(
            document["title"], document["markdown"], instruction, fact_snapshot=fact_snapshot,
            generated_by=["document.markdown@1.0.0"],
        )
        formatter = None
        layout_preserved = False
        if preserve_layout and payload.get("structural_render") is True:
            try:
                renderer_ref = str(existing_artifact["renderer"] or "")
                renderer_match = re.fullmatch(
                    r"([A-Za-z0-9][A-Za-z0-9._-]{2,99})@([0-9]+\.[0-9]+\.[0-9]+)",
                    renderer_ref,
                )
                if not renderer_match:
                    raise ApiError("기존 HWPX에 다시 적용할 양식 MCP 버전 정보가 없습니다.", 409)
                artifact, package_ref = _apply_template_binding_to_artifact(
                    {"packageId": renderer_match.group(1), "version": renderer_match.group(2)},
                    artifact,
                )
                preserved_bytes = base64.b64decode(str(artifact["contentBase64"]), validate=True)
                preserved_parsed = parse_hwpx(preserved_bytes, str(artifact["filename"]))
                preserved_map = _build_hwpx_render_map(artifact.get("reportDocument") or {}, preserved_parsed)
                preserved_map["renderMode"] = "structural-template-rebuild-v2"
                artifact["template"] = {**(artifact.get("template") or {}), "id": package_ref}
                artifact["layoutPreserved"] = True
                artifact["layoutRefreshMode"] = "structural-template-rebuild"
                layout_preserved = True
            except (ApiError, ValueError, TypeError):
                preserved_map = None
        if preserve_layout and not layout_preserved:
            try:
                preserved_bytes, preserved_map = _refresh_hwpx_layout_in_place(
                    bytes(existing_artifact["content_blob"]),
                    _load_json(existing_artifact["render_map_json"], {}),
                    artifact.get("reportDocument") or {},
                )
                artifact["contentBase64"] = base64.b64encode(preserved_bytes).decode("ascii")
                artifact["filename"] = str(existing_artifact["filename"] or artifact["filename"])
                artifact["template"] = {**(artifact.get("template") or {}), "id": str(existing_artifact["template_id"] or (artifact.get("template") or {}).get("id") or "")}
                artifact["layoutPreserved"] = True
                artifact["layoutRefreshMode"] = "mapped-text-refresh"
                layout_preserved = True
            except ApiError as mapped_error:
                try:
                    structured_bytes = base64.b64decode(str(artifact["contentBase64"]), validate=True)
                    preserved_bytes, refill_metadata = _apply_builder_hwpx_template(
                        bytes(existing_artifact["content_blob"]),
                        structured_bytes,
                        str(existing_artifact["filename"] or artifact["filename"]),
                        {"templateName": str(existing_artifact["template_id"] or "기존 HWPX 양식"), "version": "project-layout-refill-v1"},
                        artifact.get("reportDocument") or {},
                    )
                    preserved_parsed = parse_hwpx(preserved_bytes, str(existing_artifact["filename"] or artifact["filename"]))
                    new_semantics = {
                        _semantic_text(block.get("text") or "")
                        for block in artifact.get("reportDocument", {}).get("blocks") or []
                        if block.get("type") != "table"
                    }
                    for block in artifact.get("reportDocument", {}).get("blocks") or []:
                        if block.get("type") == "table":
                            new_semantics.update(_semantic_text(cell) for row in block.get("rows") or [] for cell in row)
                    refilled_semantics = {_semantic_text(item.get("text") or "") for item in preserved_parsed.get("paragraphs") or []}
                    stale_values = {
                        _semantic_text(item.get("canonicalText") or item.get("sourceText") or "")
                        for item in _load_json(existing_artifact["render_map_json"], {}).get("entries") or []
                    } - new_semantics
                    if any(value and value in refilled_semantics for value in stale_values):
                        raise ApiError("기존 HWPX 재충전 결과에 이전 MD 문구가 남아 있어 전체 렌더링으로 전환합니다.", 409)
                    preserved_map = _build_hwpx_render_map(artifact.get("reportDocument") or {}, preserved_parsed)
                    preserved_map["renderMode"] = "layout-preserving-template-refill"
                    preserved_map["fallbackReason"] = str(mapped_error)
                    artifact["contentBase64"] = base64.b64encode(preserved_bytes).decode("ascii")
                    artifact["filename"] = str(existing_artifact["filename"] or artifact["filename"])
                    artifact["template"] = {
                        **(artifact.get("template") or {}),
                        "id": str(existing_artifact["template_id"] or (artifact.get("template") or {}).get("id") or ""),
                        "refill": refill_metadata,
                    }
                    artifact["layoutPreserved"] = True
                    artifact["layoutRefreshMode"] = "template-refill"
                    layout_preserved = True
                except ApiError:
                    preserved_map = None
        if not layout_preserved:
            artifact, formatter = _finalize_report_with_loopback_mcp(artifact, instruction)
    except ApiError as error:
        with _connect() as db:
            _upsert_project_artifact(db, document, target_format="hwpx", status="failed", instruction=instruction, error=str(error), origin="renderer")
        raise
    artifact["markdownDocument"] = {"id": document["id"], "versionId": document["versionId"], "revision": document["revision"], "markdownSha256": document["markdownSha256"], "projectId": project_id, "sourceOfTruth": True}
    artifact["sourceOfTruth"] = {"format": "markdown", "persistence": "project-version", "status": "persisted", "documentId": document["id"], "versionId": document["versionId"]}
    renderer = str(existing_artifact["renderer"] or "") if layout_preserved else (formatter["packageRef"] if formatter else "document.report-hwpx@0.1.0")
    artifact["derivedOutput"] = {"format": "hwpx", "renderer": renderer, "derivedFromMarkdownVersion": document["versionId"], "layoutPreserved": layout_preserved}
    artifact_bytes = base64.b64decode(str(artifact["contentBase64"]), validate=True)
    parsed = parse_hwpx(artifact_bytes, str(artifact["filename"]))
    render_map = preserved_map if layout_preserved else _build_hwpx_render_map(artifact.get("reportDocument") or {}, parsed)
    with _connect() as db:
        project_artifact = _upsert_project_artifact(
            db, document, target_format="hwpx", status="synced", data=artifact_bytes,
            filename=str(artifact.get("filename") or ""), media_type=str(artifact.get("mediaType") or "application/hwp+zip"),
            template_id=str((artifact.get("template") or {}).get("id") or ""), renderer=artifact["derivedOutput"]["renderer"],
            instruction=instruction, render_map=render_map, origin="renderer",
        )
        _audit(db, _actor(payload), "project.markdown_rendered", {"project_id": project_id, "document_id": document_id, "version_id": document["versionId"], "format": "hwpx", "template": artifact["template"]["id"], "renderer": artifact["derivedOutput"]["renderer"], "layout_preserved": layout_preserved})
    artifact["projectArtifact"] = project_artifact
    return {"sourceDocument": artifact["markdownDocument"], "artifact": artifact, "adapter": artifact["derivedOutput"], "projectArtifact": project_artifact}


def _knowledge_node(db: sqlite3.Connection, row: sqlite3.Row) -> dict:
    sources = [
        {
            "id": source["id"],
            "documentId": source["document_id"],
            "locator": source["locator"],
            "excerpt": source["excerpt"],
            "effectiveDate": source["effective_date"],
            "confidence": source["confidence"],
        }
        for source in db.execute(
            "SELECT * FROM knowledge_sources WHERE node_id=? ORDER BY effective_date DESC, id", (row["id"],)
        ).fetchall()
    ]
    return {
        "id": row["id"],
        "nodeType": row["node_type"],
        "title": row["title"],
        "content": row["content"],
        "classification": row["classification"],
        "metadata": _load_json(row["metadata_json"], {}),
        "sources": sources,
    }


def knowledge_graph() -> dict:
    ensure_schema()
    with _connect() as db:
        nodes = [_knowledge_node(db, row) for row in db.execute("SELECT * FROM knowledge_nodes ORDER BY node_type,title").fetchall()]
        edges = [
            {
                "id": row["id"],
                "source": row["source_node_id"],
                "target": row["target_node_id"],
                "relation": row["relation"],
                "weight": row["weight"],
                "evidenceSourceId": row["evidence_source_id"],
            }
            for row in db.execute("SELECT * FROM knowledge_edges ORDER BY id").fetchall()
        ]
    return {"nodes": nodes, "edges": edges, "counts": {"nodes": len(nodes), "edges": len(edges), "sources": sum(len(node["sources"]) for node in nodes)}}


def _query_terms(question: str) -> list[str]:
    stop = {"알려줘", "무엇인가", "무엇", "현재", "대한", "관련", "기준", "값은", "어떻게"}
    return [term.lower() for term in re.findall(r"[가-힣A-Za-z0-9][가-힣A-Za-z0-9._-]+", question) if term.lower() not in stop]


def query_knowledge(payload: dict) -> dict:
    ensure_schema()
    question = str(payload.get("question") or "").strip()
    if not question:
        raise ApiError("지식 질문이 필요합니다.")
    if len(question) > 1_000:
        raise ApiError("지식 질문은 1,000자를 넘을 수 없습니다.")
    clearance = str(payload.get("clearance") or "internal")
    if clearance not in KNOWLEDGE_CLASSIFICATION_RANK:
        raise ApiError("지원하지 않는 지식 접근 등급입니다.")
    as_of = str(payload.get("as_of") or "").strip() or None
    if as_of and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
        raise ApiError("as_of는 YYYY-MM-DD 형식이어야 합니다.")
    terms = _query_terms(question)
    with _connect() as db:
        candidates = []
        for row in db.execute("SELECT * FROM knowledge_nodes").fetchall():
            if KNOWLEDGE_CLASSIFICATION_RANK[row["classification"]] > KNOWLEDGE_CLASSIFICATION_RANK[clearance]:
                continue
            node = _knowledge_node(db, row)
            if not node["sources"]:
                continue
            if as_of:
                node["sources"] = [
                    source
                    for source in node["sources"]
                    if not source["effectiveDate"] or source["effectiveDate"] <= as_of
                ]
                if not node["sources"]:
                    continue
            if as_of and node["nodeType"] == "common-data":
                versions = [version for version in node["metadata"].get("versions", []) if version["effectiveDate"] <= as_of]
                if not versions:
                    continue
                selected = sorted(versions, key=lambda item: item["effectiveDate"])[-1]
                node["content"] = f'{node["title"]}: {selected["value"]}' + (f' {node["metadata"].get("unit")}' if node["metadata"].get("unit") else "")
                node["sources"] = [source for source in node["sources"] if source["effectiveDate"] == selected["effectiveDate"]]
            searchable = " ".join([node["title"], node["content"]] + [source["excerpt"] for source in node["sources"]]).lower()
            score = sum(3 if term in node["title"].lower() else 1 for term in terms if term in searchable)
            if not score:
                continue
            candidates.append((score, node))
    candidates.sort(key=lambda item: (-item[0], -max(source["confidence"] for source in item[1]["sources"]), item[1]["title"]))
    results = [node for _, node in candidates[:5]]
    if not results:
        return {"answerable": False, "grounded": True, "answer": "연결된 출처에서 답변 근거를 찾지 못했습니다.", "results": [], "citations": [], "asOf": as_of}
    citations = []
    for node in results:
        for source in node["sources"][:2]:
            citations.append({"nodeId": node["id"], "title": node["title"], **source})
    answer = " / ".join(node["content"] for node in results[:3])
    return {"answerable": True, "grounded": True, "answer": answer, "results": results, "citations": citations, "asOf": as_of}


def compare_knowledge_versions(payload: dict) -> dict:
    ensure_schema()
    record_id = str(payload.get("record_id") or "").strip()
    from_date = str(payload.get("from_date") or "").strip()
    to_date = str(payload.get("to_date") or "").strip()
    with _connect() as db:
        row = db.execute("SELECT * FROM knowledge_nodes WHERE id=?", ("data:" + record_id,)).fetchone()
        if not row:
            raise ApiError("비교할 공통데이터를 찾을 수 없습니다.", 404)
        node = _knowledge_node(db, row)
    versions = sorted(node["metadata"].get("versions", []), key=lambda item: item["effectiveDate"])
    before_candidates = [item for item in versions if not from_date or item["effectiveDate"] <= from_date]
    after_candidates = [item for item in versions if not to_date or item["effectiveDate"] <= to_date]
    if not before_candidates or not after_candidates:
        raise ApiError("요청한 시점의 값을 찾을 수 없습니다.", 404)
    before, after = before_candidates[-1], after_candidates[-1]
    delta = after["value"] - before["value"] if isinstance(before["value"], (int, float)) and isinstance(after["value"], (int, float)) else None
    percent = round(delta / before["value"] * 100, 2) if delta is not None and before["value"] else None
    return {"recordId": record_id, "label": node["title"], "unit": node["metadata"].get("unit"), "from": before, "to": after, "delta": delta, "percentChange": percent, "improved": delta > 0 if delta is not None else None}


def create_knowledge_note(payload: dict) -> dict:
    ensure_schema()
    title = str(payload.get("title") or "").strip()
    content = str(payload.get("content") or "").strip()
    sources = payload.get("sources")
    if not title or not content:
        raise ApiError("노트 제목과 내용이 필요합니다.")
    if not isinstance(sources, list) or not sources:
        raise ApiError("근거 출처가 없는 지식 노트는 저장할 수 없습니다.")
    classification = str(payload.get("classification") or "internal")
    if classification not in KNOWLEDGE_CLASSIFICATION_RANK:
        raise ApiError("지원하지 않는 지식 접근 등급입니다.")
    node_id = "note:" + uuid.uuid4().hex
    now = utc_now()
    with _connect() as db:
        db.execute(
            "INSERT INTO knowledge_nodes(id,node_type,title,content,classification,metadata_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (node_id, "note", title[:200], content[:10_000], classification, _json({"tags": payload.get("tags") or []}), now, now),
        )
        for index, source in enumerate(sources, 1):
            if not isinstance(source, dict) or not source.get("documentId") or not source.get("locator"):
                raise ApiError("노트 출처에는 documentId와 locator가 필요합니다.")
            try:
                confidence = float(source.get("confidence", 1.0))
            except (TypeError, ValueError) as error:
                raise ApiError("노트 출처 신뢰도는 숫자여야 합니다.") from error
            if not 0 <= confidence <= 1:
                raise ApiError("노트 출처 신뢰도는 0과 1 사이여야 합니다.")
            effective_date = source.get("effectiveDate")
            if effective_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(effective_date)):
                raise ApiError("노트 출처 기준일은 YYYY-MM-DD 형식이어야 합니다.")
            db.execute(
                "INSERT INTO knowledge_sources(id,node_id,document_id,locator,excerpt,effective_date,confidence) VALUES(?,?,?,?,?,?,?)",
                (f"source:{node_id}:{index}", node_id, str(source["documentId"])[:200], str(source["locator"])[:500], str(source.get("excerpt") or "")[:2_000], effective_date, confidence),
            )
        for index, target in enumerate(payload.get("relates_to") or [], 1):
            if not db.execute("SELECT 1 FROM knowledge_nodes WHERE id=?", (target,)).fetchone():
                raise ApiError("연결할 지식 노드를 찾을 수 없습니다.", 404)
            db.execute(
                "INSERT INTO knowledge_edges(id,source_node_id,target_node_id,relation,weight,evidence_source_id,created_at) VALUES(?,?,?,?,?,?,?)",
                (f"edge:{node_id}:{index}", node_id, target, "relates_to", 1.0, f"source:{node_id}:1", now),
            )
        _audit(db, _actor(payload), "knowledge.note_created", {"node_id": node_id, "sources": len(sources), "relations": len(payload.get("relates_to") or [])})
        row = db.execute("SELECT * FROM knowledge_nodes WHERE id=?", (node_id,)).fetchone()
        result = _knowledge_node(db, row)
    return result
    {"id": "document.docx", "version": "0.1.0", "modality": "document", "runtime": "local-ooxml", "operations": ["inspect", "extractText", "ragIndex"], "permissions": ["asset.read"], "status": "implemented", "limits": {"maxBytes": MAX_ASSET_BYTES, "formats": [".docx"]}},
    {"id": "document.xlsx", "version": "0.1.0", "modality": "document", "runtime": "local-ooxml", "operations": ["inspect", "extractCells", "ragIndex"], "permissions": ["asset.read"], "status": "implemented", "limits": {"maxBytes": MAX_ASSET_BYTES, "formats": [".xlsx"]}},


CAPABILITY_ADAPTERS = [
    {"id": "document.hwpx", "version": "1.2.0", "modality": "document", "runtime": "local", "operations": ["inspect", "applyPatch"], "permissions": ["asset.read", "asset.write"], "status": "implemented", "limits": {"maxBytes": MAX_HWPX_BYTES, "formats": [".hwpx"]}},
    {"id": "document.rhwp", "version": "1.0.0", "modality": "document", "runtime": "windows-native-bridge", "operations": sorted(RHWP_AUTOMATION_MCP.TOOLS), "permissions": ["document.read", "document.write"], "status": "implemented", "limits": {"transport": "authenticated-stdio", "formats": [".hwp", ".hwpx", ".hwt", ".hml", ".pdf"]}},
    {"id": "code.source", "version": "0.1.0", "modality": "code", "runtime": "local", "operations": ["inspect", "extractSymbols"], "permissions": ["asset.read"], "status": "implemented", "limits": {"maxBytes": MAX_ASSET_BYTES, "formats": [".py", ".js", ".ts", ".json", ".md"]}},
    {"id": "image.metadata", "version": "0.1.0", "modality": "image", "runtime": "local", "operations": ["inspect"], "permissions": ["asset.read"], "status": "implemented", "limits": {"maxBytes": MAX_ASSET_BYTES, "formats": [".png", ".jpg", ".jpeg"]}},
    {"id": "image.compose", "version": "0.1.0", "modality": "image", "runtime": "external", "operations": ["generate", "edit"], "permissions": ["asset.read", "asset.write", "network.send"], "status": "contract-only", "limits": {"maxBytes": MAX_ASSET_BYTES}},
    {"id": "audio.wav", "version": "0.1.0", "modality": "audio", "runtime": "local", "operations": ["inspect"], "permissions": ["asset.read"], "status": "implemented", "limits": {"maxBytes": MAX_ASSET_BYTES, "formats": [".wav"]}},
    {"id": "audio.transcribe", "version": "0.1.0", "modality": "audio", "runtime": "external", "operations": ["transcribe"], "permissions": ["asset.read", "network.send"], "status": "contract-only", "limits": {"maxBytes": MAX_ASSET_BYTES}},
    {"id": "video.mp4", "version": "0.1.0", "modality": "video", "runtime": "local", "operations": ["inspect"], "permissions": ["asset.read"], "status": "implemented", "limits": {"maxBytes": MAX_ASSET_BYTES, "formats": [".mp4"]}},
    {"id": "video.summarize", "version": "0.1.0", "modality": "video", "runtime": "external", "operations": ["extractFrames", "transcribe", "summarize"], "permissions": ["asset.read", "network.send"], "status": "contract-only", "limits": {"maxBytes": MAX_ASSET_BYTES}},
]


WORKFLOW_PRESETS = [
    {"id": "document.budget-request", "name": "예산요청서 생성", "description": "HWPX와 공통데이터로 예산요청서 변경안을 생성합니다.", "modality": "document", "acceptedFormats": [".hwpx"], "maxBytes": MAX_HWPX_BYTES, "steps": [{"id": "inspect", "adapter": "document.hwpx@1.2.0", "operation": "inspect", "runtime": "local", "status": "implemented", "permissions": ["asset.read"]}, {"id": "patch", "adapter": "document.hwpx@1.2.0", "operation": "applyPatch", "runtime": "local", "status": "implemented", "permissions": ["asset.write"]}], "status": "ready", "modelPersonality": "document-specialist"},
    {"id": "code.review", "name": "소스코드 검토", "description": "코드 구조를 로컬에서 추출한 뒤 복합 추론 모델로 검토 계획을 만듭니다.", "modality": "code", "acceptedFormats": [".py", ".js", ".ts", ".json", ".md"], "maxBytes": MAX_ASSET_BYTES, "steps": [{"id": "inspect", "adapter": "code.source@0.1.0", "operation": "extractSymbols", "runtime": "local", "status": "implemented", "permissions": ["asset.read"]}, {"id": "review", "adapter": "core.model-management@0.1.0", "operation": "review", "runtime": "external", "status": "implemented", "permissions": ["model.invoke", "network.send"]}], "status": "ready", "modelPersonality": "reasoning-agent"},
    {"id": "image.brief", "name": "이미지 제작 브리프", "description": "이미지 메타데이터를 검사하고 생성·편집 브리프를 구성합니다.", "modality": "image", "acceptedFormats": [".png", ".jpg", ".jpeg"], "maxBytes": MAX_ASSET_BYTES, "steps": [{"id": "inspect", "adapter": "image.metadata@0.1.0", "operation": "inspect", "runtime": "local", "status": "implemented", "permissions": ["asset.read"]}, {"id": "compose", "adapter": "image.compose@0.1.0", "operation": "edit", "runtime": "external", "status": "contract-only", "permissions": ["asset.write", "network.send"]}], "status": "preview", "modelPersonality": None},
    {"id": "audio.meeting", "name": "회의 음성 정리", "description": "WAV를 검사한 뒤 전사와 회의 결과 정리를 수행합니다.", "modality": "audio", "acceptedFormats": [".wav"], "maxBytes": MAX_ASSET_BYTES, "steps": [{"id": "inspect", "adapter": "audio.wav@0.1.0", "operation": "inspect", "runtime": "local", "status": "implemented", "permissions": ["asset.read"]}, {"id": "transcribe", "adapter": "audio.transcribe@0.1.0", "operation": "transcribe", "runtime": "external", "status": "contract-only", "permissions": ["network.send"]}], "status": "preview", "modelPersonality": None},
    {"id": "video.summary", "name": "영상 요약", "description": "MP4 컨테이너를 검사하고 프레임·음성 기반 요약 계획을 구성합니다.", "modality": "video", "acceptedFormats": [".mp4"], "maxBytes": MAX_ASSET_BYTES, "steps": [{"id": "inspect", "adapter": "video.mp4@0.1.0", "operation": "inspect", "runtime": "local", "status": "implemented", "permissions": ["asset.read"]}, {"id": "summarize", "adapter": "video.summarize@0.1.0", "operation": "summarize", "runtime": "external", "status": "contract-only", "permissions": ["network.send"]}], "status": "preview", "modelPersonality": None},
]


def list_workflow_presets() -> dict:
    return {"items": WORKFLOW_PRESETS, "adapters": CAPABILITY_ADAPTERS, "counts": {"ready": sum(item["status"] == "ready" for item in WORKFLOW_PRESETS), "preview": sum(item["status"] == "preview" for item in WORKFLOW_PRESETS)}}


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\xff\xd8"):
        return None
    offset = 2
    while offset + 9 < len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            return struct.unpack(">HH", data[offset + 5 : offset + 9])[::-1]
        if offset + 4 > len(data):
            break
        length = struct.unpack(">H", data[offset + 2 : offset + 4])[0]
        if length < 2:
            break
        offset += 2 + length
    return None


def inspect_asset(payload: dict) -> dict:
    filename = str(payload.get("filename") or "").strip()
    if not filename or Path(filename).name != filename or filename in {".", ".."}:
        raise ApiError("안전한 파일 이름이 필요합니다.")
    encoded = str(payload.get("content_base64") or "")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as error:
        raise ApiError("content_base64가 올바르지 않습니다.") from error
    if not data:
        raise ApiError("검사할 파일 내용이 비어 있습니다.")
    if len(data) > MAX_ASSET_BYTES:
        raise ApiError(f"파일은 {MAX_ASSET_BYTES:,}바이트를 넘을 수 없습니다.", 413)
    extension = Path(filename).suffix.lower()
    result = {"filename": filename, "extension": extension, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "externalTransfer": False}
    if extension in {".py", ".js", ".ts", ".json", ".md"}:
        if b"\x00" in data:
            raise ApiError("코드 파일에 바이너리 데이터가 포함되어 있습니다.")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ApiError("코드 파일은 UTF-8이어야 합니다.") from error
        language = {".py": "python", ".js": "javascript", ".ts": "typescript", ".json": "json", ".md": "markdown"}[extension]
        if extension == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError as error:
                raise ApiError("JSON 문법이 올바르지 않습니다.") from error
        result.update({"modality": "code", "adapter": "code.source@0.1.0", "language": language, "lines": len(text.splitlines()), "functions": len(re.findall(r"(?m)^\s*(?:def|async\s+def|function)\s+[A-Za-z_$][\w$]*", text)), "classes": len(re.findall(r"(?m)^\s*class\s+[A-Za-z_$][\w$]*", text)), "todos": len(re.findall(r"(?i)\b(?:TODO|FIXME)\b", text))})
    elif extension in {".docx", ".xlsx"}:
        parts = _extract_docx_parts(data) if extension == ".docx" else _extract_xlsx_parts(data)
        text_content = "\n\n".join(text for _index, text in parts)
        result.update({
            "modality": "document",
            "adapter": "document." + extension[1:] + "@0.1.0",
            "format": extension[1:],
            "sections": len(parts),
            "characters": len(text_content),
            "textExcerpt": text_content[:2_000],
            "ragReady": bool(text_content.strip()),
        })

    elif extension == ".png":
        if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n") or data[12:16] != b"IHDR":
            raise ApiError("확장자와 PNG 파일 내용이 일치하지 않습니다.")
        width, height = struct.unpack(">II", data[16:24])
        result.update({"modality": "image", "adapter": "image.metadata@0.1.0", "format": "png", "width": width, "height": height})
    elif extension in {".jpg", ".jpeg"}:
        dimensions = _jpeg_dimensions(data)
        if not dimensions:
            raise ApiError("확장자와 JPEG 파일 내용이 일치하지 않습니다.")
        result.update({"modality": "image", "adapter": "image.metadata@0.1.0", "format": "jpeg", "width": dimensions[0], "height": dimensions[1]})
    elif extension == ".wav":
        try:
            with wave.open(io.BytesIO(data), "rb") as audio:
                frames, rate = audio.getnframes(), audio.getframerate()
                result.update({"modality": "audio", "adapter": "audio.wav@0.1.0", "channels": audio.getnchannels(), "sampleRate": rate, "sampleWidth": audio.getsampwidth(), "durationSeconds": round(frames / rate, 3) if rate else 0})
        except (wave.Error, EOFError) as error:
            raise ApiError("확장자와 WAV 파일 내용이 일치하지 않습니다.") from error
    elif extension == ".mp4":
        if len(data) < 12 or data[4:8] != b"ftyp":
            raise ApiError("확장자와 MP4 컨테이너가 일치하지 않습니다.")
        result.update({"modality": "video", "adapter": "video.mp4@0.1.0", "container": "mp4", "brand": data[8:12].decode("ascii", errors="replace")})
    else:
        raise ApiError("지원하지 않는 파일 형식입니다.", 415)
    ensure_schema()
    with _connect() as db:
        _audit(db, _actor(payload), "asset.inspected", {"filename": filename, "modality": result["modality"], "bytes": len(data), "sha256": result["sha256"], "external_transfer": False})
    return result


def create_workflow_plan(payload: dict) -> dict:
    preset_id = str(payload.get("preset_id") or "").strip()
    preset = next((item for item in WORKFLOW_PRESETS if item["id"] == preset_id), None)
    if not preset:
        raise ApiError("업무 프리셋을 찾을 수 없습니다.", 404)
    assets = payload.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ApiError("프리셋에 사용할 파일이 필요합니다.")
    classification = str(payload.get("classification") or "internal")
    if classification not in KNOWLEDGE_CLASSIFICATION_RANK:
        raise ApiError("지원하지 않는 데이터 등급입니다.")
    for asset in assets:
        if not isinstance(asset, dict):
            raise ApiError("파일 메타데이터는 객체여야 합니다.")
        filename = str(asset.get("filename") or "")
        try:
            size = int(asset.get("bytes") or 0)
        except (TypeError, ValueError) as error:
            raise ApiError("파일 크기는 정수여야 합니다.") from error
        if Path(filename).suffix.lower() not in preset["acceptedFormats"]:
            raise ApiError("프리셋이 지원하지 않는 파일 형식입니다.", 415)
        if size < 1 or size > preset["maxBytes"]:
            raise ApiError("파일 크기가 프리셋 제한을 벗어났습니다.", 413)
    contract_only = [step["id"] for step in preset["steps"] if step["status"] != "implemented"]
    external = any(step["runtime"] == "external" for step in preset["steps"])
    classification_allowed = classification in {"public", "internal"} or not external
    personality = preset.get("modelPersonality")
    model = next((item for item in MODEL_MANAGEMENT_MCP.list_models() if item["personality"] == personality), None)
    executable = not contract_only and classification_allowed and (not personality or model is not None)
    required_permissions = sorted({permission for step in preset["steps"] for permission in step["permissions"]})
    return {"id": "workflow_" + uuid.uuid4().hex, "preset": preset, "assets": assets, "classification": classification, "steps": preset["steps"], "requiredPermissions": required_permissions, "externalTransfer": external, "model": model, "executable": executable, "blockedBy": contract_only + ([] if classification_allowed else ["classification.external-transfer-blocked"]), "approvalRequired": bool(required_permissions)}


def _plan_steps(intent: str, route: dict, document_context: dict) -> tuple[list[dict], dict]:
    workflow = WORKSPACE_ORCHESTRATION_MCP.build_workflow(intent, document_context, route)
    return workflow["steps"], workflow


def _bind_dynamic_capability(intent: str, steps: list[dict], workflow: dict) -> tuple[list[dict], dict]:
    if workflow.get("responseType") in {"selection-edit", "document-transform"}:
        return steps, workflow
    if workflow.get("responseType") == "report-artifact" and workflow.get("contextPriority") == "previous-answer":
        return steps, workflow
    resolved = resolve_capabilities({"intent": intent, "limit": 5})
    explicit_formatter = any(term in intent.lower() for term in ("kodak", "kordoc", "코닥", "hwpx 변환", "한글 문서로", "서식이 적용"))
    candidates = [
        item for item in resolved["items"]
        if explicit_formatter or not (item.get("mcpType") == "external" and item.get("capabilityId") == "document.hwpx.finalize")
    ]
    if not candidates:
        return steps, workflow
    report_intent = any(term in intent for term in ("보고서", "문서", "초안", "작성"))
    data_binding = next((item for item in candidates if item.get("mcpType") == "data"), None)
    template_requested = any(term in intent for term in ("양식", "서식", "형식", "포맷"))
    template_binding = next(
        (item for item in candidates if item.get("mcpType") == "template"),
        None,
    ) if template_requested else None
    binding = data_binding if data_binding and report_intent else candidates[0]
    post_bindings = [template_binding] if template_binding and template_binding["packageRef"] != binding["packageRef"] else []
    make_data_report = binding.get("mcpType") == "data" and report_intent
    make_report = report_intent and (
        binding.get("mcpType") == "data" or "artifact.process" in (binding.get("capabilities") or [])
    )
    template_transform = binding.get("mcpType") == "template" and workflow.get("responseType") == "template-transform"
    formatter = _installed_loopback_formatter() if make_report and not post_bindings else None
    permissions = sorted(
        set(binding["permissions"])
        | {permission for item in post_bindings for permission in item.get("permissions") or []}
        | ({"document.write"} if make_report else set())
        | (set(formatter["permissions"]) if formatter else set())
    )
    loaded_mcps = [binding["packageRef"]]
    if template_transform:
        loaded_mcps.append("document.rhwp@1.0.0")
    if make_report:
        loaded_mcps.extend([
            "document.markdown@1.0.0",
            "document.report-structure@0.1.0",
            "document.quality-harness@0.1.0",
            "template.report-style@0.1.0",
            "document.report-hwpx@0.1.0",
            "document.rhwp@1.0.0",
        ])
        if formatter:
            loaded_mcps.insert(-1, formatter["packageRef"])
        elif post_bindings:
            loaded_mcps.insert(-1, post_bindings[0]["packageRef"])
    dynamic_step = {
        "id": "dynamic-capability",
        "mcp": binding["packageRef"],
        "action": "data.report" if make_data_report else binding["capabilityId"],
        "model": None,
        "runtime": binding["executionAdapter"],
        "permissions": permissions,
        "status": "resolved",
    }
    dynamic_workflow = {
        **workflow,
        "id": "dynamic." + binding["packageId"],
        "responseType": "template-transform" if template_transform else ("report-artifact" if make_report else "context-answer"),
        "steps": [dynamic_step] + ([{
            "id": "apply-user-template",
            "mcp": post_bindings[0]["packageRef"],
            "action": "document.template.apply",
            "model": None,
            "runtime": post_bindings[0]["executionAdapter"],
            "permissions": post_bindings[0]["permissions"],
            "status": "resolved",
        }] if post_bindings else []) + ([{
            "id": "local-hwpx-finalizer",
            "mcp": formatter["packageRef"],
            "action": formatter["capabilityId"],
            "model": None,
            "runtime": "external-mcp-localhost",
            "permissions": formatter["permissions"],
            "status": "resolved",
        }] if formatter else []),
        "loadedMcps": loaded_mcps,
        "capabilityBindings": [binding] + post_bindings + ([formatter] if formatter else []),
        "dynamic": True,
        "pipeline": (["현재 프로젝트 Markdown 읽기", "사용자 등록 HWPX 양식 적용", "RHWP revision 저장"] if template_transform else (
            ["데이터 MCP 검색", "Solar LLM Markdown 초안 생성", "질문·근거·초안 품질 하네스", "Markdown revision 저장·Fact 후보 추출"] + (["사용자 등록 HWPX 양식 적용"] if post_bindings else ["양식 MCP v2 적용"]) + (["KODAK HWPX 렌더링"] if formatter else ([] if post_bindings else ["HWPX 형식 어댑터 렌더링"])) + ["RHWP 파생 산출물 편집"]
            if make_report else ["데이터 MCP 검색", "근거·연도 검증", "출처 포함 응답"]
        )),
    }
    return [dynamic_step], dynamic_workflow


def _installed_mcp_ref(package_id: str, fallback_version: str) -> str:
    with _connect() as db:
        row = db.execute(
            "SELECT pinned_version FROM mcp_installations WHERE package_id=? AND status='active'",
            (package_id,),
        ).fetchone()
    return package_id + "@" + (row["pinned_version"] if row else fallback_version)


def _filter_fact_snapshot_for_text(snapshot: dict, *values: str) -> dict:
    source = snapshot if isinstance(snapshot, dict) else {}
    haystack = _semantic_text(" ".join(str(value or "") for value in values)).lower()
    facts = {}
    for key, item in (source.get("facts") or {}).items():
        label = _semantic_text(item.get("label") or "").lower()
        value = _semantic_text(item.get("value") or "").lower()
        if (label and label in haystack) or (value and len(value) >= 3 and value in haystack):
            facts[key] = item
    return {
        **source,
        "facts": facts,
        "valueIds": [item.get("valueId") for item in facts.values() if item.get("valueId")],
        "contextFilter": "previous-answer-relevance",
    }


def create_plan(payload: dict) -> dict:
    ensure_schema()
    intent = str(payload.get("intent") or "").strip()
    if not intent:
        raise ApiError("실행할 업무 요청이 필요합니다.")
    if len(intent) > 2_000:
        raise ApiError("업무 요청은 2,000자를 넘을 수 없습니다.")
    document_context = payload.get("document_context") or {}
    if not isinstance(document_context, dict):
        raise ApiError("document_context는 객체여야 합니다.")
    classification = str(document_context.get("classification") or "internal")
    if classification not in {"public", "internal", "confidential", "personal"}:
        raise ApiError("지원하지 않는 데이터 등급입니다.")
    project_id = _safe_project_id(document_context.get("project_id"))
    document_context = {**document_context, "project_id": project_id}
    with _connect() as db:
        _ensure_project(db, project_id, _actor(payload))
        fact_snapshot = _project_fact_snapshot(db, project_id, str(document_context.get("as_of") or ""))
        markdown_context = _project_markdown_context(db, project_id)
    intent_configuration = _runtime_mcp_configuration("core.intent-analysis", INTENT_ANALYSIS_MCP.MANIFEST)
    intent_analysis = INTENT_ANALYSIS_MCP.analyze(intent, document_context, intent_configuration)
    route = MODEL_MANAGEMENT_MCP.select_model(intent_analysis, classification)
    steps, workflow = _plan_steps(intent, route, document_context)
    steps, workflow = _bind_dynamic_capability(intent, steps, workflow)
    if workflow.get("contextPriority") == "previous-answer":
        fact_snapshot = _filter_fact_snapshot_for_text(
            fact_snapshot,
            intent,
            str(document_context.get("previous_answer") or ""),
        )
        markdown_context = []
    elif workflow.get("contextPriority") == "data-source":
        # A fresh lookup must be grounded in the selected data MCP. Reusing an
        # open report here can silently replace the requested subject with the
        # previous document's subject.
        fact_snapshot = _filter_fact_snapshot_for_text(fact_snapshot, intent)
        markdown_context = []
    workflow["projectId"] = project_id
    workflow["factSnapshot"] = fact_snapshot
    workflow["markdownContext"] = markdown_context
    if workflow.get("responseType") in {"report-artifact", "document-transform"}:
        template = TEMPLATE_REPORT_STYLE_MCP.select(intent)
        workflow["styleProfile"] = template["styleProfile"]
        workflow["template"] = template
        workflow["documentPipeline"] = [
            "프로젝트 Markdown 원본·Fact 문맥 조립",
            "Solar LLM Markdown 초안 생성·갱신",
            "질문·검색 근거·초안 품질 하네스 및 1회 보완",
            "Markdown 불변 revision 저장·메타정보 후보 추출",
            "양식 MCP v2 구조·스타일 적용",
            "KODAK/형식 어댑터 파생 산출물 생성",
        ]
        loaded_mcps = list(workflow.get("loadedMcps") or [])
        for package_ref in ("document.report-structure@0.1.0", "template.report-style@0.1.0"):
            if package_ref not in loaded_mcps:
                loaded_mcps.append(package_ref)
        workflow["loadedMcps"] = loaded_mcps
    initial_live_model = (
        bool(intent_analysis.get("createsInitialDocument"))
        and _live_model_execution_enabled()
        and bool(_upstage_key() or _openrouter_key())
    )
    if initial_live_model:
        model_id = str((route.get("model") or {}).get("id") or "")
        if steps:
            steps[0]["permissions"] = sorted(set(steps[0].get("permissions") or []) | {"model.invoke", "network.send"})
            steps[0]["model"] = model_id
        workflow["liveModelRequired"] = True
        workflow["selectedModel"] = model_id
        loaded_mcps = list(workflow.get("loadedMcps") or [])
        if "core.model-management@0.1.0" not in loaded_mcps:
            loaded_mcps.insert(0, "core.model-management@0.1.0")
        workflow["loadedMcps"] = loaded_mcps
        pipeline = list(workflow.get("pipeline") or [])
        workflow["pipeline"] = ["Solar 최고 품질 모델로 최초 본문 생성"] + pipeline
    required = sorted({permission for step in steps for permission in step["permissions"]})
    external_transfer = "network.send" in required or "model.invoke" in required
    if external_transfer and not route["classificationAllowed"]:
        raise ApiError("이 데이터 등급은 선택된 외부 모델로 전송할 수 없습니다.", 403)
    plan_id = "plan_" + uuid.uuid4().hex
    now = utc_now()
    with _connect() as db:
        db.execute(
            """
            INSERT INTO plans(
                id, intent, actor, status, classification, external_transfer,
                masked_fields_json, required_permissions_json, steps_json,
                document_context_json, routing_json, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                plan_id,
                intent,
                _actor(payload),
                "awaiting-approval",
                classification,
                1 if external_transfer else 0,
                _json(document_context.get("masked_fields") or []),
                _json(required),
                _json(steps),
                _json(document_context),
                _json({"intentAnalysis": intent_analysis, "route": route, "workflow": workflow}),
                now,
                now,
            ),
        )
        _audit(
            db,
            "core-orchestrator",
            "plan.created",
            {
                "intent": intent,
                "permissions": required,
                "external_transfer": external_transfer,
                "selected_model": route["model"]["id"],
                "intent_type": intent_analysis["intentType"],
                "workflow": workflow["id"],
                "capability_bindings": workflow.get("capabilityBindings", []),
                "project_id": project_id,
                "fact_value_ids": fact_snapshot.get("valueIds") or [],
            },
            plan_id=plan_id,
        )
    return {
        "id": plan_id,
        "intent": intent,
        "status": "awaiting-approval",
        "dataPolicy": {
            "classification": classification,
            "externalTransfer": external_transfer,
            "maskedFields": document_context.get("masked_fields") or [],
        },
        "requiredPermissions": required,
        "steps": steps,
        "intentAnalysis": intent_analysis,
        "routing": route,
        "workflow": workflow,
        "project": {"id": project_id, "factCount": len(fact_snapshot.get("facts") or {}), "factValueIds": fact_snapshot.get("valueIds") or []},
        "markdownDocuments": [{"documentId": item["documentId"], "versionId": item["versionId"], "revision": item["revision"], "title": item["title"], "markdownSha256": item["markdownSha256"]} for item in markdown_context],
        "createdAt": now,
    }


def _plan_row(db: sqlite3.Connection, plan_id: str) -> sqlite3.Row:
    row = db.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    if row is None:
        raise ApiError("실행 계획을 찾을 수 없습니다.", 404)
    return row


def get_plan(plan_id: str) -> dict:
    ensure_schema()
    with _connect() as db:
        row = _plan_row(db, plan_id)
    return {
        "id": row["id"],
        "intent": row["intent"],
        "actor": row["actor"],
        "status": row["status"],
        "dataPolicy": {
            "classification": row["classification"],
            "externalTransfer": bool(row["external_transfer"]),
            "maskedFields": _load_json(row["masked_fields_json"], []),
        },
        "intentAnalysis": _load_json(row["routing_json"], {}).get("intentAnalysis", {}),
        "workflow": _load_json(row["routing_json"], {}).get("workflow", {}),
        "routing": _load_json(row["routing_json"], {}).get("route", {}),
        "requiredPermissions": _load_json(row["required_permissions_json"], []),
        "steps": _load_json(row["steps_json"], []),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def approve_plan(payload: dict) -> dict:
    ensure_schema()
    plan_id = str(payload.get("plan_id") or "").strip()
    approved = payload.get("permissions")
    if not plan_id:
        raise ApiError("plan_id가 필요합니다.")
    if not isinstance(approved, list):
        raise ApiError("승인 권한 목록이 필요합니다.")
    approved = sorted({str(item) for item in approved})
    now_epoch = int(time.time())
    expires_at = now_epoch + TOKEN_TTL_SECONDS
    nonce = secrets.token_urlsafe(18)
    actor = _actor(payload)
    with _connect() as db:
        row = _plan_row(db, plan_id)
        if row["status"] not in {"awaiting-approval", "approved"}:
            raise ApiError("현재 상태에서는 승인할 수 없습니다.", 409)
        required = set(_load_json(row["required_permissions_json"], []))
        missing = sorted(required - set(approved))
        if missing:
            raise ApiError("필수 권한이 승인되지 않았습니다: " + ", ".join(missing), 403)
        claims = {
            "aud": "aiworks-executor",
            "plan_id": plan_id,
            "actor": actor,
            "permissions": approved,
            "nonce": nonce,
            "iat": now_epoch,
            "exp": expires_at,
        }
        db.execute(
            "INSERT INTO approvals(nonce, plan_id, actor, permissions_json, expires_at, created_at) VALUES(?,?,?,?,?,?)",
            (nonce, plan_id, actor, _json(approved), expires_at, utc_now()),
        )
        db.execute("UPDATE plans SET status='approved', updated_at=? WHERE id=?", (utc_now(), plan_id))
        _audit(
            db,
            actor,
            "plan.approved",
            {"permissions": approved, "expires_at": expires_at},
            plan_id=plan_id,
        )
    return {
        "planId": plan_id,
        "approvalToken": _sign_claims(claims),
        "expiresAt": datetime.fromtimestamp(expires_at, timezone.utc).isoformat().replace("+00:00", "Z"),
        "permissions": approved,
    }


def _openrouter_key() -> str:
    return os.getenv("OPENROUTER_API_KEY", "").strip()


def _upstage_key() -> str:
    return (os.getenv("UPSTAGE_API_KEY") or os.getenv("UPSTAGE_SECRET_KEY") or "").strip()


def _live_model_execution_enabled() -> bool:
    flag = os.getenv("AIWORKS_SOLAR_LIVE")
    if flag is None:
        flag = os.getenv("AIWORKS_OPENROUTER_LIVE", "0")
    return str(flag).strip() == "1"


def _openrouter_chat(model_id: str, messages: list[dict], max_tokens: int = 500) -> dict:
    models = {model["id"]: model for model in MODEL_MANAGEMENT_MCP.list_models()}
    if model_id not in models:
        raise ApiError("등록되지 않은 모델 호출은 차단됩니다.", 403)
    model = models[model_id]
    provider = str(model.get("provider") or "")
    if provider == "upstage":
        key = _upstage_key()
        if not key:
            raise ApiError("UPSTAGE_API_KEY가 설정되지 않았습니다.", 503)
        base_url = os.getenv("UPSTAGE_BASE_URL", "https://api.upstage.ai/v1").rstrip("/")
        api_model = str(model.get("apiModel") or model_id.removeprefix("upstage:"))
        request_max_tokens = max(32, min(16_384, int(max_tokens)))
        reasoning_effort = model.get("reasoningEffort")
        if reasoning_effort:
            reasoning_minimum = max(1_024, min(16_384, int(os.getenv("UPSTAGE_REASONING_MIN_TOKENS", "4096"))))
            request_max_tokens = max(request_max_tokens, reasoning_minimum)
        headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
        provider_label = "Upstage Solar"
    elif provider == "openrouter":
        key = _openrouter_key()
        if not key:
            raise ApiError("OPENROUTER_API_KEY가 설정되지 않았습니다.", 503)
        base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
        api_model = model_id
        request_max_tokens = max(32, min(4_000, int(max_tokens)))
        reasoning_effort = None
        headers = {
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv("AIWORKS_HTTP_REFERER", "https://minslab.local/poc/aiworks"),
            "X-Title": "AIWorks PoC",
        }
        provider_label = "OpenRouter"
    else:
        raise ApiError("선택 모델의 승인된 외부 실행기를 찾을 수 없습니다.", 503)
    request_payload = {
        "model": api_model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": request_max_tokens,
    }
    if reasoning_effort:
        request_payload["reasoning_effort"] = reasoning_effort
    elif model_id == "openai/gpt-oss-20b:free":
        request_payload["reasoning"] = {"effort": "minimal", "exclude": True}
    body = _json(request_payload).encode("utf-8")
    request = url_request.Request(
        base_url + "/chat/completions",
        data=body,
        method="POST",
        headers=headers,
    )
    timeout = max(5, min(180, int(os.getenv("AIWORKS_SOLAR_TIMEOUT_SECONDS", os.getenv("AIWORKS_OPENROUTER_TIMEOUT_SECONDS", "120")))))
    try:
        with url_request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except url_error.HTTPError as error:
        detail = error.read(2_000).decode("utf-8", "replace")
        raise ApiError(f"{provider_label} 호출 실패 ({error.code}): {detail}", 502) from error
    except (url_error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(f"{provider_label} 호출 실패: {error}", 502) from error
    choices = data.get("choices") or []
    content = ((choices[0].get("message") or {}).get("content") if choices else None)
    if not isinstance(content, str) or not content.strip():
        raise ApiError(provider_label + " 응답 내용이 비어 있습니다.", 502)
    return {
        "content": content.strip(),
        "requestedModel": model_id,
        "resolvedModel": data.get("model") or model_id,
        "usage": data.get("usage") or {},
        "requestId": data.get("id"),
    }


def _is_transient_model_error(error: Exception) -> bool:
    if not isinstance(error, ApiError) or error.status != 502:
        return False
    detail = str(error).lower()
    return any(
        signal in detail
        for signal in (
            "timed out",
            "timeout",
            "read operation",
            "temporarily",
            "unavailable",
            "overloaded",
            "connection reset",
            "(429)",
            "(500)",
            "(502)",
            "(503)",
            "(504)",
        )
    )


def _chat_with_route_fallback(
    route: dict,
    messages: list[dict],
    *,
    max_tokens: int = 500,
    primary_model_id: str = "",
) -> dict:
    primary_id = primary_model_id or str((route.get("model") or {}).get("id") or "")
    try:
        return _openrouter_chat(primary_id, messages, max_tokens=max_tokens)
    except ApiError as primary_error:
        fallback_id = str(route.get("fallbackModelId") or "")
        if (
            not fallback_id
            or fallback_id == primary_id
            or not _is_transient_model_error(primary_error)
        ):
            raise
        try:
            result = _openrouter_chat(fallback_id, messages, max_tokens=max_tokens)
        except ApiError as fallback_error:
            raise ApiError(
                f"{primary_id} 호출 실패 후 {fallback_id} 자동 전환도 실패했습니다: {fallback_error}",
                fallback_error.status,
            ) from fallback_error
        return {
            **result,
            "fallbackUsed": True,
            "fallbackFrom": primary_id,
            "fallbackReason": str(primary_error)[:500],
        }


def _ollama_chat(messages: list[dict], max_tokens: int = 600) -> dict:
    model_id = os.getenv(
        "AIWORKS_OLLAMA_RAG_MODEL", "qwen2.5:1.5b"
    ).strip()
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    if not re.fullmatch(r"http://(?:127\.0\.0\.1|localhost):\d+", base_url):
        raise ApiError("데이터 MCP의 로컬 LLM은 loopback Ollama만 사용할 수 있습니다.", 503)
    request_payload = {
        "model": model_id,
        "messages": messages,
        "stream": False,
        "keep_alive": "10m",
        "options": {
            "temperature": 0.15,
            "num_predict": max(64, min(500, int(max_tokens))),
            "num_ctx": 8_192,
        },
    }
    request = url_request.Request(
        base_url + "/api/chat",
        data=_json(request_payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    timeout = max(10, min(90, int(os.getenv("AIWORKS_OLLAMA_TIMEOUT_SECONDS", "45"))))
    try:
        with url_request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except url_error.HTTPError as error:
        detail = error.read(2_000).decode("utf-8", "replace")
        raise ApiError(f"로컬 Ollama 호출 실패 ({error.code}): {detail}", 502) from error
    except (url_error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(f"로컬 Ollama 호출 실패: {error}", 502) from error
    content = (data.get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise ApiError("로컬 Ollama 응답 내용이 비어 있습니다.", 502)
    return {
        "content": content.strip(),
        "requestedModel": model_id,
        "resolvedModel": data.get("model") or model_id,
        "usage": {
            "input_tokens": int(data.get("prompt_eval_count") or 0),
            "output_tokens": int(data.get("eval_count") or 0),
        },
        "requestId": data.get("created_at"),
    }


def analyze_and_route(intent: str, classification: str = "internal") -> dict:
    ensure_schema()
    configuration = _runtime_mcp_configuration("core.intent-analysis", INTENT_ANALYSIS_MCP.MANIFEST)
    analysis = INTENT_ANALYSIS_MCP.analyze(intent, {}, configuration)
    route = MODEL_MANAGEMENT_MCP.select_model(analysis, classification)
    return {"intentAnalysis": analysis, "routing": route}


def routing_test(payload: dict) -> dict:
    intent = str(payload.get("intent") or "").strip()
    classification = str(payload.get("classification") or "public")
    decision = analyze_and_route(intent, classification)
    result = {
        **decision,
        "live": False,
        "openrouterConfigured": bool(_openrouter_key()),
    }
    if payload.get("live"):
        if not decision["routing"]["classificationAllowed"]:
            raise ApiError("이 데이터 등급은 선택된 외부 모델 테스트에 사용할 수 없습니다.", 403)
        model_id = decision["routing"]["model"]["id"]
        live = _openrouter_chat(
            model_id,
            [
                {
                    "role": "system",
                    "content": (
                        "You are a routing verification model. Do not reveal chain of thought. "
                        "Answer in Korean with one short sentence describing how you would handle the task."
                    ),
                },
                {"role": "user", "content": "합성 테스트 요청: " + intent[:500]},
            ],
            max_tokens=320,
        )
        result.update({"live": True, "response": live})
        ensure_schema()
        with _connect() as db:
            _audit(
                db,
                _actor(payload),
                "model.routing_test",
                {
                    "intent_type": decision["intentAnalysis"]["intentType"],
                    "selected_model": model_id,
                    "resolved_model": live["resolvedModel"],
                    "usage": live["usage"],
                    "synthetic_only": True,
                },
            )
    return result


def _make_result(intent: str, context: dict, route: dict | None = None) -> dict:
    before = str(
        context.get("selection")
        or "민원 업무의 복잡도가 높아지고 담당자별 답변 품질 편차가 발생함에 따라 지능형 업무 기반을 구축하고자 한다."
    )
    budget = "예산" in intent or "현재" in intent or "산출" in intent
    if budget:
        after = (
            "2026년 SW사업 대가산정 기준을 적용하여 중급기술자 월평균임금 856만원과 "
            "투입기간 10개월을 반영함. 이에 따라 SW 개발비 856백만원, 총사업비 "
            "1,284백만원을 산정함."
        )
        sources = [
            {"documentId": "sw-cost-guide-2026", "locator": "표 2 > 중급기술자", "confidence": 0.97},
            {"documentId": "doc-budget-2027-01", "locator": "3. 소요 예산", "confidence": 0.99},
        ]
    else:
        after = (
            "민원 대응의 신속성과 답변 품질의 일관성을 확보하기 위해 축적된 행정 지식과 "
            "최신 업무 기준을 연계한 지능형 지원 기반을 구축하고자 함.\n"
            "담당자의 업무 부담을 줄이고 대국민 서비스 품질을 향상하는 것을 목적으로 함."
        )
        sources = [{"documentId": "doc-budget-2027-01", "locator": "2. 추진 배경", "confidence": 0.98}]
    return {
        "patches": [
            {
                "op": "replace",
                "target": context.get("selection_id") or "document.paragraph.background",
                "before": before,
                "after": after,
            }
        ],
        "sources": sources,
        "model": {
            "provider": "openrouter",
            "name": ((route or {}).get("model") or {}).get(
                "id", "google/gemma-4-26b-a4b-it:free"
            ),
            "externalTransfer": True,
            "mode": "routing-simulation",
        },
        "policy": {"personalDataDetected": False, "maskedFields": []},
    }


def _installed_builder_package(binding: dict) -> dict:
    package_id = str(binding.get("packageId") or "")
    version = str(binding.get("version") or "")
    with _connect() as db:
        installation = db.execute(
            "SELECT * FROM mcp_installations WHERE package_id=? AND status='active'",
            (package_id,),
        ).fetchone()
        if not installation or installation["pinned_version"] != version:
            raise ApiError("계획에 고정된 MCP 버전이 더 이상 활성 상태가 아닙니다. 계획을 다시 만들어 주세요.", 409)
        package = _get_package(db, package_id, version)
    if not package["manifest"].get("builderGuide"):
        raise ApiError("Builder 실행 가이드가 없는 MCP는 동적 런타임에서 실행할 수 없습니다.", 409)
    return package


def _builder_runtime_references(package: dict) -> list[dict]:
    manifest = package["manifest"]
    references = {item.get("id"): item for item in manifest.get("references") or []}
    with _connect() as db:
        rows = db.execute(
            "SELECT * FROM mcp_package_files WHERE package_id=? AND version=? ORDER BY reference_id",
            (package["packageId"], package["version"]),
        ).fetchall()
    items = []
    for row in rows:
        contract = references.get(row["reference_id"], {})
        data = bytes(row["content_blob"])
        excerpt = ""
        if row["media_type"] in {"text/plain", "text/markdown"}:
            excerpt = data.decode("utf-8", errors="replace")[:4_000]
        items.append(
            {
                "id": row["reference_id"],
                "filename": row["filename"],
                "mediaType": row["media_type"],
                "sha256": row["sha256"],
                "role": contract.get("role", "guide"),
                "excerpt": excerpt,
                "content": data,
            }
        )
    return items


def _escape_xml_text(value: str) -> str:
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _set_hwpx_paragraph_text(node: ElementTree.Element, value: str) -> None:
    text_nodes = [item for item in node.iter() if _xml_local_name(item.tag) == "t"]
    if text_nodes:
        text_nodes[0].text = value
        for item in text_nodes[1:]:
            item.text = ""
        return
    run = next((item for item in node.iter() if _xml_local_name(item.tag) == "run"), None)
    if run is None:
        raise ApiError("양식 입력 영역에 텍스트 run이 없어 자동으로 채울 수 없습니다.", 409)
    namespace = run.tag.split("}", 1)[0] + "}" if "}" in run.tag else ""
    ElementTree.SubElement(run, namespace + "t").text = value


def _serialize_hwpx_xml(original: bytes, root: ElementTree.Element) -> bytes:
    for _event, namespace in ElementTree.iterparse(io.BytesIO(original), events=("start-ns",)):
        prefix, uri = namespace
        try:
            ElementTree.register_namespace(prefix, uri)
        except ValueError:
            pass
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=original.lstrip().startswith(b"<?xml"))




def _hwpx_node_text(node: ElementTree.Element) -> str:
    return "".join(str(item.text or "") for item in node.iter() if _xml_local_name(item.tag) == "t").strip()


def _prepare_hwpx_clone(node: ElementTree.Element, id_counter) -> ElementTree.Element:
    cloned = copy.deepcopy(node)
    for parent in list(cloned.iter()):
        for child in list(parent):
            if _xml_local_name(child.tag) == "linesegarray":
                parent.remove(child)
    for item in cloned.iter():
        if _xml_local_name(item.tag) in {"p", "tbl"} and "id" in item.attrib:
            item.attrib["id"] = str(next(id_counter))
    return cloned

_HWPX_MARKDOWN_INDENT_STEP = 1400


def _hwpx_paragraph_node(node: ElementTree.Element) -> ElementTree.Element | None:
    if _xml_local_name(node.tag) == "p":
        return node
    return next((item for item in node.iter() if _xml_local_name(item.tag) == "p"), None)


def _prepare_hwpx_indent_styles(original: bytes) -> dict | None:
    """Create paragraph styles without changing the template's shared styles."""
    try:
        root = ElementTree.fromstring(original)
    except ElementTree.ParseError:
        return None
    parents = {child: parent for parent in root.iter() for child in parent}
    styles = [item for item in root.iter() if _xml_local_name(item.tag) == "paraPr"]
    if not styles:
        return None
    style_parent = parents.get(styles[0])
    if style_parent is None:
        return None
    by_id = {str(item.attrib.get("id") or ""): item for item in styles}
    numeric_ids = [int(value) for value in by_id if value.isdigit()]
    return {
        "root": root,
        "original": original,
        "parent": style_parent,
        "byId": by_id,
        "nextId": max(numeric_ids, default=-1) + 1,
        "cache": {},
        "changed": False,
    }


def _hwpx_style_left(registry: dict | None, style_id: str) -> int:
    if not registry:
        return 0
    style = registry["byId"].get(str(style_id or ""))
    if style is None:
        return 0
    left = next((item for item in style.iter() if _xml_local_name(item.tag) == "left"), None)
    try:
        return int((left.attrib if left is not None else {}).get("value") or 0)
    except ValueError:
        return 0


def _ensure_hwpx_indent_style(registry: dict | None, base_style_id: str, left: int) -> str:
    if not registry:
        return str(base_style_id or "")
    key = (str(base_style_id or ""), max(0, int(left)))
    if key in registry["cache"]:
        return registry["cache"][key]
    base = registry["byId"].get(key[0])
    if base is None:
        base = next(iter(registry["byId"].values()))
    clone = copy.deepcopy(base)
    new_id = str(registry["nextId"])
    registry["nextId"] += 1
    clone.attrib["id"] = new_id
    for item in clone.iter():
        local_name = _xml_local_name(item.tag)
        if local_name == "left":
            item.attrib["value"] = str(key[1])
        elif local_name == "intent":
            item.attrib["value"] = "0"
    registry["parent"].append(clone)
    registry["byId"][new_id] = clone
    registry["cache"][key] = new_id
    registry["changed"] = True
    return new_id


def _apply_hwpx_indent(
    node: ElementTree.Element,
    registry: dict | None,
    *,
    base_left: int,
    depth: int,
) -> int:
    paragraph = _hwpx_paragraph_node(node)
    if paragraph is None or not registry:
        return 0
    base_style_id = str(paragraph.attrib.get("paraPrIDRef") or "")
    target_left = max(0, int(base_left) + max(0, min(3, int(depth))) * _HWPX_MARKDOWN_INDENT_STEP)
    paragraph.attrib["paraPrIDRef"] = _ensure_hwpx_indent_style(registry, base_style_id, target_left)
    return target_left


def _serialize_hwpx_indent_styles(registry: dict | None) -> bytes | None:
    if not registry or not registry.get("changed"):
        return None
    parent = registry["parent"]
    if "itemCnt" in parent.attrib:
        parent.attrib["itemCnt"] = str(sum(1 for item in list(parent) if _xml_local_name(item.tag) == "paraPr"))
    return _serialize_hwpx_xml(registry["original"], registry["root"])



def _report_template_text(value: str, prefix: str = "") -> str:
    text_value = str(value or "").strip()
    text_value = re.sub(r"^(?:(?:[IVXLCDM]+|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ]+)|\d{1,2})[.)]\s*", "", text_value, flags=re.IGNORECASE)
    text_value = re.sub(r"^(?:(?:[-*+•·○ㅇ□▪◦※])\s*)+", "", text_value).strip()
    text_value = re.sub(r"\*\*(.*?)\*\*", r"\1", text_value)
    text_value = text_value.replace("**", "").replace("`", "").strip()
    return (prefix + text_value).strip()


def _fill_hwpx_table_prototype(container: ElementTree.Element, rows: list[list[str]], id_counter) -> None:
    table = next((item for item in container.iter() if _xml_local_name(item.tag) in {"tbl", "table"}), None)
    if table is None:
        raise ApiError("양식의 표 prototype을 찾지 못했습니다.", 409)
    source_rows = [list(row) for row in rows if isinstance(row, list)]
    if not source_rows:
        source_rows = [[""]]
    column_count = max(1, max(len(row) for row in source_rows))
    normalized = [row + [""] * (column_count - len(row)) for row in source_rows]
    row_prototypes = [item for item in list(table) if _xml_local_name(item.tag) == "tr"]
    if not row_prototypes:
        raise ApiError("양식 표에 복제할 행 prototype이 없습니다.", 409)
    first_row_index = list(table).index(row_prototypes[0])
    for row in row_prototypes:
        table.remove(row)
    table.attrib["rowCnt"] = str(len(normalized))
    table.attrib["colCnt"] = str(column_count)
    table_size = next((item for item in table if _xml_local_name(item.tag) == "sz"), None)
    try:
        table_width = int((table_size.attrib if table_size is not None else {}).get("width") or 48000)
    except ValueError:
        table_width = 48000
    cell_width = max(1, table_width // column_count)
    rendered_rows = []
    for row_index, values in enumerate(normalized):
        row_source = row_prototypes[0] if row_index == 0 else row_prototypes[min(1, len(row_prototypes) - 1)]
        row_node = copy.deepcopy(row_source)
        cell_prototypes = [item for item in list(row_node) if _xml_local_name(item.tag) in {"tc", "cell"}]
        if not cell_prototypes:
            raise ApiError("양식 표에 복제할 셀 prototype이 없습니다.", 409)
        for cell in cell_prototypes:
            row_node.remove(cell)
        for column_index, value in enumerate(values):
            cell_source = cell_prototypes[min(column_index, len(cell_prototypes) - 1)]
            cell = _prepare_hwpx_clone(cell_source, id_counter)
            address = next((item for item in cell.iter() if _xml_local_name(item.tag) == "cellAddr"), None)
            if address is not None:
                address.attrib["colAddr"] = str(column_index)
                address.attrib["rowAddr"] = str(row_index)
            span = next((item for item in cell.iter() if _xml_local_name(item.tag) == "cellSpan"), None)
            if span is not None:
                span.attrib["colSpan"] = "1"
                span.attrib["rowSpan"] = "1"
            size = next((item for item in cell.iter() if _xml_local_name(item.tag) == "cellSz"), None)
            if size is not None:
                size.attrib["width"] = str(cell_width)
            paragraph = next((item for item in cell.iter() if _xml_local_name(item.tag) == "p"), None)
            if paragraph is None:
                raise ApiError("양식 표 셀에 텍스트 문단이 없습니다.", 409)
            _set_hwpx_paragraph_text(paragraph, str(value))
            row_node.append(cell)
        rendered_rows.append(row_node)
    for offset, row_node in enumerate(rendered_rows):
        table.insert(first_row_index + offset, row_node)


def _render_report_document_hwpx_template(
    template: bytes,
    report_document: dict,
    source_filename: str,
    guide: dict,
) -> tuple[bytes, dict]:
    title = str(report_document.get("title") or Path(source_filename).stem or "AIWorks 보고서").strip()
    source_blocks = [item for item in report_document.get("blocks") or [] if isinstance(item, dict)]
    blocks = []
    for item in source_blocks:
        normalized_heading = _report_template_text(item.get("text")) if item.get("type") == "heading" else ""
        decorative_business_heading = (
            item.get("type") == "heading"
            and "사업" in normalized_heading
            and bool(re.match(r"^[―—-].+[―—-]$", normalized_heading))
        )
        if not decorative_business_heading:
            blocks.append(item)
    if not blocks:
        raise ApiError("양식에 적용할 ReportDocument 블록이 없습니다.", 409)
    try:
        source_archive = zipfile.ZipFile(io.BytesIO(template))
    except zipfile.BadZipFile as error:
        raise ApiError("등록된 양식 원본이 유효한 HWPX가 아닙니다.", 409) from error
    section_payloads = {}
    rendered_blocks = 0
    rendered_tables = 0
    id_counter = iter(range(4000000000, 4294967000))
    document_metadata = report_document.get("metadata") if isinstance(report_document.get("metadata"), dict) else {}
    fact_items = (report_document.get("factSnapshot") or {}).get("facts") or {}

    def metadata_value(explicit_key: str, *signals: str) -> str:
        explicit = str(document_metadata.get(explicit_key) or "").strip()
        if explicit:
            return explicit
        for fact_key, item in fact_items.items():
            haystack = (str(fact_key) + " " + str(item.get("label") or "")).lower()
            if any(signal.lower() in haystack for signal in signals):
                value = item.get("value")
                return str(value if value is not None else "").strip()
        return ""

    with source_archive:
        infos = source_archive.infolist()
        header_info = next(
            (item for item in infos if item.filename.lower() == "contents/header.xml"),
            None,
        )
        indent_registry = _prepare_hwpx_indent_styles(source_archive.read(header_info.filename)) if header_info else None
        indentation_levels = set()
        target_found = False
        for info in infos:
            if not re.fullmatch(r"Contents/section\d+\.xml", info.filename, flags=re.IGNORECASE):
                continue
            original = source_archive.read(info.filename)
            root = ElementTree.fromstring(original)
            auxiliary_replaced = False
            auxiliary_values = {
                "{{date}}": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d"),
                "{{source_filename}}": Path(source_filename).name,
                "{{department}}": metadata_value("department", "department", "부서", "기관"),
                "{{author}}": metadata_value("author", "author", "작성자", "담당자"),
                "{{document_number}}": metadata_value("documentNumber", "document_number", "문서번호"),
                "{{approval_line}}": metadata_value("approvalLine", "approval", "결재") or "담당 / 검토 / 승인",
            }
            for text_node in (item for item in root.iter() if _xml_local_name(item.tag) == "t" and item.text):
                for token, value in auxiliary_values.items():
                    if token in text_node.text:
                        text_node.text, auxiliary_replaced = text_node.text.replace(token, value), True
            paragraphs = [node for node in root.iter() if _xml_local_name(node.tag) == "p"]
            title_targets = [
                node for node in paragraphs
                if not any(item is not node and _xml_local_name(item.tag) == "p" for item in node.iter())
                and ("{{title}}" in _hwpx_node_text(node) or _TEMPLATE_SAMPLE_TITLE_PATTERN.search(_hwpx_node_text(node)))
            ]
            if title_targets:
                _set_hwpx_paragraph_text(title_targets[-1], title)
            parents = {child: parent for parent in root.iter() for child in parent}
            leaf_body_targets = [
                node
                for node in paragraphs
                if not any(item is not node and _xml_local_name(item.tag) == "p" for item in node.iter())
                and (
                    "{{content}}" in _hwpx_node_text(node)
                    or "{{body}}" in _hwpx_node_text(node)
                    or _TEMPLATE_SAMPLE_BODY_PATTERN.search(_hwpx_node_text(node))
                )
            ]
            if not leaf_body_targets:
                section_payloads[info.filename] = _serialize_hwpx_xml(original, root) if title_targets or auxiliary_replaced else original
                continue
            body_anchor = next(
                (
                    node for node in leaf_body_targets
                    if "{{content}}" in _hwpx_node_text(node) or "{{body}}" in _hwpx_node_text(node)
                ),
                leaf_body_targets[0],
            )
            body_container = parents.get(body_anchor, root)
            container_nodes = list(body_container)
            body_indexes = []
            for index, node in enumerate(container_nodes):
                if _xml_local_name(node.tag) != "p":
                    continue
                if node is not body_anchor and any(title_target is descendant for descendant in node.iter() for title_target in title_targets):
                    continue
                text_value = _hwpx_node_text(node)
                has_data_table = any(_xml_local_name(item.tag) in {"tbl", "table"} for item in node.iter()) and (
                    _TEMPLATE_SAMPLE_CLEAR_PATTERN.search(text_value)
                    or "항목" in text_value
                    or "내용" in text_value
                )
                if (
                    node is body_anchor
                    or _TEMPLATE_SAMPLE_BODY_PATTERN.search(text_value)
                    or _TEMPLATE_SAMPLE_CLEAR_PATTERN.search(text_value)
                    or has_data_table
                ):
                    body_indexes.append(index)
            if not body_indexes:
                body_indexes = [container_nodes.index(body_anchor)]
            start_index, end_index = min(body_indexes), max(body_indexes)
            prototypes = container_nodes[start_index : end_index + 1]
            heading_prototype = next(
                (item for item in prototypes if "{{content}}" in _hwpx_node_text(item) or "{{body}}" in _hwpx_node_text(item) or "대제목" in _hwpx_node_text(item)),
                prototypes[0],
            )
            main_prototype = next((item for item in prototypes if re.match(r"^\s*[○ㅇ]", _hwpx_node_text(item))), next((item for item in paragraphs if re.match(r"^\s*[○ㅇ]", _hwpx_node_text(item))), heading_prototype))
            sub_prototype = next((item for item in prototypes if re.match(r"^\s*[-·]", _hwpx_node_text(item))), next((item for item in paragraphs if re.match(r"^\s*[-·]", _hwpx_node_text(item))), main_prototype))
            note_prototype = next((item for item in prototypes if re.match(r"^\s*[※*]", _hwpx_node_text(item))), next((item for item in paragraphs if re.match(r"^\s*[※*]", _hwpx_node_text(item))), sub_prototype))
            heading_paragraph = _hwpx_paragraph_node(heading_prototype)
            heading_style_id = str((heading_paragraph.attrib if heading_paragraph is not None else {}).get("paraPrIDRef") or "")
            base_left = _hwpx_style_left(indent_registry, heading_style_id)
            table_prototype = next(
                (
                    item for item in prototypes
                    if any(_xml_local_name(desc.tag) in {"tbl", "table"} for desc in item.iter())
                    and ("항목" in _hwpx_node_text(item) or "내용" in _hwpx_node_text(item))
                ),
                None,
            )
            if table_prototype is None:
                table_prototype = next(
                    (
                        item for item in paragraphs
                        if any(_xml_local_name(desc.tag) in {"tbl", "table"} for desc in item.iter())
                        and ("항목" in _hwpx_node_text(item) or "내용" in _hwpx_node_text(item))
                    ),
                    None,
                )
            for node in reversed(container_nodes[start_index : end_index + 1]):
                body_container.remove(node)
            output_nodes = []
            heading_depth = 0
            for block in blocks:
                kind = str(block.get("type") or "")
                if kind == "table":
                    if table_prototype is None:
                        for row in block.get("rows") or []:
                            fallback = _prepare_hwpx_clone(main_prototype, id_counter)
                            _set_hwpx_paragraph_text(fallback, "○ " + " / ".join(str(cell) for cell in row))
                            indentation_levels.add(_apply_hwpx_indent(fallback, indent_registry, base_left=base_left, depth=max(1, heading_depth + 1)))
                            output_nodes.append(fallback)
                            rendered_blocks += 1
                    else:
                        table_node = _prepare_hwpx_clone(table_prototype, id_counter)
                        _fill_hwpx_table_prototype(table_node, block.get("rows") or [], id_counter)
                        indentation_levels.add(_apply_hwpx_indent(table_node, indent_registry, base_left=base_left, depth=max(1, heading_depth + 1)))
                        output_nodes.append(table_node)
                        rendered_blocks += 1
                        rendered_tables += 1
                    continue
                if kind == "heading":
                    markdown_level = max(2, min(6, int(block.get("level") or 2)))
                    heading_depth = min(3, markdown_level - 2)
                    if heading_depth == 0:
                        prototype, marker = heading_prototype, "□ "
                    elif heading_depth == 1:
                        prototype, marker = main_prototype, "○ "
                    elif heading_depth == 2:
                        prototype, marker = sub_prototype, "- "
                    else:
                        prototype, marker = note_prototype, "※ "
                    depth, value = heading_depth, _report_template_text(block.get("text"), marker)
                elif kind == "list_item":
                    level = max(1, int(block.get("level") or 1))
                    depth = min(3, max(level, heading_depth + 1))
                    if depth == 1:
                        prototype, value = main_prototype, _report_template_text(block.get("text"), "○ ")
                    elif depth == 2:
                        prototype, value = sub_prototype, _report_template_text(block.get("text"), "- ")
                    else:
                        prototype, value = note_prototype, _report_template_text(block.get("text"), "※ ")
                elif kind == "note":
                    depth = 3
                    prototype, value = note_prototype, _report_template_text(block.get("text"), "※ ")
                else:
                    depth = min(3, max(1, heading_depth + 1))
                    if depth == 1:
                        prototype, marker = main_prototype, "○ "
                    elif depth == 2:
                        prototype, marker = sub_prototype, "- "
                    else:
                        prototype, marker = note_prototype, "※ "
                    value = _report_template_text(block.get("text"), marker)
                node = _prepare_hwpx_clone(prototype, id_counter)
                _set_hwpx_paragraph_text(node, value)
                indentation_levels.add(_apply_hwpx_indent(node, indent_registry, base_left=base_left, depth=depth))
                output_nodes.append(node)
                rendered_blocks += 1
            for offset, node in enumerate(output_nodes):
                body_container.insert(start_index + offset, node)
            section_payloads[info.filename] = _serialize_hwpx_xml(original, root)
            target_found = True
        if not target_found:
            raise ApiError("양식에서 ReportDocument를 반복 배치할 본문 prototype 영역을 찾지 못했습니다.", 409)
        output = io.BytesIO()
        preview_lines = [title]
        for block in blocks:
            if block.get("type") == "table":
                preview_lines.extend(" | ".join(str(cell) for cell in row) for row in block.get("rows") or [])
            else:
                preview_lines.append(str(block.get("text") or ""))
        with zipfile.ZipFile(output, "w") as target:
            rendered_header = _serialize_hwpx_indent_styles(indent_registry)
            for info in infos:
                data = rendered_header if rendered_header is not None and header_info and info.filename == header_info.filename else section_payloads.get(info.filename, source_archive.read(info.filename))
                if info.filename == "Preview/PrvText.txt":
                    data = "\n".join(preview_lines).encode("utf-8")
                target.writestr(info, data)
    result = output.getvalue()
    parsed_result = parse_hwpx(result, str(guide.get("templateName") or source_filename))
    expected_tables = sum(1 for block in blocks if block.get("type") == "table")
    if rendered_blocks < len(blocks) or parsed_result.get("stats", {}).get("tables", 0) < expected_tables:
        raise ApiError("양식 구조 바인딩 결과에서 문단 또는 표가 누락되었습니다.", 409)
    literal_markdown = any(
        re.search(r"\|\s*:?-{3,}:?\s*\|", str(item.get("text") or ""))
        for item in parsed_result.get("paragraphs") or []
    )
    if literal_markdown:
        raise ApiError("양식 결과에 Markdown 표 구분자가 평문으로 남았습니다.", 409)
    return result, {
        "name": str(guide.get("templateName") or "사용자 등록 양식"),
        "mode": "report-document-structural",
        "confidence": 1.0,
        "analysis": _analyze_hwpx_template(template),
        "placeholderReplacements": 0,
        "preservedParagraphs": len(parsed_result.get("paragraphs") or []),
        "renderedBlocks": rendered_blocks,
        "renderedTables": rendered_tables,
        "indentationApplied": bool(indent_registry and indent_registry.get("changed")),
        "indentationStepHwpunit": _HWPX_MARKDOWN_INDENT_STEP,
        "indentationLevels": sorted(value for value in indentation_levels if isinstance(value, int)),
        "mappingCoverage": 1.0,
        "guideVersion": guide.get("version", "1.0"),
    }


def _evaluate_hwpx_template_quality(template: bytes, filename: str) -> dict:
    """Exercise the structural renderer and verify its parsed output."""
    schema = _hwpx_template_schema(template)
    sentinels = {
        "title": "AIWORKS_QUALITY_TITLE_7F3A",
        "heading": "AIWORKS_QUALITY_SECTION_7F3A",
        "body": "AIWORKS_QUALITY_BODY_7F3A",
        "list": "AIWORKS_QUALITY_LIST_7F3A",
        "tableHeader": "AIWORKS_QUALITY_TABLE_HEADER_7F3A",
        "tableValue": "AIWORKS_QUALITY_TABLE_VALUE_7F3A",
    }
    blocks = [
        {"id": "quality-heading", "type": "heading", "level": 2, "text": sentinels["heading"]},
        {"id": "quality-body", "type": "paragraph", "text": sentinels["body"]},
        {"id": "quality-list", "type": "list_item", "level": 2, "text": sentinels["list"]},
    ]
    table_required = bool((schema.get("repeaters") or {}).get("tables"))
    if table_required:
        blocks.append({
            "id": "quality-table",
            "type": "table",
            "rows": [[sentinels["tableHeader"], "값"], ["항목", sentinels["tableValue"]]],
        })
    checks = []

    def check(check_id: str, passed: bool, detail: str) -> None:
        checks.append({"id": check_id, "passed": bool(passed), "detail": detail})

    try:
        rendered, metadata = _render_report_document_hwpx_template(
            template,
            {"title": sentinels["title"], "blocks": blocks},
            filename,
            {"templateName": filename, "version": "quality-1.0"},
        )
        parsed = parse_hwpx(rendered, "AIWorks-template-quality.hwpx")
        texts = [str(item.get("text") or "") for item in parsed.get("paragraphs") or []]
        joined = "\n".join(texts)
        with zipfile.ZipFile(io.BytesIO(rendered)) as rendered_archive:
            raw_sections = "\n".join(
                rendered_archive.read(item.filename).decode("utf-8", errors="replace")
                for item in rendered_archive.infolist() if re.fullmatch(r"Contents/section\d+\.xml", item.filename, flags=re.IGNORECASE)
            )
        title_count = raw_sections.count(sentinels["title"])
        body_count = raw_sections.count(sentinels["body"])
        check("render.completed", True, "테스트 ReportDocument 렌더링 완료")
        check("render.title-once", title_count == 1, f"테스트 제목 출현 {title_count}회")
        check("render.body-once", body_count == 1, f"테스트 본문 출현 {body_count}회")
        check("render.heading", sentinels["heading"] in joined, "Markdown 제목 블록 배치 확인")
        check("render.list", sentinels["list"] in joined, "Markdown 목록 블록 배치 확인")
        unresolved = sorted(set(re.findall(r"\{\{[A-Za-z0-9_.-]+\}\}", raw_sections)))
        check("render.placeholders", not unresolved, "미치환 토큰 없음" if not unresolved else "미치환 토큰: " + ", ".join(unresolved))
        if table_required:
            table_ok = (
                int(metadata.get("renderedTables") or 0) == 1
                and sentinels["tableHeader"] in joined
                and sentinels["tableValue"] in joined
            )
            check("render.table", table_ok, "실제 표 1개와 테스트 셀 값 확인")
        coverage = float(metadata.get("mappingCoverage") or 0)
        check("render.mapping", coverage >= 0.95, f"구조 매핑률 {coverage:.0%}")
        metrics = {
            "renderedBlocks": int(metadata.get("renderedBlocks") or 0),
            "renderedTables": int(metadata.get("renderedTables") or 0),
            "mappingCoverage": coverage,
            "parsedParagraphs": len(texts),
            "parsedTables": int((parsed.get("stats") or {}).get("tables") or 0),
            "tableCapability": table_required,
        }
    except Exception as error:
        check("render.completed", False, str(error))
        metrics = {"renderedBlocks": 0, "renderedTables": 0, "mappingCoverage": 0.0, "tableCapability": table_required}
    return {"passed": all(item["passed"] for item in checks), "checks": checks, "metrics": metrics, "contractVersion": "1.0"}

def _apply_builder_hwpx_template(template: bytes, source: bytes, source_filename: str, guide: dict, report_document: dict | None = None) -> tuple[bytes, dict]:
    if isinstance(report_document, dict) and report_document.get("blocks"):
        return _render_report_document_hwpx_template(template, report_document, source_filename, guide)
    parsed = parse_hwpx(source, source_filename)
    paragraphs = [item["text"] for item in parsed.get("paragraphs") or [] if item.get("text")]
    if not paragraphs:
        raise ApiError("양식에 대응할 원문 문구가 없습니다.", 409)
    title = paragraphs[0][:500]
    body = "\n".join(paragraphs[1:300])
    now = datetime.now(timezone.utc).astimezone()
    replacements = {
        "{{title}}": title,
        "{{content}}": body,
        "{{body}}": body,
        "{{source_filename}}": Path(source_filename).name,
        "{{date}}": now.strftime("%Y-%m-%d"),
    }
    profile = _analyze_hwpx_template(template)
    try:
        source_archive = zipfile.ZipFile(io.BytesIO(template))
    except zipfile.BadZipFile as error:
        raise ApiError("등록된 양식 원본이 유효한 HWPX가 아닙니다.", 409) from error
    section_payloads = {}
    replacement_count = 0
    with source_archive:
        infos = source_archive.infolist()
        if profile["mode"] == "explicit-placeholders":
            for info in infos:
                if not re.fullmatch(r"Contents/section\d+\.xml", info.filename, flags=re.IGNORECASE):
                    continue
                text = source_archive.read(info.filename).decode("utf-8")
                for token, value in replacements.items():
                    count = text.count(token)
                    if count:
                        text = text.replace(token, _escape_xml_text(value))
                        replacement_count += count
                section_payloads[info.filename] = text.encode("utf-8")
        else:
            section_models = []
            candidates = []
            blanks = []
            title_targets = []
            sample_cleanup = []
            for info in infos:
                if not re.fullmatch(r"Contents/section\d+\.xml", info.filename, flags=re.IGNORECASE):
                    continue
                original = source_archive.read(info.filename)
                root, nodes = _hwpx_paragraph_nodes(original)
                section_models.append((info.filename, original, root))
                for node, text in nodes:
                    is_leaf_paragraph = not any(
                        item is not node and _xml_local_name(item.tag) == "p"
                        for item in node.iter()
                    )
                    if not text:
                        blanks.append((node, text))
                    elif profile["mode"] == "guided-fields":
                        if _TEMPLATE_INSTRUCTION_PATTERN.search(text) or _TEMPLATE_EXAMPLE_PATTERN.search(text):
                            candidates.append((node, text))
                    elif profile["mode"] == "sample-structure" and is_leaf_paragraph:
                        if _TEMPLATE_SAMPLE_TITLE_PATTERN.search(text):
                            title_targets.append((node, text))
                        elif _TEMPLATE_SAMPLE_BODY_PATTERN.search(text):
                            candidates.append((node, text))
                        elif _TEMPLATE_SAMPLE_CLEAR_PATTERN.search(text):
                            sample_cleanup.append((node, text))
                    elif len(text) >= 18 and not re.match(r"^(?:붙임|담당|부서|일시|장소|목적|개요|[ⅠⅡⅢⅣⅤ]|\d+[.)])", text):
                        candidates.append((node, text))
            if profile["mode"] == "guided-fields" and not candidates:
                candidates = blanks[: max(1, min(8, len(paragraphs)))]
            if not candidates:
                raise ApiError("양식에서 자동으로 채울 본문 영역을 찾지 못했습니다. 작성요령·예시 문구를 추가하거나 시작 양식의 플레이스홀더를 사용해 주세요.", 409)
            title_target = next((item for item in candidates if "제목" in item[1]), None)
            if title_target and not title_targets:
                title_targets = [title_target]
            for target in title_targets:
                _set_hwpx_paragraph_text(target[0], title)
                candidates = [item for item in candidates if item[0] is not target[0]]
                replacement_count += 1
            body_parts = paragraphs[1:] or paragraphs
            if not candidates:
                candidates = blanks[:1]
            if not candidates:
                raise ApiError("양식에 본문을 넣을 수 있는 문단이 없습니다.", 409)
            for index, item in enumerate(candidates):
                if index >= len(body_parts):
                    if profile["mode"] == "guided-fields":
                        _set_hwpx_paragraph_text(item[0], "")
                    continue
                if index == len(candidates) - 1:
                    value = "\n".join(body_parts[index:])
                else:
                    value = body_parts[index]
                _set_hwpx_paragraph_text(item[0], value)
                replacement_count += 1
            for item in sample_cleanup:
                _set_hwpx_paragraph_text(item[0], "")
                replacement_count += 1
            for filename, original, root in section_models:
                section_payloads[filename] = _serialize_hwpx_xml(original, root)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as target:
            for info in infos:
                data = section_payloads.get(info.filename, source_archive.read(info.filename))
                if info.filename == "Preview/PrvText.txt":
                    data = (title + "\n" + body).encode("utf-8")
                target.writestr(info, data)
    return output.getvalue(), {
        "name": str(guide.get("templateName") or "사용자 등록 양식"),
        "mode": profile["mode"],
        "confidence": profile["confidence"],
        "analysis": profile,
        "placeholderReplacements": replacement_count,
        "preservedParagraphs": len(paragraphs),
        "guideVersion": guide.get("version", "1.0"),
    }


def _apply_template_binding_to_artifact(binding: dict, artifact: dict) -> tuple[dict, str]:
    package = _installed_builder_package(binding)
    manifest = package["manifest"]
    package_ref = package["packageId"] + "@" + package["version"]
    references = _builder_runtime_references(package)
    template_reference = next((item for item in references if item["role"] == "template-source"), None)
    if not template_reference:
        raise ApiError("선택된 양식 MCP에 양식 원본이 없습니다.", 409)
    if not template_reference["filename"].lower().endswith(".hwpx"):
        raise ApiError("선택된 양식 MCP의 원본이 HWPX가 아닙니다.", 415)
    try:
        source_hwpx = base64.b64decode(str(artifact.get("contentBase64") or ""), validate=True)
    except (ValueError, TypeError) as error:
        raise ApiError("양식에 적용할 보고서 HWPX가 올바르지 않습니다.", 422) from error
    formatted, metadata = _apply_builder_hwpx_template(
        template_reference["content"],
        source_hwpx,
        str(artifact.get("filename") or "AIWorks_보고서.hwpx"),
        {**(manifest.get("builderGuide") or {}), "templateName": manifest.get("name")},
        artifact.get("reportDocument") or {},
    )
    safe_name = re.sub(r'[^0-9A-Za-z가-힣._-]+', "_", str(manifest.get("name") or "등록양식"))[:60]
    filename = (Path(str(artifact.get("filename") or "AIWorks_보고서.hwpx")).stem[:60] or "AIWorks") + "_" + safe_name + ".hwpx"
    return {
        **artifact,
        "filename": filename,
        "contentBase64": base64.b64encode(formatted).decode("ascii"),
        "template": {
            **metadata,
            "packageRef": package_ref,
            "source": template_reference["filename"],
            "sourceSha256": template_reference["sha256"],
        },
        "templateApplication": {
            "packageRef": package_ref,
            "mode": "new-report",
            "source": template_reference["filename"],
        },
        "derivedOutput": {"format": "hwpx", "renderer": package_ref},
        "generatedBy": list(dict.fromkeys([*(artifact.get("generatedBy") or []), package_ref])),
    }, package_ref


def _builder_runtime_messages(manifest: dict, intent: str, input_context: dict, references: list[dict]) -> list[dict]:
    guide = manifest.get("builderGuide") or {}
    selection = str(input_context.get("selection") or "")[:4_000]
    reference_text = "\n\n".join(
        item["filename"] + ":\n" + item["excerpt"]
        for item in references
        if item.get("excerpt")
    )[:8_000]
    system = "\n".join(
        [
            "당신은 AIWorks에서 검증·설치된 MCP 실행기입니다.",
            "MCP: " + str(manifest.get("name") or manifest.get("id")),
            "실행 지침: " + str(guide.get("instructions") or ""),
            "유의사항: " + " / ".join(guide.get("cautions") or []),
            "처리 절차: " + " -> ".join(guide.get("procedure") or []),
            "확인할 수 없는 값은 임의로 만들지 말고 확인 필요로 표시하세요.",
        ]
    )[:12_000]
    user = "요청: " + intent[:2_000]
    if selection:
        user += "\n선택 문구: " + selection
    if reference_text:
        user += "\n등록 참고자료:\n" + reference_text
    facts = ((input_context.get("project_fact_snapshot") or {}).get("facts") or {})
    if facts:
        user += "\n프로젝트 확정 메타정보:\n" + "\n".join(
            f"- [FACT {key}] {item.get('label')}: {item.get('value')} {item.get('unit') or ''}".rstrip()
            for key, item in list(facts.items())[:30]
        )
    markdown_documents = input_context.get("project_markdown_context") or []
    if input_context.get("project_markdown_prompt_allowed") is True and markdown_documents:
        user += "\n프로젝트 Markdown 원본:\n" + "\n\n".join(
            "[MD " + str(item.get("versionId") or "") + "] " + str(item.get("title") or "프로젝트 문서") + "\n" + str(item.get("markdown") or "")
            for item in markdown_documents[:6]
        )[:24_000]
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _rag_runtime_messages(manifest: dict, intent: str, hits: list[dict], fact_snapshot: dict | None = None, markdown_documents: list[dict] | None = None, allow_markdown: bool = False) -> list[dict]:
    guide = manifest.get("builderGuide") or {}
    evidence = "\n\n".join(
        f"[{index}] {item['filename']}"
        + (f" {item['pageNumber']}쪽" if item.get("pageNumber") else "")
        + "\n"
        + str(item.get("content") or "")[:1_300]
        for index, item in enumerate(hits[:3], start=1)
    )[:4_500]
    current_year = datetime.now(timezone.utc).year
    evidence_years = sorted({
        int(year) for year in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", evidence)
        if 2000 <= int(year) <= current_year + 2
    })
    year_hint = ", ".join(str(year) + "년" for year in evidence_years)
    issue_focused = any(term in intent for term in ("지적", "문제", "우려", "개선"))
    issue_rule = (
        "이 질문은 지적사항 중심입니다. 단순 예산 현황을 되풀이하지 말고 문제·원인·재정 위험·개선 필요만 최대 8개 항목으로 작성하세요. "
        "근거가 특정 연도에 명시한 수치나 집행 실적을 다른 연도에 복사하지 마세요."
        if issue_focused else
        "질문의 범위를 벗어나는 표나 부가 분석을 만들지 마세요."
    )
    facts = ((fact_snapshot or {}).get("facts") or {})
    fact_context = "\n".join(
        f"- [FACT {key}] {item.get('label')}: {item.get('value')} {item.get('unit') or ''}".rstrip()
        for key, item in list(facts.items())[:30]
    )
    markdown_context = ""
    if allow_markdown:
        markdown_context = "\n\n".join(
            "[MD " + str(item.get("versionId") or "") + "] " + str(item.get("title") or "프로젝트 문서") + "\n" + str(item.get("markdown") or "")
            for item in (markdown_documents or [])[:6]
        )[:24_000]
    return [
        {
            "role": "system",
            "content": "\n".join(
                [
                    "당신은 AIWorks의 출처 기반 데이터 MCP입니다.",
                    "검색 청크를 그대로 복사하지 말고, 아래 검색 근거를 읽고 판단하여 질문이 요구한 형식으로 종합하세요.",
                    "연도별·기관별·항목별·비교·표·시사점처럼 사용자가 지정한 정리 기준을 반드시 따르세요.",
                    "문서의 발간연도와 본문에서 언급하는 사업연도를 구분하고, 같은 지적을 중복해서 쓰지 마세요.",
                    "질문이 연도별 정리를 요구하면 근거에 등장하는 관련 사업연도마다 별도 행을 만들고 서로 합치지 마세요.",
                    ("연도별 정리 후보: " + year_hint + ". 관련 내용이 있는 각 연도를 빠짐없이 별도 행으로 작성하세요.") if year_hint else "연도가 확인되지 않으면 임의로 만들지 마세요.",
                    issue_rule,
                    "각 핵심 주장 끝에 반드시 [1] 같은 근거 번호를 표시하세요.",
                    "근거에 없는 값은 추측하지 말고 확인할 수 없다고 답하세요.",
                    "먼저 결론을 제시하고 필요한 경우 짧은 표나 글머리표를 사용하세요.",
                    "보고서 요청이면 Markdown 제목과 절, 표, '- ' 목록만 사용하세요. 목록 본문에 ·, •, ○ 같은 글머리표 문자를 다시 넣지 마세요.",
                    "실행 지침: " + str(guide.get("instructions") or ""),
                    "유의사항: " + " / ".join(guide.get("cautions") or []),
                ]
            )[:8_000],
        },
        {"role": "user", "content": "질문: " + intent[:2_000] + "\n\n프로젝트 확정 메타정보:\n" + (fact_context or "없음") + "\n\n프로젝트 Markdown 원본:\n" + (markdown_context or "없음") + "\n\n검색 근거:\n" + evidence},
    ]


def _validate_rag_synthesis(intent: str, answer: str, hits: list[dict]) -> str:
    normalized = str(answer or "").strip()
    if not normalized:
        raise ApiError("LLM 종합 답변이 비어 있습니다.", 502)
    if hits and not re.search(r"\[\d+\]", normalized):
        raise ApiError("LLM 종합 답변에 원문 근거 번호가 없습니다.", 502)
    if "연도별" in intent:
        evidence = " ".join(str(item.get("content") or "") for item in hits[:3])
        current_year = datetime.now(timezone.utc).year
        required_years = sorted({
            year for year in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", evidence)
            if 2000 <= int(year) <= current_year + 2
        })
        missing = [year for year in required_years if year + "년" not in normalized]
        if missing:
            raise ApiError("LLM 종합 답변에 요청 연도가 누락되었습니다: " + ", ".join(missing), 502)
    return normalized


def _review_report_against_request(intent: str, markdown: str, hits: list[dict]) -> dict:
    request = str(intent or "").strip()
    content = str(markdown or "").strip()
    normalized_request = _semantic_text(request).lower()
    normalized_content = _semantic_text(content).lower()
    checks = []

    def add(check_id: str, passed: bool, message: str, severity: str = "error") -> None:
        checks.append({"id": check_id, "passed": bool(passed), "severity": severity, "message": message})

    add("document.non-empty", bool(content), "초안 본문이 생성되어야 합니다.")
    add("document.markdown-title", bool(re.search(r"(?m)^#\s+\S", content)), "Markdown 최상위 제목이 필요합니다.", "warning")
    requested_years = set(re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", request))
    requested_years.update("20" + year for year in re.findall(r"(?<!\d)(\d{2})\s*년", request))
    for year in sorted(requested_years):
        add("request.year." + year, year in content or year[2:] + "년" in content, year + "년 요청 범위가 초안에 반영되어야 합니다.")
    required_terms = []
    if "지적" in normalized_request:
        required_terms.append(("request.issues", ("지적", "문제", "우려"), "요청한 지적사항이 포함되어야 합니다."))
    if any(term in normalized_request for term in ("대안", "개선방안", "개선 방안")):
        required_terms.append(("request.alternatives", ("대안", "개선", "조치"), "지적사항별 대안 또는 개선방안이 포함되어야 합니다."))
    if "향후 계획" in normalized_request or "향후계획" in normalized_request:
        required_terms.append(("request.future-plan", ("향후 계획", "향후계획", "추진계획"), "향후 계획이 포함되어야 합니다."))
    for check_id, terms, message in required_terms:
        add(check_id, any(term in normalized_content for term in terms), message)
    generic = {"관련", "보고서", "작성", "확인", "대해서", "포함", "양식", "행안부", "행정안전부", "예산", "결산", "사항", "올해", "대한"}
    generic_suffixes = ("으로", "에서", "에게", "부터", "까지", "처럼", "별로", "에", "을", "를", "이", "가", "은", "는", "와", "과", "로", "의")
    candidates = [
        token
        for token in _rag_query_tokens(request)
        if len(token) >= 4
        and not re.fullmatch(r"\d+년?", token)
    ]
    def is_generic_subject(token: str) -> bool:
        stem = token
        for suffix in generic_suffixes:
            if stem.endswith(suffix) and len(stem) - len(suffix) >= 2:
                stem = stem[:-len(suffix)]
                break
        return token in generic or stem in generic or token in {"작성해줘", "작성해주세요", "확인해줘", "확인해주세요"}
    ordered_candidates = sorted(
        candidates,
        key=lambda token: (
            normalized_request.find(token.lower()) if normalized_request.find(token.lower()) >= 0 else 10_000,
            len(token),
            token,
        ),
    )
    subject_tokens = []
    for token in ordered_candidates:
        if is_generic_subject(token):
            continue
        if any(token.startswith(existing) or existing.startswith(token) for existing in subject_tokens):
            continue
        subject_tokens.append(token)
        if len(subject_tokens) == 4:
            break
    if subject_tokens:
        matched = [token for token in subject_tokens if token.lower() in normalized_content]
        add("request.subject", len(matched) >= max(1, (len(subject_tokens) + 1) // 2), "요청 핵심 주제와 초안 대상이 일치해야 합니다: " + ", ".join(subject_tokens))
    if hits:
        add("evidence.citations", bool(re.search(r"\[\d+\]", content)), "검색 근거 번호를 핵심 주장에 표시해야 합니다.")
    errors = [item for item in checks if not item["passed"] and item["severity"] == "error"]
    warnings = [item for item in checks if not item["passed"] and item["severity"] == "warning"]
    passed_count = sum(1 for item in checks if item["passed"])
    return {
        "contractVersion": "1.0",
        "passed": not errors,
        "score": round(passed_count / max(1, len(checks)), 3),
        "checks": checks,
        "issues": [item["message"] for item in errors],
        "warnings": [item["message"] for item in warnings],
        "requestCompared": True,
        "evidenceCompared": bool(hits),
    }


def _external_mcp_endpoint(connector: dict) -> str:
    env_name = str(connector.get("endpointEnv") or "").strip()
    endpoint = str(os.getenv(env_name, "")).strip() if env_name else ""
    if not endpoint:
        raise ApiError(f"외부 MCP 연결 주소가 없습니다. 서버에 {env_name or 'endpoint 환경변수'}를 설정해 주세요.", 503)
    from urllib.parse import urlparse
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ApiError("외부 MCP 연결 주소는 유효한 HTTP(S) URL이어야 합니다.", 503)
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ApiError("원격 외부 MCP는 HTTPS 연결만 허용합니다.", 403)
    return endpoint


def _decode_mcp_response(raw: bytes) -> dict:
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return {}
    candidates = []
    for line in text.splitlines():
        if line.startswith("data:"):
            candidates.append(line[5:].strip())
    candidate = candidates[-1] if candidates else text
    try:
        result = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise ApiError("외부 MCP가 JSON-RPC 응답을 반환하지 않았습니다.", 502) from error
    if isinstance(result, dict) and result.get("error"):
        detail = result["error"]
        raise ApiError("외부 MCP 오류: " + str(detail.get("message") if isinstance(detail, dict) else detail), 502)
    return result if isinstance(result, dict) else {}


def _external_mcp_post(endpoint: str, message: dict, session_id: str = "", token: str = "") -> tuple[dict, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-03-26",
        "User-Agent": "AIWorks-MCP-Gateway/0.27",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    if token:
        headers["Authorization"] = "Bearer " + token
    request = url_request.Request(endpoint, data=_json(message).encode("utf-8"), headers=headers, method="POST")
    try:
        with url_request.urlopen(request, timeout=20) as response:
            payload = _decode_mcp_response(response.read())
            return payload, str(response.headers.get("Mcp-Session-Id") or session_id)
    except url_error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise ApiError(f"외부 MCP HTTP {error.code}: {detail or error.reason}", 502) from error
    except (url_error.URLError, TimeoutError, OSError) as error:
        raise ApiError("외부 MCP에 연결하지 못했습니다: " + str(error), 503) from error


def _stdio_mcp_response(process: subprocess.Popen, request_id: str, timeout: float = 25.0) -> dict:
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            ready = selector.select(max(0.05, min(0.5, deadline - time.monotonic())))
            if not ready:
                if process.poll() is not None:
                    break
                continue
            line = process.stdout.readline()
            if not line:
                break
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(message.get("id")) != str(request_id):
                continue
            if message.get("error"):
                detail = message["error"]
                raise ApiError("로컬 MCP 오류: " + str(detail.get("message") if isinstance(detail, dict) else detail), 502)
            return message
    finally:
        selector.close()
    detail = ""
    if process.poll() is not None and process.stderr:
        detail = process.stderr.read()[-500:].strip()
    raise ApiError("로컬 MCP가 제한 시간 안에 JSON-RPC 응답을 반환하지 않았습니다." + ((" " + detail) if detail else ""), 504)


def _stdio_mcp_exchange(connector: dict, *, tool_arguments: dict | None = None, workspace_root: Path | None = None) -> dict:
    profile_id = str(connector.get("serverProfile") or "")
    profile = EXTERNAL_MCP_SERVER_PROFILES.get(profile_id)
    if not profile:
        raise ApiError("승인되지 않은 로컬 MCP 서버 프로필입니다.", 403)
    tool_name = str(connector.get("toolName") or "")
    if tool_name not in profile["allowedTools"]:
        raise ApiError("서버 프로필에서 허용되지 않은 MCP 도구입니다.", 403)
    status = _external_profile_status(profile_id)
    if not status["available"]:
        raise ApiError(f"{profile['name']} 런타임이 설치되지 않았습니다. 고정 버전 {profile_id} 로컬 런타임을 설치해 주세요.", 503)
    if os.getenv("AIWORKS_LOCAL_MCP_LIVE", "1").strip() != "1":
        raise ApiError("로컬 MCP 실행이 비활성화되어 있습니다. AIWORKS_LOCAL_MCP_LIVE=1을 설정해 주세요.", 503)
    owned_workspace = None
    if workspace_root is None:
        owned_workspace = tempfile.TemporaryDirectory(prefix="aiworks-mcp-")
        workspace_root = Path(owned_workspace.name)
    workspace_root = workspace_root.resolve()
    safe_env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin:" + os.getenv("PATH", ""),
        "LANG": os.getenv("LANG", "C.UTF-8"),
        "LC_ALL": os.getenv("LC_ALL", "C.UTF-8"),
        "HOME": str(workspace_root),
        "TMPDIR": str(workspace_root),
        "KORDOC_ROOT": str(workspace_root),
        "KORDOC_OFFLINE": "1",
    }
    process = None
    try:
        process = subprocess.Popen(
            [str(profile["binary"]), *profile["args"]],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=str(workspace_root),
            env=safe_env,
            bufsize=1,
        )

        def call(method: str, params: dict, *, notification: bool = False) -> dict:
            request_id = uuid.uuid4().hex
            message = {"jsonrpc": "2.0", "method": method, "params": params}
            if not notification:
                message["id"] = request_id
            process.stdin.write(_json(message) + "\n")
            process.stdin.flush()
            return {} if notification else _stdio_mcp_response(process, request_id)

        initialized = call(
            "initialize",
            {
                "protocolVersion": str(connector.get("contractVersion") or "2025-03-26"),
                "capabilities": {},
                "clientInfo": {"name": "AIWorks", "version": "0.30.0"},
            },
        )
        negotiated = ((initialized.get("result") or {}).get("protocolVersion") if isinstance(initialized.get("result"), dict) else None)
        call("notifications/initialized", {}, notification=True)
        if tool_arguments is None:
            listed = call("tools/list", {})
            tools = ((listed.get("result") or {}).get("tools") if isinstance(listed.get("result"), dict) else []) or []
            return {"connected": True, "serverProfile": profile_id, "protocolVersion": negotiated, "tools": tools, "runtime": status}
        called = call("tools/call", {"name": tool_name, "arguments": tool_arguments})
        result = called.get("result") if isinstance(called.get("result"), dict) else {}
        if result.get("isError"):
            message = next((str(item.get("text") or "") for item in result.get("content") or [] if isinstance(item, dict)), "도구 실행 실패")
            raise ApiError("로컬 MCP 도구 실행이 실패했습니다: " + message[:500], 502)
        return {"connected": True, "serverProfile": profile_id, "protocolVersion": negotiated, "result": result, "runtime": status}
    except OSError as error:
        raise ApiError("로컬 MCP 프로세스를 시작하지 못했습니다: " + str(error), 503) from error
    finally:
        if process is not None:
            if process.stdin:
                process.stdin.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()
        if owned_workspace is not None:
            owned_workspace.cleanup()


def _external_mcp_exchange(connector: dict, *, tool_arguments: dict | None = None, workspace_root: Path | None = None) -> dict:
    if connector.get("transport") == "stdio":
        return _stdio_mcp_exchange(connector, tool_arguments=tool_arguments, workspace_root=workspace_root)
    if os.getenv("AIWORKS_EXTERNAL_MCP_LIVE", "0").strip() != "1":
        raise ApiError("외부 MCP 실연동이 비활성화되어 있습니다. AIWORKS_EXTERNAL_MCP_LIVE=1 설정 후 다시 시도해 주세요.", 503)
    endpoint = _external_mcp_endpoint(connector)
    token_env = str(connector.get("authTokenEnv") or "AIWORKS_EXTERNAL_MCP_TOKEN").strip()
    token = str(os.getenv(token_env, "")).strip()
    request_id = uuid.uuid4().hex
    initialized, session_id = _external_mcp_post(
        endpoint,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": str(connector.get("contractVersion") or "2025-03-26"),
                "capabilities": {},
                "clientInfo": {"name": "AIWorks", "version": "0.30.0"},
            },
        },
        token=token,
    )
    negotiated = ((initialized.get("result") or {}).get("protocolVersion") if isinstance(initialized.get("result"), dict) else None)
    _external_mcp_post(endpoint, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id, token)
    if tool_arguments is None:
        listed, _ = _external_mcp_post(endpoint, {"jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "tools/list", "params": {}}, session_id, token)
        tools = ((listed.get("result") or {}).get("tools") if isinstance(listed.get("result"), dict) else []) or []
        return {"connected": True, "endpointEnv": connector.get("endpointEnv"), "protocolVersion": negotiated, "tools": tools}
    called, _ = _external_mcp_post(
        endpoint,
        {
            "jsonrpc": "2.0",
            "id": uuid.uuid4().hex,
            "method": "tools/call",
            "params": {"name": connector["toolName"], "arguments": tool_arguments},
        },
        session_id,
        token,
    )
    result = called.get("result") if isinstance(called.get("result"), dict) else {}
    if result.get("isError"):
        raise ApiError("외부 MCP 도구 실행이 실패했습니다.", 502)
    return {"connected": True, "protocolVersion": negotiated, "result": result}


def probe_external_mcp_draft(draft_id: str, payload: dict) -> dict:
    draft = get_mcp_draft(draft_id)
    if draft["manifest"].get("mcpType") != "external":
        raise ApiError("외부 MCP 연결 초안에서만 연결 테스트를 실행할 수 있습니다.", 409)
    connector = draft["manifest"].get("externalMcp") or {}
    if connector.get("transport") == "stdio":
        profile_id = str(connector.get("serverProfile") or "")
        status = _external_profile_status(profile_id)
        if not status["available"]:
            return {"connected": False, "serverProfile": profile_id, "toolName": connector.get("toolName"), "reason": status["reason"], "runtime": status}
        result = _external_mcp_exchange(connector)
        names = [str(item.get("name") or "") for item in result.get("tools") or [] if isinstance(item, dict)]
        result["configuredToolFound"] = str(connector.get("toolName") or "") in names
        result["configuredToolName"] = connector.get("toolName")
        return result
    endpoint_env = str(connector.get("endpointEnv") or "")
    if not os.getenv(endpoint_env, "").strip():
        return {"connected": False, "endpointEnv": endpoint_env, "toolName": connector.get("toolName"), "reason": "endpoint-not-configured"}
    result = _external_mcp_exchange(connector)
    names = [str(item.get("name") or "") for item in result.get("tools") or [] if isinstance(item, dict)]
    result["configuredToolFound"] = str(connector.get("toolName") or "") in names
    result["configuredToolName"] = connector.get("toolName")
    return result


def _json_path_value(value, path: str):
    current = value
    for part in [item for item in str(path or "").split(".") if item]:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _installed_loopback_formatter() -> dict | None:
    from urllib.parse import urlparse
    ensure_schema()
    with _connect() as db:
        rows = db.execute(
            """
            SELECT p.*
             FROM mcp_installations i
              JOIN mcp_packages p ON p.package_id=i.package_id AND p.version=i.pinned_version
             WHERE i.status='active'
             ORDER BY CASE WHEN p.package_id='integration.kordoc' THEN 0 ELSE 1 END,
                      p.package_id
            """
        ).fetchall()
    for row in rows:
        manifest = _load_json(row["manifest_json"], {})
        if manifest.get("mcpType") != "external" or "document.hwpx.finalize" not in (manifest.get("capabilities") or []):
            continue
        connector = manifest.get("externalMcp") or {}
        if connector.get("transport") == "stdio":
            if os.getenv("AIWORKS_LOCAL_MCP_LIVE", "1").strip() != "1":
                continue
            if not _external_profile_status(str(connector.get("serverProfile") or ""))["available"]:
                continue
        else:
            if os.getenv("AIWORKS_EXTERNAL_MCP_LIVE", "0").strip() != "1":
                continue
            endpoint = str(os.getenv(str(connector.get("endpointEnv") or ""), "")).strip()
            parsed = urlparse(endpoint)
            if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                continue
        return {
            "packageId": row["package_id"],
            "version": row["version"],
            "packageRef": row["package_id"] + "@" + row["version"],
            "capabilityId": "document.hwpx.finalize",
            "permissions": [item["scope"] for item in manifest.get("permissions") or []],
            "connector": connector,
        }
    return None


def _external_result_payload(tool_result: dict) -> dict:
    if isinstance(tool_result.get("structuredContent"), dict):
        return tool_result["structuredContent"]
    for block in tool_result.get("content") or []:
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        try:
            value = json.loads(str(block.get("text") or ""))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return tool_result


def _artifact_markdown(artifact: dict) -> str:
    report_document = artifact.get("reportDocument")
    if isinstance(report_document, dict):
        normalized = str(report_document.get("normalizedMarkdown") or "").strip()
        if normalized:
            return normalized
    title = str(artifact.get("title") or Path(str(artifact.get("filename") or "AIWorks 보고서")).stem).strip()
    content = str(artifact.get("content") or "").strip()
    if not content and artifact.get("contentBase64"):
        try:
            data = base64.b64decode(str(artifact["contentBase64"]), validate=True)
            parsed = parse_hwpx(data, str(artifact.get("filename") or "report.hwpx"))
            paragraphs = [str(item.get("text") or "").strip() for item in parsed.get("paragraphs") or []]
            content = "\n\n".join(item for item in paragraphs if item and item != title)
        except (ApiError, ValueError, TypeError):
            content = ""
    if not content:
        raise ApiError("KODAK에 전달할 보고서 본문을 추출하지 못했습니다.", 422)
    return ("# " + title + "\n\n" + content).strip()


def _run_external_document_transform(connector: dict, artifact: dict, intent: str) -> tuple[bytes, str, dict]:
    if connector.get("transport") == "stdio":
        if connector.get("invocationAdapter") != "markdown-output-hwpx" or connector.get("toolName") != "generate_document":
            raise ApiError("현재 자동 보고서 후처리는 stdio MCP의 markdown-output-hwpx 어댑터를 지원합니다.", 409)
        with tempfile.TemporaryDirectory(prefix="aiworks-kordoc-") as temporary:
            workspace = Path(temporary).resolve()
            safe_stem = re.sub(r'[^0-9A-Za-z가-힣._-]+', "_", Path(str(artifact.get("filename") or "AIWorks_보고서.hwpx")).stem)[:70] or "AIWorks_보고서"
            output_path = workspace / (safe_stem + "_KODAK.hwpx")
            template = artifact.get("template") if isinstance(artifact.get("template"), dict) else {}
            renderer_options = template.get("rendererOptions") if isinstance(template.get("rendererOptions"), dict) else {}
            arguments = {
                "markdown": _artifact_markdown(artifact),
                "output_path": str(output_path),
                "preset": str(renderer_options.get("preset") or connector.get("preset") or "보고서"),
            }
            exchange = _external_mcp_exchange(connector, tool_arguments=arguments, workspace_root=workspace)
            if not output_path.is_file():
                raise ApiError("KODAK이 성공 응답을 반환했지만 HWPX 출력 파일을 만들지 않았습니다.", 502)
            data = output_path.read_bytes()
            if len(data) > MAX_HWPX_BYTES:
                raise ApiError("KODAK HWPX 결과가 허용 크기를 초과했습니다.", 413)
            parse_hwpx(data, output_path.name)
            return data, output_path.name, exchange
    input_map = connector.get("inputMap") or {}
    arguments = {
        str(input_map.get("filename") or "filename"): artifact["filename"],
        str(input_map.get("contentBase64") or "contentBase64"): artifact["contentBase64"],
        str(input_map.get("instruction") or "instruction"): intent,
    }
    exchange = _external_mcp_exchange(connector, tool_arguments=arguments)
    payload = _external_result_payload(exchange.get("result") or {})
    encoded = _json_path_value(payload, str(connector.get("outputContentPath") or "contentBase64"))
    filename = _json_path_value(payload, str(connector.get("outputFilenamePath") or "filename"))
    try:
        data = base64.b64decode(str(encoded or ""), validate=True)
    except (ValueError, TypeError) as error:
        raise ApiError("외부 MCP 결과의 HWPX base64 출력 매핑이 올바르지 않습니다.", 502) from error
    output_filename = str(filename or artifact["filename"])
    if Path(output_filename).suffix.lower() != ".hwpx":
        output_filename = str(Path(output_filename).with_suffix(".hwpx"))
    parse_hwpx(data, output_filename)
    return data, output_filename, exchange


def _finalize_report_with_loopback_mcp(artifact: dict, intent: str) -> tuple[dict, dict | None]:
    formatter = _installed_loopback_formatter()
    if not formatter:
        return artifact, None
    connector = formatter["connector"]
    data, output_filename, exchange = _run_external_document_transform(connector, artifact, intent)
    return {
        **artifact,
        "filename": output_filename,
        "contentBase64": base64.b64encode(data).decode("ascii"),
        "generatedBy": [*(artifact.get("generatedBy") or []), formatter["packageRef"]],
        "externalFormatter": {"packageRef": formatter["packageRef"], "toolName": connector.get("toolName"), "transport": connector.get("transport"), "serverProfile": connector.get("serverProfile"), "protocolVersion": exchange.get("protocolVersion")},
    }, formatter


def _execute_builder_binding(
    binding: dict,
    intent: str,
    input_context: dict,
    route: dict,
    live_model_enabled: bool,
    model_required: bool = False,
    additional_bindings: list[dict] | None = None,
) -> dict:
    package = _installed_builder_package(binding)
    manifest = package["manifest"]
    guide = manifest.get("builderGuide") or {}
    references = _builder_runtime_references(package)
    package_ref = package["packageId"] + "@" + package["version"]
    additional_bindings = list(additional_bindings or [])
    workflow = {
        "id": "dynamic." + package["packageId"],
        "dynamic": True,
        "responseType": "context-answer",
        "loadedMcps": [package_ref],
        "capabilityBindings": [binding, *additional_bindings],
        "pipeline": [str(item) for item in guide.get("procedure") or []],
    }
    source_records = [
        {"documentId": package_ref, "locator": item["filename"], "sha256": item["sha256"], "role": item["role"]}
        for item in references
    ]
    model_id = (route.get("model") or {}).get("id", "upstage/solar-pro-3")
    model = {
        "provider": "local",
        "name": package_ref,
        "externalTransfer": False,
        "mode": "builder-composite",
    }
    permissions = {item["scope"] for item in manifest.get("permissions") or []}
    if manifest.get("mcpType") == "external":
        connector = manifest.get("externalMcp") or {}
        session_id = str(input_context.get("document_id") or "")
        if not session_id.startswith("docsession_"):
            raise ApiError("외부 MCP로 변환할 현재 HWPX 보고서를 먼저 열어 주세요.", 409)
        session = get_native_document_session(session_id, include_artifact=True)
        artifact, output_filename, exchange = _run_external_document_transform(
            connector,
            {
                "title": (session.get("document") or {}).get("title") or Path(session["filename"]).stem,
                "filename": session["filename"],
                "contentBase64": session["contentBase64"],
            },
            intent,
        )
        external_transfer = bool(connector.get("documentTransfer"))
        workflow["responseType"] = "template-transform"
        workflow["pipeline"] = ["현재 보고서 읽기", "외부 MCP 도구 호출", "HWPX 무결성 검사", "RHWP 편집"]
        model.update({"name": package_ref, "mode": "external-mcp", "provider": "external-mcp", "externalTransfer": external_transfer, "protocolVersion": exchange.get("protocolVersion")})
        return {
            "responseType": "template-transform",
            "artifact": {
                "title": (session.get("document") or {}).get("title") or Path(session["filename"]).stem,
                "filename": output_filename,
                "format": "hwpx",
                "mediaType": "application/hwp+zip",
                "contentBase64": base64.b64encode(artifact).decode("ascii"),
                "editorMcp": "document.rhwp@1.0.0",
                "applyMode": "replace-current-session",
                "externalMcp": {"packageRef": package_ref, "toolName": connector.get("toolName"), "transport": connector.get("transport"), "serverProfile": connector.get("serverProfile"), "endpointEnv": connector.get("endpointEnv")},
            },
            "workflow": workflow,
            "loadedMcps": [package_ref, "document.rhwp@1.0.0"],
            "sources": source_records,
            "model": model,
            "policy": {"personalDataDetected": False, "maskedFields": [], "externalTransfer": external_transfer},
        }
    if manifest.get("mcpType") == "data":
        chunks = _package_rag_chunks(package["packageId"], package["version"])
        top_k = int((manifest.get("retrieval") or {}).get("topK") or 5)
        hits = _search_rag_chunks(chunks, intent, limit=top_k)
        make_data_report = any(term in intent for term in ("보고서", "문서", "초안", "작성"))
        use_live_model = bool(hits) and live_model_enabled and (
            model_required or (bool(guide.get("useModel")) and "network.send" in permissions)
        )
        live_synthesis_succeeded = False
        if use_live_model:
            try:
                live = _chat_with_route_fallback(
                    route,
                    _rag_runtime_messages(manifest, intent, hits, input_context.get("project_fact_snapshot"), input_context.get("project_markdown_context"), input_context.get("project_markdown_prompt_allowed") is True),
                    max_tokens=1_000,
                    primary_model_id=model_id,
                )
                answer = _validate_rag_synthesis(intent, live["content"], hits)
                quality_review = _review_report_against_request(intent, answer, hits) if make_data_report else None
                if quality_review and not quality_review["passed"]:
                    repair_messages = _rag_runtime_messages(manifest, intent, hits, input_context.get("project_fact_snapshot"), input_context.get("project_markdown_context"), input_context.get("project_markdown_prompt_allowed") is True)
                    repair_messages.extend([
                        {"role": "assistant", "content": answer},
                        {"role": "user", "content": "품질 검증에서 다음 문제가 발견되었습니다. 원 질문과 검색 근거를 다시 대조하여 Markdown 전체를 한 번만 다시 작성하세요.\n- " + "\n- ".join(quality_review["issues"])},
                    ])
                    repaired = _chat_with_route_fallback(route, repair_messages, max_tokens=1_000, primary_model_id=live.get("requestedModel") or model_id)
                    answer = _validate_rag_synthesis(intent, repaired["content"], hits)
                    quality_review = _review_report_against_request(intent, answer, hits)
                    if not quality_review["passed"]:
                        raise ApiError("보고서 품질 하네스를 통과하지 못했습니다: " + "; ".join(quality_review["issues"]), 422)
                    live = repaired
                    quality_review["repaired"] = True
                live_synthesis_succeeded = True
                model.update({"provider": str((route.get("model") or {}).get("provider") or "upstage"), "name": live.get("requestedModel") or model_id, "mode": "rag-live-fallback" if live.get("fallbackUsed") else "rag-live", "externalTransfer": True, "resolvedModel": live["resolvedModel"], "usage": live["usage"], "requestId": live["requestId"], "fallbackUsed": bool(live.get("fallbackUsed")), "fallbackFrom": live.get("fallbackFrom"), "fallbackReason": live.get("fallbackReason")})
            except ApiError as error:
                if not _is_transient_model_error(error):
                    raise
                answer = _rag_extract_answer(intent, hits)
                model.update({"provider": "local", "name": package_ref, "mode": "rag-local-after-solar-timeout", "externalTransfer": True, "retrievedChunks": len(hits), "synthesisError": str(error)[:1_000]})
        elif not make_data_report and hits and os.getenv("AIWORKS_LOCAL_RAG_LLM", "0").strip() != "0":
            try:
                local = _ollama_chat(_rag_runtime_messages(manifest, intent, hits, input_context.get("project_fact_snapshot"), input_context.get("project_markdown_context"), True), max_tokens=320)
                answer = _validate_rag_synthesis(intent, local["content"], hits)
                model.update({"provider": "ollama", "name": local["resolvedModel"], "mode": "rag-local-llm", "externalTransfer": False, "usage": local["usage"], "requestId": local["requestId"], "retrievedChunks": len(hits)})
            except ApiError as error:
                answer = "관련 근거는 찾았지만 로컬 LLM이 제한 시간 안에 종합하지 못했습니다. 청크 원문을 답변으로 대신 표시하지 않았습니다. 잠시 후 다시 시도해 주세요. (" + str(error) + ")"
                model.update({"mode": "rag-local-fallback", "retrievedChunks": len(hits), "synthesisError": str(error)})
        else:
            answer = _rag_extract_answer(intent, hits)
            model.update({"mode": "rag-local-evidence", "retrievedChunks": len(hits)})
        source_records = [
            {
                "documentId": package_ref,
                "referenceId": item["referenceId"],
                "locator": item["filename"] + (f" · {item['pageNumber']}쪽" if item.get("pageNumber") else ""),
                "sha256": item["sha256"],
                "role": "data-source",
                "excerpt": str(item.get("content") or "")[:500],
                "score": int(item.get("score") or 0),
            }
            for item in hits
        ]
        workflow.update(
            {
                "responseType": "report-artifact" if make_data_report else "context-answer",
                "retrieval": {"kind": "local-rag", "indexedChunks": len(chunks), "retrievedChunks": len(hits), "topK": top_k},
            }
        )
        if make_data_report:
            artifact = _rag_report_artifact(intent, hits, package_ref, answer if live_synthesis_succeeded else "", input_context.get("project_fact_snapshot"))
            artifact["qualityReview"] = _review_report_against_request(intent, artifact.get("content") or "", hits)
            template_binding = next((item for item in additional_bindings if item.get("mcpType") == "template"), None)
            if template_binding:
                artifact, applied_template_ref = _apply_template_binding_to_artifact(template_binding, artifact)
                formatter = None
            else:
                artifact, formatter = _finalize_report_with_loopback_mcp(artifact, intent)
                applied_template_ref = ""
            loaded_mcps = [package_ref, "document.markdown@1.0.0", "document.report-structure@0.1.0", "document.quality-harness@0.1.0", "template.report-style@0.1.0", "document.report-hwpx@0.1.0"]
            if use_live_model:
                loaded_mcps.insert(0, "core.model-management@0.1.0")
            if formatter:
                loaded_mcps.append(formatter["packageRef"])
            if applied_template_ref:
                loaded_mcps.append(applied_template_ref)
            loaded_mcps.append("document.rhwp@1.0.0")
            workflow["loadedMcps"] = loaded_mcps
            return {
                "responseType": "report-artifact",
                "artifact": artifact,
                "workflow": workflow,
                "loadedMcps": loaded_mcps,
                "sources": source_records,
                "model": model,
                "policy": {"personalDataDetected": False, "maskedFields": []},
            }
        return {
            "responseType": "context-answer",
            "answer": answer,
            "workflow": workflow,
            "loadedMcps": [package_ref],
            "sources": source_records,
            "model": model,
            "policy": {"personalDataDetected": False, "maskedFields": []},
        }
    if manifest.get("mcpType") == "template":
        template_reference = next((item for item in references if item["role"] == "template-source"), None)
        if not template_reference:
            raise ApiError("설치된 양식 MCP에 양식 원본이 없습니다.", 409)
        if not template_reference["filename"].lower().endswith(".hwpx"):
            raise ApiError("현재 동적 양식 실행기는 편집 가능한 HWPX 양식을 지원합니다.", 415)
        session_id = str(input_context.get("document_id") or "")
        if not session_id.startswith("docsession_"):
            raise ApiError("양식을 적용할 프로젝트 Markdown 문서가 연결된 편집 세션을 먼저 열어 주세요.", 409)
        session = get_native_document_session(session_id, include_artifact=True)
        markdown_document_id = str(session.get("markdownDocumentId") or "")
        if markdown_document_id:
            markdown_document = get_project_markdown_document(str(session.get("projectId") or DEFAULT_PROJECT_ID), markdown_document_id)
            source_markdown = markdown_document["markdown"]
            report_title = markdown_document["title"]
        else:
            source_hwpx_bytes = base64.b64decode(session["contentBase64"], validate=True)
            converted = hwpx_to_markdown(parse_hwpx(source_hwpx_bytes, session["filename"]), session["filename"])
            source_markdown = converted["markdown"]
            report_title = converted["title"]
            markdown_document = None
        structured = _build_structured_report_artifact(
            report_title,
            source_markdown,
            intent,
            fact_snapshot=input_context.get("project_fact_snapshot"),
            generated_by=["document.markdown@1.0.0", package_ref],
        )
        source_hwpx = base64.b64decode(structured["contentBase64"], validate=True)
        artifact, template_metadata = _apply_builder_hwpx_template(
            template_reference["content"],
            source_hwpx,
            session["filename"],
            {**guide, "templateName": manifest.get("name")},
            structured.get("reportDocument") or {},
        )
        safe_name = re.sub(r'[^0-9A-Za-z가-힣._-]+', "_", str(manifest.get("name") or "등록양식"))[:60]
        workflow["responseType"] = "template-transform"
        return {
            "responseType": "template-transform",
            "artifact": {
                "title": report_title,
                "filename": (Path(session["filename"]).stem[:60] or "AIWorks") + "_" + safe_name + ".hwpx",
                "format": "hwpx",
                "mediaType": "application/hwp+zip",
                "contentBase64": base64.b64encode(artifact).decode("ascii"),
                "editorMcp": "document.rhwp@1.0.0",
                "applyMode": "replace-current-session",
                "content": structured["content"],
                "reportDocument": structured["reportDocument"],
                "markdownDocument": ({"id": markdown_document["id"], "versionId": markdown_document["versionId"], "revision": markdown_document["revision"], "markdownSha256": markdown_document["markdownSha256"], "projectId": markdown_document["projectId"], "sourceOfTruth": True} if markdown_document else None),
                "derivedOutput": {"format": "hwpx", "renderer": package_ref, "derivedFromMarkdownVersion": markdown_document["versionId"] if markdown_document else None},
                "template": {**template_metadata, "packageRef": package_ref, "source": template_reference["filename"]},
            },
            "workflow": workflow,
            "loadedMcps": [package_ref],
            "sources": source_records,
            "model": model,
            "policy": {"personalDataDetected": False, "maskedFields": []},
        }
    use_live_model = live_model_enabled and (
        model_required or (bool(guide.get("useModel")) and "network.send" in permissions)
    )
    if use_live_model:
        live = _chat_with_route_fallback(route, _builder_runtime_messages(manifest, intent, input_context, references), max_tokens=900, primary_model_id=model_id)
        answer = str(live["content"]).strip()
        model.update({"provider": str((route.get("model") or {}).get("provider") or "upstage"), "name": live.get("requestedModel") or model_id, "mode": "live-fallback" if live.get("fallbackUsed") else "live", "externalTransfer": True, "resolvedModel": live["resolvedModel"], "usage": live["usage"], "requestId": live["requestId"], "fallbackUsed": bool(live.get("fallbackUsed")), "fallbackFrom": live.get("fallbackFrom"), "fallbackReason": live.get("fallbackReason")})
    else:
        procedure = guide.get("procedure") or []
        excerpts = [item["excerpt"].strip() for item in references if item.get("excerpt")]
        answer = "\n".join(
            [
                str(manifest.get("name") or package["packageId"]) + " 실행 결과",
                "요청: " + intent,
                *("- " + item for item in procedure),
                *("참고: " + item[:1_000] for item in excerpts[:2]),
            ]
        )
    selection = str(input_context.get("selection") or "").strip()
    if selection and "document.write" in permissions and use_live_model:
        replacement = REWRITE_OUTPUT_MCP.clean(answer)
        workflow["responseType"] = "selection-edit"
        return {
            "responseType": "selection-edit",
            "patches": [{"op": "replace", "target": input_context.get("selection_id") or "document.selection", "before": selection, "after": replacement}],
            "workflow": workflow,
            "loadedMcps": [package_ref],
            "sources": source_records,
            "model": model,
            "policy": {"personalDataDetected": False, "maskedFields": []},
        }
    make_report = "artifact.process" in (manifest.get("capabilities") or []) and any(term in intent for term in ("보고서", "문서", "작성"))
    if make_report:
        report_title = str(manifest.get("name") or "AIWorks 파생 보고서").removesuffix(" MCP")
        report_artifact = _build_structured_report_artifact(
            report_title,
            answer,
            intent,
            fact_snapshot=input_context.get("project_fact_snapshot"),
            generated_by=[package_ref],
        )
        report_artifact, formatter = _finalize_report_with_loopback_mcp(report_artifact, intent)
        loaded_mcps = [package_ref, "document.markdown@1.0.0", "document.report-structure@0.1.0", "template.report-style@0.1.0", "document.report-hwpx@0.1.0"]
        if formatter:
            loaded_mcps.append(formatter["packageRef"])
        loaded_mcps.append("document.rhwp@1.0.0")
        workflow["responseType"] = "report-artifact"
        workflow["loadedMcps"] = loaded_mcps
        return {
            "responseType": "report-artifact",
            "artifact": report_artifact,
            "workflow": workflow,
            "loadedMcps": loaded_mcps,
            "sources": source_records,
            "model": model,
            "policy": {"personalDataDetected": False, "maskedFields": []},
        }
    return {"responseType": "text-answer", "answer": answer, "workflow": workflow, "loadedMcps": [package_ref], "sources": source_records, "model": model, "policy": {"personalDataDetected": False, "maskedFields": []}}



_WORKFLOW_RUNTIME_STEPS = (
    ("context", "프로젝트 문맥·권한 범위 확정"),
    ("execute", "MCP·모델 실행"),
    ("persist", "Markdown·메타정보·파생 산출물 저장"),
)


def _workflow_safe_payload(value, depth: int = 0):
    """Bound persisted workflow diagnostics and avoid duplicating binary payloads."""
    if depth > 5:
        return "[depth-limited]"
    if isinstance(value, dict):
        result = {}
        for key, item in list(value.items())[:60]:
            key_text = str(key)
            if key_text.lower() in {"contentbase64", "content_base64", "artifact_blob", "content_blob"}:
                raw = str(item or "")
                result[key_text] = {"omitted": True, "characters": len(raw), "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()}
            else:
                result[key_text] = _workflow_safe_payload(item, depth + 1)
        return result
    if isinstance(value, list):
        return [_workflow_safe_payload(item, depth + 1) for item in value[:40]]
    if isinstance(value, str):
        return value if len(value) <= 4_000 else value[:4_000] + "…[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:4_000]


def _create_workflow_run(db: sqlite3.Connection, execution_id: str, plan_id: str, input_context: dict) -> str:
    run_id = "wfrun_" + uuid.uuid4().hex
    now = utc_now()
    resume = input_context.get("_workflow_resume") if isinstance(input_context.get("_workflow_resume"), dict) else {}
    db.execute(
        "INSERT INTO workflow_runs(id,execution_id,plan_id,status,current_step_key,input_json,output_json,checkpoint_json,resumed_from_run_id,resume_step_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            run_id, execution_id, plan_id, "running", "context", _json(_workflow_safe_payload(input_context)),
            "{}", _json(_workflow_safe_payload(resume.get("checkpoint") or {})),
            str(resume.get("runId") or "") or None, str(resume.get("stepKey") or "") or None, now, now,
        ),
    )
    db.execute(
        "INSERT INTO workflow_run_executions(workflow_run_id,execution_id,plan_id,attempt,created_at) VALUES(?,?,?,?,?)",
        (run_id, execution_id, plan_id, 1, now),
    )
    for step_key, label in _WORKFLOW_RUNTIME_STEPS:
        db.execute(
            "INSERT INTO workflow_step_runs(id,workflow_run_id,step_key,label,status,attempt,input_json,output_json,checkpoint_json,started_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                "wfstep_" + uuid.uuid4().hex,
                run_id,
                step_key,
                label,
                "running" if step_key == "context" else "pending",
                1,
                _json(_workflow_safe_payload(input_context) if step_key == "context" else {}),
                "{}",
                "{}",
                now if step_key == "context" else None,
            ),
        )
    return run_id


def _resume_workflow_run(db: sqlite3.Connection, run_id: str, execution_id: str, plan_id: str, input_context: dict) -> str:
    run = db.execute("SELECT * FROM workflow_runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        raise ApiError("재개할 Workflow Run을 찾을 수 없습니다.", 404)
    if run["status"] != "failed":
        raise ApiError("실패한 Workflow Run만 같은 Run에서 재개할 수 있습니다.", 409)
    attempt = int(db.execute("SELECT COALESCE(MAX(attempt),0) AS value FROM workflow_step_runs WHERE workflow_run_id=?", (run_id,)).fetchone()["value"]) + 1
    resume = input_context.get("_workflow_resume") if isinstance(input_context.get("_workflow_resume"), dict) else {}
    resume_step = str(resume.get("stepKey") or run["current_step_key"] or "execute")
    now = utc_now()
    db.execute(
        "UPDATE workflow_runs SET plan_id=?,status='running',current_step_key='context',input_json=?,output_json='{}',resumed_from_run_id=?,resume_step_key=?,error=NULL,updated_at=?,completed_at=NULL WHERE id=?",
        (plan_id, _json(_workflow_safe_payload(input_context)), run_id, resume_step, now, run_id),
    )
    db.execute(
        "INSERT INTO workflow_run_executions(workflow_run_id,execution_id,plan_id,attempt,created_at) VALUES(?,?,?,?,?)",
        (run_id, execution_id, plan_id, attempt, now),
    )
    for step_key, label in _WORKFLOW_RUNTIME_STEPS:
        db.execute(
            "INSERT INTO workflow_step_runs(id,workflow_run_id,step_key,label,status,attempt,input_json,output_json,checkpoint_json,started_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("wfstep_" + uuid.uuid4().hex, run_id, step_key, label, "running" if step_key == "context" else "pending", attempt, _json(_workflow_safe_payload(input_context) if step_key == "context" else {}), "{}", _json(_workflow_safe_payload(resume.get("checkpoint") or {})), now if step_key == "context" else None),
        )
    _audit(db, "sandbox-executor", "workflow.resumed_in_place", {"workflow_run_id": run_id, "attempt": attempt, "resume_step_key": resume_step}, plan_id=plan_id, execution_id=execution_id)
    return run_id


def _complete_workflow_step(
    db: sqlite3.Connection,
    run_id: str,
    step_key: str,
    output,
    checkpoint: dict | None = None,
    *,
    next_step: str | None = None,
    next_input=None,
) -> None:
    now = utc_now()
    db.execute(
        "UPDATE workflow_step_runs SET status='completed',output_json=?,checkpoint_json=?,completed_at=? WHERE workflow_run_id=? AND step_key=? AND attempt=(SELECT MAX(attempt) FROM workflow_step_runs WHERE workflow_run_id=?)",
        (_json(_workflow_safe_payload(output)), _json(_workflow_safe_payload(checkpoint or {})), now, run_id, step_key, run_id),
    )
    if next_step:
        db.execute(
            "UPDATE workflow_step_runs SET status='running',input_json=?,started_at=? WHERE workflow_run_id=? AND step_key=? AND attempt=(SELECT MAX(attempt) FROM workflow_step_runs WHERE workflow_run_id=?) AND status='pending'",
            (_json(_workflow_safe_payload(next_input or {})), now, run_id, next_step, run_id),
        )
        db.execute(
            "UPDATE workflow_runs SET current_step_key=?,checkpoint_json=?,updated_at=? WHERE id=?",
            (next_step, _json(_workflow_safe_payload(checkpoint or {})), now, run_id),
        )


def _complete_workflow_run(db: sqlite3.Connection, run_id: str, result: dict, checkpoint: dict | None = None) -> None:
    _complete_workflow_step(db, run_id, "persist", {"saved": True, "responseType": result.get("responseType")}, checkpoint)
    now = utc_now()
    db.execute(
        "UPDATE workflow_runs SET status='completed',current_step_key=NULL,output_json=?,checkpoint_json=?,updated_at=?,completed_at=? WHERE id=?",
        (_json(_workflow_safe_payload(result)), _json(_workflow_safe_payload(checkpoint or {})), now, now, run_id),
    )


def _fail_workflow_run(db: sqlite3.Connection, run_id: str, error: Exception) -> None:
    now = utc_now()
    message = str(error)[:4_000]
    db.execute(
        "UPDATE workflow_step_runs SET status='failed',error=?,completed_at=? WHERE workflow_run_id=? AND status='running'",
        (message, now, run_id),
    )
    db.execute(
        "UPDATE workflow_runs SET status='failed',error=?,updated_at=?,completed_at=? WHERE id=?",
        (message, now, now, run_id),
    )


def get_workflow_run(run_id: str) -> dict:
    ensure_schema()
    with _connect() as db:
        run = db.execute("SELECT * FROM workflow_runs WHERE id=?", (run_id,)).fetchone()
        if not run:
            raise ApiError("Workflow Run을 찾을 수 없습니다.", 404)
        steps = db.execute(
            "SELECT * FROM workflow_step_runs WHERE workflow_run_id=? ORDER BY attempt, CASE step_key WHEN 'context' THEN 1 WHEN 'execute' THEN 2 ELSE 3 END",
            (run_id,),
        ).fetchall()
        execution_attempts = db.execute(
            "SELECT * FROM workflow_run_executions WHERE workflow_run_id=? ORDER BY attempt",
            (run_id,),
        ).fetchall()
    return {
        "id": run["id"],
        "executionId": run["execution_id"],
        "planId": run["plan_id"],
        "projectId": run["project_id"],
        "status": run["status"],
        "currentStepKey": run["current_step_key"],
        "input": _load_json(run["input_json"], {}),
        "output": _load_json(run["output_json"], {}),
        "checkpoint": _load_json(run["checkpoint_json"], {}),
        "retryCount": run["retry_count"],
        "resumedFromRunId": run["resumed_from_run_id"],
        "resumeStepKey": run["resume_step_key"],
        "error": run["error"],
        "createdAt": run["created_at"],
        "updatedAt": run["updated_at"],
        "completedAt": run["completed_at"],
        "executionAttempts": [
            {"executionId": item["execution_id"], "planId": item["plan_id"], "attempt": item["attempt"], "createdAt": item["created_at"]}
            for item in execution_attempts
        ],
        "steps": [
            {
                "id": item["id"], "stepKey": item["step_key"], "label": item["label"],
                "status": item["status"], "attempt": item["attempt"],
                "input": _load_json(item["input_json"], {}),
                "output": _load_json(item["output_json"], {}),
                "checkpoint": _load_json(item["checkpoint_json"], {}),
                "error": item["error"], "startedAt": item["started_at"], "completedAt": item["completed_at"],
            }
            for item in steps
        ],
    }



def create_workflow_retry_plan(run_id: str, payload: dict) -> dict:
    ensure_schema()
    with _connect() as db:
        run = db.execute("SELECT * FROM workflow_runs WHERE id=?", (run_id,)).fetchone()
        if not run:
            raise ApiError("Workflow Run을 찾을 수 없습니다.", 404)
        if run["status"] != "failed":
            raise ApiError("실패한 Workflow Run만 재시도 계획을 만들 수 있습니다.", 409)
        original_plan = _plan_row(db, run["plan_id"])
        checkpoint = _load_json(run["checkpoint_json"], {})
        original_context = _load_json(original_plan["document_context_json"], {})
        failed_step = db.execute(
            "SELECT step_key,attempt,input_json,checkpoint_json FROM workflow_step_runs WHERE workflow_run_id=? AND status='failed' ORDER BY attempt DESC,completed_at DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        resume_step_key = str(failed_step["step_key"] if failed_step else run["current_step_key"] or "execute")
        original_context = {
            **original_context,
            "_workflow_resume": {
                "runId": run_id, "stepKey": resume_step_key,
                "attempt": int(failed_step["attempt"]) + 1 if failed_step else 2,
                "checkpoint": checkpoint,
            },
        }
    retry_plan = create_plan({
        "intent": original_plan["intent"],
        "actor": _actor(payload),
        "document_context": original_context,
        "retry_of_workflow_run_id": run_id,
        "resume_checkpoint": checkpoint,
    })
    now = utc_now()
    with _connect() as db:
        db.execute(
            "UPDATE workflow_runs SET retry_count=retry_count+1,checkpoint_json=?,updated_at=? WHERE id=?",
            (_json({**checkpoint, "retryPlanId": retry_plan["id"], "retryPreparedAt": now}), now, run_id),
        )
        _audit(db, _actor(payload), "workflow.retry_plan_created", {
            "workflow_run_id": run_id, "original_plan_id": run["plan_id"], "retry_plan_id": retry_plan["id"],
            "checkpoint": checkpoint,
        }, plan_id=retry_plan["id"], execution_id=run["execution_id"])
    retry_plan["retryOfWorkflowRunId"] = run_id
    retry_plan["resumeCheckpoint"] = checkpoint
    retry_plan["resumeFromStep"] = resume_step_key
    retry_plan["notice"] = "실패 체크포인트를 바탕으로 새 계획을 만들었습니다. 권한 범위를 다시 확인하고 승인해야 실행됩니다."
    return retry_plan


def execute_plan(payload: dict, *, force_local: bool = False) -> dict:
    ensure_schema()
    token = str(payload.get("approval_token") or "")
    claims = _verify_token(token)
    if claims.get("aud") != "aiworks-executor":
        raise ApiError("이 실행기에 사용할 수 없는 승인 토큰입니다.", 403)
    plan_id = str(claims.get("plan_id") or "")
    nonce = str(claims.get("nonce") or "")
    idempotency_key = str(payload.get("idempotency_key") or uuid.uuid4().hex)[:120]
    input_context = payload.get("input") or {}
    if not isinstance(input_context, dict):
        raise ApiError("실행 input은 객체여야 합니다.")
    input_hash = hashlib.sha256(_json(input_context).encode("utf-8")).hexdigest()
    execution_id = "exec_" + uuid.uuid4().hex
    queued_at = utc_now()
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        plan = _plan_row(db, plan_id)
        approval = db.execute("SELECT * FROM approvals WHERE nonce=? AND plan_id=?", (nonce, plan_id)).fetchone()
        if approval is None:
            raise ApiError("승인 기록을 찾을 수 없습니다.", 403)
        if approval["consumed_at"]:
            existing = db.execute(
                "SELECT * FROM executions WHERE plan_id=? AND idempotency_key=?",
                (plan_id, idempotency_key),
            ).fetchone()
            if existing and existing["result_json"]:
                existing_run = db.execute("SELECT workflow_run_id AS id FROM workflow_run_executions WHERE execution_id=?", (existing["id"],)).fetchone()
                return {
                    "id": existing["id"],
                    "planId": plan_id,
                    "workflowRunId": existing_run["id"] if existing_run else None,
                    "status": existing["status"],
                    "result": _load_json(existing["result_json"], {}),
                    "idempotent": True,
                }
            raise ApiError("이미 사용된 승인 토큰입니다.", 409)
        if approval["expires_at"] < int(time.time()):
            raise ApiError("승인 토큰이 만료되었습니다.", 403)
        required = set(_load_json(plan["required_permissions_json"], []))
        granted = set(claims.get("permissions") or [])
        if not required.issubset(granted):
            raise ApiError("승인 토큰의 권한 범위가 부족합니다.", 403)
        db.execute("UPDATE approvals SET consumed_at=? WHERE nonce=?", (queued_at, nonce))
        db.execute(
            """
            INSERT INTO executions(id, plan_id, status, idempotency_key, input_hash, queued_at)
            VALUES(?,?,?,?,?,?)
            """,
            (execution_id, plan_id, "queued", idempotency_key, input_hash, queued_at),
        )
        db.execute("UPDATE plans SET status='running', updated_at=? WHERE id=?", (queued_at, plan_id))
        _audit(
            db,
            str(claims.get("actor") or "user"),
            "execution.queued",
            {"input_hash": input_hash, "external_transfer": False},
            plan_id=plan_id,
            execution_id=execution_id,
        )
        stored_context = _load_json(plan["document_context_json"], {})
        resume_context = stored_context.get("_workflow_resume")
        if isinstance(resume_context, dict):
            input_context = {**input_context, "_workflow_resume": resume_context}
        resume_run_id = str((input_context.get("_workflow_resume") or {}).get("runId") or "") if isinstance(input_context.get("_workflow_resume"), dict) else ""
        if resume_run_id:
            workflow_run_id = _resume_workflow_run(db, resume_run_id, execution_id, plan_id, input_context)
        else:
            workflow_run_id = _create_workflow_run(db, execution_id, plan_id, input_context)
    try:
        started_at = utc_now()
        live_model_enabled = _live_model_execution_enabled() and bool(_upstage_key() or _openrouter_key()) and not force_local and "network.send" in required
        if input_context.get("require_live_model") and not live_model_enabled:
            raise ApiError("실제 LLM 실행이 비활성화되어 있어 선택 문구를 생성하지 않았습니다.", 503)
        with _connect() as db:
            db.execute(
                "UPDATE executions SET status='running', started_at=? WHERE id=? AND status='queued'",
                (started_at, execution_id),
            )
            _audit(
                db,
                "sandbox-executor",
                "execution.started",
                {"runtime": "openrouter" if live_model_enabled else "local", "network": "approved" if live_model_enabled else "denied", "external_transfer": live_model_enabled},
                plan_id=plan_id,
                execution_id=execution_id,
            )
        routing_record = _load_json(plan["routing_json"], {})
        routing = routing_record.get("route", {})
        workflow = routing_record.get("workflow") or WORKSPACE_ORCHESTRATION_MCP.build_workflow(
            plan["intent"], _load_json(plan["document_context_json"], {}), routing
        )
        project_id = _safe_project_id(workflow.get("projectId") or _load_json(plan["document_context_json"], {}).get("project_id"))
        fact_snapshot = workflow.get("factSnapshot")
        if not isinstance(fact_snapshot, dict):
            with _connect() as db:
                fact_snapshot = _project_fact_snapshot(db, project_id)
        markdown_context = workflow.get("markdownContext")
        if not isinstance(markdown_context, list):
            with _connect() as db:
                markdown_context = _project_markdown_context(db, project_id)
        markdown_transfer_approved = input_context.get("project_markdown_transfer_approved") is True
        if live_model_enabled and markdown_context and not markdown_transfer_approved:
            raise ApiError("프로젝트 Markdown 원문을 Solar에 전송하려면 계획에 표시된 문서 범위를 명시적으로 승인해야 합니다.", 403)
        input_context = {
            **input_context,
            "intent": plan["intent"],
            "project_id": project_id,
            "project_fact_snapshot": fact_snapshot,
            "project_markdown_context": markdown_context,
            "project_markdown_prompt_allowed": (not live_model_enabled) or markdown_transfer_approved,
        }
        with _connect() as db:
            db.execute("UPDATE workflow_runs SET project_id=?,updated_at=? WHERE id=?", (project_id, utc_now(), workflow_run_id))
            _complete_workflow_step(
                db,
                workflow_run_id,
                "context",
                {
                    "projectId": project_id,
                    "factCount": len((fact_snapshot or {}).get("facts") or []),
                    "markdownDocuments": len(markdown_context),
                    "liveModelEnabled": live_model_enabled,
                },
                {"workflow": workflow, "routing": routing},
                next_step="execute",
                next_input={"intent": plan["intent"], "capabilityBindings": workflow.get("capabilityBindings") or []},
            )

        capability_bindings = workflow.get("capabilityBindings") or []
        if workflow.get("dynamic") is True and capability_bindings:
            result = _execute_builder_binding(
                capability_bindings[0],
                plan["intent"],
                input_context,
                routing,
                live_model_enabled,
                bool(workflow.get("liveModelRequired")),
                capability_bindings[1:],
            )
            result.setdefault("workflow", workflow)
            result.setdefault("loadedMcps", workflow.get("loadedMcps") or [])
            completed_at = utc_now()
            with _connect() as db:
                _complete_workflow_step(
                    db,
                    workflow_run_id,
                    "execute",
                    {"responseType": result.get("responseType"), "loadedMcps": result.get("loadedMcps") or []},
                    {"dynamic": True, "packageRef": capability_bindings[0]["packageRef"]},
                    next_step="persist",
                    next_input={"projectId": project_id, "responseType": result.get("responseType")},
                )

                _persist_result_markdown(db, project_id, plan_id, execution_id, input_context, result)
                _record_report_fact_snapshot(db, project_id, plan_id, execution_id, result)
                db.execute(
                    "UPDATE executions SET status='completed', result_json=?, completed_at=? WHERE id=?",
                    (_json(result), completed_at, execution_id),
                )
                db.execute("UPDATE plans SET status='completed', updated_at=? WHERE id=?", (completed_at, plan_id))
                _audit(
                    db,
                    "builder-runtime",
                    "execution.completed",
                    {
                        "response_type": result["responseType"],
                        "patches": len(result.get("patches", [])),
                        "sources": len(result.get("sources", [])),
                        "loaded_mcps": result.get("loadedMcps", []),
                        "dynamic": True,
                        "package_ref": capability_bindings[0]["packageRef"],
                    },
                    plan_id=plan_id,
                    execution_id=execution_id,
                )
                _complete_workflow_run(
                    db, workflow_run_id, result, {"executionId": execution_id, "projectId": project_id}
                )
            return {
                "id": execution_id,
                "planId": plan_id,
                "workflowRunId": workflow_run_id,
                "status": "completed",
                "result": result,
                "queuedAt": queued_at,
                "startedAt": started_at,
                "completedAt": completed_at,
            }
        if input_context.get("selection") and not workflow.get("hasSelection"):
            execution_context = {**_load_json(plan["document_context_json"], {}), **input_context, "has_selection": True}
            workflow = WORKSPACE_ORCHESTRATION_MCP.build_workflow(plan["intent"], execution_context, routing)
        generic_live_model_enabled = live_model_enabled and workflow["responseType"] in {
            "text-answer",
            "context-answer",
            "report-artifact",
            "document-transform",
        }
        if live_model_enabled and workflow["responseType"] == "selection-edit":
            model_id = (routing.get("model") or {}).get("id", "")
            selection_text = str(input_context.get("selection") or "")[:4_000]
            live = _chat_with_route_fallback(
                routing,
                [
                    {
                        "role": "system",
                        "content": (
                            "당신은 AIWorks 문서 편집 모델입니다. 사용자 지시를 정확히 반영해 "
                            "원문을 실질적으로 고쳐 쓰세요. 최종 대체 문장만 한국어로 출력하고 "
                            "설명, 머리말, 따옴표, 마크다운을 넣지 마세요. 사용자가 명시적으로 "
                            "원문 유지를 요구하지 않았다면 원문을 그대로 반복하지 마세요."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "요청: "
                            + plan["intent"][:1_000]
                            + "\n변경할 문장: "
                            + selection_text
                        ),
                    },
                ],
                max_tokens=500,
                primary_model_id=model_id,
            )
            replacement_text = REWRITE_OUTPUT_MCP.clean(live["content"])
            if replacement_text == selection_text.strip() or not replacement_text:
                live = _chat_with_route_fallback(
                    routing,
                    [
                        {
                            "role": "system",
                            "content": "원문과 다른 최종 대체 문장만 출력하세요. 설명이나 인용 표시는 금지합니다.",
                        },
                        {
                            "role": "user",
                            "content": "첫 결과가 원문과 같았습니다. 다음 지시를 반드시 반영해 다시 작성하세요.\n요청: " + plan["intent"][:1_000] + "\n원문: " + selection_text,
                        },
                    ],
                    max_tokens=500,
                    primary_model_id=model_id,
                )
                replacement_text = REWRITE_OUTPUT_MCP.clean(live["content"])
                if replacement_text == selection_text.strip() or not replacement_text:
                    raise ApiError("모델이 두 번 연속 원문과 동일한 문장을 반환했습니다.", 502)
            result = _make_result(plan["intent"], input_context, routing)
            result["patches"][0]["after"] = replacement_text
            result["model"].update(
                {
                    "name": live.get("requestedModel") or model_id,
                    "mode": "live-fallback" if live.get("fallbackUsed") else "live",
                    "resolvedModel": live["resolvedModel"],
                    "usage": live["usage"],
                    "requestId": live["requestId"],
                    "fallbackUsed": bool(live.get("fallbackUsed")),
                    "fallbackFrom": live.get("fallbackFrom"),
                    "fallbackReason": live.get("fallbackReason"),
                }
            )
        else:
            result = _make_result(plan["intent"], input_context, routing)
        if workflow["responseType"] != "selection-edit":
            local = WORKSPACE_ORCHESTRATION_MCP.local_result(plan["intent"], input_context, workflow)
            result = {
                **local,
                "responseType": workflow["responseType"],
                "workflow": workflow,
                "loadedMcps": workflow["loadedMcps"],
                "sources": [],
                "model": {
                    "provider": "openrouter",
                    "name": (routing.get("model") or {}).get("id", "upstage/solar-pro-3"),
                    "externalTransfer": generic_live_model_enabled,
                    "mode": "local-preview",
                },
                "policy": {"personalDataDetected": False, "maskedFields": []},
            }
            if workflow["responseType"] == "template-transform":
                session_id = str(input_context.get("document_id") or "")
                if not session_id.startswith("docsession_"):
                    raise ApiError("양식을 적용할 현재 RHWP 문서를 먼저 열어 주세요.", 409)
                session = get_native_document_session(session_id, include_artifact=True)
                if session.get("snapshot", {}).get("kind") != "structured-hwpx":
                    raise ApiError("현재 버전의 양식 MCP는 HWPX 문서 세션에만 적용할 수 있습니다.", 415)
                source_hwpx = base64.b64decode(session["contentBase64"], validate=True)
                formatted_hwpx, template_metadata = MOIS_REPORT_TEMPLATE_MCP.apply(
                    source_hwpx,
                    session["filename"],
                    REPORT_HWPX_MCP.build,
                )
                source_stem = Path(session["filename"]).stem
                for suffix in ("_AIWorks", "_행안부보고"):
                    if source_stem.endswith(suffix):
                        source_stem = source_stem[: -len(suffix)]
                result["artifact"] = {
                    "title": template_metadata["preservedTitle"],
                    "filename": (source_stem[:70] or "AIWorks_보고서") + "_행안부보고.hwpx",
                    "format": "hwpx",
                    "mediaType": "application/hwp+zip",
                    "contentBase64": base64.b64encode(formatted_hwpx).decode("ascii"),
                    "editorMcp": "document.rhwp@1.0.0",
                    "applyMode": "replace-current-session",
                    "template": template_metadata["template"],
                    "sourceParagraphCount": template_metadata["sourceParagraphCount"],
                }
                result["model"].update({
                    "provider": "local",
                    "name": "template.mois-report@0.1.0",
                    "externalTransfer": False,
                    "mode": "local-template",
                })
            if generic_live_model_enabled:
                model_id = result["model"]["name"]
                live = _chat_with_route_fallback(
                    routing,
                    WORKSPACE_ORCHESTRATION_MCP.live_messages(plan["intent"], input_context, workflow),
                    max_tokens=900 if workflow["responseType"] in {"report-artifact", "document-transform"} else 500,
                    primary_model_id=model_id,
                )
                if workflow["responseType"] in {"report-artifact", "document-transform"}:
                    result["artifact"]["content"] = live["content"]
                else:
                    result["answer"] = live["content"]
                result["model"].update({
                    "name": live.get("requestedModel") or model_id,
                    "mode": "live-fallback" if live.get("fallbackUsed") else "live",
                    "resolvedModel": live["resolvedModel"],
                    "usage": live["usage"],
                    "requestId": live["requestId"],
                    "fallbackUsed": bool(live.get("fallbackUsed")),
                    "fallbackFrom": live.get("fallbackFrom"),
                    "fallbackReason": live.get("fallbackReason"),
                })
        if workflow["responseType"] in {"report-artifact", "document-transform"}:
            report_title = str(result["artifact"].get("title") or workflow.get("title") or "AIWorks 파생 보고서")
            report_content = str(result["artifact"].get("content") or "")
            apply_mode = result["artifact"].get("applyMode")
            structured_artifact = _build_structured_report_artifact(
                report_title,
                report_content,
                plan["intent"],
                fact_snapshot=fact_snapshot,
                generated_by=["document.report@1.0.0"],
            )
            formatter = None
            if workflow.get("signals", {}).get("moisTemplate"):
                source_hwpx = base64.b64decode(structured_artifact["contentBase64"], validate=True)
                formatted_hwpx, template_metadata = MOIS_REPORT_TEMPLATE_MCP.apply(
                    source_hwpx,
                    structured_artifact["filename"],
                    REPORT_HWPX_MCP.build,
                )
                structured_artifact["contentBase64"] = base64.b64encode(formatted_hwpx).decode("ascii")
                structured_artifact["filename"] = (Path(structured_artifact["filename"]).stem[:70] or "AIWorks_보고서") + "_행안부보고.hwpx"
                structured_artifact["template"] = template_metadata["template"]
                structured_artifact["templateApplication"] = {
                    "packageRef": "template.mois-report@0.1.0",
                    "mode": "new-report",
                    "sourceParagraphCount": template_metadata["sourceParagraphCount"],
                }
                structured_artifact["generatedBy"] = list(dict.fromkeys([
                    *(structured_artifact.get("generatedBy") or []),
                    "template.mois-report@0.1.0",
                ]))
            else:
                structured_artifact, formatter = _finalize_report_with_loopback_mcp(structured_artifact, plan["intent"])
                if formatter and formatter["packageRef"] not in result["loadedMcps"]:
                    result["loadedMcps"].insert(-1, formatter["packageRef"])
            if apply_mode:
                structured_artifact["applyMode"] = apply_mode
            result["artifact"] = structured_artifact
        result.setdefault("responseType", "selection-edit")
        result.setdefault("workflow", workflow)
        result.setdefault("loadedMcps", workflow["loadedMcps"])
        completed_at = utc_now()
        with _connect() as db:
            _complete_workflow_step(
                db,
                workflow_run_id,
                "execute",
                {"responseType": result.get("responseType"), "loadedMcps": result.get("loadedMcps") or []},
                {"dynamic": False, "model": result.get("model") or {}},
                next_step="persist",
                next_input={"projectId": project_id, "responseType": result.get("responseType")},
            )

            _persist_result_markdown(db, project_id, plan_id, execution_id, input_context, result)
            _record_report_fact_snapshot(db, project_id, plan_id, execution_id, result)
            db.execute(
                "UPDATE executions SET status='completed', result_json=?, completed_at=? WHERE id=?",
                (_json(result), completed_at, execution_id),
            )
            db.execute("UPDATE plans SET status='completed', updated_at=? WHERE id=?", (completed_at, plan_id))
            _audit(
                db,
                "sandbox-executor",
                "execution.completed",
                {"response_type": result["responseType"], "patches": len(result.get("patches", [])), "sources": len(result.get("sources", [])), "loaded_mcps": result.get("loadedMcps", [])},
                plan_id=plan_id,
                execution_id=execution_id,
            )
            _complete_workflow_run(
                db, workflow_run_id, result, {"executionId": execution_id, "projectId": project_id}
            )
    except Exception as error:
        with _connect() as db:
            db.execute(
                "UPDATE executions SET status='failed', error=?, completed_at=? WHERE id=?",
                (str(error), utc_now(), execution_id),
            )
            db.execute("UPDATE plans SET status='failed', updated_at=? WHERE id=?", (utc_now(), plan_id))
            _audit(
                db,
                "sandbox-executor",
                "execution.failed",
                {"error": str(error)},
                plan_id=plan_id,
                execution_id=execution_id,
            )
            _fail_workflow_run(db, workflow_run_id, error)
        raise
    return {
        "id": execution_id,
        "planId": plan_id,
        "workflowRunId": workflow_run_id,
        "status": "completed",
        "result": result,
        "queuedAt": queued_at,
        "startedAt": started_at,
        "completedAt": completed_at,
    }


def list_audit(limit: int = 50) -> dict:
    ensure_schema()
    limit = max(1, min(200, int(limit)))
    with _connect() as db:
        rows = db.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        counts = {
            row["status"]: row["count"]
            for row in db.execute("SELECT status, COUNT(*) AS count FROM executions GROUP BY status")
        }
    return {
        "items": [
            {
                "id": row["id"],
                "executionId": row["execution_id"],
                "planId": row["plan_id"],
                "actor": row["actor"],
                "eventType": row["event_type"],
                "detail": _load_json(row["detail_json"], {}),
                "createdAt": row["created_at"],
            }
            for row in rows
        ],
        "executionCounts": counts,
    }


def operational_readiness() -> dict:
    ensure_schema()
    checks = []

    def add(check_id: str, status: str, detail: str) -> None:
        checks.append({"id": check_id, "status": status, "detail": detail})

    try:
        with _connect() as db:
            quick_check = db.execute("PRAGMA quick_check").fetchone()[0]
            package_rows = db.execute("SELECT * FROM mcp_packages").fetchall()
            knowledge_sources = db.execute("SELECT COUNT(*) FROM knowledge_sources").fetchone()[0]
        add("database.integrity", "pass" if quick_check == "ok" else "fail", str(quick_check))
        add("knowledge.sources", "pass" if knowledge_sources else "warn", f"연결 출처 {knowledge_sources}개" if knowledge_sources else "연결 출처 0개 · 데이터 MCP 설치 전에는 선택 기능")
    except Exception as error:
        add("database.integrity", "fail", str(error))
        package_rows = []
    verified_packages = 0
    package_failures = []
    for row in package_rows:
        try:
            _verified_package(row)
            verified_packages += 1
        except ApiError as error:
            package_failures.append(f'{row["package_id"]}@{row["version"]}: {error}')
    add("store.signatures", "fail" if package_failures else "pass", "; ".join(package_failures) if package_failures else f"서명 검증 {verified_packages}개")
    models = MODEL_MANAGEMENT_MCP.list_models()
    default_models = [model for model in models if model.get("default")]
    solar_default = bool(default_models) and default_models[0]["id"] == "upstage:solar-pro3-fast"
    solar_roles = {model.get("routingRole") for model in models if model.get("provider") == "upstage"}
    add(
        "models.registry",
        "pass" if len(models) >= 2 and len(default_models) == 1 and solar_default else "fail",
        f'등록 모델 {len(models)}개 · 기본 {default_models[0]["label"] if default_models else "없음"}',
    )
    add("approval.secret", "pass" if os.getenv("AIWORKS_APPROVAL_SECRET", "").strip() else "warn", "환경 전용 키 사용" if os.getenv("AIWORKS_APPROVAL_SECRET", "").strip() else "파생 개발 키 사용")
    add("store.signing-secret", "pass" if os.getenv("AIWORKS_STORE_SIGNING_SECRET", "").strip() else "warn", "분리된 서명 키 사용" if os.getenv("AIWORKS_STORE_SIGNING_SECRET", "").strip() else "승인 키에서 파생된 PoC 키 사용")
    pdf_extractor = _pdf_text_extractor_status()
    add(
        "data-mcp.pdf-extractor",
        "pass" if pdf_extractor["available"] else "fail",
        f'{pdf_extractor.get("version") or pdf_extractor.get("error")} · {pdf_extractor.get("executable") or "경로 없음"}',
    )
    rhwp_status = RHWP_AUTOMATION_MCP.runtime_status()
    add("rhwp.runtime", "pass" if rhwp_status["available"] else "warn", f'Windows 브리지 · 도구 {rhwp_status["tools"]}개' if rhwp_status["available"] else "Windows 브리지 명령·비밀키 미설정")
    contract_only = [adapter["id"] for adapter in CAPABILITY_ADAPTERS if adapter["status"] == "contract-only"]
    add("adapters.runtime", "warn" if contract_only else "pass", "미연결: " + ", ".join(contract_only) if contract_only else "모든 어댑터 연결됨")
    failures = sum(check["status"] == "fail" for check in checks)
    warnings = sum(check["status"] == "warn" for check in checks)
    return {"ready": failures == 0, "status": "not-ready" if failures else ("ready-with-warnings" if warnings else "ready"), "checks": checks, "summary": {"passed": sum(check["status"] == "pass" for check in checks), "warnings": warnings, "failed": failures}, "checkedAt": utc_now()}


def _acceptance_hwpx() -> bytes:
    output = io.BytesIO()
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <hs:sec xmlns:hs="urn:hancom:section" xmlns:hp="urn:hancom:paragraph">
      <hp:p><hp:run><hp:t>총사업비 산출 근거를 최신 기준으로 반영한다.</hp:t></hp:run></hp:p>
      <hp:p><hp:run><hp:t>총사업비: 1,284백만원</hp:t></hp:run></hp:p>
    </hs:sec>"""
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/section0.xml", xml)
        archive.writestr("BinData/acceptance.bin", b"AIWORKS-E2E-PRESERVE")
    return output.getvalue()


def run_budget_acceptance(payload: dict) -> dict:
    ensure_schema()
    injection = str(payload.get("inject_failure") or "none")
    if injection not in {"none", "stale-document"}:
        raise ApiError("지원하지 않는 실패 주입 유형입니다.")
    run_id = "accept_" + uuid.uuid4().hex
    actor = _actor(payload)
    started_at = utc_now()
    checks = []
    artifacts = {}
    error_message = None

    def check(check_id: str, passed: bool, detail: str) -> None:
        checks.append({"id": check_id, "passed": bool(passed), "detail": str(detail)})
        if not passed:
            raise ApiError(detail, 409)

    try:
        source = _acceptance_hwpx()
        inspected = parse_hwpx(source, "acceptance-budget.hwpx")
        first = inspected["paragraphs"][0]
        check("document.inspect", inspected["stats"]["paragraphs"] == 2, f'문단 {inspected["stats"]["paragraphs"]}개 분석')
        plan = create_plan({"intent": "예산 산출 근거를 현재 기준으로 갱신해줘", "actor": actor, "document_context": {"document_id": inspected["document"]["id"], "classification": "internal", "has_selection": True, "selection_id": first["id"], "selection_text": first["text"]}})
        check("plan.permissions", {"document.read", "document.write", "model.invoke", "network.send"}.issubset(set(plan["requiredPermissions"])), "최소권한 실행 계획 생성")
        approval = approve_plan({"plan_id": plan["id"], "actor": actor, "permissions": plan["requiredPermissions"]})
        claims = _verify_token(approval["approvalToken"])
        check("approval.signature", claims["plan_id"] == plan["id"], "서명된 일회용 승인 토큰 검증")
        execution = execute_plan({"approval_token": approval["approvalToken"], "idempotency_key": run_id, "input": {"selection": first["text"], "selection_id": first["id"]}}, force_local=True)
        patch = execution["result"]["patches"][0]
        check("execution.completed", execution["status"] == "completed" and execution["result"]["model"]["mode"] == "routing-simulation", "외부 호출 없는 승인 실행 완료")
        source_sha = "0" * 64 if injection == "stale-document" else inspected["document"]["sha256"]
        artifact = apply_hwpx_document_patch({"filename": "acceptance-budget.hwpx", "document_id": inspected["document"]["id"], "content_base64": base64.b64encode(source).decode("ascii"), "actor": actor, "patch": {"op": "replace", "target": first["id"], "expectedBefore": patch["before"], "after": patch["after"], "sourceSha256": source_sha, "executionId": execution["id"], "sources": execution["result"]["sources"]}})
        artifact_bytes = base64.b64decode(artifact["contentBase64"])
        reparsed = parse_hwpx(artifact_bytes, artifact["filename"])
        check("document.patch", reparsed["paragraphs"][0]["text"] == patch["after"], "승인 변경안이 지정 문단에 적용됨")
        with zipfile.ZipFile(io.BytesIO(artifact_bytes)) as archive:
            preserved = archive.read("BinData/acceptance.bin") == b"AIWORKS-E2E-PRESERVE"
        check("document.preserve-assets", preserved, "비대상 ZIP 자산 보존")
        with _connect() as db:
            events = {row["event_type"] for row in db.execute("SELECT event_type FROM audit_events WHERE execution_id=?", (execution["id"],)).fetchall()}
        check("audit.trace", {"execution.queued", "execution.started", "execution.completed", "document.patch_applied"}.issubset(events), "실행 ID 기반 감사 이벤트 연결")
        artifacts = {"planId": plan["id"], "executionId": execution["id"], "documentVersionId": artifact["versionId"], "filename": artifact["filename"], "sourceSha256": artifact["sourceSha256"], "artifactSha256": artifact["artifactSha256"]}
    except Exception as error:
        error_message = str(error)
        if not checks or checks[-1]["passed"]:
            checks.append({"id": "scenario.exception", "passed": False, "detail": error_message})
    status = "passed" if checks and all(item["passed"] for item in checks) else "failed"
    completed_at = utc_now()
    with _connect() as db:
        db.execute("INSERT INTO acceptance_runs(id,scenario,status,checks_json,artifacts_json,error,actor,started_at,completed_at) VALUES(?,?,?,?,?,?,?,?,?)", (run_id, "budget-request-e2e", status, _json(checks), _json(artifacts), error_message, actor, started_at, completed_at))
        _audit(db, actor, "acceptance." + status, {"run_id": run_id, "scenario": "budget-request-e2e", "checks": len(checks), "injection": injection})
    return {"id": run_id, "scenario": "budget-request-e2e", "status": status, "checks": checks, "artifacts": artifacts, "error": error_message, "startedAt": started_at, "completedAt": completed_at}


def list_acceptance_runs() -> dict:
    ensure_schema()
    with _connect() as db:
        rows = db.execute("SELECT * FROM acceptance_runs ORDER BY completed_at DESC LIMIT 50").fetchall()
    return {"items": [{"id": row["id"], "scenario": row["scenario"], "status": row["status"], "checks": _load_json(row["checks_json"], []), "artifacts": _load_json(row["artifacts_json"], {}), "error": row["error"], "actor": row["actor"], "startedAt": row["started_at"], "completedAt": row["completed_at"]} for row in rows]}


def rhwp_capabilities() -> dict:
    ensure_schema()
    with _connect() as db:
        installation = db.execute(
            "SELECT pinned_version,status FROM mcp_installations WHERE package_id='document.rhwp'"
        ).fetchone()
    return {
        "manifest": RHWP_AUTOMATION_MCP.MANIFEST,
        "tools": RHWP_AUTOMATION_MCP.tool_catalog(),
        "runtime": RHWP_AUTOMATION_MCP.runtime_status(),
        "installation": dict(installation) if installation else None,
        "approvalRequired": True,
        "externalTransfer": False,
    }


def invoke_rhwp(payload: dict) -> dict:
    ensure_schema()
    with _connect() as db:
        installation = db.execute(
            "SELECT pinned_version,status FROM mcp_installations WHERE package_id='document.rhwp' AND status='active'"
        ).fetchone()
    if not installation:
        raise ApiError("RHWP MCP가 설치되어 있지 않습니다.", 409)
    tool = str(payload.get("tool") or "").strip()
    arguments = payload.get("arguments") or {}
    permissions = payload.get("approved_permissions") or []
    if not isinstance(permissions, list) or any(not isinstance(item, str) for item in permissions):
        raise ApiError("approved_permissions는 문자열 배열이어야 합니다.")
    try:
        result = RHWP_AUTOMATION_MCP.invoke(
            tool,
            arguments,
            permissions,
            payload.get("confirmed") is True,
        )
    except RHWP_AUTOMATION_MCP.RhwpMcpError as error:
        status = 503 if "브리지" in str(error) or "설정되지" in str(error) else 403
        with _connect() as db:
            _audit(db, _actor(payload), "rhwp.invoke_blocked", {"tool": tool, "error": str(error), "external_transfer": False})
        raise ApiError(str(error), status) from error
    with _connect() as db:
        _audit(db, _actor(payload), "rhwp.invoked", {"tool": tool, "request_id": result["requestId"], "permissions": permissions, "external_transfer": False})
    return result


def bootstrap() -> dict:
    ensure_schema()
    with _connect() as db:
        plans = db.execute("SELECT COUNT(*) AS count FROM plans").fetchone()["count"]
        executions = db.execute("SELECT COUNT(*) AS count FROM executions").fetchone()["count"]
        knowledge_nodes = db.execute("SELECT COUNT(*) AS count FROM knowledge_nodes").fetchone()["count"]
        knowledge_sources = db.execute("SELECT COUNT(*) AS count FROM knowledge_sources").fetchone()["count"]
        recent = db.execute(
            "SELECT event_type, actor, created_at FROM audit_events ORDER BY id DESC LIMIT 5"
        ).fetchall()
    return {
        "service": "AIWorks",
        "version": "0.30.0",
        "runtime": "local-sandbox",
        "models": MODEL_MANAGEMENT_MCP.list_models(),
        "mcp": {
            "intentAnalysis": INTENT_ANALYSIS_MCP.MANIFEST,
            "modelManagement": MODEL_MANAGEMENT_MCP.MANIFEST,
            "workspaceOrchestration": WORKSPACE_ORCHESTRATION_MCP.MANIFEST,
            "moisReportTemplate": {
                **MOIS_REPORT_TEMPLATE_MCP.MANIFEST,
                "templates": MOIS_REPORT_TEMPLATE_MCP.catalog(),
            },
            "rhwpAutomation": RHWP_AUTOMATION_MCP.MANIFEST,
        },
        "openrouter": {
            "configured": bool(_upstage_key() or _openrouter_key()),
            "liveExecutionEnabled": bool(_upstage_key() or _openrouter_key()) and _live_model_execution_enabled(),
            "freeOnly": False,
            "defaultModel": MODEL_MANAGEMENT_MCP.select_model({"intentType": "information_query"})["model"]["id"],
        },
        "localRagLlm": {
            "enabled": os.getenv("AIWORKS_LOCAL_RAG_LLM", "0").strip() != "0",
            "provider": "ollama",
            "model": os.getenv("AIWORKS_OLLAMA_RAG_MODEL", "qwen2.5:1.5b"),
            "externalTransfer": False,
        },
        "policies": {
            "externalTransferDefault": False,
            "approvalRequired": True,
            "approvalTokenTtlSeconds": TOKEN_TTL_SECONDS,
            "auditPersistent": True,
        },
        "capabilities": {"workflowPresets": len(WORKFLOW_PRESETS), "adapters": len(CAPABILITY_ADAPTERS), "templates": len(MOIS_REPORT_TEMPLATE_MCP.catalog()), "maxAssetBytes": MAX_ASSET_BYTES, "acceptanceScenario": "budget-request-e2e", "mcpBuilder": True, "mcpBuilderTypes": list(MCP_BUILDER_TYPES), "builderReferenceFormats": [".hwpx", ".pdf", ".docx", ".xlsx", ".md", ".txt"], "capabilityRegistry": True, "dynamicBuilderRuntime": ["prompt", "composite", "retrieval", "external-mcp"], "externalMcpTransport": ["stdio", "streamable-http"], "externalMcpProfiles": [_external_profile_status(item) for item in EXTERNAL_MCP_SERVER_PROFILES], "templateAnalysisModes": ["explicit-placeholders", "guided-fields", "sample-structure"], "arbitraryBuilderCode": False, "workspaceDocuments": True, "nativeDocumentSessions": True, "downloadableDocumentVersions": True, "rhwp": RHWP_AUTOMATION_MCP.runtime_status()},
        "pdfTextExtraction": _pdf_text_extractor_status(),
        "counts": {"plans": plans, "executions": executions, "knowledgeNodes": knowledge_nodes, "knowledgeSources": knowledge_sources},
        "recent": [dict(row) for row in recent],
    }


def _xml_attribute(element, name: str, default: str = "") -> str:
    if element is None:
        return default
    for key, value in element.attrib.items():
        if key.rsplit("}", 1)[-1] == name:
            return str(value)
    return default


def _positive_integer(value: str, default: int = 1) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _nonnegative_integer(value: str, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _hwpunit_pixels(value: str) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return max(1, min(2_000, round(number / 75)))


def parse_hwpx(data: bytes, filename: str = "document.hwpx") -> dict:
    if not data:
        raise ApiError("HWPX 파일 내용이 비어 있습니다.")
    if len(data) > MAX_HWPX_BYTES:
        raise ApiError(f"HWPX 파일은 {MAX_HWPX_BYTES:,}바이트를 넘을 수 없습니다.", 413)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise ApiError("유효한 HWPX ZIP 구조가 아닙니다.") from error
    with archive:
        members = archive.infolist()
        if len(members) > 2_000:
            raise ApiError("HWPX 내부 파일 수가 허용 범위를 넘었습니다.")
        total_size = sum(member.file_size for member in members)
        if total_size > MAX_UNCOMPRESSED_BYTES:
            raise ApiError("HWPX 압축 해제 크기가 허용 범위를 넘었습니다.", 413)
        section_names = sorted(
            member.filename
            for member in members
            if re.fullmatch(r"Contents/section\d+\.xml", member.filename, flags=re.IGNORECASE)
        )
        if not section_names:
            raise ApiError("HWPX 본문 section XML을 찾을 수 없습니다.")
        paragraphs = []
        layout_sections = []
        table_count = 0
        cell_count = 0
        object_count = 0
        for section_name in section_names:
            raw = archive.read(section_name)
            upper = raw.upper()
            if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
                raise ApiError("외부 엔터티가 포함된 XML은 처리할 수 없습니다.")
            try:
                root = ElementTree.fromstring(raw)
            except ElementTree.ParseError as error:
                raise ApiError(f"HWPX XML 분석 실패: {section_name}") from error
            section_paragraph_index = 0
            paragraph_ids = {}
            paragraph_items = {}
            for element in root.iter():
                if element.tag.rsplit("}", 1)[-1] != "p":
                    continue
                section_paragraph_index += 1
                text = "".join(element.itertext())
                text = re.sub(r"\s+", " ", text).strip()
                paragraph_id = f"{section_name}#p{section_paragraph_index}"
                paragraph_ids[id(element)] = paragraph_id
                item = {
                    "id": paragraph_id,
                    "text": text[:10_000],
                    "paraPrId": _xml_attribute(element, "paraPrIDRef"),
                    "styleId": _xml_attribute(element, "styleIDRef"),
                }
                paragraphs.append(item)
                paragraph_items[id(element)] = item

            tables = [
                element for element in root.iter()
                if element.tag.rsplit("}", 1)[-1] == "tbl"
            ]
            table_paragraphs = {
                id(element)
                for table in tables
                for element in table.iter()
                if element.tag.rsplit("}", 1)[-1] == "p"
            }
            blocks = []
            seen_tables = set()
            for element in root.iter():
                local_name = element.tag.rsplit("}", 1)[-1]
                if local_name == "p":
                    item = paragraph_items.get(id(element))
                    contains_table = any(
                        descendant.tag.rsplit("}", 1)[-1] == "tbl"
                        for descendant in element.iter()
                        if descendant is not element
                    )
                    if item and id(element) not in table_paragraphs and not contains_table:
                        blocks.append({"type": "paragraph", "paragraphId": item["id"]})
                elif local_name == "tbl" and id(element) not in seen_tables:
                    seen_tables.add(id(element))
                    rows = []
                    for row_element in [
                        child for child in list(element)
                        if child.tag.rsplit("}", 1)[-1] == "tr"
                    ]:
                        cells = []
                        for cell_element in [
                            child for child in list(row_element)
                            if child.tag.rsplit("}", 1)[-1] == "tc"
                        ]:
                            span_element = next(
                                (
                                    child for child in cell_element.iter()
                                    if child.tag.rsplit("}", 1)[-1] == "cellSpan"
                                ),
                                None,
                            )
                            address_element = next(
                                (
                                    child for child in cell_element.iter()
                                    if child.tag.rsplit("}", 1)[-1] == "cellAddr"
                                ),
                                None,
                            )
                            size_element = next(
                                (
                                    child for child in cell_element.iter()
                                    if child.tag.rsplit("}", 1)[-1] == "cellSz"
                                ),
                                None,
                            )
                            cell_paragraph_ids = [
                                paragraph_ids[id(child)]
                                for child in cell_element.iter()
                                if child.tag.rsplit("}", 1)[-1] == "p"
                                and id(child) in paragraph_items
                            ]
                            cells.append({
                                "rowSpan": _positive_integer(_xml_attribute(span_element if span_element is not None else cell_element, "rowSpan", "1")),
                                "colSpan": _positive_integer(_xml_attribute(span_element if span_element is not None else cell_element, "colSpan", "1")),
                                "row": _nonnegative_integer(_xml_attribute(address_element, "rowAddr", str(len(rows))), len(rows)),
                                "column": _nonnegative_integer(_xml_attribute(address_element, "colAddr", str(len(cells))), len(cells)),
                                "widthPx": _hwpunit_pixels(_xml_attribute(size_element, "width")),
                                "heightPx": _hwpunit_pixels(_xml_attribute(size_element, "height")),
                                "paragraphIds": cell_paragraph_ids,
                            })
                            cell_count += 1
                        if cells:
                            rows.append({"cells": cells})
                    if rows:
                        table_count += 1
                        blocks.append({"type": "table", "id": f"{section_name}#table{table_count}", "rows": rows})
                elif local_name in {"pic", "equation", "ole", "container"}:
                    object_count += 1
                    blocks.append({"type": "object", "objectType": local_name, "id": f"{section_name}#object{object_count}"})
            layout_sections.append({"id": section_name, "blocks": blocks})
        combined = "\n".join(item["text"] for item in paragraphs)
        values = []
        patterns = [
            ("project.name", "사업명", r"사업명\s*[:：]?\s*([^\n]{2,80})"),
            ("project.period", "사업기간", r"사업기간\s*[:：]?\s*([^\n]{4,80})"),
            ("budget.total", "총사업비", r"총사업비\s*[:：]?\s*([0-9,\.]+\s*(?:백만원|억원|원))"),
        ]
        for key, label, pattern in patterns:
            match = re.search(pattern, combined)
            if match:
                values.append(
                    {
                        "id": key,
                        "label": label,
                        "value": match.group(1).strip(),
                        "source": {"documentId": filename, "locator": "HWPX 본문"},
                        "confidence": 0.9,
                    }
                )
    return {
        "document": {
            "id": "doc_" + hashlib.sha256(data).hexdigest()[:16],
            "name": filename[:200],
            "format": "hwpx",
            "sha256": hashlib.sha256(data).hexdigest(),
        },
        "paragraphs": paragraphs[:500],
        "layout": {"sections": layout_sections, "fidelity": "structure", "nativePreviewAvailable": RHWP_AUTOMATION_MCP.runtime_status()["available"]},
        "commonDataCandidates": values,
        "stats": {"sections": len(section_names), "paragraphs": len(paragraphs), "tables": table_count, "cells": cell_count, "objects": object_count, "bytes": len(data)},
    }


def hwpx_to_markdown(parsed: dict, filename: str = "document.hwpx") -> dict:
    paragraphs = {str(item.get("id")): item for item in parsed.get("paragraphs") or []}
    ordered_text = [item for item in parsed.get("paragraphs") or [] if str(item.get("text") or "").strip()]
    layout_sections = (parsed.get("layout") or {}).get("sections") or []
    title_item = next(
        (
            item for item in ordered_text
            if not re.match(r"^(?:행정안전부 업무보고|작성일\s*[:：]|※)", str(item.get("text") or "").strip())
            and len(str(item.get("text") or "").strip()) <= 200
        ),
        None,
    )
    title = str((title_item or {}).get("text") or Path(filename).stem).strip()
    decorative_paragraph_ids = set()
    for section in layout_sections:
        for block in section.get("blocks") or []:
            if block.get("type") != "table":
                continue
            paragraph_ids = [
                str(paragraph_id)
                for row in block.get("rows") or []
                for cell in row.get("cells") or []
                for paragraph_id in cell.get("paragraphIds") or []
            ]
            values = [str((paragraphs.get(paragraph_id) or {}).get("text") or "").strip() for paragraph_id in paragraph_ids]
            nonempty = [value for value in values if value]
            if nonempty and all(value == title for value in nonempty):
                decorative_paragraph_ids.update(paragraph_ids)
    generated_cover_detected = bool(decorative_paragraph_ids)
    lines = ["# " + title, ""]
    emitted = set(decorative_paragraph_ids)

    def emit_paragraph(paragraph_id: str) -> None:
        if paragraph_id in emitted:
            return
        emitted.add(paragraph_id)
        item = paragraphs.get(paragraph_id) or {}
        text = str(item.get("text") or "").strip()
        if not text or item is title_item or text == title:
            return
        if generated_cover_detected and re.fullmatch(r"\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.", text):
            return
        marker = re.match(r"^(?:(?:[-*+•·○ㅇ□▪◦])\s*)+(.+)$", text)
        if str(item.get("paraPrId") or "") == "59" or marker:
            clean = (marker.group(1) if marker else text).strip()
            lines.append("- " + clean)
        elif str(item.get("paraPrId") or "") == "64" or (len(text) <= 60 and re.match(r"^(?:\d+[.)]\s*)?[가-힣A-Za-z].*(?:개요|현황|결과|계획|사항|시사점|배경|목적)$", text)):
            lines.extend(["## " + text, ""])
        else:
            lines.extend([text, ""])

    for section in layout_sections:
        for block in section.get("blocks") or []:
            if block.get("type") == "paragraph":
                emit_paragraph(str(block.get("paragraphId") or ""))
            elif block.get("type") == "table":
                block_paragraph_ids = {
                    str(paragraph_id)
                    for row in block.get("rows") or []
                    for cell in row.get("cells") or []
                    for paragraph_id in cell.get("paragraphIds") or []
                }
                if block_paragraph_ids and block_paragraph_ids <= decorative_paragraph_ids:
                    continue
                rows = []
                for row in block.get("rows") or []:
                    cells = []
                    for cell in row.get("cells") or []:
                        values = []
                        for paragraph_id in cell.get("paragraphIds") or []:
                            emitted.add(str(paragraph_id))
                            value = str((paragraphs.get(str(paragraph_id)) or {}).get("text") or "").strip()
                            if value:
                                values.append(value)
                        cells.append("<br>".join(values))
                    rows.append(cells)
                if rows:
                    width = max(len(row) for row in rows)
                    normalized = [row + [""] * (width - len(row)) for row in rows]
                    lines.append("| " + " | ".join(normalized[0]) + " |")
                    lines.append("| " + " | ".join(["---"] * width) + " |")
                    lines.extend("| " + " | ".join(row) + " |" for row in normalized[1:])
                    lines.append("")
            elif block.get("type") == "object":
                lines.extend(["※ 원본 HWPX 개체: " + str(block.get("objectType") or "object"), ""])
    for item in ordered_text:
        emit_paragraph(str(item.get("id") or ""))
    markdown = "\n".join(lines).strip()
    source_map = [
        {"paragraphId": item["id"], "text": item["text"]}
        for item in ordered_text[:500]
    ]
    return {
        "title": title,
        "markdown": markdown,
        "sourceFormat": "hwpx",
        "sourceDocument": parsed.get("document") or {},
        "sourceMap": source_map,
        "conversion": {"textPreserved": True, "layoutSeparated": True, "layoutArtifactsRemoved": len(decorative_paragraph_ids), "objectsAsNotes": True, "visualFidelity": "semantic"},
    }


def analyze_hwpx(payload: dict) -> dict:
    encoded = str(payload.get("content_base64") or "")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as error:
        raise ApiError("content_base64가 올바르지 않습니다.") from error
    result = parse_hwpx(data, str(payload.get("filename") or "document.hwpx"))
    ensure_schema()
    with _connect() as db:
        _audit(
            db,
            _actor(payload),
            "document.analyzed",
            {"document": result["document"], "stats": result["stats"], "external_transfer": False},
        )
    return result


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def apply_hwpx_patch(data: bytes, patch: dict, filename: str = "document.hwpx") -> tuple[bytes, dict]:
    if not isinstance(patch, dict):
        raise ApiError("patch는 객체여야 합니다.")
    if patch.get("op") != "replace":
        raise ApiError("현재 HWPX 어댑터는 replace patch만 지원합니다.")
    target = str(patch.get("target") or "")
    target_match = re.fullmatch(r"(Contents/section\d+\.xml)#p([1-9]\d*)", target, re.IGNORECASE)
    if not target_match:
        raise ApiError("HWPX patch 대상 위치가 올바르지 않습니다.")
    expected_sha256 = str(patch.get("sourceSha256") or "").lower()
    source_sha256 = hashlib.sha256(data).hexdigest()
    if expected_sha256 != source_sha256:
        raise ApiError("원본 문서가 분석 이후 변경되었습니다. 다시 열어 주세요.", 409)
    replacement = str(patch.get("after") or "")
    if not replacement.strip():
        raise ApiError("빈 문장으로 교체할 수 없습니다.")
    if len(replacement) > 50_000:
        raise ApiError("교체 문장은 50,000자를 넘을 수 없습니다.")
    expected_before = str(patch.get("expectedBefore") or "")
    section_name = target_match.group(1)
    paragraph_index = int(target_match.group(2))
    if len(data) > MAX_HWPX_BYTES:
        raise ApiError(f"HWPX 파일은 {MAX_HWPX_BYTES:,}바이트를 넘을 수 없습니다.", 413)
    try:
        source_archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise ApiError("유효한 HWPX ZIP 구조가 아닙니다.") from error
    output_buffer = io.BytesIO()
    with source_archive:
        infos = source_archive.infolist()
        if any(info.flag_bits & 0x1 for info in infos):
            raise ApiError("암호화된 HWPX 항목은 수정할 수 없습니다.")
        if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
            raise ApiError("HWPX 압축 해제 크기가 허용 범위를 넘었습니다.", 413)
        names = {info.filename for info in infos}
        actual_section_name = next(
            (name for name in names if name.lower() == section_name.lower()),
            None,
        )
        if not actual_section_name:
            raise ApiError("patch 대상 section XML을 찾을 수 없습니다.", 404)
        raw_section = source_archive.read(actual_section_name)
        if b"<!DOCTYPE" in raw_section.upper() or b"<!ENTITY" in raw_section.upper():
            raise ApiError("외부 엔터티가 포함된 XML은 수정할 수 없습니다.")
        try:
            root = ElementTree.fromstring(raw_section)
        except ElementTree.ParseError as error:
            raise ApiError("patch 대상 XML을 분석할 수 없습니다.") from error
        paragraphs = [
            element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "p"
        ]
        if paragraph_index > len(paragraphs):
            raise ApiError("patch 대상 문단을 찾을 수 없습니다.", 404)
        paragraph = paragraphs[paragraph_index - 1]
        before = _normalized_text("".join(paragraph.itertext()))
        if _normalized_text(expected_before) != before:
            raise ApiError("대상 문단 내용이 예상 원문과 다릅니다. 다시 분석해 주세요.", 409)
        text_nodes = [
            element for element in paragraph.iter() if element.tag.rsplit("}", 1)[-1] == "t"
        ]
        if not text_nodes:
            raise ApiError("대상 문단에 수정 가능한 텍스트 노드가 없습니다.")
        text_nodes[0].text = replacement
        for node in text_nodes[1:]:
            node.text = ""
        modified_section = ElementTree.tostring(
            root, encoding="utf-8", xml_declaration=True
        )
        with zipfile.ZipFile(output_buffer, "w") as output_archive:
            for info in infos:
                entry_data = (
                    modified_section
                    if info.filename == actual_section_name
                    else source_archive.read(info.filename)
                )
                output_archive.writestr(info, entry_data)
    artifact = output_buffer.getvalue()
    metadata = {
        "sourceSha256": source_sha256,
        "artifactSha256": hashlib.sha256(artifact).hexdigest(),
        "target": target,
        "before": before,
        "after": replacement,
        "sourceBytes": len(data),
        "artifactBytes": len(artifact),
        "filename": filename,
    }
    return artifact, metadata


def _aiworks_hwpx_filename(filename: str) -> str:
    stem = Path(filename).stem
    return (stem if stem.endswith("_AIWorks") else stem + "_AIWorks") + ".hwpx"


def apply_hwpx_document_patch(payload: dict) -> dict:
    encoded = str(payload.get("content_base64") or "")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as error:
        raise ApiError("content_base64가 올바르지 않습니다.") from error
    filename = str(payload.get("filename") or "document.hwpx")[:200]
    patch = payload.get("patch") or {}
    artifact, metadata = apply_hwpx_patch(data, patch, filename)
    version_id = "docver_" + uuid.uuid4().hex
    document_id = str(payload.get("document_id") or "doc_" + metadata["sourceSha256"][:16])
    created_at = utc_now()
    output_name = _aiworks_hwpx_filename(filename)
    ensure_schema()
    with _connect() as db:
        db.execute(
            """
            INSERT INTO document_versions(
                id, document_id, filename, source_sha256, artifact_sha256,
                patch_json, execution_id, created_by, created_at, content_blob
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                version_id,
                document_id,
                output_name,
                metadata["sourceSha256"],
                metadata["artifactSha256"],
                _json(patch),
                patch.get("executionId"),
                _actor(payload),
                created_at,
                artifact,
            ),
        )
        _audit(
            db,
            _actor(payload),
            "document.patch_applied",
            {
                "version_id": version_id,
                "document_id": document_id,
                "target": metadata["target"],
                "source_sha256": metadata["sourceSha256"],
                "artifact_sha256": metadata["artifactSha256"],
                "artifact_bytes": metadata["artifactBytes"],
            },
            execution_id=patch.get("executionId"),
        )
    return {
        "versionId": version_id,
        "documentId": document_id,
        "filename": output_name,
        "contentBase64": base64.b64encode(artifact).decode("ascii"),
        "sourceSha256": metadata["sourceSha256"],
        "artifactSha256": metadata["artifactSha256"],
        "bytes": metadata["artifactBytes"],
        "target": metadata["target"],
        "createdAt": created_at,
    }


def list_document_versions() -> dict:
    ensure_schema()
    with _connect() as db:
        rows = db.execute(
            """
            SELECT id, document_id, filename, source_sha256, artifact_sha256,
                   execution_id, created_by, created_at, length(content_blob) AS bytes
              FROM document_versions
             ORDER BY created_at DESC
             LIMIT 100
            """
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


def get_document_version(version_id: str) -> dict:
    ensure_schema()
    with _connect() as db:
        row = db.execute("SELECT * FROM document_versions WHERE id=?", (version_id,)).fetchone()
    if not row:
        raise ApiError("문서 버전을 찾을 수 없습니다.", 404)
    if row["content_blob"] is None:
        raise ApiError("이전 문서 버전에는 다운로드 산출물이 보관되지 않았습니다.", 410)
    return {
        "id": row["id"],
        "documentId": row["document_id"],
        "filename": row["filename"],
        "contentBase64": base64.b64encode(row["content_blob"]).decode("ascii"),
        "sha256": row["artifact_sha256"],
        "bytes": len(row["content_blob"]),
        "createdAt": row["created_at"],
    }


def _workspace_content(payload: dict) -> dict:
    content = payload.get("content")
    if not isinstance(content, dict) or not content:
        raise ApiError("저장할 문서 필드가 필요합니다.")
    if len(content) > 500:
        raise ApiError("문서 필드는 500개를 넘을 수 없습니다.", 413)
    normalized = {}
    total = 0
    for key, value in content.items():
        key = str(key).strip()
        text = str(value)
        if not key or len(key) > 160 or len(text) > 30_000:
            raise ApiError("문서 필드 이름 또는 내용 길이가 허용 범위를 넘었습니다.", 413)
        total += len(text.encode("utf-8"))
        normalized[key] = text
    if total > 1_000_000:
        raise ApiError("문서 초안은 1MB를 넘을 수 없습니다.", 413)
    return normalized


def save_workspace_document(payload: dict) -> dict:
    ensure_schema()
    name = str(payload.get("name") or "").strip()
    if not name or len(name) > 200:
        raise ApiError("문서 이름은 1자 이상 200자 이하여야 합니다.")
    content = _workspace_content(payload)
    actor = _actor(payload)
    document_id = str(payload.get("id") or "").strip()
    now = utc_now()
    with _connect() as db:
        existing = db.execute("SELECT * FROM workspace_documents WHERE id=?", (document_id,)).fetchone() if document_id else None
        if existing:
            base_revision = payload.get("base_revision")
            if not isinstance(base_revision, int) or base_revision != existing["revision"]:
                raise ApiError("다른 작업에서 문서가 변경되었습니다. 다시 열어 주세요.", 409)
            revision = existing["revision"] + 1
            db.execute(
                "UPDATE workspace_documents SET name=?,content_json=?,revision=?,updated_at=? WHERE id=?",
                (name, _json(content), revision, now, document_id),
            )
            event_type = "workspace.document_updated"
        else:
            document_id = "workdoc_" + uuid.uuid4().hex
            revision = 1
            db.execute(
                "INSERT INTO workspace_documents(id,owner,name,content_json,revision,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (document_id, actor, name, _json(content), revision, now, now),
            )
            event_type = "workspace.document_created"
        _audit(db, actor, event_type, {"document_id": document_id, "name": name, "revision": revision, "fields": len(content)})
        row = db.execute("SELECT * FROM workspace_documents WHERE id=?", (document_id,)).fetchone()
    return {
        "id": row["id"], "owner": row["owner"], "name": row["name"],
        "content": _load_json(row["content_json"], {}), "revision": row["revision"],
        "createdAt": row["created_at"], "updatedAt": row["updated_at"],
    }


def list_workspace_documents() -> dict:
    ensure_schema()
    with _connect() as db:
        rows = db.execute("SELECT * FROM workspace_documents ORDER BY updated_at DESC LIMIT 100").fetchall()
    return {"items": [{
        "id": row["id"], "owner": row["owner"], "name": row["name"],
        "revision": row["revision"], "fields": len(_load_json(row["content_json"], {})),
        "createdAt": row["created_at"], "updatedAt": row["updated_at"],
    } for row in rows]}


def get_workspace_document(document_id: str) -> dict:
    ensure_schema()
    with _connect() as db:
        row = db.execute("SELECT * FROM workspace_documents WHERE id=?", (document_id,)).fetchone()
    if not row:
        raise ApiError("작업 문서를 찾을 수 없습니다.", 404)
    return {
        "id": row["id"], "owner": row["owner"], "name": row["name"],
        "content": _load_json(row["content_json"], {}), "revision": row["revision"],
        "createdAt": row["created_at"], "updatedAt": row["updated_at"],
    }


def _native_session_response(row: sqlite3.Row, *, include_artifact: bool = False) -> dict:
    analysis = _load_json(row["intent_json"], {})
    requested_adapter = {
        "document.markdown@1.0.0": "document.markdown@1.0.0",
        "code.editor@1.0.0": "code.editor@1.0.0",
    }.get(row["adapter_id"], "document.rhwp@1.0.0")
    request_text = str(analysis.get("requestText") or "")
    loaded_mcps = ["core.intent-analysis@0.1.0", requested_adapter]
    if any(signal in request_text for signal in ("결산", "회계연도", "집행 실적")):
        loaded_mcps.extend(["template.settlement@0.1.0", "document.report@1.0.0"])
    elif any(signal in request_text for signal in ("보고서", "작성", "초안")):
        loaded_mcps.append("document.report@1.0.0")
    if any(signal in request_text for signal in ("법률", "법령", "법조항", "법 조항")):
        loaded_mcps.append("knowledge.legal@0.1.0")
    if "예산" in request_text:
        loaded_mcps.append("data.budget@0.1.0")
    loaded_mcps = list(dict.fromkeys(loaded_mcps))
    result = {
        "id": row["id"],
        "purpose": str(analysis.get("sessionPurpose") or "document"),
        "builderDraftId": analysis.get("builderDraftId"),
        "builderReferenceId": analysis.get("builderReferenceId"),
        "projectId": row["project_id"] or DEFAULT_PROJECT_ID,
        "markdownDocumentId": row["markdown_document_id"],
        "projectArtifactId": row["project_artifact_id"],
        "markdownBaseRevision": row["markdown_base_revision"],
        "filename": row["filename"],
        "format": row["format"],
        "adapter": row["adapter_id"],
        "runtime": row["runtime"],
        "status": row["status"],
        "revision": row["revision"],
        "intentAnalysis": analysis,
        "orchestration": {
            "requestedAdapter": requested_adapter,
            "selectedAdapter": row["adapter_id"],
            "fallback": requested_adapter != row["adapter_id"],
            "reason": "요청 형식 전용 편집기 MCP 선택" if requested_adapter == row["adapter_id"] else ("Windows RHWP 미연결로 자체 호스팅 RHWP Web/WASM 편집기 사용" if row["adapter_id"].startswith("document.rhwp-web") else "Windows RHWP 미연결로 HWPX 안전 어댑터 사용"),
        },
        "workspace": {
            "editorMcp": row["adapter_id"],
            "loadedMcps": loaded_mcps,
            "pipeline": ["첨부파일 분석", "메타정보 추출", "업무 MCP 적용", "편집기 MCP 스트리밍 반영"],
            "streaming": True,
        },
        "snapshot": _load_json(row["snapshot_json"], {}),
        "artifactSha256": row["artifact_sha256"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
    if include_artifact:
        result["contentBase64"] = base64.b64encode(row["artifact_blob"]).decode("ascii")
    return result


def open_native_document_session(payload: dict) -> dict:
    ensure_schema()
    filename = str(payload.get("filename") or "").strip()
    if not filename or filename != Path(filename).name:
        raise ApiError("안전한 문서 파일 이름이 필요합니다.")
    extension = Path(filename).suffix.lower()
    source_filename, source_extension = filename, extension
    text_formats = {".md": ("document.markdown@1.0.0", "markdown"), ".py": ("code.editor@1.0.0", "python"), ".js": ("code.editor@1.0.0", "javascript"), ".ts": ("code.editor@1.0.0", "typescript"), ".json": ("code.editor@1.0.0", "json"), ".txt": ("document.markdown@1.0.0", "text")}
    if extension not in {".hwp", ".hwpx", ".hwt", ".hml", ".docx", ".xlsx"} | set(text_formats):
        raise ApiError("지원하는 편집기 MCP가 없는 파일 형식입니다.", 415)
    try:
        artifact = base64.b64decode(str(payload.get("content_base64") or ""), validate=True)
    except (ValueError, TypeError) as error:
        raise ApiError("문서 content_base64가 올바르지 않습니다.") from error
    if not artifact or len(artifact) > 15_000_000:
        raise ApiError("문서 크기가 허용 범위를 벗어났습니다.", 413)
    intent_text = str(payload.get("intent") or "한글 문서를 원본 형식으로 열고 편집").strip()
    office_conversion = None
    if source_extension in {".docx", ".xlsx"}:
        parts = _extract_docx_parts(artifact) if source_extension == ".docx" else _extract_xlsx_parts(artifact)
        extracted = "\n\n".join(text for _index, text in parts).strip()
        if not extracted:
            raise ApiError("Office 문서에서 Markdown으로 변환할 내용을 찾지 못했습니다.", 415)
        markdown_text = "# " + Path(source_filename).stem + "\n\n" + extracted
        office_conversion = {"sourceFormat": source_extension[1:], "sections": len(parts), "externalTransfer": False}
        artifact, filename, extension = markdown_text.encode("utf-8"), Path(source_filename).stem + ".md", ".md"
    session_purpose = str(payload.get("session_purpose") or "document").strip()
    if session_purpose not in {"document", "template-authoring"}:
        raise ApiError("지원하지 않는 문서 편집 세션 목적입니다.")
    intent_analysis = INTENT_ANALYSIS_MCP.analyze(intent_text)
    intent_analysis["requestText"] = intent_text[:2_000]
    intent_analysis["sessionPurpose"] = session_purpose
    if session_purpose == "template-authoring":
        intent_analysis["builderDraftId"] = str(payload.get("builder_draft_id") or "")
        intent_analysis["builderReferenceId"] = str(payload.get("builder_reference_id") or "")
    rhwp_status = RHWP_AUTOMATION_MCP.runtime_status()
    if extension in text_formats:
        try:
            text_content = artifact.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ApiError("Markdown·코드 문서는 UTF-8이어야 합니다.") from error
        adapter_id, language = text_formats[extension]
        snapshot = {"kind": "text-editor", "language": language, "content": text_content}
        runtime = "browser-editor-plugin"
    elif rhwp_status["available"]:
        try:
            transformed = RHWP_AUTOMATION_MCP.invoke(
                "rhwp.document.transform",
                {"filename": filename, "contentBase64": base64.b64encode(artifact).decode("ascii"), "operations": []},
                ["document.write"],
                payload.get("confirmed") is True,
            )["result"]
        except RHWP_AUTOMATION_MCP.RhwpMcpError as error:
            raise ApiError(str(error), 503) from error
        artifact = base64.b64decode(transformed["contentBase64"], validate=True)
        snapshot = {"kind": "native-pdf", "previewPdfBase64": transformed["previewPdfBase64"]}
        adapter_id, runtime = "document.rhwp@1.0.0", "windows-native-bridge"
    elif extension == ".hwpx":
        parsed = parse_hwpx(artifact, filename)
        snapshot = {"kind": "structured-hwpx", "document": parsed}
        adapter_id, runtime = "document.hwpx@1.2.0", "server-python-fallback"
    else:
        if extension in {".hwp", ".hwt"} and not artifact.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            raise ApiError("유효한 HWP OLE 문서가 아닙니다.")
        if extension == ".hml" and b"<" not in artifact[:256]:
            raise ApiError("유효한 HML XML 문서가 아닙니다.")
        snapshot = {"kind": "rhwp-web", "sourceFormat": extension.removeprefix(".")}
        adapter_id, runtime = "document.rhwp-web@0.8.2", "browser-wasm"
    session_id = "docsession_" + uuid.uuid4().hex
    project_id = _safe_project_id(payload.get("project_id"))
    markdown_document_id = str(payload.get("markdown_document_id") or "")
    project_artifact_id = str(payload.get("project_artifact_id") or "")
    markdown_base_revision = payload.get("markdown_base_revision")
    canonical_markdown = str(payload.get("canonical_markdown") or "").strip()
    markdown_source = None
    if extension == ".hwpx" and session_purpose != "template-authoring":
        parsed_for_markdown = parse_hwpx(artifact, filename)
        markdown_source = hwpx_to_markdown(parsed_for_markdown, filename)
        if canonical_markdown:
            markdown_source["markdown"] = canonical_markdown
            markdown_source["title"] = _markdown_title(canonical_markdown, markdown_source["title"])
            markdown_source["sourceFormat"] = "markdown-rendered-hwpx"
    elif extension in {".md", ".txt"}:
        markdown_text = artifact.decode("utf-8")
        if extension == ".txt" and not re.search(r"(?m)^#\s+", markdown_text):
            markdown_text = "# " + Path(filename).stem + "\n\n" + markdown_text
        markdown_source = {"title": _markdown_title(markdown_text, Path(filename).stem), "markdown": markdown_text, "sourceFormat": extension.removeprefix("."), "sourceMap": []}
        if office_conversion:
            markdown_source.update({"sourceFormat": office_conversion["sourceFormat"], "conversion": office_conversion})
    now = utc_now()
    with _connect() as db:
        if project_artifact_id:
            linked_artifact = db.execute("SELECT * FROM project_document_artifacts WHERE id=?", (project_artifact_id,)).fetchone()
            if not linked_artifact or (markdown_document_id and linked_artifact["document_id"] != markdown_document_id):
                raise ApiError("프로젝트 파생 문서 연결이 올바르지 않습니다.", 409)
            markdown_document_id = linked_artifact["document_id"]
            markdown_base_revision = linked_artifact["source_revision"]
        if markdown_source:
            markdown_record = _save_project_markdown_version(
                db,
                project_id,
                markdown_source["markdown"],
                title=markdown_source["title"],
                document_id=markdown_document_id,
                expected_revision=payload.get("markdown_base_revision"),
                source_format=markdown_source["sourceFormat"],
                source_filename=source_filename,
                source_artifact_sha256=hashlib.sha256(artifact).hexdigest(),
                source_session_id=session_id,
                actor=_actor(payload),
            )
            markdown_document_id = markdown_record["id"]
            markdown_base_revision = markdown_record["revision"]
            snapshot["markdownSource"] = {"documentId": markdown_record["id"], "versionId": markdown_record["versionId"], "revision": markdown_record["revision"], "markdownSha256": markdown_record["markdownSha256"], "conversion": markdown_source.get("conversion") or {}}
        db.execute(
            "INSERT INTO native_document_sessions(id,actor,filename,format,adapter_id,runtime,status,revision,intent_json,snapshot_json,artifact_blob,artifact_sha256,created_at,updated_at,project_id,markdown_document_id,project_artifact_id,markdown_base_revision) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (session_id, _actor(payload), filename, extension.removeprefix("."), adapter_id, runtime, "active", 1, _json(intent_analysis), _json(snapshot), artifact, hashlib.sha256(artifact).hexdigest(), now, now, project_id, markdown_document_id or None, project_artifact_id or None, int(markdown_base_revision) if markdown_base_revision is not None else None),
        )
        _audit(db, _actor(payload), "document.session_opened", {"session_id": session_id, "project_id": project_id, "markdown_document_id": markdown_document_id or None, "filename": filename, "adapter": adapter_id, "runtime": runtime, "intent_type": intent_analysis["intentType"]})
        row = db.execute("SELECT * FROM native_document_sessions WHERE id=?", (session_id,)).fetchone()
    return _native_session_response(row)


def get_native_document_session(session_id: str, *, include_artifact: bool = False) -> dict:
    ensure_schema()
    with _connect() as db:
        row = db.execute("SELECT * FROM native_document_sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
        raise ApiError("문서 MCP 세션을 찾을 수 없습니다.", 404)
    return _native_session_response(row, include_artifact=include_artifact)


def command_native_document_session(session_id: str, payload: dict) -> dict:
    ensure_schema()
    with _connect() as db:
        row = db.execute("SELECT * FROM native_document_sessions WHERE id=?", (session_id,)).fetchone()
        linked_artifact = db.execute("SELECT * FROM project_document_artifacts WHERE id=?", (row["project_artifact_id"],)).fetchone() if row and row["project_artifact_id"] else None
        linked_document = db.execute("SELECT * FROM project_markdown_documents WHERE id=?", (row["markdown_document_id"],)).fetchone() if row and row["markdown_document_id"] else None
    if not row:
        raise ApiError("문서 MCP 세션을 찾을 수 없습니다.", 404)
    try:
        base_revision = int(payload.get("base_revision"))
    except (TypeError, ValueError) as error:
        raise ApiError("base_revision이 필요합니다.") from error
    if base_revision != row["revision"]:
        raise ApiError("문서 세션 revision이 변경되었습니다. 다시 불러와 주세요.", 409)
    if linked_artifact and linked_document and int(linked_document["current_revision"]) != int(row["markdown_base_revision"] or 0):
        raise ApiError("MD 원본이 다른 탭에서 변경되었습니다. HWPX 탭을 새로고침한 뒤 다시 편집해 주세요.", 409)
    command = str(payload.get("command") or "").strip()
    arguments = payload.get("arguments") or {}
    if command not in {"replace_selection", "replace_document", "replace_artifact", "set_fields", "action", "undo", "redo"} or not isinstance(arguments, dict):
        raise ApiError("지원하지 않는 문서 MCP 명령입니다.")
    artifact = bytes(row["artifact_blob"])
    parsed_before = parse_hwpx(artifact, row["filename"]) if linked_artifact and row["adapter_id"].startswith("document.hwpx") else None
    if row["adapter_id"] in {"document.markdown@1.0.0", "code.editor@1.0.0"}:
        try:
            current_text = artifact.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ApiError("세션 문서 인코딩이 올바르지 않습니다.", 409) from error
        if command == "replace_selection":
            before, after = str(arguments.get("before") or ""), str(arguments.get("after") or "")
            if not before or before not in current_text:
                raise ApiError("선택 원문이 현재 문서와 일치하지 않습니다.", 409)
            updated_text = current_text.replace(before, after, 1)
        elif command == "replace_document":
            updated_text = str(arguments.get("content") or "")
            if len(updated_text.encode("utf-8")) > 5_000_000:
                raise ApiError("텍스트 문서는 5MB를 넘을 수 없습니다.", 413)
        else:
            raise ApiError("이 편집기 MCP가 지원하지 않는 명령입니다.", 422)
        artifact = updated_text.encode("utf-8")
        language = {".md": "markdown", ".py": "python", ".js": "javascript", ".ts": "typescript", ".json": "json", ".txt": "text"}.get("." + row["format"], "text")
        snapshot = {"kind": "text-editor", "language": language, "content": updated_text}
        filename = row["filename"]
    elif row["adapter_id"].startswith("document.hwpx"):
        if command == "replace_artifact":
            try:
                candidate = base64.b64decode(str(arguments.get("contentBase64") or ""), validate=True)
            except (ValueError, TypeError) as error:
                raise ApiError("RHWP 산출물 contentBase64가 올바르지 않습니다.") from error
            if not candidate or len(candidate) > MAX_HWPX_BYTES:
                raise ApiError("RHWP 산출물 크기가 허용 범위를 벗어났습니다.", 413)
            requested_filename = str(arguments.get("filename") or "").strip()
            if requested_filename:
                if requested_filename != Path(requested_filename).name or Path(requested_filename).suffix.lower() != ".hwpx":
                    raise ApiError("양식 적용 결과는 안전한 HWPX 파일명이어야 합니다.")
                filename = requested_filename[:200]
            else:
                filename = _aiworks_hwpx_filename(row["filename"])
            parsed_candidate = parse_hwpx(candidate, filename)
            artifact = candidate
            snapshot = {"kind": "structured-hwpx", "document": parsed_candidate}
        elif command == "replace_selection":
            parsed = parse_hwpx(artifact, row["filename"])
            target = str(arguments.get("target") or "")
            before = str(arguments.get("before") or "")
            after = str(arguments.get("after") or "")
            result = apply_hwpx_document_patch({
                "filename": row["filename"],
                "document_id": parsed["document"]["id"],
                "content_base64": base64.b64encode(artifact).decode("ascii"),
                "actor": _actor(payload),
                "patch": {"op": "replace", "target": target, "expectedBefore": before, "after": after, "sourceSha256": parsed["document"]["sha256"], "sources": []},
            })
            artifact = base64.b64decode(result["contentBase64"], validate=True)
            snapshot = {"kind": "structured-hwpx", "document": parse_hwpx(artifact, result["filename"])}
            filename = result["filename"]
        else:
            raise ApiError("HWPX 편집기 MCP가 지원하지 않는 명령입니다.", 422)
    elif row["adapter_id"].startswith("document.rhwp-web"):
        if command != "replace_artifact":
            raise ApiError("RHWP Web 편집기 MCP는 현재 전체 산출물 저장만 지원합니다.", 422)
        try:
            candidate = base64.b64decode(str(arguments.get("contentBase64") or ""), validate=True)
        except (ValueError, TypeError) as error:
            raise ApiError("RHWP 산출물 contentBase64가 올바르지 않습니다.") from error
        if not candidate or len(candidate) > 15_000_000:
            raise ApiError("RHWP 산출물 크기가 허용 범위를 벗어났습니다.", 413)
        output_format = str(arguments.get("format") or row["format"]).lower()
        if output_format in {"hwp", "hwt"} and not candidate.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            raise ApiError("RHWP 산출물이 유효한 HWP OLE 형식이 아닙니다.")
        artifact = candidate
        filename = str(Path(row["filename"]).with_suffix("." + output_format))
        snapshot = {"kind": "rhwp-web", "sourceFormat": output_format}
    else:
        tool_map = {
            "replace_selection": ("rhwp.document.replace", {"find": arguments.get("before", ""), "replace": arguments.get("after", ""), "all": False}),
            "set_fields": ("rhwp.document.set_fields", {"values": arguments.get("values") or {}}),
            "action": ("rhwp.document.action", arguments),
            "undo": ("rhwp.document.undo", {}),
            "redo": ("rhwp.document.redo", {}),
        }
        operation_tool, operation_arguments = tool_map[command]
        try:
            transformed = RHWP_AUTOMATION_MCP.invoke(
                "rhwp.document.transform",
                {"filename": row["filename"], "contentBase64": base64.b64encode(artifact).decode("ascii"), "operations": [{"tool": operation_tool, "arguments": operation_arguments}]},
                ["document.write"],
                payload.get("confirmed") is True,
            )["result"]
        except RHWP_AUTOMATION_MCP.RhwpMcpError as error:
            raise ApiError(str(error), 503) from error
        artifact = base64.b64decode(transformed["contentBase64"], validate=True)
        snapshot = {"kind": "native-pdf", "previewPdfBase64": transformed["previewPdfBase64"]}
        filename = str(transformed.get("filename") or row["filename"])
    revision = row["revision"] + 1
    now = utc_now()
    digest = hashlib.sha256(artifact).hexdigest()
    project_id = _safe_project_id(row["project_id"] or DEFAULT_PROJECT_ID)
    markdown_document_id = str(row["markdown_document_id"] or "")
    semantic_changes = []
    synced_artifact = None
    deferred_artifact = None
    with _connect() as db:
        markdown_source = None
        if row["adapter_id"].startswith("document.hwpx") and markdown_document_id and payload.get("sync_markdown") is not True:
            current_markdown = _project_markdown_result(db, markdown_document_id)
            render_map = _load_json(linked_artifact["render_map_json"], {}) if linked_artifact else {}
            canonical_markdown = str(arguments.get("canonical_markdown") or "").strip()
            conversion = {"canonicalMarkdownPreserved": True} if canonical_markdown else {}
            if canonical_markdown:
                patched = canonical_markdown
            elif linked_artifact and command == "replace_selection":
                target = str(arguments.get("target") or "")
                mapping = next((item for item in render_map.get("entries") or [] if str(item.get("paragraphId") or "") == target), None)
                if not mapping:
                    raise ApiError("선택한 HWPX 문단이 MD 원본과 연결되어 있지 않습니다. MD 탭에서 수정해 주세요.", 409)
                patched = _semantic_patch_markdown(current_markdown["markdown"], mapping, str(arguments.get("before") or ""), str(arguments.get("after") or ""))
                semantic_changes = [{"paragraphId": target, "blockId": mapping.get("blockId"), "before": str(arguments.get("before") or ""), "after": str(arguments.get("after") or "")}]
                conversion = {"semanticPatch": True, "changes": semantic_changes}
            elif linked_artifact and command == "replace_artifact" and parsed_before is not None:
                parsed_after = parse_hwpx(artifact, filename)
                try:
                    patched, semantic_changes = _semantic_patch_from_hwpx_artifacts(current_markdown["markdown"], render_map, parsed_before, parsed_after)
                    conversion = {"semanticPatch": True, "changes": semantic_changes}
                except ApiError as error:
                    if error.status != 409:
                        raise
                    converted = hwpx_to_markdown(parsed_after, filename)
                    patched = converted["markdown"]
                    semantic_changes = [{"kind": "full-document-reimport", "reason": str(error)}]
                    conversion = {**(converted.get("conversion") or {}), "semanticPatch": False, "fullDocumentReimport": True, "reason": str(error)}
            else:
                converted = hwpx_to_markdown(parse_hwpx(artifact, filename), filename)
                patched = converted["markdown"]
                semantic_changes = [{"kind": "full-document-reimport", "reason": "연결된 Render Map이 없어 전체 의미 변환을 준비했습니다."}]
                conversion = {**(converted.get("conversion") or {}), "semanticPatch": False, "fullDocumentReimport": True}
            render_map["pendingPromotion"] = {
                "baseVersionId": current_markdown["versionId"],
                "baseRevision": current_markdown["revision"],
                "markdown": patched,
                "title": _markdown_title(patched, current_markdown["title"]),
                "sourceFormat": "hwpx-semantic-edit" if conversion.get("semanticPatch") else "hwpx-full-reimport",
                "conversion": conversion,
                "changes": semantic_changes,
                "preparedAt": now,
                "sessionId": session_id,
            }
            promotion_required = hashlib.sha256(str(patched).strip().encode("utf-8")).hexdigest() != current_markdown["markdownSha256"]
            if not promotion_required:
                render_map.pop("pendingPromotion", None)
            saved_hwpx_artifact = _upsert_project_artifact(
                db, current_markdown, target_format="hwpx", status="diverged" if promotion_required else "synced", data=artifact, filename=filename,
                media_type=str(linked_artifact["media_type"] or "application/hwp+zip") if linked_artifact else "application/hwp+zip",
                template_id=str(linked_artifact["template_id"] or "") if linked_artifact else "",
                renderer=str(linked_artifact["renderer"] or row["adapter_id"]) if linked_artifact else row["adapter_id"],
                instruction=str(linked_artifact["instruction"] or "") if linked_artifact else "",
                render_map=render_map, origin="hwpx-editor",
            )
            if promotion_required:
                deferred_artifact = saved_hwpx_artifact
                _record_document_sync_event(
                    db, project_id, markdown_document_id, "hwpx.saved-pending-markdown", origin="hwpx", status="diverged",
                    artifact_id=deferred_artifact["id"], source_version_id=current_markdown["versionId"],
                    detail={"sessionId": session_id, "changes": semantic_changes, "explicitPromotionRequired": True},
                )
            else:
                synced_artifact = saved_hwpx_artifact
        elif row["adapter_id"].startswith("document.hwpx"):
            canonical_markdown = str(arguments.get("canonical_markdown") or "").strip()
            if canonical_markdown:
                markdown_source = {"title": _markdown_title(canonical_markdown, Path(filename).stem), "markdown": canonical_markdown, "sourceFormat": "markdown-rendered-hwpx", "conversion": {"canonicalMarkdownPreserved": True}}
            elif linked_artifact and markdown_document_id:
                current_markdown = _project_markdown_result(db, markdown_document_id)
                render_map = _load_json(linked_artifact["render_map_json"], {})
                if command == "replace_selection":
                    target = str(arguments.get("target") or "")
                    mapping = next((item for item in render_map.get("entries") or [] if str(item.get("paragraphId") or "") == target), None)
                    if not mapping:
                        raise ApiError("선택한 HWPX 문단이 MD 원본과 연결되어 있지 않습니다. MD 탭에서 수정해 주세요.", 409)
                    patched = _semantic_patch_markdown(current_markdown["markdown"], mapping, str(arguments.get("before") or ""), str(arguments.get("after") or ""))
                    semantic_changes = [{"paragraphId": target, "blockId": mapping.get("blockId"), "before": str(arguments.get("before") or ""), "after": str(arguments.get("after") or "")}]
                    conversion = {"semanticPatch": True, "changes": semantic_changes}
                elif command == "replace_artifact" and parsed_before is not None:
                    parsed_after = parse_hwpx(artifact, filename)
                    try:
                        patched, semantic_changes = _semantic_patch_from_hwpx_artifacts(current_markdown["markdown"], render_map, parsed_before, parsed_after)
                        conversion = {"semanticPatch": True, "changes": semantic_changes}
                    except ApiError as error:
                        if error.status != 409:
                            raise
                        converted = hwpx_to_markdown(parsed_after, filename)
                        patched = converted["markdown"]
                        semantic_changes = [{"kind": "full-document-reimport", "reason": str(error)}]
                        conversion = {**(converted.get("conversion") or {}), "semanticPatch": False, "fullDocumentReimport": True, "reason": str(error)}
                else:
                    raise ApiError("이 HWPX 변경을 MD semantic patch로 변환할 수 없습니다.", 409)
                markdown_source = {"title": _markdown_title(patched, current_markdown["title"]), "markdown": patched, "sourceFormat": "hwpx-semantic-edit" if conversion.get("semanticPatch") else "hwpx-full-reimport", "conversion": conversion}
            else:
                parsed_for_markdown = parse_hwpx(artifact, filename)
                markdown_source = hwpx_to_markdown(parsed_for_markdown, filename)
                markdown_source["sourceFormat"] = "hwpx-edited"
        elif row["adapter_id"] == "document.markdown@1.0.0":
            text = artifact.decode("utf-8")
            markdown_source = {"title": _markdown_title(text, Path(filename).stem), "markdown": text, "sourceFormat": "markdown-edited", "conversion": {"nativeMarkdown": True}}
        if markdown_source:
            markdown_record = _save_project_markdown_version(
                db, project_id, markdown_source["markdown"], title=markdown_source["title"], document_id=markdown_document_id,
                source_format=markdown_source["sourceFormat"], source_filename=filename, source_artifact_sha256=digest,
                source_session_id=session_id, actor=_actor(payload),
            )
            markdown_document_id = markdown_record["id"]
            snapshot["markdownSource"] = {"documentId": markdown_record["id"], "versionId": markdown_record["versionId"], "revision": markdown_record["revision"], "markdownSha256": markdown_record["markdownSha256"], "conversion": markdown_source.get("conversion") or {}}
            if linked_artifact and row["adapter_id"].startswith("document.hwpx"):
                render_map = _load_json(linked_artifact["render_map_json"], {})
                changed_by_paragraph = {item["paragraphId"]: item["after"] for item in semantic_changes if item.get("paragraphId")}
                if conversion.get("fullDocumentReimport"):
                    reverse_document = REPORT_DOCUMENT_MCP.parse(markdown_source["markdown"], title=markdown_source["title"], style_profile="standard")
                    render_map = _build_hwpx_render_map(reverse_document, parse_hwpx(artifact, filename))
                    render_map["renderMode"] = "hwpx-full-document-reimport"
                else:
                    for entry in render_map.get("entries") or []:
                        if entry.get("paragraphId") in changed_by_paragraph:
                            entry["sourceText"] = _semantic_text(changed_by_paragraph[entry["paragraphId"]])
                            entry["canonicalText"] = _semantic_text(changed_by_paragraph[entry["paragraphId"]])
                synced_artifact = _upsert_project_artifact(
                    db, markdown_record, target_format="hwpx", status="synced", data=artifact, filename=filename,
                    media_type=str(linked_artifact["media_type"] or "application/hwp+zip"), template_id=str(linked_artifact["template_id"] or ""),
                    renderer=str(linked_artifact["renderer"] or row["adapter_id"]), instruction=str(linked_artifact["instruction"] or ""),
                    render_map=render_map, origin="hwpx",
                )
                _record_document_sync_event(
                    db, project_id, markdown_document_id, "hwpx.promoted-to-markdown", origin="hwpx", status="synced",
                    artifact_id=linked_artifact["id"], source_version_id=str(linked_artifact["source_version_id"] or ""), target_version_id=markdown_record["versionId"],
                    detail={"sessionId": session_id, "changes": semantic_changes},
                )
        markdown_base_revision = markdown_record["revision"] if markdown_source else row["markdown_base_revision"]
        project_artifact_id = (
            deferred_artifact["id"] if deferred_artifact
            else synced_artifact["id"] if synced_artifact
            else row["project_artifact_id"]
        )
        db.execute("UPDATE native_document_sessions SET filename=?,revision=?,snapshot_json=?,artifact_blob=?,artifact_sha256=?,updated_at=?,project_id=?,markdown_document_id=?,project_artifact_id=?,markdown_base_revision=? WHERE id=?", (filename, revision, _json(snapshot), artifact, digest, now, project_id, markdown_document_id or None, project_artifact_id, markdown_base_revision, session_id))
        _audit(db, _actor(payload), "document.session_command", {"session_id": session_id, "project_id": project_id, "markdown_document_id": markdown_document_id or None, "command": command, "adapter": row["adapter_id"], "revision": revision})
        updated = db.execute("SELECT * FROM native_document_sessions WHERE id=?", (session_id,)).fetchone()
    response = _native_session_response(updated)
    if synced_artifact:
        response["projectSync"] = {"status": "synced", "origin": "hwpx", "artifact": synced_artifact, "changes": semantic_changes}
    elif deferred_artifact:
        response["projectSync"] = {"status": "diverged", "origin": "hwpx", "artifact": deferred_artifact, "changes": semantic_changes, "explicitPromotionRequired": True}
    elif row["adapter_id"] == "document.markdown@1.0.0" and payload.get("auto_render") is True and markdown_document_id:
        try:
            rendered = render_project_markdown_document(project_id, markdown_document_id, {"format": "hwpx", "instruction": str(payload.get("instruction") or ""), "preserve_layout": payload.get("preserve_layout") is not False, "actor": _actor(payload)})
            response["projectSync"] = {"status": "synced", "origin": "markdown", "artifact": rendered.get("projectArtifact")}
        except ApiError as error:
            response["projectSync"] = {"status": "failed", "origin": "markdown", "error": str(error)}
    return response


def dispatch(subpath: str, method: str, payload: dict) -> dict:
    route = "/" + str(subpath or "/").strip("/")
    if route == "/bootstrap" and method == "GET":
        return bootstrap()
    if route == "/models" and method == "GET":
        return {
            "items": MODEL_MANAGEMENT_MCP.list_models(),
            "freeOnly": False,
            "defaultModel": MODEL_MANAGEMENT_MCP.select_model({"intentType": "information_query"})["model"]["id"],
            "openrouterConfigured": bool(_openrouter_key()),
        }
    if route == "/routing/analyze" and method == "POST":
        return analyze_and_route(
            str(payload.get("intent") or ""),
            str(payload.get("classification") or "internal"),
        )
    if route == "/routing/test" and method == "POST":
        return routing_test(payload)
    if route == "/plans" and method == "POST":
        return create_plan(payload)
    if route.startswith("/plans/") and method == "GET":
        return get_plan(route.removeprefix("/plans/"))
    if route == "/approvals" and method == "POST":
        return approve_plan(payload)
    if route == "/executions" and method == "POST":
        return execute_plan(payload)
    workflow_run_detail = re.fullmatch(r"/workflow-runs/(wfrun_[a-f0-9]+)", route)
    if workflow_run_detail and method == "GET":
        return get_workflow_run(workflow_run_detail.group(1))
    workflow_retry_plan = re.fullmatch(r"/workflow-runs/(wfrun_[a-f0-9]+)/retry-plan", route)
    if workflow_retry_plan and method == "POST":
        return create_workflow_retry_plan(workflow_retry_plan.group(1), payload)

    if route == "/audit" and method == "GET":
        return list_audit()
    if route == "/store/packages" and method == "GET":
        return list_store_packages()
    if route == "/store/install" and method == "POST":
        return install_mcp_package(payload)
    if route == "/store/rollback" and method == "POST":
        return rollback_mcp_package(payload)
    if route == "/store/edit" and method == "POST":
        return fork_mcp_package(payload)
    if route == "/store/delete" and method == "POST":
        return delete_mcp_package(payload)
    if route == "/store/configuration/get" and method == "POST":
        return get_mcp_configuration(payload)
    if route == "/store/configuration/save" and method == "POST":
        return save_mcp_configuration(payload)
    if route == "/capabilities/registry" and method == "GET":
        return list_capability_registry()
    if route == "/capabilities/resolve" and method == "POST":
        return resolve_capabilities(payload)
    if route == "/capabilities/evaluations" and method == "POST":
        return save_mcp_evaluation(payload)
    if route == "/builder/drafts" and method == "GET":
        return list_mcp_drafts()
    if route == "/builder/types" and method == "GET":
        return list_mcp_builder_types()
    if route == "/builder/template-starter" and method == "GET":
        return builder_template_starter()
    if route == "/builder/drafts" and method == "POST":
        return create_mcp_draft(payload)
    draft_template_sample = re.fullmatch(r"/builder/drafts/(draft_[a-f0-9]+)/template-sample", route)
    if draft_template_sample and method == "GET":
        return build_mcp_template_sample(draft_template_sample.group(1))
    draft_template_quality = re.fullmatch(r"/builder/drafts/(draft_[a-f0-9]+)/template-quality", route)
    if draft_template_quality and method == "GET":
        return evaluate_mcp_template_quality(draft_template_quality.group(1))
    draft_template_mapping = re.fullmatch(r"/builder/drafts/(draft_[a-f0-9]+)/template-mapping", route)
    if draft_template_mapping and method == "GET":
        return get_mcp_template_mapping(draft_template_mapping.group(1))
    if draft_template_mapping and method == "POST":
        return apply_mcp_template_mapping(draft_template_mapping.group(1), payload)
    draft_template_convert = re.fullmatch(r"/builder/drafts/(draft_[a-f0-9]+)/template-convert", route)
    if draft_template_convert and method == "POST":
        return convert_mcp_template_source(draft_template_convert.group(1), payload)
    draft_template_authoring = re.fullmatch(r"/builder/drafts/(draft_[a-f0-9]+)/template-authoring/(?P<action>session|commit)", route)
    if draft_template_authoring and method == "POST":
        draft_id = draft_template_authoring.group(1)
        if draft_template_authoring.group("action") == "session":
            return open_mcp_template_authoring_session(draft_id, payload)
        return commit_mcp_template_authoring(draft_id, payload)
    draft_detail = re.fullmatch(r"/builder/drafts/(draft_[a-f0-9]+)", route)
    if draft_detail and method == "GET":
        return get_mcp_draft(draft_detail.group(1))
    draft_reference = re.fullmatch(r"/builder/drafts/(draft_[a-f0-9]+)/references", route)
    if draft_reference and method == "POST":
        return add_mcp_draft_reference(draft_reference.group(1), payload)
    draft_reference_delete = re.fullmatch(r"/builder/drafts/(draft_[a-f0-9]+)/references/(ref_[a-f0-9]+)", route)
    if draft_reference_delete and method == "DELETE":
        return delete_mcp_draft_reference(draft_reference_delete.group(1), draft_reference_delete.group(2), payload)
    draft_rag_query = re.fullmatch(r"/builder/drafts/(draft_[a-f0-9]+)/rag/query", route)
    if draft_rag_query and method == "POST":
        return query_mcp_draft_rag(draft_rag_query.group(1), payload)
    draft_external_probe = re.fullmatch(r"/builder/drafts/(draft_[a-f0-9]+)/external/probe", route)
    if draft_external_probe and method == "POST":
        return probe_external_mcp_draft(draft_external_probe.group(1), payload)
    draft_action = re.fullmatch(r"/builder/drafts/(draft_[a-f0-9]+)/(?P<action>validate|publish)", route)
    if draft_action and method == "POST":
        draft_id = draft_action.group(1)
        if draft_action.group("action") == "validate":
            return validate_mcp_draft(draft_id, payload)
        return publish_mcp_draft(draft_id, payload)
    if route == "/knowledge/graph" and method == "GET":
        return knowledge_graph()
    if route == "/knowledge/query" and method == "POST":
        return query_knowledge(payload)
    if route == "/knowledge/compare" and method == "POST":
        return compare_knowledge_versions(payload)
    if route == "/knowledge/notes" and method == "POST":
        return create_knowledge_note(payload)
    if route == "/recipes" and method == "GET":
        return list_workflow_recipes(payload)
    if route == "/recipes/search" and method == "POST":
        return list_workflow_recipes(payload)
    if route == "/recipes" and method == "POST":
        return save_workflow_recipe(payload)
    recipe_fork = re.fullmatch(r"/recipes/([a-z0-9][a-z0-9._-]{2,119})/fork", route)
    if recipe_fork and method == "POST":
        return fork_workflow_recipe(recipe_fork.group(1), payload)
    recipe_deprecate = re.fullmatch(r"/recipes/([a-z0-9][a-z0-9._-]{2,119})/deprecate", route)
    if recipe_deprecate and method == "POST":
        return deprecate_workflow_recipe(recipe_deprecate.group(1), payload)
    project_recipe_install = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/recipes/([a-z0-9][a-z0-9._-]{2,119})/install", route)
    if project_recipe_install and method == "POST":
        return install_workflow_recipe(project_recipe_install.group(1), project_recipe_install.group(2), payload)
    project_recipe_list = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/recipes", route)
    if project_recipe_list and method == "GET":
        return list_workflow_recipes({**payload, "project_id": project_recipe_list.group(1)})
    if route == "/projects/archived" and method == "GET":
        return list_archived_projects(payload)
    if route == "/projects" and method == "GET":
        return list_projects()
    if route == "/projects" and method == "POST":
        return create_project(payload)
    if route == "/projects/import" and method == "POST":
        return import_project_backup(payload)
    project_backup = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/backup", route)
    if project_backup and method == "GET":
        return export_project_backup(project_backup.group(1), payload)
    project_governance = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/governance", route)
    if project_governance and method == "GET":
        return get_project_governance(project_governance.group(1), payload)
    project_member = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/members", route)
    if project_member and method == "POST":
        return save_project_member(project_member.group(1), payload)
    project_policy = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/policy", route)
    if project_policy and method == "POST":
        return save_project_policy(project_policy.group(1), payload)
    project_grant = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/grants", route)
    if project_grant and method == "POST":
        return save_permission_grant(project_grant.group(1), payload)
    project_status = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/status", route)
    if project_status and method == "POST":
        return change_project_status(project_status.group(1), payload)

    project_workspace = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/workspace", route)
    if project_workspace and method == "GET":
        return get_project_workspace(project_workspace.group(1))
    project_workspace_state = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/workspace-state", route)
    if project_workspace_state and method == "POST":
        return save_project_workspace_state(project_workspace_state.group(1), payload)
    project_facts = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/facts", route)
    if project_facts and method == "GET":
        return list_project_facts(project_facts.group(1))
    if project_facts and method == "POST":
        return save_project_fact(project_facts.group(1), payload)
    project_fact_decision = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/facts/(factvalue_[a-f0-9]+)/decision", route)
    if project_fact_decision and method == "POST":
        return decide_project_fact_candidate(project_fact_decision.group(1), project_fact_decision.group(2), payload)
    project_fact_bulk_decision = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/facts/decisions", route)
    if project_fact_bulk_decision and method == "POST":
        return decide_project_fact_candidates_bulk(project_fact_bulk_decision.group(1), payload)

    project_artifacts = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/artifacts", route)
    if project_artifacts and method == "GET":
        return list_project_artifacts(project_artifacts.group(1))
    if project_artifacts and method == "POST":
        return create_project_artifact(project_artifacts.group(1), payload)
    project_artifact_detail = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/artifacts/(gart_[a-f0-9]+)", route)
    if project_artifact_detail and method == "GET":
        return get_project_artifact(project_artifact_detail.group(1), project_artifact_detail.group(2), include_content=True)
    project_artifact_version = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/artifacts/(gart_[a-f0-9]+)/versions", route)
    if project_artifact_version and method == "POST":
        return append_project_artifact_version(project_artifact_version.group(1), project_artifact_version.group(2), payload)
    project_artifact_relation = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/artifact-relations", route)
    if project_artifact_relation and method == "POST":
        return create_project_artifact_relation(project_artifact_relation.group(1), payload)

    project_artifact_evidence = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/artifact-evidence", route)
    if project_artifact_evidence and method == "GET":
        return list_project_artifact_evidence(project_artifact_evidence.group(1), payload)
    if project_artifact_evidence and method == "POST":
        return create_project_artifact_evidence(project_artifact_evidence.group(1), payload)

    if route == "/document-format-adapters" and method == "GET":
        return project_document_format_adapters()
    project_markdown_documents = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/documents", route)
    if project_markdown_documents and method == "GET":
        return list_project_markdown_documents(project_markdown_documents.group(1))
    if project_markdown_documents and method == "POST":
        return save_project_markdown_document(project_markdown_documents.group(1), payload)
    project_markdown_status = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/documents/status", route)
    if project_markdown_status and method == "POST":
        return set_project_markdown_documents_status(project_markdown_status.group(1), payload)
    project_markdown_document = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/documents/(mdoc_[a-f0-9]+)", route)
    if project_markdown_document and method == "GET":
        return get_project_markdown_document(project_markdown_document.group(1), project_markdown_document.group(2))
    project_document_workbench = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/documents/(mdoc_[a-f0-9]+)/workbench", route)
    if project_document_workbench and method == "GET":
        return get_project_document_workbench(project_document_workbench.group(1), project_document_workbench.group(2))
    project_document_artifact = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/documents/(mdoc_[a-f0-9]+)/artifacts/(artifact_[a-f0-9]+)", route)
    if project_document_artifact and method == "GET":
        return get_project_document_artifact(project_document_artifact.group(1), project_document_artifact.group(2), project_document_artifact.group(3))
    project_document_promote = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/documents/(mdoc_[a-f0-9]+)/artifacts/(artifact_[a-f0-9]+)/promote-markdown", route)
    if project_document_promote and method == "POST":
        return promote_project_artifact_to_markdown(project_document_promote.group(1), project_document_promote.group(2), project_document_promote.group(3), payload)
    project_document_conflict = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/documents/(mdoc_[a-f0-9]+)/conflicts/(conflict_[a-f0-9]+)/resolve", route)
    if project_document_conflict and method == "POST":
        return resolve_project_document_conflict(project_document_conflict.group(1), project_document_conflict.group(2), project_document_conflict.group(3), payload)

    project_markdown_render = re.fullmatch(r"/projects/([A-Za-z0-9][A-Za-z0-9._-]{2,99})/documents/(mdoc_[a-f0-9]+)/render", route)
    if project_markdown_render and method == "POST":
        return render_project_markdown_document(project_markdown_render.group(1), project_markdown_render.group(2), payload)
    if route == "/workflows/presets" and method == "GET":
        return list_workflow_presets()
    if route == "/workflows/plan" and method == "POST":
        return create_workflow_plan(payload)
    if route == "/assets/inspect" and method == "POST":
        return inspect_asset(payload)
    if route == "/operations/readiness" and method == "GET":
        return operational_readiness()
    if route == "/rhwp/capabilities" and method == "GET":
        return rhwp_capabilities()
    if route == "/rhwp/invoke" and method == "POST":
        return invoke_rhwp(payload)
    if route == "/acceptance/budget-request" and method == "POST":
        return run_budget_acceptance(payload)
    if route == "/acceptance/runs" and method == "GET":
        return list_acceptance_runs()
    if route == "/documents/analyze-hwpx" and method == "POST":
        return analyze_hwpx(payload)
    if route == "/documents/apply-hwpx" and method == "POST":
        return apply_hwpx_document_patch(payload)
    if route == "/documents/versions" and method == "GET":
        return list_document_versions()
    document_version = re.fullmatch(r"/documents/versions/(docver_[a-f0-9]+)", route)
    if document_version and method == "GET":
        return get_document_version(document_version.group(1))
    if route == "/documents/workspace" and method == "GET":
        return list_workspace_documents()
    if route == "/documents/workspace" and method == "POST":
        return save_workspace_document(payload)
    if route == "/documents/sessions" and method == "POST":
        return open_native_document_session(payload)
    native_session = re.fullmatch(r"/documents/sessions/(docsession_[a-f0-9]+)", route)
    if native_session and method == "GET":
        return get_native_document_session(native_session.group(1))
    native_command = re.fullmatch(r"/documents/sessions/(docsession_[a-f0-9]+)/commands", route)
    if native_command and method == "POST":
        return command_native_document_session(native_command.group(1), payload)
    native_artifact = re.fullmatch(r"/documents/sessions/(docsession_[a-f0-9]+)/artifact", route)
    if native_artifact and method == "GET":
        return get_native_document_session(native_artifact.group(1), include_artifact=True)
    workspace_document = re.fullmatch(r"/documents/workspace/(workdoc_[a-f0-9]+)", route)
    if workspace_document and method == "GET":
        return get_workspace_document(workspace_document.group(1))
    raise ApiError("AIWorks API 경로를 찾을 수 없습니다.", 404)
