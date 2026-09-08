"""Deterministic Golden Workflow runner for AI Work Hub Phase 1."""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = Path(__file__).resolve().parent / "budget_business_review" / "workflow.json"


def load_spec(path: Path) -> dict:
    spec = json.loads(path.read_text(encoding="utf-8"))
    required = {"contractVersion", "id", "title", "project", "intent", "sourceFiles", "expectations"}
    missing = sorted(required - set(spec))
    if missing:
        raise ValueError("Golden Workflow 필수 필드가 없습니다: " + ", ".join(missing))
    if spec["contractVersion"] != "golden-workflow/1.0":
        raise ValueError("지원하지 않는 Golden Workflow 계약 버전입니다.")
    if not isinstance(spec["sourceFiles"], list) or not spec["sourceFiles"]:
        raise ValueError("Golden Workflow에는 한 개 이상의 sourceFiles가 필요합니다.")
    return spec


def _fixture_path(spec_path: Path, relative: str) -> Path:
    scenario_root = spec_path.resolve().parent
    candidate = (scenario_root / relative).resolve()
    if not candidate.is_relative_to(scenario_root) or not candidate.is_file():
        raise ValueError("Golden fixture 경로가 시나리오 밖이거나 존재하지 않습니다: " + relative)
    return candidate


def run(backend, spec_path: Path = DEFAULT_SPEC) -> dict:
    spec_path = Path(spec_path).resolve()
    spec = load_spec(spec_path)
    checks: list[dict] = []
    artifacts: dict = {}

    def check(check_id: str, passed: bool, detail: str) -> bool:
        checks.append({"id": check_id, "passed": bool(passed), "detail": str(detail)})
        return bool(passed)

    try:
        actor = "golden-workflow-runner"
        project = backend.create_project({**spec["project"], "actor": actor})
        source_ids = []
        for item in spec["sourceFiles"]:
            source_path = _fixture_path(spec_path, item["path"])
            created = backend.create_project_source(
                project["id"],
                {
                    "filename": item["filename"],
                    "classification": item["classification"],
                    "content_base64": base64.b64encode(source_path.read_bytes()).decode("ascii"),
                    "actor": actor,
                },
            )["source"]
            source_ids.append(created["id"])
            check("source." + created["id"], created["ragReady"] and created["chunkCount"] > 0, item["filename"])

        expected = spec["expectations"]
        retrieval = backend.query_project_sources(
            project["id"],
            {"question": spec.get("retrievalQuestion") or spec["intent"], "source_ids": source_ids, "top_k": 6},
        )
        retrieval_text = " ".join(item.get("excerpt") or "" for item in retrieval["sources"])
        check(
            "retrieval.minimum-sources",
            retrieval["retrievedChunks"] >= expected["retrieval"]["minimumSources"],
            f"검색 근거 {retrieval['retrievedChunks']}건",
        )
        for term in expected["retrieval"]["requiredTerms"]:
            check("retrieval.term." + term, term in retrieval_text, term)

        plan = backend.create_plan(
            {
                "intent": spec["intent"],
                "actor": actor,
                "document_context": {
                    "classification": spec["project"]["classification"],
                    "project_id": project["id"],
                    "project_source_ids": source_ids,
                },
            }
        )
        plan_expected = expected["plan"]
        check("plan.response-type", plan["workflow"]["responseType"] == plan_expected["responseType"], plan["workflow"]["responseType"])
        check("plan.no-external-transfer", plan["dataPolicy"]["externalTransfer"] == plan_expected["externalTransfer"], str(plan["dataPolicy"]))
        loaded = set(plan["workflow"].get("loadedMcps") or [])
        for package_ref in plan_expected["requiredPackageRefs"]:
            check("plan.package." + package_ref, package_ref in loaded, package_ref)
        check("plan.task-contract", plan["workflow"]["taskContract"]["valid"], "고정 버전 Task 계약")
        check("plan.capability-dag", plan["workflow"]["capabilityDag"]["valid"], "Artifact I/O 연결")

        approval = backend.approve_plan(
            {"plan_id": plan["id"], "actor": actor, "permissions": plan["requiredPermissions"]}
        )
        check("approval.single-use", approval["lease"]["consumableOnce"], approval["lease"]["type"])
        execution = backend.execute_plan(
            {
                "approval_token": approval["approvalToken"],
                "idempotency_key": "golden-" + spec["id"],
                "input": {},
            },
            force_local=True,
        )
        result = execution["result"]
        check("execution.completed", execution["status"] == "completed", execution["status"])
        check("execution.local", result["model"]["externalTransfer"] is False, str(result["model"]))
        check("execution.sources", len(result.get("sources") or []) >= expected["retrieval"]["minimumSources"], str(len(result.get("sources") or [])))

        artifact = result["artifact"]
        document_ref = artifact["markdownDocument"]
        project_artifact = artifact["projectArtifact"]
        document = backend.get_project_markdown_document(project["id"], document_ref["id"])
        markdown = document["markdown"]
        for section in expected["markdown"]["requiredSections"]:
            check("markdown.section." + section, bool(re.search(r"(?m)^#{1,6}\s+" + re.escape(section) + r"\s*$", markdown)), section)
        for term in expected["markdown"]["requiredTerms"]:
            check("markdown.term." + term, term in markdown, term)
        for term in expected["markdown"]["forbiddenTerms"]:
            check("markdown.forbidden." + term, term not in markdown, term)
        citation_count = len(re.findall(r"\[\d+\]", markdown))
        check("markdown.citations", citation_count >= expected["markdown"]["minimumCitations"], f"인용 {citation_count}개")
        check("markdown.revision-one", document["revision"] == 1, f"r{document['revision']}")
        check("quality.review", artifact["qualityReview"]["passed"], str(artifact["qualityReview"].get("issues") or []))

        hwpx_bytes = base64.b64decode(artifact["contentBase64"], validate=True)
        parsed = backend.parse_hwpx(hwpx_bytes, artifact["filename"])
        hwpx_text = "\n".join(item["text"] for item in parsed["paragraphs"])
        for term in expected["hwpx"]["requiredTerms"]:
            check("hwpx.term." + term, term in hwpx_text, term)
        check("hwpx.paragraphs", parsed["stats"]["paragraphs"] >= expected["hwpx"]["minimumParagraphs"], str(parsed["stats"]["paragraphs"]))
        mapping_coverage = float(project_artifact["renderMap"].get("mappingCoverage") or 0)
        check("hwpx.mapping-coverage", mapping_coverage >= expected["hwpx"]["minimumMappingCoverage"], str(mapping_coverage))
        check("lineage.source-revision", project_artifact["sourceVersionId"] == document["versionId"], project_artifact["sourceVersionId"])
        check("lineage.synced", project_artifact["status"] == "synced", project_artifact["status"])

        round_trip = expected["roundTrip"]
        session = backend.open_native_document_session(
            {
                "filename": artifact["filename"],
                "content_base64": artifact["contentBase64"],
                "project_id": project["id"],
                "markdown_document_id": document["id"],
                "project_artifact_id": project_artifact["id"],
                "markdown_base_revision": document["revision"],
                "canonical_markdown": markdown,
                "actor": actor,
            }
        )
        target = next(
            (item for item in session["snapshot"]["document"]["paragraphs"] if round_trip["targetTerm"] in item["text"]),
            None,
        )
        check("roundtrip.target", target is not None, round_trip["targetTerm"])
        if target is None:
            raise ValueError("HWPX 역반영 대상 문단을 찾지 못했습니다.")
        after = target["text"].replace(round_trip["targetTerm"], round_trip["replacement"], 1)
        edited = backend.command_native_document_session(
            session["id"],
            {
                "base_revision": session["revision"],
                "command": "replace_selection",
                "arguments": {"target": target["id"], "before": target["text"], "after": after},
                "actor": actor,
            },
        )
        check("roundtrip.diverged", edited["projectSync"]["status"] == "diverged", edited["projectSync"]["status"])
        promoted = backend.promote_project_artifact_to_markdown(
            project["id"], document["id"], edited["projectSync"]["artifact"]["id"], {"actor": actor}
        )["document"]
        check("roundtrip.revision", promoted["revision"] == round_trip["expectedRevision"], f"r{promoted['revision']}")
        check("roundtrip.content", round_trip["replacement"] in promoted["markdown"], round_trip["replacement"])

        audit = backend.list_audit(200)
        event_types = {item["eventType"] for item in audit["items"]}
        for event_type in expected["auditEventTypes"]:
            check("audit." + event_type, event_type in event_types, event_type)
        integrity = backend.verify_audit_integrity()
        check("audit.integrity", integrity["valid"], f"이벤트 {integrity['events']}개")

        artifacts = {
            "projectId": project["id"],
            "sourceIds": source_ids,
            "planId": plan["id"],
            "executionId": execution["id"],
            "workflowRunId": execution["workflowRunId"],
            "markdownDocumentId": document["id"],
            "initialMarkdownVersionId": document["versionId"],
            "finalMarkdownVersionId": promoted["versionId"],
            "finalRevision": promoted["revision"],
            "hwpxArtifactId": project_artifact["id"],
            "hwpxSha256": project_artifact["artifactSha256"],
        }
    except Exception as error:
        check("scenario.exception", False, str(error))

    failed = [item for item in checks if not item["passed"]]
    return {
        "contractVersion": "golden-workflow-run/1.0",
        "workflowId": spec["id"],
        "title": spec["title"],
        "status": "passed" if not failed else "failed",
        "summary": {"passed": len(checks) - len(failed), "failed": len(failed), "total": len(checks)},
        "checks": checks,
        "artifacts": artifacts,
    }


def _load_backend(db_path: Path):
    os.environ["AIWORKS_DB_PATH"] = str(db_path)
    os.environ["AIWORKS_ENABLE_DEMO_SEED"] = "0"
    os.environ["AIWORKS_APPROVAL_SECRET"] = "golden-workflow-local-only"
    os.environ["AIWORKS_SOLAR_LIVE"] = "0"
    os.environ["AIWORKS_OPENROUTER_LIVE"] = "0"
    os.environ["AIWORKS_LOCAL_RAG_LLM"] = "0"
    spec = importlib.util.spec_from_file_location("ai_work_hub_golden_backend", ROOT / "backend.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("backend.py를 불러오지 못했습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Work Hub Golden Workflow 실행")
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--db", type=Path, help="결과를 보존할 격리 SQLite 경로; 생략하면 임시 DB 사용")
    args = parser.parse_args(argv)
    if args.db:
        backend = _load_backend(args.db.resolve())
        report = run(backend, args.spec)
    else:
        with tempfile.TemporaryDirectory(prefix="ai-work-hub-golden-") as temp_dir:
            backend = _load_backend(Path(temp_dir) / "golden.sqlite3")
            report = run(backend, args.spec)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
