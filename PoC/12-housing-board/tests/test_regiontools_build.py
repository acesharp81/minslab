import unittest
from datetime import date

from helpers import ROOT  # noqa: F401  (tools/ 를 sys.path 에 넣는다)

from regiontools import build_region as BR

TODAY = date(2026, 10, 4)


def box(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def poly_geom(ring):
    return {"type": "MultiPolygon", "coordinates": [[ring + [ring[0]]]]}


def bldg(ring, dong="", flr="20", name="", height="0"):
    return {"type": "Feature", "geometry": poly_geom(ring),
            "properties": {"bld_nm": name, "dong_nm": dong, "grnd_flr": flr, "ugrnd_flr": "1", "height": height,
                           "usability": "", "useapr_day": ""}}


def permit(pk, apprv, units=0, bun="0000", ji="0000", gb="2", block=" ", name=" ", stcns=" ", insp=" ",
           main=0, purps="공동주택", bjdong="10600"):
    return {"mgmHsrgstPk": pk, "apprvDay": apprv, "totHhldCnt": units, "bun": bun, "ji": ji, "platGbCd": gb,
            "block": block, "bldNm": name, "splotNm": " ", "stcnsDay": stcns, "useInsptDay": insp,
            "mainBldCnt": main, "purpsCdNm": purps, "sigunguCd": "12330", "bjdongCd": bjdong}


def dong_row(pk, dong, floors, pub=0, cvl_lot=0, cvl_rent=0, main=True):
    return {"mgmHsrgstPk": pk, "dongNm": dong, "mainAtchGbCd": "0" if main else "1", "ugrndFlrCnt": floors,
            "grndFlrCnt": 1, "heit": 0, "hhldCntPeplRent": pub, "hhldCntPubRentTot": 0, "hhldCntPubLotou": 0,
            "hhldCntEmplRent": 0, "hhldCntLaborWlfar": 0, "hhldCntCvlRent": cvl_rent, "hhldCntCvlLotou": cvl_lot}


class Names(unittest.TestCase):
    def test_normalize_block(self):
        cases = {"A-1BL": "A-1", "A-1블록": "A-1", "광주선운2 A-1블록": "A-1", "광주선운2지구 A-3BL": "A-3",
                 "에이-2블록": "A-2", "B-1BL블럭": "B-1", "광주선운2 B-1BL 공공지원 민간임대주택사업 신축공사": "B-1",
                 "a-2bl": "A-2", "A1": "A-1", "LH아파트": None, " ": None, "8-1,2BL": None, "3BL": None,
                 "빛가람LH3단지": None, "LH빛가람1단지": None, None: None}
        for text, want in cases.items():
            self.assertEqual(BR.normalize_block(text), want, text)

    def test_short_label(self):
        strip = ["광주전남공동혁신도시", "광주 전남혁신도시", "빛가람", "선운2지구"]
        cases = {"LH빛가람1단지": "LH1단지", "빛가람LH3단지": "LH3단지", "빛가람우미린": "우미린",
                 "광주 전남혁신도시 영무예다음": "영무예다음",
                 "광주전남공동혁신도시 빛가람 대방엘리움 로얄카운티 1차": "대방엘리움 1차",
                 "이노시티애시앙1단지": "이노시티애시앙1", "빛가람 이지더원 아파트": "이지더원",
                 "광주전남공동혁신도시 C7블럭 부영아파트": "C7블럭 부영", "선운2지구 예다음 퍼스티지": "예다음 퍼스티지"}
        for name, want in cases.items():
            got = BR.short_label(name, strip)
            self.assertEqual(got, want, name)
            self.assertLessEqual(len(got), 8)

    def test_kind_from_text(self):
        self.assertEqual(BR.kind_from_text("광주선운2 A-1,3블록 신혼희망타운 공공분양 선착순계약"), "신혼희망타운")
        self.assertEqual(BR.kind_from_text("행복주택 예비입주자"), "행복주택")
        self.assertIsNone(BR.kind_from_text("잔여세대 일반매각 공고 아파트"))

    def test_dong_number(self):
        self.assertEqual(BR.dong_number("105동"), "105")
        self.assertEqual(BR.dong_number("108동(어린이집)"), "108")
        self.assertIsNone(BR.dong_number(""))
        self.assertIsNone(BR.dong_number("관리동"))


class Pnu(unittest.TestCase):
    def test_make_pnu(self):
        self.assertEqual(BR.make_pnu("12330", "10600", "0519", "0000", "0"), "1233010600105190000")
        self.assertEqual(BR.make_pnu("12330", "10600", "12", "5", "0"), "1233010600100120005")
        self.assertEqual(BR.make_pnu("12330", "10600", "0012", "0005", "1"), "1233010600200120005")
        self.assertIsNone(BR.make_pnu("12330", "10600", "0000", "0000", "0"))
        self.assertIsNone(BR.make_pnu("12330", "10600", "0519", "0000", "2"))
        self.assertIsNone(BR.make_pnu("12330", "10600", None, None, "0"))

    def test_ymd(self):
        self.assertEqual(BR.ymd("20220311"), "2022-03-11")
        self.assertIsNone(BR.ymd(" "))
        self.assertIsNone(BR.ymd("2022"))


class UnitsAndSponsor(unittest.TestCase):
    def test_unit_mix(self):
        rows = [dong_row("1", "101동", 20, cvl_lot=80), dong_row("1", "102동", 19, cvl_rent=70),
                dong_row("1", "근린생활시설", 1), dong_row("1", "관리동", 1, main=False)]
        mix = BR.unit_mix(rows)
        self.assertEqual((mix["public"], mix["private"], mix["other"], mix["residential_main"]), (0, 150, 0, 2))

    def test_classify_sponsor(self):
        priv = BR.unit_mix([dong_row("1", "101동", 20, cvl_lot=80)])
        pub = BR.unit_mix([dong_row("1", "101동", 20, pub=80)])
        empty = BR.unit_mix([])
        self.assertEqual(BR.classify_sponsor(["LH아파트"], pub)[:2], ("public", "LH"))
        self.assertEqual(BR.classify_sponsor(["빛가람엘에이치6단지"], empty)[:2], ("public", "LH"))
        self.assertEqual(BR.classify_sponsor(["예다음 퍼스티지"], priv)[0], "private")
        kind, name, reason = BR.classify_sponsor(["중흥 센트럴"], pub)
        self.assertIsNone(kind)
        self.assertIn("공공", reason)
        self.assertIsNone(BR.classify_sponsor(["무명"], empty)[0])


class PermitEvents(unittest.TestCase):
    def test_basic_record(self):
        ev = BR.permit_events(permit("1064100004987", "20220311", units=828), TODAY)
        self.assertEqual(ev, [{"type": "permit_approved", "date": "2022-03-11", "value": 828,
                               "source": "hub-housing-permit", "ref": "1064100004987"}])

    def test_zero_units_is_unknown(self):
        ev = BR.permit_events(permit("9", "20250704", stcns="20250731", insp="20250812"), TODAY)
        self.assertEqual([(e["type"], e["value"] if "value" in e else "-") for e in ev],
                         [("permit_approved", None), ("construction_start", "-"), ("completion_inspection", "-")])
        self.assertFalse(any(e.get("suspect") for e in ev))

    def test_order_and_future_are_suspect(self):
        ev = BR.permit_events(permit("8", "20251107", stcns="20261223", insp="20260120"), TODAY)
        flags = {e["type"]: e.get("suspect", False) for e in ev}
        self.assertEqual(flags, {"permit_approved": False, "construction_start": True, "completion_inspection": True})


class Dongs(unittest.TestCase):
    def test_dongs_from_buildings(self):
        b = [bldg(box(0, 0, 1, 1), "101동", "25"), bldg(box(1, 0, 2, 1), "101동", "25", height="72.5"),
             bldg(box(3, 0, 4, 1), "102동", "4"), bldg(box(5, 0, 6, 1), "", "8")]
        dongs = BR.dongs_from_buildings(b)
        # 동 이름이 붙은 건물이 있으면 이름 없는 건물(경로당 등 부대시설일 수 있음)은 동으로 세지 않는다
        self.assertEqual([d["no"] for d in dongs], ["101"])
        self.assertEqual(len(dongs[0]["poly"]), 2)
        self.assertEqual(dongs[0]["heightM"], 72.5)

    def test_unnamed_buildings_are_numbered_only_when_no_dong_has_a_name(self):
        b = [bldg(box(0, 0, 1, 1), "", "20"), bldg(box(2, 0, 3, 1), "", "18", height="52.5")]
        dongs = BR.dongs_from_buildings(b)
        self.assertEqual([d["no"] for d in dongs], ["1", "2"])
        self.assertEqual([d["floorsAbove"] for d in dongs], [20, 18])
        self.assertEqual(dongs[1]["heightM"], 52.5)

    def test_floor_profile_match(self):
        rows = [dong_row("A2", f"10{i}동", fl, pub=100) for i, fl in enumerate([20, 21, 21, 14, 8, 14], start=1)]
        rows.append(dong_row("A2", "근린생활시설", 1, main=False))
        prof = BR.permit_floor_profile(rows)
        cands = {"b4": BR.building_floor_profile([bldg(box(0, 0, 1, 1), f"20{i}동", str(fl))
                                                  for i, fl in enumerate([20, 21, 21, 14, 8, 14], start=1)]),
                 "b3": {}}
        self.assertEqual(BR.match_floor_profile(prof, cands), "b4")
        cands["b5"] = dict(cands["b4"])
        self.assertIsNone(BR.match_floor_profile(prof, cands))  # 둘 이상이면 연결하지 않음
        self.assertIsNone(BR.match_floor_profile({1: 20, 2: 21}, {"b4": {1: 20, 2: 21}}))  # 3개동 미만


class Plan(unittest.TestCase):
    """블록 5개짜리 가상 지구: 마이홈 PNU, 이름(LH), 층수 대조, 민간 지번, 근거 없음을 한 번에 시험한다."""

    def setUp(self):
        self.cfg = BR.RegionConfig(
            slug="test-region", name="테스트구", title="주택파동 · 테스트구", description="", zoom=15, pitch=52,
            codes=[], zone_id="z1", zone_name="테스트 공공주택지구", zone_type="공공주택지구",
            zone_match=lambda zn: "테스트" in zn, search_bbox=(0, 0, 10, 10), sigungu="12330",
            bjdongs=["10600"], jibun_slug={"10600": "unsu"}, myhome_filter=lambda it: True,
            name_reject=r"선운(?!2)", label_strip=["테스트지구"], zone_short="테스트2")
        self.blocks = [{"type": "Feature", "geometry": poly_geom(box(i * 10, 0, i * 10 + 8, 8)),
                        "properties": {"blocktype": "공동주택", "zonename": "테스트"}} for i in range(5)]
        # b0: 마이홈 A-1, b1: LH A-2(층수 대조), b2: 민간 지번, b3: 건물 없음(B-1 후보), b4: 공공 호수 민간(제외)
        self.buildings = ([bldg(box(1 + k, 1, 1.5 + k, 1.5), f"10{k}동", "25") for k in range(1, 4)]
                          + [bldg(box(11 + k, 1, 11.5 + k, 1.5), f"20{k}동", str(fl)) for k, fl in [(1, 20), (2, 21), (3, 14)]]
                          + [bldg(box(21 + k, 1, 21.5 + k, 1.5), f"10{k}동", "19") for k in range(1, 3)]
                          + [bldg(box(41, 1, 41.5, 1.5), "101동", "15")])
        self.parcels = {"1233010600105190000": poly_geom(box(0.5, 0.5, 7.5, 7.5)),
                        "1233010600105460000": poly_geom(box(20.5, 0.5, 27.5, 7.5)),
                        "1233010600105500000": poly_geom(box(40.5, 0.5, 47.5, 7.5))}
        self.myhome = [{"hsmpNm": "테스트2 A-1블록", "pblancNm": "테스트2 A-1블록 신혼희망타운 공공분양", "suplyInsttNm": "LH",
                        "pnu": "1233010600105190000", "sumSuplyCo": 39, "rcritPblancDe": "20260706", "houseTyNm": "아파트",
                        "url": "https://apply.lh.or.kr/x?panId=0000061131&a=1", "pblancId": "1440"}]
        self.permits = [
            permit("P1", "20220311", units=828, block="A-1BL", name="테스트2지구 A-1BL", main=7),
            permit("P1b", "20250704", bun="0519", gb="0", stcns="20250731", insp="20250812"),
            permit("P2", "20211229", units=300, block="A-2BL", name="LH아파트", main=3),
            permit("P2b", "20260804", block="에이-2블록"),
            permit("P3", "20230613", units=154, bun="0546", gb="0", name="테스트2지구 예다음", stcns="20230908",
                   insp="20260706", main=3),
            permit("P4", "20231221", units=494, block="B-1BL블럭", name="테스트2 B-1BL 민간임대", main=6),
            permit("P5", "20140214", units=993, bun="0550", gb="0", name="중흥 센트럴", insp="20160920", main=17),
            permit("P6", "20141230", units=1022, block="3BL", name="광주선운지구 3BL 주택건설사업", main=12),
        ]
        self.dong_rows = (
            [dong_row("P1", f"10{k}동", 25, pub=140) for k in range(1, 4)] + [dong_row("P1", "근린생활시설", 1)]
            + [dong_row("P2", f"10{k}동", fl, pub=100) for k, fl in [(1, 20), (2, 21), (3, 14)]]
            + [dong_row("P3", f"10{k}동", 19, cvl_lot=77) for k in range(1, 3)]
            + [dong_row("P4", f"10{k}동", 25, cvl_rent=98) for k in range(1, 7)]
            + [dong_row("P5", "101동", 15, pub=993)])

    def plan(self):
        return BR.plan_projects(self.cfg, apt_blocks=self.blocks, buildings=self.buildings, myhome=self.myhome,
                                parcels=self.parcels, permits=self.permits, dong_rows=self.dong_rows, today=TODAY)

    def test_pnus_to_fetch(self):
        self.assertEqual(BR.pnus_to_fetch(self.myhome, self.permits),
                         {"1233010600105190000", "1233010600105460000", "1233010600105500000"})

    def test_projects(self):
        res = self.plan()
        by_id = {p["id"]: p for p in res["projects"]}
        self.assertEqual(sorted(by_id), ["z1-A1", "z1-A2", "z1-unsu-546"])
        a1 = by_id["z1-A1"]
        self.assertEqual((a1["label"], a1["sponsor"], a1["sponsorClass"], a1["kind"], a1["status"], a1["units"]),
                         ("A-1", {"name": "LH", "type": "public"}, "public", "신혼희망타운", "입주 단계", 828))
        self.assertEqual(a1["name"], "테스트2 A-1블록 신혼희망타운")
        self.assertEqual(a1["dongCount"], 3)
        self.assertEqual([d["no"] for d in a1["dongs"]], ["101", "102", "103"])
        self.assertEqual(a1["outline"]["tier"], "official")
        types = [(e["type"], e["date"]) for e in a1["events"]]
        self.assertIn(("notice", "2026-07-06"), types)
        self.assertIn(("completion_inspection", "2025-08-12"), types)
        self.assertIn(("structure_observed", "2026-10-04"), types)
        self.assertEqual(set(a1["sources"]), {"myhome-notice", "hub-housing-permit", "vworld-lhblpn",
                                              "vworld-bldginfo", "vworld-cadastral"})
        a2 = by_id["z1-A2"]
        self.assertEqual((a2["sponsor"]["name"], a2["status"], a2["units"], a2["dongCount"], a2["kind"]),
                         ("LH", "입주 단계", 300, 3, "공동주택"))
        self.assertIn("층수", a2["note"])
        self.assertEqual(sum(1 for e in a2["events"] if e["type"] == "permit_approved"), 2)
        priv = by_id["z1-unsu-546"]
        self.assertEqual((priv["sponsor"]["type"], priv["sponsorClass"], priv["status"], priv["units"]),
                         ("private", "private_on_public_land", "입주 단계", 154))
        self.assertEqual(priv["note"], "시행자 미확인, 인허가의 세대 유형이 민간분양·민간임대")
        self.assertEqual(priv["label"], "예다음")

    def test_exclusions_and_other_blocks(self):
        res = self.plan()
        reasons = {x["name"]: x["reason"] for x in res["exclusions"]}
        self.assertTrue(any("B-1" in n for n in reasons))
        self.assertTrue(any("중흥" in n for n in reasons))
        self.assertFalse(any("3BL" in n for n in reasons))  # 다른 지구 이름은 후보가 아님
        self.assertEqual(len(res["other_blocks"]), 2)  # b3(B-1 후보), b4(제외 단지)


class FakeBuildingClient:
    """fetch_buildings 가 부르는 두 가지만 흉내 낸다."""
    def __init__(self, n):
        self.n = n

    def vworld_features(self, layer, bbox=None):
        if layer == "LT_C_BLDGINFO":
            # 면적이 서로 다른 건물 n 개(전부 10 m² 이상)
            return [bldg(box(i * 0.0002, 0, i * 0.0002 + 0.0001 + i * 1e-8, 0.0001), dong=f"{i}동", flr="5") for i in range(self.n)]
        return []


class BuildingCap(unittest.TestCase):
    def cfg(self, **kw):
        base = dict(slug="t", name="t", title="t", description="", zoom=15, pitch=52, codes=[], zone_id="z", zone_name="z",
                    zone_type="공공주택지구", zone_match=lambda zn: True, search_bbox=(0, 0, 1, 1), sigungu="1",
                    bjdongs=[], jibun_slug={}, myhome_filter=lambda it: True, name_reject=None, label_strip=[], zone_short="z")
        base.update(kw)
        return BR.RegionConfig(**base)

    def test_default_cap_is_not_the_old_5000(self):
        self.assertGreaterEqual(self.cfg().max_buildings, 20000)

    def test_nothing_is_dropped_below_the_cap(self):
        res = BR.fetch_buildings(self.cfg(max_buildings=100), FakeBuildingClient(60), (0, 0, 0.02, 0.01), "20261004")
        self.assertEqual(len(res["features"]), 60)
        self.assertNotIn("capped_dropped", res["meta"])

    def test_cap_is_recorded_in_meta(self):
        res = BR.fetch_buildings(self.cfg(max_buildings=50), FakeBuildingClient(60), (0, 0, 0.02, 0.01), "20261004")
        self.assertEqual(len(res["features"]), 50)
        self.assertEqual(res["meta"]["capped_dropped"], 10)


if __name__ == "__main__":
    unittest.main()
