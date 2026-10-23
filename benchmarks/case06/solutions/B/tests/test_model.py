import math
import unittest

from ascii_tree.model import generate_tree


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_seed_42_is_deterministic(self):
        self.assertEqual(self.tree, generate_tree(42))

    def test_multiple_seeds_make_distinct_geometry(self):
        trees = [generate_tree(seed) for seed in (7, 42, 123)]
        self.assertEqual(len({tree.segments for tree in trees}), 3)
        self.assertEqual(len({tree.leaves for tree in trees}), 3)

    def test_connected_acyclic_positive_finite_segment_graph(self):
        roots = []
        for index, segment in enumerate(self.tree.segments):
            if segment.parent is None:
                roots.append(index)
            else:
                self.assertLess(segment.parent, index)
                self.assertEqual(segment.start, self.tree.segments[segment.parent].end)
            self.assertGreater(segment.radius_start, 0)
            self.assertGreater(segment.radius_end, 0)
            self.assertLessEqual(segment.radius_end, segment.radius_start)
            self.assertGreater(math.dist((segment.start.x, segment.start.y, segment.start.z),
                                         (segment.end.x, segment.end.y, segment.end.z)), 0)
            self.assertGreater(segment.end.w, segment.start.w)
            for point in (segment.start, segment.end):
                self.assertTrue(all(math.isfinite(v) for v in (point.x, point.y, point.z, point.w)))
        self.assertEqual(roots, [0])
        self.assertLess(len(self.tree.segments), 4000)
        self.assertEqual(max(s.order for s in self.tree.segments), 4)

    def test_trunk_tapers_and_tree_is_not_flat_in_z_or_w(self):
        trunk = [s for s in self.tree.segments if s.order == 0]
        self.assertGreater(trunk[0].radius_start, 5 * trunk[-1].radius_end)
        points = [s.end for s in self.tree.segments]
        self.assertGreater(max(p.z for p in points) - min(p.z for p in points), 8)
        self.assertGreater(max(p.w for p in points) - min(p.w for p in points), 5)
        self.assertGreater(len(self.tree.leaves), 100)


if __name__ == "__main__":
    unittest.main()
