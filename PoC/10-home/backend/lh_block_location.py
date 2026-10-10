"""Conservative block-label coordinates from the public LH Bizmap page.

These points place LH's block labels. They are not parcel boundaries, building
footprints, or evidence for household counts or construction progress.
"""
import json
import math
import re
from collections import defaultdict

from sqlalchemy import text

from datetime import datetime
from zoneinfo import ZoneInfo

LABEL_PATTERN = re.compile(r"var HOUSEPLAN_LABEL_INFO\s*=\s*'(\{.*?\})';", re.S)
BLOCK_PATTERN = re.compile(r"([A-Za-z]{1,3})\s*-?\s*0*(\d+)(?:BL)?", re.I)
CONVERT_POINT = text("""SELECT ST_Y(ST_Transform(ST_SetSRID(ST_MakePoint(:x,:y),5174),4326)) AS latitude,
                             ST_X(ST_Transform(ST_SetSRID(ST_MakePoint(:x,:y),5174),4326)) AS longitude""")


def district_key(value):
    value = re.sub(r"\s+", "", value or "").replace("국제화계획", "")
    return re.sub(r"(?:공공주택지구|택지개발사업|택지개발지구|지구)+$", "", value)


def block_code(value):
    match = BLOCK_PATTERN.fullmatch(str(value or ""))
    return match[1].upper() + str(int(match[2])) if match else None


def parse_label_points(content):
    page = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
    match = LABEL_PATTERN.search(page)
    if not match:
        raise ValueError("LH 공개 지도 블록 라벨 schema 변경")
    try:
        rows = json.loads(match[1])["housePlanLabelInfo"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("LH 공개 지도 블록 라벨 JSON schema 변경") from exc
    if not isinstance(rows, list) or not rows:
        raise ValueError("LH 공개 지도 블록 라벨 목록 없음")
    grouped = defaultdict(list)
    inspected = 0
    for row in rows:
        if str(row.get("flag")) != "4" or str(row.get("sggCd")) not in {"11", "41"}:
            continue
        inspected += 1
        region = {"11": "서울특별시", "41": "경기도"}[str(row["sggCd"])]
        district, block = district_key(row.get("bzdtNm")), block_code(row.get("bnm"))
        try:
            x, y = float(row["x"]), float(row["y"])
        except (ValueError, TypeError, KeyError):
            continue
        if not district or not block or not math.isfinite(x) or not math.isfinite(y):
            continue
        grouped[region, district, block].append((x, y, row["bzdtNm"], row.get("zonecode")))
    if inspected == 0:
        raise ValueError("LH 공개 지도 서울·경기 블록 라벨 없음")
    unique = {}
    ambiguous = 0
    for key, values in grouped.items():
        # Repeat rows across years are valid only if the published label point agrees.
        coordinates = {(round(x, 1), round(y, 1)) for x, y, _, _ in values}
        if len(coordinates) != 1:
            ambiguous += 1
            continue
        unique[key] = values[0]
    return unique, {"source_label_rows": inspected, "unique_blocks": len(unique), "ambiguous_blocks": ambiguous}


def collect_block_locations(source, fetcher, service):
    points, stats = parse_label_points(fetcher.get(source["url"]))
    records = []
    rejected = 0
    today = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    with service.engine.connect() as connection:
        for (region, district, block), (x, y, name, zonecode) in sorted(points.items()):
            latitude, longitude = connection.execute(CONVERT_POINT, {"x": x, "y": y}).one()
            # Reject source/projection changes rather than plotting a misplaced label.
            if not (math.isfinite(latitude) and math.isfinite(longitude) and 36.5 <= latitude <= 38.8 and 125.7 <= longitude <= 128.0):
                rejected += 1
                continue
            key = "|".join((region, district, block))
            records.append(("block_location", key, {
                "region": region, "district_key": district, "district_name": name,
                "block": block, "zonecode": zonecode, "latitude": latitude, "longitude": longitude,
                "coordinate_basis": "LH_PUBLIC_BLOCK_LABEL_POINT", "source_crs": "EPSG:5174",
                "base_date": today, "date_precision": "COLLECTION", "evidence_url": source["url"],
                "warnings": ["LABEL_POINT_NOT_BOUNDARY_OR_BUILDING"],
            }))
    if not records:
        raise ValueError("LH 공개 지도 블록 좌표 변환 결과 없음")
    return records, dict(stats, rejected_coordinates=rejected, located_blocks=len(records))
