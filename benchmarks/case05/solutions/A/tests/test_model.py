import math
import unittest

from ascii_tree.model import generate_tree


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_seed_determinism(self):
        self.assertEqual(self.tree, generate_tree(42))

    def test_several_seeds_give_different_geometry(self):
        others = [generate_tree(seed) for seed in (7, 2026, -1)]
        fingerprints = {tuple((s.start, s.end) for s in t.segments) for t in [self.tree] + others}
        self.assertEqual(len(fingerprints), 4)

    def test_graph_is_connected_acyclic_and_finite(self):
        segments = self.tree.segments
        self.assertTrue(100 < len(segments) < 6000)
        for index, segment in enumerate(segments):
            values = [getattr(p, axis) for p in (segment.start, segment.end) for axis in 'xyzw']
            self.assertTrue(all(math.isfinite(value) for value in values))
            distance = sum((getattr(segment.start, axis) - getattr(segment.end, axis)) ** 2 for axis in 'xyz')
            self.assertGreater(distance, 1e-8)
            self.assertGreater(segment.radius_start, 0)
            self.assertGreater(segment.radius_end, 0)
            self.assertLessEqual(segment.radius_end, segment.radius_start)
            if index == 0:
                self.assertIsNone(segment.parent)
            else:
                self.assertIsNotNone(segment.parent)
                self.assertLess(segment.parent, index)
                self.assertEqual(segment.start, segments[segment.parent].end)
                self.assertGreater(segment.end.w, segment.start.w)
        self.assertTrue(all(all(math.isfinite(getattr(leaf.point, a)) for a in 'xyzw') for leaf in self.tree.leaves))

    def test_taper_and_multiple_branch_orders(self):
        trunk = [s for s in self.tree.segments if s.order == 0]
        self.assertGreater(trunk[0].radius_start, trunk[-1].radius_end * 15)
        self.assertEqual({s.order for s in self.tree.segments}, {0, 1, 2, 3, 4})
        self.assertGreater(len(self.tree.leaves), 100)

    def test_spatial_z_and_growth_w_are_variable(self):
        points = [s.end for s in self.tree.segments]
        for axis in ('z', 'w'):
            values = [getattr(p, axis) for p in points]
            self.assertGreater(max(values) - min(values), 4)
        # Actual volume: three vectors from the base are linearly independent.
        a, b, c = points[5], points[25], points[120]
        determinant = a.x * (b.y*c.z - b.z*c.y) - a.y * (b.x*c.z - b.z*c.x) + a.z * (b.x*c.y - b.y*c.x)
        self.assertGreater(abs(determinant), 0.01)


if __name__ == '__main__':
    unittest.main()
