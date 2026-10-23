import math
import unittest

from ascii_tree.geometry import generate_tree
from ascii_tree.projection import Point4, Projector, View, project_4d, rotate_xw


class GeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_seed_determinism_and_variation(self):
        self.assertEqual(self.tree, generate_tree(42))
        self.assertEqual(3, len({generate_tree(seed).segments for seed in (42, 43, 2026)}))

    def test_graph_connected_acyclic_finite_and_positive(self):
        for seed in (42, 43, 2026):
            tree = generate_tree(seed)
            self.assertEqual(1, sum(s.parent is None for s in tree.segments))
            self.assertLess(len(tree.segments), 2000)
            for i, segment in enumerate(tree.segments):
                if segment.parent is not None:
                    self.assertLess(segment.parent, i)
                    self.assertGreaterEqual(segment.parent, 0)
                    self.assertEqual(tree.segments[segment.parent].end, segment.start)
                    self.assertLessEqual(segment.radius_start, tree.segments[segment.parent].radius_end + 1e-9)
                self.assertGreater(math.dist((segment.start.x, segment.start.y, segment.start.z),
                                             (segment.end.x, segment.end.y, segment.end.z)), 0)
                self.assertGreater(segment.radius_end, 0)
                self.assertGreaterEqual(segment.radius_start, segment.radius_end)
                for p in (segment.start, segment.end):
                    self.assertTrue(all(math.isfinite(v) for v in (p.x, p.y, p.z, p.w)))
                self.assertGreater(segment.end.w, segment.start.w)
            for leaf in tree.leaves:
                self.assertTrue(all(math.isfinite(v) for v in
                                    (leaf.point.x, leaf.point.y, leaf.point.z, leaf.point.w, leaf.size)))
                self.assertTrue(0 <= leaf.branch < len(tree.segments))

    def test_tapering_and_nonplanar_geometry(self):
        trunk = [s for s in self.tree.segments if s.order == 0]
        self.assertGreater(trunk[0].radius_start, 10 * trunk[-1].radius_end)
        self.assertTrue(all(a.radius_end == b.radius_start for a, b in zip(trunk, trunk[1:])))
        points = [s.end for s in self.tree.segments]
        self.assertGreater(max(p.z for p in points) - min(p.z for p in points), 4)
        self.assertGreater(max(p.w for p in points) - min(p.w for p in points), 3)
        # Not merely a tilted plane: scalar triple product of three vertex vectors.
        a, b, c = (self.tree.segments[i].end for i in (7, 80, 400))
        determinant = a.x * (b.y*c.z-b.z*c.y) - a.y * (b.x*c.z-b.z*c.x) + a.z * (b.x*c.y-b.y*c.x)
        self.assertGreater(abs(determinant), 1)

    def test_xw_basis_rotation(self):
        x = rotate_xw(Point4(1, 0, 0, 0), math.pi / 2)
        w = rotate_xw(Point4(0, 0, 0, 1), math.pi / 2)
        self.assertAlmostEqual(x.x, 0)
        self.assertAlmostEqual(x.w, 1)
        self.assertAlmostEqual(w.x, -1)
        self.assertAlmostEqual(w.w, 0)
        point = rotate_xw(Point4(1, 2, 3, 4), math.pi / 2)
        self.assertAlmostEqual(point.x, -4)
        self.assertEqual((point.y, point.z), (2, 3))

    def test_xw_norm_inverse_and_determinant(self):
        p = Point4(1.3, -2.1, 0.4, 3.8)
        q = rotate_xw(p, 0.73)
        r = rotate_xw(q, -0.73)
        self.assertAlmostEqual(sum(getattr(p, a)**2 for a in "xyzw"),
                               sum(getattr(q, a)**2 for a in "xyzw"))
        for axis in "xyzw":
            self.assertAlmostEqual(getattr(p, axis), getattr(r, axis))
        c, s = math.cos(0.73), math.sin(0.73)
        self.assertAlmostEqual(c*c + s*s, 1)  # determinant of the nontrivial XW block

    def test_4d_then_3d_projection_numeric(self):
        tree = self.tree
        p = Point4(1, tree.center[1] + 2, 3, 4)
        view = View("4d", yaw=0, pitch=0, angle4d=90)
        projector = Projector(tree, 100, 40, view)
        actual = projector(p)
        # XW maps (1,2,3,4) to (-4,2,3,1), then 18/(18-1).
        factor4 = 18 / 17
        factor3 = 25 / (25 - 3 * factor4)
        self.assertAlmostEqual(actual.x, 49.5 - 4 * factor4 * projector.scale * factor3 / 0.5)
        self.assertAlmostEqual(actual.y, 19.5 - 2 * factor4 * projector.scale * factor3)

    def test_near_planes_and_invalid_values(self):
        self.assertIsNone(project_4d(Point4(1, 2, 3, 18)))
        self.assertIsNone(project_4d(Point4(1, 2, 3, 18.1)))
        self.assertIsNone(project_4d(Point4(1, 2, 3, math.nan)))
        projector = Projector(self.tree, 80, 30, View(yaw=0, pitch=0))
        self.assertIsNone(projector(Point4(1, 2, 25, 0)))
        self.assertIsNone(projector(Point4(math.inf, 2, 3, 0)))
        for changes in ({"zoom": 0}, {"zoom": 9}, {"aspect": 0}, {"yaw": math.nan}, {"mode": "5d"}):
            with self.assertRaises(ValueError):
                View(**changes)


if __name__ == "__main__":
    unittest.main()
