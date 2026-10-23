import math
import unittest

from ascii_tree.geometry import Camera, project_4d, rotate_camera, rotate_xw, xw_matrix
from ascii_tree.model import generate_tree


class ModelTests(unittest.TestCase):
    def test_seed_determinism_and_variety(self):
        self.assertEqual(generate_tree(42), generate_tree(42))
        trees = [generate_tree(seed) for seed in (7, 42, 99)]
        self.assertEqual(len({tree.segments for tree in trees}), 3)

    def test_graph_connected_positive_finite_and_tapered(self):
        for seed in (0, 7, 42, 99, -10):
            tree = generate_tree(seed)
            self.assertLess(len(tree.segments), 2500)
            self.assertGreater(len(tree.segments), 100)
            self.assertEqual(sum(s.parent is None for s in tree.segments), 1)
            for index, segment in enumerate(tree.segments):
                self.assertTrue(all(math.isfinite(v) for v in segment.start + segment.end))
                self.assertGreater(math.dist(segment.start[:3], segment.end[:3]), 0)
                self.assertGreater(segment.radius_end, 0)
                self.assertGreaterEqual(segment.radius_start, segment.radius_end)
                self.assertGreater(segment.end[3], segment.start[3])
                if segment.parent is not None:
                    self.assertLess(segment.parent, index)  # no cycles; path reaches root
                    parent = tree.segments[segment.parent]
                    self.assertEqual(segment.start, parent.end)
                    self.assertLessEqual(segment.radius_start, parent.radius_end + 1e-12)
            trunk = [s for s in tree.segments if s.order == 0]
            self.assertGreater(trunk[0].radius_start, trunk[-1].radius_end * 10)
            z = [s.end[2] for s in tree.segments]
            w = [s.end[3] for s in tree.segments]
            self.assertGreater(max(z) - min(z), 4)
            self.assertGreater(max(w) - min(w), 4)
            self.assertEqual({s.order for s in tree.segments}, {0, 1, 2, 3})
            self.assertGreater(len(tree.leaves), 100)
            self.assertTrue(all(math.isfinite(v) for leaf in tree.leaves for v in leaf.position))


class GeometryTests(unittest.TestCase):
    def test_xw_rotation_exact_quarter_turn(self):
        actual = rotate_xw((2, 3, 4, 5), 90)
        for a, b in zip(actual, (-5, 3, 4, 2)):
            self.assertAlmostEqual(a, b)

    def test_xw_matrix_orthonormal_and_inverse(self):
        for angle in (0, 15, 90, 145, 359):
            matrix = xw_matrix(angle)
            for i in range(4):
                for j in range(4):
                    dot = sum(matrix[k][i] * matrix[k][j] for k in range(4))
                    self.assertAlmostEqual(dot, int(i == j))
            p = (2.4, -1.0, 5.0, 3.2)
            q = rotate_xw(p, angle)
            self.assertAlmostEqual(sum(v*v for v in p), sum(v*v for v in q))
            for a, b in zip(rotate_xw(q, -angle), p):
                self.assertAlmostEqual(a, b)
            for a, row in zip(q, matrix):
                self.assertAlmostEqual(a, sum(x*y for x, y in zip(p, row)))
        self.assertNotEqual(xw_matrix(35)[0][3], 0)
        self.assertNotEqual(xw_matrix(35)[3][0], 0)

    def test_perspective_near_plane_guard(self):
        for point in ((1, 2, 3, 18), (1, 2, 3, 40), (1, 2, 3, -30)):
            self.assertTrue(all(math.isfinite(v) for v in project_4d(point, 0)))
        self.assertEqual(project_4d((1, 2, 3, 0), 0), (1, 2, 3))

    def test_camera_rotation_moves_z_into_x(self):
        x, y, z = rotate_camera((0, 2, 3), 90, 0)
        self.assertAlmostEqual(x, 3)
        self.assertAlmostEqual(y, 2)
        self.assertAlmostEqual(z, 0)

    def test_camera_validation(self):
        for kwargs in ({"width": 0}, {"height": 501}, {"yaw": math.nan},
                       {"zoom": 0}, {"aspect": 0}, {"mode": "5d"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Camera(**kwargs)


if __name__ == "__main__":
    unittest.main()
