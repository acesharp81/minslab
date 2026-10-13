import json
import unittest

from helpers import ROOT, SPEC

SCHEMAS = ROOT / "schemas" / "bundle"
NAMES = ["index", "region", "projects", "buildings", "context", "infra"]
STATUSES = ["계획", "분양중", "건설 단계", "준공 임박", "입주 단계"]


def load(name):
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))


class BundleSchemas(unittest.TestCase):
    def test_all_schemas_are_json_schema_documents(self):
        for name in NAMES:
            with self.subTest(name):
                s = load(name)
                self.assertEqual(s["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertTrue(s["title"].startswith("regions/"))
                self.assertEqual(s["type"], "object")
                self.assertIn("required", s)

    def test_refs_resolve_inside_each_schema(self):
        for name in NAMES:
            schema = load(name)

            def walk(node):
                if isinstance(node, dict):
                    ref = node.get("$ref")
                    if ref:
                        self.assertTrue(ref.startswith("#/$defs/"), ref)
                        self.assertIn(ref.split("/")[-1], schema["$defs"], f"{name}: {ref}")
                    for v in node.values():
                        walk(v)
                elif isinstance(node, list):
                    for v in node:
                        walk(v)

            walk(schema)

    def test_enums_match_the_input_spec(self):
        projects, region, index = load("projects"), load("region"), load("index")
        self.assertEqual(projects["$defs"]["status"]["enum"], STATUSES)
        self.assertEqual(tuple(projects["$defs"]["tier"]["enum"]), SPEC.enums["tier"])
        event_enum = projects["$defs"]["project"]["properties"]["events"]["items"]["properties"]["type"]["enum"]
        self.assertEqual(tuple(event_enum), SPEC.enums["event_type"])
        zone_enum = region["properties"]["zones"]["items"]["properties"]["type"]["enum"]
        self.assertEqual(tuple(zone_enum), SPEC.enums["zone_type"])
        self.assertEqual(region["properties"]["statusOrder"]["items"]["enum"], STATUSES)
        self.assertEqual(index["properties"]["regions"]["items"]["properties"]["visibility"]["enum"],
                         ["public", "preview"])

    def test_sponsor_class_and_flags(self):
        project = load("projects")["$defs"]["project"]["properties"]
        self.assertEqual(project["sponsorClass"]["enum"], ["public", "private_on_public_land"])
        self.assertEqual(project["flags"]["items"]["enum"], ["suspect_floors", "suspect_dates"])


class BundleSchema110(unittest.TestCase):
    def test_1_1_0_optional_fields_exist_and_stay_optional(self):
        projects, region = load("projects"), load("region")
        project = projects["$defs"]["project"]
        for name in ("note", "builder", "contractAmountM"):
            self.assertIn(name, project["properties"], name)
            self.assertNotIn(name, project["required"], name)
        progress = project["properties"]["progress"]["properties"]
        for name in ("start", "end", "source"):
            self.assertIn(name, progress, name)
        self.assertEqual(project["properties"]["progress"]["required"], ["rate", "asOf"])
        self.assertEqual(region["properties"]["projectOrder"]["items"], {"type": "string"})
        self.assertNotIn("projectOrder", region["required"])
        self.assertIn("schema_version", load("buildings")["properties"])


if __name__ == "__main__":
    unittest.main()
