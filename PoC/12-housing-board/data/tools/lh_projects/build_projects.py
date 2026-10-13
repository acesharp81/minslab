#!/usr/bin/env python3
"""인천계양 A6·A9·A10·A17 블록의 위치·동 윤곽·동별 층수를 지도용 JS(window.GY_PROJECTS)와 CSV로 만든다.

입력:
  data/raw/vworld/vworld_LT_C_LHBLPN_인천계양테크노밸리_*.geojson   V-World 공식 블록(용지) 윤곽. 블록 이름이 없어 아래 PLAN 위치로 A-번호를 찾는다.
  blocks_px.json        팸플릿 '토지이용계획도'에서 읽은 블록 윤곽(그림 px). V-World 윤곽을 어느 블록으로 볼지 찾는 용도로만 쓴다.
  plan_px.json          팸플릿 '단지배치도'에서 읽은 A9·A17 단지경계와 동 지붕 조각 (extract_plans.py)
  이 파일 안의 DONG_A6   A6 동 윤곽(손으로 옮긴 값)
  data/raw/lh/cwstt/*.csv   LH 청약플러스 '공사현황' 공정율과 날짜별 이력
위치 맞춤: 그림의 단지경계 다각형을 V-World 블록 윤곽에 겹치도록 크기·회전·이동을 맞춘다(겹침률 IoU를 출력).
면적 검증: 공고문 세대별 공유대지×세대수 합계(AREA_NOTICE)와 V-World 윤곽 면적을 비교해 출력한다.
출력: data/legacy/gyeyang_projects.js (운영 데이터), data/processed/gyeyang_projects.csv
오차: 블록 윤곽 수 m~수십 m, 동 윤곽 10~20 m. 정확한 필지(지번)가 아니다.
"""
import csv, json, math, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from paths import RAW, PROCESSED, PROD_DATA  # noqa: E402

OUT = PROD_DATA / "gyeyang_projects.js"
OUT_CSV = PROCESSED / "gyeyang_projects.csv"

# ---- 1. 토지이용계획도(그림 px) → 위도·경도.  지구 외곽(빨간 점선) 극값과 OSM 지구경계 bbox를 맞춘다.
IMG = dict(x0=28, x1=882, y0=54, y1=1443)
GEO = dict(lon0=126.7441, lon1=126.7675, lat_n=37.5710, lat_s=37.5406)
def land_ll(x, y):
    return (GEO["lon0"] + (x - IMG["x0"]) / (IMG["x1"] - IMG["x0"]) * (GEO["lon1"] - GEO["lon0"]),
            GEO["lat_n"] - (y - IMG["y0"]) / (IMG["y1"] - IMG["y0"]) * (GEO["lat_n"] - GEO["lat_s"]))

def plan_polys():
    """토지이용계획도 기반 블록 윤곽(위도·경도). 껍질 채움이 가장자리 선 약 2px를 빼므로 사방 2px를 더한다."""
    px = json.loads((HERE / "blocks_px.json").read_text(encoding="utf-8"))
    out = {}
    for bid, pts in px.items():
        cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
        out[bid] = [land_ll(x + (2 if x >= cx else -2), y + (2 if y >= cy else -2)) for x, y in pts]
    return out

# ---- 2. 미터 좌표 도우미 (기준점 근처에서 동서·남북 m)
LON0, LAT0 = 126.755, 37.552
KX, KY = 111320 * math.cos(math.radians(LAT0)), 110574
to_m = lambda lon, lat: ((lon - LON0) * KX, (lat - LAT0) * KY)
to_ll = lambda x, y: (LON0 + x / KX, LAT0 + y / KY)

def _cross_sum(P): return sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P)))
def area(P): return abs(_cross_sum(P)) / 2
def ccw(P): return P if _cross_sum(P) > 0 else P[::-1]
def clip(subject, clipper):   # Sutherland–Hodgman (clipper는 볼록·반시계)
    out = subject
    for i in range(len(clipper)):
        a, b = clipper[i], clipper[(i + 1) % len(clipper)]
        inside = lambda p: (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0
        def cross(p, q):
            x1, y1, x2, y2, x3, y3, x4, y4 = p[0], p[1], q[0], q[1], a[0], a[1], b[0], b[1]
            d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
            return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
        inp, out = out, []
        for j in range(len(inp)):
            p, q = inp[j], inp[(j + 1) % len(inp)]
            if inside(q):
                if not inside(p): out.append(cross(p, q))
                out.append(q)
            elif inside(p): out.append(cross(p, q))
        if not out: return []
    return out
def iou(A, B):
    I = clip(A, B); ia = area(I) if len(I) >= 3 else 0
    return ia / (area(A) + area(B) - ia)
def buffer(P, d):             # 볼록 다각형을 d m 넓힌다 (모서리 이음)
    P = ccw(P); n = len(P); lines = []
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]; L = math.hypot(b[0] - a[0], b[1] - a[1]); nx, ny = (b[1] - a[1]) / L, -(b[0] - a[0]) / L
        lines.append(((a[0] + nx * d, a[1] + ny * d), (b[0] + nx * d, b[1] + ny * d)))
    out = []
    for i in range(n):
        (p1, p2), (p3, p4) = lines[i - 1], lines[i]
        dd = (p1[0] - p2[0]) * (p3[1] - p4[1]) - (p1[1] - p2[1]) * (p3[0] - p4[0])
        t = ((p1[0] - p3[0]) * (p3[1] - p4[1]) - (p1[1] - p3[1]) * (p3[0] - p4[0])) / dd
        out.append((p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1])))
    return out

def fit(src_px, target_m):
    """그림 px 다각형을 미터 좌표 target에 겹치도록 (배율 m, 회전 th, 이동 tx, ty)를 찾는다. 반환: 변환 함수, IoU, 배율, 회전(도)
    단지배치도는 북쪽이 위가 아닌 경우가 있어(A9) 회전을 함께 찾는다. 시작 회전 0°, ±20°를 모두 시험한다."""
    target = ccw(target_m)
    cs = (sum(p[0] for p in src_px) / len(src_px), sum(p[1] for p in src_px) / len(src_px))
    ct = (sum(p[0] for p in target) / len(target), sum(p[1] for p in target) / len(target))
    m0 = math.sqrt(area(target) / area(src_px))
    def mk(m, th, tx, ty):
        c, s_ = math.cos(th), math.sin(th)
        def f(p):
            vx, vy = (p[0] - cs[0]) * m, -(p[1] - cs[1]) * m
            return (vx * c - vy * s_ + ct[0] + tx, vx * s_ + vy * c + ct[1] + ty)
        return f
    score = lambda q: iou(ccw([mk(*q)(p) for p in src_px]), target)
    best_all = None
    for th0 in (0.0, math.radians(20), math.radians(-20)):
        q = [m0, th0, 0.0, 0.0]; best = score(q); step = [0.03 * m0, math.radians(3), 5.0, 5.0]
        for _ in range(160):
            moved = False
            for k in range(4):
                for sg in (+1, -1):
                    t = q[:]; t[k] += sg * step[k]; sc = score(t)
                    if sc > best + 1e-6: q, best, moved = t, sc, True
            if not moved:
                step = [x * 0.5 for x in step]
                if step[2] < 0.05: break
        if best_all is None or best > best_all[0]: best_all = (best, q)
    best, q = best_all
    return mk(*q), best, q[0], math.degrees(q[1])

# ---- 3. 동 윤곽
OFFSET = (100, 480)     # A6 동 좌표는 단지배치도를 이만큼 잘라낸 그림 기준이다
A6_BOUNDARY = [(143, 1416), (356, 597), (990, 498), (1020, 513), (1127, 1287)]   # 잘리지 않은 그림 기준
def rect(x0, y0, x1, y1): return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
def band(cx, cy, length, th, ang_deg):
    a = math.radians(ang_deg); c, s = math.cos(a), math.sin(a)
    return [(cx + x * c - y * s, cy + x * s + y * c) for x, y in [(-length / 2, -th / 2), (length / 2, -th / 2), (length / 2, th / 2), (-length / 2, th / 2)]]
DONG_A6 = {
    "601": (15, [rect(816, 416, 954, 470)]),
    "602": (15, [rect(910, 582, 970, 746), band(800, 778, 310, 50, -6)]),
    "603": (15, [rect(240, 796, 292, 872), band(452, 842, 290, 48, -7)]),
    "604": (14, [rect(106, 690, 220, 765)]),
    "605": (9,  [band(560, 645, 452, 52, -5)]),
    "606": (10, [band(637, 472, 268, 52, -7)]),
    "607": (9,  [rect(356, 445, 426, 505)]),
    "608": (9,  [rect(276, 511, 354, 570)]),
    "609": (11, [rect(160, 466, 240, 530)]),
    "610": (14, [rect(222, 312, 336, 400)]),
    "611": (8,  [band(562, 303, 300, 38, -7.7)]),
    "612": (15, [band(607, 138, 560, 44, -8.7), rect(848, 120, 905, 295), rect(275, 170, 330, 280)]),
}
# A9·A17의 지붕 조각 → 동 번호 (가장 가까운 동 이름표. 이름표 위치는 그림 px)
LABELS_A9 = {"907": (588, 576), "908": (205, 678), "906": (708, 708), "905": (572, 857), "904": (822, 892), "909": (202, 968), "903": (740, 1045), "902": (479, 1202), "901": (317, 1262)}
LABELS_A17 = {"1703": (480, 425), "1704": (438, 540), "1702": (698, 537), "1705": (410, 660), "1701": (590, 725), "1708": (570, 897), "1706": (368, 957), "1707": (537, 1024)}
OVERRIDE_A17 = {(556, 981): "1708"}   # 주황 '2' 조각은 1707이 아니라 1708에 속한다(그림으로 확인)
A17_BOUNDARY = [(152, 1007), (378, 400), (551, 373), (854, 486), (607, 1132)]   # 빨간 점선 꼭짓점을 그림에서 확인한 값

# 공고문 '공급대상' 표의 세대별 공유대지(㎡) × 세대수의 합계 = 블록 대지면적에 가깝다 (직접 계산)
#  A6  : 384×46.9404+52×46.9169+15×46.9326+10×46.8384+52×46.8462+6×47.0424+10×46.9247+5×54.7691+69×58.7775+16×60.7229+2×60.7229+26×66.5042+16×66.6689 ≈ 33,043 (663세대 전체)
#  A17 : 205×46.7333+146×46.7166+112×46.6163 ≈ 21,622 (463세대 전체, 행복주택 포함)
#  A9  : 공공분양 317세대 217×46.9434+70×46.6324+30×46.9770 ≈ 14,860. 차후공급(장기임대) 158세대의 공유대지는 표에 없어 같은 평균(약 46.9)으로 가정해 더하면 ≈ 22,270 (추정)
AREA_NOTICE = {"A6": 33043, "A17": 21622, "A9": 22270, "A2": 36854, "A3": 25394}
#  A2  : 59A~84A 7개 주택형의 세대별 공유대지×세대수 = 36,854 (747세대 전체)
#  A3  : 공고문 표에 주택형별 세대수가 없어 538세대 × 세 주택형 공유대지 평균(약 47.2) ≈ 25,394 (추정)
# 위치 찾기: 팸플릿 토지이용계획도에서 A2·A3 이름표 위치를 위도·경도로 바꾼 점 (블록 윤곽이 이 점을 품은 것을 고른다)
LOCATE = {"A2": (126.7546, 37.5561), "A3": (126.7577, 37.5565)}

def scale_to_area(P, target):
    P = ccw(P); k = math.sqrt(target / area(P)); cx = sum(p[0] for p in P) / len(P); cy = sum(p[1] for p in P) / len(P)
    return [(cx + (x - cx) * k, cy + (y - cy) * k) for x, y in P], k

META = {
    "A2":  dict(status="준공 임박", kind="공공분양", units=747, dongCount=10, floorsDoc="12~15층(최고층 기준)", moveIn="2026.12", src="LH 입주자모집공고(2024-10-09 정정)·팸플릿", builder="제일건설 주식회사", contractM=136444, builderSrc="LH 건설공사현황(2026-07-01)", note="A3와 한 공사(1공구)로 짓고 있고, 공사 종료 예정은 2026-10-11입니다."),
    "A3":  dict(status="준공 임박", kind="신혼희망타운(공공분양)", units=359, dongCount=8, floorsDoc="11~15층(최고층 기준)", moveIn="2026.12", src="LH 입주자모집공고(2024-09-20 정정)·팸플릿", builder="제일건설 주식회사", contractM=94046, builderSrc="LH 건설공사현황(2026-07-01)", note="블록 538세대 중 359세대 분양, 179세대는 행복주택입니다. 공사 종료 예정은 2026-10-11입니다."),
    "A6":  dict(status="분양중", kind="공공분양", units=663, dongCount=12, floorsDoc="최고층 기준 7~15층", moveIn="2029.06", src="LH 입주자모집공고(2026-09-14 정정)·팸플릿", builder="(주)케이알산업, 우암건설", builderSrc="청약홈 공고 시공사 표기"),
    "A17": dict(status="분양중", kind="신혼희망타운(공공분양)", units=309, dongCount=8, floorsDoc="최고층 기준 13~15층", moveIn="2029.11", src="LH 입주자모집공고(2026-09-30)·팸플릿", builder="(주)케이씨씨건설", contractM=121114, builderSrc="LH 건설공사현황(2026-07-01)", note="블록 463세대 중 309세대 분양, 154세대는 행복주택으로 후속 공급"),
    "A9":  dict(status="건설 단계", kind="신혼희망타운(공공분양)", units=317, dongCount=9, floorsDoc="14~15층", moveIn="2029.02", src="LH 입주자모집공고(2026-05-14 정정)·팸플릿", builder="진흥기업(주)", contractM=119627, builderSrc="LH 건설공사현황(2026-07-01)", note="블록 475세대 중 317세대 분양"),
    "A10": dict(status="건설 단계", kind="통합공공임대", units=778, dongCount=None, floorsDoc=None, moveIn="준공 예정 2028-09-30", src="LH 공공주택 준공예정현황(2026-01 기준), LH 공사현황(공정율)", builder="주식회사 대우건설", contractM=116707, builderSrc="LH 건설공사현황(2026-07-01)", note="모집공고 전이지만 2026-06-25 공사를 시작했습니다. 층수·동수는 미확인입니다."),
}

def load_official():
    """V-World 공식 블록 윤곽 중 공동주택·주상복합 목록: [{ring(lon,lat), types}]"""
    import glob
    f = sorted(glob.glob(str(RAW / "vworld" / "vworld_LT_C_LHBLPN_인천계양테크노밸리_*.geojson")))
    if not f: return []
    d = json.loads(Path(f[-1]).read_text(encoding="utf-8")); out = []
    for ft in d["features"]:
        if ft["properties"].get("blocktype") not in ("공동주택", "주상복합"): continue
        g = ft["geometry"]; rings = [g["coordinates"][0]] if g["type"] == "Polygon" else [p[0] for p in g["coordinates"]]
        out.append(max(rings, key=lambda r: len(r)))
    return out

def point_in(ring, pt):
    x, y = pt; inside = False
    for i in range(len(ring)):
        x1, y1 = ring[i]; x2, y2 = ring[(i + 1) % len(ring)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1: inside = not inside
    return inside

def convex_hull(P):
    P = sorted(set(P)); cr = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]); lo, up = [], []
    for p in P:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0: lo.pop()
        lo.append(p)
    for p in reversed(P):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 0: up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]

def read_progress():
    """LH 공사현황 CSV → {블록: {rate, asOf, start, end, history[[날짜,공정율],..]}}"""
    import glob
    out = {}
    for f in sorted(glob.glob(str(RAW / "lh" / "cwstt" / "lh_공사현황_인천계양_공정율_이력_*.csv"))):
        with open(f, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                b = out.setdefault(r["블록"], dict(start=r["공사시작"], end=r["공사종료"], units=int(r["세대수"] or 0), history=[]))
                b["history"].append([r["기준일"], float(r["공정율_퍼센트"])])
    for b in out.values():
        b["history"].sort(); b["asOf"], b["rate"] = b["history"][-1]
    return out

def build():
    plan = plan_polys()
    pm = {k: [to_m(*p) for p in v] for k, v in plan.items()}
    official = load_official(); progress = read_progress()
    block_m, how, ofc = {}, {}, {}
    for bid in ("A2", "A3", "A6", "A9", "A17", "A10"):
        cen = LOCATE[bid] if bid in LOCATE else (sum(p[0] for p in plan[bid]) / len(plan[bid]), sum(p[1] for p in plan[bid]) / len(plan[bid]))
        hit = [r for r in official if point_in(r, cen)]
        if hit:
            ring = hit[0]; ofc[bid] = ring
            block_m[bid] = ccw([to_m(*p) for p in ring[:-1]])
            na = AREA_NOTICE.get(bid)
            how[bid] = "V-World 공식 블록(LT_C_LHBLPN)" + (f", 공고문 면적과 {abs(area(block_m[bid]) / na - 1) * 100:.1f}% 차이" if na else ", 공고문이 없어 면적은 비교하지 못함")
        else:
            block_m[bid] = ccw(pm[bid]); how[bid] = "토지이용계획도 윤곽(공식 윤곽을 찾지 못함)"
            if bid not in pm: raise SystemExit(f"{bid}: 공식 윤곽을 찾지 못했고 대체할 윤곽도 없습니다.")
    plans = json.loads((HERE / "plan_px.json").read_text(encoding="utf-8"))
    blocks, report = [], {}
    for bid in ("A2", "A3", "A6", "A17", "A9", "A10"):
        poly_ll = [tuple(p) for p in ofc[bid][:-1]] if bid in ofc else [to_ll(*p) for p in block_m[bid]]
        b = dict(id=bid, **META[bid], poly=[[round(a, 6), round(c, 6)] for a, c in poly_ll], areaM2=round(area(block_m[bid])), outlineHow=how[bid])
        if bid in progress:
            pg = progress[bid]; b["progress"] = dict(rate=pg["rate"], asOf=pg["asOf"], start=pg["start"], end=pg["end"], history=pg["history"],
                                                     src="LH청약플러스 공사현황(공정율)")
        dongs = []
        if bid == "A6":
            tf, sc, m, th = fit(A6_BOUNDARY, convex_hull(block_m[bid])); report[bid] = (sc, m, th)
            for no, (fl, polys) in DONG_A6.items():
                dongs.append(dict(no=no, floors=fl, poly=[[[round(v, 6) for v in to_ll(*tf((x + OFFSET[0], y + OFFSET[1])))] for x, y in poly] for poly in polys]))
        elif bid in ("A9", "A17", "A2", "A3"):
            src = A17_BOUNDARY if bid == "A17" else [tuple(p) for p in plans[bid]["boundary"]]
            tf, sc, m, th = fit(src, convex_hull(block_m[bid])); report[bid] = (sc, m, th)
            labels = LABELS_A9 if bid == "A9" else LABELS_A17 if bid == "A17" else {}
            floors = {"A9": {f"9{n:02d}": (14 if n == 5 else 15) for n in range(1, 10)},
                      "A17": {f"17{n:02d}": 15 for n in range(1, 9)},
                      "A2": {f"2{n:02d}": 15 for n in range(1, 11)},   # 동호배치도: 201~210동 모두 15층까지
                      "A3": {"301": 15, "302": 15, "303": 14, "304": 14, "305": 14, "306": 15, "307": 15, "308": 15}}[bid]
            groups = {}
            for pc in plans[bid]["pieces"]:
                c = tuple(pc["center"]); no = pc.get("dong") or (OVERRIDE_A17.get(c) if bid == "A17" else None)
                no = no or min(labels, key=lambda k: math.hypot(labels[k][0] - c[0], labels[k][1] - c[1]))
                groups.setdefault(no, []).append([[round(v, 6) for v in to_ll(*tf(tuple(q)))] for q in pc["poly"]])
            for no in sorted(groups):
                dongs.append(dict(no=no, floors=floors[no], poly=groups[no]))
            b["dongFloors"] = floors
        if dongs: b["dongs"] = dongs
        blocks.append(b)
    # 이름을 아직 모르는 나머지 공동주택·주상복합 용지(공식 윤곽): 지도에서 "여기까지가 이 지구의 주택 용지"라는 맥락을 보여 주는 용도
    mine = [r for r in ofc.values()]
    others = []
    for ring in official:
        if any(ring is m or ring == m for m in mine): continue
        others.append([[round(x, 6), round(y, 6)] for x, y in ring[:-1]])
    dj = HERE / "district.json"
    district = json.loads(dj.read_text(encoding="utf-8")) if dj.exists() else None
    data = dict(district=district, otherBlocks=others, meta=dict(
        title="인천계양 테크노밸리 공공주택지구 공급 블록",
        method="블록 윤곽: V-World 공식 블록 레이어(LT_C_LHBLPN). 어느 윤곽이 A6·A9·A10·A17인지는 LH 팸플릿 토지이용계획도의 위치와 공고문 면적으로 맞춤. 동 윤곽: 팸플릿 단지배치도를 블록 윤곽에 맞춰 옮긴 근사값(10~20 m).",
        floorsMethod="LH 팸플릿 동호배치도의 동별 최상층(필로티 1층 포함). 공고문의 '최고층 기준 N~M층'은 주택형별 최상층 범위라 동 높이와 다르다.",
        sources=["LH청약플러스 인천계양 A2·A3·A6·A9·A17 입주자모집공고문과 팸플릿", "국토교통부 V-World 데이터 API(LT_C_LHBLPN) 및 배경지도", "LH청약플러스 공사현황(공정율)", "OpenStreetMap contributors (ODbL)"],
        fit={k: dict(iou=round(v[0], 3), mPerPx=round(v[1], 3), rotationDeg=round(v[2], 1)) for k, v in report.items()}, asOf="2026-10-03"), blocks=blocks)
    OUT.write_text("/* 자동 생성: data/tools/lh_projects/build_projects.py · 근사 위치 */\nwindow.GY_PROJECTS=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    rows = [["블록", "상태", "사업유형", "세대수", "동수", "동별 최상층", "입주예정", "중심_위도", "중심_경도", "면적_㎡(근사)", "윤곽 근거", "위치 정확도", "층수 근거", "공정율(%)", "공정율 기준일", "공사기간", "시공사", "공사금액_백만원"]]
    for bb in blocks:
        lons = [p[0] for p in bb["poly"]]; lats = [p[1] for p in bb["poly"]]
        fl = "; ".join(f'{d["no"]}동 {d["floors"]}층' for d in bb["dongs"]) if bb.get("dongs") else "미확인"
        rows.append([bb["id"], bb["status"], bb["kind"], bb["units"], bb.get("dongCount") or "미확인", fl, bb["moveIn"],
                     round(sum(lats) / len(lats), 5), round(sum(lons) / len(lons), 5), bb["areaM2"], bb["outlineHow"], "블록 윤곽 공식, 동 윤곽 근사" if bb.get("dongs") else "블록 윤곽 공식", bb["src"],
                     bb.get("progress", {}).get("rate", ""), bb.get("progress", {}).get("asOf", ""), (bb["progress"]["start"] + " ~ " + bb["progress"]["end"]) if bb.get("progress") else "",
                     bb.get("builder", ""), bb.get("contractM", "")])
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(rows)
    print(OUT.name, OUT.stat().st_size, "bytes | 겹침률(IoU):", {k: round(v[0], 3) for k, v in report.items()}, "| 회전(도):", {k: round(v[2], 1) for k, v in report.items()}, "| 면적 ㎡:", {b["id"]: b["areaM2"] for b in blocks})

if __name__ == "__main__":
    build()
