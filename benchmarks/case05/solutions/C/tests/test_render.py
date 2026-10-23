from dataclasses import replace
import unittest

from ascii_tree.model import generate_tree
from ascii_tree.render import DepthBuffer, Projected, RenderOptions, draw_segment, render_lines, render_text


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_exact_dimensions_and_printable_ascii(self):
        for mode in ("2d", "3d", "4d"):
            for width, height in ((80, 30), (100, 40), (1, 1), (2, 3), (12, 5)):
                with self.subTest(mode=mode, size=(width, height)):
                    text = render_text(self.tree, RenderOptions(width, height, mode))
                    lines = text.splitlines()
                    self.assertEqual(len(lines), height)
                    self.assertEqual(set(map(len, lines)), {width})
                    self.assertTrue(all(c == "\n" or 32 <= ord(c) <= 126 for c in text))
                    self.assertNotIn("\x1b", text)
                    self.assertEqual(len(text.encode("ascii")), (width + 1) * height)

    def test_all_modes_have_visible_tree(self):
        for mode in ("2d", "3d", "4d"):
            frame = render_text(self.tree, RenderOptions(mode=mode))
            self.assertGreater(sum(c not in " \n" for c in frame), 300)

    def test_render_determinism(self):
        options = RenderOptions(mode="4d", yaw=64, pitch=16, angle4=38, time=1.25)
        self.assertEqual(render_text(self.tree, options), render_text(generate_tree(42), options))

    def test_seeds_change_frames(self):
        self.assertNotEqual(render_text(self.tree, RenderOptions()), render_text(generate_tree(43), RenderOptions()))

    def test_3d_orbit_and_tilt_change_silhouette(self):
        original = render_text(self.tree, RenderOptions())
        for options in (RenderOptions(yaw=118), RenderOptions(pitch=35)):
            rotated = render_text(self.tree, options)
            self.assertGreater(sum(a != b for a, b in zip(original, rotated)), 300)

    def test_2d_is_fixed_front_projection(self):
        self.assertEqual(render_text(self.tree, RenderOptions(mode="2d", yaw=0)),
                         render_text(self.tree, RenderOptions(mode="2d", yaw=123, pitch=73)))

    def test_xw_changes_frame_with_same_geometry_and_camera(self):
        first = render_text(self.tree, RenderOptions(mode="4d", angle4=0))
        second = render_text(self.tree, RenderOptions(mode="4d", angle4=45))
        self.assertGreater(sum(a != b for a, b in zip(first, second)), 300)

    def test_zoom_aspect_and_time_have_visible_effect(self):
        original = render_text(self.tree, RenderOptions())
        for options in (RenderOptions(zoom=1.5), RenderOptions(aspect=1.0), RenderOptions(time=1.5)):
            self.assertNotEqual(original, render_text(self.tree, options))

    def test_2d_wood_is_one_connected_silhouette(self):
        lines = render_lines(replace(self.tree, leaves=()), RenderOptions(mode="2d"))
        occupied = {(x, y) for y, line in enumerate(lines) for x, c in enumerate(line) if c != " "}
        visited, pending = set(), [next(iter(occupied))]
        while pending:
            p = pending.pop()
            if p in visited:
                continue
            visited.add(p)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbor = p[0] + dx, p[1] + dy
                    if neighbor in occupied and neighbor not in visited:
                        pending.append(neighbor)
        self.assertEqual(visited, occupied)

    def test_extreme_angles_zoom_and_minimum_sizes_are_bounded(self):
        for angle in (0, 90, 180, 270):
            frame = render_text(self.tree, RenderOptions(11, 4, "4d", 180, 85, angle, 8))
            self.assertEqual(len(frame), 48)

    def test_reject_invalid_or_nonfinite_parameters(self):
        for kwargs in ({"width": 0}, {"height": 201}, {"mode": "5d"}, {"zoom": 0},
                       {"yaw": float("inf")}, {"angle4": float("nan")}, {"aspect": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                RenderOptions(**kwargs)


class OcclusionTests(unittest.TestCase):
    def test_nearer_cell_wins_in_both_submission_orders(self):
        for reverse in (False, True):
            buffer = DepthBuffer(3, 3)
            samples = [(8, "F"), (2, "N")]
            for depth, char in reversed(samples) if reverse else samples:
                buffer.put(1, 1, depth, char)
            self.assertEqual(buffer.lines()[1][1], "N")

    def test_real_crossing_segments_reverse_visibility_with_depth(self):
        for reverse_order in (False, True):
            for horizontal_near in (False, True):
                buffer = DepthBuffer(21, 13)
                hd, vd = (5, 15) if horizontal_near else (15, 5)
                primitives = [(Projected(2, 6, hd, 1), Projected(18, 6, hd, 1), "H"),
                              (Projected(10, 1, vd, 1), Projected(10, 11, vd, 1), "V")]
                for a, b, glyph in reversed(primitives) if reverse_order else primitives:
                    draw_segment(buffer, a, b, 0.1, 0.1, 2, 20, glyph=glyph)
                self.assertEqual(buffer.lines()[6][10], "H" if horizontal_near else "V")

    def test_clip_and_nonfinite_depth_do_not_write(self):
        buffer = DepthBuffer(2, 2)
        for x, y, depth in ((-1, 0, 1), (0, 2, 1), (0, 0, float("nan"))):
            buffer.put(x, y, depth, "X")
        self.assertEqual(buffer.lines(), ("  ", "  "))
