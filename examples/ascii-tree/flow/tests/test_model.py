import math
import unittest

from ascii_tree.model import MAX_ORDER, MAX_SEGMENTS, generate_tree


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_seed_42_deterministic(self):
        self.assertEqual(self.tree, generate_tree(42))

    def test_seeds_vary(self):
        for seed in (7, 43, -1, 2026):
            self.assertNotEqual(self.tree.vertices, generate_tree(seed).vertices)

    def test_connected_finite_positive_tapered_graph(self):
        for seed in (42, 7, 0, -123, 2**64):
            tree = generate_tree(seed)
            self.assertEqual(len(tree.vertices), len(tree.segments) + 1)
            reached = {0}
            for i, segment in enumerate(tree.segments):
                self.assertIn(segment.start, reached)
                self.assertNotIn(segment.end, reached)
                reached.add(segment.end)
                a, b = tree.vertices[segment.start], tree.vertices[segment.end]
                self.assertGreater(math.dist(a[:3], b[:3]), 0)
                self.assertGreater(segment.radius_end, 0)
                self.assertGreaterEqual(segment.radius_start, segment.radius_end)
                if segment.parent is not None:
                    self.assertLess(segment.parent, i)
                    self.assertEqual(tree.segments[segment.parent].end, segment.start)
                else:
                    self.assertEqual(i, 0)
                self.assertLessEqual(segment.order, MAX_ORDER)
            self.assertEqual(reached, set(range(len(tree.vertices))))
            self.assertLessEqual(len(tree.segments), MAX_SEGMENTS)
            for point in (*tree.vertices, *(leaf.position for leaf in tree.leaves)):
                self.assertTrue(all(math.isfinite(x) for x in point))

    def test_trunk_tapers(self):
        trunk = [s for s in self.tree.segments if s.order == 0]
        self.assertGreater(trunk[0].radius_start, trunk[-1].radius_end * 10)
        for a, b in zip(trunk, trunk[1:]):
            self.assertEqual(a.radius_end, b.radius_start)

    def test_nonplanar_z_and_variable_developmental_w(self):
        z, w = [p[2] for p in self.tree.vertices], [p[3] for p in self.tree.vertices]
        self.assertGreater(max(z) - min(z), 3)
        self.assertGreater(max(w) - min(w), 3)
        for s in self.tree.segments:
            a, b = self.tree.vertices[s.start], self.tree.vertices[s.end]
            self.assertGreater(b[3], a[3])
            self.assertAlmostEqual(b[3] - a[3], math.dist(a[:3], b[:3]) * 0.55)


if __name__ == "__main__":
    unittest.main()
