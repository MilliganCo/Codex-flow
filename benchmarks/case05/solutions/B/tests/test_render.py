from dataclasses import replace
import math
from pathlib import Path
import unittest

from ascii_tree.geometry import Camera
from ascii_tree.model import generate_tree
from ascii_tree.render import Raster, ScreenPoint, export_frame, frame_bytes, render
from tests.support import temporary_directory


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_deterministic_frames_all_modes_and_sizes(self):
        for width, height in ((80, 30), (100, 40), (1, 1), (2, 3), (12, 5)):
            for mode in ("2d", "3d", "4d"):
                with self.subTest(size=(width, height), mode=mode):
                    camera = Camera(width, height, mode, angle4d=35)
                    frame = render(self.tree, camera)
                    self.assertEqual(frame, render(self.tree, camera))
                    self.assertEqual(len(frame), height)
                    self.assertTrue(all(len(row) == width for row in frame))
                    data = frame_bytes(frame)
                    self.assertEqual(len(data), (width + 1) * height)
                    self.assertNotIn(b"\x1b", data)
                    self.assertNotIn(b"\r", data)
                    self.assertTrue(all(32 <= b <= 126 for row in data.splitlines() for b in row))

    def test_various_seeds_change_image(self):
        images = {frame_bytes(render(generate_tree(seed), Camera())) for seed in (7, 42, 99)}
        self.assertEqual(len(images), 3)

    def test_camera_rotation_changes_shape_not_just_translation(self):
        def occupied(camera):
            pixels = {(x, y) for y, row in enumerate(render(self.tree, camera))
                      for x, char in enumerate(row) if char != " "}
            left, top = min(x for x, y in pixels), min(y for x, y in pixels)
            return {(x - left, y - top) for x, y in pixels}
        a = occupied(Camera(yaw=0, pitch=0))
        b = occupied(Camera(yaw=70, pitch=20))
        self.assertGreater(len(a ^ b), 150)

    def test_4d_angle_changes_frame_on_same_tree(self):
        base = Camera(mode="4d", angle4d=0)
        a = render(self.tree, base)
        b = render(self.tree, replace(base, angle4d=55))
        self.assertGreater(sum(x != y for row_a, row_b in zip(a, b)
                               for x, y in zip(row_a, row_b)), 150)
        self.assertEqual(a, render(self.tree, replace(base, angle4d=360)))
        self.assertNotEqual(a, render(self.tree, Camera(mode="3d")))

    def test_2d_has_connected_wood_and_readable_trunk(self):
        frame = render(self.tree, Camera(mode="2d"))
        wood = {(x, y) for y, row in enumerate(frame) for x, ch in enumerate(row)
                if ch in "|/\\_:oO%#@"}
        start = max(wood, key=lambda p: p[1])
        seen, stack = {start}, [start]
        while stack:
            x, y = stack.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    point = (x + dx, y + dy)
                    if point in wood and point not in seen:
                        seen.add(point)
                        stack.append(point)
        # Some branches may be obscured by leaves; most wood joins the trunk.
        self.assertGreater(len(seen) / len(wood), 0.75)
        self.assertGreater(max(y for x, y in seen) - min(y for x, y in seen), 20)

    def test_2d_bare_branch_silhouette_fully_connected(self):
        frame = render(replace(self.tree, leaves=()), Camera(mode="2d"))
        pixels = {(x, y) for y, row in enumerate(frame) for x, ch in enumerate(row) if ch != " "}
        seen = {next(iter(pixels))}
        stack = list(seen)
        while stack:
            x, y = stack.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    p = (x + dx, y + dy)
                    if p in pixels and p not in seen:
                        seen.add(p)
                        stack.append(p)
        self.assertEqual(seen, pixels)

    def test_2d_wind_is_deterministic_and_changes_frame(self):
        camera = Camera(mode="2d", time=0.9)
        self.assertEqual(render(self.tree, camera), render(self.tree, camera))
        self.assertNotEqual(render(self.tree, camera), render(self.tree, replace(camera, time=0)))

    def test_export_preserves_exact_frame_bytes(self):
        with temporary_directory() as directory:
            path = Path(directory) / "frame.txt"
            lines = render(self.tree, Camera(80, 30))
            export_frame(path, lines)
            self.assertEqual(path.read_bytes(), frame_bytes(lines))

    def test_export_rejects_ansi_unicode_and_ragged_rows(self):
        for lines in (("abc", "a"), ("\x1b[0m",), ("\u2588",), ("a\t",)):
            with self.assertRaises(ValueError):
                frame_bytes(lines)

    def test_zoom_changes_frame_and_extreme_views_stay_safe(self):
        self.assertNotEqual(render(self.tree, Camera()), render(self.tree, Camera(zoom=1.6)))
        for angle in (90, 180, 270):
            camera = Camera(8, 3, "4d", yaw=angle, pitch=85,
                            angle4d=angle, zoom=5, aspect=4)
            data = frame_bytes(render(self.tree, camera))
            self.assertEqual(len(data), 27)


class OcclusionTests(unittest.TestCase):
    def test_near_segment_wins_independent_of_draw_order(self):
        def crossing(reverse):
            raster = Raster(21, 11)
            near = (ScreenPoint(10, 1, 6, 1), ScreenPoint(10, 9, 6, 1), "@")
            far = (ScreenPoint(1, 5, 12, 1), ScreenPoint(19, 5, 12, 1), ".")
            for a, b, glyph in ((far, near) if reverse else (near, far)):
                raster.segment(a, b, 0.3, 0.3, 2, glyph)
            return raster
        a, b = crossing(False), crossing(True)
        self.assertEqual(a.lines(), b.lines())
        self.assertEqual(a.chars[5][10], "@")
        self.assertLess(a.depth[5][10], 7)
        self.assertEqual(a.chars[5][3], ".")

    def test_interpolated_depth_changes_visibility_along_segment(self):
        raster = Raster(21, 11)
        raster.segment(ScreenPoint(1, 5, 12, 1), ScreenPoint(19, 5, 4, 1),
                       0.1, 0.1, 2, "#")
        raster.segment(ScreenPoint(1, 5, 8, 1), ScreenPoint(19, 5, 8, 1),
                       0.1, 0.1, 2, "o")
        self.assertEqual(raster.chars[5][2], "o")
        self.assertEqual(raster.chars[5][18], "#")

    def test_raster_clipping_and_non_finite_depth(self):
        raster = Raster(1, 1)
        for depth in (math.nan, math.inf, -1):
            raster.put(0, 0, depth, "@")
        raster.put(-1, 0, 1, "#")
        self.assertEqual(raster.lines(), (" ",))


if __name__ == "__main__":
    unittest.main()
