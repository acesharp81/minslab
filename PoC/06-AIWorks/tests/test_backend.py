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
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]


def load_backend(db_path):
    os.environ["AIWORKS_DB_PATH"] = str(db_path)
    os.environ["AIWORKS_ENABLE_DEMO_SEED"] = "1"
    os.environ["AIWORKS_APPROVAL_SECRET"] = "test-only-secret"
    os.environ["AIWORKS_OPENROUTER_LIVE"] = "0"
    os.environ["AIWORKS_LOCAL_RAG_LLM"] = "0"
    os.environ["AIWORKS_LOCAL_MCP_LIVE"] = "0"
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


def placeholder_template_hwpx():
    buffer = io.BytesIO()
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <hs:sec xmlns:hs="urn:hancom:section" xmlns:hp="urn:hancom:paragraph">
      <hp:p><hp:run><hp:t>{{title}}</hp:t></hp:run></hp:p>
      <hp:p><hp:run><hp:t>{{content}}</hp:t></hp:run></hp:p>
      <hp:p><hp:run><hp:t>작성일 {{date}}</hp:t></hp:run></hp:p>
    </hs:sec>"""
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/section0.xml", xml)
        archive.writestr("Preview/PrvText.txt", "template")
    return buffer.getvalue()


def guided_template_hwpx():
    buffer = io.BytesIO()
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <hs:sec xmlns:hs="urn:hancom:section" xmlns:hp="urn:hancom:paragraph">
      <hp:p><hp:run><hp:t>기관 표준 보고서</hp:t></hp:run></hp:p>
      <hp:p><hp:run><hp:t>[제목 작성요령: 보고서 제목을 입력하세요]</hp:t></hp:run></hp:p>
      <hp:p><hp:run><hp:t>※ 작성요령: 핵심 내용을 근거 중심으로 작성하고 안내 문구는 삭제</hp:t></hp:run></hp:p>
      <hp:p><hp:run><hp:t>(예시: 추진 배경과 주요 결과를 작성)</hp:t></hp:run></hp:p>
    </hs:sec>"""
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/section0.xml", xml)
        archive.writestr("Preview/PrvText.txt", "guided template")
    return buffer.getvalue()




def sample_form_template_hwpx():
    buffer = io.BytesIO()
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <hs:sec xmlns:hs="urn:hancom:section" xmlns:hp="urn:hancom:paragraph">
      <hp:p><hp:run><hp:t>행정안전부 업무보고 | 내부검토</hp:t></hp:run></hp:p>
      <hp:p><hp:run><hp:t>보고서 제목</hp:t></hp:run></hp:p>
      <hp:p><hp:run><hp:t>작성일: 2026. 8. 17.</hp:t></hp:run></hp:p>
      <hp:p><hp:run><hp:t>□ 대제목1</hp:t></hp:run></hp:p>
      <hp:p><hp:run><hp:t>○ (소제목1) 핵심 내용</hp:t></hp:run></hp:p>
      <hp:p><hp:run><hp:tbl id="100" rowCnt="2" colCnt="2"><hp:sz width="48000" height="4000"/>
        <hp:tr>
          <hp:tc><hp:subList><hp:p><hp:run><hp:t>항목1</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/><hp:cellSz width="24000" height="2000"/></hp:tc>
          <hp:tc><hp:subList><hp:p><hp:run><hp:t>항목2</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="1" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/><hp:cellSz width="24000" height="2000"/></hp:tc>
        </hp:tr>
        <hp:tr>
          <hp:tc><hp:subList><hp:p><hp:run><hp:t>내용1</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="0" rowAddr="1"/><hp:cellSpan colSpan="1" rowSpan="1"/><hp:cellSz width="24000" height="2000"/></hp:tc>
          <hp:tc><hp:subList><hp:p><hp:run><hp:t>내용2</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="1" rowAddr="1"/><hp:cellSpan colSpan="1" rowSpan="1"/><hp:cellSz width="24000" height="2000"/></hp:tc>
        </hp:tr>
      </hp:tbl></hp:run></hp:p>
    </hs:sec>"""
    header = """<?xml version="1.0" encoding="UTF-8"?>
    <hh:head xmlns:hh="urn:hancom:head" xmlns:hc="urn:hancom:core">
      <hh:paraProperties itemCnt="1">
        <hh:paraPr id="0"><hh:margin><hc:intent value="0" unit="HWPUNIT"/><hc:left value="0" unit="HWPUNIT"/></hh:margin></hh:paraPr>
      </hh:paraProperties>
    </hh:head>"""
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/header.xml", header)
        archive.writestr("Contents/section0.xml", xml)
        archive.writestr("Preview/PrvText.txt", "sample report form")
    return buffer.getvalue()

def ordinary_completed_report_hwpx():
    source = zipfile.ZipFile(io.BytesIO(sample_form_template_hwpx()))
    buffer = io.BytesIO()
    replacements = {
        "보고서 제목": "2026년도 디지털 행정 개선방안 보고서",
        "□ 대제목1": "□ 분석 개요",
        "○ (소제목1) 핵심 내용": "○ 사업 추진 현황",
        "항목1": "구분",
        "항목2": "내용",
        "내용1": "지적사항",
        "내용2": "사업계획 확정 전 예산 편성",
    }
    with source, zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "Contents/section0.xml":
                text = data.decode("utf-8")
                for before, after in replacements.items():
                    text = text.replace(before, after)
                data = text.encode("utf-8")
            target.writestr(info, data)
    return buffer.getvalue()


def searchable_budget_pdf():
    stream = b"BT /F1 12 Tf 72 720 Td (Budget policy total amount is 1,234 million won for 2027.) Tj 0 -24 Td (Digital government investment is 420 million won.) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(content)


def sample_docx():
    buffer = io.BytesIO()
    document = """<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>2026년 인공지능 공통기반 예산 분석</w:t></w:r></w:p><w:p><w:r><w:t>지적사항과 향후 계획을 정리합니다.</w:t></w:r></w:p></w:body></w:document>"""
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def sample_xlsx():
    buffer = io.BytesIO()
    shared = """<?xml version="1.0" encoding="UTF-8"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>연도</t></si><si><t>예산</t></si><si><t>2026</t></si></sst>"""
    sheet = """<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c t="s"><v>0</v></c><c t="s"><v>1</v></c></row><row r="2"><c t="s"><v>2</v></c><c><v>1200</v></c></row></sheetData></worksheet>"""
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/sharedStrings.xml", shared)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
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
        workflow_run = self.backend.get_workflow_run(execution["workflowRunId"])
        self.assertEqual(workflow_run["status"], "completed")
        self.assertEqual([item["stepKey"] for item in workflow_run["steps"]], ["context", "execute", "persist"])
        self.assertTrue(all(item["status"] == "completed" for item in workflow_run["steps"]))
        self.assertEqual(workflow_run["steps"][1]["output"]["responseType"], "selection-edit")

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
        self.assertEqual(replay["workflowRunId"], execution["workflowRunId"])

    def test_failed_workflow_creates_reapproval_retry_plan_from_checkpoint(self):
        plan = self.backend.create_plan({
            "intent": "선택 문장을 더 명확하게 바꿔줘",
            "actor": "tester",
            "document_context": {"classification": "internal", "has_selection": True},
        })
        approval = self.backend.approve_plan({
            "plan_id": plan["id"], "actor": "tester", "permissions": plan["requiredPermissions"],
        })
        with self.assertRaises(self.backend.ApiError):
            self.backend.execute_plan({
                "approval_token": approval["approvalToken"],
                "idempotency_key": "workflow-failure-1",
                "input": {"selection": "원문", "require_live_model": True},
            }, force_local=True)
        with self.backend._connect() as db:
            run_id = db.execute("SELECT id FROM workflow_runs WHERE plan_id=?", (plan["id"],)).fetchone()["id"]
        failed = self.backend.get_workflow_run(run_id)
        self.assertEqual(failed["status"], "failed")
        self.assertTrue(any(item["status"] == "failed" for item in failed["steps"]))
        failed_step_key = next(item["stepKey"] for item in failed["steps"] if item["status"] == "failed")
        retry = self.backend.create_workflow_retry_plan(run_id, {"actor": "tester"})
        self.assertNotEqual(retry["id"], plan["id"])
        self.assertEqual(retry["retryOfWorkflowRunId"], run_id)
        self.assertEqual(retry["resumeFromStep"], failed_step_key)
        self.assertEqual(self.backend.get_workflow_run(run_id)["retryCount"], 1)
        retry_approval = self.backend.approve_plan({
            "plan_id": retry["id"], "actor": "tester",
            "permissions": retry["requiredPermissions"],
        })
        resumed = self.backend.execute_plan({
            "approval_token": retry_approval["approvalToken"],
            "idempotency_key": "workflow-resume-1",
            "input": {"selection": "원문"},
        }, force_local=True)
        resumed_run = self.backend.get_workflow_run(resumed["workflowRunId"])
        self.assertEqual(resumed["workflowRunId"], run_id)
        self.assertEqual(resumed_run["resumedFromRunId"], run_id)
        self.assertEqual([item["attempt"] for item in resumed_run["executionAttempts"]], [1, 2])
        self.assertEqual({item["attempt"] for item in resumed_run["steps"]}, {1, 2})
        self.assertTrue(all(item["status"] == "completed" for item in resumed_run["steps"] if item["attempt"] == 2))
        self.assertEqual(resumed_run["resumeStepKey"], failed_step_key)


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
        with mock.patch.dict(os.environ, {"AIWORKS_SOLAR_LIVE": "1", "UPSTAGE_API_KEY": "test-upstage-key"}), mock.patch.object(
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

    def test_registry_uses_solar_pro_3_as_fast_default_with_fallbacks(self):
        models = self.backend.MODEL_MANAGEMENT_MCP.list_models()
        self.assertGreaterEqual(len(models), 3)
        defaults = [item for item in models if item.get("default")]
        self.assertEqual(len(defaults), 1)
        self.assertEqual(defaults[0]["id"], "upstage:solar-pro3-fast")
        self.assertEqual(defaults[0]["speedClass"], "fast")
        self.assertEqual({item["routingRole"] for item in models}, {"fast", "balanced", "deep"})

    def test_intent_analysis_switches_between_distinct_models(self):
        writing = self.backend.analyze_and_route("선택 문장을 2줄 공문체로 다듬어줘")
        reasoning = self.backend.analyze_and_route("최신 기준과 비교해 예산 산출 근거를 검증해줘")
        self.assertEqual(writing["intentAnalysis"]["intentType"], "document_writing")
        self.assertEqual(writing["routing"]["model"]["id"], "upstage:solar-pro3")
        self.assertEqual(reasoning["intentAnalysis"]["intentType"], "complex_reasoning")
        self.assertEqual(reasoning["routing"]["model"]["id"], "upstage:solar-pro4")
        self.assertNotEqual(writing["routing"]["fallbackModelId"], "upstage:solar-pro3")

    def test_intent_mcp_configuration_controls_initial_document_model(self):
        catalog = self.backend.list_store_packages()
        intent_mcp = next(item for item in catalog["items"] if item["packageId"] == "core.intent-analysis")
        self.assertEqual(intent_mcp["installedVersion"], "0.1.0")
        self.assertTrue(intent_mcp["configurable"])

        initial = self.backend.get_mcp_configuration({"package_id": "core.intent-analysis"})
        self.assertEqual(initial["revision"], 0)
        self.assertEqual(initial["values"]["initialDocumentModel"], "upstage:solar-pro4")
        first_plan = self.backend.create_plan(
            {"intent": "분석 결과를 사업계획서로 만들어줘", "document_context": {"classification": "internal"}}
        )
        self.assertTrue(first_plan["intentAnalysis"]["createsInitialDocument"])
        self.assertEqual(first_plan["routing"]["model"]["id"], "upstage:solar-pro4")
        self.assertEqual(first_plan["routing"]["reason"], "최초 문서 생성 품질 우선 설정")

        saved = self.backend.save_mcp_configuration(
            {
                "package_id": "core.intent-analysis",
                "base_revision": 0,
                "values": {"initialDocumentModel": "upstage:solar-pro3"},
                "actor": "tester",
            }
        )
        self.assertEqual(saved["revision"], 1)
        second_plan = self.backend.create_plan(
            {"intent": "이 결과를 보고서로 작성해줘", "document_context": {"classification": "internal"}}
        )
        self.assertEqual(second_plan["routing"]["model"]["id"], "upstage:solar-pro3")
        with self.assertRaises(self.backend.ApiError):
            self.backend.save_mcp_configuration(
                {
                    "package_id": "core.intent-analysis",
                    "base_revision": 1,
                    "values": {"initialDocumentModel": "unknown-model"},
                }
            )

    def test_upstage_solar_pro4_live_request_uses_reasoning_contract(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = self.backend._json(
            {
                "id": "chat-test",
                "model": "solar-pro4",
                "choices": [{"message": {"content": "품질 우선 보고서 초안"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 12},
            }
        ).encode("utf-8")
        with mock.patch.dict(
            os.environ,
            {"UPSTAGE_API_KEY": "test-upstage-key", "UPSTAGE_REASONING_MIN_TOKENS": "4096"},
        ), mock.patch.object(self.backend.url_request, "urlopen", return_value=response) as urlopen:
            result = self.backend._openrouter_chat(
                "upstage:solar-pro4",
                [{"role": "user", "content": "보고서를 작성해줘"}],
                max_tokens=900,
            )
        request = urlopen.call_args.args[0]
        request_body = self.backend.json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://api.upstage.ai/v1/chat/completions")
        self.assertEqual(request_body["model"], "solar-pro4")
        self.assertEqual(request_body["reasoning_effort"], "medium")
        self.assertEqual(request_body["max_tokens"], 4096)
        self.assertEqual(result["resolvedModel"], "solar-pro4")

    def test_transient_solar_error_falls_back_to_approved_route_model(self):
        route = {
            "model": {"id": "upstage:solar-pro4"},
            "fallbackModelId": "upstage:solar-pro3",
        }
        fallback_result = {
            "content": "Solar Pro 3 대체 응답",
            "requestedModel": "upstage:solar-pro3",
            "resolvedModel": "solar-pro3",
            "usage": {},
            "requestId": "fallback-request",
        }
        with mock.patch.object(
            self.backend,
            "_openrouter_chat",
            side_effect=[
                self.backend.ApiError("Upstage Solar 호출 실패: The read operation timed out", 502),
                fallback_result,
            ],
        ) as chat:
            result = self.backend._chat_with_route_fallback(
                route,
                [{"role": "user", "content": "보고서를 작성해줘"}],
                max_tokens=900,
            )
        self.assertEqual([call.args[0] for call in chat.call_args_list], ["upstage:solar-pro4", "upstage:solar-pro3"])
        self.assertEqual(result["requestedModel"], "upstage:solar-pro3")
        self.assertTrue(result["fallbackUsed"])
        self.assertEqual(result["fallbackFrom"], "upstage:solar-pro4")

    def test_non_transient_solar_error_does_not_fallback(self):
        route = {
            "model": {"id": "upstage:solar-pro4"},
            "fallbackModelId": "upstage:solar-pro3",
        }
        with mock.patch.object(
            self.backend,
            "_openrouter_chat",
            side_effect=self.backend.ApiError("UPSTAGE_API_KEY가 설정되지 않았습니다.", 503),
        ) as chat:
            with self.assertRaises(self.backend.ApiError):
                self.backend._chat_with_route_fallback(
                    route,
                    [{"role": "user", "content": "보고서를 작성해줘"}],
                )
        self.assertEqual(chat.call_count, 1)

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
            plan["routing"]["model"]["id"], "upstage:solar-pro3"
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
        self.assertIn("document.report@1.0.0", plan["workflow"]["loadedMcps"])
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

    def test_store_edit_forks_next_version_and_user_package_can_be_deleted(self):
        draft = self.backend.create_mcp_draft(
            {
                "name": "편집 가능한 MCP",
                "package_id": "org.editable",
                "description": "사용자 제작 MCP의 수정과 삭제 흐름을 검증하는 충분히 긴 설명이다.",
                "procedure": "입력을 확인한다.\n결과를 반환한다.",
            }
        )
        validated = self.backend.validate_mcp_draft(draft["id"], {})
        self.assertTrue(validated["validation"]["passed"])
        self.backend.publish_mcp_draft(
            draft["id"],
            {"confirm_visibility": "private", "confirm_source_included": False},
        )
        forked = self.backend.fork_mcp_package(
            {"package_id": "org.editable", "version": "0.1.0", "actor": "tester"}
        )
        self.assertEqual(forked["draft"]["manifest"]["version"], "0.1.1")
        self.assertEqual(forked["draft"]["manifest"]["derivedFrom"], "org.editable@0.1.0")
        deleted = self.backend.delete_mcp_package(
            {
                "package_id": "org.editable",
                "version": "0.1.0",
                "confirm_package_ref": "org.editable@0.1.0",
                "actor": "tester",
            }
        )
        self.assertTrue(deleted["deleted"])
        self.assertFalse(any(item["packageId"] == "org.editable" for item in self.backend.list_store_packages()["items"]))
        with self.assertRaises(self.backend.ApiError) as protected:
            self.backend.delete_mcp_package(
                {
                    "package_id": "document.hwpx",
                    "version": "1.2.0",
                    "confirm_package_ref": "document.hwpx@1.2.0",
                }
            )
        self.assertEqual(protected.exception.status, 403)

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
        self.assertEqual(len(validated["validation"]["tests"]), 7)
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

    def test_builder_publish_reassigns_legacy_id_owned_by_different_mcp(self):
        self.assertNotEqual(
            self.backend._builder_package_id("예산 정책 데이터 MCP"),
            self.backend._builder_package_id("행안부 보고 양식 MCP"),
        )
        self.assertNotEqual(self.backend._builder_package_id("행안부 보고 양식 MCP"), "org.mcp")
        first = self.backend.create_mcp_draft(
            {
                "name": "예산 정책 데이터 MCP",
                "package_id": "org.shared-mcp",
                "description": "등록된 예산 정책 자료를 조회하여 근거와 함께 결과를 반환한다.",
                "mcp_type": "tool",
                "instructions": "등록된 자료의 근거를 확인하고 사용자의 질문에 맞는 결과를 반환한다.",
                "procedure": "질문을 확인한다.\n근거를 조회한다.\n결과를 반환한다.",
            }
        )
        second = self.backend.create_mcp_draft(
            {
                "name": "행안부 보고 양식 MCP",
                "package_id": "org.shared-mcp",
                "description": "첨부된 행정안전부 HWPX 양식을 분석하여 현재 보고서 내용을 해당 서식으로 변환한다.",
                "mcp_type": "template",
                "instructions": "첨부 양식의 고정 서식과 입력 영역을 구분하고 현재 보고서의 제목과 본문을 대응한다.",
                "procedure": "양식을 분석한다.\n현재 문서를 대응한다.\n새 HWPX를 생성한다.",
                "source_included": True,
            }
        )
        self.backend.add_mcp_draft_reference(
            second["id"],
            {
                "filename": "행안부-보고-양식.hwpx",
                "role": "template-source",
                "content_base64": base64.b64encode(placeholder_template_hwpx()).decode(),
            },
        )
        self.backend.validate_mcp_draft(first["id"], {})
        self.backend.publish_mcp_draft(
            first["id"],
            {"confirm_visibility": "private", "confirm_source_included": False},
        )
        self.backend.validate_mcp_draft(second["id"], {})

        published = self.backend.publish_mcp_draft(
            second["id"],
            {"confirm_visibility": "private", "confirm_source_included": True},
        )

        self.assertEqual(published["identityAdjustment"]["previousPackageId"], "org.shared-mcp")
        self.assertNotEqual(published["package"]["packageId"], "org.shared-mcp")
        self.assertEqual(published["package"]["manifest"]["name"], "행안부 보고 양식 MCP")
        self.assertEqual(published["draft"]["manifest"]["id"], published["package"]["packageId"])
        store_names = {item["name"] for item in self.backend.list_store_packages()["items"]}
        self.assertIn("예산 정책 데이터 MCP", store_names)
        self.assertIn("행안부 보고 양식 MCP", store_names)

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

    def test_builder_supports_template_process_data_and_tool_guides(self):
        template = self.backend.create_mcp_draft(
            {
                "name": "행안부 보고서 양식 MCP",
                "package_id": "org.mois-report-template",
                "description": "현재 HWPX 내용을 등록된 행정 보고서 양식에 맞춰 새 문서로 변환한다.",
                "mcp_type": "template",
                "instructions": "입력 문서의 제목과 본문을 유지하고 등록된 양식의 입력 영역에 대응한다.",
                "cautions": "원문에 없는 수치를 추가하지 않는다.\n공식 양식 버전을 결과에 기록한다.",
                "procedure": "양식의 고정 영역을 식별한다.\n입력 문단을 필드에 대응한다.\n검증 후 새 revision으로 저장한다.",
                "trigger_examples": "행안부 보고서 양식으로 바꿔줘",
                "source_included": True,
                "use_model": False,
                "visibility": "organization",
            }
        )
        manifest = template["manifest"]
        self.assertEqual(manifest["mcpType"], "template")
        self.assertIn("document.template.apply", manifest["capabilities"])
        self.assertEqual(len(manifest["builderGuide"]["procedure"]), 3)
        self.assertNotIn("model.invoke", {item["scope"] for item in manifest["permissions"]})
        rejected = self.backend.validate_mcp_draft(template["id"], {})
        type_test = next(item for item in rejected["validation"]["tests"] if item["id"] == "builder.type-guide")
        self.assertFalse(type_test["passed"])

        attached = self.backend.add_mcp_draft_reference(
            template["id"],
            {
                "filename": "mois-report.hwpx",
                "role": "template-source",
                "content_base64": base64.b64encode(placeholder_template_hwpx()).decode(),
            },
        )
        self.assertEqual(attached["reference"]["role"], "template-source")
        self.assertEqual(attached["draft"]["manifest"]["references"][0]["role"], "template-source")
        validated = self.backend.validate_mcp_draft(template["id"], {})
        self.assertEqual(validated["status"], "validated")

        process = self.backend.create_mcp_draft(
            {
                "name": "결재 전 검토 처리 MCP",
                "description": "제출 문서를 확인하고 검토 단계와 결과 저장을 순서대로 수행한다.",
                "mcp_type": "process",
                "instructions": "입력 문서를 검토 절차에 따라 처리하고 단계별 결과를 기록한다.",
                "procedure": "입력 조건을 검사한다.\n검토 규칙을 실행한다.\n결과를 저장한다.",
                "use_model": False,
            }
        )
        self.assertEqual(self.backend.validate_mcp_draft(process["id"], {})["status"], "validated")

        data = self.backend.create_mcp_draft(
            {
                "name": "조직 예산 데이터 MCP",
                "package_id": "org.budget-data-rag",
                "description": "내부 예산 데이터를 기준일과 출처를 포함하여 읽기 전용으로 조회한다.",
                "mcp_type": "data",
                "instructions": "사용자 질의를 필터로 바꾸고 접근권한과 기준일을 적용해 조회한다.",
                "procedure": "질의를 분석한다.\n데이터를 조회한다.\n출처와 함께 반환한다.",
                "data_source": "내부 예산 DB 읽기 전용 뷰",
                "use_model": False,
                "source_included": True,
            }
        )
        self.assertEqual(data["manifest"]["executionAdapter"]["kind"], "retrieval")
        rejected_data = self.backend.validate_mcp_draft(data["id"], {})
        self.assertEqual(rejected_data["status"], "rejected")
        attached_data = self.backend.add_mcp_draft_reference(
            data["id"],
            {
                "filename": "budget-policy-2027.pdf",
                "role": "data-source",
                "content_base64": base64.b64encode(searchable_budget_pdf()).decode(),
            },
        )
        self.assertTrue(attached_data["reference"]["summary"]["ragReady"])
        self.assertGreater(attached_data["reference"]["summary"]["chunks"], 0)
        preview = self.backend.query_mcp_draft_rag(
            data["id"], {"query": "Budget policy total amount", "actor": "tester"}
        )
        self.assertTrue(preview["hits"])
        self.assertIn("1,234 million won", preview["hits"][0]["excerpt"])
        report_preview = self.backend.query_mcp_draft_rag(
            data["id"],
            {"query": "Budget policy total amount", "report": True, "actor": "tester"},
        )
        self.assertEqual(report_preview["responseType"], "report-artifact")
        preview_hwpx = base64.b64decode(report_preview["artifact"]["contentBase64"])
        preview_document = self.backend.parse_hwpx(preview_hwpx, report_preview["artifact"]["filename"])
        self.assertIn("1,234 million won", "\n".join(item["text"] for item in preview_document["paragraphs"]))
        self.assertEqual(self.backend.validate_mcp_draft(data["id"], {})["status"], "validated")
        self.assertIn("data.query", data["manifest"]["capabilities"])

        published_data = self.backend.publish_mcp_draft(
            data["id"], {"confirm_visibility": "private", "confirm_source_included": True}
        )
        manifest = published_data["package"]["manifest"]
        self.backend.install_mcp_package(
            {
                "package_id": manifest["id"],
                "version": manifest["version"],
                "approved_permissions": [item["scope"] for item in manifest["permissions"]],
                "acknowledge_signature": True,
            }
        )
        intent = "Budget policy total amount 조회해줘"
        resolved = self.backend.resolve_capabilities({"intent": intent, "limit": 1})
        self.assertEqual(resolved["items"][0]["packageRef"], "org.budget-data-rag@0.1.0")
        plan = self.backend.create_plan({"intent": intent, "document_context": {"classification": "internal"}})
        approval = self.backend.approve_plan(
            {"plan_id": plan["id"], "permissions": plan["requiredPermissions"]}
        )
        execution = self.backend.execute_plan(
            {"approval_token": approval["approvalToken"], "idempotency_key": "data-rag-runtime", "input": {}}
        )
        result = execution["result"]
        self.assertEqual(result["responseType"], "context-answer")
        self.assertEqual(result["model"]["mode"], "rag-local-evidence")
        self.assertIn("1,234 million won", result["answer"])
        self.assertEqual(result["sources"][0]["locator"], "budget-policy-2027.pdf · 1쪽")
        report_intent = "Budget policy total amount를 근거 보고서로 작성해줘"
        report_plan = self.backend.create_plan(
            {"intent": report_intent, "document_context": {"classification": "internal"}}
        )
        self.assertEqual(report_plan["workflow"]["responseType"], "report-artifact")
        self.assertIn("document.write", report_plan["requiredPermissions"])
        self.assertFalse(report_plan["dataPolicy"]["externalTransfer"])
        report_approval = self.backend.approve_plan(
            {"plan_id": report_plan["id"], "permissions": report_plan["requiredPermissions"]}
        )
        report_execution = self.backend.execute_plan(
            {
                "approval_token": report_approval["approvalToken"],
                "idempotency_key": "data-rag-report-runtime",
                "input": {},
            }
        )
        report_result = report_execution["result"]
        self.assertEqual(report_result["responseType"], "report-artifact")
        self.assertIn("document.report-hwpx@0.1.0", report_result["loadedMcps"])
        report_bytes = base64.b64decode(report_result["artifact"]["contentBase64"])
        report_document = self.backend.parse_hwpx(report_bytes, report_result["artifact"]["filename"])
        self.assertIn("1,234 million won", "\n".join(item["text"] for item in report_document["paragraphs"]))

        live_response = {
            "content": "## 핵심 결론\nBudget policy total amount는 1,234 million won으로 확인됩니다. [1]\n\n## 시사점\n근거 수치의 기준연도와 집행 범위를 함께 검토해야 합니다. [1]",
            "resolvedModel": "solar-pro4-260806",
            "usage": {"prompt_tokens": 50, "completion_tokens": 40},
            "requestId": "live-data-report",
        }
        with mock.patch.dict(
            os.environ,
            {"AIWORKS_SOLAR_LIVE": "1", "UPSTAGE_API_KEY": "test-upstage-key"},
        ), mock.patch.object(self.backend, "_openrouter_chat", return_value=live_response) as solar:
            live_plan = self.backend.create_plan(
                {"intent": report_intent, "document_context": {"classification": "internal"}}
            )
            self.assertTrue(live_plan["workflow"]["liveModelRequired"])
            self.assertEqual(live_plan["workflow"]["selectedModel"], "upstage:solar-pro4")
            self.assertIn("model.invoke", live_plan["requiredPermissions"])
            self.assertIn("network.send", live_plan["requiredPermissions"])
            live_approval = self.backend.approve_plan(
                {"plan_id": live_plan["id"], "permissions": live_plan["requiredPermissions"]}
            )
            live_execution = self.backend.execute_plan(
                {
                    "approval_token": live_approval["approvalToken"],
                    "idempotency_key": "data-rag-report-solar-runtime",
                    "input": {"project_markdown_transfer_approved": True},
                }
            )
        solar.assert_called_once()
        live_result = live_execution["result"]
        self.assertEqual(live_result["model"]["mode"], "rag-live")
        self.assertEqual(live_result["model"]["resolvedModel"], "solar-pro4-260806")
        live_document = self.backend.parse_hwpx(
            base64.b64decode(live_result["artifact"]["contentBase64"]),
            live_result["artifact"]["filename"],
        )
        live_text = "\n".join(item["text"] for item in live_document["paragraphs"])
        self.assertIn("시사점", live_text)
        self.assertIn("1,234 million won", live_text)

    def test_data_mcp_resolver_uses_rag_content_for_korean_confirmation_request(self):
        draft = self.backend.create_mcp_draft(
            {
                "name": "예산 정책 데이터 MCP",
                "package_id": "org.korean-budget-data",
                "description": "등록된 정책 자료를 근거와 함께 조회한다.",
                "mcp_type": "data",
                "instructions": "질문의 기관, 연도, 정책 항목을 확인하고 원문 근거를 반환한다.",
                "procedure": "질의를 분석한다.\n관련 청크를 검색한다.\n출처와 함께 답한다.",
                "data_source": "행정안전부 예산 분석 보고서",
                "source_included": True,
                "visibility": "private",
                "use_model": False,
            }
        )
        self.backend.add_mcp_draft_reference(
            draft["id"],
            {
                "filename": "2025-2026-행정안전부-분석.txt",
                "role": "data-source",
                "content_base64": base64.b64encode(
                    "2025년 행정안전부 범정부 인공지능 공통기반은 2026년 구축 지연으로 중복투자 우려가 지적되었다.".encode()
                ).decode(),
            },
        )
        self.backend.validate_mcp_draft(draft["id"], {})
        published = self.backend.publish_mcp_draft(
            draft["id"], {"confirm_visibility": "private", "confirm_source_included": True}
        )
        manifest = published["package"]["manifest"]
        self.backend.install_mcp_package(
            {
                "package_id": manifest["id"],
                "version": manifest["version"],
                "approved_permissions": [item["scope"] for item in manifest["permissions"]],
                "acknowledge_signature": True,
            }
        )

        resolved = self.backend.resolve_capabilities(
            {"intent": "행안부 25년, 26년 인공지능 공통기반 주요 지적사항을 확인해줘", "limit": 1}
        )

        self.assertTrue(resolved["resolved"])
        self.assertEqual(resolved["items"][0]["packageRef"], "org.korean-budget-data@0.1.0")
        self.assertIn("rag-content-topic", resolved["items"][0]["matchedBy"])

    def test_fresh_data_report_uses_uploaded_template_and_ignores_open_stale_report(self):
        data_draft = self.backend.create_mcp_draft(
            {
                "name": "예산 정책 데이터 MCP",
                "package_id": "org.ai-budget-data",
                "description": "등록한 예산 정책 자료에서 인공지능 공통기반 지적사항과 수치를 조회한다.",
                "mcp_type": "data",
                "instructions": "질문의 사업명과 연도를 확인하고 해당 사업의 근거만 반환한다.",
                "procedure": "사업명을 확인한다.\n관련 청크를 검색한다.\n근거를 반환한다.",
                "trigger_examples": "인공지능 공통기반 예산 지적사항을 확인해줘",
                "data_source": "행정안전부 예산 분석 자료",
                "source_included": True,
                "use_model": False,
            }
        )
        source_text = (
            "2026년 인공지능 공통기반 예산 지적사항은 사전계획 수립 지연과 개별 사업 중복투자 우려이다. "
            "대안으로 사전검토 완료 후 예산을 편성하고 공통기반 활용계획을 의무화할 필요가 있다. "
            + ("일반 행정자료 설명. " * 120)
            + "2026년 지역균형발전 사업은 별도 사업으로 검토한다."
        )
        self.backend.add_mcp_draft_reference(
            data_draft["id"],
            {
                "filename": "2026-행안부-예산분석.txt",
                "role": "data-source",
                "content_base64": base64.b64encode(source_text.encode()).decode(),
            },
        )
        template_draft = self.backend.create_mcp_draft(
            {
                "name": "행안부 보고 양식 MCP",
                "package_id": "org.mois-uploaded-template",
                "description": "사용자가 등록한 행정안전부 HWPX 양식으로 새 보고서를 변환한다.",
                "mcp_type": "template",
                "instructions": "업로드된 양식의 제목과 본문 위치에 새 보고서 내용을 적용한다.",
                "procedure": "양식을 분석한다.\n제목과 본문을 적용한다.\n새 HWPX를 저장한다.",
                "trigger_examples": "행안부 보고서 양식으로 작성해줘",
                "source_included": True,
                "use_model": False,
            }
        )
        self.backend.add_mcp_draft_reference(
            template_draft["id"],
            {
                "filename": "사용자-행안부-양식.hwpx",
                "role": "template-source",
                "content_base64": base64.b64encode(placeholder_template_hwpx()).decode(),
            },
        )
        for draft in (data_draft, template_draft):
            self.backend.validate_mcp_draft(draft["id"], {})
            published = self.backend.publish_mcp_draft(
                draft["id"],
                {"confirm_visibility": "private", "confirm_source_included": True},
            )
            manifest = published["package"]["manifest"]
            self.backend.install_mcp_package(
                {
                    "package_id": manifest["id"],
                    "version": manifest["version"],
                    "approved_permissions": [item["scope"] for item in manifest["permissions"]],
                    "acknowledge_signature": True,
                }
            )
        stale_hwpx = self.backend.REPORT_HWPX_MCP.build(
            "과거 보고서",
            "# 과거 보고서\n\n## 대상\n- 인구감소지역-기업 상생협업활성화 지원",
        )
        session = self.backend.open_native_document_session(
            {
                "filename": "과거보고서.hwpx",
                "content_base64": base64.b64encode(stale_hwpx).decode(),
                "confirmed": True,
            }
        )
        intent = "인공지능 공통기반 관련 26년 예산 지적사항을 확인하고 이에 대한 대안을 포함해서 행안부 보고서 양식으로 작성해줘"
        plan = self.backend.create_plan(
            {
                "intent": intent,
                "document_context": {
                    "classification": "internal",
                    "has_attachment": True,
                    "document_id": session["id"],
                    "document_excerpt": "인구감소지역-기업 상생협업활성화 지원",
                },
            }
        )
        self.assertEqual(plan["workflow"]["contextPriority"], "data-source")
        self.assertEqual(plan["workflow"]["markdownContext"], [])
        self.assertEqual(
            [item["mcpType"] for item in plan["workflow"]["capabilityBindings"][:2]],
            ["data", "template"],
        )
        self.assertNotIn("template.mois-report@0.1.0", plan["workflow"]["loadedMcps"])
        approval = self.backend.approve_plan(
            {"plan_id": plan["id"], "permissions": plan["requiredPermissions"]}
        )
        execution = self.backend.execute_plan(
            {"approval_token": approval["approvalToken"], "idempotency_key": "fresh-data-uploaded-template", "input": {}},
            force_local=True,
        )
        artifact = execution["result"]["artifact"]
        self.assertEqual(artifact["template"]["packageRef"], "org.mois-uploaded-template@0.1.0")
        self.assertEqual(artifact["template"]["source"], "사용자-행안부-양식.hwpx")
        parsed = self.backend.parse_hwpx(base64.b64decode(artifact["contentBase64"]), artifact["filename"])
        rendered = " ".join(item["text"] for item in parsed["paragraphs"])
        self.assertIn("인공지능 공통기반", rendered)
        self.assertNotIn("인구감소지역-기업", rendered)
        self.assertNotIn("지역균형발전", rendered)

    def test_data_mcp_uses_local_llm_to_synthesize_requested_structure(self):
        draft = self.backend.create_mcp_draft(
            {
                "name": "연도별 예산 데이터 MCP",
                "package_id": "org.yearly-budget-data",
                "description": "등록된 예산 정책 자료를 검색하고 연도별 지적사항을 정리한다.",
                "mcp_type": "data",
                "instructions": "검색 근거를 읽고 사용자가 요구한 분류 기준으로 종합하며 출처를 표시한다.",
                "procedure": "관련 청크를 검색한다.\n연도별로 비교·종합한다.\n근거 번호를 연결한다.",
                "trigger_examples": "인공지능 공통기반 예산 지적사항을 연도별로 정리해줘",
                "data_source": "행정안전부 예산 분석 자료",
                "source_included": True,
                "use_model": False,
            }
        )
        self.backend.add_mcp_draft_reference(
            draft["id"],
            {
                "filename": "ai-budget.txt",
                "role": "data-source",
                "content_base64": base64.b64encode(
                    "2025년 인공지능 공통기반은 계획 수립 전에 예산이 편성되었다. 2026년에는 개별 사업의 선행 착수로 중복투자 우려가 있다.".encode()
                ).decode(),
            },
        )
        self.backend.validate_mcp_draft(draft["id"], {})
        published = self.backend.publish_mcp_draft(
            draft["id"], {"confirm_visibility": "private", "confirm_source_included": True}
        )
        manifest = published["package"]["manifest"]
        self.backend.install_mcp_package(
            {
                "package_id": manifest["id"],
                "version": manifest["version"],
                "approved_permissions": [item["scope"] for item in manifest["permissions"]],
                "acknowledge_signature": True,
            }
        )
        binding = self.backend.resolve_capabilities(
            {"intent": "인공지능 공통기반 예산 지적사항을 연도별로 정리해줘", "limit": 1}
        )["items"][0]
        synthesized = "2025년: 사전계획 미비 상태의 예산 편성 [1]\n2026년: 개별 사업 선행 착수에 따른 중복투자 우려 [1]"
        with mock.patch.dict(os.environ, {"AIWORKS_LOCAL_RAG_LLM": "1"}), mock.patch.object(
            self.backend,
            "_ollama_chat",
            return_value={
                "content": synthesized,
                "resolvedModel": "qwen3:4b-instruct-2507-q4_K_M",
                "usage": {"input_tokens": 120, "output_tokens": 45},
                "requestId": "local-rag-test",
            },
        ) as chat:
            result = self.backend._execute_builder_binding(
                binding,
                "인공지능 공통기반 예산 지적사항을 연도별로 정리해줘",
                {},
                {"model": {"id": "upstage/solar-pro-3"}},
                False,
            )

        chat.assert_called_once()
        self.assertEqual(result["answer"], synthesized)
        self.assertEqual(result["model"]["mode"], "rag-local-llm")
        self.assertEqual(result["model"]["provider"], "ollama")
        self.assertFalse(result["model"]["externalTransfer"])

    def test_korean_rag_query_normalizes_agency_aliases_particles_and_compounds(self):
        tokens = self.backend._rag_query_tokens(
            "행안부 인공지능 공통기반에 대해 예산관련 지적사항을 연도별로 정리해줘"
        )

        self.assertIn("행정안전부", tokens)
        self.assertIn("공통기반", tokens)
        self.assertIn("예산", tokens)
        self.assertIn("지적사항", tokens)
        self.assertNotIn("대해", tokens)
        self.assertNotIn("정리해줘", tokens)

    def test_rag_ranking_prefers_consecutive_topic_phrase_over_generic_budget_terms(self):
        chunks = [
            {"filename": "예산분석.txt", "content": "행정안전부 다른 사업의 예산 관련 국회 지적사항", "searchText": "행정안전부 다른 사업의 예산 관련 국회 지적사항", "chunkIndex": 0},
            {"filename": "예산분석.txt", "content": "행정안전부 인공지능 공통기반 예산의 구축 지연 지적사항", "searchText": "행정안전부 인공지능 공통기반 예산의 구축 지연 지적사항", "chunkIndex": 1},
        ]

        hits = self.backend._search_rag_chunks(
            chunks,
            "행안부 인공지능 공통기반에 대해 예산관련 지적사항을 연도별로 정리해줘",
            limit=2,
        )

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["chunkIndex"], 1)

    def test_rag_prompt_lists_detected_business_years_for_structured_synthesis(self):
        messages = self.backend._rag_runtime_messages(
            {"builderGuide": {}},
            "예산 지적사항을 연도별로 정리해줘",
            [{"filename": "분석.pdf", "pageNumber": 1, "content": "2025년 예산 편성 문제와 2026년 중복투자 우려"}],
        )

        self.assertIn("2025년, 2026년", messages[0]["content"])
        self.assertIn("별도 행", messages[0]["content"])
        self.assertIn("단순 예산 현황", messages[0]["content"])
        self.assertIn("다른 연도에 복사하지", messages[0]["content"])

    def test_rag_synthesis_rejects_answers_without_citations_or_required_years(self):
        hits = [{"content": "2025년 편성 문제와 2026년 중복투자 우려"}]
        with self.assertRaises(self.backend.ApiError):
            self.backend._validate_rag_synthesis(
                "지적사항을 연도별로 정리해줘", "2025년 편성 문제, 2026년 중복투자 우려", hits
            )
        with self.assertRaises(self.backend.ApiError):
            self.backend._validate_rag_synthesis(
                "지적사항을 연도별로 정리해줘", "2025년 편성 문제 [1]", hits
            )
        accepted = self.backend._validate_rag_synthesis(
            "지적사항을 연도별로 정리해줘", "2025년 편성 문제 [1]\n2026년 중복투자 우려 [1]", hits
        )
        self.assertIn("2026년", accepted)

    def test_local_evidence_report_keeps_requested_years_and_clean_title(self):
        query = "행안부 25년, 26년 인공지능 공통기반 지적사항을 연도별 보고서로 작성해줘"
        hits = [
            {
                "filename": "2025회계연도 결산 분석.pdf",
                "pageNumber": 76,
                "content": "2025년 인공지능 공통기반은 사전 계획 수립 전에 예산이 편성되어 개선이 필요하다.",
            },
            {
                "filename": "2026년도 예산안 분석.pdf",
                "pageNumber": 25,
                "content": "개별 사업 선행 착수로 중복투자 우려가 있어 범정부 공통기반과의 조정이 필요하다.",
            },
        ]

        report = self.backend._rag_evidence_report(query, hits)
        self.assertIn("### 2025년", report)
        self.assertIn("### 2026년", report)
        self.assertIn("2026년 자료명 기준", report)
        artifact = self.backend._rag_report_artifact(query, hits)
        self.assertNotIn("보고서로 보고서", artifact["filename"])
        self.assertEqual(artifact["title"], "데이터 MCP 근거 분석 보고서")
        self.assertNotIn("작성해줘", artifact["title"])
        self.assertTrue(artifact["contentBase64"])

    def test_installed_builder_package_is_indexed_resolved_and_runs_in_isolation(self):
        draft = self.backend.create_mcp_draft(
            {
                "name": "결재 검토 처리 MCP",
                "package_id": "org.approval-review",
                "description": "결재 요청을 규칙에 따라 검토하고 단계별 결과를 보고서로 작성한다.",
                "mcp_type": "process",
                "instructions": "결재 요청의 누락 항목을 확인하고 처리 절차에 따라 검토 결과를 작성한다.",
                "procedure": "입력 조건을 검사한다.\n누락 항목을 확인한다.\n결과를 보고서로 정리한다.",
                "trigger_examples": "결재 요청을 검토 보고서로 작성해줘",
                "use_model": False,
            }
        )
        self.assertEqual(draft["manifest"]["executionAdapter"]["kind"], "composite")
        self.assertEqual(self.backend.validate_mcp_draft(draft["id"], {})["status"], "validated")
        published = self.backend.publish_mcp_draft(
            draft["id"],
            {"confirm_visibility": "private", "confirm_source_included": False},
        )
        manifest = published["package"]["manifest"]
        self.backend.install_mcp_package(
            {
                "package_id": manifest["id"],
                "version": manifest["version"],
                "approved_permissions": [item["scope"] for item in manifest["permissions"]],
                "acknowledge_signature": True,
            }
        )
        registry = self.backend.list_capability_registry()
        self.assertTrue(any(item["packageRef"] == "org.approval-review@0.1.0" for item in registry["items"]))
        resolved = self.backend.resolve_capabilities(
            {"intent": "결재 요청을 검토 보고서로 작성해줘", "limit": 1}
        )
        self.assertTrue(resolved["resolved"])
        self.assertEqual(resolved["items"][0]["packageRef"], "org.approval-review@0.1.0")
        plan = self.backend.create_plan(
            {"intent": "결재 요청을 검토 보고서로 작성해줘", "document_context": {"classification": "internal"}}
        )
        self.assertTrue(plan["workflow"]["dynamic"])
        self.assertEqual(plan["steps"][0]["mcp"], "org.approval-review@0.1.0")
        isolated = self.backend._execute_builder_binding(
            resolved["items"][0],
            "결재 요청을 검토 보고서로 작성해줘",
            {},
            plan["routing"],
            False,
        )
        self.assertEqual(isolated["responseType"], "report-artifact")
        self.assertIn("org.approval-review@0.1.0", isolated["loadedMcps"])
        approval = self.backend.approve_plan(
            {"plan_id": plan["id"], "permissions": plan["requiredPermissions"]}
        )
        executed = self.backend.execute_plan(
            {
                "approval_token": approval["approvalToken"],
                "idempotency_key": "dynamic-builder-runtime",
                "input": {},
            }
        )
        self.assertEqual(executed["result"]["responseType"], "report-artifact")
        self.assertEqual(executed["result"]["workflow"]["id"], "dynamic.org.approval-review")
        audit = self.backend.list_audit()
        dynamic_audit = next(
            item for item in audit["items"]
            if item["executionId"] == executed["id"] and item["eventType"] == "execution.completed"
        )
        self.assertTrue(dynamic_audit["detail"]["dynamic"])

    def test_builder_template_runtime_preserves_layout_and_replaces_placeholders(self):
        artifact, metadata = self.backend._apply_builder_hwpx_template(
            placeholder_template_hwpx(), sample_hwpx(), "source.hwpx", {"version": "1.0"}
        )
        parsed = self.backend.parse_hwpx(artifact, "result.hwpx")
        texts = [item["text"] for item in parsed["paragraphs"]]
        self.assertIn("사업명: 지능형 민원지원 기반 구축", texts[0])
        self.assertIn("사업기간: 2027.01 ~ 2027.12", texts[1])
        self.assertEqual(metadata["placeholderReplacements"], 3)
        self.assertEqual(metadata["mode"], "explicit-placeholders")

    def test_builder_template_analyzes_and_applies_written_guidance(self):
        profile = self.backend._analyze_hwpx_template(guided_template_hwpx())
        self.assertEqual(profile["mode"], "guided-fields")
        self.assertGreaterEqual(profile["instructionParagraphs"], 2)
        artifact, metadata = self.backend._apply_builder_hwpx_template(
            guided_template_hwpx(), sample_hwpx(), "source.hwpx", {"version": "1.1"}
        )
        text = "\n".join(item["text"] for item in self.backend.parse_hwpx(artifact, "guided-result.hwpx")["paragraphs"])
        self.assertIn("사업명: 지능형 민원지원 기반 구축", text)
        self.assertNotIn("제목 작성요령", text)
        self.assertEqual(metadata["mode"], "guided-fields")

    def test_external_mcp_builder_creates_pinned_local_kordoc_contract(self):
        draft = self.backend.create_mcp_draft(
            {
                "name": "KODAK HWPX 변환 어댑터",
                "package_id": "org.kodak-adapter",
                "description": "공개 KODAK MCP의 HWPX 변환 도구를 AIWorks 보고서 파이프라인에 연결한다.",
                "mcp_type": "external",
                "instructions": "현재 보고서 HWPX를 변환 도구에 전달하고 반환 산출물의 무결성을 검사한다.",
                "procedure": "tools/list를 확인한다.\n도구를 호출한다.\n반환 HWPX를 검사한다.",
                "trigger_examples": "KODAK으로 HWPX를 변환해줘",
                "external_transport": "stdio",
                "external_server_profile": "kordoc@4.7.3",
                "external_tool_name": "generate_document",
                "external_capability": "document.hwpx.finalize",
            }
        )
        manifest = draft["manifest"]
        self.assertEqual(manifest["mcpType"], "external")
        self.assertEqual(manifest["executionAdapter"]["kind"], "external-mcp")
        self.assertEqual(manifest["externalMcp"]["serverProfile"], "kordoc@4.7.3")
        self.assertEqual(manifest["externalMcp"]["toolName"], "generate_document")
        self.assertFalse(manifest["externalMcp"]["documentTransfer"])
        self.assertNotIn("network.send", {item["scope"] for item in manifest["permissions"]})
        with mock.patch.object(self.backend, "_external_profile_status", return_value={"available": False, "reason": "profile-runtime-not-installed"}):
            probed = self.backend.probe_external_mcp_draft(draft["id"], {})
        self.assertFalse(probed["connected"])
        validated = self.backend.validate_mcp_draft(draft["id"], {})
        self.assertTrue(validated["validation"]["passed"])

    def test_builder_template_starter_is_editable_and_contains_placeholders(self):
        starter = self.backend.builder_template_starter()
        artifact = base64.b64decode(starter["contentBase64"], validate=True)
        parsed = self.backend.parse_hwpx(artifact, starter["filename"])
        text = "\n".join(item["text"] for item in parsed["paragraphs"])
        self.assertIn("{{title}}", text)
        self.assertIn("{{content}}", text)
        self.assertIn("{{date}}", text)
        self.assertEqual(starter["mediaType"], "application/hwp+zip")



    def test_template_authoring_sample_opens_rhwp_without_creating_project_markdown(self):
        draft = self.backend.create_mcp_draft(
            {
                "name": "행안부 등록 양식 MCP",
                "package_id": "org.mois-authoring-template",
                "description": "첨부된 행정안전부 보고서 양식을 명시적 슬롯 양식으로 등록한다.",
                "mcp_type": "template",
                "instructions": "등록 양식의 고정 서식을 유지하고 제목과 본문 슬롯에 보고서 내용을 대응한다.",
                "procedure": "양식 원본을 분석한다.\nRHWP에서 슬롯과 서식을 확정한다.\n검증 후 게시한다.",
                "trigger_examples": "행안부 등록 양식으로 보고서를 바꿔줘",
                "source_included": True,
                "use_model": False,
            }
        )
        self.backend.add_mcp_draft_reference(
            draft["id"],
            {
                "filename": "행정안전부-보고서-예시.hwpx",
                "role": "template-source",
                "content_base64": base64.b64encode(sample_form_template_hwpx()).decode(),
            },
        )
        rejected = self.backend.validate_mcp_draft(draft["id"], {})
        structure_test = next(item for item in rejected["validation"]["tests"] if item["id"] == "template.structure")
        self.assertFalse(structure_test["passed"])

        sample = self.backend.build_mcp_template_sample(draft["id"])
        sample_bytes = base64.b64decode(sample["contentBase64"], validate=True)
        sample_text = "\n".join(item["text"] for item in self.backend.parse_hwpx(sample_bytes, sample["filename"])["paragraphs"])
        self.assertIn("{{title}}", sample_text)
        self.assertIn("{{content}}", sample_text)

        session = self.backend.open_mcp_template_authoring_session(draft["id"], {"actor": "builder"})
        self.assertEqual(session["purpose"], "template-authoring")
        self.assertEqual(session["builderDraftId"], draft["id"])
        self.assertIsNone(session["markdownDocumentId"])

        committed = self.backend.commit_mcp_template_authoring(
            draft["id"], {"session_id": session["id"], "actor": "builder"}
        )
        self.assertEqual(committed["reference"]["role"], "template-source")
        self.assertTrue(committed["authoring"]["schema"]["required"]["title"])
        self.assertTrue(committed["authoring"]["schema"]["required"]["body"])
        validated = self.backend.validate_mcp_draft(draft["id"], {})
        self.assertEqual(validated["status"], "validated")



    def test_template_conversion_keeps_first_paragraph_title_and_body_slots_distinct(self):
        converted, authoring = self.backend._build_template_authoring_sample(
            sample_hwpx(),
            "첫문단-제목-일반보고서.hwpx",
        )
        texts = [
            item["text"]
            for item in self.backend.parse_hwpx(converted, "converted.hwpx")["paragraphs"]
            if item.get("text")
        ]
        self.assertEqual(texts.count("{{title}}"), 1)
        self.assertEqual(texts.count("{{content}}"), 1)
        self.assertEqual(authoring["analysis"]["mode"], "explicit-placeholders")
        self.assertTrue(authoring["schema"]["required"]["title"])
        self.assertTrue(authoring["schema"]["required"]["body"])

    def test_template_source_replaces_previous_file_and_can_be_deleted(self):
        draft = self.backend.create_mcp_draft(
            {
                "name": "단일 기준 양식 MCP",
                "description": "등록된 HWPX 한 파일을 기준으로 현재 보고서의 제목과 본문을 해당 형식으로 변환한다.",
                "mcp_type": "template",
                "instructions": "양식 기준 파일은 항상 하나만 유지하고 제목과 본문 슬롯을 확인한다.",
                "procedure": "원본을 확인한다.\n구조를 변환한다.\n결과를 검증한다.",
                "source_included": True,
            }
        )
        first = self.backend.add_mcp_draft_reference(
            draft["id"],
            {
                "filename": "이전-양식.hwpx",
                "role": "template-source",
                "content_base64": base64.b64encode(placeholder_template_hwpx()).decode(),
            },
        )
        second = self.backend.add_mcp_draft_reference(
            draft["id"],
            {
                "filename": "새-양식.hwpx",
                "role": "template-source",
                "content_base64": base64.b64encode(ordinary_completed_report_hwpx()).decode(),
            },
        )
        sources = [item for item in second["draft"]["references"] if item["role"] == "template-source"]
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["filename"], "새-양식.hwpx")
        self.assertNotEqual(sources[0]["id"], first["reference"]["id"])
        deleted = self.backend.dispatch(
            f"/builder/drafts/{draft['id']}/references/{sources[0]['id']}",
            "DELETE",
            {"actor": "builder"},
        )
        self.assertEqual(deleted["deleted"]["filename"], "새-양식.hwpx")
        self.assertEqual(deleted["draft"]["references"], [])
        self.assertEqual(deleted["draft"]["manifest"]["references"], [])
        rejected = self.backend.validate_mcp_draft(draft["id"], {})
        structure = next(item for item in rejected["validation"]["tests"] if item["id"] == "template.structure")
        self.assertFalse(structure["passed"])

    def test_ordinary_hwpx_converts_to_active_downloadable_template_source(self):
        draft = self.backend.create_mcp_draft(
            {
                "name": "일반 보고서 양식 변환 MCP",
                "package_id": "org.ordinary-report-template",
                "description": "일반 완성 보고서 HWPX의 제목과 본문 구조를 분석해 재사용 가능한 양식으로 변환한다.",
                "mcp_type": "template",
                "instructions": "첨부 보고서의 고정 서식은 유지하고 현재 프로젝트 보고서의 제목·절·목록·표를 구조적으로 배치한다.",
                "procedure": "일반 HWPX를 분석한다.\n제목과 본문 prototype을 확정한다.\n변환본을 검증한다.",
                "trigger_examples": "등록한 일반 보고서 양식으로 바꿔줘",
                "source_included": True,
                "use_model": False,
            }
        )
        added = self.backend.add_mcp_draft_reference(
            draft["id"],
            {
                "filename": "완성된-업무보고.hwpx",
                "role": "template-source",
                "content_base64": base64.b64encode(ordinary_completed_report_hwpx()).decode(),
            },
        )
        self.assertEqual(added["reference"]["summary"]["templateProfile"]["mode"], "sample-structure")
        converted = self.backend.dispatch(
            f"/builder/drafts/{draft['id']}/template-convert",
            "POST",
            {"actor": "builder"},
        )
        converted_bytes = base64.b64decode(converted["contentBase64"], validate=True)
        converted_text = "\n".join(
            item["text"] for item in self.backend.parse_hwpx(converted_bytes, converted["filename"])["paragraphs"]
        )
        self.assertIn("{{title}}", converted_text)
        self.assertIn("{{content}}", converted_text)
        self.assertEqual(converted["conversion"]["inference"]["title"], "heuristic-report-title")
        self.assertEqual(converted["conversion"]["inference"]["body"], "heuristic-first-content")
        self.assertTrue(converted["conversion"]["schema"]["structuralBindingReady"])
        template_sources = [item for item in converted["draft"]["references"] if item["role"] == "template-source"]
        self.assertEqual(len(template_sources), 1)
        self.assertEqual(template_sources[0]["sha256"], converted["reference"]["sha256"])
        self.assertTrue(converted["reference"]["summary"]["templateQuality"]["passed"])
        quality = self.backend.dispatch(f"/builder/drafts/{draft['id']}/template-quality", "GET", {})
        self.assertTrue(quality["quality"]["passed"])
        self.assertEqual(quality["quality"]["metrics"]["renderedTables"], 1)
        mapping = self.backend.dispatch(f"/builder/drafts/{draft['id']}/template-mapping", "GET", {})
        self.assertGreater(mapping["mapping"]["total"], 2)
        slots = mapping["mapping"]["currentSlots"]
        corrected = self.backend.dispatch(
            f"/builder/drafts/{draft['id']}/template-mapping",
            "POST",
            {
                "title_locator": slots["title"],
                "body_locator": slots["content"],
                "actor": "builder",
            },
        )
        self.assertTrue(corrected["authoring"]["quality"]["passed"])
        self.assertEqual(corrected["mapping"]["currentSlots"]["title"], slots["title"])

        validated = self.backend.validate_mcp_draft(draft["id"], {})
        self.assertEqual(validated["status"], "validated")
        validation_tests = {item["id"]: item for item in validated["validation"]["tests"]}
        self.assertTrue(validation_tests["template.render-quality"]["passed"])

        report_document = {
            "title": "새로운 정책 검토보고서",
            "blocks": [
                {"id": "h2", "type": "heading", "level": 2, "text": "검토 개요"},
                {"id": "p1", "type": "paragraph", "text": "현재 프로젝트 기준정보를 반영함."},
                {"id": "t1", "type": "table", "rows": [["구분", "결과"], ["검토", "적정"]]},
            ],
        }
        rendered, metadata = self.backend._render_report_document_hwpx_template(
            converted_bytes,
            report_document,
            converted["filename"],
            {"templateName": "일반 보고서 변환 양식"},
        )
        rendered_text = "\n".join(
            item["text"] for item in self.backend.parse_hwpx(rendered, "converted-result.hwpx")["paragraphs"]
        )
        self.assertIn("새로운 정책 검토보고서", rendered_text)
        self.assertIn("□ 검토 개요", rendered_text)
        self.assertNotIn("2026년도 디지털 행정 개선방안 보고서", rendered_text)
        self.assertNotIn("사업계획 확정 전 예산 편성", rendered_text)
        self.assertEqual(metadata["renderedTables"], 1)

    def test_structural_template_renderer_clones_paragraphs_and_real_table_cells(self):
        report_document = {
            "title": "인공지능 공통기반 예산 검토보고",
            "blocks": [
                {"id": "decorative", "type": "heading", "level": 2, "text": "I. ― 인공지능 공통기반 구현 사업 ―"},
                {"id": "overview", "type": "heading", "level": 2, "text": "II. 분석 개요"},
                {"id": "body", "type": "paragraph", "text": "**분석 대상**: 2026년 예산안"},
                {"id": "detail", "type": "list_item", "level": 2, "text": "집행 지연 원인을 점검함."},
                {"id": "reference", "type": "list_item", "level": 3, "text": "세부 산출근거를 별도로 확인함."},
                {
                    "id": "table",
                    "type": "table",
                    "rows": [
                        ["구분", "내용"],
                        ["지적사항", "사업계획 확정 전 예산 편성"],
                        ["향후 방안", "단계별 검증 후 집행"],
                    ],
                },
            ],
        }
        rendered, metadata = self.backend._render_report_document_hwpx_template(
            sample_form_template_hwpx(),
            report_document,
            "source.hwpx",
            {"templateName": "행안부 테스트 양식"},
        )
        parsed = self.backend.parse_hwpx(rendered, "result.hwpx")
        texts = [item["text"] for item in parsed["paragraphs"] if item.get("text")]
        self.assertEqual(metadata["mode"], "report-document-structural")
        self.assertEqual(metadata["renderedTables"], 1)
        self.assertEqual(parsed["stats"]["tables"], 1)
        self.assertEqual(parsed["stats"]["cells"], 6)
        self.assertIn("□ 분석 개요", texts)
        self.assertIn("○ 분석 대상: 2026년 예산안", texts)
        self.assertIn("※ 세부 산출근거를 별도로 확인함.", texts)
        self.assertIn("- 집행 지연 원인을 점검함.", texts)
        self.assertIn("향후 방안", texts)
        self.assertFalse(any("| --- |" in value or "**" in value for value in texts))
        self.assertTrue(metadata["indentationApplied"])
        self.assertEqual(metadata["indentationLevels"], [0, 1400, 2800, 4200])
        with zipfile.ZipFile(io.BytesIO(rendered)) as archive:
            header_root = ElementTree.fromstring(archive.read("Contents/header.xml"))
            section_root = ElementTree.fromstring(archive.read("Contents/section0.xml"))
        local_name = lambda tag: tag.rsplit("}", 1)[-1]
        style_left = {}
        for style in (item for item in header_root.iter() if local_name(item.tag) == "paraPr"):
            left = next((item for item in style.iter() if local_name(item.tag) == "left"), None)
            style_left[str(style.attrib.get("id") or "")] = int((left.attrib if left is not None else {}).get("value") or 0)
        paragraph_left = {}
        for paragraph in (item for item in section_root.iter() if local_name(item.tag) == "p"):
            value = "".join(str(item.text or "") for item in paragraph.iter() if local_name(item.tag) == "t").strip()
            if value:
                paragraph_left[value] = style_left.get(str(paragraph.attrib.get("paraPrIDRef") or ""), 0)
        self.assertEqual(paragraph_left["□ 분석 개요"], 0)
        self.assertEqual(paragraph_left["○ 분석 대상: 2026년 예산안"], 1400)
        self.assertEqual(paragraph_left["- 집행 지연 원인을 점검함."], 2800)
        self.assertEqual(paragraph_left["※ 세부 산출근거를 별도로 확인함."], 4200)
        self.assertFalse(any("인공지능 공통기반 구현 사업 ―" in value for value in texts))

    def test_builder_prompt_runtime_uses_approved_live_model(self):
        draft = self.backend.create_mcp_draft(
            {
                "name": "회의 핵심 요약 MCP",
                "package_id": "org.meeting-summary",
                "description": "회의 기록에서 결정 사항과 후속 조치를 빠르게 요약한다.",
                "mcp_type": "tool",
                "instructions": "회의 기록을 읽고 결정 사항과 담당자별 후속 조치만 간결하게 반환한다.",
                "procedure": "회의 기록을 분석한다.\n결정 사항과 후속 조치를 정리한다.",
                "trigger_examples": "회의 핵심과 후속 조치를 요약해줘",
                "use_model": True,
                "allow_external": True,
            }
        )
        self.backend.validate_mcp_draft(draft["id"], {})
        published = self.backend.publish_mcp_draft(
            draft["id"],
            {"confirm_visibility": "private", "confirm_source_included": False},
        )
        manifest = published["package"]["manifest"]
        self.assertEqual(manifest["executionAdapter"]["kind"], "prompt")
        self.backend.install_mcp_package(
            {
                "package_id": manifest["id"],
                "version": manifest["version"],
                "approved_permissions": [item["scope"] for item in manifest["permissions"]],
                "acknowledge_signature": True,
            }
        )
        plan = self.backend.create_plan(
            {"intent": "회의 핵심과 후속 조치를 요약해줘", "document_context": {"classification": "internal"}}
        )
        approval = self.backend.approve_plan(
            {"plan_id": plan["id"], "permissions": plan["requiredPermissions"]}
        )
        live_response = {
            "content": "결정 사항: 시범 운영 승인\n후속 조치: 담당 부서가 일정 확정",
            "resolvedModel": "upstage/solar-pro-3",
            "usage": {"input_tokens": 30, "output_tokens": 18},
            "requestId": "builder-prompt-test",
        }
        with mock.patch.dict(os.environ, {"AIWORKS_SOLAR_LIVE": "1", "UPSTAGE_API_KEY": "test-upstage-key"}), mock.patch.object(
            self.backend, "_openrouter_chat", return_value=live_response
        ) as chat:
            executed = self.backend.execute_plan(
                {"approval_token": approval["approvalToken"], "idempotency_key": "builder-prompt-live", "input": {}}
            )
        self.assertEqual(chat.call_count, 1)
        self.assertEqual(executed["result"]["responseType"], "text-answer")
        self.assertIn("시범 운영 승인", executed["result"]["answer"])
        self.assertEqual(executed["result"]["model"]["mode"], "live")

    def test_builder_prompt_runtime_never_sends_without_network_permission(self):
        draft = self.backend.create_mcp_draft(
            {
                "name": "비공개 회의 요약 MCP",
                "package_id": "org.local-meeting-summary",
                "description": "내부 회의 기록을 외부 전송 없이 핵심 항목으로 요약한다.",
                "mcp_type": "tool",
                "instructions": "내부 회의 기록에서 결정 사항과 후속 조치를 분리해 요약한다.",
                "procedure": "입력을 확인한다.\n결정 사항과 후속 조치를 정리한다.",
                "trigger_examples": "비공개 회의 내용을 요약해줘",
                "use_model": True,
                "allow_external": False,
            }
        )
        self.backend.validate_mcp_draft(draft["id"], {})
        published = self.backend.publish_mcp_draft(
            draft["id"],
            {"confirm_visibility": "private", "confirm_source_included": False},
        )
        manifest = published["package"]["manifest"]
        permissions = [item["scope"] for item in manifest["permissions"]]
        self.assertNotIn("network.send", permissions)
        self.backend.install_mcp_package(
            {"package_id": manifest["id"], "version": manifest["version"], "approved_permissions": permissions, "acknowledge_signature": True}
        )
        plan = self.backend.create_plan(
            {"intent": "비공개 회의 내용을 요약해줘", "document_context": {"classification": "internal"}}
        )
        approval = self.backend.approve_plan(
            {"plan_id": plan["id"], "permissions": plan["requiredPermissions"]}
        )
        with mock.patch.dict(os.environ, {"AIWORKS_SOLAR_LIVE": "1", "UPSTAGE_API_KEY": "test-upstage-key"}), mock.patch.object(
            self.backend, "_openrouter_chat"
        ) as chat:
            executed = self.backend.execute_plan(
                {"approval_token": approval["approvalToken"], "idempotency_key": "builder-prompt-local-only", "input": {}}
            )
        chat.assert_not_called()
        self.assertEqual(executed["result"]["model"]["mode"], "builder-composite")
        self.assertFalse(executed["result"]["model"]["externalTransfer"])

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
        self.assertEqual(code_plan["model"]["id"], "upstage:solar-pro4")
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
        self.assertEqual(checks["models.registry"]["status"], "pass")
        self.assertEqual(checks["data-mcp.pdf-extractor"]["status"], "pass")
        self.assertEqual(self.backend._pdf_text_extractor_path(), "/usr/bin/pdftotext")
        self.assertIn(checks["adapters.runtime"]["status"], {"pass", "warn"})
        with self.backend._connect() as db:
            db.execute("DELETE FROM knowledge_edges")
            db.execute("DELETE FROM knowledge_sources")
        without_sources = self.backend.operational_readiness()
        source_check = next(item for item in without_sources["checks"] if item["id"] == "knowledge.sources")
        self.assertTrue(without_sources["ready"])
        self.assertEqual(source_check["status"], "warn")

    def test_pdf_extraction_uses_absolute_binary_when_service_path_is_restricted(self):
        with mock.patch.dict(os.environ, {"PATH": str(ROOT / ".venv" / "bin")}, clear=False):
            pages = self.backend._extract_pdf_pages(searchable_budget_pdf())
        self.assertEqual(pages[0][0], 1)
        self.assertIn("1,234 million won", pages[0][1])

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

    def test_report_document_normalizes_duplicate_markers_and_outline_style(self):
        document = self.backend.REPORT_DOCUMENT_MCP.parse(
            "# 검토 보고\n\n- · 100입니다.\n- • 추진이 필요합니다.",
            title="검토 보고",
            style_profile="central-government-outline",
        )
        self.assertTrue(document["validation"]["passed"])
        self.assertEqual(document["normalizedMarkdown"].count("# 검토 보고"), 1)
        self.assertIn("- 100임.", document["normalizedMarkdown"])
        self.assertIn("- 추진이 필요함.", document["normalizedMarkdown"])
        self.assertNotIn("- ·", document["normalizedMarkdown"])
        self.assertNotIn("- •", document["normalizedMarkdown"])
        self.assertTrue(all(not str(item.get("text") or "").startswith(("-", "·", "•")) for item in document["blocks"] if item["type"] == "list_item"))

    def test_report_h1_replaces_prompt_fallback_and_body_sections_restart_at_one(self):
        artifact = self.backend._build_structured_report_artifact(
            "26년 예산 지적 사항을 바탕으로 행안부 양식으로 작성해줘 보고서",
            (
                "# I. 2026년도 행정안전부 예산안 분석 및 개선방안 보고서\n\n"
                "## II. 분석 개요\n- 분석 대상은 행정안전부 예산안입니다.\n\n"
                "## III. 주요 지적사항 및 개선방안\n- 집행 가능성을 점검합니다."
            ),
            "행안부 중앙부처 개조식 보고서로 작성해줘",
        )

        self.assertEqual(artifact["title"], "2026년도 행정안전부 예산안 분석 및 개선방안 보고서")
        self.assertTrue(artifact["content"].startswith("# 2026년도 행정안전부 예산안 분석 및 개선방안 보고서\n"))
        self.assertIn("## I. 분석 개요", artifact["content"])
        self.assertIn("## II. 주요 지적사항 및 개선방안", artifact["content"])
        self.assertNotIn("작성해줘 보고서\n", artifact["content"])
        self.assertEqual(artifact["filename"], "2026년도 행정안전부 예산안 분석 및 개선방안 보고서.hwpx")

    def test_central_report_normalizes_numeric_top_level_sections_to_roman(self):
        document = self.backend.REPORT_DOCUMENT_MCP.parse(
            "# 2026년도 행정안전부 예산안 분석 및 개선방안 보고서\n\n## 1. 분석 개요\n\n## 2. 주요 지적사항",
            title="사용자 요청문 보고서",
            style_profile="central-government-outline",
        )

        self.assertEqual(document["title"], "2026년도 행정안전부 예산안 분석 및 개선방안 보고서")
        self.assertIn("## I. 분석 개요", document["normalizedMarkdown"])
        self.assertIn("## II. 주요 지적사항", document["normalizedMarkdown"])

    def test_structured_report_binds_project_facts_and_exposes_template_contract(self):
        facts = self.backend.list_project_facts("project-default")["snapshot"]
        artifact = self.backend._build_structured_report_artifact(
            "사업 검토",
            "## 산정 기준\n- · 월평균임금은 {{fact:cost.engineer.monthly}}입니다.",
            "중앙부처 개조식 보고서로 작성해줘",
            fact_snapshot=facts,
        )
        self.assertEqual(artifact["template"]["id"], "central-government-outline.v2")
        self.assertEqual(artifact["template"]["rendererOptions"]["preset"], "개조식")
        self.assertEqual(artifact["reportDocument"]["presentation"]["markerOwnership"], "renderer")
        self.assertIn("cost.engineer.monthly", artifact["reportDocument"]["factRefs"])
        self.assertNotIn("- ·", artifact["content"])
        self.assertIn("document.report-structure@0.1.0", artifact["generatedBy"])
        self.assertTrue(base64.b64decode(artifact["contentBase64"]).startswith(b"PK"))

    def test_report_plan_snapshots_project_facts_and_declares_five_stage_pipeline(self):
        plan = self.backend.create_plan(
            {
                "intent": "사업 현황을 중앙부처 개조식 보고서로 작성해줘",
                "document_context": {"classification": "internal", "project_id": "project-default"},
            }
        )
        self.assertEqual(plan["project"]["id"], "project-default")
        self.assertGreater(plan["project"]["factCount"], 0)
        self.assertEqual(len(plan["workflow"]["documentPipeline"]), 6)
        self.assertIn("document.report-structure@0.1.0", plan["workflow"]["loadedMcps"])
        self.assertIn("document.quality-harness@0.1.0", plan["workflow"]["loadedMcps"])
        self.assertIn("template.report-style@0.1.0", plan["workflow"]["loadedMcps"])
        self.assertEqual(plan["workflow"]["styleProfile"], "central-government-outline")
        approval = self.backend.approve_plan({"plan_id": plan["id"], "permissions": plan["requiredPermissions"]})
        execution = self.backend.execute_plan(
            {"approval_token": approval["approvalToken"], "idempotency_key": "structured-report-snapshot", "input": {}},
            force_local=True,
        )
        artifact = execution["result"]["artifact"]
        self.assertTrue(artifact["reportDocument"]["validation"]["passed"])
        self.assertEqual(set(artifact["factSnapshot"]["facts"]), set(plan["workflow"]["factSnapshot"]["facts"]))
        with self.backend._connect() as db:
            stored = db.execute("SELECT * FROM report_fact_snapshots WHERE execution_id=?", (execution["id"],)).fetchone()
        self.assertIsNotNone(stored)
        self.assertTrue(artifact["markdownDocument"]["sourceOfTruth"])
        self.assertEqual(artifact["sourceOfTruth"]["status"], "persisted")

    def test_project_registry_restores_markdown_metadata_and_derived_files(self):
        project = self.backend.create_project(
            {"name": "인공지능 예산 검토", "classification": "internal", "actor": "registry-tester"}
        )
        self.assertTrue(project["id"].startswith("project-"))
        document = self.backend.save_project_markdown_document(
            project["id"],
            {"title": "예산 검토 보고", "markdown": "# 예산 검토 보고\n\n- 총사업비: 100백만원", "actor": "registry-tester"},
        )
        self.backend.save_project_fact(
            project["id"],
            {"key": "project.department", "label": "담당부서", "value": "디지털정책과", "status": "confirmed", "actor": "registry-tester"},
        )
        rendered = self.backend.render_project_markdown_document(
            project["id"], document["id"], {"format": "hwpx", "actor": "registry-tester"}
        )

        registry = self.backend.list_projects()
        listed = next(item for item in registry["items"] if item["id"] == project["id"])
        self.assertEqual(listed["documentCount"], 1)
        self.assertEqual(listed["factCount"], 1)
        self.assertEqual(listed["artifactCount"], 1)

        workspace = self.backend.get_project_workspace(project["id"])
        self.assertEqual(workspace["project"]["name"], "인공지능 예산 검토")
        self.assertEqual(workspace["summary"], {"documentCount": 1, "factCount": 1, "candidateCount": 1, "artifactCount": 1})
        self.assertEqual(workspace["documents"][0]["id"], document["id"])
        self.assertEqual(workspace["documents"][0]["artifacts"][0]["id"], rendered["projectArtifact"]["id"])
        self.assertEqual(workspace["metadata"]["facts"]["project.department"]["value"], "디지털정책과")

    def test_project_workspace_restores_last_document_tab_view_and_chat(self):
        project = self.backend.create_project({"name": "연속 작업 검증", "actor": "tester"})
        document = self.backend.save_project_markdown_document(
            project["id"], {"markdown": "# 연속 작업 검증\n\n- 마지막 화면을 복원함.", "actor": "tester"}
        )
        saved = self.backend.save_project_workspace_state(project["id"], {
            "active_document_id": document["id"],
            "active_tab": "artifact:hwpx",
            "active_view": "editor",
            "chat": [
                {"role": "user", "text": "이 보고서를 계속 수정해줘"},
                {"role": "assistant", "text": "마지막 작업을 저장했습니다."},
            ],
            "last_answer": "마지막 작업을 저장했습니다.",
            "actor": "tester",
        })
        self.assertEqual(saved["activeDocumentId"], document["id"])
        restored = self.backend.get_project_workspace(project["id"])["workspaceState"]
        self.assertEqual(restored["activeTab"], "artifact:hwpx")
        self.assertEqual(restored["activeView"], "editor")
        self.assertEqual(restored["chat"][0]["role"], "user")
        self.assertEqual(restored["lastAnswer"], "마지막 작업을 저장했습니다.")

    def test_quality_harness_rejects_wrong_subject_and_missing_requested_sections(self):
        review = self.backend._review_report_against_request(
            "인공지능 공통기반 2026년 예산 지적사항과 대안 및 향후 계획을 보고서로 작성해줘",
            "# 지역균형발전 보고서\n\n## 현황\n- 지역 사업을 확대함. [1]",
            [{"content": "2026년 인공지능 공통기반 예산 지적사항", "filename": "source.pdf"}],
        )
        self.assertFalse(review["passed"])
        failed = {item["id"] for item in review["checks"] if not item["passed"]}
        self.assertIn("request.subject", failed)
        self.assertIn("request.alternatives", failed)
        self.assertIn("request.future-plan", failed)

    def test_project_markdown_is_versioned_source_of_truth(self):
        first = self.backend.save_project_markdown_document(
            "project-default",
            {"title": "정책 검토", "markdown": "# 정책 검토\n\n- 사업명: 지능형 플랫폼\n- 총사업비: 100백만원\n- 담당부서: 디지털정책과", "actor": "tester"},
        )
        self.assertEqual(first["revision"], 1)
        second = self.backend.save_project_markdown_document(
            "project-default",
            {"document_id": first["id"], "base_revision": 1, "markdown": first["markdown"] + "\n- 향후 계획: 단계적 추진", "actor": "tester"},
        )
        self.assertEqual(second["revision"], 2)
        self.assertEqual([item["revision"] for item in second["versions"]], [2, 1])
        with self.assertRaises(self.backend.ApiError) as stale:
            self.backend.save_project_markdown_document(
                "project-default",
                {"document_id": first["id"], "base_revision": 1, "markdown": "# 충돌본"},
            )
        self.assertEqual(stale.exception.status, 409)
        facts = self.backend.list_project_facts("project-default")
        self.assertTrue(any(item["key"] == "budget.total" for item in facts["candidates"]))
        department = next(item for item in facts["candidates"] if item["label"] == "담당부서")
        decided = self.backend.decide_project_fact_candidate("project-default", department["valueId"], {"decision": "confirmed", "actor": "reviewer"})
        self.assertEqual(decided["decision"], "confirmed")
        self.assertEqual(next(item for item in decided["snapshot"]["facts"].values() if item["label"] == "담당부서")["value"], "디지털정책과")
    def test_duplicate_markdown_archive_restore_and_bulk_fact_decision(self):
        first = self.backend.save_project_markdown_document(
            "project-default", {"markdown": "# 동일 문서\n\n- 검토 내용", "actor": "tester"}
        )
        second = self.backend.save_project_markdown_document(
            "project-default", {"markdown": "# 동일 문서\n\n- 검토 내용", "actor": "tester"}
        )
        listed = self.backend.list_project_markdown_documents("project-default")
        self.assertEqual(listed["duplicateCount"], 1)
        duplicate = next(item for item in listed["items"] if item.get("duplicateOf"))
        canonical_id = duplicate["duplicateOf"]
        archived = self.backend.set_project_markdown_documents_status(
            "project-default", {"action": "archive", "document_ids": [duplicate["id"]], "canonical_document_id": canonical_id, "actor": "tester"}
        )
        self.assertEqual(len(archived["items"]), 1)
        restored = self.backend.set_project_markdown_documents_status(
            "project-default", {"action": "restore", "document_ids": [duplicate["id"]], "actor": "tester"}
        )
        self.assertEqual(restored["duplicateCount"], 1)
        candidate_one = self.backend.save_project_fact(
            "project-default", {"key": "meta.bulk_one", "label": "일괄1", "value": "A", "status": "candidate", "actor": "tester"}
        )
        candidate_two = self.backend.save_project_fact(
            "project-default", {"key": "meta.bulk_two", "label": "일괄2", "value": "B", "status": "candidate", "actor": "tester"}
        )
        decided = self.backend.decide_project_fact_candidates_bulk(
            "project-default", {"value_ids": [candidate_one["valueId"], candidate_two["valueId"]], "decision": "confirmed", "actor": "tester"}
        )
        self.assertEqual(decided["count"], 2)
        self.assertFalse(any(item["valueId"] in {candidate_one["valueId"], candidate_two["valueId"]} for item in self.backend.list_project_facts("project-default")["candidates"]))


    def test_fact_conflict_distinguishes_time_change_from_correction(self):
        self.backend.save_project_fact(
            "project-default", {"key": "budget.total", "label": "총사업비", "value": 100, "effective_date": "2025-01-01", "status": "confirmed", "actor": "tester"}
        )
        changed = self.backend.save_project_fact(
            "project-default", {"key": "budget.total", "label": "총사업비", "value": 120, "effective_date": "2026-01-01", "status": "candidate", "actor": "tester"}
        )
        time_candidate = next(item for item in self.backend.list_project_facts("project-default")["candidates"] if item["valueId"] == changed["valueId"])
        self.assertEqual(time_candidate["conflict"]["type"], "time-change")
        self.backend.decide_project_fact_candidate(
            "project-default", changed["valueId"], {"decision": "confirmed", "resolution": "time-change", "actor": "reviewer"}
        )
        correction = self.backend.save_project_fact(
            "project-default", {"key": "budget.total", "label": "총사업비", "value": 125, "status": "candidate", "actor": "tester"}
        )
        correction_candidate = next(item for item in self.backend.list_project_facts("project-default")["candidates"] if item["valueId"] == correction["valueId"])
        self.assertEqual(correction_candidate["conflict"]["type"], "correction-review")
        decided = self.backend.decide_project_fact_candidate(
            "project-default", correction["valueId"], {"decision": "confirmed", "resolution": "correction", "actor": "reviewer"}
        )
        self.assertEqual(decided["resolution"], "correction")
        self.assertEqual(decided["snapshot"]["facts"]["budget.total"]["value"], 125)
        with self.backend._connect() as db:
            superseded = db.execute("SELECT COUNT(*) FROM project_fact_values v JOIN project_facts f ON f.id=v.fact_id WHERE f.project_id=? AND f.fact_key=? AND v.status='superseded'", ("project-default", "budget.total")).fetchone()[0]
        self.assertEqual(superseded, 2)


    def test_hwpx_upload_creates_markdown_and_edit_updates_revision(self):
        source = sample_hwpx()
        session = self.backend.open_native_document_session(
            {"filename": "uploaded.hwpx", "content_base64": base64.b64encode(source).decode("ascii"), "project_id": "project-default", "actor": "tester"}
        )
        self.assertTrue(session["markdownDocumentId"].startswith("mdoc_"))
        markdown = self.backend.get_project_markdown_document("project-default", session["markdownDocumentId"])
        self.assertIn("사업명", markdown["markdown"])
        paragraph = session["snapshot"]["document"]["paragraphs"][0]
        updated = self.backend.command_native_document_session(
            session["id"],
            {"base_revision": session["revision"], "command": "replace_selection", "arguments": {"target": paragraph["id"], "before": paragraph["text"], "after": "사업명: 갱신된 플랫폼"}, "actor": "tester"},
        )
        pending_markdown = self.backend.get_project_markdown_document("project-default", updated["markdownDocumentId"])
        self.assertEqual(pending_markdown["revision"], 1)
        self.assertEqual(updated["projectSync"]["status"], "diverged")
        promoted = self.backend.promote_project_artifact_to_markdown(
            "project-default", updated["markdownDocumentId"], updated["projectSync"]["artifact"]["id"], {"actor": "tester"}
        )
        revised_markdown = promoted["document"]
        self.assertEqual(revised_markdown["revision"], 2)
        self.assertIn("갱신된 플랫폼", revised_markdown["markdown"])

    def test_hwpx_reverse_conversion_removes_renderer_cover_artifacts(self):
        parsed = {
            "document": {"id": "doc_cover", "name": "cover.hwpx", "format": "hwpx", "sha256": "abc"},
            "paragraphs": [
                {"id": "p1", "text": "정책 검토 보고서"},
                {"id": "p2", "text": "2026. 8. 16."},
                {"id": "p3", "text": "□ 추진방향: 단계적으로 추진함.", "paraPrId": "59"},
                {"id": "p4", "text": "정책 검토 보고서"},
            ],
            "layout": {"sections": [{"blocks": [
                {"type": "table", "rows": [{"cells": [{"paragraphIds": ["p1"]}, {"paragraphIds": []}]}]},
                {"type": "paragraph", "paragraphId": "p2"},
                {"type": "paragraph", "paragraphId": "p3"},
                {"type": "paragraph", "paragraphId": "p4"},
            ]}]},
        }
        converted = self.backend.hwpx_to_markdown(parsed, "cover.hwpx")
        self.assertEqual(converted["markdown"], "# 정책 검토 보고서\n\n- 추진방향: 단계적으로 추진함.")
        self.assertEqual(converted["conversion"]["layoutArtifactsRemoved"], 1)

    def test_project_markdown_renders_hwpx_and_declares_third_party_adapter_boundary(self):
        document = self.backend.save_project_markdown_document("project-default", {"markdown": "# 보고서\n\n## 현황\n- 100입니다.", "actor": "tester"})
        rendered = self.backend.render_project_markdown_document(
            "project-default", document["id"], {"format": "hwpx", "instruction": "행안부 보고서 양식으로 바꿔줘", "actor": "tester"}
        )
        self.assertEqual(rendered["artifact"]["template"]["id"], "central-government-outline.v2")
        self.assertEqual(rendered["sourceDocument"]["versionId"], document["versionId"])
        self.assertEqual(rendered["artifact"]["sourceOfTruth"]["status"], "persisted")
        self.assertEqual(rendered["artifact"]["content"].count("# 보고서"), 1)
        self.assertTrue(base64.b64decode(rendered["artifact"]["contentBase64"]).startswith(b"PK"))
        adapters = self.backend.project_document_format_adapters()
        self.assertEqual(adapters["sourceFormat"], "md")
        with self.assertRaises(self.backend.ApiError) as missing:
            self.backend.render_project_markdown_document("project-default", document["id"], {"format": "pdf"})
        self.assertEqual(missing.exception.status, 409)

    def test_markdown_refresh_preserves_existing_hwpx_layout_resources(self):
        document = self.backend.save_project_markdown_document(
            "project-default", {"markdown": "# 양식 보존 보고서\n\n## 현황\n- 기존 내용임.", "actor": "tester"}
        )
        first = self.backend.render_project_markdown_document(
            "project-default", document["id"], {"format": "hwpx", "instruction": "중앙부처 개조식 보고서", "actor": "tester"}
        )
        first_detail = self.backend.get_project_document_artifact(
            "project-default", document["id"], first["projectArtifact"]["id"]
        )
        original = base64.b64decode(first_detail["contentBase64"])
        source = zipfile.ZipFile(io.BytesIO(original))
        customized_buffer = io.BytesIO()
        with source, zipfile.ZipFile(customized_buffer, "w") as customized:
            for info in source.infolist():
                customized.writestr(info, source.read(info.filename))
            customized.writestr("AIWorks/layout-preservation.marker", b"keep-existing-layout")
        customized_bytes = customized_buffer.getvalue()
        with self.backend._connect() as db:
            db.execute(
                "UPDATE project_document_artifacts SET content_blob=?,artifact_sha256=? WHERE id=?",
                (customized_bytes, hashlib.sha256(customized_bytes).hexdigest(), first["projectArtifact"]["id"]),
            )

        revised = self.backend.save_project_markdown_document(
            "project-default",
            {
                "document_id": document["id"],
                "base_revision": document["revision"],
                "markdown": "# 양식 보존 보고서\n\n## 현황\n- 변경된 내용임.\n- 새로 추가한 문단임.",
                "actor": "tester",
            },
        )
        refreshed = self.backend.render_project_markdown_document(
            "project-default", document["id"], {"format": "hwpx", "actor": "tester"}
        )
        refreshed_bytes = base64.b64decode(refreshed["artifact"]["contentBase64"])
        with zipfile.ZipFile(io.BytesIO(refreshed_bytes)) as archive:
            self.assertEqual(archive.read("AIWorks/layout-preservation.marker"), b"keep-existing-layout")
        refreshed_text = "\n".join(
            item["text"] for item in self.backend.parse_hwpx(refreshed_bytes, refreshed["artifact"]["filename"])["paragraphs"]
        )
        self.assertIn("변경된 내용임.", refreshed_text)
        self.assertIn("새로 추가한 문단임.", refreshed_text)
        self.assertNotIn("기존 내용임.", refreshed_text)
        self.assertEqual(refreshed["sourceDocument"]["revision"], revised["revision"])
        self.assertTrue(refreshed["artifact"]["layoutPreserved"])
        self.assertTrue(refreshed["artifact"]["derivedOutput"]["layoutPreserved"])
        self.assertEqual(refreshed["projectArtifact"]["instruction"], "중앙부처 개조식 보고서")
        self.assertEqual(refreshed["artifact"]["layoutRefreshMode"], "mapped-text-refresh")
        self.assertEqual(refreshed["projectArtifact"]["renderMap"]["renderMode"], "layout-preserving-structure-refresh")

        self.backend.save_project_markdown_document(
            "project-default",
            {
                "document_id": document["id"],
                "base_revision": revised["revision"],
                "markdown": "# 양식 보존 보고서\n\n## 현황\n- 최종 내용임.",
                "actor": "tester",
            },
        )
        reduced = self.backend.render_project_markdown_document(
            "project-default", document["id"], {"format": "hwpx", "actor": "tester"}
        )
        reduced_bytes = base64.b64decode(reduced["artifact"]["contentBase64"])
        with zipfile.ZipFile(io.BytesIO(reduced_bytes)) as archive:
            self.assertEqual(archive.read("AIWorks/layout-preservation.marker"), b"keep-existing-layout")
        reduced_text = "\n".join(
            item["text"] for item in self.backend.parse_hwpx(reduced_bytes, reduced["artifact"]["filename"])["paragraphs"]
        )
        self.assertIn("최종 내용임.", reduced_text)
        self.assertNotIn("새로 추가한 문단임.", reduced_text)
        self.assertEqual(reduced["projectArtifact"]["renderMap"]["renderMode"], "layout-preserving-structure-refresh")

    def test_whole_hwpx_save_promotes_changed_text_to_markdown(self):
        document = self.backend.save_project_markdown_document(
            "project-default", {"markdown": "# 전체 저장 보고서\n\n## 현황\n- 저장 전 내용임.", "actor": "tester"}
        )
        rendered = self.backend.render_project_markdown_document(
            "project-default", document["id"], {"format": "hwpx", "instruction": "중앙부처 개조식 보고서", "actor": "tester"}
        )
        detail = self.backend.get_project_document_artifact(
            "project-default", document["id"], rendered["projectArtifact"]["id"]
        )
        session = self.backend.open_native_document_session({
            "filename": detail["filename"],
            "content_base64": detail["contentBase64"],
            "project_id": "project-default",
            "markdown_document_id": document["id"],
            "project_artifact_id": rendered["projectArtifact"]["id"],
            "markdown_base_revision": document["revision"],
            "canonical_markdown": document["markdown"],
            "actor": "tester",
        })
        mapping = next(item for item in rendered["projectArtifact"]["renderMap"]["entries"] if item["blockType"] == "list_item")
        parsed = self.backend.parse_hwpx(base64.b64decode(detail["contentBase64"]), detail["filename"])
        paragraph = next(item for item in parsed["paragraphs"] if item["id"] == mapping["paragraphId"])
        changed_bytes, _metadata = self.backend.apply_hwpx_patch(
            base64.b64decode(detail["contentBase64"]),
            {
                "op": "replace",
                "target": paragraph["id"],
                "expectedBefore": paragraph["text"],
                "after": "□ HWPX에서 변경한 내용임.",
                "sourceSha256": parsed["document"]["sha256"],
            },
            detail["filename"],
        )
        saved = self.backend.command_native_document_session(session["id"], {
            "base_revision": session["revision"],
            "command": "replace_artifact",
            "arguments": {"contentBase64": base64.b64encode(changed_bytes).decode("ascii"), "format": "hwpx"},
            "actor": "tester",
        })
        pending = self.backend.get_project_markdown_document("project-default", document["id"])
        self.assertEqual(pending["revision"], 1)
        self.assertEqual(saved["projectSync"]["status"], "diverged")
        promoted = self.backend.promote_project_artifact_to_markdown(
            "project-default", document["id"], saved["projectSync"]["artifact"]["id"], {"actor": "tester"}
        )
        revised = promoted["document"]
        self.assertEqual(revised["revision"], 2)
        self.assertIn("- HWPX에서 변경한 내용임.", revised["markdown"])
        self.assertEqual(saved["projectSync"]["origin"], "hwpx")
        self.assertEqual(promoted["artifact"]["status"], "synced")

    def test_project_workbench_promotes_hwpx_semantic_edit_to_markdown_and_blocks_stale_session(self):
        document = self.backend.save_project_markdown_document(
            "project-default", {"markdown": "# 동기화 보고서\n\n## 현황\n- 100입니다.", "actor": "tester"}
        )
        rendered = self.backend.render_project_markdown_document(
            "project-default", document["id"], {"format": "hwpx", "instruction": "중앙부처 개조식 보고서", "actor": "tester"}
        )
        project_artifact = rendered["projectArtifact"]
        self.assertEqual(project_artifact["status"], "synced")
        self.assertGreater(project_artifact["renderMap"]["mapped"], 0)
        workbench = self.backend.get_project_document_workbench("project-default", document["id"])
        self.assertEqual(workbench["project"]["id"], "project-default")
        relations = workbench["relationGraph"]
        self.assertTrue(any(item["type"] == "markdown-version" for item in relations["nodes"]))
        self.assertTrue(any(item["type"] == "artifact" for item in relations["nodes"]))
        self.assertTrue(any(item["relation"] == "derived_from" and item["source"] == project_artifact["id"] for item in relations["edges"]))

        self.assertIn("metadata", workbench["tabs"])
        self.assertEqual(next(item for item in workbench["artifacts"] if item["format"] == "hwpx")["sourceRevision"], 1)

        artifact_detail = self.backend.get_project_document_artifact("project-default", document["id"], project_artifact["id"])
        session = self.backend.open_native_document_session({
            "filename": artifact_detail["filename"], "content_base64": artifact_detail["contentBase64"],
            "project_id": "project-default", "markdown_document_id": document["id"], "markdown_base_revision": 1,
            "project_artifact_id": project_artifact["id"], "canonical_markdown": document["markdown"], "actor": "tester",
        })
        mapping = next(item for item in project_artifact["renderMap"]["entries"] if item["blockType"] == "list_item")
        paragraph = next(item for item in session["snapshot"]["document"]["paragraphs"] if item["id"] == mapping["paragraphId"])
        updated = self.backend.command_native_document_session(session["id"], {
            "base_revision": session["revision"], "command": "replace_selection",
            "arguments": {"target": paragraph["id"], "before": paragraph["text"], "after": "□ 200으로 조정함."}, "actor": "tester",
        })
        pending = self.backend.get_project_markdown_document("project-default", document["id"])
        self.assertEqual(pending["revision"], 1)
        self.assertEqual(updated["projectSync"]["status"], "diverged")
        promoted = self.backend.promote_project_artifact_to_markdown(
            "project-default", document["id"], updated["projectSync"]["artifact"]["id"], {"actor": "tester"}
        )
        revised = promoted["document"]
        self.assertEqual(revised["revision"], 2)
        self.assertIn("- 200으로 조정함.", revised["markdown"])
        self.assertEqual(promoted["artifact"]["status"], "synced")
        self.assertEqual(self.backend.get_native_document_session(session["id"])["markdownBaseRevision"], 2)

        stale_session = self.backend.open_native_document_session({
            "filename": artifact_detail["filename"], "content_base64": artifact_detail["contentBase64"],
            "project_id": "project-default", "markdown_document_id": document["id"],
            "project_artifact_id": project_artifact["id"], "canonical_markdown": revised["markdown"], "actor": "tester",
        })
        self.backend.save_project_markdown_document("project-default", {"document_id": document["id"], "base_revision": 2, "markdown": revised["markdown"] + "\n- 추가 검토함.", "actor": "other-tab"})
        with self.assertRaises(self.backend.ApiError) as conflict:
            self.backend.command_native_document_session(stale_session["id"], {
                "base_revision": stale_session["revision"], "command": "replace_selection",
                "arguments": {"target": paragraph["id"], "before": "□ 200으로 조정함.", "after": "□ 300으로 조정함."}, "actor": "tester",
            })
        self.assertEqual(conflict.exception.status, 409)

    def test_concurrent_markdown_and_hwpx_edits_create_resolvable_conflict(self):
        document = self.backend.save_project_markdown_document(
            "project-default", {"markdown": "# 충돌 보고서\n\n## 현황\n- 100입니다.", "actor": "tester"}
        )
        rendered = self.backend.render_project_markdown_document(
            "project-default", document["id"], {"format": "hwpx", "instruction": "중앙부처 개조식 보고서", "actor": "tester"}
        )
        artifact = rendered["projectArtifact"]
        detail = self.backend.get_project_document_artifact("project-default", document["id"], artifact["id"])
        session = self.backend.open_native_document_session({
            "filename": detail["filename"], "content_base64": detail["contentBase64"], "project_id": "project-default",
            "markdown_document_id": document["id"], "markdown_base_revision": 1, "project_artifact_id": artifact["id"],
            "canonical_markdown": document["markdown"], "actor": "tester",
        })
        mapping = next(item for item in artifact["renderMap"]["entries"] if item["blockType"] == "list_item")
        paragraph = next(item for item in session["snapshot"]["document"]["paragraphs"] if item["id"] == mapping["paragraphId"])
        saved_hwpx = self.backend.command_native_document_session(session["id"], {
            "base_revision": session["revision"], "command": "replace_selection",
            "arguments": {"target": paragraph["id"], "before": paragraph["text"], "after": "□ HWPX에서 120으로 변경함."}, "actor": "tester",
        })
        current_md = self.backend.save_project_markdown_document(
            "project-default", {"document_id": document["id"], "base_revision": 1, "markdown": document["markdown"] + "\n- MD에서 별도 검토함.", "actor": "md-editor"}
        )
        with self.assertRaises(self.backend.ApiError) as raised:
            self.backend.promote_project_artifact_to_markdown(
                "project-default", document["id"], saved_hwpx["projectSync"]["artifact"]["id"], {"actor": "tester"}
            )
        self.assertEqual(raised.exception.status, 409)
        workbench = self.backend.get_project_document_workbench("project-default", document["id"])
        conflict = next(item for item in workbench["conflicts"] if item["status"] == "open")
        self.assertEqual(conflict["conflictType"], "concurrent-md-hwpx-edit")
        resolved = self.backend.resolve_project_document_conflict(
            "project-default", document["id"], conflict["id"], {"resolution": "keep-markdown", "actor": "reviewer"}
        )
        self.assertEqual(resolved["conflict"]["status"], "resolved")
        self.assertEqual(resolved["document"]["versionId"], current_md["versionId"])
        self.assertEqual(resolved["artifact"]["status"], "stale")


    def test_project_governance_policy_grant_archive_and_restore(self):
        project = self.backend.create_project({"name": "거버넌스 검증", "actor": "owner-a"})
        governed = self.backend.save_project_member(project["id"], {
            "actor": "owner-a", "member_actor": "editor-a", "role": "editor",
        })
        self.assertEqual(governed["currentRole"], "owner")
        self.assertEqual(self.backend.get_project_governance(project["id"], {"actor": "editor-a"})["currentRole"], "editor")
        with self.assertRaises(self.backend.ApiError) as denied:
            self.backend.save_project_policy(project["id"], {
                "actor": "editor-a", "policy": governed["policy"]["policy"],
            })
        self.assertEqual(denied.exception.status, 403)
        policy = governed["policy"]["policy"]
        policy["resolver"]["preferredPackages"] = ["document.report@1.0.0"]
        saved = self.backend.save_project_policy(project["id"], {
            "actor": "owner-a", "expected_revision": 0, "policy": policy,
        })
        self.assertEqual(saved["policy"]["revision"], 1)
        granted = self.backend.save_permission_grant(project["id"], {
            "actor": "owner-a", "member_actor": "editor-a",
            "package_id": "document.report", "scopes": ["document.read", "document.write"],
        })
        self.assertEqual(granted["grants"][0]["actor"], "editor-a")
        self.backend.change_project_status(project["id"], {"actor": "owner-a", "action": "archive"})
        self.assertIn(project["id"], [item["id"] for item in self.backend.list_archived_projects({"actor": "owner-a"})["items"]])
        restored = self.backend.change_project_status(project["id"], {"actor": "owner-a", "action": "restore"})
        self.assertEqual(restored["status"], "active")

    def test_generic_artifact_versions_lineage_and_cycle_guard(self):
        first = self.backend.create_project_artifact("project-default", {
            "actor": "tester", "artifact_type": "analysis", "title": "분석",
            "source_id": "analysis:test", "content": {"text": "초안"},
        })
        second = self.backend.create_project_artifact("project-default", {
            "actor": "tester", "artifact_type": "report", "title": "보고서",
            "source_id": "report:test", "content": {"text": "보고서"},
        })
        revised = self.backend.append_project_artifact_version(
            "project-default", first["artifact"]["id"],
            {"actor": "tester", "expected_version": 1, "content": {"text": "수정본"}},
        )
        self.assertEqual(revised["version"]["version"], 2)
        relation = self.backend.create_project_artifact_relation("project-default", {
            "actor": "tester", "source_version_id": first["version"]["id"],
            "target_version_id": second["version"]["id"], "relation": "derived_from",
        })
        self.assertEqual(relation["relation"], "derived_from")
        with self.assertRaises(self.backend.ApiError) as cycle:
            self.backend.create_project_artifact_relation("project-default", {
                "actor": "tester", "source_version_id": second["version"]["id"],
                "target_version_id": first["version"]["id"], "relation": "transforms",
            })
        self.assertEqual(cycle.exception.status, 409)
        self.assertEqual(self.backend.list_project_artifacts("project-default")["count"], 2)

    def test_markdown_versions_are_registered_in_generic_artifact_store(self):
        document = self.backend.save_project_markdown_document(
            "project-default", {"actor": "tester", "title": "기준 MD", "markdown": "# 기준 MD\n\n- 내용"}
        )
        revised = self.backend.save_project_markdown_document(
            "project-default", {
                "actor": "tester", "document_id": document["id"], "base_revision": 1,
                "title": "기준 MD", "markdown": "# 기준 MD\n\n- 변경 내용",
            },
        )
        artifacts = self.backend.list_project_artifacts("project-default")
        markdown_artifact = next(item for item in artifacts["items"] if item["source"]["id"] == document["id"])
        self.assertEqual(markdown_artifact["currentVersionId"], markdown_artifact["versions"][0]["id"])
        self.assertEqual(revised["revision"], 2)
        self.assertEqual(len(markdown_artifact["versions"]), 2)
        self.assertTrue(any(item["relation"] == "supersedes" for item in artifacts["relations"]))

    def test_docx_and_xlsx_are_extracted_and_docx_opens_as_project_markdown(self):
        docx = sample_docx()
        xlsx = sample_xlsx()
        inspected_docx = self.backend.inspect_asset({
            "filename": "예산분석.docx", "content_base64": base64.b64encode(docx).decode("ascii"),
        })
        inspected_xlsx = self.backend.inspect_asset({
            "filename": "예산현황.xlsx", "content_base64": base64.b64encode(xlsx).decode("ascii"),
        })
        self.assertTrue(inspected_docx["ragReady"])
        self.assertIn("인공지능 공통기반", inspected_docx["textExcerpt"])
        self.assertTrue(inspected_xlsx["ragReady"])
        self.assertIn("1200", inspected_xlsx["textExcerpt"])
        session = self.backend.open_native_document_session({
            "filename": "예산분석.docx", "content_base64": base64.b64encode(docx).decode("ascii"),
            "project_id": "project-default", "actor": "tester",
        })
        self.assertEqual(session["format"], "md")
        self.assertEqual(session["snapshot"]["markdownSource"]["conversion"]["sourceFormat"], "docx")
        self.assertIn("인공지능 공통기반", session["snapshot"]["content"])
        formats = {item["format"]: item for item in self.backend.project_document_format_adapters()["adapters"]}
        self.assertEqual(formats["docx"]["direction"], "input")
        self.assertEqual(formats["xlsx"]["direction"], "input")

    def test_template_schema_detects_merged_approval_table_and_mapping_metadata(self):
        data = sample_form_template_hwpx()
        source_archive = zipfile.ZipFile(io.BytesIO(data))
        buffer = io.BytesIO()
        with source_archive, zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
            for info in source_archive.infolist():
                payload = source_archive.read(info.filename)
                if info.filename == "Contents/section0.xml":
                    text = payload.decode("utf-8")
                    text = text.replace("항목1", "담당 결재", 1)
                    text = text.replace('colSpan="1" rowSpan="1"', 'colSpan="2" rowSpan="1"', 1)
                    payload = text.encode("utf-8")
                target.writestr(info, payload)
        source = buffer.getvalue()
        schema = self.backend._hwpx_template_schema(source)
        mapping = self.backend._template_mapping_candidates(source)
        self.assertEqual(schema["contractVersion"], "1.1")
        self.assertTrue(schema["mergedTables"])
        self.assertTrue(schema["approvalBlocks"])
        table_items = [item for item in mapping["candidates"] if item["insideTable"]]
        self.assertTrue(any(item["tableMerged"] for item in table_items))
        self.assertTrue(any(item["approvalLike"] for item in table_items))

    def test_workflow_recipe_version_share_fork_install_and_deprecate(self):
        definition = {
            "description": "근거를 조회하고 보고서를 생성합니다.",
            "inputArtifactTypes": ["document.markdown"],
            "outputArtifactTypes": ["document.hwpx"],
            "steps": [
                {"id": "query", "capability": "data.query", "permissions": ["data.read"]},
                {"id": "report", "capability": "document.generate", "permissions": ["document.write"], "outputArtifactType": "document.markdown"},
                {"id": "format", "capability": "document.hwpx.render", "permissions": ["document.read", "document.write"], "outputArtifactType": "document.hwpx"},
            ],
        }
        recipe = self.backend.save_workflow_recipe({
            "id": "org.report-flow", "name": "근거 보고서 흐름",
            "description": "데이터 조회부터 HWPX까지", "version": "1.0.0",
            "visibility": "organization", "definition": definition, "actor": "workspace-user",
        })
        self.assertEqual(recipe["versions"][0]["definition"]["steps"][1]["capability"], "document.generate")
        updated = self.backend.save_workflow_recipe({
            "id": recipe["id"], "name": recipe["name"], "description": recipe["description"],
            "version": "1.1.0", "visibility": "organization", "definition": definition,
            "changelog": "양식 단계 안정화", "actor": "workspace-user",
        })
        self.assertEqual(len(updated["versions"]), 2)
        installed = self.backend.install_workflow_recipe(
            "project-default", recipe["id"], {"version": "1.1.0", "actor": "workspace-user"}
        )
        self.assertEqual(installed["installed"]["status"], "active")
        forked = self.backend.fork_workflow_recipe(recipe["id"], {
            "id": "personal.report-flow", "name": "개인 보고서 흐름",
            "visibility": "private", "actor": "reviewer",
        })
        self.assertEqual(forked["owner"], "reviewer")
        self.assertEqual([item["capability"] for item in forked["versions"][0]["definition"]["steps"]], [item["capability"] for item in definition["steps"]])
        visible = self.backend.list_workflow_recipes({"actor": "reviewer", "project_id": "project-default"})
        self.assertIn(forked["id"], [item["id"] for item in visible["items"]])
        deprecated = self.backend.deprecate_workflow_recipe(recipe["id"], {"actor": "workspace-user"})
        self.assertEqual(deprecated["status"], "deprecated")
        self.assertEqual(deprecated["installed"]["status"] if deprecated["installed"] else None, None)

    def test_artifact_evidence_tracks_source_excerpt_and_hash(self):
        project = self.backend.create_project({"name": "근거 계보 검증", "actor": "evidence-tester"})
        source = self.backend.create_project_artifact(project["id"], {"artifact_type": "data.pdf", "title": "예산 원문", "content": {"page": 12}, "actor": "evidence-tester"})
        report = self.backend.create_project_artifact(project["id"], {"artifact_type": "document.markdown", "title": "분석 보고서", "content": {"markdown": "# 분석"}, "actor": "evidence-tester"})
        evidence = self.backend.create_project_artifact_evidence(project["id"], {
            "artifact_id": report["artifact"]["id"], "artifact_version_id": report["version"]["id"],
            "source_artifact_id": source["artifact"]["id"], "source_version_id": source["version"]["id"],
            "locator": "p.12 표 3", "excerpt": "인공지능 공통기반 예산 집행 지연", "confidence": 0.93, "actor": "evidence-tester",
        })
        self.assertEqual(evidence["excerptSha256"], hashlib.sha256(evidence["excerpt"].encode()).hexdigest())
        listed = self.backend.list_project_artifacts(project["id"])
        self.assertEqual(listed["evidence"][0]["sourceVersionId"], source["version"]["id"])
        self.assertEqual(self.backend.list_project_artifact_evidence(project["id"], {"artifact_id": report["artifact"]["id"], "actor": "evidence-tester"})["count"], 1)

    def test_project_backup_round_trip_preserves_md_fact_hwpx_and_evidence(self):
        project = self.backend.create_project({"name": "백업 원본", "classification": "internal", "actor": "backup-tester"})
        document = self.backend.save_project_markdown_document(project["id"], {"title": "예산 보고", "markdown": "# 예산 보고\n\n- 집행 지연 개선이 필요함.", "actor": "backup-tester"})
        self.backend.save_project_fact(project["id"], {"key": "budget.year", "label": "예산연도", "value": 2026, "status": "confirmed", "actor": "backup-tester"})
        self.backend.render_project_markdown_document(project["id"], document["id"], {"format": "hwpx", "actor": "backup-tester"})
        artifacts = self.backend.list_project_artifacts(project["id"])
        target = next(item for item in artifacts["items"] if item["currentVersionId"])
        self.backend.create_project_artifact_evidence(project["id"], {"artifact_id": target["id"], "locator": "MD #1", "excerpt": "집행 지연 개선", "actor": "backup-tester"})
        backup = self.backend.export_project_backup(project["id"], {"actor": "backup-tester"})
        self.assertEqual(backup["format"], "aiworks-project-backup")
        restored = self.backend.import_project_backup({"bundle": backup, "name": "백업 복원본", "actor": "backup-tester"})
        self.assertNotEqual(restored["project"]["id"], project["id"])
        workspace = self.backend.get_project_workspace(restored["project"]["id"])
        self.assertEqual(workspace["summary"]["documentCount"], 1)
        self.assertEqual(workspace["summary"]["factCount"], 1)
        restored_document = workspace["documents"][0]
        restored_detail = self.backend.get_project_markdown_document(restored["project"]["id"], restored_document["id"])
        self.assertIn("집행 지연 개선", restored_detail["markdown"])
        restored_artifacts = self.backend.list_project_artifacts(restored["project"]["id"])
        self.assertTrue(restored_artifacts["evidence"])
        self.assertTrue(any(version.get("contentBase64") is None for item in restored_artifacts["items"] for version in item["versions"]))
        workbench = self.backend.get_project_document_workbench(restored["project"]["id"], restored_document["id"])
        self.assertTrue(any(item["format"] == "hwpx" for item in workbench["artifacts"]))

    def test_recipe_search_preview_and_security_block(self):
        definition = {
            "tags": ["budget", "report"], "estimatedCost": 0.2, "estimatedLatencyMs": 1500,
            "license": "Apache-2.0", "provenance": "https://example.invalid/recipe",
            "steps": [{"id": "draft", "capability": "document.generate", "permissions": ["document.write"]}],
        }
        recipe = self.backend.save_workflow_recipe({"id": "org.budget-preview", "name": "예산 보고서", "description": "예산 분석", "version": "1.0.0", "visibility": "organization", "definition": definition, "actor": "workspace-user"})
        self.assertEqual(recipe["preview"]["permissions"], ["document.write"])
        searched = self.backend.list_workflow_recipes({"q": "budget", "tags": ["report"], "max_cost": 0.3, "actor": "workspace-user"})
        self.assertIn(recipe["id"], [item["id"] for item in searched["items"]])
        blocked_definition = dict(definition)
        blocked_definition["security"] = {"status": "vulnerable", "blocked": True, "advisories": ["CVE-TEST"]}
        blocked = self.backend.save_workflow_recipe({"id": "org.blocked-recipe", "name": "차단 Recipe", "description": "취약 버전", "version": "1.0.0", "visibility": "organization", "definition": blocked_definition, "actor": "workspace-user"})
        self.assertIn("security-blocked", blocked["preview"]["riskFlags"])
        with self.assertRaises(self.backend.ApiError) as error:
            self.backend.install_workflow_recipe("project-default", blocked["id"], {"actor": "workspace-user", "acknowledge_risks": True})
        self.assertEqual(error.exception.status, 409)

    def test_semantic_patch_updates_gfm_table_cell_without_rewriting_table(self):
        markdown = "# 표 보고서\n\n| 연도 | 예산 |\n| --- | ---: |\n| 2026 | 100 |"
        updated = self.backend._semantic_patch_markdown(markdown, {"blockType": "table", "cellRow": 1, "cellColumn": 1, "canonicalText": "100"}, "100", "120")
        self.assertIn("| 2026 | 120 |", updated)
        self.assertIn("| --- | ---: |", updated)


if __name__ == "__main__":
    unittest.main()
