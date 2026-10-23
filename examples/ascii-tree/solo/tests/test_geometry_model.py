import math
from dataclasses import replace
import unittest

from ascii_tree.geometry import Vec3, Vec4, camera_rotate, perspective, project4, rotation4, transform4
from ascii_tree.model import Leaf, MAX_SEGMENTS, Segment, Tree, generate_tree


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_seed_determinism_and_variety(self):
        self.assertEqual(self.tree, generate_tree(42))
        self.assertEqual(len({generate_tree(s).fingerprint for s in (7, 42, 103)}), 3)

    def test_fingerprint_tolerates_ulp_drift_and_tracks_material_changes(self):
        points = (Vec4(0.0, 0.0, 0.0, 0.0), Vec4(1.25, 2.5, 3.75, 4.5),
                  Vec4(2.75, 4.0, 5.25, 6.5))
        segments = (Segment(0, 1, .4, .2, None, 0), Segment(1, 2, .2, .1, 0, 1))
        tree = Tree(42, points, segments, (Leaf(points[2], .125, 1, 2),))

        def drift(value):
            return math.nextafter(value, math.inf)

        def drift_point(point):
            return Vec4(*(drift(value) for value in (point.x, point.y, point.z, point.w)))

        drifted = replace(tree, vertices=tuple(map(drift_point, points)),
                          segments=tuple(replace(s, radius_start=drift(s.radius_start),
                                                 radius_end=drift(s.radius_end)) for s in segments),
                          leaves=tuple(replace(leaf, position=drift_point(leaf.position),
                                               size=drift(leaf.size)) for leaf in tree.leaves))
        self.assertEqual(tree.fingerprint, drifted.fingerprint)
        self.assertEqual(tree.fingerprint, replace(tree, vertices=(
            Vec4(-0.0, 0.0, -0.0, 0.0), *points[1:])).fingerprint)
        alternatives = {
            "seed": replace(tree, seed=43),
            "spatial_geometry": replace(tree, vertices=(*points[:2], replace(points[2], x=points[2].x + 1e-6))),
            "fourth_coordinate": replace(tree, vertices=(*points[:2], replace(points[2], w=points[2].w + 1e-6))),
            "topology": replace(tree, segments=(segments[0], replace(segments[1], start=0, parent=None))),
            "thickness": replace(tree, segments=(segments[0], replace(segments[1], radius_end=.11))),
            "foliage": replace(tree, leaves=(replace(tree.leaves[0], size=.15, tone=3),)),
        }
        for name, changed in alternatives.items():
            with self.subTest(change=name):
                self.assertNotEqual(tree.fingerprint, changed.fingerprint)

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
