"""Remove known AIWorks browser/HTTP fixtures without touching user MCP data.

Dry-run is the default. ``--apply`` creates an online SQLite backup first and
then removes only records matching the explicit fixture identities below.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "aiworks.sqlite3"
DEFAULT_PROJECT = "project-default"

TEST_DOCUMENT_TITLES = {
    "워크벤치 브라우저 검증",
    "Markdown 원본 수용성 검토",
    "사업계획",
    "품목번호",
    "분석 및 시사점 보고서",
}
TEST_DOCUMENT_PREFIXES = ("브라우저에서 HWPX 파일을 직접 편집",)
TEST_SESSION_PREFIXES = (
    "browser-sample",
    "native-selection",
    "browser-plan",
    "form-002",
    "Budget policy total amount",
)
TEST_DRAFT_OWNERS = {"http-v010-test", "http-builder-test"}
TEST_DRAFT_PACKAGES = {"org.browser-mois-template"}
TEST_PACKAGE_IDS = {"org.policy-budget-review", "org.budget-evidence-checker", "budget.form", "sw-cost"}
TEST_PLAN_ACTORS = {
    "smoke-test",
    "integration-test",
    "http-acceptance-test",
    "routing-smoke",
    "local-acceptance",
    "http-store-test",
    "acceptance",
}
TEST_PLAN_INTENTS = {
    "선택한 글귀를 보다 공손한 어투로 바꿔줘",
    "선택한 글귀를 공손하게 바꿔줘",
    "선택 문장을 2줄 공문체로 정리해줘",
    "우리부 예산 현황을 확인하고 요약해줘",
    "Budget policy total amount 조회해줘",
    "예산요청서 초안을 완성해줘",
    "현재 기준값으로 예산 산출 근거를 갱신해줘",
}
TEST_AUDIT_ACTORS = TEST_PLAN_ACTORS | {
    "browser-smoke",
    "http-v010-test",
    "http-builder-test",
    "http-multimodal-test",
    "http-test",
    "http-knowledge-test",
}
TEST_KNOWLEDGE_NODE_IDS = {
    "data:cost.engineer.monthly",
    "data:project.name",
    "data:project.period",
    "document:doc-budget-2027-01",
    "document:sw-cost-guide-2025",
    "document:sw-cost-guide-2026",
    "note:budget-cost-assumption",
}


def placeholders(values: set[str] | list[str]) -> str:
    return ",".join("?" for _ in values)


def fixture_document_ids(db: sqlite3.Connection) -> list[str]:
    rows = db.execute(
        "SELECT id,title FROM project_markdown_documents WHERE project_id=?",
        (DEFAULT_PROJECT,),
    ).fetchall()
    return [
        row["id"]
        for row in rows
        if row["title"] in TEST_DOCUMENT_TITLES
        or any(row["title"].startswith(prefix) for prefix in TEST_DOCUMENT_PREFIXES)
    ]


def fixture_draft_ids(db: sqlite3.Connection) -> list[str]:
    result = []
    for row in db.execute("SELECT id,owner,manifest_json FROM mcp_drafts"):
        manifest = json.loads(row["manifest_json"] or "{}")
        package_id = manifest.get("id") or manifest.get("packageId")
        if row["owner"] in TEST_DRAFT_OWNERS or package_id in TEST_DRAFT_PACKAGES:
            result.append(row["id"])
    return result


def preview(db: sqlite3.Connection) -> dict:
    document_ids = fixture_document_ids(db)
    draft_ids = fixture_draft_ids(db)
    return {
        "database": str(Path(db.execute("PRAGMA database_list").fetchone()[2]).resolve()),
        "documents": [
            dict(row)
            for row in db.execute(
                f"SELECT id,title,current_revision FROM project_markdown_documents WHERE id IN ({placeholders(document_ids)}) ORDER BY updated_at DESC",
                document_ids,
            )
        ] if document_ids else [],
        "workspaceDocuments": db.execute(
            "SELECT COUNT(*) FROM workspace_documents WHERE name='2027년도 신규사업 예산요청서'"
        ).fetchone()[0],
        "defaultProjectFacts": db.execute(
            "SELECT COUNT(*) FROM project_facts WHERE project_id=?", (DEFAULT_PROJECT,)
        ).fetchone()[0],
        "unlinkedBrowserSessions": db.execute(
            "SELECT COUNT(*) FROM native_document_sessions WHERE project_id IS NULL AND ("
            + " OR ".join("filename LIKE ?" for _ in TEST_SESSION_PREFIXES) + ")",
            [prefix + "%" for prefix in TEST_SESSION_PREFIXES],
        ).fetchone()[0],
        "draftIds": draft_ids,
        "packageIds": [
            row[0]
            for row in db.execute(
                f"SELECT DISTINCT package_id FROM mcp_packages WHERE package_id IN ({placeholders(TEST_PACKAGE_IDS)}) ORDER BY package_id",
                sorted(TEST_PACKAGE_IDS),
            )
        ],
        "testPlanCount": db.execute(
            f"SELECT COUNT(*) FROM plans WHERE actor IN ({placeholders(TEST_PLAN_ACTORS)}) OR intent IN ({placeholders(TEST_PLAN_INTENTS)})",
            sorted(TEST_PLAN_ACTORS) + sorted(TEST_PLAN_INTENTS),
        ).fetchone()[0],
        "testAcceptanceRuns": db.execute("SELECT COUNT(*) FROM acceptance_runs").fetchone()[0],
        "legacyBrowserVersions": db.execute(
            "SELECT COUNT(*) FROM document_versions WHERE filename LIKE 'browser-sample%' OR filename LIKE '워크벤치_브라우저_검증%' OR filename='acceptance-budget_AIWorks.hwpx'"
        ).fetchone()[0],
    }


def backup_database(source: sqlite3.Connection, db_path: Path) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"{db_path.stem}-before-test-cleanup-{stamp}.sqlite3"
    destination = sqlite3.connect(backup_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
    return backup_path


def cleanup(db: sqlite3.Connection) -> dict:
    before = db.total_changes
    document_ids = fixture_document_ids(db)
    draft_ids = fixture_draft_ids(db)

    if document_ids:
        marks = placeholders(document_ids)
        db.execute(f"DELETE FROM native_document_sessions WHERE markdown_document_id IN ({marks})", document_ids)
        db.execute(f"DELETE FROM project_document_sync_events WHERE document_id IN ({marks})", document_ids)
        db.execute(f"DELETE FROM project_document_artifacts WHERE document_id IN ({marks})", document_ids)
        db.execute(f"DELETE FROM project_fact_values WHERE source_document_id IN ({marks})", document_ids)
        db.execute(f"DELETE FROM project_markdown_versions WHERE document_id IN ({marks})", document_ids)
        db.execute(f"DELETE FROM project_markdown_documents WHERE id IN ({marks})", document_ids)

    db.execute(
        "DELETE FROM native_document_sessions WHERE project_id IS NULL AND ("
        + " OR ".join("filename LIKE ?" for _ in TEST_SESSION_PREFIXES) + ")",
        [prefix + "%" for prefix in TEST_SESSION_PREFIXES],
    )
    db.execute("DELETE FROM workspace_documents WHERE name='2027년도 신규사업 예산요청서'")

    default_fact_ids = [
        row[0] for row in db.execute("SELECT id FROM project_facts WHERE project_id=?", (DEFAULT_PROJECT,))
    ]
    if default_fact_ids:
        marks = placeholders(default_fact_ids)
        db.execute(f"DELETE FROM project_fact_values WHERE fact_id IN ({marks})", default_fact_ids)
        db.execute(f"DELETE FROM project_facts WHERE id IN ({marks})", default_fact_ids)

    if draft_ids:
        marks = placeholders(draft_ids)
        db.execute(f"DELETE FROM mcp_draft_references WHERE draft_id IN ({marks})", draft_ids)
        db.execute(f"DELETE FROM mcp_drafts WHERE id IN ({marks})", draft_ids)

    for package_id in TEST_PACKAGE_IDS:
        db.execute("DELETE FROM mcp_reference_chunks WHERE package_id=?", (package_id,))
        db.execute("DELETE FROM mcp_package_files WHERE package_id=?", (package_id,))
        db.execute("DELETE FROM mcp_capabilities WHERE package_id=?", (package_id,))
        db.execute("DELETE FROM mcp_configurations WHERE package_id=?", (package_id,))
        db.execute("DELETE FROM mcp_install_history WHERE package_id=?", (package_id,))
        db.execute("DELETE FROM mcp_installations WHERE package_id=?", (package_id,))
        db.execute("DELETE FROM mcp_packages WHERE package_id=?", (package_id,))

    plan_ids = [
        row[0]
        for row in db.execute(
            f"SELECT id FROM plans WHERE actor IN ({placeholders(TEST_PLAN_ACTORS)}) OR intent IN ({placeholders(TEST_PLAN_INTENTS)})",
            sorted(TEST_PLAN_ACTORS) + sorted(TEST_PLAN_INTENTS),
        )
    ]
    if plan_ids:
        marks = placeholders(plan_ids)
        execution_ids = [row[0] for row in db.execute(f"SELECT id FROM executions WHERE plan_id IN ({marks})", plan_ids)]
        if execution_ids:
            execution_marks = placeholders(execution_ids)
            db.execute(f"DELETE FROM audit_events WHERE execution_id IN ({execution_marks})", execution_ids)
        db.execute(f"DELETE FROM audit_events WHERE plan_id IN ({marks})", plan_ids)
        db.execute(f"DELETE FROM approvals WHERE plan_id IN ({marks})", plan_ids)
        db.execute(f"DELETE FROM executions WHERE plan_id IN ({marks})", plan_ids)
        db.execute(f"DELETE FROM plans WHERE id IN ({marks})", plan_ids)
    db.execute(
        f"DELETE FROM audit_events WHERE actor IN ({placeholders(TEST_AUDIT_ACTORS)})",
        sorted(TEST_AUDIT_ACTORS),
    )
    db.execute("DELETE FROM acceptance_runs")
    db.execute(
        "DELETE FROM document_versions WHERE created_by IN ('http-test','http-acceptance-test') OR filename LIKE 'browser-sample%' OR filename LIKE '워크벤치_브라우저_검증%' OR filename='acceptance-budget_AIWorks.hwpx'"
    )

    knowledge_ids = sorted(TEST_KNOWLEDGE_NODE_IDS)
    test_note_ids = [row[0] for row in db.execute("SELECT id FROM knowledge_nodes WHERE title='HTTP 통합 검증 메모'")]
    knowledge_ids.extend(test_note_ids)
    if knowledge_ids:
        marks = placeholders(knowledge_ids)
        source_ids = [row[0] for row in db.execute(f"SELECT id FROM knowledge_sources WHERE node_id IN ({marks})", knowledge_ids)]
        if source_ids:
            source_marks = placeholders(source_ids)
            db.execute(f"DELETE FROM knowledge_edges WHERE evidence_source_id IN ({source_marks})", source_ids)
        db.execute(f"DELETE FROM knowledge_edges WHERE source_node_id IN ({marks}) OR target_node_id IN ({marks})", knowledge_ids * 2)
        db.execute(f"DELETE FROM knowledge_sources WHERE node_id IN ({marks})", knowledge_ids)
        db.execute(f"DELETE FROM knowledge_nodes WHERE id IN ({marks})", knowledge_ids)

    existing = {
        "plans": {row[0] for row in db.execute("SELECT id FROM plans")},
        "executions": {row[0] for row in db.execute("SELECT id FROM executions")},
        "sessions": {row[0] for row in db.execute("SELECT id FROM native_document_sessions")},
        "markdownDocuments": {row[0] for row in db.execute("SELECT id FROM project_markdown_documents")},
        "markdownVersions": {row[0] for row in db.execute("SELECT id FROM project_markdown_versions")},
        "workspaceDocuments": {row[0] for row in db.execute("SELECT id FROM workspace_documents")},
        "documentVersions": {row[0] for row in db.execute("SELECT id FROM document_versions")},
        "drafts": {row[0] for row in db.execute("SELECT id FROM mcp_drafts")},
        "packages": {row[0] for row in db.execute("SELECT DISTINCT package_id FROM mcp_packages")},
    }
    orphan_audit_ids = []
    for row in db.execute("SELECT id,execution_id,plan_id,detail_json FROM audit_events"):
        detail = json.loads(row["detail_json"] or "{}")
        orphan = bool(row["plan_id"] and row["plan_id"] not in existing["plans"])
        orphan = orphan or bool(row["execution_id"] and row["execution_id"] not in existing["executions"])
        references = (
            ("session_id", "sessions", "docsession_"),
            ("markdown_document_id", "markdownDocuments", "mdoc_"),
            ("document_id", "markdownDocuments", "mdoc_"),
            ("document_id", "workspaceDocuments", "workdoc_"),
            ("version_id", "markdownVersions", "mdver_"),
            ("version_id", "documentVersions", "docver_"),
            ("draft_id", "drafts", "draft_"),
            ("package_id", "packages", "org."),
        )
        for key, collection, prefix in references:
            value = str(detail.get(key) or "")
            if value.startswith(prefix) and value not in existing[collection]:
                orphan = True
                break
        if orphan:
            orphan_audit_ids.append(row["id"])
    if orphan_audit_ids:
        for offset in range(0, len(orphan_audit_ids), 500):
            batch = orphan_audit_ids[offset:offset + 500]
            db.execute(f"DELETE FROM audit_events WHERE id IN ({placeholders(batch)})", batch)

    active_document = db.execute(
        "SELECT id FROM project_markdown_documents WHERE project_id=? AND status='active' ORDER BY updated_at DESC LIMIT 1",
        (DEFAULT_PROJECT,),
    ).fetchone()
    db.execute(
        "UPDATE project_workspace_states SET active_document_id=?,active_tab='markdown',active_view='editor',chat_json='[]',last_answer='',updated_by='test-data-cleanup',updated_at=? WHERE project_id=?",
        (
            active_document[0] if active_document else None,
            datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            DEFAULT_PROJECT,
        ),
    )
    db.execute("DELETE FROM project_facts WHERE status='candidate' AND NOT EXISTS (SELECT 1 FROM project_fact_values v WHERE v.fact_id=project_facts.id)")
    return {"changedRows": db.total_changes - before, "removedDocumentIds": document_ids}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    db_path = args.db.expanduser().resolve()
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        report = {"mode": "apply" if args.apply else "dry-run", "preview": preview(connection)}
        if args.apply:
            report["backup"] = str(backup_database(connection, db_path))
            with connection:
                report["result"] = cleanup(connection)
            report["after"] = preview(connection)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
