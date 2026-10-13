#!/usr/bin/env python3
"""V-World GIS건물통합정보(인천 SHP) → 시군구 하나의 건물 윤곽·높이 데이터(웹 지도용 JS)로 바꾼다.

입력  : data/raw/vworld/vworld_GIS건물통합정보_인천_20260909.zip  (AL_D010_28_*.shp/.dbf/.shx, EPSG:5186)
출력  : data/legacy/gyeyang_buildings.js                      window.GY_BUILDINGS = GeoJSON + meta (운영 데이터)
        data/processed/gyeyang_buildings_summary.json  품질 요약(건수·결측률·환산 오차)
실행  : python3 data/tools/vworld_buildings/build_buildings.py [시군구코드=28245] [출력이름=gyeyang]

외부 라이브러리 없이 표준 라이브러리만 쓴다(좌표 변환은 같은 폴더의 tm.py).
높이 표시값(eh)은 공식 높이 → 층수×층고 → 3 m 평면 순으로 정하고, 어느 것을 썼는지 src에 남긴다.
층고는 같은 파일에서 높이와 층수가 모두 있는 건물의 중앙값(용도·층수대별)으로 구하며, 임의 가정값을 쓰지 않는다.
출처: 국토교통부 GIS건물통합정보(V-World), 공공누리가 아닌 CC BY 2.0 KR. 이용 시 출처를 표시해야 한다.
"""
import collections, json, math, statistics, struct, sys, tempfile, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from tm import inverse  # noqa: E402
from paths import RAW, PROCESSED, PROD_DATA  # noqa: E402

ZIP = RAW / "vworld" / "vworld_GIS건물통합정보_인천_20260909.zip"
SIGUNGU = sys.argv[1] if len(sys.argv) > 1 else "28245"
NAME = sys.argv[2] if len(sys.argv) > 2 else "gyeyang"
STEM = "AL_D010_28_20260909"
HIGH_CEILING = {"공장", "창고시설", "위험물저장및처리시설", "운동시설", "문화및집회시설", "종교시설", "교육연구시설", "자동차관련시설", "동.식물 관련시설"}


def read_dbf(zf):
    """DBF를 압축 파일에서 바로 읽어(562 MB를 풀지 않음) 대상 시군구 행만 모은다."""
    rows, total = [], 0
    with zf.open(f"{STEM}.dbf") as f:
        h = f.read(32)
        nrec, hlen, rlen = struct.unpack("<IHH", h[4:12])
        desc = f.read(hlen - 32)  # 필드 설명(32바이트씩) + 끝 표시 0x0D. 레코드는 hlen 바이트부터 시작한다.
        fields, off = [], 1
        for k in range(0, len(desc), 32):
            d = desc[k:k + 32]
            if d[0] == 0x0D:
                break
            fields.append((d[:11].split(b"\0")[0].decode(), d[16], off))
            off += d[16]
        F = {n: (l, o) for n, l, o in fields}

        def s(rec, n):
            l, o = F[n]
            return rec[o:o + l].replace(b"\0", b" ").decode("cp949", "replace").strip()

        def num(rec, n):
            v = s(rec, n)
            try:
                return float(v) if v else None
            except ValueError:
                return None

        for i in range(nrec):
            rec = f.read(rlen)
            if len(rec) < rlen:
                break
            total += 1
            if s(rec, "A23") != SIGUNGU:
                continue
            rows.append(dict(i=i, dong=s(rec, "A4"), use=s(rec, "A9"), appr=s(rec, "A13"), h=num(rec, "A16"),
                             name=s(rec, "A24"), fl=num(rec, "A26"), bfl=num(rec, "A27"), basis=s(rec, "A22")))
    return rows, total


def read_shp_rings(zf, wanted, tmp):
    zf.extract(f"{STEM}.shp", tmp)
    zf.extract(f"{STEM}.shx", tmp)
    shp = open(Path(tmp) / f"{STEM}.shp", "rb")
    shx = open(Path(tmp) / f"{STEM}.shx", "rb")
    shp.read(100)
    shx.seek(100)
    idx = shx.read()
    geoms = {}
    for i in wanted:
        off, _ = struct.unpack(">ii", idx[i * 8:i * 8 + 8])
        shp.seek(off * 2 + 8)
        st, = struct.unpack("<i", shp.read(4))
        if st == 0:
            continue
        shp.read(32)
        nparts, npts = struct.unpack("<ii", shp.read(8))
        parts = list(struct.unpack("<%di" % nparts, shp.read(4 * nparts)))
        pts = struct.unpack("<%dd" % (2 * npts), shp.read(16 * npts))
        pts = [(pts[2 * k], pts[2 * k + 1]) for k in range(npts)]
        parts.append(npts)
        geoms[i] = [pts[parts[k]:parts[k + 1]] for k in range(nparts)]
    return geoms


def ring_area(pts):
    return sum(pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1] for i in range(len(pts) - 1)) / 2


def band(r):
    """층고 환산표의 열쇠. 공동주택은 층수대별로 나눈다."""
    u = r["use"]
    if "공동주택" in u:
        f = r["fl"]
        return "공동주택_" + ("1-5" if f <= 5 else "6-10" if f <= 10 else "11-15" if f <= 15 else "16-20" if f <= 20 else "21+")
    return u


def has_h(r):
    return (r["h"] or 0) > 0


def has_f(r):
    return (r["fl"] or 0) > 0


def derive_factor(rows):
    by = collections.defaultdict(list)
    for r in rows:
        if has_h(r) and has_f(r) and r["fl"] <= 60:
            by[band(r)].append(r["h"] / r["fl"])
    allv = [x for v in by.values() for x in v]
    factor = {k: round(statistics.median(v), 2) for k, v in by.items() if len(v) >= 30}
    factor["_기타"] = round(statistics.median(allv), 2)
    return factor, {k: len(v) for k, v in by.items() if len(v) >= 30}


def floors_to_height(r, factor):
    return r["fl"] * factor.get(band(r), factor["_기타"])


def cross_validate(rows):
    """층수 환산이 얼마나 맞는지: 높이·층수가 모두 있는 건물을 짝/홀로 나눠 한쪽에서 구한 층고를 다른 쪽에 적용."""
    both = [r for r in rows if has_h(r) and has_f(r) and r["fl"] <= 60]
    errs = []
    for k in (0, 1):
        train = [r for j, r in enumerate(both) if j % 2 != k]
        test = [r for j, r in enumerate(both) if j % 2 == k]
        fac, _ = derive_factor(train)
        for r in test:
            errs.append(abs(floors_to_height(r, fac) - r["h"]) / r["h"])
    errs.sort()
    n = len(errs)
    return {"n": n, "median_abs_pct": round(100 * errs[n // 2], 1), "p90_abs_pct": round(100 * errs[int(n * 0.9)], 1)}


def main():
    PROD_DATA.mkdir(exist_ok=True); PROCESSED.mkdir(parents=True, exist_ok=True)
    zf = zipfile.ZipFile(ZIP)
    rows, total = read_dbf(zf)
    print(f"전체 {total:,}건 중 시군구 {SIGUNGU} {len(rows):,}건")
    factor, factor_n = derive_factor(rows)
    cv = cross_validate(rows)
    print("층고 환산표:", factor)
    print("층수환산 교차검증:", cv)

    with tempfile.TemporaryDirectory() as tmp:
        geoms = read_shp_rings(zf, [r["i"] for r in rows], tmp)

    def conv(ring):
        out = []
        for x, y in ring:
            lo, la = inverse(x, y)
            out.append([round(lo, 6), round(la, 6)])
        return out

    feats, src = [], collections.Counter()
    zero_h = sum(1 for r in rows if r["h"] == 0)
    bbox = [999, 999, 0, 0]
    for r in rows:
        rings = geoms.get(r["i"])
        if not rings:
            continue
        outers, holes = [], []
        for ring in rings:
            (outers if ring_area(ring) < 0 else holes).append(conv(ring))  # SHP 바깥 고리는 시계 방향
        if not outers:
            outers, holes = [conv(rings[0])], []
        geom = ({"type": "Polygon", "coordinates": [outers[0]] + holes} if len(outers) == 1
                else {"type": "MultiPolygon", "coordinates": [[o] for o in outers]})
        if has_h(r):
            eh, s = round(r["h"], 1), "공식높이"
        elif has_f(r):
            eh, s = round(floors_to_height(r, factor), 1), "층수환산"
        else:
            eh, s = 3.0, "정보없음"
        src[s] += 1
        for lo, la in outers[0]:
            bbox = [min(bbox[0], lo), min(bbox[1], la), max(bbox[2], lo), max(bbox[3], la)]
        p = {"eh": eh, "src": s, "u": r["use"][:10]}
        if has_h(r):
            p["h"] = round(r["h"], 1)
        if has_f(r):
            p["f"] = int(r["fl"])
        if has_h(r) and has_f(r):
            per = r["h"] / r["fl"]
            # 층당 높이가 2 m 미만이거나 8 m 초과면 둘 중 하나가 틀렸을 수 있다(고치지 않고 표시만).
            # 공장·창고·체육시설·학교처럼 층고가 큰 용도는 8 m 초과를 정상으로 본다.
            if per < 2.0 or (per > 8.0 and r["use"] not in HIGH_CEILING):
                p["x"] = 1
        if (r["bfl"] or 0) > 0:
            p["b"] = int(r["bfl"])
        if r["name"]:
            p["n"] = r["name"][:24]
        if r["appr"][:4].isdigit():
            p["a"] = int(r["appr"][:4])
        if r["dong"]:
            p["d"] = r["dong"].split()[-1]
        feats.append({"type": "Feature", "properties": p, "geometry": geom})

    n = len(feats)
    years = [f["properties"]["a"] for f in feats if "a" in f["properties"]]
    use_cnt = collections.Counter(f["properties"]["u"] or "용도 미기재" for f in feats)
    n_noh = sum(1 for f in feats if "h" not in f["properties"])
    n_sus = sum(1 for f in feats if f["properties"].get("x"))
    summary = {
        "시군구코드": SIGUNGU, "건물수": n, "높이출처": dict(src),
        "높이출처_비율": {k: round(100 * v / n, 1) for k, v in src.items()},
        "지상층수_있음": sum(1 for f in feats if "f" in f["properties"]),
        "사용승인_있음": len(years), "사용승인_최근": max(years) if years else None,
        "높이_0기재_결측처리": zero_h, "공식높이_결측": n_noh, "높이층수_불일치_의심": n_sus,
        "데이터기준일_최대": max((r["basis"] for r in rows if r["basis"]), default=""),
        "용도_상위": use_cnt.most_common(8), "층고환산표": factor, "층고표본수": factor_n,
        "층수환산_교차검증": cv, "bbox": [round(v, 4) for v in bbox],
    }
    meta = {
        "title": "국토교통부 GIS건물통합정보 (V-World) · 인천 계양구", "license": "CC BY 2.0 KR",
        "attribution": "국토교통부 GIS건물통합정보, V-World(vworld.kr)", "basis": summary["데이터기준일_최대"],
        "crs": "원본 EPSG:5186 → WGS84(EPSG:4326)로 변환, 소수 6자리", "factor": factor, "crossCheck": cv, "bbox": summary["bbox"],
        "fields": {"eh": "화면에 그리는 높이(m)", "src": "높이 출처(공식높이/층수환산/정보없음)", "h": "공식 높이(m)", "f": "지상층수",
                   "b": "지하층수", "u": "용도", "n": "건물명", "a": "사용승인 연도", "d": "법정동",
                   "x": "1이면 층당 높이가 2 m 미만 또는 8 m 초과(층고 큰 용도 제외): 높이·층수 불일치 의심"},
        "counts": dict(src), "total": n, "suspect": n_sus, "lastApproval": max(years) if years else None,
        "approvalByYear": {str(y): c for y, c in sorted(collections.Counter(years).items()) if y >= 2010},
    }
    data = {"type": "FeatureCollection", "features": feats, "meta": meta}
    js = PROD_DATA / f"{NAME}_buildings.js"
    js.write_text("/* 자동 생성: data/tools/vworld_buildings/build_buildings.py · 출처 " + meta["attribution"] + " · " + meta["license"] + " */\n"
                  "window.GY_BUILDINGS=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    (PROCESSED / f"{NAME}_buildings_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{js.name}: {js.stat().st_size / 1e6:.2f} MB, {n:,}동 | 높이 출처 {dict(src)} | bbox {summary['bbox']}")


if __name__ == "__main__":
    main()
