import base64
import hashlib
import importlib.util
import io
import os
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_backend(db_path):
    os.environ["AIWORKS_DB_PATH"] = str(db_path)
    os.environ["AIWORKS_APPROVAL_SECRET"] = "test-only-secret"
    os.environ["AIWORKS_OPENROUTER_LIVE"] = "0"
    os.environ["OPENROUTER_API_KEY"] = ""
    spec = importlib.util.spec_from_file_location("aiworks_backend_test", ROOT / "backend.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_hwpx():
    buffer = io.BytesIO()
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <hs:sec xmlns:hs="urn:hancom:section" xmlns:hp="urn:hancom:paragraph">
      <hp:p><hp:run><hp:t>사업명: 지능형 민원지원 기반 구축</hp:t></hp:run></hp:p>
      <hp:p><hp:run><hp:t>사업기간: 2027.01 ~ 2027.12</hp:t></hp:run></hp:p>
      <hp:p><hp:run><hp:t>총사업비: 1,284백만원</hp:t></hp:run></hp:p>
    </hs:sec>"""
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/section0.xml", xml)
        archive.writestr("BinData/sample.bin", b"preserve-this-asset")
    return buffer.getvalue()


class AIWorksBackendTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.backend = load_backend(Path(self.tempdir.name) / "aiworks.sqlite3")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_plan_approval_execution_is_persistent_and_one_time(self):
        plan = self.backend.create_plan(
            {
                "intent": "선택 문장을 2줄 공문체로 정리해줘",
                "actor": "tester",
                "document_context": {"classification": "internal"},
            }
        )
        approval = self.backend.approve_plan(
            {
                "plan_id": plan["id"],
                "actor": "tester",
                "permissions": plan["requiredPermissions"],
            }
        )
        execution = self.backend.execute_plan(
            {
                "approval_token": approval["approvalToken"],
                "idempotency_key": "test-execution-1",
                "input": {"selection": "기존 문장", "selection_id": "p1"},
            }
        )
        self.assertEqual(execution["status"], "completed")
        self.assertEqual(execution["result"]["patches"][0]["before"], "기존 문장")
        stored = self.backend.get_plan(plan["id"])
        self.assertEqual(stored["status"], "completed")
        audit = self.backend.list_audit()
        self.assertTrue(any(item["eventType"] == "execution.completed" for item in audit["items"]))
        replay = self.backend.execute_plan(
            {
                "approval_token": approval["approvalToken"],
                "idempotency_key": "test-execution-1",
                "input": {"selection": "기존 문장", "selection_id": "p1"},
            }
        )
        self.assertTrue(replay["idempotent"])

    def test_live_selection_rewrite_retries_when_model_copies_source(self):
        plan = self.backend.create_plan(
            {
                "intent": "더 간결하고 분명하게 바꿔줘",
                "actor": "tester",
                "document_context": {"classification": "internal"},
            }
        )
        approval = self.backend.approve_plan(
            {
                "plan_id": plan["id"],
                "actor": "tester",
                "permissions": plan["requiredPermissions"],
            }
        )
        model_responses = [
            {
                "content": "기존 문장",
                "resolvedModel": "test/free:free",
                "usage": {},
                "requestId": "request-1",
            },
            {
                "content": "핵심이 분명한 새 문장",
                "resolvedModel": "test/free:free",
                "usage": {},
                "requestId": "request-2",
            },
        ]
        with mock.patch.dict(os.environ, {"AIWORKS_OPENROUTER_LIVE": "1"}), mock.patch.object(
            self.backend, "_openrouter_chat", side_effect=model_responses
        ) as chat:
            execution = self.backend.execute_plan(
                {
                    "approval_token": approval["approvalToken"],
                    "idempotency_key": "test-live-selection-rewrite",
                    "input": {
                        "selection": "기존 문장",
                        "selection_id": "native-selection",
                        "require_live_model": True,
                    },
                }
            )
        self.assertEqual(chat.call_count, 2)
        self.assertEqual(execution["result"]["patches"][0]["after"], "핵심이 분명한 새 문장")
        self.assertEqual(execution["result"]["model"]["mode"], "live")

    def test_missing_permission_is_rejected(self):
        plan = self.backend.create_plan(
            {"intent": "예산 산출", "document_context": {"classification": "internal"}}
        )
        with self.assertRaises(self.backend.ApiError) as raised:
            self.backend.approve_plan(
                {"plan_id": plan["id"], "permissions": ["document.read"]}
            )
        self.assertEqual(raised.exception.status, 403)

    def test_rhwp_mcp_catalog_permissions_and_signed_bridge(self):
        capabilities = self.backend.rhwp_capabilities()
        self.assertEqual(capabilities["manifest"]["id"], "document.rhwp")
        self.assertEqual(capabilities["installation"]["pinned_version"], "1.0.0")
        self.assertGreaterEqual(len(capabilities["tools"]), 20)
        mcp = self.backend.RHWP_AUTOMATION_MCP
        with self.assertRaises(mcp.RhwpMcpError):
            mcp.invoke("rhwp.document.save", {}, ["document.write"], False)

        captured = {}

        def bridge(envelope):
            captured.update(envelope)
            return {"id": envelope["id"], "ok": True, "result": {"saved": True}}

        with mock.patch.dict(os.environ, {"AIWORKS_RHWP_BRIDGE_SECRET": "test-rhwp-bridge-secret-123"}):
            result = mcp.invoke(
                "rhwp.document.save",
                {},
                ["document.write"],
                True,
                transport=bridge,
            )
        self.assertTrue(result["result"]["saved"])
        self.assertEqual(captured["protocol"], "aiworks.rhwp-bridge/1")
        self.assertEqual(len(captured["signature"]), 64)
        self.assertFalse(result["externalTransfer"])

    def test_tampered_token_is_rejected(self):
        plan = self.backend.create_plan(
            {"intent": "문장 변경", "document_context": {"classification": "internal"}}
        )
        approval = self.backend.approve_plan(
            {"plan_id": plan["id"], "permissions": plan["requiredPermissions"]}
        )
        token = approval["approvalToken"][:-1] + ("A" if approval["approvalToken"][-1] != "A" else "B")
        with self.assertRaises(self.backend.ApiError) as raised:
            self.backend.execute_plan({"approval_token": token, "input": {}})
        self.assertEqual(raised.exception.status, 403)

    def test_hwpx_adapter_extracts_values_without_external_io(self):
        data = sample_hwpx()
        result = self.backend.analyze_hwpx(
            {
                "filename": "sample.hwpx",
                "content_base64": base64.b64encode(data).decode("ascii"),
                "actor": "tester",
            }
        )
        self.assertEqual(result["stats"]["paragraphs"], 3)
        values = {item["id"]: item["value"] for item in result["commonDataCandidates"]}
        self.assertIn("project.name", values)
        self.assertEqual(values["budget.total"], "1,284백만원")

    def test_hwpx_layout_preserves_table_cells_and_spans(self):
        buffer = io.BytesIO()
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <hs:sec xmlns:hs="urn:hancom:section" xmlns:hp="urn:hancom:paragraph">
          <hp:p><hp:run><hp:t>표 앞 문단</hp:t></hp:run></hp:p>
          <hp:tbl><hp:tr>
            <hp:tc><hp:cellAddr rowAddr="0" colAddr="0"/><hp:cellSpan rowSpan="2" colSpan="1"/><hp:subList><hp:p><hp:run><hp:t>병합 셀</hp:t></hp:run></hp:p></hp:subList></hp:tc>
            <hp:tc><hp:cellAddr rowAddr="0" colAddr="1"/><hp:cellSpan rowSpan="1" colSpan="1"/><hp:subList><hp:p><hp:run><hp:t>값</hp:t></hp:run></hp:p></hp:subList></hp:tc>
          </hp:tr></hp:tbl>
        </hs:sec>"""
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("mimetype", "application/hwp+zip")
            archive.writestr("Contents/section0.xml", xml)
        parsed = self.backend.parse_hwpx(buffer.getvalue(), "table.hwpx")
        self.assertEqual(parsed["stats"]["tables"], 1)
        self.assertEqual(parsed["stats"]["cells"], 2)
        blocks = parsed["layout"]["sections"][0]["blocks"]
        table = next(item for item in blocks if item["type"] == "table")
        self.assertEqual(table["rows"][0]["cells"][0]["rowSpan"], 2)
        self.assertEqual(table["rows"][0]["cells"][0]["paragraphIds"], ["Contents/section0.xml#p2"])

    def test_document_session_routes_to_mcp_and_applies_revisioned_command(self):
        source = sample_hwpx()
        session = self.backend.open_native_document_session(
            {
                "filename": "session.hwpx",
                "content_base64": base64.b64encode(source).decode(),
                "intent": "원본 표 구조를 유지하며 한글 문서를 수정",
                "confirmed": True,
                "actor": "tester",
            }
        )
        self.assertEqual(session["adapter"], "document.hwpx@1.2.0")
        self.assertEqual(session["runtime"], "server-python-fallback")
        self.assertEqual(session["revision"], 1)
        target = session["snapshot"]["document"]["paragraphs"][0]
        updated = self.backend.command_native_document_session(
            session["id"],
            {
                "base_revision": 1,
                "command": "replace_selection",
                "arguments": {
                    "target": target["id"],
                    "before": target["text"],
                    "after": "MCP 세션으로 변경한 사업명",
                },
                "confirmed": True,
                "actor": "tester",
            },
        )
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(
            updated["snapshot"]["document"]["paragraphs"][0]["text"],
            "MCP 세션으로 변경한 사업명",
        )
        artifact = self.backend.get_native_document_session(
            session["id"], include_artifact=True
        )
        reparsed = self.backend.parse_hwpx(
            base64.b64decode(artifact["contentBase64"]), artifact["filename"]
        )
        self.assertEqual(reparsed["paragraphs"][0]["text"], "MCP 세션으로 변경한 사업명")
        with self.assertRaises(self.backend.ApiError) as stale:
            self.backend.command_native_document_session(
                session["id"],
                {
                    "base_revision": 1,
                    "command": "replace_selection",
                    "arguments": {},
                    "confirmed": True,
                },
            )
        self.assertEqual(stale.exception.status, 409)

    def test_hwpx_session_replace_artifact_uses_aiworks_filename(self):
        source = sample_hwpx()
        session = self.backend.open_native_document_session(
            {
                "filename": "native-selection.hwpx",
                "content_base64": base64.b64encode(source).decode(),
                "intent": "RHWP에서 직접 편집한 원본을 저장",
                "confirmed": True,
            }
        )
        updated = self.backend.command_native_document_session(
            session["id"],
            {
                "base_revision": 1,
                "command": "replace_artifact",
                "arguments": {"contentBase64": base64.b64encode(source).decode(), "format": "hwpx"},
                "confirmed": True,
            },
        )
        self.assertEqual(updated["filename"], "native-selection_AIWorks.hwpx")
        self.assertEqual(updated["revision"], 2)
        artifact = self.backend.get_native_document_session(
            session["id"], include_artifact=True
        )
        self.assertEqual(artifact["filename"], "native-selection_AIWorks.hwpx")

    def test_binary_hwp_routes_to_self_hosted_rhwp_web_runtime(self):
        ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"test-hwp-payload"
        session = self.backend.open_native_document_session(
            {
                "filename": "native.hwp",
                "content_base64": base64.b64encode(ole).decode(),
                "intent": "한글 편집기로 열어줘",
                "confirmed": True,
            }
        )
        self.assertEqual(session["adapter"], "document.rhwp-web@0.8.2")
        self.assertEqual(session["runtime"], "browser-wasm")
        self.assertEqual(session["snapshot"]["kind"], "rhwp-web")

    def test_markdown_editor_session_replaces_selection_and_document(self):
        original = "# 사업계획\n\n검토가 필요하다."
        session = self.backend.open_native_document_session(
            {
                "filename": "plan.md",
                "content_base64": base64.b64encode(original.encode()).decode(),
                "intent": "공손한 보고서로 수정해줘",
                "confirmed": True,
            }
        )
        self.assertEqual(session["adapter"], "document.markdown@1.0.0")
        self.assertEqual(session["snapshot"]["kind"], "text-editor")
        updated = self.backend.command_native_document_session(
            session["id"],
            {
                "base_revision": 1,
                "command": "replace_selection",
                "arguments": {"before": "필요하다.", "after": "필요합니다."},
                "confirmed": True,
            },
        )
        self.assertEqual(updated["revision"], 2)
        self.assertIn("필요합니다.", updated["snapshot"]["content"])

    def test_registry_accepts_only_two_zero_cost_free_variants(self):
        models = self.backend.MODEL_MANAGEMENT_MCP.list_models()
        self.assertEqual(len(models), 2)
        self.assertTrue(all(item["id"].endswith(":free") for item in models))
        self.assertTrue(
            all(item["price"]["input"] == 0 and item["price"]["output"] == 0 for item in models)
        )

    def test_intent_analysis_switches_between_distinct_models(self):
        writing = self.backend.analyze_and_route("선택 문장을 2줄 공문체로 다듬어줘")
        reasoning = self.backend.analyze_and_route("최신 기준과 비교해 예산 산출 근거를 검증해줘")
        self.assertEqual(writing["intentAnalysis"]["intentType"], "document_writing")
        self.assertEqual(
            writing["routing"]["model"]["id"], "google/gemma-4-26b-a4b-it:free"
        )
        self.assertEqual(reasoning["intentAnalysis"]["intentType"], "complex_reasoning")
        self.assertEqual(
            reasoning["routing"]["model"]["id"],
            "openai/gpt-oss-20b:free",
        )

    def test_plan_includes_external_transfer_approval_and_route(self):
        plan = self.backend.create_plan(
            {
                "intent": "보고서 문장을 요약해줘",
                "document_context": {"classification": "internal"},
            }
        )
        self.assertTrue(plan["dataPolicy"]["externalTransfer"])
        self.assertIn("network.send", plan["requiredPermissions"])
        self.assertEqual(
            plan["routing"]["model"]["id"], "google/gemma-4-26b-a4b-it:free"
        )

    def test_confidential_data_is_not_routed_to_free_external_model(self):
        with self.assertRaises(self.backend.ApiError) as raised:
            self.backend.create_plan(
                {
                    "intent": "문장을 요약해줘",
                    "document_context": {"classification": "confidential"},
                }
            )
        self.assertEqual(raised.exception.status, 403)

    def test_signed_store_installs_pinned_version_and_rolls_back(self):
        catalog = self.backend.list_store_packages()
        budget = next(item for item in catalog["items"] if item["packageId"] == "budget.form")
        self.assertEqual(budget["installedVersion"], "1.0.3")
        self.assertEqual(budget["versions"][0]["version"], "1.0.4")
        self.assertTrue(budget["versions"][0]["signatureVerified"])
        self.assertTrue(budget["versions"][0]["validationPassed"])
        self.assertEqual(budget["versions"][0]["vulnerabilities"], 0)
        installed = self.backend.install_mcp_package(
            {
                "package_id": "budget.form",
                "version": "1.0.4",
                "actor": "store-admin",
                "approved_permissions": budget["permissions"],
                "acknowledge_signature": True,
            }
        )
        self.assertEqual(installed["installation"]["pinned_version"], "1.0.4")
        plan = self.backend.create_plan(
            {"intent": "예산 산출 근거를 작성해줘", "document_context": {"classification": "internal"}}
        )
        self.assertTrue(any(step["mcp"] == "budget.form@1.0.4" for step in plan["steps"]))
        rolled_back = self.backend.rollback_mcp_package(
            {
                "package_id": "budget.form",
                "actor": "store-admin",
                "approved_permissions": budget["permissions"],
                "acknowledge_signature": True,
            }
        )
        self.assertEqual(rolled_back["installation"]["pinned_version"], "1.0.3")
        events = self.backend.list_audit()["items"]
        self.assertTrue(any(item["eventType"] == "mcp.package_rolled_back" for item in events))

    def test_builder_draft_validates_publishes_and_installs_signed_package(self):
        draft = self.backend.create_mcp_draft(
            {
                "name": "예산 근거 검증 MCP",
                "package_id": "org.budget-evidence-checker",
                "description": "예산요청서 문서의 산출 근거를 현재 기준값과 비교 검증하고 수정안을 제안한다.",
                "visibility": "organization",
                "source_included": False,
                "allow_external": False,
                "actor": "builder",
            }
        )
        self.assertEqual(draft["status"], "draft")
        self.assertEqual(draft["manifest"]["runtime"], "local")
        self.assertNotIn(
            "network.send",
            [item["scope"] for item in draft["manifest"]["permissions"]],
        )
        self.assertTrue(
            all("@" in item and "^" not in item for item in draft["manifest"]["dependencies"])
        )
        with self.assertRaises(self.backend.ApiError) as premature:
            self.backend.publish_mcp_draft(draft["id"], {})
        self.assertEqual(premature.exception.status, 409)

        validated = self.backend.validate_mcp_draft(draft["id"], {"actor": "builder"})
        self.assertEqual(validated["status"], "validated")
        self.assertTrue(validated["validation"]["passed"])
        self.assertEqual(len(validated["validation"]["tests"]), 6)
        with self.assertRaises(self.backend.ApiError) as unconfirmed:
            self.backend.publish_mcp_draft(
                draft["id"],
                {
                    "confirm_visibility": "organization",
                    "confirm_source_included": True,
                },
            )
        self.assertEqual(unconfirmed.exception.status, 403)

        published = self.backend.publish_mcp_draft(
            draft["id"],
            {
                "actor": "builder",
                "confirm_visibility": "organization",
                "confirm_source_included": False,
            },
        )
        self.assertEqual(published["draft"]["status"], "published")
        self.assertTrue(published["package"]["signature"]["verified"])
        catalog = self.backend.list_store_packages()
        package = next(
            item
            for item in catalog["items"]
            if item["packageId"] == "org.budget-evidence-checker"
        )
        installed = self.backend.install_mcp_package(
            {
                "package_id": package["packageId"],
                "version": package["versions"][0]["version"],
                "approved_permissions": package["permissions"],
                "acknowledge_signature": True,
                "actor": "store-admin",
            }
        )
        self.assertEqual(installed["installation"]["pinned_version"], "0.1.0")
        events = {item["eventType"] for item in self.backend.list_audit(100)["items"]}
        self.assertTrue(
            {
                "mcp.draft_created",
                "mcp.draft_validated",
                "mcp.draft_published",
                "mcp.package_installed",
            }.issubset(events)
        )

    def test_builder_adds_network_permission_only_with_explicit_consent(self):
        description = "문서 내용을 분석하고 요약 결과를 생성하되 원문을 외부로 보내지 않는다."
        local = self.backend.create_mcp_draft(
            {"name": "로컬 요약", "description": description, "allow_external": False}
        )
        external = self.backend.create_mcp_draft(
            {
                "name": "승인형 요약",
                "description": description,
                "allow_external": True,
            }
        )
        local_scopes = {item["scope"] for item in local["manifest"]["permissions"]}
        external_scopes = {item["scope"] for item in external["manifest"]["permissions"]}
        self.assertEqual(local["manifest"]["runtime"], "local")
        self.assertNotIn("network.send", local_scopes)
        self.assertEqual(external["manifest"]["runtime"], "hybrid")
        self.assertIn("network.send", external_scopes)

    def test_builder_reference_is_inspected_included_and_integrity_checked(self):
        draft = self.backend.create_mcp_draft(
            {
                "name": "지침 기반 검토",
                "package_id": "org.guideline-review",
                "description": "첨부한 예산 지침 문서를 분석하고 필수 항목을 검증한다.",
                "visibility": "organization",
                "source_included": True,
            }
        )
        content = "# 예산 지침\n\n모든 산출 근거에는 단가와 물량을 기재한다.\n".encode()
        attached = self.backend.add_mcp_draft_reference(
            draft["id"],
            {
                "filename": "budget-guide.md",
                "content_base64": base64.b64encode(content).decode(),
                "actor": "builder",
            },
        )
        self.assertFalse(attached["idempotent"])
        self.assertEqual(attached["reference"]["summary"]["kind"], "text")
        self.assertEqual(len(attached["draft"]["references"]), 1)
        duplicate = self.backend.add_mcp_draft_reference(
            draft["id"],
            {
                "filename": "same-guide.md",
                "content_base64": base64.b64encode(content).decode(),
            },
        )
        self.assertTrue(duplicate["idempotent"])
        validated = self.backend.validate_mcp_draft(draft["id"], {})
        references = next(
            item
            for item in validated["validation"]["tests"]
            if item["id"] == "references.integrity"
        )
        self.assertTrue(references["passed"])
        published = self.backend.publish_mcp_draft(
            draft["id"],
            {
                "confirm_visibility": "organization",
                "confirm_source_included": True,
            },
        )
        self.assertEqual(len(published["package"]["includedFiles"]), 1)
        self.assertEqual(
            published["package"]["includedFiles"][0]["sha256"],
            hashlib.sha256(content).hexdigest(),
        )
        with self.backend._connect() as db:
            db.execute(
                "UPDATE mcp_package_files SET content_blob=? WHERE package_id=? AND version=?",
                (b"tampered", "org.guideline-review", "0.1.0"),
            )
        catalog = self.backend.list_store_packages()
        self.assertEqual(catalog["quarantined"][0]["packageId"], "org.guideline-review")
        readiness = self.backend.operational_readiness()
        store_check = next(
            item for item in readiness["checks"] if item["id"] == "store.signatures"
        )
        self.assertEqual(store_check["status"], "fail")

    def test_builder_reference_rejects_disguised_or_unsafe_files(self):
        draft = self.backend.create_mcp_draft(
            {
                "name": "안전 검사",
                "description": "기준 문서를 분석해 입력 문서의 형식을 검증한다.",
            }
        )
        with self.assertRaises(self.backend.ApiError) as disguised:
            self.backend.add_mcp_draft_reference(
                draft["id"],
                {
                    "filename": "guide.pdf",
                    "content_base64": base64.b64encode(b"not a pdf").decode(),
                },
            )
        self.assertEqual(disguised.exception.status, 400)
        with self.assertRaises(self.backend.ApiError):
            self.backend.add_mcp_draft_reference(
                draft["id"],
                {
                    "filename": "../guide.txt",
                    "content_base64": base64.b64encode(b"safe text").decode(),
                },
            )

    def test_store_rejects_missing_approval_and_tampered_signature(self):
        catalog = self.backend.list_store_packages()
        citation = next(item for item in catalog["items"] if item["packageId"] == "citation.linker")
        with self.assertRaises(self.backend.ApiError) as missing_approval:
            self.backend.install_mcp_package(
                {
                    "package_id": "citation.linker",
                    "version": citation["versions"][0]["version"],
                    "approved_permissions": [],
                    "acknowledge_signature": True,
                }
            )
        self.assertEqual(missing_approval.exception.status, 403)
        with self.backend._connect() as db:
            db.execute(
                "UPDATE mcp_packages SET signature=? WHERE package_id=? AND version=?",
                ("A" * 43, "citation.linker", citation["versions"][0]["version"]),
            )
        with self.assertRaises(self.backend.ApiError) as tampered:
            self.backend.install_mcp_package(
                {
                    "package_id": "citation.linker",
                    "version": citation["versions"][0]["version"],
                    "approved_permissions": citation["permissions"],
                    "acknowledge_signature": True,
                }
            )
        self.assertEqual(tampered.exception.status, 403)

    def test_knowledge_query_is_grounded_and_supports_as_of(self):
        current = self.backend.query_knowledge(
            {"question": "SW 기술자 월평균임금", "clearance": "internal", "as_of": "2026-12-31"}
        )
        self.assertTrue(current["answerable"])
        self.assertTrue(current["grounded"])
        self.assertIn("8560000", current["answer"])
        self.assertTrue(current["citations"])
        historical = self.backend.query_knowledge(
            {"question": "SW 기술자 월평균임금", "clearance": "internal", "as_of": "2025-12-31"}
        )
        self.assertIn("8200000", historical["answer"])
        self.assertTrue(all(item["effectiveDate"] <= "2025-12-31" for item in historical["citations"]))
        denied = self.backend.query_knowledge(
            {"question": "SW 기술자 월평균임금", "clearance": "public"}
        )
        self.assertFalse(denied["answerable"])
        unknown = self.backend.query_knowledge(
            {"question": "화성 탐사선 발사 일정", "clearance": "internal"}
        )
        self.assertFalse(unknown["answerable"])
        self.assertEqual(unknown["citations"], [])

    def test_knowledge_graph_compare_and_sourced_note(self):
        graph = self.backend.knowledge_graph()
        self.assertGreaterEqual(graph["counts"]["nodes"], 7)
        self.assertGreaterEqual(graph["counts"]["sources"], 4)
        self.assertTrue(any(edge["relation"] == "uses" for edge in graph["edges"]))
        comparison = self.backend.compare_knowledge_versions(
            {
                "record_id": "cost.engineer.monthly",
                "from_date": "2025-12-31",
                "to_date": "2026-12-31",
            }
        )
        self.assertEqual(comparison["delta"], 360000)
        self.assertEqual(comparison["percentChange"], 4.39)
        with self.assertRaises(self.backend.ApiError):
            self.backend.create_knowledge_note({"title": "근거 없음", "content": "저장 차단"})
        note = self.backend.create_knowledge_note(
            {
                "title": "검토 메모",
                "content": "월평균임금 변경을 예산에 반영한다.",
                "actor": "knowledge-tester",
                "sources": [
                    {
                        "documentId": "sw-cost-guide-2026",
                        "locator": "표 2",
                        "excerpt": "8,560,000원",
                        "effectiveDate": "2026-01-01",
                        "confidence": 0.97,
                    }
                ],
                "relates_to": ["data:cost.engineer.monthly"],
            }
        )
        self.assertEqual(note["nodeType"], "note")
        self.assertEqual(len(note["sources"]), 1)

    def test_multimodal_asset_inspection_checks_actual_bytes(self):
        code = b"class Sample:\n    pass\n\ndef run():\n    # TODO review\n    return True\n"
        inspected_code = self.backend.inspect_asset(
            {
                "filename": "sample.py",
                "content_base64": base64.b64encode(code).decode(),
                "actor": "asset-tester",
            }
        )
        self.assertEqual(inspected_code["modality"], "code")
        self.assertEqual(inspected_code["functions"], 1)
        self.assertEqual(inspected_code["classes"], 1)
        self.assertEqual(inspected_code["todos"], 1)
        png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (320).to_bytes(4, "big") + (180).to_bytes(4, "big") + b"\x08\x02\x00\x00\x00"
        inspected_png = self.backend.inspect_asset(
            {"filename": "brief.png", "content_base64": base64.b64encode(png).decode()}
        )
        self.assertEqual((inspected_png["width"], inspected_png["height"]), (320, 180))
        audio_buffer = io.BytesIO()
        with wave.open(audio_buffer, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b"\x00\x00" * 800)
        inspected_audio = self.backend.inspect_asset(
            {"filename": "meeting.wav", "content_base64": base64.b64encode(audio_buffer.getvalue()).decode()}
        )
        self.assertEqual(inspected_audio["sampleRate"], 8000)
        self.assertEqual(inspected_audio["durationSeconds"], 0.1)
        mp4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 16
        inspected_video = self.backend.inspect_asset(
            {"filename": "summary.mp4", "content_base64": base64.b64encode(mp4).decode()}
        )
        self.assertEqual(inspected_video["brand"], "isom")
        with self.assertRaises(self.backend.ApiError) as forged:
            self.backend.inspect_asset(
                {"filename": "forged.png", "content_base64": base64.b64encode(b"not a png").decode()}
            )
        self.assertEqual(forged.exception.status, 400)
        with self.assertRaises(self.backend.ApiError):
            self.backend.inspect_asset(
                {"filename": "../escape.py", "content_base64": base64.b64encode(code).decode()}
            )

    def test_workflow_presets_report_readiness_and_model_route(self):
        registry = self.backend.list_workflow_presets()
        self.assertEqual(len(registry["items"]), 5)
        self.assertEqual(registry["counts"], {"ready": 2, "preview": 3})
        code_plan = self.backend.create_workflow_plan(
            {
                "preset_id": "code.review",
                "classification": "internal",
                "assets": [{"filename": "service.py", "bytes": 1200}],
            }
        )
        self.assertTrue(code_plan["executable"])
        self.assertEqual(code_plan["model"]["id"], "openai/gpt-oss-20b:free")
        self.assertIn("network.send", code_plan["requiredPermissions"])
        confidential = self.backend.create_workflow_plan(
            {
                "preset_id": "code.review",
                "classification": "confidential",
                "assets": [{"filename": "service.py", "bytes": 1200}],
            }
        )
        self.assertFalse(confidential["executable"])
        self.assertIn("classification.external-transfer-blocked", confidential["blockedBy"])
        image_plan = self.backend.create_workflow_plan(
            {
                "preset_id": "image.brief",
                "assets": [{"filename": "brief.png", "bytes": 2400}],
            }
        )
        self.assertFalse(image_plan["executable"])
        self.assertIn("compose", image_plan["blockedBy"])
        with self.assertRaises(self.backend.ApiError) as wrong_format:
            self.backend.create_workflow_plan(
                {
                    "preset_id": "audio.meeting",
                    "assets": [{"filename": "meeting.mp3", "bytes": 1200}],
                }
            )
        self.assertEqual(wrong_format.exception.status, 415)

    def test_operational_readiness_reports_required_boundaries(self):
        readiness = self.backend.operational_readiness()
        self.assertTrue(readiness["ready"])
        checks = {item["id"]: item for item in readiness["checks"]}
        self.assertEqual(checks["database.integrity"]["status"], "pass")
        self.assertEqual(checks["store.signatures"]["status"], "pass")
        self.assertEqual(checks["models.free-only"]["status"], "pass")
        self.assertIn(checks["adapters.runtime"]["status"], {"pass", "warn"})

    def test_budget_acceptance_passes_and_failure_injection_is_recorded(self):
        passed = self.backend.run_budget_acceptance(
            {"actor": "acceptance-tester", "inject_failure": "none"}
        )
        self.assertEqual(passed["status"], "passed")
        self.assertTrue(all(item["passed"] for item in passed["checks"]))
        self.assertIn("documentVersionId", passed["artifacts"])
        self.assertEqual(passed["error"], None)
        failed = self.backend.run_budget_acceptance(
            {"actor": "acceptance-tester", "inject_failure": "stale-document"}
        )
        self.assertEqual(failed["status"], "failed")
        self.assertIn("다시 열어 주세요", failed["error"])
        self.assertNotIn("documentVersionId", failed["artifacts"])
        runs = self.backend.list_acceptance_runs()["items"]
        self.assertEqual([item["status"] for item in runs[:2]], ["failed", "passed"])
        audit_types = {item["eventType"] for item in self.backend.list_audit(200)["items"]}
        self.assertIn("acceptance.passed", audit_types)
        self.assertIn("acceptance.failed", audit_types)

    def test_hwpx_patch_replaces_target_and_preserves_other_entries(self):
        source = sample_hwpx()
        inspected = self.backend.parse_hwpx(source, "sample.hwpx")
        target = inspected["paragraphs"][0]
        replacement = "변경된 사업명: AIWorks 문서 자동화"
        artifact, metadata = self.backend.apply_hwpx_patch(
            source,
            {
                "op": "replace",
                "target": target["id"],
                "expectedBefore": target["text"],
                "after": replacement,
                "sourceSha256": hashlib.sha256(source).hexdigest(),
            },
            "sample.hwpx",
        )
        reparsed = self.backend.parse_hwpx(artifact, "sample_AIWorks.hwpx")
        self.assertEqual(reparsed["paragraphs"][0]["text"], replacement)
        self.assertNotEqual(metadata["sourceSha256"], metadata["artifactSha256"])
        with zipfile.ZipFile(io.BytesIO(artifact)) as archive:
            self.assertEqual(archive.read("BinData/sample.bin"), b"preserve-this-asset")
            self.assertEqual(archive.read("mimetype"), b"application/hwp+zip")

    def test_hwpx_patch_rejects_stale_source_and_paragraph(self):
        source = sample_hwpx()
        inspected = self.backend.parse_hwpx(source)
        patch = {
            "op": "replace",
            "target": inspected["paragraphs"][0]["id"],
            "expectedBefore": "다른 원문",
            "after": "새 문장",
            "sourceSha256": hashlib.sha256(source).hexdigest(),
        }
        with self.assertRaises(self.backend.ApiError) as paragraph_error:
            self.backend.apply_hwpx_patch(source, patch)
        self.assertEqual(paragraph_error.exception.status, 409)
        patch["expectedBefore"] = inspected["paragraphs"][0]["text"]
        patch["sourceSha256"] = "0" * 64
        with self.assertRaises(self.backend.ApiError) as hash_error:
            self.backend.apply_hwpx_patch(source, patch)
        self.assertEqual(hash_error.exception.status, 409)

    def test_apply_endpoint_records_document_version(self):
        source = sample_hwpx()
        inspected = self.backend.parse_hwpx(source)
        first = inspected["paragraphs"][0]
        result = self.backend.apply_hwpx_document_patch(
            {
                "filename": "sample.hwpx",
                "document_id": inspected["document"]["id"],
                "content_base64": base64.b64encode(source).decode("ascii"),
                "actor": "tester",
                "patch": {
                    "op": "replace",
                    "target": first["id"],
                    "expectedBefore": first["text"],
                    "after": "버전 기록 테스트",
                    "sourceSha256": inspected["document"]["sha256"],
                },
            }
        )
        self.assertTrue(result["filename"].endswith("_AIWorks.hwpx"))
        self.assertEqual(len(result["artifactSha256"]), 64)
        downloadable = self.backend.get_document_version(result["versionId"])
        self.assertEqual(downloadable["contentBase64"], result["contentBase64"])
        self.assertEqual(downloadable["bytes"], len(base64.b64decode(result["contentBase64"])))
        versions = self.backend.list_document_versions()["items"]
        self.assertEqual(versions[0]["id"], result["versionId"])
        second = self.backend.apply_hwpx_document_patch(
            {
                "filename": result["filename"],
                "document_id": result["documentId"],
                "content_base64": result["contentBase64"],
                "actor": "tester",
                "patch": {
                    "op": "replace",
                    "target": first["id"],
                    "expectedBefore": "버전 기록 테스트",
                    "after": "두 번째 직접 편집",
                    "sourceSha256": result["artifactSha256"],
                },
            }
        )
        self.assertEqual(second["filename"], "sample_AIWorks.hwpx")

    def test_workspace_document_persists_and_rejects_stale_revision(self):
        created = self.backend.save_workspace_document(
            {
                "name": "예산요청서 작업본",
                "content": {"title": "2027년도 예산요청서", "body": "초안"},
                "actor": "editor",
            }
        )
        self.assertEqual(created["revision"], 1)
        reopened = self.backend.get_workspace_document(created["id"])
        self.assertEqual(reopened["content"]["body"], "초안")
        updated = self.backend.save_workspace_document(
            {
                "id": created["id"],
                "base_revision": created["revision"],
                "name": created["name"],
                "content": {"title": "2027년도 예산요청서", "body": "수정본"},
                "actor": "editor",
            }
        )
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(
            self.backend.list_workspace_documents()["items"][0]["id"], created["id"]
        )
        with self.assertRaises(self.backend.ApiError) as stale:
            self.backend.save_workspace_document(
                {
                    "id": created["id"],
                    "base_revision": 1,
                    "name": created["name"],
                    "content": {"body": "충돌본"},
                }
            )
        self.assertEqual(stale.exception.status, 409)


if __name__ == "__main__":
    unittest.main()
