#!/usr/bin/env python3
"""월별 avg_rad 상위 3개 격자에 가장 가까운 북한 도시명을 연결한다."""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import heapq
import io
import json
import math
import os
import re
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
DATA_DIR = OUTPUT / "data"
GEONAMES_ZIP = OUTPUT / "geonames" / "KP.zip"
MANIFEST = OUTPUT / "top3_locations.json"
GEONAMES_URL = "https://download.geonames.org/export/dump/KP.zip"
HANGUL = re.compile(r"[가-힣]")
WORKER_CITIES: list[dict] = []


def download_geonames(force: bool = False) -> None:
    if GEONAMES_ZIP.is_file() and GEONAMES_ZIP.stat().st_size > 0 and not force:
        return
    GEONAMES_ZIP.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(GEONAMES_URL, headers={"User-Agent": "minslab-poc5/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        content = response.read()
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if "KP.txt" not in archive.namelist():
            raise RuntimeError("GeoNames KP.zip에 KP.txt가 없습니다.")
    temporary = GEONAMES_ZIP.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_bytes(content)
    temporary.replace(GEONAMES_ZIP)


def preferred_korean_name(alternate_names: str) -> str | None:
    names = {name.strip() for name in alternate_names.split(",") if HANGUL.search(name)}
    if not names:
        return None
    preferred = [name for name in names if not name.endswith(("리", "동", "읍"))]
    return min(preferred or names, key=lambda value: (len(value), value))


def load_cities() -> list[dict]:
    cities = []
    with zipfile.ZipFile(GEONAMES_ZIP) as archive:
        lines = archive.read("KP.txt").decode("utf-8").splitlines()
    for line in lines:
        fields = line.split("\t")
        if len(fields) < 19 or fields[6] != "P":
            continue
        feature_code = fields[7]
        population = int(fields[14] or 0)
        if population < 10_000 and not feature_code.startswith("PPLA") and feature_code != "PPLC":
            continue
        cities.append({
            "geoname_id": int(fields[0]),
            "name": fields[1],
            "name_ascii": fields[2] or fields[1],
            "name_ko": preferred_korean_name(fields[3]),
            "lat": float(fields[4]),
            "lon": float(fields[5]),
            "feature_code": feature_code,
            "population": population,
        })
    if not cities:
        raise RuntimeError("GeoNames에서 북한 도시 후보를 찾지 못했습니다.")
    return cities


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    value = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


def initialize_worker(cities: list[dict]) -> None:
    global WORKER_CITIES
    WORKER_CITIES = cities


def process_month(file_path_text: str) -> tuple[str, list[dict]]:
    file_path = Path(file_path_text)
    with gzip.open(file_path, "rt", encoding="utf-8") as stream:
        payload = json.load(stream)
    top_rows = heapq.nlargest(3, payload["data"], key=lambda row: float(row[2]))
    locations = []
    for rank, row in enumerate(top_rows, start=1):
        lon, lat, radiance, coverage, log_value = row[:5]
        city = min(
            WORKER_CITIES,
            key=lambda item: haversine_km(float(lon), float(lat), item["lon"], item["lat"]),
        )
        distance = haversine_km(float(lon), float(lat), city["lon"], city["lat"])
        locations.append({
            "rank": rank,
            "lon": lon,
            "lat": lat,
            "avg_rad": radiance,
            "cf_cvg": int(coverage),
            "log": log_value,
            "city": city["name_ko"] or city["name"],
            "city_en": city["name_ascii"],
            "city_lon": city["lon"],
            "city_lat": city["lat"],
            "distance_km": round(distance, 1),
            "geoname_id": city["geoname_id"],
        })
    return payload["month"], locations


def main() -> int:
    parser = argparse.ArgumentParser(description="북한 VIIRS 월별 Top 3 도시 인덱스를 생성합니다.")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--refresh-geonames", action="store_true")
    args = parser.parse_args()
    download_geonames(args.refresh_geonames)
    cities = load_cities()
    files = sorted(DATA_DIR.glob("north_korea_viirs_????-??.json.gz"))
    print(f"GeoNames 도시 후보 {len(cities):,}개 · VIIRS {len(files)}개월", flush=True)
    months = {}
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=max(1, args.workers),
        initializer=initialize_worker,
        initargs=(cities,),
    ) as executor:
        futures = {executor.submit(process_month, str(path)): path for path in files}
        for completed, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            month, locations = future.result()
            months[month] = locations
            labels = ", ".join(f"{item['rank']}위 {item['city']}" for item in locations)
            print(f"[{completed}/{len(files)}] {month} · {labels}", flush=True)
    document = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "GeoNames KP country extract",
        "source_url": GEONAMES_URL,
        "license": "CC BY 4.0",
        "method": "Top 3 avg_rad grid cells; nearest city with population >= 10,000 or administrative seat",
        "months": dict(sorted(months.items())),
    }
    temporary = MANIFEST.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(MANIFEST)
    print(f"완료: {MANIFEST} ({len(months)}개월)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
