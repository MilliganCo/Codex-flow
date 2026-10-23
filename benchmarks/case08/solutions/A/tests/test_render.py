from dataclasses import replace
import math
import unittest

from ascii_tree.geometry import generate_tree
from ascii_tree.math4d import project_camera
from ascii_tree.render import (DepthBuffer, RenderOptions, draw_segment,
                                frame_bytes, render_frame)


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_deterministic_for_each_mode_and_time(self):
        for mode in ("2d", "3d", "4d"):
            with self.subTest(mode=mode):
                o = RenderOptions(mode=mode, angle4=32, time=1.25)
                self.assertEqual(frame_bytes(self.tree, o), frame_bytes(generate_tree(42), o))

    def test_dimensions_and_pure_ascii_at_minimum_and_normal_sizes(self):
        for width, height in ((1, 1), (2, 3), (12, 5), (80, 30), (100, 40), (500, 200)):
            for mode in ("2d", "3d", "4d"):
                with self.subTest(size=(width, height), mode=mode):
                    data = frame_bytes(self.tree, RenderOptions(mode=mode, width=width, height=height))
                    self.assertEqual(len(data), (width + 1) * height)
                    self.assertEqual(len(data.splitlines()), height)
                    self.assertTrue(all(len(row) == width for row in data.splitlines()))
                    self.assertTrue(all(c == 10 or 32 <= c <= 126 for c in data))
                    self.assertNotIn(b"\x1b", data)
                    self.assertNotIn(b"\r", data)

    def test_multiple_seeds_change_the_frame(self):
        frames = {frame_bytes(generate_tree(s), RenderOptions()) for s in (7, 42, 43)}
        self.assertEqual(len(frames), 3)

    def test_3d_orbit_and_tilt_change_many_pixels(self):
        base = frame_bytes(self.tree, RenderOptions())
        for options in (RenderOptions(yaw=105), RenderOptions(pitch=30)):
            other = frame_bytes(self.tree, options)
            self.assertGreater(sum(a != b for a, b in zip(base, other)), 300)

    def test_4d_xw_angle_changes_image_without_regeneration(self):
        before = self.tree
        a = frame_bytes(self.tree, RenderOptions(mode="4d", angle4=0))
        b = frame_bytes(self.tree, RenderOptions(mode="4d", angle4=55))
        self.assertGreater(sum(x != y for x, y in zip(a, b)), 300)
        self.assertIs(before, self.tree)
        self.assertNotEqual(a, frame_bytes(self.tree, RenderOptions(mode="3d")))

    def test_2d_ignores_camera_angles_and_4d_angle(self):
        base = RenderOptions(mode="2d")
        self.assertEqual(frame_bytes(self.tree, base),
                         frame_bytes(self.tree, replace(base, yaw=150, pitch=75, angle4=70)))

    def test_animation_is_deterministic_and_changes_each_mode(self):
        for mode in ("2d", "3d", "4d"):
            base = RenderOptions(mode=mode)
            moved = replace(base, time=3.0)
            self.assertNotEqual(frame_bytes(self.tree, base), frame_bytes(self.tree, moved))
            self.assertEqual(frame_bytes(self.tree, moved), frame_bytes(self.tree, moved))

    def test_aspect_corrects_cell_shape(self):
        center = project_camera((0, 0, 25), "3d", 100, 40, aspect=2)
        right = project_camera((1, 0, 25), "3d", 100, 40, aspect=2)
        up = project_camera((0, 1, 25), "3d", 100, 40, aspect=2)
        self.assertAlmostEqual(right[0] - center[0], 2 * (center[1] - up[1]))

    def test_depth_buffer_nearer_surface_wins_in_both_draw_orders(self):
        # Two known crossing branches, not an assertion about random pixels.
        far = ((1, 3, 30, 1), (9, 3, 30, 1), "-")
        near = ((5, 0, 10, 1), (5, 6, 10, 1), "|")
        buffers = []
        for sequence in ((far, near), (near, far)):
            buffer = DepthBuffer(11, 7)
            for a, b, char in sequence:
                draw_segment(buffer, a, b, 0.1, 0.1, char=char)
            self.assertEqual(buffer.chars[3][5], "|")
            self.assertLess(buffer.depth[3][5], 11)
            buffers.append(buffer.lines())
        self.assertEqual(*buffers)

    def test_perspective_depth_interpolation_at_crossing(self):
        buffer = DepthBuffer(11, 5)
        draw_segment(buffer, (0, 2, 10, 1), (10, 2, 30, 1), 0.01, 0.01, char="A")
        draw_segment(buffer, (5, 0, 18, 1), (5, 4, 18, 1), 0.01, 0.01, char="B")
        # Perspective depth at midpoint is 15 (harmonic), in front of 18.
        self.assertEqual(buffer.chars[2][5], "A")

    def test_tree_segment_reordering_preserves_occlusion(self):
        reversed_tree = replace(self.tree, segments=tuple(reversed(self.tree.segments)))
        self.assertEqual(frame_bytes(self.tree, RenderOptions()),
                         frame_bytes(reversed_tree, RenderOptions()))

    def test_offscreen_line_is_clipped_and_invalid_writes_ignored(self):
        buffer = DepthBuffer(10, 5)
        draw_segment(buffer, (-1e9, 2, 20, 1), (1e9, 2, 20, 1), 0.01, 0.01, char="-")
        self.assertEqual(buffer.lines()[2], "-" * 10)
        before = buffer.lines()
        buffer.put(-1, 0, 0, "x")
        buffer.put(0, 0, math.nan, "x")
        self.assertEqual(before, buffer.lines())

    def test_extreme_valid_views_are_finite_and_bounded(self):
        for mode in ("2d", "3d", "4d"):
            options = RenderOptions(mode=mode, width=9, height=3, zoom=8,
                                    yaw=1e308, pitch=-1e308, angle4=1e308, time=1e308)
            self.assertEqual(len(frame_bytes(self.tree, options)), 30)

    def test_invalid_sizes_and_floats_rejected(self):
        for kwargs in ({"width": 0}, {"height": -1}, {"width": 501}, {"height": 201},
                       {"zoom": 0}, {"aspect": 0}, {"time": math.inf}, {"yaw": math.nan}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                RenderOptions(**kwargs)
