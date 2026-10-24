from dataclasses import replace
import math
import unittest

from ascii_tree.geometry import Point4, Segment, Tree, generate_tree
from ascii_tree.projection import (Projector, RenderOptions, ScreenPoint,
                                   perspective4, rotate_xw, xw_matrix)
from ascii_tree.render import Raster, render_tree


class ProjectionTests(unittest.TestCase):
    def test_xw_quarter_turn_mixes_components(self):
        p = rotate_xw(Point4(2, 3, 5, 7), 90)
        for expected, actual in zip((-7, 3, 5, 2), (p.x, p.y, p.z, p.w)):
            self.assertAlmostEqual(expected, actual)

    def test_matrix_is_orthonormal_and_nondegenerate(self):
        matrix = xw_matrix(37)
        self.assertGreater(abs(matrix[0][3]), 0.5)
        for i in range(4):
            for j in range(4):
                self.assertAlmostEqual(float(i == j), sum(a * b for a, b in zip(matrix[i], matrix[j])))
        self.assertAlmostEqual(1, matrix[0][0] * matrix[3][3] - matrix[0][3] * matrix[3][0])
        original = Point4(1, 3, -5, 7)
        rotated = rotate_xw(original, 37)
        restored = rotate_xw(rotated, -37)
        for field in ("x", "y", "z", "w"):
            self.assertAlmostEqual(getattr(original, field), getattr(restored, field))

    def test_4d_perspective_and_near_plane(self):
        self.assertEqual((2, 4, 6, 2), perspective4(Point4(1, 2, 3, 5), 10))
        for w in (9.6, 10, 11):
            self.assertIsNone(perspective4(Point4(1, 2, 3, w), 10))
        self.assertIsNone(perspective4(Point4(1, 2, 3, 0), 0))

    def test_2d_ignores_camera_but_3d_uses_z(self):
        tree = generate_tree(42)
        a = Projector(tree, RenderOptions(mode="2d", yaw=0, pitch=0))
        b = Projector(tree, RenderOptions(mode="2d", yaw=90, pitch=50))
        self.assertEqual(a.project(tree.vertices[40]), b.project(tree.vertices[40]))
        camera = Projector(tree, RenderOptions(yaw=90, pitch=0))
        p1 = camera.project(Point4(0, 3, 0, 0))
        p2 = camera.project(Point4(0, 3, 2, 0))
        self.assertGreater(abs(p1.x - p2.x), 2)

    def test_nonfinite_or_unbounded_options_rejected(self):
        for fields in ({"width": 0}, {"height": 241}, {"zoom": 0}, {"aspect": 0},
                       {"yaw": math.nan}, {"angle4": math.inf}, {"time": -1}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                RenderOptions(**fields)


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_sizes_printable_ascii_no_ansi(self):
        for width, height in ((80, 30), (100, 40), (1, 1), (2, 3), (14, 5)):
            for mode in ("2d", "3d", "4d"):
                with self.subTest(size=(width, height), mode=mode):
                    frame = render_tree(self.tree, RenderOptions(width, height, mode))
                    self.assertEqual(height, len(frame.rows))
                    self.assertTrue(all(len(row) == width for row in frame.rows))
                    self.assertTrue(all(32 <= ord(c) <= 126 for row in frame.rows for c in row))
                    self.assertNotIn(b"\x1b", frame.bytes())
                    self.assertEqual((width + 1) * height, len(frame.bytes()))

    def test_byte_determinism_including_time(self):
        options = RenderOptions(mode="4d", yaw=58, pitch=17, angle4=39, time=1.25)
        a = render_tree(self.tree, options).bytes()
        self.assertEqual(a, render_tree(generate_tree(42), options).bytes())

    def test_different_seeds_different_frames(self):
        self.assertNotEqual(render_tree(self.tree).bytes(), render_tree(generate_tree(7)).bytes())

    def test_2d_wood_is_one_connected_pixel_silhouette(self):
        wood = render_tree(replace(self.tree, leaves=()), RenderOptions(mode="2d"))
        pixels = {(x, y) for y, row in enumerate(wood.rows) for x, c in enumerate(row) if c != " "}
        visited = {next(iter(pixels))}
        pending = list(visited)
        while pending:
            x, y = pending.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbour = (x + dx, y + dy)
                    if neighbour in pixels and neighbour not in visited:
                        visited.add(neighbour)
                        pending.append(neighbour)
        self.assertEqual(pixels, visited)

    def test_cell_aspect_compensates_horizontal_distance(self):
        narrow = Projector(self.tree, RenderOptions(200, 30, "2d", aspect=1))
        tall = Projector(self.tree, RenderOptions(200, 30, "2d", aspect=2))
        a, b = Point4(0, 3, 0, 0), Point4(1, 3, 0, 0)
        delta1 = narrow.project(b).x - narrow.project(a).x
        delta2 = tall.project(b).x - tall.project(a).x
        self.assertAlmostEqual(delta1 * 2, delta2)

    def test_yaw_pitch_and_xw_visibly_change_projection(self):
        for mode, changed in (("3d", {"yaw": 100}), ("3d", {"pitch": 42}),
                              ("4d", {"angle4": 65})):
            options = RenderOptions(mode=mode)
            a = render_tree(self.tree, options).bytes()
            b = render_tree(self.tree, replace(options, **changed)).bytes()
            self.assertGreater(sum(x != y for x, y in zip(a, b)), 250)

    def test_wind_time_changes_frame(self):
        a = render_tree(self.tree, RenderOptions(time=0)).bytes()
        b = render_tree(self.tree, RenderOptions(time=2)).bytes()
        self.assertNotEqual(a, b)

    def test_depth_buffer_front_wins_in_either_draw_order(self):
        for reverse in (False, True):
            raster = Raster(11, 11)
            front = (ScreenPoint(5, 1, 3, 1), ScreenPoint(5, 9, 3, 1))
            back = (ScreenPoint(1, 5, 9, 1), ScreenPoint(9, 5, 9, 1))
            for a, b in ((back, front) if reverse else (front, back)):
                raster.branch(a, b, 0.02, 0.01, 2)
            self.assertEqual("|", raster.frame().rows[5][5])
            self.assertLess(raster.depth[5][5], 3)

    def test_complete_renderer_occludes_back_branch(self):
        for front_z, expected in ((1.0, "|"), (-1.0, "-")):
            tree = Tree(0, (Point4(0, -2, front_z, 0), Point4(0, 2, front_z, 1),
                            Point4(-2, 0, -front_z, 0), Point4(2, 0, -front_z, 1)),
                        (Segment(0, 1, 0.02, 0.01, None, 2),
                         Segment(2, 3, 0.02, 0.01, None, 2)), ())
            options = RenderOptions(31, 17, yaw=0, pitch=0)
            frame = render_tree(tree, options)
            self.assertEqual(expected, frame.rows[8][15])
            self.assertEqual(frame, render_tree(replace(tree, segments=tree.segments[::-1]), options))

    def test_clipping_and_extreme_views_are_finite(self):
        for angle in (0, 90, 180, 270, 359, 1e20):
            frame = render_tree(self.tree, RenderOptions(12, 5, "4d", angle, angle, angle, 5))
            self.assertEqual(5, len(frame.rows))

    def test_raster_rejects_offscreen_and_nonfinite_depth(self):
        raster = Raster(1, 1)
        for x, y, z in ((-1, 0, 1), (1, 0, 1), (0, -1, 1), (0, 1, 1), (0, 0, math.nan)):
            raster.put(x, y, z, "#")
        self.assertEqual((" ",), raster.frame().rows)
