import itertools
import math
import random
import unittest

from ascii_tree.geometry import Point4, generate_tree
from ascii_tree.math4d import (NEAR, W_EYE, camera_point, project_4d,
                               project_camera, rotate_xw, rotation_xw)


class GeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_seed_determinism_and_local_random_state(self):
        before = random.getstate()
        self.assertEqual(self.tree, generate_tree(42))
        self.assertEqual(before, random.getstate())

    def test_seeds_give_different_geometry(self):
        self.assertEqual(len({generate_tree(seed).nodes for seed in (7, 42, 43, -1)}), 4)

    def test_graph_connected_finite_positive_and_bounded(self):
        tree = self.tree
        self.assertLess(len(tree.segments), 1500)
        self.assertEqual(len(tree.nodes), len(tree.segments) + 1)
        reached = {0}
        for i, s in enumerate(tree.segments):
            self.assertIn(s.start, reached)
            self.assertNotIn(s.end, reached)
            reached.add(s.end)
            a, b = tree.nodes[s.start], tree.nodes[s.end]
            distance = math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))
            self.assertGreater(distance, 0.0)
            self.assertGreater(s.radius_end, 0.0)
            self.assertGreaterEqual(s.radius_start, s.radius_end)
            if s.parent is None:
                self.assertEqual(s.start, 0)
            else:
                self.assertLess(s.parent, i)
                self.assertEqual(tree.segments[s.parent].end, s.start)
        self.assertEqual(reached, set(range(len(tree.nodes))))
        for p in tree.nodes + tuple(leaf.point for leaf in tree.leaves):
            self.assertTrue(all(math.isfinite(v) for v in (p.x, p.y, p.z, p.w)))
        for leaf in tree.leaves:
            self.assertEqual(leaf.point.w, tree.nodes[leaf.attachment].w)

    def test_trunk_tapers_and_model_is_spatial(self):
        trunk = [s for s in self.tree.segments if s.order == 0][:12]
        self.assertGreater(trunk[0].radius_start, 10 * trunk[-1].radius_end)
        self.assertGreater(max(p.z for p in self.tree.nodes) - min(p.z for p in self.tree.nodes), 5)
        self.assertGreater(max(p.w for p in self.tree.nodes) - min(p.w for p in self.tree.nodes), 4)
        self.assertEqual({s.order for s in self.tree.segments}, {0, 1, 2, 3})

    def test_xw_matrix_is_proper_nontrivial_orthogonal_rotation(self):
        angle = 0.73
        matrix = rotation_xw(angle)
        self.assertGreater(abs(matrix[0][3]), 0.5)
        self.assertGreater(abs(matrix[3][0]), 0.5)
        for i in range(4):
            for j in range(4):
                self.assertAlmostEqual(sum(matrix[i][k] * matrix[j][k] for k in range(4)), i == j)
        determinant = 0.0
        for p in itertools.permutations(range(4)):
            inversions = sum(p[i] > p[j] for i in range(4) for j in range(i + 1, 4))
            determinant += (-1) ** inversions * math.prod(matrix[i][p[i]] for i in range(4))
        self.assertAlmostEqual(determinant, 1.0)
        point = Point4(2.0, -1.0, 3.0, 4.0)
        rotated = rotate_xw(point, angle)
        vector = (point.x, point.y, point.z, point.w)
        expected = tuple(sum(row[i] * vector[i] for i in range(4)) for row in matrix)
        for actual, wanted in zip((rotated.x, rotated.y, rotated.z, rotated.w), expected):
            self.assertAlmostEqual(actual, wanted)
        self.assertAlmostEqual(rotated.x ** 2 + rotated.w ** 2, point.x ** 2 + point.w ** 2)
        self.assertNotEqual(rotated.x, point.x)
        self.assertNotEqual(rotated.w, point.w)

    def test_projection_has_near_plane_guards(self):
        self.assertIsNone(project_4d(Point4(1, 2, 3, W_EYE), 0))
        self.assertIsNone(project_4d(Point4(1, 2, 3, W_EYE + 1), 0))
        self.assertIsNotNone(project_4d(Point4(1, 2, 3, W_EYE - NEAR - 0.1), 0))
        self.assertIsNone(project_camera((1, 2, 0), "3d", 80, 30))
        self.assertIsNone(project_camera((1, 2, -1), "4d", 80, 30))
        self.assertIsNotNone(project_camera((1, 2, NEAR + 0.1), "3d", 80, 30))

    def test_3d_rotation_mixes_xyz_not_just_screen_translation(self):
        point = Point4(2, 7, 3, 1)
        front = camera_point(point, "3d", 0, 0, 0)
        side = camera_point(point, "3d", math.pi / 2, 0, 0)
        self.assertNotEqual(front[0], side[0])
        self.assertNotEqual(front[2], side[2])
        self.assertAlmostEqual(side[0], point.z)
