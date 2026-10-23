from dataclasses import replace
import math
import unittest

from ascii_tree.model import generate_tree
from ascii_tree.render import FrameBuffer, RenderOptions, render_tree


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_exact_dimensions_ascii_no_ansi_in_all_modes(self):
        for width, height in ((80, 30), (100, 40), (1, 1), (2, 2), (12, 4)):
            for mode in ("2d", "3d", "4d"):
                with self.subTest(width=width, height=height, mode=mode):
                    frame = render_tree(self.tree, RenderOptions(width=width, height=height, mode=mode))
                    self.assertEqual(len(frame.splitlines()), height)
                    self.assertTrue(all(len(row) == width for row in frame.splitlines()))
                    self.assertTrue(all(c == "\n" or 32 <= ord(c) <= 126 for c in frame))
                    self.assertNotIn("\x1b", frame)
                    self.assertEqual(len(frame.encode("ascii")), (width + 1) * height)

    def test_seed_42_same_arguments_same_bytes_including_time(self):
        for mode in ("2d", "3d", "4d"):
            options = RenderOptions(mode=mode, time=2.5)
            self.assertEqual(render_tree(self.tree, options).encode(), render_tree(generate_tree(42), options).encode())

    def test_distinct_seeds_have_distinct_frames(self):
        frames = [render_tree(generate_tree(seed)) for seed in (42, 7, 123)]
        self.assertEqual(len(set(frames)), 3)

    def test_2d_bare_skeleton_is_one_connected_raster(self):
        for seed in (7, 42, 123):
            frame = render_tree(generate_tree(seed), RenderOptions(mode="2d", foliage=False))
            occupied = {(x, y) for y, row in enumerate(frame.splitlines()) for x, char in enumerate(row) if char != " "}
            self.assertTrue(occupied)
            stack = [occupied.pop()]
            while stack:
                x, y = stack.pop()
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        neighbor = (x + dx, y + dy)
                        if neighbor in occupied:
                            occupied.remove(neighbor)
                            stack.append(neighbor)
            self.assertFalse(occupied, f"disconnected pixels at seed {seed}")

    def test_yaw_and_pitch_change_actual_tree_projection(self):
        options = RenderOptions()
        frame = render_tree(self.tree, options)
        for altered in (replace(options, yaw=100), replace(options, pitch=35)):
            rotated = render_tree(self.tree, altered)
            self.assertGreater(sum(a != b for a, b in zip(frame, rotated)), 250)
            # Different row occupancy rules out merely horizontally shifting the image.
            self.assertNotEqual([len(r.strip()) for r in frame.splitlines()],
                                [len(r.strip()) for r in rotated.splitlines()])

    def test_4d_xw_rotation_changes_frame(self):
        options = RenderOptions(mode="4d")
        before = render_tree(self.tree, options)
        after = render_tree(self.tree, replace(options, angle4d=35))
        self.assertGreater(sum(a != b for a, b in zip(before, after)), 250)
        self.assertNotEqual(before, render_tree(self.tree, replace(options, mode="3d")))

    def test_saved_4d_views_have_vertical_breathing_room(self):
        for angle in (0, 35):
            rows = render_tree(self.tree, RenderOptions(mode="4d", angle4d=angle)).splitlines()
            self.assertFalse(rows[0].strip())
            self.assertFalse(rows[-1].strip())

    def test_rotation_full_turn_returns_same_frame(self):
        options = RenderOptions(mode="4d", angle4d=17, yaw=20)
        self.assertEqual(render_tree(self.tree, options), render_tree(self.tree, replace(options, angle4d=377, yaw=380)))

    def test_zoom_and_aspect_change_coverage(self):
        options = RenderOptions()
        frame = render_tree(self.tree, options)
        self.assertNotEqual(frame, render_tree(self.tree, replace(options, zoom=1.5)))
        self.assertNotEqual(frame, render_tree(self.tree, replace(options, aspect=1)))

    def test_occlusion_crossing_segments_independent_of_submission_order(self):
        # Far horizontal F crosses near vertical N at cell (10, 5).
        far = ((2, 5, 40, 0.7), (18, 5, 40, 0.7), "F")
        near = ((10, 1, 20, 0.7), (10, 9, 20, 0.7), "N")
        frames = []
        for segments in ((far, near), (near, far)):
            buffer = FrameBuffer(21, 11)
            for a, b, char in segments:
                buffer.capsule(a, b, char)
            self.assertEqual(buffer.cells[5][10], "N")
            self.assertEqual(buffer.cells[5][3], "F")
            frames.append(buffer.text())
        self.assertEqual(*frames)
        # Swap actual depths: the previously far branch must now win.
        buffer = FrameBuffer(21, 11)
        buffer.capsule((2, 5, 10, 0.7), (18, 5, 10, 0.7), "F")
        buffer.capsule(*near)
        self.assertEqual(buffer.cells[5][10], "F")

    def test_depth_varies_along_slanted_segment(self):
        buffer = FrameBuffer(21, 11)
        buffer.capsule((1, 5, 15, 0.5), (19, 5, 45, 0.5), "A")
        buffer.capsule((1, 5, 30, 0.5), (19, 5, 30, 0.5), "B")
        self.assertEqual(buffer.cells[5][2], "A")
        self.assertEqual(buffer.cells[5][18], "B")

    def test_offscreen_capsules_and_nonfinite_depth_are_safe(self):
        buffer = FrameBuffer(3, 2)
        buffer.capsule((-10000, -10000, 5, 0.5), (-9000, -9000, 5, 0.5), "X")
        buffer.put(0, 0, math.nan, "X")
        self.assertEqual(buffer.text(), "   \n   \n")

    def test_extreme_valid_options_are_safe(self):
        for angle in (0, 90, 180, 270):
            frame = render_tree(self.tree, RenderOptions(width=8, height=3, mode="4d", angle4d=angle, pitch=80, zoom=5))
            self.assertEqual(len(frame), 27)

    def test_invalid_options_rejected(self):
        for options in (RenderOptions(width=0), RenderOptions(height=251), RenderOptions(mode="5d"),
                        RenderOptions(yaw=math.nan), RenderOptions(zoom=math.inf), RenderOptions(aspect=0)):
            with self.subTest(options=options), self.assertRaises(ValueError):
                render_tree(self.tree, options)


if __name__ == "__main__":
    unittest.main()
