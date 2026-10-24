import math
import unittest

from ascii_tree.model import generate_tree


class ModelTests(unittest.TestCase):
    def test_deterministic_graph_and_seed_diversity(self):
        trees = [generate_tree(seed) for seed in (42, 43, 2718)]
        self.assertEqual(trees[0], generate_tree(42))
        self.assertEqual(len(set(trees)), 3)

    def test_graph_is_finite_connected_and_tapered(self):
        for seed in (0, 42, 43, -99, 2**64):
            tree = generate_tree(seed)
            self.assertGreater(len(tree.segments), 200)
            self.assertLess(len(tree.segments), 2000)
            for i, segment in enumerate(tree.segments):
                for point in (segment.start, segment.end):
                    self.assertTrue(all(math.isfinite(getattr(point, k)) for k in ('x', 'y', 'z', 'w')))
                    self.assertTrue(0 <= point.w <= 1)
                self.assertGreater(math.dist((segment.start.x, segment.start.y, segment.start.z),
                                             (segment.end.x, segment.end.y, segment.end.z)), 0)
                self.assertGreater(segment.radius_end, 0)
                self.assertGreaterEqual(segment.radius_start, segment.radius_end)
                self.assertGreaterEqual(segment.end.w, segment.start.w)
                if i == 0:
                    self.assertIsNone(segment.parent)
                else:
                    self.assertIsNotNone(segment.parent)
                    self.assertLess(segment.parent, i)
                    self.assertEqual(tree.segments[segment.parent].end, segment.start)
                    self.assertLessEqual(segment.radius_start,
                                         tree.segments[segment.parent].radius_end)
            self.assertEqual({s.order for s in tree.segments}, {0, 1, 2, 3})
            zs = [s.end.z for s in tree.segments]
            ws = [s.end.w for s in tree.segments]
            self.assertGreater(max(zs)-min(zs), 3)
            self.assertGreater(max(ws)-min(ws), .8)
            trunk = [s for s in tree.segments if s.order == 0]
            self.assertGreater(trunk[0].radius_start, trunk[-1].radius_end*10)
