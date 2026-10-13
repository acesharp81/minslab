import math
import unittest

from helpers import ROOT  # noqa: F401  (tools/ 를 sys.path 에 넣는다)

from regiontools import geo

SQ = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
HOLE = [[0.4, 0.4], [0.6, 0.4], [0.6, 0.6], [0.4, 0.6]]


class PointInPolygon(unittest.TestCase):
    def test_ring_open_and_closed(self):
        self.assertTrue(geo.point_in_ring((0.5, 0.5), SQ))
        self.assertFalse(geo.point_in_ring((1.5, 0.5), SQ))
        self.assertTrue(geo.point_in_ring((0.5, 0.5), SQ + [SQ[0]]))

    def test_polygon_with_hole(self):
        self.assertTrue(geo.point_in_polygon((0.2, 0.2), [SQ, HOLE]))
        self.assertFalse(geo.point_in_polygon((0.5, 0.5), [SQ, HOLE]))

    def test_geometry_polygon_and_multipolygon(self):
        poly = {"type": "Polygon", "coordinates": [SQ]}
        multi = {"type": "MultiPolygon", "coordinates": [[SQ], [[[2, 0], [3, 0], [3, 1], [2, 1]]]]}
        self.assertTrue(geo.point_in_geometry((0.5, 0.5), poly))
        self.assertTrue(geo.point_in_geometry((2.5, 0.5), multi))
        self.assertFalse(geo.point_in_geometry((1.5, 0.5), multi))


class Hull(unittest.TestCase):
    def test_convex_hull_drops_interior_points(self):
        pts = SQ + [[0.5, 0.5], [0.2, 0.7], [1.0, 0.5]]
        hull = geo.convex_hull(pts)
        self.assertEqual(sorted(map(tuple, hull)), sorted(map(tuple, SQ)))
        # 반시계 방향(넓이 양수)
        area2 = sum(hull[i][0] * hull[(i + 1) % len(hull)][1] - hull[(i + 1) % len(hull)][0] * hull[i][1]
                    for i in range(len(hull)))
        self.assertGreater(area2, 0)

    def test_simplify_ring_limits_points(self):
        circle = [[math.cos(2 * math.pi * i / 400), math.sin(2 * math.pi * i / 400)] for i in range(400)]
        out = geo.simplify_ring(circle, max_points=100)
        self.assertLessEqual(len(out), 100)
        self.assertGreaterEqual(len(out), 3)
        originals = {tuple(p) for p in circle}
        self.assertTrue(all(tuple(p) in originals for p in out))

    def test_simplify_keeps_small_ring(self):
        self.assertEqual(geo.simplify_ring(SQ, max_points=100), SQ)


class Rounding(unittest.TestCase):
    def test_clean_ring_rounds_and_dedupes(self):
        ring = [[126.1234564, 35.1], [126.1234561, 35.1], [126.2, 35.1], [126.2, 35.2], [126.1234564, 35.1]]
        self.assertEqual(geo.clean_ring(ring), [[126.123456, 35.1], [126.2, 35.1], [126.2, 35.2]])
        closed = geo.clean_ring(ring, closed=True)
        self.assertEqual(closed[0], closed[-1])
        self.assertEqual(len(closed), 4)

    def test_clean_ring_degenerate(self):
        self.assertIsNone(geo.clean_ring([[1, 1], [1, 1], [2, 2]]))

    def test_round_pt(self):
        self.assertEqual(geo.round_pt([126.12345678, 35.98765432]), [126.123457, 35.987654])


class AreaCentroid(unittest.TestCase):
    def test_ring_area_m2(self):
        d = 0.001
        ring = [[126.0, 35.0], [126.0 + d, 35.0], [126.0 + d, 35.0 + d], [126.0, 35.0 + d]]
        expected = (111320 * math.cos(math.radians(35.0005)) * d) * (110540 * d)
        self.assertAlmostEqual(geo.ring_area_m2(ring), expected, delta=expected * 0.01)

    def test_centroids(self):
        self.assertEqual(geo.ring_centroid(SQ), (0.5, 0.5))
        multi = {"type": "MultiPolygon", "coordinates": [[SQ], [[[2, 0], [3, 0], [3, 1], [2, 1]]]]}
        cx, cy = geo.geometry_centroid(multi)
        self.assertAlmostEqual(cx, 1.5)
        self.assertAlmostEqual(cy, 0.5)

    def test_centroid_precision_at_real_coordinates(self):
        # 경위도 절대값으로 계산하면 상쇄 오차로 중심이 수 m~수십 m 틀어진다(건물 크기 링)
        x0, y0, d = 126.786452, 35.149181, 0.00015
        ring = [[x0, y0], [x0 + d, y0], [x0 + d, y0 + d / 2], [x0 + d / 2, y0 + d / 2], [x0 + d / 2, y0 + d],
                [x0, y0 + d], [x0, y0]]
        cx, cy = geo.ring_centroid(ring)
        # L자 모양(넓이 3/4 d²)의 정확한 중심: (5/12 d, 5/12 d)
        self.assertAlmostEqual(cx, x0 + 5 * d / 12, delta=1e-9)
        self.assertAlmostEqual(cy, y0 + 5 * d / 12, delta=1e-9)
        self.assertAlmostEqual(geo.ring_area_m2(ring),
                               0.75 * d * d * 111320 * math.cos(math.radians(y0 + d * 0.4)) * 110540, delta=0.5)

    def test_geometry_area_subtracts_holes(self):
        a_full = geo.geometry_area_m2({"type": "Polygon", "coordinates": [SQ]})
        a_hole = geo.geometry_area_m2({"type": "Polygon", "coordinates": [SQ, HOLE]})
        self.assertAlmostEqual(a_hole / a_full, 0.96, places=2)


class Boxes(unittest.TestCase):
    def test_bbox_expand_center(self):
        b = geo.bbox_of([[1, 2], [3, 5], [2, 4]])
        self.assertEqual(b, (1, 2, 3, 5))
        self.assertEqual(geo.expand_bbox(b, 0.5), (0.5, 1.5, 3.5, 5.5))
        self.assertEqual(geo.bbox_center(b), (2.0, 3.5))

    def test_outer_rings_and_points(self):
        multi = {"type": "MultiPolygon", "coordinates": [[SQ, HOLE], [[[2, 0], [3, 0], [3, 1]]]]}
        self.assertEqual(len(geo.outer_rings(multi)), 2)
        self.assertEqual(len(list(geo.geometry_points(multi))), 11)


if __name__ == "__main__":
    unittest.main()
