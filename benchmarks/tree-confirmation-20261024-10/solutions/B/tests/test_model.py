import math
import unittest

from ascii_tree.model import MAX_SEGMENTS, generate_tree, unit
from ascii_tree.render import Camera
from ascii_tree.terminal import Explorer


class ModelTests(unittest.TestCase):
    def test_deterministic_geometry(self):
        self.assertEqual(generate_tree(42), generate_tree(42))

    def test_seeds_have_different_geometry(self):
        trees = [generate_tree(seed) for seed in (0, 42, 137, -5)]
        self.assertEqual(4, len({tree.segments for tree in trees}))

    def test_connected_finite_tapered_graph(self):
        for seed in (0, 42, 137, -5):
            tree = generate_tree(seed)
            self.assertLessEqual(len(tree.segments), MAX_SEGMENTS)
            self.assertGreater(len(tree.segments), 100)
            self.assertTrue(all(all(math.isfinite(v) for v in leaf.point)
                                and leaf.size > 0 for leaf in tree.leaves))
            for i, segment in enumerate(tree.segments):
                self.assertTrue(all(math.isfinite(v) for v in segment.start + segment.end))
                self.assertGreater(math.dist(segment.start[:3], segment.end[:3]), 1e-9)
                self.assertGreater(segment.radius_end, 0)
                self.assertGreaterEqual(segment.radius_start, segment.radius_end)
                self.assertLessEqual(segment.order, 4)
                if i == 0:
                    self.assertIsNone(segment.parent)
                else:
                    self.assertGreaterEqual(segment.parent, 0)
                    self.assertLess(segment.parent, i)
                    self.assertEqual(segment.start, tree.segments[segment.parent].end)
                    self.assertLessEqual(segment.radius_start,
                                         tree.segments[segment.parent].radius_end + 1e-12)

    def test_spatial_and_age_variation(self):
        points = [s.end for s in generate_tree(42).segments]
        self.assertGreater(max(p[2] for p in points) - min(p[2] for p in points), 2)
        self.assertGreater(max(p[3] for p in points) - min(p[3] for p in points), .5)

    def test_switch_modes_preserves_identity(self):
        tree = generate_tree(42)
        state = Explorer(tree, Camera())
        for key, mode in (("1", "2d"), ("2", "3d"), ("3", "4d"), ("1", "2d")):
            state.key(key)
            self.assertIs(state.tree, tree)
            self.assertEqual(state.camera.mode, mode)
        state.key("g")
        self.assertEqual(state.tree.seed, 43)
        self.assertIsNot(state.tree, tree)

    def test_bad_seed_and_degenerate_direction(self):
        for seed in (None, "42", True, 2.4):
            with self.assertRaises(ValueError):
                generate_tree(seed)
        for v in ((0, 0, 0), (1e-20, 0, 0), (math.inf, 0, 0), (math.nan, 0, 0)):
            with self.assertRaises(ValueError):
                unit(v)
