import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from helpers import make_region
from datacheck.cli import main


def run_main(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(argv)
    return code, out.getvalue()


def cli(*args):
    """검증일을 2026-10-04로 고정해 main을 실행한다. (종료 코드, 출력)을 돌려준다."""
    return run_main([*map(str, args), "--today", "2026-10-04"])


def load(out_dir):
    return json.loads((Path(out_dir) / "validation_report.json").read_text(encoding="utf-8"))


def zip_region(zip_path, region_dir, prefix, extras=()):
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in sorted(Path(region_dir).iterdir()):
            zf.write(f, f"{prefix}{f.name}")
        for name, data in extras:
            zf.writestr(name, data)


def set_first(**kw):
    return lambda rows: rows[0].update(kw)


class CliTest(unittest.TestCase):
    def test_valid_folder_exits_0_and_writes_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            region, out = make_region(tmp), Path(tmp) / "out"
            code, text = cli(region, "--out", out)
            report = load(out)
            self.assertEqual(code, 0)
            self.assertEqual(report["summary"]["error"], 0)
            self.assertEqual([r["slug"] for r in report["regions"]], ["test-region"])
            self.assertFalse(report["regions"][0]["rejected"])
            self.assertEqual(report["regions"][0]["scope"]["public"], 1)
            md = (out / "validation_report.md").read_text(encoding="utf-8")
            self.assertIn("## test-region", md)
            self.assertIn("I202", md)
            self.assertIn("test-region", text)

    def test_error_exits_1_and_region_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            region, out = make_region(tmp, drop=("events.csv",)), Path(tmp) / "out"
            code, _ = cli(region, "--out", out)
            report = load(out)
            self.assertEqual(code, 1)
            self.assertTrue(report["regions"][0]["rejected"])
            self.assertIn("E001", [i["rule"] for i in report["issues"]])

    def test_strict_turns_warnings_into_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            region, out = make_region(tmp, edits={"projects.csv": set_first(units="500")}), Path(tmp) / "out"
            self.assertEqual(cli(region, "--out", out)[0], 0)
            self.assertIn("W104", [i["rule"] for i in load(out)["issues"]])
            self.assertEqual(cli(region, "--out", out, "--strict")[0], 1)

    def test_usage_errors_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty, afile = Path(tmp) / "empty", Path(tmp) / "a.txt"
            empty.mkdir()
            afile.write_text("x")
            self.assertEqual(cli(Path(tmp) / "nope")[0], 2)  # 경로 없음
            self.assertEqual(cli(empty)[0], 2)  # 지역 폴더를 찾지 못함
            self.assertEqual(cli(afile)[0], 2)  # .zip이 아닌 파일
            region = make_region(Path(tmp) / "r")
            code, text = run_main([str(region), "--today", "not-a-date"])
            self.assertEqual(code, 2)
            self.assertIn("--today", text)

    def test_quarantine_files_are_written_and_stale_ones_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            bad = make_region(Path(tmp) / "a", edits={"projects.csv": set_first(project_name="")})
            cli(bad, "--out", out)
            q = out / "quarantine" / "test-region" / "projects.csv"
            text = q.read_text(encoding="utf-8-sig")
            self.assertIn("_rule", text.splitlines()[0])
            self.assertIn("E101", text)
            good = make_region(Path(tmp) / "b")
            cli(good, "--out", out)
            self.assertFalse((out / "quarantine").exists())

    def test_quarantined_geojson_feature_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            region = make_region(tmp)
            bad = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [126.78, 35.15]},
                   "properties": {"project_id": "z1-A1", "tier": "schematic", "basis": "x",
                                  "source_id": "src-a", "observed_at": "2026-10-04"}}
            (region / "geometry_overrides.geojson").write_text(
                json.dumps({"type": "FeatureCollection", "features": [bad]}), encoding="utf-8")
            cli(region, "--out", out)
            data = json.loads((out / "quarantine" / "test-region" / "geometry_overrides.geojson").read_text(encoding="utf-8"))
            self.assertEqual(data["features"][0]["properties"]["_issues"][0]["rule"], "E108")

    def test_non_object_geojson_features_do_not_crash_the_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            region = make_region(tmp)
            features = ["abc", 5, {"type": "Feature", "properties": {}, "geometry": None}]
            (region / "geometry_overrides.geojson").write_text(
                json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
            code, _ = cli(region, "--out", out)
            self.assertEqual(code, 1)
            self.assertTrue((out / "validation_report.json").exists())
            data = json.loads((out / "quarantine" / "test-region" / "geometry_overrides.geojson").read_text(encoding="utf-8"))
            self.assertEqual(len(data["features"]), 3)
            self.assertEqual({f["properties"]["_issues"][0]["rule"] for f in data["features"]}, {"E101"})

    def test_two_regions_one_broken_still_reports_the_other(self):  # Review Focus 5
        with tempfile.TemporaryDirectory() as tmp:
            parent, out = Path(tmp) / "input", Path(tmp) / "out"
            make_region(parent, slug="test-region")
            make_region(parent, slug="broken-region", drop=("events.csv",))
            code, _ = cli(parent, "--out", out)
            report = load(out)
            by_slug = {r["slug"]: r for r in report["regions"]}
            self.assertEqual(code, 1)
            self.assertFalse(by_slug["test-region"]["rejected"])
            self.assertTrue(by_slug["broken-region"]["rejected"])
            self.assertEqual(report["summary"]["regions"], 2)
            self.assertEqual(report["summary"]["regions_rejected"], 1)
            self.assertEqual(by_slug["test-region"]["scope"]["public"], 1)

    def test_zip_from_macos_with_noise_and_top_folder(self):  # Review Focus 4
        with tempfile.TemporaryDirectory() as tmp:
            region, out, zp = make_region(Path(tmp) / "src"), Path(tmp) / "out", Path(tmp) / "submit.zip"
            zip_region(zp, region, "input/test-region/",
                       extras=[("__MACOSX/input/test-region/._regions.csv", "junk"), ("input/.DS_Store", "junk")])
            code, _ = cli(zp, "--out", out)
            self.assertEqual(code, 0)
            self.assertEqual([r["slug"] for r in load(out)["regions"]], ["test-region"])

    def test_zip_with_files_at_root_uses_zip_name_as_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            region, out, zp = make_region(Path(tmp) / "src"), Path(tmp) / "out", Path(tmp) / "test-region.zip"
            zip_region(zp, region, "")
            code, _ = cli(zp, "--out", out)
            self.assertEqual(code, 0)
            self.assertEqual([r["slug"] for r in load(out)["regions"]], ["test-region"])

    def test_zip_slip_is_refused_with_exit_2(self):  # Review Focus 4
        with tempfile.TemporaryDirectory() as tmp:
            zp = Path(tmp) / "evil.zip"
            with zipfile.ZipFile(zp, "w") as zf:
                zf.writestr("../evil.txt", "x")
            code, text = cli(zp, "--out", Path(tmp) / "out")
            self.assertEqual(code, 2)
            self.assertIn("안전하지 않은", text)
            self.assertFalse((Path(tmp) / "evil.txt").exists())


if __name__ == "__main__":
    unittest.main()
