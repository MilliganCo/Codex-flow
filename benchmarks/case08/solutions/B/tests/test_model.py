import math
import unittest
from ascii_tree.model import generate_tree


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_seed_42_determinism(self):
        self.assertEqual(self.tree, generate_tree(42))

    def test_seed_diversity(self):
        trees = [generate_tree(seed) for seed in (1, 42, 43, 2026)]
        self.assertEqual(len({t.segments for t in trees}), 4)

    def test_connected_acyclic_positive_tapered_graph(self):
        roots = 0
        for index, seg in enumerate(self.tree.segments):
            for point in (seg.start, seg.end):
                self.assertTrue(all(math.isfinite(v) for v in (point.x, point.y, point.z, point.w)))
            self.assertGreater(math.dist((seg.start.x, seg.start.y, seg.start.z),
                                         (seg.end.x, seg.end.y, seg.end.z)), 0)
            self.assertGreaterEqual(seg.radius_start, seg.radius_end)
            self.assertGreater(seg.radius_end, 0)
            self.assertGreater(seg.end.w, seg.start.w)
            if seg.parent is None:
                roots += 1
            else:
                self.assertLess(seg.parent, index)
                self.assertEqual(seg.start, self.tree.segments[seg.parent].end)
                self.assertLessEqual(seg.radius_start, self.tree.segments[seg.parent].radius_end)
        self.assertEqual(roots, 1)
        trunk = [s for s in self.tree.segments if s.order == 0]
        self.assertGreater(trunk[0].radius_start, trunk[-1].radius_end * 8)

    def test_nonplanar_z_and_variable_w(self):
        points = [s.end for s in self.tree.segments]
        self.assertGreater(max(p.z for p in points) - min(p.z for p in points), 4)
        self.assertGreater(max(p.w for p in points) - min(p.w for p in points), 4)

    def test_generation_bounded_multiple_seeds(self):
        for seed in range(12):
            tree = generate_tree(seed)
            self.assertLessEqual(len(tree.segments), 2210)
            self.assertLessEqual(max(s.order for s in tree.segments), 4)
