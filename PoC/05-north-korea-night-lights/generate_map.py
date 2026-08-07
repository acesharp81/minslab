#!/usr/bin/env python3
"""북한 월별 VIIRS 야간조명 3D GridCellLayer HTML 생성기."""

from __future__ import annotations

import argparse
import gzip
import html
import json
import math
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from datetime import date
from pathlib import Path
from typing import Any


VIIRS_COLLECTION = "NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG"
BOUNDARY_COLLECTION = "USDOS/LSIB_SIMPLE/2017"
NORTH_KOREA_FIPS = "KN"
NATIVE_SCALE_METERS = 463.83
DEFAULT_MONTH = "2024-01"
DEFAULT_COLOR_MAX = 60.0
DEFAULT_ELEVATION_SCALE = 5000.0

# 어두운 배경부터 고휘도 핵심부까지 이어지는 고정 팔레트다.
COLOR_STOPS = (
    (8, 14, 36),
    (27, 54, 93),
    (35, 116, 133),
    (92, 177, 128),
    (232, 216, 90),
    (245, 137, 55),
    (255, 244, 210),
)


def load_runtime_environment() -> None:
    """루트와 PoC 로컬 .env를 읽되 이미 설정된 환경변수는 덮어쓰지 않는다."""
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise RuntimeError(
            "python-dotenv가 없습니다. 먼저 `pip install -r requirements.txt`를 실행하세요."
        ) from exc

    project_dir = Path(__file__).resolve().parent
    repository_root = project_dir.parents[1]
    load_dotenv(repository_root / ".env", override=False)
    load_dotenv(project_dir / ".env", override=False)


def parse_month(value: str) -> tuple[date, date]:
    """YYYY-MM를 해당 월 시작일과 다음 달 시작일로 변환한다."""
    try:
        year_text, month_text = value.split("-", maxsplit=1)
        start = date(int(year_text), int(month_text), 1)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("월은 YYYY-MM 형식이어야 합니다.") from exc

    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)
    return start, end


def initialize_earth_engine(project: str | None) -> Any:
    """저장된 사용자 인증 또는 ADC로 Earth Engine을 초기화한다."""
    try:
        import ee
    except ImportError as exc:
        raise RuntimeError(
            "earthengine-api가 없습니다. 먼저 `pip install -r requirements.txt`를 실행하세요."
        ) from exc

    try:
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            import google.auth

            credentials, detected_project = google.auth.default(
                scopes=[
                    "https://www.googleapis.com/auth/earthengine",
                    "https://www.googleapis.com/auth/cloud-platform",
                ]
            )
            ee.Initialize(
                credentials=credentials,
                project=project or detected_project,
            )
        elif project:
            ee.Initialize(project=project)
        else:
            ee.Initialize()
    except Exception as exc:
        raise RuntimeError(
            "Earth Engine 초기화에 실패했습니다. `earthengine authenticate`를 실행하고 "
            "--project 또는 GEE_PROJECT로 Cloud 프로젝트를 지정하세요."
        ) from exc
    return ee


def prepare_month_image(ee: Any, month: str) -> tuple[Any, dict[str, Any]]:
    """북한 경계로 자르고 cf_cvg > 0 마스크를 적용한 월 영상을 만든다."""
    start, end = parse_month(month)
    boundary_fc = ee.FeatureCollection(BOUNDARY_COLLECTION).filter(
        ee.Filter.eq("country_co", NORTH_KOREA_FIPS)
    )
    if int(boundary_fc.size().getInfo()) == 0:
        raise RuntimeError("LSIB 경계 컬렉션에서 북한(country_co=KN)을 찾지 못했습니다.")

    collection = ee.ImageCollection(VIIRS_COLLECTION).filterDate(
        start.isoformat(), end.isoformat()
    )
    if int(collection.size().getInfo()) == 0:
        raise RuntimeError(f"{month}에 해당하는 VIIRS 월 영상이 없습니다.")

    boundary = boundary_fc.geometry(maxError=100)
    source = ee.Image(collection.first()).select(["avg_rad", "cf_cvg"])
    valid = source.select("cf_cvg").gt(0)
    # 명시적 결측값을 두어 GeoTIFF가 마스크 메타데이터를 잃어도 국외 픽셀이 제외되게 한다.
    image = source.updateMask(valid).clip(boundary).unmask(-9999)
    boundary_feature = {
        "type": "Feature",
        "properties": {"name": "North Korea"},
        "geometry": boundary.getInfo(),
    }
    return image, boundary_feature


def _download_file(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "poc5-viirs-map/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            with destination.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
    except Exception as exc:
        raise RuntimeError(f"Earth Engine GeoTIFF 다운로드에 실패했습니다: {exc}") from exc


def download_geotiff(image: Any, boundary_geometry: dict[str, Any], scale: float, path: Path) -> None:
    """Earth Engine의 소용량 다운로드 API로 2밴드 GeoTIFF를 받는다."""
    region = boundary_geometry["geometry"]
    try:
        url = image.getDownloadURL(
            {
                "name": "north_korea_viirs",
                "bands": ["avg_rad", "cf_cvg"],
                "region": region,
                "scale": scale,
                "crs": "EPSG:4326",
                "format": "GEO_TIFF",
                "filePerBand": False,
            }
        )
    except Exception as exc:
        raise RuntimeError(f"Earth Engine 다운로드 URL 생성에 실패했습니다: {exc}") from exc

    downloaded = path.with_suffix(".download")
    _download_file(url, downloaded)
    with downloaded.open("rb") as stream:
        signature = stream.read(4)

    if signature.startswith(b"PK"):
        with zipfile.ZipFile(downloaded) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith((".tif", ".tiff"))]
            if not members:
                raise RuntimeError("다운로드 ZIP 안에 GeoTIFF가 없습니다.")
            with archive.open(members[0]) as source, path.open("wb") as output:
                shutil.copyfileobj(source, output)
    else:
        downloaded.replace(path)

    if downloaded.exists():
        downloaded.unlink()


def _interpolate_colors(values: Any, maximum: float) -> Any:
    import numpy as np

    palette = np.asarray(COLOR_STOPS, dtype=np.float64)
    denominator = math.log1p(maximum)
    normalized = np.clip(values / denominator, 0.0, 1.0)
    position = normalized * (len(palette) - 1)
    low = np.floor(position).astype(np.int16)
    high = np.minimum(low + 1, len(palette) - 1)
    fraction = (position - low)[:, None]
    return np.rint(palette[low] * (1.0 - fraction) + palette[high] * fraction).astype(np.uint8)


def raster_to_frame(tif_path: Path, color_max: float) -> Any:
    """유효 격자를 GridCellLayer용 테이블로 변환한다."""
    try:
        import numpy as np
        import pandas as pd
        import rasterio
        from rasterio.warp import transform as transform_coordinates
    except ImportError as exc:
        raise RuntimeError(
            "numpy, pandas 또는 rasterio가 없습니다. `pip install -r requirements.txt`를 실행하세요."
        ) from exc

    with rasterio.open(tif_path) as dataset:
        if dataset.count < 2:
            raise RuntimeError("GeoTIFF에 avg_rad와 cf_cvg 두 밴드가 모두 있어야 합니다.")
        avg_rad = dataset.read(1)
        cf_cvg = dataset.read(2)
        valid = (
            np.isfinite(avg_rad)
            & np.isfinite(cf_cvg)
            & (avg_rad > -9999)
            & (cf_cvg > 0)
        )
        rows, columns = np.nonzero(valid)
        if rows.size == 0:
            raise RuntimeError("cf_cvg > 0인 북한 격자가 없습니다.")

        # GridCellLayer의 getPosition은 셀 중심이 아니라 좌하단 좌표를 요구한다.
        xs, ys = rasterio.transform.xy(dataset.transform, rows, columns, offset="ll")
        if dataset.crs and dataset.crs.to_string() != "EPSG:4326":
            xs, ys = transform_coordinates(dataset.crs, "EPSG:4326", xs, ys)

        raw = avg_rad[valid].astype(np.float64)
        coverage = cf_cvg[valid]

    # VIIRS 배경 잡음에는 음수가 있을 수 있다. 원값은 보존하고 시각화 입력만 0으로 제한한다.
    log_radiance = np.log1p(np.clip(raw, 0.0, None))
    colors = _interpolate_colors(log_radiance, color_max)
    return pd.DataFrame(
        {
            "lon": np.round(np.asarray(xs, dtype=np.float64), 6),
            "lat": np.round(np.asarray(ys, dtype=np.float64), 6),
            "rad": np.round(raw, 4),
            "cvg": np.rint(coverage).astype(np.int16),
            "log": np.round(log_radiance, 5),
            "r": colors[:, 0],
            "g": colors[:, 1],
            "b": colors[:, 2],
        }
    )


def _page_overlay(month: str, count: int, color_max: float, scale: float) -> tuple[str, str]:
    title = html.escape(f"북한 VIIRS 야간조명 · {month}")
    css = """
<style>
  html, body { margin: 0; background: #050914; font-family: Inter, Pretendard, sans-serif; }
  .map-info { position: fixed; z-index: 9; top: 18px; left: 18px; width: 310px;
    color: #edf6ff; background: rgba(5, 12, 28, .88); border: 1px solid rgba(133, 194, 255, .28);
    border-radius: 14px; padding: 15px 16px; box-shadow: 0 12px 34px rgba(0,0,0,.3); backdrop-filter: blur(10px); }
  .map-info h1 { font-size: 17px; line-height: 1.35; margin: 0 0 8px; }
  .map-info p { color: #aebed2; font-size: 12px; line-height: 1.55; margin: 0; }
  .map-info .legend { height: 9px; margin: 12px 0 5px; border-radius: 8px;
    background: linear-gradient(90deg, rgb(8,14,36), rgb(35,116,133), rgb(232,216,90), rgb(245,137,55), rgb(255,244,210)); }
  .map-info .range { display: flex; justify-content: space-between; color: #91a5bc; font-size: 11px; }
</style>
"""
    panel = f"""
<aside class="map-info" aria-label="지도 설명">
  <h1>{title}</h1>
  <p>{count:,}개 유효 격자 · 약 {scale:.2f}m · cf_cvg &gt; 0<br>
  높이 = log1p(max(avg_rad, 0)) × 시각 배율<br>드래그 회전 · 휠 확대 · 격자에 마우스를 올려 값 확인</p>
  <div class="legend"></div>
  <div class="range"><span>0</span><span>{color_max:g}+ nW/sr/cm²</span></div>
</aside>
"""
    return css, panel


def build_map_html(
    frame: Any,
    boundary_feature: dict[str, Any],
    month: str,
    output: Path,
    scale: float,
    color_max: float,
    elevation_scale: float,
    offline: bool,
) -> None:
    try:
        import pydeck as pdk
    except ImportError as exc:
        raise RuntimeError("pydeck이 없습니다. `pip install -r requirements.txt`를 실행하세요.") from exc

    grid = pdk.Layer(
        "GridCellLayer",
        data=frame,
        id="viirs-grid-cells",
        get_position="[lon, lat]",
        get_elevation="log",
        get_color="[r, g, b, 225]",
        cell_size=scale,
        coverage=0.94,
        elevation_scale=elevation_scale,
        extruded=True,
        pickable=True,
        auto_highlight=True,
        highlight_color=[255, 255, 255, 110],
        material={"ambient": 0.45, "diffuse": 0.55, "shininess": 12, "specularColor": [80, 90, 110]},
    )
    border = pdk.Layer(
        "GeoJsonLayer",
        data=boundary_feature,
        id="north-korea-boundary",
        filled=False,
        stroked=True,
        get_line_color=[145, 205, 255, 210],
        line_width_min_pixels=1.5,
        pickable=False,
    )
    view = pdk.ViewState(
        longitude=127.15,
        latitude=40.15,
        zoom=6.15,
        min_zoom=4,
        max_zoom=14,
        pitch=52,
        bearing=-12,
    )
    tooltip = {
        "html": (
            "<b>VIIRS 월 야간조명</b><br>"
            "avg_rad: <b>{rad}</b> nW/sr/cm²<br>"
            "cf_cvg: <b>{cvg}</b>회<br>"
            "log1p 보정값: <b>{log}</b><br>"
            "좌하단: {lat}, {lon}"
        ),
        "style": {
            "backgroundColor": "rgba(5, 12, 28, 0.94)",
            "color": "#edf6ff",
            "fontSize": "12px",
            "border": "1px solid rgba(133, 194, 255, .35)",
        },
    }
    deck = pdk.Deck(
        layers=[grid, border],
        initial_view_state=view,
        tooltip=tooltip,
        map_provider="carto",
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    )
    document = deck.to_html(as_string=True, offline=offline, css_background_color="#050914")
    css, panel = _page_overlay(month, len(frame), color_max, scale)
    document = document.replace("</head>", f"{css}</head>", 1).replace("</body>", f"{panel}</body>", 1)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")


def build_map_data(
    frame: Any,
    boundary_feature: dict[str, Any],
    month: str,
    output: Path,
    scale: float,
    color_max: float,
    elevation_scale: float,
) -> None:
    """공통 플레이어가 읽는 북한 한정 월별 격자를 compact gzip JSON으로 기록한다."""
    columns = ["lon", "lat", "rad", "cvg", "log", "r", "g", "b"]
    records = frame.loc[:, columns].values.tolist()
    payload = {
        "month": month,
        "scope": "North Korea (USDOS/LSIB_SIMPLE/2017 country_co=KN)",
        "filter": "cf_cvg > 0",
        "scale_m": scale,
        "color_max": color_max,
        "elevation_scale": elevation_scale,
        "count": len(records),
        "columns": columns,
        "boundary": boundary_feature,
        "data": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output.with_suffix(output.suffix + f".{os.getpid()}.tmp")
    with gzip.open(temporary_output, "wt", encoding="utf-8", compresslevel=6) as stream:
        json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    temporary_output.replace(output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Google Earth Engine VIIRS 월 자료로 북한 야간조명 3D HTML을 생성합니다."
    )
    parser.add_argument("--month", default=DEFAULT_MONTH, help=f"대상 월 YYYY-MM (기본: {DEFAULT_MONTH})")
    parser.add_argument(
        "--project",
        default=os.getenv("GEE_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT"),
        help="Earth Engine에 등록된 Google Cloud 프로젝트 (또는 GEE_PROJECT)",
    )
    parser.add_argument("--output", type=Path, help="결과 HTML 경로")
    parser.add_argument("--data-output", type=Path, help="공통 플레이어용 compact JSON.gz 경로")
    parser.add_argument("--no-html", action="store_true", help="월별 HTML은 만들지 않고 압축 데이터만 생성")
    parser.add_argument("--scale", type=float, default=NATIVE_SCALE_METERS, help="요청 격자 크기(m)")
    parser.add_argument("--color-max", type=float, default=DEFAULT_COLOR_MAX, help="색상 상한 avg_rad")
    parser.add_argument(
        "--elevation-scale",
        type=float,
        default=DEFAULT_ELEVATION_SCALE,
        help="log1p 높이에 곱할 시각적 배율",
    )
    parser.add_argument("--save-raster", type=Path, help="중간 GeoTIFF도 이 경로에 보존")
    parser.add_argument(
        "--cdn",
        action="store_true",
        help="deck.gl JS를 HTML에 포함하지 않고 CDN에서 불러와 파일 크기를 줄임",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        load_runtime_environment()
        args = build_parser().parse_args(argv)
        parse_month(args.month)
        if args.scale <= 0:
            raise ValueError("--scale은 0보다 커야 합니다.")
        if args.color_max <= 0:
            raise ValueError("--color-max는 0보다 커야 합니다.")
        if args.elevation_scale <= 0:
            raise ValueError("--elevation-scale은 0보다 커야 합니다.")
        if args.no_html and not args.data_output:
            raise ValueError("--no-html에는 --data-output이 필요합니다.")

        output = args.output or Path("output") / f"north_korea_viirs_{args.month}.html"
        ee = initialize_earth_engine(args.project)
        print(f"[1/4] {args.month} VIIRS 영상과 북한 경계를 준비합니다.", flush=True)
        image, boundary = prepare_month_image(ee, args.month)

        with tempfile.TemporaryDirectory(prefix="poc5_viirs_") as temporary_dir:
            raster_path = Path(temporary_dir) / f"viirs_{args.month}.tif"
            print(f"[2/4] 약 {args.scale:.2f}m GeoTIFF를 내려받습니다.", flush=True)
            download_geotiff(image, boundary, args.scale, raster_path)
            if args.save_raster:
                args.save_raster.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(raster_path, args.save_raster)

            print("[3/4] cf_cvg > 0 격자와 log1p 높이·색상을 계산합니다.", flush=True)
            frame = raster_to_frame(raster_path, args.color_max)

        print(f"[4/4] {len(frame):,}개 북한 격자를 결과로 기록합니다.", flush=True)
        if args.data_output:
            build_map_data(
                frame=frame,
                boundary_feature=boundary,
                month=args.month,
                output=args.data_output,
                scale=args.scale,
                color_max=args.color_max,
                elevation_scale=args.elevation_scale,
            )
            print(f"압축 데이터: {args.data_output.resolve()} ({args.data_output.stat().st_size / 1024 / 1024:.1f} MiB)")
        if not args.no_html:
            build_map_html(
                frame=frame,
                boundary_feature=boundary,
                month=args.month,
                output=output,
                scale=args.scale,
                color_max=args.color_max,
                elevation_scale=args.elevation_scale,
                offline=not args.cdn,
            )
            print(f"HTML: {output.resolve()} ({output.stat().st_size / 1024 / 1024:.1f} MiB)")
        return 0
    except (argparse.ArgumentTypeError, RuntimeError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
