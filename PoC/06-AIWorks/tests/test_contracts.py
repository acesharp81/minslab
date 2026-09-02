import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AIWorksContractTests(unittest.TestCase):
    def load(self, relative):
        return json.loads((ROOT / relative).read_text(encoding="utf-8"))

    def test_project_metadata(self):
        project = self.load("project.json")
        self.assertEqual(project["id"], "aiworks")
        self.assertEqual(project["order"], 6)
        self.assertTrue((ROOT / project["entry_file"]).is_file())

    def test_contracts_have_required_boundaries(self):
        manifest = self.load("contracts/mcp-manifest.schema.json")
        common = self.load("contracts/common-data.schema.json")
        plan = self.load("contracts/execution-plan.schema.json")
        intent = self.load("contracts/intent-analysis.schema.json")
        self.assertIn("permissions", manifest["required"])
        self.assertIn("versions", common["required"])
        self.assertIn("dataPolicy", plan["required"])
        self.assertEqual(intent["properties"]["contractVersion"]["const"], "intent-analysis/1.0")
        self.assertIn("requiredCapabilities", intent["required"])
        self.assertNotIn("packageId", intent["properties"])
        scopes = manifest["properties"]["permissions"]["items"]["properties"]["scope"]["enum"]
        self.assertIn("network.send", scopes)
        context = self.load("contracts/context-assembly.schema.json")
        tasks = self.load("contracts/task-compiler.schema.json")
        resolution = self.load("contracts/capability-resolution.schema.json")
        self.assertEqual(context["properties"]["contractVersion"]["const"], "context-assembly/1.0")
        self.assertEqual(tasks["properties"]["contractVersion"]["const"], "task-compiler/1.0")
        self.assertEqual(resolution["properties"]["contractVersion"]["const"], "capability-resolution/1.0")
        self.assertIn("decisions", resolution["required"])
        task_required = tasks["properties"]["tasks"]["items"]["required"]
        self.assertIn("capabilityId", task_required)
        self.assertIn("inputArtifactTypes", task_required)
        self.assertIn("outputArtifactTypes", task_required)
        decision_required = resolution["properties"]["decisions"]["items"]["required"]
        self.assertIn("rankScore", decision_required)
        self.assertIn("ioContract", decision_required)
        self.assertIn("reason", decision_required)
        self.assertIn("model.invoke", scopes)
        dag = self.load("contracts/capability-dag.schema.json")
        self.assertEqual(dag["properties"]["contractVersion"]["const"], "capability-dag/1.0")
        self.assertIn("compatibilityChecks", dag["required"])

    def test_document_patch_and_native_bridge_boundaries(self):
        patch = self.load("contracts/document-patch.schema.json")
        bridge = self.load("contracts/document-adapter-bridge.json")
        self.assertEqual(patch["properties"]["op"]["const"], "replace")
        self.assertIn("sourceSha256", patch["required"])
        self.assertIn("expectedBefore", patch["required"])
        self.assertFalse(patch["additionalProperties"])
        self.assertEqual(bridge["adapters"]["hwpx"]["status"], "implemented")
        self.assertEqual(bridge["adapters"]["rhwp"]["status"], "implemented")
        self.assertEqual(bridge["adapters"]["rhwp"]["mcp"], "document.rhwp@1.0.0")
        self.assertIn("rhwp.document.action", bridge["adapters"]["rhwp"]["tools"])
        self.assertIn("no direct internet access", bridge["adapters"]["rhwp"]["restrictions"])
        session = self.load("contracts/document-session.schema.json")
        self.assertIn("orchestration", session["required"])
        self.assertIn("purpose", session["required"])
        self.assertEqual(set(session["properties"]["purpose"]["enum"]), {"document", "template-authoring"})
        self.assertEqual(
            session["properties"]["orchestration"]["properties"]["requestedAdapter"]["type"],
            "string",
        )
        self.assertEqual(
            set(session["properties"]["adapter"]["enum"]),
            {"document.rhwp@1.0.0", "document.rhwp-web@0.8.2", "document.hwpx@1.2.0", "document.markdown@1.0.0", "code.editor@1.0.0"},
        )

    def test_signed_mcp_package_contract(self):
        package = self.load("contracts/mcp-package.schema.json")
        self.assertIn("bundleSha256", package["required"])
        self.assertIn("signature", package["required"])
        signature = package["properties"]["signature"]
        self.assertEqual(signature["properties"]["algorithm"]["const"], "HMAC-SHA256")
        self.assertFalse(signature["additionalProperties"])

    def test_mcp_builder_draft_contract_tracks_validation_and_publication(self):
        draft = self.load("contracts/mcp-draft.schema.json")
        self.assertIn("validation", draft["required"])
        self.assertEqual(
            set(draft["properties"]["status"]["enum"]),
            {"draft", "validated", "rejected", "published"},
        )
        test = draft["properties"]["validation"]["properties"]["tests"]["items"]
        self.assertEqual(test["required"], ["id", "passed", "detail"])
        self.assertIn("publishedPackageId", draft["properties"])
        reference_roles = draft["properties"]["references"]["items"]["properties"]["role"]["enum"]
        self.assertIn("data-source", reference_roles)

    def test_dynamic_capability_binding_is_versioned_and_signed(self):
        manifest = self.load("contracts/mcp-manifest.schema.json")
        binding = self.load("contracts/capability-binding.schema.json")
        self.assertIn("executionAdapter", manifest["properties"])
        self.assertIn("packageRef", binding["required"])
        self.assertIn("score", binding["required"])
        self.assertEqual(binding["properties"]["signatureVerified"]["const"], True)
        self.assertEqual(set(binding["properties"]["executionAdapter"]["enum"]), {"prompt", "composite", "retrieval", "external-mcp"})
        self.assertEqual(manifest["properties"]["retrieval"]["properties"]["kind"]["const"], "local-rag")
        self.assertEqual(set(manifest["properties"]["externalMcp"]["properties"]["transport"]["enum"]), {"stdio", "streamable-http"})

    def test_grounded_knowledge_contract_requires_sources(self):
        knowledge = self.load("contracts/knowledge-node.schema.json")
        self.assertIn("sources", knowledge["required"])
        self.assertIn("classification", knowledge["required"])
        source = knowledge["properties"]["sources"]["items"]
        self.assertIn("documentId", source["required"])
        self.assertIn("locator", source["required"])
        self.assertIn("confidence", source["required"])

    def test_report_document_contract_separates_content_facts_and_presentation(self):
        contract = self.load("contracts/report-document.schema.json")
        self.assertIn("blocks", contract["required"])
        self.assertIn("factRefs", contract["required"])
        self.assertIn("normalizedMarkdown", contract["required"])
        self.assertEqual(contract["properties"]["blocks"]["items"]["properties"]["type"]["enum"], ["heading", "paragraph", "list_item", "table", "note"])

    def test_project_markdown_and_format_adapter_contracts(self):
        document = self.load("contracts/project-markdown-document.schema.json")
        adapter = self.load("contracts/document-format-adapter.schema.json")
        workbench = self.load("contracts/project-document-workbench.schema.json")
        self.assertIn("markdown", document["required"])
        self.assertIn("markdownSha256", document["required"])
        self.assertIn("factSnapshot", document["required"])
        self.assertEqual(adapter["properties"]["sourceOfTruth"]["type"], "boolean")
        self.assertIn("document", adapter["properties"]["capability"]["pattern"])
        self.assertIn("artifacts", workbench["required"])
        self.assertIn("outputs", workbench["required"])
        self.assertIn("stale", workbench["properties"]["artifacts"]["items"]["properties"]["status"]["enum"])
        self.assertFalse(workbench["properties"]["outputs"]["items"]["properties"]["projectManaged"]["const"])

    def test_project_governance_artifact_workflow_and_recipe_contracts(self):
        project = self.load("contracts/project.schema.json")
        policy = self.load("contracts/project-policy.schema.json")
        grant = self.load("contracts/permission-grant.schema.json")
        artifact = self.load("contracts/artifact.schema.json")
        relation = self.load("contracts/artifact-relation.schema.json")
        workflow = self.load("contracts/workflow-run.schema.json")
        recipe = self.load("contracts/workflow-recipe.schema.json")
        self.assertIn("resolver", policy["properties"])
        self.assertEqual(set(project["properties"]["status"]["enum"]), {"active", "archived"})
        self.assertIn("classification", project["required"])
        evidence = self.load("contracts/artifact-evidence.schema.json")
        backup = self.load("contracts/project-backup.schema.json")
        self.assertIn("scopes", grant["required"])
        self.assertIn("currentVersionId", artifact["required"])
        self.assertIn("derived_from", relation["properties"]["relation"]["enum"])
        self.assertIn("resumedFromRunId", workflow["properties"])
        self.assertEqual(recipe["properties"]["versions"]["items"]["properties"]["definition"]["properties"]["contractVersion"]["const"], "1.0")
        self.assertEqual(recipe["properties"]["visibility"]["enum"], ["private", "organization", "public"])
        self.assertIn("preview", recipe["properties"])
        self.assertIn("excerptSha256", evidence["required"])
        self.assertEqual(backup["properties"]["format"]["const"], "aiworks-project-backup")
        self.assertEqual(backup["properties"]["schemaVersion"]["const"], "1.2")
        conversation = self.load("contracts/project-conversation.schema.json")
        decision = self.load("contracts/project-decision.schema.json")
        self.assertIn("messages", conversation["properties"])
        self.assertIn("documentVersionId", conversation["properties"]["messages"]["items"]["properties"])
        self.assertIn("scope", decision["required"])
        self.assertNotIn("documentArtifacts", backup["properties"]["data"]["required"])
        self.assertEqual(backup["properties"]["integrity"]["properties"]["algorithm"]["const"], "SHA-256")

    def test_builder_beginner_manual_is_visual_and_inside_application_body(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertLess(html.index('id="builderManualDialog"'), html.index("</body>"))
        self.assertIn("처음부터 따라하기", script)
        self.assertIn("manual-choice-scene", script)
        self.assertIn("manual-test-scene", script)
        self.assertIn("manual-call-scene", script)
        self.assertIn(".builder-manual-layout", styles)
        self.assertIn("data-manual-step", script)

    def test_multimodal_adapter_and_preset_contracts(self):
        adapter = self.load("contracts/capability-adapter.schema.json")
        preset = self.load("contracts/workflow-preset.schema.json")
        modalities = set(adapter["properties"]["modality"]["enum"])
        self.assertEqual(modalities, {"document", "code", "image", "audio", "video"})
        self.assertIn("acceptedFormats", preset["required"])
        self.assertIn("steps", preset["required"])
        statuses = preset["properties"]["steps"]["items"]["properties"]["status"]["enum"]
        self.assertIn("contract-only", statuses)

    def test_acceptance_report_contract_is_check_based(self):
        report = self.load("contracts/acceptance-report.schema.json")
        self.assertEqual(report["properties"]["scenario"]["const"], "budget-request-e2e")
        self.assertIn("checks", report["required"])
        check = report["properties"]["checks"]["items"]
        self.assertIn("passed", check["required"])
        self.assertFalse(check["additionalProperties"])

    def test_template_render_map_and_operations_contracts(self):
        template = self.load("contracts/template-schema.schema.json")
        render_map = self.load("contracts/render-map.schema.json")
        metrics = self.load("contracts/operations-metrics.schema.json")
        self.assertEqual(template["properties"]["contractVersion"]["const"], "1.2")
        self.assertIn("slotDefinitions", template["required"])
        self.assertIn("ocrRequired", template["required"])
        self.assertEqual(render_map["properties"]["contractVersion"]["const"], "1.2")
        self.assertIn("structureFingerprint", render_map["properties"]["mappings"]["items"]["required"])
        self.assertEqual(metrics["properties"]["exportBoundary"]["properties"]["status"]["const"], "adapter-required")
        self.assertIn("approvalLeases", metrics["required"])
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("merge-selected", script)
        self.assertIn("selected_change_ids", script)
        self.assertIn("data-conflict-change", script)
        self.assertIn(".conflict-block-diff", styles)

    def test_sample_data_is_traceable_and_temporal(self):
        sample = self.load("sample-data/budget-request.json")
        records = sample["commonData"]
        self.assertTrue(all(item["versions"] for item in records))
        self.assertTrue(all(v["source"]["locator"] for item in records for v in item["versions"]))
        temporal = next(item for item in records if item["kind"] == "temporal")
        self.assertGreaterEqual(len(temporal["versions"]), 2)


if __name__ == "__main__":
    unittest.main()
