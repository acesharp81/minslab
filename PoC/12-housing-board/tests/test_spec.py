import unittest

from helpers import SPEC

REQUIRED = ["regions.csv", "region_codes.csv", "sources.csv", "zones.csv", "projects.csv", "events.csv"]
OPTIONAL = ["dongs.csv", "geometry_overrides.geojson"]


class SpecTest(unittest.TestCase):
    def test_files_and_required_flags(self):
        self.assertEqual(SPEC.order, REQUIRED + OPTIONAL)
        self.assertEqual([n for n, f in SPEC.files.items() if f.required_file], REQUIRED)
        self.assertEqual(SPEC.files["geometry_overrides.geojson"].kind, "geojson")
        self.assertEqual(SPEC.files["projects.csv"].kind, "csv")

    def test_primary_keys_use_known_columns(self):
        for name, fs in SPEC.files.items():
            known = set(fs.column_names) | {"region_slug"}  # GeoJSON 행에는 region_slug가 자동으로 들어간다
            self.assertLessEqual(set(fs.primary_key), known, name)

    def test_refs_point_to_existing_files_and_primary_keys(self):
        for name, fs in SPEC.files.items():
            for ref in fs.refs:
                self.assertIn(ref.to, SPEC.files, f"{name} → {ref.to}")
                self.assertEqual(len(ref.columns), len(ref.to_columns))
                self.assertEqual(tuple(ref.to_columns), SPEC.files[ref.to].primary_key, f"{name} → {ref.to}")
                self.assertLessEqual(set(ref.columns), set(fs.column_names) | {"region_slug"})

    def test_ref_targets_come_first_in_order(self):
        order = SPEC.order
        for name, fs in SPEC.files.items():
            for ref in fs.refs:
                self.assertLess(order.index(ref.to), order.index(name), f"{name} → {ref.to}")

    def test_enums_and_public_land_types(self):
        self.assertEqual(SPEC.public_land_zone_types, ("택지개발", "공공주택지구", "혁신도시", "신도시"))
        self.assertLessEqual(set(SPEC.public_land_zone_types), set(SPEC.enums["zone_type"]))
        self.assertEqual(SPEC.enums["sponsor_type"], ("public", "private", "joint", "unknown"))
        self.assertEqual(
            SPEC.enums["event_type"],
            ("notice", "permit_approved", "construction_start", "progress",
             "completion_inspection", "move_in", "structure_observed"),
        )
        self.assertEqual(SPEC.enums["tier"], ("official", "building", "schematic"))

    def test_schema_version_is_semver(self):
        self.assertRegex(SPEC.schema_version, r"^\d+\.\d+\.\d+$")

    def test_required_columns_of_projects(self):
        self.assertEqual(
            SPEC.files["projects.csv"].required_columns,
            ["region_slug", "project_id", "project_name", "block_label", "sponsor_name",
             "sponsor_type", "project_kind", "source_id", "observed_at"],
        )


if __name__ == "__main__":
    unittest.main()
