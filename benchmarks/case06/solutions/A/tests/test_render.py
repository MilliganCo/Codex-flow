from dataclasses import replace
import math
import unittest

from ascii_tree.geometry import Point4
from ascii_tree.model import generate_tree
from ascii_tree.render import DepthBuffer, Projected, Projector, RenderOptions, draw_segment, render_tree


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_deterministic_frames_for_all_modes(self):
        for mode in ("2d", "3d", "4d"):
            options = RenderOptions(mode=mode, angle4=35, time=1.25)
            self.assertEqual(render_tree(self.tree, options), render_tree(generate_tree(42), options))

    def test_seed_changes_image(self):
        options = RenderOptions(width=80, height=30)
        frames = {render_tree(generate_tree(seed), options) for seed in (7, 42, 314)}
        self.assertEqual(len(frames), 3)

    def test_dimensions_printable_ascii_and_no_ansi(self):
        for width, height in ((80, 30), (100, 40), (1, 1), (2, 3), (15, 6)):
            for mode in ("2d", "3d", "4d"):
                with self.subTest(width=width, height=height, mode=mode):
                    frame = render_tree(self.tree, RenderOptions(width, height, mode))
                    self.assertTrue(frame.endswith("\n"))
                    self.assertEqual(len(frame.splitlines()), height)
                    self.assertTrue(all(len(line) == width for line in frame.splitlines()))
                    self.assertTrue(all(32 <= ord(c) <= 126 or c == "\n" for c in frame))
                    self.assertNotIn("\x1b", frame)
                    self.assertEqual(len(frame.encode("ascii")), (width + 1) * height)

    def test_camera_rotation_is_more_than_translation(self):
        a = Projector(self.tree, RenderOptions(yaw=0, pitch=0))
        b = Projector(self.tree, RenderOptions(yaw=70, pitch=20))
        differences = [(b(p).x - a(p).x, b(p).y - a(p).y) for p in self.tree.vertices[::100]]
        self.assertGreater(max(x for x, _ in differences) - min(x for x, _ in differences), 10)
        self.assertGreater(max(y for _, y in differences) - min(y for _, y in differences), 2)
        self.assertNotEqual(render_tree(self.tree, a.options), render_tree(self.tree, b.options))

    def test_2d_is_fixed_orthographic_view(self):
        a = RenderOptions(mode="2d", yaw=0, pitch=0)
        self.assertEqual(render_tree(self.tree, a), render_tree(self.tree, replace(a, yaw=90, pitch=50)))

    def test_depth_buffer_is_order_independent_for_front_and_back(self):
        for layers in (((3, "#"), (1, "*")), ((1, "*"), (3, "#"))):
            buffer = DepthBuffer(3, 3)
            for depth, char in layers:
                buffer.put(1, 1, depth, char)
            self.assertEqual(buffer.cells[1][1], "*")
            self.assertEqual(buffer.depth[1][1], 1)

    def test_crossing_tubes_occlude_correctly_in_both_draw_orders(self):
        near = (Projected(5, 1, 2, 1), Projected(5, 9, 2, 1))
        far = (Projected(1, 5, 8, 1), Projected(9, 5, 8, 1))
        frames = []
        for segments in ((near, far), (far, near)):
            buffer = DepthBuffer(11, 11)
            for a, b in segments:
                draw_segment(buffer, a, b, 0.1, 0.1, 0.5, 5)
            self.assertEqual(buffer.cells[5][5], "|")
            self.assertLess(buffer.depth[5][5], 3)
            frames.append(buffer.frame())
        self.assertEqual(frames[0], frames[1])

    def test_crossing_with_sloping_depth_uses_per_cell_z_test(self):
        buffer = DepthBuffer(13, 7)
        draw_segment(buffer, Projected(1, 3, 2, 1), Projected(11, 3, 9, 1), 0.1, 0.1, 0.5, 10)
        for x in range(1, 12):
            buffer.put(x, 3, 4, "o")
        self.assertEqual(buffer.cells[3][1], "-")
        self.assertEqual(buffer.cells[3][11], "o")

    def test_hyperplane_rotation_changes_frames_in_all_planes(self):
        for plane in ("xw", "yw", "zw"):
            a = RenderOptions(mode="4d", plane=plane, angle4=0)
            b = replace(a, angle4=48)
            one, two = render_tree(self.tree, a), render_tree(self.tree, b)
            self.assertGreater(sum(x != y for x, y in zip(one, two)), 150)

    def test_4d_projection_at_zero_is_not_merely_a_label(self):
        self.assertNotEqual(render_tree(self.tree, RenderOptions(mode="3d")), render_tree(self.tree, RenderOptions(mode="4d")))

    def test_aspect_ratio_changes_horizontal_scale_only_when_height_limited(self):
        a = Projector(self.tree, RenderOptions(width=300, height=20, aspect=0.5, mode="2d"))
        b = Projector(self.tree, RenderOptions(width=300, height=20, aspect=1, mode="2d"))
        point = Point4(2, 5, 0, 0)
        self.assertAlmostEqual(a(point).x - 149.5, (b(point).x - 149.5) * 2)
        self.assertEqual(a(point).y, b(point).y)

    def test_near_plane_clipping_and_extreme_zoom_are_safe(self):
        projector = Projector(self.tree, RenderOptions(yaw=0, pitch=0))
        self.assertIsNone(projector(Point4(0, 0, projector.distance + 1, 0)))
        for plane in ("xw", "yw", "zw"):
            for angle in (90, 180, 270):
                frame = render_tree(self.tree, RenderOptions(1, 1, "4d", angle4=angle, plane=plane, zoom=6))
                self.assertEqual(len(frame), 2)

    def test_breeze_is_deterministic_and_does_not_mutate_geometry(self):
        vertices = self.tree.vertices
        a = RenderOptions(mode="2d", time=0)
        b = replace(a, time=1.7)
        self.assertNotEqual(render_tree(self.tree, a), render_tree(self.tree, b))
        self.assertIs(vertices, self.tree.vertices)
        render_tree(self.tree, replace(a, time=1.7e308, width=5, height=2))

    def test_options_reject_unsafe_dimensions_and_nonfinite_values(self):
        for kwargs in ({"width": 0}, {"height": 201}, {"width": 501}, {"zoom": 0},
                       {"angle4": math.inf}, {"yaw": math.nan}, {"aspect": 0.1}, {"time": math.inf}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                RenderOptions(**kwargs)
