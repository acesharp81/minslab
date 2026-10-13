#!/usr/bin/env python3
"""API로 지역 지도 번들(region·projects·buildings·context)을 만든다.

  python3 tools/regiontools/build_region.py gwangju-gwangsan|jeonnam-naju [--cache-dir DIR] [--out DIR]

키(.env.local의 DATA_GO_KR_KEY·VWORLD_KEY 또는 VWORLD_DEV_KEY·VWORLD_DOMAIN)가 있을 때만 동작한다. 키·요청 URL은 출력하지 않는다.
--cache-dir(또는 환경변수 REGIONBUILD_CACHE)를 주면 응답을 그 폴더에 캐시한다. 저장소 밖 폴더를 쓴다.

단지를 올리는 근거(정의서 4·5·9절):
  - 마이홈 공고의 PNU → 연속지적 필지 중심 → 그 점을 품은 공동주택 블록(LT_C_LHBLPN). 공급기관이 시행자.
  - 건축HUB 주택인허가: 지번 레코드는 지번 → PNU → 필지 중심 → 블록. 블록 레코드(지번 0000-0000)는
    블록 이름 정규화로 같은 이름의 마이홈 단지에 붙이고, 없으면 동 개요의 동별 지상층수가 블록 안 건물과
    정확히 같을 때만(3개동 이상, 후보 블록 하나) 그 블록에 붙인다.
  - 시행자: 마이홈 공급기관 → 공공. 인허가뿐이면 이름에 LH가 있을 때 LH, 세대 유형이 민간뿐일 때만 민간.
    그 밖(공공 호수가 섞임, 세대 유형 정보 없음, 총세대 0)은 지도에서 빼고 보고한다.
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from regiontools import api, bundle, existence, geo  # noqa: E402
from regiontools import buildings as B  # noqa: E402
from regiontools.status import compute_status, flag_future  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
APT_TYPES = {"공동주택", "아파트", "주상복합"}
PUBLIC_LAND_TYPES = {"택지개발", "공공주택지구", "혁신도시", "신도시"}
SRC_MYHOME, SRC_HUB, SRC_BLD, SRC_BLOCK, SRC_CAD = (
    "myhome-notice", "hub-housing-permit", "vworld-bldginfo", "vworld-lhblpn", "vworld-cadastral")
PRIVATE_NOTE = "시행자 미확인, 인허가의 세대 유형이 민간분양·민간임대"
PRIVATE_SPONSOR = "민간(시행자 미확인)"
FLOOR_MATCH_NOTE = "블록 위치는 인허가 동별 지상층수와 건물 자료를 대조해 연결"
HOW_BLOCK = "V-World 공식 블록(LT_C_LHBLPN)"
HOW_PARCEL = "V-World 연속지적도 필지(LP_PA_CBND_BUBUN)"
KIND_WORDS = ["신혼희망타운", "행복주택", "통합공공임대", "국민임대", "영구임대", "공공지원민간임대",
              "공공분양", "공공임대", "민간임대", "민간분양"]
GENERIC_WORDS = ["신축공사", "주택건설사업", "건설공사"]
PUBLIC_FIELDS = ("hhldCntPeplRent", "hhldCntPubRentTot", "hhldCntPubLotou")
PRIVATE_FIELDS = ("hhldCntCvlRent", "hhldCntCvlLotou")
OTHER_FIELDS = ("hhldCntEmplRent", "hhldCntLaborWlfar")
OSM_SOURCE = "© OpenStreetMap contributors (ODbL)"


# ------------------------------------------------------------------ 지역 설정
@dataclass
class RegionConfig:
    slug: str
    name: str
    title: str
    description: str
    zoom: float
    pitch: float
    codes: list
    zone_id: str
    zone_name: str
    zone_type: str
    zone_match: Callable[[str], bool]
    search_bbox: tuple
    sigungu: str
    bjdongs: list
    jibun_slug: dict
    myhome_filter: Callable[[dict], bool]
    name_reject: str | None
    label_strip: list
    zone_short: str
    zone_centroid_bbox: tuple | None = None
    max_buildings: int = 20000   # 보통은 걸리지 않는 안전 상한. 넘으면 큰 건물부터 남기고 meta.capped_dropped 에 뺀 수를 적는다
    min_building_m2: float = 10.0
    context_radius_m: int = 3000


def _sources(today: str) -> list:
    data_go = "국토교통부"
    vw = "국토교통부 V-World"
    return [
        {"id": SRC_MYHOME, "label": "마이홈포털 공공주택 모집공고", "publisher": data_go,
         "url": "https://www.data.go.kr/data/15108420/openapi.do", "asOf": today, "redistributable": "unknown"},
        {"id": SRC_HUB, "label": "건축HUB 주택인허가", "publisher": data_go,
         "url": "https://www.data.go.kr/data/15136560/openapi.do", "asOf": today, "redistributable": "unknown"},
        {"id": SRC_BLD, "label": "V-World 건물 데이터", "publisher": vw, "url": "https://www.vworld.kr",
         "asOf": today, "redistributable": "unknown"},
        {"id": SRC_BLOCK, "label": "V-World 블록 레이어", "publisher": vw, "url": "https://www.vworld.kr",
         "asOf": today, "redistributable": "unknown"},
        {"id": SRC_CAD, "label": "V-World 연속지적도", "publisher": vw, "url": "https://www.vworld.kr",
         "asOf": today, "redistributable": "unknown"},
    ]


REGIONS = {
    "gwangju-gwangsan": RegionConfig(
        slug="gwangju-gwangsan", name="광주 광산구", title="주택파동 · 광주 광산구",
        description="광주선운2 공공주택지구의 공공주택과 공공택지 위 민간 단지 공급 현황을 3차원 지도로 보여 줍니다.",
        zoom=15, pitch=52,
        codes=[{"code": "12330", "type": "sigungu", "name": "광산구"},
               {"code": "12330106", "type": "bjdong", "name": "운수동"},
               {"code": "12330107", "type": "bjdong", "name": "선암동"},
               {"code": "12330108", "type": "bjdong", "name": "소촌동"}],
        zone_id="sunwoon2", zone_name="광주선운2 공공주택지구", zone_type="공공주택지구",
        zone_match=lambda zn: "광주선운2" in zn,
        search_bbox=(126.770, 35.135, 126.800, 35.162),
        sigungu="12330", bjdongs=["10600", "10700", "10800"],
        jibun_slug={"10600": "unsu", "10700": "seonam", "10800": "sochon"},
        myhome_filter=lambda it: (it.get("signguNm") or "").strip() == "광산구",
        name_reject=r"선운(?!2)", label_strip=["광주선운2지구", "선운2지구"], zone_short="광주선운2"),
    "jeonnam-naju": RegionConfig(
        slug="jeonnam-naju", name="전남 나주시", title="주택파동 · 전남 나주시",
        description="광주·전남 공동혁신도시(빛가람)의 공공주택과 공공택지 위 민간 단지를 3차원 지도로 보여 줍니다.",
        zoom=14.5, pitch=52,
        codes=[{"code": "12170", "type": "sigungu", "name": "나주시"},
               {"code": "12170134", "type": "bjdong", "name": "빛가람동"}],
        zone_id="bitgaram", zone_name="광주 전남 공동혁신도시(빛가람)", zone_type="혁신도시",
        zone_match=lambda zn: zn.strip() == "광주 전남 공동혁신도시 개발사업",
        zone_centroid_bbox=(126.76, 35.00, 126.82, 35.05),
        search_bbox=(126.74, 34.99, 126.84, 35.06),
        sigungu="12170", bjdongs=["13400"], jibun_slug={"13400": ""},
        myhome_filter=lambda it: ((it.get("signguNm") or "").strip() == "나주시"
                                  or "빛가람" in (it.get("hsmpNm") or "") or "빛가람" in (it.get("pblancNm") or "")),
        name_reject=None,
        label_strip=["광주전남공동혁신도시", "광주·전남 공동혁신도시", "광주전남 공동혁신도시", "광주 전남 공동혁신도시",
                     "광주 전남혁신도시", "광주전남혁신", "혁신도시", "빛가람동"],
        zone_short="빛가람"),
}


# ------------------------------------------------------------------ 이름·코드 정규화(순수 함수)
_KO_LETTER = {"에이": "A", "비": "B", "씨": "C", "디": "D"}
_BLOCK_RE = re.compile(r"(?<![A-Za-z])([A-Za-z])\s*-?\s*(\d{1,2})(?=\s*(?:BL|블록|블럭)|\s|,|$)", re.IGNORECASE)


def normalize_block(text) -> str | None:
    """블록 이름 → 'A-1' 꼴. 'A-1BL'·'A-1블록'·'광주선운2 A-1블록'·'에이-2블록'·'B-1BL블럭' 모두 같은 값."""
    if not text:
        return None
    s = str(text).strip()
    if not s:
        return None
    s = re.sub(r"(?<![가-힣])(에이|비|씨|디)(?=\s*-?\s*\d)", lambda m: _KO_LETTER[m.group(1)], s)
    m = _BLOCK_RE.search(s)
    return f"{m.group(1).upper()}-{int(m.group(2))}" if m else None


def make_pnu(sigungu, bjdong, bun, ji, plat_gb="0") -> str | None:
    """시군구5+법정동5+대지구분1(대지 1, 산 2)+본번4+부번4. 블록(platGbCd 2)·본번 0은 None."""
    land = {"0": "1", "1": "2"}.get(str(plat_gb if plat_gb is not None else "0").strip())
    if land is None:
        return None
    try:
        b = int(str(bun).strip())
        j = int(str(ji if ji is not None else 0).strip() or 0)
    except ValueError:
        return None
    if b <= 0:
        return None
    return f"{str(sigungu).strip()}{str(bjdong).strip()}{land}{b:04d}{j:04d}"


def ymd(s) -> str | None:
    s = str(s or "").strip()
    if len(s) != 8 or not s.isdigit():
        return None
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:])).isoformat()
    except ValueError:
        return None


def short_label(name, strip_words=(), maxlen: int = 8) -> str:
    """지도용 짧은 이름. 지구·지역 접두어와 '아파트'·'신축공사'를 빼고 8자 이내로 줄인다(끝의 'N차'·'N단지'는 살림)."""
    s = str(name or "")
    for w in sorted(set(strip_words) | set(GENERIC_WORDS), key=len, reverse=True):
        if w:
            s = s.replace(w, "")
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s*아파트$", "", s).strip()
    if len(s) <= maxlen:
        return s
    m = re.search(r"(\s*)(\d+)\s*(차|단지)$", s)
    if m:
        sep = " " if m.group(1) else ""
        base = s[:m.start()].strip()
        tokens = base.split() or [base]
        full = m.group(2) + m.group(3)
        short = m.group(2) + ("차" if m.group(3) == "차" else "")
        for cand in (base.replace(" ", "") + sep + full, tokens[0] + sep + full, tokens[0] + sep + short):
            if len(cand) <= maxlen:
                return cand
        return tokens[0][:max(maxlen - len(sep) - len(short), 1)] + sep + short
    first = s.split()[0]
    return first if len(first) <= maxlen else s.replace(" ", "")[:maxlen]


def kind_from_text(text) -> str | None:
    t = str(text or "")
    for w in KIND_WORDS:
        if w in t:
            return w
    return None


def dong_number(s) -> str | None:
    m = re.match(r"^\s*(\d{1,4})\s*(?:동|\(|$)", str(s or ""))
    return m.group(1) if m else None


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _row_units(r) -> float:
    return sum(_num(r.get(f)) for f in PUBLIC_FIELDS + PRIVATE_FIELDS + OTHER_FIELDS)


def unit_mix(rows: list[dict]) -> dict:
    """동 개요 행들의 세대 유형 합계. residential_main = 세대가 있는 주건축물 수(주동 수)."""
    return {
        "public": int(sum(_num(r.get(f)) for r in rows for f in PUBLIC_FIELDS)),
        "private": int(sum(_num(r.get(f)) for r in rows for f in PRIVATE_FIELDS)),
        "other": int(sum(_num(r.get(f)) for r in rows for f in OTHER_FIELDS)),
        "residential_main": sum(1 for r in rows if str(r.get("mainAtchGbCd")).strip() == "0" and _row_units(r) > 0),
    }


def classify_sponsor(names, mix: dict):
    """(유형, 시행자 이름, 제외 사유). 인허가뿐인 단지용. 세대 유형 '공공' 호수만으로 공공이라 하지 않는다(정의서 5절·함정 5)."""
    text = " ".join(str(n) for n in names if n)
    if re.search(r"LH|엘에이치|한국토지주택공사", text):
        return "public", "LH", None
    if mix["private"] > 0 and mix["public"] == 0 and mix["other"] == 0:
        return "private", PRIVATE_SPONSOR, None
    if mix["public"] > 0:
        return None, None, (f"인허가 세대 유형에 공공 호수 {mix['public']}세대가 있으나 시행자를 직접 말하는 자료가 없음"
                            "(정의서 5절·함정 5)")
    if mix["other"] > 0:
        return None, None, "인허가 세대 유형이 사원임대·근로자복지뿐이라 시행자 판단 불가"
    return None, None, "인허가 동 개요에 세대 유형 정보가 없어 시행자 판단 불가"


def permit_events(rec: dict, today: date) -> list[dict]:
    """인허가 기본개요 레코드 하나 → 사건. 0 세대는 미상(None). 레코드 안 날짜 순서 모순·미래 실제 날짜는 suspect."""
    ref = str(rec.get("mgmHsrgstPk") or "").strip() or None
    apprv, stcns, insp = ymd(rec.get("apprvDay")), ymd(rec.get("stcnsDay")), ymd(rec.get("useInsptDay"))
    evs = []
    if apprv:
        evs.append({"type": "permit_approved", "date": apprv, "value": B.to_pos_int(rec.get("totHhldCnt")),
                    "source": SRC_HUB, "ref": ref})
    if stcns:
        evs.append({"type": "construction_start", "date": stcns, "source": SRC_HUB, "ref": ref})
    if insp:
        evs.append({"type": "completion_inspection", "date": insp, "source": SRC_HUB, "ref": ref})
    bad = set()
    if apprv and stcns and apprv > stcns:
        bad |= {"permit_approved", "construction_start"}
    if stcns and insp and stcns > insp:
        bad |= {"construction_start", "completion_inspection"}
    if apprv and insp and apprv > insp:
        bad |= {"permit_approved", "completion_inspection"}
    out = []
    for e in flag_future(evs, today):
        if e["type"] in bad:
            e["suspect"] = True
        if not e.get("suspect"):
            e.pop("suspect", None)
        out.append(e)
    return out


# ------------------------------------------------------------------ 동·층수 대조
def dongs_from_buildings(features: list[dict], min_floors: int = 5) -> list[dict]:
    """블록 안 건물 중 지상 min_floors층 이상 → 동. 같은 동 번호의 조각은 링 여러 개로 합친다."""
    named: dict[str, dict] = {}
    unnamed: list[dict] = []
    for f in features:
        p = f.get("properties") or {}
        fl = B.to_pos_int(p.get("grnd_flr"))
        if not fl or fl < min_floors:
            continue
        rings = [r for r in (geo.clean_ring(r) for r in geo.outer_rings(f.get("geometry"))) if r]
        if not rings:
            continue
        no = dong_number(p.get("dong_nm"))
        if no:
            d = named.setdefault(no, {"no": no, "tier": "building", "floorsAbove": 0, "poly": [], "_h": None})
        else:
            d = {"no": None, "tier": "building", "floorsAbove": 0, "poly": [], "_h": None}
            unnamed.append(d)
        d["floorsAbove"] = max(d["floorsAbove"], fl)
        d["poly"] += rings
        h = B.to_pos_float(p.get("height"))
        if h:
            d["_h"] = max(d["_h"] or 0.0, h)
    out = sorted(named.values(), key=lambda d: int(d["no"]))
    if out:
        unnamed = []   # 동 이름이 붙은 건물이 있으면 이름 없는 건물은 부대시설일 수 있어 동으로 세지 않는다
    for i, d in enumerate(unnamed, start=1):
        d["no"] = str(i)
    result = []
    for d in out + unnamed:
        h = d.pop("_h")
        if h:
            d["heightM"] = round(h, 2)
        result.append(d)
    return result


def permit_floor_profile(rows: list[dict]) -> dict:
    """동 개요의 주동(세대 있는 주건축물) → {동 번호 끝 두 자리: 지상층수}. 지상층수는 ugrndFlrCnt(함정 1)."""
    prof: dict[int, int] = {}
    for r in rows:
        if str(r.get("mainAtchGbCd")).strip() != "0" or _row_units(r) <= 0:
            continue
        no, fl = dong_number(r.get("dongNm")), B.to_pos_int(r.get("ugrndFlrCnt"))
        if not no or not fl:
            continue
        k = int(no) % 100
        if prof.get(k, fl) != fl:
            return {}
        prof[k] = fl
    return prof


def building_floor_profile(features: list[dict], min_floors: int = 5) -> dict:
    prof: dict[int, int] = {}
    for f in features:
        p = f.get("properties") or {}
        fl, no = B.to_pos_int(p.get("grnd_flr")), dong_number(p.get("dong_nm"))
        if not fl or fl < min_floors or not no:
            continue
        k = int(no) % 100
        if prof.get(k, fl) != fl:
            return {}
        prof[k] = fl
    return prof


def match_floor_profile(prof: dict, candidates: dict, min_dongs: int = 3):
    if len(prof) < min_dongs:
        return None
    hits = [k for k, c in candidates.items() if c == prof]
    return hits[0] if len(hits) == 1 else None


# ------------------------------------------------------------------ 연결·조립
def is_block_record(rec: dict) -> bool:
    return str(rec.get("platGbCd") or "").strip() == "2" or not B.to_pos_int(rec.get("bun"))


def record_pnu(rec: dict) -> str | None:
    return make_pnu(rec.get("sigunguCd") or "", rec.get("bjdongCd") or "", rec.get("bun"), rec.get("ji"),
                    rec.get("platGbCd"))


def is_candidate_record(rec: dict) -> bool:
    return bool(B.to_pos_int(rec.get("totHhldCnt"))) and "공동주택" in str(rec.get("purpsCdNm") or "")


def _named(rec: dict) -> bool:
    return bool(str(rec.get("bldNm") or "").strip()) and bool(B.to_pos_int(rec.get("mainBldCnt")))


def _valid_pnu(p) -> bool:
    return bool(re.fullmatch(r"\d{19}", str(p or "").strip()))


def pnus_to_fetch(myhome: list[dict], permits: list[dict]) -> set:
    """필지를 조회할 PNU: 마이홈 공고 PNU + 지번 인허가 중 세대수 있는 공동주택 + 이름·주동이 있는 레코드."""
    out = {str(it["pnu"]).strip() for it in myhome if _valid_pnu(it.get("pnu"))}
    for r in permits:
        if is_block_record(r):
            continue
        if is_candidate_record(r) or _named(r):
            p = record_pnu(r)
            if p:
                out.add(p)
    return out


def _apprv(rec) -> str:
    return ymd(rec.get("apprvDay")) or ""


def _largest_ring(geom) -> list | None:
    best, area = None, -1.0
    for r in geo.outer_rings(geom):
        a = geo.ring_area_m2(r)
        if a > area:
            best, area = r, a
    return geo.clean_ring(best) if best else None


def _safe_centroid(geom):
    try:
        return geo.geometry_centroid(geom)
    except (ValueError, ZeroDivisionError, TypeError):
        return None


def _best_record(recs: list[dict], rows_by_pk: dict):
    """동 개요의 주동이 가장 많은 레코드(같으면 최근 승인). 없으면 None."""
    scored = []
    for r in recs:
        rows = rows_by_pk.get(str(r.get("mgmHsrgstPk")), [])
        mix = unit_mix(rows)
        if mix["residential_main"] > 0 or mix["public"] + mix["private"] + mix["other"] > 0:
            scored.append((mix["residential_main"], _apprv(r), r, rows))
    if not scored:
        return None, []
    scored.sort(key=lambda x: (x[0], x[1]))
    return scored[-1][2], scored[-1][3]


def _project_id(cfg: RegionConfig, label: str | None, pnu: str | None) -> str:
    if label:
        return f"{cfg.zone_id}-{label.replace('-', '')}"
    bj, bun, ji = pnu[5:10], int(pnu[11:15]), int(pnu[15:19])
    jb = f"{bun}" + (f"-{ji}" if ji else "")
    return "-".join(x for x in (cfg.zone_id, cfg.jibun_slug.get(bj, bj), jb) if x)


def _supplier(name: str):
    n = (name or "").strip()
    if re.search(r"LH|한국토지주택공사", n):
        return "LH"
    if re.search(r"공사$|도시공사|개발공사|주택공사", n):
        return n
    return None


def _dedupe_events(evs: list[dict]) -> list[dict]:
    order = {t: i for i, t in enumerate(["notice", "permit_approved", "construction_start", "progress",
                                         "completion_inspection", "move_in", "structure_observed"])}
    seen, out = set(), []
    for e in evs:
        k = (e["type"], e["date"], e.get("ref"))
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return sorted(out, key=lambda e: (e["date"], order.get(e["type"], 9)))


def plan_projects(cfg: RegionConfig, *, apt_blocks, buildings, myhome, parcels, permits, dong_rows, today: date) -> dict:
    """네트워크 없이 단지 목록을 만든다. 반환: projects, other_blocks, exclusions, stats."""
    today_s = today.isoformat()
    stats: collections.Counter = collections.Counter()
    exclusions: list[dict] = []
    strip_words = list(cfg.label_strip) + [cfg.zone_short + "지구", cfg.zone_short]

    blocks = []
    for i, f in enumerate(apt_blocks):
        ring = _largest_ring(f.get("geometry"))
        if ring:
            blocks.append({"key": f"b{i}", "geom": f["geometry"], "ring": ring, "bbox": geo.bbox_of(ring)})
    by_key = {b["key"]: b for b in blocks}

    def block_at(pt):
        if pt is None:
            return None
        for b in blocks:
            x0, y0, x1, y1 = b["bbox"]
            if x0 <= pt[0] <= x1 and y0 <= pt[1] <= y1 and geo.point_in_geometry(pt, b["geom"]):
                return b["key"]
        return None

    bld_by_block: dict[str, list] = collections.defaultdict(list)
    for f in buildings:
        k = block_at(_safe_centroid(f.get("geometry")))
        if k:
            bld_by_block[k].append(f)

    rows_by_pk: dict[str, list] = collections.defaultdict(list)
    for r in dong_rows:
        rows_by_pk[str(r.get("mgmHsrgstPk"))].append(r)

    def parcel_block(pnu):
        g = parcels.get(pnu) if pnu else None
        return block_at(_safe_centroid(g)) if g else None

    # 1) 마이홈 → 블록
    my_by_block: dict[str, list] = collections.defaultdict(list)
    my_pnus: dict[str, set] = collections.defaultdict(set)
    for it in myhome:
        pnu = str(it.get("pnu") or "").strip()
        if not _valid_pnu(pnu) or not parcels.get(pnu):
            stats["myhome_no_parcel"] += 1
            continue
        k = parcel_block(pnu)
        if not k:
            stats["myhome_outside_zone_blocks"] += 1
            continue
        my_by_block[k].append(it)
        my_pnus[k].add(pnu)

    # 2) 인허가 → 이름 묶음(블록 레코드) / 지번 묶음
    name_groups: dict[str, list] = collections.defaultdict(list)
    pnu_groups: dict[str, dict] = {}
    for r in permits:
        if is_block_record(r):
            text = f"{r.get('bldNm') or ''} {r.get('splotNm') or ''}"
            if cfg.name_reject and re.search(cfg.name_reject, text):
                stats["permit_other_zone_name"] += 1
                continue
            lab = normalize_block(r.get("block")) or normalize_block(r.get("bldNm"))
            if lab:
                name_groups[lab].append(r)
            continue
        p = record_pnu(r)
        k = parcel_block(p)
        if k:
            pnu_groups.setdefault(p, {"block": k, "recs": []})["recs"].append(r)

    cands: list[dict] = []
    used_pnus: set = set()
    for k, items in my_by_block.items():
        items = sorted(items, key=lambda it: str(it.get("rcritPblancDe") or ""), reverse=True)
        labels = {normalize_block(it.get("hsmpNm")) for it in items} - {None}
        label = next(iter(labels)) if len(labels) == 1 else None
        recs = list(name_groups.pop(label, [])) if label else []
        for p in sorted(my_pnus[k]):
            if p in pnu_groups:
                recs += pnu_groups[p]["recs"]
                used_pnus.add(p)
        cands.append({"origin": "myhome", "block": k, "label": label, "items": items, "recs": recs,
                      "pnus": set(my_pnus[k])})

    occupied = set(my_by_block)
    for p, g in pnu_groups.items():
        if p not in used_pnus and any(is_candidate_record(r) or _named(r) for r in g["recs"]):
            occupied.add(g["block"])

    free_profiles = {b["key"]: building_floor_profile(bld_by_block[b["key"]]) for b in blocks if b["key"] not in occupied}
    for lab, recs in sorted(name_groups.items()):
        main = sorted((r for r in recs if is_candidate_record(r)), key=_apprv, reverse=True)
        if not main:
            stats["permit_name_group_without_units"] += 1
            continue
        hit = None
        for r in main:
            hit = match_floor_profile(permit_floor_profile(rows_by_pk.get(str(r.get("mgmHsrgstPk")), [])), free_profiles)
            if hit:
                break
        if not hit:
            nm = next((str(r.get("bldNm")).strip() for r in main if str(r.get("bldNm") or "").strip()), f"{lab}BL")
            exclusions.append({"name": nm, "label": lab, "units": B.to_pos_int(main[0].get("totHhldCnt")),
                               "reason": f"블록 윤곽에 연결할 근거 없음: 지번이 없는 블록 인허가(블록 {lab})이고 같은 이름의 "
                                         "마이홈 공고가 없으며, 동별 지상층수가 같은 건물이 지구 안 빈 블록에 없음"})
            continue
        free_profiles.pop(hit, None)
        occupied.add(hit)
        cands.append({"origin": "name", "block": hit, "label": lab, "items": [], "recs": recs, "pnus": set(),
                      "floor_match": True})

    for p, g in sorted(pnu_groups.items()):
        if p in used_pnus:
            continue
        recs = g["recs"]
        if any(is_candidate_record(r) for r in recs):
            cands.append({"origin": "pnu", "block": g["block"], "label": None, "items": [], "recs": recs, "pnus": {p}})
        elif any(_named(r) for r in recs):
            nm = next(str(r.get("bldNm")).strip() for r in recs if _named(r))
            exclusions.append({"name": nm, "pnu": p, "units": None,
                               "reason": "인허가 총세대가 0(미상)이고 세대수를 말하는 다른 자료가 없음"})

    # 3) 시행자 판정
    accepted: list[dict] = []
    for c in cands:
        if c["origin"] == "myhome":
            it = c["items"][0]
            sup = _supplier(it.get("suplyInsttNm"))
            if not sup:
                exclusions.append({"name": it.get("hsmpNm"), "units": None,
                                   "reason": f"마이홈 공급기관 '{it.get('suplyInsttNm')}'의 공공 여부를 판단할 수 없음"})
                continue
            c["sponsor"] = {"name": sup, "type": "public"}
        else:
            best, rows = _best_record(c["recs"], rows_by_pk)
            names = [r.get("bldNm") for r in c["recs"]]
            typ, sname, reason = classify_sponsor(names, unit_mix(rows))
            if not typ:
                nm = next((str(r.get("bldNm")).strip() for r in sorted(c["recs"], key=_apprv, reverse=True)
                           if is_candidate_record(r) and str(r.get("bldNm") or "").strip()), "이름 없음")
                exclusions.append({"name": nm, "pnu": next(iter(c["pnus"]), None), "label": c.get("label"),
                                   "units": _latest_units(c["recs"]), "reason": reason})
                continue
            if typ == "private" and cfg.zone_type not in PUBLIC_LAND_TYPES:
                exclusions.append({"name": names[0], "units": None, "reason": "공공택지가 아닌 지구의 민간 단지(범위 밖)"})
                continue
            c["sponsor"] = {"name": sname, "type": typ}
        accepted.append(c)

    # 4) 같은 블록에 단지가 둘 이상이면 필지 윤곽을 쓴다(필지가 없으면 제외)
    per_block = collections.Counter(c["block"] for c in accepted)
    final = []
    for c in accepted:
        c["shared"] = per_block[c["block"]] > 1
        if c["shared"] and not any(parcels.get(p) for p in c["pnus"]):
            exclusions.append({"name": c.get("label") or "이름 없음", "units": None,
                               "reason": "같은 블록에 다른 단지가 있고 필지 윤곽도 없어 윤곽을 정할 수 없음"})
            continue
        final.append(c)

    projects = [_assemble(cfg, c, by_key, bld_by_block, parcels, rows_by_pk, today, today_s, strip_words) for c in final]
    order = {s: i for i, s in enumerate(["분양중", "건설 단계", "준공 임박", "입주 단계", "계획"])}
    projects.sort(key=lambda p: (order[p["status"]], -(p.get("units") or 0), p["label"]))
    used_blocks = {c["block"] for c in final}
    other = [b["ring"] for b in blocks if b["key"] not in used_blocks]
    return {"projects": projects, "other_blocks": other, "exclusions": exclusions, "stats": stats}


def _latest_units(recs) -> int | None:
    vals = [(_apprv(r), B.to_pos_int(r.get("totHhldCnt"))) for r in recs]
    vals = [v for v in vals if v[1]]
    return max(vals)[1] if vals else None


def _assemble(cfg, c, by_key, bld_by_block, parcels, rows_by_pk, today, today_s, strip_words) -> dict:
    blk = by_key[c["block"]]
    if c["shared"]:
        pnu = sorted(p for p in c["pnus"] if parcels.get(p))[0]
        geom = parcels[pnu]
        ring = _largest_ring(geom)
        how, outline_src = HOW_PARCEL, SRC_CAD
        blds = [f for f in bld_by_block[c["block"]]
                if (lambda pt: pt is not None and geo.point_in_geometry(pt, geom))(_safe_centroid(f.get("geometry")))]
    else:
        ring, how, outline_src = blk["ring"], HOW_BLOCK, SRC_BLOCK
        blds = bld_by_block[c["block"]]
    dongs = dongs_from_buildings(blds)

    events = []
    for it in c["items"]:
        d = ymd(it.get("rcritPblancDe"))
        if d:
            events.append({"type": "notice", "date": d, "value": B.to_pos_int(it.get("sumSuplyCo")),
                           "source": SRC_MYHOME, "ref": api.pan_id(it.get("url")) or str(it.get("pblancId") or "") or None})
    for r in c["recs"]:
        events += permit_events(r, today)
    if dongs:
        events.append({"type": "structure_observed", "date": today_s, "value": len(dongs), "source": SRC_BLD})
    events = _dedupe_events(events)
    status = compute_status(events, today)

    permits_ok = sorted((e for e in events if e["type"] == "permit_approved" and e.get("value") and not e.get("suspect")),
                        key=lambda e: e["date"])
    units = permits_ok[-1]["value"] if permits_ok else None

    best, rows = _best_record(c["recs"], rows_by_pk)
    dong_count = unit_mix(rows)["residential_main"] if rows else 0
    if not dong_count:
        mains = sorted(((_apprv(r), B.to_pos_int(r.get("mainBldCnt"))) for r in c["recs"]
                        if B.to_pos_int(r.get("mainBldCnt"))), reverse=True)
        dong_count = mains[0][1] if mains else (len(dongs) or None)

    label = c.get("label")
    if c["origin"] == "myhome":
        it = c["items"][0]
        kind = kind_from_text(" ".join(str(x.get(k) or "") for x in c["items"]
                                       for k in ("pblancNm", "houseTyNm", "hsmpNm"))) or "공동주택"
        base = str(it.get("hsmpNm") or "").strip()
        name = base + (f" {kind}" if kind != "공동주택" and kind not in base else "")
        label = label or short_label(base, strip_words)
        pnu = sorted(c["pnus"])[0]
    else:
        kind = "공동주택"
        recs_by_date = sorted(c["recs"], key=_apprv, reverse=True)
        bld = next((str(r.get("bldNm")).strip() for r in recs_by_date
                    if is_candidate_record(r) and str(r.get("bldNm") or "").strip()), "")
        if label:
            name = bld if normalize_block(bld) == label else " ".join(x for x in (f"{cfg.zone_short} {label}블록", bld) if x)
        else:
            name = bld
            label = short_label(bld, strip_words)
        pnu = sorted(c["pnus"])[0] if c["pnus"] else None

    sponsor = c["sponsor"]
    notes = []
    if sponsor["type"] == "private":
        notes.append(PRIVATE_NOTE)
    if c.get("floor_match"):
        notes.append(FLOOR_MATCH_NOTE)
    srcs = []
    if c["items"]:
        srcs.append(SRC_MYHOME)
    if c["recs"]:
        srcs.append(SRC_HUB)
    srcs.append(outline_src)
    if c["pnus"]:
        srcs.append(SRC_CAD)
    if dongs:
        srcs.append(SRC_BLD)
    return {
        "id": _project_id(cfg, c.get("label"), pnu), "zoneId": cfg.zone_id, "label": label, "name": name,
        "sponsor": sponsor,
        "sponsorClass": "public" if sponsor["type"] in ("public", "joint") else "private_on_public_land",
        "kind": kind, "status": status, "units": units, "dongCount": dong_count,
        "outline": {"tier": "official", "poly": ring, "how": how},
        "dongs": dongs or None, "events": events, "sources": list(dict.fromkeys(srcs)),
        "note": " · ".join(notes) or None,
    }


# ------------------------------------------------------------------ 네트워크 단계
def fetch_zone(cfg: RegionConfig, client: api.Client) -> dict:
    feats = client.vworld_features("LT_C_LHBLPN", bbox=cfg.search_bbox)
    zone = [f for f in feats if cfg.zone_match(str((f.get("properties") or {}).get("zonename") or ""))]
    if cfg.zone_centroid_bbox:
        x0, y0, x1, y1 = cfg.zone_centroid_bbox
        zone = [f for f in zone if (lambda c: c and x0 <= c[0] <= x1 and y0 <= c[1] <= y1)(_safe_centroid(f["geometry"]))]
    if not zone:
        raise SystemExit(f"오류: 지구 피처를 찾지 못함({cfg.zone_name})")
    pts = [p for f in zone for p in geo.geometry_points(f["geometry"])]
    zb = geo.bbox_of(pts)
    sb = cfg.search_bbox
    touches = zb[0] <= sb[0] or zb[1] <= sb[1] or zb[2] >= sb[2] or zb[3] >= sb[3]
    hull = geo.simplify_ring(geo.convex_hull(pts), max_points=100)
    poly = geo.clean_ring(hull)
    center = geo.ring_centroid(poly)
    apt = [f for f in zone if str(f["properties"].get("blocktype") or "").strip() in APT_TYPES]
    apt.sort(key=lambda f: tuple(round(v, 6) for v in (_safe_centroid(f["geometry"]) or (0, 0))))
    return {"features": zone, "apt_blocks": apt, "poly": poly, "center": center, "bbox": zb,
            "touches_search_edge": touches, "blocktypes": collections.Counter(f["properties"].get("blocktype") for f in zone)}


def fetch_buildings(cfg: RegionConfig, client: api.Client, zone_bbox, basis: str) -> dict:
    bb = tuple(round(v, 6) for v in geo.expand_bbox(zone_bbox, 0.003))
    raw = client.vworld_features("LT_C_BLDGINFO", bbox=bb)
    emds = client.vworld_features("LT_C_ADEMD_INFO", bbox=bb)
    emd_polys = [(str((e.get("properties") or {}).get("full_nm") or "").split()[-1:] or [""], e.get("geometry")) for e in emds]
    factor = B.compute_factor([B.raw_values(f.get("properties") or {}) for f in raw])
    feats, tiny, broken = [], 0, 0
    for f in raw:
        g = f.get("geometry")
        area = geo.geometry_area_m2(g)
        if area < cfg.min_building_m2:
            tiny += 1
            continue
        c = _safe_centroid(g)
        d = next((nm[0] for nm, eg in emd_polys if c and eg and geo.point_in_geometry(c, eg)), None)
        feat = B.building_feature(g, B.building_props(f.get("properties") or {}, factor, d=d or None))
        if feat is None:
            broken += 1
            continue
        feats.append((area, feat))
    capped = 0
    if len(feats) > cfg.max_buildings:
        feats.sort(key=lambda x: -x[0])
        capped = len(feats) - cfg.max_buildings
        feats = feats[:cfg.max_buildings]
    src = collections.Counter(f["properties"]["src"] for _, f in feats)
    return {"raw": raw, "features": [f for _, f in feats], "factor": factor, "bbox": bb,
            "meta": B.make_meta(basis, factor, capped_dropped=capped or None), "stats": {"raw": len(raw), "tiny_dropped": tiny, "broken": broken,
                                                          "capped_dropped": capped, "src": dict(src)}}


def fetch_context(client: api.Client, center, radius_m: int, today_s: str):
    lon, lat = center
    q = (f'[out:json][timeout:90];('
         f'node["railway"="station"](around:{radius_m},{lat:.6f},{lon:.6f});'
         f'node["amenity"="school"](around:{radius_m},{lat:.6f},{lon:.6f});'
         f'way["amenity"="school"](around:{radius_m},{lat:.6f},{lon:.6f});'
         f'relation["amenity"="school"](around:{radius_m},{lat:.6f},{lon:.6f}););out center tags;')
    payload = client.overpass(q, budget_s=120)
    stations, schools, seen = [], [], set()
    for el in payload.get("elements", []):
        tags = el.get("tags") or {}
        name = (tags.get("name:ko") or tags.get("name") or "").strip()
        if not name:
            continue
        x = el.get("lon", (el.get("center") or {}).get("lon"))
        y = el.get("lat", (el.get("center") or {}).get("lat"))
        if x is None or y is None:
            continue
        kind = "station" if tags.get("railway") == "station" else "school" if tags.get("amenity") == "school" else None
        if not kind or (kind, name) in seen:
            continue
        seen.add((kind, name))
        (stations if kind == "station" else schools).append({"name": name, "lon": x, "lat": y})
    return bundle.context_doc(stations, schools, today_s, OSM_SOURCE)


def build(cfg: RegionConfig, client: api.Client, today: date, out_dir: Path, with_context: bool = True) -> dict:
    t0 = time.time()
    today_s, basis = today.isoformat(), today.strftime("%Y%m%d")
    zone = fetch_zone(cfg, client)
    bld = fetch_buildings(cfg, client, zone["bbox"], basis)
    bld["existence"] = existence.apply(client, bld["features"], [zone["poly"]], zone["bbox"], bld["meta"])   # 지구 안 철거 잔존 의심 건물에 g=1(existence.py)
    notices = client.myhome_notices()
    all_items = notices["rental"] + notices["sale"]
    myhome = [it for it in all_items if cfg.myhome_filter(it)]
    permits, dong_rows = [], []
    for bj in cfg.bjdongs:
        permits += client.hub_basis(cfg.sigungu, bj)
        dong_rows += client.hub_dong(cfg.sigungu, bj)
    parcels = {}
    for pnu in sorted(pnus_to_fetch(myhome, permits)):
        f = client.parcel(pnu)
        parcels[pnu] = f.get("geometry") if f else None
    plan = plan_projects(cfg, apt_blocks=zone["apt_blocks"], buildings=bld["raw"], myhome=myhome, parcels=parcels,
                         permits=permits, dong_rows=dong_rows, today=today)

    context, ctx_err = None, None
    if with_context:
        try:
            context = fetch_context(client, zone["center"], cfg.context_radius_m, today_s)
        except Exception as e:  # 실패하면 생략
            ctx_err = type(e).__name__ + ": " + api.redact(str(e), client.keys.secrets())[:200]

    zone_doc = {"id": cfg.zone_id, "name": cfg.zone_name, "type": cfg.zone_type,
                "publicLand": cfg.zone_type in PUBLIC_LAND_TYPES, "poly": zone["poly"]}
    region = bundle.region_doc(slug=cfg.slug, name=cfg.name, title=cfg.title, description=cfg.description,
                               center=zone["center"], zoom=cfg.zoom, pitch=cfg.pitch, codes=cfg.codes,
                               zones=[zone_doc], sources=_sources(today_s), updated=today_s)
    written = bundle.write_bundle(out_dir, region, bundle.projects_doc(plan["projects"], plan["other_blocks"]),
                                  bundle.buildings_doc(bld["features"], bld["meta"]), context)
    return {"zone": zone, "buildings": bld, "plan": plan, "myhome_total": len(all_items), "myhome_region": len(myhome),
            "permits": len(permits), "dong_rows": len(dong_rows), "parcels": parcels, "context": context,
            "context_error": ctx_err, "written": written, "elapsed_s": round(time.time() - t0, 1),
            "calls": dict(client.calls)}


def _report(cfg: RegionConfig, res: dict) -> str:
    z, b, plan = res["zone"], res["buildings"], res["plan"]
    lines = [f"# {cfg.slug} ({cfg.name})",
             f"- 지구 피처 {len(z['features'])}개, 공동주택 블록 {len(z['apt_blocks'])}개, 중심 {tuple(round(v, 6) for v in z['center'])}"
             + (" (경고: 지구가 검색 범위 경계에 닿음)" if z["touches_search_edge"] else ""),
             f"- 건물: 원본 {b['stats']['raw']} → 번들 {len(b['features'])} (10㎡ 미만 {b['stats']['tiny_dropped']}, "
             f"퇴화 {b['stats']['broken']}, 상한 초과 {b['stats']['capped_dropped']}) 높이 출처 {b['stats']['src']}",
             f"- meta.factor: {b['factor'] or '없음(표본 30개 미만 → 화면 기본 2.85 m/층)'}",
             existence.report(b["existence"]),
             f"- 마이홈 공고 전체 {res['myhome_total']}건 중 지역 {res['myhome_region']}건, 인허가 기본개요 {res['permits']}건, "
             f"동 개요 {res['dong_rows']}행, 필지 조회 {len(res['parcels'])}건(없음 {sum(1 for v in res['parcels'].values() if not v)})",
             f"- 통계: {dict(plan['stats'])}",
             f"- 단지 {len(plan['projects'])}개, 이름 모르는 주택 용지 {len(plan['other_blocks'])}개"]
    for p in plan["projects"]:
        lines.append(f"  - {p['id']} | {p['label']} | {p['status']} | {p['sponsorClass']} | {p['sponsor']['name']} | "
                     f"세대 {p.get('units')} | 동 {p.get('dongCount')} (관측 {len(p.get('dongs') or [])}) | {p['name']}")
    lines.append(f"- 제외 {len(plan['exclusions'])}건")
    for x in plan["exclusions"]:
        lines.append(f"  - {x.get('name')} (세대 {x.get('units')}): {x['reason']}")
    ctx = res["context"]
    lines.append(f"- context: " + (f"역 {len(ctx['stations'])}, 학교 {len(ctx['schools'])}" if ctx else f"생략 ({res['context_error']})"))
    for p in res["written"]:
        lines.append(f"- {p.relative_to(ROOT) if p.is_relative_to(ROOT) else p}: {p.stat().st_size:,} B")
    lines.append(f"- 소요 {res['elapsed_s']} s, 호출 {res['calls']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="build_region", description="API로 지역 지도 번들을 만든다.")
    ap.add_argument("slug", choices=sorted(REGIONS))
    ap.add_argument("--env", default=str(ROOT / ".env.local"), help="키 파일(기본 저장소의 .env.local)")
    ap.add_argument("--cache-dir", default=os.environ.get("REGIONBUILD_CACHE"), help="응답 캐시 폴더(저장소 밖)")
    ap.add_argument("--refresh", action="store_true", help="캐시를 무시하고 다시 받기")
    ap.add_argument("--out", default=None, help="출력 폴더(기본 regions/<slug>)")
    ap.add_argument("--today", default=None, help="기준일 YYYY-MM-DD(기본 오늘)")
    ap.add_argument("--no-context", action="store_true", help="Overpass(역·학교)를 건너뜀")
    args = ap.parse_args(argv)
    try:
        keys = api.load_keys(args.env)
    except api.MissingKey as e:
        print(f"오류: {e}. 키가 있을 때만 동작합니다.")
        return 2
    if args.cache_dir and Path(args.cache_dir).resolve().is_relative_to(ROOT):
        print("오류: 캐시 폴더는 저장소 밖이어야 합니다.")
        return 2
    cfg = REGIONS[args.slug]
    today = date.fromisoformat(args.today) if args.today else date.today()
    out = Path(args.out) if args.out else ROOT / "regions" / cfg.slug
    client = api.Client(keys, cache_dir=args.cache_dir, refresh=args.refresh)
    try:
        res = build(cfg, client, today, out, with_context=not args.no_context)
    except api.ApiError as e:
        print(f"오류: API 호출 실패 — {e}")
        return 1
    print(_report(cfg, res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
