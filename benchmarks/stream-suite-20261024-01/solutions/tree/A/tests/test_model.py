import math
import unittest

from ascii_tree.model import generate_tree
from ascii_tree.projection import Point4, project_4d, rotate_xw


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_seed_determinism(self):
        self.assertEqual(self.tree, generate_tree(42))

    def test_multiple_seeds_have_distinct_geometry(self):
        trees = [generate_tree(seed) for seed in (1, 42, 43, 2026)]
        self.assertEqual(len({tree.segments for tree in trees}), 4)

    def test_one_connected_acyclic_graph(self):
        segments = self.tree.segments
        roots = []
        for index, segment in enumerate(segments):
            if segment.parent is None:
                roots.append(index)
            else:
                self.assertLess(segment.parent, index)
                self.assertEqual(segment.start, segments[segment.parent].end)
                self.assertLessEqual(segment.radius_start, segments[segment.parent].radius_end + 1e-12)
        self.assertEqual(roots, [0])

    def test_positive_lengths_radii_finite_coordinates_and_bounded_recursion(self):
        for seed in (0, 1, -1, 42, 43, 99999):
            tree = generate_tree(seed)
            self.assertLessEqual(len(tree.segments), 3500)
            for s in tree.segments:
                self.assertGreater(math.dist((s.start.x, s.start.y, s.start.z),
                                             (s.end.x, s.end.y, s.end.z)), 0)
                self.assertGreater(s.radius_end, 0)
                self.assertGreaterEqual(s.radius_start, s.radius_end)
                self.assertLessEqual(s.order, 4)
                for p in (s.start, s.end):
                    self.assertTrue(all(math.isfinite(v) for v in (p.x, p.y, p.z, p.w)))
                    self.assertLess(p.w, 20)
            self.assertTrue(all(math.isfinite(v) for leaf in tree.leaves
                                for v in (leaf.point.x, leaf.point.y, leaf.point.z, leaf.point.w, leaf.size)))

    def test_real_spatial_volume_and_variable_w(self):
        points = [s.end for s in self.tree.segments]
        self.assertGreater(max(p.z for p in points) - min(p.z for p in points), 7)
        self.assertGreater(max(p.w for p in points) - min(p.w for p in points), 3)
        # Spatial directions are not contained in a single XY or XZ plane.
        self.assertGreater(len({round(p.z, 2) for p in points}), 100)

    def test_trunk_has_visible_taper_and_multiple_orders(self):
        trunk = [s for s in self.tree.segments if s.order == 0]
        self.assertGreater(trunk[0].radius_start, trunk[-1].radius_end * 10)
        self.assertEqual({s.order for s in self.tree.segments}, {0, 1, 2, 3, 4})

    def test_w_grows_along_every_branch(self):
        for segment in self.tree.segments:
            self.assertGreater(segment.end.w, segment.start.w)


class HyperRotationTests(unittest.TestCase):
    def test_xw_basis_actually_mixes_components(self):
        x = rotate_xw(Point4(1, 0, 0, 0), math.pi / 2)
        w = rotate_xw(Point4(0, 0, 0, 1), math.pi / 2)
        self.assertAlmostEqual(x.x, 0)
        self.assertAlmostEqual(x.w, 1)
        self.assertAlmostEqual(w.x, -1)
        self.assertAlmostEqual(w.w, 0)

    def test_orthonormal_matrix_and_positive_determinant(self):
        angle = 0.73
        c, s = math.cos(angle), math.sin(angle)
        # The XW block is [[c,-s],[s,c]]; Y,Z are identity.
        self.assertAlmostEqual(c * c + s * s, 1)
        self.assertAlmostEqual(c * (-s) + s * c, 0)
        self.assertAlmostEqual(c * c - (-s) * s, 1)
        p = Point4(2, 3, -4, 5)
        q = rotate_xw(p, angle)
        self.assertEqual((q.y, q.z), (p.y, p.z))
        self.assertAlmostEqual(sum(v * v for v in (p.x, p.y, p.z, p.w)),
                               sum(v * v for v in (q.x, q.y, q.z, q.w)))
        back = rotate_xw(q, -angle)
        for a, b in zip((p.x, p.y, p.z, p.w), (back.x, back.y, back.z, back.w)):
            self.assertAlmostEqual(a, b)

    def test_4d_perspective_and_near_plane_guard(self):
        self.assertEqual(project_4d(Point4(2, 4, 6, 9)), (4, 8, 12))
        self.assertIsNone(project_4d(Point4(1, 1, 1, 18)))
        self.assertIsNone(project_4d(Point4(1, 1, 1, 20)))
        self.assertIsNone(project_4d(Point4(math.nan, 1, 1, 0)))
