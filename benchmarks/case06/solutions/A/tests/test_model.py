import math
import random
import unittest

from ascii_tree.model import generate_tree


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_seed_42_geometry_is_deterministic(self):
        self.assertEqual(self.tree, generate_tree(42))

    def test_distinct_seeds_produce_distinct_geometry(self):
        signatures = {generate_tree(seed).vertices for seed in (7, 42, 314)}
        self.assertEqual(len(signatures), 3)

    def test_rooted_connected_acyclic_segment_graph(self):
        tree = self.tree
        reached = {0}
        roots = 0
        self.assertEqual(len(tree.vertices), len(tree.segments) + 1)
        for i, segment in enumerate(tree.segments):
            self.assertIn(segment.start, reached)
            self.assertNotIn(segment.end, reached)
            reached.add(segment.end)
            if segment.parent is None:
                roots += 1
                self.assertEqual(segment.start, 0)
            else:
                self.assertLess(segment.parent, i)
                self.assertEqual(tree.segments[segment.parent].end, segment.start)
        self.assertEqual(roots, 1)
        self.assertEqual(reached, set(range(len(tree.vertices))))

    def test_finite_positive_lengths_and_tapering(self):
        tree = self.tree
        for point in tree.vertices:
            self.assertTrue(all(math.isfinite(v) for v in point.values()))
        for leaf in tree.leaves:
            self.assertTrue(all(math.isfinite(v) for v in leaf.point.values()))
            self.assertGreater(leaf.size, 0)
        for segment in tree.segments:
            a, b = tree.vertices[segment.start], tree.vertices[segment.end]
            self.assertGreater(math.dist(a.values()[:3], b.values()[:3]), 0)
            self.assertGreater(segment.radius_end, 0)
            self.assertGreater(segment.radius_start, segment.radius_end)
            self.assertGreater(b.w, a.w)
            if segment.parent is not None:
                self.assertLessEqual(segment.radius_start, tree.segments[segment.parent].radius_end + 1e-12)
        trunk = [s for s in tree.segments if s.order == 0]
        self.assertGreater(trunk[0].radius_start, trunk[-1].radius_end * 20)

    def test_spatial_z_and_growth_w_are_not_constant(self):
        self.assertGreater(max(p.z for p in self.tree.vertices) - min(p.z for p in self.tree.vertices), 4)
        self.assertGreater(max(p.w for p in self.tree.vertices) - min(p.w for p in self.tree.vertices), 4)

    def test_recursion_is_bounded_for_several_seeds(self):
        for seed in (-1, 0, 7, 42, 314):
            tree = generate_tree(seed)
            self.assertLess(len(tree.segments), 5000)
            self.assertLess(len(tree.leaves), 10000)
            self.assertEqual(max(s.order for s in tree.segments), 4)

    def test_generation_does_not_change_global_rng(self):
        random.seed(15)
        before = random.getstate()
        generate_tree(42)
        self.assertEqual(before, random.getstate())
