"""tools/boarddata — 통계누리·LH 원천 → data/board/*.json. 계산 규칙과 항등식, 저장소의 JSON 이 원천과 같은지(낡음 검사)."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT  # noqa: F401  (tools/ 를 sys.path 에 넣는다)

from boarddata import build_board_data as B, catalog, lh, molit as M

DATA = ROOT / "data"
HAVE_SOURCES = (DATA / "processed" / "molit_인허가_월별누계.csv").exists() and (DATA / "raw" / "datagokr").exists()
needs_sources = unittest.skipUnless(HAVE_SOURCES, "원천 파일(data/raw·processed)이 없다")


def row(month, name, gubun, bubun, value, key="호수"):
    return {"기간": month, "시도": name, "구분": gubun, "부문": bubun, key: str(value), "잠정치": ""}


class Rules(unittest.TestCase):
    def test_actor_of_picks_totals_and_four_actors_only(self):
        self.assertEqual(M.actor_of("총계", "총계"), "total")
        for a in ("지자체", "LH", "주택업체"):
            self.assertEqual(M.actor_of(a, "소계"), a)
            self.assertIsNone(M.actor_of(a, "공공임대"))   # 세부 부문 행은 시행주체 합에 넣지 않는다
        # 민간은 착공·준공이 (민간부문, 소계), 인허가가 (민간부문, 민간부문) 로 적혀 있다
        self.assertEqual(M.actor_of("민간부문", "소계"), "민간")
        self.assertEqual(M.actor_of("민간부문", "민간부문"), "민간")
        self.assertIsNone(M.actor_of("민간", "민간분양"))
        self.assertIsNone(M.actor_of("공공부문", "공공부문"))   # 공공 합계는 세 분류의 합이라 따로 세지 않는다

    def test_cumulative_to_flow(self):
        months = ["2021-09", "2021-10", "2021-12", "2022-01", "2022-02"]
        # 2021-09 는 첫 달이라 알 수 없고, 직전 달이 자료에 없는 2021-12 도 알 수 없다. 1월은 값 그대로.
        got = M.cumulative_to_flow({"2021-09": 100, "2021-10": 130, "2021-12": 200, "2022-01": 7, "2022-02": 20}, months)
        self.assertEqual(got, [None, 30, None, 7, 13])
        self.assertEqual(M.cumulative_to_flow({"2021-09": 1, "2021-10": 3}, ["2021-09", "2021-10", "2021-11"]), [None, 2, None])   # 값이 빈 달은 None

    def test_gwangju_and_jeonnam_are_summed_into_code_12_until_they_merge(self):
        items = [("광주", "total", "2026-06", 10), ("전남", "total", "2026-06", 5), ("전남광주", "total", "2026-07", 20), ("서울", "total", "2026-07", 1)]
        acc = M._collect(items)
        self.assertEqual(dict(acc["12"]["total"]), {"2026-06": 15, "2026-07": 20})
        self.assertEqual(dict(acc["11"]["total"]), {"2026-07": 1})

    def test_collect_rejects_bad_name_sets(self):
        with self.assertRaises(ValueError):   # 통합 뒤에 광주가 또 나오면 이중 집계다
            M._collect([("광주", "total", "2026-07", 1), ("전남광주", "total", "2026-07", 2)])
        with self.assertRaises(ValueError):
            M._collect([("서울", "total", "2026-07", 1), ("서울", "total", "2026-07", 1)])   # 같은 행 중복
        with self.assertRaises(ValueError):
            M._collect([("수도권", "total", "2026-07", 1)])   # 시도가 아닌 집계 행

    def test_verify_catches_actor_sum_and_nation_sum_mismatch(self):
        months = ["2022-01", "2022-12"]
        zeros = {a: [0, 0] for a in M.ACTORS}
        ser = {c: {"total": [0, 0], "actors": dict(zeros)} for c in [M.NATION] + [c for c, _ in M.SIDO]}
        data = {"months": months, "sido": [{"code": c} for c in ser], "metrics": {k: {"series": json.loads(json.dumps(ser))} for k in ("permit", "start", "complete")}}
        data["metrics"]["sale"] = {"series": {c: {"total": [0, 0]} for c in ser}}
        self.assertEqual(M.verify(data, [], []), [])
        data["metrics"]["start"]["series"]["11"]["total"][0] = 5   # 총계만 올리면 시행주체 합과 시도 합이 모두 어긋난다
        bad = M.verify(data, [], [])
        self.assertTrue(any("시행주체 합" in b for b in bad) and any("시도 합" in b for b in bad), bad)

    def test_lh_rejects_unknown_sido(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "lh.csv"
            p.write_bytes("사업지구명,블록명,위치,공급유형,세대수,준공예정일\nA,1,화성시 어딘가,공공분양,10,2027-01-01\n".encode("cp949"))
            with self.assertRaises(ValueError):
                lh.read_blocks(p)

    def test_catalog_filename_shapes(self):
        self.assertEqual(catalog._split_name("15141761_한국토지주택공사_공공주택 준공예정현황_20260127"), ("15141761", "한국토지주택공사", "공공주택 준공예정현황", "2026-01-27"))
        self.assertEqual(catalog._split_name("15043330_한국토지주택공사 행복주택 공급계획_20250922"), ("15043330", "한국토지주택공사", "행복주택 공급계획", "2025-09-22"))
        self.assertEqual(catalog._split_name("15061908_국방부_군 특별공급 주택 공고 상세 현황"), ("15061908", "국방부", "군 특별공급 주택 공고 상세 현황", None))


@needs_sources
class RealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.made = B.make(ROOT)   # 항등식이 어긋나면 여기서 SystemExit

    def test_identities_hold_for_every_month_sido_and_metric(self):
        p = DATA / "processed"
        permit, annual = M.read_csv(p / "molit_인허가_월별누계.csv"), M.read_csv(p / "molit_인허가_지역별_연간.csv")
        self.assertEqual(M.verify(self.made["molit.json"], permit, annual), [])

    def test_shape(self):
        d = self.made["molit.json"]
        self.assertEqual(len(d["months"]), 60)
        self.assertEqual((d["months"][0], d["months"][-1]), ("2021-09", "2026-08"))
        self.assertEqual(d["provisional"], [f"2026-{m:02d}" for m in range(1, 9)])   # 잠정치: 2026-01 ~ 08
        self.assertEqual([s["code"] for s in d["sido"]], ["00"] + [c for c, _ in M.SIDO])
        permit = d["metrics"]["permit"]["series"]["00"]["total"]
        self.assertIsNone(permit[0])   # 자료가 2021-09 부터라 첫 달의 월 흐름은 알 수 없다
        self.assertTrue(all(v is not None for v in permit[1:]))
        for k in ("start", "complete", "sale"):
            self.assertTrue(all(v is not None for v in d["metrics"][k]["series"]["00"]["total"]), k)

    def test_spot_values_match_the_source_files(self):
        d = self.made["molit.json"]
        i = d["months"].index("2026-08")
        # 통계누리 착공 월계 전국 2026-08 = 18,013 (지자체 497 + LH 0 + 주택업체 265 + 민간 17,251)
        start = d["metrics"]["start"]["series"]["00"]
        self.assertEqual((start["total"][i], [start["actors"][a][i] for a in M.ACTORS]), (18013, [497, 0, 265, 17251]))
        # 인허가 누계 전국 2021-12 = 535,971 = 2021 연간 실적, 2021-10 월 흐름 = 401,562 - 355,923
        permit = d["metrics"]["permit"]["series"]["00"]["total"]
        self.assertEqual(permit[d["months"].index("2021-10")], 401562 - 355923)
        self.assertEqual(permit[d["months"].index("2026-01")], 16531)   # 1월은 누계 값 그대로
        self.assertEqual(sum(permit[d["months"].index("2026-01"):]), 163935)   # 2026-01~08 흐름의 합 = 2026-08 누계

    def test_lh_completion(self):
        d = self.made["lh-completion.json"]
        self.assertEqual((d["count"], d["units"], d["sourceAsOf"]), (351, 151590, "2026-01-27"))
        self.assertEqual(sum(b["units"] for b in d["blocks"]), 151590)
        self.assertEqual({b["sido"] for b in d["blocks"]} - {c for c, _ in M.SIDO}, set())
        self.assertEqual([b["date"] for b in d["blocks"]], sorted(b["date"] for b in d["blocks"]))

    def test_catalog_covers_every_source_file_and_keeps_collected_and_as_of_apart(self):
        items = self.made["sources.json"]["items"]
        self.assertEqual(len({i["id"] for i in items}), len(items))
        files = {i["query"]["file"] for i in items if i["id"].startswith("datagokr-")}
        self.assertEqual(files, {p.name for p in (DATA / "raw" / "datagokr").glob("*.csv")})
        for i in items:
            self.assertIn("collectedAt", i)
            self.assertIn("sourceAsOf", i)   # 둘을 섞지 않는다(스펙 9.3). 모르면 None
            self.assertNotIn("usedCount", i)   # '사용'의 정의가 미결(기획서 Q8)이라 건수는 만들지 않는다
        lh_item = next(i for i in items if i["id"] == "datagokr-15141761")
        self.assertEqual((lh_item["count"], lh_item["sourceAsOf"], lh_item["usedBy"]), (351, "2026-01-27", ["/", "/month", "/agency"]))

    def test_committed_json_is_current(self):
        for name, obj in self.made.items():
            path = ROOT / "data" / "board" / name
            self.assertTrue(path.exists(), f"{name} 이 없다: python3 tools/boarddata/build_board_data.py")
            self.assertEqual(path.read_text(encoding="utf-8"), B.dump(obj), f"{name} 이 원천과 다르다: python3 tools/boarddata/build_board_data.py")


class SidoTable(unittest.TestCase):
    def test_sido_codes_equal_the_known_sido_set_of_lib_codes(self):
        src = (ROOT / "lib" / "codes.js").read_text(encoding="utf-8")
        known = set(re.search(r"KNOWN_SIDO = new Set\(\[([^\]]*)\]\)", src).group(1).replace("'", "").replace(" ", "").split(","))
        self.assertEqual({c for c, _ in M.SIDO}, known)


if __name__ == "__main__":
    unittest.main()
