from dataclasses import replace
import math
from pathlib import Path
import tempfile
import unittest

from ascii_tree.geometry import generate_tree
from ascii_tree.projection import ScreenPoint, View
from ascii_tree.render import Raster, render_tree


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_frames_sizes_ascii_and_seed_42_determinism(self):
        for mode in ("2d", "3d", "4d"):
            for width, height in ((80, 30), (100, 40), (1, 1), (2, 2), (12, 5)):
                with self.subTest(mode=mode, size=(width, height)):
                    frame = render_tree(self.tree, width, height, View(mode=mode))
                    self.assertEqual((width, height), (frame.width, frame.height))
                    self.assertTrue(all(len(row) == width for row in frame.rows))
                    data = frame.to_bytes()
                    self.assertEqual(height * (width + 1), len(data))
                    self.assertNotIn(b"\x1b", data)
                    self.assertTrue(all(32 <= byte <= 126 or byte == 10 for byte in data))
                    self.assertEqual(frame, render_tree(generate_tree(42), width, height, View(mode=mode)))

    def test_rotation_changes_projection_substantially(self):
        a = render_tree(self.tree, 100, 40, View(yaw=0)).to_bytes()
        b = render_tree(self.tree, 100, 40, View(yaw=90)).to_bytes()
        self.assertGreater(sum(x != y for x, y in zip(a, b)), 250)
        # Pitch affects the crown and trunk too; not a horizontal translation.
        c = render_tree(self.tree, 100, 40, View(yaw=0, pitch=40)).to_bytes()
        self.assertGreater(sum(x != y for x, y in zip(a, c)), 250)

    def test_4d_rotation_changes_projection(self):
        a = render_tree(self.tree, 100, 40, View(mode="4d", angle4d=0)).to_bytes()
        b = render_tree(self.tree, 100, 40, View(mode="4d", angle4d=35)).to_bytes()
        self.assertGreater(sum(x != y for x, y in zip(a, b)), 250)

    def test_multiple_seed_images_differ(self):
        frames = {render_tree(generate_tree(seed), 80, 30).to_bytes() for seed in (42, 43, 2026)}
        self.assertEqual(len(frames), 3)

    def test_export_exact_bytes(self):
        frame = render_tree(self.tree, 100, 40, View(mode="4d"))
        with tempfile.TemporaryDirectory(dir=".tmp") as directory:
            path = Path(directory) / "frame.txt"
            frame.save(path)
            data = path.read_bytes()
            self.assertEqual(data, frame.to_bytes())
            self.assertNotIn(b"\r", data)
            self.assertNotIn(b"\x1b", data)

    def test_crossing_segments_depth_order_independent(self):
        def draw(near_vertical, reverse):
            raster = Raster(11, 11)
            horizontal = (ScreenPoint(1, 5, 10 if near_vertical else 3, 1),
                          ScreenPoint(9, 5, 10 if near_vertical else 3, 1), "-")
            vertical = (ScreenPoint(5, 1, 3 if near_vertical else 10, 1),
                        ScreenPoint(5, 9, 3 if near_vertical else 10, 1), "|")
            items = [horizontal, vertical]
            for a, b, char in reversed(items) if reverse else items:
                raster.segment(a, b, 0.3, 0.3, 0.5, char)
            return raster.frame()
        for near_vertical in (True, False):
            a, b = draw(near_vertical, False), draw(near_vertical, True)
            self.assertEqual(a, b)
            self.assertEqual(a.rows[5][5], "|" if near_vertical else "-")

    def test_segment_depth_varies_along_its_length(self):
        raster = Raster(11, 11)
        raster.segment(ScreenPoint(1, 5, 2, 1), ScreenPoint(9, 5, 10, 1),
                       0.3, 0.3, 0.5, "A")
        raster.segment(ScreenPoint(1, 5, 4, 1), ScreenPoint(9, 5, 4, 1),
                       0.3, 0.3, 0.5, "B")
        self.assertEqual(raster.cells[5][2], "A")
        self.assertEqual(raster.cells[5][8], "B")
        # Harmonic midpoint is 3.333, so A wins here (an arithmetic midpoint would fail).
        self.assertEqual(raster.cells[5][5], "A")

    def test_wood_silhouette_connected_without_leaves(self):
        frame = render_tree(replace(self.tree, leaves=()), 100, 40, View(mode="2d"))
        filled = {(x, y) for y, row in enumerate(frame.rows) for x, c in enumerate(row) if c != " "}
        visited = {next(iter(filled))}
        pending = list(visited)
        while pending:
            x, y = pending.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    p = x + dx, y + dy
                    if p in filled and p not in visited:
                        visited.add(p)
                        pending.append(p)
        self.assertEqual(visited, filled)

    def test_thin_horizontal_branch_at_half_row_does_not_disappear(self):
        raster = Raster(11, 11)
        raster.segment(ScreenPoint(1, 5.5, 5, 1), ScreenPoint(9, 5.5, 5, 1),
                       0.01, 0.01, 0.5, "-")
        self.assertTrue(all(c == "-" for c in raster.cells[5][1:10]))

    def test_clipping_extreme_zoom_and_raster_input(self):
        for mode in ("2d", "3d", "4d"):
            frame = render_tree(self.tree, 7, 3, View(mode=mode, zoom=8, angle4d=179))
            self.assertEqual(len(frame.to_bytes()), 24)
        raster = Raster(2, 2)
        raster.segment(ScreenPoint(-1e10, -1e10, 2, 1), ScreenPoint(1e10, 1e10, 3, 1), 1, 1, 0.5)
        raster.segment(ScreenPoint(math.nan, 0, 2, 1), ScreenPoint(0, 0, 2, 1), 1, 1, 0.5)
        self.assertEqual(raster.frame().height, 2)
        for dimensions in ((0, 1), (1, 0), (-1, 3), (501, 2), (2, 241)):
            with self.assertRaises(ValueError):
                render_tree(self.tree, *dimensions)


if __name__ == "__main__":
    unittest.main()
