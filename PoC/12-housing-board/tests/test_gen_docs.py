import unittest

from helpers import SPEC
import gen_docs


class GenDocs(unittest.TestCase):
    def test_csv_templates_are_header_only_with_bom(self):
        templates = gen_docs.render_templates(SPEC)
        text = templates["projects.csv"]
        self.assertTrue(text.startswith("﻿region_slug,project_id,zone_id,project_name"))
        self.assertEqual(text.count("\n"), 1)
        self.assertEqual(sorted(templates), sorted(SPEC.files))

    def test_geojson_template_is_an_empty_feature_collection(self):
        text = gen_docs.render_templates(SPEC)["geometry_overrides.geojson"]
        self.assertIn('"type": "FeatureCollection"', text)
        self.assertIn('"features": []', text)

    def test_field_tables_list_every_file_and_column(self):
        md = gen_docs.render_field_tables(SPEC)
        for name, fs in SPEC.files.items():
            self.assertIn(f"#### {name}", md)
            for c in fs.columns:
                self.assertIn(f"| `{c.name}` |", md)
        self.assertIn("참조:", md)

    def test_required_columns_are_marked(self):
        md = gen_docs.render_field_tables(SPEC)
        self.assertIn("| `project_id` | ● |", md)
        self.assertIn("| `zone_id` |  |", md)

    def test_enum_table_lists_every_value(self):
        md = gen_docs.render_enums(SPEC)
        for name, values in SPEC.enums.items():
            self.assertIn(f"`{name}`", md)
            for v in values:
                self.assertIn(v, md)

    def test_type_label(self):
        floors = SPEC.files["dongs.csv"].columns[3]
        self.assertEqual(floors.name, "floors_above")
        self.assertEqual(gen_docs.type_label(floors), "정수 0~120")
        sponsor = [c for c in SPEC.files["projects.csv"].columns if c.name == "sponsor_type"][0]
        self.assertEqual(gen_docs.type_label(sponsor), "열거 (sponsor_type)")

    def test_inject_replaces_between_markers_and_is_idempotent(self):
        text = "머리\n<!-- GENERATED:x:BEGIN -->\n옛 내용\n<!-- GENERATED:x:END -->\n꼬리\n"
        once = gen_docs.inject(text, "x", "새 내용\n")
        self.assertEqual(once, "머리\n<!-- GENERATED:x:BEGIN -->\n새 내용\n<!-- GENERATED:x:END -->\n꼬리\n")
        self.assertEqual(gen_docs.inject(once, "x", "새 내용\n"), once)

    def test_inject_without_markers_raises(self):
        with self.assertRaises(ValueError):
            gen_docs.inject("표지 없음", "x", "내용\n")


class RepoDocs(unittest.TestCase):
    def test_repo_docs_and_templates_are_up_to_date(self):
        self.assertEqual(gen_docs.main(["--check"]), 0)

    def test_definition_has_all_sections_and_markers(self):
        text = gen_docs.DOC.read_text(encoding="utf-8")
        for heading in ["## 0. 개요·범위·용어", "## 1. 데이터 흐름과 책임", "## 2. 공통 규약", "## 3. 입력 표 정의",
                        "## 4. 이벤트와 상태 계산 규칙", "## 5. 시행자 유형과 공공택지 판정",
                        "## 6. 윤곽 등급과 화면 표기", "## 7. 출력 번들 스키마", "## 8. 검증 규칙과 격리 목록",
                        "## 9. 품질 함정 체크리스트", "## 10. 버전과 변경 절차", "## 11. 제출 방법",
                        "## 부록 A", "## 부록 B", "## 부록 C"]:
            self.assertIn(heading, text)
        for name in ("fields", "enums"):
            self.assertIn(f"<!-- GENERATED:{name}:BEGIN -->", text)

    def test_every_rule_id_appears_in_the_definition(self):
        text = gen_docs.DOC.read_text(encoding="utf-8")
        for rule in "E001 E002 E003 E101 E102 E103 E104 E105 E106 E107 E108 W001 W101 W102 W103 W104 W105 W106 I201 I202".split():
            self.assertIn(f"| {rule} |", text, rule)


    def test_definition_warns_about_excel_number_format(self):
        text = gen_docs.DOC.read_text(encoding="utf-8")
        self.assertIn("셀 서식을 '텍스트'", text)
        self.assertIn("| 9 |", text)  # 9절 체크리스트의 9번째 함정


if __name__ == "__main__":
    unittest.main()
