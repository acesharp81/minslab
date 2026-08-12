"""AIWorks server boundary: plans, approvals, executions, audit, and HWPX intake."""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import importlib.util
import json
import os
import re
import secrets
import sqlite3
import struct
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
TOKEN_TTL_SECONDS = max(60, min(3600, int(os.getenv("AIWORKS_APPROVAL_TTL_SECONDS", "600"))))
MAX_HWPX_BYTES = max(1_000_000, min(30_000_000, int(os.getenv("AIWORKS_MAX_HWPX_BYTES", "10000000"))))
MAX_UNCOMPRESSED_BYTES = 50_000_000
MAX_ASSET_BYTES = max(1_000_000, min(20_000_000, int(os.getenv("AIWORKS_MAX_ASSET_BYTES", "5000000"))))
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
                CREATE INDEX IF NOT EXISTS idx_mcp_history ON mcp_install_history(package_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_knowledge_source_node ON knowledge_sources(node_id);
                CREATE INDEX IF NOT EXISTS idx_knowledge_edge_source ON knowledge_edges(source_node_id);
                CREATE INDEX IF NOT EXISTS idx_acceptance_completed ON acceptance_runs(completed_at DESC);
                CREATE INDEX IF NOT EXISTS idx_mcp_draft_owner ON mcp_drafts(owner, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_mcp_draft_reference ON mcp_draft_references(draft_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_native_document_session_actor ON native_document_sessions(actor, updated_at DESC);
                """
            )
            plan_columns = {row["name"] for row in db.execute("PRAGMA table_info(plans)")}
            if "routing_json" not in plan_columns:
                db.execute("ALTER TABLE plans ADD COLUMN routing_json TEXT NOT NULL DEFAULT '{}'")
            document_version_columns = {row["name"] for row in db.execute("PRAGMA table_info(document_versions)")}
            if "content_blob" not in document_version_columns:
                db.execute("ALTER TABLE document_versions ADD COLUMN content_blob BLOB")
            _seed_mcp_store(db)
            _seed_knowledge(db)
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
    value = str(payload.get("actor") or "demo-user").strip()
    return value[:80] or "demo-user"


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


def _store_catalog() -> list[tuple[dict, str]]:
    return [
        (_package_manifest("document.hwpx", "HWPX 문서 어댑터", "1.2.0", "local", "HWPX 문단을 안전하게 읽고 변경합니다.", [("document.read", "문서 구조 분석"), ("document.write", "승인된 patch 적용")], supports=[".hwpx"]), "AIWorks Core"),
        (RHWP_AUTOMATION_MCP.MANIFEST, "AIWorks Core"),
        (_package_manifest("budget.form", "예산요청서 양식", "1.0.2", "local", "예산요청서 구조와 필수 항목을 검증합니다.", [("common-data.read", "예산 기준값 확인"), ("document.write", "예산 변경안 생성")]), "업무자동화팀"),
        (_package_manifest("budget.form", "예산요청서 양식", "1.0.3", "local", "예산요청서 구조와 필수 항목을 검증하고 초안을 생성합니다.", [("common-data.read", "예산 기준값 확인"), ("document.write", "예산 변경안 생성")]), "업무자동화팀"),
        (_package_manifest("budget.form", "예산요청서 양식", "1.0.4", "local", "예산요청서 초안 생성과 금액 형식 검증을 강화합니다.", [("common-data.read", "예산 기준값 확인"), ("document.write", "예산 변경안 생성")]), "업무자동화팀"),
        (_package_manifest("common-data.registry", "공통데이터 레지스트리", "1.1.0", "local", "기준일·출처·신뢰도를 포함한 업무 값을 관리합니다.", [("common-data.read", "현재 값 조회"), ("common-data.write", "승인된 값 저장")]), "AIWorks Core"),
        (_package_manifest("sw-cost", "SW 대가산정", "2.0.0", "hybrid", "SW사업 대가 기준으로 산출 근거를 계산합니다.", [("common-data.read", "대가 기준 조회"), ("network.send", "공개 기준 갱신")]), "공개 MCP"),
        (_package_manifest("sw-cost", "SW 대가산정", "2.1.0", "hybrid", "최신 SW사업 대가 기준과 검증 규칙을 적용합니다.", [("common-data.read", "대가 기준 조회"), ("network.send", "공개 기준 갱신")]), "공개 MCP"),
        (_package_manifest("citation.linker", "출처·인용 연결기", "0.9.4", "local", "생성 문장과 근거 문서 위치를 연결합니다.", [("document.read", "원문 위치 연결")]), "Knowledge Lab"),
        (_package_manifest("privacy.mask", "개인정보 마스킹", "1.4.1", "local", "외부 실행 전 개인정보를 탐지하고 마스킹합니다.", [("document.read", "개인정보 탐지")]), "Security Lab"),
        (_package_manifest("document.rewrite", "공문체 변경기", "1.0.0", "hybrid", "선택 문장을 공문체 변경안으로 생성합니다.", [("document.read", "선택 문장 읽기"), ("model.invoke", "문체 변경 모델 호출"), ("network.send", "승인된 선택 문장 전송")]), "AIWorks Core"),
    ]


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
        for package_id, version in (
            ("document.hwpx", "1.2.0"),
            ("budget.form", "1.0.3"),
            ("common-data.registry", "1.1.0"),
        ):
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
    return {
        "items": list(grouped.values()),
        "signature": {"algorithm": STORE_SIGNATURE_ALGORITHM, "keyId": STORE_KEY_ID},
        "installedCount": len(installations),
        "quarantined": quarantined,
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


def _reference_row_result(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "filename": row["filename"],
        "mediaType": row["media_type"],
        "bytes": row["bytes"],
        "sha256": row["sha256"],
        "summary": _load_json(row["summary_json"], {}),
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


def _inspect_builder_reference(filename: str, data: bytes) -> tuple[str, dict]:
    extension = Path(filename).suffix.lower()
    if extension == ".hwpx":
        parsed = parse_hwpx(data, filename)
        excerpt = "\n".join(item["text"] for item in parsed["paragraphs"][:8])[:2_000]
        return "application/hwp+zip", {
            "kind": "hwpx",
            "paragraphs": parsed["stats"]["paragraphs"],
            "commonDataCandidates": len(parsed["commonDataCandidates"]),
            "excerpt": excerpt,
        }
    if extension == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise ApiError("확장자와 PDF 파일 내용이 일치하지 않습니다.")
        if b"/Encrypt" in data:
            raise ApiError("암호화된 PDF는 기준 문서로 등록할 수 없습니다.", 415)
        pages = len(re.findall(rb"/Type\s*/Page\b", data))
        return "application/pdf", {
            "kind": "pdf",
            "pagesDetected": pages,
            "excerpt": "PDF 구조 확인 완료 · 텍스트 추출기는 후속 연결",
        }
    if extension in {".md", ".txt"}:
        if b"\x00" in data:
            raise ApiError("텍스트 기준 문서에 바이너리 데이터가 포함되어 있습니다.")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ApiError("텍스트 기준 문서는 UTF-8이어야 합니다.") from error
        return ("text/markdown" if extension == ".md" else "text/plain"), {
            "kind": "text",
            "lines": len(text.splitlines()),
            "characters": len(text),
            "excerpt": text[:2_000],
        }
    raise ApiError("기준 문서는 HWPX, PDF, Markdown 또는 TXT만 지원합니다.", 415)


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
        manifest = _load_json(draft["manifest_json"], {})
        manifest["references"] = [
            {
                "id": item["id"],
                "filename": item["filename"],
                "mediaType": item["media_type"],
                "bytes": item["bytes"],
                "sha256": item["sha256"],
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


def _builder_package_id(name: str, requested: str = "") -> str:
    if requested:
        package_id = requested.strip().lower()
    else:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        package_id = "org." + (slug or "mcp-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:10])
    if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", package_id):
        raise ApiError("MCP ID는 영문 소문자, 숫자, 점과 하이픈만 사용할 수 있습니다.")
    return package_id


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
    package_id = _builder_package_id(name, str(payload.get("package_id") or ""))
    lowered = description.lower()
    permissions = []

    def permission(scope: str, reason: str) -> None:
        if not any(item[0] == scope for item in permissions):
            permissions.append((scope, reason))

    document_work = any(term in lowered for term in ("문서", "예산", "양식", "hwpx", "pdf"))
    if document_work:
        permission("document.read", "입력 문서와 선택 영역 분석")
    if any(term in lowered for term in ("생성", "작성", "수정", "변경", "제안", "초안")):
        permission("document.write", "사용자 승인 후 변경안 생성")
    common_data = any(term in lowered for term in ("공통데이터", "기준값", "현재 값", "예산", "대가"))
    if common_data:
        permission("common-data.read", "업무 기준값과 출처 조회")
    if any(term in lowered for term in ("요약", "분석", "생성", "검증", "제안", "변경")):
        permission("model.invoke", "구조화된 업무 결과 생성")
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
    manifest["visibility"] = visibility
    manifest["sourceIncluded"] = source_included
    draft_id = "draft_" + uuid.uuid4().hex
    now = utc_now()
    validation = {"passed": False, "tests": []}
    owner = _actor(payload)
    with _connect() as db:
        db.execute("INSERT INTO mcp_drafts(id,owner,status,manifest_json,validation_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (draft_id, owner, "draft", _json(manifest), _json(validation), now, now))
        _audit(db, owner, "mcp.draft_created", {"draft_id": draft_id, "package_id": package_id, "visibility": visibility, "source_included": source_included})
        row = db.execute("SELECT * FROM mcp_drafts WHERE id=?", (draft_id,)).fetchone()
    return _draft_row_result(row)


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
        package_id, version = manifest["id"], manifest["version"]
        if db.execute("SELECT 1 FROM mcp_packages WHERE package_id=? AND version=?", (package_id, version)).fetchone():
            raise ApiError("동일한 MCP 버전이 이미 게시되어 있습니다.", 409)
        digest = _bundle_sha256(manifest)
        signature = _package_signature(package_id, version, digest)
        now = utc_now()
        db.execute("INSERT INTO mcp_packages(package_id,version,manifest_json,bundle_sha256,signature,publisher,published_at) VALUES(?,?,?,?,?,?,?)", (package_id, version, _json(manifest), digest, signature, actor, now))
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
        db.execute("UPDATE mcp_drafts SET status='published',published_package_id=?,published_version=?,updated_at=? WHERE id=?", (package_id, version, now, draft_id))
        _audit(db, actor, "mcp.draft_published", {"draft_id": draft_id, "package_id": package_id, "version": version, "visibility": manifest["visibility"], "source_included": manifest["sourceIncluded"], "bundle_sha256": digest, "signature_verified": True})
        package_row = db.execute("SELECT * FROM mcp_packages WHERE package_id=? AND version=?", (package_id, version)).fetchone()
        updated = db.execute("SELECT * FROM mcp_drafts WHERE id=?", (draft_id,)).fetchone()
    return {"draft": _draft_row_result(updated), "package": _verified_package(package_row)}


KNOWLEDGE_CLASSIFICATION_RANK = {"public": 0, "internal": 1, "confidential": 2, "personal": 3}


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


def _plan_steps(intent: str, route: dict) -> list[dict]:
    budget = "예산" in intent or "현재" in intent or "산출" in intent
    document_adapter = _installed_mcp_ref("document.hwpx", "1.2.0")
    common_data = _installed_mcp_ref("common-data.registry", "1.1.0")
    generator = _installed_mcp_ref("budget.form", "1.0.3") if budget else _installed_mcp_ref("document.rewrite", "1.0.0")
    return [
        {
            "id": "read-document",
            "mcp": document_adapter,
            "action": "read-selection",
            "model": None,
            "permissions": ["document.read"],
            "dependsOn": [],
        },
        {
            "id": "read-common-data",
            "mcp": common_data,
            "action": "resolve-current-values" if budget else "resolve-sources",
            "model": None,
            "permissions": ["common-data.read"],
            "dependsOn": ["read-document"],
        },
        {
            "id": "generate",
            "mcp": generator,
            "action": "generate-budget-patch" if budget else "rewrite-official-style",
            "model": route["model"]["id"],
            "permissions": ["model.invoke", "network.send"],
            "dependsOn": ["read-document", "read-common-data"],
        },
        {
            "id": "validate-patch",
            "mcp": document_adapter,
            "action": "validate-patch",
            "model": None,
            "permissions": ["document.write"],
            "dependsOn": ["generate"],
        },
    ]


def _installed_mcp_ref(package_id: str, fallback_version: str) -> str:
    with _connect() as db:
        row = db.execute(
            "SELECT pinned_version FROM mcp_installations WHERE package_id=? AND status='active'",
            (package_id,),
        ).fetchone()
    return package_id + "@" + (row["pinned_version"] if row else fallback_version)


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
    intent_analysis = INTENT_ANALYSIS_MCP.analyze(intent)
    route = MODEL_MANAGEMENT_MCP.select_model(intent_analysis, classification)
    if not route["classificationAllowed"]:
        raise ApiError("이 데이터 등급은 선택된 무료 외부 모델로 전송할 수 없습니다.", 403)
    steps = _plan_steps(intent, route)
    required = sorted({permission for step in steps for permission in step["permissions"]})
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
                1,
                _json(document_context.get("masked_fields") or []),
                _json(required),
                _json(steps),
                _json(document_context),
                _json({"intentAnalysis": intent_analysis, "route": route}),
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
                "external_transfer": True,
                "selected_model": route["model"]["id"],
                "intent_type": intent_analysis["intentType"],
            },
            plan_id=plan_id,
        )
    return {
        "id": plan_id,
        "intent": intent,
        "status": "awaiting-approval",
        "dataPolicy": {
            "classification": classification,
            "externalTransfer": True,
            "maskedFields": document_context.get("masked_fields") or [],
        },
        "requiredPermissions": required,
        "steps": steps,
        "intentAnalysis": intent_analysis,
        "routing": route,
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


def _openrouter_chat(model_id: str, messages: list[dict], max_tokens: int = 500) -> dict:
    if not model_id.endswith(":free"):
        raise ApiError("무료 variant가 아닌 모델 호출은 차단됩니다.", 403)
    key = _openrouter_key()
    if not key:
        raise ApiError("OPENROUTER_API_KEY가 설정되지 않았습니다.", 503)
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    request_payload = {
        "model": model_id,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max(32, min(1_000, int(max_tokens))),
    }
    if model_id == "openai/gpt-oss-20b:free":
        request_payload["reasoning"] = {"effort": "minimal", "exclude": True}
    body = _json(request_payload).encode("utf-8")
    request = url_request.Request(
        base_url + "/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv("AIWORKS_HTTP_REFERER", "https://minslab.local/poc/aiworks"),
            "X-Title": "AIWorks PoC",
        },
    )
    timeout = max(5, min(120, int(os.getenv("AIWORKS_OPENROUTER_TIMEOUT_SECONDS", "45"))))
    try:
        with url_request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except url_error.HTTPError as error:
        detail = error.read(2_000).decode("utf-8", "replace")
        raise ApiError(f"OpenRouter 호출 실패 ({error.code}): {detail}", 502) from error
    except (url_error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(f"OpenRouter 호출 실패: {error}", 502) from error
    choices = data.get("choices") or []
    content = ((choices[0].get("message") or {}).get("content") if choices else None)
    if not isinstance(content, str) or not content.strip():
        raise ApiError("OpenRouter 응답 내용이 비어 있습니다.", 502)
    return {
        "content": content.strip(),
        "requestedModel": model_id,
        "resolvedModel": data.get("model") or model_id,
        "usage": data.get("usage") or {},
        "requestId": data.get("id"),
    }


def analyze_and_route(intent: str, classification: str = "internal") -> dict:
    analysis = INTENT_ANALYSIS_MCP.analyze(intent)
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
            raise ApiError("이 데이터 등급은 무료 외부 모델 테스트에 사용할 수 없습니다.", 403)
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
                return {
                    "id": existing["id"],
                    "planId": plan_id,
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
    try:
        started_at = utc_now()
        live_model_enabled = os.getenv("AIWORKS_OPENROUTER_LIVE", "0").strip() == "1" and not force_local
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
        routing = _load_json(plan["routing_json"], {}).get("route", {})
        if live_model_enabled:
            model_id = (routing.get("model") or {}).get("id", "")
            selection_text = str(input_context.get("selection") or "")[:4_000]
            live = _openrouter_chat(
                model_id,
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
            )
            if live["content"].strip() == selection_text.strip():
                live = _openrouter_chat(
                    model_id,
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
                )
                if live["content"].strip() == selection_text.strip():
                    raise ApiError("모델이 두 번 연속 원문과 동일한 문장을 반환했습니다.", 502)
            result = _make_result(plan["intent"], input_context, routing)
            result["patches"][0]["after"] = live["content"]
            result["model"].update(
                {
                    "mode": "live",
                    "resolvedModel": live["resolvedModel"],
                    "usage": live["usage"],
                    "requestId": live["requestId"],
                }
            )
        else:
            result = _make_result(plan["intent"], input_context, routing)
        completed_at = utc_now()
        with _connect() as db:
            db.execute(
                "UPDATE executions SET status='completed', result_json=?, completed_at=? WHERE id=?",
                (_json(result), completed_at, execution_id),
            )
            db.execute("UPDATE plans SET status='completed', updated_at=? WHERE id=?", (completed_at, plan_id))
            _audit(
                db,
                "sandbox-executor",
                "execution.completed",
                {"patches": len(result["patches"]), "sources": len(result["sources"])},
                plan_id=plan_id,
                execution_id=execution_id,
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
        raise
    return {
        "id": execution_id,
        "planId": plan_id,
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
        add("knowledge.sources", "pass" if knowledge_sources else "fail", f"연결 출처 {knowledge_sources}개")
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
    free_models = [model for model in models if model["id"].endswith(":free") and model["price"]["input"] == 0 and model["price"]["output"] == 0]
    add("models.free-only", "pass" if len(free_models) == len(models) == 2 else "fail", f"무료 모델 {len(free_models)}개")
    add("approval.secret", "pass" if os.getenv("AIWORKS_APPROVAL_SECRET", "").strip() else "warn", "환경 전용 키 사용" if os.getenv("AIWORKS_APPROVAL_SECRET", "").strip() else "파생 개발 키 사용")
    add("store.signing-secret", "pass" if os.getenv("AIWORKS_STORE_SIGNING_SECRET", "").strip() else "warn", "분리된 서명 키 사용" if os.getenv("AIWORKS_STORE_SIGNING_SECRET", "").strip() else "승인 키에서 파생된 PoC 키 사용")
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
        plan = create_plan({"intent": "예산 산출 근거를 현재 기준으로 갱신해줘", "actor": actor, "document_context": {"document_id": inspected["document"]["id"], "classification": "internal", "selection_id": first["id"]}})
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
        "version": "0.17.0",
        "runtime": "local-sandbox",
        "models": MODEL_MANAGEMENT_MCP.list_models(),
        "mcp": {
            "intentAnalysis": INTENT_ANALYSIS_MCP.MANIFEST,
            "modelManagement": MODEL_MANAGEMENT_MCP.MANIFEST,
            "rhwpAutomation": RHWP_AUTOMATION_MCP.MANIFEST,
        },
        "openrouter": {
            "configured": bool(_openrouter_key()),
            "liveExecutionEnabled": os.getenv("AIWORKS_OPENROUTER_LIVE", "0").strip() == "1",
            "freeOnly": True,
        },
        "policies": {
            "externalTransferDefault": False,
            "approvalRequired": True,
            "approvalTokenTtlSeconds": TOKEN_TTL_SECONDS,
            "auditPersistent": True,
        },
        "capabilities": {"workflowPresets": len(WORKFLOW_PRESETS), "adapters": len(CAPABILITY_ADAPTERS), "maxAssetBytes": MAX_ASSET_BYTES, "acceptanceScenario": "budget-request-e2e", "mcpBuilder": True, "builderReferenceFormats": [".hwpx", ".pdf", ".md", ".txt"], "workspaceDocuments": True, "nativeDocumentSessions": True, "downloadableDocumentVersions": True, "rhwp": RHWP_AUTOMATION_MCP.runtime_status()},
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
                item = {"id": paragraph_id, "text": text[:10_000]}
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
    budget_intent = any(signal in {"예산", "산출", "계산", "최신 기준"} for signal in analysis.get("matchedSignals", []))
    loaded_mcps = ["core.intent-analysis@0.1.0", requested_adapter]
    if budget_intent:
        loaded_mcps.extend(["budget.form@1.0.3", "common-data.registry@1.1.0", "sw-cost@2.1.0"])
    result = {
        "id": row["id"],
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
    text_formats = {".md": ("document.markdown@1.0.0", "markdown"), ".py": ("code.editor@1.0.0", "python"), ".js": ("code.editor@1.0.0", "javascript"), ".ts": ("code.editor@1.0.0", "typescript"), ".json": ("code.editor@1.0.0", "json"), ".txt": ("document.markdown@1.0.0", "text")}
    if extension not in {".hwp", ".hwpx", ".hwt", ".hml"} | set(text_formats):
        raise ApiError("지원하는 편집기 MCP가 없는 파일 형식입니다.", 415)
    try:
        artifact = base64.b64decode(str(payload.get("content_base64") or ""), validate=True)
    except (ValueError, TypeError) as error:
        raise ApiError("문서 content_base64가 올바르지 않습니다.") from error
    if not artifact or len(artifact) > 15_000_000:
        raise ApiError("문서 크기가 허용 범위를 벗어났습니다.", 413)
    intent_text = str(payload.get("intent") or "한글 문서를 원본 형식으로 열고 편집").strip()
    intent_analysis = INTENT_ANALYSIS_MCP.analyze(intent_text)
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
    now = utc_now()
    with _connect() as db:
        db.execute(
            "INSERT INTO native_document_sessions(id,actor,filename,format,adapter_id,runtime,status,revision,intent_json,snapshot_json,artifact_blob,artifact_sha256,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (session_id, _actor(payload), filename, extension.removeprefix("."), adapter_id, runtime, "active", 1, _json(intent_analysis), _json(snapshot), artifact, hashlib.sha256(artifact).hexdigest(), now, now),
        )
        _audit(db, _actor(payload), "document.session_opened", {"session_id": session_id, "filename": filename, "adapter": adapter_id, "runtime": runtime, "intent_type": intent_analysis["intentType"]})
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
    if not row:
        raise ApiError("문서 MCP 세션을 찾을 수 없습니다.", 404)
    try:
        base_revision = int(payload.get("base_revision"))
    except (TypeError, ValueError) as error:
        raise ApiError("base_revision이 필요합니다.") from error
    if base_revision != row["revision"]:
        raise ApiError("문서 세션 revision이 변경되었습니다. 다시 불러와 주세요.", 409)
    command = str(payload.get("command") or "").strip()
    arguments = payload.get("arguments") or {}
    if command not in {"replace_selection", "replace_document", "replace_artifact", "set_fields", "action", "undo", "redo"} or not isinstance(arguments, dict):
        raise ApiError("지원하지 않는 문서 MCP 명령입니다.")
    artifact = bytes(row["artifact_blob"])
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
    with _connect() as db:
        db.execute("UPDATE native_document_sessions SET filename=?,revision=?,snapshot_json=?,artifact_blob=?,artifact_sha256=?,updated_at=? WHERE id=?", (filename, revision, _json(snapshot), artifact, digest, now, session_id))
        _audit(db, _actor(payload), "document.session_command", {"session_id": session_id, "command": command, "adapter": row["adapter_id"], "revision": revision})
        updated = db.execute("SELECT * FROM native_document_sessions WHERE id=?", (session_id,)).fetchone()
    return _native_session_response(updated)


def dispatch(subpath: str, method: str, payload: dict) -> dict:
    route = "/" + str(subpath or "/").strip("/")
    if route == "/bootstrap" and method == "GET":
        return bootstrap()
    if route == "/models" and method == "GET":
        return {
            "items": MODEL_MANAGEMENT_MCP.list_models(),
            "freeOnly": True,
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
    if route == "/audit" and method == "GET":
        return list_audit()
    if route == "/store/packages" and method == "GET":
        return list_store_packages()
    if route == "/store/install" and method == "POST":
        return install_mcp_package(payload)
    if route == "/store/rollback" and method == "POST":
        return rollback_mcp_package(payload)
    if route == "/builder/drafts" and method == "GET":
        return list_mcp_drafts()
    if route == "/builder/drafts" and method == "POST":
        return create_mcp_draft(payload)
    draft_detail = re.fullmatch(r"/builder/drafts/(draft_[a-f0-9]+)", route)
    if draft_detail and method == "GET":
        return get_mcp_draft(draft_detail.group(1))
    draft_reference = re.fullmatch(r"/builder/drafts/(draft_[a-f0-9]+)/references", route)
    if draft_reference and method == "POST":
        return add_mcp_draft_reference(draft_reference.group(1), payload)
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
