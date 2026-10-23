import math
import random
import unittest

from ascii_tree.math4d import Point4, perspective4, rotate3, rotate_xw, xw_matrix
from ascii_tree.model import generate_tree


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_seed_determinism(self):
        self.assertEqual(self.tree, generate_tree(42))

    def test_seeds_change_geometry(self):
        trees = [generate_tree(seed) for seed in (42, 43, 137)]
        self.assertEqual(len({t.segments for t in trees}), 3)

    def test_generator_does_not_change_global_rng(self):
        state = random.getstate()
        generate_tree(9)
        self.assertEqual(state, random.getstate())

    def test_connected_finite_positive_graph(self):
        roots = 0
        for i, s in enumerate(self.tree.segments):
            self.assertTrue(all(math.isfinite(v) for p in (s.start, s.end) for v in p.values()))
            self.assertGreater(math.dist(s.start.values()[:3], s.end.values()[:3]), 0)
            self.assertGreaterEqual(s.radius_start, s.radius_end)
            self.assertGreater(s.radius_end, 0)
            if s.parent is None:
                roots += 1
                self.assertEqual(i, 0)
            else:
                self.assertLess(s.parent, i)
                self.assertGreaterEqual(s.parent, 0)
                self.assertEqual(s.start, self.tree.segments[s.parent].end)
            self.assertGreater(s.end.w, s.start.w)
        self.assertEqual(roots, 1)

    def test_branch_orders_and_bounded_generation(self):
        self.assertEqual({s.order for s in self.tree.segments}, {0, 1, 2, 3})
        self.assertTrue(300 < len(self.tree.segments) <= 3000)

    def test_base_flare_and_taper(self):
        trunk = [s for s in self.tree.segments if s.order == 0]
        self.assertGreater(trunk[0].radius_start, trunk[0].radius_end)
        self.assertGreater(trunk[0].radius_start / trunk[-1].radius_end, 10)

    def test_genuinely_spatial_and_variable_w(self):
        points = [s.end for s in self.tree.segments]
        self.assertGreater(max(p.z for p in points) - min(p.z for p in points), 4)
        self.assertGreater(max(p.w for p in points) - min(p.w for p in points), 4)

    def test_leaves_are_attached_and_finite(self):
        for leaf in self.tree.leaves:
            self.assertTrue(all(math.isfinite(v) for v in leaf.position.values()))
            self.assertTrue(0 <= leaf.parent < len(self.tree.segments))
            self.assertGreater(leaf.radius, 0)


class MathTests(unittest.TestCase):
    def test_xw_known_quarter_turn(self):
        p = rotate_xw(Point4(1, 2, 3, 4), 90)
        for actual, expected in zip(p.values(), (-4, 2, 3, 1)):
            self.assertAlmostEqual(actual, expected)

    def test_rotation_matrix_is_non_degenerate_and_orthogonal(self):
        m = xw_matrix(37)
        self.assertNotEqual(m[0][3], 0)
        self.assertNotEqual(m[3][0], 0)
        self.assertAlmostEqual(m[0][0] * m[3][3] - m[0][3] * m[3][0], 1)
        for i in range(4):
            for j in range(4):
                self.assertAlmostEqual(sum(m[k][i] * m[k][j] for k in range(4)), float(i == j))

    def test_xw_norm_inverse_and_matrix_agree(self):
        p = Point4(3, -4, 2, 7)
        for angle in (-350, 0, 28, 90, 180, 379):
            rotated = rotate_xw(p, angle)
            matrix_result = tuple(sum(a * b for a, b in zip(row, p.values())) for row in xw_matrix(angle))
            for actual, expected in zip(rotated.values(), matrix_result):
                self.assertAlmostEqual(actual, expected)
            self.assertAlmostEqual(sum(v * v for v in p.values()), sum(v * v for v in rotated.values()))
            for actual, expected in zip(rotate_xw(rotated, -angle).values(), p.values()):
                self.assertAlmostEqual(actual, expected)

    def test_perspective4_is_real_and_near_plane_is_safe(self):
        self.assertEqual(perspective4(Point4(1, 2, 3, 5), 10), (2, 4, 6))
        for w in (10, 11, 9.99, math.nan, math.inf):
            self.assertIsNone(perspective4(Point4(1, 2, 3, w), 10))

    def test_3d_rotation_moves_depth(self):
        x, y, z = rotate3((1, 0, 0), 90, 0)
        self.assertAlmostEqual(x, 0)
        self.assertAlmostEqual(y, 0)
        self.assertAlmostEqual(z, -1)
