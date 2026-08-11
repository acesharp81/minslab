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
        self.assertIn("permissions", manifest["required"])
        self.assertIn("versions", common["required"])
        self.assertIn("dataPolicy", plan["required"])
        scopes = manifest["properties"]["permissions"]["items"]["properties"]["scope"]["enum"]
        self.assertIn("network.send", scopes)
        self.assertIn("model.invoke", scopes)

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

    def test_grounded_knowledge_contract_requires_sources(self):
        knowledge = self.load("contracts/knowledge-node.schema.json")
        self.assertIn("sources", knowledge["required"])
        self.assertIn("classification", knowledge["required"])
        source = knowledge["properties"]["sources"]["items"]
        self.assertIn("documentId", source["required"])
        self.assertIn("locator", source["required"])
        self.assertIn("confidence", source["required"])

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

    def test_sample_data_is_traceable_and_temporal(self):
        sample = self.load("sample-data/budget-request.json")
        records = sample["commonData"]
        self.assertTrue(all(item["versions"] for item in records))
        self.assertTrue(all(v["source"]["locator"] for item in records for v in item["versions"]))
        temporal = next(item for item in records if item["kind"] == "temporal")
        self.assertGreaterEqual(len(temporal["versions"]), 2)


if __name__ == "__main__":
    unittest.main()
