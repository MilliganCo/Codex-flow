from dataclasses import replace
import math
import unittest

from ascii_tree.model import Point4, Segment, Tree, generate_tree
from ascii_tree.projection import Projected, Projector
from ascii_tree.render import Raster, RenderSettings, render


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_repeatable_frame_bytes(self):
        settings = RenderSettings(mode="4d", yaw=71, pitch=17, angle4d=33, time=1.25)
        self.assertEqual(render(self.tree, settings).encode("ascii"),
                         render(generate_tree(42), settings).encode("ascii"))

    def test_dimensions_ascii_and_no_ansi(self):
        for width, height in ((80, 30), (100, 40), (1, 1), (2, 3), (8, 4), (500, 200)):
            for mode in ("2d", "3d", "4d"):
                with self.subTest(width=width, height=height, mode=mode):
                    frame = render(self.tree, RenderSettings(width, height, mode, angle4d=42))
                    self.assertEqual(len(frame), (width + 1) * height)
                    self.assertEqual(len(frame.splitlines()), height)
                    self.assertTrue(all(len(line) == width for line in frame.splitlines()))
                    self.assertTrue(all(c == "\n" or 32 <= ord(c) <= 126 for c in frame))
                    self.assertNotIn("\x1b", frame)
                    self.assertNotIn("\r", frame)

    def test_nonempty_and_varied_seeds(self):
        frames = [render(generate_tree(seed)) for seed in (42, 43, 2026)]
        self.assertEqual(len(set(frames)), 3)
        self.assertTrue(all(sum(c not in " \n" for c in f) > 300 for f in frames))

    def test_3d_rotation_changes_substantial_part_of_image(self):
        a = render(self.tree, RenderSettings(yaw=0, pitch=0))
        b = render(self.tree, RenderSettings(yaw=90, pitch=15))
        self.assertGreater(sum(x != y for x, y in zip(a, b)), 400)

    def test_3d_rotation_moves_depth_and_projected_endpoints(self):
        p = Point4(3, 2, 4, 1)
        kwargs = dict(center=Point4(0, 0, 0, 0), width=80, height=30, scale=1,
                      mode="3d", pitch=0, angle4d=0)
        a, b = Projector(yaw=0, **kwargs)(p), Projector(yaw=math.pi / 2, **kwargs)(p)
        self.assertNotEqual(a.depth, b.depth)
        self.assertNotEqual(a.x, b.x)
        self.assertNotEqual(a.y, b.y)

    def test_2d_fixed_xy_view_ignores_camera_rotation(self):
        a = render(self.tree, RenderSettings(mode="2d", yaw=0, pitch=0))
        b = render(self.tree, RenderSettings(mode="2d", yaw=75, pitch=30))
        self.assertEqual(a, b)

    def test_4d_angle_changes_image_without_changing_tree(self):
        original = self.tree.segments
        a = render(self.tree, RenderSettings(mode="4d", angle4d=0))
        b = render(self.tree, RenderSettings(mode="4d", angle4d=45))
        self.assertGreater(sum(x != y for x, y in zip(a, b)), 400)
        self.assertIs(self.tree.segments, original)

    def test_every_4d_quadrant_and_extreme_zoom_is_safe(self):
        for angle in range(0, 361, 30):
            frame = render(self.tree, RenderSettings(20, 8, "4d", yaw=angle,
                           pitch=-75, angle4d=angle, zoom=5))
            self.assertEqual(len(frame), 21 * 8)

    def test_aspect_and_zoom_change_projection(self):
        base = RenderSettings()
        self.assertNotEqual(render(self.tree, base), render(self.tree, replace(base, zoom=1.5)))
        self.assertNotEqual(render(self.tree, base), render(self.tree, replace(base, aspect=1)))

    def test_deterministic_breeze_preserves_joint_identity(self):
        base = RenderSettings(mode="2d")
        self.assertNotEqual(render(self.tree, base), render(self.tree, replace(base, time=1)))
        self.assertEqual(render(self.tree, replace(base, time=1)),
                         render(self.tree, replace(base, time=1)))

    def test_invalid_settings_are_rejected(self):
        for kwargs in (dict(width=0), dict(width=501), dict(height=-1), dict(height=201),
                       dict(mode="5d"), dict(zoom=0), dict(aspect=0), dict(yaw=math.inf),
                       dict(angle4d=math.nan), dict(time=math.inf)):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                RenderSettings(**kwargs)

    def test_near_planes_and_nonfinite_projection_are_safe(self):
        p = Projector(Point4(0, 0, 0, 0), 80, 30, 1, "3d", 0, 0, 0)
        self.assertIsNone(p(Point4(1, 1, 30, 0)))
        self.assertIsNone(p(Point4(1, 1, math.nan, 0)))
        self.assertIsNone(p(Point4(math.inf, 1, 1, 0)))
        self.assertIsNone(p(Point4(1, math.nan, 1, 0)))
        hyper = Projector(Point4(0, 0, 0, 0), 80, 30, 1, "4d", 0, 0, 0)
        self.assertIsNone(hyper(Point4(1, 1, 1, 18)))


class OcclusionTests(unittest.TestCase):
    def crossing(self, reverse=False):
        raster = Raster(21, 11)
        far = (Projected(1, 5, 35, 1), Projected(19, 5, 35, 1))
        near = (Projected(10, 1, 25, 1), Projected(10, 9, 25, 1))
        for a, b in ((near, far) if reverse else (far, near)):
            raster.segment(a, b, .1, .1, 1, 2)
        return raster

    def test_near_segment_hides_far_segment_in_both_draw_orders(self):
        a, b = self.crossing(), self.crossing(reverse=True)
        self.assertEqual(a.text(), b.text())
        self.assertEqual(a.chars[5][10], "|")
        self.assertAlmostEqual(a.depth[5][10], 24.9)
        self.assertEqual(a.chars[5][2], "_")

    def test_depth_is_perspective_correctly_interpolated(self):
        raster = Raster(21, 11)
        raster.segment(Projected(10, 1, 5, 1), Projected(10, 9, 5, 1), 0, 0, 1, 2)
        raster.segment(Projected(0, 5, 2, 1), Projected(20, 5, 10, 1), 0, 0, 1, 2)
        self.assertEqual(raster.chars[5][10], "_")
        self.assertAlmostEqual(raster.depth[5][10], 1 / (.5 / 2 + .5 / 10))

    def test_thick_near_wood_occludes_distant_leaf(self):
        raster = Raster(20, 10)
        raster.put(5, 5, 31, "o", 0)
        raster.segment(Projected(5, 1, 25, 1), Projected(5, 8, 25, 1), 1, 1, 1, 2)
        self.assertIn(raster.chars[5][5], "#%@")
        raster.put(5, 5, 20, "o", 0)
        self.assertEqual(raster.chars[5][5], "o")

    def test_offscreen_fragments_do_not_wrap(self):
        raster = Raster(2, 2)
        for x, y in ((-1, 0), (0, -1), (2, 0), (0, 2)):
            raster.put(x, y, 1, "X")
        self.assertEqual(raster.text(), "  \n  \n")
