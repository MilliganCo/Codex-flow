import math
import unittest

from ascii_tree.geometry import generate_tree


class GeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_seed_42_is_reproducible(self):
        self.assertEqual(self.tree, generate_tree(42))

    def test_several_seeds_have_distinct_geometry(self):
        trees = [generate_tree(seed) for seed in (7, 42, 43, -12)]
        self.assertEqual(4, len({tree.vertices for tree in trees}))

    def test_connected_acyclic_parent_graph(self):
        tree = self.tree
        self.assertEqual(len(tree.vertices) - 1, len(tree.segments))
        reached = {0}
        for index, segment in enumerate(tree.segments):
            self.assertIn(segment.start, reached)
            self.assertNotIn(segment.end, reached)
            reached.add(segment.end)
            if segment.parent is None:
                self.assertEqual(0, segment.start)
            else:
                self.assertLess(segment.parent, index)
                self.assertEqual(tree.segments[segment.parent].end, segment.start)
        self.assertEqual(set(range(len(tree.vertices))), reached)

    def test_positive_lengths_taper_and_growth(self):
        for segment in self.tree.segments:
            start, end = self.tree.vertices[segment.start], self.tree.vertices[segment.end]
            self.assertGreater(math.dist(start.xyz, end.xyz), 1e-6)
            self.assertGreater(segment.radius_end, 0)
            self.assertGreaterEqual(segment.radius_start, segment.radius_end)
            self.assertGreater(end.w, start.w)
        trunk = [s for s in self.tree.segments if s.order == 0]
        self.assertGreater(trunk[0].radius_start, trunk[-1].radius_end * 10)

    def test_finite_coordinates_and_nonplanar_zw(self):
        points = self.tree.vertices + tuple(leaf.position for leaf in self.tree.leaves)
        for p in points:
            self.assertTrue(all(math.isfinite(x) for x in (p.x, p.y, p.z, p.w)))
        self.assertGreater(max(p.z for p in points) - min(p.z for p in points), 3)
        self.assertGreater(max(p.w for p in points) - min(p.w for p in points), 3)

    def test_bounded_for_many_seeds(self):
        for seed in range(12):
            tree = generate_tree(seed)
            self.assertLess(len(tree.segments), 1800)
            self.assertLessEqual(max(s.order for s in tree.segments), 3)
            self.assertGreater(len(tree.leaves), 500)
