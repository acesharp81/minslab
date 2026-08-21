import base64
import tempfile
import unittest
from pathlib import Path

from test_backend import load_backend


class AIWorksWorkspaceFlowTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.backend = load_backend(Path(self.tempdir.name) / "aiworks.sqlite3")

    def tearDown(self):
        self.tempdir.cleanup()

    def execute(self, intent, context, key):
        plan = self.backend.create_plan(
            {"intent": intent, "actor": "flow-tester", "document_context": context}
        )
        approval = self.backend.approve_plan(
            {
                "plan_id": plan["id"],
                "actor": "flow-tester",
                "permissions": plan["requiredPermissions"],
            }
        )
        execution = self.backend.execute_plan(
            {
                "approval_token": approval["approvalToken"],
                "idempotency_key": key,
                "input": context,
            },
            force_local=True,
        )
        return plan, execution

    def test_no_file_budget_answer_then_derived_report(self):
        plan, execution = self.execute(
            "우리부 예산 현황을 확인하고 싶어",
            {"classification": "internal", "has_attachment": False},
            "flow-budget-answer",
        )
        self.assertEqual(plan["workflow"]["responseType"], "text-answer")
        self.assertIn("data.budget@0.1.0", plan["workflow"]["loadedMcps"])
        self.assertIn("output.text@1.0.0", plan["workflow"]["loadedMcps"])
        self.assertIn("1,284백만원", execution["result"]["answer"])

        report_plan, report_execution = self.execute(
            "분석 내용에 시사점을 추가해서 보고서로 작성해줘",
            {
                "classification": "internal",
                "previous_answer": execution["result"]["answer"],
            },
            "flow-derived-report",
        )
        self.assertEqual(report_plan["workflow"]["responseType"], "report-artifact")
        self.assertIn("document.report@1.0.0", report_plan["workflow"]["loadedMcps"])
        artifact = report_execution["result"]["artifact"]
        self.assertEqual(artifact["format"], "hwpx")
        self.assertEqual(artifact["editorMcp"], "document.rhwp@1.0.0")
        self.assertTrue(artifact["filename"].endswith(".hwpx"))
        self.assertIn("document.report-hwpx@0.1.0", report_plan["workflow"]["loadedMcps"])
        self.assertIn("document.rhwp@1.0.0", report_plan["workflow"]["loadedMcps"])
        parsed = self.backend.parse_hwpx(base64.b64decode(artifact["contentBase64"]), artifact["filename"])
        self.assertIn("분석 및 시사점 보고서", [item["text"] for item in parsed["paragraphs"]])
        self.assertIn("## 4. 정책적 시사점", report_execution["result"]["artifact"]["content"])

    def test_previous_answer_creates_new_mois_outline_report_without_current_rhwp(self):
        previous = (
            "## 요청 및 검토 범위\n인공지능 공통기반 관련 예산 결산 지적사항\n\n"
            "- 2025년 예산현액 53억 9,200만원을 전액 집행하였으나 NIA 실집행률은 92.3%이고 4억 1,600만원이 이월됨. [1]\n"
            "- 정보화전략계획 수립 전에 예산이 편성되어 수시배정 후 사업이 지연되고 2026년 3월 말 구축이 완료됨. [2]\n"
            "- 성과지표가 사업 목적과 직접 연결되는지 점검할 필요가 있음. [3]"
        )
        intent = "이 내용을 바탕으로 지적사항별 대안을 포함하여 행안부 양식으로 개조식으로 보고서를 작성해줘"
        plan, execution = self.execute(
            intent,
            {
                "classification": "internal",
                "document_id": "workspace-document",
                "filename": "새 프로젝트",
                "document_excerpt": "아직 생성된 산출물이 없습니다.",
                "previous_answer": previous,
            },
            "flow-previous-answer-mois-report",
        )
        self.assertEqual(plan["workflow"]["responseType"], "report-artifact")
        self.assertEqual(plan["workflow"]["contextPriority"], "previous-answer")
        self.assertTrue(plan["workflow"]["signals"]["previousAnswerPrimary"])
        self.assertIn("template.mois-report@0.1.0", plan["workflow"]["loadedMcps"])
        self.assertNotIn("read-current-document", [step["id"] for step in plan["steps"]])
        self.assertEqual(plan["workflow"]["markdownContext"], [])
        self.assertNotIn("project.name", plan["workflow"]["factSnapshot"]["facts"])

        result = execution["result"]
        artifact = result["artifact"]
        self.assertEqual(result["responseType"], "report-artifact")
        self.assertEqual(artifact["template"]["id"], "mois.internal-report.v1")
        self.assertEqual(artifact["templateApplication"]["mode"], "new-report")
        self.assertTrue(artifact["filename"].endswith("_행안부보고.hwpx"))
        self.assertIn("## IV. 지적사항별 개선대안 및 향후계획", artifact["content"])
        self.assertIn("개선대안", artifact["content"])
        self.assertIn("향후계획", artifact["content"])
        self.assertNotIn("지능형 민원", artifact["content"])
        self.assertTrue((artifact.get("markdownDocument") or {}).get("id", "").startswith("mdoc_"))
        parsed = self.backend.parse_hwpx(base64.b64decode(artifact["contentBase64"]), artifact["filename"])
        texts = [item["text"] for item in parsed["paragraphs"]]
        self.assertIn("행정안전부 업무보고 | 내부검토", texts)
        self.assertTrue(any("실집행률은 92.3%" in item for item in texts))

    def test_followup_edit_wording_creates_rhwp_artifact(self):
        for index, intent in enumerate((
            "이를 바탕으로 문서를 편집하자",
            "위 내용을 수정할 수 있도록 준비해줘",
            "이 답변을 편집 가능한 문서로 만들어줘",
        )):
            with self.subTest(intent=intent):
                plan, execution = self.execute(
                    intent,
                    {
                        "classification": "internal",
                        "previous_answer": "업무 현황과 주요 시사점 요약",
                    },
                    f"flow-editable-followup-{index}",
                )
                self.assertEqual(plan["workflow"]["responseType"], "report-artifact")
                self.assertTrue(plan["workflow"]["signals"]["editableDocument"])
                self.assertIn("document.report-hwpx@0.1.0", plan["workflow"]["loadedMcps"])
                self.assertIn("document.rhwp@1.0.0", plan["workflow"]["loadedMcps"])
                artifact = execution["result"]["artifact"]
                self.assertEqual(artifact["format"], "hwpx")
                self.assertEqual(artifact["editorMcp"], "document.rhwp@1.0.0")
                self.assertTrue(artifact["contentBase64"])

    def test_mois_template_mcp_reformats_current_hwpx_revision_locally(self):
        source = self.backend.REPORT_HWPX_MCP.build(
            "예산 현황 분석 및 검토보고",
            "# 예산 현황 분석 및 검토보고\n\n## 1. 보고 목적\n현재 예산 현황을 검토합니다.\n\n## 2. 주요 현황\n총사업비 1,284백만원",
        )
        session = self.backend.open_native_document_session(
            {
                "filename": "예산_검토보고.hwpx",
                "content_base64": base64.b64encode(source).decode("ascii"),
                "intent": "보고서를 RHWP에서 열기",
                "confirmed": True,
                "actor": "flow-tester",
            }
        )
        context = {
            "classification": "internal",
            "has_attachment": True,
            "document_id": session["id"],
            "filename": session["filename"],
            "document_excerpt": "예산 현황 분석 및 검토보고",
        }
        plan, execution = self.execute(
            "행안부 보고서 양식으로 바꿔줘",
            context,
            "flow-mois-template",
        )
        self.assertEqual(plan["workflow"]["responseType"], "template-transform")
        self.assertFalse(plan["dataPolicy"]["externalTransfer"])
        self.assertNotIn("model.invoke", plan["requiredPermissions"])
        self.assertNotIn("network.send", plan["requiredPermissions"])
        self.assertIn("template.mois-report@0.1.0", plan["workflow"]["loadedMcps"])

        result = execution["result"]
        artifact = result["artifact"]
        self.assertEqual(result["model"]["mode"], "local-template")
        self.assertEqual(artifact["template"]["id"], "mois.internal-report.v1")
        self.assertEqual(artifact["applyMode"], "replace-current-session")
        self.assertTrue(artifact["filename"].endswith("_행안부보고.hwpx"))
        parsed = self.backend.parse_hwpx(
            base64.b64decode(artifact["contentBase64"]),
            artifact["filename"],
        )
        formatted_text = [item["text"] for item in parsed["paragraphs"]]
        self.assertIn("행정안전부 업무보고 | 내부검토", formatted_text)
        self.assertIn("예산 현황 분석 및 검토보고", formatted_text)
        self.assertIn("○ 총사업비 1,284백만원", formatted_text)

        updated = self.backend.command_native_document_session(
            session["id"],
            {
                "base_revision": 1,
                "command": "replace_artifact",
                "arguments": {
                    "contentBase64": artifact["contentBase64"],
                    "filename": artifact["filename"],
                },
                "confirmed": True,
                "actor": "flow-tester",
            },
        )
        self.assertEqual(updated["id"], session["id"])
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(updated["filename"], artifact["filename"])

    def test_full_report_outline_request_replaces_current_rhwp_revision(self):
        content = (
            "# 인공지능 공통기반 검토보고\n\n"
            "## 1. 추진 배경\n인공지능 공동 활용 기반을 구축하여 행정업무 효율을 높인다.\n\n"
            "## 2. 주요 내용\n공통 서비스를 단계적으로 구축한다. 부처별 수요를 반영한다."
        )
        source = self.backend.REPORT_HWPX_MCP.build("인공지능 공통기반 검토보고", content)
        session = self.backend.open_native_document_session(
            {
                "filename": "인공지능_공통기반_검토보고.hwpx",
                "content_base64": base64.b64encode(source).decode("ascii"),
                "intent": "1차 보고서를 RHWP에서 열기",
                "confirmed": True,
                "actor": "flow-tester",
            }
        )
        context = {
            "classification": "internal",
            "document_id": session["id"],
            "filename": session["filename"],
            "document_excerpt": content,
            "previous_answer": content,
        }
        plan, execution = self.execute(
            "전체 내용을 개조식으로 다듬어줘",
            context,
            "flow-full-report-outline",
        )
        self.assertEqual(plan["workflow"]["responseType"], "document-transform")
        self.assertIn("document.report@1.0.0", plan["workflow"]["loadedMcps"])
        self.assertIn("document.report-hwpx@0.1.0", plan["workflow"]["loadedMcps"])
        self.assertIn("document.rhwp@1.0.0", plan["workflow"]["loadedMcps"])
        self.assertNotIn("output.text@1.0.0", plan["workflow"]["loadedMcps"])
        self.assertFalse(plan["dataPolicy"]["externalTransfer"])
        self.assertNotIn("model.invoke", plan["requiredPermissions"])
        self.assertNotIn("network.send", plan["requiredPermissions"])
        artifact = execution["result"]["artifact"]
        self.assertEqual(artifact["applyMode"], "replace-current-session")
        self.assertIn("- 인공지능 공동 활용 기반", artifact["content"])
        updated = self.backend.command_native_document_session(
            session["id"],
            {
                "base_revision": session["revision"],
                "command": "replace_artifact",
                "arguments": {"contentBase64": artifact["contentBase64"], "filename": artifact["filename"]},
                "confirmed": True,
                "actor": "flow-tester",
            },
        )
        self.assertEqual(updated["id"], session["id"])
        self.assertEqual(updated["revision"], 2)

    def test_outline_report_request_in_empty_workspace_creates_new_artifact(self):
        intent = (
            "인공지능 공통기반 관련 예산 결산 지적사항을 정리해주고, "
            "지적사항별 대안 및 향후 계획을 산출하여 보고서로 생성해줘. "
            "중앙부처 개조식으로 구성해줘"
        )
        plan = self.backend.create_plan(
            {
                "intent": intent,
                "actor": "flow-tester",
                "document_context": {
                    "classification": "internal",
                    "document_id": "workspace-document",
                    "filename": "새 프로젝트",
                    "has_attachment": False,
                    "has_selection": False,
                    "document_excerpt": "아직 생성된 산출물이 없습니다.",
                },
            }
        )
        self.assertEqual(plan["workflow"]["responseType"], "report-artifact")
        self.assertFalse(plan["workflow"]["signals"]["documentTransform"])
        self.assertFalse(plan["workflow"]["hasAttachment"])
        self.assertTrue(plan["intentAnalysis"]["createsInitialDocument"])
        self.assertEqual(plan["routing"]["model"]["id"], "upstage:solar-pro4")
        self.assertNotIn("read-current-document", [step["id"] for step in plan["steps"]])

    def test_attachment_settlement_and_selection_capabilities(self):
        plan, execution = self.execute(
            "첨부된 문서를 기준으로 올해 결산 보고서 양식으로 작성해줘",
            {
                "classification": "internal",
                "has_attachment": True,
                "filename": "사업실적.hwpx",
                "document_excerpt": "사업비 집행률 92%, 주요 기능 구축 완료",
            },
            "flow-settlement-report",
        )
        self.assertEqual(plan["workflow"]["responseType"], "report-artifact")
        self.assertIn("document.report-hwpx@0.1.0", plan["workflow"]["loadedMcps"])
        self.assertEqual(execution["result"]["artifact"]["editorMcp"], "document.rhwp@1.0.0")
        self.assertIn("template.settlement@0.1.0", plan["workflow"]["loadedMcps"])
        self.assertIn("사업실적.hwpx", execution["result"]["artifact"]["content"])

        rewrite = self.backend.WORKSPACE_ORCHESTRATION_MCP.build_workflow(
            "이 문구의 당위성을 강조해줘",
            {"has_selection": True, "selection_text": "사업을 추진한다."},
            {"model": {"id": "upstage/solar-pro-3"}},
        )
        self.assertEqual(rewrite["responseType"], "selection-edit")
        self.assertIn("document.report@1.0.0", rewrite["loadedMcps"])

        legal = self.backend.WORKSPACE_ORCHESTRATION_MCP.build_workflow(
            "이 문구에 해당되는 법조항을 찾아줘",
            {"has_selection": True, "selection_text": "개인정보를 처리한다."},
            {"model": {"id": "upstage/solar-pro-3"}},
        )
        self.assertEqual(legal["responseType"], "context-answer")
        self.assertIn("knowledge.legal@0.1.0", legal["loadedMcps"])


    def test_verbose_model_rewrite_is_reduced_to_replacement_text(self):
        verbose = (
            "수정된 문장 **: ** \"브라우저를 통해 HWPX 원문을 편집해 주시기 바랍니다.\"\n\n"
            "**변경 사항 설명**\n1. 공손한 어투를 적용했습니다."
        )
        self.assertEqual(
            self.backend.REWRITE_OUTPUT_MCP.clean(verbose),
            "브라우저를 통해 HWPX 원문을 편집해 주시기 바랍니다.",
        )

if __name__ == "__main__":
    unittest.main()
