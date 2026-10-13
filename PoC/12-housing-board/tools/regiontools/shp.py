"""폴리곤 SHP · DBF 읽기(표준 라이브러리만). 학구도처럼 큰 전국 파일에서 필요한 구역만 골라 읽는다.

SHP 는 레코드를 차례로 건너뛰며 읽고, 찾는 범위(bbox)와 겹치지 않는 레코드는 점을 읽지 않는다(54 MB 전국 파일도 몇 초).
DBF 의 레코드 순서는 SHP 와 같아서, 둘의 번호(0부터)가 같은 구역을 가리킨다. 삭제 표시된 레코드도 번호를 지키려고 남기고 `_deleted` 로 알린다.
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterator, Sequence

POLYGON = 5


def read_dbf(path, encoding: str = "euc-kr") -> list[dict]:
    """모든 필드를 문자열로 읽는다(앞뒤 공백 제거). 레코드마다 `_deleted` 가 붙는다."""
    b = Path(path).read_bytes()
    n, header_len, rec_len = struct.unpack("<IHH", b[4:12])
    fields, off = [], 32
    while b[off] != 0x0D:
        name = b[off:off + 11].split(b"\0")[0].decode("ascii", "replace")
        fields.append((name, b[off + 16]))
        off += 32
    rows, pos = [], header_len
    for _ in range(n):
        rec = b[pos:pos + rec_len]
        pos += rec_len
        row, q = {}, 1
        for name, width in fields:
            row[name] = rec[q:q + width].decode(encoding, "replace").strip()
            q += width
        row["_deleted"] = rec[:1] == b"*"
        rows.append(row)
    return rows


def iter_polygons(path, bbox: Sequence[float] | None = None) -> Iterator[tuple[int, tuple, list[list[tuple]]]]:
    """(레코드 번호, (xmin, ymin, xmax, ymax), 고리 목록)을 차례로 준다. bbox 와 겹치는 레코드만 점을 읽는다."""
    with open(path, "rb") as f:
        head = f.read(100)
        if len(head) < 100 or struct.unpack(">i", head[:4])[0] != 9994:
            raise ValueError("SHP 파일이 아님")
        if struct.unpack("<i", head[32:36])[0] != POLYGON:
            raise ValueError("폴리곤 SHP 가 아님")
        index = 0
        while True:
            h = f.read(8)
            if len(h) < 8:
                return
            _, words = struct.unpack(">ii", h)
            data = f.read(words * 2)
            if struct.unpack("<i", data[:4])[0] == POLYGON:   # 빈 레코드(type 0)는 건너뛴다
                box = struct.unpack("<4d", data[4:36])
                if bbox is None or not (box[2] < bbox[0] or box[0] > bbox[2] or box[3] < bbox[1] or box[1] > bbox[3]):
                    parts_n, pts_n = struct.unpack("<ii", data[36:44])
                    parts = struct.unpack(f"<{parts_n}i", data[44:44 + 4 * parts_n])
                    o = 44 + 4 * parts_n
                    flat = struct.unpack(f"<{2 * pts_n}d", data[o:o + 16 * pts_n])
                    pts = [(flat[2 * i], flat[2 * i + 1]) for i in range(pts_n)]
                    bounds = list(parts) + [pts_n]
                    yield index, box, [pts[bounds[i]:bounds[i + 1]] for i in range(parts_n)]
            index += 1


def contains(rings: Sequence[Sequence[tuple]], pt: Sequence[float]) -> bool:
    """짝홀 규칙: 점이 고리를 홀수 번 감싸면 안(구멍·여러 바깥 고리 모두 처리)."""
    x, y = pt[0], pt[1]
    inside = False
    for ring in rings:
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i][:2]
            xj, yj = ring[j][:2]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
    return inside


def _signed_area(ring: Sequence[tuple]) -> float:
    return sum(ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1] for i in range(len(ring))) / 2


def outer_rings(rings: Sequence[Sequence[tuple]]) -> list[list[tuple]]:
    """ESRI 규칙(바깥 고리는 시계 방향, 구멍은 반시계)으로 바깥 고리만 남긴다."""
    return [list(r) for r in rings if len(r) >= 4 and _signed_area(r) < 0]
