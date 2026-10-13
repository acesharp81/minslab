#!/usr/bin/env python3
"""OSM에서 받은 역·학교 위치를 지도용 JS(window.GY_CONTEXT)로 줄인다.

입력 : data/raw/osm/ctx.json  (Overpass: railway=station, amenity=school·kindergarten, 계양 일대 bbox)
출력 : data/legacy/gyeyang_context.js (운영 데이터)
기준 : 인천계양 테크노밸리 지구 중심에서 직선거리 — 지하철역 3.2 km, 학교 2.2 km 안만 남긴다.
주의: OSM에 있는 것만 담았다. 지구 안에 새로 짓는 학교·역은 아직 OSM에 없을 수 있다. 직선거리이며 걷는 거리가 아니다.
출처: © OpenStreetMap contributors (ODbL)
"""
import json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import RAW, PROD_DATA

SRC = RAW / "osm" / "ctx.json"
OUT = PROD_DATA / "gyeyang_context.js"
CENTER = (126.7585, 37.5515)

def dist_km(lon, lat):
    return math.hypot((lon - CENTER[0]) * 88.3, (lat - CENTER[1]) * 110.6)

def main():
    d = json.loads(SRC.read_text(encoding="utf-8"))
    stations, schools, seen = [], [], set()
    for e in d["elements"]:
        t = e.get("tags", {}); c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
        name = t.get("name")
        if not name or c.get("lat") is None: continue
        km = dist_km(c["lon"], c["lat"])
        if t.get("railway") == "station" and t.get("station") == "subway" and km <= 3.2:
            if name in seen: continue
            seen.add(name); stations.append({"name": name + "역", "lon": round(c["lon"], 5), "lat": round(c["lat"], 5)})
        elif t.get("amenity") == "school" and km <= 2.2:
            schools.append({"name": name, "lon": round(c["lon"], 5), "lat": round(c["lat"], 5)})
    data = {"stations": stations, "schools": schools, "asOf": "2026-10-03", "source": "© OpenStreetMap contributors (ODbL)"}
    OUT.write_text("/* 자동 생성: data/tools/context/build_context.py · © OpenStreetMap contributors (ODbL) */\nwindow.GY_CONTEXT=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(len(stations), "역,", len(schools), "학교 →", OUT.name)

if __name__ == "__main__":
    main()
