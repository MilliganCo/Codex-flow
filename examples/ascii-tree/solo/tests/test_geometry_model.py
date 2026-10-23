import math
import unittest

from ascii_tree.geometry import Vec3, Vec4, camera_rotate, perspective, project4, rotation4, transform4
from ascii_tree.model import MAX_SEGMENTS, generate_tree


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_seed_determinism_and_variety(self):
        self.assertEqual(self.tree, generate_tree(42))
        self.assertEqual(len({generate_tree(s).fingerprint for s in (7, 42, 103)}), 3)

    def test_connected_finite_positive_tapered_graph(self):
        tree = self.tree
        self.assertLess(len(tree.segments), MAX_SEGMENTS)
        reached = {0}
        for index, segment in enumerate(tree.segments):
            self.assertIn(segment.start, reached)
            reached.add(segment.end)
            self.assertGreater((tree.vertices[segment.end].xyz - tree.vertices[segment.start].xyz).length(), 0)
            self.assertGreater(segment.radius_end, 0)
            self.assertGreaterEqual(segment.radius_start, segment.radius_end)
            if segment.parent is not None:
                self.assertLess(segment.parent, index)
                self.assertEqual(tree.segments[segment.parent].end, segment.start)
        self.assertEqual(len(reached), len(tree.vertices))
        for p in tree.vertices:
            self.assertTrue(all(math.isfinite(v) for v in (p.x, p.y, p.z, p.w)))
        self.assertGreater(max(p.z for p in tree.vertices) - min(p.z for p in tree.vertices), 5)
        self.assertGreater(max(p.w for p in tree.vertices) - min(p.w for p in tree.vertices), 10)
        self.assertEqual({s.order for s in tree.segments}, {0, 1, 2, 3, 4})

    def test_leaf_attachment(self):
        self.assertGreater(len(self.tree.leaves), 300)
        for leaf in self.tree.leaves:
            self.assertIn(leaf.segment, range(len(self.tree.segments)))
            self.assertTrue(all(math.isfinite(v) for v in (leaf.position.x, leaf.position.y,
                                                          leaf.position.z, leaf.position.w)))


class GeometryTests(unittest.TestCase):
    def test_hyperrotation_mixes_w_and_preserves_norm(self):
        point = Vec4(2, 3, 5, 7)
        for plane in ("xw", "yw", "zw"):
            matrix = rotation4(37, plane)
            result = transform4(point, matrix)
            self.assertNotEqual(result.xyz, point.xyz)
            self.assertNotEqual(result.w, point.w)
            self.assertAlmostEqual(sum(v*v for v in (2, 3, 5, 7)),
                                   sum(v*v for v in (result.x, result.y, result.z, result.w)))
            for i in range(4):
                for j in range(4):
                    self.assertAlmostEqual(sum(matrix[i][k] * matrix[j][k] for k in range(4)), float(i == j))
        quarter = transform4(Vec4(2, 3, 5, 7), rotation4(90))
        self.assertAlmostEqual(quarter.x, -7)
        self.assertAlmostEqual(quarter.w, 2)

    def test_projection_and_near_plane(self):
        self.assertIsNone(project4(Vec4(1, 2, 3, 32)))
        self.assertIsNone(project4(Vec4(1, 2, 3, 33)))
        self.assertIsNone(perspective(Vec3(1, 2, -40), 32))
        self.assertIsNone(perspective(Vec3(1, 2, -32), 32))
        self.assertEqual(project4(Vec4(1, 2, 3, 0)), Vec3(1, 2, 3))
        self.assertNotEqual(camera_rotate(Vec3(1, 2, 3), 0, 0), camera_rotate(Vec3(1, 2, 3), 45, 20))
        with self.assertRaises(ValueError):
            rotation4(10, "xy")


if __name__ == "__main__":
    unittest.main()
