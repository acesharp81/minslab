import struct
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT  # noqa: F401  (tools/ 를 sys.path 에 넣는다)

from regiontools import shp

SQUARE_CW = [(0, 0), (0, 10), (10, 10), (10, 0), (0, 0)]            # ESRI 바깥 고리: 시계 방향
HOLE_CCW = [(4, 4), (6, 4), (6, 6), (4, 6), (4, 4)]                  # 구멍: 반시계
FAR = [(100, 100), (100, 110), (110, 110), (110, 100), (100, 100)]


def write_shp(path, polygons):
    """polygons: [[ring, ring, ...], ...] 을 폴리곤 SHP(type 5)로 쓴다. 시험용 최소 작성기."""
    recs = b""
    xs = [x for rings in polygons for r in rings for x, _ in r]
    ys = [y for rings in polygons for r in rings for _, y in r]
    for n, rings in enumerate(polygons, 1):
        pts = [p for r in rings for p in r]
        parts, off = [], 0
        for r in rings:
            parts.append(off)
            off += len(r)
        bx = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
        body = struct.pack("<i4dii", 5, *bx, len(rings), len(pts)) + struct.pack(f"<{len(parts)}i", *parts)
        body += b"".join(struct.pack("<2d", *p) for p in pts)
        recs += struct.pack(">ii", n, len(body) // 2) + body
    total = 100 + len(recs)
    head = struct.pack(">i5ii", 9994, 0, 0, 0, 0, 0, total // 2) + struct.pack("<ii4d", 1000, 5, min(xs), min(ys), max(xs), max(ys)) + b"\0" * 32
    Path(path).write_bytes(head + recs)


def write_dbf(path, rows, encoding="euc-kr"):
    """rows: [{'ID': '1', 'NAME': '한글'}...] 모두 문자 필드. 시험용 최소 작성기."""
    names = list(rows[0])
    width = {n: max(len(str(r[n]).encode(encoding)) for r in rows) + 2 for n in names}
    hl = 32 + 32 * len(names) + 1
    rl = 1 + sum(width.values())
    head = struct.pack("<BBBBIHH", 3, 26, 10, 4, len(rows), hl, rl) + b"\0" * 20
    fields = b"".join(n.encode("ascii").ljust(11, b"\0") + b"C" + b"\0" * 4 + bytes([width[n]]) + b"\0" * 15 for n in names)
    body = b"".join(b" " + b"".join(str(r[n]).encode(encoding).ljust(width[n], b" ") for n in names) for r in rows)
    Path(path).write_bytes(head + fields + b"\r" + body)


class Dbf(unittest.TestCase):
    def test_reads_korean_text_in_euc_kr_and_trims_padding(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.dbf"
            write_dbf(p, [{"ID": "Z1", "NAME": "인천당산초통학구역"}, {"ID": "Z2", "NAME": "소양초"}])
            rows = shp.read_dbf(p)
            self.assertEqual([r["NAME"] for r in rows], ["인천당산초통학구역", "소양초"])
            self.assertEqual(rows[1]["ID"], "Z2")

    def test_deleted_records_are_kept_and_flagged_so_indexes_line_up_with_the_shp(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.dbf"
            write_dbf(p, [{"ID": "1"}, {"ID": "2"}])
            raw = bytearray(p.read_bytes())
            raw[32 + 32 + 1] = ord("*")          # 첫 레코드의 삭제 표시(헤더 길이 = 32+32+1 바로 다음 바이트가 첫 레코드)
            p.write_bytes(bytes(raw))
            rows = shp.read_dbf(p)
            self.assertEqual([r["_deleted"] for r in rows], [True, False])
            self.assertEqual(len(rows), 2)


class Polygons(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "a.shp"
        write_shp(self.path, [[SQUARE_CW, HOLE_CCW], [FAR]])

    def tearDown(self):
        self.tmp.cleanup()

    def test_iterates_records_with_index_bbox_and_rings(self):
        recs = list(shp.iter_polygons(self.path))
        self.assertEqual([r[0] for r in recs], [0, 1])
        self.assertEqual(recs[0][1], (0.0, 0.0, 10.0, 10.0))
        self.assertEqual(len(recs[0][2]), 2)
        self.assertEqual(recs[1][2][0][0], (100.0, 100.0))

    def test_bbox_filter_skips_records_without_reading_points(self):
        near = list(shp.iter_polygons(self.path, bbox=(5, 5, 6, 6)))
        self.assertEqual([r[0] for r in near], [0])
        self.assertEqual(list(shp.iter_polygons(self.path, bbox=(50, 50, 60, 60))), [])
        both = list(shp.iter_polygons(self.path, bbox=(0, 0, 120, 120)))
        self.assertEqual([r[0] for r in both], [0, 1])      # 번호는 필터와 상관없이 파일 안의 순번

    def test_contains_uses_even_odd_so_holes_are_empty(self):
        rings = list(shp.iter_polygons(self.path))[0][2]
        self.assertTrue(shp.contains(rings, (1, 1)))
        self.assertFalse(shp.contains(rings, (5, 5)))       # 구멍
        self.assertFalse(shp.contains(rings, (20, 20)))

    def test_outer_rings_drop_holes(self):
        rings = list(shp.iter_polygons(self.path))[0][2]
        outers = shp.outer_rings(rings)
        self.assertEqual(len(outers), 1)
        self.assertEqual(outers[0][0], (0.0, 0.0))

    def test_rejects_non_polygon_files(self):
        raw = bytearray(self.path.read_bytes())
        raw[32:36] = struct.pack("<i", 1)                   # 점(point) 형식
        self.path.write_bytes(bytes(raw))
        with self.assertRaises(ValueError):
            list(shp.iter_polygons(self.path))


if __name__ == "__main__":
    unittest.main()
