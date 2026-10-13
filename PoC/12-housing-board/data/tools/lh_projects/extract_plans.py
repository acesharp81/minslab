#!/usr/bin/env python3
"""LH 팸플릿(이미지 PDF)의 '단지배치도'에서 단지경계선과 동 지붕 조각을 읽어 plan_px.json으로 저장한다.

대상: A9, A17, A2, A3 (A6는 동 모양이 복잡해 build_projects.py에 손으로 옮긴 값을 쓴다)
방법: pdftoppm으로 5쪽을 120dpi로 그린 뒤 왼쪽 면(단지배치도)을 잘라
  - 빨간 점선(단지경계선) 픽셀의 볼록껍질 → 경계 다각형
  - 분홍·파랑·주황(A9) / 보라·청록·주황(A17) 지붕 색 덩어리 → 동 조각 다각형
좌표는 잘라낸 그림의 px이며, 위도·경도로의 변환은 build_projects.py가 한다.
필요: poppler(pdftoppm), Pillow
"""
import colorsys, json, math, subprocess, sys, tempfile
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import RAW as _RAW  # noqa: E402

RAW = _RAW / "lh" / "pamphlets"
OUT = Path(__file__).with_name("plan_px.json")

def render_left(pdf, page=5, dpi=120):
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page), "-png", str(pdf), f"{td}/p"], check=True)
        f = sorted(Path(td).glob("p-*.png"))[0]
        im = Image.open(f).convert("RGB")
        w, h = im.size
        return im.crop((0, 0, w // 2, h)).copy()

def hull(P):
    P = sorted(set(P))
    cr = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in P:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0: lo.pop()
        lo.append(p)
    for p in reversed(P):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 0: up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]

def simplify(P, eps):
    def seg(a, b, pts):
        if not pts: return []
        d = [abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1])) / math.hypot(b[0] - a[0], b[1] - a[1]) for p in pts]
        m = max(range(len(pts)), key=lambda i: d[i])
        if d[m] <= eps: return []
        return seg(a, pts[m], pts[:m]) + [pts[m]] + seg(pts[m], b, pts[m + 1:])
    i1 = max(range(len(P)), key=lambda i: math.hypot(P[i][0] - P[0][0], P[i][1] - P[0][1]))
    A = P[:i1 + 1]; B = P[i1:] + [P[0]]
    return [A[0]] + seg(A[0], A[-1], A[1:-1]) + [A[-1]] + seg(B[0], B[-1], B[1:-1])

def boundary(im, region, excl):
    px = im.load(); x0, y0, x1, y1 = region
    pts = [(x, y) for y in range(y0, y1) for x in range(x0, x1)
           if not any(a <= x <= c and b <= y <= d for a, b, c, d in excl)
           and px[x, y][0] > 205 and px[x, y][1] < 75 and px[x, y][2] < 75]
    return simplify(hull(pts), 6)

def pieces(im, region, hues, minarea, drop=()):
    px = im.load(); x0, y0, x1, y1 = region
    mask = {}
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = px[x, y]
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255); h *= 360
            if v < 0.45: continue
            for name, (a, c, ms) in hues.items():
                if a <= h <= c and s >= ms: mask[(x, y)] = name; break
    seen, out = set(), []
    for p, name in mask.items():
        if p in seen: continue
        st, pts = [p], []; seen.add(p)
        while st:
            q = st.pop(); pts.append(q)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (q[0] + dx, q[1] + dy)
                if n in mask and n not in seen and mask[n] == name: seen.add(n); st.append(n)
        if len(pts) < minarea: continue
        cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
        if any(abs(cx - dx_) < 6 and abs(cy - dy_) < 6 for dx_, dy_ in drop): continue
        out.append({"color": name, "area": len(pts), "center": [round(cx), round(cy)], "poly": [list(p) for p in simplify(hull(pts), 2)]})
    return out

def hull_dist_clusters(pcs, thr):
    """조각들을 윤곽 사이 실제 거리가 thr px 이하면 한 건물로 묶는다."""
    def dens(h, step=3):
        out = []
        for i in range(len(h)):
            a, b = h[i], h[(i + 1) % len(h)]; L = math.hypot(b[0] - a[0], b[1] - a[1]); n = max(1, int(L / step))
            out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
        return out
    D = [dens(p["hull"]) for p in pcs]; par = list(range(len(pcs)))
    def f(i):
        while par[i] != i: par[i] = par[par[i]]; i = par[i]
        return i
    for i in range(len(pcs)):
        for j in range(i + 1, len(pcs)):
            if min(math.hypot(p[0] - q[0], p[1] - q[1]) for p in D[i] for q in D[j]) <= thr: par[f(i)] = f(j)
    g = {}
    for i in range(len(pcs)): g.setdefault(f(i), []).append(i)
    return sorted(g.values(), key=lambda m: min(p[0] for i in m for p in pcs[i]["hull"]))

def inside_poly(poly, pt):
    x, y = pt; ins = False
    for i in range(len(poly)):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1: ins = not ins
    return ins

def pieces_in(im, bound, hues, minsat, minval, minarea, maxarea=9000):
    px = im.load(); xs = [p[0] for p in bound]; ys = [p[1] for p in bound]; mask = {}
    for y in range(int(min(ys)), int(max(ys)) + 1):
        for x in range(int(min(xs)), int(max(xs)) + 1):
            if not inside_poly(bound, (x, y)): continue
            r, g, b = px[x, y]; h, s_, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255); h *= 360
            if s_ < minsat or v < minval: continue
            for name, (a, c) in hues.items():
                if a <= h <= c: mask[(x, y)] = name; break
    seen, out = set(), []
    for p, name in mask.items():
        if p in seen: continue
        st, pts = [p], []; seen.add(p)
        while st:
            q = st.pop(); pts.append(q)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    n = (q[0] + dx, q[1] + dy)
                    if n in mask and n not in seen and mask[n] == name: seen.add(n); st.append(n)
        if minarea <= len(pts) <= maxarea:
            out.append({"color": name, "area": len(pts), "hull": [list(p) for p in simplify(hull(pts), 1.5)]})
    return out

# A2·A3: 팸플릿 단지배치도가 있는 쪽(쪽번호는 0부터가 아닌 1부터)과 지붕 색, 단지경계(그림 px)
# 단지경계는 빨간 점선 픽셀의 볼록껍질에서 읽었다. 군집→동 번호는 그림에서 동 이름표 옆 건물을 눈으로 확인해 정했다.
A23 = {
    "A2": dict(pdf="LH_인천계양A2_팸플릿_통합.pdf", page=30,
               boundary=[(143, 646), (256, 230), (1075, 230), (1093, 248), (1025, 617), (1002, 648)],
               hues={"purple": (240, 262), "dblue": (201, 212), "lblue": (190, 200.9), "orange": (20, 38), "pink": (335, 355), "green": (150, 175), "dpurple": (295, 315)},
               minsat=0.28, minval=0.42, minarea=220,
               # 군집 번호(왼쪽 위치 순) → 동. 군집이 12개로 나오며 206·207동은 초록 조각(8호) 하나가 따로 떨어진다.
               dongs={"204": [0], "203": [1], "202": [2], "205": [3], "201": [4], "206": [5, 6], "210": [7], "209": [8], "207": [9, 10], "208": [11]}),
    "A3": dict(pdf="LH_인천계양A3_팸플릿.pdf", page=19,
               boundary=[(200, 253), (1100, 252), (1105, 725), (108, 727)],
               hues={"blue": (196, 212), "gold": (30, 48), "pink": (338, 356)},
               minsat=0.30, minval=0.60, minarea=140,
               dongs={"303": [0, 3], "302": [1, 2], "304": [4, 6], "301": [5, 7], "305": [8, 10], "308": [9, 11], "307": [12, 14], "306": [13, 15]}),
}

def a23_plan(key):
    c = A23[key]; im = render_page(RAW / c["pdf"], c["page"])
    pcs = pieces_in(im, c["boundary"], c["hues"], c["minsat"], c["minval"], c["minarea"])
    groups = hull_dist_clusters(pcs, 12)
    need = sum(len(v) for v in c["dongs"].values())
    if len(groups) != need:
        raise SystemExit(f"{key}: 군집 {len(groups)}개로 나와 기대({need}개)와 다릅니다. 색 범위·거리 기준을 확인하세요.")
    out = []
    for dong, ids in c["dongs"].items():
        for gi in ids:
            for i in groups[gi]:
                pc = pcs[i]; cx = sum(p[0] for p in pc["hull"]) / len(pc["hull"]); cy = sum(p[1] for p in pc["hull"]) / len(pc["hull"])
                out.append({"dong": dong, "color": pc["color"], "area": pc["area"], "center": [round(cx), round(cy)], "poly": pc["hull"]})
    return {"boundary": [list(p) for p in c["boundary"]], "pieces": out}

def render_page(pdf, page, dpi=130):
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page), "-png", str(pdf), f"{td}/p"], check=True)
        im = Image.open(sorted(Path(td).glob("p-*.png"))[0]).convert("RGB")
        w, h = im.size
        return im.crop((0, int(h * 0.25), int(w * 0.5), int(h * 0.78))).copy()

def main():
    res = {}
    # A9: 지붕은 분홍·파랑·주황. 면적 1300px 미만(체육시설·보관소 아이콘 등)과 목재 데크는 건물이 아니다.
    im9 = render_left(RAW / "LH_인천계양A9_팸플릿_20260430.pdf")
    res["A9"] = {"boundary": boundary(im9, (140, 520, 1100, 1395), [(930, 1135, 1075, 1395), (965, 545, 1040, 625), (110, 1210, 152, 1250), (130, 610, 200, 630)]),
                 "pieces": pieces(im9, (150, 530, 1060, 1390), {"pink": (318, 350, 0.38), "blue": (195, 222, 0.38), "orange": (18, 42, 0.38)}, 1300)}
    # A17: 지붕은 보라·청록·주황. 보라는 채도가 낮아 기준을 낮춘다.
    im17 = render_left(RAW / "LH_인천계양A17_팸플릿_20260930.pdf")
    res["A17"] = {"boundary": boundary(im17, (100, 360, 900, 1140), [(785, 915, 925, 1170), (70, 395, 115, 455), (695, 895, 725, 925), (705, 725, 745, 760)]),
                  "pieces": pieces(im17, (150, 370, 870, 1140), {"purple": (245, 268, 0.26), "teal": (160, 188, 0.38), "orange": (18, 42, 0.38)}, 800)}
    for k in ("A2", "A3"):
        res[k] = a23_plan(k)
    OUT.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    print({k: (len(v["boundary"]), len(v["pieces"])) for k, v in res.items()})

if __name__ == "__main__":
    main()
