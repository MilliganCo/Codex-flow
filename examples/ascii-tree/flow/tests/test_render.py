from dataclasses import replace
import math
from pathlib import Path
import tempfile
import unittest

from ascii_tree.geometry import camera, project4, transform4, xw_matrix
from ascii_tree.model import generate_tree
from ascii_tree.render import Projector, Raster, RenderOptions, ScreenPoint, draw_segment, render, write_frame


class GeometryTests(unittest.TestCase):
    def test_xw_quarter_turn_mixes_w_and_x(self):
        point = transform4((2, 3, 5, 7), xw_matrix(math.pi / 2))
        for actual, expected in zip(point, (-7, 3, 5, 2)):
            self.assertAlmostEqual(actual, expected)

    def test_xw_rotation_is_orthogonal_and_invertible(self):
        for angle in (0, 0.7, math.pi / 2, math.pi, 3.8):
            matrix = xw_matrix(angle)
            for i in range(4):
                for j in range(4):
                    self.assertAlmostEqual(sum(matrix[i][k] * matrix[j][k] for k in range(4)), float(i == j))
            p = (0.3, -0.2, 0.7, 0.8)
            restored = transform4(transform4(p, matrix), xw_matrix(-angle))
            for a, b in zip(p, restored):
                self.assertAlmostEqual(a, b)
            # The only nontrivial 2x2 block has determinant +1.
            self.assertAlmostEqual(matrix[0][0] * matrix[3][3] - matrix[0][3] * matrix[3][0], 1)

    def test_4d_perspective_singularity_clipped(self):
        self.assertIsNone(project4((0, 0, 0, 4), 0))
        self.assertIsNone(project4((0, 0, 0, 5), 0))
        result = project4((1, 2, 3, 0), 0)
        self.assertEqual(result, ((1, 2, 3), 1))

    def test_camera_yaw_changes_z(self):
        x, y, z = camera((1, 2, 0), math.pi / 2, 0)
        self.assertAlmostEqual(x, 0)
        self.assertEqual(y, 2)
        self.assertAlmostEqual(z, -1)


class RasterTests(unittest.TestCase):
    def test_depth_order_independent(self):
        for samples in (((6, "F"), (3, "N")), ((3, "N"), (6, "F"))):
            r = Raster(5, 5)
            for depth, char in samples:
                r.put(2, 2, depth, char)
            self.assertEqual(r.cells[2][2], "N")

    def test_crossing_segment_occlusion_independent_of_order(self):
        near = (ScreenPoint(1, 4, 3, 10), ScreenPoint(9, 4, 3, 10))
        far = (ScreenPoint(5, 1, 6, 10), ScreenPoint(5, 7, 6, 10))
        images = []
        for pairs in ((near, far), (far, near)):
            r = Raster(11, 9)
            for a, b in pairs:
                draw_segment(r, a, b, 0.01, 0.01, 2, 1)
            self.assertEqual(r.cells[4][5], "-")
            self.assertLess(r.depth[4][5], 3.1)
            images.append(r.text())
        self.assertEqual(*images)

    def test_depth_interpolates_on_sloping_segment(self):
        r = Raster(11, 3)
        draw_segment(r, ScreenPoint(0, 1, 3, 10), ScreenPoint(10, 1, 6, 10), 0.01, 0.01, 2, 1)
        self.assertGreater(r.depth[1][5], 3)
        self.assertLess(r.depth[1][5], 6)

    def test_clipping_and_nan_do_not_write(self):
        r = Raster(1, 1)
        for x, y, d in ((-1, 0, 1), (0, 3, 1), (0, 0, math.nan)):
            r.put(x, y, d, "X")
        self.assertEqual(r.text(), " \n")


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_exact_dimensions_and_printable_ascii(self):
        for width, height in ((80, 30), (100, 40), (1, 1), (2, 3), (12, 4)):
            for mode in ("2d", "3d", "4d"):
                with self.subTest(width=width, height=height, mode=mode):
                    frame = render(self.tree, RenderOptions(width=width, height=height, mode=mode))
                    lines = frame.splitlines()
                    self.assertEqual(len(lines), height)
                    self.assertTrue(all(len(line) == width for line in lines))
                    self.assertTrue(all(32 <= ord(c) <= 126 for line in lines for c in line))
                    self.assertNotIn("\x1b", frame)

    def test_repeated_parameters_same_bytes(self):
        for mode in ("2d", "3d", "4d"):
            options = RenderOptions(mode=mode, time=1.25, angle4d=33)
            self.assertEqual(render(self.tree, options).encode("ascii"), render(generate_tree(42), options).encode("ascii"))

    def test_multiple_seeds_have_distinct_frames(self):
        frames = [render(generate_tree(seed)) for seed in (7, 42, 43, 2026)]
        self.assertEqual(len(set(frames)), len(frames))

    def test_rotation_changes_shape_not_just_translation(self):
        a = render(self.tree, RenderOptions(yaw=0))
        b = render(self.tree, RenderOptions(yaw=90))
        self.assertGreater(sum(x != y for x, y in zip(a, b)), 250)
        # Translation preserves occupied widths on each row; orbit does not.
        widths = lambda frame: [len(row.strip()) for row in frame.splitlines()]
        self.assertNotEqual(widths(a), widths(b))
        self.assertNotEqual(a, render(self.tree, RenderOptions(pitch=35)))

    def test_xw_angle_changes_4d_frame(self):
        a = render(self.tree, RenderOptions(mode="4d", angle4d=0))
        b = render(self.tree, RenderOptions(mode="4d", angle4d=65))
        self.assertGreater(sum(x != y for x, y in zip(a, b)), 250)

    def test_modes_share_geometry_and_2d_ignores_camera(self):
        snapshot = self.tree.vertices, self.tree.segments, self.tree.leaves
        frames = [render(self.tree, RenderOptions(mode=mode)) for mode in ("2d", "3d", "4d")]
        self.assertEqual(snapshot, (self.tree.vertices, self.tree.segments, self.tree.leaves))
        self.assertEqual(len(set(frames)), 3)
        self.assertEqual(frames[0], render(self.tree, RenderOptions(mode="2d", yaw=90, pitch=70)))

    def test_aspect_ratio_adjusts_horizontal_spacing(self):
        o = RenderOptions(width=200, height=30)
        a = Projector(self.tree, o).point(self.tree.vertices[0])
        b = Projector(self.tree, replace(o, aspect=1)).point(self.tree.vertices[0])
        self.assertIsNotNone(a)
        self.assertAlmostEqual(a.y, b.y)
        self.assertAlmostEqual(a.x - 99.5, 2 * (b.x - 99.5))

    def test_zoom_and_animation_time(self):
        default = render(self.tree)
        self.assertNotEqual(default, render(self.tree, RenderOptions(zoom=1.6)))
        self.assertNotEqual(default, render(self.tree, RenderOptions(time=3)))
        self.assertEqual(render(self.tree, RenderOptions(mode="2d", time=0)), render(self.tree, RenderOptions(mode="2d", time=3)))

    def test_export_lf_exact_bytes(self):
        frame = render(self.tree)
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            path = Path(directory) / "frame.txt"
            write_frame(path, frame)
            self.assertEqual(path.read_bytes(), frame.encode("ascii"))
            self.assertNotIn(b"\r", path.read_bytes())
            self.assertNotIn(b"\x1b", path.read_bytes())
            with self.assertRaises(ValueError):
                write_frame(path, "bad\x1b[0m")

    def test_extreme_angles_and_zoom_remain_bounded(self):
        for angle in (90, 180, 270, 1e100):
            frame = render(self.tree, RenderOptions(mode="4d", angle4d=angle, yaw=angle, pitch=angle, zoom=5))
            self.assertEqual(len(frame), 4040)
        frame = render(self.tree, RenderOptions(mode="4d", angle4d=1e308, yaw=1e308, time=1e308))
        self.assertEqual(len(frame), 4040)

    def test_invalid_options_fail_early(self):
        for kwargs in ({"width": 0}, {"height": -1}, {"width": 100000, "height": 10000},
                       {"yaw": math.nan}, {"time": math.inf}, {"mode": "5d"},
                       {"zoom": 0}, {"aspect": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                RenderOptions(**kwargs)
