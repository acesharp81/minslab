"""한국 2000 / 중부원점(2010) TM(EPSG:5186) ↔ 경위도. 표준 라이브러리만 쓴다.

학구도 SHP 같은 국내 공간 자료는 이 좌표계(미터)로 온다. 한국 2000은 WGS84와 센티미터 안에서 같으므로 경위도로 바로 바꿔 쓴다.
식은 횡메르카토르의 표준 급수(Snyder)이며, 이 지역(경도 127도에서 ±3도 안)에서 1 mm 아래로 맞는다.
"""
from __future__ import annotations

import math

A = 6378137.0                 # GRS80 장반경
F = 1 / 298.257222101
E2 = F * (2 - F)
EP2 = E2 / (1 - E2)
LON0 = math.radians(127.0)
LAT0 = math.radians(38.0)
FALSE_E = 200000.0
FALSE_N = 600000.0


def _meridian_arc(phi: float) -> float:
    e4, e6 = E2 * E2, E2 ** 3
    return A * ((1 - E2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi
                - (3 * E2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * math.sin(2 * phi)
                + (15 * e4 / 256 + 45 * e6 / 1024) * math.sin(4 * phi)
                - (35 * e6 / 3072) * math.sin(6 * phi))


_M0 = _meridian_arc(LAT0)


def to_tm(lon: float, lat: float) -> tuple[float, float]:
    """경위도(도) → TM 미터 (x=동쪽, y=북쪽)."""
    phi, lam = math.radians(lat), math.radians(lon)
    n = A / math.sqrt(1 - E2 * math.sin(phi) ** 2)
    t = math.tan(phi) ** 2
    c = EP2 * math.cos(phi) ** 2
    a = (lam - LON0) * math.cos(phi)
    x = FALSE_E + n * (a + (1 - t + c) * a ** 3 / 6 + (5 - 18 * t + t * t + 72 * c - 58 * EP2) * a ** 5 / 120)
    y = FALSE_N + (_meridian_arc(phi) - _M0 + n * math.tan(phi) * (
        a * a / 2 + (5 - t + 9 * c + 4 * c * c) * a ** 4 / 24
        + (61 - 58 * t + t * t + 600 * c - 330 * EP2) * a ** 6 / 720))
    return x, y


def from_tm(x: float, y: float) -> tuple[float, float]:
    """TM 미터 → 경위도(도). (경도, 위도) 순서."""
    e1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))
    mu = (_M0 + (y - FALSE_N)) / (A * (1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    c1 = EP2 * math.cos(phi1) ** 2
    t1 = math.tan(phi1) ** 2
    n1 = A / math.sqrt(1 - E2 * math.sin(phi1) ** 2)
    r1 = A * (1 - E2) / (1 - E2 * math.sin(phi1) ** 2) ** 1.5
    d = (x - FALSE_E) / n1
    phi = phi1 - (n1 * math.tan(phi1) / r1) * (
        d * d / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * EP2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * EP2 - 3 * c1 * c1) * d ** 6 / 720)
    lam = LON0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6
                  + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * EP2 + 24 * t1 * t1) * d ** 5 / 120) / math.cos(phi1)
    return math.degrees(lam), math.degrees(phi)
